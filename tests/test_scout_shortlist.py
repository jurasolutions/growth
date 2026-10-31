"""Shortlist research with job boards (scout PRD §5.2a, amended 2026-10-31).

About 20 candidates a day, scored with the §5.2a weights, ranked in code; every
one at or above the threshold is kept, best first, up to `research.shortlist`
(default 10). The rest are remembered in `scout_rejections` with their score.
"""

import json

import httpx
import pytest
from click.testing import CliRunner

from jura_growth import caps, db
from jura_growth.agents import scout
from jura_growth.agents.scout import contact, settings
from jura_growth.cli import cli

from test_scout_support import add, at, configure, contact_page, lead_data, outbox, pages, scout_env, seed  # noqa: F401

MONDAY_9AM = "2026-10-26T09:00:00+08:00"
WEIGHTS = {
    "industry_fit": 20,
    "size_fit": 15,
    "hiring_signals": 30,
    "paperwork_signals": 20,
    "specific_observations": 5,
    "enquiry_address": 10,
}


def posting(url="https://www.mycareersfuture.gov.sg/job/admin-assistant-1a2b", *, seen="2026-10-20",
            title="Admin assistant (logistics)", duties=("key in delivery orders", "prepare invoices")):
    return {"url": url, "title": title, "seen": seen, "duties": list(duties)}


def breakdown(score: int) -> dict:
    """`score` spread over the §5.2a factors in order, each up to its weight."""
    left, parts = score, {}
    for name in ("enquiry_address", "industry_fit", "size_fit", "hiring_signals", "paperwork_signals", "specific_observations"):
        parts[name] = min(left, WEIGHTS[name])
        left -= parts[name]
    assert left == 0
    return parts


def candidate(n: int, score: int, **overrides) -> dict:
    data = lead_data(
        n,
        score=score,
        score_breakdown=breakdown(score),
        hiring_evidence=[posting(f"https://sg.jobstreet.com/job/{8000 + n}")],
        comparison=f"Candidate {n}: current admin hiring and paper delivery orders",
    )
    data.update(overrides)
    return data


def client_for(candidates: list[dict]):
    """Serve every candidate's contact page with its own address."""
    mapping = {}
    for c in candidates:
        found = c.get("contact") or {}
        if found.get("source_url"):
            mapping[found["source_url"]] = contact_page(found.get("email", ""))
    return pages(mapping)


def submit(conn, candidates: list[dict], client=None):
    from jura_growth.agents.scout import shortlist

    return shortlist.submit(conn, {"candidates": candidates}, client=client or client_for(candidates))


def kept_scores(conn) -> list[int]:
    return [r["score"] for r in db.rows(conn, "SELECT score FROM leads ORDER BY score DESC")]


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


# Code review P1: every way round the careers-page rule the review found, and a few more.
CAREERS_BYPASSES = [
    "/%63areers/", "/%2563areers/", "/CAREERS", "/Careers/", "/careers.html", "/careers-2/", "/careers_2",
    "/jobs.php", "/job-openings", "/jobopenings", "/vacancies.aspx", "/vacancy", "/join-our-team.html",
    "/joinus", "/join-us/", "/career-opportunities", "/en/we-are-hiring", "/work-with-us", "/recruitment",
    "/index.php?page=careers", "/?p=jobs", "/about#careers", "/about-us/careers/admin",
]


@pytest.mark.parametrize("path", CAREERS_BYPASSES)
def test_no_spelling_of_a_careers_page_passes(path):
    assert contact.job_ad_problem(f"https://www.alderlogistics.sg{path}") is not None, path


@pytest.mark.parametrize("path", ["/contact", "/contact-us", "/about", "/services/job-sheets", "/job-sheet-printing",
                                  "/enquiry", "/?lang=en", "/our-team", "/locations#east", "/projects/joinery"])
def test_ordinary_pages_are_still_contact_sources(path):
    assert contact.job_ad_problem(f"https://www.alderlogistics.sg{path}") is None, path


@pytest.mark.parametrize("path", ["/%63areers/", "/careers.html", "/index.php?page=careers"])
def test_a_bypass_spelling_is_refused_when_adding_a_lead(conn, path):
    source = f"https://www.alderlogistics.sg{path}"
    outcome = add(conn, lead_data(1, contact={"email": "info@alderlogistics.sg", "source_url": source}))
    assert outcome.status == "rejected" and "evidence only, never a contact source" in outcome.reasons[0]


def redirecting(mapping, redirects):
    def handler(request):
        key = str(request.url)
        if key in redirects:
            return httpx.Response(302, headers={"location": redirects[key]})
        if key in mapping:
            return httpx.Response(200, text=mapping[key], headers={"content-type": "text/html"})
        return httpx.Response(404, text="not found")

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


@pytest.mark.parametrize("target", ["https://careers.alderlogistics.sg/apply", "https://www.alderlogistics.sg/%63areers/"])
def test_a_contact_page_that_redirects_to_a_careers_page_is_refused(conn, monkeypatch, target):
    """Code review P1: the rule is applied to the page the code actually read."""
    at(monkeypatch, MONDAY_9AM)
    c = candidate(1, 80)
    client = redirecting({target: contact_page(c["contact"]["email"])}, {c["contact"]["source_url"]: target})
    result = submit(conn, [c], client=client)
    assert result.kept == [] and "evidence only, never a contact source" in result.candidates[0]["reasons"][0]
    assert db.scalar(conn, "SELECT count(*) FROM contacts") == 0


