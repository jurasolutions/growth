"""Ting Yu's own toolbox ideas: `apps idea <text>` from Discord, and the factory picking them first.

`apps idea` adds a backlog row (`source: ting-yu`) and nothing else: the PRD and both build
gates still apply. The factory reads the queue from `apps context --json` (`ting_yu_ideas`),
oldest first; an idea that fails a check is held with `apps hold-idea`, which records the reason
in the row's notes and in the digest, and `apps submit-prd --idea <slug>` marks the row even when
the PRD's name had to change.

The world is `test_app.py`'s (`prd_tree`: APP-001 Quote builder and APP-002 Receipt reader
pending, an empty registry, the clock at Monday 26 October 06:30), with Ting Yu as the control
user. Remote calls go through click's `CliRunner` with the SSH origin passed in process, as in
`test_remote.py`.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import yaml

import pytest
from click.testing import CliRunner

import approval_world as aw
from test_apps import GOOD, TODAY, invoke, prd_tree, write  # noqa: F401 - prd_tree is the autouse world
from jura_growth import config, db, headless, paths, remote as remote_mod
from jura_growth.agents import apps as apps_plugin
from jura_growth.agents.apps import backlog, ideas
from jura_growth.cli import cli
from jura_growth.origin import Origin

PICKS = "the app factory picks it at its next run (06:30 SGT)"


@pytest.fixture(autouse=True)
def control(monkeypatch):
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", aw.CONTROL_ID)
    config.reset_caches()


def remote(words, *, as_json=True):
    argv = ["remote", "--actor", aw.CONTROL, "--ref", "m1:d1", *(["--json"] if as_json else []), "--", *words]
    return CliRunner().invoke(cli, argv, obj={"origin": Origin.ssh()})


def answer(result) -> dict:
    return json.loads(result.output)


def idea_words(text: str) -> list[str]:
    """What Dispatch sends: the text split on whitespace, after `apps idea`."""
    return ["apps", "idea", *text.split()]


def row(slug: str) -> dict:
    return next(r for r in backlog.load() if r.get("slug") == slug)


# --- the remote command -------------------------------------------------------------------------


def test_an_idea_from_discord_becomes_a_backlog_row_and_the_answer_shows_it(conn):
    text = "Site visit report: write up a site visit with photos and a signature, and save it as a PDF"
    result = remote(idea_words(text))
    body = answer(result)
    assert result.exit_code == 0 == body["exit_code"] and body["answer"] == "recorded", body
    added = row("site-visit-report")
    assert added == {
        "name": "Site visit report",
        "slug": "site-visit-report",
        "does": text,
        "status": "idea",
        "source": "ting-yu",
        "added": TODAY,
        "actor": aw.CONTROL,
        "notes": f"Sent by Ting Yu with `apps idea` on {TODAY}.",
    }
    for shown in ("Site visit report", "site-visit-report", text, "source: ting-yu", TODAY):
        assert shown in body["text"], shown
    assert PICKS.lower() in body["text"].lower()
    assert len(body["text"]) <= remote_mod.TEXT_LIMIT


def test_the_seed_rows_are_kept_when_the_first_idea_writes_the_backlog_file(conn):
    assert not backlog.path().exists()
    assert remote(idea_words("Timesheet tidier: turn a messy timesheet into clean rows")).exit_code == 0
    rows = backlog.load()
    assert len(rows) == 21 and rows[-1]["slug"] == "timesheet-tidier"
    assert row("quote-builder")["app_id"] == "APP-001"


def test_without_a_colon_the_name_is_the_first_few_words(conn):
    assert remote(idea_words("a tool that turns supplier price lists into one comparison table.")).exit_code == 0
    added = backlog.load()[-1]
    assert added["name"] == "A tool that turns supplier" and added["slug"] == "a-tool-that-turns-supplier"
    assert added["does"] == "a tool that turns supplier price lists into one comparison table."


@pytest.mark.parametrize("text, name", [
    ("Stock count sheet: print a count sheet", "Stock count sheet"),
    ("  : a colon first, so the words name it", "A colon first, so the"),
    ("GST checker for imports: add GST to the landed cost", "GST checker for imports"),
    ("Petty cash log.", "Petty cash log"),
    # Review N4: only a colon and a space name it, so a web address or a time doesn't.
    ("https://www.iras.gov.sg/gst a GST registration checker", "Https://www.iras.gov.sg/gst a GST registration checker"),
    ("Remind staff at 9:30 to submit timesheets", "Remind staff at 9:30 to"),
    ("Shift planner (06:30 starts): plan early shifts", "Shift planner (06:30 starts)"),
    ("Petty cash log:", "Petty cash log"),
])
def test_the_name_comes_from_the_part_before_the_first_colon(text, name):
    assert ideas.name_for(text) == name


@pytest.mark.parametrize("text", [
    "A very long name for a tool that goes on and on well past the sixty character mark: and then the rest",
    "Supercalifragilisticexpialidocious" * 4 + " and more words",
    "https://www.iras.gov.sg/taxes/goods-services-tax-(gst)/basics-of-gst/current-gst-rates a checker",
])
def test_a_derived_name_is_at_most_60_characters_cut_at_a_word(text):
    """Review N7: the cap holds for the first-words fallback too."""
    name = ideas.name_for(text)
    assert 0 < len(name) <= 60 and len(ideas.slug_for(name)) <= 60
    if " " in text[:61]:
        assert text.lower().startswith(name.lower()) and text[len(name)] in " :"


def test_two_ideas_that_start_with_a_web_address_are_not_the_same_idea(conn):
    first = answer(remote(idea_words("https://www.iras.gov.sg/gst a GST registration checker")))
    second = answer(remote(idea_words("https://www.mom.gov.sg/leave a leave calculator")))
    assert first["exit_code"] == 0 == second["exit_code"], (first, second)


def test_an_empty_idea_is_refused_and_nothing_is_written(conn):
    body = answer(remote(["apps", "idea"]))
    assert body["exit_code"] == 2 and body["answer"] == "refused"
    assert body["text"].startswith("refused:") and "apps idea <text>" in body["text"]
    assert not backlog.path().exists()


@pytest.mark.parametrize("words", [["…", "!!"], ["请假", "计划", "工具"], ["Планировщик", "отпусков"]])
def test_an_idea_with_no_latin_letters_is_refused_with_why(conn, words):
    """Review N8: the name becomes the tool's web address, so it needs Latin letters."""
    body = answer(remote(["apps", "idea", *words]))
    assert body["exit_code"] == 2 and body["text"].startswith("refused:")
    assert "Latin letters" in body["text"] and "web address" in body["text"]
    assert not backlog.path().exists()


