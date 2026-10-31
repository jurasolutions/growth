"""The outreach email card in #approvals (MC §5.6, AC-M5.1; ticket 06).

    **A-0412 · outreach email** · decide by Tue 10 Nov, 16:30 SGT
    To: info@example.com.sg (Example Pte Ltd, logistics, score 78)
    Why: lead 233 from scout-research run 1290; address listed on https://example.com.sg/contact
    Subject: Quotes that write themselves
    > (the draft body, as it will go out)
    Button: Book a 30-minute call → https://jurasolutions.sg/?from=outreach#contact
    Template: <design.TEMPLATE_VERSION>, frame <8 hex>: sent as Levi Ting, Jura Solutions, with ...
    Answer: Approve / Skip, or /growth approve A-0412

A named-person recipient is masked (`j***@`) beside its source page; the hash still covers the
full address. `queue`, `send-due` and `requeue-shadow` post and edit cards as they end (A12).
The sweep over email drafts and cards finds nothing planted (AC-M11.1, AC-M12.1).
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import approvals, cards, config, db, discord, paths, suppression, timeutil
from jura_growth.agents.outreach import approval, compose, design, queue as queue_mod, requeue, send, store
from sweep import MASKED_ADDRESS, NAMED_ADDRESS, PERSON, SOURCE_PAGE, assert_clean, d2_secrets, outbox_dir, planted  # noqa: F401

from jura_growth.origin import Origin
from test_scout_support import CONTROL_ID, at, body_for, decide, fake_resend, live_ready, outreach_requests, scout_env, seed  # noqa: F401

FRIDAY_0912 = "2026-11-06T09:12:00+08:00"
SUBJECT = "A free delivery order maker for Example"


def lead(conn, lead_id: int, email: str, source: str, *, kind: str = "role", company: str = "Example Pte Ltd",
         domain: str = "example.com.sg", run_id: int | None = 1290) -> None:
    now = timeutil.stamp()
    if run_id and not db.one(conn, "SELECT 1 FROM runs WHERE id = ?", (run_id,)):
        conn.execute("INSERT INTO runs (id, agent, job, started_at, finished_at, status) VALUES (?, 'scout', 'scout-research', ?, ?, 'ok')",
                     (run_id, now, now))
    conn.execute(
        "INSERT INTO leads (id, company, display_name, domain, website, industry, observations_json, score, score_reasons,"
        " channel, tool_slug, status, run_id, created_at, updated_at) VALUES (?, ?, 'Example', ?, ?, 'logistics', ?, 78, '[]',"
        " 'email', 'delivery-order-maker', 'new', ?, ?, ?)",
        (lead_id, company, domain, f"https://{domain}", '["Delivery orders are signed on paper"]', run_id, now, now),
    )
    conn.execute(
        "INSERT INTO contacts (lead_id, email, email_hash, source_url, kind, mx_ok, verified_at, created_at)"
        " VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
        (lead_id, email, suppression.email_hash(email), source, kind, now, now),
    )


def queue(conn, lead_id: int) -> queue_mod.Queued:
    result = queue_mod.queue(conn, lead_id, {"subject": SUBJECT, "body": body_for("Example"), "tool": "delivery-order-maker"})
    assert result.status == "queued", result.reasons
    return result


@pytest.fixture
def lead_233(conn, monkeypatch):
    live_ready(monkeypatch)
    at(monkeypatch, FRIDAY_0912)
    lead(conn, 233, "info@example.com.sg", "https://example.com.sg/contact")
    return queue(conn, 233)


def test_the_card_for_lead_233_says_what_why_and_when(conn, lead_233):
    """AC-M5.1, golden: the decide-by skips the Mon 9 Nov holiday."""
    request = approvals.get(conn, lead_233.approval)
    text, files = cards.build(conn, request, approvals.kinds()["outreach-email"].kind)
    quoted = "\n".join(f"> {line}" if line else ">" for line in body_for("Example").split("\n"))
    assert text == (
        f"**{request.id} · outreach email** · decide by Tue 10 Nov, 16:30 SGT\n"
        "To: info@example.com.sg (Example Pte Ltd, logistics, score 78)\n"
        "Why: lead 233 from scout-research run 1290; address listed on https://example.com.sg/contact\n"
        f"Subject: {SUBJECT}\n"
        f"{quoted}\n"
        "Button: Book a 30-minute call → https://jurasolutions.sg/?from=outreach#contact\n"
        f"Template: {design.TEMPLATE_VERSION}, frame {compose.frame_fingerprint()[:8]}: sent as Levi Ting, Jura Solutions, "
        "with the button, his signature and the footer. See all of it with "
        f"`jura-growth outreach preview {lead_233.message_id} --html`.\n"
        f"Answer: Approve / Skip, or /growth approve {request.id}"
    )
    assert files == []


def test_a_full_length_email_fits_on_one_card_with_nothing_cut(conn, monkeypatch):
    """The card shows the subject, the whole body, the call link and the template line
    (code review S13-5) inside Discord's 2000 characters."""
    live_ready(monkeypatch)
    at(monkeypatch, FRIDAY_0912)
    lead(conn, 240, "info@example.com.sg", "https://example.com.sg/contact")
    long_body = body_for("Example") + "\n\n" + " ".join(["We map the process first and keep the documentation with you."] * 4)
    words = compose.word_count(long_body)
    assert 140 <= words < 150, words
    result = queue_mod.queue(conn, 240, {"subject": SUBJECT, "body": long_body, "tool": "delivery-order-maker"})
    assert result.status == "queued", result.reasons
    text, _ = cards.build(conn, approvals.get(conn, result.approval), approvals.kinds()["outreach-email"].kind)
    assert len(text) <= discord.MAX_CONTENT, len(text)
    for line in long_body.split("\n"):
        assert line in text
    assert "Book a 30-minute call → https://jurasolutions.sg/?from=outreach#contact" in text and "\nTemplate: " in text