def test_check_contact_refuses_a_redirect_to_a_careers_page(isolated, monkeypatch):
    from jura_growth.agents.scout import contact as contact_mod

    monkeypatch.setattr(contact_mod, "http_client", lambda: redirecting(
        {"https://www.alderlogistics.sg/careers.html": contact_page("info@alderlogistics.sg")},
        {"https://www.alderlogistics.sg/contact": "https://www.alderlogistics.sg/careers.html"}))
    result = CliRunner().invoke(cli, ["scout", "check-contact", "--website", "https://www.alderlogistics.sg",
                                      "--email", "info@alderlogistics.sg", "--source", "https://www.alderlogistics.sg/contact"])
    assert result.exit_code == 1 and "evidence only, never a contact source" in result.output


@pytest.mark.parametrize("url", [
    "https://glints.com/sg/opportunities/jobs/1", "https://www.stjobs.sg/job/1", "https://jobs.ashbyhq.com/acme/1",
    "https://acme.jobs.personio.com/job/1", "https://www.adzuna.sg/details/1", "https://www.kalibrr.com/c/acme/jobs/1",
    "https://jobs.jobvite.com/acme/job/1", "https://acme.teamtailor.com/jobs/1", "https://www.manatal.com/x",
    "https://acme.applytojob.com/apply/1",
])
def test_more_job_boards_and_applicant_tracking_hosts_are_known(url):
    """Code review P5."""
    assert contact.job_ad_problem(url) is not None
    assert contact.is_job_board(contact.host_of(url))


@pytest.mark.parametrize("local", ["career", "job", "recruitment", "recruit", "talent", "hiring", "apply", "resume", "cv"])
def test_recruitment_inboxes_are_not_enquiry_addresses(local):
    """Code review P7."""
    from jura_growth.role_addresses import not_for_enquiries

    assert not_for_enquiries(f"{local}@alderlogistics.sg")
    assert not_for_enquiries(f"{local}2@alderlogistics.sg") and not_for_enquiries(f"{local}.sg@alderlogistics.sg")


@pytest.mark.parametrize("address", ["cvlogistics@gmail.com", "talentdance@gmail.com", "jobmaster.sg@gmail.com",
                                     "applyfix@gmail.com", "hrithik.tan@acme.sg"])
def test_a_business_name_that_starts_with_a_recruitment_word_is_still_an_address(address):
    """Re-review R9: the words are matched whole (or before a separator or number), not as prefixes."""
    from jura_growth.role_addresses import not_for_enquiries

    assert not not_for_enquiries(address)


# --- re-review R1 and R2: careers pages by any host label, and field-service pages kept ----


@pytest.mark.parametrize("url", [
    "https://www.careers.alderlogistics.sg/", "https://sg.careers.alderlogistics.sg/", "https://careers-sg.alderlogistics.sg/",
    "https://career-portal.alderlogistics.sg/", "https://jobs2.alderlogistics.sg/",
    "https://www.alderlogistics.sg/opportunities", "https://www.alderlogistics.sg/people/opportunities",
    "https://www.alderlogistics.sg/work-for-us", "https://www.alderlogistics.sg/openings",
    "https://www.alderlogistics.sg/internship", "https://www.alderlogistics.sg/karriere",
    "https://www.alderlogistics.sg/zh/招聘", "https://www.alderlogistics.sg/zh/%E6%8B%9B%E8%81%98",
    "https://www.alderlogistics.sg/zh/职位", "https://www.alderlogistics.sg/ms/kerjaya",
    "https://www.alderlogistics.sg/jawatan-kosong", "https://www.alderlogistics.sg/ｃａｒｅｅｒｓ",
    "https://www.alderlogistics.sg/vacancies", "https://www.alderlogistics.sg/staff-vacancies",
    "https://www.alderlogistics.sg/we-are-hiring", "https://www.alderlogistics.sg/jobs",
])
def test_more_careers_pages_are_refused(url):
    assert contact.job_ad_problem(url, "alderlogistics.sg") is not None, url


@pytest.mark.parametrize("url", [
    "https://www.alderlogistics.sg/book-a-job", "https://www.alderlogistics.sg/job-request",
    "https://www.alderlogistics.sg/request-a-job-quote", "https://www.alderlogistics.sg/our-jobs",
    "https://www.alderlogistics.sg/equipment-hiring", "https://www.alderlogistics.sg/car-hiring-rates",
    "https://www.alderlogistics.sg/office-vacancies", "https://www.alderlogistics.sg/vacancies/units",
    "https://www.alderlogistics.sg/join-us-for-dinner", "https://www.alderlogistics.sg/careers/../contact",
    "https://apply.alderlogistics.sg/", "https://www.careerworks.sg/contact",
])
def test_field_service_and_property_pages_are_still_contact_sources(url):
    domain = "careerworks.sg" if "careerworks" in url else "alderlogistics.sg"
    assert contact.job_ad_problem(url, domain) is None, url


# --- re-review R6: hiring evidence is current ---------------------------------