def test_non_latin_text_after_a_latin_name_is_kept_word_for_word(conn):
    text = "Leave form maker: 请假 表格, a leave form in English and Chinese"
    assert remote(idea_words(text)).exit_code == 0
    assert row("leave-form-maker")["does"] == text


def test_an_idea_over_500_characters_is_refused_and_one_of_500_is_taken(conn):
    long = "Long idea: " + "x" * 490
    assert len(long) == 501
    body = answer(remote(idea_words(long)))
    assert body["exit_code"] == 2 and body["answer"] == "refused"
    assert body["text"].startswith("refused:") and "500" in body["text"]
    assert not backlog.path().exists()
    fits = long[:-1]
    assert answer(remote(idea_words(fits)))["exit_code"] == 0
    assert row("long-idea")["does"] == fits


@pytest.mark.parametrize("text, clash", [
    ("Quote builder: quotes with deposits", "APP-001"),  # pending, by slug and name
    ("Receipt-reader: read receipts", "APP-002"),  # pending, by slug
    ("Invoice builder: invoices with PayNow", "Invoice builder"),  # a backlog idea with no PRD
    ("invoice  BUILDER: the same, typed differently", "Invoice builder"),  # by name, normalised
])
def test_a_near_duplicate_is_refused_with_what_it_clashes_with(conn, text, clash):
    before = backlog.load()
    body = answer(remote(idea_words(text)))
    assert body["exit_code"] == 1 and body["answer"] == "refused" and body["ok"] is False, body
    assert body["text"].startswith("not added:") and clash in body["text"]
    assert backlog.load() == before


