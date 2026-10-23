"""Gmail opportunity classification: deterministic hints, never automatic stage changes."""
import re
from email.utils import parseaddr

DELIVERY=re.compile(r"undeliverable|delivery (?:has )?failed|mail delivery (?:subsystem|failure)|address not found|recipient unknown|couldn.t be delivered|delivery status notification",re.I)
AUTO_REPLY=re.compile(r"automatic reply|auto.?reply|out.of.office|out of (?:the )?office|on pto|vacation responder|away from (?:the )?office",re.I)
REJECTION=re.compile(r"unfortunately|not moving forward|we regret|other candidates|not selected|unable to proceed with your application",re.I)
RECEIPT=re.compile(r"thank you for (?:your |the )?application|we (?:have )?received your application|application (?:received|submitted|confirmation)|thanks for (?:filling out|applying)|we've received your application",re.I)
INTERVIEW=re.compile(r"interview invitation|interview scheduled|schedule (?:an? )?(?:interview|call)|meet with (?:our|the) team|technical round|invited to interview",re.I)
ASSESSMENT=re.compile(r"assessment invitation|coding challenge|online test|hackerrank test|take.home assignment|assessment link",re.I)
APPLICATION=re.compile(r"internship|intern|application|job opportunity|hiring|career|developer|engineer|graduate|recruit",re.I)
AUTOMATED_SENDER=re.compile(r"no.?reply|donotreply|noreply|mailer-daemon|postmaster",re.I)

def sender_address(from_header):
    return parseaddr(str(from_header or ""))[1].strip().lower()

def classify_message(message,known_sent):
    """Classify messages without treating auto-replies or bounces as human replies."""
    subject=str(message.get("subject",""))
    snippet=str(message.get("snippet",""))
    sender=sender_address(message.get("from",""))
    info=subject+" "+snippet
    known={str(x.get("recipient","")).lower().strip() for x in known_sent}
    related=bool(sender and sender in known)
    if DELIVERY.search(info):
        stage="Delivery failure"
    elif AUTO_REPLY.search(info):
        stage="Automated reply"
    elif REJECTION.search(info):
        stage="Possible rejection"
    elif RECEIPT.search(info):
        stage="Application received"
    elif INTERVIEW.search(info):
        stage="Possible interview"
    elif ASSESSMENT.search(info):
        stage="Possible assessment"
    elif APPLICATION.search(info):
        stage="Needs review"
    else:
        stage="Needs review"
    human=stage not in ("Delivery failure","Automated reply") and not AUTOMATED_SENDER.search(sender)
    return {**message,"stage":stage,"possible_reply":bool(related and human),
        "reply_evidence":("Sender matches outreach recipient; verify original Gmail thread." if related and human else
            "Automatic notice, not a human recruiter reply." if not human else
            "No exact outgoing-recipient match; classification is provisional.")}
