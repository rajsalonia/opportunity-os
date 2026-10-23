"""Conservative, explainable extraction/ranking. No external model or private-document training."""
import hashlib
import ipaddress
import html
import re
from datetime import datetime, timezone, timedelta, date
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

VERSION = 'rules-3.0.1'
STAGES = ('Discovered','Saved','Researching','Preparing','Ready to Apply','Applied','Assessment','Interview','Offer','Rejected','Withdrawn','Closed')
SUBSTATES = ('','Waiting for Reply','Follow-up Due','On Hold')
LEGACY = {'Researching':'Saved','Preparing':'Draft ready','Ready to Apply':'Draft ready','Withdrawn':'Closed'}
TERMINAL = {'Applied','Assessment','Interview','Offer','Rejected','Withdrawn','Closed'}
FEEDBACK = ('Interested','Not interested','Too senior','Wrong location','Ineligible','Prefer similar','Already applied')
SKILLS = ('python','fastapi','backend','api','sql','postgresql','aws','cloud','docker','kubernetes','devops','sre','distributed systems','machine learning','llm','rag','generative ai','agentic','git','linux','react','typescript','java','c++','pytorch')
INDIA = re.compile(r'\b(india|indian|delhi|noida|gurgaon|gurugram|ncr|bengaluru|bangalore|pune|hyderabad|mumbai|chennai|kolkata|faridabad|ghaziabad|chandigarh|kochi)\b',re.I)
NCR = re.compile(r'\b(delhi|noida|gurgaon|gurugram|ncr|faridabad|ghaziabad)\b',re.I)
SENIOR = re.compile(r'\b(senior|sr\.?|staff|principal|lead|director|head of|vp|manager)\b',re.I)
EARLY = re.compile(r'\b(intern(?:ship)?|junior|trainee|graduate|new grad|apprentice|entry.level|fresher|co.op)\b',re.I)
TECH = re.compile(r'\b(software|engineer|python|backend|developer|cloud|devops|sre|machine learning|ai|llm|data|research|infrastructure|platform|security)\b',re.I)
FIRST_PARTY = {'greenhouse','lever','ashby','smartrecruiters','personio'}
DEFAULT_PROFILE = {'graduation_year':2028,'country':'India','city':'Delhi NCR','target_season':'Summer 2027',
    'degree':'B.Tech Computer Science','skills':['python','fastapi','backend','api','sql','aws','cloud','docker','generative ai','llm','rag','git'],
    'interests':['Software engineering','Backend','AI engineering','Cloud','DevOps','Research'],
    'work_authorized_india':False,'preferred_modes':['Remote','Hybrid','On-site'],'timezone':'Asia/Kolkata'}

def plain(value, limit=16000):
    text = html.unescape(html.unescape(str(value or '')))
    text = re.sub(r'(?i)<br\s*/?>|</(?:p|div|li|h[1-6])\s*>','\n',text)
    return re.sub(r'\n{3,}','\n\n',html.unescape(re.sub(r'<[^>]*>',' ',text))).strip()[:limit]

def canonical_url(value):
    try:
        parts = urlsplit(str(value or '').strip())
        if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password: return ''
        host = parts.hostname.lower().removeprefix('www.')
        if host in ('localhost','metadata.google.internal') or host.endswith(('.local','.internal')): return ''
        try:
            if not ipaddress.ip_address(host).is_global:return ''
        except ValueError:pass
        pairs = [(key,val) for key,val in parse_qsl(parts.query,keep_blank_values=True) if not key.lower().startswith(('utm_','ref_')) and key.lower() not in ('source','ref','trk','trackingid','gh_src','lever-source')]
        # Gmail's fragment is the actual message locator; retain it without fetching it.
        fragment = parts.fragment if host == 'mail.google.com' else ''
        return urlunsplit(('https',host,parts.path.rstrip('/') or '/',urlencode(sorted(pairs)),fragment))
    except (ValueError,TypeError): return ''

