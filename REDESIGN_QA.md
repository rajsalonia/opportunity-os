# Opportunity OS redesign verification

Verified locally on 23 October 2026. Work is confined to `opportunity-os-hosted`.

## Automated checks
- `python -m pytest -q tests`: **17 passed**.
- `node --check static/app.js`: passed.
- `git diff --check`: passed.
- Existing hosted tests are retained, with a portable isolated test database path. CI now checks JavaScript syntax and the full Python test suite.

Behavioral coverage includes private HTML and API authentication, login/logout, cross-origin mutation rejection, all nine exact application stages, notes/deadline persistence and validation, API text/stage search, CSV formula protection, backup/restore, private upload gates, CSV and XLSX contact imports with duplicate skipping, original PDF bytes and SHA-256 verification, replacement refusal, Gmail explicit review and duplicate sending gates, recorded sent history, reply classification and timestamps, source configuration/removal, refresh preserving pipeline state, readable employer descriptions, and sanitized connection failures.

Private-file and Gmail-send tests use synthetic fixtures with external sending mocked. They do not access the owner's original PDF or send actual email. PostgreSQL-specific connection settings are implemented; local database tests run on SQLite, not a separately provisioned Supabase project.

## Browser verification
- All eight sections inspected at **360, 390, 768, 1366, and 1920px** viewport widths. Each displayed exactly one active section and no horizontal page overflow. The desktop board scrolls within its own container; mobile uses a vertical list and hides empty stage columns.
- Password sign-in, navigation, mobile sidebar, active section, drawer, source-description text, search, combined filters, empty results, reset, company sort, progressive results (24 then 48), save, stage/notes editing, draft generation/editing, and review-checkbox reset checked through Chrome.
- A manual opportunity form was submitted using an explicitly synthetic local-only fixture. No fixture is included in tracked source or production data.
- A real refresh against the configured employer boards returned **54 listings** in the isolated local workspace. Listings outside India remain labeled with their actual locations and unverified eligibility.
- Empty and configured/unconfigured integration screens use real backend responses. Private storage controls and Gmail sends are disabled when unavailable.
- Contrast inspection prompted darker primary buttons (white text exceeds 4.5:1 across the normal gradient) and readable secondary text. Keyboard focus, native dialog semantics, reduced-motion styling, mobile focus containment, Escape, and the skip link are implemented. This is focused QA, not a third-party accessibility certification.
- A mobile-menu focus bug discovered from Settings and an existing sent-history row mapping bug were fixed. A fresh browser tab reported no console errors/warnings during the subsequent verification.

## Scope and release limits
- No profile README, portfolio files, default branch, real resume file, database credentials, OAuth tokens, or unrelated service configuration changed.
- No database deletion or data migration. Existing `DATABASE_URL`, Flask authentication, and Render service URL remain in use.
- Google OAuth configuration and user authorization remain prerequisites for real Gmail access. Original-PDF upload requires connected PostgreSQL and user selection of the original file.
- Discovery imports public employer listings only; no automatic ATS submissions or unattended email sending are implemented.
- Live deployment checks are reported separately after the tested commit is pushed.
