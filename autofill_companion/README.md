# Opportunity OS — Chrome Autofill Companion

A local-only Chrome extension that fills supported employer form fields using an authenticated Opportunity OS application pack.

## Install and use
1. From the GitHub branch, use Code → Download ZIP. Extract and locate the autofill_companion folder.
2. Open chrome://extensions in Chrome/Edge. Enable Developer Mode and choose Load unpacked → autofill_companion. It gets access to the active job tab only when you click Fill.
3. Sign in to Opportunity OS → My Applications. Complete and verify your encrypted contact, education and professional links profile.
4. Open any job detail or Auto-Apply Queue and download its Autofill pack JSON.
5. Download your original PDF resume from the Resume Vault to your own computer, unchanged.
6. Open the companion popup. Import the JSON (kept in extension-local storage). Choose your original PDF (used for the current click only).
7. Click Open official job listing, navigate to the application form, and click Fill current application form.
8. Verify every field, answer employer-specific questions yourself, and click Submit on the employer site. Record the employer receipt in Opportunity OS.

## Supported features and limitations
- Fields: legal name, email, phone, LinkedIn, GitHub, portfolio, college, degree, graduation year, city, country; CGPA/percentage only if explicitly entered and verified by the account owner.
- Uploads: attempts to attach the owner-selected PDF on standard file inputs named resume/CV. Some custom uploaders and cross-origin iframes will not work.
- Never auto-clicks Apply/Submit, bypasses CAPTCHA, guesses visa/citizenship/EEO answers, signs into sites, scrapes unrelated pages, or uses external servers. This does not imply an application was submitted.
- Separate employer-authorized submission automation remains in the app, currently restricted to supported Greenhouse Job Board API integrations.
- Do not commit imported JSON profiles or PDF resumes to GitHub; those contain private details.
- On a shared device click Delete locally saved profile.
- The extension uses only activeTab, scripting, and storage permissions. There are no always-on site permissions or tracking dependencies.
