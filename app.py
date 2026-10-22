import os, csv, io, hashlib, hmac, re, secrets
from datetime import datetime, timezone
from urllib.parse import urlsplit
from concurrent.futures import ThreadPoolExecutor
import requests
from flask import Flask, request, jsonify, session, send_file, render_template, abort
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from werkzeug.middleware.proxy_fix import ProxyFix

app=Flask(__name__)
app.config["SECRET_KEY"]=os.environ.get("SESSION_SECRET") or secrets.token_urlsafe(48)
app.config["SESSION_COOKIE_SECURE"]=os.getenv("HTTPS_ONLY","true")=="true"
app.config["SESSION_COOKIE_SAMESITE"]="Lax"
app.wsgi_app=ProxyFix(app.wsgi_app,x_for=1,x_proto=1,x_host=1)
pw=os.environ.get("APP_PASSWORD","")
url=os.environ.get("DATABASE_URL","sqlite:////tmp/opportunity_os.db")
if url.startswith("postgres://"):url="postgresql+psycopg://"+url[11:]
if url.startswith("postgresql://"):url="postgresql+psycopg://"+url[13:]
db=create_engine(url,pool_pre_ping=True,pool_recycle=150)
schema=[
"""CREATE TABLE IF NOT EXISTS jobs(id VARCHAR(64) PRIMARY KEY,company TEXT NOT NULL,title TEXT NOT NULL,location TEXT,url TEXT NOT NULL,provider TEXT,description TEXT,score INTEGER DEFAULT 0,warnings TEXT DEFAULT '',status TEXT DEFAULT 'Discovered',notes TEXT DEFAULT '',deadline TEXT DEFAULT '',discovered TEXT,updated TEXT)""",
"""CREATE TABLE IF NOT EXISTS contacts(id VARCHAR(64) PRIMARY KEY, company TEXT, name TEXT,email TEXT,role TEXT,notes TEXT)""",
"""CREATE TABLE IF NOT EXISTS settings(key VARCHAR(64) PRIMARY KEY,value TEXT)"""
]
with db.begin() as con:
 for stmt in schema: con.execute(text(stmt))
boards=[
 ("greenhouse","stripe","Stripe"),("greenhouse","figma","Figma"),
 ("greenhouse","cloudflare","Cloudflare"),("greenhouse","notion","Notion"),
 ("greenhouse","mongodb","MongoDB"),("greenhouse","databricks","Databricks"),
 ("greenhouse","webflow","Webflow"),("greenhouse","canonical","Canonical"),
 ("lever","postman","Postman"),("lever","retool","Retool"),
 ("lever","sourcegraph","Sourcegraph")
]
roles=re.compile(r"\b(intern(?:ship)?|co-op|co op|graduate|new grad|trainee|junior|apprentice)\b",re.I)
technical=re.compile(r"\b(software|engineer|backend|back-end|python|AI|machine learning|developer|SRE|devops|cloud|security|infrastructure|data)\b",re.I)
skills=("python","fastapi","backend","software","engineering","ai","ml","aws","cloud","devops","docker","microservice")
def now():return datetime.now(timezone.utc).isoformat(timespec="seconds")
def secure_url(s):
 try:
  p=urlsplit(s)
  return p.scheme=="https" and bool(p.hostname) and not p.username and not p.password
 except Exception:return False
def rank(title,descr,location):
 title=title.lower(); descr=descr.lower();loc=location.lower()
 score=28 if roles.search(title) else 0
 score+=sum(5 if x in title else 2 for x in skills if x in (title+" "+descr))
 score+=14 if any(x in loc for x in ("india","delhi","noida","gurugram","gurgaon","bengaluru","pune","hyderabad")) else 0
 score+=8 if "remote" in loc else 0
 score+=7 if "2028" in descr else 0
 warning=[]
 if re.search(r"202[567] graduates only|class of 202[567] only|must graduate in 202[567]",descr):warning.append("Check graduation eligibility")
 if re.search(r"us citizenship required|must be authorized to work in the united states",descr):warning.append("Check work authorization")
 return min(100,max(0,score)), "; ".join(warning)
def owner():
 if not session.get("owner"):abort(401)
def check_origin():
 owner()
 origin=request.headers.get("Origin")
 if origin and urlsplit(origin).netloc !=request.host:abort(403)
