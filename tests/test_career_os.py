"""Version 3 behavioral checks with isolated data and no real email/application sends."""
import os
os.environ.setdefault("APP_PASSWORD", "test-secret-not-a-real-password")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-for-test-only")
os.environ.setdefault("HTTPS_ONLY", "false")
import hashlib
import json
from datetime import datetime, timezone
from unittest.mock import Mock
import pytest
from sqlalchemy import create_engine, text
from career_os.schema import Store, metadata, dumps, sources, sync, accounts, messages
from career_os.service import CareerService
from career_os.discovery import Discovery, fetch_source, SourceFailure, bounded_get
from career_os.intelligence import extract, eligibility, DEFAULT_PROFILE, identity, canonical_url, parse_deadline
from career_os.mail import classify, Mail
from career_os.api import ics_calendar

@pytest.fixture
def service(tmp_path):
    db=create_engine('sqlite:///'+(tmp_path/'career.db').as_posix())
    import app
    with db.begin() as c:
        for statement in app.schema:c.execute(text(statement))
    from opportunity_radar import ensure
    ensure(db)
    store=Store(db,lambda:datetime.now(timezone.utc).isoformat());store.ensure()
    return CareerService(store)

def add(service,suffix='one',**extra):
    url='https://example.org/careers/'+suffix;uid=hashlib.sha256(url.encode()).hexdigest()[:32]
    row={'id':uid,'company':'Example Company','title':'Python Backend Intern','location':'India · Remote',
        'url':url,'provider':'greenhouse','description':'Students graduating in 2028 can apply. Build Python backend APIs. Paid internship, stipend INR 25000 per month. Duration 12 weeks.',
        'status':'Discovered','notes':'Owner note preserved','deadline':'','discovered':'2026-10-01T10:00:00+00:00','updated':'2026-10-01T10:00:00+00:00',**extra}
    with service.store.db.begin() as c:c.execute(text('INSERT INTO jobs('+','.join(row)+') VALUES('+','.join(':'+n for n in row)+')'),row)
    service.invalidate();return 'j:'+uid

@pytest.mark.parametrize('description,location,title,expected',[
 ('Must graduate in 2027.','India','Python Intern','ineligible'),
 ('2027 graduates only.','India','Python Intern','ineligible'),
 ('Students graduating in 2028 may apply.','India','Python Intern','likely'),
 ('Summer 2027 internship for undergraduate students.','India','Python Intern','likely'),
 ('Students welcome. US only.','Remote US only','Python Intern','ineligible'),
 ('Undergraduate students welcome.','Worldwide remote','Python Intern','likely'),
 ('Build Python systems.','Remote','Python Intern','unknown'),
 ('5 years of professional experience required.','India','Senior Backend Engineer','ineligible'),
 ('PhD required.','India','Research Intern','ineligible'),
 ('Students graduating in 2028. India candidate privacy notice.','San Francisco, CA','PhD Intern, Data Science','ineligible'),
 ('Students graduating in 2028.','New York, NY','Software Intern','unknown'),
])
def test_eligibility_evidence(description,location,title,expected):
    item={'title':title,'location':location,'description':description,'url':'https://example.org/job','provider':'greenhouse'}
    result=eligibility(item,extract(item),DEFAULT_PROFILE)
    assert result['code']==expected
    if expected=='ineligible':assert result['evidence'] and result['hard_conflict']

def test_missing_facts_and_remote_are_honest():
    f=extract({'title':'Intern','description':'Build services','location':'Delhi','url':'https://example.org'})
    assert f['fields']['compensation']['value'] is None
    assert f['fields']['duration']['value'] is None
    assert f['work_mode']=='Not disclosed' and not f['deadline']['date']
    budget=extract({'description':'Our compensation varies. Personal learning budget USD 2,000 per year.','url':'https://example.org'})
    assert budget['fields']['compensation']['value'] is None

