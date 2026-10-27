"""Seam S4: the one-pager's text (MC-08; posting, the PNG and the job are MC-09).

`health.strip(snapshot)` is "Needs you"; `one_pager.text(snapshot)` is the whole
message and `one_pager.messages(snapshot)` its Discord pieces. Snapshots come
from `mission.read()` on temp data, or are built directly for one health item
at a time. The clock is Tue 2026-11-10 08:00 SGT unless a test says otherwise.
"""

from __future__ import annotations

import types
from datetime import datetime

import pytest
from click.testing import CliRunner

import mission_world as world
import sweep
from sweep import d2_secrets  # noqa: F401 - the D2 env file and Keychain double
from jura_growth import cli, discord, health, mission, one_pager, paths, privacy, run_update, schedule, slots
from jura_growth.timeutil import SGT

NOW = datetime(2026, 11, 10, 8, 0, tzinfo=SGT)
SECTIONS = ("Needs you", "Approvals waiting", "Today", "Yesterday", "Ask me")


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", "2026-11-10T08:00:00+08:00")


def snap(**fields) -> mission.Snapshot:
    fields.setdefault("last_one_pager", datetime(2026, 11, 9, 8, 0, tzinfo=SGT))
    fields.setdefault("next_one_pager", datetime(2026, 11, 11, 8, 0, tzinfo=SGT))
    return mission.Snapshot(NOW, fields.pop("db_state", mission.OK), **fields)


def request(number, kind="outreach-email", reading=mission.Reading.WAITING, **fields) -> mission.Request:
    values = dict(
        id=f"A-{number:04d}",
        kind=kind,
        reading=reading,
        requested_at=datetime(2026, 11, 9, 9, number % 60, tzinfo=SGT),
        decide_by=datetime(2026, 11, 10, 16, 30, tzinfo=SGT),
        use_by=None,
        posted=True,
        close_reason=None,
    )
    values.update(fields)
    return mission.Request(**values)


def section(text: str, name: str) -> list[str]:
    lines = text.splitlines()
    start = lines.index(f"**{name}**")
    rest = lines[start + 1 :]
    end = next((i for i, line in enumerate(rest) if line.startswith("**") and line.endswith("**")), len(rest))
    return [line for line in rest[:end] if line.strip()]


# --- the shape (AC-M1.1, text half) -------------------------------------------------


def test_the_header_and_the_sections_come_in_order():
    text = one_pager.text(snap())
    lines = text.splitlines()
    assert lines[0] == "**Tue 10 Nov, as of 08:00 SGT**"
    positions = [lines.index(f"**{name}**") for name in SECTIONS]
    assert positions == sorted(positions)


def test_under_2000_characters_it_is_one_message():
    pieces = one_pager.messages(snap())
    assert len(pieces) == 1 and len(pieces[0]) <= 2000


def test_past_2000_characters_it_splits_at_lines_through_discord_split():
    long = snap(plugin_lines=tuple(f"Build it: APP-{n:03d} is waiting for a builder, approval A-{n:04d}" for n in range(40)))
    text = one_pager.text(long)
    assert 2000 < len(text)
    pieces = one_pager.messages(long)
    assert pieces == discord.split(privacy.for_discord(text))
    assert len(pieces) > 1 and all(len(piece) <= 2000 for piece in pieces)


def test_ask_me_names_the_control_commands():
    assert "`/growth status`" in " ".join(section(one_pager.text(snap()), "Ask me"))
    assert "`/growth approvals`" in " ".join(section(one_pager.text(snap()), "Ask me"))


# --- Needs you (AC-M1.2) --------------------------------------------------------------


def test_nothing_in_the_health_strip_reads_nothing_needs_you():
    assert health.strip(snap()) == []
    assert section(one_pager.text(snap()), "Needs you") == ["Nothing needs you"]