@app.after_request
def headers(response):
 response.headers["X-Content-Type-Options"]="nosniff"
 response.headers["X-Frame-Options"]="DENY"
 response.headers["Referrer-Policy"]="strict-origin-when-cross-origin"
 response.headers["Cache-Control"]="no-store"
 return response
@app.get("/")
def homepage():return render_template("index.html")
@app.get("/health")
def health():return {"ok":True,"storage":"postgres" if "postgres" in url else "ephemeral"}
@app.get("/api/session")
def whoami():return {"authenticated":bool(session.get("owner")),"storage":"persistent_postgres" if "postgres" in url else "temporary_sqlite"}
@app.post("/api/login")
def login():
 if not pw:return jsonify(error="APP_PASSWORD not configured"),503
 entered=str((request.get_json(silent=True) or {}).get("password",""))
 if len(entered)>500:return jsonify(error="Invalid"),400
 if not hmac.compare_digest(hashlib.sha256(entered.encode()).digest(),hashlib.sha256(pw.encode()).digest()):
  return jsonify(error="Incorrect password"),401
 session.clear();session["owner"]=True
 return {"ok":True}
@app.post("/api/logout")
def logout():check_origin();session.clear();return {"ok":True}
@app.get("/api/jobs")
def jobs():
 owner()
 with db.connect() as c:
  data=[dict(x._mapping) for x in c.execute(text("SELECT * FROM jobs ORDER BY discovered DESC LIMIT 2000"))]
 search=request.args.get("q","").lower()[:100]; status=request.args.get("status","")[:32]
 if search:data=[x for x in data if search in " ".join([x["title"],x["company"],x["location"] or ""]).lower()]
 if status:data=[x for x in data if x["status"]==status]
 data.sort(key=lambda x: x["score"] or 0,reverse=True)
 return {"jobs":data,"count":len(data)}
@app.get("/api/summary")
def summary():
 owner()
 with db.connect() as c:
  data=[r[0] for r in c.execute(text("SELECT status FROM jobs"))]
  contacts=c.scalar(text("SELECT count(*) FROM contacts"))
 return {"total":len(data),"saved":data.count("Saved"),"applied":data.count("Applied"),
         "assessment":data.count("Assessment"),"interviews":data.count("Interview"),
         "offers":data.count("Offer"),"contacts":contacts}
@app.post("/api/jobs")
def addjob():
 check_origin();j=request.get_json(silent=True) or {}
 company=str(j.get("company","")).strip()[:150]; title=str(j.get("title","")).strip()[:200]
 link=str(j.get("url","")).strip()[:2000]; location=str(j.get("location",""))[:200]
 if not (company and title and secure_url(link)):return {"error":"Valid company, title and HTTPS application URL required"},422
 jid=hashlib.sha256(link.encode()).hexdigest()[:32];score,warning=rank(title,"",location)
 with db.begin() as c:
  c.execute(text("""INSERT INTO jobs(id,company,title,location,url,provider,description,score,warnings,status,notes,deadline,discovered,updated)
  VALUES(:id,:co,:ti,:lo,:ur,'manual','',:sc,:warn,'Saved',:notes,:dl,:ts,:ts)
  ON CONFLICT(id) DO UPDATE SET notes=excluded.notes, deadline=excluded.deadline"""),
  {"id":jid,"co":company,"ti":title,"lo":location,"ur":link,"sc":score,"warn":warning,
   "notes":str(j.get("notes",""))[:4000],"dl":str(j.get("deadline",""))[:40],"ts":now()})
 return {"ok":True,"id":jid}
@app.patch("/api/jobs/<jid>")
def updatejob(jid):
 check_origin();body=request.get_json(silent=True) or {}
 allowed=("Discovered","Saved","Draft ready","Applied","Assessment","Interview","Offer","Rejected","Closed")
 status=str(body.get("status","Saved"))
 if status not in allowed:return {"error":"Invalid status"},422
 with db.begin() as c:
  row=c.execute(text("SELECT id FROM jobs WHERE id=:id"),{"id":jid}).first()
  if not row:return {"error":"Not found"},404
  c.execute(text("UPDATE jobs SET status=:st,notes=:no,updated=:ts WHERE id=:id"),
    {"st":status,"no":str(body.get("notes",""))[:4000],"ts":now(),"id":jid})
 return {"ok":True}
@app.delete("/api/jobs/<jid>")
def deletejob(jid):
 check_origin()
 with db.begin() as c:c.execute(text("DELETE FROM jobs WHERE id=:id"),{"id":jid})
 return {"ok":True}