def test_a_live_tool_in_the_site_registry_is_a_duplicate(conn):
    registry = paths.site_repo() / "src" / "apps" / "registry.json"
    registry.write_text(json.dumps([{"slug": "site-visit-report", "name": "Site visit report", "status": "live"}]))
    body = answer(remote(idea_words("Site visit report: write up a visit")))
    assert body["exit_code"] == 1 and "live in the site registry" in body["text"]


def test_the_same_idea_sent_twice_is_added_once(conn):
    assert remote(idea_words("Petty cash log: track petty cash")).exit_code == 0
    again = answer(remote(idea_words("Petty cash log: track petty cash")))
    assert again["exit_code"] == 1 and "Petty cash log" in again["text"]
    assert [r["slug"] for r in backlog.load()].count("petty-cash-log") == 1


@pytest.mark.parametrize("words", [
    ["--source", "agent", "Petty", "cash", "log"],
    ["Petty", "cash", "log", "--status", "prd-done"],
    ["Petty", "cash", "log", "--status=live"],
    ["-x", "Petty", "cash", "log"],
])
def test_options_are_refused_and_nothing_is_written(conn, words):
    body = answer(remote(["apps", "idea", *words]))
    assert body["exit_code"] == 2 and body["text"].startswith("refused:") and "takes no options" in body["text"]
    assert not backlog.path().exists()


def test_a_hyphen_or_a_dash_inside_the_text_is_not_an_option(conn):
    text = "Job sheet: a one-page job sheet - signed on site, with a -5% discount line"
    assert remote(idea_words(text)).exit_code == 0
    assert row("job-sheet")["does"] == text


# --- review S2: the text can't inject YAML or mentions --------------------------------------------

HOSTILE = [
    "Anchor tool: &a [1, 2] *a <<: *a",
    "Tag tool: !!python/object/apply:os.system ['echo hi'] !!binary aGk=",
    "Doc tool: --- status: live ... --- second: doc",
    "Key tool: status: live, source: agent, slug: quote-builder",
    "Null tool: ~ null yes no on off 0x1F 1e3 'single' \"double\"",
    "Comment tool: # not a comment | > {flow: map} [flow, list]",
]


@pytest.mark.parametrize("text", HOSTILE)
def test_yaml_in_the_text_stays_text_and_sets_no_field(conn, text):
    result = remote(idea_words(text))
    assert answer(result)["exit_code"] == 0, result.output
    documents = list(yaml.safe_load_all(backlog.path().read_text(encoding="utf-8")))
    assert len(documents) == 1
    [added] = [r for r in documents[0]["apps"] if r.get("source") == "ting-yu"]
    assert added["does"] == text and added["status"] == "idea" and added["source"] == "ting-yu"
    assert set(added) == {"name", "slug", "does", "status", "source", "added", "actor", "notes"}
    assert row("quote-builder")["app_id"] == "APP-001" and len(backlog.load()) == 21


@pytest.mark.parametrize("text", [
    "Multi line tool: first line\nstatus: live\n- name: Forged\n  source: ting-yu",
    "Doc break tool: one\n---\napps: []\n...",
    "Odd space tool: one\u2028two\u0085three\ttab",
])
def test_newlines_from_the_terminal_stay_inside_the_one_row(conn, text):
    """Dispatch splits on whitespace, so only the terminal can send a newline."""
    assert invoke("apps", "idea", text).exit_code == 0
    rows = backlog.load()
    assert len(rows) == 21 and not any(r["name"] == "Forged" for r in rows)
    assert rows[-1]["does"] == text.strip() and rows[-1]["source"] == "ting-yu"


