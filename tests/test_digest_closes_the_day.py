"""The digest runs after the day's use-by and writes the lapses first (functional review B3), so a
card nobody answered closes the same evening, its feed line goes out, and the day's count is right.
"""

from __future__ import annotations

import json

import publish_world as pw
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import approvals, cards, config, db, paths
from test_approvals_first import HEADLINE, feed_lines, social_day, submit_tip  # noqa: F401 - a fixture
from test_social import env  # noqa: F401 - a fixture


def test_the_1805_digest_closes_an_unanswered_card_and_counts_it(conn, social_day, monkeypatch):
    submit_tip(conn)
    first, second = approvals.pending(conn)
    cards.sweep(conn)
    pw.at(monkeypatch, "2026-11-10T18:05:00+08:00")
    conn.commit()
    result = pw.invoke("digest")
    assert result.exit_code == 0, result.output

    assert [approvals.get(conn, a.id).status for a in (first, second)] == [approvals.EXPIRED, approvals.EXPIRED]
    assert [line.split(" · ")[0] for line in feed_lines(social_day)] == [f"**{first.id} expired**", f"**{second.id} expired**"]
    assert all(line.endswith("Not approved in time.") and HEADLINE in line for line in feed_lines(social_day))
    summary = json.loads((paths.data_dir() / "daily-summary.json").read_text(encoding="utf-8"))
    assert summary["figures"]["publish_expired"] == 2
    assert summary["figures"]["social_drafts_waiting"] == 0
    assert "waiting" not in summary["brief_line"]
    assert any(line.startswith("Social: 2 drafts expired (facebook, instagram)") for line in summary["lines"])
    assert "2 expired" in result.output
    assert db.rows(conn, "SELECT * FROM approvals WHERE used_at IS NOT NULL") == []


def test_a_post_approved_and_never_claimed_closes_with_its_own_line_at_the_digest(conn, social_day, monkeypatch):
    submit_tip(conn)
    first, _ = approvals.pending(conn)
    pw.at(monkeypatch, "2026-11-10T16:59:00+08:00")
    pw.decide(conn, first, monkeypatch=monkeypatch)
    cards.sweep(conn)
    pw.at(monkeypatch, "2026-11-10T18:05:00+08:00")
    conn.commit()
    assert pw.invoke("digest").exit_code == 0
    mine = [line for line in feed_lines(social_day) if first.id in line]
    assert [line.split(" · ")[0] for line in mine] == [f"**{first.id} approved**", f"**{first.id} expired**"]
    assert mine[1].endswith("Approved but not used in time.")


def test_a_digest_that_posts_nothing_writes_no_lapse(conn, social_day, monkeypatch):
    submit_tip(conn)
    first, _ = approvals.pending(conn)
    pw.at(monkeypatch, "2026-11-10T18:05:00+08:00")
    conn.commit()
    assert pw.invoke("digest", "--no-post").exit_code == 0
    assert approvals.get(conn, first.id).status == approvals.PENDING
    assert feed_lines(social_day) == []


def test_the_digest_is_scheduled_after_the_use_by():
    assert config.settings()["jobs"]["digest"]["schedule"] == {"daily": "18:05"}
