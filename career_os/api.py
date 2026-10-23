"""Owner-only v3 API; legacy routes and private artifacts retain their original contracts."""
import csv
import io
import secrets
from datetime import datetime, timezone
from flask import request, session, jsonify, abort, Response, render_template, redirect, Blueprint
from sqlalchemy import text
from .schema import Store, models, messages, events, aliases, dumps, loads
from .service import CareerService
from .discovery import Discovery, SourceFailure
from .mail import Mail
from .intelligence import STAGES, SUBSTATES, FEEDBACK, parse_deadline

def ics_escape(value):return str(value or '').replace('\\','\\\\').replace('\n','\\n').replace(';','\\;').replace(',','\\,').replace('\r','')

def ics_calendar(rows):
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Opportunity OS//Private Career Calendar//EN','CALSCALE:GREGORIAN']
    for row in rows:
        deadline=row.get('deadline') or parse_deadline(row.get('date_value'),row.get('timezone'),'Owner recorded')
        if not deadline['date']:continue
        lines+=['BEGIN:VEVENT','UID:'+ics_escape(row['id'])+'@opportunity-os','DTSTAMP:'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')]
        if deadline['precision']=='date':lines.append('DTSTART;VALUE=DATE:'+deadline['date'].replace('-',''))
        elif deadline['utc']:lines.append('DTSTART:'+datetime.fromisoformat(deadline['utc']).astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
        else:
            # Unknown time zone is intentionally exported as a date, never a made-up instant.
            lines.append('DTSTART;VALUE=DATE:'+deadline['date'].replace('-',''))
        note=(row.get('notes') or '')+'\nSource time zone: '+deadline['timezone']+('\nExact cutoff unknown.' if not deadline['cutoff_known'] else '')
        lines+=['SUMMARY:'+ics_escape(row['title']),'DESCRIPTION:'+ics_escape(note)]
        if row.get('url'):lines.append('URL:'+ics_escape(row['url']))
        if row.get('reminder_minutes') is not None:lines+=['BEGIN:VALARM','ACTION:DISPLAY','DESCRIPTION:Opportunity reminder','TRIGGER:-PT'+str(max(0,int(row['reminder_minutes'])))+'M','END:VALARM']
        lines.append('END:VEVENT')
    lines.append('END:VCALENDAR')
    # RFC 5545 folds UTF-8 by octets, not characters.
    folded=[]
    for line in lines:
        chunk='';size=0
        for char in line:
            length=len(char.encode('utf-8'))
            if size+length>73:folded.append(chunk);chunk=' ';size=1
            chunk+=char;size+=length
        folded.append(chunk)
    return '\r\n'.join(folded)+'\r\n'

def register(app,db,owner,check_origin,clock,cipher,token_table,legacy_token,google_ready,boards,portals):
    bp=Blueprint('career',__name__)
    store=Store(db,clock);service=CareerService(store,cipher);discovery=Discovery(store,service,boards,portals);mail=Mail(store,cipher,token_table,legacy_token,google_ready)
    app.extensions['career']={'store':store,'service':service,'discovery':discovery,'mail':mail}

    @bp.before_request
    def secure_career():
        if request.path.startswith('/api/v3/'):
            owner()
            if request.method not in ('GET','HEAD','OPTIONS'):
                check_origin()
                if not secrets.compare_digest(request.headers.get('X-CSRF-Token',''),session.get('career_csrf','missing')):abort(403)

    def run(action):
        try:return action()
        except SourceFailure as exc:return {'error':'Public source validation failed: '+exc.category},422
        except ValueError as exc:return {'error':str(exc)},422
        except LookupError as exc:return {'error':str(exc)},404

    def body():
        value=request.get_json(silent=True)
        if not isinstance(value,dict):raise ValueError('Send a JSON object.')
        return value

    @bp.get('/classic')
    def classic():
        owner();return render_template('index.html')

    @bp.get('/api/v3/bootstrap')
    def bootstrap():
        return run(lambda:{'profile':service.profile(),'stages':STAGES,'substates':SUBSTATES,'feedback':FEEDBACK,'version':'3.0','timezone':'Asia/Kolkata'})

    @bp.get('/api/v3/today')
    def today():return run(service.today)

    @bp.post('/api/v3/visit')
    def visit():store.put_setting('career_last_visit',clock());return {'recorded':True}

    @bp.route('/api/v3/profile',methods=['GET','PUT'])
    def profile():return run(lambda:service.update_profile(body()) if request.method=='PUT' else service.profile())

    @bp.get('/api/v3/opportunities')
    def opportunities():
        def action():
            items,implicit=service.filtered(request.args)
            try:page=max(1,int(request.args.get('page',1)));size=max(1,min(60,int(request.args.get('size',18))))
            except ValueError:raise ValueError('Page and size must be numbers.')
            start=(page-1)*size
            return {'items':items[start:start+size],'total':len(items),'page':page,'size':size,'has_more':start+size<len(items),'interpreted_filters':implicit}
        return run(action)

    @bp.route('/api/v3/opportunities/<key>',methods=['GET','PATCH'])
    def opportunity(key):
        def action():
            if request.method=='PATCH':return service.update(key,body())
            item=service.get(key)
            timeline=store.rows('SELECT * FROM career_history WHERE opportunity_key=:key ORDER BY created_at DESC LIMIT 100',{'key':key})
            receipts=store.rows('SELECT * FROM career_receipts WHERE opportunity_key=:key ORDER BY created_at DESC',{'key':key})
            return {**item,'timeline':timeline,'receipts':receipts,'checklist_items':service.checklist(key)}
        return run(action)

    @bp.route('/api/v3/opportunities/<key>/checklist',methods=['GET','POST'])
    def checklist(key):return run(lambda:{'items':service.checklist(key,create=True) if request.method=='POST' and not (request.get_json(silent=True) or {}).get('label') else service.add_checklist(key,body()) if request.method=='POST' else service.checklist(key)})

    @bp.patch('/api/v3/opportunities/<key>/checklist/<cid>')
    def checklist_item(key,cid):return run(lambda:{'items':service.edit_checklist(key,cid,body())})

    @bp.post('/api/v3/opportunities/<key>/feedback')
    def feedback(key):return run(lambda:service.add_feedback(key,body().get('kind')))

    @bp.post('/api/v3/merge')
    def merge():return run(lambda:service.merge(body().get('primary'),body().get('secondary'),str(body().get('reason') or '')))

    @bp.delete('/api/v3/merge/<key>')
    def unmerge(key):
        with db.begin() as c:
            row=c.execute(text('SELECT * FROM career_aliases WHERE alias_key=:key'),{'key':key}).mappings().first()
            if not row:return {'error':'Merge not found'},404
            c.execute(aliases.delete().where(aliases.c.alias_key==key));store.audit(c,key,'merge_undone',before=dict(row))
        service.invalidate();return {'restored':True}

    @bp.get('/api/v3/sources')
    def source_health():return run(discovery.health)

    @bp.post('/api/v3/sources')
    def add_source():return run(lambda:discovery.add_board(body()))

    @bp.patch('/api/v3/sources/<sid>')
    def enable_source(sid):
        def action():
            value=body().get('enabled')
            if not isinstance(value,bool):raise ValueError('Enabled must be true or false.')
            rows=store.rows('SELECT * FROM career_sources WHERE id=:id',{'id':sid})
            if not rows or rows[0]['mode'] not in ('API','Feed'):raise ValueError('Only connected adapters can be enabled.')
            with db.begin() as c:c.execute(text('UPDATE career_sources SET enabled=:enabled WHERE id=:id'),{'enabled':int(value),'id':sid})
            return {'updated':True}
        return run(action)

    @bp.post('/api/v3/refresh')
    def refresh():return run(lambda:(discovery.launch(),202))

    @bp.get('/api/v3/calendar')
    def calendar():return run(lambda:{'events':service.calendar(),'timezone':'Asia/Kolkata','cutoff_policy':'Date-only deadlines have no inferred time of day.'})

    @bp.post('/api/v3/calendar')
    def add_event():return run(lambda:service.add_event(body()))

    @bp.delete('/api/v3/calendar/<eid>')
    def archive_event(eid):
        with db.begin() as c:c.execute(events.update().where(events.c.id==eid).values(archived=1,updated_at=clock()));store.audit(c,'calendar','event_archived',after={'id':eid})
        return {'archived':True}

    @bp.get('/api/v3/calendar.ics')
    def ics():return Response(ics_calendar(service.calendar()),mimetype='text/calendar',headers={'Content-Disposition':'attachment; filename=opportunity-os-calendar.ics'})

    @bp.get('/api/v3/inbox')
    def inbox():return run(lambda:mail.snapshot(request.args.get('account')))

    @bp.post('/api/v3/inbox/refresh')
    def mail_refresh():return run(lambda:(mail.launch(body().get('account_id')),202))

    @bp.post('/api/v3/inbox/<mid>/reviewed')
    def review_mail(mid):
        if mid.startswith('legacy:'):
            from mail_activity import mark_reviewed
            return run(lambda:{'reviewed':bool(mark_reviewed(db,mid[7:]))})
        with db.begin() as c:c.execute(messages.update().where(messages.c.id==mid).values(reviewed=1))
        return {'reviewed':True}

    @bp.get('/api/v3/gmail/connect')
    def add_gmail():
        owner()
        if not google_ready():return {'error':'Google OAuth is not configured with persistent storage.'},503
        session['career_oauth_add']=True
        return redirect('/api/gmail/connect')

    @bp.post('/api/v3/intelligence')
    def intelligence():return run(lambda:service.assistant(body().get('question',''),body().get('keys',[])))

    @bp.get('/api/v3/models')
    def model_status():return run(service.model_status)

    @bp.post('/api/v3/models/evaluate')
    def evaluate_model():return run(service.evaluate_model)

    @bp.post('/api/v3/models/activate')
    def activate_model():
        def action():
            mid=body().get('id')
            rows=store.rows('SELECT * FROM career_models WHERE id=:id',{'id':mid})
            if not rows or loads(rows[0]['metrics'],{}).get('improved') is not True:raise ValueError('Only an evaluated candidate that improves held-out loss can be activated.')
            with db.begin() as c:
                c.execute(text("UPDATE career_models SET status='retired' WHERE status='active'"));c.execute(text("UPDATE career_models SET status='active' WHERE id=:id"),{'id':mid});store.audit(c,'models','model_activated',after={'id':mid})
            service.invalidate();return service.model_status()
        return run(action)

    @bp.post('/api/v3/models/rollback')
    def rollback():
        with db.begin() as c:c.execute(text("UPDATE career_models SET status='retired' WHERE status='active'"));store.audit(c,'models','rules_restored')
        service.invalidate();return service.model_status()

    @bp.get('/api/v3/analytics')
    def analytics():
        items=service.snapshot();stages={s:sum(r['stage']==s for r in items) for s in STAGES}
        return {'opportunities':len(items),'stages':stages,'eligibility':{s:sum(r['eligibility']['code']==s for r in items) for s in ('eligible','likely','unknown','ineligible','closed')},
          'owner_reported_submissions':store.rows('SELECT count(*) AS n FROM career_receipts')[0]['n'],
          'audit_events':store.rows('SELECT count(*) AS n FROM career_history')[0]['n'],
          'limitation':'Stage totals reflect current records, not conversion rates. Historical transitions and employer receipts were not consistently recorded before version 3.0.'}

    @bp.get('/api/v3/export')
    def export():
        rows=[{k:r.get(k) for k in ('key','title','company','category','location','url','stage','notes','first_seen','published','last_checked','saved','archived')} for r in service.snapshot()]
        if request.args.get('format')=='csv':
            stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=list(rows[0]) if rows else ['key','title']);writer.writeheader()
            # Prevent spreadsheet formula injection in user or source text.
            for row in rows:writer.writerow({k:('\''+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v) for k,v in row.items()})
            return Response(stream.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=opportunity-os-private.csv'})
        payload={'format':'opportunity-os-workspace-v3','exported_at':clock(),'opportunities':rows}
        for name in ('states','checklists','history','events','feedback','receipts','aliases'):
            payload[name]=store.rows('SELECT * FROM career_'+name)
        return Response(dumps(payload),mimetype='application/json',headers={'Content-Disposition':'attachment; filename=opportunity-os-workspace-private.json'})

    app.register_blueprint(bp)
    return service