MISSED = slots.SlotStatus("scout-send", datetime(2026, 11, 6, 10, 0, tzinfo=SGT), "missed")
LAPSED_EMAIL = request(412, reading=mission.Reading.LAPSED_UNUSED, use_by=datetime(2026, 11, 10, 7, 59, tzinfo=SGT))

HEALTH_ITEMS = [
    ("PAUSE file", dict(pause_file="holiday"), "The PAUSE file is in place"),
    ("paused agent", dict(paused=(("outreach", "3 failed runs in a row"),)), "`outreach` is paused: 3 failed runs in a row"),
    ("latest run failed", dict(failures=(mission.Failure("community", datetime(2026, 11, 9, 7, 30, tzinfo=SGT), "boom"),)), "`community` failed on Mon 9 Nov, 07:30 SGT"),
    ("missed slot", dict(slots={("scout-send", MISSED.at.date()): [MISSED]}), "`scout-send` missed 1 slot since Fri 6 Nov: Fri 6 Nov, 10:00 SGT."),
    ("undelivered post", dict(undelivered=2), "2 Discord messages since the last one-pager wait in the outbox"),
    ("outbox file", dict(outbox=1), "1 Discord message since the last one-pager waits in the outbox"),
    ("unposted request", dict(approvals=(request(412, posted=False),)), "Not posted to #approvals yet: A-0412"),
    ("approved email lapsed unsent", dict(approvals=(LAPSED_EMAIL,)), "A-0412 (outreach-email) was approved but not used before its use-by, Tue 10 Nov, 07:59 SGT"),
    ("job not installed", dict(installs={"backup": health.NOT_INSTALLED, "social": health.INSTALLED}), "Jobs not installed: backup."),
    ("job out of date", dict(installs={"social": health.OUT_OF_DATE}), "Jobs installed but out of date: social."),
    ("setup gap", dict(gaps=(health.Gap("RESEND_API_KEY_OUTREACH"),)), "`RESEND_API_KEY_OUTREACH`: not set"),
    ("unfinished write", dict(db_state=mission.UNFINISHED_WRITE), "growth.db has an unfinished write. Send `/growth status` to clear it."),
    ("missing growth.db", dict(db_state=mission.MISSING), "growth.db doesn't exist yet"),
    ("not migrated", dict(missing_migrations=("core/0003_approvals.sql",)), "growth.db isn't migrated yet (core/0003_approvals.sql)"),
    ("plug-in line (build handoff)", dict(plugin_lines=("Build it: APP-014 (approval A-0153)",)), "Build it: APP-014 (approval A-0153)"),
    ("broken plug-in", dict(broken=("social (ImportError: x)",)), "A plug-in failed to load: social (ImportError: x)"),
]


@pytest.mark.parametrize("cause, fields, line", HEALTH_ITEMS, ids=[item[0] for item in HEALTH_ITEMS])
def test_each_health_item_appears_when_its_cause_is_planted(cause, fields, line):
    strip = health.strip(snap(**fields))
    assert any(line in item for item in strip), strip
    assert "Nothing needs you" not in section(one_pager.text(snap(**fields)), "Needs you")


def test_a_missed_slot_before_the_previous_business_day_is_not_listed():
    old = slots.SlotStatus("scout-send", datetime(2026, 11, 5, 16, 30, tzinfo=SGT), "missed")  # Thu; Fri 6 Nov is the previous business day
    assert health.strip(snap(slots={("scout-send", old.at.date()): [old]})) == []


def test_missed_slot_times_are_set_apart_by_semicolons_since_each_time_holds_a_comma():
    times = [slots.SlotStatus("scout-send", datetime(2026, 11, 6, 10, minute, tzinfo=SGT), "missed") for minute in (0, 10)]
    [line] = health.strip(snap(slots={("scout-send", times[0].at.date()): times}))
    assert line.endswith("missed 2 slots since Fri 6 Nov: Fri 6 Nov, 10:00 SGT; Fri 6 Nov, 10:10 SGT.")


