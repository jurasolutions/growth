"""Replies waiting on the one-pager (inbox watch ticket 04). Rows: IW-R4 and IW-R2, with functional S12
and S16, F10 and F13, and technical N8, named by their own numbers in each test.

Through the seam it is read at: rows in a real database, then `mission.read(Source)`, then
`one_pager.text(snapshot)`, and `/growth inbox list` through `remote`. Ting Yu reads this on his phone
at 08:00, so a line must say who wrote, where, how long ago and what he must do.
"""

from __future__ import annotations

import json
import re
import sqlite3

import pytest
from click.testing import CliRunner

import inbox_watch_world as w
import mission_world as world
import sweep
from jura_growth import db, mission, one_pager
from jura_growth.agents import inbox
from jura_growth.agents.inbox import kinds, store, watch
from jura_growth.cli import cli
from jura_growth.origin import Origin

NOW = "2026-11-10T08:00:00+08:00"
HOURS_AGO = {1: "2026-11-10T07:00:00+08:00", 3: "2026-11-10T05:00:00+08:00", 14: "2026-11-09T18:00:00+08:00",
             27: "2026-11-09T05:00:00+08:00"}
PRIYA = "priya@clinic.example"


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", NOW)


@pytest.fixture
def jobs():
    return {"one-pager": {"schedule": {"daily": "08:00"}, "agent": "one-pager", "kind": "command", "command": ["one-pager"]}}


_serial = {"n": 0}


def item(conn, *, source="email", state=store.REPORTED, name="Priya Nair", domain="clinic.example", text="Do you work with clinics?",
         subject="", at=HOURS_AGO[3], priority=None, target="", note="", promised=False, sent_at=None, updated_at=None, cls=None,
         address=PRIYA, asked_at=None, thread="{}") -> int:
    _serial["n"] += 1
    key = f"key-{_serial['n']}"
    cursor = conn.execute(
        "INSERT INTO inbox_items (key, source, conversation, sender_name, sender_address, sender_domain, subject, text, target, "
        "state, note, priority, class, promised, sent_at, received_at, recorded_at, reported_at, updated_at, asked_at, thread_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (key, source, key, name, address, domain, subject, text, target, state, note, priority, cls, int(promised), sent_at, at, at, at,
         updated_at or at, asked_at, thread),
    )
    return cursor.lastrowid


def card(conn, item_id: int, number: int, *, status="pending", decide_by="2026-11-12T10:00:00+08:00", posted=True, used_at=None,
         decided_at=None) -> None:
    conn.execute(
        "INSERT INTO approvals (id, kind, subject, content_hash, status, reason, requested_at, decide_by, decided_at, decided_by, "
        "decided_origin, used_at, posted_at) VALUES (?, ?, ?, ?, ?, 'a test asked', ?, ?, ?, ?, ?, ?, ?)",
        (number, kinds.KIND, kinds.subject_of(item_id), f"{number:064x}", status, HOURS_AGO[1], decide_by, decided_at,
         "discord:111" if decided_at else None, "ssh" if decided_at else None, used_at, NOW if posted else None),
    )


def known_contact(conn) -> None:
    """A named contact, which is how a person's name is learned for plain masking."""
    conn.execute("INSERT INTO leads (id, company, display_name, domain, website, industry, score, score_reasons, channel, status, created_at, updated_at) "
                 "VALUES (233, 'Example Pte Ltd', 'Example', 'example.com.sg', 'https://example.com.sg', 'logistics', 78, '[]', 'email', 'new', ?, ?)", (NOW, NOW))
    conn.execute("INSERT INTO contacts (lead_id, email, email_hash, source_url, kind, mx_ok, verified_at, created_at) "
                 "VALUES (233, ?, 'h', ?, 'named', 1, ?, ?)", (sweep.NAMED_ADDRESS, sweep.SOURCE_PAGE, NOW, NOW))


def snapshot(jobs, now: str = NOW) -> mission.Snapshot:
    return mission.read(world.source(now, jobs=jobs))