def test_deadline_zone_and_date_only_ics():
    date=parse_deadline('2027-01-15','Asia/Kolkata','Owner recorded')
    assert date['precision']=='date' and not date['cutoff_known'] and date['utc'] is None
    instant=parse_deadline('2027-01-15T10:00:00-05:00',None,'Employer stated')
    assert instant['utc']=='2027-01-15T15:00:00+00:00'
    text=ics_calendar([{'id':'a','title':'Deadline, accurate','deadline':date,'timezone':'Asia/Kolkata','reminder_minutes':1440}])
    assert 'DTSTART;VALUE=DATE:20270115' in text and '23:59' not in text
    assert 'Exact cutoff unknown' in text and 'TRIGGER:-PT1440M' in text

def test_holiday_and_learning_benefits_are_not_contract_duration_or_pay():
    f=extract({'title':'Graduate Software Engineer','description':'Base pay varies by location. Annual compensation review. Personal learning and development budget of USD 2,000 per year. Four annual sprints and 4 weeks annual holiday leave.','url':'https://example.org'})
    assert f['fields']['duration']['value'] is None
    assert f['fields']['compensation']['value'] is None
    f=extract({'title':'Software Intern','description':'Internship duration: 12 weeks. Salary $50 per hour.','url':'https://example.org'})
    assert '12 weeks' in f['fields']['duration']['value']
    assert f['fields']['currency']['value'] is None

def test_today_does_not_present_an_elapsed_instant_as_upcoming(service,monkeypatch):
    from datetime import timedelta
    past=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()
    event={'id':'past','opportunity_key':'','title':'Elapsed deadline','kind':'Application deadline','deadline':parse_deadline(past,'UTC','Employer stated')}
    monkeypatch.setattr(service,'calendar',lambda:[event])
    result=service.today()
    assert result['deadlines']['today']==[]
    assert next(p for p in result['priorities'] if p['kind']=='deadline')['count']==0

def test_conservative_dedupe_tracking_parameters_and_separate_roles(service):
    a=add(service,'one');b=add(service,'two')
    assert len(service.snapshot())==2
    url='https://jobs.lever.co/company/123'
    assert identity({'url':url+'?utm_source=x'})==identity({'url':url+'/apply'})
    assert canonical_url('https://127.0.0.1/a')==''
    assert canonical_url('javascript:alert(1)')==''
    service.merge(a,b,'Both refer to the same employer identifier.')
    assert len(service.snapshot())==1
    assert len(service.store.rows('SELECT * FROM jobs'))==2

def test_checklist_persists_and_never_implies_submitted(service):
    key=add(service);rows=service.checklist(key,True);assert len(rows)==19
    for row in rows:service.edit_checklist(key,row['id'],{'completed':True})
    assert service.get(key)['stage']=='Discovered'
    assert all(r['completed'] for r in CareerService(service.store).checklist(key))
    with pytest.raises(ValueError):service.update(key,{'stage':'Applied'})
    service.update(key,{'stage':'Applied','submitted_by_owner':True,'reference':'Owner observed employer confirmation R123'})
    assert service.get(key)['submission_evidence']['kind']=='Owner-reported submission'
    assert len(service.store.rows('SELECT * FROM career_receipts'))==1
    assert service.store.rows('SELECT * FROM jobs')[0]['notes']=='Owner note preserved'

def test_owner_override_cannot_remove_hard_conflict(service):
    key=add(service,description='Must graduate in 2027. India only.')
    service.update(key,{'eligibility_override':{'reason':'Recruiter clarification is pending review.'}})
    assert service.get(key)['eligibility']['code']=='ineligible'
    assert service.get(key)['eligibility_override']['reason']

def test_archive_pin_and_filter_roundtrip(service):
    keys=[add(service,str(i)) for i in range(6)]
    for key in keys[:5]:service.update(key,{'pinned':True,'saved':True})
    with pytest.raises(ValueError):service.update(keys[5],{'pinned':True})
    assert len(service.filtered({'q':'paid remote Python internships in India'})[0])==6
    assert len(service.filtered({'view':'saved'})[0])==5
    service.update(keys[0],{'archived':True})
    assert len(service.filtered({})[0])==5
    service.update(keys[0],{'archived':False})
    assert len(service.filtered({})[0])==6

