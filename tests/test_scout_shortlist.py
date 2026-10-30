"""Shortlist research with job boards (scout PRD §5.2a, amended 2026-10-31).

About 20 candidates a day, scored with the §5.2a weights, ranked in code; every
one at or above the threshold is kept, best first, up to `research.shortlist`
(default 10). The rest are remembered in `scout_rejections` with their score.
"""

import json

import pytest
from click.testing import CliRunner

from jura_growth import caps, db
from jura_growth.agents import scout
from jura_growth.agents.scout import contact, settings
from jura_growth.cli import cli

from test_scout_support import add, at, configure, contact_page, lead_data, scout_env, seed  # noqa: F401


# --- §5.2a points 1 and 4: the two settings ---------------------------------


def test_candidates_and_shortlist_default_to_twenty_and_ten():
    assert settings.candidates() == 20
    assert settings.shortlist() == 10


def test_config_may_lower_the_shortlist_and_candidates_but_never_raise_them(monkeypatch):
    configure(monkeypatch, research={"candidates": 12, "shortlist": 3})
    assert settings.candidates() == 12 and settings.shortlist() == 3
    configure(monkeypatch, research={"candidates": 500, "shortlist": 500})
    assert settings.candidates() == caps.SCOUT_CANDIDATES_PER_RUN == 40
    assert settings.shortlist() == caps.SCOUT_SHORTLIST_PER_DAY == 10
    configure(monkeypatch, research={"candidates": -1, "shortlist": -1})
    assert settings.candidates() == 1 and settings.shortlist() == 0


def test_daily_target_is_retired():
    assert "daily_target" not in settings.DEFAULTS["research"]
    assert not hasattr(settings, "daily_target")


def test_today_reports_candidates_shortlist_and_room(isolated, monkeypatch, conn):
    at(monkeypatch, "2026-10-26T09:00:00+08:00")
    seed(conn, 1, queue=False)
    conn.commit()
    info = json.loads(CliRunner().invoke(cli, ["scout", "today", "--json"]).output)
    assert info["candidates"] == 20 and info["shortlist"] == 10
    assert info["kept_today"] == 1 and info["remaining"] == 9
    assert "daily_target" not in info and "added_today" not in info


def test_precheck_skips_once_the_shortlist_is_kept(conn, monkeypatch):
    configure(monkeypatch, research={"shortlist": 1})
    assert scout.precheck("scout-research", conn) is None
    seed(conn, 1, queue=False)
    assert "shortlist of 1" in scout.precheck("scout-research", conn)


# --- §5.2a point 6: job boards are evidence only, never a contact source ------

JOB_AD_SOURCES = [
    "https://www.mycareersfuture.gov.sg/job/logistics/admin-assistant-alder-logistics-1a2b3c",
    "https://sg.jobstreet.com/job/80123456",
    "https://www.jobstreet.com.sg/en/job/admin-executive-123",
    "https://sg.indeed.com/viewjob?jk=abc123",
    "https://www.indeed.com.sg/viewjob?jk=abc123",
    "https://www.linkedin.com/jobs/view/3912345678",
    "https://www.glassdoor.sg/job-listing/admin-assistant-alder-logistics-JV_IC3235921.htm",
    "https://www.glassdoor.com/job-listing/admin-JV_IC1.htm",
    "https://www.fastjobs.sg/singapore-job-ad/123/admin",
    "https://www.foundit.sg/job/admin-executive-alder-logistics-123",
    "https://www.recruitexpress.com.sg/jobs/admin-assistant-123",
    "https://www.kellyservices.com.sg/sg/jobs/123",
    "https://www.michaelpage.com.sg/job-detail/admin/ref/123",
    "https://jobs.lever.co/alderlogistics/123",
    "https://apply.workable.com/alder-logistics/j/ABC123/",
    "https://alderlogistics.recruitee.com/o/admin",
    "https://www.sgtalentrecruitment.com/jobs/admin",  # an unlisted agency, by its name
]


@pytest.mark.parametrize("source", JOB_AD_SOURCES, ids=lambda u: contact.host_of(u))
def test_a_contact_source_on_a_job_board_or_recruiter_is_refused(conn, source):
    data = lead_data(1, contact={"email": "info@alderlogistics.sg", "source_url": source})
    outcome = add(conn, data, page_html=contact_page("info@alderlogistics.sg"))
    assert outcome.status == "rejected"
    assert "evidence only, never a contact source" in outcome.reasons[0]
    assert db.scalar(conn, "SELECT count(*) FROM leads") == 0


@pytest.mark.parametrize("path", ["/careers", "/careers/admin-assistant", "/jobs/123", "/vacancies", "/join-us"])
def test_a_job_ad_on_the_company_own_site_is_not_a_contact_source_either(conn, path):
    source = f"https://www.alderlogistics.sg{path}"
    data = lead_data(1, contact={"email": "info@alderlogistics.sg", "source_url": source})
    outcome = add(conn, data, page_html=contact_page("info@alderlogistics.sg"))
    assert outcome.status == "rejected" and "evidence only, never a contact source" in outcome.reasons[0]


def test_a_careers_subdomain_is_not_a_contact_source():
    assert contact.job_ad_problem("https://careers.alderlogistics.sg/") is not None
    assert contact.job_ad_problem("https://jobs.alderlogistics.sg/admin") is not None
    assert contact.job_ad_problem("https://www.alderlogistics.sg/contact") is None
    assert contact.job_ad_problem("https://www.alderlogistics.sg/services/job-sheets") is None


def test_a_contact_form_on_a_job_ad_is_refused(conn):
    data = lead_data(1, contact={"form_url": "https://www.alderlogistics.sg/careers/apply"})
    outcome = add(conn, data)
    assert outcome.status == "rejected" and "evidence only, never a contact source" in outcome.reasons[0]


@pytest.mark.parametrize("website", ["https://sg.jobstreet.com", "https://www.recruitexpress.com.sg", "https://www.glassdoor.sg", "https://www.indeed.com.sg"])
def test_a_job_board_or_recruiter_is_never_a_lead_website(conn, website):
    domain = contact.site_domain(website)
    data = lead_data(1, website=website, source_urls=[f"{website}/about"],
                     contact={"email": f"info@{domain}", "source_url": f"{website}/contact"})
    outcome = add(conn, data)
    assert outcome.status == "rejected" and "not the company's own website" in outcome.reasons[0]