def section(jobs, now: str = NOW) -> list[str]:
    """The Replies waiting section as the one-pager prints it."""
    found = one_pager.text(snapshot(jobs, now)).split("\n\n")
    named = [part.split("\n") for part in found if part.startswith("**Replies waiting**")]
    assert len(named) == 1, found
    return named[0][1:]


def listed() -> str:
    return CliRunner().invoke(cli, ["inbox", "list"]).output


def test_iw_r4_the_section_sits_between_needs_you_and_approvals_waiting(conn, jobs):
    conn.commit()
    text = one_pager.text(snapshot(jobs))
    assert text.index("**Needs you**") < text.index("**Replies waiting**") < text.index("**Approvals waiting**")


def test_iw_r4_a_snapshot_with_no_section_renders_as_it_did():
    plain = mission.Snapshot(world.source(NOW, jobs={}).now, mission.OK)
    assert "Replies waiting" not in one_pager.text(plain)
    assert plain.plugin_sections == ()


def test_iw_r4_a_card_waiting_says_who_where_how_long_and_what_to_do(conn, jobs):
    first = item(conn, source="enquiry", state=store.WAITING, name="Jane Tan", domain="acme.example", text="We retype every invoice by hand.",
                 at=HOURS_AGO[14], address="jane@acme.example")
    card(conn, first, 412)
    conn.commit()

    [_, line] = section(jobs)
    assert "A-0412" in line and "Jane Tan" in line and "acme.example" in line and "Website enquiry" in line
    assert "14h" in line and "We retype every invoice by hand." in line
    assert "Approve or skip in #approvals by Thu 12 Nov" in line


def test_iw_r4_says_when_nothing_is_waiting(conn, jobs):
    conn.commit()
    assert section(jobs) == ["Nothing waiting"]


def test_iw_r4_counts_reactions_since_the_last_one_pager_not_before(conn, jobs):
    item(conn, at="2026-11-09T07:00:00+08:00", state=store.REPORTED)  # before yesterday's 08:00
    item(conn, at=HOURS_AGO[3], state=store.REPORTED)
    item(conn, at=HOURS_AGO[1], state=store.REPORTED)
    item(conn, at=HOURS_AGO[1], state=store.BASELINE, source="facebook-comment")
    item(conn, at=HOURS_AGO[1], state=store.OWN, source="facebook-comment")
    conn.commit()

    assert section(jobs)[0].startswith("2 reactions since the last one-pager")


def test_iw_r4_a_message_that_needs_nothing_isnt_a_line(conn, jobs):
    item(conn, state=store.REPORTED, cls="thanks")
    item(conn, state=store.SENT, sent_at=HOURS_AGO[1])
    item(conn, state=store.SKIPPED)
    item(conn, state=store.SUPERSEDED)
    item(conn, state=store.OBSERVED, source="facebook-comment")  # held: it is told after its run's checks
    conn.commit()

    assert len(section(jobs)) == 1


def test_iw_d9_a_high_item_shows_first_and_says_so(conn, jobs):
    older = item(conn, state=store.WAITING, name="Old Asker", at=HOURS_AGO[27])
    card(conn, older, 1)
    high = item(conn, state=store.WAITING, name="Upset Person", at=HOURS_AGO[1], priority="high")
    card(conn, high, 2)
    conn.commit()

    lines = section(jobs)
    assert "Upset Person" in lines[1] and "**High" in lines[1]
    assert "Old Asker" in lines[2]


def test_iw_f10_a_promised_reply_stays_first_past_seven_days_until_done(conn, jobs):
    item(conn, state=store.WAITING, name="High One", priority="high", at=HOURS_AGO[1])
    promised = item(conn, state=store.NEEDS_HAND_REPLY, name="Promised One", promised=True, sent_at="2026-10-20T10:00:00+08:00",
                    at="2026-10-20T09:00:00+08:00", updated_at="2026-10-20T10:00:00+08:00")
    conn.commit()

    lines = section(jobs)
    assert "Promised One" in lines[1] and "**Promised" in lines[1] and "20d" in lines[1]
    assert f"/growth inbox done {store.label(promised)}" in lines[1]


