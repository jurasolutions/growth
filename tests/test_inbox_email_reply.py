"""Approve an email reply and it goes out threaded (inbox watch ticket 03).

The mail is real bytes through the strict IMAP double, triage comes in at `triage.submit`, decisions
come through the only origin that decides, Resend is `httpx.MockTransport` with assertions on the whole
JSON request, and Discord is the double. The matrix for this kind is in `gate_adapter_email_reply.py`.
"""

from __future__ import annotations

import dataclasses
import json

import httpx
import pytest
import yaml

import approval_world as aw
import publish_fake
from discord_double import discord_double  # noqa: F401
from inbox_world import DKIM_FAIL, NOW, enquiry_mail, mailbox_env, raw_mail, trust_servers
from jura_growth import approvals, caps, cards, config, db, discord, headless, pause, paths, privacy, runner, suppression
from jura_growth.agents.inbox import kinds, mail, report, send, store, triage
from jura_growth.agents.outreach import replies
from jura_growth.cli import cli
from click.testing import CliRunner
from test_outreach_sync import live_sends
from test_scout_support import at, buttons, decide, fake_d1, fake_resend, live_ready, scout_env  # noqa: F401

LEVI = "levi@jurasolutions.sg"
DRAFT = "We help with invoices and the copying between systems that follows.\n\nThe first step is a short discovery call."
PRIYA = "priya@clinic.example"
LONG_DRAFT = " ".join(["Plain"] * 179)  # under 180 words
WIDE_DRAFT = "\n".join(" ".join(["Understood"] * 4) for _ in range(27))  # near the character and line limits
HOLDING = "I am sorry to hear this. I will reply to you personally."


@pytest.fixture
def box(scout_env, conn, monkeypatch):  # noqa: F811
    """A mailbox, every switch on, and the clock on a Monday morning."""
    live_ready(monkeypatch)
    trust_servers(monkeypatch)
    at(monkeypatch, NOW)
    return mailbox_env(monkeypatch, [])


@pytest.fixture
def sent(monkeypatch) -> list:
    return fake_resend(monkeypatch)


def bodies(requests: list) -> list[dict]:
    return [json.loads(request.content) for request in requests]


def only_item(conn) -> dict:
    [item] = db.rows(conn, "SELECT * FROM inbox_items")
    return item


def arrives(conn, box, raw: bytes) -> dict:
    """The mail comes in, as a check would read it. Returns the newest inbox item."""
    box.messages.append(raw)
    mail.intake(conn)
    return db.rows(conn, "SELECT * FROM inbox_items ORDER BY id DESC LIMIT 1")[0]


def triaged(conn, item: dict, *, draft: str = DRAFT, kind: str = "question", **rest) -> triage.Submitted:
    outcome = triage.submit(conn, {"id": store.label(item["id"]), "class": kind, "draft": draft, **rest})
    assert outcome.exit_code == 0, outcome.text()
    return outcome


def carded(conn, box, raw: bytes | None = None, **rest) -> tuple[dict, approvals.Approval]:
    """Someone writes in and triage drafts: the item and its pending request."""
    item = arrives(conn, box, raw or raw_mail())
    triaged(conn, item, **rest)
    return store.get(conn, item["id"]), request_for(conn, item)


def request_for(conn, item: dict) -> approvals.Approval:
    found = approvals.latest(conn, kinds.KIND, kinds.subject_of(item["id"]))
    assert found is not None, "no request was raised"
    return found


def approved(conn, box, monkeypatch, raw: bytes | None = None, **rest) -> tuple[dict, approvals.Approval]:
    item, record = carded(conn, box, raw, **rest)
    assert decide(conn, record, "approve", monkeypatch).answer == "recorded"
    return item, record


def card_of(discord_double, record: approvals.Approval):  # noqa: F811
    [card] = [r for r in discord_double.requests if r.channel == "approvals" and r.method == "POST" and record.id in (r.content or "")]
    return card


def draft_on(card) -> str:
    """The draft as a card shows it, each line under its quote mark, as Ting Yu reads it."""
    lines = card.content.split("\n")
    start = lines.index("Draft, exactly as it goes out, with Levi's signature under it:") + 1
    end = next(n for n, line in enumerate(lines) if line.startswith("Template: "))
    return "\n".join(line.removeprefix(">").removeprefix(" ") for line in lines[start:end])


def lines_in(discord_double, channel: str) -> list[str]:  # noqa: F811
    return [r.content for r in discord_double.requests if r.channel == channel]


def raw_bytes(*headers: str, body: str = "Do you work with clinics?") -> bytes:
    """Mail no well-behaved library would write: exactly these header lines, as a server hands them over."""
    base = ["Date: Mon, 26 Oct 2026 09:30:00 +0800", "To: levi@jurasolutions.sg"]
    return "\r\n".join([*base, *headers, "", body, ""]).encode("utf-8")


# --- D1, B3, B8, F-S5, F-S6: the card ------------------------------------------------------------


def test_iw_d1_f_s6_the_card_shows_what_they_said_who_where_the_draft_and_each_next_step(conn, box, discord_double, sent):  # noqa: F811
    """IW-D1, IW-F-S6: one card with Approve and Skip, and what each answer does."""
    item, record = carded(conn, box, raw_mail("Priya Nair <priya@clinic.example>"))

    card = card_of(discord_double, record)

    assert draft_on(card) == DRAFT
    assert "Do you work with clinics?" in card.content
    assert "Priya Nair" in card.content and "p***@clinic.example" in card.content and PRIYA not in card.content
    assert "Approve: sends as Levi within 10 minutes, or at 08:00 if it's after 22:00." in card.content
    assert "Skip: nothing goes out. Use this too if you've answered by hand." in card.content
    assert f"/growth inbox redraft {record.id}" in card.content and f"/growth inbox reword {record.id}" in card.content
    assert [button["label"] for row in card.components for button in row["components"]] == ["Approve", "Skip"]
    assert sent == [], "a card asks. Nothing has gone out"


def test_iw_d1_the_kind_declares_its_feed_for_when_approvals_first_lands():
    """Technical review, "Merging": inert until then, because `feed.py` reads both with getattr."""
    kind = kinds.EmailReply()
    assert kind.feed_channel == "mission-control" and "within 10 minutes" in kind.feed_approved


def test_iw_d1_the_cards_first_line_after_the_header_names_no_person(conn, box, discord_double, sent):  # noqa: F811
    """Technical review, "Merging": `feed._card_title` posts that line through plain masking."""
    _, record = carded(conn, box, raw_mail("Priya Nair <priya@clinic.example>"))

    assert card_of(discord_double, record).content.split("\n")[1] == "Email reply"


def test_iw_b3_hi_jane_reaches_the_card_unchanged_and_stays_when_it_is_decided(conn, box, discord_double, monkeypatch, sent):  # noqa: F811
    """IW-B3: a learned name masks a greeting elsewhere, and the card's edit mustn't re-mask it."""
    privacy.remember_address("jane.tan@acme.example")
    item = arrives(conn, box, raw_mail("Jane Tan <jane.tan@acme.example>", body="Hello from Jane."))
    triaged(conn, item, draft="Hi Jane,\n\nThanks for writing.")
    record = request_for(conn, item)

    assert "> Hi Jane," in card_of(discord_double, record).content.split("\n")

    decide(conn, record, "approve", monkeypatch)
    cards.sweep(conn)

    [edit] = [r for r in discord_double.requests if r.channel == "approvals" and r.method == "PATCH"]
    assert edit.content.startswith(f"**{record.id} · email reply** · Approved by Ting Yu")
    assert "> Hi Jane," in edit.content.split("\n") and "Jane Tan" in edit.content and "[name removed]" not in edit.content


