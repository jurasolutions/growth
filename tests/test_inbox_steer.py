"""He steers it from Discord (inbox watch ticket 04). Rows: IW-D6 and IW-S6. In this file `s1` and `s2`
are functional S1 and S2, and `n9` is technical N9, and the unsuppress tests are code review 02's SEC-2.

The seam is `remote` with the origin in process, as Dispatch reaches it: `remote --actor discord:<id>
--json -- inbox reword A-nnnn …`. Mail comes in as real bytes through the strict IMAP double, triage comes
in at `triage.submit`, and Discord is the double.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from discord_double import discord_double  # noqa: F401 - a fixture
from inbox_world import raw_mail
from jura_growth import approvals, caps, cards, db, headless, origin, pause, paths, remote as remote_mod, suppression
from jura_growth.agents.inbox import job, kinds, mail, report, store, triage
from jura_growth.cli import cli
from jura_growth.origin import Origin
from test_inbox_email_reply import DRAFT, PRIYA, approved, box, carded, request_for, sent, triaged  # noqa: F401
from test_inbox_email_reply import arrives as arrives_raw
from test_scout_support import decide, fake_d1, scout_env  # noqa: F401

WORDS = "Thanks for asking. Levi will write back today."
STEERING = ("inbox done", "inbox draft", "inbox redraft", "inbox reword", "inbox unsuppress")


def remote(*words, origin_=None) -> dict:
    """Dispatch's call, after the forced command split the words."""
    result = CliRunner().invoke(cli, ["remote", "--actor", "discord:111", "--json", "--", *words], obj={"origin": origin_ or Origin.ssh()})
    return json.loads(result.output)


@pytest.fixture(autouse=True)
def control(monkeypatch):
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", "111")


def reload(conn, item: dict) -> dict:
    return store.get(conn, item["id"])


def arrives(conn, box, raw: bytes | None = None) -> dict:
    return arrives_raw(conn, box, raw or raw_mail())


# --- reword ------------------------------------------------------------------------------------------


def test_iw_d6_a_reword_closes_the_old_card_and_raises_a_new_one_with_his_exact_words(conn, box, sent, discord_double):
    item, old = carded(conn, box)
    cards.sweep(conn)

    body = remote("inbox", "reword", old.id, *WORDS.split())

    assert body["exit_code"] == 0, body
    assert approvals.get(conn, old.id).status == approvals.SUPERSEDED
    new = request_for(conn, item)
    assert new.id != old.id and new.status == approvals.PENDING and new.supersedes == old.number
    assert new.id in body["text"]
    assert reload(conn, item)["draft"] == WORDS
    assert reload(conn, item)["state"] == store.WAITING
    posted = discord_double.contents(cards.CHANNEL)
    assert any(new.id in text and f"> {WORDS}" in text for text in posted)
    assert sent == []  # nothing goes out on a reword


def test_iw_s1_a_brand_refusal_answers_with_the_reasons_and_leaves_the_card_open(conn, box, sent, discord_double):
    item, old = carded(conn, box)

    body = remote("inbox", "reword", old.id, "Thanks!")

    assert body["exit_code"] == 1 and "exclamation" in body["text"].lower() and body["answer"] == "refused"
    assert approvals.get(conn, old.id).status == approvals.PENDING
    assert reload(conn, item)["draft"] == DRAFT
    assert reload(conn, item)["brand_failures"] == 0  # D8's two strikes aren't for his words


def test_iw_s1_a_draft_that_would_be_masked_on_the_card_is_refused(conn, box, sent, discord_double):
    _, old = carded(conn, box)
    body = remote("inbox", "reword", old.id, "Call", "+65", "9123", "4567", "please")
    assert body["exit_code"] == 1 and approvals.get(conn, old.id).status == approvals.PENDING


def test_iw_n9_a_paragraph_break_survives_dispatchs_split(conn, box, sent, discord_double):
    item, old = carded(conn, box)
    remote("inbox", "reword", old.id, "First", "line.", "//", "Second", "line.")
    assert reload(conn, item)["draft"] == "First line.\n\nSecond line."

    newer = request_for(conn, item)
    remote("inbox", "reword", newer.id, "Third", "line.", "\\n\\n", "Fourth", "line.")
    assert reload(conn, item)["draft"] == "Third line.\n\nFourth line."