def test_mail_is_excluded_without_deleting_old_radar(service):
    with service.store.db.begin() as c:
        c.execute(text("INSERT INTO radar_items(id,title,summary,url,source,category,seen_at,state) VALUES(:id,'Hiring alert','A sent copy','https://mail.google.com/mail/u/0/#all/123','Gmail opening alert','Internship','2026-10-01','new')"),{'id':'a'*32})
    assert service.snapshot()==[]
    assert len(service.store.rows('SELECT * FROM radar_items'))==1

def test_additive_tables_preserve_legacy_records_and_document_bytes(service):
    key=add(service);before=service.store.rows('SELECT * FROM jobs')
    with service.store.db.begin() as c:
        c.execute(text('CREATE TABLE private_documents(id TEXT PRIMARY KEY,content BLOB,hash TEXT)'))
        c.execute(text("INSERT INTO private_documents VALUES('original',:blob,:hash)"),{'blob':b'%PDF-original-bytes','hash':'owner-approved'})
    Store(service.store.db,service.store.clock).ensure()
    assert before==service.store.rows('SELECT * FROM jobs')
    assert service.store.rows('SELECT content FROM private_documents')[0]['content']==b'%PDF-original-bytes'

def fake_gh(records,status=200):
    return lambda url,headers=None,params=None:(json.dumps({'jobs':records}).encode() if status!=304 else None,{'ETag':'"v1"'},status)

def gh_job(uid=123):return {'id':uid,'title':'Python Backend Intern','location':{'name':'India'},'absolute_url':'https://boards.greenhouse.io/example/jobs/'+str(uid),'content':'Students graduating in 2028. Python engineering internship.'}

def allow_again(service,sid):
    with service.store.db.begin() as c:c.execute(sync.update().where(sync.c.source_id==sid).values(next_at=None))

def test_source_missing_twice_but_outage_never_closes(service):
    engine=Discovery(service.store,service);source=engine.board('greenhouse','example','Example','https://example.org/careers')
    result=engine.run_source(source,fake_gh([gh_job()]))
    assert result['status']=='healthy';first=service.store.rows('SELECT * FROM jobs')[0]['discovered']
    key=service.snapshot()[0]['key'];service.update(key,{'stage':'Preparing','notes':'Keep my preparation'})
    allow_again(service,source['id'])
    def fail(*args):raise SourceFailure('timeout')
    assert engine.run_source(source,fail)['status']=='degraded'
    assert service.store.rows('SELECT * FROM career_evidence')[0]['status']=='listed'
    allow_again(service,source['id']);engine.run_source(source,fake_gh([]))
    assert service.store.rows('SELECT * FROM career_evidence')[0]['status']=='missing_once'
    allow_again(service,source['id']);engine.run_source(source,fake_gh([]))
    assert service.get(key)['eligibility']['code']=='closed'
    assert service.get(key)['stage']=='Preparing' and service.get(key)['notes']=='Keep my preparation'
    allow_again(service,source['id']);engine.run_source(source,fake_gh([gh_job()]))
    assert service.store.rows('SELECT * FROM jobs')[0]['discovered']==first
    assert service.get(key)['eligibility']['code']=='likely'

def test_conditional_cache_lease_and_rate_limit(service,monkeypatch):
    engine=Discovery(service.store,service);source=engine.board('greenhouse','example','Example','https://example.org')
    assert engine.claim(source['id']);assert engine.claim(source['id']) is None
    with service.store.db.begin() as c:c.execute(sync.update().values(lease_until=None,next_at=None))
    engine.run_source(source,fake_gh([gh_job()]));allow_again(service,source['id'])
    seen=[]
    def not_modified(url,headers,params):seen.append(headers);return None,{},304
    assert engine.run_source(source,not_modified)['records']==1
    assert seen[0]['If-None-Match']=='"v1"'
    allow_again(service,source['id'])
    def limited(*args):raise SourceFailure('rate_limited',7200)
    engine.run_source(source,limited)
    assert engine.run_source(source,fake_gh([]))['status']=='cached'
    with pytest.raises(SourceFailure):bounded_get('https://169.254.169.254/latest/meta-data')

