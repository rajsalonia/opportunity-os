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