def test_iw_n9_a_link_keeps_its_slashes(conn, box, sent, discord_double):
    item, old = carded(conn, box)
    assert remote("inbox", "reword", old.id, "See", "https://jurasolutions.sg", "for", "more.")["exit_code"] == 0
    assert reload(conn, item)["draft"] == "See https://jurasolutions.sg for more."


def test_iw_d6_words_that_change_nothing_raise_nothing(conn, box, sent, discord_double):
    item, old = carded(conn, box)
    body = remote("inbox", "reword", old.id, *DRAFT.split("\n\n")[0].split(), "//", *DRAFT.split("\n\n")[1].split())
    assert body["exit_code"] == 1 and "already" in body["text"]
    assert request_for(conn, item).id == old.id


def test_iw_f10_a_reword_that_promises_a_reply_is_promised(conn, box, sent, discord_double):
    item, old = carded(conn, box)
    assert not reload(conn, item)["promised"]
    remote("inbox", "reword", old.id, *WORDS.split())
    assert reload(conn, item)["promised"] == 1


def test_iw_d6_a_reworded_card_when_approved_sends_his_words_exactly(conn, box, sent, discord_double, monkeypatch):
    from jura_growth.agents.inbox import send

    item, old = carded(conn, box)
    remote("inbox", "reword", old.id, *WORDS.split())
    assert decide(conn, request_for(conn, item), "approve", monkeypatch).answer == "recorded"
    send.send_due(conn)
    [request] = sent
    assert json.loads(request.content)["text"].startswith(WORDS + "\n\n")


def closed_in(conn, box, monkeypatch, how: str):
    """A card in each state a change must refuse, and the words that should say why."""
    item, record = carded(conn, box)
    if how == "approved":
        decide(conn, record, "approve", monkeypatch)
        return record, "already approved"
    if how == "skipped":
        decide(conn, record, "skip", monkeypatch)
        return record, "skipped"
    if how == "lapsed":
        monkeypatch.setenv("JURA_GROWTH_NOW", "2026-10-30T10:00:00+08:00")
        return record, "lapsed"
    if how == "superseded":
        box.messages.append(raw_mail(subject="A question about invoices", body="And another thing."))
        mail.intake(conn)
        return record, "wrote again"
    if how == "claimed":
        decide(conn, record, "approve", monkeypatch)
        with db.transaction(conn):
            approvals.use(conn, kinds.KIND, kinds.subject_of(item["id"]), run_id=None)
            store.set_item_state(conn, item["id"], store.SENDING)
        return record, "claimed"
    raise AssertionError(how)


@pytest.mark.parametrize("command", ["reword", "redraft"])
@pytest.mark.parametrize("how", ["approved", "skipped", "lapsed", "superseded", "claimed"])
def test_iw_s1_each_change_refuses_a_decided_lapsed_superseded_or_claimed_card_and_says_why(conn, box, sent, discord_double, monkeypatch, command, how):
    record, why = closed_in(conn, box, monkeypatch, how)
    rows = db.scalar(conn, "SELECT count(*) FROM approvals")

    body = remote("inbox", command, record.id, "Plain", "and", "warm.")

    assert body["exit_code"] == 1, body
    assert why in body["text"], body["text"]
    assert db.scalar(conn, "SELECT count(*) FROM approvals") == rows
    assert not db.scalar(conn, "SELECT asked_at FROM inbox_items WHERE id = ?", (kinds.item_id_of(record.subject),))


@pytest.mark.parametrize("command", ["reword", "redraft"])
def test_iw_d6_only_an_inbox_reply_can_be_changed(conn, box, sent, discord_double, command):
    assert "no approval request" in remote("inbox", command, "A-9999", "words")["text"]
    conn.execute(
        "INSERT INTO approvals (id, kind, subject, content_hash, status, reason, requested_at, decide_by) "
        "VALUES (77, 'outreach-email', 'outreach_message:1', 'x', 'pending', 'r', '2026-10-26T09:00:00+08:00', '2026-10-29T09:00:00+08:00')"
    )
    conn.commit()
    assert "isn't an inbox reply" in remote("inbox", command, "A-0077", "words")["text"]


