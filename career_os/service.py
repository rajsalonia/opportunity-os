"""Unified projections and owner actions over legacy jobs/radar, without deleting originals."""
import csv
import hashlib
import io
import json
import math
import re
import secrets
import time
from datetime import datetime, timezone, timedelta, date
from zoneinfo import ZoneInfo
from sqlalchemy import inspect, text
from application_profile import PUBLIC_PROFESSIONAL_PROFILE
from .schema import states, checklists, events, feedback, receipts, aliases, preferences, models, dumps, loads
from .intelligence import DEFAULT_PROFILE, STAGES, SUBSTATES, LEGACY, TERMINAL, FEEDBACK, VERSION, canonical_url, identity, extract, eligibility, recommend, warnings, parse_deadline, plain

DEFAULT_CHECKLIST = [
 ('Before applying','Confirm graduation-year eligibility'),('Before applying','Confirm location and remote restrictions'),
 ('Before applying','Read responsibilities and required skills'),('Before applying','Review compensation and duration'),
 ('Before applying','Select the reviewed resume'),('Before applying','Prepare portfolio and GitHub links'),
 ('Before applying','Prepare a relevant verified project explanation'),('Before applying','Review employer-specific questions'),
 ('Application','Open the official application form'),('Application','Complete required fields'),
 ('Application','Attach the reviewed resume'),('Application','Review all answers before submitting'),
 ('Application','Verify actual submission and save its acknowledgement'),
 ('After applying','Record the actual submission date'),('After applying','Update application status'),
 ('After applying','Set an appropriate follow-up reminder'),('After applying','Review incoming recruiter messages'),
 ('After applying','Complete any invited assessment'),('After applying','Prepare for an interview if invited')]

