import os, csv, io, hashlib, hmac, re, secrets, tempfile, html
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit
from concurrent.futures import ThreadPoolExecutor
import requests
from flask import Flask, request, jsonify, session, send_file, render_template, abort
from sqlalchemy import create_engine, text, select, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError, InterfaceError
from werkzeug.middleware.proxy_fix import ProxyFix

app=Flask(__name__)
# Throttle repeated password attempts per worker; proxy IPs are trusted only through Render.
from collections import defaultdict
from threading import Lock
login_failures=defaultdict(list)
login_lock=Lock()
app.config["SECRET_KEY"]=os.environ.get("SESSION_SECRET") or secrets.token_urlsafe(48)
app.config["SESSION_COOKIE_SECURE"]=os.getenv("HTTPS_ONLY","true")=="true"
app.config["SESSION_COOKIE_SAMESITE"]="Lax"
app.wsgi_app=ProxyFix(app.wsgi_app,x_for=1,x_proto=1,x_host=1)
pw=os.environ.get("APP_PASSWORD","")
url=os.environ.get("DATABASE_URL") or "sqlite:///"+os.path.join(tempfile.gettempdir(),"opportunity_os.db").replace("\\","/")
if url.startswith("postgres://"):url="postgresql+psycopg://"+url[11:]
if url.startswith("postgresql://"):url="postgresql+psycopg://"+url[13:]
engine_options={"pool_pre_ping":True,"pool_recycle":150}
if url.startswith("postgresql+psycopg://"):
 # Bounded connections for free PostgreSQL plans; also works with Supabase poolers.
 engine_options.update(pool_size=3,max_overflow=2,pool_timeout=8,
                       connect_args={"connect_timeout":4,"prepare_threshold":None})
db=create_engine(url,**engine_options)
schema=[
"""CREATE TABLE IF NOT EXISTS jobs(id VARCHAR(64) PRIMARY KEY,company TEXT NOT NULL,title TEXT NOT NULL,location TEXT,url TEXT NOT NULL,provider TEXT,description TEXT,score INTEGER DEFAULT 0,warnings TEXT DEFAULT '',status TEXT DEFAULT 'Discovered',notes TEXT DEFAULT '',deadline TEXT DEFAULT '',discovered TEXT,updated TEXT)""",
"""CREATE TABLE IF NOT EXISTS contacts(id VARCHAR(64) PRIMARY KEY, company TEXT, name TEXT,email TEXT,role TEXT,notes TEXT)""",
"""CREATE TABLE IF NOT EXISTS settings(key VARCHAR(64) PRIMARY KEY,value TEXT)"""
]
schema_ready=False
def initialize_storage():
 global schema_ready
 with db.begin() as con:
  for stmt in schema:con.execute(text(stmt))
 if "_extra_meta" in globals():_extra_meta.create_all(db)
 schema_ready=True
try:initialize_storage()
except (OperationalError,InterfaceError):
 # Keep the sign-in screen reachable and retry after configuration is corrected.
 app.logger.warning("Storage unavailable at startup; check DATABASE_URL privately in Render.")
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
def plain_description(value):
 # Employer feeds sometimes entity-encode their HTML. Return text, never markup.
 decoded=html.unescape(html.unescape(str(value or "")))
 decoded=re.sub(r"(?i)<br\s*/?>|</(?:p|div|li|h[1-6]|ul|ol)\s*>","\n",decoded)
 return html.unescape(re.sub(r"<[^>]*>","",decoded))[:5000].strip()
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
@app.get("/favicon.ico")
def favicon():return app.send_static_file("mark.svg")
@app.get("/health")
def health():
 try:
  if not schema_ready:initialize_storage()
  with db.connect() as c:c.execute(text("SELECT 1"))
  return {"ok":True,"storage":"postgres" if "postgres" in url else "ephemeral","database_connected":True}
 except (OperationalError,InterfaceError):
  return {"ok":False,"database_connected":False,"error":"Database unavailable"},503

@app.before_request
def prepare_storage():
 if request.path.startswith("/api/") and request.path not in ("/api/session","/api/login","/api/logout"):
  owner()
  if not schema_ready:initialize_storage()