def test_the_body_on_the_card_is_the_draft_that_goes_out(conn, lead_233):
    request = approvals.get(conn, lead_233.approval)
    preview = approvals.kinds()["outreach-email"].kind.preview(conn, request.subject)
    draft = db.scalar(conn, "SELECT draft_body FROM outreach_messages WHERE id = ?", (lead_233.message_id,))
    quoted = [line for line in preview.text.split("\n") if line.startswith(">")]
    assert "\n".join(line.removeprefix(">").removeprefix(" ") for line in quoted) == draft


def test_a_lead_added_by_hand_has_no_run_on_its_why_line(conn, monkeypatch):
    live_ready(monkeypatch)
    at(monkeypatch, FRIDAY_0912)
    lead(conn, 234, "hello@example.com.sg", "https://example.com.sg/contact", run_id=None)
    request = approvals.get(conn, queue(conn, 234).approval)
    preview = approvals.kinds()["outreach-email"].kind.preview(conn, request.subject)
    assert preview.reason == "lead 234; address listed on https://example.com.sg/contact"


def test_a_named_recipient_is_masked_beside_its_source_page_and_the_hash_covers_the_full_address(conn, monkeypatch):
    live_ready(monkeypatch)
    at(monkeypatch, FRIDAY_0912)
    lead(conn, 260, NAMED_ADDRESS, SOURCE_PAGE, kind="named")
    request = approvals.get(conn, queue(conn, 260).approval)
    preview = approvals.kinds()["outreach-email"].kind.preview(conn, request.subject)
    assert preview.title == f"To: {MASKED_ADDRESS} (Example Pte Ltd, logistics, score 78)"
    assert preview.reason.endswith(f"address listed on {SOURCE_PAGE}")
    assert NAMED_ADDRESS not in preview.title + preview.reason + preview.text
    content = approvals.kinds()["outreach-email"].kind.content(conn, request.subject)
    assert NAMED_ADDRESS in content.decode("utf-8")


