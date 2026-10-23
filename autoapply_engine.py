"""Private, opt-in Opportunity OS application queue.

Only an employer-authorized Greenhouse Job Board API integration can submit.
Lever/Ashby and unrecognized forms remain in a review queue. Never store
provider credentials, applicant details or the resume in the Git repository.
"""
import base64
import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

import requests
from cryptography.fernet import Fernet, InvalidToken
from flask import request, abort
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, InterfaceError

_SAFE_FIELDS = {"first_name", "last_name", "email", "phone", "resume"}
_BAD_LOCATION = re.compile(r"\b(USA|United States|Canada|Europe|London|Berlin|Germany|Australia|Singapore|US only|UK only)\b", re.I)
_INDIA_LOCATION = re.compile(r"\b(India|Delhi|Gurugram|Gurgaon|Noida|Bengaluru|Bangalore|Hyderabad|Pune|Mumbai|Chennai|Kolkata|NCR)\b", re.I)
_BAD_YEAR = re.compile(r"\b(?:only|exclusively)\s+(?:class of |graduates? of )?202[4567]\b|must graduate (?:in|by) 202[4567]", re.I)
_GOOD_YEAR = re.compile(r"\b(?:class of|graduating(?: in)?|graduates? in|students graduating(?: in)?|expected graduation(?: in)?|graduation year)\s*[:\-]?\s*2028\b|\b2028\s*(?:graduates?|graduation|cohort|class)\b", re.I)
_EXCLUDED_2028 = re.compile(r"\b(?:not|no|excluding|ineligible|except)\b.{0,45}\b2028\b|\b2028\b.{0,40}\b(?:ineligible|excluded|not eligible)\b", re.I)
_UUID = re.compile(r"^[a-z0-9_-]{2,90}$")
_VALID_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_TERMINAL = {"Applied", "Assessment", "Interview", "Offer", "Rejected", "Closed"}

