/**
 * Opportunity OS - AI Outreach Manager Frontend
 * Interactive Spreadsheet Ingestion, Candidate CRM, Grounded AI Composer,
 * Safe 10/day Gmail Outreach, and Smart Follow-ups.
 */

window.outreachState = {
  selectedContacts: new Set(),
  activeTab: 'contacts',
  searchQuery: '',
  statusFilter: '',
  uploadedFiles: [],
  previews: [],
  selectedStyle: 'professional',
  selectedCategory: ''
};

window.renderOutreach = async function(ticket) {
  const oState = window.outreachState;
  const currentTab = state.outreachTab || oState.activeTab || 'contacts';
  oState.activeTab = currentTab;

  let analytics = null;
  try {
    analytics = await api('/api/outreach/analytics');
  } catch (e) {
    // Analytics fallback if loading
  }
  if (ticket !== state.request) return;

  const tabs = [
    ['contacts', 'Candidate Directory'],
    ['import', 'Import Spreadsheets'],
    ['drafts', 'AI Email Composer'],
    ['followups', 'Smart Follow-ups'],
    ['suppression', 'Suppression & Profile']
  ];

  const kpisHtml = analytics ? `
    <div class="stat-grid" style="grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); margin-bottom: 20px;">
      <div class="stat-block">
        <span class="muted small-text">Total Contacts</span>
        <strong style="font-size:24px;display:block;margin:4px 0">${analytics.contacts.total}</strong>
        <small class="muted">${analytics.contacts.valid} verified · ${analytics.contacts.duplicates} merged</small>
      </div>
      <div class="stat-block">
        <span class="muted small-text">AI Drafts</span>
        <strong style="font-size:24px;display:block;margin:4px 0">${analytics.drafts.total}</strong>
        <small class="muted">${analytics.drafts.approved} approved for sending</small>
      </div>
      <div class="stat-block">
        <span class="muted small-text">Daily Safe Sends</span>
        <strong style="font-size:24px;display:block;margin:4px 0; color: var(--accent);">${analytics.outreach.sends_today} / ${analytics.outreach.daily_limit}</strong>
        <small class="muted">${analytics.outreach.remaining_today} remaining today (domain health safe)</small>
      </div>
      <div class="stat-block">
        <span class="muted small-text">Outreach Sent</span>
        <strong style="font-size:24px;display:block;margin:4px 0">${analytics.outreach.total_sent}</strong>
        <small class="muted">${analytics.outreach.replies} replies (${analytics.outreach.response_rate_pct}% response)</small>
      </div>
      <div class="stat-block">
        <span class="muted small-text">Day 7 Cadence</span>
        <strong style="font-size:24px;display:block;margin:4px 0">${analytics.outreach.pending_followups}</strong>
        <small class="muted">Pending follow-up reminders</small>
      </div>
    </div>
  ` : '';

  $('#content').innerHTML = heading(
    'Opportunity OS · AI Outreach Manager',
    'Recruiter CRM & AI Outreach',
    'Multi-spreadsheet candidate ingestion, grounded AI email composition, 10/day safe Gmail delivery, and Day 7 follow-up cadence.',
    `<div style="display:flex;gap:10px;">
      <a href="/api/outreach/export" class="button optional">${icon('download')} Export Contacts CSV</a>
      <button class="button primary" data-action="quick-import">${icon('plus')} Import Spreadsheets</button>
    </div>`
  ) + kpisHtml + `
    <div class="tabs" aria-label="Outreach sections">
      ${tabs.map(([id, label]) => `<button class="${id === currentTab ? 'active' : ''}" data-outreach-tab="${id}">${label}</button>`).join('')}
    </div>
    <div id="outreach-subcontent" class="loading-state" role="status">Loading ${currentTab}…</div>
  `;

  const host = $('#outreach-subcontent');
  if (currentTab === 'import') {
    await renderOutreachImport(host, ticket);
  } else if (currentTab === 'drafts') {
    await renderOutreachDrafts(host, ticket);
  } else if (currentTab === 'followups') {
    await renderOutreachFollowups(host, ticket);
  } else if (currentTab === 'suppression') {
    await renderOutreachSuppression(host, ticket);
  } else {
    await renderOutreachContacts(host, ticket);
  }
};