def test_iw_d6_what_he_typed_stays_out_of_the_log_that_is_never_pruned(conn, box, sent, discord_double):
    """`events` and its mirror can't be deleted from, so his draft and guidance don't go there (N6)."""
    _, old = carded(conn, box)
    remote("inbox", "reword", old.id, "Hi", "Priya,", "thanks", "for", "asking.")
    mirrored = "\n".join(path.read_text() for path in (paths.data_dir() / "runs").glob("*.jsonl"))
    [event] = [json.loads(row["payload_json"]) for row in db.rows(conn, "SELECT payload_json FROM events WHERE kind = 'remote.command'")]
    assert event["words"][:3] == ["inbox", "reword", old.id] and "thanks" not in event["words"]
    assert "thanks for asking" not in mirrored and "Priya," not in mirrored


# --- redraft -----------------------------------------------------------------------------------------


def test_iw_d6_a_redraft_keeps_the_card_open_and_hands_the_conversation_to_triage(conn, box, sent, discord_double):
    item, old = carded(conn, box)

    body = remote("inbox", "redraft", old.id, "shorter,", "and", "ask", "what", "they", "use", "today")

    assert body["exit_code"] == 0 and "15 minutes" in body["text"]
    assert approvals.get(conn, old.id).status == approvals.PENDING
    assert triage.waiting(conn)
    [given] = triage.hand_out(conn)["conversations"]
    assert given["guidance"] == "shorter, and ask what they use today"
    assert given["must_draft"] is True and given["earlier_draft"] == DRAFT
    assert given["id"] == store.label(item["id"])


def test_iw_d6_the_old_card_closes_only_as_the_new_one_exists(conn, box, sent, discord_double):
    item, old = carded(conn, box)
    remote("inbox", "redraft", old.id, "shorter")

    triaged(conn, item, draft="We help with invoices.")

    new = request_for(conn, item)
    assert new.id != old.id and new.supersedes == old.number and new.status == approvals.PENDING
    assert approvals.get(conn, old.id).status == approvals.SUPERSEDED
    found = reload(conn, item)
    assert found["draft"] == "We help with invoices." and found["state"] == store.WAITING and found["asked_at"] is None
    assert not triage.waiting(conn)


def test_iw_d6_a_redraft_cant_be_answered_with_no_draft(conn, box, sent, discord_double):
    item, old = carded(conn, box)
    remote("inbox", "redraft", old.id, "shorter")
    outcome = triage.submit(conn, {"id": store.label(item["id"]), "class": "thanks"})
    assert outcome.exit_code == 2 and "asked for a draft" in outcome.text()
    assert approvals.get(conn, old.id).status == approvals.PENDING


def test_iw_s1_two_brand_refusals_of_a_redraft_leave_the_old_card_open_and_tell_him(conn, box, sent, discord_double):
    item, old = carded(conn, box)
    remote("inbox", "redraft", old.id, "shorter")

    for _ in range(2):
        outcome = triage.submit(conn, {"id": store.label(item["id"]), "class": "question", "draft": "Thanks!"})
        assert outcome.exit_code == 1

    assert approvals.get(conn, old.id).status == approvals.PENDING
    found = reload(conn, item)
    assert found["draft"] == DRAFT and found["state"] == store.WAITING and found["asked_at"] is None
    assert not triage.waiting(conn)
    report.report_due(conn)
    assert any("redraft" in text and old.id in text for text in discord_double.contents(report.CHANNEL))


def test_iw_s1_a_redraft_out_of_attempts_leaves_the_old_card_open_and_tells_him(conn, box, sent, discord_double):
    item, old = carded(conn, box)
    remote("inbox", "redraft", old.id, "shorter")
    store.set_attempts(conn, [item["id"]], caps.INBOX_TRIAGE_ATTEMPTS)
    conn.commit()

    triage.settle(conn)
    report.report_due(conn)

    assert approvals.get(conn, old.id).status == approvals.PENDING
    found = reload(conn, item)
    assert found["state"] == store.WAITING and found["asked_at"] is None
    assert any("redraft" in text and old.id in text for text in discord_double.contents(report.CHANNEL))


def test_iw_s1_approving_the_old_card_while_a_redraft_waits_drops_the_redraft(conn, box, sent, discord_double, monkeypatch):
    item, old = carded(conn, box)
    remote("inbox", "redraft", old.id, "shorter")
    decide(conn, old, "approve", monkeypatch)

    triage.settle(conn)

    found = reload(conn, item)
    assert found["asked_at"] is None and found["draft"] == DRAFT
    assert not triage.waiting(conn)
    assert approvals.get(conn, old.id).status == approvals.APPROVED