def test_mentions_in_the_text_never_ping_anyone_from_the_reply(conn):
    text = "Ping tool: @everyone and @here and <@123> and <@!456> and <@&789> please"
    body = answer(remote(idea_words(text)))
    assert body["exit_code"] == 0
    for live in ("@everyone", "@here", "<@1", "<@!", "<@&"):
        assert live not in body["text"], live
    assert row("ping-tool")["does"] == text  # the row keeps his words; only the answer is defused
    plain = remote(idea_words("Pong tool: @everyone <@&789>"), as_json=False)
    assert "@everyone" not in plain.output and "<@&" not in plain.output


def test_an_older_idea_of_ting_yus_is_named_as_coming_first(conn):
    assert remote(idea_words("Petty cash log: track petty cash")).exit_code == 0
    body = answer(remote(idea_words("Stock count sheet: print a count sheet")))
    assert body["exit_code"] == 0
    assert PICKS.lower() not in body["text"].lower()
    assert "1 older idea of yours comes first" in body["text"]


def test_the_allowlist_row_and_the_contract_row():
    assert remote_mod.ALLOWLIST["apps idea"].usage == "apps idea <text>"
    assert not remote_mod.ALLOWLIST["apps idea"].decision
    assert remote_mod.match(["apps", "idea", "x"])[0] == "apps idea"
    with pytest.raises(remote_mod.Refusal):
        remote_mod.match(["apps", "hold-idea", "x"])
    text = (paths.REPO_ROOT / "docs" / "dispatch-contract.md").read_text(encoding="utf-8")
    assert "| `apps idea <text>` | `apps idea` |" in text


def test_no_scheduled_run_may_add_an_idea_of_ting_yus():
    assert headless.never("apps idea Petty cash log")
    assert not headless.never("apps hold-idea petty-cash-log --reason x")
    for job in config.settings()["jobs"]:
        assert not headless.may_use(job, "apps idea Petty cash log")


def test_from_the_terminal_the_actor_is_local(conn):
    result = invoke("apps", "idea", "Petty cash log: track petty cash")
    assert result.exit_code == 0, result.output
    assert row("petty-cash-log")["actor"] == "local"


def test_the_event_names_the_row_not_the_text(conn):
    assert remote(idea_words("Petty cash log: track petty cash")).exit_code == 0
    events = db.rows(conn, "SELECT payload_json FROM events WHERE kind = 'apps.idea.added'")
    [payload] = [json.loads(e["payload_json"]) for e in events]
    assert payload == {"slug": "petty-cash-log", "name": "Petty cash log", "actor": aw.CONTROL}


# --- the factory's queue: `ting_yu_ideas`, oldest first ------------------------------------------


def _add(text: str, day: str, monkeypatch) -> None:
    monkeypatch.setenv("JURA_GROWTH_NOW", f"{day}T09:00:00+08:00")
    assert invoke("apps", "idea", text).exit_code == 0


def test_context_lists_ting_yus_ideas_oldest_first_and_only_open_ones(conn, monkeypatch):
    _add("Stock count sheet: print a count sheet", "2026-10-21", monkeypatch)
    _add("Petty cash log: track petty cash", "2026-10-19", monkeypatch)
    _add("Job sheet: a one-page job sheet", "2026-10-20", monkeypatch)
    monkeypatch.setenv("JURA_GROWTH_NOW", f"{TODAY}T06:30:00+08:00")
    view = json.loads(invoke("apps", "context", "--json").output)
    assert [r["slug"] for r in view["ting_yu_ideas"]] == ["petty-cash-log", "job-sheet", "stock-count-sheet"]
    assert invoke("apps", "hold-idea", "petty-cash-log", "--reason", "it reads as legal advice").exit_code == 0
    view = json.loads(invoke("apps", "context", "--json").output)
    assert [r["slug"] for r in view["ting_yu_ideas"]] == ["job-sheet", "stock-count-sheet"]
    assert all(r["source"] == "ting-yu" and r["effective_status"] == "idea" for r in view["ting_yu_ideas"])


