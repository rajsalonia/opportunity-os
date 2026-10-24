# Opportunity OS 3.0

The private workspace is available at https://opportunity-os-autoapply.onrender.com. The production branch is `opportunity-os-hosted`. The profile README and portfolio are separate projects and are not modified by this release.

## Workspace

The primary navigation is Today, Discover, Saved, Applications, Inbox, and Calendar. Settings contains profile preferences, source health, analytics, exports, recommendation controls, archive, and links to the existing private tools at `/classic`.

Today shows actual stored priorities, upcoming deadlines, records first discovered since the last successful visit, pinned opportunities, and audit activity. Missing eligibility or company facts remain unknown. It never fabricates suitable openings to fill a dashboard. Discover supports natural-language keywords and structured filters for type, eligibility, mode, geography, compensation, stated graduation year, source, deadline period, and sorting. Lists are paginated.

Both themes use locally hosted [Lucide](https://github.com/lucide-icons/lucide) line icons. Lucide's ISC and inherited Feather MIT notices are included in `static/vendor/lucide/LICENSE`. [Iconoir](https://github.com/iconoir-icons/iconoir), under MIT, was also reviewed; Lucide was selected for the existing navigation and workflow vocabulary. No remote icon service, font request, or frontend package build is required.

## Data preservation and architecture

`career_os/schema.py` creates versioned `career_*` tables alongside the existing schema. It does not rewrite or delete jobs, radar records, contacts, documents, settings, OAuth tokens, or application tasks. PostgreSQL first-use schema initialization uses an advisory transaction lock across workers. Existing routes retain their contracts; `/api/v3/*` adds owner-only workspace operations and CSRF tokens.

The modules separate source adapters and synchronization (`discovery.py`), deterministic extraction and eligibility (`intelligence.py`), projections and workflow actions (`service.py`), account-bound Gmail intelligence (`mail.py`), and API/calendar exports (`api.py`). Browser-only changes live in `workspace.html`, `workspace.css`, and `workspace.js`.

The original resume vault, encrypted contacts, existing imports, single reviewed Gmail sends, application packs, form companion, guarded application queue, and legacy backup/restore remain reachable in Settings → Tools & integrations. The original PDF bytes are never used by extraction, ranking, feedback training, or this release's migration. General outreach introductions no longer insert graduation year or college automatically.

## Discovery coverage

Initial registry counts, before owner additions: 16 configured API sources, 11 feeds, 30 search-only portals, 4 systems requiring credentials, and 1 unsupported integration. These are configuration counts, **not** claims of 27 successful connections. Source health separately reports actual attempts, last success, matching records, success rate, next permitted check, error category, and cooldown state. Existing custom employer boards are imported if supported; those change the counts.

| Mode | Scope | Actual behavior |
| --- | --- | --- |
| Public API | Existing 11 Greenhouse/Lever boards, verified Notion Ashby board, verified Bosch Group SmartRecruiters board, Jobicy, Remotive, Arbeitnow | Bounded public requests; working and retired boards are distinguished by actual health results |
| Public feed | Two Brabble feeds, five DEV tag feeds, two HN feeds, Himalayas, InternScan | RSS/Atom discovery with source attribution; invalid feeds are reported, not counted as empty successful scans |
| Authorized page parser | None | No HTML parser is represented as connected |
| Search only | Existing 20 portals plus Devfolio, MLH, Devpost, GSoC, Outreachy, GitHub Education, Google Research, Microsoft Research, NSP, DAAD | Links for owner research; no automated coverage claim |
| Requires credentials | Recruitee, Workday, Oracle Recruiting, SAP SuccessFactors | No account or undocumented private API scraping |
| Unsupported here | Personio XML | No employer-authorized feed configured; not scanned |

The new board identifiers are grounded in [Notion's official careers page](https://www.notion.com/careers) and [Bosch's published SmartRecruiters India page](https://careers.smartrecruiters.com/BoschGroup/india). Retired legacy board configurations remain visible as degraded sources so their saved records survive. Large Greenhouse boards use a compact index followed by at most 40 relevant descriptions. Lever pagination is bounded to 500 records; SmartRecruiters to 500. Truncated windows cannot prove closure. Rolling job feeds and RSS cannot prove closure either.

Sources refresh no more often than every eight hours after success, with conditional HTTP headers when supported, timeouts, response caps, atomic leases, and exponential failure cooldown (up to a day). Rate-limit responses honor Retry-After. Three failures put a source into cooldown. Cached data loads before background work. Only two successful **complete** employer listings that omit a previously seen role can mark its source evidence closed. An outage never closes a role. Original first-discovery dates, notes, checklists, and stages survive synchronization.

On a sleeping free Render instance, background code does not run. Opening the app queues due work while it is awake; there is no always-on scheduler or newly provisioned paid resource. A fresh scan is neither a guarantee that every public vacancy was retrieved nor proof that an employer is accepting applications at that instant.

Adapter documentation: [Greenhouse](https://developers.greenhouse.io/job-board.html), [Lever](https://github.com/lever/postings-api), [Ashby](https://developers.ashbyhq.com/docs/public-job-posting-api), [SmartRecruiters](https://developers.smartrecruiters.com/reference/v1listpostings). Recruitee documents a careers-token requirement; it is explicitly not advertised as a working anonymous connector.

## Eligibility and workflow

Eligibility is evaluated separately from relevance: eligible, likely eligible, unknown, specific conflict, or closed/expired. Rules inspect graduation requirements, seniority, required experience, postgraduate-only roles, geography, remote-region restrictions, citizenship/work authorization, and recorded deadlines. A Summer 2027 season is not automatically a 2027 graduation requirement. Company boilerplate about India does not establish a role's location. Unknown relocation or payroll eligibility remains a verification step. Availability and degree ambiguity still require human review; the engine is not a complete legal or employer eligibility determination.

Priority points explain skill overlap, location preference, early-career signals, first discovery, eligibility, and disclosed pay. Points are not an acceptance probability. Hard conflicts stay below opportunities worth researching even when skills match. Owner corrections retain the original requirements and evidence. Canonical URL and employer identifier matches group duplicates conservatively; owner duplicate links are reversible and retain original records.

Each opportunity has an independently editable 19-step preparation template, optional custom items, notes, source evidence, and audit history. Stages: Discovered, Saved, Researching, Preparing, Ready to Apply, Applied, Assessment, Interview, Offer, Rejected, Withdrawn, Closed. Additional states: Waiting for Reply, Follow-up Due, On Hold. Opening an application page and completing the checklist do not mark a submission. Changing to Applied requires explicit confirmation of actual owner submission. Owner reports are labelled separately from existing employer-API-confirmed receipts.

## Calendar

Day, week, month, and agenda views display Asia/Kolkata dates. Original timestamp offsets and source zones remain recorded. A date-only deadline has no fabricated 23:59 cutoff. Owner events include reminders, assessments, interviews, application or registration deadlines, and follow-ups. ICS exports preserve exact instants, export unknown cutoffs as all-day dates, and include requested reminders. The receiving calendar handles imported alarms; this app does not send background notifications while asleep. Google Calendar OAuth synchronization is not connected.

## Inbox and intelligence

New Gmail connections verify identity through Google's profile endpoint and store independently encrypted tokens by mailbox. Reconnecting one account preserves its own refresh token. Existing single-account credentials remain available. Old ledger records without recorded account identity are labelled historical; they are not silently assigned to another mailbox. Gmail links identify the verified account. A bounded read-only scan covers relevant messages from the past 120 days, including Spam, excluding Trash, up to 120 messages. Metadata and attachment filenames/types/sizes are retained; message bodies and attachment bytes are not downloaded by the new scanner.

Sent and draft copies are outbound activity, never vacancies or recruiter replies. Provisional categories include delivery failure, out of office, acknowledgement, interview, assessment, offer, rejection, newsletter, possible human reply, and needs review. Human reply classification requires an exact recipient or thread match **within the same account**, with automatic notices excluded. Classification never changes an application stage. Added accounts are read-only; single reviewed sending remains in the original connection's existing tool, with its confirmation, duplicate guard, and daily limit. No email or external application is sent by development, synchronization, or intelligence.

Opportunity Intelligence runs locally with deterministic rules and recorded sources: prioritization, comparison, company summaries, skill gaps, preparation suggestions, professional draft scaffolds, and stored mail-signal summaries. It cites original records. It uses no paid or external language model and does not claim unrestricted generative reasoning. Company summaries are extractive; undisclosed size, industry, or headquarters remain unknown.

Explicit opportunity feedback is stored separately. An optional small logistic model uses seven numeric relevance features only after at least 40 distinct opportunities, including at least 8 positive and 8 negative labels. A deterministic held-out split compares Brier loss with the rules baseline. Evaluation never activates the candidate. Explicit activation requires a measured improvement; rollback restores rules. No Gmail content, contact information, resume text, document bytes, or inferred personal attributes enter this training process. With insufficient feedback, the rules remain fully usable.

## Security, exports, and operational limits

All private APIs require the owner session. Version 3 mutations additionally require a session CSRF token and validate origin. Dynamic text is escaped, source links use HTTPS with no embedded credentials, public adapters use fixed hosts and validated slugs, redirects are not followed, private IP URLs are rejected, and exported CSV cells are protected against formula injection. Gmail tokens continue to use the existing encryption key. No credentials are committed.

Private CSV/JSON exports include opportunity records, notes, checklist items, history, calendar events, feedback, receipts, and duplicate links. They exclude OAuth tokens, contacts, private document bytes, and mail bodies. JSON workspace exports are distinct from the older v1 backup/restore format; the original restore tool does not accept a v3 workspace export. Analytics shows current record totals and explicit history limitations, not fabricated funnel conversion rates.

Known practical limits: public sources are incomplete; some configured boards have retired or feeds return non-XML content; source freshness depends on the service being awake; the source registry does not implement every ATS in the brief; additional mailboxes are read-only; the assistant supplies grounded templates rather than an external generative model; existing advanced tools retain their original interface; calendar synchronization requires a separate future authorized integration. These are labelled in the UI and are not advertised as completed connectors.

## Implementation log and verification

1. Audited the actual hosted branch and matching live deployment at `4d7de186a7ad87c069c08fae5d0e9b58dd0ca854`; baseline 57 tests passed.
2. Added isolated, additive storage; eligibility and source provenance; bounded source adapters and health; persistent checklists, explicit receipts, calendar exports, feedback evaluation, and account-scoped mail.
3. Implemented the six-view responsive workspace and retained original private tools under `/classic`.
4. Live public-source probes populated an isolated local database with real records. Both previously oversized Greenhouse boards passed the revised compact-index adapter (3 Cloudflare and 8 Databricks matching roles at verification time). Source-health evidence records failures as failures, not coverage.
5. Automated suite: 94 tests passed locally. Browser checks exercised search, saved preparation, checkbox persistence, calendar views, both themes, and widths 360/390/768/1366/1920. No email/application send was performed. GitHub CI and exact live deploy verification are recorded in the delivery report after release.

Run checks with `python -m pytest -q tests` and `node --check static/workspace.js`. On constrained Windows workspaces, use a unique writable `--basetemp=.qa/<run-name>`. Deploy the tested branch to the existing Render service, wait for a live status, and verify `/health`, public/private access boundaries, the authenticated workspace, and shipped asset hashes.


## Follow-up UX milestone: readable decisions and direct actions
The original version 3 card markup was hard to scan because of very small text and hidden next steps. Cards now show a concise source-derived summary, eligibility reason, location, work mode, disclosed/unknown compensation, official deadline vs unknown cutoff, and attribution with larger accessible typography. Every card offers **Details**, a **Checklist** shortcut (without automatically changing its stage), and a direct **Open source** link that never records an application as submitted. Source links remain clearly labelled instead of falsely asserting all listings are official employer application forms. Mobile actions form a simple two-row grid. Existing application checklists, stages, emails and records are not migrated or modified by this UI change.


## October 24: application priorities and less cluttered discovery
The Discover page now shows four essential selectors by default (type, eligibility, next action and location), with the six detailed search facets in an accessible native Advanced filters expander. Server-side filters accept exactly the existing rules-engine action buckets. Opportunity cards display a transparent next-action label and suggested review date, explicitly **not** an official employer deadline. The Today view shows actionable "Apply today / Deadline approaching" opportunities first when any exist, then verified/largely eligible opportunities. It does not recommend already-applied stages as new applications. The previously connected private data tables and their contents are untouched.

The Discover list now excludes previously submitted or terminal-stage applications by default. These records remain visible under Applications and can still be retrieved by explicit priority/status filters. This prevents misleading duplicate calls to apply to a role that already has recorded submission evidence.


## Verified employer source expansion
The configured direct employer-board registry adds six India-relevant published boards: [Merkle Science](https://jobs.lever.co/merklescience) (backend engineering internship, Bengaluru), [Hevo Data](https://jobs.lever.co/hevodata) (SDE internship, Bengaluru), [Interview Kickstart](https://jobs.ashbyhq.com/interview-kickstart) (remote India software/backend internships), [AiStudio](https://jobs.ashbyhq.com/aistudio) (remote India forward-deployed engineering internship), [Outmarket AI](https://jobs.ashbyhq.com/outmarket) (remote India AI software internship listing), and [Emergence Software](https://jobs.ashbyhq.com/emergence) (remote software development internship). These are employer-published listing boards, not a claim that any specific job remains open or accepts a 2028 graduate. They are crawled with the existing fixed-host, bounded Greenhouse/Lever/Ashby adapters and acquire a verified success/failure status only after a live sync. Initial API registry configuration counts increase by six (from 16 to 22, assuming no owner custom additions); active coverage must be read from source health, not these counts.


### Remote job RSS adapter
Two additional permitted public feeds are monitored: [We Work Remotely – Programming](https://weworkremotely.com/categories/remote-programming-jobs.rss) and [DevOps/System Administration](https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss). The publisher [explicitly authorizes public RSS consumption](https://weworkremotely.com/remote-job-rss-feed) with link attribution. The feed adapter only retains early-career technical leads with valid HTTPS source links; remote work eligibility for India remains unverified until read from the employer. These feeds add two **configured** sources, not guaranteed available jobs. Failure, caching, and retry use the existing safe sync system.

### More global discovery directories (manual/search-only)
Twenty-one additional official destinations are included under Source Health: Hack2Skill, HackerEarth challenges, Kaggle competitions, Hugging Face, DoraHacks, ETHGlobal, WeMakeDevs, TAIKAI, CTFtime, MLH Fellowship, LFX Mentorship, Startup India, Product Hunt, GDG, AWS events, Microsoft Reactor, CNCF events, Luma, Meetup, Eventbrite, and IEEE conferences. They are clearly **Search only / not automatically scanned**. Users open the real publisher page and save suitable opportunities with source attribution; unsupported unofficial scraping is not claimed.

### Refresh feedback
After a refresh is queued, the workspace polls its read-only source-health endpoint for up to three minutes. It reports completion and the number of degraded/cooldown sources, then refreshes the visible Today/Discover/Saved/Applications view if no form or dialog is open. This does not bypass source cooldowns or guarantee a fixed number of jobs. On a sleeping Render free-tier instance, refreshes still require a visit or some authorized wake-up; no always-on scheduler is claimed.


### SmartRecruiters eligibility enrichment
The public SmartRecruiters Posting API documents `GET /v1/companies/{companyIdentifier}/postings/{postingId}`. After retrieving up to 500 index records, the connector now fetches detailed sections for **at most 25 relevant early-career engineering titles**, preferring Indian locations. It extracts employer job descriptions, qualifications, and company summaries, retaining the original posting URL. If details are unavailable or a schema mismatch occurs, the source reports a degraded/error state rather than manufacturing eligibility. Full-page extraction of all hundreds of postings is deliberately avoided. Source: https://developers.smartrecruiters.com/reference/v1getposting .