def identity(item):
    url = canonical_url(item.get('url'))
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    company = re.sub(r'[^a-z0-9]','',str(item.get('company') or '').lower())
    ghid = query.get('gh_jid')
    if not ghid and 'greenhouse.io' in parts.netloc:
        match = re.search(r'/jobs/(\d+)',parts.path); ghid = match.group(1) if match else None
    if ghid: return 'greenhouse:' + company + ':' + ghid
    if parts.netloc == 'jobs.lever.co': return 'lever:' + parts.path.rstrip('/').removesuffix('/apply').lower()
    if parts.netloc == 'jobs.ashbyhq.com': return 'ashby:' + parts.path.rstrip('/').removesuffix('/application').lower()
    return url or str(item.get('key'))

def parse_deadline(value, zone=None, provenance='Not disclosed'):
    raw = str(value or '').strip()
    result = {'value':raw,'date':None,'local_date':None,'utc':None,'timezone':zone or 'Unknown','precision':'unknown','provenance':provenance,'cutoff_known':False}
    if not raw: return result
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}',raw):
        try: result.update(date=date.fromisoformat(raw).isoformat(),local_date=date.fromisoformat(raw).isoformat(),precision='date')
        except ValueError: pass
        return result
    try: parsed = datetime.fromisoformat(raw.replace('Z','+00:00'))
    except ValueError:
        try: parsed = parsedate_to_datetime(raw)
        except (ValueError,TypeError,OverflowError): return result
    result['date'] = parsed.date().isoformat()
    result['local_date'] = result['date']
    if parsed.tzinfo is None and zone:
        try: parsed = parsed.replace(tzinfo=ZoneInfo(zone))
        except (ZoneInfoNotFoundError,ValueError): return result
    if parsed.tzinfo:
        result.update(utc=parsed.astimezone(timezone.utc).isoformat(),local_date=parsed.astimezone(ZoneInfo('Asia/Kolkata')).date().isoformat(),timezone=zone or str(parsed.tzinfo),precision='datetime',cutoff_known=True)
    else: result['precision'] = 'time_zone_unknown'
    return result

