"""Regressions for code review 02 (BP-02a): repros r1 to r5 and findings S2 and S7.

- B1 (r1, r2): a content change raises a fresh request whose deadlines come from the new
  content, whichever path notices it, and an item is never withdrawn without its replacement.
- B2 (r3): the claim hands out exactly the bytes it checked against the approval.
- S6 (r4, r5): a claim nobody will close can still be settled.
- S7: the digest counts a skip made by hand.
- S2: the preamble never lists a `NEVER` command, however many words it has.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date

import pytest

import publish_world as pw
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import approvals, headless, paths, runner, timeutil
from jura_growth.agents import publish
from jura_growth.agents.publish import kinds
from test_publish_queue import next_json, state, world  # noqa: F401 - world is a fixture


# --- B1 ---------------------------------------------------------------------------------------------


def test_r1_a_new_day_raises_a_request_whose_deadlines_are_the_new_days(conn, world, monkeypatch):
    found, request = pw.approved(conn, monkeypatch)
    conn.execute("UPDATE social_posts SET date = '2026-11-11' WHERE id = ?", (found.ref_id,))
    assert next_json()["due"] is False
    assert approvals.get(conn, request.id).status == "superseded"
    [fresh] = [a for a in approvals.pending(conn) if a.subject == found.subject]
    assert fresh.decide_by == "2026-11-11T18:00:00+08:00"
    assert pw.item_row(conn, found.id)["day"] == "2026-11-11" and state(conn, found) == "ready"
    pw.at(monkeypatch, "2026-11-11T10:00:00+08:00")
    assert pw.decide(conn, fresh).answer == "recorded"
    assert approvals.get(conn, fresh.id).use_by == "2026-11-11T18:00:00+08:00"
    handed = next_json()
    assert handed["approval"] == fresh.id and handed["day"] == "2026-11-11"


def test_r2_a_change_the_heartbeat_finds_still_gets_its_new_card(conn, world, monkeypatch, discord_double):
    found, request = pw.approved(conn, monkeypatch)
    conn.execute("UPDATE social_posts SET text = text || ' (edited)' WHERE id = ?", (found.ref_id,))
    approvals.expire_due(conn)  # what the noon heartbeat and the 08:00 job do: supersedes, raises nothing
    assert approvals.get(conn, request.id).status == "superseded"
    assert next_json()["due"] is False
    assert state(conn, found) == "ready"
    [fresh] = [a for a in approvals.pending(conn) if a.subject == found.subject]
    assert fresh.content_hash != request.content_hash
    assert json.loads(pw.item_row(conn, found.id)["content_json"])["text"].endswith(" (edited)")
    cards = [c for c in discord_double.contents("approvals") if fresh.id in c]
    assert cards and "(edited)" in cards[0]


def test_an_item_is_withdrawn_only_when_there_is_nothing_to_replace_it_with(conn, world, monkeypatch):
    found, _ = pw.approved(conn, monkeypatch)
    pw.invoke("social", "skip", "2026-11-10", "facebook")
    approvals.expire_due(conn)
    assert next_json()["due"] is False
    assert state(conn, found) == "withdrawn"
    assert [a for a in approvals.pending(conn) if a.subject == found.subject] == []


# --- B2 ---------------------------------------------------------------------------------------------


def test_r3_an_image_swapped_after_use_is_never_handed_out(conn, world, monkeypatch):
    image = pw.image("facebook-1.png")
    found, request = pw.approved(conn, monkeypatch, images=[image])
    real_use = approvals.use

    def use_then_swap(*args, **kwargs):
        record = real_use(*args, **kwargs)
        image.write_bytes(pw.png(extra=b"never approved"))
        return record

    monkeypatch.setattr(approvals, "use", use_then_swap)
    handed = next_json()
    assert handed["due"] is False and "changed while it was being claimed" in handed["reasons"][0]
    record = approvals.get(conn, request.id)
    assert record.status == "approved" and record.used_at is None
    assert state(conn, found) == "ready"
    assert not (paths.work_dir("publish") / request.id).exists()


def test_the_bytes_handed_out_hash_to_the_approval(conn, world, monkeypatch):
    images = [pw.image("facebook-1.png"), pw.image("facebook-2.png", pw.png(extra=b"two"))]
    _, request = pw.approved(conn, monkeypatch, images=images)
    handed = next_json()
    blobs = [pw.Path(copy).read_bytes() for copy in handed["images"]]
    content = {key: handed[key] for key in ("platform", "posting_identity", "target_url", "day", "text")}
    content["images"] = [{"sha256": hashlib.sha256(blob).hexdigest()} for blob in blobs]
    assert approvals.content_hash(kinds.hashed(content)) == request.content_hash


# --- S6 ---------------------------------------------------------------------------------------------


def test_r4_a_claim_whose_run_died_is_resolvable_and_the_next_run_settles_one(conn, world, monkeypatch):
    found, request = pw.approved(conn, monkeypatch)
    dead = pw.run(conn, monkeypatch=monkeypatch)
    next_json()
    conn.execute("UPDATE runs SET status = 'failed', finished_at = ? WHERE id = ?", (timeutil.stamp(), dead))
    assert pw.invoke("publish", "resolve", request.id, "not-posted").exit_code == 0
    assert pw.item_row(conn, found.id)["outcome"] == "not-posted"

    other, second = pw.approved(conn, monkeypatch, "facebook", day=date(2026, 11, 11))
    pw.at(monkeypatch, "2026-11-11T10:00:00+08:00")
    killed = pw.run(conn, monkeypatch=monkeypatch)
    next_json()
    conn.execute("UPDATE runs SET status = 'failed', finished_at = ? WHERE id = ?", (timeutil.stamp(), killed))
    later = pw.run(conn, "2026-11-11T10:30:00+08:00")
    outcome = publish.after_run(conn, "publish", later, runner.Outcome("ok"))
    assert outcome is not None and outcome.status == "failed" and second.id in outcome.error
    assert pw.item_row(conn, other.id)["state"] == "unknown"


def test_r5_a_terminal_claim_with_no_run_can_be_resolved(conn, world, monkeypatch):
    found, request = pw.approved(conn, monkeypatch)
    next_json()
    assert approvals.get(conn, request.id).used_by_run is None
    url = "https://www.facebook.com/jura-test-page/posts/5"
    assert pw.invoke("publish", "resolve", request.id, "posted", "--url", url).exit_code == 0
    row = pw.item_row(conn, found.id)
    assert (row["state"], row["post_url"]) == ("done", url)


def test_a_claim_by_a_run_still_running_cant_be_resolved(conn, world, monkeypatch):
    _, request = pw.approved(conn, monkeypatch)
    pw.run(conn, monkeypatch=monkeypatch)
    next_json()
    result = pw.invoke("publish", "resolve", request.id, "not-posted")
    assert result.exit_code == 1 and "isn't unknown" in result.output


# --- S7 ---------------------------------------------------------------------------------------------


def test_the_digest_counts_a_skip_made_by_hand(conn, world, monkeypatch):
    pw.approved(conn, monkeypatch)
    pw.invoke("social", "skip", "2026-11-10", "facebook")
    assert publish.digest(conn, "2026-11-10")["figures"]["publish_skipped"] == 1
    approvals.expire_due(conn)
    next_json()  # the item is withdrawn now
    assert publish.digest(conn, "2026-11-10")["figures"]["publish_skipped"] == 1


# --- S2 ---------------------------------------------------------------------------------------------


def test_the_preamble_never_lists_a_several_word_never_command(monkeypatch):
    real = headless.permissions

    def declares_resolve(job):
        found = real(job)
        return headless.Permissions(commands=(*found.commands, "publish resolve"), disallowed_tools=found.disallowed_tools)

    monkeypatch.setattr(headless, "permissions", declares_resolve)
    assert "publish resolve" not in runner._commands_line("social")


# --- S4 ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("url", ["http://www.facebook.com/jura", "https://evil.test/jura", "https://www.facebook.com@evil.test/x"])
def test_a_page_url_off_the_platforms_hosts_raises_no_item(conn, monkeypatch, url):
    pw.social_config(monkeypatch, urls={"facebook": url})
    pw.at(monkeypatch, pw.TEN)
    made = publish.items.create_social(conn, pw.draft(conn), run_id=None)
    assert made.item is None and "page_url" in made.why
