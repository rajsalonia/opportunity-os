"""Classification tests for real-world opportunity mailbox states."""
from sqlalchemy import create_engine
from inbox_intelligence import classify_message
from mail_activity import ingest, snapshot

def test_bounces_and_ooo_never_count_as_recruiter_replies():
    sent=[{"recipient":"recruiter@example.org"}]
    ooo=classify_message({"id":"b"*16,"from":"Recruiter <recruiter@example.org>",
        "subject":"Automatic reply: internship inquiry","snippet":"I am on PTO"},sent)
    assert ooo["stage"]=="Automated reply"
    assert ooo["possible_reply"] is False
    bounce=classify_message({"id":"c"*16,"from":"postmaster@example.org",
        "subject":"Undeliverable: software engineering internship inquiry","snippet":"recipient unknown"},sent)
    assert bounce["stage"]=="Delivery failure"
    assert bounce["possible_reply"] is False

def test_receipt_rejection_and_human_reply_are_distinct():
    sent=[{"recipient":"hr@example.org"}]
    receipt=classify_message({"from":"no-reply@jobs.example.org","subject":"Thank you for your application",
         "snippet":"We received your application for Engineering Intern."},sent)
    assert receipt["stage"]=="Application received"
    reject=classify_message({"from":"HR <hr@example.org>","subject":"Application update",
        "snippet":"Unfortunately, we are moving forward with other candidates."},sent)
    assert reject["stage"]=="Possible rejection"
    assert reject["possible_reply"] is True
    human=classify_message({"from":"HR <hr@example.org>","subject":"Re: Internship",
        "snippet":"Can you share availability?"},sent)
    assert human["possible_reply"] is True

def test_ledger_never_overrides_automated_classification_with_thread_match(tmp_path):
    engine=create_engine("sqlite:///"+str(tmp_path/"mail.db"))
    outbox=[{"id":"a"*16,"gmail_thread_id":"thread123","subject":"Internship inquiry",
             "to":"hr@example.org","date":"today"}]
    inbox=[{"id":"b"*16,"thread_id":"thread123","from":"HR <hr@example.org>",
            "subject":"Automatic reply","snippet":"On PTO","stage":"Automated reply",
            "possible_reply":True,"date":"today"}]
    counts=ingest(engine,"2026-10-24T00:00:00Z",inbox,outbox)
    assert counts["possible_replies"]==0
    rows=snapshot(engine)["items"]
    incoming=[x for x in rows if x["direction"]=="received"][0]
    assert incoming["stage"]=="Automated reply"
    assert incoming["reply_match"]=="Not matched to outgoing outreach"
