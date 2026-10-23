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
 ("Hacker News • Hiring threads","https://hnrss.org/whoishiring/jobs?q=intern","Startup hiring")]
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
 for item in items[:90]:
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
 new=0
 with db.begin() as c:
  for items,error in results:
   for item in items:
    r=c.execute(text("""INSERT INTO radar_items(id,title,summary,url,source,category,location,
      deadline,published,seen_at,state,verification)
      VALUES(:id,:title,:summary,:url,:source,:category,:location,:deadline,:published,:seen_at,
      :state,:verification) ON CONFLICT(id) DO NOTHING"""),item)
    new+=max(0,r.rowcount)
  c.execute(text("""INSERT INTO settings(key,value) VALUES('radar_checked_at',:ts)
     ON CONFLICT(key) DO UPDATE SET value=excluded.value"""),{"ts":ts})
 return {"skipped":False,"checked_at":ts,"new":new,
         "failed_sources":[FEEDS[i][0] for i,(items,error) in enumerate(results) if error]}
def snapshot(db):
 ensure(db)
 with db.connect() as c:
  rows=[dict(r) for r in c.execute(text("""SELECT * FROM radar_items WHERE state!='dismissed'
       ORDER BY CASE WHEN state='saved' THEN 0 ELSE 1 END, seen_at DESC LIMIT 1200""")).mappings()]
  checked=c.scalar(text("SELECT value FROM settings WHERE key='radar_checked_at'"))
 return {"items":rows,"checked_at":checked,"count":len(rows),"refresh_hours":4,
     "sources":[{"name":x[0],"url":x[1]} for x in FEEDS],
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