def test_iw_d5_they_write_again_while_a_redraft_waits_and_the_new_draft_answers_all_of_it(conn, box, sent, discord_double):
    item, old = carded(conn, box)
    remote("inbox", "redraft", old.id, "shorter")
    newer = arrives(conn, box, raw_mail(subject="A question about invoices", body="And another thing."))
    [given] = triage.hand_out(conn)["conversations"]
    assert given["id"] == store.label(newer["id"]) and given["guidance"] == "shorter"

    triaged(conn, newer, draft="We help with invoices.")

    assert reload(conn, item)["state"] == store.SUPERSEDED and reload(conn, item)["asked_at"] is None
    assert reload(conn, newer)["state"] == store.WAITING


# --- draft -------------------------------------------------------------------------------------------


def reported(conn, box, **kwargs) -> dict:
    item = arrives(conn, box, raw_mail(**kwargs))
    assert triage.submit(conn, {"id": store.label(item["id"]), "class": "thanks"}).exit_code == 0
    return reload(conn, item)


def test_iw_s2_every_report_carries_its_id_and_a_no_reply_report_says_how_to_ask_for_one(conn, box, sent, discord_double):
    item = reported(conn, box)
    report.report_due(conn)
    [post] = discord_double.contents(report.CHANNEL)
    label = store.label(item["id"])
    assert label in post and f"`/growth inbox draft {label} [guidance]`" in post


def test_iw_s2_a_draft_asks_triage_for_one_where_the_model_said_none(conn, box, sent, discord_double):
    item = reported(conn, box)

    body = remote("inbox", "draft", store.label(item["id"]), "say", "hello", "back")

    assert body["exit_code"] == 0
    found = reload(conn, item)
    assert found["state"] == store.NEW and found["guidance"] == "say hello back" and found["asked_at"]
    [given] = triage.hand_out(conn)["conversations"]
    assert given["guidance"] == "say hello back" and given["must_draft"] is True

    outcome = triage.submit(conn, {"id": store.label(item["id"]), "class": "thanks"})
    assert outcome.exit_code == 2 and "asked for a draft" in outcome.text()

    triaged(conn, item)
    assert request_for(conn, item).status == approvals.PENDING
    assert reload(conn, item)["asked_at"] is None


def test_iw_s2_a_draft_needs_no_guidance(conn, box, sent, discord_double):
    item = reported(conn, box)
    assert remote("inbox", "draft", store.label(item["id"]))["exit_code"] == 0
    assert reload(conn, item)["state"] == store.NEW


def test_iw_s2_a_draft_answers_the_conversations_newest_message(conn, box, sent, discord_double):
    first = reported(conn, box)
    second = arrives(conn, box, raw_mail(subject="A question about invoices", body="Thanks again."))
    triage.submit(conn, {"id": store.label(second["id"]), "class": "thanks"})

    assert remote("inbox", "draft", store.label(first["id"]))["exit_code"] == 0

    assert reload(conn, first)["state"] == store.REPORTED
    assert reload(conn, second)["state"] == store.NEW


@pytest.mark.parametrize("state, word", [(store.SENT, "already went"), (store.UNVERIFIED, "unverified"), (store.BASELINE, "never"), (store.OWN, "the Page's own")])
def test_iw_s2_a_draft_refuses_what_cant_have_one(conn, box, sent, discord_double, state, word):
    item = reported(conn, box)
    with db.transaction(conn):
        store.set_item_state(conn, item["id"], state)
    body = remote("inbox", "draft", store.label(item["id"]))
    assert body["exit_code"] == 1 and word in body["text"]
    assert reload(conn, item)["state"] == state


def test_iw_d2_a_draft_refuses_a_reply_resend_refused(conn, box, sent, discord_double):
    """A new draft would go under the item's one idempotency key, which Resend has already answered."""
    item = reported(conn, box)
    with db.transaction(conn):
        store.set_item_state(conn, item["id"], store.FAILED)
    body = remote("inbox", "draft", store.label(item["id"]))
    assert body["exit_code"] == 1 and "Resend refused" in body["text"]