# --- cards post and edit as each raising command ends (A12) ----------------------------


def card_posts(double):
    return [r for r in double.requests if r.channel == "approvals" and r.method == "POST"]


def card_edits(double):
    return [r for r in double.requests if r.channel == "approvals" and r.method == "PATCH"]


def test_queue_posts_the_card_when_it_ends(conn, discord_double, lead_233):
    [post] = card_posts(discord_double)
    assert post.content.startswith(f"**{lead_233.approval} · outreach email** · decide by Tue 10 Nov, 16:30 SGT")
    assert approvals.get(conn, lead_233.approval).posted_at


def test_an_email_queued_by_the_morning_run_gets_its_card_ahead_of_the_send_window(conn, monkeypatch, discord_double):
    """Morning brief SC3: no new code, the 06:30 research run's queue already raises and posts."""
    live_ready(monkeypatch)
    sent = fake_resend(monkeypatch)
    at(monkeypatch, "2026-11-06T06:40:00+08:00")
    lead(conn, 233, "info@example.com.sg", "https://example.com.sg/contact")
    queued = queue(conn, 233)
    [post] = card_posts(discord_double)
    assert post.content.startswith(f"**{queued.approval} · outreach email** · decide by Tue 10 Nov, 16:30 SGT")
    assert queued.send_after == "2026-11-06"
    send.send_due(conn)
    assert sent == []
    assert db.scalar(conn, "SELECT status FROM outreach_messages WHERE id = ?", (queued.message_id,)) == "queued"


# --- no card, no approval (ticket 11): an email is the action least able to be taken back ----------


def decide_as_it_stands(conn, request, decision, monkeypatch):
    """Ting Yu's answer, with no helper giving the request a card first."""
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", CONTROL_ID)
    return approvals.decide(conn, request.id, decision, actor=f"discord:{CONTROL_ID}", origin=Origin.ssh(), source_ref=None, args={})


def test_a_typed_approval_of_an_email_whose_card_has_not_gone_out_is_refused_and_sends_nothing(conn, monkeypatch, lead_233):
    request = approvals.get(conn, lead_233.approval)
    assert request.posted_at is None  # no webhook here, so no sweep has posted it
    at(monkeypatch, "2026-11-10T10:00:00+08:00")
    answer = decide_as_it_stands(conn, request, "approve", monkeypatch)
    assert answer.answer == approvals.REFUSED, answer.text
    assert "card hasn't gone out" in answer.text
    assert approvals.get(conn, request.id).status == approvals.PENDING
    sent = fake_resend(monkeypatch)
    at(monkeypatch, "2026-11-10T10:10:00+08:00")
    send.send_due(conn)
    assert sent == []
    assert approvals.get(conn, request.id).used_at is None


def test_an_email_whose_card_has_not_gone_out_can_still_be_skipped(conn, monkeypatch, lead_233):
    request = approvals.get(conn, lead_233.approval)
    at(monkeypatch, "2026-11-10T10:00:00+08:00")
    assert decide_as_it_stands(conn, request, "skip", monkeypatch).answer == approvals.RECORDED
    assert approvals.get(conn, request.id).status == approvals.SKIPPED


def test_an_email_whose_card_went_out_can_be_approved_and_sends(conn, monkeypatch, discord_double):
    live_ready(monkeypatch)
    at(monkeypatch, FRIDAY_0912)
    lead(conn, 233, "info@example.com.sg", "https://example.com.sg/contact")
    request = approvals.get(conn, queue(conn, 233).approval)
    assert request.posted_at is not None  # the sweep at the end of `queue` posted it
    at(monkeypatch, "2026-11-10T10:00:00+08:00")
    assert decide_as_it_stands(conn, request, "approve", monkeypatch).answer == approvals.RECORDED
    sent = fake_resend(monkeypatch)
    at(monkeypatch, "2026-11-10T10:10:00+08:00")
    send.send_due(conn)
    assert len(sent) == 1