def test_iw_r4_a_hand_reply_says_where_and_leaves_after_seven_days(conn, jobs):
    item(conn, state=store.NEEDS_HAND_REPLY, name="Fresh Hand", source="facebook-comment", target="https://www.facebook.com/x/posts/1",
         updated_at=HOURS_AGO[3])
    stale = item(conn, state=store.NEEDS_HAND_REPLY, name="Stale Hand", updated_at="2026-11-02T09:00:00+08:00", at="2026-11-02T09:00:00+08:00")
    conn.commit()

    text = "\n".join(section(jobs))
    assert "Fresh Hand" in text and "<https://www.facebook.com/x/posts/1>" in text and "Answer by hand" in text
    assert "Stale Hand" not in text, stale


@pytest.mark.parametrize("state, words", [
    (store.LAPSED, "Lapsed: answer by hand if it still matters"),
    (store.FAILED, "It didn't go: answer by hand if it still matters"),
    (store.UNKNOWN, "It may have gone out: check Levi's mailbox before answering by hand"),
    (store.UNVERIFIED, "Unverified: read the thread yourself"),
])
def test_iw_r4_lapsed_dropped_or_uncertain_lists_seven_days_with_where_to_answer(conn, jobs, state, words):
    item(conn, state=state, name="In Time", updated_at="2026-11-03T09:00:00+08:00", at="2026-11-03T09:00:00+08:00")
    item(conn, state=state, name="Too Late", updated_at="2026-11-03T07:59:00+08:00", at="2026-11-03T07:59:00+08:00")
    conn.commit()

    text = "\n".join(section(jobs))
    assert "In Time" in text and words in text
    assert "Too Late" not in text


def test_iw_r4_a_pending_card_past_its_decide_by_reads_lapsed_by_the_clock_without_writing(conn, jobs):
    found = item(conn, state=store.WAITING, name="Past Due")
    card(conn, found, 9, decide_by="2026-11-10T07:59:00+08:00")
    conn.commit()

    line = section(jobs)[1]
    assert "Lapsed: answer by hand" in line
    assert db.scalar(conn, "SELECT status FROM approvals WHERE id = 9") == "pending"
    assert store.get(conn, found)["state"] == store.WAITING


@pytest.mark.parametrize("state, status, used, words", [
    (store.WAITING, "approved", None, "Approved: it goes out on the next send"),
    (store.SENDING, "approved", NOW, "On its way"),
])
def test_iw_r4_an_approved_reply_asks_nothing_of_him(conn, jobs, state, status, used, words):
    found = item(conn, state=state)
    card(conn, found, 3, status=status, used_at=used, decided_at=HOURS_AGO[1])
    conn.commit()
    assert words in section(jobs)[1]


def test_iw_r4_a_card_that_never_posted_says_so(conn, jobs):
    found = item(conn, state=store.WAITING)
    card(conn, found, 4, posted=False)
    conn.commit()
    assert "hasn't posted yet" in section(jobs)[1]


def test_iw_r4_a_conversation_is_one_line_with_its_newest_words(conn, jobs):
    item_id = item(conn, state=store.REPORTED, text="How much?")
    conn.execute("UPDATE inbox_items SET conversation = 'c' WHERE id = ?", (item_id,))
    for text in ("first", "second"):
        found = item(conn, state=store.NEW, text=text)
        conn.execute("UPDATE inbox_items SET conversation = 'c' WHERE id = ?", (found,))
    conn.commit()

    lines = section(jobs)
    assert len(lines) == 2 and "second" in lines[1] and "2 messages" in lines[1]
    assert "Being read" in lines[1]


def test_iw_r4_ten_lines_then_and_n_more_and_the_list_shows_more(conn, jobs):
    for number in range(13):
        found = item(conn, state=store.WAITING, name=f"Person{number}", text="short")
        card(conn, found, number + 1)
    conn.commit()

    lines = section(jobs)
    people = [line for line in lines if "Person" in line]
    assert len(people) == 10
    assert any("and 3 more: `/growth inbox list`" in line for line in lines)
    assert listed().count("Person") == 13