def test_iw_s2_a_draft_points_at_the_card_when_there_is_one(conn, box, sent, discord_double):
    item, old = carded(conn, box)
    body = remote("inbox", "draft", store.label(item["id"]))
    assert body["exit_code"] == 1 and old.id in body["text"] and "redraft" in body["text"]


def test_iw_s16_a_junk_message_never_gets_a_draft(conn, box, sent, discord_double):
    box.folders["Junk"].append(raw_mail("Somebody <a@elsewhere.example>", subject="Junk one", body="Hello"))
    mail.intake(conn)
    [item] = db.rows(conn, "SELECT * FROM inbox_items WHERE state = 'noise'")
    body = remote("inbox", "draft", store.label(item["id"]))
    assert body["exit_code"] == 1 and "no words" in body["text"]


def test_iw_e2_a_suppressed_person_gets_no_draft_and_the_answer_says_how_to_lift_it(conn, box, sent, discord_double):
    item = reported(conn, box)
    with db.transaction(conn):
        suppression.add(conn, email=PRIYA, reason="unsubscribe", source="reply")
    body = remote("inbox", "draft", store.label(item["id"]))
    assert body["exit_code"] == 1 and "unsuppress" in body["text"]


def test_iw_s2_an_unknown_id_is_refused(conn, box, sent, discord_double):
    assert "no inbox item" in remote("inbox", "draft", "I-9999")["text"]
    assert remote("inbox", "draft", "A-0001")["answer"] == "refused"


# --- done --------------------------------------------------------------------------------------------


def test_iw_f10_done_clears_a_promised_reply_from_the_list(conn, box, sent, discord_double, monkeypatch):
    from jura_growth.agents.inbox import send

    item, _ = approved(conn, box, monkeypatch, draft=WORDS)
    send.send_due(conn)
    label = store.label(item["id"])
    assert reload(conn, item)["state"] == store.NEEDS_HAND_REPLY
    assert label in CliRunner().invoke(cli, ["inbox", "list"]).output

    body = remote("inbox", "done", label)

    assert body["exit_code"] == 0
    found = reload(conn, item)
    assert found["state"] == store.DONE and found["closed_at"]
    assert label not in CliRunner().invoke(cli, ["inbox", "list"]).output


def test_iw_s2_done_takes_the_conversations_hand_replies(conn, box, sent, discord_double):
    first = arrives(conn, box)
    second = arrives(conn, box, raw_mail(subject="A question about invoices", body="And more."))
    with db.transaction(conn):
        store.set_item_state(conn, first["id"], store.NEEDS_HAND_REPLY)
        store.set_item_state(conn, second["id"], store.NEEDS_HAND_REPLY)
    remote("inbox", "done", store.label(first["id"]))
    assert reload(conn, first)["state"] == reload(conn, second)["state"] == store.DONE


@pytest.mark.parametrize("state", [store.LAPSED, store.FAILED, store.UNKNOWN, store.UNVERIFIED])
def test_iw_s2_done_clears_a_lapsed_or_uncertain_line_too(conn, box, sent, discord_double, state):
    item = arrives(conn, box)
    with db.transaction(conn):
        store.set_item_state(conn, item["id"], state)
    assert remote("inbox", "done", store.label(item["id"]))["exit_code"] == 0
    assert reload(conn, item)["state"] == store.DONE


def test_iw_n13_done_on_an_unknown_item_never_sends_it(conn, box, sent, discord_double):
    from jura_growth.agents.inbox import send

    item = arrives(conn, box)
    with db.transaction(conn):
        store.set_item_state(conn, item["id"], store.UNKNOWN)
    remote("inbox", "done", store.label(item["id"]))
    send.send_due(conn)
    assert sent == []


def test_iw_s2_done_on_an_open_card_says_to_skip_it(conn, box, sent, discord_double):
    item, old = carded(conn, box)
    body = remote("inbox", "done", store.label(item["id"]))
    assert body["exit_code"] == 1 and f"skip {old.id}" in body["text"]
    assert reload(conn, item)["state"] == store.WAITING


def test_iw_s2_done_with_nothing_open_says_so(conn, box, sent, discord_double):
    item = reported(conn, box)
    body = remote("inbox", "done", store.label(item["id"]))
    assert body["exit_code"] == 0 and "nothing open" in body["text"]
    assert reload(conn, item)["state"] == store.REPORTED