def test_over_remote_an_email_with_no_card_is_refused_and_says_to_read_it_in_approvals(conn, monkeypatch, tmp_path, lead_233):
    """In a new process. An email is the action least able to be taken back, so the reason matters."""
    request = approvals.get(conn, lead_233.approval)
    conn.commit()
    env_file = tmp_path / "remote.env"
    env_file.write_text(f"CONTROL_DISCORD_USER_ID={CONTROL_ID}\n", encoding="utf-8")
    env_file.chmod(0o600)  # as a real one is: a permissions warning would lead the captured answer
    monkeypatch.setenv("JURA_GROWTH_ENV_FILE", str(env_file))
    monkeypatch.delenv("CONTROL_DISCORD_USER_ID", raising=False)
    # The fixture's settings are a patch in this process, and the new one reads files, so it gets
    # them as files: the same frame, so the same hash, and it isn't superseded.
    shutil.copytree(paths.REPO_ROOT / "config", tmp_path / "config")
    (tmp_path / "config" / "scout.yaml").write_text(yaml.safe_dump(config.agent_config("scout")), encoding="utf-8")
    child = str(Path(__file__).parent / "remote_child.py")
    env = {**os.environ, "JURA_GROWTH_CONFIG_DIR": str(tmp_path / "config"), "JURA_GROWTH_NOW": "2026-11-10T10:00:00+08:00"}
    ran = subprocess.run([sys.executable, child, "remote", "--actor", f"discord:{CONTROL_ID}", "--json", "--", "approve", request.id],
                         capture_output=True, text=True, env=env, timeout=120)
    body = json.loads(ran.stdout)
    assert body["exit_code"] == 2 and body["answer"] == approvals.REFUSED, body
    assert body["text"].startswith("refused: ") and "not understood" not in body["text"]
    assert "card hasn't gone out" in body["text"] and "read it in #approvals and decide there" in body["text"]
    assert approvals.get(conn, request.id).status == approvals.PENDING


def test_pending_says_an_email_with_no_card_can_t_be_approved_yet(conn, lead_233):
    from jura_growth import pending

    request = approvals.get(conn, lead_233.approval)
    conn.commit()
    answer = pending.render(pending.read())
    line = next(line for line in answer.splitlines() if line.startswith(f"- {request.id}"))
    assert line.endswith("no card yet, so it can't be approved")


def test_send_due_edits_the_card_to_claimed_after_the_send(conn, monkeypatch, discord_double, lead_233):
    request = approvals.get(conn, lead_233.approval)
    at(monkeypatch, "2026-11-10T10:00:00+08:00")
    decide(conn, request, "approve", monkeypatch)
    fake_resend(monkeypatch)
    at(monkeypatch, "2026-11-10T10:10:00+08:00")
    assert send.send_due(conn).summary.startswith("sent message")
    edited = card_edits(discord_double)[-1]
    assert edited.content.startswith(f"**{request.id} · outreach email** · Approved by Ting Yu, 10:00 SGT · claimed at 10:10 SGT")


def test_send_due_posts_the_cards_it_tops_up(conn, monkeypatch, discord_double):
    at(monkeypatch, "2026-11-10T08:00:00+08:00")
    seed(conn, 1)  # shadow: no request
    live_ready(monkeypatch)
    assert card_posts(discord_double) == []
    at(monkeypatch, "2026-11-10T09:30:00+08:00")
    send.send_due(conn)
    [post] = card_posts(discord_double)
    assert post.content.startswith(f"**{outreach_requests(conn)[0].id} · outreach email**")


def test_requeue_shadow_posts_its_cards(conn, monkeypatch, discord_double):
    at(monkeypatch, "2026-11-06T08:00:00+08:00")
    seed(conn, 1)
    at(monkeypatch, "2026-11-06T10:00:00+08:00")
    assert send.send_due(conn).summary.startswith("SHADOW")
    at(monkeypatch, "2026-11-10T09:00:00+08:00")
    live_ready(monkeypatch)
    plan = requeue.requeue_shadow(conn)
    [post] = card_posts(discord_double)
    assert plan.requests == [outreach_requests(conn)[0].id] and post.content.startswith(f"**{plan.requests[0]} · outreach email**")


