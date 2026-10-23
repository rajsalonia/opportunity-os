"""Remote-first public job discovery with source attribution and safe eligibility labels.

Official public feeds only. No scraping, job application submission, account
creation or inferred work authorization. Each returned URL links to its source.
"""
import hashlib
import html
import re
from urllib.parse import urlsplit
import requests

FEEDS=(
    ("jobicy","Jobicy","https://jobicy.com/api/v2/remote-jobs"),
    ("remotive","Remotive","https://remotive.com/api/remote-jobs"),
    ("arbeitnow","Arbeitnow","https://www.arbeitnow.com/api/job-board-api"),
)
REMOTE_TERMS=re.compile(r"\b(remote|work from anywhere|work from home|distributed|wfh|fully remote)\b",re.I)
INDIA_TERMS=re.compile(r"\b(india|indian|delhi|noida|gurgaon|gurugram|ncr|pune|mumbai|hyderabad|bengaluru|bangalore|chennai|kolkata)\b",re.I)
GLOBAL_TERMS=re.compile(r"\b(worldwide|anywhere in the world|globally|global remote|work from anywhere|any location|anywhere)\b",re.I)
REGION_RESTRICTION=re.compile(r"\b(us(?:a)? only|united states only|canada only|uk only|europe only|emea only|eu only|north america only|must reside in (?:the )?(?:united states|usa|canada|uk|europe)|us residents only|united states residents only)\b",re.I)
SENIOR=re.compile(r"\b(senior|staff|principal|lead|director|head of|vp|manager|architect)\b",re.I)
EARLY=re.compile(r"\b(intern(?:ship)?|co-?op|graduate|new grad|entry[- ]level|junior|trainee|apprentice|associate|fresher|early career)\b",re.I)
TECH=re.compile(r"\b(software|backend|back.end|developer|engineering|devops|cloud|infrastructure|sre|site reliability|python|machine learning|artificial intelligence|data engineer|platform engineer|security engineer|ai engineer)\b",re.I)
EXPERIENCE=re.compile(r"\b([4-9]|1\d)\+?\s*(?:years?|yrs?)\s*(?:of\s*)?(?:relevant\s*)?(?:professional\s*)?experience\b",re.I)
NO_INDIA=re.compile(r"\b(not available in india|excluding india|india is excluded|not hiring in india|cannot hire in india|outside india only)\b",re.I)
EXPLICIT_2028_EXCLUSION=re.compile(r"\b(?:202[4567]\s*(?:graduates?|only)|must graduate (?:in|by) 202[4567]|not eligible.{0,40}2028)\b",re.I)

def work_details(location, description="", remote_flag=None):
    loc=str(location or "").strip()
    desc=str(description or "")
    text=loc+" "+desc[:3500]
    remote=remote_flag is True or bool(REMOTE_TERMS.search(loc)) or bool(re.search(r"\b(?:fully remote|100% remote|remote position|remote role|work from anywhere)\b",desc,re.I))
    hybrid=bool(re.search(r"\bhybrid\b",loc)) or bool(re.search(r"\bhybrid (?:role|work|schedule|model)\b",desc,re.I))
    mode="Remote" if remote else ("Hybrid" if hybrid else ("On-site" if loc and not re.search(r"\bflexible\b",loc,re.I) else "Unspecified"))
    if hybrid:mode="Hybrid"
    if not remote:
        scope="Not established"
    elif NO_INDIA.search(text) or REGION_RESTRICTION.search(loc):
        scope="Region-restricted / verify"
    elif re.fullmatch(r"(?:remote\s*[·,|/ -]*\s*)?(?:usa|united states|canada|united kingdom|uk|europe|emea|north america|australia)",loc,re.I):
        scope="Region-restricted / verify"
    elif INDIA_TERMS.search(loc) or re.search(r"\bremote\s*[-–,(/ ]\s*india\b",desc,re.I):
        scope="India mentioned / verify"
    elif GLOBAL_TERMS.search(loc):
        scope="Worldwide claimed / verify"
    else:
        scope="Location eligibility unverified"
    return {"work_mode":mode,"remote_scope":scope,"india_eligible_confirmed":False}