# --- unsuppress ----------------------------------------------------------------------------------------


def test_iw_e2_triages_opt_out_note_names_the_way_back(conn, box, sent, discord_double):
    item = arrives(conn, box, raw_mail(body="Please leave me out of this."))
    store.set_item_state(conn, item["id"], store.NEW)
    with db.transaction(conn):
        conn.execute("UPDATE inbox_items SET thread_json = json_set(thread_json, '$.own_sender', 1) WHERE id = ?", (item["id"],))
    outcome = triage.submit(conn, {"id": store.label(item["id"]), "class": "opt-out"})
    assert outcome.exit_code == 0
    assert f"/growth inbox unsuppress {store.label(item['id'])}" in reload(conn, item)["note"]
    assert suppression.is_suppressed(conn, PRIYA)


def lead_with_contact(conn) -> int:
    now = "2026-10-20T09:00:00+08:00"
    conn.execute("INSERT INTO leads (id, company, display_name, domain, website, industry, score, score_reasons, channel, status, created_at, updated_at) "
                 "VALUES (50, 'Clinic', 'Clinic', 'clinic.example', 'https://clinic.example', 'health', 70, '[]', 'email', 'unsubscribed', ?, ?)", (now, now))
    conn.execute("INSERT INTO contacts (lead_id, email, email_hash, source_url, kind, mx_ok, verified_at, created_at) "
                 "VALUES (50, ?, ?, 'https://clinic.example', 'named', 1, ?, ?)", (PRIYA, suppression.email_hash(PRIYA), now, now))
    return 50


def test_iw_e2_unsuppress_lifts_a_reply_suppression_and_restores_the_lead(conn, box, sent, discord_double):
    item = arrives(conn, box)
    lead = lead_with_contact(conn)
    with db.transaction(conn):
        suppression.add(conn, email=PRIYA, reason="unsubscribe", source="reply")
        conn.execute("UPDATE inbox_items SET lead_id = ? WHERE id = ?", (lead, item["id"]))
        conn.execute("INSERT INTO outreach_replies (lead_id, contact_id, message_key, received_at, unsubscribe, detected_at) "
                     "SELECT 50, id, ?, ?, 1, ? FROM contacts WHERE lead_id = 50", (item["key"], item["recorded_at"], item["recorded_at"]))

    body = remote("inbox", "unsuppress", store.label(item["id"]))

    assert body["exit_code"] == 0
    assert suppression.is_suppressed(conn, PRIYA) is None
    assert db.scalar(conn, "SELECT status FROM leads WHERE id = 50") == "replied"
    assert db.scalar(conn, "SELECT unsubscribe FROM outreach_replies WHERE lead_id = 50") == 0
    event = db.one(conn, "SELECT payload_json FROM events WHERE kind = 'suppression.lifted'")
    assert PRIYA not in event["payload_json"]


@pytest.mark.parametrize("reason, source", [("unsubscribe", "d1:link"), ("bounce", "d1:resend"), ("complaint", "d1:resend"), ("manual", "cli")])
def test_iw_e2_unsuppress_lifts_only_a_suppression_that_came_from_a_reply(conn, box, sent, discord_double, reason, source):
    item = arrives(conn, box)
    with db.transaction(conn):
        suppression.add(conn, email=PRIYA, reason=reason, source=source)
    body = remote("inbox", "unsuppress", store.label(item["id"]))
    assert body["exit_code"] == 1 and "didn't come from a reply" in body["text"]
    assert suppression.is_suppressed(conn, PRIYA)


@pytest.mark.parametrize("source", ["d1:link", "manual", "cli"])
def test_iw_e2_lifting_itself_takes_only_a_replys_entry(conn, source):
    """The core's own rule, under the command's check: entries of any other kind are kept indefinitely."""
    with db.transaction(conn):
        suppression.add(conn, email=PRIYA, reason="unsubscribe", source=source)
        assert suppression.lift_reply(conn, PRIYA) is False
    assert suppression.is_suppressed(conn, PRIYA)


def test_iw_e2_unsuppress_never_lifts_a_whole_domain(conn, box, sent, discord_double):
    item = arrives(conn, box)
    with db.transaction(conn):
        suppression.add(conn, domain="clinic.example", reason="manual", source="reply")
    assert remote("inbox", "unsuppress", store.label(item["id"]))["exit_code"] == 1
    assert suppression.is_suppressed(conn, PRIYA)