def test_the_health_items_follow_the_order_in_mc_5_4():
    together = ("unfinished write", "missing growth.db", "outbox file")  # each would replace another item's line
    everything: dict = {"installs": {}}
    for cause, fields, _ in HEALTH_ITEMS:
        if cause not in together:
            everything["installs"].update(fields.get("installs", {}))
            everything.update({k: v for k, v in fields.items() if k != "installs"})
    everything["approvals"] = (request(412, posted=False), LAPSED_EMAIL)
    strip = health.strip(snap(**everything))
    wanted = [line for cause, _, line in HEALTH_ITEMS if cause not in together]
    found = [next(i for i, item in enumerate(strip) if line in item) for line in wanted]
    assert found == sorted(found)


def test_a_failure_shows_its_error_in_a_quote_on_one_line():
    failure = mission.Failure("community", datetime(2026, 11, 9, 7, 30, tzinfo=SGT), "Traceback\n> line two `x`")
    item = health.strip(snap(failures=(failure,)))[0]
    assert item.splitlines()[1] == "> Traceback > line two \\`x\\`"


def test_a_failures_model_written_error_is_escaped_like_a_run_update():
    """Final review Sp2: `runs.error` can be a model's `FAIL:` line, so it gets the run update's
    single-line escaping (MC §4.3): no masked link, no code fence, no mention."""
    error = "FAIL: [approve A-0412 here](https://evil.test/x) ```py\nboom``` @everyone <@111222333444555666>"
    failure = mission.Failure("scout", datetime(2026, 11, 9, 7, 30, tzinfo=SGT), error)
    item = health.strip(snap(failures=(failure,)))[0]
    quoted = item.splitlines()[1]
    assert len(item.splitlines()) == 2 and quoted.startswith("> ")
    assert "](" not in quoted and "]\\(https://evil.test/x)" in quoted
    assert "```" not in quoted.replace("\\`", "") and "\\`\\`\\`py" in quoted
    assert "@everyone" not in quoted and "<@1" not in quoted
    assert quoted[2:] == run_update.untrusted_line(error)


# --- Approvals waiting (AC-M1.3, AC-M1.4, AC-M6.4) -------------------------------------


@pytest.fixture
def five_waiting(conn):
    for number in (101, 102, 103, 104):
        world.approval(conn, number, "outreach-email", requested_at=f"2026-11-09T09:{number - 90:02d}:00+08:00")
    world.approval(conn, 105, "social-post", requested_at="2026-11-09T10:00:00+08:00", decide_by="2026-11-10T18:00:00+08:00")
    return conn


def test_approvals_waiting_counts_by_kind_names_the_oldest_and_what_lapses_first(five_waiting):
    lines = section(one_pager.text(mission.read(world.source())), "Approvals waiting")
    assert lines[0] == "outreach-email 4, social-post 1"
    assert lines[1].startswith("Oldest: A-0101 (outreach-email), waiting since Mon 9 Nov, 09:11 SGT, decide by ")
    assert lines[1].endswith(" SGT")
    lapsing = next(line for line in lines if line.startswith("Lapsing before the next one-pager:"))
    for number in (101, 102, 103, 104, 105):
        assert f"A-0{number}" in lapsing


def test_a_social_post_past_its_decide_by_yesterday_is_not_waiting(conn):
    world.approval(conn, 7, "social-post", requested_at="2026-11-09T07:00:00+08:00", decide_by="2026-11-09T18:00:00+08:00")
    folders = world.watched()
    before = world.stat_snapshot(*folders)
    lines = section(one_pager.text(mission.read(world.source())), "Approvals waiting")
    assert world.stat_snapshot(*folders) == before
    assert lines == ["Nothing waiting"]


def test_approvals_waiting_points_to_the_approvals_channel_with_the_count(five_waiting):
    lines = section(one_pager.text(mission.read(world.source())), "Approvals waiting")
    assert lines[-1] == "Decide in #approvals: 5 waiting for you."


