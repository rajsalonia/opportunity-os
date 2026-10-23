"""Behavioral coverage for the redesigned private workspace and retained APIs."""
import base64
import hashlib
import io
import json
from email import policy
from email.parser import BytesParser
from unittest.mock import Mock

from test_hosted import app, mod
from sqlalchemy import text
from sqlalchemy.exc import OperationalError


def signed_in():
    client = app.test_client()
    assert client.post('/api/login', json={'password':'test-secret-not-a-real-password'}).status_code == 200
    return client


def add_job(client, suffix, **extra):
    payload = dict(company='Verification Company', title='Python Backend Intern',
                   location='Delhi India', url='https://example.org/verification/' + suffix)
    payload.update(extra)
    response = client.post('/api/jobs', json=payload)
    assert response.status_code == 200
    return response.json['id']


def test_public_html_excludes_private_workspace_and_logout_clears_access():
    with app.test_client() as client:
        page = client.get('/').data.decode()
        assert 'Dashboard password' in page
        assert 'id="workspace"' not in page
        assert 'rajsalonia1@gmail.com' not in page
        for path in ['/api/jobs','/api/summary','/api/contacts','/api/integrations',
                     '/api/resume/download','/api/resume/verify','/api/gmail/sent',
                     '/api/backup','/api/alerts','/api/sources']:
            assert client.get(path).status_code == 401
        client.post('/api/login',json={'password':'test-secret-not-a-real-password'})
        page = client.get('/').data.decode()
        for section in ['overview','explore','applications','contacts','gmail','resume','sources','settings']:
            assert f'id="page-{section}"' in page
        assert client.post('/api/logout',headers={'Origin':'https://foreign.example'}).status_code == 403
        assert client.get('/api/session').json['authenticated'] is True
        assert client.post('/api/logout').status_code == 200
        assert client.get('/api/jobs').status_code == 401
        assert 'id="workspace"' not in client.get('/').data.decode()


def test_job_search_all_stages_notes_and_deadline_roundtrip():
    client = signed_in()
    jid = add_job(client,'deadline-roundtrip')
    for stage in ['Discovered','Saved','Draft ready','Applied','Assessment','Interview','Offer','Rejected','Closed']:
        response = client.patch('/api/jobs/'+jid,json={'status':stage,'notes':'Next: review employer criteria','deadline':'2027-01-15'})
        assert response.status_code == 200
        jobs = client.get('/api/jobs?q=Verification&status='+stage).json['jobs']
        job = next(job for job in jobs if job['id'] == jid)
        assert job['status'] == stage and job['deadline'] == '2027-01-15'
    assert client.patch('/api/jobs/'+jid,json={'status':'Applied','deadline':'not-a-date'}).status_code == 422
    assert client.patch('/api/jobs/'+jid,json={'status':'Applied','deadline':'2027-02-30'}).status_code == 422
    assert client.patch('/api/jobs/'+jid,json={'status':'Automatic apply'}).status_code == 422
    assert client.patch('/api/jobs/'+jid,json={'status':'Saved','deadline':''}).status_code == 200
    job = next(job for job in client.get('/api/jobs').json['jobs'] if job['id'] == jid)
    assert job['notes'] == 'Next: review employer criteria' and job['deadline'] == ''


def test_csv_export_escapes_formula_cells_and_safe_url_validation():
    client = signed_in()
    add_job(client,'csv-formula',company='=HYPERLINK("https://example.org")')
    response = client.get('/api/export')
    assert response.status_code == 200
    assert "'=HYPERLINK" in response.data.decode()
    assert 'attachment' in response.headers['Content-Disposition']
    for link in ['javascript:alert(1)','http://example.org','https://user:secret@example.org/job']:
        assert client.post('/api/jobs',json={'company':'Invalid','title':'Intern','url':link}).status_code == 422