def test_iw_e2_unsuppress_with_nothing_to_lift_says_so(conn, box, sent, discord_double):
    item = arrives(conn, box)
    body = remote("inbox", "unsuppress", store.label(item["id"]))
    assert body["exit_code"] == 1 and "isn't suppressed" in body["text"]


@pytest.mark.parametrize("rows", [[{"email_hash": suppression.email_hash(PRIYA), "reason": "unsubscribe", "source": "link"}], "down"])
def test_iw_e2_unsuppress_refuses_when_the_website_also_lists_them_or_cant_say(conn, box, sent, discord_double, monkeypatch, rows):
    """A click on the website also suppressed them, or D1 can't answer: lifting would mail someone who
    said stop, because the sync's cursor has moved past that event."""
    import httpx

    fake_d1(monkeypatch, rows if rows != "down" else lambda request: httpx.Response(500, json={"success": False}))
    item = arrives(conn, box)
    with db.transaction(conn):
        suppression.add(conn, email=PRIYA, reason="unsubscribe", source="reply")
    body = remote("inbox", "unsuppress", store.label(item["id"]))
    assert body["exit_code"] == 1, body
    assert suppression.is_suppressed(conn, PRIYA)


def test_iw_e2_a_lifted_person_can_then_have_a_draft(conn, box, sent, discord_double):
    item = reported(conn, box)
    with db.transaction(conn):
        suppression.add(conn, email=PRIYA, reason="unsubscribe", source="reply")
    label = store.label(item["id"])
    assert remote("inbox", "draft", label)["exit_code"] == 1
    assert remote("inbox", "unsuppress", label)["exit_code"] == 0
    assert remote("inbox", "draft", label)["exit_code"] == 0


def test_iw_e2_a_social_item_has_no_address_to_lift(conn, box, sent, discord_double):
    store.record(conn, store.Reaction(source="facebook-comment", key="k", conversation="k", sender_name="Mei", text="Hello", state=store.REPORTED))
    conn.commit()
    [row] = db.rows(conn, "SELECT id FROM inbox_items")
    body = remote("inbox", "unsuppress", store.label(row["id"]))
    assert body["exit_code"] == 1 and "no address" in body["text"]


# --- only a human origin -------------------------------------------------------------------------------


@pytest.mark.parametrize("name", STEERING + ("inbox list",))
def test_iw_d6_each_is_on_the_allowlist_and_never_for_a_run(name):
    assert name in remote_mod.ALLOWLIST
    assert headless.never(name)
    assert headless.never(f"{name} A-0001 words")


@pytest.mark.parametrize("words", [("inbox", "reword", "A-0001", "x"), ("inbox", "redraft", "A-0001", "x"), ("inbox", "draft", "I-0001"),
                                   ("inbox", "done", "I-0001"), ("inbox", "unsuppress", "I-0001")])
def test_iw_a1_typed_in_terminal_they_refuse_and_change_nothing(conn, box, sent, words):
    result = CliRunner().invoke(cli, list(words))
    assert result.exit_code == 2 and "refused:" in result.output


@pytest.mark.parametrize("reason", [origin.NOT_DISPATCH, origin.IN_CLAUDE])
def test_iw_a1_a_refused_origin_reaches_none_of_them(conn, box, sent, discord_double, reason):
    item, old = carded(conn, box)
    for words in (("inbox", "reword", old.id, *WORDS.split()), ("inbox", "redraft", old.id, "x"), ("inbox", "done", store.label(item["id"]))):
        body = remote(*words, origin_=Origin.refused(reason))
        assert body["exit_code"] == 2
    assert reload(conn, item)["draft"] == DRAFT and approvals.get(conn, old.id).status == approvals.PENDING


@pytest.mark.parametrize("words", [("inbox", "reword", "A-0001", "x"), ("inbox", "redraft", "A-0001", "x"), ("inbox", "draft", "I-0001"),
                                   ("inbox", "done", "I-0001"), ("inbox", "unsuppress", "I-0001"), ("inbox", "list")])