def extract(item):
    description = plain(item.get('description') or item.get('summary'))
    title = plain(item.get('title'),250)
    source = item.get('provider') or item.get('source') or 'Owner-added information'
    provenance = 'Employer stated' if source in FIRST_PARTY else 'Recorded source text; verify'
    def fact(value=None, evidence='', confidence=provenance):
        return {'value':value,'evidence':evidence[:500],'provenance':confidence if value not in (None,'') else 'Not disclosed','source_url':canonical_url(item.get('url'))}
    fields = {key:fact() for key in ('company_website','industry','company_size','company_type','headquarters','compensation','currency','payment_period','duration','start_date','degree','experience','graduation_years','work_authorization','team_size','fees','prizes','event_dates','benefits')}
    text = title + '\n' + description
    structured = item.get('facts') if isinstance(item.get('facts'),dict) else {}
    for name,value in structured.items():
        if name in fields and isinstance(value,(str,int,float)) and value != '': fields[name] = fact(value,str(value))
    salary = re.search(r'(?i)(?:₹|INR\s*|USD\s*|\$|EUR\s*|€|GBP\s*|£)\s*[\d,.]+\s*[kK]?(?:\s*[-–—]\s*(?:(?:₹|\$|INR|USD|EUR|€|GBP|£)\s*)?[\d,.]+\s*[kK]?)?(?:\s*(?:per|/|a)\s*(?:month|annum|year|hour|week)|\s*(?:monthly|annually|LPA))?',description)
    salary_context=description[max(0,salary.start()-100):salary.end()+65] if salary else ''
    salary_is_pay=bool(salary and re.search(r'(?i)stipend|salary|compensation|base pay|pay range|paid internship',salary_context) and not re.search(r'(?i)learning.{0,40}(?:budget|fund)|development.{0,40}(?:budget|fund)|travel grant|prize|registration fee',salary_context))
    if salary_is_pay:
        fields['compensation'] = fact(salary.group().strip(),description[max(0,salary.start()-60):salary.end()+60])
        currency = next((currency for pattern,currency in [(r'₹|INR','INR'),(r'USD|\$','USD'),(r'EUR|€','EUR'),(r'GBP|£','GBP')] if re.search(pattern,salary.group())),None)
        fields['currency'] = fact(currency,salary.group())
        period = re.search(r'(?i)month|monthly|annum|year|annually|hour|week|LPA',salary.group())
        if period: fields['payment_period'] = fact(period.group().lower(),salary.group())
    elif re.search(r'\bunpaid\b',description,re.I): fields['compensation'] = fact('Unpaid','Unpaid stated in source')
    elif re.search(r'\bpaid (?:internship|position|role)\b',description,re.I): fields['compensation'] = fact('Paid; amount not disclosed','Paid role stated in source')
    duration = re.search(r'(?i)\b(?:duration\s*[:=-]?\s*|(?:internship|intern)\s+(?:of|for)\s+)?(\d+(?:\s*[-–]\s*\d+)?)\s*[- ]?(months?|weeks?)(?:\s+(?:internship|term|program|full.time))?',description)
    if duration: fields['duration'] = fact(duration.group().strip(),duration.group())
    requirement_sentences = [s.strip() for s in re.split(r'[\n.!?;]+',text) if re.search(r'graduat|class of|batch|cohort|passing out|pass.out',s,re.I)]
    graduation = []
    for sentence in requirement_sentences:
        if not re.search(r'graduat|class of|batch|passing out',sentence,re.I): continue
        years = [int(y) for y in re.findall(r'\b20[2-4]\d\b',sentence)]
        if years: graduation.append({'years':sorted(set(years)),'evidence':sentence[:400]})
    if graduation: fields['graduation_years'] = fact(sorted({year for row in graduation for year in row['years']}),' · '.join(row['evidence'] for row in graduation))
    degree = next((s.strip() for s in re.split(r'[\n.!?;]+',description) if re.search(r'(?i)(?:pursuing|enrolled|bachelor|undergraduate|master|ph\.?d|b\.tech).{0,90}(?:degree|computer science|engineering|student)|(?:bachelor|master|phd|undergraduate).{0,30}required',s)),None)
    if degree: fields['degree'] = fact(degree[:300],degree)
    experience = re.search(r'(?i)\b(?:at least |minimum |requires? )?(\d+(?:\s*[-–]\s*\d+)?\+?)\s*(?:years?|yrs?)\s*(?:of\s+)?(?:professional\s+|relevant\s+)?experience',description)
    if experience: fields['experience'] = fact(experience.group(),experience.group())
    for name,pattern in [('team_size',r'(?i)team(?: size)?\s*[:=-]\s*\d+(?:\s*[-–]\s*\d+)?'),('fees',r'(?i)(?:registration|entry) fee\s*[:=-]\s*[^\n.;]+|\bfree (?:registration|entry)\b'),('prizes',r'(?i)(?:prize(?: pool)?|awards?)\s*[:=-]\s*[^\n.;]+'),('benefits',r'(?i)(?:swag|certificate|travel grant|mentorship|networking)\s*(?:provided|available|included|offered)')]:
        match = re.search(pattern,description)
        if match: fields[name] = fact(match.group().strip(),match.group())
    mode = str(structured.get('work_mode') or '')
    location = str(item.get('location') or '')
    if mode not in ('Remote','Hybrid','On-site'):
        mode = 'Hybrid' if re.search(r'\bhybrid\b',location+' '+description,re.I) else 'Remote' if re.search(r'\bremote\b|work from home|work from anywhere|home based',location,re.I) or re.search(r'fully remote|100% remote|remote (?:role|position|internship)',description,re.I) else 'On-site' if re.search(r'on.?site|in.person|in.office',location+' '+description,re.I) else 'Not disclosed'
    known = [skill for skill in SKILLS if re.search(r'(?<![a-z0-9])'+re.escape(skill)+r'(?![a-z0-9])',text,re.I)]
    preferred = [skill for skill in known if re.search(r'(?i)(?:preferred|nice to have|bonus).{0,100}'+re.escape(skill),description)]
    required = [skill for skill in known if skill not in preferred]
    deadline_value = item.get('deadline') or ''
    deadline_origin = item.get('deadline_provenance') or ('Owner recorded' if deadline_value else 'Not disclosed')
    if not deadline_value:
        match = re.search(r'(?i)(?:registration closes|application deadline|apply by|deadline)\s*[:=-]?\s*((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+\d{1,2}\s+\w+\s+\d{4}\s+[\d:]+\s+(?:GMT|UTC)|\d{4}-\d{2}-\d{2}(?:T[\d:.]+(?:Z|[+-][\d:]+))?)',description)
        if match: deadline_value,deadline_origin = match.group(1),provenance
    remote_scope='Not applicable' if mode!='Remote' else 'India eligibility unverified'
    if mode=='Remote':
        if re.search(r'(?i)worldwide|anywhere in the world|work from anywhere',location):remote_scope='Worldwide claimed; verify work authorization'
        elif INDIA.search(location):remote_scope='India mentioned; verify requirements'
        elif re.search(r'(?i)\b(?:us|usa|united states|canada|uk|europe|emea)\b',location):remote_scope='Region restricted; verify India eligibility'
    return {'fields':fields,'description':description,'required_skills':required,'preferred_skills':preferred,'remote_scope':remote_scope,
            'graduation_requirements':graduation,'work_mode':mode,
            'deadline':parse_deadline(deadline_value,item.get('deadline_timezone'),deadline_origin)}

