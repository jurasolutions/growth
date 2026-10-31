"""Regression tests for the defects QA filed at f0db1e5 (`reviews/qa-final.md`, tickets 05 to 09)."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

import publish_world as pw
from discord_double import discord_double  # noqa: F401 - a fixture
from gate_adapter_community_post import ADAPTER as COMMUNITY_POST
from jura_growth import approvals, brand_check, cards, config, db, paths
from jura_growth.agents import social
from test_approvals_first import BOTH, LATE, feed_lines, refuse_facebook, social_day, submit_tip  # noqa: F401 - a fixture
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
    assert "2 drafts expired (facebook, instagram)" in social_line(found)
    assert "no card" not in social_line(found)
    assert "waiting" not in found["brief_line"]
    assert found["figures"]["social_drafts_waiting"] == 0


def test_a_digest_that_writes_no_lapse_still_calls_a_past_decide_by_expired(conn, social_day, monkeypatch):
    """`digest --no-post` and the morning read write nothing, and the card has closed all the same."""
    submit_tip(conn)
    cards.sweep(conn)
    conn.commit()
    pw.at(monkeypatch, "2026-11-10T18:05:00+08:00")
    found = social.digest(conn, "2026-11-10")
    assert "2 drafts expired" in social_line(found)
    assert found["figures"]["social_drafts_waiting"] == 0


def test_a_post_claimed_by_a_run_is_not_called_a_draft_with_no_card(conn, social_day, monkeypatch):
    submit_tip(conn)
    first, _ = approvals.pending(conn)
    pw.at(monkeypatch, pw.TEN)
    pw.decide(conn, first, monkeypatch=monkeypatch)
    pw.run(conn, monkeypatch=monkeypatch)
    assert pw.next_item(conn).item is not None
    conn.commit()
    found = social.digest(conn, "2026-11-10")
    line = social_line(found)
    assert "with no card (facebook" not in line
    assert "1 draft claimed by a publish run (facebook)" in line
    assert found["figures"]["social_drafts_waiting"] == 1  # Instagram's card still waits


def test_an_approved_post_waits_on_a_publish_run(conn, social_day, monkeypatch):
    submit_tip(conn)
    first, _ = approvals.pending(conn)
    pw.at(monkeypatch, pw.TEN)
    pw.decide(conn, first, monkeypatch=monkeypatch)
    conn.commit()
    found = social.digest(conn, "2026-11-10")
    assert "1 draft approved, waiting on a publish run (facebook)" in social_line(found)
    assert found["figures"]["social_drafts_waiting"] == 2


def test_a_no_images_day_says_no_card_and_nothing_waits(conn, env, monkeypatch, discord_double):
    pw.at(monkeypatch, LATE)  # too late to ask: drafts and no card, as with no images
    pw.social_config(monkeypatch, browser=BOTH)
    assert submit_tip(conn).status == "delivered"
    found = social.digest(conn, "2026-11-10")
    assert "2 drafts with no card (facebook, instagram)" in social_line(found)
    assert found["figures"]["social_drafts_waiting"] == 0
    assert found["brief"] == []


def test_a_refused_card_says_no_card_and_is_not_counted_as_waiting(conn, social_day, monkeypatch):
    refuse_facebook(monkeypatch)
    submit_tip(conn)
    found = social.digest(conn, "2026-11-10")
    assert "1 draft waiting in #approvals (instagram)" in social_line(found)
    assert "1 draft with no card (facebook)" in social_line(found)
    assert found["figures"]["social_drafts_waiting"] == 1


def test_a_card_discord_has_not_taken_yet_still_waits(conn, social_day, monkeypatch):
    """The heartbeat posts it, so it isn't lost, and he will be asked."""
    social_day.mode = "500"
    submit_tip(conn)
    found = social.digest(conn, "2026-11-10")
    assert "2 drafts with no card (facebook, instagram)" in social_line(found)
    assert found["figures"]["social_drafts_waiting"] == 2


