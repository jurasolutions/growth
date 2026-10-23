"""Block 1: research records, the contact rules in code, dedupe, the ICP."""

import json
from datetime import date

from click.testing import CliRunner

from jura_growth import db, paths, runner, suppression
from jura_growth.agents import scout
from jura_growth.agents.scout import icp, leads
from jura_growth.cli import cli

from test_scout_support import add, at, configure, contact_page, lead_data, outbox, pages, scout_env, seed  # noqa: F401


def test_lead_is_added_with_its_verified_address(conn):
    outcome = add(conn, lead_data(1))
    assert outcome.status == "added", outcome.reasons
    lead = db.one(conn, "SELECT * FROM leads WHERE id = ?", (outcome.lead_id,))
    assert lead["domain"] == "alderlogistics.sg" and lead["channel"] == "email" and lead["status"] == "new"
    assert lead["display_name"] == "Alder Logistics"
    assert json.loads(lead["score_reasons"])[0] == "Logistics is in the ICP"
    row = db.one(conn, "SELECT * FROM contacts WHERE lead_id = ?", (outcome.lead_id,))
    assert row["email"] == "info@alderlogistics.sg" and row["kind"] == "role" and row["mx_ok"] == 1
    assert row["source_url"] == "https://www.alderlogistics.sg/contact"
    assert row["email_hash"] == suppression.email_hash("info@alderlogistics.sg")
    posted = outbox("scout-leads")
    assert posted and "Alder Logistics" in posted[-1]["content"] and "score 72" in posted[-1]["content"]
    assert "delivery-order-maker" in posted[-1]["content"]


def test_five_leads_then_a_rerun_adds_no_duplicates(conn):
    for n in range(1, 6):
        assert add(conn, lead_data(n)).status == "added"
    again = [add(conn, lead_data(n)) for n in range(1, 6)]
    assert all(o.status == "rejected" and "already a lead" in o.reasons[0] for o in again)
    assert db.scalar(conn, "SELECT count(*) FROM leads") == 5
    assert db.scalar(conn, "SELECT count(*) FROM contacts") == 5


def test_unverified_address_is_rejected_and_hints_at_real_ones(conn):
    outcome = add(conn, lead_data(1), page_html="<p>Write to sales@alderlogistics.sg</p>")
    assert outcome.status == "rejected"
    assert "unverified" in outcome.reasons[0] and "sales@alderlogistics.sg" in outcome.reasons[0]
    assert db.scalar(conn, "SELECT count(*) FROM leads") == 0


def test_cloudflare_protected_address_verifies(conn):
    key = 0x33
    encoded = f"{key:02x}" + "".join(f"{ord(c) ^ key:02x}" for c in "info@alderlogistics.sg")
    page = f'<a href="/cdn-cgi/l/email-protection#{encoded}"><span class="__cf_email__" data-cfemail="{encoded}">[email protected]</span></a>'
    assert add(conn, lead_data(1), page_html=page).status == "added"


def test_source_page_must_be_on_the_company_site(conn):
    data = lead_data(1, contact={"email": "info@alderlogistics.sg", "source_url": "https://www.sgpbusiness.com/alder"})
    outcome = add(conn, data)
    assert outcome.status == "rejected" and "not on the company's own website" in outcome.reasons[0]


def test_website_must_be_the_company_own_site(conn):
    outcome = add(conn, lead_data(1, website="https://www.facebook.com/alderlogistics", domain="facebook.com"))
    assert outcome.status == "rejected" and "not the company's own website" in outcome.reasons[0]


def test_government_domains_are_excluded(conn):
    outcome = add(conn, lead_data(1, domain="lta.gov.sg"))
    assert outcome.status == "rejected" and "government" in outcome.reasons[0]


def test_score_below_threshold_is_not_kept(conn, monkeypatch):
    assert add(conn, lead_data(1, score=59)).status == "rejected"
    configure(monkeypatch, research={"score_threshold": 40})  # config can't lower the floor
    outcome = add(conn, lead_data(2, score=55))
    assert outcome.status == "rejected" and "below 60" in outcome.reasons[0]
    assert add(conn, lead_data(3, score=60)).status == "added"


