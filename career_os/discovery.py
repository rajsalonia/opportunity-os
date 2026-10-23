"""Bounded public-source synchronization. Failed requests never close an opportunity."""
import hashlib
import json
import re
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
import requests
from sqlalchemy import text
from .schema import sources, sync, evidence, dumps, loads
from .intelligence import canonical_url, plain, TECH, EARLY

DOCS = {
 'greenhouse':'https://developers.greenhouse.io/job-board.html',
 'lever':'https://github.com/lever/postings-api',
 'ashby':'https://developers.ashbyhq.com/docs/public-job-posting-api',
 'smartrecruiters':'https://developers.smartrecruiters.com/reference/v1listpostings',
}
BOARD_URLS = {'greenhouse':'https://boards.greenhouse.io/{}','lever':'https://jobs.lever.co/{}',
 'ashby':'https://jobs.ashbyhq.com/{}','smartrecruiters':'https://careers.smartrecruiters.com/{}'}

class SourceFailure(Exception):
    def __init__(self, category, retry=0): self.category,self.retry=category,retry

def bounded_get(url, headers=None, params=None):
    """Only adapters construct these URLs. No arbitrary source URL or redirect is fetched."""
    allowed={'boards-api.greenhouse.io','api.lever.co','api.ashbyhq.com','api.smartrecruiters.com',
      'jobicy.com','remotive.com','www.arbeitnow.com','brabble.ai','dev.to','hnrss.org','himalayas.app','internscan.vercel.app'}
    if urlsplit(url).scheme!='https' or urlsplit(url).hostname not in allowed: raise SourceFailure('unsupported_host')
    try:
        response=requests.get(url,params=params,headers={'User-Agent':'OpportunityOS/3.0 (personal discovery; cached)',**(headers or {})},
                              timeout=(4,12),allow_redirects=False,stream=True)
        if response.status_code==304:return None,dict(response.headers),304
        if response.status_code==429:
            try: wait=min(86400,max(300,int(response.headers.get('Retry-After','1800'))))
            except ValueError:
                try:wait=max(300,int((parsedate_to_datetime(response.headers['Retry-After'])-datetime.now(timezone.utc)).total_seconds()))
                except Exception:wait=1800
            raise SourceFailure('rate_limited',wait)
        if response.status_code>=400:raise SourceFailure('http_'+str(response.status_code))
        if response.status_code>=300:raise SourceFailure('redirect_requires_review')
        chunks=[];size=0
        for chunk in response.iter_content(65536):
            size+=len(chunk)
            if size>8_000_000:raise SourceFailure('response_too_large')
            chunks.append(chunk)
        return b''.join(chunks),dict(response.headers),200
    except requests.Timeout:raise SourceFailure('timeout')
    except requests.RequestException:raise SourceFailure('network_error')
    finally:
        if 'response' in locals():response.close()

def normalize(source, raw):
    title=plain(raw.get('title'),250);url=canonical_url(raw.get('url'))
    if not title or not url:return None
    if source['category']=='Jobs' and not (TECH.search(title) and EARLY.search(title+' '+plain(raw.get('description'))[:1000])):return None
    return {'id':hashlib.sha256(url.encode()).hexdigest()[:32], 'company':plain(raw.get('company') or source['name'],200),
      'title':title,'location':plain(raw.get('location'),250),'url':url,'provider':source['provider'],
      'description':plain(raw.get('description')),'published':raw.get('published'),
      'facts':raw.get('facts') or {},'category':raw.get('category') or source['category'],
      'deadline':raw.get('deadline') or '', 'source_record_id':str(raw.get('source_record_id') or raw.get('id') or url)[:250]}

