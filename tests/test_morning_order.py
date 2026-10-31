"""The morning, end to end (test strategy "End to end"; PRD SC2, SC3, MB1).

The clock steps through the morning in live mode: 06:40, 08:30, 09:00. The one-pager posts through
real Chrome, Decide lists what was raised, soonest first, and nothing sends.

Two mornings, because `queue` tops up: when the research run queues an email, its `raise_due` also
raises anything older still waiting, so the 08:30 job finds nothing left. The job does its own work
on a morning the research run stops early and queues nothing (PRD §1).
"""

from __future__ import annotations

import pytest

from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import images, one_pager, paths, runner
from test_scout_support import at, configure, fake_resend, live_ready, outreach_requests, scout_env, seed  # noqa: F401

FRIDAY = "2026-11-06T15:00:00+08:00"
AT_0640, AT_0830, AT_0900 = ("2026-11-10T06:40:00+08:00", "2026-11-10T08:30:00+08:00", "2026-11-10T09:00:00+08:00")
needs_chrome = pytest.mark.skipif(images.chrome_path(images.DEFAULT_CHROME) is None, reason="Google Chrome is not installed")
pytestmark = needs_chrome


def cards(double) -> list:
    return [r for r in double.requests if r.channel == "approvals" and r.method == "POST"]


@pytest.fixture
def sent(monkeypatch):
    monkeypatch.setattr(one_pager, "OFFLINE", True)
    return fake_resend(monkeypatch)


def leftovers(conn, monkeypatch, n: int) -> None:
    """Emails queued on Friday in shadow mode, so none has a request. Then live mode."""
    at(monkeypatch, FRIDAY)
    for lead in range(1, n + 1):
        seed(conn, lead)
    assert outreach_requests(conn) == []
    live_ready(monkeypatch)
    configure(monkeypatch, mode="live", legal_review_done=True, sending_domain="hello.jurasolutions.sg", send={"per_day": 5})


def assert_the_post_decides_both_and_nothing_sends(conn, double, sent) -> None:
    pending = outreach_requests(conn, "pending")
    assert len(pending) == 2
    (post,) = double.posts("mission-control")
    (name, body), = post.files
    assert name == "picture-2026-11-10.png" and body.startswith(images.PNG_SIGNATURE)
    lines = post.content.splitlines()
    assert lines[0] == "**Tue 10 Nov, as of 09:00 SGT**"
    assert lines[1].startswith("2 to decide")

    first, second = sorted(pending, key=lambda r: (r.decide_by, r.number))
    assert f"Decide in #approvals: outreach email 2. Soonest: {first.id}, by " in post.content
    page = (paths.data_dir() / "one-pager" / "picture-2026-11-10.html").read_text(encoding="utf-8")
    assert page.index(first.id) < page.index(second.id)

    assert sent == []
    assert not list(conn.execute("SELECT 1 FROM outreach_messages WHERE status != 'queued'"))


def test_a_morning_when_the_research_run_queues_an_email(conn, monkeypatch, discord_double, sent):
    leftovers(conn, monkeypatch, 1)

    at(monkeypatch, AT_0640)  # the queue raises this email and the leftover, and posts both cards
    seed(conn, 2)
    assert len(outreach_requests(conn, "pending")) == 2
    assert len(cards(discord_double)) == 2

    at(monkeypatch, AT_0830)  # nothing left for the job to do: it stays quiet, and adds no card
    outcome = runner.run("outreach-requests", ignore_schedule=True)
    assert outcome.status == "ok" and not outcome.summary
    assert len(cards(discord_double)) == 2

    at(monkeypatch, AT_0900)
    assert runner.run("one-pager", ignore_schedule=True).status == "ok"
    assert_the_post_decides_both_and_nothing_sends(conn, discord_double, sent)


def test_a_morning_when_the_research_run_queues_nothing(conn, monkeypatch, discord_double, sent):
    leftovers(conn, monkeypatch, 2)

    at(monkeypatch, AT_0640)  # research stopped early: no request, and no card, yet
    assert outreach_requests(conn) == [] and cards(discord_double) == []

    at(monkeypatch, AT_0830)  # the leftovers get their requests and cards before the picture
    outcome = runner.run("outreach-requests", ignore_schedule=True)
    assert outcome.status == "ok" and outcome.summary == "raised 2 approval requests"
    assert len(cards(discord_double)) == 2

    at(monkeypatch, AT_0900)
    assert runner.run("one-pager", ignore_schedule=True).status == "ok"
    assert_the_post_decides_both_and_nothing_sends(conn, discord_double, sent)
