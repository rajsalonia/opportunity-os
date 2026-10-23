# Opportunity OS — private internship command center

This branch contains **Opportunity OS**, independent of the repository's default GitHub profile README. The profile's `main` branch is unchanged.

## Goals
Find 2028-graduation-eligible Summer 2027 internships, prioritize Delhi NCR, India and remote roles eligible for India, and track application/outreach steps. Only employer-posted jobs from accessible Greenhouse, Lever and Ashby boards are auto-imported. LinkedIn, YC, Internshala, Wellfound and other platforms are openable search links; automatic submission on those sites is **not** implemented.

## Hosted service
https://opportunity-os-autoapply.onrender.com

## Render environment variables
- `APP_PASSWORD`: long unique login password.
- `SESSION_SECRET`: random strong session signing secret.
- `HTTPS_ONLY=true`.
- `DATABASE_URL`: PostgreSQL connection string, including Supabase PostgreSQL. Enter it privately in Render; without it, SQLite records are TEMPORARY and confidential uploads and OAuth are disabled. For the free Supabase plan, copy the **Session pooler** connection string from the project's Connect dialog (port 5432; pooled username includes the project reference), percent-encode reserved password characters, and use `sslmode=require`. Preserve stronger SSL verification if configured. The app normalizes `postgres://` and `postgresql://` to SQLAlchemy's psycopg driver. Connections are bounded and prepared statements are disabled for pooler compatibility.
- For optional Gmail integration, `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` (from Google Cloud OAuth desktop/web application; **web** origin). Authorized redirect URL: `https://opportunity-os-autoapply.onrender.com/auth/google/callback`.
- The Google OAuth consent screen may require configuring permitted test users and enabling Gmail API. Gmail integration uses read-only and send OAuth scopes only after your authorization.

## Resume safety
Upload **Raj_Salonia_Resume-2.pdf** through the logged-in UI only after PostgreSQL is configured. The original PDF bytes are saved exactly and its SHA-256 is displayed. Never commit personal resume/HR files to this public source-code branch.

The vault refuses to replace an existing original with a different PDF, including concurrent uploads. Uploading the same bytes is idempotent. **Verify integrity** recomputes SHA-256 from stored bytes; it never modifies the document. Optional `ORIGINAL_RESUME_SHA256` pins the approved checksum and rejects other bytes. The redesign does not read or alter a local or production resume file.

## Install locally
```bash
pip install -r requirements.txt
export APP_PASSWORD='set-your-own-long-password'
export SESSION_SECRET='set-your-own-random-secret'
export HTTPS_ONLY=false
gunicorn -w 1 -b 0.0.0.0:8000 app:app
```

## Current functionality
- Private login; verified public employer board search; skills-based match scoring; 2028-eligibility warning; location filters; application stages.
- CSV app export; contact import (CSV/XLSX) after permanent database connection.
- PDF original vault after permanent DB connection.
- Gmail inbox status classification and one-email-at-a-time reviewed sending **after user completes their own Google OAuth setup**. Email sends are capped at 10 per day and require explicit confirmation each time.
- No account passwords are required for job sites in this app. No unattended ATS auto-submit; many employer platforms require interactive forms and do not expose public applicant-write APIs.
- No billing-enabled infrastructure or paid plans.

## Workspace interface
- Eight real sections: Overview, Explore opportunities, My applications, Recruiter CRM, Gmail & outreach, Resume vault, Career sources, and Settings & integrations. Hash navigation supports browser back/forward. Desktop sidebar collapses; mobile navigation supports keyboard focus and Escape.
- Overview derives counts from server summary and reminder data. The radar uses estimated keyword matches; recent activity represents the latest stored update for each loaded job, not a fabricated event history.
- Explore combines text, location, exact stage, and estimated-match filters, four sort choices, and progressive loading in groups of 24. The API loads up to 2,000 recent records; export covers all records. Remote location does not imply India eligibility.
- Job details show the source description as escaped text. Stage, notes/next action, and confirmed deadline are editable. The tracker has board/list controls and automatically uses a vertical layout on small screens.
- Contacts display company, person, email, and target role, with search and personal draft preparation. CSV/XLSX imports retain validation and duplicate skipping. No bulk send action exists.
- Drafts are editable and copyable without Gmail. Connected Gmail sends require review plus a final individual confirmation. Editing a recipient, subject, message, or attachment clears the review checkbox. No emails are sent by discovery or reminders.
- Settings shows actual database, session, Gmail, resume, and source configuration. Configured boards are not represented as successfully reachable until a refresh returns its result.
- JSON backup/restore and CSV exports remain available. Restore updates matching job URLs; backups exclude resumes and OAuth tokens.