def fetch_source(source, headers=None, getter=bounded_get):
    provider=source['provider'];slug=source['slug'];headers=headers or {}
    def read(url, params=None):
        body,meta,status=getter(url,headers,params)
        if status==304:return None,meta,status
        try:return json.loads(body),meta,status
        except (ValueError,TypeError):raise SourceFailure('invalid_response')
    posts=[];complete=True;listed_ids=None
    if provider=='greenhouse':
        endpoint='https://boards-api.greenhouse.io/v1/boards/'+slug+'/jobs'
        # Fetch the compact board index, then only relevant early-career descriptions.
        data,meta,status=read(endpoint,{'content':'false'})
        if status==304:return [],meta,False,304
        if not isinstance(data,dict) or not isinstance(data.get('jobs'),list):raise SourceFailure('invalid_schema')
        listed_ids=[str(p.get('id')) for p in data['jobs']]
        candidates=[p for p in data['jobs'] if TECH.search(str(p.get('title',''))) and EARLY.search(str(p.get('title','')))]
        candidates.sort(key=lambda p:not bool(re.search(r'(?i)india|delhi|noida|gurugram|bengaluru|bangalore|remote',(p.get('location') or {}).get('name',''))))
        complete=len(candidates)<=40
        for p in candidates[:40]:
            if 'content' not in p:
                detail,_,_=read(endpoint+'/'+str(int(p['id'])))
                if not isinstance(detail,dict) or detail.get('id')!=p.get('id'):raise SourceFailure('invalid_schema')
                p={**p,**detail}
            posts.append({'id':p.get('id'),'title':p.get('title'),'location':(p.get('location') or {}).get('name'),
                'url':p.get('absolute_url'),'description':p.get('content'),'published':p.get('first_published')})
    elif provider=='lever':
        data,meta,status=read('https://api.lever.co/v0/postings/'+slug,{'mode':'json','limit':100,'skip':0})
        if status==304:return [],meta,False,304
        if not isinstance(data,list):raise SourceFailure('invalid_schema')
        allposts=list(data)
        while len(data)==100 and len(allposts)<500:
            data,_,_=read('https://api.lever.co/v0/postings/'+slug,{'mode':'json','limit':100,'skip':len(allposts)})
            if not isinstance(data,list):raise SourceFailure('invalid_schema')
            allposts+=data
        complete=len(data)<100
        listed_ids=[str(p.get('id')) for p in allposts]
        posts=[{'id':p.get('id'),'title':p.get('text'),'location':(p.get('categories') or {}).get('location'),
                'url':p.get('hostedUrl'),'description':(p.get('descriptionPlain') or p.get('description') or '')+'\n'+'\n'.join(plain(x.get('content')) for x in p.get('lists',[])),
                'published':datetime.fromtimestamp(p['createdAt']/1000,timezone.utc).isoformat() if p.get('createdAt') else None} for p in allposts]
    elif provider=='ashby':
        data,meta,status=read('https://api.ashbyhq.com/posting-api/job-board/'+slug,{'includeCompensation':'true'})
        if status==304:return [],meta,False,304
        if not isinstance(data,dict) or not isinstance(data.get('jobs'),list):raise SourceFailure('invalid_schema')
        listed_ids=[str(p.get('id')) for p in data['jobs'] if p.get('isListed',True)]
        posts=[{'id':p.get('id'),'title':p.get('title'),'location':str(p.get('location') or '')+(' · Remote' if p.get('isRemote') else ''),
                'url':p.get('jobUrl'),'description':p.get('descriptionPlain') or p.get('descriptionHtml'),
                'published':p.get('publishedAt'),'facts':{'compensation':(p.get('compensation') or {}).get('compensationTierSummary','')}} for p in data['jobs'] if p.get('isListed',True)]
    elif provider=='smartrecruiters':
        allposts=[];offset=0
        while offset<500:
            data,meta,status=read('https://api.smartrecruiters.com/v1/companies/'+slug+'/postings',{'limit':100,'offset':offset})
            if status==304:return [],meta,False,304
            if not isinstance(data,dict) or not isinstance(data.get('content'),list):raise SourceFailure('invalid_schema')
            allposts+=data['content'];offset+=len(data['content'])
            if len(data['content'])<100 or offset>=int(data.get('totalFound',offset+1)):break
        complete=offset>=int(data.get('totalFound',offset+1))
        # List API contains no requirements. Do not invent descriptions or fetch hundreds of detail pages.
        posts=[{'id':p.get('id'),'title':p.get('name'),'company':(p.get('company') or {}).get('name') or source['name'],
                'location':', '.join(str(v) for v in [(p.get('location') or {}).get('city'),(p.get('location') or {}).get('country')] if v),
                'url':p.get('ref') if str(p.get('ref','')).startswith('https://jobs.smartrecruiters.com/') else 'https://jobs.smartrecruiters.com/'+slug+'/'+str(p.get('id')),
                'published':p.get('releasedDate'),'description':'Employer posting. Requirements and compensation are not included in the public list response; review the official form.'} for p in allposts]
    elif provider in ('jobicy','remotive','arbeitnow'):
        from global_discovery import FEEDS
        endpoint=next(x[2] for x in FEEDS if x[0]==provider)
        data,meta,status=read(endpoint,{'count':100} if provider=='jobicy' else None)
        if status==304:return [],meta,False,304
        if not isinstance(data,dict) or not isinstance(data.get('data' if provider=='arbeitnow' else 'jobs'),list):raise SourceFailure('invalid_schema')
        for p in data.get('data' if provider=='arbeitnow' else 'jobs',[]):
            posts.append({'id':p.get('id') or p.get('slug'),'company':p.get('companyName') or p.get('company_name'),
               'title':p.get('jobTitle') or p.get('title'),'location':str(p.get('jobGeo') or p.get('candidate_required_location') or p.get('location') or 'Region not stated')+(' · Remote' if p.get('remote') or provider!='arbeitnow' else ''),
               'url':p.get('url'),'description':p.get('jobDescription') or p.get('description'),'published':p.get('pubDate') or p.get('publication_date')})
        complete=False # Rolling public-feed windows cannot prove closure.
    elif provider=='rss':
        from opportunity_radar import parse_feed
        body,meta,status=getter(source['url'],headers,None)
        if status==304:return [],meta,False,304
        # Reject invalid feeds rather than treating a parser failure as an empty success.
        from xml.etree import ElementTree as ET
        try:ET.fromstring(body)
        except ET.ParseError:raise SourceFailure('invalid_feed')
        posts=parse_feed(body,source['name'],source['category'],datetime.now(timezone.utc).isoformat())
        posts=[{**p,'description':p.get('summary'),'company':'Organizer not disclosed'} for p in posts]
        complete=False
    else:raise SourceFailure('unsupported_adapter')
    if listed_ids is not None:meta={**meta,'_listed_ids':listed_ids}
    return [row for raw in posts if (row:=normalize(source,raw))],meta,complete,200

