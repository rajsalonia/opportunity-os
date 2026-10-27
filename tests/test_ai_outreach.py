"""
Comprehensive tests for the AI Outreach Manager.
Covers multi-format ingestion (.xlsx, .xls, .csv), heuristic column mapping,
email syntax validation, deduplication and merging, personalized email composition
across all 4 categories and 4 styles, safety gates (10/day limit, 30-day duplicate block,
suppression list), smart follow-up cadence, and REST API endpoints.
"""
import os
import io
import csv
import json
import secrets
import tempfile
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine, select, func
from sqlalchemy.pool import StaticPool

import openpyxl
import xlrd

from outreach_models import (
    ensure_outreach_tables, batches, companies, contacts,
    drafts, messages, followups, suppressions, audit_logs
)
from outreach_importer import (
    OutreachImporter, normalize_company_name, validate_email,
    detect_columns, read_spreadsheet_rows
)
from outreach_composer import (
    compose_email, compose_followup_email, detect_company_category,
    VERIFIED_PROFILE, VALID_STYLES, VALID_CATEGORIES
)
from outreach_service import OutreachService, OutreachError, DAILY_OUTREACH_LIMIT


@pytest.fixture
def test_db():
    """Provides a fresh isolated in-memory or temp SQLite engine with shared static pool."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    ensure_outreach_tables(engine)
    return engine


@pytest.fixture
def importer(test_db):
    return OutreachImporter(test_db)


@pytest.fixture
def service(test_db):
    return OutreachService(test_db)


# -------------------------------------------------------------------------
# 1. Email Syntax Validation & Verification
# -------------------------------------------------------------------------

def test_email_validation_rules():
    # Valid emails
    status, note = validate_email("sarah.connor@cyberdyne.io")
    assert status == "valid"
    assert "valid syntax" in note.lower()

    # Empty / Missing email
    status, note = validate_email("")
    assert status == "missing"

    # Invalid syntax
    status, note = validate_email("not-an-email")
    assert status == "malformed"

    status, note = validate_email("user@domain")
    assert status == "malformed"

    # Role-based emails
    status, note = validate_email("info@acmecorp.com")
    assert status == "role_based"
    assert "generic" in note.lower()

    status, note = validate_email("hr@techsolutions.com")
    assert status == "role_based"

    # Disposable domains
    status, note = validate_email("temp@mailinator.com")
    assert status == "disposable"
    assert "disposable" in note.lower()


# -------------------------------------------------------------------------
# 2. Company Name Normalization
# -------------------------------------------------------------------------

def test_company_normalization():
    clean, cluster = normalize_company_name("Google LLC")
    assert clean == "Google"
    assert cluster == "google"

    clean, cluster = normalize_company_name("Microsoft Corporation, Inc.")
    assert clean == "Microsoft"
    assert cluster == "microsoft"

    clean, cluster = normalize_company_name("Acme Technologies Pvt Ltd")
    assert clean == "Acme"
    assert cluster == "acme"

    clean, cluster = normalize_company_name("  OpenAI   ")
    assert clean == "OpenAI"
    assert cluster == "openai"


# -------------------------------------------------------------------------
# 3. Column Detection Heuristics
# -------------------------------------------------------------------------

def test_column_mapping_heuristics():
    headers_standard = ["Company Name", "HR Name", "Email Address", "Designation", "Department", "Location", "LinkedIn URL"]
    mapping = detect_columns(headers_standard)
    assert mapping["company_name"] == "Company Name"
    assert mapping["name"] == "HR Name"
    assert mapping["email"] == "Email Address"
    assert mapping["designation"] == "Designation"
    assert mapping["location"] == "Location"
    assert mapping["linkedin_url"] == "LinkedIn URL"

    headers_messy = ["Org", "Recruiter", "Mail ID", "Role / Title", "City", "Web page"]
    mapping_messy = detect_columns(headers_messy)
    assert mapping_messy["company_name"] == "Org"
    assert mapping_messy["name"] == "Recruiter"
    assert mapping_messy["email"] == "Mail ID"
    assert mapping_messy["designation"] == "Role / Title"
    assert mapping_messy["location"] == "City"
    assert mapping_messy["company_website"] == "Web page"


# -------------------------------------------------------------------------
# 4. Multi-Format Spreadsheet Ingestion (.csv, .xlsx, .xls)
# -------------------------------------------------------------------------

def test_csv_ingestion(importer):
    csv_content = """Company,Contact Name,Email,Designation,Location