def test_lever_pagination_and_incomplete_smartrecruiters():
    calls=[]
    def lever(url,headers,params):
        calls.append(params['skip']);n=100 if params['skip']==0 else 1
        return json.dumps([{'id':str(params['skip']+i),'text':'Software Intern','categories':{'location':'India'},'hostedUrl':'https://jobs.lever.co/example/'+str(params['skip']+i),'descriptionPlain':'Students can apply.'} for i in range(n)]).encode(),{},200
    source=Discovery.board('lever','example','Example','https://example.org')
    rows,_,complete,_=fetch_source(source,getter=lever)
    assert len(rows)==101 and calls==[0,100] and complete
    def smart(url,headers,params):
        if '/postings/' in url:
            posting_id=url.rsplit('/',1)[-1]
            return json.dumps({'id':posting_id,'postingUrl':'https://jobs.smartrecruiters.com/Example/'+posting_id,
                 'jobAd':{'sections':{'qualifications':{'text':'Students welcome.'}}}}).encode(),{},200
        return json.dumps({'totalFound':1000,'content':[{'id':str(params['offset']+i),'name':'Software Intern','location':{'country':'India'}} for i in range(100)]}).encode(),{},200
    source=Discovery.board('smartrecruiters','Example','Example','https://example.org')
    rows,_,complete,_=fetch_source(source,getter=smart)
    assert len(rows)==500 and complete is False

@pytest.mark.parametrize('subject,headers,labels,expected',[
 ('Delivery Status Notification (Failure)',{},[],'Delivery failure'),
 ('Automatic reply: internship',{},[],'Out of office'),
 ('We received your application',{},[],'Application acknowledgement'),
 ('Interview invitation',{},[],'Possible interview'),
 ('Assessment invitation',{},[],'Possible assessment'),
 ('Offer letter',{},[],'Possible offer'),
 ('Unfortunately, not moving forward',{},[],'Possible rejection'),
 ('Latest internships',{'list-unsubscribe':'<https://example.org/unsubscribe>'},[],'Newsletter / alert'),
 ('Re: your interest',{},[],'Possible human reply'),
 ('Re: your interest',{},['SENT'],'Sent'),
])
def test_account_bound_mail_categories(subject,headers,labels,expected):
    raw={'subject':subject,'snippet':'','from':'recruiter@example.org','to':'owner@example.org','thread_id':'thread-1','headers':headers,'labels':labels}
    result=classify(raw,[{'thread_id':'thread-1','to':'recruiter@example.org'}],'owner@example.org')
    assert result['category']==expected
    assert result['human_reply']==(expected=='Possible human reply')
    if expected=='Possible human reply':assert not classify(raw,[],'owner@example.org')['human_reply']

def test_rules_fallback_feedback_and_no_premature_ml(service):
    key=add(service);service.add_feedback(key,'Interested')
    assert service.model_status()['feedback_records']==1
    service.add_feedback(key,'Prefer similar')
    assert service.model_status()['feedback_records']==1
    with pytest.raises(ValueError):service.evaluate_model()
    answer=service.assistant('Explain my next step',[key]);assert answer['citations'][0]['key']==key
    assert answer['engine'].startswith('rules-')
    draft=service.assistant('Draft a cold email',[key])['answer']
    assert 'BPIT' not in draft and 'graduating in 2028' not in draft

def test_feedback_candidate_uses_distinct_numeric_examples_and_holdout(service):
    from career_os.schema import feedback
    with service.store.db.begin() as c:
        for i in range(50):
            c.execute(feedback.insert().values(id=str(i),opportunity_key='j:'+str(i).zfill(32),kind='Interested' if i%2 else 'Wrong location',features=dumps([i%2,1,1,.5,i%2,0,1]),category='Internship',created_at=service.store.clock()))
    result=service.evaluate_model()
    assert result['activated'] is False and result['metrics']['holdout']==10
    row=service.store.rows('SELECT * FROM career_models')[0]
    config=json.loads(row['config'])
    assert len(config['weights'])==8 and row['status']=='evaluated'
    assert not set(config)&{'resume','mail','contacts','legal_name'}

