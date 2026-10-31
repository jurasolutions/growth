"""Where inbox watch meets `/growth pending`, `/growth help` and the morning picture, from merging main.

Through the seams they are read at: rows in a real database, `/growth pending` and `/growth help` through
`remote`, and `mission.read` then `picture` and `one_pager`. Rows and helpers come from
`test_inbox_replies_waiting.py`, so the items here are the ones R4 is tested on.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import timedelta

import pytest
from click.testing import CliRunner

import approval_world as aw
import picture_world as world
import sweep
from jura_growth import agents, backup, caps, config, digest, discord, headless, one_pager, paths, picture, privacy, remote as remote_mod, runner, slots, timeutil
from jura_growth.agents.inbox import kinds, store
from jura_growth.cli import cli
from jura_growth.origin import Origin
from test_inbox_replies_waiting import HOURS_AGO, card, clock, item, jobs, known_contact, snapshot  # noqa: F401 - fixtures too

WORDS = "We retype every invoice by hand."
WHO = "Priya Nair"
YOU, GROWTH = "Waiting for you", "Growth is on it"
INBOX_COMMANDS = ("inbox list", "inbox redraft", "inbox reword", "inbox draft", "inbox done", "inbox unsuppress")


@pytest.fixture(autouse=True)
def control(monkeypatch):
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", aw.CONTROL_ID)
    config.reset_caches()


def pending(conn) -> str:
    """What Dispatch would post."""
    conn.commit()
    result = CliRunner().invoke(cli, ["remote", "--actor", aw.CONTROL, "--json", "--", "pending"], obj={"origin": Origin.ssh()})
    assert result.exit_code == 0, result.output
    return json.loads(result.output)["text"]


def under(answer: str, heading: str) -> str:
    assert f"**{heading}**" in answer, answer
    return answer.split(f"**{heading}**", 1)[1].split("\n\n", 1)[0]


# --- `/growth pending` ---------------------------------------------------------------------------


def test_a_hand_reply_waits_for_him_with_what_to_send(conn):
    found = item(conn, state=store.NEEDS_HAND_REPLY)
    mine = under(pending(conn), YOU)
    assert store.label(found) in mine
    assert f"`/growth inbox done {store.label(found)}`" in mine


def test_a_promised_reply_comes_first_and_says_he_owes_it(conn):
    item(conn, state=store.NEEDS_HAND_REPLY, name="Someone Else", at=HOURS_AGO[27])
    promised = item(conn, state=store.NEEDS_HAND_REPLY, promised=True, sent_at=HOURS_AGO[3], at=HOURS_AGO[3])
    first = under(pending(conn), YOU).strip().splitlines()[0]
    assert f"**Promised · {store.label(promised)}**" in first
    assert "You owe a personal reply" in first and f"`/growth inbox done {store.label(promised)}`" in first


@pytest.mark.parametrize("state", [store.LAPSED, store.FAILED, store.UNKNOWN, store.UNVERIFIED])
def test_whatever_else_needs_his_hand_says_what_to_send_too(conn, state):
    found = item(conn, state=state)
    assert f"`/growth inbox done {store.label(found)}`" in under(pending(conn), YOU)


def test_an_open_card_is_listed_once_with_what_to_send_and_no_persons_words(conn):
    """The core lists a request, with its A-id and the commands. The plug-in doesn't list it again."""
    card(conn, item(conn, state=store.WAITING, source="enquiry", text=WORDS, thread='{"subject": "x"}'), 412)
    mine = under(pending(conn), YOU)
    assert mine.count("A-0412") == 1
    assert "`/growth approve A-nnnn`" in mine and "`/growth skip A-nnnn`" in mine
    assert WORDS not in mine and WHO not in mine


def test_a_card_lapsed_by_the_clock_is_his_to_answer_by_hand_and_nothing_is_written(conn):
    found = item(conn, state=store.WAITING)
    card(conn, found, 412, decide_by=HOURS_AGO[1])
    mine = under(pending(conn), YOU)
    assert "Lapsed: answer by hand" in mine and store.label(found) in mine
    assert conn.execute("SELECT status FROM approvals").fetchone()[0] == "pending"
    assert conn.execute("SELECT state FROM inbox_items").fetchone()[0] == store.WAITING


