"""Account-bound, read-only Gmail intelligence. No automatic application-stage changes."""
import hashlib
import os
import re
import threading
import time
from datetime import datetime, timezone
from email.utils import parseaddr, getaddresses
from urllib.parse import urlencode
import requests
from sqlalchemy import text
from .schema import accounts, messages, dumps, loads
from inbox_intelligence import classify_message, DELIVERY, AUTO_REPLY, INTERVIEW, ASSESSMENT, REJECTION, RECEIPT, AUTOMATED_SENDER

def classify(raw, sent, own_email):
    labels=raw.get('labels',[]);sender=parseaddr(raw.get('from',''))[1].lower()
    if 'SENT' in labels or 'DRAFT' in labels or sender==own_email.lower():return {**raw,'direction':'outbound','category':'Sent','human_reply':False,'reply_evidence':'Sent copy; excluded from recruiter replies and discovery.'}
    header=raw.get('headers',{});info=raw.get('subject','')+' '+raw.get('snippet','')
    automated=header.get('auto-submitted','no').lower()!='no' or header.get('precedence','').lower() in ('bulk','list','junk') or bool(header.get('list-unsubscribe')) or bool(AUTOMATED_SENDER.search(sender))
    same_thread=any(x.get('thread_id')==raw.get('thread_id') and raw.get('thread_id') for x in sent)
    exact_sender=any(sender in [address.lower() for _,address in getaddresses([x.get('to','')])] for x in sent)
    if DELIVERY.search(info):category='Delivery failure'
    elif AUTO_REPLY.search(info):category='Out of office'
    elif re.search(r'(?i)job offer|offer of employment|pleased to offer|offer letter',info):category='Possible offer'
    elif INTERVIEW.search(info):category='Possible interview'
    elif ASSESSMENT.search(info):category='Possible assessment'
    elif REJECTION.search(info):category='Possible rejection'
    elif RECEIPT.search(info):category='Application acknowledgement'
    elif header.get('list-unsubscribe') or header.get('precedence','').lower() in ('bulk','list'):category='Newsletter / alert'
    elif (same_thread or exact_sender) and not automated:category='Possible human reply'
    else:category='Needs review'
    human=category=='Possible human reply'
    return {**raw,'direction':'inbound','category':category,'human_reply':human,
        'reply_evidence':'Same account and outgoing thread matched; verify original.' if human and same_thread else 'Exact recipient matched within this account; verify original.' if human else 'Provisional content classification. No application stage was changed.'}

