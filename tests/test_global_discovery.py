"""Regression checks for worldwide job feed normalization."""
from global_discovery import FEEDS, work_details, normalize


def test_remote_scope_is_not_work_authorization():
    result = work_details('Anywhere', 'Python internship', True)
    assert result['work_mode'] == 'Remote'
    assert result['india_eligible_confirmed'] is False
    assert result['remote_scope'] == 'Worldwide claimed / verify'


def test_reject_insecure_job_links():
    assert normalize('jobicy', 'Example', 'Python Intern', 'Anywhere', 'Internship', 'http://example.com/job', lambda *args: (75, ''), True) is None


def test_public_feed_registry():
    assert {feed[0] for feed in FEEDS} == {'jobicy', 'remotive', 'arbeitnow'}


def test_jobicy_normalizes_and_attributes_original_url():
    from global_discovery import fetch_public_feed
    class FakeResponse:
        def raise_for_status(self): pass
        def json(self):
            return {'jobs':[{'companyName':'Sample Startup','jobTitle':'Junior Backend Developer',
                    'jobGeo':'Anywhere','jobDescription':'2028 graduate internship in Python',
                    'url':'https://jobicy.com/jobs/sample-backend'}]}
    jobs,error=fetch_public_feed(FEEDS[0],lambda *args:(78,''),http_get=lambda *a,**kw:FakeResponse())
    assert error is None and len(jobs)==1
    assert jobs[0]['provider']=='jobicy'
    assert jobs[0]['url']=='https://jobicy.com/jobs/sample-backend'
    assert jobs[0]['location'].startswith('Remote')


def test_feed_rejects_senior_or_2028_excluded_roles():
    from global_discovery import fetch_public_feed
    class FakeResponse:
        def raise_for_status(self): pass
        def json(self):
            return {'jobs':[{'company_name':'Senior Co','title':'Senior Backend Engineer',
                             'candidate_required_location':'Anywhere','description':'Junior skills',
                             'url':'https://remotive.com/remote-jobs/senior'},
                            {'company_name':'Example','title':'Backend Intern',
                             'candidate_required_location':'India','description':'2028 graduates only',
                             'url':'https://remotive.com/remote-jobs/intern'}]}
    jobs,error=fetch_public_feed(FEEDS[1],lambda *args:(80,''),http_get=lambda *a,**kw:FakeResponse())
    assert error is None and len(jobs)==1
    assert jobs[0]['company']=='Example'