def test_private_contact_create_csv_xlsx_import_and_deduplication(monkeypatch):
    from openpyxl import Workbook
    monkeypatch.setattr(mod,'has_persistent_db',lambda:True)
    client = signed_in()
    assert client.post('/api/contacts',json={'company':'CRM Verify','name':'Test Recruiter','email':'crm-verify@example.org','role':'Python Intern'}).status_code == 200
    csv_data = b'Company,Name,Email,Role\nImport Verify,Test Contact,import-verify@example.org,Backend\nImport Verify,Duplicate,import-verify@example.org,AI\nInvalid,No address,invalid,Cloud\n'
    response = client.post('/api/contacts/import',data={'file':(io.BytesIO(csv_data),'contacts.csv')})
    assert response.status_code == 200 and response.json['imported'] == 1 and response.json['skipped'] == 2
    book = Workbook(); sheet = book.active
    sheet.append(['Company','Name','Email','Role']); sheet.append(['XLSX Verify','Test Name','xlsx-verify@example.org','AI Intern'])
    output = io.BytesIO(); book.save(output); output.seek(0)
    response = client.post('/api/contacts/import',data={'file':(output,'contacts.xlsx')})
    assert response.status_code == 200 and response.json['imported'] == 1
    people = client.get('/api/contacts').json['contacts']
    assert any(p['email'] == 'xlsx-verify@example.org' and p['role'] == 'AI Intern' for p in people)


def test_original_resume_bytes_hash_verification_and_replacement_protection(monkeypatch):
    monkeypatch.setattr(mod,'has_persistent_db',lambda:True)
    client = signed_in()
    original = b'%PDF-1.4\n% Synthetic test fixture only\n1 0 obj\n<<>>\nendobj\n%%EOF\n'
    digest = hashlib.sha256(original).hexdigest()
    monkeypatch.setenv('ORIGINAL_RESUME_SHA256',digest)
    with mod.db.begin() as conn:
        conn.execute(mod.resume_table.delete())
    response = client.post('/api/resume',data={'file':(io.BytesIO(original),'test-only.pdf')})
    assert response.status_code == 200 and response.json['sha256'] == digest
    assert client.get('/api/resume/download').data == original
    assert client.get('/api/resume/verify').json['verified'] is True
    caps = client.get('/api/integrations').json
    assert caps['resume_bytes'] == len(original) and caps['resume_sha256'] == digest
    assert caps['resume_updated'] and caps['database_connected'] is True
    assert client.post('/api/resume',data={'file':(io.BytesIO(original),'same.pdf')}).status_code == 200
    monkeypatch.delenv('ORIGINAL_RESUME_SHA256')
    different = b'%PDF-1.4\n% Different test-only file\n%%EOF'
    assert client.post('/api/resume',data={'file':(io.BytesIO(different),'different.pdf')}).status_code == 409
    assert client.get('/api/resume/download').data == original
    with mod.db.begin() as conn:
        conn.execute(mod.resume_table.update().values(hash='0'*64))
    assert client.get('/api/resume/verify').json['verified'] is False
    with mod.db.begin() as conn:
        conn.execute(mod.resume_table.delete())


def test_reviewed_email_gates_and_duplicate_block_no_external_send(monkeypatch):
    monkeypatch.setattr(mod,'has_persistent_db',lambda:True)
    sender = Mock(return_value={'id':'synthetic-message-id'})
    monkeypatch.setattr(mod,'gmail_req',sender)
    client = signed_in()
    payload = {'to':'reviewed-verify@example.org','subject':'Synthetic test only','body':'This is a synthetic test of explicit individual email review, never sent externally.'}
    assert client.post('/api/gmail/send',json=payload).status_code == 422
    sender.assert_not_called()
    response = client.post('/api/gmail/send',json={**payload,'reviewed_and_confirmed':True})
    assert response.status_code == 200 and response.json['sent'] is True
    sender.assert_called_once()
    method,path,data = sender.call_args.args
    assert method == 'POST' and path == 'messages/send'
    email = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(data['raw']+'==='))
    assert str(email['To']) == payload['to'] and str(email['Subject']) == payload['subject']
    assert client.post('/api/gmail/send',json={**payload,'reviewed_and_confirmed':True}).status_code == 409
    sender.assert_called_once()
    assert any(row['recipient'] == payload['to'] for row in client.get('/api/gmail/sent').json['emails'])