class Discovery:
    def __init__(self,store,service,existing_boards=(),portals=()):
        self.store,self.service=store,service;self.existing_boards=existing_boards;self.portals=portals
        self._ready=False;self.lock=threading.Lock()

    def seed(self):
        if self._ready:return
        with self.lock:
            if self._ready:return
            self.store.ensure();from opportunity_radar import FEEDS
            entries=[]
            for provider,slug,name in self.existing_boards:
                entries.append(self.board(provider,slug,name,'Existing configured employer board; check source-health result.'))
            if 'job_sources' in __import__('sqlalchemy').inspect(self.store.db).get_table_names():
                for row in self.store.rows('SELECT * FROM job_sources'):
                    if row.get('provider') in BOARD_URLS and row.get('slug'):
                        try:entries.append(self.board(row['provider'],row['slug'],row.get('name') or row.get('company') or row['slug'],'Owner-registered board from the original source registry.'))
                        except ValueError:pass
            # Employer slug comes from the employer's published SmartRecruiters careers page.
            entries.append(self.board('smartrecruiters','BoschGroup','Bosch Group','https://careers.smartrecruiters.com/BoschGroup/india'))
            entries.append(self.board('ashby','notion','Notion','https://www.notion.com/careers'))
            from global_discovery import FEEDS as REMOTE
            entries += [dict(id=p,provider=p,slug='',name=n,category='Jobs',mode='API',url=u,reference=u,interval_minutes=480,enabled=1) for p,n,u in REMOTE]
            entries += [dict(id='rss-'+hashlib.sha256(u.encode()).hexdigest()[:16],provider='rss',slug='',name=n,category=c,mode='Feed',url=u,reference=u,interval_minutes=480,enabled=1) for n,u,c in FEEDS]
            directory=list(self.portals)+[
                ('Devfolio','https://devfolio.co/hackathons','Hackathons','India'),('MLH','https://mlh.io/seasons/2027/events','Hackathons','Global'),
                ('Devpost','https://devpost.com/hackathons','Hackathons','Global'),('Google Summer of Code','https://summerofcode.withgoogle.com/','Open source','Global'),
                ('Outreachy','https://www.outreachy.org/','Open source','Eligibility-specific'),('GitHub Student Developer Pack','https://education.github.com/pack','Student benefits','Global'),
                ('Google Research','https://research.google/programs-and-events/','Research','Global'),('Microsoft Research','https://www.microsoft.com/en-us/research/academic-program/','Research','Global'),
                ('National Scholarship Portal','https://scholarships.gov.in/','Scholarships','India'),('DAAD Scholarships','https://www.daad.de/en/studying-in-germany/scholarships/','Scholarships','Germany')]
            entries += [dict(id='search-'+hashlib.sha256(u.encode()).hexdigest()[:16],provider='directory',slug='',name=n,category=c,mode='Search only',url=u,reference=u,interval_minutes=0,enabled=0) for n,u,c,_ in directory]
            for name,url in [('Recruitee','https://docs.recruitee.com/reference/authentication-1'),('Workday','https://www.workday.com/'),('Oracle Recruiting','https://www.oracle.com/human-capital-management/recruiting/'),('SAP SuccessFactors','https://www.sap.com/products/hcm/recruiting-software.html')]:
                entries.append(dict(id='credentials-'+name.lower().replace(' ','-'),provider='unconfigured',slug='',name=name,category='Employer systems',mode='Requires credentials',url=url,reference=url,interval_minutes=0,enabled=0))
            entries.append(dict(id='unsupported-personio',provider='unconfigured',slug='',name='Personio XML',category='Employer systems',mode='Unsupported here',url='https://www.personio.com/',reference='No employer-authorized XML feed has been registered.',interval_minutes=0,enabled=0))
            with self.store.db.begin() as c:
                for row in entries:
                    c.execute(text('INSERT INTO career_sources(id,provider,slug,name,category,mode,url,reference,interval_minutes,enabled,created_at) VALUES(:id,:provider,:slug,:name,:category,:mode,:url,:reference,:interval_minutes,:enabled,:ts) ON CONFLICT(id) DO NOTHING'),{**row,'ts':self.store.clock()})
            self._ready=True

    @staticmethod
    def board(provider,slug,name,reference):
        if provider not in BOARD_URLS or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',slug):raise ValueError('Choose a supported provider and a valid published board identifier.')
        return dict(id=provider+'-'+slug.lower(),provider=provider,slug=slug,name=plain(name,160),category='Jobs',mode='API',url=BOARD_URLS[provider].format(slug),reference=reference,interval_minutes=480,enabled=1)

    def add_board(self,data):
        row=self.board(str(data.get('provider','')),str(data.get('slug','')),str(data.get('name','')).strip(),canonical_url(data.get('reference')))
        if not row['name'] or not row['reference']:raise ValueError('Provide the employer name and the official careers-page evidence URL.')
        # Validate the actual public board before registering it. Fixed-host adapter prevents SSRF.
        records,_,_,_=fetch_source(row)
        with self.store.db.begin() as c:
            c.execute(text('INSERT INTO career_sources(id,provider,slug,name,category,mode,url,reference,interval_minutes,enabled,created_at) VALUES(:id,:provider,:slug,:name,:category,:mode,:url,:reference,:interval_minutes,:enabled,:ts) ON CONFLICT(id) DO NOTHING'),{**row,'ts':self.store.clock()})
            self.store.audit(c,'sources','source_registered',after={'id':row['id'],'validated_matching_roles':len(records),'reference':row['reference']})
        return row

    def health(self):
        self.seed()
        rows=self.store.rows('SELECT s.*,h.status,h.last_attempt,h.last_success,h.next_at,h.failures,h.success_count,h.attempt_count,h.record_count,h.error_category,h.lease_until FROM career_sources s LEFT JOIN career_sync h ON s.id=h.source_id ORDER BY s.enabled DESC,s.name')
        counts={}
        for row in rows:
            row['status']=row['status'] or ('Not checked' if row['enabled'] else row['mode'])
            row['success_rate']=round(100*row['success_count']/row['attempt_count']) if row['attempt_count'] else None
            row['documentation']=DOCS.get(row['provider']);counts[row['mode']]=counts.get(row['mode'],0)+1
        return {'sources':rows,'counts':counts,'enabled':sum(bool(r['enabled']) for r in rows),'running':any(r['status']=='running' for r in rows),'hosting_note':'Refresh runs while the service is awake. Sleeping free instances do not execute background schedules. Cached records remain available.'}

    def claim(self,source_id):
        self.store.ensure();stamp=datetime.now(timezone.utc);now=stamp.isoformat();claim=secrets.token_hex(12)
        with self.store.db.begin() as c:
            c.execute(text("INSERT INTO career_sync(source_id,status,failures,success_count,attempt_count) VALUES(:id,'pending',0,0,0) ON CONFLICT(source_id) DO NOTHING"),{'id':source_id})
            result=c.execute(text("UPDATE career_sync SET status='running',last_attempt=:now,lease_until=:lease,claim=:claim,attempt_count=attempt_count+1 WHERE source_id=:id AND (next_at IS NULL OR next_at<=:now) AND (lease_until IS NULL OR lease_until<=:now)"),{'now':now,'lease':(stamp+timedelta(minutes=8)).isoformat(),'claim':claim,'id':source_id})
            return claim if result.rowcount else None

    def run_source(self,source,getter=bounded_get):
        claim=self.claim(source['id'])
        if not claim:return {'id':source['id'],'status':'cached'}
        state=self.store.rows('SELECT * FROM career_sync WHERE source_id=:id',{'id':source['id']})[0]
        headers={}
        if state['etag']:headers['If-None-Match']=state['etag']
        if state['modified']:headers['If-Modified-Since']=state['modified']
        if source['provider'] in ('lever','smartrecruiters'):headers={}
        stamp=datetime.now(timezone.utc);ts=stamp.isoformat()
        try:
            records,meta,complete,status=fetch_source(source,headers,getter)
            with self.store.db.begin() as c:
                seen=[]
                for row in records:
                    key=('j:' if source['category']=='Jobs' else 'r:')+row['id'];seen.append(key)
                    if key.startswith('j:'):
                        c.execute(text("INSERT INTO jobs(id,company,title,location,url,provider,description,score,warnings,status,notes,deadline,discovered,updated) VALUES(:id,:company,:title,:location,:url,:provider,:description,0,'','Discovered','',:deadline,:ts,:ts) ON CONFLICT(id) DO UPDATE SET company=excluded.company,title=excluded.title,location=excluded.location,description=excluded.description"),{**row,'ts':ts})
                    else:
                        from opportunity_radar import ensure
                        # Existing radar schema is additive and remains the canonical store for saved signals.
                        c.execute(text("INSERT INTO radar_items(id,title,summary,url,source,category,location,deadline,published,seen_at,state,verification) VALUES(:id,:title,:description,:url,:source,:category,:location,:deadline,:published,:ts,'new','Public feed; verify original') ON CONFLICT(id) DO UPDATE SET title=excluded.title,summary=excluded.summary"),{**row,'source':source['name'],'ts':ts})
                    eid=hashlib.sha256((source['id']+':'+row['source_record_id']).encode()).hexdigest()[:32]
                    payload=dumps(row)
                    c.execute(text("INSERT INTO career_evidence(id,opportunity_key,source_id,source_record_id,canonical_url,content_hash,payload,first_seen,last_seen,status,misses) VALUES(:id,:key,:source,:record,:url,:hash,:payload,:ts,:ts,'listed',0) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,content_hash=excluded.content_hash,last_seen=excluded.last_seen,status='listed',misses=0"),{'id':eid,'key':key,'source':source['id'],'record':row['source_record_id'],'url':row['url'],'hash':hashlib.sha256(payload.encode()).hexdigest(),'payload':payload,'ts':ts})
                if status==304:
                    c.execute(text("UPDATE career_evidence SET last_seen=:ts WHERE source_id=:id AND status='listed'"),{'ts':ts,'id':source['id']})
                elif complete:
                    old=c.execute(text("SELECT id,opportunity_key,source_record_id,misses FROM career_evidence WHERE source_id=:id AND status!='closed'"),{'id':source['id']}).mappings().all()
                    for previous in old:
                        if previous['opportunity_key'] not in seen:
                            if previous['source_record_id'] in (meta.get('_listed_ids') or []):
                                # It remains in the employer index but no longer matches our early-career filter.
                                c.execute(evidence.update().where(evidence.c.id==previous['id']).values(status='retained',misses=0))
                                continue
                            misses=(previous['misses'] or 0)+1
                            c.execute(evidence.update().where(evidence.c.id==previous['id']).values(misses=misses,status='closed' if misses>=2 else 'missing_once'))
                count=len(records) if status!=304 else state['record_count']
                c.execute(sync.update().where((sync.c.source_id==source['id'])&(sync.c.claim==claim)).values(status='healthy',last_success=ts,next_at=(stamp+timedelta(minutes=source['interval_minutes'])).isoformat(),failures=0,success_count=(state['success_count'] or 0)+1,record_count=count,error_category=None,etag=meta.get('ETag') or meta.get('etag') or state['etag'],modified=meta.get('Last-Modified') or meta.get('last-modified') or state['modified'],lease_until=None))
            self.service.invalidate();return {'id':source['id'],'status':'healthy','records':count,'complete_listing':complete}
        except Exception as exc:
            category=exc.category if isinstance(exc,SourceFailure) else 'adapter_error'
            failures=(state['failures'] or 0)+1;delay=max(getattr(exc,'retry',0),min(86400,1800*2**min(failures-1,5)))
            with self.store.db.begin() as c:
                c.execute(sync.update().where((sync.c.source_id==source['id'])&(sync.c.claim==claim)).values(status='cooldown' if failures>=3 else 'degraded',failures=failures,error_category=category,next_at=(stamp+timedelta(seconds=delay)).isoformat(),lease_until=None))
            return {'id':source['id'],'status':'degraded','error':category}

    def launch(self):
        self.seed();from opportunity_radar import ensure
        ensure(self.store.db)
        # Atomic per-source leases also serialize work across Gunicorn workers.
        now=self.store.clock()
        due=self.store.rows('SELECT s.* FROM career_sources s LEFT JOIN career_sync h ON s.id=h.source_id WHERE s.enabled=1 AND (h.next_at IS NULL OR h.next_at<=:now) AND (h.lease_until IS NULL OR h.lease_until<=:now) ORDER BY h.last_success NULLS FIRST,s.id LIMIT 32',{'now':now})
        if not due:return {'queued':0,'status':'Cached sources are within their refresh interval.'}
        def work():
            with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(self.run_source,due))
        threading.Thread(target=work,daemon=True,name='career-source-refresh').start()
        return {'queued':len(due),'status':'Refresh queued; cached opportunities remain available.'}