@pytest.mark.parametrize("state,words", [(store.NEW, "Being read by triage"), (store.TRIAGED, "Draft ready"), (store.SENDING, "On its way")])
def test_what_is_being_read_or_sent_is_growths(conn, state, words):
    item(conn, state=state)
    answer = pending(conn)
    assert words in under(answer, GROWTH) and words not in under(answer, YOU)


def test_an_approved_card_is_growths(conn):
    card(conn, item(conn, state=store.WAITING), 412, status="approved", decided_at=HOURS_AGO[1])
    assert "Approved: it goes out on the next send" in under(pending(conn), GROWTH)


def test_a_message_needing_nothing_isnt_pending(conn):
    item(conn, state=store.REPORTED)
    assert pending(conn).startswith("Nothing pending")


def test_a_long_list_is_capped_and_says_where_the_rest_are(conn):
    for _ in range(7):
        item(conn, state=store.NEEDS_HAND_REPLY)
    mine = under(pending(conn), YOU)
    assert mine.count("/growth inbox done") == 5
    assert "and 2 more: send `/growth inbox list`" in mine


def test_it_stays_plain_masked_with_no_conversation_class(conn, monkeypatch):
    """B3: a learned name reads `[name removed]` here, though a card shows it. Nothing on this path asks
    for the conversation class, and the words that do reach Discord are masked."""
    known_contact(conn)
    item(conn, state=store.NEEDS_HAND_REPLY, name=sweep.PERSON, text=f"{sweep.PERSON} at {sweep.NAMED_ADDRESS}, {sweep.PHONE}")
    real, asked = privacy.for_discord, []

    def spy(text, *args, **kwargs):
        asked.append(kwargs.get("conversation"))
        return real(text, *args, **kwargs)

    monkeypatch.setattr(privacy, "for_discord", spy)
    answer = pending(conn)
    for value in (sweep.PERSON, sweep.NAMED_ADDRESS, sweep.PHONE):
        assert value not in answer
    assert not any(asked)


def test_it_only_reads(conn):
    item(conn, state=store.NEEDS_HAND_REPLY)
    card(conn, item(conn, state=store.WAITING), 412, decide_by=HOURS_AGO[1])
    before = [tuple(row) for table in ("inbox_items", "approvals") for row in conn.execute(f"SELECT * FROM {table}")]
    pending(conn)
    assert before == [tuple(row) for table in ("inbox_items", "approvals") for row in conn.execute(f"SELECT * FROM {table}")]


def test_a_missing_table_says_so_and_never_nothing_pending(conn):
    conn.execute("DROP TABLE inbox_items")
    answer = pending(conn)
    assert "inbox: its pending work couldn't be read" in answer
    assert "Nothing pending" not in answer


# --- `/growth help` --------------------------------------------------------------------------------


def test_help_names_every_inbox_command_and_still_fits_with_no_cut():
    text = remote_mod.help_text()
    for name in INBOX_COMMANDS:
        assert f"`{name}" in text, name
    assert len(privacy.for_discord(text)) <= remote_mod.TEXT_LIMIT


def test_the_allowlist_stays_sorted_and_every_inbox_command_is_refused_to_a_run():
    names = list(remote_mod.ALLOWLIST)
    assert names == sorted(names)
    assert all(headless.never(name) for name in INBOX_COMMANDS)
    assert headless.never("apps idea")


def test_an_inbox_commands_event_still_keeps_only_its_name_and_id():
    """The merged `_record` writes `_logged`, on the database and the mirror alike: `events` is never pruned."""
    assert remote_mod._logged(["inbox", "reword", "A-0001", "Dear", "Jane"]) == ["inbox", "reword", "A-0001"]
    assert remote_mod._logged(["reword", "Dear", "Jane"]) == ["reword", "Dear"]


