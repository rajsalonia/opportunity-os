"""Opportunity Radar does not imply registration or job submission."""
import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from opportunity_radar import parse_feed, refresh, snapshot, save, mark, FEEDS

@pytest.fixture
def db(tmp_path):
    engine=create_engine("sqlite:///"+str(tmp_path/"radar.db"))
    with engine.begin() as c:
        c.execute(text("CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT)"))
    yield engine
    engine.dispose()

def test_rss_feed_deduplicates_and_sanitizes_markup():
    feed=b"""<rss><channel>
    <item><title>Delhi Hackathon &amp; AI Challenge</title>
      <link>https://organizer.example/hacks</link>
      <description><![CDATA[<b>Join</b> the hackathon to build climate tools.]]></description></item>
    <item><title>Delhi Hackathon</title><link>https://organizer.example/hacks</link></item>
    <item><title>Unsafe</title><link>javascript:alert(1)</link></item>
    </channel></rss>"""
    parsed=parse_feed(feed,"Brabble - Hackathons","Hackathon","2026-10-23T00:00:00+00:00")
    assert len(parsed)==1
    assert parsed[0]["category"]=="Hackathon"
    assert "<b>" not in parsed[0]["summary"]
    assert parsed[0]["state"]=="new"
    assert "Unverified" in parsed[0]["verification"]

def test_owner_saved_public_post_needs_review(db):
    uid=save(db,lambda:"2026-10-23T08:00:00+00:00",{
      "title":"Company shares a backend internship","url":"https://www.linkedin.com/posts/company/internship-test-123",
      "category":"Internship","summary":"Contact organizer for eligibility. <script>ignore</script>"})
    record=next(x for x in snapshot(db)["items"] if x["id"]==uid)
    assert record["state"]=="saved"
    assert record["source"]=="Saved link"
    assert "not an application" in record["verification"]
    assert "<script>" not in record["summary"]
    assert mark(db,uid,"dismissed") is True
    assert not snapshot(db)["items"]
    with pytest.raises(ValueError):mark(db,uid,"unverified")

def test_bad_owner_links_cannot_be_imported(db):
    for link in ["javascript:alert(1)","http://example.com","file:///tmp/x","https://user:pass@example.com"]:
        with pytest.raises(ValueError):
            save(db,lambda:"now",{"title":"Hackathon opening","url":link,"category":"Hackathon"})

def test_refresh_caches_and_preserves_saved_status(db,monkeypatch):
    import opportunity_radar as radar
    calls=[]
    def mocked_feed(item,ts):
        calls.append(item[0])
        return ([dict(id="a"*32,title="Climate build contest",summary="Open hackathon",
          url="https://example.org/build",source="Brabble - Hackathons",
          category="Hackathon",location="See organizer",deadline="",published="",
          seen_at=ts,state="new",verification="Check organizer")] if item is FEEDS[0] else []),None
    monkeypatch.setattr(radar,"fetch",mocked_feed)
    now=lambda:datetime.now(timezone.utc).isoformat()
    first=refresh(db,now)
    assert first["new"]==1
    assert len(calls)==len(FEEDS)
    assert mark(db,"a"*32,"saved")
    second=refresh(db,now)
    assert second["skipped"] is True
    assert snapshot(db)["items"][0]["state"]=="saved"
