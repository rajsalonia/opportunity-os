import os, importlib, tempfile, uuid
os.environ["APP_PASSWORD"]="test-secret-not-a-real-password"
os.environ["SESSION_SECRET"]="test-session-secret-for-test-only"
os.environ["HTTPS_ONLY"]="false"
os.environ["DATABASE_URL"]="sqlite:////tmp/opportunity-os-test-"+str(uuid.uuid4())+".db"
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