def test_decisions_are_discord_only_so_the_one_pager_never_mentions_terminal(conn):
    world.approval(conn, 153, "outreach-email", status="approved", decided_at="2026-11-09T21:14:00+08:00",
                   decided_origin="terminal", use_by="2026-11-12T16:30:00+08:00")
    world.approval(conn, 154, "outreach-email")
    text = one_pager.text(mission.read(world.source()))
    assert "terminal" not in text.lower()
    assert "Decide in #approvals: 1 waiting for you." in section(text, "Approvals waiting")


def test_without_an_approvals_table_the_section_says_so():
    lines = section(one_pager.text(snap(approvals=None, missing_migrations=("core/0003_approvals.sql",))), "Approvals waiting")
    assert lines == ["Not available: growth.db isn't migrated yet"]


@pytest.mark.parametrize("db_state", [s for s in mission.DB_STATES if s != mission.OK])
def test_the_strip_and_the_sections_word_each_database_state_from_one_map(db_state):
    """Code review 08 ST-3: one map beside the states in mission.py words each one, for the health
    strip and for a section the database can't fill, so a new state can't reach only one of them."""
    assert set(mission.DB_WORDING) == set(mission.DB_STATES) - {mission.OK}
    wording = mission.DB_WORDING[db_state]
    shown = snap(db_state=db_state, db_error="SQLITE_CORRUPT", approvals=None)
    assert health.strip(shown)[0] == wording.strip.format(error="SQLITE_CORRUPT")
    assert section(one_pager.text(shown), "Approvals waiting") == [wording.unavailable]


def test_a_database_state_with_no_wording_fails_loudly_rather_than_reading_as_unmigrated():
    with pytest.raises(KeyError):
        mission.db_problem(snap(db_state="a state added later"))


# --- Today and Yesterday ------------------------------------------------------------------


