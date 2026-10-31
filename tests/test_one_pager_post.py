"""Posting the one-pager: the job, the command and the remote request (ticket MC-09).

Seams S4 and S5 (the one-pager through the Discord double), S9 (the `one-pager` job through
`runner.run`, in process) and S8 (`jura-growth remote -- one-pager`). The picture is drawn by real
headless Chrome, offline, where a test looks at the PNG; elsewhere `picture.render` and
`one_pager.render_grid` are stubs that write a small valid PNG, so the tests stay quick.

Rows: MB1 (one message with one PNG), MB9, MB10, MB11, MB12, AC-M1.5 (the job passes `may_use`),
AC-M1.6, AC-M3.7 (no run update), AC-M10.1 (`one-pager` through `remote`; its table row is in
test_remote.py), X12 (the job writes lapses before it builds) and the sweep (AC-M11.1, AC-M12.1).
"""

from __future__ import annotations

import dataclasses
import json
import sqlite3
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
from jura_growth import approvals, backup, cards, config, db, discord, headless, images, log, mission, one_pager, paths, picture, privacy, runner
from jura_growth.cli import cli
from jura_growth.origin import Origin
from jura_growth import pause as pause_module, timeutil

EIGHT_AM = "2026-11-10T08:00:00+08:00"
NINE = "2026-11-10T09:00:00+08:00"
SECTIONS = ("Needs you", "Approvals waiting", "Today", "Yesterday", "Ask me")
HEADER = "**Tue 10 Nov, as of 08:00 SGT**"
CHROME = images.chrome_path(images.DEFAULT_CHROME)
needs_chrome = pytest.mark.skipif(CHROME is None, reason="Google Chrome is not installed")


def one_pager_now():
    return timeutil.parse(NINE)


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
    """`picture.render` and `render_grid` write a 1×1 PNG where the real one would go, and count their calls."""
    drawn = []

    def render(snapshot, out, *, chrome, offline=False):
        out = paths.writable(Path(out))
        out.write_bytes(tiny_png())
        drawn.append(out)
        return out

    monkeypatch.setattr(one_pager, "render_grid", render)
    monkeypatch.setattr(picture, "render", render)
    return drawn


@pytest.fixture
def no_picture(monkeypatch):
    """The picture can't be drawn, so the long text goes out."""
    def refuse(snapshot, out, *, chrome, offline=False):
        raise images.RenderError("no picture in this test")

    monkeypatch.setattr(picture, "render", refuse)


def posts(double):
    return double.posts("mission-control")


def section_order(text: str) -> list[int]:
    lines = text.splitlines()
    return [lines.index(f"**{name}**") for name in SECTIONS]


# --- the settings (AC-M1.5, ticket review N8) ----------------------------------------------------


def test_the_one_pager_job_runs_at_09_00_as_the_digest_agent_directly_after_digest():
    jobs = config.settings()["jobs"]
    assert jobs["one-pager"] == {"agent": "digest", "kind": "command", "command": ["one-pager"], "schedule": {"daily": "09:00"}}
    names = list(jobs)
    assert names[names.index("digest") + 1] == "one-pager"
    assert "mission-control" in discord.channels()


def test_the_scheduled_one_pager_may_use_its_own_command():
    assert "one-pager" not in headless.NEVER
    assert headless.may_use("one-pager", "one-pager")


# --- MB1, MB10: one message with one picture ---------------------------------------------------------


@needs_chrome
def test_the_job_posts_one_message_with_the_picture_on_it(conn, discord_double):
    world.load_fortnight(conn)
    outcome = runner.run("one-pager", ignore_schedule=True)
    assert outcome.status == "ok", outcome
    (post,) = posts(discord_double)
    assert post.content.splitlines()[0] == HEADER
    assert post.content.splitlines()[1] == picture.verdict(mission.read(mission.Source.here()))
    assert "**Needs you**" not in post.content
    (name, body), = post.files
    assert name == "picture-2026-11-10.png" and body.startswith(images.PNG_SIGNATURE)
    width, height = struct.unpack(">II", body[16:24])
    assert width == 1200 and 400 < height <= picture.MAX_HEIGHT
    assert outcome.summary == "posted to #mission-control"