def test_a_posting_seen_more_than_twelve_months_ago_is_refused(conn, monkeypatch):
    at(monkeypatch, MONDAY_9AM)
    bad(conn, [candidate(1, 80, hiring_evidence=[posting(seen="2025-10-25")])], "within the last 12 months")
    assert len(submit(conn, [candidate(1, 80, hiring_evidence=[posting(seen="2025-10-27")])]).kept) == 1


# --- re-review R3: product names and the company's own name are not people -----


@pytest.mark.parametrize("text", [
    "Proficient in MS Excel and MS Word", "Update the MS Teams channel", "Use Ms Excel daily",
    "Prepare DR forms and DO slips", "Key in orders in Google Sheets, Xero and QuickBooks",
])
def test_product_names_survive_the_name_filter(text):
    from jura_growth import privacy

    assert privacy.strip_personal(text) == (text, False)


def test_the_company_own_name_survives_the_name_filter(conn, monkeypatch):
    at(monkeypatch, MONDAY_9AM)
    evidence = [posting(title="Admin assistant at Dr Aircon", duties=("prepare Dr Aircon service reports",))]
    result = submit(conn, [candidate(1, 80, company="Dr Aircon Services Pte Ltd", hiring_evidence=evidence,
                                     comparison="Dr Aircon is hiring for service reports")])
    assert len(result.kept) == 1
    row = db.one(conn, "SELECT hiring_evidence_json, comparison FROM leads")
    assert "Dr Aircon" in json.loads(row["hiring_evidence_json"])[0]["title"] and "Dr Aircon" in row["comparison"]


def test_a_person_is_still_stripped_beside_a_product(conn):
    from jura_growth import privacy

    assert privacy.strip_personal("Ms Tan uses MS Excel") == ("[name removed] uses MS Excel", True)


# --- re-review R8: a lead added by hand meanwhile never takes the day past the shortlist ---


def test_a_lead_added_by_hand_during_a_batch_still_holds_the_shortlist(conn, monkeypatch):
    from jura_growth.agents.scout import leads

    configure(monkeypatch, research={"shortlist": 2})
    at(monkeypatch, MONDAY_9AM)
    real = leads.assess
    added, started = [], []

    def hand_add_meanwhile(*args, **kwargs):
        if not started:
            started.append(True)
            added.append(add(conn, lead_data(9)))  # Ting Yu, in Terminal, mid-batch
        return real(*args, **kwargs)

    monkeypatch.setattr(leads, "assess", hand_add_meanwhile)
    result = submit(conn, [candidate(1, 90), candidate(2, 80)])
    assert added[0].status == "added"
    assert leads.added_today(conn) == 2 and len(result.kept) == 1
    passed = next(c for c in result.candidates if c["score"] == 80)
    assert passed["status"] == "not_kept" and "shortlist of 2 was full" in passed["reasons"][0]


def test_a_contact_form_on_a_job_ad_is_refused(conn):
    data = lead_data(1, contact={"form_url": "https://www.alderlogistics.sg/careers/apply"})
    outcome = add(conn, data)
    assert outcome.status == "rejected" and "evidence only, never a contact source" in outcome.reasons[0]


def test_hiring_evidence_on_a_job_board_is_allowed(conn):
    """Evidence only: the posting's URL is recorded; the address still comes from the company's site."""
    evidence = [posting("https://www.mycareersfuture.gov.sg/job/admin-assistant-alder-1a2b")]
    outcome = add(conn, lead_data(1, hiring_evidence=evidence, comparison="Two current admin postings"))
    assert outcome.status == "added", outcome.reasons
    row = db.one(conn, "SELECT hiring_evidence_json, comparison FROM leads WHERE id = ?", (outcome.lead_id,))
    assert json.loads(row["hiring_evidence_json"]) == evidence
    assert row["comparison"] == "Two current admin postings"
    assert db.scalar(conn, "SELECT source_url FROM contacts") == "https://www.alderlogistics.sg/contact"


@pytest.mark.parametrize("website", ["https://sg.jobstreet.com", "https://www.glassdoor.sg", "https://www.indeed.com.sg",
                                     "https://glints.com"])
def test_a_job_board_is_never_a_lead_website(conn, website):
    domain = contact.site_domain(website)
    data = lead_data(1, website=website, source_urls=[f"{website}/about"],
                     contact={"email": f"info@{domain}", "source_url": f"{website}/contact"})
    outcome = add(conn, data)
    assert outcome.status == "rejected" and "not the company's own website" in outcome.reasons[0]


@pytest.mark.parametrize("website", ["https://www.recruitexpress.com.sg", "https://www.sgtalentrecruitment.com"])
def test_a_recruitment_agency_may_be_a_lead_in_its_own_right(conn, website):
    """Conductor's decision on review P6: a recruiter is refused only as the contact source
    for another company. Its own enquiry address on its own contact page is fine."""
    domain = contact.site_domain(website)
    data = lead_data(1, website=website, source_urls=[f"{website}/about"],
                     contact={"email": f"info@{domain}", "source_url": f"{website}/contact"})
    outcome = add(conn, data)
    assert outcome.status == "added", outcome.reasons
    assert contact.job_ad_problem(f"{website}/contact", domain) is None
    assert contact.job_ad_problem(f"{website}/contact") is not None  # for anyone else, it's a recruiter's site
    assert contact.job_ad_problem(f"{website}/jobs/123", domain) is not None  # its own job ads stay evidence only