def test_iw_a1_a_scheduled_run_is_refused_by_the_real_child(monkeypatch, conn, words):
    monkeypatch.setenv("JURA_GROWTH_JOB", "inbox-check")
    result = CliRunner().invoke(cli, list(words), obj={"origin": Origin.ssh(), "actor": "discord:111"})
    assert result.exit_code == 2 and "refused" in result.output


def test_iw_a1_a_person_cant_steer_triage_into_steering(conn):
    """The commands triage may use stay its two, whatever anyone writes."""
    declared = headless.permissions("inbox-check").commands
    assert set(declared) == {"inbox pending", "inbox submit"}
    allowed, disallowed = headless.claude_rules("inbox-check")
    for name in STEERING:
        assert f"Bash(jura-growth {name}:*)" in disallowed and f"Bash(jura-growth {name}:*)" not in allowed


# --- what remote refuses before it runs ----------------------------------------------------------------


@pytest.mark.parametrize("words", [("inbox", "reword", "A-0001"), ("inbox", "reword", "I-0001", "x"), ("inbox", "reword", "--help", "x"),
                                   ("inbox", "redraft", "A-0001"), ("inbox", "draft"), ("inbox", "draft", "A-0001"),
                                   ("inbox", "done"), ("inbox", "done", "I-0001", "x"), ("inbox", "unsuppress"), ("inbox", "unsuppress", "I-1", "x"),
                                   ("inbox", "list", "x")])
def test_iw_d6_the_wrong_shape_is_refused_before_it_runs(conn, words):
    body = remote(*words)
    assert body["exit_code"] == 2 and body["text"].startswith("refused:"), body


def test_iw_d6_a_word_that_looks_like_an_option_is_only_a_word(conn, box, sent, discord_double):
    item, old = carded(conn, box)
    assert remote("inbox", "redraft", old.id, "--help", "-x")["exit_code"] == 0
    assert reload(conn, item)["guidance"] == "--help -x"


# --- pause, S6 -------------------------------------------------------------------------------------------


@pytest.mark.parametrize("agent", ["inbox", "all"])
def test_iw_s6_a_paused_inbox_takes_no_change_that_would_raise_a_card(conn, box, sent, discord_double, agent):
    item, old = carded(conn, box)
    pause.pause(conn, agent, "a test", notify=False)
    conn.commit()
    for words in (("inbox", "reword", old.id, *WORDS.split()), ("inbox", "redraft", old.id, "x"), ("inbox", "draft", store.label(item["id"]))):
        body = remote(*words)
        assert body["exit_code"] == 1 and "paused" in body["text"]
    assert approvals.get(conn, old.id).status == approvals.PENDING


def test_iw_s6_a_paused_inbox_still_lists_and_clears(conn, box, sent, discord_double):
    item = arrives(conn, box)
    with db.transaction(conn):
        store.set_item_state(conn, item["id"], store.NEEDS_HAND_REPLY)
    pause.pause(conn, "inbox", "a test", notify=False)
    conn.commit()
    assert store.label(item["id"]) in remote("inbox", "list")["text"]
    assert remote("inbox", "done", store.label(item["id"]))["exit_code"] == 0


@pytest.mark.parametrize("flag, stopped, running", [
    ("inbox", {"inbox-check", "inbox-send"}, {"inbox-watch", "inbox-reply"}),
    ("inbox-browser", {"inbox-watch", "inbox-reply"}, {"inbox-check", "inbox-send"}),
    ("all", {"inbox-check", "inbox-send", "inbox-watch", "inbox-reply"}, set()),
])
def test_iw_s6_each_flag_stops_its_own_jobs_through_remote(conn, flag, stopped, running):
    """The runner's own pause check on these agents is proved in test_inbox_watch_run and test_core."""
    agent_of = {"inbox-check": "inbox", "inbox-send": "inbox", "inbox-watch": "inbox-browser", "inbox-reply": "inbox-browser"}
    assert remote("pause", flag)["exit_code"] == 0
    for name in stopped | running:
        assert bool(pause.is_paused(conn, agent_of[name])) is (name in stopped), name


def test_iw_s10_a_precheck_in_hours_counts_a_redraft_as_work_for_triage(conn, box, sent, discord_double, monkeypatch):
    _, old = carded(conn, box)
    remote("inbox", "redraft", old.id, "shorter")
    assert job.precheck(conn) is None  # Claude starts, for the redraft alone