@app.errorhandler(OperationalError)
@app.errorhandler(InterfaceError)
def storage_error(error):
 return {"error":"Database connection unavailable. Check DATABASE_URL and Supabase project status privately in Render, then retry."},503

@app.errorhandler(401)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(413)
@app.errorhandler(422)
@app.errorhandler(503)
def api_error(error):
 if request.path.startswith("/api/"):return jsonify(error=error.description),error.code
 return error
@app.get("/api/session")
def whoami():return {"authenticated":bool(session.get("owner")),"storage":"persistent_postgres" if "postgres" in url else "temporary_sqlite","gmail_requires_user_setup":True}
@app.post("/api/login")
def login():
 if not pw:return jsonify(error="APP_PASSWORD not configured"),503
 client=request.remote_addr or "unknown"
 with login_lock:
  login_failures[client]=[t for t in login_failures[client] if time.time()-t<900]
  if len(login_failures[client])>=10:
   return jsonify(error="Too many login attempts; wait 15 minutes"),429
 entered=str((request.get_json(silent=True) or {}).get("password",""))
 if len(entered)>500:return jsonify(error="Invalid"),400
 if not hmac.compare_digest(hashlib.sha256(entered.encode()).digest(),hashlib.sha256(pw.encode()).digest()):
  with login_lock:login_failures[client].append(time.time())
  return jsonify(error="Incorrect password"),401
 with login_lock:login_failures.pop(client,None)
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
 for item in data:item["description"]=plain_description(item.get("description"))
 data.sort(key=lambda x: x["score"] or 0,reverse=True)
 return {"jobs":data,"count":len(data),"limit":2000}
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
 deadline=str(body["deadline"]).strip() if "deadline" in body else None
 if deadline:
  try:datetime.strptime(deadline,"%Y-%m-%d")
  except ValueError:return {"error":"Deadline must be a valid YYYY-MM-DD date"},422
 with db.begin() as c:
  row=c.execute(text("SELECT id FROM jobs WHERE id=:id"),{"id":jid}).first()
  if not row:return {"error":"Not found"},404
  c.execute(text("UPDATE jobs SET status=:st,notes=COALESCE(:no,notes),deadline=COALESCE(:dl,deadline),updated=:ts WHERE id=:id"),
    {"st":status,"no":str(body["notes"])[:4000] if "notes" in body else None,"dl":deadline,"ts":now(),"id":jid})
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
   desc=plain_description(p.get("content") or p.get("descriptionPlain") or p.get("description"))
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
 check_origin();persistent_only();j=request.get_json(silent=True) or {}
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
 w=csv.DictWriter(out,fieldnames=keys,extrasaction="ignore");w.writeheader()
 # Avoid CSV formula injection if a recruiter opens the export in Excel.
 for record in rows:
  cleaned={k:("'" + str(record.get(k,"")) if isinstance(record.get(k),str) and str(record.get(k)).lstrip().startswith(("=","+","-","@")) else record.get(k,"")) for k in keys}
  w.writerow(cleaned)
 return send_file(io.BytesIO(out.getvalue().encode()),mimetype="text/csv",as_attachment=True,download_name="opportunity-os.csv")


# -----------------------------------------------------------------------
# Opportunity OS integrations: searchable sources, CSV/XLSX contacts,
# original-resume vault, and explicitly approved Gmail sending.
# External OAuth credentials and DB URL are configured only in Render env.
# -----------------------------------------------------------------------
import base64
import mimetypes
import time
from email.message import EmailMessage
from urllib.parse import urlencode
from flask import redirect, url_for
from sqlalchemy import MetaData, Table, Column, String, Text, DateTime, LargeBinary
from cryptography.fernet import Fernet, InvalidToken

_extra_meta=MetaData()
resume_table=Table("private_documents",_extra_meta,
 Column("id",String(40),primary_key=True),
 Column("name",String(250)),
 Column("content",LargeBinary),
 Column("hash",String(64)),
 Column("updated",String(50)))
oauth_table=Table("oauth_tokens",_extra_meta,
 Column("id",String(40),primary_key=True),
 Column("token",LargeBinary),
 Column("updated",String(50)))
email_table=Table("email_log",_extra_meta,
 Column("id",String(40),primary_key=True),
 Column("job_id",String(64)),
 Column("recipient",String(320)),
 Column("subject",Text),
 Column("status",String(40)),
 Column("gmail_id",String(320)),
 Column("sent_at",String(50)))
