"""Text is removed 90 days after an item closes (PRD §4; ticket 04: technical N6, functional N7).

"Closes" is defined per state in `inbox/text_retention.py`, and removal has to reach every place the words
land: the row, the card's `first_piece`, the Discord outbox, and tonight's backup copy.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import timedelta

import pytest

from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import backup, cards, db, discord, timeutil
from jura_growth.agents.inbox import kinds, store
from jura_growth.agents.inbox import one_pager as inbox_one_pager
from jura_growth.agents.inbox import text_retention as retention

NOW = "2026-11-30T23:30:00+08:00"
WORDS = "PRIVATE-WORDS my son has diabetes"
_serial = {"n": 0}


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", NOW)


def days_ago(days: float) -> str:
    return timeutil.stamp(timeutil.now_sgt() - timedelta(days=days))


def item(conn, state: str, *, age: float = 100, promised=False, sent_days=None, reported_days="same", source="email", thread=None,
         closed_days=None) -> int:
    """An item whose every stamp is `age` days old unless named."""
    _serial["n"] += 1
    stamp = days_ago(age)
    reported = stamp if reported_days == "same" else (None if reported_days is None else days_ago(reported_days))
    cursor = conn.execute(
        "INSERT INTO inbox_items (key, source, conversation, sender_name, sender_address, sender_domain, subject, text, draft, guidance, "
        "target, thread_json, attachments_json, state, note, promised, sent_at, recorded_at, reported_at, closed_at, updated_at) "
        "VALUES (?, ?, ?, 'Priya Nair', 'priya@clinic.example', 'clinic.example', 'PRIVATE-SUBJECT', ?, 'PRIVATE-DRAFT', 'PRIVATE-GUIDANCE', "
        "'https://www.facebook.com/x/PRIVATE', ?, '[\"PRIVATE-FILE.pdf\"]', ?, 'PRIVATE-NOTE', ?, ?, ?, ?, ?, ?)",
        (f"key-{_serial['n']}", source, f"c-{_serial['n']}", WORDS,
         json.dumps(thread if thread is not None else {"reply_to": "priya@clinic.example", "message_id": "<PRIVATE@x>", "references": ["<PRIVATE@y>"],
                                                       "words_key": "kept", "comment_id": "123", "thread": "/x"}),
         state, int(promised), None if sent_days is None else days_ago(sent_days), stamp, reported,
         None if closed_days is None else days_ago(closed_days), stamp),
    )
    return cursor.lastrowid


def closed_request(conn, number: int, kind: str, subject: str) -> None:
    conn.execute("INSERT INTO approvals (id, kind, subject, content_hash, status, reason, requested_at, decide_by, closed_at, close_reason) "
                 "VALUES (?, ?, ?, ?, 'superseded', 'r', ?, ?, ?, 'the item is gone')",
                 (number, kind, subject, "h" * 64, days_ago(100), days_ago(97), days_ago(99)))


def removed(conn, item_id: int) -> bool:
    found = store.get(conn, item_id)
    return found["text_removed_at"] is not None


# --- what "closes" means, for each state -------------------------------------------------------------


@pytest.mark.parametrize("state", [store.SENT, store.SKIPPED, store.LAPSED, store.SUPERSEDED, store.UNKNOWN, store.FAILED,
                                   store.ANSWERED_BY_HAND, "closed", store.DONE])
def test_iw_n7_an_item_at_its_end_closes_when_it_got_there(conn, state):
    kept, gone = item(conn, state, age=89.9), item(conn, state, age=90.1)
    assert retention.prune(conn)["items"] == 1
    assert not removed(conn, kept) and removed(conn, gone)


def test_iw_n7_reported_closes_when_its_report_went(conn):
    told_late = item(conn, store.REPORTED, age=200, reported_days=10)
    told_long_ago = item(conn, store.REPORTED, age=200, reported_days=91)
    retention.prune(conn)
    assert not removed(conn, told_late) and removed(conn, told_long_ago)


def test_iw_n7_reported_but_not_told_stays_open(conn):
    """Discord has been down: he hasn't seen it, so its words can't go."""
    untold = item(conn, store.REPORTED, age=200, reported_days=None)
    retention.prune(conn)
    assert not removed(conn, untold)


@pytest.mark.parametrize("state", [store.NOISE, store.BASELINE, store.OWN])
def test_iw_n7_what_never_asked_anything_closes_when_it_was_recorded(conn, state):
    kept, gone = item(conn, state, age=89.9, reported_days=None), item(conn, state, age=90.1, reported_days=None)
    retention.prune(conn)
    assert not removed(conn, kept) and removed(conn, gone)


def test_iw_n7_unverified_closes_when_its_report_went(conn):
    gone = item(conn, store.UNVERIFIED, age=100, reported_days=91)
    kept = item(conn, store.UNVERIFIED, age=100, reported_days=None)
    retention.prune(conn)
    assert removed(conn, gone) and not removed(conn, kept)


def test_iw_n7_a_hand_reply_closes_when_it_leaves_the_list_a_week_on(conn):
    """R4 lists it for 7 days. Its words go 90 days after that, whether or not he sends `done`."""
    kept, gone = item(conn, store.NEEDS_HAND_REPLY, age=96.9), item(conn, store.NEEDS_HAND_REPLY, age=97.1)
    retention.prune(conn)
    assert not removed(conn, kept) and removed(conn, gone)


def test_iw_n7_a_promised_reply_loses_its_words_and_keeps_its_line(conn):
    """F10: it is listed until `done`, but its words don't stay forever because he never sent that."""
    kept = item(conn, store.NEEDS_HAND_REPLY, age=300, promised=True, sent_days=89.9)
    gone = item(conn, store.NEEDS_HAND_REPLY, age=300, promised=True, sent_days=90.1)
    retention.prune(conn)
    assert not removed(conn, kept) and removed(conn, gone)
    assert store.get(conn, gone)["state"] == store.NEEDS_HAND_REPLY