def test_an_idea_whose_prd_was_written_leaves_the_queue(conn, tmp_path):
    """The factory renamed "DO maker" to meet its name rules; `--idea` marks Ting Yu's row."""
    backlog.save([r for r in backlog.load() if r["slug"] != "delivery-order-maker"])  # not a seed idea here
    assert invoke("apps", "idea", "DO maker: delivery orders with a signature box").exit_code == 0
    result = invoke("apps", "submit-prd", "--idea", "do-maker", str(write(tmp_path, GOOD)))
    assert result.exit_code == 0, result.output
    marked = row("delivery-order-maker")
    assert marked["status"] == "prd-pending" and marked["app_id"] == "APP-003"
    assert marked["source"] == "ting-yu" and marked["does"] == "DO maker: delivery orders with a signature box"
    assert not [r for r in backlog.load() if r.get("slug") == "do-maker"]
    view = json.loads(invoke("apps", "context", "--json").output)
    assert view["ting_yu_ideas"] == []


@pytest.mark.parametrize("slug", ["no-such-idea", "quote-builder", "invoice-builder"])
def test_submit_prd_refuses_an_idea_slug_that_isnt_an_open_idea_of_ting_yus(tmp_path, conn, slug):
    """Review B1: `invoice-builder` is an open seed idea. Marking it would rename it to the PRD's
    name, so the seed idea would be lost from the backlog."""
    before = backlog.load()
    for dry_run in (["--dry-run"], []):
        result = invoke("apps", "submit-prd", *dry_run, "--idea", slug, str(write(tmp_path, GOOD)))
        assert result.exit_code == 1 and f"idea: {slug!r} isn't an open idea of Ting Yu's" in result.output, result.output
    assert backlog.load() == before
    assert not (paths.prd_dir() / "pending" / "apps" / "prd-app-003-delivery-order-maker-2026-10-26.md").exists()


def _without_the_seed_delivery_order_row() -> None:
    backlog.save([r for r in backlog.load() if r["slug"] != "delivery-order-maker"])


def test_submit_prd_marks_only_the_oldest_of_ting_yus_ideas(tmp_path, conn, monkeypatch):
    _without_the_seed_delivery_order_row()
    _add("Petty cash log: track petty cash", "2026-10-20", monkeypatch)
    _add("DO maker: delivery orders with a signature box", "2026-10-21", monkeypatch)
    monkeypatch.setenv("JURA_GROWTH_NOW", f"{TODAY}T06:30:00+08:00")
    result = invoke("apps", "submit-prd", "--dry-run", "--idea", "do-maker", str(write(tmp_path, GOOD)))
    assert result.exit_code == 1 and "petty-cash-log comes first" in result.output, result.output


def test_a_renamed_prd_without_idea_is_refused_while_ting_yus_idea_waits(tmp_path, conn):
    """The link doesn't rest on the prompt remembering `--idea`."""
    _without_the_seed_delivery_order_row()
    assert invoke("apps", "idea", "DO maker: delivery orders with a signature box").exit_code == 0
    result = invoke("apps", "submit-prd", "--dry-run", str(write(tmp_path, GOOD)))
    assert result.exit_code == 1 and "--idea do-maker" in result.output and "apps hold-idea" in result.output


def test_a_prd_with_his_ideas_own_name_is_marked_against_it_without_idea(tmp_path, conn):
    _without_the_seed_delivery_order_row()
    assert invoke("apps", "idea", "Delivery order maker: DOs with a signature box").exit_code == 0
    assert invoke("apps", "submit-prd", str(write(tmp_path, GOOD))).exit_code == 0
    marked = row("delivery-order-maker")
    assert marked["source"] == "ting-yu" and marked["status"] == "prd-pending" and marked["app_id"] == "APP-003"
    assert [r["slug"] for r in backlog.load()].count("delivery-order-maker") == 1


def test_after_his_idea_is_held_today_the_normal_pick_may_be_filed(tmp_path, conn):
    assert invoke("apps", "idea", "Petty cash log: track petty cash").exit_code == 0
    assert invoke("apps", "submit-prd", "--dry-run", str(write(tmp_path, GOOD))).exit_code == 1
    assert invoke("apps", "hold-idea", "petty-cash-log", "--reason", "it needs a rule no page confirms").exit_code == 0
    result = invoke("apps", "submit-prd", str(write(tmp_path, GOOD)))
    assert result.exit_code == 0, result.output
    assert row("delivery-order-maker")["status"] == "prd-pending" and "source" not in row("delivery-order-maker")
    assert row("petty-cash-log")["status"] == "idea"