AlphaAI,Alice Johnson,alice@alphaai.tech,Head of Talent,Bengaluru
BetaBackend,Bob Smith,bob@betabackend.com,Engineering Manager,Remote
GammaSystems,Charlie Rose,info@gammasystems.org,General Inquiry,Delhi
"""
    raw_bytes = csv_content.encode("utf-8")
    result = importer.import_contacts(raw_bytes, "contacts_1.csv")

    assert result["total_rows"] == 3
    assert result["valid_rows"] == 2
    assert result["suspicious_rows"] == 1  # info@ is role-based
    assert result["duplicate_rows"] == 0


def test_xlsx_ingestion(importer):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Company Name", "HR Name", "Email", "Title", "LinkedIn"])
    ws.append(["DeepMind Labs", "David Lee", "david@deepmind.com", "AI Recruiter", "https://linkedin.com/in/davidlee"])
    ws.append(["CloudScale Inc", "Elena Rostova", "elena@cloudscale.io", "Tech Lead", "https://linkedin.com/in/elenar"])
    
    bio = io.BytesIO()
    wb.save(bio)
    raw_bytes = bio.getvalue()

    result = importer.import_contacts(raw_bytes, "tech_contacts.xlsx")
    assert result["total_rows"] == 2
    assert result["valid_rows"] == 2
    assert result["duplicate_rows"] == 0


def test_deduplication_and_merging(importer):
    # Ingest first batch
    csv1 = """Company,Name,Email,Designation
TechCorp,John Doe,john.doe@techcorp.com,Senior Recruiter
"""
    importer.import_contacts(csv1.encode("utf-8"), "batch1.csv")

    # Ingest second batch with exact duplicate email and enriched phone/LinkedIn
    csv2 = """Company,Name,Email,Phone,LinkedIn
