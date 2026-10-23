"""Application-pack tests: synthetic data only."""
import pytest
from application_profile import application_pack, clean_public_details

JOB={"id":"abc123","company":"SampleCo","title":"Backend Intern","location":"Remote India",
     "url":"https://example.org/careers/123","provider":"manual"}

def test_pack_contains_public_links_but_no_invented_grades():
    pack=application_pack(JOB,{},True)
    assert pack["application"]["status"]=="prepared_not_submitted"
    assert pack["education"]["graduation_year"]=="2028"
    assert pack["education"]["cgpa"]==""
    assert pack["education"]["percentage"]==""
    assert pack["links"]["github"].endswith("/rajsalonia")
    assert len(pack["projects"])==4
    assert pack["declarations"]["visa_sponsorship"]=="ask_owner"
    assert pack["resume"]["owner_download_path"]=="/api/resume/download"

def test_optional_professional_values_validation():
    assert clean_public_details({"linkedin":"https://www.linkedin.com/in/example","cgpa":"8.2"})["cgpa"]=="8.2"
    for data in [{"cgpa":"17"},{"percentage":"101"},{"portfolio":"javascript:alert(1)"},{"passing_month":"2029-01"},{"cgpa":"7.8 SGPA"}]:
        with pytest.raises(ValueError):clean_public_details(data)

def test_explicit_grade_is_used_only_if_provided():
    item=application_pack(JOB,{"first_name":"Sample","last_name":"Applicant",
         "email":"example@invalid.test","phone":"00000000","cgpa":"8.4"},False)
    assert item["education"]["cgpa"]=="8.4"
    assert item["education"]["percentage"]==""
    assert item["resume"]["available_in_private_vault"] is False
