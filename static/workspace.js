'use strict';
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon=(name,cls='')=>`<svg class="icon ${cls}" aria-hidden="true"><use href="/static/vendor/lucide/icons.svg#${name}"/></svg>`;
const button=(label,action,extra='',style='')=>`<button class="button ${style}" data-action="${action}" ${extra}>${label}</button>`;
const safeURL=value=>{try{const u=new URL(value);return u.protocol==='https:'&&!u.username&&!u.password?u.href:'#';}catch{return '#';}};
const link=(label,url,cls='button')=>`<a class="${cls}" href="${esc(safeURL(url))}" target="_blank" rel="noopener noreferrer">${label}</a>`;
const fmt=(value,options={})=>{if(!value)return 'Not recorded';try{return new Intl.DateTimeFormat('en-IN',{day:'numeric',month:'short',...options,timeZone:'Asia/Kolkata'}).format(new Date(/^\d{4}-\d\d-\d\d$/.test(value)?value+'T12:00:00+05:30':value));}catch{return String(value).slice(0,30);}};
const isoDay=d=>new Intl.DateTimeFormat('en-CA',{year:'numeric',month:'2-digit',day:'2-digit',timeZone:'Asia/Kolkata'}).format(d);
const state={page:'today',pageNumber:1,filters:{},items:new Map(),selected:new Set(),bootstrap:null,settings:'profile',detailTab:'overview',detail:null,calendarView:'month',calendarDate:new Date(),mailFilter:'all',account:'',request:0,sourceData:null};
let toastTimer,searchTimer;
function toast(message){$('#toast').textContent=message;$('#toast').classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.remove('show'),5000);}
async function api(path,options={}){
  const response=await fetch(path.startsWith('/api/')?path:'/api/v3/'+path,{credentials:'same-origin',...options,headers:{'Content-Type':'application/json','X-CSRF-Token':$('meta[name=csrf-token]').content,...options.headers}});
  const data=await response.json().catch(()=>({error:'The server returned an unexpected response. Please retry.'}));
  if(response.status===401){location.href='/';throw new Error('Sign in again to continue.');}
  if(!response.ok)throw new Error(data.error||'This action could not be completed. Your saved records are preserved.');
  return data;
}
function mutate(path,data={},method='POST'){return api(path,{method,body:JSON.stringify(data)});}
function empty(title,message,action='discover'){return `<div class="empty-state">${icon('compass')}<h3>${esc(title)}</h3><p>${esc(message)}</p>${action?button('Explore opportunities','navigate',`data-page="${action}"`):''}</div>`;}
function heading(eyebrow,title,subtitle,actions=''){return `<div class="page-heading"><div><div class="eyebrow">${esc(eyebrow)}</div><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div><div class="heading-actions">${actions}</div></div>`;}
function tag(label,cls=''){return `<span class="tag ${cls}">${esc(label)}</span>`;}
function eligibilityTag(item){const code=item.eligibility.code;return tag(({eligible:'Eligible · verify before applying',likely:'Likely eligible',unknown:'Eligibility needs review',ineligible:'Eligibility conflict',closed:'Closed or expired'})[code],code==='eligible'||code==='likely'?'success':code==='ineligible'||code==='closed'?'danger':'warning');}
function remember(items){items.forEach(x=>state.items.set(x.key,x));return items;}
function card(item){
  // Put the decision in the card; keep long requirements inside Details.
  const f=item.extracted,fields=f.fields,key=esc(item.key),deadline=f.deadline;
  const company=String(item.company||'Organizer not disclosed');
  const pay=fields.compensation.value||'Pay not disclosed';
  const mode=f.work_mode||'Work mode unknown';
  const reason=(item.eligibility.code==='ineligible'?item.eligibility.reasons[0]:item.recommendation.reasons[0])
    ||'Read the employer requirements before applying.';
  const checklist=item.checklist||{done:0,total:0};
  const prepLabel=checklist.total
    ?'Checklist '+(checklist.done||0)+'/'+checklist.total
    :'Start checklist';
  const rawSummary=String(item.summary||'').replace(/\\s+/g,' ').trim();
  const summary=rawSummary.length>240?rawSummary.slice(0,237).replace(/\\s+\\S*$/,'')+'…':rawSummary;
  const sourceTitle=String(item.provider||item.source||'Owner-added source');
  const timeLabel=item.published
    ?'Published '+fmt(item.published,{year:'numeric'})
    :'Discovered '+fmt(item.first_seen,{year:'numeric'});
  return `<article class="card opportunity-card" data-key="${key}">
    <div class="card-top">
      <div class="company-avatar" aria-hidden="true">${esc(company.slice(0,1))}</div>
      <div class="card-identity">
        <div class="company-line">${esc(company)} ${tag(item.category)}</div>
        <button class="card-title" data-action="detail" data-key="${key}">${esc(item.title)}</button>
      </div>
      <button class="icon-button save-button ${item.saved?'selected':''}" data-action="save"
        data-key="${key}" aria-label="${item.saved?'Unsave':'Save'} ${esc(item.title)}"
        aria-pressed="${Boolean(item.saved)}">${icon('bookmark')}</button>
    </div>
    <div class="card-meta">
      <span>${icon('map-pin')}${esc(item.location||'Location unknown')}</span>
      <span>${icon('globe')}${esc(mode)}</span>
      <span>${icon('banknote')}${esc(pay)}</span>
    </div>
    <div class="tags">
      ${eligibilityTag(item)}
      ${tag(item.recommendation.bucket,'accent')}
      ${deadline.date?tag('Employer deadline: '+fmt(deadline.utc||deadline.date),'accent'):tag('Deadline not stated')}
      ${item.stage!=='Discovered'?tag(item.stage):''}
      ${item.pinned?tag('Pinned','accent'):''}
    </div>
    ${!['Applied','Assessment','Interview','Offer','Rejected','Withdrawn','Closed'].includes(item.stage)
      ?`<p class="card-next-action">${icon('calendar-days')} Suggested review: ${esc(fmt(item.recommendation.suggested_action_date,{year:'numeric'}))} <small>(not an official deadline)</small></p>`:''}
    ${summary?`<p class="card-summary">${esc(summary)}</p>`:''}
    <p class="why-line">${icon(item.eligibility.code==='ineligible'?'circle-alert':'circle-question-mark')}
      <span><strong>${item.eligibility.code==='ineligible'?'Eligibility warning:':'Why consider it:'}</strong> ${esc(reason)}</span>
    </p>
    <div class="card-footer">
      <span class="source-label">${esc(sourceTitle)} · ${timeLabel}
      ${deadline.date&&!deadline.cutoff_known?' · Deadline time unknown':''}</span>
      <label class="checkbox-inline"><input type="checkbox" data-compare="${key}"
        ${state.selected.has(item.key)?'checked':''}>Compare</label>
    </div>
    <div class="card-action-bar">
      ${button('Details '+icon('arrow-right'),'detail',`data-key="${key}"`,'soft')}
      ${button(icon('list-checks')+esc(prepLabel),'checklist',`data-key="${key}"`)}
      ${link('Open source '+icon('external-link'),item.url,'button primary')}
    </div>
  </article>`;
}
function mini(item){return `<button class="mini-row" data-action="detail" data-key="${esc(item.key)}"><span class="company-avatar">${esc((item.company||'O')[0])}</span><span class="row-copy"><strong>${esc(item.title)}</strong><small>${esc(item.company)} · ${fmt(item.first_seen)}</small></span>${icon('arrow-up-right')}</button>`;}
function deadlineRow(event){return `<button class="deadline-row" data-action="${event.opportunity_key?'detail':'event-info'}" data-key="${esc(event.opportunity_key||'')}" data-event="${esc(event.title)}"><span class="date-tile">${esc((event.deadline.local_date||event.deadline.date).slice(8))}<small>${esc(fmt(event.deadline.local_date||event.deadline.date,{month:'short',day:undefined}).toUpperCase())}</small></span><span><strong>${esc(event.title)}</strong><p>${esc(event.kind)} · ${event.deadline.cutoff_known?fmt(event.deadline.utc,{hour:'numeric',minute:'2-digit'}):'Exact cutoff unknown'}</p></span></button>`;}
async function renderToday(ticket){
  const data=await api('today');if(ticket!==state.request)return;
  remember([...data.recommended,...data.research_first,...data.recently_discovered,...data.pinned]);
  const hour=Number(new Intl.DateTimeFormat('en-GB',{hour:'numeric',timeZone:'Asia/Kolkata'}).format(new Date()));
  const greeting=hour<12?'Good morning':hour<17?'Good afternoon':'Good evening';
  const urgent=data.apply_today||[];
  const recommended=urgent.length?urgent:data.recommended.length?data.recommended:data.research_first;
  const isResearch=!data.recommended.length;
  const headingLabel=urgent.length?'Apply or review today':isResearch?'Worth a closer look':'Worth reviewing this week';
  const upcoming=[...data.deadlines.today,...data.deadlines.week,...data.deadlines.month].slice(0,4);
  $('#content').innerHTML=heading(fmt(data.date,{weekday:'long',year:'numeric'}),`${greeting}, Raj.`,'A little focus today. A step closer to what’s next.',button(icon('refresh-cw')+'Refresh sources','refresh','','optional')+button('Find opportunities '+icon('arrow-right'),'navigate','data-page="discover"','primary'))+
   `<section class="focus-strip" aria-label="Your priorities">${data.priorities.map((p,i)=>`<button class="focus-item" data-action="navigate" data-page="${p.action}" ${p.filter?'data-filter="'+p.filter+'"':''}>${icon(['compass','clock','inbox','bell'][i])}<div><strong>${p.count}</strong><span>${esc(p.title)}</span></div></button>`).join('')}</section><div class="dashboard-grid"><div><section class="section-block"><div class="section-heading"><div><h2>${headingLabel}</h2><p>${isResearch?'These leads need eligibility checks before you prepare.':'Based on your profile, stated requirements, and recorded source evidence.'}</p></div><button class="text-button" data-action="navigate" data-page="discover">View all ${icon('arrow-right')}</button></div>${recommended.length?recommended.slice(0,3).map(card).join(''):empty('Your next opportunity starts here','Refresh connected sources or add an official listing to start reviewing relevant opportunities.')}</section>${data.pinned.length?`<section class="section-block"><div class="section-heading"><h2>Your focus list ${tag('Pinned')}</h2></div><div class="card mini-list">${data.pinned.map(mini).join('')}</div></section>`:''}<section class="section-block"><div class="section-heading"><div><h2>Since your last visit <span class="count">${data.recently_discovered.length}</span></h2><p>${data.last_visit?'Newly discovered after '+fmt(data.last_visit,{hour:'numeric',minute:'2-digit'}):'Your most recently discovered records. No previous visit is recorded yet.'}</p></div></div><div class="card mini-list">${data.recently_discovered.length?data.recently_discovered.slice(0,4).map(mini).join(''):'<p class="empty-inline">No newly discovered records since your last recorded visit.</p>'}</div></section></div><aside class="dashboard-side"><section class="side-card"><div class="side-title">${icon('calendar-days')}On the horizon</div>${upcoming.length?upcoming.map(deadlineRow).join(''):'<p class="empty-inline">No upcoming deadlines are recorded. Add verified dates as you review official listings.</p>'}<p class="muted small-text" style="margin-top:13px">${data.undated_count} opportunities have no stated deadline.</p><button class="text-button" data-action="navigate" data-page="calendar">Open calendar ${icon('arrow-right')}</button></section><section class="side-card"><div class="side-title">${icon('sparkles')}A clearer next step</div><p class="muted small-text">Compare opportunities, understand eligibility, or turn recorded requirements into a preparation plan.</p><button class="button full-width" style="margin-top:17px" data-action="assistant">Ask Opportunity Intelligence ${icon('arrow-up-right')}</button></section><section class="side-card"><div class="side-title">${icon('clock')}Your recent activity</div>${data.activity.length?data.activity.slice(0,5).map(row=>`<div class="activity-item"><span class="activity-dot"></span><div><strong>${esc(row.event.replaceAll('_',' '))}</strong>${fmt(row.created_at,{hour:'numeric',minute:'2-digit'})} · ${esc(row.actor)}</div></div>`).join(''):'<p class="empty-inline">Your saved actions and application updates will appear here.</p>'}</section><div class="health-note">${icon('shield-check')}<div id="today-health">Source freshness is shown per connection.<a href="#settings/sources">Review source health</a></div></div></aside></div>`;
  $('#count-saved').textContent=data.counts.saved||'';$('#count-applications').textContent=data.counts.applications||'';
  // Record a visit only after the previous-visit view has been rendered successfully.
  mutate('visit').catch(()=>{});
  api('sources').then(health=>{if(state.page!=='today')return;const checked=health.sources.filter(x=>x.last_success);const degraded=health.sources.filter(x=>['degraded','cooldown'].includes(x.status));$('#today-health').innerHTML=`${checked.length} sources have a successful recorded check.${degraded.length?' '+degraded.length+' need attention.':''}<a href="#settings/sources">Review freshness & coverage</a>`;}).catch(()=>{if($('#today-health'))$('#today-health').innerHTML='Source health is temporarily unavailable. Cached records remain usable.<a href="#settings/sources">Retry in source settings</a>';});
}
function option(value,label,current){return `<option value="${esc(value)}" ${String(value)===String(current)?'selected':''}>${esc(label)}</option>`;}
function filters(){
  const f=state.filters;
  const choice=(name,label,values)=>`<select name="${name}" aria-label="${label}">${values.map(([v,t])=>option(v,t,f[name])).join('')}</select>`;
  const primary=[
    choice('type','Opportunity type',[['','All types'],['Internship','Internships'],['Job','Jobs'],['Hackathon','Hackathons'],['Event','Events'],['Fellowship','Fellowships'],['Scholarship','Scholarships'],['Community','Community leads']]),
    choice('eligibility','Eligibility',[['','All eligibility'],['actionable','Eligible / likely'],['unknown','Needs verification'],['ineligible','Conflicts'],['closed','Closed']]),
    choice('priority','Recommended next action',[['','All priorities'],['Apply today','Apply today'],['Deadline approaching','Deadline approaching'],['Worth reviewing this week','Review this week'],['Research first','Research first'],['Already applied','Already applied'],['Not eligible','Not eligible']]),
    choice('location','Location',[['','All locations'],['india','India'],['ncr','Delhi NCR']])
  ];
  const advanced=[
    choice('mode','Work arrangement',[['','All work modes'],['Remote','Remote'],['Hybrid','Hybrid'],['On-site','On-site']]),
    choice('paid','Compensation',[['','Any compensation'],['yes','Paid stated']]),
    choice('year','Stated graduation year',[['','Any graduation year'],['2028','2028 stated'],['2027','2027 stated']]),
    choice('source','Source provider',[['','All sources'],['greenhouse','Greenhouse'],['lever','Lever'],['ashby','Ashby'],['smartrecruiters','SmartRecruiters'],['Brabble','Brabble'],['DEV','DEV'],['Hacker','Hacker News'],['arbeitnow','Arbeitnow'],['jobicy','Jobicy'],['remotive','Remotive']]),
    choice('deadline','Deadline period',[['','Any deadline'],['today','Due today'],['week','Next 7 days'],['month','Next 30 days'],['undated','No stated deadline']]),
    choice('sort','Sort',[['priority','Priority'],['recent','Recently discovered'],['deadline','Deadline'],['company','Company']])
  ];
  const active=['mode','paid','year','source','deadline','sort'].some(k=>f[k]&&f[k]!=='priority');
  return `<form id="search-form" class="filters-panel">
    <div class="search-row">
      <div class="search-box">${icon('search')}<input name="q" value="${esc(f.q||'')}"
        aria-label="Search opportunities" placeholder="Paid remote Python internships in India"></div>
      <button class="button primary" type="submit">Search</button>
      ${button(icon('plus')+'Add listing','add-listing')}
    </div>
    <div class="filter-row filter-primary">${primary.join('')}</div>
    <details class="filter-advanced" ${active?'open':''}>
      <summary>${icon('sliders-horizontal')} Advanced filters ${active?tag('Active'):''}</summary>
      <div class="filter-row">${advanced.join('')}</div>
    </details>
  </form>`;
}
async function renderOpportunities(ticket){
  const page=state.page,view=page==='saved'?'saved':page==='applications'?'applications':state.filters.view||'discover';
  const params=new URLSearchParams({...state.filters,view,page:state.pageNumber,size:18});
  const data=await api('opportunities?'+params);if(ticket!==state.request)return;remember(data.items);
  const titles={discover:['Your next chapter','Discover opportunities','Real leads. Clear requirements. Choose what deserves your time.'],saved:['A shortlist with intention','Saved opportunities','Keep the opportunities you want to return to.'],applications:['From preparation to progress','Your applications','Every step tracked. Every submission explicitly confirmed.']};
  $('#content').innerHTML=heading(...titles[page],button(icon('refresh-cw')+'Refresh sources','refresh'))+filters()+`<div class="search-summary"><span>${data.total} ${view==='applications'?'tracked':'matching'} opportunities${Object.keys(data.interpreted_filters).length?' · Search interpreted: '+esc(Object.entries(data.interpreted_filters).map(([k,v])=>k+': '+v).join(', ')):''}</span><button class="text-button" data-action="clear-filters">Reset filters</button></div>`+
   (data.items.length?(page==='applications'?applicationTable(data.items):`<div class="opportunities-grid">${data.items.map(card).join('')}</div>`):empty(page==='saved'?'Build your personal shortlist':'No matches in this view',page==='saved'?'Save an opportunity using its bookmark. It stays here as you research and prepare.':'Broaden the filters or refresh sources. Missing requirements are shown as unknown.'))+
   `<div class="pagination">${button(icon('chevron-left')+'Previous','previous',state.pageNumber===1?'disabled':'')}<span>Page ${data.page} · ${data.total} records</span>${button('Next '+icon('chevron-right'),'next',!data.has_more?'disabled':'')}</div><div id="compare-bar"></div>`;
  renderCompare();
}
function applicationTable(items){return `<div class="table-wrap"><table><thead><tr><th>Opportunity</th><th>Stage</th><th>Preparation</th><th>Submission evidence</th><th>Last update</th></tr></thead><tbody>${items.map(r=>`<tr><td><button class="card-title" data-action="detail" data-key="${esc(r.key)}">${esc(r.title)}</button><small>${esc(r.company)}</small></td><td>${tag(r.stage,'accent')}<small>${esc(r.substate||'')}</small></td><td>${r.checklist.done||0}/${r.checklist.total||0} checklist items<div class="progress-track"><span style="width:${100*(r.checklist.done||0)/Math.max(1,r.checklist.total||0)}%"></span></div></td><td>${esc(r.submission_evidence.kind)}<small>Checklist completion does not mean submitted.</small></td><td>${fmt(r.updated||r.first_seen)}</td></tr>`).join('')}</tbody></table></div>`;}
function renderCompare(){const bar=$('#compare-bar');if(bar)bar.innerHTML=state.selected.size?`<div class="compare-bar"><span>${state.selected.size} of 2 selected</span>${button('Compare with Intelligence','assistant')}${state.selected.size===2?button('Group duplicate records','merge-form'):''}<button class="text-button" data-action="clear-compare">Clear selection</button></div>`:'';$('#compare-context').textContent=state.selected.size?'Using selected opportunities: '+[...state.selected].map(k=>state.items.get(k)?.title||k).join(' · '):'No opportunities selected. Answers use your current recorded profile and opportunity evidence.';}
async function showDetail(key,tab='overview'){
  const data=await api('opportunities/'+encodeURIComponent(key));state.detail=data;state.detailTab=tab;remember([data]);renderDetail();if(!$('#detail-dialog').open)$('#detail-dialog').showModal();
}
function fact(label,value){return `<div class="detail-fact"><small>${esc(label)}</small><strong>${esc(Array.isArray(value)?value.join(', '):value||'Not disclosed')}</strong></div>`;}
function renderDetail(){
  const x=state.detail,f=x.extracted,k=esc(x.key),field=n=>f.fields[n]?.value;
  $('#detail-content').innerHTML=`<div class="dialog-heading"><div class="company-avatar">${esc((x.company||'O')[0])}</div><div><p>${esc(x.company)} · ${esc(x.category)}</p><h2 id="detail-title">${esc(x.title)}</h2></div><button class="icon-button" data-close aria-label="Close opportunity">${icon('x')}</button></div><div class="dialog-body"><div class="tabs" aria-label="Opportunity details">${[['overview','Overview'],['checklist','Preparation checklist'],['tracking','Track & history']].map(([id,label])=>`<button data-detail-tab="${id}" class="${state.detailTab===id?'active':''}">${label}</button>`).join('')}</div><div class="tags">${eligibilityTag(x)}${tag(x.stage,'accent')}${x.stale?tag('Freshness needs verification','warning'):tag('Source checked '+fmt(x.last_checked))}</div><div class="detail-actions">${link('Open official / source page '+icon('external-link'),x.url,'button primary')}${button(icon('bookmark')+(x.saved?'Saved':'Save'),'detail-save',`data-key="${k}"`)}${button(icon('pin')+(x.pinned?'Unpin':'Pin'),'pin',`data-key="${k}"`)}${button(icon('sparkles')+'Explain this','explain',`data-key="${k}"`)}</div><p class="muted small-text">Opening a page or finishing preparation never marks an application as submitted.</p>${state.detailTab==='overview'?detailOverview(x):state.detailTab==='checklist'?detailChecklist(x):detailTracking(x)}</div>`;
}
function detailOverview(x){const f=x.extracted,field=n=>f.fields[n]?.value;return `<p class="detail-summary">${esc(x.summary)}</p><div class="detail-grid">${fact('Location',x.location)}${fact('Work mode / remote scope',f.work_mode+' · '+f.remote_scope)}${fact('Compensation',field('compensation'))}${fact('Duration / start',field('duration')||field('start_date'))}${fact('Graduation requirements',field('graduation_years'))}${fact('Degree / experience',field('degree')||field('experience'))}${fact('Actual deadline',f.deadline.date?fmt(f.deadline.utc||f.deadline.date,{year:'numeric'})+(f.deadline.cutoff_known?' · '+fmt(f.deadline.utc,{hour:'numeric',minute:'2-digit'}):' · Exact cutoff unknown'):'Not stated')}${fact('Suggested review date',x.recommendation.suggested_action_date+' · not an employer deadline')}${fact('Published',x.published?fmt(x.published,{year:'numeric'}):'Not disclosed')}${fact('First discovered',fmt(x.first_seen,{year:'numeric'}))}${fact('Last source check',x.last_checked?fmt(x.last_checked,{year:'numeric'}):'Not freshly checked')}${fact('Priority',x.recommendation.score+' points · rules, not acceptance probability')}</div><section class="detail-section"><h3>Understand your eligibility</h3><ul>${x.eligibility.reasons.map(r=>`<li>${esc(r)}</li>`).join('')}</ul>${x.eligibility.evidence.map(q=>`<blockquote class="evidence-quote">${esc(q)}</blockquote>`).join('')}${x.eligibility_override?`<p>Owner review: ${esc(x.eligibility_override.reason||'Recorded correction')}</p>`:''}<form id="correction-form"><label for="correction-reason">Add an evidence-based correction</label><textarea id="correction-reason" name="reason" minlength="12" maxlength="1500" placeholder="Record an employer clarification. Original requirements remain visible." required></textarea><label for="correction-source">Official evidence URL</label><input id="correction-source" name="source_url" type="url" placeholder="https://…"><button class="text-button" type="submit">Save review note</button></form></section><section class="detail-section"><h3>Skills & preparation</h3><p>Recorded overlap: ${esc(x.recommendation.matched_skills.join(', ')||'Not established')}</p><p>Verify or develop: ${esc(x.recommendation.skills_to_verify.join(', ')||'No additional skills extracted; read the full listing.')}</p><div class="detail-actions">${button('Create preparation checklist','prepare',`data-key="${esc(x.key)}"`,'soft')}${button('Add deadline or reminder','add-event',`data-key="${esc(x.key)}"`)}</div></section><section class="detail-section"><h3>About ${esc(x.company)}</h3><p>${esc(x.company_summary.description)}</p><div class="detail-grid">${fact('Industry',x.company_summary.industry)}${fact('Company type',x.company_summary.company_type)}${fact('Size',x.company_summary.size)}${fact('Headquarters',x.company_summary.headquarters)}</div><p>${esc(x.company_summary.interpretation)}</p></section><section class="detail-section"><h3>Information to check</h3><ul>${x.warnings.map(w=>`<li>${esc(w)}</li>`).join('')}</ul></section><section class="detail-section"><h3>Original recorded description</h3><div class="detail-description">${esc(f.description||'Description not supplied. Review the official source.')}</div></section><section class="detail-section"><h3>Source evidence · ${x.source_records.length}</h3>${x.source_records.map(r=>`<p>${link(esc(r.name),r.url,'text-button')} · ${esc(r.status)} · ${r.last_seen?'Checked '+fmt(r.last_seen):'No recent check'}</p>`).join('')}<p class="muted">${x.related_keys.length>1?'Canonical duplicates grouped; original records retained.':''}</p>${x.related_keys.filter(key=>key!==x.key).map(key=>button('Undo owner duplicate link','unmerge',`data-key="${esc(key)}"`)).join('')}</section><section class="detail-section"><h3>Help improve your recommendations</h3><div class="feedback-row">${state.bootstrap.feedback.map(label=>button(esc(label),'feedback',`data-kind="${esc(label)}" data-key="${esc(x.key)}"`)).join('')}</div><p style="margin-top:10px">Feedback can adjust priorities; it cannot change hard employer requirements.</p></section><section class="detail-section"><div class="detail-actions">${button(x.archived?'Restore from archive':'Archive','archive',`data-key="${esc(x.key)}"`)}${button(x.dismissed?'Restore dismissed lead':'Dismiss lead','dismiss',`data-key="${esc(x.key)}"`)}</div></section>`;}
function detailChecklist(x){const rows=x.checklist_items||[];return `<div class="detail-section"><h3>Prepare with intention</h3><p>Each check is independently editable and saved. Completing every item does not record a submission.</p>${!rows.length?button('Create checklist','prepare',`data-key="${esc(x.key)}"`,'primary'):''}${[...new Set(rows.map(r=>r.phase))].map(phase=>`<div class="checklist-group"><h3>${esc(phase)}</h3>${rows.filter(r=>r.phase===phase).map(r=>`<div class="checklist-item ${r.completed?'completed':''}"><input type="checkbox" id="check-${esc(r.id)}" data-check-id="${esc(r.id)}" ${r.completed?'checked':''}><label class="check-text" for="check-${esc(r.id)}">${esc(r.label)}</label><button class="icon-button" data-action="edit-check" data-id="${esc(r.id)}" aria-label="Edit checklist item">${icon('sliders-horizontal')}</button></div>`).join('')}</div>`).join('')}<form id="add-check-form" class="inline-form"><label for="new-check">Add your own preparation step</label><div class="input-action"><input id="new-check" name="label" required minlength="3" maxlength="300" placeholder="A specific step for this opportunity"><button class="button" type="submit">Add item</button></div></form></div>`;}
function detailTracking(x){return `<section class="detail-section"><form id="tracking-form"><div class="form-grid"><div><label for="stage">Application stage</label><select id="stage" name="stage">${state.bootstrap.stages.map(s=>option(s,s,x.stage)).join('')}</select></div><div><label for="substate">Follow-up state</label><select id="substate" name="substate">${state.bootstrap.substates.map(s=>option(s,s||'No additional state',x.substate)).join('')}</select></div><div class="full"><label for="track-notes">Your notes</label><textarea id="track-notes" name="notes" maxlength="4000" placeholder="What matters for your next step?">${esc(x.notes||'')}</textarea></div><div class="full"><label for="submission-ref">Employer acknowledgement or submission reference</label><input id="submission-ref" name="reference" maxlength="400" placeholder="Optional receipt ID, confirmation link, or factual note"></div><div class="full"><label class="check-label"><input type="checkbox" name="submitted_by_owner"><span>I actually submitted this application on the employer’s site. Recording Applied is an owner report unless an employer API receipt exists.</span></label></div></div><button type="submit" class="button primary" style="margin-top:18px">Save tracking update</button></form></section><section class="detail-section"><h3>Submission evidence</h3><p>${esc(x.submission_evidence.kind)}</p>${x.receipts.map(r=>`<blockquote class="evidence-quote">${esc(r.evidence_type)} · ${esc(r.reference)}<br>${fmt(r.created_at,{year:'numeric',hour:'numeric',minute:'2-digit'})}</blockquote>`).join('')}</section><section class="detail-section"><h3>Recorded history</h3>${x.timeline.length?x.timeline.map(r=>`<div class="activity-item"><span class="activity-dot"></span><div><strong>${esc(r.event.replaceAll('_',' '))}</strong>${fmt(r.created_at,{year:'numeric',hour:'numeric',minute:'2-digit'})} · ${esc(r.actor)}<br>${esc(r.after_data||'').slice(0,250)}</div></div>`).join(''):'<p>No version 3.0 history has been recorded yet. Older stage changes may not have an audit trail.</p>'}</section>`;}
async function renderInbox(ticket){
  const data=await api('inbox'+(state.account?'?account='+encodeURIComponent(state.account):''));if(ticket!==state.request)return;state.mailData=data;
  const rows=data.messages.filter(r=>state.mailFilter==='all'||state.mailFilter==='unreviewed'&&!r.reviewed||state.mailFilter==='sent'&&r.direction==='outbound'||state.mailFilter==='signals'&&['Possible interview','Possible assessment','Possible offer','Possible human reply'].includes(r.category));
  $('#content').innerHTML=heading('The conversation continues','Your inbox','Read the signal. Review the original. Decide your next step.','<a class="button" href="/api/v3/gmail/connect">Connect another Gmail '+icon('plus')+'</a>')+`<div class="notice">${esc(data.scan_scope)} Messages are classified provisionally; application stages never change automatically.</div><div class="inbox-toolbar" style="margin-top:20px"><select id="mail-account" aria-label="Gmail account">${option('','All accounts & historical records',state.account)}${data.accounts.map(a=>option(a.id,a.email,state.account)).join('')}</select><select id="mail-filter" aria-label="Filter mail">${[['all','All stored messages'],['unreviewed','Unreviewed'],['signals','Recruiter signals'],['sent','Sent activity']].map(x=>option(...x,state.mailFilter)).join('')}</select>${button(icon('refresh-cw')+'Scan relevant mail','mail-refresh')}<a class="text-button" href="/classic#gmail">Review & compose an email ${icon('arrow-up-right')}</a></div><div class="tags" style="margin-bottom:16px">${data.accounts.map(a=>tag(a.email+' · '+a.status+(a.last_checked?' · '+fmt(a.last_checked):''),a.status==='connected'?'success':'warning')).join('')}</div><div class="card" style="padding:0">${rows.length?rows.map(r=>`<article class="mail-row"><div class="mail-avatar">${esc((r.sender||'M')[0])}</div><div class="mail-copy"><div class="mail-meta"><span>${esc(r.sender)}</span><span>${fmt(r.date,{year:'numeric'})}</span>${tag(r.category||'Needs review',r.human_reply?'success':'')}${r.reviewed?tag('Reviewed'):tag('Unreviewed','accent')}</div><h3>${esc(r.subject||'(No subject)')}</h3><p>${esc(r.snippet)}</p><p style="font-size:9px">${esc(r.account_email)} · ${esc(r.reply_evidence)}</p>${r.attachments.length?`<p>Attachment metadata: ${r.attachments.map(a=>esc(a.filename)).join(', ')}. Contents not downloaded.</p>`:''}<div class="mail-actions">${link('Open original in Gmail '+icon('external-link'),r.gmail_url)}${!r.reviewed?button('Mark reviewed','mail-reviewed',`data-id="${esc(r.id)}"`):''}</div></div></article>`).join(''):empty('No mail in this view','Connect an account or scan your existing connection. Historical records are retained, with their identity uncertainty clearly labelled.','')}</div><p class="muted small-text" style="margin-top:15px">${esc(data.legacy_send)} ${data.running_accounts.length?'A background scan is running. Refresh this view shortly.':''}</p>`;
}
function calendarDateTitle(){return fmt(isoDay(state.calendarDate),{month:'long',year:'numeric',day:undefined});}
async function renderCalendar(ticket){
  const data=await api('calendar');if(ticket!==state.request)return;state.events=data.events;
  $('#content').innerHTML=heading('Make room for what matters','Your calendar','Real deadlines and your reminders, displayed in Asia/Kolkata.',`<a href="/api/v3/calendar.ics" class="button optional">${icon('download')}Export ICS</a>`+button(icon('plus')+'Add event','add-event','','primary'))+`<div class="calendar-toolbar"><div style="display:flex;gap:10px;align-items:center">${button(icon('chevron-left'),'calendar-prev','aria-label="Previous period"')}<h2>${calendarDateTitle()}</h2>${button(icon('chevron-right'),'calendar-next','aria-label="Next period"')}</div><div class="segmented" aria-label="Calendar view">${['day','week','month','agenda'].map(v=>`<button data-calendar-view="${v}" class="${v===state.calendarView?'active':''}">${v[0].toUpperCase()+v.slice(1)}</button>`).join('')}</div></div><div class="notice" style="margin-bottom:18px">Date-only deadlines have an unknown cutoff time. Suggested action dates are kept separate from official deadlines. Source time zones are retained in details and ICS.</div><div id="calendar-body">${calendarBody()}</div>`;
}
function calendarBody(){
  const d=state.calendarDate,view=state.calendarView,items=state.events;
  if(view==='month'){
    const first=new Date(d.getFullYear(),d.getMonth(),1,12);const start=new Date(first);start.setDate(1-(first.getDay()+6)%7);
    return `<div class="calendar-grid">${['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(day=>`<div class="calendar-weekday">${day}</div>`).join('')}${Array.from({length:42},(_,i)=>{const day=new Date(start);day.setDate(start.getDate()+i);const iso=isoDay(day);const events=items.filter(e=>isoDay(new Date(e.deadline.utc||e.deadline.date+'T12:00:00+05:30'))===iso);return `<div class="calendar-day ${day.getMonth()!==d.getMonth()?'other-month':''} ${iso===isoDay(new Date())?'is-today':''}"><span>${day.getDate()}</span>${events.slice(0,3).map(e=>`<button class="calendar-event" data-action="${e.opportunity_key?'detail':'event-info'}" data-key="${esc(e.opportunity_key||'')}" data-event="${esc(e.title)}">${esc(e.title)}</button>`).join('')}${events.length>3?`<small class="desktop-more">+${events.length-3} more</small>`:''}${events.length?`<button class="calendar-day-summary" data-calendar-day="${iso}" aria-label="${events.length} events on ${iso}">${events.length} event${events.length===1?'':'s'}</button>`:''}</div>`;}).join('')}</div>`;
  }
  const start=new Date(d);start.setHours(0,0,0,0);if(view==='week')start.setDate(start.getDate()-(start.getDay()+6)%7);const end=new Date(start);end.setDate(start.getDate()+(view==='day'?1:view==='week'?7:366));
  const visible=items.filter(e=>{const date=new Date(e.deadline.utc||e.deadline.date+'T12:00:00+05:30');return date>=start&&date<end;});
  return visible.length?`<div class="card">${visible.map(e=>`<div class="agenda-date">${fmt(e.deadline.utc||e.deadline.date,{weekday:'long',year:'numeric'})}</div>${deadlineRow(e)}<p class="muted small-text">${esc(e.source||'Your calendar')} · Source time zone: ${esc(e.deadline.timezone)} ${e.deadline.cutoff_known?'':'· Exact cutoff unknown'}${e.reminder_minutes!=null?' · Reminder '+e.reminder_minutes+' minutes before':''}</p>${e.id.startsWith('source-')?'':button('Remove reminder','delete-event',`data-id="${esc(e.id)}"`)}`).join('')}</div>`:empty('Nothing scheduled for this period','Add a reminder or record a verified deadline while reviewing an opportunity.','');
}
function showSimpleForm(title,bodyHTML,id){$('#detail-content').innerHTML=`<div class="dialog-heading"><h2 id="detail-title">${esc(title)}</h2><button class="icon-button" data-close aria-label="Close form">${icon('x')}</button></div><form id="${id}" class="dialog-body">${bodyHTML}<button class="button primary" type="submit" style="margin-top:20px">Save</button></form>`;if(!$('#detail-dialog').open)$('#detail-dialog').showModal();}
function eventForm(key=''){
  const item=key?state.items.get(key):null;
  showSimpleForm('Add a deadline or reminder',`<input type="hidden" name="opportunity_key" value="${esc(key)}"><label for="event-title">Title</label><input id="event-title" name="title" required maxlength="200" value="${esc(item?.title||'')}"><div class="form-grid"><div><label for="event-kind">Event type</label><select id="event-kind" name="kind">${['Reminder','Application deadline','Registration deadline','Assessment','Interview','Event','Follow-up'].map(x=>option(x,x,'Reminder')).join('')}</select></div><div><label for="event-date">Date or ISO timestamp</label><input id="event-date" name="date" required placeholder="2027-01-15 or 2027-01-15T10:00:00+05:30"></div><div><label for="event-zone">Source time zone</label><input id="event-zone" name="timezone" value="Asia/Kolkata" required></div><div><label for="event-reminder">Reminder minutes before</label><input id="event-reminder" type="number" min="0" max="43200" name="reminder_minutes" value="1440"></div></div><label for="event-notes">Evidence or notes</label><textarea id="event-notes" name="notes" maxlength="1500"></textarea><p class="muted small-text">Use a date alone when the actual cutoff is unknown. ICS reminders are handled by the calendar you import into; this service does not send notifications while asleep.</p>`,'event-form');
}
async function renderSettings(ticket){
  const tabs=[['profile','Your profile'],['sources','Sources'],['tools','Tools & integrations'],['reports','Analytics & exports'],['models','Recommendations'],['archive','Archive']];
  $('#content').innerHTML=heading('A workspace that fits you','Settings & tools','Your preferences, trusted sources, and the tools behind your next move.')+`<div class="tabs">${tabs.map(([id,label])=>`<button class="${id===state.settings?'active':''}" data-settings-tab="${id}">${label}</button>`).join('')}</div><div id="settings-content" class="loading-state" role="status">Loading settings…</div>`;
  const host=$('#settings-content');
  if(state.settings==='profile'){
    const p=await api('profile');if(ticket!==state.request)return;host.className='';host.innerHTML=`<div class="settings-card"><h2>Your opportunity profile</h2><p>Used to explain fit and flag requirements. Grades and private contact details are never inferred.</p><form id="profile-form"><div class="form-grid"><div><label for="profile-year">Graduation year</label><input id="profile-year" name="graduation_year" type="number" min="2025" max="2045" value="${p.graduation_year}"></div><div><label for="profile-season">Target season</label><input id="profile-season" name="target_season" value="${esc(p.target_season)}"></div><div><label for="profile-country">Country</label><input id="profile-country" name="country" value="${esc(p.country)}"></div><div><label for="profile-city">Preferred city / region</label><input id="profile-city" name="city" value="${esc(p.city)}"></div><div class="full"><label for="profile-degree">Degree</label><input id="profile-degree" name="degree" value="${esc(p.degree)}"></div><div class="full"><label for="profile-skills">Verified skills, separated by commas</label><input id="profile-skills" name="skills" value="${esc(p.skills.join(', '))}"></div><div class="full"><label class="check-label"><input type="checkbox" name="work_authorized_india" ${p.work_authorized_india?'checked':''}>I confirm that I am authorized to work in India.</label></div></div><button class="button primary" type="submit" style="margin-top:20px">Save profile</button></form></div><div class="notice" style="margin-top:18px">Verified professional links and project history remain in application packs. General outreach introductions use professional experience and projects; academic details are included only when required.</div>`;
  }else if(state.settings==='sources'){
    const data=await api('sources');if(ticket!==state.request)return;state.sourceData=data;host.className='';
    host.innerHTML=`<div class="section-heading"><div><h2>Connected sources & honest coverage</h2><p>${esc(data.hosting_note)}</p></div>${button(icon('refresh-cw')+'Refresh due sources','refresh')}</div><div class="source-counts">${Object.entries(data.counts).map(([mode,n])=>tag(n+' '+mode)).join('')}</div><div class="notice">A configured adapter becomes a successfully connected source only after a successful recorded check. Search-only portals are never counted as scanned. No guessed employer board identifiers have been added.</div><div class="settings-card" style="margin-top:18px"><h3>Add an employer-published board</h3><form id="source-form"><div class="form-grid"><div><label for="source-provider">Provider</label><select id="source-provider" name="provider">${['greenhouse','lever','ashby','smartrecruiters'].map(x=>option(x,x,'greenhouse')).join('')}</select></div><div><label for="source-slug">Published board identifier</label><input id="source-slug" name="slug" pattern="[A-Za-z0-9_-]{1,80}" required></div><div><label for="source-name">Employer name</label><input id="source-name" name="name" required maxlength="160"></div><div><label for="source-reference">Official careers-page evidence</label><input id="source-reference" name="reference" type="url" placeholder="https://…" required></div></div><button type="submit" class="button" style="margin-top:16px">Validate & register board</button></form></div>${Object.keys(data.counts).map(mode=>`<section class="source-group"><h3>${esc(mode)}</h3>${data.sources.filter(s=>s.mode===mode).map(s=>`<div class="source-card"><div class="source-head"><strong>${esc(s.name)}</strong>${tag(s.status,s.status==='healthy'?'success':['degraded','cooldown'].includes(s.status)?'warning':'')}${s.enabled?tag('Enabled'):''}${link('Open source '+icon('external-link'),s.url,'text-button')}</div><div class="source-details"><span>${esc(s.provider)} · ${esc(s.category)}</span><span>Last success: ${s.last_success?fmt(s.last_success,{year:'numeric',hour:'numeric',minute:'2-digit'}):'Not recorded'}</span><span>${s.record_count??'Unknown'} matching records</span><span>Success rate: ${s.success_rate==null?'No checks yet':s.success_rate+'% of '+s.attempt_count+' attempts'}</span><span>Next permitted check: ${s.next_at?fmt(s.next_at,{hour:'numeric',minute:'2-digit'}):'Not scheduled'}</span>${s.error_category?`<span>Error: ${esc(s.error_category)}</span>`:''}</div>${['API','Feed'].includes(mode)?`<label class="checkbox-inline" style="margin-top:10px"><input type="checkbox" data-source-toggle="${esc(s.id)}" ${s.enabled?'checked':''}>Enable periodic checks while awake</label>`:''}${s.documentation?link('Adapter documentation',s.documentation,'text-button'):''}</div>`).join('')}</section>`).join('')}`;
  }else if(state.settings==='tools'){
    host.className='';host.innerHTML=`<div class="settings-grid">${[
      ['file-text','Original resume vault','Keep the exact original PDF. Download it or verify its saved hash; derived application drafts remain separate.','/classic#resume','Open resume vault'],
      ['building','Recruiter CRM','Your existing encrypted contacts and CSV/XLSX imports remain available. No contact is messaged automatically.','/classic#contacts','Open recruiter CRM'],
      ['mail','Gmail & reviewed sending','The original mailbox powers single reviewed sends. Each email stays editable and requires your confirmation.','/classic#gmail','Review connection & compose'],
      ['list-checks','Application packs & companion','Prepare verified answers, download an application pack, or use the form companion. Existing guarded application controls remain explicit.','/classic#autoapply','Open application tools'],
      ['compass','Manual opportunity capture','Save an official job, event, or fellowship link for research. Source evidence and missing requirements remain visible.','/classic#radar','Capture a public lead'],
      ['shield-check','Private backup & restore','Existing private backups and restore remain available. Workspace exports add checklists, events, and history without tokens or document bytes.','/classic#settings','Open original backup tools']
    ].map(([i,t,p,u,l])=>`<article class="settings-card">${icon(i)}<h3>${t}</h3><p>${p}</p><a class="text-button" href="${u}">${l} ${icon('arrow-up-right')}</a></article>`).join('')}</div><div class="notice" style="margin-top:20px">Additional Gmail accounts support read-only intelligence. Google Calendar synchronization is not connected; use the private ICS export with your chosen calendar.</div>`;
  }else if(state.settings==='reports'){
    const data=await api('analytics');if(ticket!==state.request)return;host.className='';host.innerHTML=`<div class="notice">${esc(data.limitation)}</div><div class="stat-grid"><div class="stat-block"><strong>${data.opportunities}</strong><small>Stored opportunities</small></div><div class="stat-block"><strong>${data.owner_reported_submissions}</strong><small>Version 3.0 owner submission records</small></div><div class="stat-block"><strong>${data.audit_events}</strong><small>Recorded audit events</small></div></div><div class="settings-card"><h3>Current application stages</h3>${Object.entries(data.stages).map(([label,n])=>`<div class="bar-row"><span>${esc(label)}</span><div class="bar"><span style="width:${n/Math.max(1,...Object.values(data.stages))*100}%"></span></div><strong>${n}</strong></div>`).join('')}</div><div class="detail-actions"><a class="button" href="/api/v3/export">${icon('download')}Private JSON export</a><a class="button" href="/api/v3/export?format=csv">${icon('download')}Private CSV export</a><a class="button" href="/api/v3/calendar.ics">${icon('calendar-days')}Calendar ICS</a></div><p class="muted small-text">Exports contain private opportunity notes and history. Tokens, mail bodies, contact details, and original document bytes are excluded.</p>`;
  }else if(state.settings==='models'){
    const data=await api('models');if(ticket!==state.request)return;host.className='';host.innerHTML=`<div class="settings-card"><h2>Explainable recommendations</h2><p>Baseline: ${esc(data.baseline)}. Rules separate eligibility conflicts from skill relevance. Priority points are not an acceptance probability.</p><p>${esc(data.privacy)}</p><div class="notice">${data.feedback_records} distinct opportunities have genuine recorded feedback. A candidate needs at least 40, with at least 8 positive and 8 negative examples. Training uses a held-out comparison. Activation is a separate, explicit action available only after an improvement.</div><div class="detail-actions">${button('Evaluate feedback candidate','evaluate-model',data.feedback_records<40?'disabled':'')}${button('Restore rules baseline','rollback-model')}</div>${data.models.map(m=>`<div class="source-card"><div class="source-head"><strong>${esc(m.id)}</strong>${tag(m.status)}</div><p>${esc(JSON.stringify(m.metrics))}</p>${m.status!=='active'&&m.metrics.improved?button('Activate evaluated candidate','activate-model',`data-id="${esc(m.id)}"`):''}</div>`).join('')}</div>`;
  }else{
    const data=await api('opportunities?view=archive&size=60');const dismissed=await api('opportunities?view=dismissed&size=60');if(ticket!==state.request)return;remember([...data.items,...dismissed.items]);host.className='';host.innerHTML=`<h2>Archived & dismissed</h2><p class="muted small-text" style="margin:10px 0 20px">Records are retained. Open an opportunity to restore it.</p><div class="opportunities-grid">${[...new Map([...data.items,...dismissed.items].map(x=>[x.key,x])).values()].map(card).join('')||empty('Nothing archived','Archive and dismiss actions are reversible.','')}</div>`;
  }
}
async function route(){
  const [page,sub]=location.hash.slice(1).split('/');state.page=['today','discover','saved','applications','inbox','calendar','settings'].includes(page)?page:'today';if(state.page==='settings'&&sub)state.settings=sub;
  const ticket=++state.request;$$('[data-nav]').forEach(a=>{if(a.dataset.nav===state.page)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  $('#breadcrumb').innerHTML=`Workspace <span>/</span> ${state.page[0].toUpperCase()+state.page.slice(1)}`;$('#sidebar').classList.remove('open');$('.mobile-menu').setAttribute('aria-expanded','false');
  $('#content').innerHTML='<div class="loading-state" role="status">Loading your '+esc(state.page)+'…</div>';
  try{if(state.page==='today')await renderToday(ticket);else if(['discover','saved','applications'].includes(state.page))await renderOpportunities(ticket);else if(state.page==='inbox')await renderInbox(ticket);else if(state.page==='calendar')await renderCalendar(ticket);else await renderSettings(ticket);}catch(error){if(ticket===state.request)$('#content').innerHTML=heading('Your workspace','Something needs a moment','Your saved records are preserved.')+`<div class="notice warning">${esc(error.message)}</div><div class="detail-actions">${button('Retry','retry')}<a href="/classic" class="button">Open existing tools</a></div>`;}
}
function navigate(page,filter){state.filters=filter?{eligibility:filter}:{};state.pageNumber=1;if(location.hash==='#'+page)route();else location.hash=page;}
async function updateOpportunity(key,changes){const item=await mutate('opportunities/'+encodeURIComponent(key),changes,'PATCH');remember([item]);return item;}
async function refreshUnderlying(){if(state.detail&&$('#detail-dialog').open)await showDetail(state.detail.key,state.detailTab);else await route();}

async function monitorSourceRefresh(launchResult){
  // This only observes the per-source refresh; it never retries or bypasses cooldown.
  if(!launchResult?.queued)return;
  for(let i=0;i<30;i++){
    await new Promise(resolve=>setTimeout(resolve,6000));
    let status;
    try{status=await api('sources');}catch{return;}
    if(status.running)continue;
    const failed=status.sources.filter(x=>['degraded','cooldown'].includes(x.status)).length;
    toast('Source check finished.'+(failed?' '+failed+' sources need review in Settings.':' Check your updated leads.'));
    // Never erase unsaved input or interrupt an active opportunity dialog.
    if(['today','discover','saved','applications'].includes(state.page)
       && !$('#detail-dialog').open
       && !$('#assistant-dialog').open
       && !document.activeElement?.closest('form')){
      await route();
    }
    return;
  }
  toast('Source checking is taking longer than expected. Review source health in Settings.');
}

async function ask(question){$('#assistant-answer').textContent='Reviewing your recorded evidence…';try{const response=await mutate('intelligence',{question,keys:[...state.selected]});$('#assistant-answer').innerHTML=`<div>${esc(response.answer)}</div>${response.citations.map(c=>link(esc(c.title)+' '+icon('arrow-up-right'),c.url,'citation')).join('')}<div class="engine-label">${esc(response.engine)}<br>${esc(response.limitations)}</div>`;}catch(error){$('#assistant-answer').textContent=error.message;}}
document.addEventListener('click',async event=>{
  const close=event.target.closest('[data-close]');if(close){close.closest('dialog').close();return;}
  const detailTab=event.target.closest('[data-detail-tab]');if(detailTab){state.detailTab=detailTab.dataset.detailTab;renderDetail();return;}
  const settings=event.target.closest('[data-settings-tab]');if(settings){state.settings=settings.dataset.settingsTab;location.hash='settings/'+state.settings;return;}
  const calendarView=event.target.closest('[data-calendar-view]');if(calendarView){state.calendarView=calendarView.dataset.calendarView;route();return;}
  const calendarDay=event.target.closest('[data-calendar-day]');if(calendarDay){state.calendarDate=new Date(calendarDay.dataset.calendarDay+'T12:00:00');state.calendarView='day';route();return;}
  const prompt=event.target.closest('[data-question]');if(prompt){$('#assistant-question').value=prompt.dataset.question;ask(prompt.dataset.question);return;}
  const el=event.target.closest('[data-action]');if(!el||el.disabled)return;const action=el.dataset.action,key=el.dataset.key;el.disabled=true;
  try{
    if(action==='navigate')navigate(el.dataset.page,el.dataset.filter);
    else if(action==='retry')await route();
    else if(action==='theme'){const theme=document.documentElement.dataset.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=theme;localStorage.setItem('career-theme',theme);}
    else if(action==='menu'){const open=$('#sidebar').classList.toggle('open');el.setAttribute('aria-expanded',String(open));}
    else if(action==='logout'){await mutate('/api/logout');location.href='/';}
    else if(action==='refresh'){const r=await mutate('refresh');toast(r.status);monitorSourceRefresh(r).catch(()=>{});}
    else if(action==='detail')await showDetail(key);
    else if(action==='checklist')await showDetail(key,'checklist');
    else if(action==='save'||action==='detail-save'){const x=state.items.get(key);await updateOpportunity(key,{saved:!x.saved});toast(x.saved?'Removed from Saved':'Saved to your shortlist');await refreshUnderlying();}
    else if(action==='pin'){const x=state.items.get(key);await updateOpportunity(key,{pinned:!x.pinned});await refreshUnderlying();}
    else if(action==='archive'||action==='dismiss'){const x=state.items.get(key);await updateOpportunity(key,{[action==='archive'?'archived':'dismissed']:!(action==='archive'?x.archived:x.dismissed)});toast('Your workspace was updated. This action is reversible.');await refreshUnderlying();}
    else if(action==='prepare'){await mutate('opportunities/'+encodeURIComponent(key)+'/checklist');if(!['Applied','Assessment','Interview','Offer','Rejected','Closed','Withdrawn'].includes(state.items.get(key).stage))await updateOpportunity(key,{stage:'Preparing',saved:true});await showDetail(key,'checklist');}
    else if(action==='feedback'){if(el.dataset.kind==='Already applied'){await showDetail(key,'tracking');toast('Confirm the actual submission in tracking.');}else{await mutate('opportunities/'+encodeURIComponent(key)+'/feedback',{kind:el.dataset.kind});toast('Feedback saved. Employer requirements remain unchanged.');}}
    else if(action==='assistant'||action==='explain'){if(action==='explain'){state.selected=new Set([key]);renderCompare();}if(!$('#assistant-dialog').open)$('#assistant-dialog').showModal();$('#assistant-question').focus();if(action==='explain')await ask('Explain this opportunity and my next step');}
    else if(action==='merge-form'){const keys=[...state.selected];showSimpleForm('Group duplicate source records',`<p class="muted small-text">Use this only when both records describe the same real opening. Original records, notes, and evidence are retained.</p><label for="merge-primary">Keep as primary</label><select id="merge-primary" name="primary">${keys.map(k=>option(k,state.items.get(k)?.title||k,keys[0])).join('')}</select><label for="merge-reason">Evidence that these are the same opening</label><textarea id="merge-reason" name="reason" minlength="12" maxlength="1000" required></textarea>`,'merge-form');}
    else if(action==='unmerge'){await api('merge/'+encodeURIComponent(key),{method:'DELETE'});toast('Owner duplicate link undone.');await refreshUnderlying();}
    else if(action==='clear-compare'){state.selected.clear();$$('[data-compare]').forEach(x=>x.checked=false);renderCompare();}
    else if(action==='clear-filters'){state.filters={};state.pageNumber=1;await route();}
    else if(action==='previous'||action==='next'){state.pageNumber+=action==='next'?1:-1;await route();window.scrollTo({top:0,behavior:'smooth'});}
    else if(action==='edit-check'){const row=state.detail.checklist_items.find(x=>x.id===el.dataset.id);const label=window.prompt('Edit this preparation step',row.label);if(label!==null){await mutate('opportunities/'+encodeURIComponent(state.detail.key)+'/checklist/'+el.dataset.id,{label},'PATCH');await showDetail(state.detail.key,'checklist');}}
    else if(action==='add-event')eventForm(key||'');
    else if(action==='event-info')toast(el.dataset.event+' · Open the agenda view for the recorded reminder details.');
    else if(action==='delete-event'){await api('calendar/'+encodeURIComponent(el.dataset.id),{method:'DELETE'});await route();}
    else if(action==='calendar-prev'||action==='calendar-next'){const n=action==='calendar-next'?1:-1;if(state.calendarView==='month')state.calendarDate=new Date(state.calendarDate.getFullYear(),state.calendarDate.getMonth()+n,1,12);else state.calendarDate.setDate(state.calendarDate.getDate()+n*(state.calendarView==='week'?7:1));await route();}
    else if(action==='mail-refresh'){const r=await mutate('inbox/refresh',{account_id:state.account||null});toast(r.status);}
    else if(action==='mail-reviewed'){await mutate('inbox/'+encodeURIComponent(el.dataset.id)+'/reviewed');await route();}
    else if(action==='evaluate-model'){const r=await mutate('models/evaluate');toast(r.metrics.improved?'Candidate improved held-out loss. Review before activation.':'Candidate did not improve. Rules remain available.');await route();}
    else if(action==='activate-model'){await mutate('models/activate',{id:el.dataset.id});toast('Evaluated feedback model activated. Eligibility rules remain active.');await route();}
    else if(action==='rollback-model'){await mutate('models/rollback');toast('Rules baseline restored.');await route();}
    else if(action==='add-listing')showSimpleForm('Save an official opportunity',`<p class="muted small-text">Use an official employer link. For events or fellowships, use the manual capture tool in Settings.</p><label for="job-company">Employer</label><input id="job-company" name="company" maxlength="200" required><label for="job-title">Opportunity title</label><input id="job-title" name="title" maxlength="250" required><label for="job-url">Official HTTPS URL</label><input id="job-url" name="url" type="url" required><label for="job-location">Location / geographic restriction</label><input id="job-location" name="location" maxlength="200"><label for="job-description">Recorded source requirements</label><textarea id="job-description" name="description" maxlength="12000"></textarea>`,'add-listing-form');
  }catch(error){toast(error.message);}finally{if(el.isConnected)el.disabled=false;}
});
document.addEventListener('change',async event=>{
  const el=event.target;
  try{
    if(el.dataset.compare){if(el.checked&&state.selected.size>=2){el.checked=false;toast('Compare up to two opportunities at a time.');return;}el.checked?state.selected.add(el.dataset.compare):state.selected.delete(el.dataset.compare);renderCompare();}
    else if(el.dataset.checkId){el.disabled=true;const key=state.detail.key,cid=el.dataset.checkId;await mutate('opportunities/'+encodeURIComponent(key)+'/checklist/'+cid,{completed:el.checked},'PATCH');if($('#detail-dialog').open&&state.detail.key===key){await showDetail(key,'checklist');document.getElementById('check-'+cid)?.focus();}}
    else if(el.dataset.sourceToggle){await mutate('sources/'+encodeURIComponent(el.dataset.sourceToggle),{enabled:el.checked},'PATCH');toast('Source preference saved.');}
    else if(el.id==='mail-account'){state.account=el.value;await route();}
    else if(el.id==='mail-filter'){state.mailFilter=el.value;await route();}
    else if(el.closest('#search-form')&&el.tagName==='SELECT'){$('#search-form').requestSubmit();}
  }catch(error){toast(error.message);if(el.type==='checkbox')el.checked=!el.checked;}finally{el.disabled=false;}
});
document.addEventListener('submit',async event=>{
  const form=event.target;if(!form.matches('form'))return;event.preventDefault();const data=Object.fromEntries(new FormData(form));const submit=form.querySelector('[type=submit]');if(submit)submit.disabled=true;
  try{
    if(form.id==='search-form'){state.filters=data;state.pageNumber=1;await route();}
    else if(form.id==='assistant-form')await ask(data.question);
    else if(form.id==='tracking-form'){data.submitted_by_owner=new FormData(form).has('submitted_by_owner');await updateOpportunity(state.detail.key,data);toast('Tracking updated. Submission evidence is labelled explicitly.');await showDetail(state.detail.key,'tracking');}
    else if(form.id==='correction-form'){await updateOpportunity(state.detail.key,{eligibility_override:data});toast('Evidence review saved. Original eligibility evidence is retained.');await showDetail(state.detail.key);}
    else if(form.id==='add-check-form'){await mutate('opportunities/'+encodeURIComponent(state.detail.key)+'/checklist',data);await showDetail(state.detail.key,'checklist');}
    else if(form.id==='merge-form'){data.secondary=[...state.selected].find(k=>k!==data.primary);await mutate('merge',data);state.selected.clear();toast('Duplicate records grouped. Originals retained.');await showDetail(data.primary);}
    else if(form.id==='event-form'){data.reminder_minutes=Number(data.reminder_minutes);await mutate('calendar',data);$('#detail-dialog').close();toast('Calendar event saved.');await route();}
    else if(form.id==='profile-form'){data.graduation_year=Number(data.graduation_year);data.skills=data.skills.split(',').map(s=>s.trim()).filter(Boolean);data.work_authorized_india=new FormData(form).has('work_authorized_india');await mutate('profile',data,'PUT');toast('Your profile was saved.');}
    else if(form.id==='source-form'){await mutate('sources',data);toast('Published board validated and registered. Refresh to import its matching roles.');await route();}
    else if(form.id==='add-listing-form'){const r=await mutate('/api/jobs',data);$('#detail-dialog').close();toast('Official listing saved.');await showDetail('j:'+r.id);}
  }catch(error){toast(error.message);}finally{if(submit?.isConnected)submit.disabled=false;}
});
document.addEventListener('keydown',event=>{if(event.key==='Escape'){$('#sidebar').classList.remove('open');$('.mobile-menu').setAttribute('aria-expanded','false');}if((event.ctrlKey||event.metaKey)&&event.key==='k'){event.preventDefault();if($('#search-form input'))$('#search-form input').focus();else navigate('discover');}});
window.addEventListener('hashchange',()=>{state.pageNumber=1;route();});
async function init(){try{state.bootstrap=await api('bootstrap');await route();mutate('refresh').then(monitorSourceRefresh).catch(()=>{});}catch(error){$('#content').innerHTML=empty('Your workspace needs a moment',error.message,'');}}
init();
