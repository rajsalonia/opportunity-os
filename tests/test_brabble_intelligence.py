"""Structured Brabble source stays optional and never fabricates deadlines."""
from datetime import datetime, timedelta, timezone
from brabble_intelligence import normalize, fetch_brabble

def sample(**kwargs):
    value={"title":"Community Cloud Hackathon 2026","organiser":"Student tech club",
        "shareUrl":"https://brabble.ai/open/community-cloud","url":"https://organizer.example/register",
        "type":"HACKATHON","platform":"Unstop","team":"1-4","fee":"Free",
        "mode":"ONLINE","eligibility":["College students"],"prize":{"label":"See listing"},
        "deadline":(datetime.now(timezone.utc)+timedelta(days=10)).isoformat()}
    value.update(kwargs)
    return value

def test_normalization_keeps_source_link_and_real_deadline():
    item=normalize(sample(),"2026-10-24T00:00:00Z")
    assert item["url"]=="https://brabble.ai/open/community-cloud"
    assert item["deadline"]
    assert item["category"]=="Hackathon"
    assert "Student tech club" in item["summary"]
    assert "1-4" in item["summary"]
    assert "not" not in item["deadline"].lower()
    assert "Brabble" in item["verification"]

def test_rejects_malformed_and_expired_entries():
    assert normalize(sample(shareUrl="javascript:alert(1)",url=""),"now") is None
    assert normalize(sample(deadline="2020-01-01T00:00:00Z"),"now") is None
    assert normalize(sample(title=""),"now") is None

def test_no_key_never_makes_external_request():
    assert fetch_brabble("now",key="",http_get=lambda *args,**kw: (_ for _ in ()).throw(AssertionError()))==([],None)

def test_paginated_api_merges_duplicate_leads_with_source_attribution():
    calls=[]
    class Response:
        def raise_for_status(self):pass
        def json(self):return {"listings":[sample(),sample()], "total":2}
    def fake_get(url,**kwargs):
        calls.append((url,kwargs))
        return Response()
    records,error=fetch_brabble("2026-10-24T00:00:00Z",key="test-key",http_get=fake_get)
    assert error is None and len(records)==1 and len(calls)==1
    assert calls[0][1]["headers"]["Authorization"]=="Bearer test-key"
    assert "Brabble" in records[0]["source"]