@pytest.mark.parametrize("length", [10, 500, 1000, 1500, 1900, 2500, 3999, 4000])
@pytest.mark.parametrize("draft", [DRAFT, LONG_DRAFT, WIDE_DRAFT], ids=["short", "long", "wide"])
def test_iw_d1_b8_f_s5_a_card_is_one_message_at_every_length_and_the_draft_is_never_cut(conn, box, discord_double, sent, length, draft):  # noqa: F811
    """IW-B8, IW-F-S5, IW-A6: the quote gives way, with a pointer to the rest."""
    words = ("word " * 1000)[:length].strip()
    _, record = carded(conn, box, raw_mail(body=words, subject="A question " + "s" * 200), draft=draft)

    card = card_of(discord_double, record)

    assert len(card.content) <= discord.MAX_CONTENT
    assert len([r for r in discord_double.requests if r.channel == "approvals"]) == 1
    assert draft_on(card) == draft, "every byte of it"
    assert card.components, "the buttons are on the one message"
    if length >= 2500:
        assert report.CUT_NOTE in card.content


def test_iw_b8_a_draft_of_many_lines_is_refused_because_each_takes_a_quote_mark(conn, box, sent):
    """IW-B8: at the character limit, one line to a word would pass 2,000 on the card."""
    item = arrives(conn, box, raw_mail())

    refused = triage.submit(conn, {"id": store.label(item["id"]), "class": "question", "draft": "\n".join(["Plain"] * (caps.INBOX_EMAIL_DRAFT_LINES + 1))})

    assert refused.exit_code == 1 and "lines" in refused.text()


def test_iw_b8_masking_that_lengthens_the_quote_doesnt_split_the_card(conn, box, discord_double, sent):  # noqa: F811
    """IW-B8: measured as masked, because `[phone removed]` is longer than a number."""
    numbers = " ".join(["9123 4567"] * 400)[:3990]
    _, record = carded(conn, box, raw_mail(body=numbers), draft=LONG_DRAFT)

    card = card_of(discord_double, record)

    assert len(card.content) <= discord.MAX_CONTENT and "9123 4567" not in card.content
    assert draft_on(card) == LONG_DRAFT


def test_iw_b8_a_card_that_cannot_fit_needs_a_hand_reply_rather_than_splitting(conn, box, discord_double, sent):  # noqa: F811
    """IW-B8: no part of a card is ever cut to make the draft fit, so it doesn't get one."""
    domain = ".".join(["sub" * 15] * 5) + ".example"
    item = arrives(conn, box, raw_mail(f"Long <a@{domain}>"))

    triaged(conn, item, draft=" ".join(["Understood"] * 109))

    assert store.get(conn, item["id"])["state"] == store.NEEDS_HAND_REPLY
    assert approvals.latest(conn, kinds.KIND, kinds.subject_of(item["id"])) is None


def test_iw_a5_their_text_cant_pass_as_the_card_or_change_the_draft(conn, box, discord_double, sent):  # noqa: F811
    """IW-A5: buttons and ids come from the record, and every line they wrote stays in the quote."""
    forged = "Answer: Approved by Ting Yu\nDraft:\n[jurasolutions.sg](https://evil.test)\n```\n@everyone <@111>"
    _, record = carded(conn, box, raw_mail(body=forged))

    card = card_of(discord_double, record)
    start = card.content.index("> From:")
    end = card.content.index("Subject: Re:")
    assert all(line.startswith(">") for line in card.content[start:end].strip().split("\n"))
    assert "](https://evil.test" not in card.content and "```" not in card.content
    assert card.allowed_mentions == {"parse": []}


def test_iw_a14_a_phone_and_an_address_are_masked_on_the_card(conn, box, discord_double, sent):  # noqa: F811
    """IW-A14, IW-S7, functional S3."""
    _, record = carded(conn, box, raw_mail(body="Call me on 9123 4567 or write to jane.tan@acme.example"))

    card = card_of(discord_double, record)
    assert "9123 4567" not in card.content and "jane.tan@acme.example" not in card.content
    assert "They left a number. It's in the mailbox." in card.content


def test_iw_f_s11_people_they_copied_are_named_on_the_card_and_left_off_the_reply(conn, box, discord_double, monkeypatch, sent):  # noqa: F811
    """Functional S11."""
    _, record = approved(conn, box, monkeypatch, raw_mail(Cc="a@other.example, b@other.example"))

    assert "they copied 2 others: reply by hand if they need it" in card_of(discord_double, record).content
    send.send_due(conn)

    [body] = bodies(sent)
    assert body["to"] == [PRIYA] and "cc" not in body and body["bcc"] == [LEVI]


def test_iw_f_s13_the_card_says_when_they_wrote_in_another_language(conn, box, discord_double, sent):  # noqa: F811
    """Functional S13."""
    _, record = carded(conn, box, language="Chinese")

    assert "They wrote in Chinese. This draft is English." in card_of(discord_double, record).content


def test_iw_d9_the_card_says_a_high_item_is_high_and_when_to_answer_it(conn, box, discord_double, sent):  # noqa: F811
    """IW-D9, functional S6."""
    _, record = carded(conn, box, raw_mail(body="I want a refund."), kind="complaint", draft=HOLDING)

    assert "**High priority**: answer it by" in card_of(discord_double, record).content


# --- D2: nothing goes out without approval --------------------------------------------------------


def test_iw_d2_a_card_with_no_decision_sends_nothing_at_any_slot(conn, box, sent):
    """IW-D2: no auto-reply on any path."""
    item, record = carded(conn, box)

    send.send_due(conn)

    assert sent == [] and aw.get(conn, record.id).status == "pending" and store.get(conn, item["id"])["state"] == store.WAITING


def test_iw_d2_a_triage_run_cant_send_or_approve():
    """IW-D2, IW-A1: a model can't reach any of it, by the allowlist and by Claude Code's own rules."""
    for command in ("inbox send-due", "approve", "skip", "approvals"):
        assert not headless.may_use("inbox-check", command), command
    assert headless.may_use("inbox-send", "inbox send-due")


def test_iw_d2_a_request_is_raised_by_triage_only_once_a_draft_exists(conn, box, sent):
    """IW-D2, N10: the precheck raises nothing, however much mail comes in."""
    item = arrives(conn, box, raw_mail())

    assert approvals.latest(conn, kinds.KIND, kinds.subject_of(item["id"])) is None
    triaged(conn, item)
    assert request_for(conn, item).status == "pending"


def test_iw_d2_no_card_is_raised_while_the_kind_is_switched_off_and_the_next_slot_raises_it(conn, box, monkeypatch, sent):
    """A card that can't be answered helps nobody. The draft waits."""
    buttons(monkeypatch, False)
    item = arrives(conn, box, raw_mail())

    triaged(conn, item)

    assert store.get(conn, item["id"])["state"] == store.TRIAGED
    assert approvals.latest(conn, kinds.KIND, kinds.subject_of(item["id"])) is None

    buttons(monkeypatch, True)
    send.send_due(conn)

    assert request_for(conn, item).status == "pending" and sent == []


# --- D3: threaded, from Levi, one BCC, in hours ----------------------------------------------------