def eligibility(item, facts, profile, timestamp=None):
    clock = timestamp or datetime.now(timezone.utc)
    text = facts['description']; title = str(item.get('title') or ''); location = str(item.get('location') or '')
    year = int(profile.get('graduation_year',2028)); conflicts=[]; checks=[]; evidence=[]
    stage = item.get('stage') or item.get('status') or 'Discovered'
    deadline = facts['deadline']
    if stage in ('Closed','Withdrawn') or item.get('availability') == 'closed':
        return {'code':'closed','label':'Closed or expired','reasons':['Closed in your tracker or no longer listed by a successful source check.'],'evidence':[],'hard_conflict':True,'version':VERSION}
    if deadline.get('utc') and datetime.fromisoformat(deadline['utc']) < clock:
        return {'code':'closed','label':'Closed or expired','reasons':['The recorded deadline has passed.'],'evidence':[deadline['value']],'hard_conflict':True,'version':VERSION}
    if deadline.get('date') and not deadline.get('utc') and deadline['date'] < clock.astimezone(ZoneInfo('Asia/Kolkata')).date().isoformat():
        checks.append('The reported deadline date has passed; confirm whether registration remains open.')
    grad_supported=False
    for row in facts['graduation_requirements']:
        sentence=row['evidence']; years=row['years']
        excluded = bool(re.search(r'(?i)(?:not eligible|excluding|except|no students|ineligible).{0,35}\b'+str(year)+r'\b|\b'+str(year)+r'\b.{0,35}(?:not eligible|excluded|ineligible)',sentence))
        # A Summer 2027 season is not a graduation-year restriction.
        explicit = bool(re.search(r'(?i)must graduate|graduating (?:in|between)|graduates? (?:of|in|only)|20\d\d graduates? only|class of|batch of|graduation (?:date|year)|expected graduation|new grad',sentence))
        if excluded or (explicit and years and year not in years and not (len(years)>1 and min(years)<=year<=max(years))):
            conflicts.append(f'Graduation requirement conflicts with your {year} graduation.'); evidence.append(sentence)
        elif year in years or (len(years)>1 and min(years)<=year<=max(years)): grad_supported=True; evidence.append(sentence)
    if re.search(r'(?i)new grad(?:uate)?[^\n]{0,15}202[0-7]|class of 202[0-7]\b',title) and str(year) not in title:
        conflicts.append('The role title targets an earlier graduating class.'); evidence.append(title)
    if SENIOR.search(title): conflicts.append('The role is senior to your current internship target.'); evidence.append(title)
    if re.search(r'(?i)\bph\.?d\b|doctoral|postdoctoral',title):conflicts.append('The role explicitly targets doctoral candidates.');evidence.append(title)
    exp = facts['fields']['experience']['value']
    if exp and int(re.search(r'\d+',exp).group())>=3: conflicts.append('The stated professional experience exceeds your verified early-career profile.'); evidence.append(exp)
    if re.search(r'(?i)(?:ph\.?d|doctoral|master.s).{0,30}(?:required|only)|must (?:be|have).{0,30}(?:ph\.?d|master.s)',text): conflicts.append('A postgraduate qualification is required.'); evidence.append(facts['fields']['degree']['value'] or 'Postgraduate degree required')
    region_restriction = re.search(r'(?i)\b(?:us|usa|united states|canada|uk|united kingdom|europe|eu|emea|north america)[ -]+only\b|must (?:reside|be based|be located) in (?:the )?(?:united states|usa|canada|uk|europe)|(?:excluding|not (?:available|hiring) in|outside) india',location+'\n'+text)
    if region_restriction: conflicts.append('The stated geographic restriction does not include India.'); evidence.append(region_restriction.group())
    if facts['work_mode']=='Remote' and re.fullmatch(r'(?i)(?:remote\s*[—–·,|/-]*\s*)?(?:usa|us|united states|uk|united kingdom|europe|canada|australia)',location.strip()): conflicts.append('Remote is restricted to the listed overseas region.'); evidence.append(location)
    citizenship = re.search(r'(?i)(?:us|u\.s\.|united states|canadian|eu) citizen(?:ship)? (?:is )?required|must be authorized to work in the united states|security clearance (?:is )?required',text)
    if citizenship: conflicts.append('A foreign citizenship, work authorization, or clearance requirement needs an exception.'); evidence.append(citizenship.group())
    india = bool(INDIA.search(location))
    worldwide = bool(re.search(r'(?i)worldwide|anywhere in the world|work from anywhere|global remote',location+' '+text[:1200]))
    foreign_location=re.search(r'(?i)\b(?:united states|usa|san francisco|new york|seattle|boston|palo alto|san jose|austin|canada|toronto|vancouver|london|united kingdom|germany|berlin|singapore|australia|sydney|dublin|ireland|netherlands|amsterdam)\b',location)
    if foreign_location and not india and not worldwide:
        if facts['work_mode']=='Remote':conflicts.append('The remote location is in an overseas region; India is not included.');evidence.append(location)
        else:checks.append('The role is listed outside India. Relocation and local work authorization are unverified.')
    student = bool(re.search(r'(?i)(?:currently )?pursuing.{0,80}(?:bachelor|b.tech|undergraduate|computer science|degree)|enrolled.{0,80}(?:bachelor|undergraduate|university)|undergraduate students|current students',text))
    if not grad_supported and not student: checks.append('Graduation year and undergraduate eligibility are not explicitly confirmed.')
    if worldwide and not india: checks.append('Worldwide remote is claimed; India payroll, contractor, and tax restrictions still need verification.')
    elif not india: checks.append('India-based application and work authorization are not established by the listing.')
    if india and not profile.get('work_authorized_india'): checks.append('Confirm your India work authorization in your profile.')
    duration = str(facts['fields']['duration']['value'] or '')
    if re.search(r'\b6\s*[- ]?months?',duration,re.I) and facts['work_mode']=='On-site': checks.append('Confirm six-month on-site availability against your academic schedule.')
    category = item.get('category','Internship')
    if category in ('Community post','Startup hiring','Other','Scholarship','Fellowship','Hackathon','Event') and not student and not grad_supported: checks.append('Organizer-specific eligibility and participation rules need review.')
    if conflicts: code,label='ineligible','Not eligible — specific conflict'
    elif india and grad_supported and profile.get('work_authorized_india') and not checks: code,label='eligible','Eligible — stated requirements fit'
    elif (india and (grad_supported or student)) or (worldwide and not foreign_location and (grad_supported or student)): code,label='likely','Likely eligible — verify details'
    else: code,label='unknown','Unknown — needs verification'
    return {'code':code,'label':label,'reasons':list(dict.fromkeys(conflicts+checks)) or ['Available graduation and location requirements fit your profile. Confirm availability and employer-specific questions.'],
            'evidence':list(dict.fromkeys(evidence)),'hard_conflict':bool(conflicts),'version':VERSION}