def test_however_much_there_is_the_picture_and_its_message_stay_one_post(conn, discord_double, stub_grid, monkeypatch):
    real = mission.read
    lines = tuple(f"Build it: APP-{n:03d} is waiting for a builder, approval A-{n:04d} " + "x" * 400 for n in range(40))
    monkeypatch.setattr(mission, "read", lambda source: dataclasses.replace(real(source), plugin_lines=lines))
    result = CliRunner().invoke(cli, ["one-pager"])
    assert result.exit_code == 0, result.output
    (post,) = posts(discord_double)
    assert len(post.content) <= 2000 and len(post.files) == 1


def test_past_2000_characters_the_long_text_splits_with_no_picture(conn, discord_double, no_picture, monkeypatch):
    real = mission.read
    lines = tuple(f"Build it: APP-{n:03d} is waiting for a builder, approval A-{n:04d}" for n in range(40))
    monkeypatch.setattr(mission, "read", lambda source: dataclasses.replace(real(source), plugin_lines=lines))
    result = CliRunner().invoke(cli, ["one-pager"])
    assert result.exit_code == 0, result.output
    pieces = posts(discord_double)
    assert len(pieces) > 1 and all(len(p.content) <= 2000 for p in pieces)
    assert pieces[0].content.splitlines()[0] == HEADER
    assert all(p.files == [] for p in pieces)
    assert "\n".join(p.content for p in pieces).count("**Ask me**") == 1


def test_the_post_path_waits_for_a_held_lock_before_it_draws(conn, discord_double, stub_grid, monkeypatch):
    """S4: the one-pager shares its minute with publish's first slot."""
    real, patient = mission.read, mission.read_patiently
    answers = [mission.UNFINISHED_WRITE, mission.OK]
    slept = []
    monkeypatch.setattr(mission, "read", lambda source: dataclasses.replace(real(source), db_state=answers.pop(0)))
    monkeypatch.setattr(mission, "read_patiently", lambda source: patient(source, sleep=slept.append))
    result = CliRunner().invoke(cli, ["one-pager"])
    assert result.exit_code == 0, result.output
    assert slept == [mission.LOCK_RETRY] and answers == []
    assert "unfinished write" not in posts(discord_double)[0].content


def test_no_post_and_grid_dont_wait_for_a_lock(conn, stub_grid, monkeypatch):
    monkeypatch.setattr(mission, "read_patiently", lambda source: pytest.fail("this path waited"))
    assert CliRunner().invoke(cli, ["one-pager", "--no-post"]).exit_code == 0
    assert CliRunner().invoke(cli, ["one-pager", "--grid"]).exit_code == 0


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


def _assert_the_long_text_went_out(conn, double, why: str) -> None:
    (post,) = posts(double)
    assert post.files == []
    assert section_order(post.content) == sorted(section_order(post.content))
    assert post.content.splitlines()[-1].startswith(f"(The picture couldn't be drawn: {why}")
    assert aw.events(conn, "one_pager.picture_failed")


def test_when_the_picture_cant_be_drawn_the_long_text_posts_and_says_why(conn, discord_double, monkeypatch, tmp_path):
    monkeypatch.setenv("JURA_GROWTH_CHROME", str(tmp_path / "no-chrome"))
    monkeypatch.setattr(images, "DEFAULT_CHROME", str(tmp_path / "no-chrome"))
    result = CliRunner().invoke(cli, ["one-pager"])
    assert result.exit_code == 0, result.output
    _assert_the_long_text_went_out(conn, discord_double, "Google Chrome not found")


def test_when_the_page_cant_be_saved_the_long_text_posts_and_says_why(conn, discord_double, stub_grid, monkeypatch):
    real = paths.writable

    def refuse(path):
        if Path(path).suffix == ".html":
            raise OSError("the folder is read-only")
        return real(path)

    monkeypatch.setattr(paths, "writable", refuse)
    assert CliRunner().invoke(cli, ["one-pager"]).exit_code == 0
    _assert_the_long_text_went_out(conn, discord_double, "OSError: the folder is read-only")


@needs_chrome
def test_a_picture_over_the_maximum_sends_the_long_text_and_is_never_clipped(conn, discord_double, monkeypatch):
    monkeypatch.setattr(picture, "MAX_HEIGHT", 300)
    assert CliRunner().invoke(cli, ["one-pager"]).exit_code == 0
    _assert_the_long_text_went_out(conn, discord_double, "the picture would be")
    assert not list((paths.data_dir() / "one-pager").glob("picture-*.png"))


