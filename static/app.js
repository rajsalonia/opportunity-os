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
  const PAGE_TITLES = {overview:'Overview',explore:'Explore opportunities',applications:'My applications',contacts:'Recruiter CRM',gmail:'Gmail & outreach',resume:'Resume vault',sources:'Career sources',settings:'Settings & integrations'};
  const state = {jobs:null,summary:null,alerts:null,contacts:null,caps:null,sources:null,sent:null,messages:null,page:'overview',limit:24,view:'board',refreshing:false};
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
      return (!query || `${job.company} ${job.title} ${geo}`.toLowerCase().includes(query)) && (!stage || job.status === stage) && score(job) >= minimum && (location === 'all' || (location === 'ncr' && ncr.test(geo)) || (location === 'india' && india.test(geo)) || (location === 'remote' && /remote/i.test(geo)));
    });
    records.sort((a,b) => {
      const sort = $('#sort-order').value;
      if (sort === 'company') return String(a.company).localeCompare(String(b.company));
      if (sort === 'newest') return String(b.discovered || '').localeCompare(String(a.discovered || ''));
      if (sort === 'deadline') return (dateOnly(a.deadline) || '9999').localeCompare(dateOnly(b.deadline) || '9999');
      return score(b)-score(a);
    });
    return records;
  }
  function jobCard(job) {
    const tracked = !['Discovered','Saved'].includes(job.status), saved = job.status === 'Saved';
    return `<article class="job-card"><div class="job-card-top">${avatar(job.company)}<div class="job-card-copy"><div class="company-name">${esc(job.company)}</div>${detailsButton(job)}<div class="job-card-meta"><span>${icon('pin')}${esc(job.location || 'Location not listed')}</span>${/remote/i.test(job.location || '') ? '<span class="badge">Remote listing</span>' : ''}<span class="provider-label">${esc(job.provider || 'Source not recorded')}</span>${job.deadline ? `<span>${icon('clock')}Deadline: ${esc(shortDate(job.deadline))}</span>` : ''}</div></div><div class="job-match" title="Estimated keyword match"><strong>${score(job)}<small> / 100</small></strong><small>EST. MATCH</small></div></div><div class="job-card-bottom"><span class="eligibility-label${job.warnings ? ' warning' : ''}">${icon('info')}${esc(job.warnings || 'Graduation eligibility unverified')}</span><span class="badge${job.status === 'Offer' ? ' positive' : ''}">${esc(job.status)}</span><button class="button" data-action="save" data-id="${esc(job.id)}" aria-pressed="${saved}"${tracked ? ' disabled title="Already tracked in your application pipeline"' : ''}>${icon(saved ? 'check' : 'bookmark')}${tracked ? 'Tracked' : saved ? 'Saved' : 'Save'}</button><button class="button" data-action="draft" data-id="${esc(job.id)}">${icon('mail')}Draft outreach</button>${officialLink(job,'button','Open listing')}</div></article>`;
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
  function resetFilters() { $('#filters').reset(); $('#sort-order').value = 'match'; state.limit = 24; renderExplore(); }
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
    const {default_boards:defaults,sources:custom,extended_boards:extended = []} = state.sources;
    const combined = new Map([...defaults,...extended].map(source => [source.provider + ':' + source.slug,{...source,custom:false}]));
    custom.forEach(source => combined.set(source.provider + ':' + source.slug,{...source,custom:true}));
    $('#source-summary').textContent = `${combined.size} configured boards · ${custom.length} custom · reachability checked on refresh`;
    $('#source-list').innerHTML = Array.from(combined.values()).map(source => {
      const boardUrl = ({greenhouse:'https://boards.greenhouse.io/',lever:'https://jobs.lever.co/',ashby:'https://jobs.ashbyhq.com/'})[source.provider];
      return `<div class="source-row"><div><strong>${esc(source.name)}</strong><small>${esc(source.provider)} / ${esc(source.slug)}</small></div><span class="mini-tag">${source.custom ? 'CUSTOM' : 'INCLUDED'}</span>${boardUrl ? `<a class="icon-button" href="${boardUrl + encodeURIComponent(source.slug)}" target="_blank" rel="noopener noreferrer" aria-label="Open ${esc(source.name)} board">${icon('external')}</a>` : ''}${source.custom ? `<button class="icon-button" data-action="remove-source" data-id="${esc(source.id)}" aria-label="Remove custom ${esc(source.name)} source">${icon('x')}</button>` : ''}</div>`;
    }).join('');
  }
  function renderSent() {
    if (!state.sent) return;
    $('#sent-emails').innerHTML = state.sent.length ? state.sent.map(email => `<article class="message-row"><h3>${esc(email.subject)}</h3><small>${esc(email.recipient)} · ${esc(shortTime(email.sent_at))}</small><span class="badge positive">${esc(email.status)}</span></article>`).join('') : empty('No sent messages yet','Emails you explicitly review and send here will be recorded in this history.','send','',true);
  }
  function renderAll() { renderOverview(); renderExplore(); renderApplications(); renderContacts(); renderSources(); renderIntegrations(); renderSent(); }
  const requests = [
    ['jobs','/api/jobs',data => data.jobs],['summary','/api/summary',data => data],['alerts','/api/alerts',data => data],
    ['caps','/api/integrations',data => data],['contacts','/api/contacts',data => data.contacts],
    ['sources','/api/sources',data => data],['sent','/api/gmail/sent',data => data.emails]
  ];
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
      const message = `${result.new} new roles from ${result.checked} boards. ${result.errors.length} boards unavailable.`;
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
    $('#job-detail-content').innerHTML = `<div class="detail-company">${avatar(job.company)}<div><strong>${esc(job.company)}</strong><small>${esc(job.provider || 'Source not recorded')} · Added ${esc(shortDate(job.discovered))}</small></div></div><h2 id="job-dialog-title">${esc(job.title)}</h2><div class="job-card-meta"><span>${icon('pin')}${esc(job.location || 'Location not listed')}</span><span class="match-pill">${score(job)}/100 estimated match</span></div>${officialLink(job,'button primary','Open official listing')}<div class="detail-callout">${esc(job.warnings || 'Graduation year and work authorization have not been verified.')} Check the official listing for eligibility, location requirements, and current availability. A match score is a keyword estimate.</div><div class="detail-description">${esc(job.description || 'No role description is available from this source. Open the original listing for the full details.')}</div>`;
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
  $('#gmail-check').addEventListener('click',async event => {
    await busy(event.currentTarget,async () => {
      try {
        const result = await api('/api/gmail/updates'); state.messages = result.messages;
        state.caps.gmail_last_checked = result.checked_at;
        $('#gmail-last-checked').textContent = 'Last checked: ' + shortTime(result.checked_at);
        $('#gmail-messages').innerHTML = result.messages.length ? result.messages.map(message => `<article class="message-row"><h3>${esc(message.subject || '(No subject)')}</h3><small>${esc(message.from)} · ${esc(shortTime(message.date))}</small><span class="badge violet">${esc(message.stage)}</span><p>${esc(message.snippet)}</p><a class="text-link" href="https://mail.google.com/mail/u/0/#all/${encodeURIComponent(message.id)}" target="_blank" rel="noopener noreferrer">Review in Gmail ↗</a></article>`).join('') : empty('No recent matching replies','No relevant messages were returned from the past 21 days. No email was sent.','mail','',true);
        if (result.failed) $('#gmail-messages').insertAdjacentHTML('afterbegin',`<div class="detail-callout">${Number(result.failed)} messages could not be retrieved. These results are incomplete; check Gmail directly.</div>`);
        toast(result.failed ? `${result.failed} messages could not be loaded. Review the partial results in Gmail.` : 'Recruiter replies checked. No email was sent.',Boolean(result.failed));
      } catch (error) { $('#gmail-messages').innerHTML = empty('We couldn’t check your inbox',error.message,'info','',true); toast(error.message,true); }
    },'Checking replies…'); renderIntegrations();
  });
  $('#sent-refresh').addEventListener('click',event => busy(event.currentTarget,async () => { try { state.sent = (await api('/api/gmail/sent')).emails; renderSent(); } catch (error) { toast(error.message,true); } }));
  navigate(); renderExplore();
  loadData().catch(error => toast(error.message,true));
})();