async function renderOutreachContacts(host, ticket) {
  const oState = window.outreachState;
  const params = new URLSearchParams();
  if (oState.searchQuery) params.set('q', oState.searchQuery);
  if (oState.statusFilter) params.set('email_status', oState.statusFilter);
  params.set('limit', '100');

  let data = { contacts: [], total: 0 };
  try {
    data = await api('/api/outreach/contacts?' + params.toString());
  } catch (e) {
    host.innerHTML = `<div class="notice warning">Could not load contacts: ${esc(e.message)}</div>`;
    return;
  }
  if (ticket !== state.request) return;

  const rows = data.contacts;
  host.className = '';
  host.innerHTML = `
    <div class="outreach-toolbar" style="display:flex;flex-wrap:wrap;gap:12px;margin-bottom:18px;align-items:center;justify-content:space-between;">
      <div style="display:flex;gap:10px;flex:1;max-width:540px;">
        <input type="search" id="outreach-search-input" placeholder="Search company, recruiter name, email, designation…" value="${esc(oState.searchQuery)}" style="flex:1;padding:8px 12px;border:1px solid var(--line);border-radius:8px;background:var(--surface);">
        <select id="outreach-status-filter" style="padding:8px 12px;border:1px solid var(--line);border-radius:8px;background:var(--surface);">
          <option value="">All statuses</option>
          <option value="valid" ${oState.statusFilter==='valid'?'selected':''}>Verified valid</option>
          <option value="role_based" ${oState.statusFilter==='role_based'?'selected':''}>Role-based</option>
          <option value="malformed" ${oState.statusFilter==='malformed'?'selected':''}>Malformed syntax</option>
          <option value="missing" ${oState.statusFilter==='missing'?'selected':''}>Missing email</option>
        </select>
      </div>
      <div style="display:flex;gap:10px;align-items:center;">
        <span class="muted small-text" id="selected-counter">${oState.selectedContacts.size} selected</span>
        <button class="button primary" data-action="compose-batch" ${oState.selectedContacts.size===0?'disabled':''}>
          ${icon('sparkles')} Compose with AI
        </button>
      </div>
    </div>

    ${rows.length === 0 ? `
      <div class="empty-state">
        ${icon('inbox')}
        <h3>No contacts found</h3>
        <p>Import your Excel (.xlsx, .xls) or CSV spreadsheets to populate your candidate directory.</p>
        <button class="button primary" data-action="quick-import">${icon('plus')} Import Spreadsheets</button>
      </div>
    ` : `
      <div style="overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--surface);">
        <table class="outreach-table" style="width:100%;border-collapse:collapse;font-size:13px;">
          <thead>
            <tr style="border-bottom:1px solid var(--line);text-align:left;background:rgba(255,255,255,0.02);">
              <th style="padding:12px;width:36px;"><input type="checkbox" id="select-all-contacts"></th>
              <th style="padding:12px;">Company</th>
              <th style="padding:12px;">Contact Name</th>
              <th style="padding:12px;">Email & Syntax</th>
              <th style="padding:12px;">Designation</th>
              <th style="padding:12px;">Location</th>
              <th style="padding:12px;">Outreach Status</th>
              <th style="padding:12px;text-align:right;">Actions</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map(c => `
              <tr style="border-bottom:1px solid var(--line);" data-contact-id="${esc(c.id)}">
                <td style="padding:12px;"><input type="checkbox" class="contact-checkbox" data-id="${esc(c.id)}" ${oState.selectedContacts.has(c.id)?'checked':''}></td>
                <td style="padding:12px;"><strong>${esc(c.company_name)}</strong></td>
                <td style="padding:12px;">${esc(c.name || 'Hiring Team')}</td>
                <td style="padding:12px;">
                  <div>${esc(c.email)}</div>
                  <span class="tag ${c.email_status==='valid'?'success':c.email_status==='role_based'?'warning':'danger'}" style="font-size:10px;padding:2px 6px;">
                    ${esc(c.email_status)}
                  </span>
                  ${c.is_duplicate ? '<span class="tag" style="font-size:10px;padding:2px 6px;">Merged Dupe</span>' : ''}
                </td>
                <td style="padding:12px;">${esc(c.designation || 'Recruiter / HR')}</td>
                <td style="padding:12px;">${esc(c.location || '—')}</td>
                <td style="padding:12px;">
                  <span class="tag ${c.outreach_status==='contacted'?'success':c.outreach_status==='opted_out'?'danger':''}">
                    ${esc(c.outreach_status.replace('_', ' '))}
                  </span>
                  ${c.last_contacted_at ? `<small class="muted" style="display:block;font-size:10px;">${fmt(c.last_contacted_at)}</small>` : ''}
                </td>
                <td style="padding:12px;text-align:right;">
                  <button class="icon-button" data-action="single-compose" data-id="${esc(c.id)}" title="Compose AI Email">${icon('sparkles')}</button>
                  ${c.linkedin_url ? `<a href="${esc(c.linkedin_url)}" target="_blank" rel="noopener" class="icon-button" title="LinkedIn Profile">${icon('external-link')}</a>` : ''}
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
      <div style="display:flex;justify-content:space-between;margin-top:14px;align-items:center;">
        <span class="muted small-text">Showing ${rows.length} of ${data.total} records</span>
      </div>
    `}
  `;

  // Attach search & filter handlers
  const searchInput = $('#outreach-search-input');
  if (searchInput) {
    let debounce;
    searchInput.addEventListener('input', e => {
      clearTimeout(debounce);
      debounce = setTimeout(() => {
        oState.searchQuery = e.target.value.trim();
        renderOutreachContacts(host, ticket);
      }, 300);
    });
  }

  const statusFilter = $('#outreach-status-filter');
  if (statusFilter) {
    statusFilter.addEventListener('change', e => {
      oState.statusFilter = e.target.value;
      renderOutreachContacts(host, ticket);
    });
  }

  // Checkbox handling
  const selectAll = $('#select-all-contacts');
  if (selectAll) {
    selectAll.addEventListener('change', e => {
      const checked = e.target.checked;
      $$('.contact-checkbox').forEach(cb => {
        cb.checked = checked;
        const cid = cb.dataset.id;
        if (checked) oState.selectedContacts.add(cid);
        else oState.selectedContacts.delete(cid);
      });
      updateSelectionCounter();
    });
  }

  $$('.contact-checkbox').forEach(cb => {
    cb.addEventListener('change', e => {
      const cid = e.target.dataset.id;
      if (e.target.checked) oState.selectedContacts.add(cid);
      else oState.selectedContacts.delete(cid);
      updateSelectionCounter();
    });
  });

  function updateSelectionCounter() {
    const counter = $('#selected-counter');
    const composeBtn = $('[data-action="compose-batch"]');
    if (counter) counter.textContent = `${oState.selectedContacts.size} selected`;
    if (composeBtn) composeBtn.disabled = oState.selectedContacts.size === 0;
  }
}

async function renderOutreachImport(host, ticket) {
  host.className = '';
  host.innerHTML = `
    <div class="settings-card" style="margin-bottom:20px;">
      <h3>Multi-Spreadsheet High-Capacity Ingestion</h3>
      <p>Upload Excel (.xlsx, .xls) and CSV spreadsheets. Supports multi-file batches (e.g. 6 files, ~500 contacts each, ~3,000 total records). Features automatic column mapping, company normalization, RFC 5322 syntax validation, and contact deduplication.</p>
      
      <div id="dropzone" style="border: 2px dashed var(--line); border-radius: 12px; padding: 40px; text-align: center; background: rgba(255,255,255,0.01); cursor: pointer; transition: border-color 0.2s;">
        ${icon('upload', 'style="width:40px;height:40px;margin-bottom:12px;color:var(--accent);display:inline-block;"')}
        <h4 style="margin:0 0 8px;">Drag & Drop Spreadsheet Files Here</h4>
        <p class="muted small-text" style="margin:0 0 16px;">Supports .xlsx, .xls, and .csv files. Multiple files can be selected simultaneously.</p>
        <input type="file" id="outreach-file-selector" multiple accept=".xlsx,.xls,.csv" style="display:none;">
        <button class="button primary" id="btn-select-files" type="button">Choose Files from Device</button>
      </div>

      <div id="import-preview-container" style="margin-top:24px;display:none;"></div>
    </div>
  `;

  const dropzone = $('#dropzone');
  const fileSelector = $('#outreach-file-selector');
  const btnSelect = $('#btn-select-files');

  if (btnSelect && fileSelector) {
    btnSelect.addEventListener('click', () => fileSelector.click());
  }

  if (fileSelector) {
    fileSelector.addEventListener('change', async (e) => {
      const files = Array.from(e.target.files);
      if (files.length > 0) {
        await handleFilesForPreview(files);
      }
    });
  }

  if (dropzone) {
    dropzone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropzone.style.borderColor = 'var(--accent)';
    });
    dropzone.addEventListener('dragleave', () => {
      dropzone.style.borderColor = 'var(--line)';
    });
    dropzone.addEventListener('drop', async (e) => {
      e.preventDefault();
      dropzone.style.borderColor = 'var(--line)';
      const files = Array.from(e.dataTransfer.files).filter(f => /\.(xlsx|xls|csv)$/i.test(f.name));
      if (files.length > 0) {
        await handleFilesForPreview(files);
      } else {
        toast('Please upload valid .xlsx, .xls, or .csv spreadsheets.');
      }
    });
  }

  async function handleFilesForPreview(files) {
    const container = $('#import-preview-container');
    container.style.display = 'block';
    container.innerHTML = '<div class="loading-state">Analyzing spreadsheet schemas and column mappings…</div>';

    const formData = new FormData();
    files.forEach(f => formData.append('files', f));

    try {
      const res = await fetch('/api/outreach/import/preview', {
        method: 'POST',
        headers: { 'X-CSRF-Token': $('meta[name=csrf-token]').content },
        body: formData
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Preview failed');

      window.outreachState.uploadedFiles = files;
      window.outreachState.previews = data.previews;

      renderPreviewResults(container, files, data.previews);
    } catch (err) {
      container.innerHTML = `<div class="notice danger">Failed to preview spreadsheets: ${esc(err.message)}</div>`;
    }
  }

  function renderPreviewResults(container, files, previews) {
    container.innerHTML = `
      <div style="border-top: 1px solid var(--line); padding-top: 20px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
          <div>
            <h4 style="margin:0;">Files Detected (${files.length})</h4>
            <p class="muted small-text" style="margin:4px 0 0;">Inspect auto-detected column mappings and sample data below before importing.</p>
          </div>
          <button class="button primary" id="btn-execute-import" type="button">
            ${icon('check')} Ingest All & Deduplicate (${previews.reduce((acc, p) => acc + (p.total_rows || 0), 0)} Total Rows)
          </button>
        </div>

        ${previews.map((p, idx) => `
          <div style="border: 1px solid var(--line); border-radius: 8px; padding: 16px; margin-bottom: 16px; background: rgba(0,0,0,0.1);">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
              <strong>${esc(p.filename)}</strong>
              <span class="tag success">${p.total_rows || 0} rows found</span>
            </div>
            ${p.error ? `<div class="notice danger">${esc(p.error)}</div>` : `
              <div style="font-size:12px;margin-bottom:10px;">
                <span class="muted">Detected Mappings:</span>
                <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:6px;">
                  ${Object.entries(p.detected_mapping || {}).map(([std, raw]) => `
                    <span class="tag" style="font-size:11px;">${esc(std)} ➔ <strong>${esc(raw)}</strong></span>
                  `).join('')}
                </div>
              </div>
            `}
          </div>
        `).join('')}
      </div>
    `;

    const execBtn = $('#btn-execute-import');
    if (execBtn) {
      execBtn.addEventListener('click', async () => {
        execBtn.disabled = true;
        execBtn.innerHTML = '<span class="loading-state" style="padding:0;min-height:auto;">Ingesting records…</span>';
        
        const form = new FormData();
        window.outreachState.uploadedFiles.forEach(f => form.append('files', f));

        try {
          const res = await fetch('/api/outreach/import', {
            method: 'POST',
            headers: { 'X-CSRF-Token': $('meta[name=csrf-token]').content },
            body: form
          });
          const resData = await res.json();
          if (!res.ok) throw new Error(resData.error || 'Import failed');

          toast('Spreadsheets successfully ingested and deduplicated!');
          state.outreachTab = 'contacts';
          location.hash = 'outreach/contacts';
          await route();
        } catch (e) {
          container.innerHTML = `<div class="notice danger">Import error: ${esc(e.message)}</div>`;
        }
      });
    }
  }
}

async function renderOutreachDrafts(host, ticket) {
  let drafts = [];
  try {
    const data = await api('/api/outreach/drafts');
    drafts = data.drafts || [];
  } catch (e) {
    host.innerHTML = `<div class="notice warning">Could not load email drafts: ${esc(e.message)}</div>`;
    return;
  }
  if (ticket !== state.request) return;

  host.className = '';
  host.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;">
      <div>
        <h3 style="margin:0;">Personalized AI Email Composer</h3>
        <p class="muted small-text" style="margin:4px 0 0;">Zero hallucination guarantee. Strictly grounded in Raj Salonia's verified credentials. 100% editable fields.</p>
      </div>
      <div style="display:flex;gap:10px;">
        <span class="tag accent">${drafts.filter(d => d.status==='approved').length} Approved</span>
        <span class="tag success">${drafts.filter(d => d.status==='sent').length} Sent</span>
      </div>
    </div>

    ${drafts.length === 0 ? `
      <div class="empty-state">
        ${icon('mail')}
        <h3>No email drafts yet</h3>
        <p>Select contacts from the Candidate Directory and click "Compose with AI" to generate tailored messages.</p>
        <button class="button primary" data-action="go-directory">Go to Candidate Directory</button>
      </div>
    ` : `
      <div class="drafts-list" style="display:flex;flex-direction:column;gap:18px;">
        ${drafts.map(d => `
          <div class="settings-card draft-card" style="margin:0;padding:20px;" data-draft-id="${esc(d.id)}">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;border-bottom:1px solid var(--line);padding-bottom:10px;">
              <div>
                <strong>${esc(d.contact_name || 'Contact')}</strong> · <span class="muted">${esc(d.company_name)}</span>
                <small class="muted" style="display:block;">${esc(d.contact_email)}</small>
              </div>
              <div style="display:flex;gap:8px;align-items:center;">
                <span class="tag" style="font-size:11px;">${esc(d.personalization_type)}</span>
                <span class="tag" style="font-size:11px;">${esc(d.style)}</span>
                <span class="tag ${d.status==='sent'?'success':d.status==='approved'?'accent':'warning'}">
                  ${esc(d.status.toUpperCase())}
                </span>
              </div>
            </div>

            <div style="margin-bottom:12px;">
              <label style="display:block;font-size:11px;color:var(--muted);margin-bottom:4px;">Subject</label>
              <input type="text" class="draft-subject-input" value="${esc(d.subject)}" style="width:100%;padding:8px 12px;border:1px solid var(--line);border-radius:6px;background:var(--surface);" ${d.status==='sent'?'disabled':''}>
            </div>

            <div style="margin-bottom:14px;">
              <label style="display:block;font-size:11px;color:var(--muted);margin-bottom:4px;">Body</label>
              <textarea class="draft-body-input" rows="8" style="width:100%;padding:10px 12px;border:1px solid var(--line);border-radius:6px;background:var(--surface);font-family:inherit;font-size:13px;line-height:1.5;" ${d.status==='sent'?'disabled':''}>${esc(d.body)}</textarea>
            </div>

            <div style="display:flex;justify-content:space-between;align-items:center;">
              <label style="display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer;">
                <input type="checkbox" class="draft-resume-toggle" ${d.attach_resume?'checked':''} ${d.status==='sent'?'disabled':''}>
                Attach verified original resume
              </label>

              <div style="display:flex;gap:10px;">
                ${d.status !== 'sent' ? `
                  <button class="button optional" data-action="save-draft" data-id="${esc(d.id)}">Save Changes</button>
                  ${d.status !== 'approved' ? `
                    <button class="button" data-action="approve-draft" data-id="${esc(d.id)}">${icon('check')} Approve Draft</button>
                  ` : ''}
                  <button class="button primary" data-action="send-draft" data-id="${esc(d.id)}" ${d.status!=='approved'?'disabled title="Must approve draft before sending"':''}>
                    ${icon('send')} Send via Gmail
                  </button>
                ` : `
                  <span class="tag success">${icon('check')} Delivered via Gmail</span>
                `}
              </div>
            </div>
          </div>
        `).join('')}
      </div>
    `}
  `;
}

