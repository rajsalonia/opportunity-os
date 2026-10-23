# Opportunity OS — Automated applications (free-tier safe)

## What this branch implements

- Private **My Applications → Auto-Apply Queue** dashboard, with a persistent unique posting fingerprint, progress statuses, review links and employer receipts.
- Opt-in automation rules: minimum estimated match 70–100%, India or explicitly India-eligible remote locations, graduation year 2028, maximum 1–3 submissions daily.
- Encrypted, user-approved applicant profile containing legal first and last names, email, phone, confirmed India work authorization, 2028 graduation and consent. Stored in PostgreSQL, never GitHub.
- Automatic submission adapter **only for Greenhouse employer-authorized Job Board API**, conditional on that employer providing a valid Board API key and a verified simple application form. Custom questions/consents always require review.
- Lever and Ashby remain manual-form fallback until authorized and tested write integrations exist.
- Existing Gmail drafts and individual email review controls remain unchanged. **No unattended recruiter emails.**
- A token-protected schedule endpoint, POST https://opportunity-os-autoapply.onrender.com/autoapply/schedule, which refreshes employer listings, prepares tasks and runs authorized submissions. It does nothing externally when automation is disabled.

## Turn on your applicant profile and rules

1. Open https://opportunity-os-autoapply.onrender.com/#applications and sign in.
2. Choose **Find eligible opportunities**. Unclear graduation-year, location or work eligibility becomes a **needs_review** task. Check these on the real employer site before approving an individual listing.
3. In **Verified applicant profile**, enter and explicitly confirm accurate legal name, email, phone, India work authorization and submission consent. Details are encrypted using the stable SESSION_SECRET in Render.
4. In **Automation rules**, set maximum 1/day initially and minimum estimated match at least 75%. Enable only after reviewing your profile and rules.
5. Under a supported employer's Greenhouse integration, a company-authorized Job Board API key is required. No applicant can obtain this key merely by creating an account; employers control these keys. If you are genuinely authorized, add private Render Environment variable GREENHOUSE_BOARD_KEYS_JSON, mapping board slug to employer-issued key. Placeholder example: {"company-board":"EMPLOYER_ISSUED_KEY"}. Never commit or share real values. Without the key, the task stays in manual review and zero requests are sent.
6. The application engine inspects live Greenhouse job-specific required questions. Unsupported form fields, employer consent, legal or demographic fields, and uncertain outcomes are held for human review. A confirmed HTTP success is logged with provider receipt or HTTP acknowledgement. Uncertain network outcomes are recorded as unknown, and never automatically retried.

## Optional daily scheduling on free plans

Render Free spins down on inactivity. It has no guaranteed always-running worker and you must not use an unauthenticated public cron endpoint. A token-protected POST route is included.

For a free external scheduler, cron-job.org offers custom POST methods and headers; setting up that separate account is a user action.

- URL: https://opportunity-os-autoapply.onrender.com/autoapply/schedule
- Method: POST
- Example schedule: 10:00 Asia/Kolkata daily
- Custom header name: X-Opportunity-OS-Token
- Header value: copy your private OPPORTUNITY_OS_CRON_TOKEN from the Render Environment screen into the scheduler. A strong token has been generated and placed there.
- Configure failed-run alerts, and inspect execution results. Never append the token to a URL.
- Until you enable an external scheduler, automatic scheduled execution is not running. The authenticated dashboard buttons still work on demand.

## Boundaries and data safety

- No real job application was sent while implementing or testing; tests use synthetic resume bytes and mock employer responses.
- The protected original uploaded resume stays byte-for-byte unchanged. The application engine reads the current database-stored original and verifies its pinned SHA-256 before sending.
- No CAPTCHA bypass, unauthorized ATS posting, bot-evasion, or invented legal/work eligibility answers.
- An existing Applied, Interview, Assessment, Offer, Rejected or Closed role cannot be re-submitted.
- Greenhouse company credentials do not authorize submission to other employer boards. Lever/Ashby discovery does not grant submission permissions.
- Switching database providers without migration can strand your queue and application receipts. Make private database-level backups; the existing JSON backup predates queue tracking.
- Changing SESSION_SECRET invalidates encrypted applicant-profile data and Gmail OAuth tokens. Plan reauthorization before rotating.
- No paid resources or paid Render cron jobs were created. Free web services can sleep, throttle or be paused; reliability is not guaranteed.

## Files and testing

- autoapply_engine.py — persistent queue, eligibility, encryption, guarded Greenhouse API adapter, scheduled endpoint.
- tests/test_autoapply.py — tests approvals, dedup, no-key fallback, mock employer receipts, unsupported-field stops.
- static/app.js / templates/index.html / static/app.css — private responsive Auto-Apply controls.
- Branch: opportunity-os-hosted. GitHub main unchanged.


## Global remote-first discovery (October 2026 expansion)

The **Explore Opportunities** screen now sorts by remote-first relevance by default. Filter for:
- All remote
- Worldwide remote (employer/feed claim, not a guarantee of India work eligibility)
- India-mentioned remote
- Hybrid
- On-site

Each opportunity shows the provider, a longer description preview, and a full job description of up to 12,000 characters when the source supplies it. The detail view explicitly labels work mode and any inferred geographic restrictions.

**Public feeds**: Jobicy, Remotive and Arbeitnow. The publisher name and original listing URL are preserved. Jobicy and Remotive have attribution and polling restrictions; use the existing daily scheduled refresh, not continuous polling. Arbeitnow includes European listings and is not assumed to be India-eligible. These feeds provide **discovery**, not permission to submit applications.

**Company boards**: Existing Greenhouse/Lever/Ashby boards plus 45 additional candidate employer boards, including remote-first companies and startups. Slugs are tested live during refresh; some may have changed, be inactive, or provide no relevant openings. A configured board does not guarantee a live opening.

**Important**: No finite integration covers every employer or startup worldwide. Workday, LinkedIn, Indeed, company-specific forms, and other sites need separately authorized adapters or manual review. Remote jobs restricted to another country must not be treated as globally eligible.

**Submission history**: In **My Applications → Auto-Apply Queue**, choose **Confirmed submitted** to view only employer-acknowledged submissions with their receipt and timestamp. **Needs review** shows forms or eligibility requiring manual work. The downloadable private receipts backup is independent of Gmail email history.

**Automation activation**: Once the applicant profile and rules have been explicitly approved, routine eligible submissions through a genuine employer-authorized connector can run without repeated prompts. Missing authorization, custom employer questions, uncertain network outcomes, and ambiguous work eligibility must remain in review. The user does not need to approve every routine *supported* application, but the platform cannot override employer requirements or access controls.

## India hiring expansion

The **Career Sources** screen now contains 20 India/global discovery platforms (including Internshala, Unstop, Naukri, Foundit, Instahyre, Cutshort, Cuvette, Wellfound, Hirist, Freshersworld, AICTE Internship Portal, National Career Service, Superset and others). These links are explicitly marked **external discovery / manual application**. Their listings are not automatically ingested and the app does not log into these websites or submit forms there.

An additional 28 India-focused employer-board candidates are included in the existing Greenhouse/Lever/Ashby public ATS refresh. Some candidate board identifiers may be inactive or not owned by the named company: failed boards are reported, and only actual returned job postings are saved. Never imply a board candidate is a verified open role.

**Automation status**: public feed and employer ATS discovery is available from the Refresh button. Unattended daily refreshing still needs an authenticated external scheduler; adding the directory alone does not create one. Full auto-submission to every India job board is not available without supported employer APIs and/or authorized interactive integrations. Never claim a job was applied to until a real employer acknowledgment is recorded.
