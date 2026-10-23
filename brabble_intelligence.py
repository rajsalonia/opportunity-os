"""Optional, key-authorized Brabble opportunity details, with truthful source attribution.

The public RSS radar remains functional without this integration. A Brabble API
key adds structured dates, organizer and eligibility hints from Brabble's feed.
No job/competition applications are submitted from this module.
"""
import hashlib
import html
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

import requests

URL="https://brabble.ai/api/listings"
API_SOURCE="Brabble • college-student API"
TAGS=re.compile(r"<[^>]*>")

def clean(value, limit=260):
    return " ".join(TAGS.sub(" ",html.unescape(str(value or ""))).split())[:limit]

def https_url(value):
    try:
        u=urlsplit(value or "")
        return u.scheme=="https" and bool(u.hostname) and not u.username and not u.password
    except (ValueError,TypeError):
        return False

def normalize(entry, timestamp):
    if not isinstance(entry,dict):
        return None
    link=str(entry.get("shareUrl") or entry.get("url") or "").strip()[:2000]
    title=clean(entry.get("title"),180)
    if len(title)<5 or not https_url(link):
        return None
    deadline=str(entry.get("deadline") or "").strip()
    date=deadline[:10] if re.match(r"^\d{4}-\d{2}-\d{2}(?:T|$)",deadline) else ""
    # Brabble publishes currently open entries, but a stale cached listing may
    # already have passed its deadline. Do not advertise it as current.
    if date:
        try:
            if datetime.strptime(date,"%Y-%m-%d").date()<datetime.now(timezone.utc).date():
                return None
        except ValueError:
            date=""
    kind=clean(entry.get("type"),35).upper()
    category="Hackathon" if kind=="HACKATHON" else "Event" if kind in ("INNOVATION","DESIGN") else "Other"
    organizer=clean(entry.get("organiser"),90)
    platform=clean(entry.get("platform"),50)
    mode=clean(entry.get("mode"),30).title()
    city=clean(entry.get("city"),80)
    team=clean(entry.get("team"),35)
    fee=clean(entry.get("fee"),40)
    prize=entry.get("prize") or {}
    prize_label=clean(prize.get("label"),60) if isinstance(prize,dict) else ""
    eligibility=entry.get("eligibility") or []
    elig=", ".join(clean(x,100) for x in eligibility[:2]) if isinstance(eligibility,list) else ""
    details=[v for v in (
        "Organiser: "+organizer if organizer else "",
        "Platform: "+platform if platform else "",
        "Team: "+team if team else "",
        "Fee: "+fee if fee else "",
        "Prize: "+prize_label if prize_label and prize_label.lower()!="see listing" else "",
        "Eligibility hint: "+elig if elig else ""
    ) if v]
    summary=clean(" · ".join(details),500) or "Check original organiser page for eligibility and registration."
    return {
        "id":hashlib.sha256(link.split("#")[0].rstrip("/").encode()).hexdigest()[:32],
        "title":title,"summary":summary,"url":link,"source":API_SOURCE,
        "category":category,"location":" · ".join(x for x in (mode,city) if x) or "See original organiser",
        "deadline":date,"published":"","seen_at":timestamp,"state":"new",
        "verification":"Brabble aggregated lead; verify dates, work eligibility and official registration with organiser."
    }

def fetch_brabble(timestamp, key=None, http_get=None):
    """Return (items, error). An absent API key is a normal, zero-request state."""
    key=key if key is not None else os.environ.get("BRABBLE_API_KEY","")
    if not key:
        return [],None
    http_get=http_get or requests.get
    found={}
    try:
        for offset in (0,200,400):
            response=http_get(URL,params={"hub":"college-students","limit":200,"offset":offset},
                timeout=14,headers={"Authorization":"Bearer "+key,
                                    "User-Agent":"OpportunityOS/2.1 (personal student discovery)"})
            response.raise_for_status()
            payload=response.json()
            entries=payload.get("listings",[])
            if not isinstance(entries,list):
                return list(found.values()),"Brabble API returned an unexpected payload"
            for raw in entries:
                row=normalize(raw,timestamp)
                if row:found[row["id"]]=row
            total=payload.get("total")
            if len(entries)<200 or (isinstance(total,int) and offset+len(entries)>=total):
                break
        return list(found.values()),None
    except (requests.RequestException,ValueError,TypeError,KeyError):
        return list(found.values()),"Brabble API unavailable; public RSS remains enabled"
