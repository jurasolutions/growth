"""Posting the one-pager: the 08:00 job, the command and the remote request (ticket MC-09).

Seams S4 and S5 (the one-pager through the Discord double), S9 (the `one-pager` job through
`runner.run`, in process) and S8 (`jura-growth remote -- one-pager`). The grid is drawn by real
headless Chrome, offline, where a test looks at the PNG; elsewhere `one_pager.render_grid` is a
stub that writes a small valid PNG, so the tests stay quick.

Rows: AC-M1.1 (the PNG on the last piece), AC-M1.5 (the job passes `may_use`), AC-M1.6, AC-M3.7
(no run update), AC-M10.1 (`one-pager` through `remote`; its table row is in test_remote.py),
X12 (the job writes lapses before it builds) and the sweep (AC-M11.1, AC-M12.1).
"""

from __future__ import annotations

import dataclasses
import json
import struct
import zlib
from pathlib import Path

import pytest
from click.testing import CliRunner

import approval_world as aw
import mission_world as world
import sweep
from discord_double import discord_double  # noqa: F401 - a fixture
from sweep import d2_secrets  # noqa: F401 - a fixture
from jura_growth import approvals, cards, config, discord, headless, images, mission, one_pager, paths, privacy, runner
from jura_growth.cli import cli
from jura_growth.origin import Origin

EIGHT_AM = "2026-11-10T08:00:00+08:00"
SECTIONS = ("Needs you", "Approvals waiting", "Today", "Yesterday", "Ask me")
HEADER = "**Tue 10 Nov, as of 08:00 SGT**"
CHROME = images.chrome_path(images.DEFAULT_CHROME)
needs_chrome = pytest.mark.skipif(CHROME is None, reason="Google Chrome is not installed")


def tiny_png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    return images.PNG_SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(b"\x00\x00")) + chunk(b"IEND", b"")


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", EIGHT_AM)
    monkeypatch.setattr(one_pager, "OFFLINE", True)  # Chrome never reaches the network in a test


@pytest.fixture
def stub_grid(monkeypatch):
    """`render_grid` writes a 1×1 PNG where the real one would go, and counts its calls."""
    drawn = []

    def render(snapshot, out, *, chrome, offline=False):
        out = paths.writable(Path(out))
        out.write_bytes(tiny_png())
        drawn.append(out)
        return out

    monkeypatch.setattr(one_pager, "render_grid", render)
    return drawn


def posts(double):
    return double.posts("mission-control")


def section_order(text: str) -> list[int]:
    lines = text.splitlines()
    return [lines.index(f"**{name}**") for name in SECTIONS]


# --- the settings (AC-M1.5, ticket review N8) ----------------------------------------------------


def test_the_one_pager_job_runs_at_08_00_as_the_digest_agent_directly_after_digest():
    jobs = config.settings()["jobs"]
    assert jobs["one-pager"] == {"agent": "digest", "kind": "command", "command": ["one-pager"], "schedule": {"daily": "08:00"}}
    names = list(jobs)
    assert names[names.index("digest") + 1] == "one-pager"
    assert "mission-control" in discord.channels()


def test_the_scheduled_one_pager_may_use_its_own_command():
    assert "one-pager" not in headless.NEVER
    assert headless.may_use("one-pager", "one-pager")


# --- AC-M1.1: the 08:00 job ----------------------------------------------------------------------


@needs_chrome
def test_the_0800_job_posts_one_message_in_order_with_one_png_on_it(conn, discord_double):
    world.load_fortnight(conn)
    outcome = runner.run("one-pager", ignore_schedule=True)
    assert outcome.status == "ok", outcome
    (post,) = posts(discord_double)
    assert post.content.splitlines()[0] == HEADER
    assert section_order(post.content) == sorted(section_order(post.content))
    (name, body), = post.files
    assert name.endswith(".png") and body.startswith(images.PNG_SIGNATURE)
    width, height = struct.unpack(">II", body[16:24])
    assert (width, height) == one_pager.grid_size(mission.read(mission.Source.here()))
    assert outcome.summary == "posted to #mission-control"