def test_renaming_his_idea_onto_another_rows_slug_is_refused(tmp_path, conn):
    """Review B1: two rows would share one slug. The seed's Delivery order maker is still here."""
    assert invoke("apps", "idea", "DO maker: delivery orders with a signature box").exit_code == 0
    before = backlog.load()
    result = invoke("apps", "submit-prd", "--idea", "do-maker", str(write(tmp_path, GOOD)))
    assert result.exit_code == 1 and "Delivery order maker" in result.output and "backlog" in result.output
    assert backlog.load() == before


# --- holding an idea that fails a check -----------------------------------------------------------


def test_hold_idea_records_the_reason_in_the_notes_and_the_digest(conn):
    assert invoke("apps", "idea", "Petty cash log: track petty cash").exit_code == 0
    reason = "the IRAS page wouldn't load, so the rule can't be confirmed today"
    result = invoke("apps", "hold-idea", "petty-cash-log", "--reason", reason)
    assert result.exit_code == 0, result.output
    held = row("petty-cash-log")
    assert held["status"] == "idea" and held["held"] == TODAY and held["held_reason"] == reason
    assert held["notes"].endswith(f"Not picked first on {TODAY}: {reason}")
    lines = apps_plugin.digest(conn, TODAY)["lines"]
    assert f"App factory: your idea Petty cash log wasn't picked first: {reason}." in lines


def test_hold_idea_caps_the_reason_at_300_characters(conn):
    assert invoke("apps", "idea", "Petty cash log: track petty cash").exit_code == 0
    assert invoke("apps", "hold-idea", "petty-cash-log", "--reason", "word " * 1000).exit_code == 0
    reason = row("petty-cash-log")["held_reason"]
    assert len(reason) <= 300 and reason.startswith("word word") and reason.endswith("…")
    assert all(len(line) < 400 for line in apps_plugin.digest(conn, TODAY)["lines"])


def test_hold_idea_holds_only_the_oldest_of_ting_yus_ideas(conn, monkeypatch):
    _add("Petty cash log: track petty cash", "2026-10-20", monkeypatch)
    _add("Job sheet: a one-page job sheet", "2026-10-21", monkeypatch)
    result = invoke("apps", "hold-idea", "job-sheet", "--reason", "x")
    assert result.exit_code == 1 and "petty-cash-log comes first" in result.output
    assert "held" not in row("job-sheet")


def test_hold_idea_only_holds_an_open_idea_of_ting_yus(conn):
    for slug in ("invoice-builder", "quote-builder", "no-such-idea"):
        result = invoke("apps", "hold-idea", slug, "--reason", "x")
        assert result.exit_code == 1 and slug in result.output
    assert invoke("apps", "idea", "Petty cash log: track petty cash").exit_code == 0
    assert invoke("apps", "hold-idea", "petty-cash-log", "--reason", "x").exit_code == 0
    again = invoke("apps", "hold-idea", "petty-cash-log", "--reason", "y")
    assert again.exit_code == 1 and "already held" in again.output


def test_hold_idea_needs_a_reason(conn):
    assert invoke("apps", "idea", "Petty cash log: track petty cash").exit_code == 0
    assert invoke("apps", "hold-idea", "petty-cash-log", "--reason", "  ").exit_code == 2
    assert "held" not in row("petty-cash-log")


def test_the_factory_may_hold_ideas_and_link_them_but_not_add_them():
    commands = apps_plugin.permissions("app-factory").commands
    assert "apps hold-idea" in commands and "apps idea" not in commands


def test_the_digest_says_nothing_of_ideas_held_on_other_days(conn, monkeypatch):
    _add("Petty cash log: track petty cash", "2026-10-25", monkeypatch)
    assert invoke("apps", "hold-idea", "petty-cash-log", "--reason", "x").exit_code == 0
    assert not any("your idea" in line for line in apps_plugin.digest(conn, TODAY)["lines"])