@needs_chrome
def test_the_page_is_saved_beside_the_picture(conn, discord_double):
    """MB9: to open on the Mac. The page holds no script, and the PNG is the one that went."""
    assert CliRunner().invoke(cli, ["one-pager"]).exit_code == 0
    folder = paths.data_dir() / "one-pager"
    assert sorted(f.name for f in folder.iterdir()) == ["picture-2026-11-10.html", "picture-2026-11-10.png"]
    page = (folder / "picture-2026-11-10.html").read_text(encoding="utf-8")
    assert "<script" not in page and "Decide in #approvals" in page
    (_, body), = posts(discord_double)[0].files
    assert body == images.pixels_only((folder / "picture-2026-11-10.png").read_bytes())


# --- MB12: the grid is drawn on request, never posted ---------------------------------------------


def test_grid_draws_its_file_prints_its_path_and_posts_nothing(conn, discord_double, stub_grid):
    result = CliRunner().invoke(cli, ["one-pager", "--grid"])
    assert result.exit_code == 0, result.output
    path = paths.data_dir() / "one-pager" / "grid-2026-11-10.png"
    assert result.output.strip() == str(path) and path.exists()
    assert discord_double.requests == []


def test_grid_says_so_when_it_cant_be_drawn(conn, discord_double, monkeypatch, tmp_path):
    monkeypatch.setenv("JURA_GROWTH_CHROME", str(tmp_path / "no-chrome"))
    monkeypatch.setattr(images, "DEFAULT_CHROME", str(tmp_path / "no-chrome"))
    result = CliRunner().invoke(cli, ["one-pager", "--grid"])
    assert result.output.startswith("The grid couldn't be drawn: Google Chrome not found")
    assert discord_double.requests == []


def test_a_normal_post_writes_no_grid(conn, discord_double, stub_grid):
    assert CliRunner().invoke(cli, ["one-pager"]).exit_code == 0
    assert not list((paths.data_dir() / "one-pager").glob("grid-*"))


def test_no_post_still_writes_nothing_and_expires_nothing(conn, monkeypatch, stub_grid):
    called = []
    monkeypatch.setattr(approvals, "expire_due", lambda conn, now=None: called.append(1) or [])
    folders = world.watched()
    before = world.stat_snapshot(*folders)
    result = CliRunner().invoke(cli, ["one-pager", "--no-post"])
    assert result.exit_code == 0, result.output
    assert world.stat_snapshot(*folders) == before
    assert called == [] and stub_grid == []


def test_the_picture_is_kept_one_file_a_day(conn, discord_double, stub_grid):
    CliRunner().invoke(cli, ["one-pager"])
    CliRunner().invoke(cli, ["one-pager"])
    assert [p.name for p in stub_grid] == ["picture-2026-11-10.png"] * 2
    assert stub_grid[0].parent == paths.data_dir() / "one-pager"


def test_the_2330_backup_keeps_fourteen_days_of_pictures_pages_and_grids(conn, monkeypatch):
    """Code review 09, S-1, and T-B4: `retention.one_pager_days`, pruned with the backups. A
    page holds approval reasons as text, so it mustn't outlive them."""
    assert config.settings()["retention"]["one_pager_days"] == 14
    folder = paths.data_dir() / "one-pager"
    folder.mkdir(parents=True)
    for day in range(1, 21):
        (folder / f"grid-2026-10-{day:02d}.png").write_bytes(tiny_png())
        (folder / f"picture-2026-10-{day:02d}.png").write_bytes(tiny_png())
        (folder / f"picture-2026-10-{day:02d}.html").write_text("<p>a page</p>")
    kept_others = ["grid-notes.png", "notes.txt", "picture-final.html", "picture-2026-13-99.png", "picture-2026-10-01.txt"]
    for name in kept_others:
        (folder / name).write_text("not one of the dated files")
    monkeypatch.setenv("JURA_GROWTH_NOW", "2026-10-24T23:30:00+08:00")
    result = CliRunner().invoke(cli, ["backup"])
    assert result.exit_code == 0, result.output
    names = sorted(f.name for f in folder.iterdir())
    kept = [f"{stem}-2026-10-{day:02d}.{ext}" for day in range(11, 21)  # 11 Oct to 24 Oct is 14 days
            for stem, ext in (("grid", "png"), ("picture", "png"), ("picture", "html"))]
    assert names == sorted(kept + kept_others)
    (written,) = aw.events(conn, "backup.written")
    assert written["grids_pruned"] == 30