async function renderOutreachFollowups(host, ticket) {
  let followups = [];
  try {
    const data = await api('/api/outreach/followups');
    followups = data.followups || [];
  } catch (e) {
    host.innerHTML = `<div class="notice warning">Could not load follow-ups: ${esc(e.message)}</div>`;
    return;
  }
  if (ticket !== state.request) return;

  host.className = '';
  host.innerHTML = `
    <div class="settings-card" style="margin-bottom:20px;">
      <h3>Smart Follow-up Cadence (Day 7 / Day 10)</h3>
      <p>Respectful, non-intrusive follow-up schedule. Follow-up rule: Maximum 1 follow-up permitted per contact. Never auto-sends without explicit user approval. Automatically suppressed if the recruiter has replied or opted out.</p>
    </div>

    ${followups.length === 0 ? `
      <div class="empty-state">
        ${icon('check-circle')}
        <h3>No pending follow-ups</h3>
        <p>Follow-up reminders are automatically scheduled 7 days after an outreach message is sent.</p>
      </div>
    ` : `
      <div style="display:flex;flex-direction:column;gap:14px;">
        ${followups.map(f => `
          <div class="settings-card" style="margin:0;padding:18px;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
              <div>
                <strong>${esc(f.contact_name || 'Contact')}</strong> (${esc(f.company_name)})
                <small class="muted" style="display:block;">${esc(f.contact_email)} · Scheduled target: <strong>${esc(f.scheduled_date)}</strong></small>
              </div>
              <div style="display:flex;gap:10px;">
                <button class="button optional" data-action="dismiss-followup" data-id="${esc(f.id)}">Dismiss Reminder</button>
                <button class="button primary" data-action="prepare-followup" data-id="${esc(f.id)}">${icon('sparkles')} Prepare Follow-up Draft</button>
              </div>
            </div>
          </div>
        `).join('')}
      </div>
    `}
  `;
}