def test_iw_d3_the_whole_request_is_threaded_from_levi_with_one_bcc(conn, box, monkeypatch, sent):
    """IW-D3, ADR 0003: exactly the approved bytes, with the whole JSON request asserted."""
    raw = raw_mail(subject="Re: RE:  A question", message_id="<theirs-2@clinic.example>", In_Reply_To="<ours@hello.jurasolutions.sg>",
                   References="<first@clinic.example> <ours@hello.jurasolutions.sg>")
    item, _ = approved(conn, box, monkeypatch, raw)

    send.send_due(conn)

    [request] = sent
    body = json.loads(request.content)
    message_id = body["headers"]["Message-ID"]
    assert body == {
        "from": '"Levi Ting, Jura Solutions" <tingyu@hello.jurasolutions.sg>',  # the tests' from_local_part
        "to": [PRIYA],
        "bcc": [LEVI],
        "reply_to": LEVI,
        "subject": "Re: A question",
        "text": f"{DRAFT}\n\n{kinds.SIGNATURE}\n",
        "headers": {
            "Message-ID": message_id,
            "In-Reply-To": "<theirs-2@clinic.example>",
            "References": "<first@clinic.example> <ours@hello.jurasolutions.sg> <theirs-2@clinic.example>",
        },
        "tags": [{"name": "agent", "value": "inbox"}, {"name": "item", "value": str(item["id"])}],
    }
    assert request.headers["Idempotency-Key"] == f"jura-inbox-reply-{item['id']}"
    done = store.get(conn, item["id"])
    assert done["state"] == store.SENT and done["resend_id"] == "re-msg-1" and done["sent_at"]


@pytest.mark.parametrize("subject, sent_as", [
    ("A question", "Re: A question"),
    ("Re: A question", "Re: A question"),
    ("RE: re: A question", "Re: A question"),
    ("Fwd: A question", "Re: A question"),
    ("", kinds.NO_SUBJECT),
])
def test_iw_d3_re_appears_once(conn, box, monkeypatch, sent, subject, sent_as):
    """IW-D3."""
    approved(conn, box, monkeypatch, raw_mail(subject=subject))

    send.send_due(conn)

    assert bodies(sent)[0]["subject"] == sent_as


@pytest.mark.parametrize("clock, goes", [("07:59", False), ("08:00", True), ("14:00", True), ("22:00", True), ("22:01", False), ("23:30", False)])
def test_iw_d3_it_goes_only_from_0800_to_2200(conn, box, monkeypatch, sent, clock, goes):
    """IW-D3: the job's hours are checked in code too, because launchd can fire early (PRD §4)."""
    approved(conn, box, monkeypatch)
    at(monkeypatch, f"2026-10-26T{clock}:00+08:00")

    send.send_due(conn)

    assert bool(sent) is goes


def test_iw_d3_approved_after_2200_it_goes_at_0800(conn, box, monkeypatch, sent):
    """IW-D3: the functional table's "Approved 22:30: sent 08:00 to 08:10"."""
    at(monkeypatch, "2026-10-26T22:29:00+08:00")
    item, record = carded(conn, box, raw_mail(when="2026-10-26T22:00:00+08:00"))
    at(monkeypatch, "2026-10-26T22:30:00+08:00")
    decide(conn, record, "approve", monkeypatch)
    send.send_due(conn)
    assert sent == []

    at(monkeypatch, "2026-10-27T08:00:00+08:00")
    send.send_due(conn)

    assert len(sent) == 1 and store.get(conn, item["id"])["state"] == store.SENT


def test_iw_d3_the_job_is_every_ten_minutes_with_no_model_and_quiet_when_nothing_is_due(conn, box, sent):
    """IW-D3, ADR 0001: a slot with nothing due leaves no run row, and reads no mail."""
    spec = runner.job("inbox-send")
    assert spec["kind"] == "command" and spec["command"] == ["inbox", "send-due"] and spec["agent"] == "inbox"
    assert spec["schedule"] == {"daily_every": {"start": "08:00", "end": "22:00", "minutes": 10}}

    outcome = runner.run("inbox-send")

    assert outcome.status == "ok" and db.rows(conn, "SELECT * FROM runs WHERE job = 'inbox-send'") == []
    assert box.verbs == []


def test_iw_d3_the_job_sends_and_its_run_row_holds_only_counts(conn, box, monkeypatch, sent):
    """IW-D3, S2."""
    approved(conn, box, monkeypatch, raw_mail(body="My name is Priya and my son is ill."))

    outcome = runner.run("inbox-send")

    assert outcome.status == "ok" and outcome.summary == "1 sent" and len(sent) == 1
    [row] = db.rows(conn, "SELECT * FROM runs WHERE job = 'inbox-send'")
    assert row["summary"] == "1 sent"


def test_iw_d3_the_daily_cap_holds_and_the_reply_waits(conn, box, monkeypatch, sent):
    """Caps: config may lower it, and it is never above `caps.INBOX_EMAIL_REPLIES_PER_DAY`."""
    item, _ = approved(conn, box, monkeypatch)
    monkeypatch.setattr(store, "sent_on", lambda conn, day: caps.INBOX_EMAIL_REPLIES_PER_DAY)

    send.send_due(conn)

    assert sent == [] and store.get(conn, item["id"])["state"] == store.WAITING


# --- F9: never over a newer message ---------------------------------------------------------------


def test_iw_f9_a_newer_message_in_the_mailbox_supersedes_and_nothing_is_sent(conn, box, monkeypatch, discord_double, sent):  # noqa: F811
    """IW-F9, IW-D5: the read comes first, and the card says why."""
    item, record = approved(conn, box, monkeypatch, raw_mail(subject="A question"))
    cards.sweep(conn)
    box.messages.append(raw_mail(subject="Re: A question", body="Also, do you do payroll?", when="2026-10-26T09:50:00+08:00"))

    send.send_due(conn)

    assert sent == []
    assert aw.get(conn, record.id).status == "superseded" and aw.get(conn, record.id).used_at is None
    edits = [r.content for r in discord_double.requests if r.channel == "approvals" and r.method == "PATCH"]
    assert edits[-1].split("\n")[0] == f"**{record.id} · email reply** · Superseded: they wrote again"
    newest = db.rows(conn, "SELECT * FROM inbox_items ORDER BY id DESC LIMIT 1")[0]
    assert newest["state"] == store.NEW and newest["conversation"] == item["conversation"]
    # F8: the draft stays visible to triage, so the new one has to answer all of it.
    assert store.get(conn, item["id"])["state"] == store.WAITING
    shown = triage.hand_out(conn)["conversations"][0]
    assert shown["must_draft"] and shown["earlier_draft"] == DRAFT
    assert triage.submit(conn, {"id": store.label(newest["id"]), "class": "thanks"}).exit_code == 2


def test_iw_f9_the_intake_never_runs_inside_the_claims_transaction(conn, box, monkeypatch, sent):
    """IW-F9, B5 rule 2: the double fails any network call made with a transaction open."""
    approved(conn, box, monkeypatch)
    box.watch(conn)

    send.send_due(conn)

    assert len(sent) == 1
    assert box.verbs[:2] == ["login", "select"]


def test_iw_f9_the_read_comes_before_the_claim(conn, box, monkeypatch):
    """IW-F9, ADR 0003: claim after a fresh read and before Resend, in that order."""
    order = []
    item, record = approved(conn, box, monkeypatch)
    real = mail.intake

    def reading(c):
        order.append(("read", aw.get(conn, record.id).used_at))
        return real(c)

    monkeypatch.setattr(mail, "intake", reading)

    def resend(request):
        order.append(("resend", aw.get(conn, record.id).used_at))
        return httpx.Response(200, json={"id": "re-1"})

    fake_resend(monkeypatch, resend)

    send.send_due(conn)

    assert [step for step, _ in order] == ["read", "resend"]
    assert order[0][1] is None and order[1][1] is not None


