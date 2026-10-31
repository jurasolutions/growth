"""Nothing planted reaches the morning picture (test strategy risk 1; MB8).

The `.html` is written directly, not through `discord.post()`, and the pixels can't be re-masked,
so the snapshot is the only gate. These tests sweep three things: the page handed to
`images.screenshot` (a spy, standing in for the PNG's pixels), `picture-<day>.html` read from disk,
and the message.

**The trap:** the picture keeps only an item's first line and first sentence, so planting
`Planted.text()` as one block passes with most values untested. Each value is planted alone, on the
first line, per route, and each route must show the marker.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

import mission_world as world
import sweep
from discord_double import discord_double  # noqa: F401 - a fixture
from sweep import d2_secrets  # noqa: F401 - a fixture
from jura_growth import agents, cli as cli_mod, images, one_pager, paths
from jura_growth.cli import cli
from test_discord_sweep import contact_lead

NINE = "2026-11-10T09:00:00+08:00"
# The value's first sentence is what survives, so nothing here holds ". ". `FINANCE` isn't here: a
# line naming that folder is dropped whole, marker and all, and has its own test below.
VALUES = (*sweep.SECRETS, sweep.NAMED_ADDRESS, sweep.PHONE, sweep.PERSON, sweep.OWNER_ADDRESS)


def plugin(name: str):
    return next(module for module in agents.plugins() if getattr(module, "NAME", "") == name)


def _approval_reason(conn, monkeypatch, text):
    conn.execute(
        "INSERT INTO approvals (id, kind, subject, content_hash, status, reason, requested_at, decide_by, posted_at)"
        " VALUES (7, 'outreach-email', 's', 'h', 'pending', ?, '2026-11-10T08:00:00+08:00', '2026-11-10T16:30:00+08:00',"
        " '2026-11-10T08:00:05+08:00')",
        (f"Asked for {text}",),  # the page capitalises a reason's first letter, which would hide the marker
    )


def _run_summary(conn, monkeypatch, text):
    conn.execute("INSERT INTO runs (agent, job, started_at, status, summary) VALUES ('social', 'social', '2026-11-10T08:45:00+08:00', 'skipped', ?)", (text,))


def _run_error(conn, monkeypatch, text):
    conn.execute("INSERT INTO runs (agent, job, started_at, status, error) VALUES ('social', 'social', '2026-11-10T08:45:00+08:00', 'failed', ?)", (text,))


def _pause_flag(conn, monkeypatch, text):
    conn.execute("INSERT INTO pause_flags VALUES ('outreach', 1, ?, '2026-11-09T10:00:00+08:00')", (text,))


def _pause_file(conn, monkeypatch, text):
    paths.pause_file().write_text(text)


def _health_line(conn, monkeypatch, text):
    monkeypatch.setattr(plugin("app-factory"), "health", lambda conn: [text])


def _app_prd_today(conn, monkeypatch, text):
    real = plugin("app-factory").digest
    conn.execute("INSERT INTO runs (agent, job, started_at, status) VALUES ('app-factory', 'app-factory', '2026-11-10T08:45:00+08:00', 'ok')")

    def digest(conn, day):
        part = real(conn, day)
        return {**part, "figures": {**part["figures"], "app_prd_today": text}}

    monkeypatch.setattr(plugin("app-factory"), "digest", digest)


ROUTES = {
    "approvals.reason": _approval_reason,
    "runs.summary": _run_summary,
    "runs.error": _run_error,
    "pause_flags.reason": _pause_flag,
    "PAUSE file": _pause_file,
    "a plug-in's health line": _health_line,
    "app_prd_today": _app_prd_today,
}


@pytest.fixture
def seen(monkeypatch):
    """Runs the post, and hands back the spy's page, the saved page and the double's texts."""
    monkeypatch.setenv("JURA_GROWTH_NOW", NINE)
    monkeypatch.setattr(one_pager, "OFFLINE", True)
    # The fake rows here have no real item behind them, and upkeep would supersede them.
    monkeypatch.setattr(cli_mod, "_approval_upkeep", lambda conn, *, post: None)
    pages = []

    def shoot(page, out, width, height, *, chrome, offline=False):
        pages.append(page)
        out = paths.writable(Path(out))
        out.write_bytes(images.PNG_SIGNATURE)
        return out

    monkeypatch.setattr(images, "screenshot", shoot)
    monkeypatch.setattr(images, "measure_height", lambda page, width, *, chrome, offline=False: 1000)

    def post() -> SimpleNamespace:
        result = CliRunner().invoke(cli, ["one-pager"])
        assert result.exit_code == 0, result.output
        (page,) = pages
        saved = (paths.data_dir() / "one-pager" / "picture-2026-11-10.html").read_text(encoding="utf-8")
        assert page == saved, "the page shot is the page saved, which is what stands in for the pixels"
        return SimpleNamespace(page=page, saved=saved)

    return post


@pytest.mark.parametrize("value", VALUES, ids=["resend key", "keychain value", "awkward secret", "named address", "phone", "person", "owner address"])
@pytest.mark.parametrize("route", list(ROUTES))
def test_no_planted_value_reaches_the_page_the_file_or_the_message(route, value, conn, discord_double, d2_secrets, seen, monkeypatch):
    contact_lead(conn)  # masking learns the named contact from the database, as it does live
    ROUTES[route](conn, monkeypatch, f"{sweep.MARKER} {value}")
    found = seen()
    assert sweep.MARKER in found.page, f"{route} never reached the page: the sweep checked nothing"
    double = SimpleNamespace(texts=lambda: [found.page, found.saved, *discord_double.texts()])
    sweep.assert_clean(double, sweep.outbox_dir(), sweep.Planted(secrets=sweep.SECRETS, personal=sweep.PERSONAL))


@pytest.mark.parametrize("route", list(ROUTES))
def test_a_line_naming_the_finance_folder_is_dropped_whole(route, conn, discord_double, d2_secrets, seen, monkeypatch):
    ROUTES[route](conn, monkeypatch, f"{sweep.MARKER} {sweep.FINANCE}")
    found = seen()
    assert sweep.FINANCE not in found.page and sweep.FINANCE not in found.saved
    assert not [text for text in discord_double.texts() if sweep.FINANCE in text]


def test_the_page_is_escaped_as_well_as_masked(conn, discord_double, d2_secrets, seen, monkeypatch):
    _approval_reason(conn, monkeypatch, f"{sweep.MARKER} <img src=x onerror=alert(1)>")
    page = seen().page
    assert "<img" not in page and "&lt;img" in page
