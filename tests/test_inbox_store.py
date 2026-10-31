"""`inbox.store.record`, the seam mail intake and `inbox observe` both go through (technical
review, Seams). It knows nothing about mail: a reaction arrives with its key already worked out.
"""

from __future__ import annotations

import pytest

from jura_growth import config, caps, db
from jura_growth.agents.inbox import settings, store


def reaction(**overrides) -> store.Reaction:
    fields = {"source": "email", "key": "key-1", "conversation": "conversation-1", "sender_name": "Priya Nair",
              "sender_domain": "clinic.example", "text": "Do you work with clinics?"}
    return store.Reaction(**{**fields, **overrides})


def test_iw_w5_a_reaction_is_recorded_once(conn):
    """IW-W5: the second read of the same reaction records nothing new."""
    first = store.record(conn, reaction())
    second = store.record(conn, reaction(text="Told differently the second time"))

    assert isinstance(first, store.Recorded)
    assert isinstance(second, store.Duplicate) and second.item_id == first.item_id
    assert db.scalar(conn, "SELECT count(*) FROM inbox_items") == 1
    assert store.get(conn, first.item_id)["text"] == "Do you work with clinics?"


def test_iw_w5_known_says_whether_a_key_was_recorded(conn):
    """IW-W5: intake asks before it spends a body fetch."""
    assert not store.known(conn, "key-1")
    store.record(conn, reaction())
    assert store.known(conn, "key-1")


def test_the_conversation_key_is_kept_on_the_item(conn):
    """F8 in ticket 02 builds on it."""
    made = store.record(conn, reaction(conversation="thread-9"))
    assert store.get(conn, made.item_id)["conversation"] == "thread-9"


@pytest.mark.parametrize("field, value", [("source", "pigeon"), ("state", "misplaced")])
def test_a_source_or_state_outside_the_model_is_refused_in_code(conn, field, value):
    """No CHECK on the column (SQLite can't alter one): the code holds the model."""
    with pytest.raises(ValueError, match=field):
        store.record(conn, reaction(**{field: value}))


def test_every_state_in_the_prd_model_and_the_amendments_can_be_stored(conn):
    """A later ticket needs no table rebuild for a state the PRD names."""
    wanted = {"new", "triaged", "reported", "waiting", "sent", "skipped", "lapsed", "superseded", "unknown", "failed",
              "needs-you", "noise", "unverified", "answered-by-hand", "closed", "done"}
    assert wanted <= set(store.STATES)
    made = store.record(conn, reaction())
    for state in store.STATES:
        store.set_item_state(conn, made.item_id, state)
        assert store.get(conn, made.item_id)["state"] == state
    with pytest.raises(ValueError):
        store.set_item_state(conn, made.item_id, "misplaced")


@pytest.mark.parametrize("length, cut", [(3999, False), (4000, False), (4001, True), (1_000_000, True)])
def test_iw_a6_stored_text_is_capped(conn, length, cut):
    """IW-A6: at most `caps.INBOX_TEXT_CHARS`, and the item says when it was cut."""
    made = store.record(conn, reaction(text="x" * length))
    row = store.get(conn, made.item_id)
    assert len(row["text"]) == min(length, caps.INBOX_TEXT_CHARS)
    assert bool(row["text_cut"]) is cut


def test_iw_a6_a_cut_across_an_emoji_leaves_valid_text(conn):
    """IW-A6: code points are never split, and a lone surrogate from a bad decode is replaced."""
    made = store.record(conn, reaction(text="x" * 3999 + "\U0001f600\U0001f600", subject="bad \udce9 subject"))
    row = store.get(conn, made.item_id)
    assert row["text"].encode("utf-8") and row["text"].endswith("\U0001f600")
    assert row["subject"].encode("utf-8")


@pytest.mark.parametrize(
    "dirty, clean",
    [
        ("a\x00b", "ab"),
        ("a\x1b[31mred\x1b[0mb", "aredb"),
        ("a\u202eb\u2066c\u200bd\ufeffe", "abcde"),
        ("a\x07\x08b", "ab"),
        ("one\r\ntwo\u2028three\x85four", "one\ntwo\nthree\nfour"),
    ],
)
def test_iw_a12_controls_never_reach_the_stored_text(conn, dirty, clean):
    """IW-A12: NUL, ANSI escapes, RTL overrides, zero-width characters, odd line breaks."""
    made = store.record(conn, reaction(text=dirty))
    assert store.get(conn, made.item_id)["text"] == clean


