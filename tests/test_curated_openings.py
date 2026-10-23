"""Curated openings are draft tasks, never outbound applications."""
from sqlalchemy import create_engine, text
from curated_openings import CURATED, seed_curated_jobs

def test_verified_shortlist_is_review_only_and_idempotent(tmp_path):
    db=create_engine("sqlite:///"+str(tmp_path/"curated.db"))
    with db.begin() as c:
        c.execute(text("""CREATE TABLE jobs(id TEXT PRIMARY KEY,company TEXT NOT NULL,
                  title TEXT NOT NULL,location TEXT,url TEXT,provider TEXT,
                  description TEXT,score INTEGER,warnings TEXT,status TEXT,
                  notes TEXT,deadline TEXT,discovered TEXT,updated TEXT)"""))
    rank=lambda *args: (82,"")
    first=seed_curated_jobs(db,lambda:"2026-10-23T00:00:00Z",rank)
    second=seed_curated_jobs(db,lambda:"2026-10-23T00:10:00Z",rank)
    assert first["jobs_added"]==len(CURATED)
    assert first["tasks_prepared"]==len(CURATED)
    assert second=={"jobs_added":0,"tasks_prepared":0}
    with db.connect() as c:
        data=c.execute(text("SELECT status,receipt FROM application_tasks")).all()
        assert all(s=="needs_review" and not receipt for s,receipt in data)
        assert c.scalar(text("SELECT count(*) FROM jobs WHERE status='Applied'"))==0
    db.dispose()

def test_seed_never_resets_manual_history(tmp_path):
    db=create_engine("sqlite:///"+str(tmp_path/"history.db"))
    with db.begin() as c:
        c.execute(text("""CREATE TABLE jobs(id TEXT PRIMARY KEY,company TEXT NOT NULL,
                  title TEXT NOT NULL,location TEXT,url TEXT,provider TEXT,
                  description TEXT,score INTEGER,warnings TEXT,status TEXT,
                  notes TEXT,deadline TEXT,discovered TEXT,updated TEXT)"""))
    rank=lambda *args:(79,"")
    seed_curated_jobs(db,lambda:"2026-10-23T00:00:00Z",rank)
    with db.begin() as c:
        job_id=c.scalar(text("SELECT id FROM jobs LIMIT 1"))
        c.execute(text("UPDATE jobs SET status='Applied',notes='Real manual confirmation' WHERE id=:id"),{"id":job_id})
        c.execute(text("UPDATE application_tasks SET status='user_reported',receipt='employer-ref-1' WHERE job_id=:id"),{"id":job_id})
    seed_curated_jobs(db,lambda:"2026-10-23T00:20:00Z",rank)
    with db.connect() as c:
        assert c.scalar(text("SELECT status FROM jobs WHERE id=:id"),{"id":job_id})=="Applied"
        assert c.scalar(text("SELECT receipt FROM application_tasks WHERE job_id=:id"),{"id":job_id})=="employer-ref-1"
    db.dispose()