def test_a_platform_moved_to_draft_mode_with_an_approved_post_says_so_and_offers_no_hand_post(conn, social_day, monkeypatch):
    submit_tip(conn)
    first, _ = approvals.pending(conn)
    pw.at(monkeypatch, pw.TEN)
    pw.decide(conn, first, monkeypatch=monkeypatch)
    pw.social_config(monkeypatch, browser=("instagram",))
    conn.commit()
    found = social.digest(conn, "2026-11-10")
    assert "1 draft approved, held by draft mode (facebook)" in social_line(found)
    assert "#social-drafts" not in social_line(found)
    assert found["figures"]["social_drafts_by_hand"] == 0



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
    assert "draft mode" in line and "lapses at 18:00 SGT" in line


def _community_post(conn, monkeypatch, tmp_path):
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
    gate = COMMUNITY_POST(conn=conn, monkeypatch=monkeypatch, tmp_path=tmp_path)
    approval = gate.raise_request(gate.item())
    cards.sweep(conn)
    day = db.scalar(conn, "SELECT substr(decide_by, 1, 10) FROM approvals WHERE id = ?", (approval.number,))
    return gate, approval, day


def _community_line(discord_double, approval) -> str:
    [line] = [m for m in discord_double.contents("community") if m.startswith(f"**{approval.id} approved")]
    return line


def test_a_community_post_approved_after_the_last_run_promises_no_post(conn, env, monkeypatch, discord_double, tmp_path):
    gate, approval, day = _community_post(conn, monkeypatch, tmp_path)
    pw.at(monkeypatch, f"{day}T17:50:00+08:00")  # the last publish slot started at 17:40
    assert gate.approve(approval).answer == "recorded"
    cards.sweep(conn)
    line = _community_line(discord_double, approval)
    assert "It goes out" not in line
    assert "No publish run is left" in line and "18:00 SGT" in line


def test_a_community_post_approved_in_time_with_nothing_in_its_way_goes_out(conn, env, monkeypatch, discord_double, tmp_path):
    gate, approval, day = _community_post(conn, monkeypatch, tmp_path)
    pw.at(monkeypatch, f"{day}T10:00:00+08:00")
    assert gate.approve(approval).answer == "recorded"
    cards.sweep(conn)
    assert "It goes out on a publish run" in _community_line(discord_double, approval)


def test_a_community_post_whose_group_rules_stop_it_says_so(conn, env, monkeypatch, discord_double, tmp_path):
    gate, approval, day = _community_post(conn, monkeypatch, tmp_path)
    conn.execute("UPDATE community_groups SET rules_confirmed = 0")
    conn.commit()
    pw.at(monkeypatch, f"{day}T10:00:00+08:00")
    assert gate.approve(approval).answer == "recorded"
    cards.sweep(conn)
    line = _community_line(discord_double, approval)
    assert "It goes out" not in line
    assert "the group's rules aren't confirmed by Ting Yu" in line


def test_a_community_post_approved_with_browser_off_says_nothing_goes_through_the_browser(conn, env, monkeypatch, discord_double, tmp_path):
    gate, approval, day = _community_post(conn, monkeypatch, tmp_path)
    pw.at(monkeypatch, f"{day}T10:00:00+08:00")
    assert gate.approve(approval).answer == "recorded"
    monkeypatch.setattr("jura_growth.agents.publish.group_kinds.browser_on", lambda: False)
    cards.sweep(conn)
    line = _community_line(discord_double, approval)
    assert "It goes out" not in line and "community.browser is off" in line


# --- 07: a config folder that isn't there -----------------------------------------------------------


@pytest.fixture
def no_buzzword_list(monkeypatch, tmp_path):
    """A config folder with no list. `_buzzword_patterns` outlives a change of folder within one
    process, so its cache is cleared either side."""
    monkeypatch.setenv("JURA_GROWTH_CONFIG_DIR", str(tmp_path / "not-there"))
    config.reset_caches()
    brand_check._buzzword_patterns.cache_clear()
    yield tmp_path / "not-there"
    monkeypatch.undo()
    config.reset_caches()
    brand_check._buzzword_patterns.cache_clear()


def test_a_missing_buzzword_list_stops_the_gate(no_buzzword_list):
    """It must not read "no list" as "no buzzwords"."""
    with pytest.raises(FileNotFoundError, match="buzzwords.txt"):
        brand_check.check("Leverage the model", channel_name="social-card")