def test_today_has_one_line_per_job_with_scout_send_and_publish_as_counts(conn, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", "2026-11-10T11:05:00+08:00")
    world.load_fortnight(conn)
    lines = section(one_pager.text(mission.read(world.source("2026-11-10T11:05:00+08:00"))), "Today")
    by_job = {line.split("`")[1]: line for line in lines}
    assert set(by_job) == set(world.fortnight.JOBS)
    assert by_job["app-factory"] == "`app-factory` 06:30 ok"
    assert by_job["scout-research"] == "`scout-research` 09:00 due"
    assert by_job["scout-send"] == "`scout-send` 2 missed, 7 ok, 1 skipped, 33 upcoming"
    assert by_job["publish"].startswith("`publish` 7 ok,")
    assert by_job["community"] == "`community` no slot today"


def test_yesterday_is_the_digest_for_yesterday_and_both_spend_figures(conn):
    from jura_growth import digest

    conn.execute("INSERT INTO runs (agent, job, started_at, status, cost_usd) VALUES ('social', 'social', '2026-11-09T07:00:00+08:00', 'ok', 0.41)")
    conn.execute("INSERT INTO runs (agent, job, started_at, status, cost_usd) VALUES ('social', 'social', '2026-11-10T07:00:00+08:00', 'ok', 0.2)")
    lines = section(one_pager.text(mission.read(world.source())), "Yesterday")
    expected = [f"- {line}" for line in digest.build(conn, "2026-11-09")["lines"]]
    assert lines[: len(expected)] == expected
    assert lines[-1] == "Claude spend: US$0.41 yesterday, US$0.20 so far today"


def test_yesterday_names_no_day_of_its_own(conn):
    """The plug-ins' digest lines say "no run", not "no run today", so
    Yesterday can repeat them word for word (X15; code review 08, S-2)."""
    from jura_growth import digest

    conn.execute("INSERT INTO runs (agent, job, started_at, status, summary) VALUES ('app-factory', 'app-factory', '2026-11-09T06:30:00+08:00', 'skipped', '7 app PRDs waiting')")
    conn.execute("INSERT INTO social_submissions (date, attempt, status, reason, created_at) VALUES ('2026-11-09', 1, 'no-draft', 'no theme', '2026-11-09T07:05:00+08:00')")
    conn.execute("PRAGMA foreign_keys = OFF")  # a queued email without its lead: only the count matters here
    conn.execute(
        "INSERT INTO outreach_messages (lead_id, kind, subject, draft_body, body_text, body_html, send_after, queued_at, status)"
        " VALUES (1, 'first', 's', 'd', 't', 'h', '2026-11-11', '2026-11-09T09:00:00+08:00', 'queued')"
    )
    lines = section(one_pager.text(mission.read(world.source())), "Yesterday")
    assert [line for line in lines if line.startswith("- ")] == [f"- {line}" for line in digest.build(conn, "2026-11-09")["lines"]]
    assert any(line.startswith("- App factory: skipped") for line in lines)
    assert any(line.startswith("- Social: no draft") for line in lines)
    assert any(line.startswith("- Outreach") for line in lines)
    assert not any("today" in line.lower() for line in lines if line.startswith("- ")), lines


# --- the whole read, end to end (AC-M13.1, AC-M3.3, AC-M2.4) --------------------------------


def test_the_one_pager_on_the_fortnight_writes_nothing_and_lists_the_pause_file(conn, tmp_path):
    world.load_fortnight(conn)
    paths.pause_file().write_text("holiday")
    folders = world.watched()
    before = world.stat_snapshot(*folders)
    text = one_pager.text(mission.read(world.source(installed=lambda job: job != "backup")))
    assert world.stat_snapshot(*folders) == before
    needs = section(text, "Needs you")
    assert any("The PAUSE file is in place" in line for line in needs)
    assert any("Jobs not installed: backup." in line for line in needs)


def test_with_a_hot_journal_the_one_pager_says_unfinished_write_and_changes_nothing(conn, tmp_path):
    world.load_fortnight(conn)
    conn.close()
    world.hot_journal(paths.db_path(), tmp_path / "d4")
    folders = world.watched()
    before = world.stat_snapshot(*folders)
    text = one_pager.text(mission.read(world.source()))
    assert world.stat_snapshot(*folders) == before
    assert "- growth.db has an unfinished write. Send `/growth status` to clear it." in section(text, "Needs you")
    assert section(text, "Today") == ["Not available: growth.db has an unfinished write"]


# --- the sweep (AC-M11.1, AC-M12.1 over the one-pager text) -----------------------------------


def test_no_planted_secret_or_personal_data_reaches_the_one_pager(conn, d2_secrets):
    planted = sweep.planted()
    text = planted.text()
    conn.execute("INSERT INTO runs (agent, job, started_at, status, error) VALUES ('social', 'social', '2026-11-10T07:00:00+08:00', 'failed', ?)", (text,))
    conn.execute("INSERT INTO pause_flags VALUES ('outreach', 1, ?, '2026-11-09T10:00:00+08:00')", (text,))
    conn.execute("INSERT INTO runs (agent, job, started_at, status, summary) VALUES ('scout', 'scout-research', '2026-11-10T07:30:00+08:00', 'skipped', ?)", (text,))
    paths.pause_file().write_text(text)
    world.approval(conn, 9, "outreach-email", posted_at=None)
    privacy.remember_address(sweep.NAMED_ADDRESS)
    pieces = one_pager.messages(mission.read(world.source()))
    double = types.SimpleNamespace(texts=lambda: pieces)
    sweep.assert_clean(double, None, planted)


# --- jura-growth one-pager --no-post ------------------------------------------------------------


def test_one_pager_no_post_prints_the_text_and_writes_nothing(conn, monkeypatch):
    monkeypatch.setattr(schedule, "installed", lambda job: True)
    folders = world.watched()
    before = world.stat_snapshot(*folders)
    result = CliRunner().invoke(cli.cli, ["one-pager", "--no-post"])
    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[0] == "**Tue 10 Nov, as of 08:00 SGT**"
    assert world.stat_snapshot(*folders) == before