def test_iw_r4_the_read_model_calls_no_content_and_writes_nothing(conn, jobs, monkeypatch):
    found = item(conn, state=store.WAITING, text="anything")
    card(conn, found, 5)
    conn.commit()
    before = conn.execute("SELECT total_changes()").fetchone()[0]

    def forbidden(*args, **kwargs):
        raise AssertionError("mission.read called a kind's content()")

    monkeypatch.setattr(kinds.EmailReply, "content", forbidden)
    assert "A-0005" in "\n".join(section(jobs))
    assert conn.execute("SELECT total_changes()").fetchone()[0] == before


def test_iw_r4_the_hook_is_handed_the_read_only_connection(conn, jobs, monkeypatch):
    conn.commit()
    seen = {}

    def spy(reader, since):
        seen["since"] = since
        with pytest.raises(sqlite3.OperationalError):
            reader.execute("UPDATE inbox_state SET value = 'x'")
        return ("Spy", ["fine"])

    monkeypatch.setattr(inbox, "one_pager_section", spy)
    found = snapshot(jobs)
    assert ("Spy", ("fine",)) in found.plugin_sections
    assert seen["since"].startswith("2026-11-09T08:00:00")


def test_iw_r4_a_section_that_breaks_says_so_and_the_one_pager_still_goes(conn, jobs, monkeypatch):
    conn.commit()

    def broken(reader, since):
        raise ValueError("Priya wrote this")

    monkeypatch.setattr(inbox, "one_pager_section", broken)
    found = snapshot(jobs)
    text = one_pager.text(found)
    assert "ValueError" in text and "Priya wrote this" not in text


def test_iw_r4_a_section_can_be_unavailable_before_the_migration(conn, jobs, monkeypatch):
    conn.execute("DROP TABLE inbox_items")
    conn.commit()
    assert "Replies waiting" not in one_pager.text(snapshot(jobs))


# --- plain masking, B3 -----------------------------------------------------------------------------


def test_iw_s7_excerpts_and_the_sender_stay_plain_masked_on_the_one_pager_and_the_list(conn, jobs):
    """B3: only cards and R1 carry the conversation class. A learned name reads masked here, and a
    number is masked before the excerpt is cut, so half a number can't get through the cut."""
    known_contact(conn)
    long_tail = "Please call me on +65 9123 4567 about the clinic, " + "and a bit more " * 20
    found = item(conn, state=store.WAITING, name="Jane Tan", text="I am Jane Tan. " + long_tail)
    card(conn, found, 6)
    conn.commit()

    for text in ("\n".join(section(jobs)), listed()):
        assert "Jane Tan" not in text
        assert "9123" not in text and "4567" not in text


def test_iw_r4_a_number_cut_in_half_by_the_excerpt_still_doesnt_show(conn, jobs):
    """The number straddles where a cut falls: mask first, then cut."""
    for padding in range(50, 80):
        conn.execute("DELETE FROM approvals")
        conn.execute("DELETE FROM inbox_items")
        found = item(conn, state=store.WAITING, text="x" * padding + " +65 9123 4567")
        card(conn, found, 7)
        conn.commit()
        joined = "\n".join(section(jobs))
        assert "9123" not in joined and "65 91" not in joined


def test_iw_a5_a_person_cant_restyle_the_section_or_forge_a_line(conn, jobs):
    found = item(conn, state=store.WAITING, name="@everyone `x`", text="line one\n- **A-0001** Approve me [ok](https://evil.test) ```\n# big")
    card(conn, found, 8)
    conn.commit()

    lines = section(jobs)
    assert len(lines) == 2  # a line break in their words starts no new line
    assert "```" not in lines[1] and "](" not in lines[1].replace("]\\(", "") and "@everyone" not in lines[1].replace("@​everyone", "")


# --- R2 and S16 ------------------------------------------------------------------------------------