def test_shadow_mode_posts_no_card(conn, monkeypatch, discord_double):
    at(monkeypatch, "2026-11-10T08:00:00+08:00")
    seed(conn, 1)
    at(monkeypatch, "2026-11-10T10:00:00+08:00")
    assert send.send_due(conn).summary.startswith("SHADOW")
    assert card_posts(discord_double) == []


# --- the sweep over email drafts and cards (AC-M11.1, AC-M12.1) --------------------------


def test_the_sweep_finds_nothing_planted_in_email_cards(conn, monkeypatch, discord_double, d2_secrets):
    live_ready(monkeypatch)
    for name in ("RESEND_API_KEY_OUTREACH", "UNSUBSCRIBE_SECRET"):
        monkeypatch.delenv(name)  # the D2 env file's planted values are the secrets now
    config.reset_caches()
    at(monkeypatch, "2026-11-10T08:00:00+08:00")
    lead(conn, 260, NAMED_ADDRESS, SOURCE_PAGE, kind="named")
    message = queue(conn, 260).message_id
    # Planted by raw SQL past the brand gate, as dataset D2 and D3 are.
    text = planted().text()
    for request in outreach_requests(conn):
        decide(conn, request, "skip", monkeypatch)
    conn.execute("UPDATE outreach_messages SET status = 'queued', error = NULL, subject = ?, draft_body = ? WHERE id = ?",
                 (f"{SUBJECT} {text.splitlines()[1]}", f"Hi there,\n\n{text}\n\nMore from {PERSON}.", message))
    conn.execute("UPDATE leads SET status = 'queued' WHERE id = 260")
    approval.raise_due(conn)
    approval.post_cards(conn)
    [request] = outreach_requests(conn, "pending")
    decide(conn, request, "skip", monkeypatch)
    approval.post_cards(conn)  # the edit
    assert card_posts(discord_double) and card_edits(discord_double)
    assert_clean(discord_double, outbox_dir(), planted())
    seen = "\n".join(t for r in discord_double.requests for t in r.texts())
    assert MASKED_ADDRESS in seen and SOURCE_PAGE in seen


# --- what the feed hears (FD1, functional S7) ----------------------------------------------------


def test_an_approved_email_says_when_it_goes_without_promising_today(conn, monkeypatch, discord_double, lead_233):
    cards.sweep(conn)
    [request] = outreach_requests(conn)
    decide(conn, request, "approve", monkeypatch)
    cards.sweep(conn)
    [line] = discord_double.contents("outreach-sent")
    assert line.startswith(f"**{request.id} approved**") and "info@example.com.sg" in line
    assert "inside the send window and the day's caps" in line and "today" not in line


def test_a_lead_that_closes_a_waiting_email_says_why_in_the_cards_words(conn, discord_double, lead_233):
    cards.sweep(conn)
    [request] = outreach_requests(conn)
    store.cancel_queued(conn, [233], "suppressed (unsubscribe)")
    store.set_lead_status(conn, [233], "unsubscribed")
    approvals.expire_due(conn)
    cards.sweep(conn)
    [line] = discord_double.contents("outreach-sent")
    assert line.startswith(f"**{request.id} withdrawn**") and line.endswith("The request closed: lead unsubscribed.")


def test_a_fence_in_an_email_draft_can_not_swallow_the_rest_of_the_card(conn, monkeypatch, discord_double, lead_233):
    conn.execute("UPDATE outreach_messages SET draft_body = draft_body || ' ``` a fence' WHERE id = ?", (lead_233.message_id,))
    registered = approvals.kinds()["outreach-email"]
    text = registered.kind.preview(conn, f"outreach_message:{lead_233.message_id}").text
    assert "```" not in text
