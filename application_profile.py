"""Reusable, human-verifiable job application packs for Opportunity OS.

Do not treat a resume, prior conversation, or remote tag as evidence of legal
authorization, exact grades, visa status or employer application acceptance.
"""
from urllib.parse import urlsplit

PUBLIC_PROFESSIONAL_PROFILE = {
    "college": "Bhagwan Parshuram Institute of Technology",
    "degree": "B.Tech in Computer Science and Engineering",
    "graduation_year": "2028",
    "city": "New Delhi",
    "country": "India",
    "linkedin": "https://www.linkedin.com/in/rajsalonia",
    "github": "https://github.com/rajsalonia",
    "portfolio": "https://raj-salonia-portfolio.vercel.app/",
    "projects": [
        {"name":"RoofShift AI", "url":"https://github.com/rajsalonia/roofshift-ai"},
        {"name":"CityGraph", "url":"https://github.com/rajsalonia/citygraph"},
        {"name":"BoloAI", "url":"https://github.com/rajsalonia/BoloAI"},
        {"name":"ReviewLens", "url":"https://github.com/rajsalonia/ReviewLens"}
    ],
    "experience": [{
        "company":"Dexpert Systems",
        "role":"Software Engineering Intern",
        "start":"2026-04",
        "end":"2026-07"
    }],
}

OPTIONAL_PROFILE_FIELDS = (
    "college", "degree", "city", "country", "linkedin", "github", "portfolio",
    "cgpa", "percentage", "gpa_scale", "passing_month", "primary_project"
)

def safe_https_url(value):
    if not isinstance(value,str) or len(value)>1200:return False
    try:
        u=urlsplit(value)
        return u.scheme=="https" and bool(u.hostname) and not u.username and not u.password
    except ValueError:return False

def clean_public_details(data):
    """Validate optional details for future form packages without inventing answers."""
    if not isinstance(data,dict):raise ValueError("Optional profile fields must be an object.")
    result={}
    for name in OPTIONAL_PROFILE_FIELDS:
        if name not in data:continue
        value=data[name]
        if not isinstance(value,str):raise ValueError(f"{name} must be a string.")
        value=value.strip()
        if len(value)>240:raise ValueError(f"{name} is too long.")
        if name in ("linkedin","github","portfolio") and value and not safe_https_url(value):
            raise ValueError(f"{name} must be a valid HTTPS URL.")
        if name in ("cgpa","percentage"):
            # Never infer or convert SGPA to CGPA or percentage.
            if value:
                try:num=float(value)
                except ValueError:raise ValueError(f"Enter verified {name} or leave it blank.")
                if name=="cgpa" and not (0<=num<=10):
                    raise ValueError("CGPA must be between 0 and 10.")
                if name=="percentage" and not (0<=num<=100):
                    raise ValueError("Percentage must be between 0 and 100.")
        if name=="passing_month" and value and (len(value)!=7 or value[4]!="-"
                or value[:4]!="2028" or value[5:] not in {f"{x:02}" for x in range(1,13)}):
            raise ValueError("Graduation month must be YYYY-MM in 2028, or blank.")
        result[name]=value
    return result

def application_pack(job, approved_profile, resume_available):
    """Build a reusable pack; never say 'submitted' or invent missing details."""
    if not job or not isinstance(job,dict):raise ValueError("Job not found.")
    profile=dict(PUBLIC_PROFESSIONAL_PROFILE)
    selected=(approved_profile or {})
    for name in OPTIONAL_PROFILE_FIELDS:
        if name in selected:profile[name]=selected[name]
    contact={
        "first_name":selected.get("first_name",""),
        "last_name":selected.get("last_name",""),
        "full_name":(" ".join(filter(None,[selected.get("first_name",""),selected.get("last_name","")]))),
        "email":selected.get("email",""),
        "phone":selected.get("phone","")
    }
    return {
        "format":"opportunity-os-autofill-pack-v1",
        "application":{
            "job_id":job["id"],
            "company":job["company"],"title":job["title"],"location":job.get("location") or "",
            "provider":job.get("provider") or "unknown","official_url":job["url"],
            "status":"prepared_not_submitted",
            "remote_eligibility":"Review official employer location restrictions"
        },
        "contact":contact,
        "education":{
            "institution":profile["college"],"degree":profile["degree"],
            "graduation_year":"2028","graduation_month":profile.get("passing_month",""),
            "city":profile["city"],"country":profile["country"],
            "cgpa":profile.get("cgpa",""),"percentage":profile.get("percentage",""),
            "gpa_scale":profile.get("gpa_scale","")
        },
        "links":{k:profile[k] for k in ("linkedin","github","portfolio")},
        "projects":profile["projects"],
        "experience":profile["experience"],
        "resume":{
            "available_in_private_vault":bool(resume_available),
            "owner_download_path":"/api/resume/download",
            "must_select_original_pdf_in_browser":True
        },
        "declarations":{
            "india_work_authorization":(
                "confirmed_by_owner" if selected.get("work_authorized_india") is True else "not_confirmed"),
            "foreign_work_authorization":"ask_owner",
            "visa_sponsorship":"ask_owner",
            "privacy_consent":"ask_owner_per_employer",
            "eeo_demographics":"ask_owner"
        },
        "notes":"Autofill pack only. No employer form has been submitted. Read and verify all employer-specific answers."
    }