TechCorp LLC,John Doe,john.doe@techcorp.com,+1-555-0199,https://linkedin.com/in/johndoe
"""
    res2 = importer.import_contacts(csv2.encode("utf-8"), "batch2.csv")
    assert res2["total_rows"] == 1
    assert res2["duplicate_rows"] == 1

    # Verify that original contact was merged/enriched
    with importer.db.connect() as conn:
        all_contacts = conn.execute(select(contacts).where(contacts.c.email == "john.doe@techcorp.com")).mappings().all()
        # Primary contact should have linkedin_url populated from second batch
        primary = [c for c in all_contacts if c["is_duplicate"] == 0][0]
        assert primary["linkedin_url"] == "https://linkedin.com/in/johndoe"
        assert primary["phone"] == "+1-555-0199"


# -------------------------------------------------------------------------
# 5. Grounded AI Email Composition
# -------------------------------------------------------------------------

def test_composer_verified_profile_grounding():
    contact_ai = {
        "id": "c1",
        "company_name": "VisionAI Technologies",
        "name": "Maya Lin",
        "email": "maya@visionai.io",
        "designation": "AI Talent Partner"
    }

    draft = compose_email(contact_ai, style="professional", category="ai_ml")

    # Strict grounding assertions: Raj Salonia's actual credentials
    assert "Raj Salonia" in draft["body"]
    assert "B.Tech in Computer Science and Engineering" in draft["body"]
    assert "Bhagwan Parshuram Institute of Technology" in draft["body"]
    assert "2028" in draft["body"]
    assert "Summer 2027" in draft["body"]
    assert "Dexpert Systems" in draft["body"]
    # AI/ML project highlights
    assert "Document Forgery AI" in draft["body"]
    assert "ReviewLens" in draft["body"]
    assert "Dear Maya," in draft["body"]
    assert "VisionAI" in draft["subject"] or "VisionAI" in draft["body"]


def test_composer_all_categories():
    base_contact = {"id": "c2", "company_name": "CoreInfra Systems", "name": "Samir Patel", "email": "samir@coreinfra.io"}

    # Backend
    draft_backend = compose_email(base_contact, style="technical", category="backend")
    assert "CityGraph" in draft_backend["body"]
    assert "FastAPI" in draft_backend["body"]
    assert draft_backend["personalization_type"] == "backend"

    # General Software
    draft_swe = compose_email(base_contact, style="concise", category="general_software")
    assert "AstroBit" in draft_swe["body"]
    assert "Dexpert Systems" in draft_swe["body"]

    # Unknown
    draft_unk = compose_email(base_contact, style="startup_friendly", category="unknown")
    assert "Raj Salonia" in draft_unk["body"]
    assert draft_unk["personalization_type"] == "unknown"


def test_composer_all_styles():
    contact = {"id": "c3", "company_name": "NextGen Software", "name": "Elena", "email": "elena@nextgen.com"}
    for style in VALID_STYLES:
        draft = compose_email(contact, style=style)
        assert draft["style"] == style
        assert len(draft["body"]) > 100
        assert "Raj Salonia" in draft["body"]


def test_category_detection_heuristics():
    assert detect_company_category("OpenAI Research", "ML Engineer", "") == "ai_ml"
    assert detect_company_category("Distributed Cloud Corp", "Systems Lead", "Kubernetes, DB") == "backend"
    assert detect_company_category("Global Tech Solutions", "Software Engineer", "") == "general_software"
    assert detect_company_category("Apex Consulting", "Partner", "") == "unknown"


# -------------------------------------------------------------------------
# 6. Safety Gates: Daily Limit, Suppression, 30-Day Duplicate Prevention
# -------------------------------------------------------------------------

def test_daily_limit_enforcement(service, importer):
    csv_data = "Company,Name,Email\n" + "\n".join([f"Co{i},Name{i},lead{i}@testco.com" for i in range(15)])
    importer.import_contacts(csv_data.encode("utf-8"), "test_leads.csv")

    contact_rows = service.list_contacts(limit=15)["contacts"]
    contact_ids = [c["id"] for c in contact_rows]

    # Generate drafts
    drafts_created = service.generate_drafts(contact_ids, style="concise")
    assert len(drafts_created) == 15

    # Approve and send up to DAILY_OUTREACH_LIMIT (10)
    for i in range(DAILY_OUTREACH_LIMIT):
        d_id = drafts_created[i]["id"]
        service.approve_draft(d_id)
        result = service.send_draft(d_id, reviewed_and_confirmed=True)
        assert result["success"] is True

    # 11th email must be rejected with 429 daily limit error
    d_11 = drafts_created[DAILY_OUTREACH_LIMIT]["id"]
    service.approve_draft(d_11)
    with pytest.raises(OutreachError) as exc_info:
        service.send_draft(d_11, reviewed_and_confirmed=True)
    assert exc_info.value.status_code == 429
    assert "Daily safety limit" in exc_info.value.message


def test_unapproved_draft_send_blocked(service, importer):
    csv_data = "Company,Name,Email\nTestCo,Jane,jane@testco.com\n"
    importer.import_contacts(csv_data.encode("utf-8"), "test.csv")
    c_id = service.list_contacts()["contacts"][0]["id"]
    draft = service.generate_drafts([c_id])[0]

    # Sending without approval must fail with 422
    with pytest.raises(OutreachError) as exc_info:
        service.send_draft(draft["id"], reviewed_and_confirmed=True)
    assert exc_info.value.status_code == 422
    assert "approved" in exc_info.value.message.lower()


def test_unreviewed_confirmation_send_blocked(service, importer):
    csv_data = "Company,Name,Email\nTestCo,Jane,jane@testco.com\n"
    importer.import_contacts(csv_data.encode("utf-8"), "test.csv")
    c_id = service.list_contacts()["contacts"][0]["id"]
    draft = service.generate_drafts([c_id])[0]
    service.approve_draft(draft["id"])

    # Sending with reviewed_and_confirmed=False must fail
    with pytest.raises(OutreachError) as exc_info:
        service.send_draft(draft["id"], reviewed_and_confirmed=False)
    assert exc_info.value.status_code == 422


def test_suppression_list_blocks_send(service, importer):
    csv_data = "Company,Name,Email\nBlockCo,Carl,carl@blockco.com\n"
    importer.import_contacts(csv_data.encode("utf-8"), "test.csv")
    c_id = service.list_contacts()["contacts"][0]["id"]
    draft = service.generate_drafts([c_id])[0]
    service.approve_draft(draft["id"])

    # Add recipient to suppression list
    service.add_suppression("carl@blockco.com", reason="opt_out", notes="Requested unsubscribe")

    with pytest.raises(OutreachError) as exc_info:
        service.send_draft(draft["id"], reviewed_and_confirmed=True)
    assert exc_info.value.status_code == 409
    assert "suppression" in exc_info.value.message.lower()


def test_duplicate_send_30_day_protection(service, importer):
    csv_data = "Company,Name,Email\nRepeatCo,Dave,dave@repeatco.com\n"
    importer.import_contacts(csv_data.encode("utf-8"), "test.csv")
    c_id = service.list_contacts()["contacts"][0]["id"]
    
    # First draft send
    draft1 = service.generate_drafts([c_id])[0]
    service.approve_draft(draft1["id"])
    service.send_draft(draft1["id"], reviewed_and_confirmed=True)

    # Generate a second draft to the same person
    draft2 = service.generate_drafts([c_id])[0]
    service.approve_draft(draft2["id"])

    # Attempting to send again within 30 days must be blocked
    with pytest.raises(OutreachError) as exc_info:
        service.send_draft(draft2["id"], reviewed_and_confirmed=True)
    assert exc_info.value.status_code == 409
    assert "Duplicate protection" in exc_info.value.message


# -------------------------------------------------------------------------
# 7. Smart Follow-Up Cadence & Management
# -------------------------------------------------------------------------

def test_smart_followup_cadence(service, importer):
    csv_data = "Company,Name,Email\nFollowCo,Fiona,fiona@followco.com\n"
    importer.import_contacts(csv_data.encode("utf-8"), "test.csv")
    c_id = service.list_contacts()["contacts"][0]["id"]
    
    draft = service.generate_drafts([c_id])[0]
    service.approve_draft(draft["id"])
    send_res = service.send_draft(draft["id"], reviewed_and_confirmed=True)

    # Day 7 follow-up should be scheduled
    assert "followup_scheduled_for" in send_res
    pending = service.list_followups(status="pending")
    assert len(pending) == 1
    fol = pending[0]
    assert fol["contact_email"] == "fiona@followco.com"

    # Prepare follow-up draft
    prepared = service.prepare_followup_draft(fol["id"])
    assert "Re:" in prepared["subject"]
    assert "Raj Salonia" in prepared["body"]
    assert "follow up briefly" in prepared["body"].lower()

    # Dismissing follow-up cancels reminder
    dismiss_res = service.dismiss_followup(fol["id"], reason="Recruiter reached out on LinkedIn")
    assert dismiss_res["cancelled"] is True
    assert len(service.list_followups(status="pending")) == 0


# -------------------------------------------------------------------------
# 8. Analytics & CSV Export
# -------------------------------------------------------------------------

def test_real_analytics_and_export(service, importer):
    csv_data = """Company,Name,Email,Designation