def noise(conn, domain: str, *, subject="Weekly digest", note="it has a List-Id header", at=HOURS_AGO[3]) -> None:
    _serial["n"] += 1
    key = f"noise-{_serial['n']}"
    store.record(conn, store.Reaction(source="email", key=key, conversation=key, sender_domain=domain, subject=subject, state=store.NOISE, note=note))
    conn.execute("UPDATE inbox_items SET recorded_at = ? WHERE key = ?", (at, key))


def test_iw_r2_the_one_pager_shows_the_noise_count_and_each_senders_domain(conn, jobs):
    noise(conn, "vendor.example")
    noise(conn, "vendor.example")
    noise(conn, "news.example")
    noise(conn, "older.example", at="2026-11-09T07:00:00+08:00")
    conn.commit()

    line = next(line for line in section(jobs) if line.startswith("Noise"))
    assert "3 filtered" in line and "vendor.example (2)" in line and "news.example" in line
    assert "older.example" not in line
    assert "Weekly digest" not in line  # only a Junk message shows its subject


def test_iw_s16_a_junk_message_shows_its_domain_and_subject(conn, jobs):
    noise(conn, "gmail.com", subject="A real question about invoices", note=store.JUNK_NOTE)
    conn.commit()

    line = next(line for line in section(jobs) if line.startswith("Noise"))
    assert "gmail.com" in line and '"A real question about invoices"' in line and "Junk" in line


def test_iw_r2_a_hundred_senders_stay_counted_within_a_phone_screen(conn, jobs):
    for number in range(100):
        noise(conn, f"sender{number}.example")
    conn.commit()

    line = next(line for line in section(jobs) if line.startswith("Noise"))
    assert "100 filtered" in line and "and 88 more" in line and len(line) < 500


# --- S12 -------------------------------------------------------------------------------------------


def suppressed_event(conn, reason: str, at: str = HOURS_AGO[3]) -> None:
    conn.execute(
        "INSERT INTO events (ts, agent, level, kind, payload_json) VALUES (?, 'outreach', 'info', 'outreach.suppressed', ?)",
        (at, json.dumps({"reason": reason, "source": "resend", "domains": ["acme.example"], "message": None})),
    )


def test_iw_s12_an_unsubscribe_click_and_a_bounce_count_in_the_section(conn, jobs):
    suppressed_event(conn, "unsubscribe")
    suppressed_event(conn, "unsubscribe")
    suppressed_event(conn, "bounce")
    suppressed_event(conn, "bounce", at="2026-11-09T07:00:00+08:00")
    conn.commit()

    assert section(jobs)[0] == "0 reactions since the last one-pager, 2 unsubscribe clicks, 1 bounce"


# --- F13 -------------------------------------------------------------------------------------------


def surface(conn, name: str, good: str | None, *, items=0) -> None:
    conn.execute(
        "INSERT INTO inbox_surfaces (surface, first_tried_at, last_good_at, last_good_items, read_ok, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (name, "2026-11-01T09:05:00+08:00", good, items, int(good is not None), NOW),
    )


def test_iw_f13_all_surfaces_read_together_take_one_line(conn, jobs):
    for name in watch.SURFACES:
        surface(conn, name, "2026-11-09T21:05:00+08:00")
    conn.commit()

    line = next(line for line in section(jobs) if line.startswith("Last good read"))
    assert line == "Last good read: every surface, Mon 9 Nov, 21:05 SGT"


def test_iw_f13_surfaces_read_apart_each_show_their_last_good_read(conn, jobs):
    surface(conn, "instagram-primary", "2026-11-09T21:05:00+08:00")
    surface(conn, "facebook-spam", "2026-11-09T14:05:00+08:00")
    surface(conn, "posts", None)
    conn.commit()

    line = next(line for line in section(jobs) if line.startswith("Last good read"))
    assert "Instagram Primary Mon 9 Nov, 21:05" in line and "the Page's Spam Mon 9 Nov, 14:05" in line
    assert "Jura's recent posts never" in line


def test_iw_f13_a_watch_that_has_never_run_says_so(conn, jobs):
    conn.commit()
    assert section(jobs) == ["Nothing waiting"]