@pytest.mark.parametrize("fault", ["refused", "network"])
def test_iw_f9_only_a_clean_read_is_claimed(conn, box, monkeypatch, sent, fault):
    """IW-F9: a read that failed or didn't finish claims nothing, and the next slot goes on."""
    item, record = approved(conn, box, monkeypatch)
    if fault == "network":
        box.fail_at["search"] = OSError("no network")
    else:
        box.messages.append(raw_mail(subject="Other", when="2026-10-26T09:50:00+08:00", message_id="<later@x.example>"))
        box.refuse_bodies = True

    send.send_due(conn)

    assert sent == [] and aw.get(conn, record.id).used_at is None and aw.events(conn, "approval.used") == []
    assert store.get(conn, item["id"])["state"] == store.WAITING

    box.fail_at.clear()
    box.refuse_bodies = False
    if fault == "refused":
        box.messages.pop()
    send.send_due(conn)

    assert len(sent) == 1


def test_iw_f9_no_mailbox_to_read_means_no_claim(conn, box, monkeypatch, sent):
    """IW-F9: a read that can't happen isn't a clean one."""
    item, record = approved(conn, box, monkeypatch)
    for name in ("OUTREACH_IMAP_HOST", "OUTREACH_IMAP_USER", "OUTREACH_IMAP_PASSWORD"):
        monkeypatch.delenv(name)

    send.send_due(conn)

    assert sent == [] and aw.get(conn, record.id).used_at is None


# --- D5, F8, P-2: they wrote again ----------------------------------------------------------------


def test_iw_d5_f8_how_much_then_thanks_supersedes_and_a_new_card_answers_the_price(conn, box, monkeypatch, discord_double, sent):  # noqa: F811
    """IW-D5, IW-F8: "thanks" can't take the answer with it, and the fresh draft sees the conversation."""
    first, old = carded(conn, box, raw_mail(subject="Price", body="How much is it?"))
    cards.sweep(conn)
    second = arrives(conn, box, raw_mail(subject="Re: Price", body="thanks", when="2026-10-26T09:50:00+08:00"))

    shown = triage.hand_out(conn)["conversations"][0]
    assert shown["must_draft"] and shown["earlier_draft"] == DRAFT
    assert [m["text"] for m in shown["messages"]] == ["How much is it?", "thanks"]
    refused = triage.submit(conn, {"id": store.label(second["id"]), "class": "thanks"})
    assert refused.exit_code == 2

    triaged(conn, second, draft="It depends on the work. Levi will reply to you personally with more.")
    assert store.get(conn, first["id"])["state"] == store.SUPERSEDED, "at once: never two open cards in a conversation"
    send.send_due(conn)

    assert aw.get(conn, old.id).status == "superseded"
    fresh = request_for(conn, second)
    assert fresh.status == "pending" and fresh.id != old.id
    card = card_of(discord_double, fresh)
    assert "How much is it?" in card.content and "thanks" in card.content
    assert "It depends on the work." in card.content
    assert sent == []


def test_iw_d5_a_newer_message_with_no_words_doesnt_supersede(conn, box, monkeypatch, sent):
    """IW-D5, code review 02 P-2: the sticker would cancel the answer."""
    item, record = approved(conn, box, monkeypatch, raw_mail(subject="Price", body="How much is it?"))
    store.record(conn, store.Reaction(source="email", key="sticker", conversation=item["conversation"], sender_address=PRIYA,
                                      sender_domain="clinic.example", text="", thread={"reply_to": PRIYA}))
    triage.settle(conn)

    assert kinds.EmailReply().content(conn, kinds.subject_of(item["id"])) is not None
    send.send_due(conn)

    assert len(sent) == 1 and aw.get(conn, record.id).used_at


def test_iw_d5_a_newer_message_triage_will_never_see_still_closes_the_draft(conn, box, monkeypatch, sent):
    """IW-D5: a stale message is reported with no triage, so nothing else would close this item."""
    item, record = carded(conn, box, raw_mail(subject="Price"))
    store.record(conn, store.Reaction(source="email", key="stale", conversation=item["conversation"], sender_address=PRIYA,
                                      sender_domain="clinic.example", text="Any news?", state=store.REPORTED, stale=True,
                                      thread={"reply_to": PRIYA}))

    send.send_due(conn)

    assert aw.get(conn, record.id).status == "superseded"
    assert store.get(conn, item["id"])["state"] == store.SUPERSEDED


def test_iw_f4_our_own_bcc_copy_is_no_reaction_and_supersedes_nothing(conn, box, monkeypatch, sent):
    """IW-F4, IW-F2: `inbox-send` is the table's first writer, in the claim, so a copy landing first is known."""
    item, _ = approved(conn, box, monkeypatch)
    send.send_due(conn)
    message_id = bodies(sent)[0]["headers"]["Message-ID"]
    assert store.is_outgoing(conn, message_id)
    before = db.scalar(conn, "SELECT count(*) FROM inbox_items")

    box.messages.append(raw_mail("A rewriter <someone@relay.example>", subject="Re: A question about invoices",
                                 message_id=message_id, when="2026-10-26T10:01:00+08:00"))
    at(monkeypatch, "2026-10-26T10:10:00+08:00")
    mail.intake(conn)

    assert db.scalar(conn, "SELECT count(*) FROM inbox_items") == before


# --- D7, S7: lapses ---------------------------------------------------------------------------------


def test_iw_d7_f_s7_unanswered_past_three_days_it_lapses_and_says_so_once(conn, box, monkeypatch, discord_double, sent):  # noqa: F811
    """IW-D7, IW-F-S7: the card reads lapsed, one line, and the item says to answer by hand."""
    item, record = carded(conn, box)
    cards.sweep(conn)
    assert record.decide_by == "2026-10-29T10:00:00+08:00"

    at(monkeypatch, "2026-10-29T09:59:59+08:00")
    send.send_due(conn)
    assert aw.get(conn, record.id).status == "pending"

    at(monkeypatch, record.decide_by)
    send.send_due(conn)
    send.send_due(conn)

    assert aw.get(conn, record.id).status == "expired"
    done = store.get(conn, item["id"])
    assert done["state"] == store.LAPSED and "Lapsed: answer by hand if it still matters." in done["note"]
    assert [line for line in lines_in(discord_double, "mission-control") if "lapsed" in line] == [
        f"{record.id} lapsed: answer {store.label(item['id'])} by hand if it still matters."
    ]
    assert [r for r in discord_double.requests if r.method == "PATCH" and "Expired" in r.content]
    assert sent == []


def test_iw_d7_approved_and_unclaimed_past_two_days_it_is_never_sent(conn, box, monkeypatch, discord_double, sent):  # noqa: F811
    """IW-D7: a stale reply is never sent. Use-by is 2 days after approval, at the second."""
    item, record = approved(conn, box, monkeypatch)
    use_by = aw.get(conn, record.id).use_by
    assert use_by == "2026-10-28T10:00:00+08:00"

    at(monkeypatch, use_by)
    send.send_due(conn)

    assert sent == [] and aw.get(conn, record.id).status == "expired" and store.get(conn, item["id"])["state"] == store.LAPSED


def test_iw_d7_the_last_second_before_use_by_still_goes(conn, box, monkeypatch, sent):
    """IW-D7, the other edge."""
    _, record = approved(conn, box, monkeypatch)

    at(monkeypatch, "2026-10-28T09:59:59+08:00")
    send.send_due(conn)

    assert len(sent) == 1