def test_an_empty_buzzword_list_stops_the_gate(no_buzzword_list):
    no_buzzword_list.mkdir()
    (no_buzzword_list / "buzzwords.txt").write_text("# nothing here\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="buzzwords.txt"):
        brand_check.check("Leverage the model", channel_name="social-card")


def test_the_check_command_says_the_list_is_missing_and_does_not_pass(no_buzzword_list):
    result = pw.invoke("check", "--channel", "social-card", "Leverage the model")
    assert result.exit_code != 0
    assert "buzzwords.txt" in result.output
    assert "pass" not in result.output.split()


# --- 09: a typed approval of a refused card, in a new process ---------------------------------------

PICTURE = "Picture a small firm chasing its invoices.\n\nhttps://jurasolutions.sg\n"

# What one SSH call is: a new process that has learned nothing, deciding as Dispatch's call decides.
NEW_PROCESS_DECIDES = """
import json, sys
from jura_growth import approvals, db, privacy
from jura_growth.origin import Origin
assert privacy.for_discord("Picture this") == "Picture this", "this process already knows the name"
conn = db.connect()
answer = approvals.decide(conn, sys.argv[1], "approve", actor="discord:111", origin=Origin.ssh(), source_ref=None, args={})
conn.commit()
print(json.dumps({"answer": answer.answer, "text": answer.text}))
"""


def refused_card(conn, monkeypatch):
    """A post whose card the sweep refused for a name learned from a contact's address, on the
    shipped config, so a second process reads the same content."""
    from uat import seed

    pw.at(monkeypatch, pw.MORNING)
    _, request = pw.item(conn, "facebook", text=PICTURE)
    seed._lead(conn, 1, "Acme Pte Ltd", "acme.example.sg")
    seed._contact(conn, 1, "marta.picture@acme.example.sg", "named", "https://acme.example.sg/contact")
    conn.commit()
    cards.sweep(conn)
    assert approvals.get(conn, request.id).posted_at is None  # the sweep refused the card
    assert cards.refusal(conn, request.id)
    return request


def test_a_typed_approval_of_a_card_refused_for_a_learned_name_is_refused_in_a_new_process(conn, env, monkeypatch, discord_double):
    request = refused_card(conn, monkeypatch)
    conn.commit()
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
    ran = subprocess.run([sys.executable, "-c", NEW_PROCESS_DECIDES, request.id], env=dict(os.environ),
                         capture_output=True, text=True, timeout=60)
    assert ran.returncode == 0, ran.stderr
    answer = json.loads(ran.stdout)
    assert answer["answer"] == approvals.REFUSED, answer["text"]
    assert "can't show the exact text" in answer["text"]

    conn.rollback()
    assert approvals.get(conn, request.id).status == approvals.PENDING
    pw.at(monkeypatch, pw.TEN)
    pw.run(conn, monkeypatch=monkeypatch)
    assert pw.next_item(conn).item is None
    assert approvals.get(conn, request.id).used_at is None


def test_a_card_the_sweep_refused_stays_refused_when_the_vocabulary_cannot_be_read(conn, env, monkeypatch, discord_double):
    """The sweep's refusal is on record, so a plug-in that fails to teach the name can't reopen it."""
    from jura_growth import privacy

    request = refused_card(conn, monkeypatch)
    conn.commit()
    privacy.reset()
    config.reset_caches()
    monkeypatch.setattr(privacy, "learn", lambda *a, **k: None)
    answer = pw.decide(conn, request, monkeypatch=monkeypatch)
    assert answer.answer == approvals.REFUSED, answer.text
    assert approvals.get(conn, request.id).status == approvals.PENDING


def test_a_refused_card_can_still_be_skipped(conn, env, monkeypatch, discord_double):
    request = refused_card(conn, monkeypatch)
    conn.commit()
    assert pw.decide(conn, request, "skip", monkeypatch=monkeypatch).answer == "recorded"
    assert approvals.get(conn, request.id).status == approvals.SKIPPED