def collect(board):
 provider,slug,company=board
 address=(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
          if provider=="greenhouse" else f"https://api.lever.co/v0/postings/{slug}?mode=json")
 try:
  response=requests.get(address,timeout=10,headers={"User-Agent":"OpportunityOS/1.0"})
  response.raise_for_status(); payload=response.json()
  posts=payload.get("jobs",[]) if provider=="greenhouse" else payload
  found=[]
  for p in posts[:1000]:
   title=str(p.get("title") or p.get("text") or "")
   if not (roles.search(title) and technical.search(title)):continue
   cats=p.get("categories") or {}
   loc=str((p.get("location") or {}).get("name","") if provider=="greenhouse" else cats.get("location",""))
   desc=re.sub("<[^>]*>"," ",str(p.get("content") or p.get("descriptionPlain") or p.get("description") or ""))[:5000]
   link=str(p.get("absolute_url") or p.get("hostedUrl") or p.get("applyUrl") or "")
   if not secure_url(link):continue
   score,warning=rank(title,desc,loc)
   found.append({"id":hashlib.sha256(link.encode()).hexdigest()[:32],"company":company,
    "title":title[:200],"location":loc[:200],"url":link,"provider":provider,
    "description":desc[:5000],"score":score,"warnings":warning})
  return found,None
 except Exception as e:return [],company+" unavailable"
@app.post("/api/refresh")
def refresh():
 check_origin()
 with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(collect,boards))
 count=0;failed=[]
 with db.begin() as c:
  for rows,error in results:
   if error:failed.append(error)
   for r in rows:
    c.execute(text("""INSERT INTO jobs(id,company,title,location,url,provider,description,score,warnings,status,notes,deadline,discovered,updated)
     VALUES(:id,:company,:title,:location,:url,:provider,:description,:score,:warnings,'Discovered','','',:ts,:ts)
     ON CONFLICT(id) DO UPDATE SET title=excluded.title,location=excluded.location,description=excluded.description,score=excluded.score,warnings=excluded.warnings,updated=excluded.updated"""),r|{"ts":now()})
    count+=1
 return {"found":count,"checked":len(boards),"errors":failed,"note":"Openings may not match your eligibility; check each employer page."}
@app.get("/api/outreach/<jid>")
def outreach(jid):
 owner()
 with db.connect() as c:row=c.execute(text("SELECT title,company FROM jobs WHERE id=:id"),{"id":jid}).mappings().first()
 if not row:return {"error":"Not found"},404
 return {"subject":f"Application interest: {row['title']} — Raj Salonia",
 "body":f"Hello Hiring Team,\n\nI am a B.Tech Computer Science student graduating in 2028 with software engineering internship experience and projects in Python, FastAPI and AI. I would love to be considered for the {row['title']} role at {row['company']}.\n\nGitHub: https://github.com/rajsalonia\nLinkedIn: https://linkedin.com/in/rajsalonia\n\nThank you,\nRaj Salonia",
 "sent":False,"note":"Draft only. Check eligibility and attach original resume before sending."}
@app.post("/api/contacts")
def contact():
 check_origin();j=request.get_json(silent=True) or {}
 email=str(j.get("email","")).strip()[:250]
 if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",email):return {"error":"Invalid email"},422
 entry={"id":secrets.token_hex(16),"company":str(j.get("company",""))[:150],
 "name":str(j.get("name",""))[:150],"email":email,"role":str(j.get("role",""))[:150],"notes":""}
 with db.begin() as c:c.execute(text("INSERT INTO contacts VALUES(:id,:company,:name,:email,:role,:notes)"),entry)
 return {"ok":True}
@app.get("/api/contacts")
def get_contacts():
 owner()
 with db.connect() as c:rows=[dict(x._mapping) for x in c.execute(text("SELECT * FROM contacts ORDER BY company LIMIT 3000"))]
 return {"contacts":rows}
@app.get("/api/export")
def export():
 owner()
 with db.connect() as c:rows=[dict(x._mapping) for x in c.execute(text("SELECT * FROM jobs ORDER BY discovered DESC"))]
 out=io.StringIO(); keys=["company","title","location","url","provider","status","score","deadline","notes"]
 w=csv.DictWriter(out,fieldnames=keys,extrasaction="ignore");w.writeheader();w.writerows(rows)
 return send_file(io.BytesIO(out.getvalue().encode()),mimetype="text/csv",as_attachment=True,download_name="opportunity-os.csv")