source_table=Table("job_sources",_extra_meta,
 Column("id",String(180),primary_key=True),
 Column("provider",String(30)),Column("slug",String(100)),Column("name",String(200)))
if schema_ready:
 try:_extra_meta.create_all(db)
 except (OperationalError,InterfaceError):schema_ready=False
SETTINGS_SECRET=os.getenv("SESSION_SECRET","")
FERNET=Fernet(base64.urlsafe_b64encode(hashlib.sha256(SETTINGS_SECRET.encode()).digest())) if SETTINGS_SECRET else None
GMAIL_SCOPES="https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send"
def has_persistent_db():
 return url.startswith("postgresql+psycopg")
def persistent_only():
 if not has_persistent_db():
  abort(503, description="Persistent database not connected yet; confidential uploads and OAuth are disabled.")
def google_ready():
 return bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET") and FERNET and has_persistent_db())
def get_token():
 if not google_ready():return None
 with db.connect() as c:
  row=c.execute(oauth_table.select().where(oauth_table.c.id=="gmail")).mappings().first()
 if not row:return None
 try:return __import__("json").loads(FERNET.decrypt(bytes(row["token"])).decode())
 except (InvalidToken,ValueError):return None
def set_token(value):
 persistent_only()
 blob=FERNET.encrypt(__import__("json").dumps(value).encode())
 with db.begin() as c:
  c.execute(oauth_table.delete().where(oauth_table.c.id=="gmail"))
  c.execute(oauth_table.insert().values(id="gmail",token=blob,updated=now()))
def access_token():
 token=get_token()
 if not token:return None
 if float(token.get("expires_at",0))>time.time()+90:return token.get("access_token")
 refresh=token.get("refresh_token")
 if not refresh:return None
 res=requests.post("https://oauth2.googleapis.com/token",data={
   "client_id":os.getenv("GOOGLE_CLIENT_ID"),"client_secret":os.getenv("GOOGLE_CLIENT_SECRET"),
   "refresh_token":refresh,"grant_type":"refresh_token"},timeout=15)
 if res.status_code>=400:return None
 new=res.json()
 token["access_token"]=new["access_token"]
 token["expires_at"]=time.time()+int(new.get("expires_in",3600))
 set_token(token)
 return token["access_token"]
def gmail_req(method,path,payload=None):
 token=access_token()
 if not token:abort(503,description="Connect Gmail from the dashboard first.")
 headers={"Authorization":"Bearer "+token}
 r=requests.request(method,"https://gmail.googleapis.com/gmail/v1/users/me/"+path,
  headers=headers,json=payload,timeout=20)
 if r.status_code>=400:
  abort(502,description="Gmail API returned status "+str(r.status_code))
 return r.json()
@app.get("/api/integrations")
def integrations():
 owner()
 with db.connect() as c:
  row=c.execute(select(resume_table.c.name,resume_table.c.hash,resume_table.c.updated,
    func.length(resume_table.c.content).label("bytes")).where(resume_table.c.id=="original")).mappings().first()
  last_checked=c.scalar(text("SELECT value FROM settings WHERE key='gmail_last_checked'"))
 return {
  "database_connected":True,
  "login_configured":bool(pw),
  "session_secret_configured":bool(SETTINGS_SECRET),
  "persistent":has_persistent_db(),
  "gmail_available":google_ready(),
  "gmail_connected":bool(get_token()),
  "resume_uploaded":bool(row),
  "resume_filename":row["name"] if row else None,
  "resume_sha256":row["hash"] if row else None,
  "resume_bytes":row["bytes"] if row else None,
  "resume_updated":row["updated"] if row else None,
  "gmail_last_checked":last_checked,
  "email_requires_review":True,
  "auto_ats_apply":False,
  "data_warning":"" if has_persistent_db() else "No persistent DB URL. Avoid importing contacts/resume before configuration."
 }
@app.get("/api/sources")
def get_sources():
 owner()
 with db.connect() as c:rows=[dict(x._mapping) for x in c.execute(source_table.select().order_by(source_table.c.name))]
 return {"sources":rows,"default_boards":[{"provider":p,"slug":s,"name":n} for p,s,n in boards],
         "extended_boards":[{"provider":"ashby","slug":s,"name":n} for s,n in
                            [("ramp","Ramp"),("linear","Linear"),("perplexity","Perplexity"),("openai","OpenAI")]]}