def test_a_refused_inbox_command_writes_only_two_words_to_the_mirror_too(conn, monkeypatch):
    seen = []
    monkeypatch.setattr(remote_mod.log, "event", lambda conn, kind, payload, **kw: seen.append(payload))
    reply = remote_mod.Reply(2, "refused", "refused: no")
    remote_mod._record(["reword", "Dear", "Jane"], aw.CONTROL, None, reply, database=False)
    assert seen[0]["words"] == ["reword", "Dear"]


# --- the morning picture -----------------------------------------------------------------------------


def test_replies_waiting_stays_in_the_text_between_needs_you_and_approvals(conn, jobs):
    item(conn, state=store.NEEDS_HAND_REPLY, text=WORDS)
    conn.commit()
    text = one_pager.text(snapshot(jobs))
    assert text.index("**Needs you**") < text.index("**Replies waiting**") < text.index("**Approvals waiting**")
    assert WORDS in text


def test_an_open_card_counts_as_one_to_decide_and_carries_no_words_or_name(conn, jobs):
    number = item(conn, state=store.WAITING, source="enquiry", name=WHO, text=WORDS, cls="question")
    conn.execute(
        "INSERT INTO approvals (id, kind, subject, content_hash, status, reason, requested_at, decide_by, posted_at) "
        "VALUES (412, ?, ?, ?, 'pending', ?, ?, '2026-11-12T10:00:00+08:00', ?)",
        (kinds.KIND, kinds.subject_of(number), f"{412:064x}", kinds.reason_of(store.get(conn, number)), HOURS_AGO[1], HOURS_AGO[1]),
    )
    conn.commit()
    found = snapshot(jobs)
    assert picture.verdict(found).startswith("1 to decide")
    assert "email reply 1" in one_pager.summary(found)
    for surface in (picture.html(found), one_pager.summary(found)):
        assert WORDS not in surface and WHO not in surface and "Priya" not in surface


@pytest.mark.parametrize("promised", [False, True])
def test_what_only_he_can_move_counts_and_carries_no_words_or_name(conn, jobs, promised):
    item(conn, state=store.NEEDS_HAND_REPLY, name=WHO, text=WORDS, promised=promised, sent_at=HOURS_AGO[3] if promised else None)
    conn.commit()
    found = snapshot(jobs)
    assert "1 to answer by hand" in picture.verdict(found)
    assert "Answer by hand: 1. Send `/growth inbox list`." in one_pager.summary(found)
    for surface in (picture.html(found), one_pager.summary(found)):
        assert WORDS not in surface and WHO not in surface and "Priya" not in surface


def test_the_count_is_the_selection_replies_waiting_lists(conn, jobs):
    """An old hand reply that has left the section doesn't hold the verdict for ever: the two can't disagree."""
    old = "2026-10-01T09:00:00+08:00"
    item(conn, state=store.NEEDS_HAND_REPLY, at=old, updated_at=old)
    conn.commit()
    found = snapshot(jobs)
    assert "to answer by hand" not in picture.verdict(found)
    assert "Answer by hand" not in one_pager.summary(found)


def test_the_inbox_row_counts_cards_and_hand_replies_with_many_slots_a_day():
    """It owns the two reply kinds, so a card has a row to show on, like every other kind's."""
    at = world.NOW.replace(hour=7)
    statuses = [slots.SlotStatus("inbox-check", at + timedelta(minutes=15 * n), "ok" if n < 7 else "upcoming", None) for n in range(12)]
    found = world.snap(slots={("inbox-check", world.NOW.date()): statuses}, morning=world.figures(inbox_to_answer=2), yesterday=world.figures(),
                       approvals=(world.request(1, "email-reply", reason="I-0001, question"), world.request(2, "social-reply", reason="I-0002, question")))
    row = next(r for r in picture.agent_rows(found) if r.label == "Inbox")
    assert (row.word, row.detail, row.to_approve) == ("Ran", "2 to answer by hand", 2)


def test_the_inbox_row_claims_nothing_without_a_figure():
    """Quiet, or a digest that failed: it can't tell which, so it doesn't say none."""
    row = next(r for r in picture.agent_rows(world.quiet()) if r.label == "Inbox")
    assert (row.word, row.detail, row.to_approve) == ("Ran", "", 0)