def recommend(item, facts, assessment, profile, feedback=None, timestamp=None):
    clock=timestamp or datetime.now(timezone.utc)
    relevant = set(facts['required_skills']+facts['preferred_skills'])
    matched=sorted(relevant.intersection(profile.get('skills',[]))); missing=sorted(relevant.difference(profile.get('skills',[])))
    location=str(item.get('location') or '')
    geo=1 if NCR.search(location) else .85 if INDIA.search(location) else .5 if re.search(r'worldwide',location,re.I) else .1
    skill_fit=min(1,len(matched)/max(4,len(relevant)))
    early=1 if EARLY.search(str(item.get('title'))) else .3
    fresh=.25
    try: fresh=max(0,1-(clock-datetime.fromisoformat(str(item.get('first_seen') or item.get('discovered')).replace('Z','+00:00'))).days/30)
    except (ValueError,TypeError): pass
    eligible={'eligible':1,'likely':.6,'unknown':.15,'ineligible':0,'closed':0}[assessment['code']]
    paid=1 if facts['fields']['compensation']['value'] and facts['fields']['compensation']['value']!='Unpaid' else 0
    features=[skill_fit,geo,early,fresh,eligible,paid,1 if item.get('provider') in FIRST_PARTY else .35]
    points=round(35*skill_fit+20*geo+12*early+8*fresh+20*eligible+5*paid)
    positives=sum(row.get('kind') in ('Interested','Prefer similar') and row.get('category')==item.get('category') for row in (feedback or []))
    points+=min(8,positives*2)
    own=[row for row in (feedback or []) if row.get('opportunity_key')==item.get('key')]
    negative=any(row.get('kind') in ('Not interested','Too senior','Wrong location','Ineligible','Already applied') for row in own[-1:])
    if negative:points=max(0,points-35)
    reasons=[]
    if matched: reasons.append('Your recorded skills match '+', '.join(matched[:4])+'.')
    if NCR.search(location): reasons.append('The stated location matches your Delhi NCR preference.')
    elif INDIA.search(location): reasons.append('The stated location is in India.')
    if facts['fields']['compensation']['value']: reasons.append('Compensation information is available to review.')
    if assessment['code'] in ('ineligible','closed'):reasons.insert(0,assessment['reasons'][0])
    if not reasons: reasons.append('Review the source requirements before deciding whether this is relevant.')
    stage=item.get('stage') or item.get('status') or 'Discovered'
    if stage in TERMINAL: bucket='Already applied' if stage not in ('Closed','Rejected','Withdrawn') else 'History'
    elif assessment['code'] in ('ineligible','closed'):bucket='Not eligible'
    elif negative:bucket='Research first'
    elif facts['deadline'].get('date') and 0 <= (date.fromisoformat(facts['deadline']['date'])-clock.astimezone(ZoneInfo('Asia/Kolkata')).date()).days <= 2: bucket='Deadline approaching'
    elif assessment['code']=='eligible' and points>=55:bucket='Apply today'
    elif assessment['code']=='likely' and points>=45:bucket='Worth reviewing this week'
    else:bucket='Research first'
    suggestion=(clock.astimezone(ZoneInfo('Asia/Kolkata')).date()+timedelta(days=0 if bucket in ('Apply today','Deadline approaching') else 3)).isoformat()
    return {'score':min(100,max(0,points)),'score_label':'Priority points · rules, not acceptance probability','bucket':bucket,
            'reasons':reasons,'matched_skills':matched,'skills_to_verify':missing,'features':features,
            'suggested_action_date':suggestion,'suggested_action_label':'Suggested review date; not an employer deadline','model':VERSION}

def warnings(item, facts):
    text=facts['description']; result=[]
    for pattern,message in [(r'(?i)(?:pay|transfer|send).{0,30}(?:application fee|security deposit|registration fee)','The source mentions a payment before selection. Verify the organizer and payment terms.'),
                            (r'(?i)(?:share|send|provide).{0,35}(?:password|otp|one.time password|bank pin)','The source appears to request sensitive credentials. Verify through an official company channel.')]:
        if re.search(pattern,text):result.append(message)
    if facts['fields']['compensation']['value'] is None:result.append('Compensation is not disclosed.')
    if not facts['deadline']['date']:result.append('No confirmed deadline is recorded.')
    if item.get('provider') not in FIRST_PARTY:result.append('This is a discovery lead or owner-entered record; verify the original organizer.')
    return result