def description_text(value, limit=12000):
    decoded=html.unescape(html.unescape(str(value or "")))
    decoded=re.sub(r"(?i)<br\s*/?>|</(?:p|div|li|h[1-6]|ul|ol)\s*>","\n",decoded)
    return re.sub(r"\n{3,}","\n\n",html.unescape(re.sub(r"<[^>]*>","",decoded))).strip()[:limit]

def accept_role(title, desc, location):
    text=str(title or "")
    if not TECH.search(text):return False
    if SENIOR.search(text):return False
    if EXPERIENCE.search(desc):return False
    if EXPLICIT_2028_EXCLUSION.search(desc):return False
    # No broad senior full-time roles; early-career signals must be explicit.
    return bool(EARLY.search(text) or EARLY.search(desc[:1400]))

def secure_url(link):
    try:
        parsed=urlsplit(str(link or ""))
        return parsed.scheme=="https" and bool(parsed.hostname) and not parsed.username and not parsed.password
    except (TypeError,ValueError):return False

def normalize(provider, company, title, location, description, link, rank, remote_flag=None):
    if not secure_url(link):return None
    description=description_text(description)
    if not accept_role(title,description,location):return None
    meta=work_details(location,description,remote_flag)
    if meta["work_mode"]=="Remote" and not REMOTE_TERMS.search(str(location or "")):
        location="Remote · "+str(location or "Region unspecified").strip()
    score,warnings=rank(title,description,location)
    if meta["work_mode"]=="Remote":score=min(100,score+12)
    if meta["remote_scope"]=="Region-restricted / verify":
        warnings=(warnings+"; " if warnings else "")+"Remote region restriction: check India eligibility"
    if meta["remote_scope"]=="Location eligibility unverified":
        warnings=(warnings+"; " if warnings else "")+"Remote eligibility for India unverified"
    return {"id":hashlib.sha256(link.encode()).hexdigest()[:32],
            "company":str(company or "Employer not stated")[:150],
            "title":str(title or "")[:200],"location":str(location or "Location not stated")[:200],
            "url":link,"provider":provider,"description":description,"score":score,"warnings":warnings}

def fetch_public_feed(source, rank, http_get=None):
    """Returns (list of normalized jobs, error or None). Only public feeds."""
    http_get=http_get or requests.get
    provider,label,url=source
    try:
        params={"count":200} if provider=="jobicy" else None
        response=http_get(url,params=params,timeout=16,
                          headers={"User-Agent":"OpportunityOS/1.2 (personal job discovery)"})
        response.raise_for_status()
        payload=response.json()
        if provider=="jobicy":
            posts=payload.get("jobs",[]) if isinstance(payload,dict) else []
        elif provider=="remotive":
            posts=payload.get("jobs",[]) if isinstance(payload,dict) else []
        elif provider=="arbeitnow":
            posts=payload.get("data",[]) if isinstance(payload,dict) else []
        else:return [],label+" unsupported"
        results=[]
        for p in posts[:300]:
            if not isinstance(p,dict):continue
            if provider=="jobicy":
                job=normalize(provider,p.get("companyName"),p.get("jobTitle"),p.get("jobGeo") or "Remote",
                              p.get("jobDescription") or p.get("jobExcerpt"),p.get("url"),rank,remote_flag=True)
            elif provider=="remotive":
                job=normalize(provider,p.get("company_name"),p.get("title"),p.get("candidate_required_location") or "Remote",
                              p.get("description"),p.get("url"),rank,remote_flag=True)
            else:
                job=normalize(provider,p.get("company_name"),p.get("title"),p.get("location") or "",
                              p.get("description"),p.get("url"),rank,remote_flag=p.get("remote") is True)
            if job:results.append(job)
        return results,None
    except (requests.RequestException,ValueError,TypeError,KeyError):
        return [],label+" feed unavailable"