@app.post("/api/sources")
def put_source():
 check_origin();body=request.get_json(silent=True) or {}
 provider=str(body.get("provider","")).lower()
 slug=str(body.get("slug","")).lower().strip()
 name=str(body.get("name","")).strip()[:100]
 if provider not in ("greenhouse","lever","ashby") or not re.fullmatch(r"[a-z0-9_-]{2,90}",slug) or not name:
  return {"error":"Valid provider, board slug and company name required"},422
 key=provider+":"+slug
 with db.begin() as c:
  c.execute(source_table.delete().where(source_table.c.id==key))
  c.execute(source_table.insert().values(id=key,provider=provider,slug=slug,name=name))
 return {"ok":True}
@app.delete("/api/sources/<path:source_id>")
def remove_source(source_id):
 check_origin()
 with db.begin() as c:c.execute(source_table.delete().where(source_table.c.id==source_id))
 return {"ok":True}

# This is a separate endpoint so the existing original-board refresh remains usable.
@app.post("/api/refresh/extended")
def refresh_extended():
 check_origin()
 return refresh_extended_impl()

def refresh_extended_impl():
 with db.connect() as c:
  rows=[(r["provider"],r["slug"],r["name"]) for r in c.execute(source_table.select()).mappings()]
 additional=[("ashby","ramp","Ramp"),("ashby","linear","Linear"),
             ("ashby","perplexity","Perplexity"),("ashby","openai","OpenAI")]
 batch=list({(p,s):(p,s,n) for p,s,n in (boards+rows+additional)}.values())[:35]
 def get_board(entry):
  provider,slug,company=entry
  if provider in ("greenhouse","lever"):return collect(entry)
  address="https://api.ashbyhq.com/posting-api/job-board/"+slug
  try:
   result=requests.get(address,timeout=10,headers={"User-Agent":"OpportunityOS/1.1"})
   result.raise_for_status()
   posts=result.json().get("jobs",[])
   found=[]
   for post in posts[:800]:
    title=str(post.get("title") or "")
    if not (roles.search(title) and technical.search(title)):continue
    desc=plain_description(post.get("descriptionHtml") or post.get("descriptionPlain"))
    loc=str(post.get("location") or "")
    link=str(post.get("jobUrl") or post.get("applyUrl") or "")
    if not secure_url(link):continue
    score,warning=rank(title,desc,loc)
    found.append({"id":hashlib.sha256(link.encode()).hexdigest()[:32],
     "company":company,"title":title[:200],"location":loc[:200],
     "url":link,"provider":"ashby","description":desc,"score":score,"warnings":warning})
   return found,None
  except Exception:return [],company+" unavailable"
 with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(get_board,batch))
 added=0;errors=[]
 with db.begin() as c:
  for rows,error in results:
   if error:errors.append(error)
   for r in rows:
    already=c.execute(text("SELECT 1 FROM jobs WHERE id=:id"),{"id":r["id"]}).first()
    if not already:added+=1
    c.execute(text("""INSERT INTO jobs(id,company,title,location,url,provider,description,score,warnings,status,notes,deadline,discovered,updated)
    VALUES(:id,:company,:title,:location,:url,:provider,:description,:score,:warnings,'Discovered','','',:ts,:ts)
    ON CONFLICT(id) DO UPDATE SET title=excluded.title,location=excluded.location,description=excluded.description,
    score=excluded.score,warnings=excluded.warnings,updated=excluded.updated"""),r|{"ts":now()})
 return {"new":added,"checked":len(batch),"errors":errors,"hint":"Opening may not match your location, year or visa eligibility. Check original listing."}