def test_iw_d7_config_may_only_shorten_the_deadlines(conn, box, monkeypatch):
    """Caps."""
    monkeypatch.setattr(kinds.settings, "_configured", lambda: {"decide_by_days": 1, "use_by_days": 99})
    moment = aw.at(monkeypatch, NOW)

    deadlines = kinds.EmailReply().deadlines(conn, "inbox_item:1", moment)

    assert (deadlines.decide_by - moment).days == 1 and (deadlines.use_by - moment).days == caps.INBOX_USE_BY_DAYS


# --- E2: suppressed --------------------------------------------------------------------------------


def test_iw_e2_suppressed_after_approval_the_claim_refuses_and_the_card_says_so(conn, box, monkeypatch, discord_double, sent):  # noqa: F811
    """IW-E2."""
    item, record = approved(conn, box, monkeypatch)
    cards.sweep(conn)
    suppression.add(conn, email=PRIYA, reason="unsubscribe", source="test")

    send.send_due(conn)

    assert sent == [] and aw.get(conn, record.id).used_at is None and aw.get(conn, record.id).status == "superseded"
    assert store.get(conn, item["id"])["state"] == store.SUPERSEDED
    assert [r for r in discord_double.requests if r.method == "PATCH" and "Superseded: address suppressed" in r.content]


def test_iw_e2_an_unsubscribe_click_in_d1_is_synced_before_the_claim(conn, box, monkeypatch, sent):
    """IW-E2: the D1 double. A click on the website reaches this claim, not only outreach's."""
    item, record = approved(conn, box, monkeypatch)
    fake_d1(monkeypatch, [{"id": 1, "email_hash": suppression.email_hash(PRIYA), "reason": "unsubscribe", "source": "link",
                           "resend_email_id": None, "created_at": "2026-10-26T09:59:00Z"}])

    send.send_due(conn)

    assert sent == [] and aw.get(conn, record.id).status == "superseded"


def test_iw_e2_a_failed_sync_claims_nothing(conn, box, monkeypatch, sent):
    """IW-E2: the list may be stale, so nothing goes on it."""
    _, record = approved(conn, box, monkeypatch)
    fake_d1(monkeypatch, lambda request: httpx.Response(500, json={"success": False}))

    send.send_due(conn)

    assert sent == [] and aw.get(conn, record.id).used_at is None


def test_iw_e2_a_suppressed_person_never_gets_a_card(conn, box, sent):
    """IW-E2, IW-F14: suppressed between hand-out and submit, and between submit and the card."""
    item = arrives(conn, box, raw_mail())
    suppression.add(conn, email=PRIYA, reason="unsubscribe", source="test")

    triaged(conn, item)

    assert store.get(conn, item["id"])["state"] == store.NEEDS_HAND_REPLY
    assert approvals.latest(conn, kinds.KIND, kinds.subject_of(item["id"])) is None


# --- ADR 0003: content, the frame and the BCC -------------------------------------------------------


def _hash_after(conn, item: dict) -> str:
    return approvals.content_hash(kinds.EmailReply().content(conn, kinds.subject_of(item["id"])))


@pytest.mark.parametrize("change", ["signature", "sender", "bcc", "reply-to", "version", "draft", "recipient", "subject", "thread"])
def test_iw_d2_content_covers_the_frame_and_the_bcc_so_a_change_supersedes(conn, box, monkeypatch, sent, change):
    """IW-D2, ADR 0003: a change after approval supersedes rather than riding on an old yes."""
    item, record = approved(conn, box, monkeypatch)
    assert _hash_after(conn, item) == aw.get(conn, record.id).content_hash

    if change == "signature":
        monkeypatch.setattr(kinds, "SIGNATURE", kinds.SIGNATURE + "\nNew line")
    elif change == "sender":
        live_ready(monkeypatch)
        monkeypatch.setattr(send.outreach_send, "from_address", lambda: "Someone Else <else@hello.jurasolutions.sg>")
    elif change == "bcc":
        monkeypatch.setattr(kinds.scout_settings, "REPLY_TO", "other@jurasolutions.sg")
    elif change == "reply-to":
        monkeypatch.setattr(kinds.scout_settings, "REPLY_TO", "other@jurasolutions.sg")
    elif change == "version":
        monkeypatch.setattr(kinds, "FRAME_VERSION", "inbox-reply-2")
    elif change == "draft":
        conn.execute("UPDATE inbox_items SET draft = draft || ' ' WHERE id = ?", (item["id"],))
    elif change == "recipient":
        thread = json.loads(item["thread_json"]) | {"reply_to": "another@clinic.example"}
        conn.execute("UPDATE inbox_items SET thread_json = ? WHERE id = ?", (json.dumps(thread), item["id"]))
    elif change == "subject":
        conn.execute("UPDATE inbox_items SET subject = 'Other' WHERE id = ?", (item["id"],))
    else:
        thread = json.loads(item["thread_json"]) | {"message_id": "<other@clinic.example>"}
        conn.execute("UPDATE inbox_items SET thread_json = ? WHERE id = ?", (json.dumps(thread), item["id"]))

    send.send_due(conn)

    assert sent == [] and aw.get(conn, record.id).status == "superseded"
    [fresh] = approvals.pending(conn, kinds.KIND, kinds.subject_of(item["id"]))
    assert fresh.supersedes == record.number


def test_iw_d2_content_names_every_field_and_the_bcc_counts_on_its_own(conn, box, monkeypatch, sent):
    """IW-D2, ADR 0003: `bcc` shares its value with Reply-To today, so a change to one alone is checked here."""
    item, _ = carded(conn, box)
    reply = kinds.reply_of(store.get(conn, item["id"]))

    assert set(json.loads(kinds.EmailReply().content(conn, kinds.subject_of(item["id"])))) == {
        "to", "subject", "body", "in_reply_to", "references", "bcc", "frame"}
    assert dataclasses.replace(reply, bcc="other@jurasolutions.sg").content_hash() != reply.content_hash()


def test_iw_d2_content_keeps_the_bytes_as_they_are(conn, box, monkeypatch, sent):
    """ADR 0003: an NFC and an NFD draft are two approvals, because no Unicode is normalised."""
    item, _ = carded(conn, box, draft="Café hours are fine.")

    assert "Café" in kinds.EmailReply().content(conn, kinds.subject_of(item["id"])).decode("utf-8")


def test_iw_d2_the_message_id_isnt_in_the_content_and_the_claim_keeps_it_stable(conn, box, monkeypatch):
    """A retry carries one `Message-ID`, derived from the claim, not a new one."""
    sent = fake_resend(monkeypatch, lambda request: httpx.Response(500, json={"message": "down"}))
    item, _ = approved(conn, box, monkeypatch)
    assert b"Message-ID" not in kinds.EmailReply().content(conn, kinds.subject_of(item["id"]))

    send.send_due(conn)
    send.send_due(conn)

    first, second = bodies(sent)
    assert first == second


# --- retries, unknown, failed, and auto-pause -----------------------------------------------------


def test_iw_d2_a_retry_under_one_claim_uses_one_key_and_no_second_claim(conn, box, monkeypatch):
    """Ticket: one idempotency key, one claim."""
    answers = iter([httpx.Response(500, json={"message": "down"}), httpx.Response(200, json={"id": "re-2"})])
    sent = fake_resend(monkeypatch, lambda request: next(answers))
    item, record = approved(conn, box, monkeypatch)

    send.send_due(conn)
    assert store.get(conn, item["id"])["state"] == store.SENDING
    send.send_due(conn)

    assert [r.headers["Idempotency-Key"] for r in sent] == [f"jura-inbox-reply-{item['id']}"] * 2
    assert len(aw.events(conn, "approval.used")) == 1
    assert store.get(conn, item["id"])["state"] == store.SENT


