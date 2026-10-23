"""Safe tests for the on-open automated discovery and private Gmail ledger endpoints."""
from test_hosted import app,mod
from sqlalchemy import text

def signed_in():
    client=app.test_client()
    assert client.post('/api/login',json={'password':'test-secret-not-a-real-password'}).status_code==200
    return client

def test_private_mail_activity_is_owner_only_and_review_needs_real_message():
    client=app.test_client()
    assert client.get('/api/gmail/activity').status_code==401
    assert client.patch('/api/gmail/activity/fake12345/reviewed',json={}).status_code==401
    client=signed_in()
    result=client.get('/api/gmail/activity')
    assert result.status_code==200
    assert 'items' in result.json and 'counts' in result.json
    assert client.patch('/api/gmail/activity/fake12345/reviewed',json={}).status_code==404
    assert client.patch('/api/gmail/activity/fake12345/reviewed',
        headers={'Origin':'https://foreign.example'},json={}).status_code==403

def test_autodiscovery_uses_background_task_and_respects_refresh_cooldown(monkeypatch):
    client=signed_in()
    original=mod.refresh_extended_impl
    calls=[]
    class TestThread:
        def __init__(self,target,name,daemon):
            self.target=target
        def start(self):self.target()
    monkeypatch.setattr(mod,'Thread',TestThread)
    monkeypatch.setattr(mod,'refresh_extended_impl',
        lambda: calls.append('called') or {'new':2,'checked':5,'errors':[],'feeds_cached':False})
    with mod.db.begin() as c:
        for key in ('discovery_last_attempt','discovery_last_success','discovery_last_result'):
            c.execute(text("DELETE FROM settings WHERE key=:key"),{'key':key})
    assert app.test_client().post('/api/discovery/auto-refresh').status_code==401
    response=client.post('/api/discovery/auto-refresh')
    assert response.status_code==202
    assert calls==['called']
    status=client.get('/api/discovery/state')
    assert status.status_code==200
    assert status.json['status']=='ready'
    assert status.json['success_at']
    again=client.post('/api/discovery/auto-refresh')
    assert again.status_code==200
    assert again.json['result']=='cached'
    assert calls==['called']
    monkeypatch.setattr(mod,'refresh_extended_impl',original)
