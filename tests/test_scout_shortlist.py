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


@pytest.mark.parametrize("website", ["https://sg.jobstreet.com", "https://www.recruitexpress.com.sg", "https://www.glassdoor.sg", "https://www.indeed.com.sg"])
def test_a_job_board_or_recruiter_is_never_a_lead_website(conn, website):
    domain = contact.site_domain(website)
    data = lead_data(1, website=website, source_urls=[f"{website}/about"],
                     contact={"email": f"info@{domain}", "source_url": f"{website}/contact"})
    outcome = add(conn, data)
    assert outcome.status == "rejected" and "not the company's own website" in outcome.reasons[0]


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
    later = submit(conn, [candidate(2, 80)])
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
        ({"hiring_evidence": [posting(duties=("send your CV to jane.tan@alderlogistics.sg",))]}, "email address"),
    ],
    ids=lambda v: v if isinstance(v, str) else None,
)
def test_a_malformed_candidate_refuses_the_whole_batch(conn, monkeypatch, change, fragment):
    at(monkeypatch, MONDAY_9AM)
    bad(conn, [candidate(2, 70), candidate(1, 80, **change)], fragment)


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
