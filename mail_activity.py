"""Private, minimal Gmail activity ledger for application outreach.

Only mail metadata/snippets from an explicitly connected Gmail account are stored.
Classification is provisional and must never auto-change an application to Applied.
"""
import re
from email.utils import getaddresses, parseaddr
from sqlalchemy import text

def ensure(db):
 with db.begin() as c:
  c.execute(text("""CREATE TABLE IF NOT EXISTS mail_activity (
    id VARCHAR(128) PRIMARY KEY, thread_id TEXT, direction TEXT, sender TEXT,
    recipients TEXT, subject TEXT, snippet TEXT, date TEXT, stage TEXT,
    reply_match TEXT, reviewed INTEGER DEFAULT 0, updated TEXT)"""))

def ingest(db, timestamp, inbox, outbox):
 ensure(db)
 sent_threads={str(m.get("gmail_thread_id") or "") for m in outbox
               if str(m.get("gmail_thread_id") or "")}
 sent_emails={addr.lower() for row in outbox for _,addr in
              getaddresses([str(row.get("to") or "")]) if addr}
 processed=0
 with db.begin() as c:
  for mail in outbox[:100]:
   mid=str(mail.get("id") or "")
   if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}",mid):continue
   c.execute(text("""INSERT INTO mail_activity
     (id,thread_id,direction,sender,recipients,subject,snippet,date,stage,
      reply_match,reviewed,updated)
     VALUES(:id,:thread,'sent','','',:subject,'',:date,'Sent',
       'Gmail Sent folder; delivery not independently confirmed',0,:updated)
     ON CONFLICT(id) DO UPDATE SET subject=excluded.subject,
       thread_id=excluded.thread_id,date=excluded.date,updated=excluded.updated"""),
     {"id":mid,"thread":str(mail.get("gmail_thread_id") or "")[:120],
      "subject":str(mail.get("subject") or "")[:250],
      "date":str(mail.get("date") or "")[:90],"updated":timestamp})
   # Separate recipient field can be updated safely when available.
   c.execute(text("UPDATE mail_activity SET recipients=:to WHERE id=:id"),
             {"to":str(mail.get("to") or "")[:320],"id":mid})
   processed+=1
  for mail in inbox[:100]:
   mid=str(mail.get("id") or "")
   if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}",mid):continue
   sender=parseaddr(str(mail.get("from") or ""))[1].lower()
   thread=str(mail.get("thread_id") or "")[:120]
   on_thread=bool(thread and thread in sent_threads and sender)
   direct=bool(sender and sender in sent_emails)
   possible_reply=(on_thread or direct) and not bool(re.search(r"no.?reply|donotreply",sender,re.I))
   why=("Same Gmail conversation thread as sent outreach" if on_thread else
        "Sender matches an outgoing recipient" if direct else
        "Not matched to an outgoing message")
   category=str(mail.get("stage") or "Needs review")[:90]
   c.execute(text("""INSERT INTO mail_activity
     (id,thread_id,direction,sender,recipients,subject,snippet,date,stage,
      reply_match,reviewed,updated)
     VALUES(:id,:thread,'received',:sender,'',:subject,:snippet,:date,:stage,
       :reply,0,:updated)
     ON CONFLICT(id) DO UPDATE SET thread_id=excluded.thread_id,
       sender=excluded.sender,subject=excluded.subject,snippet=excluded.snippet,
       date=excluded.date,stage=excluded.stage,reply_match=excluded.reply_match,
       updated=excluded.updated"""),
     {"id":mid,"thread":thread,"sender":sender[:320],
      "subject":str(mail.get("subject") or "")[:250],
      "snippet":str(mail.get("snippet") or "")[:400],
      "date":str(mail.get("date") or "")[:90],"stage":category,
      "reply":why if possible_reply else "Not matched to outgoing outreach",
      "updated":timestamp})
   processed+=1
 return {"processed":processed,"possible_replies":sum(bool(
    (str(m.get("thread_id") or "") in sent_threads or
      parseaddr(str(m.get("from") or ""))[1].lower() in sent_emails))
    for m in inbox)}

def snapshot(db):
 ensure(db)
 with db.connect() as c:
  rows=[dict(x) for x in c.execute(text("""SELECT id,thread_id,direction,sender,
    recipients,subject,snippet,date,stage,reply_match,reviewed,updated
    FROM mail_activity ORDER BY updated DESC LIMIT 160""")).mappings()]
  counts={x["direction"]:x["count"] for x in c.execute(text(
   "SELECT direction,count(*) AS count FROM mail_activity GROUP BY direction")).mappings()}
 return {"items":rows,"counts":counts,
   "explanation":"Saved Gmail metadata only. Sending does not prove delivery; reply and hiring-stage classification require review."}

def mark_reviewed(db,mid):
 if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}",mid):return False
 ensure(db)
 with db.begin() as c:
  res=c.execute(text("UPDATE mail_activity SET reviewed=1 WHERE id=:id AND direction='received'"),{"id":mid})
 return bool(res.rowcount)