def test_two_gmail_accounts_never_share_message_identity_or_review_state(service,monkeypatch):
    mail=Mail(service.store,None,None,lambda:None,lambda:True)
    with service.store.db.begin() as c:
        for aid,email in [('one','first@example.org'),('two','second@example.org')]:
            c.execute(accounts.insert().values(id=aid,email=email,token_ref='gmail-'+aid,status='connected'))
    def request(account,path,params=None):
        if path=='profile':return {'emailAddress':account['email']}
        if path=='messages':return {'messages':[{'id':'same-gmail-id'}]}
        return {'id':'same-gmail-id','threadId':'same-thread','labelIds':['INBOX','SPAM'],'internalDate':'1792795200000','snippet':'Interview invitation','payload':{'headers':[{'name':'From','value':'recruiter@example.org'},{'name':'Subject','value':'Interview invitation'}],'parts':[{'filename':'invite.pdf','mimeType':'application/pdf','body':{'size':200}}]}}
    monkeypatch.setattr(mail,'request',request)
    assert mail.scan('one')['checked']==1 and mail.scan('two')['checked']==1
    rows=service.store.rows('SELECT * FROM career_mail_messages');assert len(rows)==2 and rows[0]['id']!=rows[1]['id']
    with service.store.db.begin() as c:c.execute(messages.update().where(messages.c.account_id=='one').values(reviewed=1))
    mail.scan('one');assert mail.snapshot('one')['messages'][0]['reviewed']==1
    assert mail.snapshot('two')['messages'][0]['reviewed']==0
    assert 'authuser=first%40example.org' in mail.snapshot('one')['messages'][0]['gmail_url']
    assert mail.snapshot('one')['messages'][0]['attachments'][0]['filename']=='invite.pdf'
    assert service.store.rows('SELECT * FROM jobs')==[]

def test_v3_api_auth_csrf_pagination_and_exports():
    from test_hosted import app
    client=app.test_client()
    assert client.get('/api/v3/opportunities').status_code==401
    assert client.get('/classic').status_code==401
    client.post('/api/login',json={'password':'test-secret-not-a-real-password'})
    html=client.get('/').data.decode()
    import re
    token=re.search(r'name="csrf-token" content="([^"]+)"',html).group(1)
    assert client.post('/api/v3/visit',json={}).status_code==403
    headers={'X-CSRF-Token':token}
    assert client.post('/api/v3/visit',json={},headers={**headers,'Origin':'https://foreign.example'}).status_code==403
    assert client.post('/api/v3/visit',json={},headers=headers).status_code==200
    result=client.get('/api/v3/opportunities?size=1').json
    assert len(result['items'])<=1 and result['size']==1
    assert client.get('/api/v3/opportunities?page=abc').status_code==422
    export=client.get('/api/v3/export').json
    assert export['format']=='opportunity-os-workspace-v3'
    assert not set(export)&{'oauth_tokens','contacts','private_documents','mail_messages'}
    assert client.get('/api/v3/calendar.ics').mimetype=='text/calendar'


def test_daily_queue_excludes_submitted_roles_and_filters_priority(service):
    first=add(service,'queue-first')
    second=add(service,'queue-second')
    before=service.today()
    assert first in [i['key'] for i in before['recommended']]
    assert second in [i['key'] for i in before['recommended']]
    priority=service.get(first)['recommendation']['bucket']
    assert first in [i['key'] for i in service.filtered({'priority':priority})[0]]
    service.update(first,{'stage':'Applied','submitted_by_owner':True,'reference':'Synthetic confirmation R123'})
    after=service.today()
    assert first not in [i['key'] for i in after['recommended']]
    assert first not in [i['key'] for i in after['apply_today']]
    assert first not in [i['key'] for i in after['review_this_week']]
    assert after['already_applied_count']>=1
    assert first in [i['key'] for i in service.filtered({'priority':'Already applied'})[0]]