@app.post("/api/contacts/import")
def import_hr_contacts():
 check_origin();persistent_only()
 f=request.files.get("file")
 if not f:return {"error":"Upload an XLSX or CSV file"},422
 content=f.read(4_000_001)
 if len(content)>4_000_000:return {"error":"Maximum file size is 4 MB"},413
 filename=(f.filename or "").lower()
 if filename.endswith(".csv"):
  try: rows=list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
  except Exception:return {"error":"CSV must be UTF-8"},422
 elif filename.endswith(".xlsx"):
  from openpyxl import load_workbook
  try:
   book=load_workbook(io.BytesIO(content),read_only=True,data_only=True)
   rows=[]
   for sheet in book.worksheets:
    it=sheet.iter_rows(values_only=True)
    headers=next(it,[])
    for cells in it:rows.append(dict(zip([str(h or "").strip() for h in headers],cells)))
    if len(rows)>6000:break
  except Exception:return {"error":"Invalid Excel workbook"},422
 else:return {"error":"Only .csv and .xlsx files are supported"},422
 inserted=0;skipped=0
 with db.begin() as c:
  for item in rows[:6000]:
   lower={str(k or "").lower().strip():str(v or "").strip() for k,v in item.items()}
   email=next((lower[k] for k in ("email","email id","email-id","emailid","e-mail","email address","hr email","contact email","work email") if lower.get(k)),"").lower()[:250]
   company=next((lower[k] for k in ("company","company name","organization","employer") if lower.get(k)),"")[:150]
   if not company or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",email):
    skipped+=1;continue
   if c.execute(text("SELECT 1 FROM contacts WHERE lower(email)=:email"),{"email":email}).first():
    skipped+=1;continue
   c.execute(text("INSERT INTO contacts(id,company,name,email,role,notes) VALUES(:id,:company,:name,:email,:role,:notes)"),
    {"id":secrets.token_hex(16),"company":company,"email":email,
     "name":lower.get("name",lower.get("hr name",""))[:150],
     "role":lower.get("role","")[:150],"notes":(lower.get("notes") or lower.get("linkedin") or "")[:500]})
   inserted+=1
 return {"imported":inserted,"skipped":skipped,"total_rows":min(len(rows),6000)}

@app.post("/api/resume")
def upload_original_resume():
 check_origin();persistent_only()
 f=request.files.get("file")
 if not f or not f.filename.lower().endswith(".pdf"):return {"error":"Upload original PDF resume"},422
 data=f.read(3_000_001)
 if not data.startswith(b"%PDF-") or len(data)>3_000_000:return {"error":"Invalid PDF or file over 3MB"},422
 name="Raj_Salonia_Resume (5)(2).pdf"
 digest=hashlib.sha256(data).hexdigest()
 expected=os.getenv("ORIGINAL_RESUME_SHA256","").lower().strip()
 if expected and digest != expected:
  return {"error":"This is not the exact approved original resume PDF. File rejected without modification."},422
 with db.begin() as c:
  existing=c.execute(resume_table.select().where(resume_table.c.id=="original")).mappings().first()
  if existing:
   if hmac.compare_digest(hashlib.sha256(bytes(existing["content"])).hexdigest(),digest):
    return {"ok":True,"sha256":digest,"bytes":len(data),"note":"Existing original preserved byte-for-byte."}
   return {"error":"An original resume is already stored. Replacement is disabled to preserve the original PDF."},409
  inserted=c.execute(text("INSERT INTO private_documents(id,name,content,hash,updated) VALUES('original',:name,:content,:hash,:updated) ON CONFLICT(id) DO NOTHING"),
                     {"name":name,"content":data,"hash":digest,"updated":now()})
  if not inserted.rowcount:return {"error":"An original resume was stored concurrently. Reload the vault; replacement is disabled."},409
 return {"ok":True,"sha256":digest,"bytes":len(data),"note":"Stored byte-for-byte unchanged."}

@app.get("/api/resume/download")
def get_original_resume():
 owner()
 with db.connect() as c:row=c.execute(resume_table.select().where(resume_table.c.id=="original")).mappings().first()
 if not row:abort(404)
 from flask import send_file as flask_send_file
 return flask_send_file(io.BytesIO(bytes(row["content"])),as_attachment=True,download_name=row["name"],mimetype="application/pdf")