def test_past_2000_characters_it_splits_and_the_png_rides_on_the_last_piece_only(conn, discord_double, stub_grid, monkeypatch):
    real = mission.read
    lines = tuple(f"Build it: APP-{n:03d} is waiting for a builder, approval A-{n:04d}" for n in range(40))
    monkeypatch.setattr(mission, "read", lambda source: dataclasses.replace(real(source), plugin_lines=lines))
    result = CliRunner().invoke(cli, ["one-pager"])
    assert result.exit_code == 0, result.output
    pieces = posts(discord_double)
    assert len(pieces) > 1 and all(len(p.content) <= 2000 for p in pieces)
    assert pieces[0].content.splitlines()[0] == HEADER
    assert [len(p.files) for p in pieces] == [0] * (len(pieces) - 1) + [1]
    assert "\n".join(p.content for p in pieces).count("**Ask me**") == 1


def test_the_job_posts_no_run_update(conn, discord_double, stub_grid):
    runner.run("one-pager", ignore_schedule=True)
    assert [c for c in discord_double.contents() if c.startswith("**one-pager** · ")] == []
    assert {r.channel for r in discord_double.posts()} == {"mission-control"}


# --- AC-M1.6: on request, twice in a minute ---------------------------------------------------------


def test_one_pager_twice_posts_twice(conn, discord_double, stub_grid):
    answers = [CliRunner().invoke(cli, ["one-pager"]) for _ in range(2)]
    assert [a.exit_code for a in answers] == [0, 0], [a.output for a in answers]
    assert [a.output.strip() for a in answers] == ["posted to #mission-control"] * 2
    assert len(posts(discord_double)) == 2
    assert posts(discord_double)[0].content == posts(discord_double)[1].content  # dedupe off


def test_remote_one_pager_twice_posts_twice_and_answers_each_time(conn, discord_double, stub_grid, monkeypatch, tmp_path):
    env = tmp_path / "remote.env"
    env.write_text("CONTROL_DISCORD_USER_ID=111\n")
    env.chmod(0o600)
    monkeypatch.setenv("JURA_GROWTH_ENV_FILE", str(env))
    config.reset_caches()
    bodies = []
    for _ in range(2):
        result = CliRunner().invoke(cli, ["remote", "--actor", aw.CONTROL, "--json", "--", "one-pager"], obj={"origin": Origin.ssh()})
        assert result.exit_code == 0, result.output
        bodies.append(json.loads(result.output))
    assert [(b["answer"], b["text"]) for b in bodies] == [("recorded", "posted to #mission-control")] * 2
    assert len(posts(discord_double)) == 2


def test_remote_one_pager_takes_nothing_after_it(conn, discord_double, stub_grid, monkeypatch, tmp_path):
    env = tmp_path / "remote.env"
    env.write_text("CONTROL_DISCORD_USER_ID=111\n")
    env.chmod(0o600)
    monkeypatch.setenv("JURA_GROWTH_ENV_FILE", str(env))
    config.reset_caches()
    result = CliRunner().invoke(cli, ["remote", "--actor", aw.CONTROL, "--", "one-pager", "--no-post"], obj={"origin": Origin.ssh()})
    assert result.exit_code == 2 and result.output.startswith("refused:")
    assert posts(discord_double) == []


# --- when something isn't there --------------------------------------------------------------------


def test_without_a_webhook_the_one_pager_waits_in_the_outbox_and_says_so(conn, stub_grid):
    result = CliRunner().invoke(cli, ["one-pager"])  # JURA_GROWTH_DISCORD=off (conftest)
    assert result.exit_code == 0, result.output
    assert result.output.startswith("not posted to #mission-control: DISCORD_WEBHOOK_MISSION_CONTROL not set")
    saved = [json.loads(line) for line in next(sweep.outbox_dir().glob("*.jsonl")).read_text().splitlines()]
    assert [r["channel"] for r in saved] == ["mission-control"]
    assert saved[0]["content"].startswith(HEADER) and saved[0]["files"][0].endswith(".png")


