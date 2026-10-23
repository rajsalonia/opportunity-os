"""Regression tests for the opt-in application engine.

No real employer submissions, credentials, or personal resume bytes are used.
"""
import hashlib
import io
from datetime import datetime, timezone

import pytest
from flask import Flask, abort, session, request
from sqlalchemy import create_engine, MetaData, Table, Column, String, LargeBinary, text

from autoapply_engine import register


@pytest.fixture
def client_and_db(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET","temporary-automated-test-key-not-production")
    monkeypatch.delenv("GREENHOUSE_BOARD_KEYS_JSON",raising=False)
    monkeypatch.delenv("OPPORTUNITY_OS_CRON_TOKEN",raising=False)
    monkeypatch.delenv("ORIGINAL_RESUME_SHA256",raising=False)
    monkeypatch.delenv("OPPORTUNITY_OS_PROFILE_IMPORT_APPROVED",raising=False)
    monkeypatch.delenv("OPPORTUNITY_OS_PROFILE_PHONE",raising=False)
    monkeypatch.delenv("OPPORTUNITY_OS_PROFILE_EMAIL",raising=False)
    db=create_engine("sqlite:///"+str(tmp_path/"autotest.db"))
    with db.begin() as c:
        c.execute(text("""CREATE TABLE jobs(id TEXT PRIMARY KEY,company TEXT,title TEXT,location TEXT,
                 url TEXT,provider TEXT,description TEXT,score INTEGER,status TEXT,warnings TEXT,updated TEXT)"""))
        c.execute(text("CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT)"))
        entries=[
            ("eligible","Example","Software Engineer Intern","Bengaluru, India",
             "https://boards.greenhouse.io/example/jobs/1234","greenhouse",
             "Summer 2027 internship for students graduating 2028",92,"Discovered",""),
            ("ineligible","Another","Software Engineering Intern","London, UK",
             "https://jobs.lever.co/another/abcdef123","lever",
             "Summer 2027 internship for students graduating 2028",94,"Discovered",""),
        ]
        for j in entries:
            c.execute(text("""INSERT INTO jobs(id,company,title,location,url,provider,description,score,status,warnings,updated)
                VALUES(:id,:company,:title,:location,:url,:provider,:description,:score,:status,:warnings,:updated)"""),
                dict(zip(("id","company","title","location","url","provider","description","score","status","warnings"),j),
                     updated="2026-10-23T00:00:00Z"))
    md=MetaData()
    resume=Table("private_documents",md,Column("id",String,primary_key=True),
                 Column("name",String),Column("content",LargeBinary),Column("hash",String))
    md.create_all(db)
    app=Flask(__name__);app.secret_key="test-flask-secret"
    def owner():
        if not session.get("owner"):abort(401)
    def check_origin():
        owner()
        if request.headers.get("Origin") not in (None,"http://localhost"):abort(403)
    register(app,db,owner,check_origin,
             lambda:datetime.now(timezone.utc).isoformat(timespec="seconds"),
             lambda:True,resume)
    with app.test_client() as client:
        yield client,db
    db.dispose()


def authenticate(client):
    with client.session_transaction() as s:s["owner"]=True


def approved_profile():
    return {"first_name":"Demo","last_name":"Applicant","email":"demo@example.test",
            "phone":"+919876543210","graduation_year":"2028",
            "work_authorized_india":True,"approved_for_employer_submission":True}


def store_test_pdf(db, monkeypatch):
    pdf=b"%PDF-1.4\nTHIS IS TEST DATA, NOT A REAL RESUME"
    monkeypatch.setenv("ORIGINAL_RESUME_SHA256",hashlib.sha256(pdf).hexdigest())
    with db.begin() as c:
        c.execute(text("""INSERT INTO private_documents(id,name,content,hash)
           VALUES('original','synthetic.pdf',:data,:digest)"""),
           {"data":pdf,"digest":hashlib.sha256(pdf).hexdigest()})


def test_approval_and_safe_queue(client_and_db,monkeypatch):
    client,db=client_and_db
    assert client.get("/api/autoapply").status_code==401
    authenticate(client)
    assert client.post("/api/autoapply/prepare",headers={"Origin":"https://evil.example"}).status_code==403
    result=client.post("/api/autoapply/prepare").json
    assert result["queued"]["ready"]==1 and result["queued"]["review"]==1
    assert client.post("/api/autoapply/prepare").json["queued"]["existing"]==2
    assert client.post("/api/autoapply/run").json["attempted"]==0
    assert client.get("/api/autoapply").json["rules"]["enabled"] is False
    assert client.post("/api/autoapply/settings",json={"enabled":True}).status_code==422
    assert client.post("/api/autoapply/settings",json={"profile":approved_profile()}).status_code==200
    with db.connect() as c:
        raw=c.scalar(text("SELECT value FROM settings WHERE key='autoapply_profile_v1'"))
    assert "demo@example.test" not in raw
    assert client.post("/api/autoapply/settings",json={"enabled":True,"minimum_match":75,"max_daily":2}).status_code==200
    store_test_pdf(db,monkeypatch)
    def refuse_post(*args,**kwargs):
        raise AssertionError("Employer API must not be called without a company-issued key")
    monkeypatch.setattr("autoapply_engine.requests.post",refuse_post)
    done=client.post("/api/autoapply/run").json
    assert done["submitted"]==0
    with db.connect() as c:
        assert c.scalar(text("SELECT status FROM jobs WHERE id='eligible'"))=="Discovered"
    tasks=client.get("/api/autoapply").json["tasks"]
    assert next(t for t in tasks if t["job_id"]=="eligible")["status"]=="needs_review"
    assert client.post("/api/autoapply/approve/eligible",json={"eligibility_checked":False}).status_code==422
    assert client.post("/api/autoapply/approve/eligible",json={"eligibility_checked":True}).status_code==200
    assert client.post("/autoapply/schedule").status_code==403


def test_authorized_greenhouse_submission_and_exact_receipt(client_and_db,monkeypatch):
    client,db=client_and_db
    authenticate(client)
    client.post("/api/autoapply/prepare")
    client.post("/api/autoapply/settings",json={"profile":approved_profile()})
    client.post("/api/autoapply/settings",json={"enabled":True})
    store_test_pdf(db,monkeypatch)
    monkeypatch.setenv("GREENHOUSE_BOARD_KEYS_JSON",'{"example":"employer-test-key"}')
    calls=[]
    class Response:
        status_code=200
        def __init__(self,body):self.body=body
        def json(self):return self.body
    def fake_get(url,**kw):
        calls.append(("GET",url))
        return Response({"questions":[{"required":True,"fields":[{"name":"first_name"}]},
                                      {"required":True,"fields":[{"name":"last_name"}]},
                                      {"required":True,"fields":[{"name":"email"}]}]})
    def fake_post(url,**kw):
        assert kw["auth"]==("employer-test-key","")
        assert kw["files"]["resume"][1].startswith(b"%PDF")
        assert kw["data"]["email"]=="demo@example.test"
        calls.append(("POST",url))
        return Response({"success":True,"id":"fake-confirmation-123"})
    monkeypatch.setattr("autoapply_engine.requests.get",fake_get)
    monkeypatch.setattr("autoapply_engine.requests.post",fake_post)
    first=client.post("/api/autoapply/run").json
    assert first["submitted"]==1 and first["attempted"]==1
    assert [c[0] for c in calls]==["GET","POST"]
    with db.connect() as c:
        assert c.scalar(text("SELECT status FROM jobs WHERE id='eligible'"))=="Applied"
        assert c.scalar(text("SELECT receipt FROM application_tasks WHERE job_id='eligible'"))=="fake-confirmation-123"
    assert client.post("/api/autoapply/run").json["attempted"]==0
    assert len(calls)==2


def test_required_custom_fields_are_never_auto_answered(client_and_db,monkeypatch):
    client,db=client_and_db
    authenticate(client)
    client.post("/api/autoapply/prepare")
    client.post("/api/autoapply/settings",json={"profile":approved_profile()})
    client.post("/api/autoapply/settings",json={"enabled":True})
    store_test_pdf(db,monkeypatch)
    monkeypatch.setenv("GREENHOUSE_BOARD_KEYS_JSON",'{"example":"test-key"}')
    class Response:
        status_code=200
        def json(self):return {"questions":[{"required":True,"fields":[{"name":"visa_sponsorship"}]}]}
    monkeypatch.setattr("autoapply_engine.requests.get",lambda *a,**kw:Response())
    monkeypatch.setattr("autoapply_engine.requests.post",lambda *a,**kw:(_ for _ in ()).throw(AssertionError("Must not send")))
    result=client.post("/api/autoapply/run").json
    assert result["submitted"]==0
    assert client.get("/api/autoapply").json["tasks"][0]["status"] in ("needs_review","ready")


def test_per_job_approval_resolves_missing_year_without_inventing_answers(client_and_db,monkeypatch):
    client,db=client_and_db
    authenticate(client)
    with db.begin() as c:
        c.execute(text("UPDATE jobs SET description='Summer internship accepting suitable enrolled students' WHERE id='eligible'"))
    queued=client.post("/api/autoapply/prepare").json["queued"]
    assert queued["ready"]==0 and queued["review"]==2
    assert client.post("/api/autoapply/approve/eligible",json={"eligibility_checked":True}).status_code==200
    client.post("/api/autoapply/settings",json={"profile":approved_profile()})
    client.post("/api/autoapply/settings",json={"enabled":True})
    store_test_pdf(db,monkeypatch)
    monkeypatch.setenv("GREENHOUSE_BOARD_KEYS_JSON",'{"example":"mock-employer-key"}')
    class Response:
        status_code=200
        def __init__(self,payload):self.payload=payload
        def json(self):return self.payload
    monkeypatch.setattr("autoapply_engine.requests.get",lambda *a,**kw:Response({"questions":[]}))
    monkeypatch.setattr("autoapply_engine.requests.post",lambda *a,**kw:Response({"success":True,"id":"demo123"}))
    result=client.post("/api/autoapply/run").json
    assert result["submitted"]==1


def test_manual_review_never_overrides_explicit_year_exclusion(client_and_db,monkeypatch):
    client,db=client_and_db
    authenticate(client)
    with db.begin() as c:
        c.execute(text("UPDATE jobs SET description='Not eligible: graduating in 2028' WHERE id='eligible'"))
    client.post("/api/autoapply/prepare")
    assert client.post("/api/autoapply/approve/eligible",json={"eligibility_checked":True}).status_code==200
    client.post("/api/autoapply/settings",json={"profile":approved_profile()})
    client.post("/api/autoapply/settings",json={"enabled":True})
    store_test_pdf(db,monkeypatch)
    monkeypatch.setenv("GREENHOUSE_BOARD_KEYS_JSON",'{"example":"mock-employer-key"}')
    monkeypatch.setattr("autoapply_engine.requests.post",lambda *a,**kw:(_ for _ in ()).throw(AssertionError("No submit")))
    assert client.post("/api/autoapply/run").json["submitted"]==0
    assert client.get("/api/autoapply").json["tasks"][0]["status"]=="needs_review"


def test_explicit_worldwide_remote_is_queued_without_claiming_submission(client_and_db):
    client,db=client_and_db
    authenticate(client)
    with db.begin() as c:
        c.execute(text("UPDATE jobs SET location='Remote Worldwide' WHERE id='eligible'"))
    counts=client.post("/api/autoapply/prepare").json["queued"]
    assert counts["ready"]==1
    assert client.get("/api/autoapply").json["rules"]["enabled"] is False
    assert client.post("/api/autoapply/run").json["attempted"]==0


def test_remote_location_restrictions_stay_review_only(client_and_db):
    client,db=client_and_db
    authenticate(client)
    with db.begin() as c:
        c.execute(text("UPDATE jobs SET location='Remote USA only' WHERE id='eligible'"))
    counts=client.post("/api/autoapply/prepare").json["queued"]
    assert counts["review"]==2


def test_autofill_pack_requires_login_and_keeps_unconfirmed_marks_blank(client_and_db):
    client,db=client_and_db
    assert client.get("/api/autoapply/pack/eligible").status_code==401
    authenticate(client)
    result=client.get("/api/autoapply/pack/eligible")
    assert result.status_code==200
    assert result.json["application"]["status"]=="prepared_not_submitted"
    assert result.json["education"]["cgpa"]==""
    assert result.json["links"]["linkedin"].endswith("/rajsalonia")
    assert client.get("/api/autoapply/pack/nonexistent").status_code==404
    attachment=client.get("/api/autoapply/pack/eligible?download=1")
    assert attachment.status_code==200
    assert b"opportunity-os-autofill-pack-v1" in attachment.data


def test_professional_fields_persist_encrypted_and_reject_unverified_grade(client_and_db):
    client,db=client_and_db
    authenticate(client)
    assert client.post("/api/autoapply/settings",json={"professional":{"cgpa":"8.0"}}).status_code==422
    assert client.post("/api/autoapply/settings",json={"profile":approved_profile(),
        "professional":{"college":"Sample Institute","linkedin":"https://www.linkedin.com/in/sample",
                        "cgpa":"8.4"}}).status_code==200
    data=client.get("/api/autoapply").json
    assert data["professional_profile"]["cgpa"]=="8.4"
    assert data["profile_contact"]["email"]=="demo@example.test"
    with db.connect() as c:
        encrypted=c.scalar(text("SELECT value FROM settings WHERE key='autoapply_profile_v1'"))
    assert "Sample Institute" not in encrypted
    assert "demo@example.test" not in encrypted
    assert client.get("/api/autoapply/pack/eligible").json["education"]["cgpa"]=="8.4"
    assert client.post("/api/autoapply/settings",json={"professional":{"cgpa":"9.0 SGPA"}}).status_code==422


def test_owner_reported_manual_application_has_separate_receipt_status(client_and_db):
    client,db=client_and_db
    authenticate(client)
    client.post("/api/autoapply/prepare")
    assert client.post("/api/autoapply/confirm-manual/eligible",json={"submitted_by_owner":True}).status_code==422
    assert client.post("/api/autoapply/confirm-manual/eligible",
        json={"submitted_by_owner":True,"reference":"Sample acknowledgment email #1234"}).status_code==200
    tasks=client.get("/api/autoapply").json["tasks"]
    row=next(t for t in tasks if t["job_id"]=="eligible")
    assert row["status"]=="user_reported"
    assert row["receipt"]=="Sample acknowledgment email #1234"
    assert row["status"]!="submitted"
    with db.connect() as c:
        assert c.scalar(text("SELECT status FROM jobs WHERE id='eligible'"))=="Applied"
    assert client.post("/api/autoapply/confirm-manual/eligible",
        json={"submitted_by_owner":True,"reference":"Duplicate submission"}).status_code==409


def test_one_time_private_phone_seed_is_encrypted_and_does_not_send(client_and_db,monkeypatch):
    client,db=client_and_db
    authenticate(client)
    monkeypatch.setenv("OPPORTUNITY_OS_PROFILE_IMPORT_APPROVED","yes")
    monkeypatch.setenv("OPPORTUNITY_OS_PROFILE_PHONE","+919876543210")
    monkeypatch.setenv("OPPORTUNITY_OS_PROFILE_EMAIL","demo@example.test")
    result=client.get("/api/autoapply")
    assert result.status_code==200
    assert result.json["profile_ready"] is True
    assert result.json["profile_contact"]["phone"]=="+919876543210"
    assert result.json["rules"]["enabled"] is False
    with db.connect() as c:
        encrypted=c.scalar(text("SELECT value FROM settings WHERE key='autoapply_profile_v1'"))
    assert "+919876543210" not in encrypted
    assert "demo@example.test" not in encrypted
    assert client.post("/api/autoapply/run").json["attempted"]==0

def test_phone_seed_preserves_existing_opt_out_and_email(client_and_db,monkeypatch):
    client,db=client_and_db
    authenticate(client)
    client.post("/api/autoapply/settings",json={"profile":approved_profile()})
    monkeypatch.setenv("OPPORTUNITY_OS_PROFILE_IMPORT_APPROVED","yes")
    monkeypatch.setenv("OPPORTUNITY_OS_PROFILE_PHONE","+919876543211")
    monkeypatch.setenv("OPPORTUNITY_OS_PROFILE_EMAIL","different@example.test")
    data=client.get("/api/autoapply").json
    assert data["profile_contact"]["phone"]=="+919876543211"
    assert data["profile_contact"]["email"]=="demo@example.test"
    assert data["rules"]["enabled"] is False
