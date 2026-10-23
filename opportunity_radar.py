"""Multi-source, opt-in opportunity radar. Discovery only; never auto-submit."""
import html, hashlib, re, requests
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET
from urllib.parse import urlsplit
from sqlalchemy import text

FEEDS=[
 ("Brabble • Hackathons","https://brabble.ai/rss/hackathons.xml","Hackathon"),
 ("Brabble • Delhi NCR","https://brabble.ai/rss/in/delhi-ncr.xml","Event"),
 ("DEV • Hackathons","https://dev.to/feed/tag/hackathon","Community post"),
 ("DEV • Internships","https://dev.to/feed/tag/internship","Community post"),
 ("Hacker News • YC jobs","https://hnrss.org/jobs","Startup hiring"),
 ("Hacker News • Hiring threads","https://hnrss.org/whoishiring/jobs?q=intern","Startup hiring"),
 ("Himalayas • Remote jobs","https://himalayas.app/jobs/rss","Internship"),
 ("InternScan • Global internships","https://internscan.vercel.app/feed.xml","Internship"),
 ("DEV • Hiring announcements","https://dev.to/feed/tag/hiring","Community post"),
 ("DEV • Fellowships","https://dev.to/feed/tag/fellowship","Community post"),
 ("DEV • Developer challenges","https://dev.to/feed/tag/devchallenge","Community post")]
CATEGORIES=("Hackathon","Event","Community post","Startup hiring","Internship","Fellowship","Scholarship","Other")
STATES=("new","saved","dismissed")
TAG=re.compile(r"<[^>]*>")
CTA=re.compile(r"hackathon|competition|challenge|register|application|apply|hiring|internship|intern|fellowship|job|recruit",re.I)
def safe_link(url):
 try:
  u=urlsplit(url or "")
  return u.scheme=="https" and bool(u.hostname) and not u.username and not u.password
 except (ValueError,TypeError):return False
def clean(s,n=360):
 return " ".join(TAG.sub(" ",html.unescape(str(s or ""))).split())[:n]
def ensure(db):
 with db.begin() as c:
  c.execute(text("""CREATE TABLE IF NOT EXISTS radar_items (
    id VARCHAR(64) PRIMARY KEY,title TEXT,summary TEXT,url TEXT,source TEXT,
    category TEXT,location TEXT,deadline TEXT,published TEXT,seen_at TEXT,
    state TEXT,verification TEXT)"""))
def parse_feed(body,source,category,ts):
 try:root=ET.fromstring(body[:1500000])
 except (ET.ParseError,ValueError):return []
 items=root.findall(".//item")
 atom=False
 if not items:
  atom=True;items=root.findall(".//{http://www.w3.org/2005/Atom}entry")
 results=[];seen=set()
 for item in items[:250]:
  def value(*tags):
   for tag in tags:
    x=item.find(tag)
    if x is not None and x.text:return x.text.strip()
   return ""
  title=clean(value("title","{http://www.w3.org/2005/Atom}title"),180)
  summary=clean(value("description","{http://www.w3.org/2005/Atom}summary",
             "{http://www.w3.org/2005/Atom}content"))
  if atom:
   links=item.findall("{http://www.w3.org/2005/Atom}link")
   url=next((x.attrib.get("href","") for x in links if safe_link(x.attrib.get("href",""))),"")
   published=value("{http://www.w3.org/2005/Atom}published")
  else:
   url=value("link");published=value("pubDate")
  if not title or not safe_link(url):continue
  if source.startswith("DEV") and not CTA.search(title):continue
  if source.startswith("Himalayas"):
   if not re.search(r"\b(intern|internship|junior|graduate|trainee|apprentice|entry.level)\b",title,re.I):continue
   if not re.search(r"\b(software|backend|developer|engineering|python|data|ai|machine learning|cloud|devops|security|platform|frontend|full.stack)\b",title,re.I):continue
   if re.search(r"\b(senior|staff|principal|lead|manager|director)\b",title,re.I):continue
  if source.startswith("InternScan") and re.search(r"\b(PhD|doctorate|postdoctoral)\b",title,re.I):continue
  if published:
   try:
    dt=parsedate_to_datetime(published)
    if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
    if (datetime.now(timezone.utc)-dt).days>45:continue
   except (ValueError,TypeError,OverflowError):pass
  uid=hashlib.sha256(url.split("#")[0].rstrip("/").encode()).hexdigest()[:32]
  if uid in seen:continue
  seen.add(uid)
  results.append(dict(id=uid,title=title,summary=summary or "Read original post for details.",
   url=url,source=source,category="Hackathon" if "hackathon" in title.lower() else category,
   location="See organizer / original post",deadline="",published=published[:80],
   seen_at=ts,state="new",verification="Unverified opportunity lead; check dates and eligibility."))
 return results