def test_when_the_grid_cant_be_drawn_the_text_still_posts_and_says_why(conn, discord_double, monkeypatch, tmp_path):
    monkeypatch.setenv("JURA_GROWTH_CHROME", str(tmp_path / "no-chrome"))
    monkeypatch.setattr(images, "DEFAULT_CHROME", str(tmp_path / "no-chrome"))
    result = CliRunner().invoke(cli, ["one-pager"])
    assert result.exit_code == 0, result.output
    (post,) = posts(discord_double)
    assert post.files == []
    assert post.content.splitlines()[-1].startswith("(The 14-day grid couldn't be drawn: Google Chrome not found")
    assert aw.events(conn, "one_pager.grid_failed")


def test_no_post_still_writes_nothing_and_expires_nothing(conn, monkeypatch, stub_grid):
    called = []
    monkeypatch.setattr(approvals, "expire_due", lambda conn, now=None: called.append(1) or [])
    folders = world.watched()
    before = world.stat_snapshot(*folders)
    result = CliRunner().invoke(cli, ["one-pager", "--no-post"])
    assert result.exit_code == 0, result.output
    assert world.stat_snapshot(*folders) == before
    assert called == [] and stub_grid == []


def test_the_grid_is_kept_one_file_a_day(conn, discord_double, stub_grid):
    CliRunner().invoke(cli, ["one-pager"])
    CliRunner().invoke(cli, ["one-pager"])
    assert [p.name for p in stub_grid] == ["grid-2026-11-10.png"] * 2
    assert stub_grid[0].parent == paths.data_dir() / "one-pager"


def test_the_2330_backup_keeps_fourteen_days_of_grids(conn, monkeypatch):
    """Code review 09, S-1: `retention.one_pager_days`, pruned with the backups."""
    assert config.settings()["retention"]["one_pager_days"] == 14
    folder = paths.data_dir() / "one-pager"
    folder.mkdir(parents=True)
    for day in range(1, 21):
        (folder / f"grid-2026-10-{day:02d}.png").write_bytes(tiny_png())
    (folder / "notes.txt").write_text("not a grid")
    monkeypatch.setenv("JURA_GROWTH_NOW", "2026-10-24T23:30:00+08:00")
    result = CliRunner().invoke(cli, ["backup"])
    assert result.exit_code == 0, result.output
    names = sorted(f.name for f in folder.iterdir())
    assert names == [f"grid-2026-10-{day:02d}.png" for day in range(11, 21)] + ["notes.txt"]  # 11 Oct to 24 Oct is 14 days
    (written,) = aw.events(conn, "backup.written")
    assert written["grids_pruned"] == 10


# --- X12: the job writes the day's lapses before it builds -----------------------------------------


@pytest.fixture
def lapsed(conn, monkeypatch, discord_double):
    """A fake-kind request with its card posted, and the clock at its decide-by, with nothing
    written since: the one-pager job is the first writer to run."""
    fake = aw.install(monkeypatch)
    aw.prepare(conn)
    aw.at(monkeypatch, aw.NOW)
    approval = aw.request(conn, aw.KIND, fake.item())
    cards.sweep(conn)
    aw.at(monkeypatch, approval.decide_by)
    assert aw.record(conn, approval.id)["status"] == "pending"
    return fake, approval