def test_a_cleared_reply_leaves_the_count(conn, jobs):
    found = item(conn, state=store.NEEDS_HAND_REPLY)
    store.mark_done(conn, [store.get(conn, found)])
    conn.commit()
    assert "to answer by hand" not in picture.verdict(snapshot(jobs))


def test_a_quiet_day_adds_no_figure_and_no_words(conn, jobs):
    conn.commit()
    found = snapshot(jobs)
    assert "inbox_to_answer" not in found.morning.figures
    assert "Answer by hand" not in one_pager.summary(found)


def test_a_digest_that_failed_cant_read_as_all_clear(conn, jobs, monkeypatch):
    """Without the figure, a hand reply it couldn't count must not read as nothing to do."""
    module = next(m for m in agents.plugins() if getattr(m, "NAME", "") == "inbox")
    conn.commit()

    def broken(conn, day):
        raise ValueError("no")

    monkeypatch.setattr(module, "digest", broken)
    found = snapshot(jobs)
    assert any(digest.FIGURES_UNAVAILABLE in line for line in found.morning.lines)
    assert picture._some_figure_unread(found)
    assert picture.verdict(found) != "Nothing needs you right now."


def test_a_lock_in_a_section_is_a_lock_not_a_section_that_couldnt_be_read(conn, jobs, monkeypatch):
    """The morning picture's rule: a lock anywhere in the read is the database's state, and the post waits."""
    module = next(m for m in agents.plugins() if getattr(m, "NAME", "") == "inbox")
    conn.commit()

    def locked(conn, since):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(module, "one_pager_section", locked)
    found = snapshot(jobs)
    assert found.db_state != "ok" and found.plugin_sections == ()


def test_a_section_that_breaks_another_way_is_still_one_line(conn, jobs, monkeypatch):
    module = next(m for m in agents.plugins() if getattr(m, "NAME", "") == "inbox")
    conn.commit()

    def broken(conn, since):
        raise ValueError("their words")

    monkeypatch.setattr(module, "one_pager_section", broken)
    found = snapshot(jobs)
    assert found.db_state == "ok"
    assert found.plugin_sections == (("From inbox", ("This section couldn't be read (ValueError).",)),)


# --- what both sides left in the runner and the backup ------------------------------------------------


def test_the_runner_keeps_the_browser_lock_and_the_morning_posts_way_past_a_lock():
    assert runner.POSTS_PAST_A_LOCK == {"one-pager"}
    assert runner.POSTS_PAST_A_LOCK.isdisjoint(caps.BROWSER_JOBS)
    assert caps.BROWSER_JOBS == {"publish", "inbox-watch", "inbox-reply"}
    assert "publish" not in caps.CLEAN_CWD_JOBS and caps.CLEAN_CWD_JOBS == {"inbox-check", "inbox-watch", "inbox-reply"}


def test_the_nightly_backup_does_what_both_sides_gave_it(conn, monkeypatch):
    """Main's pictures and pages, inbox watch's outbox and the plug-ins' retention, in one run."""
    old = "2026-01-01"
    pictures = paths.one_pager_dir()
    pictures.mkdir(parents=True, exist_ok=True)
    gone = [pictures / f"picture-{old}.png", pictures / f"picture-{old}.html", pictures / f"grid-{old}.png"]
    outbox = discord.outbox_dir()
    outbox.mkdir(parents=True, exist_ok=True)
    gone.append(outbox / f"{old}.jsonl")
    kept = pictures / f"picture-{timeutil.today_str()}.png"
    for file in [*gone, kept]:
        file.write_text("x")
    called = []
    module = next(m for m in agents.plugins() if getattr(m, "NAME", "") == "inbox")
    monkeypatch.setattr(module, "retention", lambda conn: called.append(True) or {"removed": 0})

    backup.backup(conn)

    assert called and kept.exists() and not any(file.exists() for file in gone)
    event = json.loads(conn.execute("SELECT payload_json FROM events WHERE kind = 'backup.written'").fetchone()[0])
    assert event["grids_pruned"] == 3 and event["outbox_pruned"] == 1 and event["inbox_retention"] == {"removed": 0}
