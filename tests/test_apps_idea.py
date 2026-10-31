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
import re

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
])
def test_the_name_comes_from_the_part_before_the_first_colon(text, name):
    assert ideas.name_for(text) == name


def test_an_empty_idea_is_refused_and_nothing_is_written(conn):
    body = answer(remote(["apps", "idea"]))
    assert body["exit_code"] == 2 and body["answer"] == "refused"
    assert body["text"].startswith("refused:") and "apps idea <text>" in body["text"]
    assert not backlog.path().exists()


def test_words_with_no_letters_or_figures_are_refused(conn):
    body = answer(remote(["apps", "idea", "…", "!!"]))
    assert body["exit_code"] == 2 and body["text"].startswith("refused:")
    assert not backlog.path().exists()


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
    assert invoke("apps", "hold-idea", "job-sheet", "--reason", "it reads as legal advice").exit_code == 0
    view = json.loads(invoke("apps", "context", "--json").output)
    assert [r["slug"] for r in view["ting_yu_ideas"]] == ["petty-cash-log", "stock-count-sheet"]
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


def test_submit_prd_refuses_an_idea_slug_that_isnt_an_open_backlog_idea(tmp_path):
    for slug in ("no-such-idea", "quote-builder"):
        result = invoke("apps", "submit-prd", "--dry-run", "--idea", slug, str(write(tmp_path, GOOD)))
        assert result.exit_code == 1 and f"idea: {slug!r}" in result.output, result.output


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
    assert invoke("apps", "hold-idea", "petty-cash-log", "--reason", "  ").exit_code == 1
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


def test_the_prompt_links_the_prd_to_the_idea_row():
    assert "jura-growth apps submit-prd --idea <slug>" in PROMPT
    assert "--idea <slug>" in _section("4. Check, then file")