def test_the_job_writes_the_lapse_on_its_writable_connection_before_the_read_model_runs(conn, lapsed, monkeypatch,
                                                                                        discord_double, stub_grid):
    fake, approval = lapsed
    order = []
    real_expire, real_read = approvals.expire_due, mission.read

    def expire(c, now=None):
        c.execute("SELECT 1").fetchone()
        assert not c.execute("PRAGMA query_only").fetchone()[0]  # the writable connection
        order.append("expire_due")
        return real_expire(c, now)

    def read(source):
        order.append("read")
        assert aw.record(conn, approval.id)["status"] == "expired"  # committed before the read
        return real_read(source)

    monkeypatch.setattr(approvals, "expire_due", expire)
    monkeypatch.setattr(mission, "read", read)
    outcome = runner.run("one-pager", ignore_schedule=True)
    assert outcome.status == "ok", outcome
    assert order == ["expire_due", "read"]
    assert len(fake.ran("on_expire", approval.subject)) == 1
    (patch,) = [r for r in discord_double.requests if r.method == "PATCH"]  # the lapsed card is edited
    assert "Expired: not approved in time" in patch.content.splitlines()[0]


def test_the_one_pager_posts_no_new_card(conn, monkeypatch, discord_double, stub_grid):
    """A new card notifies; the heartbeat and the raising commands post them (X12), and the
    one-pager lists one that is still unposted."""
    fake = aw.install(monkeypatch)
    aw.prepare(conn)
    aw.at(monkeypatch, EIGHT_AM)
    approval = aw.request(conn, aw.KIND, fake.item())
    CliRunner().invoke(cli, ["one-pager"])
    assert discord_double.posts("approvals") == []
    assert f"Not posted to #approvals yet: {approval.id}" in posts(discord_double)[0].content


def test_a_failing_expiry_never_stops_the_one_pager(conn, monkeypatch, discord_double, stub_grid):
    monkeypatch.setattr(approvals, "expire_due", lambda conn, now=None: (_ for _ in ()).throw(RuntimeError("expiry broke")))
    result = CliRunner().invoke(cli, ["one-pager"])
    assert result.exit_code == 0, result.output
    assert len(posts(discord_double)) == 1
    assert "expiry broke" in aw.events(conn, "approval.upkeep_error")[0]["error"]


# --- the sweep (AC-M11.1, AC-M12.1) over the posted one-pager, its pieces and the PNG ----------------


def _plant(conn, planted) -> None:
    text = planted.text()
    conn.execute("INSERT INTO runs (agent, job, started_at, status, error) VALUES ('social', 'social', '2026-11-10T07:00:00+08:00', 'failed', ?)", (text,))
    conn.execute("INSERT INTO pause_flags VALUES ('outreach', 1, ?, '2026-11-09T10:00:00+08:00')", (text,))
    conn.execute("INSERT INTO runs (agent, job, started_at, status, summary) VALUES ('scout', 'scout-research', '2026-11-10T07:30:00+08:00', 'skipped', ?)", (text,))
    paths.pause_file().write_text(text)
    privacy.remember_address(sweep.NAMED_ADDRESS)


@needs_chrome
def test_no_planted_secret_or_personal_data_reaches_the_posted_one_pager(conn, discord_double, d2_secrets):
    planted = sweep.planted()
    world.load_fortnight(conn)
    _plant(conn, planted)
    result = CliRunner().invoke(cli, ["one-pager"])
    assert result.exit_code == 0, result.output
    assert posts(discord_double)[-1].files, "the PNG went with it"
    sweep.assert_clean(discord_double, sweep.outbox_dir(), planted)


def test_no_planted_value_reaches_the_split_pieces_or_the_outbox(conn, discord_double, d2_secrets, stub_grid, monkeypatch):
    planted = sweep.planted()
    _plant(conn, planted)
    real = mission.read
    long = tuple(f"Build it: APP-{n:03d} is waiting for a builder" for n in range(45))
    monkeypatch.setattr(mission, "read", lambda source: dataclasses.replace(real(source), plugin_lines=long))
    CliRunner().invoke(cli, ["one-pager"])
    assert len(posts(discord_double)) > 1
    discord_double.mode = "500"  # this one falls back to the outbox
    CliRunner().invoke(cli, ["one-pager"])
    assert list(sweep.outbox_dir().glob("*.jsonl"))
    sweep.assert_clean(discord_double, sweep.outbox_dir(), planted)