async function renderOutreachSuppression(host, ticket) {
  let profile = {};
  let suppressions = [];
  try {
    profile = await api('/api/outreach/profile');
    const supData = await api('/api/outreach/suppressions');
    suppressions = supData.suppressions || [];
  } catch (e) {}
  if (ticket !== state.request) return;

  host.className = '';
  host.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
      <div class="settings-card">
        <h3>Verified Applicant Grounding</h3>
        <p>Opportunity OS strictly enforces that AI-composed emails only reference genuine, verified applicant credentials with zero hallucination.</p>
        
        <div style="font-size:13px;line-height:1.6;">
          <p><strong>Name:</strong> ${esc(profile.name || 'Raj Salonia')}</p>
          <p><strong>Degree:</strong> ${esc(profile.degree || 'B.Tech CSE')}</p>
          <p><strong>Institution:</strong> ${esc(profile.institution || 'BPIT (GGSIPU)')}</p>
          <p><strong>Class:</strong> ${esc(profile.graduation_year || '2028')} (Target: ${esc(profile.target_term || 'Summer 2027')})</p>
          <p><strong>Experience:</strong> Software Engineering Intern at Dexpert Systems</p>
          <p><strong>Verified Projects:</strong> CityGraph, Document Forgery AI, ReviewLens, AstroBit</p>
        </div>
      </div>

      <div class="settings-card">
        <h3>Suppression & Opt-Out List</h3>
        <p>Addresses on this list are permanently blocked from receiving outreach or follow-ups to preserve sender reputation.</p>

        <form id="add-suppression-form" style="display:flex;gap:10px;margin-bottom:18px;">
          <input type="email" name="email" required placeholder="recruiter@company.com" style="flex:1;padding:8px 12px;border:1px solid var(--line);border-radius:6px;background:var(--surface);">
          <button class="button primary" type="submit">Block Address</button>
        </form>

        <div style="max-height:220px;overflow-y:auto;border:1px solid var(--line);border-radius:6px;">
          <table style="width:100%;font-size:12px;border-collapse:collapse;">
            ${suppressions.map(s => `
              <tr style="border-bottom:1px solid var(--line);">
                <td style="padding:8px 12px;">${esc(s.email)}</td>
                <td style="padding:8px 12px;"><span class="tag danger">${esc(s.reason)}</span></td>
                <td style="padding:8px 12px;text-align:right;" class="muted">${fmt(s.created_at)}</td>
              </tr>
            `).join('')}
          </table>
        </div>
      </div>
    </div>
  `;

  const supForm = $('#add-suppression-form');
  if (supForm) {
    supForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const email = supForm.querySelector('[name=email]').value.trim();
      if (!email) return;
      try {
        await mutate('/api/outreach/suppressions', { email, reason: 'manual_block' });
        toast(`Added ${email} to suppression list`);
        await renderOutreachSuppression(host, ticket);
      } catch (err) {
        toast(`Error: ${err.message}`);
      }
    });
  }
}

// Global click delegation for Outreach UI actions
document.addEventListener('click', async (event) => {
  const el = event.target.closest('[data-action]');
  if (!el) return;
  const action = el.dataset.action;

  if (action === 'quick-import') {
    state.outreachTab = 'import';
    location.hash = 'outreach/import';
    await route();
  } else if (action === 'go-directory') {
    state.outreachTab = 'contacts';
    location.hash = 'outreach/contacts';
    await route();
  } else if (action === 'compose-batch') {
    const selectedIds = Array.from(window.outreachState.selectedContacts);
    if (selectedIds.length === 0) return;
    el.disabled = true;
    try {
      await mutate('/api/outreach/compose', {
        contact_ids: selectedIds,
        style: 'professional'
      });
      toast(`Generated personalized drafts for ${selectedIds.length} contacts!`);
      window.outreachState.selectedContacts.clear();
      state.outreachTab = 'drafts';
      location.hash = 'outreach/drafts';
      await route();
    } catch (e) {
      toast(`Composition error: ${e.message}`);
      el.disabled = false;
    }
  } else if (action === 'single-compose') {
    const cid = el.dataset.id;
    try {
      await mutate('/api/outreach/compose', { contact_ids: [cid], style: 'professional' });
      toast('Draft generated!');
      state.outreachTab = 'drafts';
      location.hash = 'outreach/drafts';
      await route();
    } catch (e) {
      toast(`Error: ${e.message}`);
    }
  } else if (action === 'save-draft') {
    const draftCard = el.closest('.draft-card');
    const did = el.dataset.id;
    const subject = draftCard.querySelector('.draft-subject-input').value;
    const body = draftCard.querySelector('.draft-body-input').value;
    const attach_resume = draftCard.querySelector('.draft-resume-toggle').checked ? 1 : 0;
    try {
      await mutate(`/api/outreach/drafts/${did}`, { subject, body, attach_resume }, 'PATCH');
      toast('Draft changes saved!');
    } catch (e) {
      toast(`Save error: ${e.message}`);
    }
  } else if (action === 'approve-draft') {
    const did = el.dataset.id;
    try {
      await mutate(`/api/outreach/drafts/${did}/approve`, {});
      toast('Draft approved! Ready for safe sending.');
      await route();
    } catch (e) {
      toast(`Approval error: ${e.message}`);
    }
  } else if (action === 'send-draft') {
    const did = el.dataset.id;
    const confirmed = window.confirm(
      'Send this personalized outreach message via Gmail?\n\n' +
      'Safety check: Daily sending is strictly limited to 10 emails/day to maintain domain health. ' +
      'A Day 7 follow-up reminder will automatically be scheduled.'
    );
    if (!confirmed) return;
    el.disabled = true;
    try {
      const res = await mutate(`/api/outreach/drafts/${did}/send`, { reviewed_and_confirmed: true });
      toast('Outreach message safely delivered via Gmail!');
      await route();
    } catch (e) {
      toast(`Sending failed: ${e.message}`);
      el.disabled = false;
    }
  } else if (action === 'prepare-followup') {
    const fid = el.dataset.id;
    try {
      await mutate(`/api/outreach/followups/${fid}/prepare`, {});
      toast('Follow-up draft prepared! Review in AI Composer.');
      state.outreachTab = 'drafts';
      location.hash = 'outreach/drafts';
      await route();
    } catch (e) {
      toast(`Error: ${e.message}`);
    }
  } else if (action === 'dismiss-followup') {
    const fid = el.dataset.id;
    try {
      await mutate(`/api/outreach/followups/${fid}/dismiss`, { reason: 'user_dismissed' });
      toast('Follow-up reminder dismissed.');
      await route();
    } catch (e) {
      toast(`Error: ${e.message}`);
    }
  }
});
