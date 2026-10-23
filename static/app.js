'use strict';

(() => {
  const $ = selector => document.querySelector(selector);
  const $$ = selector => Array.from(document.querySelectorAll(selector));
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const paths = {
    grid:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    compass:'<circle cx="12" cy="12" r="9"/><path d="m16 8-2.5 5.5L8 16l2.5-5.5Z"/>',
    board:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16M15 4v16M6 8v4M12 8v7M18 8v3"/>',
    users:'<circle cx="9" cy="8" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 5a3 3 0 0 1 0 6M17 15a5 5 0 0 1 4 5"/>',
    mail:'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 6 9 7 9-7"/>',
    file:'<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8ZM14 2v6h6M8 13h8M8 17h5"/>',
    globe:'<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/>',
    settings:'<path d="m9 3-1 3-3 1-2 5 2 5 3 1 1 3h6l1-3 3-1 2-5-2-5-3-1-1-3Z"/><circle cx="12" cy="12" r="3"/>',
    search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
    refresh:'<path d="M20 7v5h-5M4 17v-5h5M6 6a8 8 0 0 1 13 3M18 18A8 8 0 0 1 5 15"/>',
    arrow:'<path d="M4 12h16m-6-6 6 6-6 6"/>',
    external:'<path d="M14 3h7v7m0-7L10 14M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5"/>',
    plus:'<path d="M12 5v14M5 12h14"/>', bookmark:'<path d="M6 4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v17l-6-4-6 4Z"/>',
    check:'<path d="m5 12 4 4L19 6"/>', clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    pin:'<path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/>',
    lock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/>',
    shield:'<path d="m12 2 9 4v6c0 6-9 10-9 10S3 18 3 12V6Z"/><path d="m8 12 3 3 5-6"/>',
    upload:'<path d="M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5"/>', download:'<path d="M12 3v13m-5-5 5 5 5-5M4 16v5h16v-5"/>',
    x:'<path d="m6 6 12 12M6 18 18 6"/>', menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',
    collapse:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16m7-11-3 3 3 3"/>',
    spark:'<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z"/>',
    trend:'<path d="m3 17 6-6 4 4 8-10m-7 0h7v7"/>', info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7v.1"/>',
    copy:'<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
    send:'<path d="m22 2-7 20-4-9-9-4Z M11 13 22 2"/>', logout:'<path d="M9 3H4v18h5M10 12h11m-5-5 5 5-5 5"/>'
  };
  const icon = name => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${paths[name] || paths.info}</svg>`;
  $$('[data-icon]').forEach(el => { el.innerHTML = icon(el.dataset.icon); });
  let toastTimer;
  function toast(message, error = false) {
    clearTimeout(toastTimer);
    $('#toast-region').innerHTML = `<div class="toast${error ? ' error' : ''}">${icon(error ? 'info' : 'check')}<span>${esc(message)}</span></div>`;
    toastTimer = setTimeout(() => { $('#toast-region').replaceChildren(); }, error ? 8500 : 5000);
  }
  function feedback(selector, message, error = false) {
    const node = $(selector);
    node.textContent = message;
    node.classList.toggle('error', error);
    node.classList.toggle('success', !error);
  }
  async function api(path, options = {}) {
    const headers = options.body instanceof FormData ? {} : {'Content-Type':'application/json'};
    let response;
    try { response = await fetch(path, {...options, headers:{...headers, ...options.headers}, credentials:'same-origin'}); }
    catch { throw Error('Unable to reach the server. Check your connection and try again.'); }
    if (response.status === 401 && !path.endsWith('/login')) {
      // Reload removes private data and drafts from the DOM when a session expires.
      window.location.replace('/');
      throw Error('Your session expired. Please sign in again.');
    }
    let data;
    try { data = await response.json(); }
    catch { throw Error(`The server could not complete this request (${response.status}). Please retry.`); }
    if (!response.ok) throw Error(data.error || data.message || `Request failed (${response.status}).`);
    return data;
  }
  const post = (path, data = {}) => api(path, {method:'POST', body:JSON.stringify(data)});
  async function upload(path, file) {
    if (!file) throw Error('Select a file first.');
    const form = new FormData(); form.append('file', file);
    return api(path, {method:'POST', body:form});
  }
  async function busy(button, work, label) {
    const original = button.innerHTML;
    button.disabled = true; button.setAttribute('aria-busy', 'true');
    if (label) button.textContent = label;
    try { return await work(); }
    finally { button.innerHTML = original; button.disabled = false; button.removeAttribute('aria-busy'); }
  }
  if ($('#login-form')) {
    $('#login-form').addEventListener('submit', async event => {
      event.preventDefault();
      await busy(event.submitter, async () => {
        try { await post('/api/login', {password:$('#password').value}); $('#password').value = ''; window.location.replace('/'); }
        catch (error) { feedback('#auth-error', error.message, true); }
      }, 'Opening your workspace…');
    });
    return;
  }

  const STAGES = ['Discovered','Saved','Draft ready','Applied','Assessment','Interview','Offer','Rejected','Closed'];
  const PAGE_TITLES = {overview:'Overview',radar:'Opportunity Radar',explore:'Explore opportunities',applications:'My applications',contacts:'Recruiter CRM',gmail:'Gmail & outreach',resume:'Resume vault',sources:'Career sources',settings:'Settings & integrations'};
  const state = {jobs:null,radar:null,radarCategory:'all',radarLimit:48,radarScanning:false,mailActivity:null,discoveryState:null,discoveryChecking:false,summary:null,alerts:null,contacts:null,caps:null,sources:null,sent:null,messages:null,gmailOutbox:null,page:'overview',limit:24,view:'board',refreshing:false};
  const options = (selected, stages = STAGES) => stages.map(stage => `<option${stage === selected ? ' selected' : ''}>${esc(stage)}</option>`).join('');
  $('#stage-filter').insertAdjacentHTML('beforeend', options(''));
  $('#application-stage').insertAdjacentHTML('beforeend', options('',STAGES.slice(1)));
  $('#detail-stage').innerHTML = options('Saved');
  const safeUrl = value => {
    try { const url = new URL(value); return url.protocol === 'https:' && !url.username && !url.password ? url.href : ''; }
    catch { return ''; }
  };
  const officialLink = (job, className = 'button', label = 'Official listing') => {
    const url = safeUrl(job.url);
    return url ? `<a class="${className}" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)} ${icon('external')}</a>` : '';
  };
  const score = job => Math.min(100,Math.max(0,Number(job.score) || 0));
  function avatar(company) {
    const name = String(company || '?');
    const initials = name.trim().split(/\s+/).slice(0,2).map(word => Array.from(word)[0] || '').join('').toUpperCase();
    const tone = Array.from(name).reduce((sum,char) => sum + char.codePointAt(0),0) % 5;
    return `<span class="company-avatar tone-${tone}" aria-hidden="true">${esc(initials)}</span>`;
  }
  const shortDate = value => {
    if (!value) return 'Not recorded';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? 'Not recorded' : new Intl.DateTimeFormat('en-IN',{day:'numeric',month:'short',year:'numeric',timeZone:'Asia/Kolkata'}).format(date);
  };
  const shortTime = value => {
    const date = new Date(value);
    return !value || Number.isNaN(date.getTime()) ? 'Not yet checked' : new Intl.DateTimeFormat('en-IN',{day:'numeric',month:'short',hour:'numeric',minute:'2-digit',timeZone:'Asia/Kolkata'}).format(date) + ' IST';
  };
  const dateOnly = value => /^\d{4}-\d{2}-\d{2}$/.test(String(value || '').slice(0,10)) ? String(value).slice(0,10) : '';
  const empty = (title, description, name = 'compass', action = '', compact = false) => `<div class="empty-state${compact ? ' compact-empty' : ''}"><span class="empty-icon">${icon(name)}</span><h3>${esc(title)}</h3><p>${esc(description)}</p>${action}</div>`;
  const detailsButton = (job, label = job.title, className = 'job-title-button') => `<button class="${className}" data-action="details" data-id="${esc(job.id)}">${esc(label)}</button>`;
  function go(page) {
    if (window.location.hash.slice(1) === page) navigate(true);
    else window.location.hash = page;
  }
  function closeNav() {
    $('#workspace').classList.remove('nav-open'); $('#sidebar-backdrop').hidden = true;
    $('#mobile-menu').setAttribute('aria-expanded','false');
    $('#sidebar').inert = window.matchMedia('(max-width:760px)').matches;
  }
  function navigate(focus = false) {
    const raw = window.location.hash.slice(1);
    const page = Object.hasOwn(PAGE_TITLES, raw) ? raw : 'overview';
    state.page = page;
    $$('.page').forEach(el => { el.hidden = el.id !== 'page-' + page; });
    $$('[data-page]').forEach(el => { if (el.dataset.page === page) el.setAttribute('aria-current','page'); else el.removeAttribute('aria-current'); });
    $('#breadcrumb-title').textContent = PAGE_TITLES[page];
    document.title = PAGE_TITLES[page] + ' · Opportunity OS';
    closeNav(); $('#account-options').hidden = true; $('#account-button').setAttribute('aria-expanded','false');
    if (focus) { window.scrollTo({top:0}); $('#title-' + page).focus({preventScroll:true}); }
  }
  window.addEventListener('hashchange', () => navigate(true));
  $('.skip-link').addEventListener('click',event => { event.preventDefault(); $('#main-content').focus(); });
  $('#mobile-menu').addEventListener('click', () => {
    const open = !$('#workspace').classList.contains('nav-open');
    $('#workspace').classList.toggle('nav-open',open); $('#sidebar-backdrop').hidden = !open;
    $('#mobile-menu').setAttribute('aria-expanded',String(open)); $('#sidebar').inert = !open;
    if (open) ($('#sidebar [aria-current="page"]') || $('.nav-links a')).focus();
  });
  $('#sidebar-backdrop').addEventListener('click', closeNav);
  $('#collapse-sidebar').addEventListener('click', () => {
    const collapsed = $('#workspace').classList.toggle('is-collapsed');
    $('#collapse-sidebar').setAttribute('aria-expanded',String(!collapsed));
    $('#collapse-sidebar').setAttribute('aria-label',collapsed ? 'Expand sidebar' : 'Collapse sidebar');
    try { localStorage.setItem('opportunity-sidebar-collapsed',String(collapsed)); } catch { /* Browser storage is optional. */ }
  });
  try { if (localStorage.getItem('opportunity-sidebar-collapsed') === 'true') { $('#workspace').classList.add('is-collapsed'); $('#collapse-sidebar').setAttribute('aria-expanded','false'); $('#collapse-sidebar').setAttribute('aria-label','Expand sidebar'); } } catch { /* Use expanded sidebar. */ }
  window.matchMedia('(max-width:760px)').addEventListener('change', closeNav);
  $('#account-button').addEventListener('click', () => {
    const opened = $('#account-options').hidden; $('#account-options').hidden = !opened;
    $('#account-button').setAttribute('aria-expanded',String(opened));
  });
  document.addEventListener('click', event => {
    if (!event.target.closest('.account-menu')) { $('#account-options').hidden = true; $('#account-button').setAttribute('aria-expanded','false'); }
  });
  document.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); $('#global-search').focus(); }
    if (event.key === 'Escape') { if ($('#workspace').classList.contains('nav-open')) { closeNav(); $('#mobile-menu').focus(); } $('#account-options').hidden = true; $('#account-button').setAttribute('aria-expanded','false'); }
    if (event.key === 'Tab' && $('#workspace').classList.contains('nav-open')) {
      const focusable = $$('#sidebar a, #sidebar button').filter(el => el.getClientRects().length);
      const first = focusable[0], last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  });
  $('#profile-settings').addEventListener('click', () => go('settings'));
  $('#integration-indicator').addEventListener('click', () => go('settings'));
  async function logout(button) {
    await busy(button, async () => { try { await post('/api/logout'); window.location.replace('/'); } catch (error) { toast(error.message,true); } }, 'Signing out…');
  }
  $('#logout').addEventListener('click', event => logout(event.currentTarget));
  $('#settings-logout').addEventListener('click', event => logout(event.currentTarget));
  $('#global-search-form').addEventListener('submit', event => { event.preventDefault(); $('#job-search').value = $('#global-search').value; state.limit = 24; go('explore'); renderExplore(); });
  $('#today-label').textContent = new Intl.DateTimeFormat('en-IN',{weekday:'short',day:'numeric',month:'short',timeZone:'Asia/Kolkata'}).format(new Date());
  $$('dialog').forEach(dialog => {
    dialog.addEventListener('click', event => { if (event.target.closest('[data-close]')) dialog.close(); });
  });
  function openDialog(id) { const dialog = $(id); dialog.querySelectorAll('.form-feedback').forEach(node => { node.textContent = ''; }); dialog.showModal(); }

  // All views derive from the same server records. Filters never alter overview totals.
  function renderOverview() {
    if (state.summary) {
      ['total','saved','applied'].forEach(key => { $(`[data-metric="${key}"]`).textContent = state.summary[key]; });
      $('#nav-total').textContent = state.summary.total;
      $('#overview-metrics').setAttribute('aria-busy','false');
      $('#momentum').innerHTML = [['assessment','Assessments'],['interviews','Interviews'],['offers','Offers'],['contacts','Recruiter contacts']].map(([key,label]) => `<div class="momentum-stage"><strong>${Number(state.summary[key]) || 0}</strong><span>${label}</span></div>`).join('');
      $('#welcome-summary').textContent = state.summary.total ? `Welcome back, Raj. You’re tracking ${state.summary.total} opportunities. Keep your Summer 2027 search moving, one thoughtful step at a time.` : 'Welcome back, Raj. Your Summer 2027 journey starts here. Discover a role, save a possibility, and take the next step.';
    }
    if (state.jobs) {
      const recommended = state.jobs.filter(job => !['Rejected','Closed','Offer'].includes(job.status)).sort((a,b) => score(b)-score(a)).slice(0,3);
      $('#recommended-jobs').innerHTML = recommended.length ? recommended.map(job => `<div class="recommended-row">${avatar(job.company)}<div class="recommended-copy">${detailsButton(job)}<p>${esc(job.company)} <span>·</span> ${esc(job.location || 'Location not listed')}</p></div><span class="match-pill" title="Estimated keyword match, not guaranteed eligibility">${icon('spark')}${score(job)}% <small>est.</small></span><button class="icon-button" data-action="details" data-id="${esc(job.id)}" aria-label="View ${esc(job.company)} role">${icon('arrow')}</button></div>`).join('') : empty('Your radar is ready','Refresh employer boards or save an official listing to find your next possibility.','compass','<button class="button" data-action="refresh">Find opportunities ↗</button>',true);
      const recent = state.jobs.filter(job => job.updated).sort((a,b) => String(b.updated).localeCompare(String(a.updated))).slice(0,4);
      $('#recent-activity').innerHTML = recent.length ? recent.map(job => `<div class="activity-row"><span class="activity-icon">${icon(job.status === 'Discovered' ? 'compass' : 'check')}</span><div>${detailsButton(job,job.company + ' · ' + job.title)}<small>${esc(job.status)} · Latest record update</small></div><time>${esc(shortDate(job.updated))}</time></div>`).join('') : empty('A fresh start','Your latest application updates will appear here.','clock','',true);
    }
    if (state.alerts) {
      const followups = state.alerts.alerts.filter(alert => alert.kind === 'followup');
      $('[data-metric="followups"]').textContent = state.alerts.counts?.followup ?? followups.length;
      const deadlines = state.alerts.alerts.filter(alert => alert.kind === 'deadline').sort((a,b) => {
        const first = state.jobs?.find(job => job.id === a.job_id)?.deadline || '';
        const second = state.jobs?.find(job => job.id === b.job_id)?.deadline || '';
        return first.localeCompare(second);
      });
      $('#upcoming-deadlines').innerHTML = deadlines.length ? deadlines.slice(0,4).map(alert => {
        const job = state.jobs?.find(item => item.id === alert.job_id);
        const day = dateOnly(job?.deadline);
        return `<div class="deadline-row"><span class="deadline-date">${day ? esc(day.slice(8)) : '—'}<small>${day ? esc(new Intl.DateTimeFormat('en',{month:'short',timeZone:'UTC'}).format(new Date(day))) : 'DUE'}</small></span><div><strong>${esc(alert.company)}</strong><p>${esc(alert.message)}</p>${job ? detailsButton(job) : ''}</div></div>`;
      }).join('') : empty('A little breathing room','No recorded deadlines in the next 7 days. Add a confirmed date in opportunity details.','clock','',true);
      $('#followup-list').innerHTML = followups.length ? followups.map(alert => `<div class="reminder-row"><span class="amber">${icon('clock')}</span><div><strong>${esc(alert.company)} · ${esc(alert.title)}</strong><p>${esc(alert.message)}</p></div><button class="button small" data-action="details" data-id="${esc(alert.job_id)}">Review</button></div>`).join('') : empty('You’re all caught up','No follow-ups due in the current reminder window.','check','',true);
    }
    renderNextActions();
  }
  function renderNextActions() {
    const actions = [];
    if (state.caps && !state.caps.persistent) actions.push(['settings','Give your progress a permanent home','Connect PostgreSQL to retain data and enable private features.']);
    if (state.alerts?.alerts.some(alert => alert.kind === 'followup')) actions.push(['followups','Give a conversation a gentle nudge','Review the applications due for a follow-up.']);
    if (state.jobs?.length) actions.push(['explore','Find the role that feels like you','Review your strongest estimated matches and verify requirements.']);
    else actions.push(['refresh','Put your next move on the map','Check official employer boards for internship openings.']);
    if (state.caps && !state.caps.gmail_connected) actions.push(['gmail','Make room for meaningful replies','Set up Gmail and authorize your own account when ready.']);
    else if (state.caps?.gmail_connected) actions.push(['gmail','See where the conversation goes','Check recent recruiter replies and assessment invitations.']);
    if (state.caps?.persistent && !state.caps.resume_uploaded) actions.push(['resume','Bring your experience along','Store your exact original PDF in your private resume vault.']);
    $('#next-actions').innerHTML = actions.slice(0,3).map(([action,title,description],index) => `<button class="action-item" data-action="${action}"><span class="action-number">${String(index+1).padStart(2,'0')}</span><span class="action-copy"><strong>${esc(title)}</strong><small>${esc(description)}</small></span><span>↗</span></button>`).join('');
  }
  function filteredJobs() {
    const query = $('#job-search').value.toLowerCase().trim();
    const location = $('#location-filter').value, stage = $('#stage-filter').value, minimum = Number($('#match-filter').value);
    const ncr = /delhi|noida|gurugram|gurgaon|faridabad|ghaziabad|\bncr\b/i;
    const india = /\bindia\b|delhi|noida|gurugram|gurgaon|bengaluru|bangalore|pune|hyderabad|mumbai|chennai|kolkata|faridabad|ghaziabad|ahmedabad|kochi|chandigarh/i;
    const records = (state.jobs || []).filter(job => {
      const geo = String(job.location || '');
      return (!query || `${job.company} ${job.title} ${geo}`.toLowerCase().includes(query)) && (!stage || job.status === stage) && score(job) >= minimum && (location === 'all' || (location === 'ncr' && ncr.test(geo)) || (location === 'india' && india.test(geo)) || (location === 'remote' && job.work_mode === 'Remote') || (location === 'worldwide' && job.work_mode === 'Remote' && /Worldwide claimed/.test(job.remote_scope || '')) || (location === 'india-remote' && job.work_mode === 'Remote' && /India mentioned/.test(job.remote_scope || '')) || (location === 'hybrid' && job.work_mode === 'Hybrid') || (location === 'onsite' && job.work_mode === 'On-site'));
    });
    records.sort((a,b) => {
      const sort = $('#sort-order').value;
      if (sort === 'remote') {
        const remoteRank=job => job.work_mode === 'Remote' ? (/India mentioned|Worldwide claimed/.test(job.remote_scope || '') ? 3 : 2) : job.work_mode === 'Hybrid' ? 1 : 0;
        return remoteRank(b)-remoteRank(a) || score(b)-score(a);
      }
      if (sort === 'company') return String(a.company).localeCompare(String(b.company));
      if (sort === 'newest') return String(b.discovered || '').localeCompare(String(a.discovered || ''));
      if (sort === 'deadline') return (dateOnly(a.deadline) || '9999').localeCompare(dateOnly(b.deadline) || '9999');
      return score(b)-score(a);
    });
    return records;
  }
  function jobCard(job) {
    const tracked = !['Discovered','Saved'].includes(job.status), saved = job.status === 'Saved';
    return `<article class="job-card"><div class="job-card-top">${avatar(job.company)}<div class="job-card-copy"><div class="company-name">${esc(job.company)}</div>${detailsButton(job)}<div class="job-card-meta"><span>${icon('pin')}${esc(job.location || 'Location not listed')}</span>${job.work_mode ? '<span class="badge">'+esc(job.work_mode)+'</span>' : ''}${job.work_mode === 'Remote' ? '<span class="badge">'+esc(job.remote_scope || 'Region unverified')+'</span>' : ''}<span class="provider-label">${esc(job.provider || 'Source not recorded')}</span>${job.deadline ? `<span>${icon('clock')}Deadline: ${esc(shortDate(job.deadline))}</span>` : ''}</div><p class="job-description-preview">${esc(job.description_preview || job.description?.slice(0,380) || 'Open the official listing for role responsibilities and requirements.')}</p></div><div class="job-match" title="Estimated keyword match"><strong>${score(job)}<small> / 100</small></strong><small>EST. MATCH</small></div></div><div class="job-card-bottom"><span class="eligibility-label${job.warnings ? ' warning' : ''}">${icon('info')}${esc(job.warnings || 'Graduation eligibility unverified')}</span><span class="badge${job.status === 'Offer' ? ' positive' : ''}">${esc(job.status)}</span><button class="button" data-action="save" data-id="${esc(job.id)}" aria-pressed="${saved}"${tracked ? ' disabled title="Already tracked in your application pipeline"' : ''}>${icon(saved ? 'check' : 'bookmark')}${tracked ? 'Tracked' : saved ? 'Saved' : 'Save'}</button><button class="button" data-action="draft" data-id="${esc(job.id)}">${icon('mail')}Draft outreach</button>${officialLink(job,'button','Open listing')}</div></article>`;
  }
  function renderExplore() {
    if (!state.jobs) { $('#jobs-list').innerHTML = '<div class="skeleton job-skeleton"></div><div class="skeleton job-skeleton"></div>'; return; }
    const jobs = filteredJobs();
    $('#jobs-list').setAttribute('aria-busy','false');
    $('#results-count').textContent = `${jobs.length} ${jobs.length === 1 ? 'opportunity' : 'opportunities'}${jobs.length !== state.jobs.length ? ' match your filters' : ' to explore'}`;
    $('#jobs-list').innerHTML = jobs.length ? jobs.slice(0,state.limit).map(jobCard).join('') : state.jobs.length ? empty('Let’s try a wider lens','No opportunities match these filters. Try another location, stage, or estimated score.','search','<button class="button" data-action="reset-filters">Clear filters</button>') : empty('Your next chapter is waiting','Refresh official company boards or add an opening you’ve found. Every listing will appear here.','compass','<button class="button primary" data-action="refresh">Refresh employer boards ↗</button>');
    $('#load-more').hidden = jobs.length <= state.limit;
    $('#results-limit').textContent = jobs.length ? `Showing ${Math.min(state.limit,jobs.length)} of ${jobs.length}` + (state.summary?.total > state.jobs.length ? ` · Latest ${state.jobs.length} records loaded; export includes all records` : '') : '';
  }
  function resetFilters() { $('#filters').reset(); $('#sort-order').value = 'remote'; state.limit = 24; renderExplore(); }
  $('#filters').addEventListener('submit', event => event.preventDefault());
  $('#filters').addEventListener('input', () => { state.limit = 24; renderExplore(); });
  $('#filters').addEventListener('change', () => { state.limit = 24; renderExplore(); });
  $('#filters').addEventListener('reset', () => { setTimeout(() => { state.limit = 24; renderExplore(); },0); });
  $('#sort-order').addEventListener('change', renderExplore);
  $('#load-more').addEventListener('click', () => { state.limit += 24; renderExplore(); });
  function renderApplications() {
    if (!state.jobs) return;
    const jobs = state.jobs.filter(job => job.status !== 'Discovered');
    const counts = stage => jobs.filter(job => job.status === stage).length;
    $('#application-summary').innerHTML = [['Tracked roles',jobs.length],['In assessment',counts('Assessment')],['Interviews',counts('Interview')],['Offers',counts('Offer')]].map(([label,count]) => `<div class="pipeline-stat"><span>${label}</span><strong>${count}</strong></div>`).join('');
    const query = $('#application-search').value.toLowerCase().trim(), filter = $('#application-stage').value;
    const filtered = jobs.filter(job => `${job.company} ${job.title} ${job.notes || ''}`.toLowerCase().includes(query) && (!filter || job.status === filter));
    $('#application-board').classList.toggle('list-mode',state.view === 'list');
    if (!jobs.length || !filtered.length) { $('#application-board').innerHTML = empty(jobs.length ? 'No matching applications' : 'Make your first move',jobs.length ? 'Try another company, role, or stage.' : 'Save an opportunity from Explore, then track its stage, next action, and deadline here.','board','<a class="button" href="#explore">Explore opportunities ↗</a>'); return; }
    $('#application-board').innerHTML = STAGES.slice(1).filter(stage => !filter || stage === filter).map(stage => {
      const column = filtered.filter(job => job.status === stage).sort((a,b) => String(b.updated).localeCompare(String(a.updated)));
      return `<section class="board-column"><h2 class="board-column-header"><span><span class="stage-indicator"></span>${esc(stage)}</span><span class="board-column-count">${column.length}</span></h2>${column.length ? column.map(job => `<article class="pipeline-card"><div class="pipeline-company">${avatar(job.company)}${esc(job.company)}</div>${detailsButton(job)}<p class="pipeline-location">${esc(job.location || 'Location not listed')}</p>${job.notes ? `<p class="pipeline-notes">${esc(job.notes)}</p>` : ''}${job.deadline ? `<p class="pipeline-deadline">${icon('clock')}${esc(shortDate(job.deadline))}</p>` : ''}<select data-update-stage="${esc(job.id)}" aria-label="Stage for ${esc(job.company)} ${esc(job.title)}">${options(job.status)}</select></article>`).join('') : '<div class="pipeline-empty">No roles at this stage yet</div>'}</section>`;
    }).join('');
  }
  ['#application-search','#application-stage'].forEach(selector => { $(selector).addEventListener('input',renderApplications); });
  function setView(view) { state.view = view; $('#board-view').classList.toggle('active',view === 'board'); $('#list-view').classList.toggle('active',view === 'list'); $('#board-view').setAttribute('aria-pressed',String(view === 'board')); $('#list-view').setAttribute('aria-pressed',String(view === 'list')); renderApplications(); }
  $('#board-view').addEventListener('click', () => setView('board'));
  $('#list-view').addEventListener('click', () => setView('list'));
  function renderContacts() {
    if (!state.contacts) return;
    $('#contact-count').textContent = state.contacts.length;
    const query = $('#contact-search').value.toLowerCase().trim();
    const people = state.contacts.filter(person => `${person.company} ${person.name} ${person.email} ${person.role}`.toLowerCase().includes(query));
    $('#contact-list').innerHTML = people.length ? `<table class="contact-table"><thead><tr><th scope="col">Contact / company</th><th scope="col">Email</th><th scope="col">Target role</th><th scope="col">Outreach</th></tr></thead><tbody>${people.map(person => `<tr><td><strong>${esc(person.name || person.company || 'Recruiter')}</strong><small>${esc(person.company)}</small></td><td>${esc(person.email)}</td><td>${esc(person.role || 'Not specified')}</td><td><button class="button" data-action="contact-draft" data-id="${esc(person.id)}">${icon('mail')} Draft</button></td></tr>`).join('')}</tbody></table>` : empty(query ? 'No matching contacts' : 'Your next connection starts here',query ? 'Try a different name, company, or email address.' : 'Add a recruiter or import your own contacts once persistent storage is connected.','users');
  }
  $('#contact-search').addEventListener('input',renderContacts);
  function serviceRow(name, detail, badge, good, image) { return `<div class="service-row"><span class="service-icon">${icon(image)}</span><div class="service-copy"><strong>${esc(name)}</strong><p>${esc(detail)}</p></div><span class="badge ${good ? 'positive' : 'warning'}">${esc(badge)}</span></div>`; }
  function renderIntegrations() {
    const caps = state.caps;
    if (!caps) return;
    $$('[data-persistent]').forEach(node => { node.disabled = !caps.persistent; node.title = caps.persistent ? '' : 'Connect PostgreSQL in Settings to enable this private feature.'; });
    $('#storage-notice').hidden = caps.persistent;
    const needsSetup = !caps.persistent || !caps.gmail_connected;
    $('#integration-indicator').innerHTML = `<span class="status-dot${needsSetup ? ' checking' : ''}"></span><span>${needsSetup ? 'Setup to complete' : 'Integrations ready'}</span>`;
    $('#gmail-badge').textContent = caps.gmail_connected ? 'Connected' : caps.gmail_available ? 'Disconnected' : 'Setup required';
    $('#gmail-badge').className = 'badge ' + (caps.gmail_connected ? 'positive' : 'warning');
    $('#gmail-status').textContent = caps.gmail_connected ? 'Google authorization is stored. Check replies to verify current access; sending still requires your review.' : caps.gmail_available ? 'OAuth is configured. Authorize your intended account with Google to connect Gmail.' : !caps.persistent ? 'Connect persistent PostgreSQL first, then configure Google OAuth credentials and a stable session secret in Render.' : 'Configure GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and SESSION_SECRET privately in Render, then authorize Gmail.';
    $('#gmail-connect').hidden = !caps.gmail_available || caps.gmail_connected;
    $('#gmail-check').disabled = !caps.gmail_connected;
    $('#gmail-last-checked').textContent = 'Last checked: ' + shortTime(caps.gmail_last_checked);
    $('#gmail-account-label').textContent=caps.gmail_account?
      'Connected Gmail account: '+caps.gmail_account:
      'Account identity not yet verified. Use Check replies when Gmail is connected.';
    $('#attach-resume').disabled = !caps.resume_uploaded;
    if (!caps.resume_uploaded) $('#attach-resume').checked = false;
    updateSendGate();
    $('#resume-badge').textContent = caps.resume_uploaded ? 'Original stored' : 'Awaiting original PDF';
    $('#resume-badge').className = 'badge ' + (caps.resume_uploaded ? 'positive' : '');
    $('#resume-info').textContent = caps.resume_uploaded ? `${caps.resume_bytes?.toLocaleString('en-IN') || 'Unknown'} bytes · Stored ${shortDate(caps.resume_updated)}. Verify the checksum below.` : caps.persistent ? 'Upload your original PDF to keep it safely in your private vault.' : 'Persistent PostgreSQL is required before private PDF uploads are enabled.';
    $('#resume-hash').textContent = caps.resume_sha256 || 'Available after upload';
    $('#resume-download').hidden = !caps.resume_uploaded;
    $('#resume-verify').disabled = !caps.resume_uploaded;
    $('#resume-upload').disabled = !caps.persistent || caps.resume_uploaded;
    $('#resume-file').disabled = !caps.persistent || caps.resume_uploaded;
    $('#resume-upload').title = caps.resume_uploaded ? 'Your stored original is protected from replacement.' : '';
    $('#resume-upload').textContent = caps.resume_uploaded ? 'Original preserved in your vault' : 'Upload original PDF';
    const boards = state.sources ? new Set([...state.sources.default_boards,...state.sources.sources,...(state.sources.extended_boards || [])].map(item => item.provider + ':' + item.slug)).size : null;
    $('#settings-integrations').innerHTML = [
      serviceRow('Workspace login',caps.login_configured ? 'Your dashboard is protected by password authentication and a private Flask session.' : 'Configure APP_PASSWORD privately in Render.','Protected',caps.login_configured,'lock'),
      serviceRow('PostgreSQL database',caps.persistent ? 'Connected using DATABASE_URL. Application data and private uploads persist across restarts.' : 'Temporary SQLite is active. Set the Supabase session pooler URL as DATABASE_URL in Render with SSL enabled.',caps.persistent ? 'Connected' : 'Setup required',caps.persistent,'globe'),
      serviceRow('Gmail OAuth',caps.gmail_connected ? 'Google authorization is stored. No email sends without individual review.' : caps.gmail_available ? 'Credentials are configured. Complete authorization in Gmail & outreach.' : 'Requires persistent storage, Google client credentials, and a stable SESSION_SECRET.',caps.gmail_connected ? 'Connected' : 'Not connected',caps.gmail_connected,'mail'),
      serviceRow('Resume storage',caps.resume_uploaded ? 'The original PDF is stored privately. Verify its stored SHA-256 in Resume vault.' : caps.persistent ? 'Ready for your original PDF upload.' : 'Private uploads stay disabled until PostgreSQL is connected.',caps.resume_uploaded ? 'Stored' : caps.persistent ? 'Ready' : 'Unavailable',caps.persistent,'file'),
      serviceRow('Employer discovery',boards === null ? 'Source configuration could not be loaded. Retry the connection check.' : `${boards} configured boards. Refresh results report any unavailable sources; configured does not imply reachable.`,boards === null ? 'Unknown' : 'Configured',boards !== null,'compass'),
      serviceRow('Session signing',caps.session_secret_configured ? 'A stable server-side SESSION_SECRET is configured.' : 'Set a stable SESSION_SECRET in Render to keep sessions consistent across workers and enable encrypted OAuth storage.',caps.session_secret_configured ? 'Configured' : 'Setup required',caps.session_secret_configured,'shield')
    ].join('');
    if (!state.messages) $('#gmail-messages').innerHTML = empty(caps.gmail_connected ? 'Ready when you are' : 'Connect your inbox first',caps.gmail_connected ? 'Check replies to review recent recruiter responses, assessment invitations, and interview messages.' : 'Your inbox remains private. Complete the configuration and Google authorization to check replies.','mail','',true);
    renderNextActions();
  }
  function renderSources() {
    if (!state.sources) return;
    const {default_boards:defaults,sources:custom,extended_boards:extended = [],public_feeds:feeds = [],india_boards:indiaBoards = [],india_portals:indiaPortals = []} = state.sources;
    const combined = new Map([...defaults,...extended,...indiaBoards].map(source => [source.provider + ':' + source.slug,{...source,custom:false}]));
    custom.forEach(source => combined.set(source.provider + ':' + source.slug,{...source,custom:true}));
    $('#source-summary').textContent = `${combined.size} employer-board candidates (including India) + ${feeds.length} global public feeds · ${custom.length} custom · failures shown on refresh`;
    $('#india-source-summary').textContent = `${indiaPortals.length} India/global platform links · ${indiaBoards.length} Indian startup board candidates · portal links require manual application`;
    $('#india-portal-list').innerHTML = indiaPortals.map(portal => `<a class="india-portal-link" href="${esc(safeUrl(portal.url))}" target="_blank" rel="noopener noreferrer"><strong>${esc(portal.name)} ↗</strong><small>${esc(portal.category)}</small><span class="mini-tag">${esc(portal.coverage)}</span></a>`).join('');
    $('#source-list').innerHTML = Array.from(combined.values()).map(source => {
      const boardUrl = ({greenhouse:'https://boards.greenhouse.io/',lever:'https://jobs.lever.co/',ashby:'https://jobs.ashbyhq.com/'})[source.provider];
      return `<div class="source-row"><div><strong>${esc(source.name)}</strong><small>${esc(source.provider)} / ${esc(source.slug)}</small></div><span class="mini-tag">${source.custom ? 'CUSTOM' : 'INCLUDED'}</span>${boardUrl ? `<a class="icon-button" href="${boardUrl + encodeURIComponent(source.slug)}" target="_blank" rel="noopener noreferrer" aria-label="Open ${esc(source.name)} board">${icon('external')}</a>` : ''}${source.custom ? `<button class="icon-button" data-action="remove-source" data-id="${esc(source.id)}" aria-label="Remove custom ${esc(source.name)} source">${icon('x')}</button>` : ''}</div>`;
    }).join('') + feeds.map(feed => '<div class="source-row"><div><strong>'+esc(feed.name)+'</strong><small>Worldwide remote public feed · '+esc(feed.provider)+'</small></div><span class="mini-tag">PUBLIC API</span><a class="icon-button" href="'+esc(safeUrl(feed.url))+'" target="_blank" rel="noopener noreferrer" aria-label="Open '+esc(feed.name)+' source">'+icon('external')+'</a></div>').join('');
  }
  function renderSent() {
    const local=state.sent||[],outbox=state.gmailOutbox||[];
    const seen=new Set();
    const merged=[
      ...outbox.map(mail=>({id:mail.id,subject:mail.subject,recipient:mail.to,
        date:mail.date,source:'Gmail Sent · delivery unverified'})),
      ...local.map(mail=>({id:mail.gmail_id,subject:mail.subject,recipient:mail.recipient,
        date:mail.sent_at,source:'Sent from Opportunity OS'}))
    ].filter(mail=>{const key=mail.id||mail.recipient+mail.subject;
      if(seen.has(key))return false;seen.add(key);return true;});
    $('#sent-emails').innerHTML=merged.length?merged.slice(0,70).map(mail=>
      '<article class="message-row"><h3>'+esc(mail.subject||'Application outreach')+'</h3>'+
      '<small>'+esc(mail.recipient||'Recipient unavailable')+' · '+esc(shortTime(mail.date))+'</small>'+
      '<span class="badge">'+esc(mail.source)+'</span></article>').join(''):
      empty('No synced sent messages','Connect Gmail and choose Check replies to sync recent outgoing messages. Existing Opportunity OS sends will appear here.','send','',true);
  }

  function renderAutomation() {
    const data=state.autoapply, node=$('#auto-queue');
    if (!data) { $('#auto-overview').textContent='Queue is unavailable; check your database connection.'; return; }
    const defaults=data.professional_defaults || {}, professional=data.professional_profile || {}, contact=data.profile_contact || {};
    const fieldValues={
      '#auto-first':contact.first_name || 'Raj', '#auto-last':contact.last_name || 'Salonia',
      '#auto-email':contact.email || '', '#auto-phone':contact.phone || '',
      '#auto-linkedin':professional.linkedin ?? defaults.linkedin ?? '',
      '#auto-github':professional.github ?? defaults.github ?? '',
      '#auto-portfolio':professional.portfolio ?? defaults.portfolio ?? '',
      '#auto-college':professional.college ?? defaults.college ?? '',
      '#auto-degree':professional.degree ?? defaults.degree ?? '',
      '#auto-city':professional.city ?? defaults.city ?? '',
      '#auto-country':professional.country ?? defaults.country ?? '',
      '#auto-cgpa':professional.cgpa ?? '', '#auto-percentage':professional.percentage ?? '',
      '#auto-graduation-month':professional.passing_month ?? ''
    };
    for(const [selector,value] of Object.entries(fieldValues)){
      const element=$(selector);
      if(element && document.activeElement!==element) element.value=String(value);
    }
    $('#auto-work-auth').checked=data.profile_work_authorized_india===true;
    $('#auto-consent').checked=data.profile_ready===true;
    const r=data.rules || {};
    $('#auto-match').value=String(r.minimum_match || 75);
    $('#auto-daily').value=String(r.max_daily || 2);
    $('#auto-enable').checked=r.enabled === true;
    $('#auto-mode-badge').textContent=r.enabled ? 'Enabled with safeguards' : 'Automation off';
    $('#auto-mode-badge').className='badge ' + (r.enabled ? 'positive' : 'warning');
    $('#auto-run').disabled=!r.enabled || !data.profile_ready || !data.resume_ready;
    const tasks=data.tasks || [], counts=data.task_summary?.by_status || {};
    const submitted=counts.submitted ?? tasks.filter(item=>item.status==='submitted').length;
    const ownerRecorded=counts.user_reported ?? tasks.filter(item=>item.status==='user_reported').length;
    const ready=counts.ready ?? tasks.filter(item=>item.status==='ready').length;
    const review=(counts.needs_review ?? tasks.filter(item=>item.status==='needs_review').length)+(counts.unknown ?? tasks.filter(item=>item.status==='unknown').length);
    $('#auto-overview').textContent=(data.task_summary?.total ?? tasks.length)+' queued (latest '+tasks.length+' displayed) · '+ready+' eligible · '+review+' need review · '+submitted+' confirmed submissions · '+ownerRecorded+' owner-recorded. Profile: '+(data.profile_ready?'approved':'not approved')+'. Employer key: '+(data.greenhouse_keys_configured?'configured':'not configured')+'. External schedule: '+(data.scheduled_trigger_configured?'configured':'not configured')+'.';
    const historyFilter=$('#auto-history-filter').value;
    const visibleTasks=historyFilter==='all' ? tasks : tasks.filter(item=>item.status===historyFilter);
    node.innerHTML=visibleTasks.length ? visibleTasks.slice(0,80).map(item=>{
      const link=safeUrl(item.url);
      const status=esc(String(item.status || '').replaceAll('_',' '));
      const reason=esc(item.reason || '');
      const title=esc(item.company)+' — '+esc(item.title);
      const open=link ? '<a href="'+esc(link)+'" target="_blank" rel="noopener noreferrer" class="button small">Official application ↗</a>' : '';
      const pack='<a href="/api/autoapply/pack/'+encodeURIComponent(item.job_id)+'?download=1" class="button small" title="Download reusable autofill profile, not a submitted application">Autofill pack ↓</a>';
      const approve=item.status==='needs_review' ? '<button class="button small" type="button" data-auto-approve="'+esc(item.job_id)+'">I verified eligibility</button>' : '';
      const manual=['needs_review','ready'].includes(item.status) ? '<button class="button small" type="button" data-auto-manual="'+esc(item.job_id)+'">Record manual submission</button>' : '';
      const receipt=item.receipt ? '<small>'+(item.status==='user_reported'?'Owner-provided reference: ':'Employer confirmation: ')+esc(item.receipt)+'</small>' : '';
      const when=item.attempted_at ? '<small>Attempted: '+esc(shortTime(item.attempted_at))+'</small>' : '';
      const submitted=item.status==='submitted' ? '<span class="badge positive">API-confirmed submission</span>' : (item.status==='user_reported' ? '<span class="badge">Owner-recorded, not API-verified</span>' : '');
      return '<article class="automation-task"><div><strong>'+title+'</strong><p>'+esc(item.location || 'Location unconfirmed')+' · '+esc(item.provider || 'Other ATS')+' · '+esc(item.score)+'% estimated match</p><small>'+status+(reason ? ' — '+reason : '')+'</small>'+receipt+when+submitted+'</div><div class="automation-task-actions">'+open+pack+approve+manual+'</div></article>';
    }).join('') : '<p class="muted">No applications in this view. Choose All applications or refresh eligible opportunities.</p>';
  }
  $('#auto-history-filter').addEventListener('change',renderAutomation);
  async function reloadAutomation() {
    state.autoapply=await api('/api/autoapply');
    renderAutomation();
  }

  /* One glance at jobs, startup feeds, hackathons and community announcements.
     Source cards are discovery only, not application/registration receipts. */
  const radarJobItem = job => ({
    id:'job:'+job.id, category:/intern|trainee|apprentice|co.?op/i.test(job.title||'')?'Internship':'Startup hiring',
    title:job.title,summary:job.description_preview||job.description?.slice(0,320)||'Check official employer requirements.',
    url:job.url,source:job.company+' · '+(job.provider||'Employer'),
    location:job.location||'Location not specified',deadline:job.deadline||'',
    state:['Saved','Draft ready','Applied','Assessment','Interview','Offer'].includes(job.status)?'saved':'new',
    verification:job.warnings||'Employer job listing; eligibility and location must be verified.',
    score:score(job),published:job.discovered||'',isJob:true
  });
  function radarMerged() {
    const inbox=(state.radar?.items||[]).map(x=>({...x,isJob:false}));
    const jobs=(state.jobs||[])
      .filter(x=>!['Closed','Rejected'].includes(x.status))
      .map(radarJobItem)
      .sort((a,b)=>(b.score||0)-(a.score||0));
    const india=jobs.filter(x=>/\b(india|delhi|ncr|noida|gurgaon|gurugram|mumbai|pune|hyderabad|bengaluru|bangalore)\b/i.test(x.location));
    const remote=jobs.filter(x=>/remote|worldwide/i.test(x.location) && !india.includes(x));
    const remaining=jobs.filter(x=>!india.includes(x) && !remote.includes(x));
    return [...india,...remote,...inbox,...remaining];
  }
  function radarCard(item) {
    const category=esc(item.category||'Opportunity');
    const label=item.isJob?'Employer listing':(item.source||'Public feed');
    const meta=[item.location||'',item.deadline?'Deadline '+item.deadline:''].filter(Boolean).map(esc).join(' · ');
    const warning=esc(item.verification||'Confirm eligibility with the source.');
    const open=safeUrl(item.url)?'<a class="button small radar-open" href="'+esc(safeUrl(item.url))+'" target="_blank" rel="noopener noreferrer">View source '+icon('external')+'</a>':'';
    const buttons=item.isJob ?
      '<a class="button small" href="#explore" data-radar-job-search="'+esc(item.title)+'">In Explore →</a>' :
      '<button type="button" class="button small" data-radar-item="'+esc(item.id)+'" data-radar-next="'+(item.state==='saved'?'new':'saved')+'">'+(item.state==='saved'?'Unsave':'Save')+'</button>'+
      '<button type="button" class="icon-button radar-dismiss" data-radar-item="'+esc(item.id)+'" data-radar-next="dismissed" aria-label="Dismiss this signal">'+icon('x')+'</button>';
    const scorePill=item.isJob?'<span class="radar-score">'+Number(item.score||0)+'% estimated match</span>':'';
    return '<article class="radar-card"><div class="radar-card-line"><span class="radar-type">'+category+'</span><span class="radar-source">'+esc(label)+'</span>'+scorePill+'</div><h3>'+esc(item.title)+'</h3>'+
       '<p>'+esc(item.summary||'Read the original announcement for details.')+'</p>'+
       '<div class="radar-meta">'+(meta?'<span>'+meta+'</span>':'')+'<span>'+warning+'</span></div>'+
       '<div class="radar-card-actions">'+(item.state==='saved'?'<span class="badge positive">Saved</span>':'')+open+buttons+'</div></article>';
  }
  function renderRadar() {
    const list=$('#radar-list'),glance=$('#radar-glance-list');
    if(!state.radar && !state.jobs){list.innerHTML='<div class="skeleton job-skeleton"></div>';return;}
    const all=radarMerged(),countSaved=all.filter(i=>i.state==='saved').length;
    $('#nav-radar-count').textContent=all.length;
    $('#radar-total').textContent=all.length;
    $('#radar-saved-count').textContent=countSaved;
    $('#radar-feed-count').textContent=state.radar?.sources?.length??6;
    const ts=state.radar?.checked_at;
    const failures=state.radar?.failed_sources||[];
    $('#radar-freshness').textContent=failures.length ? failures.length+' source(s) temporarily unavailable' :
      ts?'Checked '+shortTime(ts):'Feed sync pending';
    $('#radar-checked').textContent=ts?'Public feeds checked '+shortTime(ts):'Public feed check pending';
    $('#radar-sources').innerHTML=(state.radar?.sources||[]).map(x=>
      '<a href="'+esc(safeUrl(x.url))+'" target="_blank" rel="noopener noreferrer" class="radar-source-link"><span>'+esc(x.name)+'</span>'+icon('external')+'</a>').join('')+
      (failures.length?'<p class="radar-outage">Temporarily unavailable: '+failures.map(esc).join(', ')+'</p>':'')+
      '<p class="muted">Listings are aggregated with source attribution; availability is never guaranteed.</p>';
    const query=$('#radar-search').value.toLowerCase().trim(),cat=state.radarCategory;
    const visible=all.filter(x=>(cat==='all'||(cat==='saved'?x.state==='saved':x.category===cat)) &&
      (!query||[x.title,x.summary,x.location,x.source].join(' ').toLowerCase().includes(query)));
    $('#radar-results-count').textContent=visible.length+' signals'+(query?' matching your search':'');
    const max=state.radarLimit;
    list.innerHTML=visible.length?visible.slice(0,max).map(radarCard).join(''):empty(
      'Nothing matching those filters','Try a different keyword or open the official hiring sites in Career Sources.','search');
    $('#radar-show-more').hidden=visible.length<=max;
    const top=all.filter(x=>x.state!=='dismissed').slice(0,3);
    glance.innerHTML=top.length?top.map(item=>'<a class="radar-glance-item" href="#radar"><span class="radar-glance-tag">'+esc(item.category)+'</span><strong>'+esc(item.title)+'</strong><small>'+esc(item.source)+'</small><span aria-hidden="true">↗</span></a>').join(''):
       '<a href="#radar" class="radar-glance-item">Check new opportunities →</a>';
  }
  async function refreshRadar(quiet=false) {
    if(state.radarScanning)return;
    state.radarScanning=true;
    const btn=$('#radar-refresh');
    if(btn)btn.disabled=true;
    if(!quiet)$('#radar-freshness').textContent='Checking source feeds…';
    try {
      const response=await post('/api/radar/refresh');
      const next=await api('/api/radar');
      state.radar=next;renderRadar();
      if(!quiet)toast(response.skipped?'Radar already up to date':response.new+' fresh signal(s) found.'+
        (next.failed_sources?.length?' '+next.failed_sources.length+' feeds were unavailable.':''),Boolean(next.failed_sources?.length));
    }catch(error){
      if(!quiet)toast('Radar refresh unavailable: '+error.message,true);
      $('#radar-freshness').textContent='Feed refresh failed · existing listings kept';
    }finally{state.radarScanning=false;if(btn)btn.disabled=false;}
  }



  // Unified, read-only command center: never infer applications from a listing.
  let briefMode='all';
  const briefFilters=[['all','For you'],['jobs','Internships & jobs'],['hackathons','Hackathons'],['startups','Startup leads'],['events','Events & more'],['replies','Replies']];
  document.addEventListener('click',event=>{
    const button=event.target.closest('[data-brief-filter]');
    if(!button)return;
    const next=button.dataset.briefFilter;
    if(!briefFilters.some(x=>x[0]===next))return;
    briefMode=next;renderDailyBrief();
  });
  function renderDailyBrief() {
    const panel=$('#daily-command-list'),stats=$('#daily-command-stats'),status=$('#discovery-freshness');
    const controls=$('#daily-brief-controls');
    if(!panel||!stats)return;
    const jobs=(state.jobs||[]).filter(job=>!['Closed','Rejected','Applied','Assessment','Interview','Offer'].includes(job.status));
    const india=/\b(india|delhi|noida|gurugram|gurgaon|bengaluru|bangalore|pune|hyderabad|mumbai|chennai|kolkata|ncr)\b/i;
    const matched=jobs.map(job=>{
      const location=String(job.location||'');
      const indiaHint=india.test(location);
      const remote=job.work_mode==='Remote';
      const worldwide=job.remote_scope==='Worldwide claimed / verify';
      const priority=score(job)+(indiaHint?18:0)+(worldwide?12:0)+(remote?5:0)+
        (job.status==='Saved'?7:0)-(job.warnings?6:0);
      return {job,priority,indiaHint,remote};
    }).sort((a,b)=>b.priority-a.priority);
    const radar=(state.radar?.items||[]).filter(x=>x.state!=='dismissed');
    const sortSignals=(list)=>list.sort((a,b)=>{
      const deadlineA=Date.parse(a.deadline||''),deadlineB=Date.parse(b.deadline||'');
      if(Number.isFinite(deadlineA)&&Number.isFinite(deadlineB))return deadlineA-deadlineB;
      if(Number.isFinite(deadlineA))return -1;
      if(Number.isFinite(deadlineB))return 1;
      return Number(b.state==='saved')-Number(a.state==='saved') ||
        (Date.parse(b.seen_at||'')||0)-(Date.parse(a.seen_at||'')||0);
    });
    const hackathons=sortSignals(radar.filter(x=>x.category==='Hackathon'));
    const startups=sortSignals(radar.filter(x=>x.category==='Startup hiring'));
    const others=sortSignals(radar.filter(x=>['Event','Community post','Fellowship','Scholarship','Other','Internship'].includes(x.category)));
    const inbound=(state.mailActivity?.items||[]).filter(x=>x.direction==='received'&&!x.reviewed);
    const possibleReplies=inbound.filter(x=>/Same Gmail conversation|Sender matches/i.test(x.reply_match||''));
    const counts={jobs:matched.length,hackathons:hackathons.length,startups:startups.length,events:others.length,replies:possibleReplies.length};
    stats.innerHTML='<span><strong>'+matched.length+'</strong> jobs to evaluate</span>'+
      '<span><strong>'+radar.length+'</strong> public & inbox signals</span>'+
      '<span><strong>'+possibleReplies.length+'</strong> possible replies</span>'+
      '<span><strong>'+Object.values(counts).reduce((sum,n)=>sum+n,0)+'</strong> items in these sections</span>';
    if(status){
      const d=state.discoveryState||{};
      status.textContent=d.status==='refreshing'?'Checking employer boards…':
        d.status==='failed'?'Some job sources failed · cached records shown':
        d.success_at?'Employer boards last checked '+shortTime(d.success_at):
        'Showing saved records · live checks may be pending';
    }
    if(controls){
      const labels=briefFilters.map(entry=>{
        const n=entry[0]==='all'?matched.length+radar.length+possibleReplies.length:counts[entry[0]];
        return '<button type="button" class="brief-filter'+(briefMode===entry[0]?' active':'')+
          '" data-brief-filter="'+entry[0]+'" aria-pressed="'+(briefMode===entry[0]?'true':'false')+'">'+
          esc(entry[1])+' <span>'+n+'</span></button>';
      }).join('');
      controls.innerHTML=labels;
    }
    const jobCard=record=>{
      const job=record.job,link=safeUrl(job.url);
      const desc=String(job.description_preview||job.description||'').trim().slice(0,235)||
        'Open the employer posting to check responsibilities, stipend, eligibility and application steps.';
      const mode=job.work_mode||'Work arrangement not specified';
      const eligibility=job.warnings || (record.indiaHint?
        'Location mentions India. Verify graduation year and the employer criteria.':
        record.remote?'Remote does not automatically mean eligible in India.':'Check location and work authorization before applying.');
      return '<article class="daily-brief-card command-job"><div class="daily-brief-top"><span class="daily-brief-kind">EMPLOYER LISTING</span>'+
        '<span class="daily-brief-score">'+score(job)+'% estimated match</span></div>'+
        '<h3>'+esc(job.title)+'</h3><p class="daily-brief-meta">'+esc(job.company)+' · '+esc(job.location||'Location unspecified')+'</p>'+
        '<p class="daily-brief-description">'+esc(desc)+'</p>'+
        '<div class="brief-tags"><span>'+esc(mode)+'</span><span>'+esc(job.provider||'Employer')+'</span></div>'+
        '<p class="brief-caution">'+esc(eligibility)+'</p>'+
        '<div class="daily-brief-foot"><span>'+esc(job.status==='Saved'?'Already saved':'Verify before applying')+'</span>'+
        (link?'<a href="'+esc(link)+'" target="_blank" rel="noopener noreferrer">View opening ↗</a>':'')+
        '</div></article>';
    };
    const signalCard=item=>{
      const link=safeUrl(item.url);
      const short=String(item.summary||'Original listing contains the complete details.').slice(0,235);
      const loc=item.location && !/^see (organizer|original)/i.test(item.location)?item.location:'';
      const date=item.deadline?'Deadline: '+item.deadline:'Deadline not confirmed';
      return '<article class="daily-brief-card command-signal"><div class="daily-brief-top"><span class="daily-brief-kind">'+esc(item.category||'LEAD')+'</span>'+
        '<span class="daily-brief-score">'+esc(item.source||'Public source')+'</span></div>'+
        '<h3>'+esc(item.title)+'</h3><p class="daily-brief-description">'+esc(short)+'</p>'+
        '<div class="brief-tags"><span>'+esc(date)+'</span>'+(loc?'<span>'+esc(loc)+'</span>':'')+'</div>'+
        '<p class="brief-caution">'+esc(item.verification||'Check original organizer and eligibility.')+'</p>'+
        '<div class="daily-brief-foot"><span>'+esc(item.state==='saved'?'Saved lead':'Discovery only · not applied')+'</span>'+
        (link?'<a href="'+esc(link)+'" target="_blank" rel="noopener noreferrer">Read details ↗</a>':'')+
        '</div></article>';
    };
    const replyCard=item=>{
      const url=connectedGmailLink(item.id);
      return '<article class="daily-brief-card command-reply"><div class="daily-brief-top"><span class="daily-brief-kind">POSSIBLE RECRUITER REPLY</span>'+
        '<span class="daily-brief-score">'+esc(item.stage||'Needs review')+'</span></div>'+
        '<h3>'+esc(item.subject||'(No subject)')+'</h3><p class="daily-brief-meta">'+esc(item.sender||'Unknown sender')+' · '+esc(shortTime(item.date))+'</p>'+
        '<p class="daily-brief-description">'+esc(String(item.snippet||'').slice(0,235))+'</p>'+
        '<p class="brief-caution">'+esc(item.reply_match||'Review the conversation before updating the application.')+'</p>'+
        '<div class="daily-brief-foot"><span>Requires your review</span><a href="'+url+'" target="_blank" rel="noopener noreferrer">Open Gmail ↗</a></div></article>';
    };
    const buckets={
      jobs:matched.slice(0,16).map(jobCard),
      hackathons:hackathons.slice(0,16).map(signalCard),
      startups:startups.slice(0,16).map(signalCard),
      events:others.slice(0,16).map(signalCard),
      replies:possibleReplies.slice(0,16).map(replyCard)
    };
    const cards=briefMode==='all'?
      [...buckets.replies.slice(0,2),...buckets.jobs.slice(0,4),...buckets.hackathons.slice(0,3),
        ...buckets.startups.slice(0,2),...buckets.events.slice(0,3)]:
      buckets[briefMode]||[];
    panel.innerHTML=cards.length?cards.join(''):empty(
      briefMode==='replies'?'No possible replies waiting for review':'No matching opportunities in this section',
      briefMode==='replies'?'Connected Gmail replies appear here after a successful inbox check.':
        'Use Opportunity Radar for all saved feeds and Explore for the full employer list. Try refreshing the sources.',
      'info','',true);
    $('#daily-brief-note').textContent='Showing '+cards.length+' of '+(briefMode==='all'?
      matched.length+radar.length+possibleReplies.length:counts[briefMode])+
      ' leads. Listings are not guaranteed open; eligibility, dates and applications require source confirmation.';
  }

  function connectedGmailLink(id){
    const addr=state.caps?.gmail_account;
    return 'https://mail.google.com/mail/'+
      (addr?'?authuser='+encodeURIComponent(addr):'/u/0/')+
      '#all/'+encodeURIComponent(id);
  }
  function renderMailLedger() {
    const node=$('#mail-ledger-list'),tag=$('#mail-ledger-count');
    if(!node)return;
    const items=state.mailActivity?.items||[];
    const count=(state.mailActivity?.counts?.received||0);
    const replies=items.filter(x=>x.direction==='received'&&
      /Same Gmail conversation|Sender matches/i.test(x.reply_match||''));
    const receipts=items.filter(x=>x.direction==='received'&&x.stage==='Application received').length;
    const bounces=items.filter(x=>x.direction==='received'&&x.stage==='Delivery failure').length;
    if(tag)tag.textContent=count+' received · '+replies.length+' possible replies · '+receipts+' receipts · '+bounces+' bounces';
    const shown=items.filter(x=>x.direction==='received').slice(0,16);
    node.innerHTML=shown.length?shown.map(x=>{
      const matched=/Same Gmail conversation|Sender matches/i.test(x.reply_match||'');
      const url=connectedGmailLink(x.id);
      return '<article class="mail-ledger-item"><div class="daily-brief-top"><span class="daily-brief-kind">'+
        esc(matched?'POSSIBLE RECRUITER REPLY':'INBOX SIGNAL')+'</span><span class="daily-brief-score">'+esc(x.stage||'Needs review')+'</span></div>'+
        '<h3>'+esc(x.subject||'(No subject)')+'</h3><p>'+esc(x.sender||'Sender unavailable')+' · '+esc(shortTime(x.date))+'</p>'+
        '<p>'+esc((x.snippet||'').slice(0,240))+'</p><small>'+esc(x.reply_match||'Check original thread')+'</small>'+
        '<div class="daily-brief-foot"><a href="'+url+'" target="_blank" rel="noopener noreferrer">Review Gmail ↗</a>'+
        (!x.reviewed?'<button type="button" class="button small" data-review-mail="'+esc(x.id)+'">Mark reviewed</button>':'<span>Reviewed</span>')+'</div></article>';
    }).join(''):empty('No synced inbox activity',
      'Connect Gmail inside Opportunity OS and click Check replies. Your connected ChatGPT Gmail account is separate from the website login.','mail','',true);
  }

  async function autoDiscover() {
    if(state.discoveryChecking || !state.caps?.persistent)return;
    state.discoveryChecking=true;
    try {
      const result=await post('/api/discovery/auto-refresh');
      state.discoveryState=result;renderDailyBrief();
      if(result.result==='started'){
        let tries=0;
        const poll=async()=>{
          if(++tries>7)return;
          try {
            state.discoveryState=await api('/api/discovery/state');
            renderDailyBrief();
            if(state.discoveryState.status==='ready'){
              await reloadJobs();
              state.radar=await api('/api/radar');
              renderRadar();renderDailyBrief();return;
            }
            if(state.discoveryState.status==='failed')return;
          }catch(error){return;}
          setTimeout(poll,18000);
        };
        setTimeout(poll,18000);
      }
    }catch(error){
      if($('#discovery-freshness'))$('#discovery-freshness').textContent='Live job check unavailable · saved roles shown';
    }finally{state.discoveryChecking=false;}
  }

  function renderAll() { renderOverview(); renderRadar(); renderExplore(); renderApplications(); renderContacts(); renderSources(); renderIntegrations(); renderSent(); renderAutomation(); renderMailLedger(); renderDailyBrief(); }
  const requests = [
    ['jobs','/api/jobs',data => data.jobs],['summary','/api/summary',data => data],['alerts','/api/alerts',data => data],
    ['caps','/api/integrations',data => data],['contacts','/api/contacts',data => data.contacts],
    ['sources','/api/sources',data => data],['radar','/api/radar',data => data],['sent','/api/gmail/sent',data => data.emails],
    ['autoapply','/api/autoapply',data => data],['mailActivity','/api/gmail/activity',data => data]
  ];

  $('#radar-search').addEventListener('input',()=>{state.radarLimit=48;renderRadar();});
  $('#radar-categories').addEventListener('click',event=>{
    const b=event.target.closest('[data-radar-category]');if(!b)return;
    state.radarCategory=b.dataset.radarCategory;state.radarLimit=48;
    $('#radar-categories button').forEach(x=>{const active=x===b;x.classList.toggle('active',active);x.setAttribute('aria-pressed',String(active));});
    renderRadar();
  });
  $('#radar-show-more').addEventListener('click',()=>{state.radarLimit+=60;renderRadar();});
  $('#radar-refresh').addEventListener('click',()=>refreshRadar(false));
  $('#radar-list').addEventListener('click',async event=>{
    const quick=event.target.closest('[data-radar-job-search]');
    if(quick){$('#job-search').value=quick.dataset.radarJobSearch;state.limit=24;renderExplore();return;}
    const target=event.target.closest('[data-radar-item]');
    if(!target)return;
    const next=target.dataset.radarNext;
    target.disabled=true;
    try{
      await api('/api/radar/'+encodeURIComponent(target.dataset.radarItem),
                {method:'PATCH',body:JSON.stringify({state:next})});
      state.radar=await api('/api/radar');renderRadar();
    }catch(error){toast(error.message,true);target.disabled=false;}
  });
  $('#radar-save-form').addEventListener('submit',async event=>{
    event.preventDefault();
    const button=event.submitter;
    await busy(button,async()=>{
      try{
        await post('/api/radar/save',{
          title:$('#radar-link-title').value.trim(),url:$('#radar-link-url').value.trim(),
          category:$('#radar-link-category').value,summary:$('#radar-link-summary').value.trim()});
        event.target.reset();state.radar=await api('/api/radar');
        $('#radar-save-feedback').textContent='Link saved. Read the original post to verify details.';renderRadar();
      }catch(error){$('#radar-save-feedback').textContent=error.message;toast(error.message,true);}
    },'Saving source…');
  });
  $('#auto-prep').addEventListener('click',async event=>{
    await busy(event.currentTarget,async()=>{
      try {const v=await post('/api/autoapply/prepare',{limit:600});$('#auto-feedback').textContent='Queued '+v.queued.ready+' eligible and '+v.queued.review+' review-needed opportunities.';await reloadAutomation();}
      catch(error){toast(error.message,true);}
    },'Preparing…');
  });
  $('#auto-run').addEventListener('click',async event=>{
    await busy(event.currentTarget,async()=>{
      try {const v=await post('/api/autoapply/run');$('#auto-feedback').textContent=v.message || ('Submitted '+v.submitted+' applications.');await reloadAutomation();await reloadJobs();}
      catch(error){toast(error.message,true);}
    },'Checking eligibility…');
  });
  $('#auto-settings-form').addEventListener('submit',async event=>{
    event.preventDefault();
    await busy(event.submitter,async()=>{
      try {
        await post('/api/autoapply/settings',{enabled:$('#auto-enable').checked,
          minimum_match:Number($('#auto-match').value),max_daily:Number($('#auto-daily').value)});
        $('#auto-feedback').textContent='Automation rules saved.';await reloadAutomation();
      } catch(error){toast(error.message,true);}
    },'Saving…');
  });
  $('#auto-profile-form').addEventListener('submit',async event=>{
    event.preventDefault();
    await busy(event.submitter,async()=>{
      try {
        await post('/api/autoapply/settings',{profile:{
          first_name:$('#auto-first').value.trim(),last_name:$('#auto-last').value.trim(),
          email:$('#auto-email').value.trim(),phone:$('#auto-phone').value.trim(),
          graduation_year:'2028',work_authorized_india:$('#auto-work-auth').checked,
          approved_for_employer_submission:$('#auto-consent').checked},
          professional:{
            linkedin:$('#auto-linkedin').value.trim(),github:$('#auto-github').value.trim(),
            portfolio:$('#auto-portfolio').value.trim(),college:$('#auto-college').value.trim(),
            degree:$('#auto-degree').value.trim(),city:$('#auto-city').value.trim(),
            country:$('#auto-country').value.trim(),cgpa:$('#auto-cgpa').value.trim(),
            percentage:$('#auto-percentage').value.trim(),
            passing_month:$('#auto-graduation-month').value.trim()}});
        $('#auto-feedback').textContent='Private applicant profile encrypted and saved.';await reloadAutomation();
      } catch(error){toast(error.message,true);}
    },'Encrypting…');
  });
  $('#auto-queue').addEventListener('click',async event=>{
    const manual=event.target.closest('[data-auto-manual]');
    if(manual){
      const reference=window.prompt('After you submitted on the official employer site, paste the actual confirmation/reference or acknowledgement. Leave empty if you have not submitted.');
      if(!reference?.trim())return;
      if(!window.confirm('Confirm: you personally submitted this application on the employer site. This will be recorded as OWNER-REPORTED, not API-verified.'))return;
      await busy(manual,async()=>{
        try{
          await post('/api/autoapply/confirm-manual/'+encodeURIComponent(manual.dataset.autoManual),{reference:reference.trim(),submitted_by_owner:true});
          await reloadAutomation();await reloadJobs();toast('Submission recorded as owner-reported, not API-verified.');
        }catch(error){toast(error.message,true);}
      },'Recording…');
      return;
    }
    const button=event.target.closest('[data-auto-approve]');
    if (!button)return;
    if (!window.confirm('Confirm you independently verified the company job requirements, India work eligibility, graduation year and custom questions for this specific opening.'))return;
    await busy(button,async()=>{
      try {await post('/api/autoapply/approve/'+encodeURIComponent(button.dataset.autoApprove),{eligibility_checked:true});await reloadAutomation();}
      catch(error){toast(error.message,true);}
    },'Saving…');
  });

  let loading;
  async function loadData() {
    if (loading) return loading;
    loading = (async () => {
      $('#load-error').hidden = true;
      const results = await Promise.allSettled(requests.map(async ([key,path,extract]) => { state[key] = extract(await api(path)); }));
      const failures = results.flatMap((result,index) => result.status === 'rejected' ? [`${requests[index][0]}: ${result.reason.message}`] : []);
      if (failures.length) {
        $('#load-error').hidden = false; $('#load-error-message').textContent = failures.join(' ');
        if (!state.jobs) { $('#jobs-list').innerHTML = empty('Your opportunities couldn’t load','Retry after checking your connection or database configuration.','info'); $('#jobs-list').setAttribute('aria-busy','false'); $('#results-count').textContent = 'Unable to load opportunities'; }
        if (!state.caps) { $('#gmail-status').textContent = 'Integration status is unavailable. Retry the connection check.'; $('#settings-integrations').innerHTML = empty('Status unavailable','Check your database connection and retry.','info'); }
      }
      renderAll();
      autoDiscover();
      if(state.radar){
        const ts=Date.parse(state.radar.checked_at||'');
        if(!Number.isFinite(ts)||Date.now()-ts>4*3600*1000)refreshRadar(true);
      }
      if(state.caps?.gmail_connected){
        const last=Date.parse(state.caps.gmail_last_checked||'');
        if(!Number.isFinite(last)||Date.now()-last>6*3600*1000)
          $('#gmail-check').click();
      }
      // Replace loading placeholders with errors rather than implying zero records.
      if (!state.jobs && failures.length) {
        $('#jobs-list').innerHTML = empty('Your opportunities couldn’t load','Check the error above and retry.','info');
        $('#recommended-jobs').innerHTML = empty('Your radar is temporarily unavailable','Retry the workspace connection.','info','',true);
      }
    })();
    try { await loading; } finally { loading = null; }
  }
  async function reloadJobs() {
    const results = await Promise.all([api('/api/jobs'),api('/api/summary'),api('/api/alerts')]);
    state.jobs = results[0].jobs; state.summary = results[1]; state.alerts = results[2];
    renderOverview(); renderExplore(); renderApplications();
  }
  $('#retry-load').addEventListener('click',loadData);
  $('#recheck-integrations').addEventListener('click',event => busy(event.currentTarget,loadData,'Checking…'));
  $('#check-alerts').addEventListener('click',event => busy(event.currentTarget,async () => { try { state.alerts = await api('/api/alerts'); renderOverview(); toast('Reminders checked.'); } catch (error) { toast(error.message,true); } },'Checking…'));
  async function refresh() {
    if (state.refreshing) return;
    state.refreshing = true;
    const buttons = $$('[data-action="refresh"]');
    const originals = buttons.map(button => button.innerHTML);
    buttons.forEach(button => { button.disabled = true; button.innerHTML = icon('refresh') + ' Checking employer boards…'; button.setAttribute('aria-busy','true'); });
    toast('Checking official employer boards. This can take a moment.');
    try {
      const result = await post('/api/refresh/extended');
      const message = `${result.new} new roles from ${result.checked} checked sources. ${result.errors.length} unavailable.${result.feeds_cached ? " Public remote feeds are cached for six hours." : ""}`;
      $('#refresh-report').hidden = false;
      $('#refresh-report').textContent = message + (result.errors.length ? ' ' + result.errors.join('; ') + '. Existing records are retained.' : ' Verify employer requirements for each role.');
      await reloadJobs();
      toast(message);
    } catch (error) { $('#refresh-report').hidden = false; $('#refresh-report').textContent = error.message; toast(error.message,true); }
    finally { state.refreshing = false; buttons.forEach((button,index) => { button.disabled = false; button.innerHTML = originals[index]; button.removeAttribute('aria-busy'); }); }
  }
  async function updateStage(id,status,more = {}) {
    await api('/api/jobs/' + encodeURIComponent(id),{method:'PATCH',body:JSON.stringify({status,...more})});
    await reloadJobs();
  }
  document.addEventListener('change',async event => {
    const select = event.target.closest('[data-update-stage]');
    if (!select) return;
    const old = state.jobs?.find(job => job.id === select.dataset.updateStage)?.status;
    select.disabled = true;
    try { await updateStage(select.dataset.updateStage,select.value); toast('Application stage updated.'); }
    catch (error) { select.value = old || 'Saved'; toast(error.message,true); }
    finally { select.disabled = false; }
  });
  function showDetails(id) {
    const job = state.jobs?.find(item => item.id === id);
    if (!job) { toast('This opportunity is no longer in the loaded results. Refresh and try again.',true); return; }
    $('#detail-id').value = job.id;
    $('#detail-stage').value = job.status;
    $('#detail-notes').value = job.notes || '';
    $('#detail-deadline').value = dateOnly(job.deadline);
    $('#job-detail-content').innerHTML = `<div class="detail-company">${avatar(job.company)}<div><strong>${esc(job.company)}</strong><small>${esc(job.provider || 'Source not recorded')} · Added ${esc(shortDate(job.discovered))}</small></div></div><h2 id="job-dialog-title">${esc(job.title)}</h2><div class="job-card-meta"><span>${icon('pin')}${esc(job.location || 'Location not listed')}</span><span class="match-pill">${score(job)}/100 estimated match</span>${job.work_mode ? '<span class="badge">'+esc(job.work_mode)+'</span>' : ''}${job.work_mode === 'Remote' ? '<span class="badge">'+esc(job.remote_scope || 'Region unverified')+'</span>' : ''}</div>${officialLink(job,'button primary','Open official listing')}<a class="button" href="/api/autoapply/pack/${encodeURIComponent(job.id)}?download=1">Download autofill pack ↓</a><div class="detail-callout">${esc(job.warnings || 'Graduation year and work authorization have not been verified.')} Check the official listing for eligibility, location requirements, and current availability. A match score is a keyword estimate.</div><div class="detail-description">${esc(job.description || 'No role description is available from this source. Open the original listing for the full details.')}</div>`;
    openDialog('#job-dialog');
  }
  $('#job-detail-form').addEventListener('submit',async event => {
    event.preventDefault();
    await busy(event.submitter,async () => { try { await updateStage($('#detail-id').value,$('#detail-stage').value,{notes:$('#detail-notes').value,deadline:$('#detail-deadline').value}); $('#job-dialog').close(); toast('Stage, notes, and deadline saved.'); } catch (error) { feedback('#detail-result',error.message,true); } },'Saving…');
  });
  async function draft(id) {
    if (($('#draft-subject').value || $('#draft-body').value) && !window.confirm('Replace the current unsent draft with a draft for this opportunity?')) return;
    const result = await api('/api/outreach/' + encodeURIComponent(id));
    $('#draft-job').value = id; $('#draft-subject').value = result.subject; $('#draft-body').value = result.body;
    $('#send-recipient').value = ''; $('#send-confirmed').checked = false; updateSendGate();
    const job = state.jobs?.find(item => item.id === id);
    $('#draft-context').textContent = job ? `Draft for ${job.company} · ${job.title}. Review and personalize it before sending.` : 'Review and personalize this draft before sending.';
    $('#send-result').textContent = '';
    if ($('#job-dialog').open) $('#job-dialog').close();
    go('gmail'); toast('Draft prepared. Nothing has been sent.');
  }
  $('#detail-draft').addEventListener('click',() => draft($('#detail-id').value).catch(error => toast(error.message,true)));
  function contactDraft(id) {
    const person = state.contacts?.find(item => item.id === id);
    if (!person) return;
    if (($('#draft-subject').value || $('#draft-body').value) && !window.confirm('Replace your current unsent draft with a personal recruiter introduction?')) return;
    $('#draft-job').value = ''; $('#send-recipient').value = person.email;
    $('#draft-subject').value = `Internship interest${person.role ? ': ' + person.role : ''}${person.company ? ' at ' + person.company : ''}`;
    $('#draft-body').value = `Hello ${person.name || 'Hiring Team'},\n\nI am a B.Tech Computer Science student graduating in 2028, exploring Summer 2027 internships in software engineering, Python backend, AI, and cloud. I would appreciate learning about ${person.role || 'relevant internship opportunities'}${person.company ? ' at ' + person.company : ''}.\n\nGitHub: https://github.com/rajsalonia\nLinkedIn: https://www.linkedin.com/in/rajsalonia\n\nThank you,\nRaj Salonia`;
    $('#draft-context').textContent = 'Personal recruiter introduction. Check and personalize every detail.';
    $('#send-confirmed').checked = false; updateSendGate(); $('#send-result').textContent = ''; go('gmail');
  }
  document.addEventListener('click',async event => {
    const button = event.target.closest('[data-action]'); if (!button || button.disabled) return;
    const action = button.dataset.action, id = button.dataset.id;
    try {
      if (action === 'details') showDetails(id);
      else if (action === 'refresh') await refresh();
      else if (action === 'add-job') openDialog('#add-job-dialog');
      else if (action === 'add-contact') openDialog('#contact-dialog');
      else if (action === 'draft') await busy(button,() => draft(id),'Preparing…');
      else if (action === 'contact-draft') contactDraft(id);
      else if (action === 'save') {
        const job = state.jobs.find(item => item.id === id);
        if (job && ['Discovered','Saved'].includes(job.status)) await busy(button,async () => { await updateStage(id,job.status === 'Saved' ? 'Discovered' : 'Saved'); toast(job.status === 'Saved' ? 'Removed from saved opportunities.' : 'Opportunity saved to your pipeline.'); },'Saving…');
      }
      else if (action === 'saved') { resetFilters(); $('#stage-filter').value = 'Saved'; renderExplore(); go('explore'); }
      else if (action === 'followups') { go('applications'); setTimeout(() => $('#reminders').scrollIntoView({block:'start',behavior:window.matchMedia('(prefers-reduced-motion:reduce)').matches ? 'auto' : 'smooth'}),0); }
      else if (action === 'reset-filters') resetFilters();
      else if (action === 'remove-source') {
        if (!window.confirm('Remove this custom employer board? Existing jobs will be retained.')) return;
        await api('/api/sources/' + encodeURIComponent(id),{method:'DELETE'}); state.sources = await api('/api/sources'); renderSources(); renderIntegrations(); toast('Custom board removed.');
      }
      else if (Object.hasOwn(PAGE_TITLES,action)) go(action);
    } catch (error) { toast(error.message,true); }
  });
  $('#add-job-form').addEventListener('submit',async event => {
    event.preventDefault(); await busy(event.submitter,async () => { try { await post('/api/jobs',Object.fromEntries(new FormData(event.target))); event.target.reset(); $('#add-job-dialog').close(); await reloadJobs(); toast('Opportunity saved. You can track it in My applications.'); } catch (error) { feedback('#add-job-result',error.message,true); } },'Saving…');
  });
  $('#contact-form').addEventListener('submit',async event => {
    event.preventDefault(); await busy(event.submitter,async () => { try { await post('/api/contacts',Object.fromEntries(new FormData(event.target))); event.target.reset(); $('#contact-dialog').close(); state.contacts = (await api('/api/contacts')).contacts; state.summary = await api('/api/summary'); renderContacts(); renderOverview(); toast('Recruiter contact added.'); } catch (error) { feedback('#contact-result',error.message,true); } },'Adding…');
  });
  $('#contact-import').addEventListener('submit',async event => {
    event.preventDefault(); await busy(event.submitter,async () => { try { const file = $('#contact-file').files[0]; if (file?.size > 4000000) throw Error('The contact file must be 4 MB or smaller.'); const result = await upload('/api/contacts/import',file); feedback('#import-result',`${result.imported} contacts imported · ${result.skipped} skipped · ${result.total_rows} rows checked.`); state.contacts = (await api('/api/contacts')).contacts; state.summary = await api('/api/summary'); renderContacts(); renderOverview(); } catch (error) { feedback('#import-result',error.message,true); } },'Importing…');
  });
  $('#source-form').addEventListener('submit',async event => {
    event.preventDefault(); await busy(event.submitter,async () => { try { await post('/api/sources',Object.fromEntries(new FormData(event.target))); event.target.reset(); state.sources = await api('/api/sources'); renderSources(); renderIntegrations(); feedback('#source-result','Board configured. Refresh opportunities to check this source.'); } catch (error) { feedback('#source-result',error.message,true); } },'Adding source…');
  });
  $('#resume-form').addEventListener('submit',async event => {
    event.preventDefault(); await busy(event.submitter,async () => { try { const file = $('#resume-file').files[0]; if (file?.size > 3000000) throw Error('The original PDF must be 3 MB or smaller.'); const result = await upload('/api/resume',file); feedback('#resume-result',`Stored unchanged · ${result.bytes.toLocaleString('en-IN')} bytes · SHA-256 ${result.sha256}`); state.caps = await api('/api/integrations'); renderIntegrations(); } catch (error) { feedback('#resume-result',error.message,true); } },'Storing original…'); renderIntegrations();
  });
  $('#resume-verify').addEventListener('click',event => busy(event.currentTarget,async () => { try { const result = await api('/api/resume/verify'); feedback('#verify-result',result.verified ? `Integrity verified. ${result.bytes.toLocaleString('en-IN')} original bytes match the stored checksum. Checked ${shortTime(result.checked_at)}.` : 'Integrity mismatch. The stored bytes do not match the expected checksum. Do not use this file until reviewed.',!result.verified); } catch (error) { feedback('#verify-result',error.message,true); } },'Verifying…'));
  $('#restore-form').addEventListener('submit',async event => {
    event.preventDefault();
    const file = $('#backup-file').files[0]; if (!file) return;
    if (!window.confirm(`Restore application data from “${file.name}”? Matching job URLs will have their stage, notes, and deadline updated. Contacts are restored only with PostgreSQL connected.`)) return;
    await busy(event.submitter,async () => { try { if (file.size > 3000000) throw Error('The backup must be 3 MB or smaller.'); const result = await upload('/api/restore',file); feedback('#restore-result',`${result.jobs_restored} job records restored. Resume and Gmail credentials were not changed.`); await loadData(); } catch (error) { feedback('#restore-result',error.message,true); } },'Restoring…');
  });
  function updateSendGate() { $('#send-email').disabled = !state.caps?.gmail_connected || !$('#send-confirmed').checked; }
  $('#send-confirmed').addEventListener('change',updateSendGate);
  // Any edit invalidates the previous review, including attachment and recipient changes.
  ['#send-recipient','#draft-subject','#draft-body','#attach-resume'].forEach(selector => $(selector).addEventListener('input',() => { $('#send-confirmed').checked = false; updateSendGate(); }));
  $('#copy-draft').addEventListener('click',async () => {
    if (!$('#draft-subject').value.trim() || !$('#draft-body').value.trim()) { toast('Prepare a subject and message before copying.',true); return; }
    try { await navigator.clipboard.writeText($('#draft-subject').value + '\n\n' + $('#draft-body').value); toast('Draft copied. Nothing has been sent.'); }
    catch { $('#draft-body').focus(); $('#draft-body').select(); toast('Clipboard access is unavailable. Your message is selected; copy it with your device’s copy action.',true); }
  });
  $('#send-form').addEventListener('submit',async event => {
    event.preventDefault();
    if (!state.caps?.gmail_connected || !$('#send-confirmed').checked) return;
    const payload = {to:$('#send-recipient').value.trim(),subject:$('#draft-subject').value,body:$('#draft-body').value,job_id:$('#draft-job').value,attach_original_resume:$('#attach-resume').checked,reviewed_and_confirmed:true};
    if (!window.confirm(`Send exactly ONE reviewed email to ${payload.to}?\nSubject: ${payload.subject}\nOriginal resume: ${payload.attach_original_resume ? 'attached' : 'not attached'}\nThis sends the email immediately.`)) return;
    await busy(event.submitter,async () => { try { const result = await post('/api/gmail/send',payload); feedback('#send-result',result.sent ? 'Email sent and recorded in your reviewed email history.' : 'The send was not confirmed. Check Gmail before retrying.',!result.sent); state.sent = (await api('/api/gmail/sent')).emails; renderSent(); } catch (error) { feedback('#send-result',error.message,true); } finally { $('#send-confirmed').checked = false; } },'Sending one email…'); updateSendGate();
  });
  $('#mail-ledger-list').addEventListener('click',async event=>{
    const btn=event.target.closest('[data-review-mail]');
    if(!btn)return;
    await busy(btn,async()=>{
      try{
        await api('/api/gmail/activity/'+encodeURIComponent(btn.dataset.reviewMail)+'/reviewed',
          {method:'PATCH',body:JSON.stringify({})});
        state.mailActivity=await api('/api/gmail/activity');
        renderMailLedger();renderDailyBrief();
      }catch(error){toast(error.message,true);}
    },'Saving…');
  });
  $('#gmail-check').addEventListener('click',async event => {
    await busy(event.currentTarget,async () => {
      try {
        const result = await api('/api/gmail/updates'); state.messages = result.messages;
        state.gmailOutbox=result.outbox||[];renderSent();
        try{state.mailActivity=await api('/api/gmail/activity');renderMailLedger();renderDailyBrief();}
        catch(error){toast('Inbox checked, but activity history could not refresh.',true);}
        if(result.imported_signals){
          try{state.radar=await api('/api/radar');renderRadar();}
          catch(error){toast('Inbox was checked, but the Radar could not reload.',true);}
        }
        state.caps.gmail_last_checked = result.checked_at;
        $('#gmail-last-checked').textContent = 'Last checked: ' + shortTime(result.checked_at);
        $('#gmail-messages').innerHTML = result.messages.length ? result.messages.map(message => `<article class="message-row"><h3>${esc(message.subject || '(No subject)')}</h3><small>${esc(message.from)} · ${esc(shortTime(message.date))}</small><span class="badge violet">${esc(message.stage)}</span>${message.possible_reply?'<span class="badge positive">Possible reply to outreach</span>':''}<p>${esc(message.snippet)}</p><small>${esc(message.reply_evidence||'Verify message context.')}</small><a class="text-link" href="https://mail.google.com/mail/u/0/#all/${encodeURIComponent(message.id)}" target="_blank" rel="noopener noreferrer">Review in Gmail ↗</a></article>`).join('') : empty('No recent matching replies','No relevant messages were returned from the past 21 days. No email was sent.','mail','',true);
        if (result.failed) $('#gmail-messages').insertAdjacentHTML('afterbegin',`<div class="detail-callout">${Number(result.failed)} messages could not be retrieved. These results are incomplete; check Gmail directly.</div>`);
        toast(result.failed ? `${result.failed} messages could not be loaded. Review the partial results in Gmail.` : 'Recruiter replies checked. No email was sent.',Boolean(result.failed));
      } catch (error) { $('#gmail-messages').innerHTML = empty('We couldn’t check your inbox',error.message,'info','',true); toast(error.message,true); }
    },'Checking replies…'); renderIntegrations();
  });
  $('#sent-refresh').addEventListener('click',event => busy(event.currentTarget,async () => { try { state.sent = (await api('/api/gmail/sent')).emails; renderSent(); } catch (error) { toast(error.message,true); } }));
  navigate(); renderExplore();
  loadData().catch(error => toast(error.message,true));
})();