def fetch(entry,ts):
 source,url,category=entry
 try:
  res=requests.get(url,timeout=9,headers={"User-Agent":"OpportunityOS/2.0","Accept":"application/rss+xml, application/xml, text/xml"})
  res.raise_for_status()
  return parse_feed(res.content,source,category,ts),None
 except (requests.RequestException,ValueError):
  return [],source+" unavailable"
def refresh(db,clock):
 ensure(db)
 with db.connect() as c:last=c.scalar(text("SELECT value FROM settings WHERE key='radar_checked_at'"))
 try:
  if last and datetime.now(timezone.utc)-datetime.fromisoformat(last)<timedelta(hours=4):
   return {"skipped":True,"checked_at":last,"new":0}
 except (ValueError,TypeError):pass
 ts=clock()
 with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(lambda f:fetch(f,ts),FEEDS))
 # Optional, authorized structured listing feed. The public RSS remains available.
 from brabble_intelligence import fetch_brabble
 api_items,api_error=fetch_brabble(ts)
 new=0
 with db.begin() as c:
  for items,error in results:
   for item in items:
    r=c.execute(text("""INSERT INTO radar_items(id,title,summary,url,source,category,location,
      deadline,published,seen_at,state,verification)
      VALUES(:id,:title,:summary,:url,:source,:category,:location,:deadline,:published,:seen_at,
      :state,:verification) ON CONFLICT(id) DO NOTHING"""),item)
    new+=max(0,r.rowcount)
  for item in api_items:
   was_present=bool(c.execute(text("SELECT 1 FROM radar_items WHERE id=:id"),
      {"id":item["id"]}).first())
   r=c.execute(text("""INSERT INTO radar_items(id,title,summary,url,source,category,location,
       deadline,published,seen_at,state,verification)
       VALUES(:id,:title,:summary,:url,:source,:category,:location,:deadline,:published,:seen_at,
         :state,:verification)
       ON CONFLICT(id) DO UPDATE SET
         deadline=CASE WHEN excluded.deadline!='' THEN excluded.deadline ELSE radar_items.deadline END,
         summary=excluded.summary,location=excluded.location,verification=excluded.verification
       """),item)
   if not was_present:new+=1
  c.execute(text("""INSERT INTO settings(key,value) VALUES('brabble_api_error',:error)
    ON CONFLICT(key) DO UPDATE SET value=excluded.value"""),
    {"error":api_error or ""})
  c.execute(text("""INSERT INTO settings(key,value) VALUES('radar_checked_at',:ts)
     ON CONFLICT(key) DO UPDATE SET value=excluded.value"""),{"ts":ts})
  c.execute(text("""INSERT INTO settings(key,value) VALUES('radar_source_errors',:err)
     ON CONFLICT(key) DO UPDATE SET value=excluded.value"""),
     {"err":"|".join(FEEDS[i][0] for i,(items,error) in enumerate(results) if error)})
 return {"skipped":False,"checked_at":ts,"new":new,
         "failed_sources":[FEEDS[i][0] for i,(items,error) in enumerate(results) if error]+
         (["Brabble API"] if api_error else [])}