@app.get("/api/resume/verify")
def verify_original_resume():
 owner()
 with db.connect() as c:row=c.execute(resume_table.select().where(resume_table.c.id=="original")).mappings().first()
 if not row:return {"error":"No original resume stored yet"},404
 data=bytes(row["content"])
 digest=hashlib.sha256(data).hexdigest()
 expected=os.getenv("ORIGINAL_RESUME_SHA256","").lower().strip()
 return {"verified":hmac.compare_digest(digest,row["hash"]) and (not expected or hmac.compare_digest(digest,expected)),
         "sha256":digest,"bytes":len(data),"filename":row["name"],"checked_at":now()}

@app.get("/api/gmail/connect")
def gmail_connect():
 owner();persistent_only()
 if not google_ready():return {"error":"Google OAuth credentials not configured in Render environment"},503
 state=secrets.token_urlsafe(32)
 session["google_oauth_state"]=state
 redirect_uri=url_for("gmail_callback",_external=True,_scheme="https")
 query=urlencode({"client_id":os.environ["GOOGLE_CLIENT_ID"],"redirect_uri":redirect_uri,"response_type":"code",
                  "scope":GMAIL_SCOPES,"access_type":"offline","prompt":"consent","state":state})
 return redirect("https://accounts.google.com/o/oauth2/v2/auth?"+query)
@app.get("/auth/google/callback")
def gmail_callback():
 owner()
 state=request.args.get("state","")
 if not state or not hmac.compare_digest(state,session.pop("google_oauth_state","")):abort(403)
 code=request.args.get("code")
 if not code:abort(400)
 uri=url_for("gmail_callback",_external=True,_scheme="https")
 response=requests.post("https://oauth2.googleapis.com/token",data={
 "client_id":os.environ["GOOGLE_CLIENT_ID"],"client_secret":os.environ["GOOGLE_CLIENT_SECRET"],
 "code":code,"redirect_uri":uri,"grant_type":"authorization_code"},timeout=20)
 if response.status_code>=400:abort(502,description="Google authorization could not be completed")
 t=response.json()
 old=get_token() or {}
 if "refresh_token" not in t and old.get("refresh_token"):t["refresh_token"]=old["refresh_token"]
 t["expires_at"]=time.time()+int(t.get("expires_in",3600))
 set_token(t)
 return redirect("/?gmail=connected")
@app.get("/api/gmail/updates")
def gmail_updates():
 owner()
 result=gmail_req("GET","messages?q="+__import__("urllib.parse",fromlist=["quote"]).quote(
  'newer_than:21d ("application" OR "interview" OR "assessment" OR "internship" OR "recruitment") -from:amazon.com')+"&maxResults=40")
 def scan_item(item):
  try:
   mail=gmail_req("GET","messages/"+item["id"]+"?format=metadata&metadataHeaders=Subject&metadataHeaders=From&metadataHeaders=Date")
   headers={x["name"].lower():x["value"] for x in mail.get("payload",{}).get("headers",[])}
   title=headers.get("subject","")
   sample=mail.get("snippet","")[:250]
   s=(title+" "+sample).lower()
   if any(y in s for y in ("rejection","unfortunately","not moving forward","not selected","other candidates")):stage="Possible rejection"
   elif any(y in s for y in ("interview","schedule a call","technical round")):stage="Possible interview"
   elif any(y in s for y in ("assessment","coding challenge","online test")):stage="Possible assessment"
   else:stage="Needs review"
   return {"id":item["id"],"from":headers.get("from",""),"subject":title,"date":headers.get("date",""),"snippet":sample,"stage":stage}
  except Exception:return None
 requested=result.get("messages",[])[:40]
 with ThreadPoolExecutor(max_workers=6) as pool:
  result_items=[x for x in pool.map(scan_item,requested) if x]
 checked_at=now()
 with db.begin() as c:
  c.execute(text("INSERT INTO settings(key,value) VALUES('gmail_last_checked',:v) ON CONFLICT(key) DO UPDATE SET value=excluded.value"),{"v":checked_at})
 return {"messages":result_items,"checked_at":checked_at,"failed":len(requested)-len(result_items),
         "note":"Labels are hints, not verified outcomes. No reply was sent."}
