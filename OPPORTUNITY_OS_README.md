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
- `DATABASE_URL`: **Render PostgreSQL internal database URL**. Enter it privately in the Render dashboard; without it, local SQLite records are TEMPORARY and confidential uploads and OAuth are disabled.
- For optional Gmail integration, `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` (from Google Cloud OAuth desktop/web application; **web** origin). Authorized redirect URL: `https://opportunity-os-autoapply.onrender.com/auth/google/callback`.
- The Google OAuth consent screen may require configuring permitted test users and enabling Gmail API. Gmail integration uses read-only and send OAuth scopes only after your authorization.

## Resume safety
Upload **Raj_Salonia_Resume-2.pdf** through the logged-in UI only after PostgreSQL is configured. The original PDF bytes are saved exactly and its SHA-256 is displayed. Never commit personal resume/HR files to this public source-code branch.

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

## Operational limitations
- Free Render PostgreSQL is time-limited, check its expiration date in Render and export backups.
- Free Render web service may sleep when idle, so application refresh occurs only when the user clicks it; daily ChatGPT job alerts are separate.
- A successful listing fetch does not prove international work authorization or graduation-year eligibility; always verify employer requirements.
- Sender Gmail remains disconnected until OAuth credentials and authorization are configured.