# --- §5.2a point 3: the weights ---------------------------------------------


def test_the_weights_are_the_prd_table():
    from jura_growth.agents.scout import scoring

    assert scoring.WEIGHTS == WEIGHTS and sum(scoring.WEIGHTS.values()) == 100


def test_today_gives_the_weights(isolated, monkeypatch):
    at(monkeypatch, MONDAY_9AM)
    info = json.loads(CliRunner().invoke(cli, ["scout", "today", "--json"]).output)
    assert info["weights"] == WEIGHTS


# --- §5.2a point 4: rank every candidate, keep the best up to the shortlist ----


SCORES = [91, 58, 77, 64, 88, 45, 70, 83, 61, 59, 95, 72, 66, 80, 52, 74, 68, 86, 79, 62]


def test_twenty_candidates_keep_the_ten_best_at_or_above_the_threshold(conn, monkeypatch):
    at(monkeypatch, MONDAY_9AM)
    candidates = [candidate(n, s) for n, s in enumerate(SCORES, start=1)]
    result = submit(conn, candidates)
    best_ten = sorted(SCORES, reverse=True)[:10]
    assert kept_scores(conn) == best_ten
    assert [c["score"] for c in result.kept] == best_ten
    assert [c["rank"] for c in result.kept] == list(range(1, 11))
    # The rest are remembered as researched, with their score and why.
    rows = {r["domain"]: r for r in db.rows(conn, "SELECT * FROM scout_rejections")}
    assert len(rows) == 10
    not_kept = [c for c in candidates if c["score"] not in best_ten]
    for c in not_kept:
        row = rows[contact.site_domain(c["website"])]
        assert row["score"] == c["score"]
        if c["score"] >= 60:
            assert "today's shortlist of 10 was full" in row["reason"] and "ranked" in row["reason"]
        else:
            assert f"score {c['score']} is below 60" in row["reason"]


def test_a_weak_day_keeps_fewer_and_never_pads(conn, monkeypatch):
    at(monkeypatch, MONDAY_9AM)
    scores = [72, 40, 55, 61, 30, 59, 64, 20, 50, 66]
    result = submit(conn, [candidate(n, s) for n, s in enumerate(scores, start=1)])
    assert kept_scores(conn) == [72, 66, 64, 61]
    assert len(result.kept) == 4
    assert db.scalar(conn, "SELECT count(*) FROM scout_rejections") == 6


def test_a_config_shortlist_of_three_keeps_three(conn, monkeypatch):
    configure(monkeypatch, research={"shortlist": 3})
    at(monkeypatch, MONDAY_9AM)
    submit(conn, [candidate(n, s) for n, s in enumerate(SCORES, start=1)])
    assert kept_scores(conn) == [95, 91, 88]


def test_ties_keep_the_order_they_were_ranked_in(conn, monkeypatch):
    configure(monkeypatch, research={"shortlist": 1})
    at(monkeypatch, MONDAY_9AM)
    result = submit(conn, [candidate(1, 80), candidate(2, 80)])
    assert [c["company"] for c in result.kept] == ["Alder Logistics Pte Ltd"]


def test_a_candidate_refused_on_its_contact_gives_its_place_to_the_next(conn, monkeypatch):
    at(monkeypatch, MONDAY_9AM)
    candidates = [candidate(n, s) for n, s in enumerate(SCORES, start=1)]
    client = client_for(candidates[1:])  # candidate 1 (91) has no page publishing its address
    result = submit(conn, candidates, client=client)
    assert 91 not in kept_scores(conn) and len(result.kept) == 10
    assert kept_scores(conn) == sorted([s for s in SCORES if s != 91], reverse=True)[:10]
    refused = next(c for c in result.candidates if c["score"] == 91)
    assert refused["status"] == "rejected" and "could not verify" in refused["reasons"][0]


def test_a_day_is_ranked_once(conn, monkeypatch):
    """Kept leads can't be taken back, so a later batch could only keep the best of
    itself, not of the day. The day's candidates are ranked together, once."""
    at(monkeypatch, MONDAY_9AM)
    first = submit(conn, [candidate(n, s) for n, s in enumerate([75, 62, 50, 81, 40, 66], start=1)])
    assert len(first.kept) == 4
    at(monkeypatch, "2026-10-26T11:00:00+08:00")
    from jura_growth.agents.scout import leads

    with pytest.raises(leads.LeadError, match="today's candidates were ranked at 09:00"):
        submit(conn, [candidate(n, 99) for n in range(7, 10)])
    assert kept_scores(conn) == [81, 75, 66, 62]
    assert "already ranked" in scout.precheck("scout-research", conn)
    ranking = db.one(conn, "SELECT * FROM scout_rankings")
    assert ranking["day"] == "2026-10-26" and ranking["candidates"] == 6 and ranking["kept"] == 4
    at(monkeypatch, "2026-10-27T09:00:00+08:00")
    assert len(submit(conn, [candidate(n, 99) for n in range(7, 10)]).kept) == 3


def test_a_refused_batch_leaves_the_day_unranked(conn, monkeypatch):
    at(monkeypatch, MONDAY_9AM)
    bad(conn, [candidate(1, 80, score_breakdown=None)], "score_breakdown")
    assert db.scalar(conn, "SELECT count(*) FROM scout_rankings") == 0
    assert len(submit(conn, [candidate(1, 80)]).kept) == 1