@pytest.mark.parametrize("state", [store.NEW, store.TRIAGED, store.WAITING, store.SENDING, store.OBSERVED])
def test_iw_n7_what_is_still_moving_hasnt_closed(conn, state):
    found = item(conn, state, age=500)
    retention.prune(conn)
    assert not removed(conn, found)


def test_iw_n7_done_closes_when_he_said_so(conn):
    kept, gone = item(conn, store.DONE, age=300, closed_days=10), item(conn, store.DONE, age=300, closed_days=91)
    conn.execute("UPDATE inbox_items SET updated_at = ? WHERE id = ?", (days_ago(10), kept))
    retention.prune(conn)
    assert not removed(conn, kept) and removed(conn, gone)


def test_iw_n7_config_may_shorten_the_days_and_never_lengthen_them(conn, monkeypatch):
    from jura_growth import config

    shorter, kept = item(conn, store.SENT, age=40), item(conn, store.SENT, age=20)
    monkeypatch.setattr(config, "agent_config", lambda name: {"text_retention_days": 30})
    retention.prune(conn)
    assert removed(conn, shorter) and not removed(conn, kept)

    longer = item(conn, store.SENT, age=91)
    monkeypatch.setattr(config, "agent_config", lambda name: {"text_retention_days": 400})
    retention.prune(conn)
    assert removed(conn, longer)


# --- what removal takes ----------------------------------------------------------------------------------


def test_iw_n6_removal_takes_every_word_and_keeps_only_what_counts_and_dedupes(conn):
    gone = item(conn, store.SENT)
    before = store.get(conn, gone)
    retention.prune(conn)

    after = store.get(conn, gone)
    for column in ("text", "subject", "sender_name", "sender_address", "target", "note"):
        assert after[column] == "", column
    assert after["draft"] is None and after["guidance"] is None and after["attachments_json"] == "[]"
    assert "PRIVATE" not in json.dumps(dict(after)) and "priya@" not in json.dumps(dict(after))
    assert after["key"] == before["key"] and after["conversation"] == before["conversation"]
    assert after["sender_domain"] == "clinic.example" and after["state"] == store.SENT
    thread = json.loads(after["thread_json"])
    assert thread == {"words_key": "kept", "comment_id": "123", "thread": "/x"}


def test_iw_n7_removing_the_words_doesnt_put_an_old_line_back_on_the_list(conn):
    """R4 lists a lapsed item for 7 days from when it lapsed, and removal is not that moment."""
    gone = item(conn, store.LAPSED)
    before = store.get(conn, gone)["updated_at"]
    retention.prune(conn)
    assert store.get(conn, gone)["updated_at"] == before
    assert store.label(gone) not in "\n".join(inbox_one_pager.lines(conn, days_ago(1)))


def test_iw_w5_a_removed_message_still_counts_once(conn):
    gone = item(conn, store.SENT)
    key = store.get(conn, gone)["key"]
    retention.prune(conn)
    assert store.known(conn, key)
    assert isinstance(store.record(conn, store.Reaction(source="email", key=key, conversation="c", text="again")), store.Duplicate)