def test_iw_a7_a_subject_and_a_name_are_one_clean_line(conn):
    """IW-A7, IW-A12: no CR, LF or control in anything that may become a header."""
    made = store.record(conn, reaction(subject="Hi\r\nBcc: x@evil.test\x00", sender_name="Jane\r\n\tTan\u202e"))
    row = store.get(conn, made.item_id)
    assert row["subject"] == "Hi Bcc: x@evil.test"
    assert row["sender_name"] == "Jane Tan"


def test_an_item_can_be_labelled_for_reports():
    """IW-FS2: every report carries `I-nnnn`."""
    assert store.label(7) == "I-0007"
    assert store.label(12345) == "I-12345"


@pytest.mark.parametrize(
    "name, hard",
    [
        ("email_replies_per_day", caps.INBOX_EMAIL_REPLIES_PER_DAY),
        ("social_replies_per_day", caps.INBOX_SOCIAL_REPLIES_PER_DAY),
        ("watch_posts_per_run", caps.INBOX_WATCH_POSTS_PER_RUN),
        ("decide_by_days", caps.INBOX_DECIDE_BY_DAYS),
        ("use_by_days", caps.INBOX_USE_BY_DAYS),
        ("text_chars", caps.INBOX_TEXT_CHARS),
        ("text_retention_days", caps.INBOX_TEXT_RETENTION_DAYS),
        ("bodies_per_check", caps.INBOX_BODIES_PER_CHECK),
        ("check_seconds", caps.INBOX_CHECK_SECONDS),
        ("first_run_days", caps.INBOX_FIRST_RUN_DAYS),
        ("look_back_days", caps.INBOX_LOOK_BACK_DAYS),
    ],
)
def test_config_may_tighten_a_limit_and_never_raise_it(monkeypatch, name, hard):
    """PRD §4: the hard limits are in caps.py, and config may only tighten."""
    assert settings.limit(name) == hard
    monkeypatch.setattr(config, "agent_config", lambda agent: {name: hard + 1000} if agent == "inbox" else {})
    assert settings.limit(name) == hard
    monkeypatch.setattr(config, "agent_config", lambda agent: {name: 1} if agent == "inbox" else {})
    assert settings.limit(name) == 1


def test_the_gap_between_social_replies_may_only_grow(monkeypatch):
    """PRD §4: a floor, as `PUBLISH_MINUTES_BETWEEN_ACTIONS` is."""
    floor = caps.INBOX_MINUTES_BETWEEN_SOCIAL_REPLIES
    assert settings.minutes_between_social_replies() == floor
    monkeypatch.setattr(config, "agent_config", lambda agent: {"minutes_between_social_replies": 1})
    assert settings.minutes_between_social_replies() == floor
    monkeypatch.setattr(config, "agent_config", lambda agent: {"minutes_between_social_replies": 45})
    assert settings.minutes_between_social_replies() == 45


def test_the_shipped_config_stays_inside_the_caps():
    """`config/inbox.yaml` as it ships changes nothing it isn't meant to."""
    shipped = config.agent_config("inbox")
    assert shipped, "config/inbox.yaml is missing"
    assert settings.limit("first_run_days") == 7
    assert settings.limit("bodies_per_check") == caps.INBOX_BODIES_PER_CHECK


def test_inbox_status_shows_counts_and_never_a_person(conn, monkeypatch):
    """R5's rule on the command line: counts and last good checks only."""
    from click.testing import CliRunner

    from jura_growth.cli import cli

    monkeypatch.setenv("JURA_GROWTH_NOW", "2026-10-26T10:00:00+08:00")
    store.record(conn, reaction(sender_address="priya@clinic.example"))
    store.record(conn, reaction(key="key-2", state=store.NOISE, sender_domain="vendor.example", subject="Weekly note"))
    store.set_state(conn, "mail.last_success.levi", "2026-10-26T09:45:00+08:00")

    output = CliRunner().invoke(cli, ["inbox", "status"], catch_exceptions=False).output

    assert "today: 1 reactions, 1 noise" in output and "1 not yet reported" in output
    assert "levi mailbox: last good check 2026-10-26T09:45:00+08:00" in output
    for private in ("Priya", "priya@", "clinic.example", "clinics", "Weekly note"):
        assert private not in output