def test_kept_leads_are_the_best_of_the_day(conn, monkeypatch):
    at(monkeypatch, MONDAY_9AM)
    submit(conn, [candidate(n, s) for n, s in enumerate(SCORES, start=1)])
    kept = kept_scores(conn)
    passed_over = [r["score"] for r in db.rows(conn, "SELECT score FROM scout_rejections WHERE reason LIKE '%shortlist%'")]
    assert len(kept) == 10 and passed_over and min(kept) >= max(passed_over)


def test_a_candidate_researched_before_is_not_researched_again_for_twelve_months(conn, monkeypatch):
    configure(monkeypatch, research={"shortlist": 1})
    at(monkeypatch, MONDAY_9AM)
    submit(conn, [candidate(1, 90), candidate(2, 80)])
    at(monkeypatch, "2026-10-27T09:00:00+08:00")
    result = submit(conn, [candidate(2, 80), candidate(3, 70)])
    again = next(c for c in result.candidates if c["domain"] == "birchlogistics.sg")
    assert again["status"] == "skipped" and "researched on 2026-10-26, score 80" in again["reasons"][0]
    assert [c["domain"] for c in result.kept] == ["cedarlogistics.sg"]
    at(monkeypatch, "2027-10-28T09:00:00+08:00")
    later = submit(conn, [candidate(2, 80, hiring_evidence=[posting(seen="2027-10-27")])])
    assert [c["domain"] for c in later.kept] == ["birchlogistics.sg"]
    check = CliRunner().invoke(cli, ["scout", "check", "birchlogistics.sg", "--json"])
    assert check.exit_code == 1  # now a lead


def test_kept_leads_record_their_comparison_evidence_and_breakdown(conn, monkeypatch):
    at(monkeypatch, MONDAY_9AM)
    submit(conn, [candidate(1, 82)])
    row = db.one(conn, "SELECT * FROM leads")
    assert row["comparison"] == "Candidate 1: current admin hiring and paper delivery orders"
    assert json.loads(row["hiring_evidence_json"]) == [posting("https://sg.jobstreet.com/job/8001")]
    assert json.loads(row["score_breakdown_json"]) == breakdown(82)


# --- validation: the whole batch or nothing ------------------------------------


def bad(conn, candidates, fragment):
    from jura_growth.agents.scout import leads, shortlist

    with pytest.raises(leads.LeadError, match=fragment):
        shortlist.submit(conn, {"candidates": candidates}, client=client_for(candidates))
    assert db.scalar(conn, "SELECT count(*) FROM leads") == 0
    assert db.scalar(conn, "SELECT count(*) FROM scout_rejections") == 0


@pytest.mark.parametrize(
    "change, fragment",
    [
        ({"score_breakdown": None}, "score_breakdown"),
        ({"score_breakdown": {**breakdown(80), "industry_fit": 25, "paperwork_signals": 0}}, "industry_fit is 25; at most 20"),
        ({"score_breakdown": {**breakdown(80), "size_fit": 5}}, "adds up to 70, not the score 80"),
        ({"score_breakdown": {**breakdown(80), "charm": 0}}, "unknown factor"),
        ({"hiring_evidence": []}, "hiring_signals needs hiring evidence"),
        ({"contact": {"form_url": "https://www.alderlogistics.sg/contact"}}, "enquiry_address needs a published address"),
        ({"comparison": ""}, "comparison"),
        ({"comparison": "x" * 281}, "one line of at most 280"),
        ({"hiring_evidence": [posting(seen="2026-11-30")]}, "in the future"),
        ({"hiring_evidence": [posting(seen="last week")]}, "YYYY-MM-DD"),
        ({"hiring_evidence": [posting(url="mycareersfuture job 12")]}, "http"),
        ({"hiring_evidence": [posting(title="")]}, "title"),
        ({"hiring_evidence": [posting(seen="2026-02-30")]}, "YYYY-MM-DD"),
        # Code review P4: hiring points need evidence from a job board or the company's own site.
        ({"hiring_evidence": [posting(url="https://example.com/anything")]}, "a known job board or the company's own site"),
        ({"hiring_evidence": [posting(url="https://www.recruitexpress.com.sg/jobs/1")]}, "a known job board or the company's own site"),
        ({"hiring_evidence": [posting(url="https://sg.jobstreet.com/job/1\n**fake line**")]}, "http"),
    ],
    ids=lambda v: v if isinstance(v, str) else None,
)
def test_a_malformed_candidate_refuses_the_whole_batch(conn, monkeypatch, change, fragment):
    at(monkeypatch, MONDAY_9AM)
    bad(conn, [candidate(2, 70), candidate(1, 80, **change)], fragment)


def test_every_bad_candidate_is_listed_at_once(conn, monkeypatch):
    """Code review N2: the prompt says fix every reason, so the refusal lists them all."""
    from jura_growth.agents.scout import leads, shortlist

    at(monkeypatch, MONDAY_9AM)
    batch = [candidate(1, 80, score_breakdown=None), candidate(2, 70), candidate(3, 75, comparison=None)]
    with pytest.raises(leads.LeadError) as refused:
        shortlist.submit(conn, {"candidates": batch}, client=client_for(batch))
    assert "candidate 1 (Alder Logistics Pte Ltd)" in str(refused.value)
    assert "candidate 3 (Cedar Logistics Pte Ltd)" in str(refused.value)
    assert "candidate 2" not in str(refused.value)


