import os, importlib, tempfile, uuid
os.environ["APP_PASSWORD"]="test-secret-not-a-real-password"
os.environ["SESSION_SECRET"]="test-session-secret-for-test-only"
os.environ["HTTPS_ONLY"]="false"
os.environ["DATABASE_URL"]="sqlite:///"+os.path.join(tempfile.gettempdir(),"opportunity-os-test-"+str(uuid.uuid4())+".db").replace("\\","/")
mod=importlib.import_module("app")
app=mod.app
app.testing=True

def test_public_routes_and_auth():
 with app.test_client() as c:
  assert c.get("/").status_code==200
  assert c.get("/health").json["ok"] is True
  assert c.get("/api/jobs").status_code==401
  assert c.post("/api/login",json={"password":"wrong"}).status_code==401
  assert c.post("/api/login",json={"password":"test-secret-not-a-real-password"}).json["ok"]
  assert c.get("/api/summary").status_code==200
  assert c.get("/api/integrations").status_code==200
  assert c.get("/api/sources").status_code==200

def test_job_flow_and_oauth_gates():
 with app.test_client() as c:
  c.post("/api/login",json={"password":"test-secret-not-a-real-password"})
  r=c.post("/api/jobs",json={"company":"Example Company","title":"Software Engineering Intern",
      "location":"Delhi India","url":"https://example.org/roles/intern"})
  assert r.status_code==200
  jid=r.json["id"]
  assert c.get("/api/jobs").json["count"]>=1
  assert c.patch("/api/jobs/"+jid,json={"status":"Applied","notes":"Submitted manually"}).status_code==200
  assert c.get("/api/summary").json["applied"]>=1
  assert c.get("/api/outreach/"+jid).json["sent"] is False
  assert c.post("/api/gmail/send",json={"reviewed_and_confirmed":True,"to":"hr@example.org",
      "subject":"Test","body":"I am interested in this role and have reviewed it."}).status_code==503
  assert c.post("/api/resume",data={}).status_code==503
  assert c.delete("/api/jobs/"+jid).status_code==200


def test_private_backup_and_alerts():
 import io, json
 with app.test_client() as c:
  assert c.get("/api/backup").status_code==401
  assert c.get("/api/alerts").status_code==401
  c.post("/api/login",json={"password":"test-secret-not-a-real-password"})
  r=c.post("/api/jobs",json={"company":"Example 2027","title":"Python Backend Intern",
    "location":"Delhi India","url":"https://example.org/jobs/backend-intern-2027"})
  assert r.status_code==200
  job_id=r.json["id"]
  assert c.patch("/api/jobs/"+job_id,json={"status":"Applied","notes":"Applied using official form"}).status_code==200
  assert c.patch("/api/jobs/"+job_id,json={"status":"Interview"}).status_code==200
  rows=c.get("/api/jobs").json["jobs"]
  current=next(x for x in rows if x["id"]==job_id)
  assert current["notes"]=="Applied using official form"
  assert current["status"]=="Interview"
  assert c.get("/api/alerts").status_code==200
  data=c.get("/api/backup")
  assert data.status_code==200
  blob=json.loads(data.data)
  assert blob["format"]=="opportunity-os-backup-v1"
  assert any(x["id"]==job_id for x in blob["jobs"])
  assert c.delete("/api/jobs/"+job_id).status_code==200
  restored=c.post("/api/restore",data={"file":(io.BytesIO(data.data),"backup.json")},
            content_type="multipart/form-data")
  assert restored.status_code==200,restored.json
  assert restored.json["jobs_restored"]>=1
  rows=c.get("/api/jobs").json["jobs"]
  assert next(x for x in rows if x["id"]==job_id)["status"]=="Interview"

def test_app_blocks_private_upload_without_persistent_db():
 from io import BytesIO
 with app.test_client() as c:
  c.post("/api/login",json={"password":"test-secret-not-a-real-password"})
  assert c.post("/api/contacts",json={"email":"hr@somecompany.com","company":"Some company"}).status_code==503
  assert c.post("/api/contacts/import",data={"file":(BytesIO(b"company,email\nTest,hr@test.com"),"contacts.csv")}, content_type="multipart/form-data").status_code==503
  assert c.post("/api/resume",data={"file":(BytesIO(b"%PDF-1.4\n"),"resume.pdf")},content_type="multipart/form-data").status_code==503
  assert c.get("/api/integrations").json["persistent"] is False

def test_source_validation():
 with app.test_client() as c:
  c.post("/api/login",json={"password":"test-secret-not-a-real-password"})
  bad=c.post("/api/sources",json={"provider":"fake","slug":"fake","name":"Example"})
  assert bad.status_code==422
  good=c.post("/api/sources",json={"provider":"ashby","slug":"exampleboard","name":"Sample Hiring"})
  assert good.status_code==200
  assert any(x["slug"]=="exampleboard" for x in c.get("/api/sources").json["sources"])


def test_api_error_handlers_return_json():
 with app.test_client() as c:
  # 405 Method Not Allowed on API route returns JSON
  res = c.delete("/api/session")
  assert res.status_code == 405
  assert "error" in res.json