def test_discover_does_not_repeat_applied_roles_as_new_vacancies(service):
    applied=add(service,'already-submitted')
    new=add(service,'not-applied')
    service.update(applied,{'stage':'Applied','submitted_by_owner':True,'reference':'Synthetic receipt A2026'})
    discover_keys={item['key'] for item in service.filtered({'view':'discover'})[0]}
    applications_keys={item['key'] for item in service.filtered({'view':'applications'})[0]}
    assert new in discover_keys
    assert applied not in discover_keys
    assert applied in applications_keys
    assert applied in {item['key'] for item in service.filtered({'view':'','priority':'Already applied'})[0]}
    assert applied in {item['key'] for item in service.filtered({'view':'discover','priority':'Already applied'})[0]}


def test_relevant_employer_boards_are_registered_with_verified_slugs(service):
    from career_os.discovery import Discovery
    discovery=Discovery(service.store,service,existing_boards=[],portals=[])
    discovery.seed()
    rows={item['id']:item for item in service.store.rows("SELECT * FROM career_sources")}
    for source_id,provider,slug in (
        ('lever-merklescience','lever','merklescience'),
        ('lever-hevodata','lever','hevodata'),
        ('ashby-interview-kickstart','ashby','interview-kickstart'),
        ('ashby-aistudio','ashby','aistudio'),
        ('ashby-outmarket','ashby','outmarket'),
        ('ashby-emergence','ashby','emergence')
    ):
        assert rows[source_id]['slug']==slug
        assert rows[source_id]['provider']==provider
        assert rows[source_id]['mode']=='API'
        assert rows[source_id]['reference'].startswith('https://jobs.')
    # Registry presence is not equivalent to an observed successful scan.
    assert not service.store.rows('SELECT * FROM career_sync')


def test_official_remote_rss_is_source_attributed_and_filters_early_career(service):
    from career_os.discovery import Discovery
    discovery=Discovery(service.store,service,existing_boards=[],portals=[])
    discovery.seed()
    rows=service.store.rows("SELECT * FROM career_sources WHERE name LIKE 'We Work Remotely%'")
    assert len(rows)==2
    assert all(row['mode']=='Feed' and row['category']=='Jobs' and row['enabled']==1 for row in rows)
    source=rows[0]
    now=datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
    xml=('<rss version="2.0"><channel>'
         '<item><title>Backend Software Engineering Intern</title>'
         '<description>Python backend engineering internship. Remote, region not verified.</description>'
         '<link>https://weworkremotely.com/remote-jobs/example/intern</link>'
         '<pubDate>'+now+'</pubDate></item>'
         '<item><title>Senior Software Engineering Manager</title>'
         '<description>Senior manager role</description>'
         '<link>https://weworkremotely.com/remote-jobs/example/senior</link></item>'
         '</channel></rss>').encode()
    def response(url,headers=None,params=None):
        assert url==source['url']
        return xml,{'ETag':'"wwr-test"'},200
    result=discovery.run_source(source,response)
    assert result['status']=='healthy' and result['records']==1
    item=service.snapshot()[0]
    assert item['provider']=='rss'
    assert item['eligibility']['code'] in ('unknown','likely')
    assert item['source_records'][0]['url'].startswith('https://weworkremotely.com/')


def test_expanded_discovery_directories_are_not_marked_as_api_connections(service):
    from career_os.discovery import Discovery
    engine=Discovery(service.store,service,existing_boards=[],portals=[])
    engine.seed()
    rows=service.store.rows("SELECT * FROM career_sources WHERE mode='Search only'")
    names={item['name'] for item in rows}
    for name in ('Kaggle Competitions','DoraHacks','HackerEarth Challenges',
                 'MLH Fellowship','Google Developer Groups','AWS Events',
                 'CNCF Events','Product Hunt','Microsoft Reactor'):
        assert name in names
    assert all(item['enabled']==0 and item['provider']=='directory' for item in rows)
    assert not service.store.rows('SELECT * FROM career_sync')