def test_a_posting_on_the_company_own_careers_page_is_good_evidence(conn, monkeypatch):
    at(monkeypatch, MONDAY_9AM)
    own = posting("https://www.alderlogistics.sg/careers/admin-assistant")
    assert len(submit(conn, [candidate(1, 80, hiring_evidence=[own])]).kept) == 1


# --- code review P2: no person's name or phone number from a posting is kept ----


def test_names_and_phone_numbers_are_stripped_from_postings_and_comparisons(conn, monkeypatch):
    at(monkeypatch, MONDAY_9AM)
    evidence = [{
        "url": "https://sg.jobstreet.com/job/1", "title": "Admin assistant (replacing Ms Tan Mei Ling)",
        "seen": "2026-10-20",
        "duties": ["contact Mr Lim Wei Jie at 9123 4567 to apply", "send your CV to jane.tan@alderlogistics.sg"],
    }]
    result = submit(conn, [candidate(1, 80, hiring_evidence=evidence,
                                     comparison="Ms Tan Mei Ling resigned; Mdm Siti at +65 9123 4567 is hiring")])
    assert len(result.kept) == 1
    assert any("removed" in note for note in result.kept[0]["notes"])
    row = db.one(conn, "SELECT hiring_evidence_json, comparison FROM leads")
    stored = row["hiring_evidence_json"] + row["comparison"]
    posted = json.dumps(outbox("scout-leads"))
    for personal in ("Tan Mei Ling", "Lim Wei Jie", "Siti", "9123", "jane.tan"):
        assert personal not in stored and personal not in posted, personal
    assert json.loads(row["hiring_evidence_json"])[0]["title"] == "Admin assistant (replacing [name removed])"
    assert json.loads(row["hiring_evidence_json"])[0]["duties"][0] == "contact [name removed] at [phone removed] to apply"


# --- code review S2: a batch cut off part-way changes nothing -------------------


class Killed(BaseException):
    """What a kill looks like from inside: not an httpx error, so nothing catches it."""