def test_suppressed_address_and_domain_are_rejected(conn):
    suppression.add(conn, email_hash_value=suppression.email_hash("info@alderlogistics.sg"), reason="unsubscribe", source="d1:unsubscribe-link")
    outcome = add(conn, lead_data(1))
    assert outcome.status == "rejected" and "suppressed" in outcome.reasons[0]
    suppression.add(conn, domain="birchlogistics.sg", reason="manual", source="test")
    outcome = add(conn, lead_data(2))
    assert outcome.status == "rejected" and "birchlogistics.sg is suppressed" in outcome.reasons[0]


def test_do_not_contact_by_name_and_domain(conn):
    (paths.inputs_dir() / "do-not-contact.csv").write_text(
        "company,domain,reason\nZOLL Medical Singapore,,\nFujifilm,,\n,birchlogistics.sg,existing contact\n"
    )
    zoll = lead_data(1, company="ZOLL Medical Singapore Pte Ltd", domain="zoll.com.sg")
    assert "do-not-contact" in add(conn, zoll).reasons[0]
    fuji = lead_data(2, company="FUJIFILM Business Innovation Singapore Pte. Ltd.", domain="fujifilm-bi.sg")
    assert "do-not-contact" in add(conn, fuji).reasons[0]
    by_domain = add(conn, lead_data(2))
    assert by_domain.status == "rejected" and "existing contact" in by_domain.reasons[0]
    assert add(conn, lead_data(3)).status == "added"


def test_do_not_contact_file_is_only_read(conn):
    path = paths.inputs_dir() / "do-not-contact.csv"
    path.write_text("company,domain\nAcme,\n")
    before = path.read_text()
    add(conn, lead_data(1))
    assert path.read_text() == before


def test_contacted_domains_are_rejected(conn):
    conn.execute("INSERT INTO contacted_domains (domain, first_contacted_at) VALUES ('alderlogistics.sg', '2025-01-01T10:00:00+08:00')")
    outcome = add(conn, lead_data(1))
    assert outcome.status == "rejected" and "contacted before" in outcome.reasons[0]


def test_contact_form_only_gives_channel_form(conn):
    data = lead_data(1, contact={"form_url": "https://www.alderlogistics.sg/contact"})
    outcome = add(conn, data)
    assert outcome.status == "added" and outcome.channel == "form"
    lead = db.one(conn, "SELECT channel, status, form_url FROM leads")
    assert lead == {"channel": "form", "status": "form_only", "form_url": "https://www.alderlogistics.sg/contact"}
    assert db.scalar(conn, "SELECT count(*) FROM contacts") == 0
    off_site = lead_data(2, contact={"form_url": "https://forms.gle/abc"})
    assert add(conn, off_site).status == "rejected"


def test_role_address_on_the_page_is_preferred_over_a_named_one(conn):
    data = lead_data(1, contact={"email": "jane@alderlogistics.sg", "source_url": "https://www.alderlogistics.sg/contact"})
    outcome = add(conn, data, page_html="<p>Jane: jane@alderlogistics.sg. General: info@alderlogistics.sg</p>")
    assert outcome.status == "added" and outcome.contact["email"] == "info@alderlogistics.sg"
    assert any("role address" in note for note in outcome.notes)


def test_named_address_needs_to_be_the_published_enquiry_contact(conn):
    data = lead_data(1, contact={"email": "jane@alderlogistics.sg", "source_url": "https://www.alderlogistics.sg/contact"})
    outcome = add(conn, data, page_html="<p>Enquiries: jane@alderlogistics.sg</p>")
    assert outcome.status == "rejected" and "named address" in outcome.reasons[0]
    data["contact"]["enquiry_contact"] = True
    outcome = add(conn, data, page_html="<p>Enquiries: jane@alderlogistics.sg</p>")
    assert outcome.status == "added" and outcome.contact["kind"] == "named"


