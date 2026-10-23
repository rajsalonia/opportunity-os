"""Employer-origin opportunities reviewed on 2026-10-23.

Source URLs are provided by the employer or employer-hosted ATS, rather than
search aggregator application forms. Listings may expire; users should check
live eligibility and required declarations before applying.

This bootstrap prepares tasks, NOT employer submissions.
"""
import hashlib
from urllib.parse import urlsplit
from sqlalchemy import text

CURATED=[
    {
      "company":"Anavai Technologies",
      "title":"Software Engineering Intern — Founding Team",
      "location":"Remote (Delhi NCR / Gurugram), India",
      "url":"https://anavaihq.com/jobs/software-engineering-intern",
      "provider":"company-site",
      "description":"3-month full-time internship, stipend up to INR 15,000, remote around Delhi NCR/Gurugram. Pre-final- or final-year B.Tech CSE/IT students eligible. Work on Python FastAPI, React/Next.js, PostgreSQL and AI-driven product features, directly with founding team. Employer application redirects to a Google Form; verify availability and answer custom form questions."
    },
    {
      "company":"Drivetrain",
      "title":"Engineering Intern — Gen AI for FP&A Platform",
      "location":"Remote — India",
      "url":"https://jobs.lever.co/drivetrain/bc1c17bc-86ac-4f00-a1e3-0eb85aae4fdc",
      "provider":"lever",
      "description":"Internship, remote in India. Employer welcomes currently pursuing Computer Science degree. Build RAG, LLM, agentic AI features and integrations for financial planning platform. DSA, system design, Gen AI projects, API integration and cloud familiarity are relevant; check official Lever application questions."
    },
    {
      "company":"Infergent Labs",
      "title":"AI / Full-Stack Engineering Intern",
      "location":"Remote — India",
      "url":"https://infergent.com/careers/ai-fullstack-engineering-intern",
      "provider":"company-site",
      "description":"3–6 month remote-in-India internship building features for a live AI product. Python, React/Next.js, LLMs, RAG pipelines, API integration, debugging and deployment. Employer listing welcomes engineering experience and personal GitHub projects. Verify the official page remains live."
    },
    {
      "company":"Weekday (client role)",
      "title":"Software Engineer Intern",
      "location":"Remote — Bengaluru, India",
      "url":"https://jobs.lever.co/weekdayworks/a86efff4-1c2e-43fc-8ecb-dc8f873db2f1",
      "provider":"lever",
      "description":"Client-company internship advertised by Weekday; Bengaluru remote and currently pursuing relevant degree accepted. Source advertises stipend INR 30,000–50,000 per month, 2–6 month internship, and Python/JavaScript/Java/C++ fundamentals. Verify salary and actual employer identity before accepting."
    },
    {
      "company":"Byteburst",
      "title":"Software Engineering Intern",
      "location":"Remote — India only",
      "url":"https://byteburst.io/careers",
      "provider":"company-site",
      "description":"India-only remote entry-level software engineering internship; full-stack web/API/cloud features and some iOS/Swift work. Position shown on the company's careers page. Verify whether it remains open and the work commitment."
    },
    {
      "company":"HackerRank",
      "title":"Software Development Engineer Intern",
      "location":"On-site — Bengaluru, India",
      "url":"https://job-boards.greenhouse.io/hackerrank/jobs/8229735",
      "provider":"greenhouse",
      "description":"On-site full-time software engineering internship, Bangalore. Application asks whether the candidate can start a six-month term January 5 2027 and work on-site the entire period. Check academic schedule and company requirements before answering."
    }
]

def seed_curated_jobs(db, now, rank):
    """Idempotent inserts. Never overwrites job or application status/notes."""
    new_jobs=0;new_tasks=0
    with db.begin() as c:
        c.execute(text("""CREATE TABLE IF NOT EXISTS application_tasks (
                job_id VARCHAR(64) PRIMARY KEY,
                fingerprint VARCHAR(64) NOT NULL UNIQUE,
                status VARCHAR(30) NOT NULL,
                reason TEXT DEFAULT '',
                receipt TEXT DEFAULT '',
                reviewed_at TEXT DEFAULT '',
                attempted_at TEXT DEFAULT '',
                updated_at TEXT DEFAULT '')"""))
        for item in CURATED:
            u=urlsplit(item["url"])
            if u.scheme!="https" or not u.hostname:continue
            job_id=hashlib.sha256(item["url"].encode()).hexdigest()[:32]
            fingerprint=hashlib.sha256((u.hostname.lower()+u.path.rstrip("/")).encode()).hexdigest()
            points,warning=rank(item["title"],item["description"],item["location"])
            row={**item,"id":job_id,"score":points,
                 "warnings":warning or "Eligibility and employer-specific form questions require review.",
                 "ts":now()}
            result=c.execute(text("""INSERT INTO jobs
               (id,company,title,location,url,provider,description,score,warnings,status,
                notes,deadline,discovered,updated)
               VALUES(:id,:company,:title,:location,:url,:provider,:description,:score,
                      :warnings,'Discovered','Imported from verified employer page 2026-10-23;
                      check listing and answer required fields on official site.','',:ts,:ts)
               ON CONFLICT(id) DO NOTHING"""),row)
            new_jobs+=int(result.rowcount>0)
            task=c.execute(text("""INSERT INTO application_tasks
                  (job_id,fingerprint,status,reason,updated_at)
                  VALUES(:job_id,:fingerprint,'needs_review',
                         'Application pack ready; open official employer form, verify eligibility and submit.',
                         :ts) ON CONFLICT DO NOTHING"""),
                 {"job_id":job_id,"fingerprint":fingerprint,"ts":row["ts"]})
            new_tasks+=int(task.rowcount>0)
    return {"jobs_added":new_jobs,"tasks_prepared":new_tasks}
