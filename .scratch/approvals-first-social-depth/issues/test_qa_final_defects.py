"""Failing regression tests for the defects QA filed at f0db1e5 (reviews/qa-final.md).

Each is red on f0db1e5 for the reason its ticket gives. Copy this file to `tests/` to run it, with
the worktree exports from docs/agents/crew.md, and take a test into the suite with its fix:

    uv run pytest tests/test_qa_final_defects.py -p no:cacheprovider -o addopts=""
"""

from __future__ import annotations

import json

import publish_world as pw
from discord_double import discord_double  # noqa: F401 - a fixture
from gate_adapter_community_post import ADAPTER as COMMUNITY_POST
from jura_growth import approvals, brand_check, cards, config, db, paths
from jura_growth.agents import social
from test_approvals_first import feed_lines, social_day, submit_tip  # noqa: F401 - a fixture
from test_social import env  # noqa: F401 - a fixture


def summary() -> dict:
    return json.loads((paths.data_dir() / "daily-summary.json").read_text(encoding="utf-8"))


def social_line(found: dict) -> str:
    return next(line for line in found["lines"] if line.startswith("Social:"))


# --- 05: the digest after a card closes ----------------------------------------------------------


def test_cards_nobody_answered_are_not_called_no_card_or_waiting_at_the_1805_digest(conn, social_day, monkeypatch):
    submit_tip(conn)
    cards.sweep(conn)
    pw.at(monkeypatch, "2026-11-10T18:05:00+08:00")
    conn.commit()
    assert pw.invoke("digest").exit_code == 0
    found = summary()
    assert found["figures"]["publish_expired"] == 2
    assert "no card" not in social_line(found)
    assert "waiting" not in found["brief_line"]
    assert found["figures"]["social_drafts_waiting"] == 0


def test_a_post_claimed_by_a_run_is_not_called_a_draft_with_no_card(conn, social_day, monkeypatch):
    submit_tip(conn)
    first, _ = approvals.pending(conn)
    pw.at(monkeypatch, pw.TEN)
    pw.decide(conn, first, monkeypatch=monkeypatch)
    pw.run(conn, monkeypatch=monkeypatch)
    assert pw.next_item(conn).item is not None
    conn.commit()
    line = social_line(social.digest(conn, "2026-11-10"))
    assert "with no card (facebook" not in line


# --- 06: an approved line that promises a post nothing can make -----------------------------------


def test_an_approval_while_the_platform_is_in_draft_mode_promises_no_post(conn, social_day, monkeypatch):
    submit_tip(conn)
    first, _ = approvals.pending(conn)
    pw.at(monkeypatch, pw.TEN)
    pw.social_config(monkeypatch, browser=())  # the way back, with a card open
    pw.decide(conn, first, monkeypatch=monkeypatch)
    cards.sweep(conn)
    [line] = feed_lines(social_day)
    assert pw.next_item(conn).item is None  # nothing posts, as AF5 wants
    assert "It goes out" not in line


def test_a_community_post_approved_after_the_last_run_promises_no_post(conn, env, monkeypatch, discord_double, tmp_path):
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
    gate = COMMUNITY_POST(conn=conn, monkeypatch=monkeypatch, tmp_path=tmp_path)
    approval = gate.raise_request(gate.item())
    cards.sweep(conn)
    day = db.scalar(conn, "SELECT substr(decide_by, 1, 10) FROM approvals WHERE id = ?", (approval.number,))
    pw.at(monkeypatch, f"{day}T17:50:00+08:00")  # the last publish slot started at 17:40
    assert gate.approve(approval).answer == "recorded"
    cards.sweep(conn)
    [line] = [m for m in discord_double.contents("community") if m.startswith(f"**{approval.id} approved")]
    assert "It goes out" not in line


# --- 07: a config folder that isn't there -----------------------------------------------------------


def test_a_missing_buzzword_list_does_not_pass_a_buzzword(monkeypatch, tmp_path):
    """Either the gate refuses, or it stops loudly. It must not read "no list" as "no buzzwords"."""
    monkeypatch.setenv("JURA_GROWTH_CONFIG_DIR", str(tmp_path / "not-there"))
    config.reset_caches()
    brand_check._buzzword_patterns.cache_clear()  # it outlives a change of folder within one process
    try:
        result = brand_check.check("Leverage the model", channel_name="social-card")
    except (OSError, ValueError, RuntimeError):  # a loud stop is a fine fix
        return
    finally:
        monkeypatch.undo()
        config.reset_caches()
        brand_check._buzzword_patterns.cache_clear()
    assert not result.passed


# --- 08: the intermittent failure --------------------------------------------------------------


def test_the_live_engine_writing_its_run_log_does_not_fail_the_refusal_test(monkeypatch, tmp_path):
    """What happened at 00:00:02 on 2026-11-01. The live publish job, not the test, wrote the day's
    run log while `test_every_scenario_refuses_the_live_folders_and_changes_nothing[note-rules]` ran.
    Stand-in folders here, so this never touches the live ones."""
    import test_uat_seed_outreach as refusal

    live = tmp_path / "growth"
    (live / "runs").mkdir(parents=True)
    (tmp_path / "config").mkdir()
    monkeypatch.setattr(refusal, "LIVE_DATA", live)
    monkeypatch.setattr(refusal, "REAL_CONFIG", tmp_path / "config")
    before = refusal.untouched_snapshot()
    (live / "runs" / "2026-11-01.jsonl").write_text('{"agent": "publish", "kind": "run.quiet"}\n', encoding="utf-8")
    assert refusal.untouched_snapshot() == before


# --- 09: a typed approval of a refused card, in a new process ---------------------------------------


def test_a_typed_approval_of_a_card_refused_for_a_learned_name_is_refused_in_a_new_process(conn, env, monkeypatch, discord_double):
    from jura_growth import privacy
    from uat import seed

    pw.at(monkeypatch, pw.MORNING)
    pw.social_config(monkeypatch, browser=("facebook", "instagram"))
    _, request = pw.item(conn, "facebook", text="Picture a small firm chasing its invoices.\n\nhttps://jurasolutions.sg\n")
    seed._lead(conn, 1, "Acme Pte Ltd", "acme.example.sg")
    seed._contact(conn, 1, "marta.picture@acme.example.sg", "named", "https://acme.example.sg/contact")
    conn.commit()
    cards.sweep(conn)
    assert approvals.get(conn, request.id).posted_at is None  # the sweep refused the card
    assert cards.refusal(conn, request.id)

    # What each SSH call is: a fresh process that has learned nothing yet.
    privacy.reset()
    config.reset_caches()
    answer = pw.decide(conn, request, monkeypatch=monkeypatch)
    assert answer.answer == approvals.REFUSED, answer.text