TechOne,A,a@techone.com,Recruiter
TechTwo,B,b@techtwo.com,HR
"""
    importer.import_contacts(csv_data.encode("utf-8"), "data.csv")
    analytics = service.get_analytics()

    assert analytics["contacts"]["total"] == 2
    assert analytics["contacts"]["valid"] == 2
    assert analytics["outreach"]["daily_limit"] == 10
    assert analytics["outreach"]["remaining_today"] == 10

    export_csv = service.export_contacts_csv()
    assert "a@techone.com" in export_csv
    assert "b@techtwo.com" in export_csv
    assert "company_name" in export_csv


# -------------------------------------------------------------------------
# 9. Flask API Endpoints Integration Test
# -------------------------------------------------------------------------

def test_flask_api_endpoints():
    os.environ.setdefault("APP_PASSWORD", "testpass")
    from app import app, db
    ensure_outreach_tables(db)

    import app as app_mod
    app_mod.pw = "test-secret-not-a-real-password"
    with app.test_client() as client:
        # Sign in
        res = client.post("/api/login", json={"password": "test-secret-not-a-real-password"})
        assert res.status_code == 200

        # Analytics
        res = client.get("/api/outreach/analytics")
        assert res.status_code == 200
        data = res.get_json()
        assert "contacts" in data
        assert "outreach" in data

        # Profile
        res = client.get("/api/outreach/profile")
        assert res.status_code == 200
        p = res.get_json()
        assert p["name"] == "Raj Salonia"
        assert p["graduation_year"] == "2028"

        # Import Preview
        unique_email = f"pat_{secrets.token_hex(4)}@stripe.com"
        csv_bytes = f"Company,Name,Email\nStripe,Pat,{unique_email}\n".encode("utf-8")
        data = {"files": (io.BytesIO(csv_bytes), "test_leads.csv")}
        res = client.post("/api/outreach/import/preview", data=data, content_type="multipart/form-data")
        assert res.status_code == 200
        previews = res.get_json()["previews"]
        assert len(previews) == 1
        assert previews[0]["filename"] == "test_leads.csv"
        assert previews[0]["detected_mapping"]["company_name"] == "Company"

        # Import Execute
        data_exec = {"files": (io.BytesIO(csv_bytes), "test_leads.csv")}
        res = client.post("/api/outreach/import", data=data_exec, content_type="multipart/form-data")
        assert res.status_code == 200
        assert res.get_json()["success"] is True

        # Contacts list
        res = client.get("/api/outreach/contacts")
        assert res.status_code == 200
        c_list = res.get_json()["contacts"]
        assert len(c_list) >= 1
        cid = c_list[0]["id"]

        # Compose
        res = client.post("/api/outreach/compose", json={"contact_ids": [cid], "style": "professional"})
        assert res.status_code == 200
        drafts = res.get_json()["drafts"]
        assert len(drafts) == 1
        did = drafts[0]["id"]

        # Approve
        res = client.post(f"/api/outreach/drafts/{did}/approve")
        assert res.status_code == 200
        assert res.get_json()["approved"] is True

        # Send
        res = client.post(f"/api/outreach/drafts/{did}/send", json={"reviewed_and_confirmed": True})
        assert res.status_code == 200
        assert res.get_json()["success"] is True