class Mail:
    def __init__(self,store,cipher,token_table,legacy_get,ready):
        self.store,self.cipher,self.token_table,self.legacy_get,self.ready=store,cipher,token_table,legacy_get,ready
        self.lock=threading.Lock();self.running=set()

    def save_token(self,reference,token):
        if not self.ready():raise ValueError('Persistent storage and configured Google OAuth are required.')
        blob=self.cipher.encrypt(dumps(token).encode())
        with self.store.db.begin() as c:
            c.execute(text('INSERT INTO oauth_tokens(id,token,updated) VALUES(:id,:token,:ts) ON CONFLICT(id) DO UPDATE SET token=excluded.token,updated=excluded.updated'),{'id':reference,'token':blob,'ts':self.store.clock()})

    def connect(self,token,legacy=False):
        # Identity is verified using this token, never inferred from the current browser account.
        response=requests.get('https://gmail.googleapis.com/gmail/v1/users/me/profile',headers={'Authorization':'Bearer '+token['access_token']},timeout=15)
        response.raise_for_status();email=str(response.json().get('emailAddress','')).lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):raise ValueError('Google did not return a verified mailbox identity.')
        aid=hashlib.sha256(email.encode()).hexdigest()[:32];reference='gmail' if legacy else 'gmail-'+aid[:24]
        old=self.store.rows('SELECT * FROM career_mail_accounts WHERE id=:id',{'id':aid})
        # Reconnecting an existing identity preserves its token reference, including the legacy connection.
        if old:reference=old[0]['token_ref']
        if old and not token.get('refresh_token'):
            with self.store.db.connect() as c:previous=c.execute(self.token_table.select().where(self.token_table.c.id==reference)).mappings().first()
            if previous:
                existing=loads(self.cipher.decrypt(bytes(previous['token'])).decode(),{})
                if existing.get('refresh_token'):token['refresh_token']=existing['refresh_token']
        self.save_token(reference,token)
        with self.store.db.begin() as c:
            c.execute(text("INSERT INTO career_mail_accounts(id,email,token_ref,verified_at,status) VALUES(:id,:email,:ref,:ts,'connected') ON CONFLICT(id) DO UPDATE SET verified_at=excluded.verified_at,status='connected',error_category=NULL"),{'id':aid,'email':email,'ref':reference,'ts':self.store.clock()})
        return aid

    def token(self,account):
        if not self.ready():raise ValueError('Connect Google OAuth with persistent storage first.')
        with self.store.db.connect() as c:row=c.execute(self.token_table.select().where(self.token_table.c.id==account['token_ref'])).mappings().first()
        if not row:raise ValueError('Reconnect this Gmail account.')
        token=loads(self.cipher.decrypt(bytes(row['token'])).decode(),{})
        if float(token.get('expires_at',0))<=time.time()+90:
            if not token.get('refresh_token'):raise ValueError('Reconnect this Gmail account to renew access.')
            response=requests.post('https://oauth2.googleapis.com/token',data={'client_id':os.getenv('GOOGLE_CLIENT_ID'),'client_secret':os.getenv('GOOGLE_CLIENT_SECRET'),'refresh_token':token['refresh_token'],'grant_type':'refresh_token'},timeout=15)
            response.raise_for_status();fresh=response.json();token.update(access_token=fresh['access_token'],expires_at=time.time()+int(fresh.get('expires_in',3600)))
            self.save_token(account['token_ref'],token)
        return token['access_token']

    def account(self,aid):
        rows=self.store.rows('SELECT * FROM career_mail_accounts WHERE id=:id',{'id':aid})
        if not rows:raise LookupError('Choose a verified Gmail account.')
        return rows[0]

    def request(self,account,path,params=None):
        response=requests.get('https://gmail.googleapis.com/gmail/v1/users/me/'+path,params=params,headers={'Authorization':'Bearer '+self.token(account)},timeout=16)
        response.raise_for_status();return response.json()

    def scan(self,aid):
        account=self.account(aid)
        try:
            identity=self.request(account,'profile')
            if str(identity.get('emailAddress','')).lower()!=account['email']:raise ValueError('Mailbox identity mismatch; reconnect the intended account.')
            refs=[]
            # Include relevant Spam, but exclude Trash. Scan is bounded to 120 messages and three pages.
            params={'q':'in:anywhere -in:trash newer_than:120d (application OR internship OR interview OR assessment OR offer OR hiring OR recruiter OR subject:undeliverable)','maxResults':40,'includeSpamTrash':'true'}
            for _ in range(3):
                page=self.request(account,'messages',params);refs+=page.get('messages',[])
                if not page.get('nextPageToken'):break
                params={**params,'pageToken':page['nextPageToken']}
            fetched=[]
            for ref in refs[:120]:
                value=self.request(account,'messages/'+ref['id'],{'format':'metadata','metadataHeaders':['Subject','From','To','Date','Auto-Submitted','Precedence','List-Unsubscribe']})
                headers={h['name'].lower():h['value'] for h in value.get('payload',{}).get('headers',[])}
                attachments=[]
                def parts(part):
                    if part.get('filename'):attachments.append({'filename':str(part['filename'])[:250],'mime_type':part.get('mimeType'),'bytes':(part.get('body') or {}).get('size')})
                    for child in part.get('parts',[]):parts(child)
                parts(value.get('payload',{}))
                fetched.append({'id':value['id'],'thread_id':value.get('threadId',''),'labels':value.get('labelIds',[]),
                  'subject':headers.get('subject','')[:500],'from':headers.get('from','')[:400],'to':headers.get('to','')[:1000],
                  'snippet':str(value.get('snippet',''))[:1000],'date':datetime.fromtimestamp(int(value.get('internalDate',0))/1000,timezone.utc).isoformat(),
                  'headers':headers,'attachments':attachments})
            sent=[x for x in fetched if 'SENT' in x['labels'] or parseaddr(x['from'])[1].lower()==account['email']]
            sent+= [{'thread_id':r['thread_id'],'to':r['recipients']} for r in self.store.rows("SELECT thread_id,recipients FROM career_mail_messages WHERE account_id=:id AND direction='outbound'",{'id':aid})]
            with self.store.db.begin() as c:
                for raw in fetched:
                    row=classify(raw,sent,account['email']);mid=hashlib.sha256((aid+':'+raw['id']).encode()).hexdigest()[:40]
                    values={'id':mid,'account_id':aid,'gmail_id':raw['id'],'thread_id':raw['thread_id'],'direction':row['direction'],'sender':raw['from'],'recipients':raw['to'],'subject':raw['subject'],'snippet':raw['snippet'],'date':raw['date'],'category':row['category'],'reply_evidence':row['reply_evidence'],'human_reply':int(row['human_reply']),'labels':dumps(raw['labels']),'attachments':dumps(raw['attachments']),'updated_at':self.store.clock()}
                    c.execute(text('INSERT INTO career_mail_messages('+','.join(values)+',reviewed) VALUES('+','.join(':'+n for n in values)+',0) ON CONFLICT(id) DO UPDATE SET category=excluded.category,reply_evidence=excluded.reply_evidence,human_reply=excluded.human_reply,updated_at=excluded.updated_at'),values)
                c.execute(accounts.update().where(accounts.c.id==aid).values(last_checked=self.store.clock(),status='connected',error_category=None))
            return {'checked':len(fetched),'account_id':aid}
        except Exception as exc:
            category='identity_or_access_error' if isinstance(exc,ValueError) else 'gmail_unavailable'
            with self.store.db.begin() as c:c.execute(accounts.update().where(accounts.c.id==aid).values(status='Needs attention',error_category=category))
            return {'error':category,'account_id':aid}
        finally:
            with self.lock:self.running.discard(aid)

    def launch(self,aid=None):
        self.store.ensure()
        if not aid:
            rows=self.store.rows('SELECT id FROM career_mail_accounts ORDER BY verified_at')
            if not rows:
                # Only bind the preserved single-account token after Google verifies its identity.
                token=self.legacy_get()
                if not token:raise ValueError('Connect a Gmail account first.')
                legacy={'token_ref':'gmail'};token['access_token']=self.token(legacy)
                aid=self.connect(token,legacy=True)
            else:aid=rows[0]['id']
        self.account(aid)
        with self.lock:
            if aid in self.running:return {'queued':False,'account_id':aid,'status':'A scan is already running.'}
            self.running.add(aid)
        threading.Thread(target=self.scan,args=(aid,),daemon=True,name='career-gmail-read').start()
        return {'queued':True,'account_id':aid,'status':'Read-only Gmail scan queued.'}

    def snapshot(self,aid=None):
        self.store.ensure();account_rows=self.store.rows('SELECT id,email,last_checked,status,error_category FROM career_mail_accounts ORDER BY verified_at')
        rows=self.store.rows('SELECT * FROM career_mail_messages '+('WHERE account_id=:id ' if aid else '')+'ORDER BY date DESC LIMIT 300',{'id':aid} if aid else {})
        known={r['gmail_id'] for r in rows}
        # Preserve historical ledger without inventing an account identity for old messages.
        if not aid and 'mail_activity' in __import__('sqlalchemy').inspect(self.store.db).get_table_names():
            for r in self.store.rows('SELECT * FROM mail_activity ORDER BY date DESC LIMIT 160'):
                if r['id'] in known:continue
                rows.append({'id':'legacy:'+r['id'],'account_id':'legacy','gmail_id':r['id'],'thread_id':r.get('thread_id'),
                    'direction':'outbound' if r.get('direction')=='sent' else 'inbound','sender':r.get('sender'),'recipients':r.get('recipients'),'subject':r.get('subject'),
                    'snippet':r.get('snippet'),'date':r.get('date'),'category':r.get('stage'),'reply_evidence':'Historical account identity was not recorded. Verify the original account in Gmail.','human_reply':False,'reviewed':r.get('reviewed'),'labels':'[]','attachments':'[]'})
        for row in rows:
            account=next((a for a in account_rows if a['id']==row['account_id']),None)
            row['account_email']=account['email'] if account else 'Historical connection — identity not recorded'
            row['gmail_url']='https://mail.google.com/mail/?'+urlencode({'authuser':account['email'] if account else 0})+'#all/'+str(row.get('thread_id') or row['gmail_id'])
            row['attachments']=loads(row['attachments'],[]);row['labels']=loads(row['labels'],[])
        rows.sort(key=lambda r:r.get('date') or '',reverse=True)
        return {'accounts':account_rows,'messages':rows[:300],'running_accounts':list(self.running),'scan_scope':'Relevant messages from the last 120 days, including Spam; up to 120 per scan. No message bodies or attachment bytes are downloaded.','legacy_send':'The existing reviewed-send tool uses the preserved original Gmail connection. Added accounts are read-only.'}
