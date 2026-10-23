"""Gmail metadata classification for opportunity monitoring. Never sends email."""
import re
from email.utils import parseaddr

INTERVIEW=re.compile(r"interview|schedule a call|meet with (?:our|the) team|technical round",re.I)
ASSESSMENT=re.compile(r"assessment|coding challenge|online test|hackerrank test|take.home assignment",re.I)
REJECTION=re.compile(r"unfortunately|not moving forward|we regret|other candidates|not selected",re.I)
APPLICATION=re.compile(r"internship|intern|application|job opportunity|hiring|career|developer|engineer|graduate|recruit",re.I)
AUTOMATED=re.compile(r"no.?reply|donotreply|noreply",re.I)
def sender_address(from_header):
 return parseaddr(str(from_header or ""))[1].strip().lower()
def classify_message(message,known_sent):
 """Only exact sender match is a possible reply; subject and snippet merely hint at stage."""
 subject=str(message.get("subject",""))
 snippet=str(message.get("snippet",""))
 sender=sender_address(message.get("from",""))
 text=subject+" "+snippet
 known={str(x.get("recipient","")).lower().strip() for x in known_sent}
 related=bool(sender and sender in known)
 if REJECTION.search(text):stage="Possible rejection — verify"
 elif INTERVIEW.search(text):stage="Possible interview — verify"
 elif ASSESSMENT.search(text):stage="Possible assessment — verify"
 elif APPLICATION.search(text):stage="Hiring-related message — review"
 else:stage="General email — review"
 return {**message,"stage":stage,
    "possible_reply":related and not AUTOMATED.search(sender),
    "reply_evidence":"Sender matches an outreach recipient; check actual thread." if related else
                     "No exact outbound recipient match; not marked as a reply."}