def test_iw_n6_it_blanks_the_cards_first_piece(conn):
    gone, open_one = item(conn, store.SENT), item(conn, store.WAITING, age=1)
    for number, item_id in ((1, gone), (2, open_one)):
        closed_request(conn, number, kinds.KIND, kinds.subject_of(item_id))
        conn.execute("INSERT INTO approval_cards (approval_id, message_id, first_piece, shows, posted_at) VALUES (?, 'm', ?, 'superseded', ?)",
                     (number, f"card with {WORDS}", days_ago(100)))
    retention.prune(conn)
    rows = {row["approval_id"]: row["first_piece"] for row in db.rows(conn, "SELECT * FROM approval_cards")}
    assert rows[1] == "" and WORDS in rows[2]


def test_iw_n6_a_blanked_card_can_still_have_its_header_edited(conn, discord_double):
    gone = item(conn, store.SENT)
    closed_request(conn, 1, kinds.KIND, kinds.subject_of(gone))
    conn.execute("INSERT INTO approval_cards (approval_id, message_id, first_piece, shows, posted_at) VALUES (1, 'm', ?, 'pending', ?)",
                 (f"card with {WORDS}", days_ago(100)))
    retention.prune(conn)
    cards.sweep(conn)
    assert not [text for text in discord_double.contents(cards.CHANNEL) if WORDS in text]


def test_iw_n6_it_leaves_other_kinds_cards_alone(conn):
    closed_request(conn, 1, "outreach-email", "outreach_message:1")
    conn.execute("INSERT INTO approval_cards (approval_id, message_id, first_piece, shows, posted_at) VALUES (1, 'm', 'kept', 'superseded', ?)", (days_ago(100),))
    item(conn, store.SENT)
    retention.prune(conn)
    assert db.scalar(conn, "SELECT first_piece FROM approval_cards") == "kept"


def test_iw_n6_pruning_twice_changes_nothing_more(conn):
    item(conn, store.SENT)
    assert retention.prune(conn)["items"] == 1
    assert retention.prune(conn)["items"] == 0


# --- the nightly backup ----------------------------------------------------------------------------------


def outbox_file(day: str):
    path = discord.outbox_dir() / f"{day}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ts": f"{day}T10:00:00+08:00", "channel": "mission-control", "content": WORDS}) + "\n")
    return path


def test_iw_n6_the_outbox_keeps_fourteen_days(conn):
    kept, gone = outbox_file("2026-11-17"), outbox_file("2026-11-16")
    assert backup.prune_outbox() == 1
    assert kept.exists() and not gone.exists()


def test_iw_n6_config_sets_the_outbox_days(conn, monkeypatch):
    from jura_growth import config

    real = config.settings()
    monkeypatch.setattr(config, "settings", lambda: {**real, "retention": {**real.get("retention", {}), "outbox_days": 3}})
    kept, gone = outbox_file("2026-11-28"), outbox_file("2026-11-27")
    backup.prune_outbox()
    assert kept.exists() and not gone.exists()


def test_iw_n6_a_file_that_isnt_a_day_stays(conn):
    folder = discord.outbox_dir()
    folder.mkdir(parents=True, exist_ok=True)
    other = folder / "notes.jsonl"
    other.write_text("{}\n")
    backup.prune_outbox()
    assert other.exists()


def test_iw_n6_the_nightly_backup_runs_it_all_and_tonights_copy_holds_none_of_it(conn):
    gone = item(conn, store.SENT)
    outbox = outbox_file("2026-11-01")
    conn.commit()

    target = backup.backup(conn)

    assert removed(conn, gone) and not outbox.exists()
    copy = sqlite3.connect(target)
    try:
        assert copy.execute("SELECT text FROM inbox_items WHERE id = ?", (gone,)).fetchone()[0] == ""
    finally:
        copy.close()
    written = db.one(conn, "SELECT payload_json FROM events WHERE kind = 'backup.written'")
    assert json.loads(written["payload_json"])["outbox_pruned"] == 1
    assert json.loads(written["payload_json"])["inbox_retention"] == {"items": 1, "cards": 0}


def test_iw_n6_a_plug_ins_retention_that_breaks_never_stops_the_backup(conn, monkeypatch):
    from jura_growth.agents import inbox

    def broken(reader):
        raise ValueError("no")

    monkeypatch.setattr(inbox, "retention", broken)
    assert backup.backup(conn).exists()
    assert db.one(conn, "SELECT 1 FROM events WHERE kind = 'backup.retention_failed'")


def test_iw_n6_it_works_while_inbox_is_paused(conn):
    from jura_growth import pause

    gone = item(conn, store.SENT)
    pause.pause(conn, "inbox", "a test", notify=False)
    backup.backup(conn)
    assert removed(conn, gone)