def test_pruning_with_no_folder_removes_nothing():
    assert backup.prune_pictures() == 0


# --- issue 03: a long lock never ends in nothing -----------------------------------------------------


def locked(*args, **kwargs):
    """What `db.connect` raises once a writer has held growth.db past its wait."""
    raise sqlite3.OperationalError("database is locked")


@pytest.fixture
def post_path(conn, discord_double, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", NINE)
    monkeypatch.setattr(mission, "read_patiently", lambda source: mission.read(source))  # no real waiting
    return discord_double


def test_the_command_gets_the_morning_post_out_past_the_write_connections_wait(post_path, monkeypatch):
    monkeypatch.setattr(db, "connect", locked)
    result = CliRunner().invoke(cli, ["one-pager"])
    assert result.exception is None, repr(result.exception)
    assert len(post_path.posts("mission-control")) == 1


def test_the_job_gets_the_morning_post_out_past_the_write_connections_wait(post_path, monkeypatch):
    monkeypatch.setattr(db, "connect", locked)
    runner.run("one-pager", ignore_schedule=True)
    assert len(post_path.posts("mission-control")) == 1


def test_a_lock_after_delivery_doesnt_report_a_post_that_went_out_as_failed(post_path, monkeypatch):
    monkeypatch.setattr(discord, "_record", locked)
    result = CliRunner().invoke(cli, ["one-pager"])
    assert len(post_path.posts("mission-control")) == 1
    assert result.exception is None, repr(result.exception)


@pytest.fixture
def hold(conn, monkeypatch):
    """A real lock from a second connection, as issue 03's steps do. Only the waits are shortened,
    because no test can spend them."""
    monkeypatch.setenv("JURA_GROWTH_NOW", NINE)
    monkeypatch.setattr(db, "BUSY_SECONDS", 0.05)
    monkeypatch.setattr(db, "SHORT_WAIT", 0.05)
    monkeypatch.setattr(mission, "BUSY_TIMEOUT", 0.01)
    monkeypatch.setattr(mission, "LOCK_PATIENCE", 0.03)
    monkeypatch.setattr(mission, "LOCK_RETRY", 0.01)
    holders = []

    def begin(kind: str) -> None:
        holder = sqlite3.connect(paths.db_path(), isolation_level=None)
        holder.execute(f"BEGIN {kind}")
        holders.append(holder)

    yield begin
    for holder in holders:
        if holder.in_transaction:
            holder.execute("ROLLBACK")
        holder.close()


def mirrored_on(now: str, kind: str) -> list[dict]:
    path = paths.data_dir() / "runs" / f"{now[:10]}.jsonl"
    return [line for line in map(json.loads, path.read_text().splitlines()) if line["kind"] == kind]


def mirrored(kind: str) -> list[dict]:
    return mirrored_on(NINE, kind)


LOCKS = ["EXCLUSIVE", "IMMEDIATE"]


@needs_chrome
@pytest.mark.parametrize("kind", LOCKS)
def test_the_job_posts_through_a_real_lock_held_throughout(kind, hold, discord_double, monkeypatch):
    hold(kind)
    outcome = runner.run("one-pager", ignore_schedule=True)
    assert (outcome.status, outcome.summary) == ("ok", "posted to #mission-control")
    (post,) = posts(discord_double)
    (name, body), = post.files
    assert name == "picture-2026-11-10.png" and body.startswith(images.PNG_SIGNATURE)
    assert post.content.splitlines()[0] == "**Tue 10 Nov, as of 09:00 SGT**"
    if kind == "EXCLUSIVE":  # nothing can be read, so this is the bad-day picture, and it says why
        assert "unfinished write" in post.content
        assert mirrored("one_pager.upkeep_skipped")
    assert mirrored("run.database_locked")[0]["payload"]["job"] == "one-pager"


def test_a_job_that_posted_through_the_lock_still_reads_as_run(hold, discord_double, stub_grid):
    hold("EXCLUSIVE")
    runner.run("one-pager", ignore_schedule=True)
    assert [line["payload"]["job"] for line in mirrored("run.quiet")] == ["one-pager"]


@pytest.mark.parametrize("kind", LOCKS)
def test_the_command_posts_through_a_real_lock_and_says_so(kind, hold, discord_double, stub_grid):
    hold(kind)
    result = CliRunner().invoke(cli, ["one-pager"])
    assert result.exception is None, repr(result.exception)
    assert result.output.strip().splitlines()[-1] == "posted to #mission-control"
    assert len(posts(discord_double)) == 1


def test_dispatchs_path_answers_through_a_real_lock(hold, discord_double, stub_grid, monkeypatch, tmp_path):
    env = tmp_path / "remote.env"
    env.write_text("CONTROL_DISCORD_USER_ID=111\n")
    env.chmod(0o600)
    monkeypatch.setenv("JURA_GROWTH_ENV_FILE", str(env))
    config.reset_caches()
    hold("EXCLUSIVE")
    result = CliRunner().invoke(cli, ["remote", "--actor", aw.CONTROL, "--json", "--", "one-pager"], obj={"origin": Origin.ssh()})
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert (body["answer"], body["text"]) == ("recorded", "posted to #mission-control")
    assert len(posts(discord_double)) == 1
    assert mirrored("remote.command")[0]["payload"]["words"] == ["one-pager"]  # the audit line isn't lost


def test_nothing_on_dispatchs_path_takes_the_long_wait(hold, discord_double, stub_grid, monkeypatch, tmp_path):
    """Thirty seconds on any one of these connections would go past Dispatch's 60."""
    env = tmp_path / "remote.env"
    env.write_text("CONTROL_DISCORD_USER_ID=111\n")
    env.chmod(0o600)
    monkeypatch.setenv("JURA_GROWTH_ENV_FILE", str(env))
    config.reset_caches()
    waits = []

    def connect(path=None, *, migrate_now=True, wait=None):
        waits.append(wait)
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(db, "connect", connect)
    result = CliRunner().invoke(cli, ["remote", "--actor", aw.CONTROL, "--json", "--", "one-pager"], obj={"origin": Origin.ssh()})
    assert result.exit_code == 0, result.output
    assert len(waits) >= 4 and set(waits) == {db.SHORT_WAIT}, waits


def test_other_remote_commands_keep_the_long_wait(conn, monkeypatch, tmp_path):
    env = tmp_path / "remote.env"
    env.write_text("CONTROL_DISCORD_USER_ID=111\n")
    env.chmod(0o600)
    monkeypatch.setenv("JURA_GROWTH_ENV_FILE", str(env))
    config.reset_caches()
    waits = []
    real = db.connect

    def connect(path=None, *, migrate_now=True, wait=None):
        waits.append(wait)
        return real(path, migrate_now=migrate_now, wait=wait)

    monkeypatch.setattr(db, "connect", connect)
    assert CliRunner().invoke(cli, ["remote", "--actor", aw.CONTROL, "--", "status"], obj={"origin": Origin.ssh()}).exit_code == 0
    assert waits and set(waits) == {None}


def test_a_lock_landing_after_the_post_never_posts_twice(hold, discord_double, stub_grid, monkeypatch):
    """Delivered, then the lock: the run's row can't be finished, and that mustn't re-run the job."""
    real = log.finish_run

    def finish(conn, *args, **kwargs):
        hold("EXCLUSIVE")
        return real(conn, *args, **kwargs)

    monkeypatch.setattr(log, "finish_run", finish)
    outcome = runner.run("one-pager", ignore_schedule=True)
    assert outcome.status == "ok"
    assert len(posts(discord_double)) == 1
    assert mirrored("run.database_locked")


def test_when_even_the_post_is_impossible_the_failure_leaves_a_clear_trace(hold, discord_double, stub_grid, monkeypatch):
    hold("EXCLUSIVE")
    monkeypatch.setattr(one_pager, "post", lambda conn, snapshot: (_ for _ in ()).throw(RuntimeError("the disk is full")))
    outcome = runner.run("one-pager", ignore_schedule=True)
    assert outcome.status == "failed" and "the disk is full" in outcome.error
    assert "the disk is full" in mirrored("one_pager.not_posted")[0]["payload"]["error"]
    assert "the disk is full" in mirrored("run.database_locked")[0]["payload"]["error"]
    assert [p for p in discord_double.posts("alerts") if "the disk is full" in p.content]


def test_the_command_reports_a_post_that_failed_rather_than_hiding_it(hold, discord_double, stub_grid, monkeypatch):
    hold("EXCLUSIVE")
    monkeypatch.setattr(one_pager, "post", lambda conn, snapshot: (_ for _ in ()).throw(RuntimeError("the disk is full")))
    result = CliRunner().invoke(cli, ["one-pager"])
    assert result.exit_code != 0
    assert mirrored("one_pager.not_posted")


def test_a_delivered_post_with_a_real_lock_on_its_record_keeps_a_trace(hold, discord_double, stub_grid, monkeypatch):
    real = discord._record

    def record(conn, *args, **kwargs):
        hold("EXCLUSIVE")
        return real(conn, *args, **kwargs)

    monkeypatch.setattr(discord, "_record", record)
    result = CliRunner().invoke(cli, ["one-pager"])
    assert result.exception is None, repr(result.exception)
    assert result.output.strip().splitlines()[-1] == "posted to #mission-control"
    assert mirrored("discord.post")[0]["payload"]["not_recorded"]


def test_a_paused_job_read_under_a_lock_stays_skipped_and_posts_nothing(conn, hold, discord_double, stub_grid):
    """A pause is the kill switch. Under a write lock the flag can still be read, and the job must
    obey it even though the skip can't be written. An EXCLUSIVE lock hides the flag: that post goes
    to his own channel and the PAUSE file still stops it, a trade recorded in the crew log."""
    pause_module.pause(conn, "digest", "held by hand", notify=False)
    conn.commit()
    hold("IMMEDIATE")
    outcome = runner.run("one-pager", ignore_schedule=True)
    assert outcome.status == "skipped" and "held by hand" in outcome.summary
    assert posts(discord_double) == []
    assert mirrored("run.quiet") == []


def test_other_jobs_still_stop_at_a_lock(hold):
    """Only the morning post runs without its database. Nothing else may."""
    hold("EXCLUSIVE")
    with pytest.raises(sqlite3.OperationalError):
        runner.run("backup", ignore_schedule=True)


def test_a_non_lock_error_isnt_taken_for_a_lock(conn, discord_double, stub_grid, monkeypatch):
    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(db, "connect", broken)
    assert CliRunner().invoke(cli, ["one-pager"]).exception is not None
    assert posts(discord_double) == []


def test_a_non_lock_error_at_the_post_isnt_taken_for_a_lock(conn, discord_double, stub_grid, monkeypatch):
    real, calls = db.connect, []

    def connect(*args, **kwargs):
        calls.append(1)
        if len(calls) > 1:  # the upkeep's is fine; the post's isn't
            raise sqlite3.OperationalError("disk I/O error")
        return real(*args, **kwargs)

    monkeypatch.setattr(db, "connect", connect)
    assert CliRunner().invoke(cli, ["one-pager"]).exception is not None
    assert posts(discord_double) == []
    assert "disk I/O error" in mirrored_on(EIGHT_AM, "one_pager.not_posted")[0]["payload"]["error"]


def test_ordinary_connections_keep_their_long_wait():
    assert db.BUSY_SECONDS == 30


def test_the_whole_wait_stays_inside_dispatchs_window(monkeypatch):
    """Dispatch runs `/growth one-pager` with a 60-second timeout, and one-pagers aren't deduplicated:
    a post that goes out after Dispatch has reported a failure gets asked for again. In the worst
    case every connection waits its turn: the upkeep, the read's retries, the post, and the masking
    and the audit line in `remote`."""
    slept = []
    reads = []
    locked_out = mission.Snapshot(one_pager_now(), mission.UNFINISHED_WRITE)
    monkeypatch.setattr(mission, "read", lambda source: reads.append(1) or locked_out)
    mission.read_patiently(None, sleep=slept.append)
    reading = sum(slept) + len(reads) * mission.BUSY_TIMEOUT
    connections = 4 * db.SHORT_WAIT
    drawing_and_posting = 6  # two Chrome runs at about a second each under load, and the upload
    assert reading + connections + drawing_and_posting < 60


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


def test_no_planted_value_reaches_the_split_pieces_or_the_outbox(conn, discord_double, d2_secrets, no_picture, monkeypatch):
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