@app.post("/api/gmail/send")
def gmail_send_reviewed():
 check_origin();persistent_only()
 body=request.get_json(silent=True) or {}
 if body.get("reviewed_and_confirmed") is not True:
  return {"error":"Explicit review and confirmation required"},422
 recipient=str(body.get("to","")).strip()[:320]
 subject=str(body.get("subject","")).strip()[:250]
 message=str(body.get("body","")).strip()[:10000]
 jid=str(body.get("job_id",""))[:64]
 if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",recipient) or not subject or len(message)<30:
  return {"error":"Recipient, subject and message must be valid"},422
 today=now()[:10]
 with db.connect() as c:
  sent=c.scalar(text("SELECT count(*) FROM email_log WHERE status='sent' AND sent_at LIKE :today"),{"today":today+"%"})
  dupe=c.execute(text("SELECT 1 FROM email_log WHERE recipient=:rec AND subject=:sub AND status='sent'"),
    {"rec":recipient,"sub":subject}).first()
 if sent>=10:return {"error":"Daily 10-email safety limit reached"},429
 if dupe:return {"error":"This exact email was already sent. Duplicate blocked."},409
 email=EmailMessage()
 email["To"]=recipient;email["Subject"]=subject
 email.set_content(message)
 if body.get("attach_original_resume"):
  with db.connect() as c:doc=c.execute(resume_table.select().where(resume_table.c.id=="original")).mappings().first()
  if not doc:return {"error":"Upload your original resume first"},409
  data=bytes(doc["content"])
  email.add_attachment(data,maintype="application",subtype="pdf",filename=doc["name"])
 encoded=base64.urlsafe_b64encode(email.as_bytes()).decode().rstrip("=")
 try:resp=gmail_req("POST","messages/send",{"raw":encoded})
 except Exception:return {"error":"Gmail rejected the send request; check your connection. No confirmed sent status."},502
 with db.begin() as c:
  c.execute(email_table.insert().values(id=secrets.token_hex(16),job_id=jid,recipient=recipient,
   subject=subject,status="sent",gmail_id=resp.get("id",""),sent_at=now()))
 return {"sent":True,"gmail_message_id":resp.get("id"),"note":"Email was sent only after your explicit confirmation."}
@app.get("/api/gmail/sent")
def gmail_sent():
 owner()
 with db.connect() as c:rows=[dict(x) for x in c.execute(email_table.select().order_by(email_table.c.sent_at.desc()).limit(100)).mappings()]
 return {"emails":rows}


# --- Dashboard alerts & application state backups ---
@app.get("/api/alerts")
def application_alerts():
 owner()
 with db.connect() as c: rows=[dict(x._mapping) for x in c.execute(text("SELECT id,company,title,url,status,discovered,updated,deadline FROM jobs LIMIT 2500"))]
 today=datetime.now(timezone.utc).date()
 alerts=[]
 for row in rows:
  base={"job_id":row["id"],"company":row["company"],"title":row["title"],"url":row["url"]}
  if row["status"]=="Discovered":
   try:
    dt=datetime.fromisoformat(row.get("discovered") or "").date()
    if 0<=(today-dt).days<=3: alerts.append({**base,"kind":"new","message":"Newly discovered role (eligibility not confirmed)"})
   except ValueError:pass
  if row["deadline"]:
   try:
    ddl=datetime.strptime(row["deadline"][:10],"%Y-%m-%d").date()
    if 0 <= (ddl-today).days <= 7 and row["status"] not in ("Rejected","Closed","Offer"):
     alerts.append({**base,"kind":"deadline","message":f"Application deadline in {(ddl-today).days} day(s)"})
   except ValueError:pass
  if row["status"] in ("Applied","Draft ready"):
   try:
    last=datetime.fromisoformat(row.get("updated") or "").date()
    if 10<=(today-last).days<=30:
     alerts.append({**base,"kind":"followup","message":"Review application status or consider a polite follow-up"})
   except ValueError:pass
 return {"alerts":alerts[:100],"count":len(alerts),"counts":{kind:sum(a["kind"]==kind for a in alerts) for kind in ("new","deadline","followup")},"checked_at":now(),
         "note":"In-app reminders shown when you open the dashboard. Push notifications are not implemented."}