def test_gmail_reply_labels_and_last_checked_are_real_fetch_metadata(monkeypatch):
    def fake_gmail(method,path,payload=None):
        if path.startswith('messages?'):return {'messages':[{'id':'synthetic-mail'}]}
        return {'payload':{'headers':[{'name':'Subject','value':'Interview invitation'},{'name':'From','value':'Test <test@example.org>'}]},'snippet':'Synthetic test message only.'}
    monkeypatch.setattr(mod,'gmail_req',fake_gmail)
    client = signed_in()
    response = client.get('/api/gmail/updates')
    assert response.status_code == 200
    assert response.json['messages'][0]['stage'] == 'Possible interview'
    assert response.json['checked_at'] == client.get('/api/integrations').json['gmail_last_checked']
    assert 'token' not in client.get('/api/integrations').json


def test_health_and_database_errors_are_sanitized(monkeypatch):
    client = signed_in()
    assert client.get('/health').json['database_connected'] is True
    def unavailable(*args,**kwargs):
        raise OperationalError('postgresql://private:credential@host/db',{},Exception('private database password'))
    monkeypatch.setattr(mod.db,'connect',unavailable)
    response = client.get('/health')
    assert response.status_code == 503 and response.json['ok'] is False
    response = client.get('/api/integrations')
    assert response.status_code == 503
    assert 'DATABASE_URL' in response.json['error']
    assert 'credential' not in response.data.decode() and 'password' not in response.data.decode()


def test_sources_include_extended_boards_and_custom_removal():
    client = signed_in()
    data = client.get('/api/sources').json
    assert len(data['extended_boards']) == 4
    assert client.post('/api/sources',json={'provider':'lever','slug':'verify-source','name':'Verification'}).status_code == 200
    assert client.delete('/api/sources/lever:verify-source').status_code == 200
    assert not any(source['slug'] == 'verify-source' for source in client.get('/api/sources').json['sources'])


def test_refresh_updates_discovered_fields_without_resetting_application(monkeypatch):
    client = signed_in()
    jid = add_job(client,'refresh-keep-state')
    client.patch('/api/jobs/'+jid,json={'status':'Interview','notes':'Keep this note','deadline':'2027-01-05'})
    def fake_collect(board):
        return ([{'id':jid,'company':'Verification Company','title':'Updated Python Intern','location':'Remote',
                  'url':'https://example.org/verification/refresh-keep-state','provider':'greenhouse',
                  'description':'Employer role description','score':76,'warnings':''}],None)
    monkeypatch.setattr(mod,'boards',[('greenhouse','verification','Verification Company')])
    monkeypatch.setattr(mod,'collect',fake_collect)
    response = client.post('/api/refresh')
    assert response.status_code == 200 and response.json['checked'] == 1
    job = next(job for job in client.get('/api/jobs').json['jobs'] if job['id'] == jid)
    assert job['title'] == 'Updated Python Intern'
    assert job['status'] == 'Interview' and job['notes'] == 'Keep this note' and job['deadline'] == '2027-01-05'


def test_invalid_backup_is_rejected_without_crashing():
    client = signed_in()
    assert client.post('/api/restore',data={'file':(io.BytesIO(b'[]'),'backup.json')}).status_code == 422
    blob = {'format':'opportunity-os-backup-v1','jobs':[{'company':'Test','title':'Intern','url':'https://example.org/bad-score','score':'not-numeric'}]}
    response = client.post('/api/restore',data={'file':(io.BytesIO(json.dumps(blob).encode()),'backup.json')})
    assert response.status_code == 200 and response.json['jobs_restored'] == 0


def test_encoded_employer_descriptions_are_readable_plain_text():
    content = '&lt;p&gt;Python &amp;amp; AI&lt;/p&gt;&lt;p&gt;Graduation 2028&lt;/p&gt;'
    assert mod.plain_description(content) == 'Python & AI\nGraduation 2028'