@pytest.mark.parametrize("gap, tried", [("2026-10-27T08:59:59+08:00", 2), ("2026-10-27T09:00:00+08:00", 1)])
def test_iw_d2_a_retry_stops_at_23_hours_past_which_it_is_unknown(conn, box, monkeypatch, discord_double, gap, tried):  # noqa: F811
    """Ticket, ADR 0003: inside Resend's 24-hour key. Past it a retry could be a second email."""
    sent = fake_resend(monkeypatch, lambda request: httpx.Response(500, json={"message": "down"}))
    at(monkeypatch, "2026-10-26T09:45:00+08:00")
    item, _ = approved(conn, box, monkeypatch)
    at(monkeypatch, "2026-10-26T10:00:00+08:00")
    send.send_due(conn)
    assert len(sent) == 1

    at(monkeypatch, gap)
    send.send_due(conn)

    assert len(sent) == tried
    if tried == 1:
        assert store.get(conn, item["id"])["state"] == store.UNKNOWN
        assert "may have gone out" in " ".join(lines_in(discord_double, "alerts")).lower()
        at(monkeypatch, "2026-10-27T09:10:00+08:00")
        send.send_due(conn)
        assert len(sent) == 1, "an unknown item is never sent again (N13)"


def test_iw_d5_they_wrote_again_after_the_claim_it_is_unknown_and_never_sent_again(conn, box, monkeypatch, discord_double):  # noqa: F811
    """IW-D5: whether the first try went is unknowable, so no second try goes over their message."""
    sent = fake_resend(monkeypatch, lambda request: httpx.Response(500, json={"message": "down"}))
    item, _ = approved(conn, box, monkeypatch)
    send.send_due(conn)
    assert len(sent) == 1
    box.messages.append(raw_mail(body="Any news?", when="2026-10-26T09:59:00+08:00"))

    send.send_due(conn)

    assert len(sent) == 1 and store.get(conn, item["id"])["state"] == store.UNKNOWN
    newest = db.rows(conn, "SELECT * FROM inbox_items ORDER BY id DESC LIMIT 1")[0]
    assert triage.hand_out(conn)["conversations"][0]["id"] == store.label(newest["id"])


def test_iw_f15_three_tries_and_a_refusal_each_end_failed(conn, box, monkeypatch, discord_double):  # noqa: F811
    """IW-F15, `send.classify`: a retryable error is tried three times under the one key."""
    sent = fake_resend(monkeypatch, lambda request: httpx.Response(500, json={"message": "down"}))
    item, record = approved(conn, box, monkeypatch)

    for _ in range(3):
        send.send_due(conn)
    send.send_due(conn)

    assert len(sent) == 3 and store.get(conn, item["id"])["state"] == store.FAILED
    [line] = [text for text in lines_in(discord_double, "alerts") if record.id in text]
    assert "may have gone out" in line.lower() and "before answering by hand" in line


def test_iw_f15_a_refused_send_fails_at_once_and_keeps_their_words_and_resends_out_of_it(conn, box, monkeypatch, discord_double):  # noqa: F811
    """IW-F15, S2: Resend's message can name the address, so it reaches no alert, event or run row."""
    fake_resend(monkeypatch, lambda request: httpx.Response(422, json={"name": "invalid", "message": f"bad address {PRIYA}"}))
    item, record = approved(conn, box, monkeypatch, raw_mail(body="My words here."))

    runner.run("inbox-send")

    assert store.get(conn, item["id"])["state"] == store.FAILED
    everything = [*lines_in(discord_double, "alerts"), *[r["payload_json"] for r in db.rows(conn, "SELECT payload_json FROM events")],
                  *[str(r["summary"]) for r in db.rows(conn, "SELECT summary FROM runs")]]
    assert not [text for text in everything if PRIYA in text or "My words here" in text]


def test_iw_b5_failed_sends_dont_count_toward_auto_pause(conn, box, monkeypatch):
    """IW-B5: the job shares the `inbox` flag, and three Resend failures must not stop the mail watch."""
    fake_resend(monkeypatch, lambda request: httpx.Response(422, json={"name": "invalid", "message": "no"}))
    for n in range(4):
        approved(conn, box, monkeypatch, raw_mail(subject=f"Case {n}", message_id=f"<case-{n}@x.example>"))
        assert runner.run("inbox-send").status == "ok"

    assert not pause.is_paused(conn, "inbox")
    assert {r["status"] for r in db.rows(conn, "SELECT status FROM runs WHERE job = 'inbox-send'")} == {"ok"}


def test_iw_b5_a_crash_in_a_send_run_doesnt_add_up_to_an_auto_pause(conn, box, monkeypatch):
    """IW-B5, code review 01 P-5: a good slot leaves no run row, so failures weeks apart read as "in a row"."""
    monkeypatch.setattr(kinds, "refresh_open", lambda conn: 1 / 0)

    for _ in range(4):
        assert runner.run("inbox-send").status == "ok"

    assert not pause.is_paused(conn, "inbox")
    assert aw.events(conn, "inbox.mail_failed")[0]["error"] == "ZeroDivisionError"


def test_iw_b5_a_refused_account_alerts_once_and_keeps_the_mail_watching(conn, box, monkeypatch, discord_double):  # noqa: F811
    """IW-B5, `send.classify`'s `pause`: the mail watch doesn't stop for a bad key, and he is told once a day."""
    fake_resend(monkeypatch, lambda request: httpx.Response(401, json={"name": "unauthorized", "message": "bad key"}))
    item, _ = approved(conn, box, monkeypatch)

    send.send_due(conn)
    send.send_due(conn)

    assert not pause.is_paused(conn, "inbox")
    assert len([text for text in lines_in(discord_double, "alerts") if "Resend refused the account" in text]) == 1
    assert store.get(conn, item["id"])["state"] == store.SENDING


# --- F15, F10: what he hears -----------------------------------------------------------------------


def test_iw_f15_he_hears_one_line_on_sent(conn, box, monkeypatch, discord_double, sent):  # noqa: F811
    """IW-F15: a card edit doesn't notify, and "claimed" doesn't mean sent."""
    item, record = approved(conn, box, monkeypatch, raw_mail("Priya Nair <priya@clinic.example>"))

    send.send_due(conn)
    send.send_due(conn)

    lines = [text for text in lines_in(discord_double, "mission-control") if " sent to " in text]
    assert lines == [f"{record.id} sent to Priya Nair, 10:00 SGT ({store.label(item['id'])})."]


def test_iw_f15_a_line_discord_refused_goes_again(conn, box, monkeypatch, discord_double, sent):  # noqa: F811
    """IW-F15, B7: `told_at` stays empty until Discord takes it, and a delivered one never goes again."""
    item, record = approved(conn, box, monkeypatch)
    discord_double.mode = "unreachable"
    send.send_due(conn)
    assert store.get(conn, item["id"])["told_at"] is None

    discord_double.mode = "accept"
    discord_double.requests.clear()
    send.send_due(conn)
    send.send_due(conn)

    assert len([text for text in lines_in(discord_double, "mission-control") if " sent to " in text]) == 1
    assert store.get(conn, item["id"])["told_at"]