# --- the prompt contract ---------------------------------------------------------------------------

PROMPT = (paths.REPO_ROOT / "prompts" / "app-factory.md").read_text(encoding="utf-8")


def _section(heading: str) -> str:
    return PROMPT.split(f"\n## {heading}", 1)[1].split("\n## ", 1)[0]


def test_the_prompt_picks_ting_yus_ideas_first_oldest_first():
    pick = _section("1. Pick the next idea")
    assert "`ting_yu_ideas`" in pick and "`source: ting-yu`" in pick and "oldest first" in pick
    assert pick.index("ting_yu_ideas") < pick.index("Weigh each candidate")


def test_the_prompt_keeps_every_check_for_ting_yus_ideas():
    pick = _section("1. Pick the next idea")
    first = pick.split("Weigh each candidate", 1)[0]
    for check in ("official", "near-duplicate", "legal, medical or financial advice", "government service"):
        assert check in first, check
    assert "prds_per_day" in first


def test_the_prompt_holds_a_failed_idea_and_says_so_in_the_summary():
    pick = _section("1. Pick the next idea")
    assert "jura-growth apps hold-idea <slug> --reason" in pick
    assert re.search(r"never skip it silently", pick, re.I)
    finish = _section("5. Finish")
    assert "Ting Yu's idea" in finish and "held" in finish


def test_the_prompt_holds_an_idea_whose_prd_still_cant_be_filed():
    """Review S4: an idea that passes the content checks but fails at `submit-prd` is held too, so
    it isn't first again tomorrow."""
    filing = _section("4. Check, then file")
    assert "jura-growth apps hold-idea <slug> --reason" in filing
    assert re.search(r"brand check fails twice", filing) and re.search(r"refus", filing)


def test_the_prompt_links_the_prd_to_the_idea_row():
    assert "jura-growth apps submit-prd --idea <slug>" in PROMPT
    assert "--idea <slug>" in _section("4. Check, then file")


# --- review S1: parallel writers never lose a row ------------------------------------------------


def test_parallel_ideas_each_answered_added_are_each_on_disk(conn):
    """Every `apps idea` that answered "Added" has its row, whatever else wrote at the same time:
    the backlog is read, changed and saved under one lock, and replaced in one step."""
    assert invoke("apps", "idea", "Seed first: make the file").exit_code == 0
    command = [sys.executable, "-m", "jura_growth"]
    children = [
        subprocess.Popen([*command, "apps", "idea", f"Race idea {chr(97 + n)}: tool number {n}"],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=dict(os.environ))
        for n in range(12)
    ]
    added = []
    for n, child in enumerate(children):
        out, err = child.communicate(timeout=120)
        assert child.returncode == 0, out + err
        assert out.startswith("Added to the app backlog:")
        added.append(f"race-idea-{chr(97 + n)}")
    on_disk = [r["slug"] for r in backlog.load()]
    assert sorted(slug for slug in on_disk if slug.startswith("race-idea")) == sorted(added)
    assert len(on_disk) == 20 + 1 + 12 and len(set(on_disk)) == len(on_disk)


def test_a_save_replaces_the_file_in_one_step_and_leaves_no_temp_file(conn, monkeypatch):
    assert invoke("apps", "idea", "Petty cash log: track petty cash").exit_code == 0
    replaced = []
    real = os.replace
    monkeypatch.setattr(os, "replace", lambda src, dst: (replaced.append((str(src), str(dst))), real(src, dst))[1])
    assert invoke("apps", "idea", "Job sheet: a one-page job sheet").exit_code == 0
    [(src, dst)] = replaced
    assert dst == str(backlog.path().resolve()) and os.path.dirname(src) == os.path.dirname(dst)
    assert sorted(p.name for p in backlog.path().parent.iterdir() if p.name.startswith(".app-backlog")) == []
    text = backlog.path().read_text(encoding="utf-8")
    assert text.startswith(backlog.HEADER) and len(backlog.load()) == 22