def test_iw_f13_comments_the_watch_couldnt_read_show_as_its_latest_message_said(conn, jobs):
    [label] = w.published(conn)
    watch.observe(conn, 1, [w.post_read(label, reactions=1, comments=0)])
    watch.post_lines(conn, 1)
    watch.observe(conn, 2, [w.post_read(label, reactions=1, comments=3)])
    said = watch.post_lines(conn, 2)
    conn.commit()
    assert "3 comments the watch couldn't read" in said[0]

    assert "3 comments the watch couldn't read: check by hand" in section(jobs)


def test_iw_f13_those_comments_leave_once_a_later_read_finds_them_read(conn, jobs):
    [label] = w.published(conn)
    watch.observe(conn, 1, [w.post_read(label, reactions=1, comments=0)])
    watch.post_lines(conn, 1)
    watch.observe(conn, 2, [w.post_read(label, reactions=1, comments=3)])
    watch.post_lines(conn, 2)
    watch.observe(conn, 3, [w.post_read(label, reactions=1, comments=0)])
    watch.post_lines(conn, 3)
    conn.commit()

    assert not [line for line in section(jobs) if "couldn't read" in line]


# --- N8 and the rest of the page ---------------------------------------------------------------------


def test_iw_n8_every_inbox_job_is_counted_not_listed_slot_by_slot():
    assert {"inbox-check", "inbox-send", "inbox-watch", "inbox-reply"} <= one_pager.COUNTED_JOBS


def test_iw_r4_ask_me_names_the_list():
    assert "`/growth inbox list`" in one_pager.ASK_ME


# --- the list ----------------------------------------------------------------------------------------


def test_iw_r4_the_list_shows_the_same_lines_on_request(conn, jobs):
    found = item(conn, state=store.WAITING, name="Jane Tan")
    card(conn, found, 10)
    noise(conn, "vendor.example")
    conn.commit()

    text = listed()
    lines = section(jobs)
    for line in lines:
        assert line in text


def test_iw_r4_the_list_through_remote_fits_dispatchs_answer(conn, monkeypatch):
    for number in range(40):
        found = item(conn, state=store.WAITING, name=f"Person{number}", text="A long message " * 30)
        card(conn, found, number + 1)
    conn.commit()
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", "111")

    result = CliRunner().invoke(cli, ["remote", "--actor", "discord:111", "--json", "--", "inbox", "list"], obj={"origin": Origin.ssh()})
    body = json.loads(result.output)
    assert body["exit_code"] == 0 and len(body["text"]) <= 1900 and "Person0" in body["text"]


def test_iw_a14_nothing_planted_reaches_the_section_or_the_list(conn, jobs):
    known_contact(conn)
    found = item(conn, state=store.WAITING, name=sweep.PERSON, text=f"{sweep.PERSON} at {sweep.NAMED_ADDRESS}, {sweep.PHONE}")
    card(conn, found, 11)
    conn.commit()

    for text in ("\n".join(section(jobs)), listed()):
        for value in (sweep.NAMED_ADDRESS, sweep.PHONE, sweep.PERSON):
            assert value not in text


def test_iw_r4_a_line_fits_a_phone(conn, jobs):
    found = item(conn, state=store.WAITING, name="N" * 120, domain="d" * 60 + ".example", text="word " * 800, source="enquiry")
    card(conn, found, 12)
    conn.commit()

    assert len(section(jobs)[1]) <= 320


def test_iw_r4_a_line_tells_how_long_in_a_word(conn, jobs):
    for at, label_ in (("2026-11-10T07:48:00+08:00", "12m"), (HOURS_AGO[3], "3h"), (HOURS_AGO[27], "1d")):
        found = item(conn, state=store.WAITING, at=at, name=f"Age{label_}")
        card(conn, found, _serial["n"] + 100)
    conn.commit()
    text = "\n".join(section(jobs))
    for label_ in ("12m", "3h", "1d"):
        assert re.search(rf"Age{label_}.*{label_}", text)

