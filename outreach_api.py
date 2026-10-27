"""
AI Outreach Manager - Flask API Blueprint.
Provides REST endpoints for spreadsheet ingestion, candidate directory,
AI email composition, review/approval workflow, Gmail outreach, follow-ups,
suppression management, and real database analytics.
"""
import json
import secrets
from typing import Dict, Any, List, Optional
from flask import Blueprint, request, jsonify, Response, abort
from sqlalchemy import select

from outreach_models import ensure_outreach_tables
from outreach_importer import OutreachImporter
from outreach_service import OutreachService, OutreachError
from outreach_composer import VERIFIED_PROFILE, VALID_STYLES, VALID_CATEGORIES


def register(app, db, owner_guard, origin_guard, now_fn=None, send_mail_fn=None):
    """Registers the Outreach API Blueprint with Flask application."""
    ensure_outreach_tables(db)
    service = OutreachService(db)
    importer = OutreachImporter(db)

    bp = Blueprint("outreach", __name__, url_prefix="/api/outreach")

    @bp.before_request
    def authenticate():
        owner_guard()

    @bp.get("/analytics")
    def get_analytics():
        """Returns live outreach pipeline statistics and safety limits."""
        return jsonify(service.get_analytics())

    @bp.get("/profile")
    def get_profile():
        """Returns verified applicant profile with 100% editable fields."""
        return jsonify(VERIFIED_PROFILE)

    @bp.post("/import/preview")
    def preview_import():
        """
        Parses uploaded spreadsheets (.xlsx, .xls, .csv), detects column mappings,
        and returns sample rows for user inspection prior to insertion.
        """
        origin_guard()
        uploaded_files = request.files.getlist("files")
        if not uploaded_files:
            return jsonify(error="No files provided for preview"), 400

        previews = []
        for f in uploaded_files:
            filename = f.filename or "unknown_file"
            raw_bytes = f.read()
            if not raw_bytes:
                continue

            try:
                headers, sample_rows, total_rows = importer.inspect_spreadsheet(filename, raw_bytes)
                mapping = importer.detect_column_mapping(headers)
                previews.append({
                    "filename": filename,
                    "file_size": len(raw_bytes),
                    "headers": headers,
                    "detected_mapping": mapping,
                    "sample_rows": sample_rows[:5],
                    "total_rows": total_rows
                })
            except Exception as e:
                previews.append({
                    "filename": filename,
                    "error": f"Failed to parse file: {str(e)}"
                })

        return jsonify(previews=previews)

    @bp.post("/import")
    def execute_import():
        """
        Executes multi-file spreadsheet ingestion with optional manual column mapping overrides.
        Validates syntax, normalizes company names, merges duplicates, and persists to DB.
        """
        origin_guard()
        uploaded_files = request.files.getlist("files")
        if not uploaded_files:
            return jsonify(error="No files uploaded for import"), 400

        mappings_raw = request.form.get("mappings")
        mappings_by_file = {}
        if mappings_raw:
            try:
                mappings_by_file = json.loads(mappings_raw)
            except Exception:
                mappings_by_file = {}

        file_tuples = []
        for f in uploaded_files:
            filename = f.filename or "uploaded_spreadsheet"
            raw_bytes = f.read()
            if not raw_bytes:
                continue
            mapping = mappings_by_file.get(filename)
            file_tuples.append((filename, raw_bytes, mapping))

        if not file_tuples:
            return jsonify(error="No non-empty files to process"), 400

        try:
            results = importer.import_files(file_tuples)
            service.log_audit("batch_import_completed", details={"files_count": len(file_tuples)})
            return jsonify(results=results, success=True)
        except Exception as e:
            return jsonify(error=f"Import execution failed: {str(e)}"), 500

    @bp.get("/batches")
    def list_batches():
        """Returns all import batches with row metrics and mappings."""
        from outreach_models import batches
        with db.connect() as conn:
            rows = conn.execute(select(batches).order_by(batches.c.created_at.desc())).mappings().all()
            return jsonify(batches=[dict(r) for r in rows])

    @bp.get("/contacts")
    def list_contacts():
        """Paginated list of recruiter and HR contacts with search and status filtering."""
        q = request.args.get("q", "")
        status = request.args.get("status", "")
        email_status = request.args.get("email_status", "")
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))

        result = service.list_contacts(
            q=q,
            status=status,
            email_status=email_status,
            limit=limit,
            offset=offset
        )
        return jsonify(result)

    @bp.get("/contacts/<contact_id>")
    def get_contact(contact_id: str):
        """Returns complete contact record, including drafts, messages, and follow-ups."""
        detail = service.get_contact_detail(contact_id)
        if not detail:
            return jsonify(error="Contact not found"), 404
        return jsonify(contact=detail)

    @bp.post("/compose")
    def compose_drafts():
        """
        Generates personalized, grounded email drafts for selected contacts.
        Does not invent facts or metrics.
        """
        origin_guard()
        payload = request.get_json(silent=True) or {}
        contact_ids = payload.get("contact_ids", [])
        if not contact_ids or not isinstance(contact_ids, list):
            return jsonify(error="A non-empty list of contact_ids is required"), 400

        style = payload.get("style", "professional")
        category = payload.get("category")
        profile = payload.get("profile")

        drafts_list = service.generate_drafts(
            contact_ids=contact_ids,
            style=style,
            category=category,
            profile=profile
        )
        return jsonify(drafts=drafts_list, count=len(drafts_list))

    @bp.get("/drafts")
    def list_drafts():
        """Lists email drafts filtered by status ('draft', 'approved', 'sent')."""
        status = request.args.get("status", "")
        from outreach_models import drafts, contacts
        with db.connect() as conn:
            stmt = select(drafts, contacts.c.name.label("contact_name"), contacts.c.email.label("contact_email"), contacts.c.company_name).select_from(
                drafts.join(contacts, drafts.c.contact_id == contacts.c.id)
            )
            if status:
                stmt = stmt.where(drafts.c.status == status)
            rows = conn.execute(stmt.order_by(drafts.c.created_at.desc())).mappings().all()
            return jsonify(drafts=[dict(r) for r in rows])

    @bp.patch("/drafts/<draft_id>")
    def update_draft(draft_id: str):
        """Allows complete manual edits of subject, body, style, or attachment flag."""
        origin_guard()
        payload = request.get_json(silent=True) or {}
        try:
            updated = service.update_draft(draft_id, payload)
            return jsonify(draft=updated)
        except OutreachError as oe:
            return jsonify(error=oe.message), oe.status_code

    @bp.post("/drafts/<draft_id>/approve")
    def approve_draft(draft_id: str):
        """Explicitly approves a draft. Required prior to sending."""
        origin_guard()
        try:
            approved = service.approve_draft(draft_id, approved_by="owner")
            return jsonify(draft=approved, approved=True)
        except OutreachError as oe:
            return jsonify(error=oe.message), oe.status_code

    @bp.post("/drafts/<draft_id>/send")
    def send_draft(draft_id: str):
        """
        Sends an approved draft through Gmail.
        Requires explicit `reviewed_and_confirmed: true` flag.
        Enforces daily 10-email limit, duplicate suppression, and schedules Day 7 follow-up.
        """
        origin_guard()
        payload = request.get_json(silent=True) or {}
        reviewed = bool(payload.get("reviewed_and_confirmed"))

        try:
            result = service.send_draft(draft_id, reviewed_and_confirmed=reviewed, send_fn=send_mail_fn)
            return jsonify(result)
        except OutreachError as oe:
            return jsonify(error=oe.message), oe.status_code
        except Exception as e:
            return jsonify(error=f"Outreach send error: {str(e)}"), 500

    @bp.get("/followups")
    def list_followups():
        """Lists pending smart follow-up reminders."""
        status = request.args.get("status", "pending")
        return jsonify(followups=service.list_followups(status=status))

    @bp.post("/followups/<followup_id>/prepare")
    def prepare_followup(followup_id: str):
        """Prepares a non-intrusive follow-up draft for user review."""
        origin_guard()
        try:
            res = service.prepare_followup_draft(followup_id)
            return jsonify(res)
        except OutreachError as oe:
            return jsonify(error=oe.message), oe.status_code

    @bp.post("/followups/<followup_id>/dismiss")
    def dismiss_followup(followup_id: str):
        """Cancels a scheduled follow-up reminder."""
        origin_guard()
        payload = request.get_json(silent=True) or {}
        reason = payload.get("reason", "dismissed_by_user")
        try:
            res = service.dismiss_followup(followup_id, reason=reason)
            return jsonify(res)
        except OutreachError as oe:
            return jsonify(error=oe.message), oe.status_code

    @bp.get("/suppressions")
    def list_suppressions():
        """Returns all suppressed emails and domains."""
        return jsonify(suppressions=service.list_suppressions())

    @bp.post("/suppressions")
    def add_suppression():
        """Adds an email address to the suppression list."""
        origin_guard()
        payload = request.get_json(silent=True) or {}
        email = payload.get("email", "")
        reason = payload.get("reason", "opt_out")
        notes = payload.get("notes", "")

        try:
            res = service.add_suppression(email, reason=reason, notes=notes)
            return jsonify(res)
        except OutreachError as oe:
            return jsonify(error=oe.message), oe.status_code

    @bp.get("/export")
    def export_contacts():
        """Exports contacts as a clean CSV download."""
        q = request.args.get("q", "")
        status = request.args.get("status", "")
        csv_data = service.export_contacts_csv(q=q, status=status)
        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=opportunity_os_contacts.csv"}
        )

    app.register_blueprint(bp)