def test_smartrecruiters_fetches_bounded_public_intern_details():
    calls=[]
    def smart(url,headers,params):
        calls.append(url)
        if url.endswith('/postings'):
            posts=[{'id':str(n),'name':('Software Engineer Intern' if n==1 else 'Senior Data Architect'),
                    'location':{'city':'Bangalore','country':'IN'},
                    'company':{'name':'Example Employer'}} for n in range(1,6)]
            return json.dumps({'totalFound':5,'content':posts}).encode(),{},200
        assert url.endswith('/postings/1')
        return json.dumps({'id':'1','postingUrl':'https://jobs.smartrecruiters.com/Example/1',
          'jobAd':{'sections':{'jobDescription':{'text':'Build backend APIs in Python.'},
          'qualifications':{'text':'Students graduating in 2028 can apply.'}}}}).encode(),{},200
    source=Discovery.board('smartrecruiters','Example','Example Employer','https://example.org')
    posts,_,complete,_=fetch_source(source,getter=smart)
    assert complete is True and len(calls)==2
    assert len(posts)==1  # only the real early-career role survives normalization
    assert 'graduating in 2028' in posts[0]['description']
    assert posts[0]['url']=='https://jobs.smartrecruiters.com/Example/1'

def test_smartrecruiters_invalid_detail_does_not_silently_create_verified_facts():
    def invalid(url,headers,params):
        if url.endswith('/postings'):
            return json.dumps({'totalFound':1,'content':[{'id':'1','name':'Software Engineer Intern'}]}).encode(),{},200
        return json.dumps({'id':'unexpected','jobAd':{}}).encode(),{},200
    source=Discovery.board('smartrecruiters','Example','Example','https://example.org')
    with pytest.raises(SourceFailure) as exc:fetch_source(source,getter=invalid)
    assert exc.value.category=='invalid_detail_schema'


def test_remoteok_public_feed_skips_metadata_and_attributes_source(service):
    from career_os.discovery import Discovery
    d=Discovery(service.store,service,existing_boards=[],portals=[])
    d.seed()
    source=service.store.rows("SELECT * FROM career_sources WHERE id='remoteok-public'")[0]
    def getter(url,headers,params):
        assert url=='https://remoteok.com/api'
        return json.dumps([
            {'legal':'remoteok.com attribution required'},
            {'id':'101','position':'Software Backend Intern','company':'Example Startup',
             'location':'Remote - India',
             'url':'https://remoteok.com/remote-jobs/example-backend-intern',
             'description':'Remote software engineering internship. Python and APIs.'},
            {'id':'102','position':'Senior Staff Engineering Manager','company':'Example Startup',
             'url':'https://remoteok.com/remote-jobs/example-staff',
             'description':'Staff engineer role.'}]).encode(),{},200
    result=d.run_source(source,getter)
    assert result['status']=='healthy' and result['records']==1
    rec=service.snapshot()[0]
    assert rec['provider']=='remoteok'
    assert rec['url']=='https://remoteok.com/remote-jobs/example-backend-intern'
    assert rec['extracted']['work_mode']=='Remote'
    assert rec['eligibility']['code'] in ('unknown','likely')


def test_enhanced_search_filtering_modes_batches_and_skills(service):
    k1 = add(service, 'hybrid-role', title='Backend Engineering Intern', description='Hybrid role in Delhi NCR. Monthly stipend INR 30000. Batch 2027 graduates. Skills required: FastAPI, Docker.')
    k2 = add(service, 'onsite-role', title='Frontend Engineer', description='On-site role in Bengaluru. Batch 2028 graduates. React, TypeScript.')
    
    # Test implicit stipend -> paid
    items, implicit = service.filtered({'q': 'stipend backend'})
    assert implicit.get('paid') == 'yes'
    assert any(i['key'] == k1 for i in items)

    # Test implicit hybrid mode
    items, implicit = service.filtered({'q': 'hybrid internship'})
    assert implicit.get('mode') == 'Hybrid'
    assert any(i['key'] == k1 for i in items)

    # Test implicit 2027 graduation year
    items, implicit = service.filtered({'q': '2027 batch'})
    assert implicit.get('year') == '2027'

    # Test extracted skills in search haystack
    items, _ = service.filtered({'q': 'docker'})
    assert any(i['key'] == k1 for i in items)