@app.get("/api/backup")
def download_backup():
 owner()
 with db.connect() as c:
  jobs_data=[dict(r._mapping) for r in c.execute(text("SELECT id,company,title,location,url,provider,description,score,warnings,status,notes,deadline,discovered,updated FROM jobs LIMIT 5000"))]
  contacts_data=[dict(r._mapping) for r in c.execute(text("SELECT id,company,name,email,role,notes FROM contacts LIMIT 5000"))] if has_persistent_db() else []
 payload={"format":"opportunity-os-backup-v1","created_at":now(),"jobs":jobs_data,"contacts":contacts_data,
          "note":"Contains application data and HR contacts; keep this file private."}
 return send_file(io.BytesIO(__import__("json").dumps(payload,ensure_ascii=False).encode("utf-8")),
                  mimetype="application/json",as_attachment=True,
                  download_name="opportunity-os-private-backup.json")

@app.post("/api/restore")
def restore_backup():
 check_origin()
 f=request.files.get("file")
 if not f or not f.filename.lower().endswith(".json"):return {"error":"Upload a JSON backup file"},422
 blob=f.read(3_000_001)
 if len(blob)>3_000_000:return {"error":"Backup over 3 MB"},413
 try:payload=__import__("json").loads(blob)
 except Exception:return {"error":"Invalid JSON"},422
 if not isinstance(payload,dict):return {"error":"Not an Opportunity OS backup"},422
 if payload.get("format")!="opportunity-os-backup-v1":return {"error":"Not an Opportunity OS backup"},422
 items=payload.get("jobs") or []
 contacts=payload.get("contacts") or []
 if not isinstance(items,list) or not isinstance(contacts,list) or len(items)>5000 or len(contacts)>5000:
  return {"error":"Backup contains too many records"},422
 if contacts and not has_persistent_db():
  return {"error":"Connect permanent database before restoring private recruiter contacts"},503
 restored=0
 statuses={"Discovered","Saved","Draft ready","Applied","Assessment","Interview","Offer","Rejected","Closed"}
 with db.begin() as c:
  for j in items:
   if not isinstance(j,dict) or not secure_url(str(j.get("url",""))):continue
   try:restored_score=max(0,min(100,int(j.get("score") or 0)))
   except (ValueError,TypeError):continue
   link=str(j["url"])[:2000]
   name=str(j.get("company",""))[:150]
   role=str(j.get("title",""))[:200]
   if not name or not role:continue
   obj={"id":hashlib.sha256(link.encode()).hexdigest()[:32],"company":name,"title":role,
        "location":str(j.get("location",""))[:200],"url":link,"provider":str(j.get("provider","restored"))[:30],
        "description":str(j.get("description",""))[:5000],
        "score":restored_score,
        "warnings":str(j.get("warnings",""))[:500],
        "status":str(j.get("status","Saved")) if str(j.get("status","Saved")) in statuses else "Saved",
        "notes":str(j.get("notes",""))[:4000],"deadline":str(j.get("deadline",""))[:40],
        "discovered":str(j.get("discovered") or now())[:60],"updated":now()}
   c.execute(text("""INSERT INTO jobs(id,company,title,location,url,provider,description,score,warnings,status,notes,deadline,discovered,updated)
     VALUES(:id,:company,:title,:location,:url,:provider,:description,:score,:warnings,:status,:notes,:deadline,:discovered,:updated)
     ON CONFLICT(id) DO UPDATE SET status=excluded.status,notes=excluded.notes,deadline=excluded.deadline,updated=excluded.updated"""),obj)
   restored+=1
  for person in contacts:
   if not isinstance(person,dict):continue
   email=str(person.get("email","")).strip().lower()[:250]
   if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",email):continue
   if c.execute(text("SELECT 1 FROM contacts WHERE lower(email)=:email"),{"email":email}).first():continue
   c.execute(text("INSERT INTO contacts(id,company,name,email,role,notes) VALUES(:id,:company,:name,:email,:role,:notes)"),
    {"id":secrets.token_hex(16),"company":str(person.get("company",""))[:150],"name":str(person.get("name",""))[:150],
     "email":email,"role":str(person.get("role",""))[:150],"notes":str(person.get("notes",""))[:4000]})
 return {"ok":True,"jobs_restored":restored,"contacts_present":len(contacts)}


# Separate private automation feature. It shares the existing session and
# persistent database, and is disabled until the owner explicitly enables it.
from autoapply_engine import register as register_autoapply
register_autoapply(app, db, owner, check_origin, now, has_persistent_db, resume_table, refresh_employers=refresh_extended_impl)