def register(app, db, owner, check_origin, now, has_persistent_db, resume_table, refresh_employers=None):
    secret = os.getenv("SESSION_SECRET", "")
    cipher = Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())) if secret else None

    def ensure():
        if not has_persistent_db():
            abort(503, description="A persistent PostgreSQL database is required for automation.")
        with db.begin() as c:
            c.execute(text("""CREATE TABLE IF NOT EXISTS application_tasks (
                job_id VARCHAR(64) PRIMARY KEY,
                fingerprint VARCHAR(64) NOT NULL UNIQUE,
                status VARCHAR(30) NOT NULL,
                reason TEXT DEFAULT '',
                receipt TEXT DEFAULT '',
                reviewed_at TEXT DEFAULT '',
                attempted_at TEXT DEFAULT '',
                updated_at TEXT DEFAULT ''
            )"""))

    def get_setting(key):
        with db.connect() as c:
            return c.scalar(text("SELECT value FROM settings WHERE key=:key"), {"key":key})

    def put_setting(key, value):
        with db.begin() as c:
            c.execute(text("""INSERT INTO settings(key,value) VALUES(:k,:v)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value"""),{"k":key,"v":value})

    def rules():
        raw=get_setting("autoapply_rules_v1")
        default={"enabled":False,"minimum_match":75,"max_daily":2,"india_only":True}
        try:
            data=json.loads(raw) if raw else {}
            return {**default,**{k:data[k] for k in default if k in data}}
        except (ValueError,TypeError):return default

    def profile():
        raw=get_setting("autoapply_profile_v1")
        if not raw or not cipher:return None
        try:
            value=json.loads(cipher.decrypt(raw.encode()).decode())
            return value if isinstance(value,dict) else None
        except (ValueError,InvalidToken):return None

    def valid_profile(p):
        if not isinstance(p,dict):return False
        return (all(re.fullmatch(r"[A-Za-z][A-Za-z .'-]{0,80}",str(p.get(k,""))) for k in ("first_name","last_name"))
                and bool(_VALID_EMAIL.fullmatch(str(p.get("email",""))))
                and re.fullmatch(r"[+0-9 ()-]{8,24}",str(p.get("phone",""))) is not None
                and p.get("graduation_year")=="2028" and p.get("work_authorized_india") is True
                and p.get("approved_for_employer_submission") is True)

    def fingerprint(url):
        p=urlsplit(str(url or ""))
        return hashlib.sha256((p.hostname.lower()+p.path.rstrip("/")).encode()).hexdigest() if p.hostname else ""

    def eligibility(job, minimum):
        if job["status"] in _TERMINAL:return "Existing application or closed stage; no duplicate submission."
        if int(job.get("score") or 0)<minimum:return "Below minimum match threshold."
        location=str(job.get("location") or "")
        descr=str(job.get("description") or "")
        if not _INDIA_LOCATION.search(location):
            if not ("remote" in location.lower() and _INDIA_LOCATION.search(descr)):
                return "India-based or explicitly India-eligible remote location not confirmed."
        if _BAD_LOCATION.search(location) and not _INDIA_LOCATION.search(location):
            return "Location outside approved India scope."
        if _BAD_YEAR.search(descr) or _EXCLUDED_2028.search(descr):return "Description may exclude your graduation year."
        if not _GOOD_YEAR.search(descr):return "Graduation year 2028 is not confirmed in the listing."
        if job.get("warnings"):return "Employer eligibility warning needs manual review."
        if job.get("provider") not in ("greenhouse","lever","ashby"):
            return "No supported employer ATS identified."
        return ""

    def list_tasks(limit=80):
        with db.connect() as c:
            rows=c.execute(text("""SELECT t.job_id,t.status,t.reason,t.receipt,t.attempted_at,t.updated_at,
                     j.company,j.title,j.location,j.url,j.provider,j.score
                FROM application_tasks t JOIN jobs j ON j.id=t.job_id
                ORDER BY t.updated_at DESC LIMIT :n"""),{"n":limit}).mappings().all()
        return [dict(x) for x in rows]

    def get_resume():
        with db.connect() as c:
            return c.execute(resume_table.select().where(resume_table.c.id=="original")).mappings().first()

    def make_queue(max_jobs=150):
        ensure()
        r=rules()
        with db.begin() as c:
            jobs=c.execute(text("""SELECT id,url,provider,score,status,description,location,warnings,
                         company,title FROM jobs ORDER BY score DESC LIMIT :n"""),
                         {"n":max_jobs}).mappings().all()
            counters={"ready":0,"review":0,"existing":0}
            for job in jobs:
                if job["status"] in _TERMINAL:continue
                fp=fingerprint(job["url"])
                if not fp:continue
                reason=eligibility(job,r["minimum_match"])
                status="needs_review" if reason else "ready"
                res=c.execute(text("""INSERT INTO application_tasks
                  (job_id,fingerprint,status,reason,updated_at)
                  VALUES(:id,:fp,:status,:reason,:updated)
                  ON CONFLICT DO NOTHING"""),
                  {"id":job["id"],"fp":fp,"status":status,"reason":reason,"updated":now()})
                if res.rowcount:counters["review" if reason else "ready"]+=1
                else:counters["existing"]+=1
        return counters

    def greenhouse_parts(job):
        p=urlsplit(str(job["url"]))
        if p.hostname not in ("boards.greenhouse.io","job-boards.greenhouse.io"):return None
        m=re.fullmatch(r"/([a-zA-Z0-9_-]+)/jobs/(\d+)(?:/)?",p.path)
        if not m or not _UUID.fullmatch(m.group(1).lower()):return None
        return m.group(1).lower(),m.group(2)

    def greenhouse_key(board):
        try:
            mapping=json.loads(os.getenv("GREENHOUSE_BOARD_KEYS_JSON","{}"))
            return mapping.get(board) if isinstance(mapping,dict) else None
        except (ValueError,TypeError):return None

    def submit_greenhouse(job, details, document):
        parts=greenhouse_parts(job)
        if not parts:return "needs_review","Cannot verify the official Greenhouse board and posting ID.",""
        board,posting=parts
        key=greenhouse_key(board)
        if not key:return "needs_review","Employer-authorized Greenhouse Job Board API key unavailable. Open the official form.",""
        target=f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{posting}"
        try:
            response=requests.get(target,params={"questions":"true"},timeout=12)
            if response.status_code!=200:
                return "needs_review","Cannot verify required job application fields.",""
            data=response.json()
            fields=set()
            for q in data.get("questions",[]):
                if q.get("required"):
                    names=[f.get("name","") for f in q.get("fields",[])]
                    if not names or not set(names).issubset(_SAFE_FIELDS):
                        return "needs_review","Employer requires custom questions or consent not preapproved.",""
                    fields.update(names)
            # Conservatively reject extra forms, location/visa/education or consent fields.
            for field in ("location_questions","demographic_questions","data_compliance","compliance","eeoc"):
                if data.get(field):
                    return "needs_review","Employer asks for additional details or consent; complete official form.",""
            if not fields.issubset(_SAFE_FIELDS):
                return "needs_review","Unsupported required job fields.",""
            payload={name:details[name] for name in ("first_name","last_name","email","phone")}
            files={"resume":(document["name"],bytes(document["content"]),"application/pdf")}
            result=requests.post(target,auth=(key,""),data=payload,files=files,timeout=30)
            if result.status_code==429:return "needs_review","Employer rate limited submissions; check application before retrying.",""
            if result.status_code>=400:return "needs_review",f"Employer rejected application (HTTP {result.status_code}). Review the official form.",""
            # Provider returned success. A non-2xx/ambiguous transport result never means applied.
            try:body=result.json()
            except ValueError:body={}
            if body.get("success") is False:
                return "needs_review","Employer did not confirm submission.",""
            receipt=str(body.get("id") or body.get("application_id") or f"Greenhouse HTTP {result.status_code}")[:180]
            return "submitted","Accepted by employer submission API.",receipt
        except requests.RequestException:
            return "unknown","Network failed during the submission; check employer portal before retrying.",""

    def run_queue(limit=2):
        ensure()
        r=rules();p=profile()
        if not r["enabled"]:return {"attempted":0,"message":"Automation disabled; enable it after reviewing your application profile."}
        if not valid_profile(p):return {"attempted":0,"message":"Complete and approve your private applicant profile first."}
        document=get_resume()
        if not document:return {"attempted":0,"message":"Upload your approved original resume first."}
        expected=os.getenv("ORIGINAL_RESUME_SHA256","").strip().lower()
        digest=hashlib.sha256(bytes(document["content"])).hexdigest()
        if expected and not hmac.compare_digest(expected,digest):
            return {"attempted":0,"message":"Stored resume failed integrity approval; no applications submitted."}
        today=datetime.now(timezone.utc).date().isoformat()
        with db.connect() as c:
            count=c.scalar(text("""SELECT count(*) FROM application_tasks
                WHERE attempted_at LIKE :today AND status IN ('submitted','unknown','processing')"""),{"today":today+"%"})
        remaining=max(0,min(int(r["max_daily"]),3)-count)
        if not remaining:return {"attempted":0,"message":"Daily submission limit reached."}
        attempted=0;submitted=0;review=0
        with db.connect() as c:
            candidates=c.execute(text("""SELECT t.job_id,j.* FROM application_tasks t
                JOIN jobs j ON j.id=t.job_id WHERE t.status='ready'
                ORDER BY j.score DESC LIMIT :n"""),{"n":min(limit,remaining)}).mappings().all()
        for job in candidates:
            reason=eligibility(job,int(r["minimum_match"]))
            if reason:
                with db.begin() as c:
                    c.execute(text("""UPDATE application_tasks SET status='needs_review',reason=:why,updated_at=:ts
                        WHERE job_id=:id AND status='ready'"""),{"why":reason,"ts":now(),"id":job["job_id"]})
                review+=1;continue
            with db.begin() as c:
                claim=c.execute(text("""UPDATE application_tasks SET status='processing',
                    attempted_at=:ts,updated_at=:ts WHERE job_id=:id AND status='ready'"""),
                    {"ts":now(),"id":job["job_id"]})
            if not claim.rowcount:continue
            attempted+=1
            if job["provider"]=="greenhouse":
                status,message,receipt=submit_greenhouse(job,p,document)
            else:
                status,message,receipt="needs_review","This ATS has no configured employer-authorized submission connector. Use the official form.",""
            with db.begin() as c:
                c.execute(text("""UPDATE application_tasks SET status=:status,reason=:reason,
                    receipt=:receipt,updated_at=:ts WHERE job_id=:id AND status='processing'"""),
                    {"status":status,"reason":message,"receipt":receipt,"ts":now(),"id":job["job_id"]})
                if status=="submitted":
                    c.execute(text("""UPDATE jobs SET status='Applied',updated=:ts
                        WHERE id=:id AND status NOT IN ('Applied','Assessment','Interview','Offer','Rejected','Closed')"""),
                        {"ts":now(),"id":job["job_id"]})
                    submitted+=1
                else:review+=1
        return {"attempted":attempted,"submitted":submitted,"needs_review":review,
                "message":"Only employer-confirmed responses are marked Applied. Ambiguous results require manual review."}

    @app.get("/api/autoapply")
    def auto_status():
        owner();ensure()
        d=rules();p=profile();doc=get_resume()
        return {"rules":d,"profile_ready":valid_profile(p),"profile_email":p.get("email") if p else None,
                "resume_ready":bool(doc),"tasks":list_tasks(),
                "greenhouse_keys_configured":bool(os.getenv("GREENHOUSE_BOARD_KEYS_JSON")),
                "scheduled_trigger_configured":bool(os.getenv("OPPORTUNITY_OS_CRON_TOKEN")),
                "supported_submission":"Employer-authorized Greenhouse Job Board API only. Lever/Ashby require manual form completion until authorized adapters exist."}

    @app.post("/api/autoapply/settings")
    def auto_settings():
        check_origin();ensure()
        data=request.get_json(silent=True) or {}
        if "profile" in data:
            if not cipher:return {"error":"Stable SESSION_SECRET required to encrypt your profile."},503
            p=data["profile"]
            if not valid_profile(p):
                return {"error":"Enter your verified legal name, email, phone, 2028 graduation year and explicit India work authorization and submission approval."},422
            approved={k:p[k] for k in ("first_name","last_name","email","phone","graduation_year","work_authorized_india","approved_for_employer_submission")}
            put_setting("autoapply_profile_v1",cipher.encrypt(json.dumps(approved).encode()).decode())
        rule=rules()
        if "enabled" in data:
            if not isinstance(data["enabled"],bool):return {"error":"enabled must be true or false"},422
            if data["enabled"] and not valid_profile(profile()):
                return {"error":"Approve a valid applicant profile before activating automation."},422
            rule["enabled"]=data["enabled"]
        if "minimum_match" in data:
            try:score=int(data["minimum_match"])
            except (TypeError,ValueError):return {"error":"Minimum match must be 70–100."},422
            if score<70 or score>100:return {"error":"Minimum match must be 70–100."},422
            rule["minimum_match"]=score
        if "max_daily" in data:
            if data["max_daily"] not in (1,2,3):return {"error":"Daily submission cap must be 1–3."},422
            rule["max_daily"]=data["max_daily"]
        put_setting("autoapply_rules_v1",json.dumps(rule))
        return {"rules":rule,"profile_ready":valid_profile(profile())}

    @app.post("/api/autoapply/prepare")
    def auto_prepare():
        check_origin()
        data=request.get_json(silent=True) or {}
        try:limit=int(data.get("limit",150))
        except (ValueError,TypeError):limit=150
        return {"queued":make_queue(max(1,min(limit,300)))}

    @app.post("/api/autoapply/approve/<jid>")
    def auto_approve(jid):
        check_origin();ensure()
        if not (request.get_json(silent=True) or {}).get("eligibility_checked"):
            return {"error":"Confirm that you checked the specific job, work authorization, graduation criteria and all required questions."},422
        with db.begin() as c:
            item=c.execute(text("SELECT status FROM jobs WHERE id=:id"),{"id":jid}).first()
            if not item:return {"error":"Job not found"},404
            if item[0] in _TERMINAL:return {"error":"Already applied or closed. Never resubmit."},409
            c.execute(text("""UPDATE application_tasks SET status='ready',reason='Eligibility explicitly reviewed by account owner',
                reviewed_at=:ts,updated_at=:ts WHERE job_id=:id AND status='needs_review'"""),{"id":jid,"ts":now()})
        return {"ok":True,"message":"Queued for supported API submission. Unsupported employer forms remain review-only."}

    @app.post("/api/autoapply/run")
    def auto_run():
        check_origin()
        return run_queue(limit=2)

    @app.get("/autoapply/schedule")
    def schedule_health():
        abort(404)

    @app.post("/autoapply/schedule")
    def auto_schedule():
        configured=os.getenv("OPPORTUNITY_OS_CRON_TOKEN","")
        candidate=request.headers.get("X-Opportunity-OS-Token","")
        if not configured or not hmac.compare_digest(configured,candidate):abort(403)
        # Free-tier Render instances sleep; invoke from a trusted external scheduler.
        # Queue refresh is performed separately in the dashboard, never by an unauthenticated caller.
        if refresh_employers is not None:
            refresh_employers()
        make_queue(150)
        return run_queue(limit=2)

    @app.get("/api/autoapply/backup")
    def auto_backup():
        owner();ensure()
        from flask import send_file
        from io import BytesIO
        with db.connect() as c:
            rows=[dict(x) for x in c.execute(text("""SELECT job_id,fingerprint,status,reason,receipt,
                 reviewed_at,attempted_at,updated_at FROM application_tasks
                 ORDER BY updated_at DESC LIMIT 5000""")).mappings()]
        payload={"format":"opportunity-os-application-receipts-v1","exported_at":now(),
                 "tasks":rows,"note":"Private application audit log. Protect this file; it excludes applicant profile, PDF and OAuth secrets."}
        blob=json.dumps(payload,ensure_ascii=False).encode("utf-8")
        return send_file(BytesIO(blob),mimetype="application/json",as_attachment=True,
                         download_name="opportunity-os-application-receipts.json")