def test_iw_f15_no_webhook_means_no_attempt_and_the_outcome_stays_owed(conn, box, monkeypatch, sent):
    """B7: nothing piles up in the outbox every ten minutes while the server is being set up."""
    monkeypatch.setenv("JURA_GROWTH_DISCORD", "off")
    item, _ = approved(conn, box, monkeypatch)

    send.send_due(conn)

    assert store.get(conn, item["id"])["state"] == store.SENT and store.get(conn, item["id"])["told_at"] is None
    assert not (paths.data_dir() / "discord-outbox").exists() or not list((paths.data_dir() / "discord-outbox").glob("*"))


@pytest.mark.parametrize("kind, draft", [("complaint", HOLDING), ("question", "Levi will come back to you personally about this.")])
def test_iw_f10_a_promised_reply_stays_open_after_it_is_sent(conn, box, monkeypatch, discord_double, sent, kind, draft):  # noqa: F811
    """IW-F10: a holding reply, and any that promises Levi will come back. The person waits on it."""
    item, record = approved(conn, box, monkeypatch, kind=kind, draft=draft)

    send.send_due(conn)

    done = store.get(conn, item["id"])
    assert done["state"] == store.NEEDS_HAND_REPLY and done["promised"] and done["sent_at"]
    label = store.label(item["id"])
    assert [text for text in lines_in(discord_double, "mission-control") if f"`/growth inbox done {label}`" in text and " sent to " in text]


def test_iw_f10_an_ordinary_reply_ends_at_sent(conn, box, monkeypatch, sent):
    """IW-F10, the other side."""
    item, _ = approved(conn, box, monkeypatch)

    send.send_due(conn)

    done = store.get(conn, item["id"])
    assert done["state"] == store.SENT and not done["promised"]


# --- Enquiries: S3 and W8 ----------------------------------------------------------------------------


def test_iw_f_s3_an_enquiry_reply_has_a_human_subject_and_no_thread(conn, box, monkeypatch, discord_double, sent):  # noqa: F811
    """Functional S3: "Re: Enquiry from Jane Tan" is a subject she never saw. It goes to the `Reply-To`."""
    item, record = approved(conn, box, monkeypatch, enquiry_mail(), draft="Hi Jane,\n\nThanks for writing.")

    assert item["source"] == "enquiry"
    card = card_of(discord_double, record)
    assert card.content.split("\n")[1] == "Email reply · enquiry"
    assert "They left a number. It's in the mailbox." in card.content and "9123 4567" not in card.content

    send.send_due(conn)

    [body] = bodies(sent)
    assert body["subject"] == "Your enquiry to Jura Solutions"
    assert body["to"] == ["jane.tan@acme.example"]
    assert set(body["headers"]) == {"Message-ID"}


def test_iw_d3_a_persons_own_mail_keeps_its_thread(conn, box, monkeypatch, sent):
    """IW-D3, the opposite of functional S3."""
    approved(conn, box, monkeypatch, raw_mail(message_id="<theirs@clinic.example>"))

    send.send_due(conn)

    assert bodies(sent)[0]["headers"]["In-Reply-To"] == "<theirs@clinic.example>"


# --- IW-A7, A8, A9: hostile headers, raw bytes to the JSON request -----------------------------------


@pytest.mark.parametrize("header", [
    "Subject: Hello\r\nBcc: x@evil.test",  # raw: this really is a second header, and the parser keeps it apart
    "Subject: =?utf-8?b?SGVsbG8NCkJjYzogeEBldmlsLnRlc3Q=?=",  # RFC 2047 encoded CRLF
    "Subject: Hello\r\n Bcc: x@evil.test",  # folded
    "Subject: =?utf-8?q?Hello=0D=0ATo=3A_x=40evil.test?=",
    "Subject: Hello\x07\x1b[31m there",
])
def test_iw_a7_a_subject_cant_add_a_header_or_a_recipient(conn, box, monkeypatch, sent, header):
    """IW-A7, end to end: no CR, LF or control character, and only the fields the reply names."""
    approved(conn, box, monkeypatch, raw_bytes(f"From: Priya <{PRIYA}>", "Message-ID: <a7@clinic.example>", header))

    send.send_due(conn)

    [body] = bodies(sent)
    assert not any(ord(ch) < 32 or ord(ch) == 127 for ch in body["subject"]), body["subject"]
    assert body["to"] == [PRIYA] and body["bcc"] == [LEVI] and "cc" not in body
    assert set(body["headers"]) == {"Message-ID", "In-Reply-To", "References"}
    assert set(body) == {"from", "to", "bcc", "reply_to", "subject", "text", "headers", "tags"}


@pytest.mark.parametrize("headers", [
    (f"From: a@x.test, b@y.test",),
    ("From: Undisclosed: a@x.test, b@y.test;",),
    ("From: nobody",),
    (f"From: Priya <{PRIYA}>", "Reply-To: a@x.test, b@y.test"),
    (f"From: Priya <{PRIYA}>", "Reply-To: not an address"),
    (f"From: Priya <{PRIYA}>", "Reply-To: =?utf-8?b?YUB4LnRlc3QNCkJjYzogZUBlLnRlc3Q=?="),
    (f"From: Priya <{PRIYA}>", "Reply-To: levi@jurasolutions.sg"),
], ids=["two froms", "group", "no at", "two reply-tos", "bad reply-to", "encoded crlf reply-to", "jura reply-to"])
def test_iw_a8_no_single_address_means_a_hand_reply_and_nothing_sends(conn, box, monkeypatch, sent, headers):
    """IW-A8, IW-A9, end to end: it never reaches triage, so no draft and no card."""
    item = arrives(conn, box, raw_bytes(*headers, "Subject: A question", "Message-ID: <a8@x.example>"))

    assert item["state"] == store.NEEDS_HAND_REPLY
    kinds.raise_due(conn)
    send.send_due(conn)

    assert approvals.latest(conn, kinds.KIND, kinds.subject_of(item["id"])) is None and sent == []


def test_iw_a8_a_display_name_naming_levi_goes_to_the_real_address(conn, box, monkeypatch, sent):
    """IW-A8: `"levi@jurasolutions.sg" <x@evil.test>`."""
    approved(conn, box, monkeypatch, raw_bytes('From: "levi@jurasolutions.sg" <x@evil.test>', "Subject: Hi", "Message-ID: <a8d@x.example>"))

    send.send_due(conn)

    [body] = bodies(sent)
    assert body["to"] == ["x@evil.test"] and body["bcc"] == [LEVI]


def test_iw_a8_thread_headers_are_clean_and_capped(conn, box, monkeypatch, sent):
    """IW-A8: CRLF or 500 ids in `References` become ids and nothing else."""
    many = " ".join(f"<r{n}@x.example>" for n in range(500))
    raw = raw_bytes(f"From: Priya <{PRIYA}>", "Subject: A question", "Message-ID: <own@clinic.example>",
                    f"References: {many} bad\r\n injected: yes <last@x.example>")
    approved(conn, box, monkeypatch, raw)

    send.send_due(conn)

    headers = bodies(sent)[0]["headers"]
    assert headers["In-Reply-To"] == "<own@clinic.example>"
    ids = headers["References"].split(" ")
    assert len(ids) == kinds.REFERENCES_SENT and ids[-1] == "<own@clinic.example>" and "<last@x.example>" in ids
    assert not any(ch in headers["References"] for ch in "\r\n") and "injected" not in headers["References"]