def snapshot(db):
 ensure(db)
 with db.connect() as c:
  rows=[dict(r) for r in c.execute(text("""SELECT * FROM radar_items WHERE state!='dismissed'
       ORDER BY CASE WHEN state='saved' THEN 0 ELSE 1 END, seen_at DESC LIMIT 3000""")).mappings()]
  checked=c.scalar(text("SELECT value FROM settings WHERE key='radar_checked_at'"))
  last_errors=c.scalar(text("SELECT value FROM settings WHERE key='radar_source_errors'"))
  api_error=c.scalar(text("SELECT value FROM settings WHERE key='brabble_api_error'"))
 return {"items":rows,"checked_at":checked,"count":len(rows),"failed_sources":((last_errors or "").split("|") if last_errors else [])+
         (["Brabble API"] if api_error else []),"refresh_hours":4,
     "sources":[{"name":x[0],"url":x[1]} for x in FEEDS]+
       ([{"name":"Brabble • college-student API","url":"https://brabble.ai/developers"}]
         if __import__("os").environ.get("BRABBLE_API_KEY") else []),
     "attribution":"Brabble.ai (public RSS). Original organizer controls registration."}
def save(db,clock,data):
 ensure(db)
 title=clean(data.get("title"),190);url=str(data.get("url","")).strip()[:2000]
 category=data.get("category","Community post")
 if len(title)<5 or not safe_link(url) or category not in CATEGORIES:raise ValueError("Valid title, category and HTTPS URL required")
 uid=hashlib.sha256(url.split("#")[0].rstrip("/").encode()).hexdigest()[:32]
 item=dict(id=uid,title=title,summary=clean(data.get("summary"),500) or "Owner-added link; read original source.",
   url=url,source="Saved link",category=category,location="See original post",deadline="",
   published="",seen_at=clock(),state="saved",
   verification="Owner-added post, not independently verified and not an application.")
 with db.begin() as c:
  c.execute(text("""INSERT INTO radar_items(id,title,summary,url,source,category,location,
    deadline,published,seen_at,state,verification)
    VALUES(:id,:title,:summary,:url,:source,:category,:location,:deadline,:published,
    :seen_at,:state,:verification) ON CONFLICT(id) DO NOTHING"""),item)
 return uid
def mark(db,uid,state):
 if state not in STATES:raise ValueError("Invalid state")
 with db.begin() as c:
  result=c.execute(text("UPDATE radar_items SET state=:state WHERE id=:id"),{"state":state,"id":uid})
 return bool(result.rowcount)

def ingest_mail_opportunities(db,clock,messages):
 """Save hiring/event announcements to the private radar as unverified leads."""
 ensure(db)
 inserted=0
 exclude=re.compile(r"rejection|not selected|thank you for applying|application received|interview|assessment|feedback|receipt|submission confirmed",re.I)
 ts=clock()
 with db.begin() as c:
  for message in messages[:40]:
   uid=str(message.get("id") or "")
   title=clean(message.get("subject"),180)
   if not re.fullmatch(r"[a-f0-9]{12,25}",uid) or not CTA.search(title) or exclude.search(title):
    continue
   category="Hackathon" if "hackathon" in title.lower() else "Internship" if re.search(r"internship|intern",title,re.I) else "Startup hiring"
   body=clean(message.get("snippet"),280) or "Open Gmail to verify the original announcement."
   rid=hashlib.sha256(("gmail:"+uid).encode()).hexdigest()[:32]
   item={"id":rid,"title":title,"summary":body,
     "url":"https://mail.google.com/mail/u/0/#all/"+uid,
     "source":"Gmail · opening alert","category":category,"location":"See original email",
     "deadline":"","published":message.get("date","")[:80],"seen_at":ts,"state":"new",
     "verification":"Inbox lead only; employer identity, opening and deadline not verified."}
   result=c.execute(text("""INSERT INTO radar_items(id,title,summary,url,source,category,
      location,deadline,published,seen_at,state,verification)
      VALUES(:id,:title,:summary,:url,:source,:category,:location,:deadline,:published,:seen_at,:state,:verification)
      ON CONFLICT(id) DO NOTHING"""),item)
   inserted+=max(0,result.rowcount)
 return inserted