def test_no_mx_record_rejects(conn, monkeypatch):
    import dns.resolver

    from jura_growth.agents.scout import contact

    def no_answer(domain):
        raise dns.resolver.NoAnswer()

    monkeypatch.setattr(contact, "resolve_mx", no_answer)
    outcome = add(conn, lead_data(1))
    assert outcome.status == "rejected" and "no MX record" in outcome.reasons[0]


def test_careers_address_is_refused(conn):
    data = lead_data(1, contact={"email": "careers@alderlogistics.sg", "source_url": "https://www.alderlogistics.sg/contact"})
    assert "not an enquiry address" in add(conn, data).reasons[0]


def test_daily_target_is_a_ceiling(conn, monkeypatch):
    configure(monkeypatch, research={"daily_target": 2})
    assert add(conn, lead_data(1)).status == "added"
    assert add(conn, lead_data(2)).status == "added"
    outcome = add(conn, lead_data(3))
    assert outcome.status == "rejected" and "target of 2" in outcome.reasons[0]


def test_bad_records_are_usage_errors(conn):
    import pytest

    with pytest.raises(leads.LeadError):
        leads.add_lead(conn, {"company": "X"})
    with pytest.raises(leads.LeadError):
        leads.add_lead(conn, lead_data(1, score=140))


def test_display_name_drops_legal_suffixes():
    assert leads.display_name("Acme Aircon Services Pte. Ltd.") == "Acme Aircon Services"
    assert leads.display_name("Kim Seng Hardware (S) Pte Ltd") == "Kim Seng Hardware"
    assert leads.display_name("Tan & Co LLP") == "Tan & Co"


# --- ICP, rotation, precheck -----------------------------------------------


def test_research_refuses_to_start_without_the_icp(isolated, monkeypatch):
    (paths.inputs_dir() / "icp.md").unlink()
    at(monkeypatch, "2026-10-26T09:00:00+08:00")
    outcome = runner.run("scout-research")
    assert outcome.status == "skipped"
    assert "icp.md is missing" in outcome.summary and "icp-draft.md" in outcome.summary


def test_precheck_skips_when_target_met_or_queue_full(conn, monkeypatch):
    configure(monkeypatch, research={"daily_target": 1, "max_queue": 1})
    assert scout.precheck("scout-research", conn) is None
    seed(conn, 1)
    assert "target of 1" in scout.precheck("scout-research", conn)
    configure(monkeypatch, research={"daily_target": 5, "max_queue": 1})
    assert "already queued" in scout.precheck("scout-research", conn)
    assert scout.precheck("scout-send", conn) is None


def test_industries_come_from_the_icp_and_rotate(monkeypatch):
    assert icp.industries() == ["logistics and delivery", "events", "property agencies"]
    monday = icp.todays_industries(date(2026, 10, 26))
    tuesday = icp.todays_industries(date(2026, 10, 27))
    assert len(monday) == 2 and monday != tuesday
    seen = set()
    for day in range(26, 31):
        seen |= set(icp.todays_industries(date(2026, 10, day)))
    assert seen == set(icp.industries())


def test_industries_fall_back_to_config_without_a_section():
    (paths.inputs_dir() / "icp.md").write_text("# ICP\n\nSingapore SMEs.\n")
    assert "events" in icp.industries() and len(icp.industries()) == 10


def test_icp_parsing_takes_the_name_before_a_dash():
    text = "## Industries with paperwork\n\n- Field service and maintenance — aircon, lifts\n- Events: planners\n\n## Signals\n- PDFs\n"
    assert icp.industries_from_icp(text) == ["Field service and maintenance", "Events"]


# --- commands --------------------------------------------------------------


