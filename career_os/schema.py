"""Versioned, additive tables. Existing jobs, mail, tokens and documents are never migrated."""
import json
import secrets
from threading import Lock
from sqlalchemy import MetaData, Table, Column, String, Text, Integer, text

metadata = MetaData()

def table(name, *columns):
    return Table('career_' + name, metadata, *columns)

def key(name='id', size=96):
    return Column(name, String(size), primary_key=True)

versions = table('schema_versions', key('version'), Column('applied_at', Text))
preferences = table('preferences', key(), Column('data', Text), Column('updated_at', Text))
companies = table('companies', key(), Column('name', Text), Column('data', Text), Column('updated_at', Text))
states = table('states', key('key'), Column('saved', Integer, default=-1), Column('pinned', Integer, default=0),
    Column('dismissed', Integer, default=0), Column('archived', Integer, default=0),
    Column('stage', Text), Column('legacy_status', Text), Column('substate', Text),
    Column('notes', Text), Column('override_data', Text), Column('updated_at', Text))
aliases = table('aliases', key('alias_key'), Column('primary_key', Text), Column('reason', Text), Column('updated_at', Text))
checklists = table('checklists', key(), Column('opportunity_key', String(96), index=True),
    Column('label', Text), Column('phase', Text), Column('completed', Integer, default=0),
    Column('position', Integer), Column('updated_at', Text))
history = table('history', key(), Column('opportunity_key', String(96), index=True),
    Column('event', Text), Column('before_data', Text), Column('after_data', Text),
    Column('actor', Text), Column('evidence', Text), Column('created_at', Text))
events = table('events', key(), Column('opportunity_key', String(96), index=True), Column('title', Text),
    Column('kind', Text), Column('date_value', Text), Column('timezone', Text), Column('precision', Text),
    Column('reminder_minutes', Integer), Column('notes', Text), Column('archived', Integer, default=0), Column('updated_at', Text))
feedback = table('feedback', key(), Column('opportunity_key', String(96), index=True), Column('kind', Text),
    Column('features', Text), Column('category', Text), Column('created_at', Text))
models = table('models', key(), Column('config', Text), Column('metrics', Text), Column('status', Text), Column('created_at', Text))
sources = table('sources', key(), Column('provider', Text), Column('slug', Text), Column('name', Text),
    Column('category', Text), Column('mode', Text), Column('url', Text), Column('reference', Text),
    Column('interval_minutes', Integer), Column('enabled', Integer), Column('created_at', Text))
sync = table('sync', key('source_id'), Column('status', Text), Column('last_attempt', Text), Column('last_success', Text),
    Column('next_at', Text), Column('failures', Integer, default=0), Column('success_count', Integer, default=0),
    Column('attempt_count', Integer, default=0), Column('record_count', Integer, default=0), Column('error_category', Text),
    Column('etag', Text), Column('modified', Text), Column('lease_until', Text), Column('claim', Text))
evidence = table('evidence', key(), Column('opportunity_key', String(96), index=True),
    Column('source_id', String(96), index=True), Column('source_record_id', Text), Column('canonical_url', Text),
    Column('content_hash', Text), Column('payload', Text), Column('first_seen', Text), Column('last_seen', Text),
    Column('status', Text), Column('misses', Integer, default=0))
receipts = table('receipts', key(), Column('opportunity_key', String(96), index=True), Column('reference', Text),
    Column('evidence_type', Text), Column('created_at', Text))
accounts = table('mail_accounts', key(), Column('email', Text), Column('token_ref', Text), Column('verified_at', Text),
    Column('last_checked', Text), Column('status', Text), Column('error_category', Text))
messages = table('mail_messages', key(), Column('account_id', String(96), index=True), Column('gmail_id', Text),
    Column('thread_id', Text), Column('direction', Text), Column('sender', Text), Column('recipients', Text),
    Column('subject', Text), Column('snippet', Text), Column('date', Text), Column('category', Text),
    Column('reply_evidence', Text), Column('human_reply', Integer), Column('reviewed', Integer, default=0),
    Column('labels', Text), Column('attachments', Text), Column('updated_at', Text))

def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))

def loads(value, fallback=None):
    try: return json.loads(value) if value else fallback
    except (ValueError, TypeError): return fallback

class Store:
    def __init__(self, db, clock):
        self.db, self.clock, self.ready, self.lock = db, clock, False, Lock()

    def ensure(self):
        if self.ready: return
        with self.lock:
            if self.ready: return
            with self.db.begin() as connection:
                # Both production workers can receive their first authenticated request together.
                if self.db.dialect.name=='postgresql':connection.execute(text('SELECT pg_advisory_xact_lock(462015030)'))
                metadata.create_all(connection)
                connection.execute(text("INSERT INTO career_schema_versions(version,applied_at) VALUES('3.0-additive-1',:ts) ON CONFLICT(version) DO NOTHING"), {'ts': self.clock()})
            self.ready = True

    def rows(self, statement, params=None):
        self.ensure()
        with self.db.connect() as connection:
            return [dict(row) for row in connection.execute(text(statement), params or {}).mappings()]

    def setting(self, name, default=None):
        with self.db.connect() as connection:
            value = connection.scalar(text('SELECT value FROM settings WHERE key=:key'), {'key': name})
        return value if value is not None else default

    def put_setting(self, name, value):
        with self.db.begin() as connection:
            connection.execute(text('INSERT INTO settings(key,value) VALUES(:key,:value) ON CONFLICT(key) DO UPDATE SET value=excluded.value'), {'key':name, 'value':value})

    def audit(self, connection, opportunity_key, event, before=None, after=None, actor='owner', evidence_ref=''):
        connection.execute(history.insert().values(id=secrets.token_hex(16), opportunity_key=opportunity_key,
            event=event, before_data=dumps(before), after_data=dumps(after), actor=actor,
            evidence=evidence_ref, created_at=self.clock()))
