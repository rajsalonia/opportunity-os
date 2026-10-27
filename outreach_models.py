"""
AI Outreach Manager - Data Models and Schema Definitions.
Supports both SQLite and PostgreSQL. Additive, non-destructive schema.
"""
import json
import secrets
from datetime import datetime, timezone
from threading import Lock
from sqlalchemy import MetaData, Table, Column, String, Text, Integer, Index

metadata = MetaData()

def table(name, *columns):
    return Table(name, metadata, *columns)

def key(name='id', size=64):
    return Column(name, String(size), primary_key=True)

# 1. Import Batches
batches = table(
    'outreach_batches',
    key(),
    Column('filename', Text, nullable=False),
    Column('file_size', Integer, default=0),
    Column('total_rows', Integer, default=0),
    Column('valid_rows', Integer, default=0),
    Column('duplicate_rows', Integer, default=0),
    Column('incomplete_rows', Integer, default=0),
    Column('column_mapping', Text),
    Column('status', String(32), default='uploaded'),
    Column('created_at', Text)
)

# 2. Companies
companies = table(
    'outreach_companies',
    key(),
    Column('name', Text, nullable=False),
    Column('normalized_name', String(128), nullable=False, index=True),
    Column('domain', Text),
    Column('category', String(32), default='unknown'),
    Column('location', Text),
    Column('website', Text),
    Column('linkedin_url', Text),
    Column('notes', Text),
    Column('created_at', Text),
    Column('updated_at', Text)
)

# 3. Contacts
contacts = table(
    'outreach_contacts',
    key(),
    Column('batch_id', String(64), index=True),
    Column('company_id', String(64), index=True),
    Column('company_name', Text, nullable=False),
    Column('name', Text, nullable=False),
    Column('email', String(254), nullable=False, index=True),
    Column('normalized_email', String(254), nullable=False, index=True),
    Column('designation', Text),
    Column('department', Text),
    Column('location', Text),
    Column('company_website', Text),
    Column('linkedin_url', Text),
    Column('phone', Text),
    Column('notes', Text),
    Column('source_filename', Text),
    Column('email_status', String(32), default='valid'),
    Column('email_notes', Text),
    Column('is_duplicate', Integer, default=0),
    Column('merged_into_id', String(64)),
    Column('is_incomplete', Integer, default=0),
    Column('outreach_status', String(32), default='not_contacted'),
    Column('last_contacted_at', Text),
    Column('created_at', Text),
    Column('updated_at', Text)
)

# 4. Email Drafts
drafts = table(
    'outreach_drafts',
    key(),
    Column('contact_id', String(64), nullable=False, index=True),
    Column('campaign_id', String(64)),
    Column('subject', Text, nullable=False),
    Column('salutation', Text),
    Column('body', Text, nullable=False),
    Column('style', String(32), default='professional'),
    Column('personalization_type', String(32), default='general_software'),
    Column('status', String(32), default='draft'),
    Column('approved_at', Text),
    Column('approved_by', Text),
    Column('attach_resume', Integer, default=0),
    Column('created_at', Text),
    Column('updated_at', Text)
)

# 5. Outreach Messages
messages = table(
    'outreach_messages',
    key(),
    Column('contact_id', String(64), nullable=False, index=True),
    Column('draft_id', String(64)),
    Column('recipient_email', Text, nullable=False),
    Column('subject', Text, nullable=False),
    Column('body', Text, nullable=False),
    Column('gmail_message_id', Text, index=True),
    Column('gmail_thread_id', Text, index=True),
    Column('status', String(32), default='sent'),
    Column('reply_summary', Text),
    Column('reply_received_at', Text),
    Column('is_human_reply', Integer, default=0),
    Column('error_details', Text),
    Column('sent_at', Text),
    Column('created_at', Text)
)

# 6. Follow-up Reminders & Sequences
followups = table(
    'outreach_followups',
    key(),
    Column('contact_id', String(64), nullable=False, index=True),
    Column('parent_message_id', String(64), nullable=False),
    Column('sequence_number', Integer, default=1),
    Column('scheduled_date', Text, nullable=False),
    Column('status', String(32), default='pending'),
    Column('draft_id', String(64)),
    Column('notes', Text),
    Column('created_at', Text),
    Column('updated_at', Text)
)

# 7. Suppression Entries (Opt-outs, bounces, explicit blocks)
suppressions = table(
    'outreach_suppressions',
    key(),
    Column('email', String(254), nullable=False, unique=True, index=True),
    Column('domain', Text),
    Column('reason', String(64), nullable=False),
    Column('notes', Text),
    Column('created_at', Text)
)

# 8. Audit Logs
audit_logs = table(
    'outreach_audit_logs',
    key(),
    Column('event_type', String(64), nullable=False),
    Column('target_id', String(64)),
    Column('actor', String(64), default='owner'),
    Column('details', Text),
    Column('created_at', Text)
)

def ensure_outreach_tables(db):
    """Safely creates all outreach tables if they do not exist."""
    metadata.create_all(db)

def now_iso():
    return datetime.now(timezone.utc).isoformat()