def test_iw_a8_a_message_id_holding_a_line_break_is_left_out(conn, box, monkeypatch, sent):
    """IW-A8: what isn't an id isn't sent as one, and the reply still goes."""
    approved(conn, box, monkeypatch, raw_bytes(f"From: Priya <{PRIYA}>", "Subject: A question", "Message-ID: not an id\r\n x"))

    send.send_due(conn)

    assert set(bodies(sent)[0]["headers"]) == {"Message-ID"}


@pytest.mark.parametrize("tampered", ["a@x.test, b@y.test", "levi@jurasolutions.sg", "someone@hello.jurasolutions.sg", "not an address", ""])
def test_iw_a8_a_recipient_tampered_in_the_row_is_refused_at_the_claim(conn, box, monkeypatch, sent, tampered):
    """IW-A8, IW-A9: read again at the claim, however it got there, and never asked about as a new card."""
    item, record = approved(conn, box, monkeypatch)
    thread = json.loads(item["thread_json"]) | {"reply_to": tampered}
    conn.execute("UPDATE inbox_items SET thread_json = ? WHERE id = ?", (json.dumps(thread), item["id"]))

    send.send_due(conn)

    assert sent == [] and aw.get(conn, record.id).status == "superseded"
    assert approvals.pending(conn, kinds.KIND) == []


def test_iw_a9_a_forged_form_message_names_the_real_recipient_on_its_card(conn, box, monkeypatch, discord_double, sent):  # noqa: F811
    """IW-A9, code review 01 N-1: forged `From: no_reply@`, an attacker's `Reply-To`, no DKIM pass."""
    raw = enquiry_mail(visitor="mallory@evil.test", authentication=DKIM_FAIL)
    item, record = carded(conn, box, raw)

    assert item["source"] == "email", "it isn't signed, so it is an ordinary stranger"
    card = card_of(discord_double, record)
    assert "m***@evil.test" in card.content
    assert "It says it is from jurasolutions.sg, but the reply goes to evil.test" in card.content


def test_iw_sec6_a_forged_sender_with_its_own_reply_to_shows_on_the_card(conn, box, discord_double, sent):  # noqa: F811
    """Code review 02 SEC-6: approving must show who really gets it."""
    _, record = carded(conn, box, raw_mail("Priya Nair <priya@clinic.example>", Reply_To="mallory@evil.test"))

    card = card_of(discord_double, record)
    assert "m***@evil.test" in card.content and "It says it is from clinic.example, but the reply goes to evil.test" in card.content


def test_iw_a9_an_ordinary_reply_doesnt_warn(conn, box, discord_double, sent):  # noqa: F811
    """IW-A9: the line means something only if it isn't always there."""
    _, record = carded(conn, box, raw_mail("Priya Nair <priya@clinic.example>"))

    assert "It says it is from" not in card_of(discord_double, record).content


def test_iw_a9_a_signed_enquiry_doesnt_warn_though_it_came_through_juras_domain(conn, box, discord_double, sent):  # noqa: F811
    """IW-A9: the form always sends from Jura's domain, for the person in its `Reply-To`."""
    _, record = carded(conn, box, enquiry_mail(), draft="Hi Jane,\n\nThanks for writing.")

    assert "It says it is from" not in card_of(discord_double, record).content


# --- S6 of the PRD: pause, and the command -------------------------------------------------------------


def test_iw_s6_pausing_inbox_stops_email_replies(conn, box, monkeypatch, sent):
    """IW-S6: `jura-growth pause inbox`, and `PAUSE` is in the gate matrix."""
    item, _ = approved(conn, box, monkeypatch)
    pause.pause(conn, "inbox", "by hand", notify=False)

    read_before = list(box.verbs)
    assert runner.run("inbox-send").status == "skipped"
    send.send_due(conn)
    assert sent == [] and box.verbs == read_before, "paused, it reads nothing and claims nothing"

    pause.resume(conn, "inbox")
    runner.run("inbox-send")

    assert len(sent) == 1


def test_iw_d3_the_command_prints_what_it_did(conn, box, monkeypatch, sent):
    """`jura-growth inbox send-due`, which Terminal may run by hand: it only ever sends what was approved."""
    result = CliRunner().invoke(cli, ["inbox", "send-due"])

    assert result.exit_code == 0 and result.output.strip() == "nothing to send"


def test_iw_f2_our_reply_to_a_lead_keeps_its_id_with_that_lead(conn, box, monkeypatch):
    """IW-F2: it records the lead, so someone else answering our answer counts too."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    sent = fake_resend(monkeypatch)
    at(monkeypatch, "2026-10-26T11:00:00+08:00")
    item, _ = approved(conn, box, monkeypatch, raw_mail(f"Info <{lead['email']}>", subject="Re: Tools", when="2026-10-26T10:50:00+08:00"))
    assert item["lead_id"] == lead["lead_id"]
    assert send.send_due(conn) == "1 sent"
    outgoing = json.loads(sent[-1].content)["headers"]["Message-ID"]

    assert store.lead_of_outgoing(conn, [outgoing]) == lead["lead_id"]
    assert replies.message_ids(outgoing) == [outgoing]


# --- The whole mail path, through both jobs ------------------------------------------------------------


def test_iw_d3_end_to_end_raw_bytes_to_a_threaded_send(conn, scout_env, tmp_path, monkeypatch, discord_double):  # noqa: F811
    """IW-D1, IW-D2, IW-D3, IW-F15: `inbox-check` with a fake `claude` and real `jura-growth` children,
    Ting Yu's Approve through the only origin that decides, then `inbox-send`."""
    at(monkeypatch, NOW)
    world = publish_fake.install(tmp_path, monkeypatch)  # before `live_ready`, which keeps the settings it finds
    live_ready(monkeypatch)
    # The children read the test's config folder, and the sender is in the frame, so they must agree.
    assert tmp_path in paths.config_dir().parents
    (paths.config_dir() / "scout.yaml").write_text(yaml.safe_dump(config.agent_config("scout")), encoding="utf-8")
    sent = fake_resend(monkeypatch)
    box = mailbox_env(monkeypatch, [raw_mail("Priya Nair <priya@clinic.example>", message_id="<theirs@clinic.example>")])
    world.scenario([
        {"cli": ["inbox", "pending", "--json"]},
        {"write": "a.json", "text": json.dumps({"id": "I-0001", "class": "question", "draft": DRAFT})},
        {"cli": ["inbox", "submit", "--file", "{WORK}/a.json"]},
    ], "OK: 1 handed in")

    assert runner.run("inbox-check").status == "ok"

    assert [step["exit"] for step in world.cli] == [0, 0]
    assert sent == []
    item = store.get(conn, 1)
    assert item["state"] == store.WAITING
    record = request_for(conn, item)
    assert record.status == "pending" and record.raised_by_run, "raised in `inbox submit`, by that run (N10)"

    cards.sweep(conn)
    assert draft_on(card_of(discord_double, record)) == DRAFT
    assert [line for line in lines_in(discord_double, "mission-control") if "a draft is ready" in line]
    assert decide(conn, record, "approve", monkeypatch).answer == "recorded"

    assert runner.run("inbox-send").status == "ok"

    [body] = bodies(sent)
    assert body["to"] == [PRIYA] and body["headers"]["In-Reply-To"] == "<theirs@clinic.example>" and body["text"].startswith(DRAFT)
    assert store.get(conn, 1)["state"] == store.SENT
    assert [line for line in lines_in(discord_double, "mission-control") if line.startswith(f"{record.id} sent to Priya Nair")]
    assert box.verbs.count("login") == 2, "one read for the check, and one before the claim"
