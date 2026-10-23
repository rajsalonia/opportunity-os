"""Regression tests for opportunity brief sources and private Gmail ledger."""
from sqlalchemy import create_engine, text
from opportunity_radar import FEEDS, parse_feed
from mail_activity import ingest, snapshot, mark_reviewed


def test_public_rss_sources_and_shortlist_quality():
    names={row[0] for row in FEEDS}
    assert "Himalayas • Remote jobs" in names
    assert "InternScan • Global internships" in names
    feed=b"""<rss><channel>
     <item><title>Senior Software Developer</title><link>https://himalayas.app/jobs/senior-1</link></item>
     <item><title>Backend Engineering Intern</title><link>https://himalayas.app/jobs/backend-1</link>
       <description>Learn FastAPI on a remote startup team.</description></item>
     <item><title>Junior Marketing Associate</title><link>https://himalayas.app/jobs/marketing-1</link></item>
    </channel></rss>"""
    found=parse_feed(feed,"Himalayas • Remote jobs","Internship","2026-10-23T00:00:00+00:00")
    assert len(found)==1
    assert found[0]["category"]=="Internship"
    assert found[0]["title"]=="Backend Engineering Intern"
    assert found[0]["verification"].startswith("Unverified")


def test_private_mail_log_preserves_review_state_and_receipt_caveat(tmp_path):
    db=create_engine("sqlite:///"+str(tmp_path/"mail.db"))
    sent=[{"id":"sentmsg123","gmail_thread_id":"threadAB123","to":"hire@example.com",
           "subject":"Application for internship","date":"2026-10-23"}]
    inbound=[{"id":"inbound123","thread_id":"threadAB123","from":"Recruiter <hire@example.com>",
        "subject":"Re: Application for internship","snippet":"Can we schedule a call?",
        "date":"2026-10-24","stage":"Possible interview"},
        {"id":"autonoreply12","thread_id":"threadAB123","from":"no-reply@example.com",
         "subject":"Automated receipt","snippet":"This is an automated response.",
         "date":"2026-10-24","stage":"Needs review"}]
    first=ingest(db,"2026-10-24T08:00:00Z",inbound,sent)
    assert first["processed"]==3
    assert first["possible_replies"]==1
    data=snapshot(db)
    assert data["counts"]["sent"]==1 and data["counts"]["received"]==2
    assert mark_reviewed(db,"inbound123")
    second=ingest(db,"2026-10-24T09:00:00Z",inbound,sent)
    assert second["processed"]==3
    all_rows=snapshot(db)["items"]
    assert len(all_rows)==3
    assert next(r for r in all_rows if r["id"]=="inbound123")["reviewed"]==1
    assert "delivery not independently confirmed" in data["explanation"].lower() or "Sending does not prove delivery" in data["explanation"]
    assert not mark_reviewed(db,"unknown123")
    db.dispose()