def dies_after(candidates, pages_served: int):
    mapping = {c["contact"]["source_url"]: contact_page(c["contact"]["email"]) for c in candidates}
    served = []

    def handler(request):
        if len(served) >= pages_served:
            raise Killed()
        served.append(str(request.url))
        return httpx.Response(200, text=mapping[str(request.url)], headers={"content-type": "text/html"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_a_batch_killed_part_way_records_nothing_and_leaves_the_day_open(conn, monkeypatch):
    at(monkeypatch, MONDAY_9AM)
    candidates = [candidate(n, s) for n, s in enumerate(SCORES, start=1)]
    with pytest.raises(Killed):
        submit(conn, candidates, client=dies_after(candidates, 3))
    for table in ("leads", "contacts", "scout_rejections", "scout_rankings"):
        assert db.scalar(conn, f"SELECT count(*) FROM {table}") == 0, table
    assert outbox("scout-leads") == []
    assert scout.precheck("scout-research", conn) is None
    assert len(submit(conn, candidates).kept) == 10  # the re-run ranks the day in full


def test_a_failure_while_writing_rolls_the_whole_batch_back(conn, monkeypatch):
    from jura_growth.agents.scout import leads

    at(monkeypatch, MONDAY_9AM)
    real = leads.remember_rejection
    calls = []

    def fail_on_third(*args, **kwargs):
        calls.append(1)
        if len(calls) == 3:
            raise Killed()
        return real(*args, **kwargs)

    monkeypatch.setattr(leads, "remember_rejection", fail_on_third)
    with pytest.raises(Killed):
        submit(conn, [candidate(n, s) for n, s in enumerate(SCORES, start=1)])
    for table in ("leads", "contacts", "scout_rejections", "scout_rankings"):
        assert db.scalar(conn, f"SELECT count(*) FROM {table}") == 0, table
    assert outbox("scout-leads") == []


# --- code review N1 and N3 -------------------------------------------------------


def test_check_reports_a_rejection_only_within_twelve_months(conn, monkeypatch):
    from jura_growth.agents.scout import leads

    at(monkeypatch, "2025-01-06T09:00:00+08:00")
    leads.remember_rejection(conn, domain="oldco.sg", company="Old Co", reason="x", score=50)
    at(monkeypatch, MONDAY_9AM)
    assert leads.check(conn, "oldco.sg")["looked_at_before"] is None
    leads.remember_rejection(conn, domain="newco.sg", company="New Co", reason="y", score=55)
    assert leads.check(conn, "newco.sg")["looked_at_before"]["score"] == 55


def test_leads_json_carries_the_evidence_comparison_and_breakdown(isolated, monkeypatch, conn):
    at(monkeypatch, MONDAY_9AM)
    submit(conn, [candidate(1, 82)])
    rows = json.loads(CliRunner().invoke(cli, ["scout", "leads", "--json"]).output)
    assert rows[0]["comparison"] == "Candidate 1: current admin hiring and paper delivery orders"
    assert rows[0]["hiring_evidence"] == [posting("https://sg.jobstreet.com/job/8001")]
    assert rows[0]["score_breakdown"] == breakdown(82)


def test_a_below_threshold_candidate_needs_no_comparison(conn, monkeypatch):
    at(monkeypatch, MONDAY_9AM)
    result = submit(conn, [candidate(1, 50, comparison=None)])
    assert result.kept == [] and db.scalar(conn, "SELECT score FROM scout_rejections") == 50


def test_more_candidates_than_the_setting_refuse_the_batch(conn, monkeypatch):
    configure(monkeypatch, research={"candidates": 3})
    at(monkeypatch, MONDAY_9AM)
    bad(conn, [candidate(n, 70) for n in range(1, 5)], "at most 3 candidates")


def test_the_same_company_twice_refuses_the_batch(conn, monkeypatch):
    at(monkeypatch, MONDAY_9AM)
    bad(conn, [candidate(1, 70), candidate(1, 75)], "twice")


# --- the command and the research run's permissions ------------------------------


def test_shortlist_command(isolated, monkeypatch):
    from jura_growth.agents.scout import contact as contact_mod

    at(monkeypatch, MONDAY_9AM)
    candidates = [candidate(n, s) for n, s in enumerate([80, 50, 70, 65], start=1)]
    monkeypatch.setattr(contact_mod, "http_client", lambda: client_for(candidates))
    path = isolated / "candidates.json"
    path.write_text(json.dumps({"candidates": candidates[:3]}))
    result = CliRunner().invoke(cli, ["scout", "shortlist", "--file", str(path), "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert [c["score"] for c in data["kept"]] == [80, 70] and data["shortlist"] == 10
    assert [c["status"] for c in data["candidates"]] == ["kept", "kept", "not_kept"]
    again = CliRunner().invoke(cli, ["scout", "shortlist", "--file", str(path)])
    assert again.exit_code == 2 and "ranked at 09:00 (2 kept of 3)" in again.output
    at(monkeypatch, "2026-10-27T09:00:00+08:00")
    path.write_text(json.dumps({"candidates": candidates[1:]}))
    text = CliRunner().invoke(cli, ["scout", "shortlist", "--file", str(path)])
    assert text.exit_code == 0, text.output
    assert "kept 1 of 3" in text.output and "researched on 2026-10-26, score 50" in text.output


def test_the_research_run_submits_ranked_batches_only():
    from jura_growth import headless

    commands = headless.permissions("scout-research").commands
    assert "scout shortlist" in commands and "scout check-contact" in commands
    assert "scout add-lead" not in commands  # one lead at a time can't be ranked against the day


def research_rules():
    from jura_growth import config, runner

    argv, _ = runner.claude_command("scout-research", config.settings()["jobs"]["scout-research"])
    start, middle = argv.index("--allowedTools"), argv.index("--disallowedTools")
    end = next((i for i in range(middle + 1, len(argv)) if argv[i].startswith("--")), len(argv))
    return argv[start + 1:middle], argv[middle + 1:end]


def test_the_research_run_can_reach_job_boards():
    """§5.2a point 7: WebSearch and WebFetch are allowed with no domain scope, and
    nothing denies a job board."""
    allowed, denied = research_rules()
    assert "WebSearch" in allowed and "WebFetch" in allowed
    assert not [rule for rule in denied if rule.startswith(("WebFetch", "WebSearch"))]
    assert "Bash(jura-growth scout add-lead:*)" in denied


def test_the_prompt_sends_the_research_to_job_boards():
    from jura_growth import paths

    prompt = (paths.prompts_dir() / "scout.md").read_text(encoding="utf-8")
    for board in ("MyCareersFuture", "JobStreet", "Indeed", "LinkedIn Jobs", "Glassdoor"):
        assert board in prompt
    for field in ("hiring_evidence", "score_breakdown", "comparison", "scout shortlist", "scout check-contact"):
        assert field in prompt
    for key, weight in WEIGHTS.items():
        assert f"`{key}` | {weight} |" in prompt


# --- checking a contact before the batch, with no side effects --------------------


def check_contact(monkeypatch, html, *args):
    from jura_growth.agents.scout import contact as contact_mod

    monkeypatch.setattr(contact_mod, "http_client", lambda: pages({"https://www.alderlogistics.sg/contact": html}))
    return CliRunner().invoke(cli, ["scout", "check-contact", "--website", "https://www.alderlogistics.sg", *args])


def test_check_contact_confirms_a_published_address(isolated, monkeypatch, conn):
    result = check_contact(monkeypatch, contact_page("info@alderlogistics.sg"),
                           "--email", "info@alderlogistics.sg", "--source", "https://www.alderlogistics.sg/contact", "--json")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"ok": True, "email": "info@alderlogistics.sg", "kind": "role",
                                         "source_url": "https://www.alderlogistics.sg/contact", "reason": None, "notes": []}
    assert db.scalar(conn, "SELECT count(*) FROM leads") == 0
    assert db.scalar(conn, "SELECT count(*) FROM scout_rejections") == 0


def test_check_contact_lists_what_the_page_does_publish(isolated, monkeypatch):
    result = check_contact(monkeypatch, "<p>Write to sales@alderlogistics.sg</p>",
                           "--email", "info@alderlogistics.sg", "--source", "https://www.alderlogistics.sg/contact")
    assert result.exit_code == 1 and "unverified" in result.output and "sales@alderlogistics.sg" in result.output


def test_check_contact_refuses_a_job_board_source(isolated, monkeypatch):
    result = check_contact(monkeypatch, contact_page("info@alderlogistics.sg"),
                           "--email", "info@alderlogistics.sg", "--source", "https://sg.jobstreet.com/job/1")
    assert result.exit_code == 1 and "evidence only, never a contact source" in result.output


# --- §5.2a point 5: #scout-leads and the digest show why a lead was kept ----------

OLDER = posting("https://www.mycareersfuture.gov.sg/job/admin-1", seen="2026-09-14", title="Admin executive",
                duties=("key in orders", "prepare invoices", "file delivery orders"))
NEWER = posting("https://sg.jobstreet.com/job/2002", seen="2026-10-24", title="Data entry clerk",
                duties=("key in delivery orders",))


def test_the_lead_post_shows_the_comparison_and_the_strongest_hiring_evidence(conn, monkeypatch):
    at(monkeypatch, MONDAY_9AM)
    submit(conn, [candidate(1, 84, hiring_evidence=[OLDER, NEWER], comparison="Hiring for order entry twice since September")])
    post = outbox("scout-leads")[-1]["content"]
    assert "Why kept: Hiring for order entry twice since September" in post
    assert ("Hiring: Data entry clerk, seen 2026-10-24: key in delivery orders "
            "(https://sg.jobstreet.com/job/2002), and 1 more posting") in post
    assert "Admin executive" not in post


def test_strongest_is_the_latest_posting_then_the_one_naming_most_duties():
    from jura_growth.agents.scout import scoring

    assert scoring.strongest([OLDER, NEWER]) == NEWER
    same_day = posting(seen="2026-10-24", title="Admin", duties=("a", "b", "c"))
    assert scoring.strongest([NEWER, same_day]) == same_day
    assert scoring.strongest([]) is None


def test_a_lead_added_without_evidence_posts_as_before(conn):
    add(conn, lead_data(1))
    post = outbox("scout-leads")[-1]["content"]
    assert "Hiring:" not in post and "Why kept:" not in post


def test_the_digest_shows_the_ranking_and_each_kept_lead(conn, monkeypatch):
    from jura_growth import timeutil

    at(monkeypatch, MONDAY_9AM)
    candidates = [candidate(n, s) for n, s in enumerate(SCORES, start=1)]
    candidates[10]["hiring_evidence"] = [OLDER, NEWER]  # the 95
    submit(conn, candidates)
    part = scout.digest(conn, timeutil.today_str())
    assert "Scout ranked 20 candidates and kept 10 (shortlist 10)" in part["lines"]
    first = next(line for line in part["lines"] if line.startswith("Kept: "))
    assert first.startswith("Kept: Kestrel Logistics Pte Ltd (score 95): Candidate 11: current admin hiring")
    assert "hiring: Data entry clerk, seen 2026-10-24" in first and "https://sg.jobstreet.com/job/2002" in first
    assert sum(1 for line in part["lines"] if line.startswith("Kept: ")) == 10
    assert part["figures"]["leads_added"] == 10


# --- §5.2a point 4: keeping more leads never means sending more ----------------


def keep_ten_and_queue(conn, monkeypatch, day="2026-10-26"):
    from jura_growth.agents.outreach import queue as queue_mod
    from jura_growth.agents.scout import leads

    from test_scout_support import body_for

    at(monkeypatch, f"{day}T08:00:00+08:00")
    result = submit(conn, [candidate(n, s) for n, s in enumerate(SCORES, start=1)])
    assert len(result.kept) == 10
    for entry in result.kept:
        name = leads.display_name(entry["company"])
        queued = queue_mod.queue(conn, entry["lead_id"], {
            "subject": f"A free delivery order maker for {name}", "body": body_for(name), "tool": "delivery-order-maker",
        })
        assert queued.status == "queued", queued.reasons
    return result


def test_ten_kept_leads_still_send_no_more_than_the_first_live_day_warm_up_cap(conn, monkeypatch):
    from test_outreach_send import run_slots
    from test_scout_support import approve_due, fake_resend, live_ready

    from jura_growth.agents.outreach import send

    live_ready(monkeypatch)
    keep_ten_and_queue(conn, monkeypatch)
    sent = fake_resend(monkeypatch)
    approve_due(conn, monkeypatch)  # requests only up to today's quota
    assert send.daily_cap(conn, "live")[0] == 5
    sends = run_slots(conn, monkeypatch)
    assert len(sends) == 5 and len(sent) == 5
    assert db.scalar(conn, "SELECT count(*) FROM outreach_messages WHERE status = 'queued'") == 5
    assert send.quota(conn, "live")[0] == 0


def test_ten_kept_leads_in_shadow_mode_stay_within_the_warm_up_too(conn, monkeypatch):
    from test_outreach_send import run_slots

    keep_ten_and_queue(conn, monkeypatch)
    assert len(run_slots(conn, monkeypatch)) == 5


def test_a_full_queue_still_holds_research_whatever_the_shortlist(conn, monkeypatch):
    configure(monkeypatch, research={"max_queue": 10})
    keep_ten_and_queue(conn, monkeypatch)
    at(monkeypatch, "2026-10-27T09:00:00+08:00")
    assert "10 emails are already queued (max_queue 10)" in scout.precheck("scout-research", conn)