class CareerService:
    def __init__(self, store, cipher=None):
        self.store, self.cipher = store, cipher
        self._cache = None; self._cache_at = 0

    def invalidate(self): self._cache = None

    def profile(self):
        rows=self.store.rows("SELECT data FROM career_preferences WHERE id='profile'")
        saved=loads(rows[0]['data'],{}) if rows else {}
        result={**DEFAULT_PROFILE,**saved}
        # Read only the approved, already encrypted field; never expose legal contact details.
        raw=self.store.setting('autoapply_profile_v1')
        if raw and self.cipher and 'work_authorized_india' not in saved:
            try: result['work_authorized_india']=loads(self.cipher.decrypt(raw.encode()).decode(),{}).get('work_authorized_india') is True
            except Exception: pass
        result['professional']={name:PUBLIC_PROFESSIONAL_PROFILE[name] for name in ('github','linkedin','portfolio','projects','experience')}
        return result

    def update_profile(self, data):
        if not isinstance(data,dict): raise ValueError('Profile must be an object.')
        current=self.profile(); current.pop('professional',None)
        for name in ('country','city','target_season','degree'):
            if name in data:
                if not isinstance(data[name],str) or not 1<=len(data[name].strip())<=160: raise ValueError('Enter valid '+name+'.')
                current[name]=data[name].strip()
        if 'graduation_year' in data:
            try: year=int(data['graduation_year'])
            except (TypeError,ValueError): raise ValueError('Graduation year must be a year.')
            if not 2025<=year<=2045: raise ValueError('Graduation year must be between 2025 and 2045.')
            current['graduation_year']=year
        for name in ('skills','interests','preferred_modes'):
            if name in data:
                if not isinstance(data[name],list) or len(data[name])>40 or any(not isinstance(x,str) or len(x)>70 for x in data[name]): raise ValueError('Invalid profile list.')
                current[name]=list(dict.fromkeys(x.strip().lower() if name=='skills' else x.strip() for x in data[name] if x.strip()))
        if 'work_authorized_india' in data:
            if not isinstance(data['work_authorized_india'],bool): raise ValueError('Work authorization must be an explicit yes or no.')
            current['work_authorized_india']=data['work_authorized_india']
        self.store.ensure()
        with self.store.db.begin() as c:
            c.execute(text("INSERT INTO career_preferences(id,data,updated_at) VALUES('profile',:data,:ts) ON CONFLICT(id) DO UPDATE SET data=excluded.data,updated_at=excluded.updated_at"),{'data':dumps(current),'ts':self.store.clock()})
            self.store.audit(c,'profile','profile_updated',after={k:current[k] for k in ('graduation_year','country','city','skills','work_authorized_india')})
        self.invalidate(); return self.profile()

    def optional_rows(self, table_name, query):
        if table_name not in inspect(self.store.db).get_table_names(): return []
        return self.store.rows(query)

    def snapshot(self, fresh=False):
        if self._cache is not None and not fresh and time.monotonic()-self._cache_at<12: return self._cache
        self.store.ensure()
        profile=self.profile(); stamp=datetime.now(timezone.utc)
        jobs=self.store.rows('SELECT * FROM jobs ORDER BY discovered DESC LIMIT 12000')
        signals=self.optional_rows('radar_items','SELECT * FROM radar_items ORDER BY seen_at DESC LIMIT 10000')
        flags={row['key']:row for row in self.store.rows('SELECT * FROM career_states')}
        evidence_rows=self.store.rows('SELECT * FROM career_evidence')
        evidence_by_key={}
        for row in evidence_rows: evidence_by_key.setdefault(row['opportunity_key'],[]).append(row)
        checklist_counts={row['opportunity_key']:row for row in self.store.rows('SELECT opportunity_key,count(*) AS total,sum(completed) AS done FROM career_checklists GROUP BY opportunity_key')}
        history_feedback=self.store.rows('SELECT * FROM career_feedback ORDER BY created_at ASC LIMIT 5000')
        aliases_map={row['alias_key']:row['primary_key'] for row in self.store.rows('SELECT * FROM career_aliases') if row['primary_key']!=row['alias_key']}
        tasks={row['job_id']:row for row in self.optional_rows('application_tasks','SELECT * FROM application_tasks')}
        owner_receipts={row['opportunity_key']:row for row in self.store.rows('SELECT * FROM career_receipts ORDER BY created_at')}
        model_rows=self.store.rows("SELECT * FROM career_models WHERE status='active' ORDER BY created_at DESC LIMIT 1")
        model=loads(model_rows[0]['config'],{}) if model_rows else None
        candidates=[]
        for row in jobs:
            key='j:'+row['id']; flag=flags.get(key,{})
            legacy_status=row.get('status') or 'Discovered'
            stage=flag.get('stage') if flag.get('legacy_status')==legacy_status else None
            stage=stage or ('Preparing' if legacy_status=='Draft ready' else legacy_status)
            item={**row,'key':key,'kind':'job','legacy_id':row['id'],'stage':stage,'category':'Internship' if re.search(r'intern|co.op|trainee|apprentice',row['title'],re.I) else 'Job',
                'first_seen':row.get('discovered'),'published':None,'last_checked':None,'availability':'unknown','facts':{},'source_records':[]}
            item.update(self.apply_flags(flag,legacy_status=='Saved'))
            task=tasks.get(row['id'])
            item['submission_evidence']=({'kind':'Employer API confirmed','reference':task.get('receipt'),'recorded_at':task.get('attempted_at')} if task and task.get('status')=='submitted' else {'kind':'Owner-reported submission','reference':task.get('receipt'),'recorded_at':task.get('attempted_at')} if task and task.get('status')=='user_reported' else {'kind':'No independent employer receipt recorded'})
            if key in owner_receipts and item['submission_evidence']['kind']!='Employer API confirmed':item['submission_evidence']={'kind':'Owner-reported submission','reference':owner_receipts[key]['reference'],'recorded_at':owner_receipts[key]['created_at']}
            candidates.append(item)
        for row in signals:
            # Keep old records intact, but never recommend private mail or sent copies as vacancies.
            if row.get('source','').lower().startswith('gmail') or 'mail.google.com' in row.get('url',''): continue
            key='r:'+row['id']; flag=flags.get(key,{})
            item={**row,'key':key,'kind':'signal','legacy_id':row['id'],'company':'Organizer not disclosed','provider':row.get('source'),
                'description':row.get('summary'),'stage':flag.get('stage') or ('Saved' if row.get('state')=='saved' else 'Discovered'),
                'first_seen':row.get('seen_at'),'last_checked':None,'availability':'unknown','facts':{},'source_records':[],
                'notes':flag.get('notes') or '', 'submission_evidence':{'kind':'No independent employer receipt recorded'}}
            item.update(self.apply_flags(flag,row.get('state')=='saved'))
            item['dismissed']=bool(item['dismissed'] or row.get('state')=='dismissed')
            candidates.append(item)
        grouped={}
        for item in candidates:
            records=evidence_by_key.get(item['key'],[])
            active=[row for row in records if row['status']!='retained']
            if active:
                latest=max(active,key=lambda row:row['last_seen'] or '')
                payload=loads(latest['payload'],{})
                item['facts']=payload.get('facts',{})
                item['published']=payload.get('published') or item.get('published')
                item['last_checked']=latest.get('last_seen')
                item['availability']='closed' if all(row['status']=='closed' for row in active) else 'listed'
                if payload.get('company'):item['company']=payload['company']
            item['url']=canonical_url(item.get('url'))
            if not item['url']: continue
            item['source_records']=[{'name':row['source_id'],'url':row['canonical_url'],'first_seen':row['first_seen'],'last_seen':row['last_seen'],'status':row['status']} for row in records] or [{'name':str(item.get('provider') or 'Owner-added source'),'url':item['url'],'first_seen':item.get('first_seen'),'last_seen':None,'status':'Historical record; not freshly checked'}]
            primary=aliases_map.get(item['key'])
            group_key='owner:'+primary if primary else identity(item)
            # Resolve explicit primary keys for every linked group, without modifying originals.
            if item['key'] in aliases_map.values():group_key='owner:'+item['key']
            existing=grouped.get(group_key)
            if existing:
                keep,other=(item,existing) if (primary is None and item['key'] in aliases_map.values()) or (item['kind']=='job' and existing['kind']!='job') else (existing,item)
                keep['source_records']+=other['source_records']
                keep['related_keys']=list(dict.fromkeys(keep.get('related_keys',[keep['key']])+other.get('related_keys',[other['key']])))
                keep['saved']=keep['saved'] or other['saved']; keep['pinned']=keep['pinned'] or other['pinned']
                # Preserve an already tracked application when another copy is merely discovered.
                if keep['stage']=='Discovered' and other['stage']!='Discovered':keep['stage']=other['stage'];keep['other_application_key']=other['key']
                grouped[group_key]=keep
            else:grouped[group_key]=item
        items=[]
        for item in grouped.values():
            facts=extract(item); assessment=eligibility(item,facts,profile,stamp); ranking=recommend(item,facts,assessment,profile,history_feedback,stamp)
            if model and isinstance(model.get('weights'),list) and len(model['weights'])==len(ranking['features'])+1:
                weights=model['weights']; value=weights[0]+sum(w*f for w,f in zip(weights[1:],ranking['features']))
                learned=100/(1+math.exp(-max(-30,min(30,value))))
                ranking['score']=round((ranking['score']+learned)/2);ranking['model']=model_rows[0]['id']
            item.update(extracted=facts,eligibility=assessment,recommendation=ranking,warnings=warnings(item,facts),checklist=checklist_counts.get(item['key'],{'total':0,'done':0}))
            item['company_summary']={'description':self.company_description(item,facts),'company_type':facts['fields']['company_type']['value'] or 'Unknown','industry':facts['fields']['industry']['value'] or 'Not disclosed','headquarters':facts['fields']['headquarters']['value'] or 'Not disclosed','size':facts['fields']['company_size']['value'] or 'Not disclosed','website':facts['fields']['company_website']['value'],'source_url':item['url'],'interpretation':'Summary from recorded source text; not independent company due diligence.'}
            item['summary']=self.summarize(facts['description'])
            item['before_applying']=assessment['reasons'][:3]
            item['stale']=bool(not item['last_checked'] or item['last_checked'][:10]<(stamp-timedelta(days=14)).date().isoformat())
            if item['stale']:item['warnings'].append('Not recently checked by the source-health engine. Verify the official page.')
            item['related_keys']=item.get('related_keys',[item['key']])
            items.append(item)
        # Hard conflicts stay below records worth researching, regardless of skill overlap or ML.
        eligibility_order={'eligible':0,'likely':1,'unknown':2,'ineligible':3,'closed':4}
        items.sort(key=lambda item:(not item['pinned'],eligibility_order[item['eligibility']['code']],-item['recommendation']['score'],str(item.get('first_seen') or '')),reverse=False)
        self._cache=items;self._cache_at=time.monotonic();return items

    @staticmethod
    def apply_flags(flag, saved=False):
        return {'saved':bool(flag['saved']) if flag.get('saved',-1) not in (-1,None) else saved,
            'pinned':bool(flag.get('pinned')),'dismissed':bool(flag.get('dismissed')),'archived':bool(flag.get('archived')),
            'substate':flag.get('substate') or '', 'eligibility_override':loads(flag.get('override_data'),None)}

    @staticmethod
    def summarize(description):
        lines=[line.strip() for line in re.split(r'\n|(?<=[.!?])\s+',description) if len(line.strip())>35]
        priority=[line for line in lines if re.search(r'(?i)you will|responsibilit|internship|work on|python|fastapi|engineering|registration|eligib',line)]
        return ' '.join((priority or lines)[:2])[:480] or 'Open the original source to review the full opportunity.'

    @staticmethod
    def company_description(item,facts):
        description=facts['description'];company=str(item.get('company') or '')
        sentences=re.split(r'\n|(?<=[.!?])\s+',description)
        sentence=next((line.strip() for line in sentences if company and company.lower() in line.lower() and re.search(r'(?i) is | builds | provides | platform|product|technology',line)),None)
        return sentence[:500] if sentence else 'The source does not provide a reliable company summary. Review the official listing and company website.'

    def get(self,key):
        if not re.fullmatch(r'[jr]:[a-f0-9]{32,64}',str(key)):raise ValueError('Invalid opportunity identifier.')
        item=next((item for item in self.snapshot() if key in item['related_keys']),None)
        if item is None:raise LookupError('Opportunity not found.')
        return item

    def filtered(self,query):
        items=self.snapshot();q=str(query.get('q','')).strip().lower()[:300]
        implicit={}
        if re.search(r'\bpaid\b',q):implicit['paid']='yes'
        if re.search(r'\bremote\b',q):implicit['mode']='Remote'
        if re.search(r'\bindia\b',q):implicit['location']='india'
        if re.search(r'\bdelhi|ncr\b',q):implicit['location']='ncr'
        if '2028' in q:implicit['year']='2028'
        for category in ('hackathon','fellowship','scholarship','event','internship'):
            if category in q:implicit['type']=category
        terms=[word for word in re.findall(r'[a-z0-9+#.]+',q) if word not in {'paid','remote','in','india','delhi','ncr','2028','accepting','graduates','graduating','students','for','me','show','the','a','an','and','internships','internship','hackathons','hackathon','jobs','opportunities','this','week','fellowships','fellowship','scholarships','scholarship','events','event'}]
        settings={**implicit,**{k:v for k,v in query.items() if v not in ('',None,'all')}}
        result=[]
        for item in items:
            if item['dismissed'] and settings.get('view')!='dismissed':continue
            if item['archived'] and settings.get('view')!='archive':continue
            if settings.get('view')=='saved' and not item['saved']:continue
            if settings.get('view')=='applications' and item['stage']=='Discovered':continue
            if settings.get('view')=='archive' and not item['archived']:continue
            if settings.get('view')=='dismissed' and not item['dismissed']:continue
            if settings.get('eligibility')=='actionable' and item['eligibility']['code'] not in ('eligible','likely'):continue
            if settings.get('eligibility') in ('eligible','likely','unknown','ineligible','closed') and settings['eligibility']!=item['eligibility']['code']:continue
            if settings.get('type') and settings['type'].lower() not in item['category'].lower():continue
            if settings.get('stage') and item['stage']!=settings['stage']:continue
            if settings.get('priority') and item['recommendation']['bucket']!=settings['priority']:continue
            if settings.get('mode') and settings['mode']!=item['extracted']['work_mode']:continue
            location=settings.get('location')
            if location=='india' and not re.search(r'\bindia\b|delhi|noida|gurgaon|gurugram|bengaluru|bangalore|hyderabad|pune|mumbai|chennai|kolkata',item.get('location') or '',re.I):continue
            if location=='ncr' and not re.search(r'delhi|noida|gurgaon|gurugram|\bncr\b|faridabad|ghaziabad',item.get('location') or '',re.I):continue
            if settings.get('paid')=='yes' and (not item['extracted']['fields']['compensation']['value'] or item['extracted']['fields']['compensation']['value']=='Unpaid'):continue
            if settings.get('source') and settings['source'].lower() not in str(item.get('provider') or '').lower():continue
            if settings.get('year') and int(settings['year']) not in (item['extracted']['fields']['graduation_years']['value'] or []):continue
            deadline=item['extracted']['deadline']
            if settings.get('deadline')=='undated' and deadline.get('date'):continue
            if settings.get('deadline') in ('today','week','month'):
                target=deadline.get('local_date') or deadline.get('date')
                if not target:continue
                delta=(date.fromisoformat(target)-datetime.now(ZoneInfo('Asia/Kolkata')).date()).days
                if not 0<=delta<={'today':0,'week':7,'month':30}[settings['deadline']]:continue
            haystack=(str(item.get('title'))+' '+str(item.get('company'))+' '+item['extracted']['description']+' '+str(item.get('location'))).lower()
            if terms and not all(term in haystack for term in terms):continue
            result.append(item)
        sort=settings.get('sort','priority')
        if sort=='recent':result.sort(key=lambda item:str(item.get('first_seen') or ''),reverse=True)
        elif sort=='deadline':result.sort(key=lambda item:item['extracted']['deadline'].get('date') or '9999')
        elif sort=='company':result.sort(key=lambda item:str(item.get('company') or '').lower())
        return result,implicit

    def update(self,key,data):
        item=self.get(key)
        if not isinstance(data,dict):raise ValueError('Opportunity changes must be an object.')
        existing=self.store.rows('SELECT * FROM career_states WHERE key=:key',{'key':key})
        row=existing[0] if existing else {'key':key,'saved':-1,'pinned':0,'dismissed':0,'archived':0,'stage':'','legacy_status':'','substate':'','notes':'','override_data':''}
        changes={}
        for name in ('saved','pinned','dismissed','archived'):
            if name in data:
                if not isinstance(data[name],bool):raise ValueError(name+' must be true or false.')
                if name=='pinned' and data[name] and not item['pinned']:
                    pinned=self.store.rows('SELECT count(*) AS n FROM career_states WHERE pinned=1')[0]['n']
                    if pinned>=5:raise ValueError('Pin up to five priority opportunities.')
                changes[name]=int(data[name])
        if 'stage' in data:
            if data['stage'] not in STAGES:raise ValueError('Invalid application stage.')
            if data['stage']=='Applied' and item['stage']!='Applied' and data.get('submitted_by_owner') is not True:raise ValueError('Confirm that you actually submitted on the employer site. Opening a link or completing a checklist is not a submission.')
            changes['stage']=data['stage'];changes['legacy_status']=LEGACY.get(data['stage'],data['stage'])
        if 'substate' in data:
            if data['substate'] not in SUBSTATES:raise ValueError('Invalid application substate.')
            changes['substate']=data['substate']
        if 'notes' in data:
            if not isinstance(data['notes'],str) or len(data['notes'])>4000:raise ValueError('Notes must be text up to 4,000 characters.')
            changes['notes']=data['notes']
        if 'eligibility_override' in data:
            override=data['eligibility_override']
            if not isinstance(override,dict) or len(str(override.get('reason','')).strip())<12:raise ValueError('Explain your eligibility correction in at least 12 characters.')
            if override.get('source_url') and not canonical_url(override['source_url']):raise ValueError('Use an HTTPS evidence URL.')
            changes['override_data']=dumps({'reason':str(override['reason'])[:1500],'source_url':canonical_url(override.get('source_url')),'recorded_at':self.store.clock(),'label':'Owner review; original requirements retained'})
        deadline=None
        if 'deadline' in data:
            deadline=parse_deadline(data['deadline'],data.get('deadline_timezone'),'Owner recorded')
            if data['deadline'] and not deadline['date']:raise ValueError('Use a valid ISO date or timestamp for the deadline.')
        with self.store.db.begin() as c:
            if not existing:c.execute(states.insert().values(**row,updated_at=self.store.clock()))
            if changes:c.execute(states.update().where(states.c.key==key).values(**changes,updated_at=self.store.clock()))
            if item['kind']=='job':
                assignments={}
                if 'stage' in changes:assignments['status']=changes['legacy_status']
                if 'notes' in changes:assignments['notes']=changes['notes']
                if deadline is not None:assignments['deadline']=deadline['value']
                if assignments:
                    statement='UPDATE jobs SET '+','.join(name+'=:'+name for name in assignments)+',updated=:ts WHERE id=:id'
                    c.execute(text(statement),{**assignments,'ts':self.store.clock(),'id':item['legacy_id']})
            if changes.get('stage')=='Applied' and item['stage']!='Applied':
                c.execute(receipts.insert().values(id=secrets.token_hex(16),opportunity_key=key,reference=str(data.get('reference') or 'Owner confirmed actual submission; reference not supplied')[:400],evidence_type='owner_reported',created_at=self.store.clock()))
            self.store.audit(c,key,'opportunity_updated',before={name:item.get(name) for name in changes},after=changes,evidence_ref=str(data.get('reference') or '')[:400])
        self.invalidate()
        if deadline and deadline['date']:self.add_event({'opportunity_key':key,'title':item['title'],'kind':'Application deadline','date':deadline['value'],'timezone':data.get('deadline_timezone') or 'Asia/Kolkata','notes':'Owner-recorded deadline; verify against the employer.'})
        return self.get(key)

    def checklist(self,key,create=False):
        item=self.get(key)
        rows=self.store.rows('SELECT * FROM career_checklists WHERE opportunity_key=:key ORDER BY position',{'key':key})
        if not rows and create:
            with self.store.db.begin() as c:
                for index,(phase,label) in enumerate(DEFAULT_CHECKLIST):
                    cid=hashlib.sha256((key+':'+str(index)).encode()).hexdigest()[:32]
                    c.execute(text('INSERT INTO career_checklists(id,opportunity_key,label,phase,completed,position,updated_at) VALUES(:id,:key,:label,:phase,0,:position,:ts) ON CONFLICT(id) DO NOTHING'),{'id':cid,'key':key,'label':label,'phase':phase,'position':index,'ts':self.store.clock()})
                self.store.audit(c,key,'checklist_created',after={'count':len(DEFAULT_CHECKLIST),'submission':False})
            self.invalidate()
            rows=self.store.rows('SELECT * FROM career_checklists WHERE opportunity_key=:key ORDER BY position',{'key':key})
        return rows

    def edit_checklist(self,key,cid,data):
        self.get(key)
        row=self.store.rows('SELECT * FROM career_checklists WHERE opportunity_key=:key AND id=:id',{'key':key,'id':cid})
        if not row:raise LookupError('Checklist item not found.')
        values={}
        if 'completed' in data:
            if not isinstance(data['completed'],bool):raise ValueError('Checklist completion must be true or false.')
            values['completed']=int(data['completed'])
        if 'label' in data:
            if not isinstance(data['label'],str) or not 3<=len(data['label'].strip())<=300:raise ValueError('Checklist label must contain 3–300 characters.')
            values['label']=data['label'].strip()
        with self.store.db.begin() as c:
            c.execute(checklists.update().where(checklists.c.id==cid).values(**values,updated_at=self.store.clock()))
            self.store.audit(c,key,'checklist_item_updated',before={'label':row[0]['label'],'completed':row[0]['completed']},after=values)
        self.invalidate();return self.checklist(key)

    def add_checklist(self,key,data):
        self.get(key);label=str(data.get('label') or '').strip()
        if not 3<=len(label)<=300:raise ValueError('Checklist label must contain 3–300 characters.')
        rows=self.checklist(key)
        if len(rows)>=60:raise ValueError('Keep checklists to 60 items per opportunity.')
        with self.store.db.begin() as c:
            c.execute(checklists.insert().values(id=secrets.token_hex(16),opportunity_key=key,label=label,phase=str(data.get('phase') or 'Before applying')[:40],completed=0,position=len(rows),updated_at=self.store.clock()))
            self.store.audit(c,key,'checklist_item_added',after={'label':label})
        self.invalidate();return self.checklist(key)

    def add_event(self,data):
        key=data.get('opportunity_key') or ''
        if key:self.get(key)
        title=str(data.get('title') or '').strip();kind=str(data.get('kind') or 'Reminder')[:60]
        zone=str(data.get('timezone') or 'Asia/Kolkata')
        try:ZoneInfo(zone)
        except Exception:raise ValueError('Use a valid IANA timezone, such as Asia/Kolkata.')
        parsed=parse_deadline(data.get('date'),zone,'Owner recorded')
        if len(title)<3 or len(title)>240 or not parsed['date']:raise ValueError('A title and valid date or timestamp are required.')
        try:minutes=int(data.get('reminder_minutes',1440))
        except (ValueError,TypeError):raise ValueError('Reminder lead time must be minutes.')
        if not 0<=minutes<=43200:raise ValueError('Reminder lead time must be between 0 and 30 days.')
        event_id=str(data.get('id') or hashlib.sha256((key+title+kind+parsed['value']).encode()).hexdigest()[:32])
        if not re.fullmatch(r'[a-f0-9]{32}',event_id):raise ValueError('Invalid event identifier.')
        values={'id':event_id,'opportunity_key':key,'title':title,'kind':kind,'date_value':parsed['value'],'timezone':zone,'precision':parsed['precision'],'reminder_minutes':minutes,'notes':str(data.get('notes') or '')[:1500],'archived':0,'updated_at':self.store.clock()}
        with self.store.db.begin() as c:
            c.execute(text('INSERT INTO career_events(id,opportunity_key,title,kind,date_value,timezone,precision,reminder_minutes,notes,archived,updated_at) VALUES(:id,:opportunity_key,:title,:kind,:date_value,:timezone,:precision,:reminder_minutes,:notes,0,:updated_at) ON CONFLICT(id) DO UPDATE SET title=excluded.title,kind=excluded.kind,date_value=excluded.date_value,timezone=excluded.timezone,precision=excluded.precision,reminder_minutes=excluded.reminder_minutes,notes=excluded.notes,updated_at=excluded.updated_at'),values)
            self.store.audit(c,key,'calendar_event_saved',after=values)
        return values

    def calendar(self):
        result=[];seen=set()
        for row in self.store.rows('SELECT * FROM career_events WHERE archived=0 ORDER BY date_value'):
            row['deadline']=parse_deadline(row['date_value'],row['timezone'],'Owner recorded')
            row['source']='Your calendar';row['url']='';result.append(row)
            seen.add((row['opportunity_key'],row['deadline']['date'],row['kind']))
        for item in self.snapshot():
            deadline=item['extracted']['deadline']
            if not deadline['date'] or item['dismissed'] or item['archived']:continue
            if (item['key'],deadline['date'],'Application deadline') in seen:continue
            result.append({'id':'source-'+hashlib.sha256(item['key'].encode()).hexdigest()[:24],'opportunity_key':item['key'],'title':item['title'],'kind':'Application deadline' if item['kind']=='job' else 'Registration deadline','deadline':deadline,'source':item.get('provider'),'url':item['url'],'notes':'Verify the stated cutoff with the original source.','reminder_minutes':1440})
        return sorted(result,key=lambda row:(row['deadline'].get('date') or '9999',row['title']))

    def today(self):
        items=[item for item in self.snapshot() if not item['dismissed'] and not item['archived']]
        day=datetime.now(ZoneInfo('Asia/Kolkata')).date(); daystring=day.isoformat()
        last_visit=self.store.setting('career_last_visit')
        suitable=[item for item in items if item['stage'] not in TERMINAL and item['eligibility']['code'] in ('eligible','likely')]
        research=[item for item in items if item['stage'] not in TERMINAL and item['eligibility']['code']=='unknown']
        apply_today=[item for item in suitable if item['recommendation']['bucket'] in ('Apply today','Deadline approaching')]
        review_week=[item for item in suitable if item['recommendation']['bucket']=='Worth reviewing this week']
        already_applied=[item for item in items if item['stage'] in ('Applied','Assessment','Interview','Offer')]
        deadlines=self.calendar();groups={'today':[],'week':[],'month':[],'later':[]}
        for event in deadlines:
            delta=(date.fromisoformat(event['deadline'].get('local_date') or event['deadline']['date'])-day).days
            if delta==0:groups['today'].append(event)
            elif 0<delta<=7:groups['week'].append(event)
            elif 7<delta<=30:groups['month'].append(event)
            elif delta>30:groups['later'].append(event)
        followups=[event for event in deadlines if re.search(r'follow.up|reminder',event['kind'],re.I) and event['deadline']['date']<=daystring]
        for item in items:
            if item['stage'] not in ('Applied','Preparing') or not item.get('updated'):continue
            try:elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(item['updated'].replace('Z','+00:00'))).days
            except (ValueError,TypeError):continue
            if 10<=elapsed<=30 and not any(event['opportunity_key']==item['key'] for event in followups):followups.append({'opportunity_key':item['key'],'title':item['title'],'kind':'Suggested follow-up','deadline':{'date':daystring,'precision':'date','cutoff_known':False},'source':'Based on your last recorded update'})
        history=self.store.rows('SELECT * FROM career_history ORDER BY created_at DESC LIMIT 12')
        # Legacy mail is counted as provisional metadata, never as verified employer outcomes.
        inbox=self.optional_rows('career_mail_messages',"SELECT * FROM career_mail_messages WHERE direction='inbound' AND reviewed=0 ORDER BY updated_at DESC LIMIT 100")
        priorities=[{'kind':'review','count':len(suitable),'title':'Suitable opportunities to review','action':'discover','filter':'actionable'},
            {'kind':'deadline','count':sum(0<=(date.fromisoformat(event['deadline'].get('local_date') or event['deadline']['date'])-day).days<=2 for event in deadlines),'title':'Recorded deadlines in the next 2 days','action':'calendar'},
            {'kind':'inbox','count':sum(row['category'] in ('Possible interview','Possible assessment','Possible offer','Possible human reply') for row in inbox),'title':'Inbox signals needing your review','action':'inbox'},
            {'kind':'followup','count':len(followups),'title':'Follow-ups to consider','action':'applications'}]
        return {'date':daystring,'priorities':priorities,'recommended':suitable[:4],
            'apply_today':apply_today[:5],'review_this_week':review_week[:5],
            'already_applied_count':len(already_applied),'research_first':research[:3],
            'recently_discovered':[item for item in sorted(items,key=lambda item:str(item.get('first_seen') or ''),reverse=True) if not last_visit or str(item.get('first_seen') or '')>last_visit][:5],
            'last_visit':last_visit,'deadlines':{name:rows[:8] for name,rows in groups.items()},
            'undated_count':sum(not item['extracted']['deadline']['date'] for item in items),
            'followups':followups[:10],'activity':history,'pinned':[item for item in items if item['pinned']][:5],
            'counts':{'total':len(items),'saved':sum(item['saved'] for item in items),'applications':sum(item['stage'] in TERMINAL for item in items)},
            'model':VERSION,'generated_at':self.store.clock()}

    def add_feedback(self,key,kind):
        item=self.get(key)
        if kind not in FEEDBACK:raise ValueError('Choose a supported feedback option.')
        with self.store.db.begin() as c:
            c.execute(feedback.insert().values(id=secrets.token_hex(16),opportunity_key=key,kind=kind,features=dumps(item['recommendation']['features']),category=item['category'],created_at=self.store.clock()))
            self.store.audit(c,key,'recommendation_feedback',after={'kind':kind})
        self.invalidate();return {'recorded':True,'model':VERSION,'note':'Feedback adjusts transparent priorities. It does not change employer eligibility requirements.'}

    def merge(self,primary,secondary,reason):
        self.get(primary);self.get(secondary)
        if primary==secondary or len(str(reason).strip())<12:raise ValueError('Select two different records and explain the duplicate evidence.')
        if self.store.rows('SELECT * FROM career_aliases WHERE alias_key=:key AND primary_key!=alias_key',{'key':primary}):raise ValueError('Choose the original primary record, not an existing alias.')
        if self.store.rows('SELECT * FROM career_aliases WHERE primary_key=:key',{'key':secondary}):raise ValueError('Unlink existing duplicates before making their primary record an alias.')
        with self.store.db.begin() as c:
            c.execute(text('INSERT INTO career_aliases(alias_key,primary_key,reason,updated_at) VALUES(:alias,:primary,:reason,:ts) ON CONFLICT(alias_key) DO UPDATE SET primary_key=excluded.primary_key,reason=excluded.reason,updated_at=excluded.updated_at'),{'alias':secondary,'primary':primary,'reason':str(reason)[:1000],'ts':self.store.clock()})
            self.store.audit(c,primary,'duplicate_linked',after={'secondary':secondary,'reason':reason,'original_records_retained':True})
        self.invalidate();return self.get(primary)

    def assistant(self,question,keys=None):
        question=str(question or '').strip()[:500]
        if not question:raise ValueError('Ask a question about your stored opportunities.')
        selected=[self.get(key) for key in (keys or [])[:2]]
        if re.search(r'repl(?:ied|y|ies)|inbox|email',question,re.I):
            rows=self.store.rows("SELECT m.account_id,m.subject,m.gmail_id,m.thread_id,m.category,m.human_reply,a.email FROM career_mail_messages m JOIN career_mail_accounts a ON a.id=m.account_id WHERE direction='inbound' ORDER BY date DESC LIMIT 12")
            from urllib.parse import urlencode
            return {'answer':f"Your account-scoped ledger contains {sum(bool(row['human_reply']) for row in rows)} possible human replies in the latest {len(rows)} stored received messages. Classification is provisional; review the Gmail evidence. No application stages were changed.", 'citations':[{'title':row['subject'],'url':'https://mail.google.com/mail/?'+urlencode({'authuser':row['email']})+'#all/'+str(row['thread_id'] or row['gmail_id']),'type':row['category']} for row in rows[:5]],'engine':'Deterministic private-ledger query','limitations':'This answers from stored metadata, not a complete live mailbox search.'}
        if not selected:
            params={'eligibility':'actionable'}
            terms=re.findall(r'\b(?:hackathon|fellowship|scholarship|paid|backend|python|remote|india|2028)\b',question,re.I)
            if terms:params['q']=' '.join(terms)
            selected=self.filtered(params)[0][:5]
            if not selected:
                params['eligibility']='unknown';selected=self.filtered(params)[0][:3]
        if not selected:return {'answer':'No stored opportunities satisfy the available evidence and filters. Broaden your search or check Sources for fresh, permitted listings. Missing information is not treated as eligibility.','citations':[],'engine':VERSION,'limitations':'Rules and stored source text only; no external AI service is used.'}
        if re.search(r'compare|comparison',question,re.I):
            lines=[f"{item['company']} — {item['title']}\nEligibility: {item['eligibility']['label']}. {item['eligibility']['reasons'][0]}\nLocation: {item.get('location') or 'Not disclosed'}. Work mode: {item['extracted']['work_mode']}.\nCompensation: {item['extracted']['fields']['compensation']['value'] or 'Not disclosed'}. Duration: {item['extracted']['fields']['duration']['value'] or 'Not disclosed'}.\nOfficial deadline: {item['extracted']['deadline']['value'] or 'Not stated'}. Priority: {item['recommendation']['score']} rules points. Next: {item['before_applying'][0]}" for item in selected[:2]]
        elif re.search(r'company|companies|what does',question,re.I):
            lines=[f"{item['company']}: {item['company_summary']['description']}\nIndustry: {item['company_summary']['industry']}. Size: {item['company_summary']['size']}. Headquarters: {item['company_summary']['headquarters']}. Recorded source: {item['url']}." for item in selected]
        elif re.search(r'missing|skill|learn',question,re.I):
            lines=[f"{item['title']}: recorded skill overlap: {', '.join(item['recommendation']['matched_skills']) or 'not established'}. Skills to verify or develop: {', '.join(item['recommendation']['skills_to_verify']) or 'none extracted; review the full requirements'}. A short plan: read the official requirement, build one small demonstrable exercise for the first missing skill, and document it honestly." for item in selected]
        elif re.search(r'cover letter|resume bullet|cold email|draft',question,re.I):
            experience=PUBLIC_PROFESSIONAL_PROFILE['experience'][0]
            lines=[f"Draft for {item['company']} — {item['title']}:\nHello Hiring Team,\nI am interested in the {item['title']} opportunity. I previously worked as a {experience['role']} at {experience['company']}. My public projects include {', '.join(project['name'] for project in PUBLIC_PROFESSIONAL_PROFILE['projects'][:2])}. I would welcome the opportunity to discuss the requirements and my relevant work.\nGitHub: {PUBLIC_PROFESSIONAL_PROFILE['github']}\nThank you,\nRaj Salonia\n\nReview every detail before use. No college or graduation year has been inserted into this general introduction." for item in selected[:1]]
        else:
            lines=[f"{index+1}. {item['company']} · {item['title']}\n{item['eligibility']['label']}. {' '.join(item['recommendation']['reasons'])} Next: {' '.join(item['before_applying'][:2])} Suggested review: {item['recommendation']['suggested_action_date']} (not an official deadline)." for index,item in enumerate(selected)]
        return {'answer':'\n\n'.join(lines),'citations':[{'key':item['key'],'title':item['title'],'url':item['url'],'type':'Recorded source'} for item in selected], 'engine':VERSION,'limitations':'Extractive summaries, rules, and your recorded profile. This is not a generative model or independent company verification. Private mail and resume bytes are not used for model training.'}

    def model_status(self):
        rows=self.store.rows('SELECT id,status,metrics,created_at FROM career_models ORDER BY created_at DESC LIMIT 10')
        latest={}
        for row in self.store.rows('SELECT * FROM career_feedback ORDER BY created_at'):
            if row['kind']!='Already applied':latest[row['opportunity_key']]=row
        return {'baseline':VERSION,'feedback_records':len(latest),'minimum_distinct_opportunities':40,'models':[{**row,'metrics':loads(row['metrics'],{})} for row in rows], 'privacy':'Only explicit opportunity feedback and numeric relevance features are eligible for training. Gmail, contact details and resume documents are excluded.'}

    def evaluate_model(self):
        latest={}
        for row in self.store.rows('SELECT * FROM career_feedback ORDER BY created_at'):
            if row['kind']!='Already applied':latest[row['opportunity_key']]=row
        rows=list(latest.values());positives=sum(row['kind'] in ('Interested','Prefer similar') for row in rows)
        if len(rows)<40 or min(positives,len(rows)-positives)<8:raise ValueError('At least 40 distinct opportunities with genuine feedback, including 8 positive and 8 negative examples, are needed. Rules remain active.')
        rows.sort(key=lambda row:hashlib.sha256(row['opportunity_key'].encode()).hexdigest())
        holdout=rows[::5];training=[row for index,row in enumerate(rows) if index%5]
        weights=[0.0]*8
        def probability(features):return 1/(1+math.exp(-max(-20,min(20,weights[0]+sum(w*f for w,f in zip(weights[1:],features))))))
        for _ in range(100):
            for row in training:
                features=loads(row['features'],[])
                if len(features)!=7:continue
                target=int(row['kind'] in ('Interested','Prefer similar'));error=probability(features)-target
                weights[0]-=.035*error
                for index,value in enumerate(features):weights[index+1]-=.035*(error*value+.02*weights[index+1])
        base_errors=[];learned_errors=[]
        for row in holdout:
            x=loads(row['features'],[])
            if len(x)!=7:continue
            target=int(row['kind'] in ('Interested','Prefer similar'))
            base=min(1,max(0,(35*x[0]+20*x[1]+12*x[2]+8*x[3]+20*x[4]+5*x[5])/100))
            base_errors.append((base-target)**2);learned_errors.append((probability(x)-target)**2)
        metrics={'training':len(training),'holdout':len(base_errors),'baseline_brier':round(sum(base_errors)/max(1,len(base_errors)),4),'candidate_brier':round(sum(learned_errors)/max(1,len(learned_errors)),4)}
        metrics['improved']=metrics['candidate_brier']+.02<metrics['baseline_brier']
        mid='feedback-'+secrets.token_hex(8)
        with self.store.db.begin() as c:c.execute(models.insert().values(id=mid,config=dumps({'weights':weights,'features':'v1-seven-features'}),metrics=dumps(metrics),status='evaluated',created_at=self.store.clock()))
        return {'id':mid,'metrics':metrics,'activated':False,'note':'Explicit activation is available only if the held-out loss improves. Eligibility remains rules-based.'}