The frontend uses a Flask template plus `static/app.css`, `static/app.js`, and inline SVG icons. There is no frontend build step or paid dependency. Google Fonts has system font fallbacks. The public template renders only sign-in; the authenticated shell is server-gated. Private API routes remain protected, and content is escaped before HTML insertion.

## Verification
```bash
python -m pytest -q tests
node --check static/app.js
```
CI runs both checks on `opportunity-os-hosted`. Tests use isolated SQLite and synthetic private-file/email fixtures; external Gmail sending is mocked. They cover authentication, origin checks, all nine stages, deadlines/notes, search, safe exports, backups, CSV/XLSX imports, Gmail review and duplicate gates, original-PDF checksums/replacement protection, source configuration, refresh state preservation, and sanitized database failures.

`/health` checks database connectivity and returns HTTP 503 on connection failure without exposing connection details. Database failure leaves the sign-in screen reachable and private APIs report a readable retry/setup error. `gunicorn.conf.py` allows up to 180 seconds for employer board and Gmail requests; the existing Render start command loads it automatically.

## Supabase setup and deployment
Keep the existing free Render service and `opportunity-os-hosted` branch. Configure `DATABASE_URL` privately, then redeploy and check `/health` and Settings. No Supabase authentication layer, paid infrastructure, database deletion, or data migration is part of this change. Existing records in another database are not moved automatically; export them before switching database URLs and restore only after reviewing the backup.

Gmail's authorized redirect remains `https://opportunity-os-autoapply.onrender.com/auth/google/callback`. Configure Google OAuth credentials and authorize the intended account yourself. Connection status means authorization is stored; Check replies verifies current Google API access. The original PDF should be uploaded only through the authenticated vault after persistent storage is connected.

## Operational limitations
- Track the selected database provider's free-tier limits and keep private application backups.
- Free Render web service may sleep when idle, so application refresh occurs only when the user clicks it; daily ChatGPT job alerts are separate.
- A successful listing fetch does not prove international work authorization or graduation-year eligibility; always verify employer requirements.
- Sender Gmail remains disconnected until OAuth credentials and authorization are configured.


## Unified daily command center (October 2026)
The dashboard home page now provides category switches for all tracked employer roles (including uncertain remote eligibility), hackathons, startup alerts, events/fellowships/community posts, and possible recruiter replies. It prioritizes real Gmail reply candidates and clearly labels the verification caveat for every item. The "For you" view shows a compact mixed selection, while the category views show up to 16 each; all jobs remain in Explore and all public signals remain in Radar. Filters are view-only and do not imply that any application has been submitted. Inbox data appears only after the website's own Gmail OAuth setup; the Gmail connector inside ChatGPT is a separate authorization.

This public repository deliberately contains **no application email content, contact spreadsheet, tokens, passwords or resume attachment**. Official employer feeds are first-party. Brabble, DEV and other sources are third-party discovery and may be unavailable; the original organizer controls registration and deadlines. LinkedIn / Wellfound / Unstop are not silently scraped, and this project cannot cover every vacancy on the internet. Manual site applications and autofill remain under user review, not falsely recorded as submitted.

## Additional opportunity source coverage
The public radar now includes DEV's hiring, fellowship and developer-challenge feeds alongside the existing hackathon, employer and remote-job feeds. Brabble's public RSS remains active without sign-in. An **optional** `BRABBLE_API_KEY` (configured privately in Render, never in GitHub) enables Brabble's structured college-student listings, including supplied deadline, organizer, platform, eligibility and team size; this is an attributed discovery lead, not a verified application or guaranteed deadline. API use follows Brabble's stated 1,000-requests/day free limit and 4-hour cache. An absent API key sends **zero** Brabble API requests. The app never scrapes private LinkedIn profiles or bypasses platform logins. Source links and failure flags remain visible.

## More accurate Gmail history
Incoming messages are now classified into application receipts, tentative interview/assessment/rejection signals, delivery failures, automated out-of-office replies and general needs-review. Delivery failures and automatic replies are explicitly excluded from the human-reply count even when they share a sent Gmail thread. This prevents bounced outreach from being reported as a recruiter response. All classifications are hints; review original email and never automatically advance application status.