def test_insights_json_shape(conn):
    add(conn, lead_data(1))
    add(conn, lead_data(2, industry="events", observations=["Bookings by phone only", "Crew timesheets on paper"]))
    result = CliRunner().invoke(cli, ["scout", "insights", "--days", "30", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert set(data) == {"industries", "observations"}
    assert data["industries"] == {"events": 1, "logistics and delivery": 1}
    assert "Bookings by phone only" in data["observations"]


def test_add_lead_and_check_commands(isolated, monkeypatch):
    from jura_growth.agents.scout import contact

    monkeypatch.setattr(contact, "http_client", lambda: pages({"https://www.alderlogistics.sg/contact": contact_page("info@alderlogistics.sg")}))
    path = isolated / "lead.json"
    path.write_text(json.dumps(lead_data(1)))
    first = CliRunner().invoke(cli, ["scout", "add-lead", "--file", str(path)])
    assert first.exit_code == 0 and "added lead 1" in first.output
    again = CliRunner().invoke(cli, ["scout", "add-lead", "--file", str(path)])
    assert again.exit_code == 1 and "already a lead" in again.output
    known = CliRunner().invoke(cli, ["scout", "check", "https://alderlogistics.sg"])
    assert known.exit_code == 1 and "already a lead" in known.output
    assert CliRunner().invoke(cli, ["scout", "check", "birchlogistics.sg"]).exit_code == 0


def test_today_and_tools_commands(isolated, monkeypatch):
    at(monkeypatch, "2026-10-26T09:00:00+08:00")
    result = CliRunner().invoke(cli, ["scout", "today", "--json"])
    info = json.loads(result.output)
    assert info["daily_target"] == 15 and info["score_threshold"] == 60 and len(info["industries"]) == 2
    assert "quote-builder" in info["tools"] and "receipt-sorter" not in info["tools"]
    tools = json.loads(CliRunner().invoke(cli, ["scout", "tools", "--json"]).output)
    assert [t["slug"] for t in tools["tools"]][:2] == ["quote-builder", "invoice-checker"]


def test_missing_registry_is_reported(isolated):
    (paths.site_repo() / "src" / "apps" / "registry.json").unlink()
    tools = json.loads(CliRunner().invoke(cli, ["scout", "tools", "--json"]).output)
    assert tools["tools"] == [] and "missing" in tools["problem"]


def test_scout_digest_lists_form_only_leads(conn):
    from jura_growth import timeutil

    add(conn, lead_data(1))
    add(conn, lead_data(2, contact={"form_url": "https://www.birchlogistics.sg/contact"}))
    part = scout.digest(conn, timeutil.today_str())
    assert part["figures"] == {"leads_added": 2, "leads_form_only": 1}
    assert any("Birch Logistics" in line and "birchlogistics.sg/contact" in line for line in part["lines"])


def test_events_never_carry_a_full_address(conn):
    add(conn, lead_data(1), page_html="<p>Write to sales@alderlogistics.sg</p>")
    payloads = " ".join(r["payload_json"] for r in db.rows(conn, "SELECT payload_json FROM events"))
    assert "sales@alderlogistics.sg" not in payloads and "info@alderlogistics.sg" not in payloads
    assert "…@alderlogistics.sg" in payloads


def test_the_same_address_is_never_recorded_twice(conn):
    shared = {"email": "orders@gmail.com", "source_url": "https://www.alderlogistics.sg/contact"}
    assert add(conn, lead_data(1, contact=shared)).status == "added"
    other = {"email": "orders@gmail.com", "source_url": "https://www.birchlogistics.sg/contact"}
    outcome = add(conn, lead_data(2, contact=other))
    assert outcome.status == "rejected" and "already recorded for lead 1" in outcome.reasons[0]


def test_named_addresses_stay_out_of_discord(conn):
    data = lead_data(1, contact={"email": "jane@alderlogistics.sg", "source_url": "https://www.alderlogistics.sg/contact", "enquiry_contact": True})
    assert add(conn, data, page_html="<p>Enquiries: jane@alderlogistics.sg</p>").status == "added"
    post = outbox("scout-leads")[-1]["content"]
    assert "jane@" not in post and "named enquiry address" in post


def test_check_command_on_the_email_channel():
    result = CliRunner().invoke(cli, ["check", "--channel", "email", "--subject", "Re: hello", "Hi there, we have tools."])
    assert result.exit_code == 1 and "Missing the signature" in result.output and "Re:" in result.output
