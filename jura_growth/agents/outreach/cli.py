"""`jura-growth outreach ...`: queueing, sending, syncing and inspecting email."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from jura_growth import config, db, suppression, timeutil
from jura_growth.agents.outreach import compose, queue as queue_mod, send, store, sync
from jura_growth.agents.scout import contact as contact_rules
from jura_growth.agents.scout import settings


def _echo_json(value) -> None:
    click.echo(json.dumps(value, ensure_ascii=False, indent=2, default=str))


@click.group("outreach")
def outreach_group() -> None:
    """Outreach email: queue, send, sync (scout PRD §5.3–5.7)."""


@outreach_group.command("queue")
@click.option("--lead", "lead_id", required=True, type=int)
@click.option("--file", "file_", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--kind", type=click.Choice(["first", "follow_up"]), help="Overrides `kind` in the file.")
@click.option("--json", "as_json", is_flag=True)
def queue_cmd(lead_id, file_, kind, as_json) -> None:
    """Brand-check and queue an email for LEAD from a JSON file.

    \b
    {"subject": "A free quote builder for Acme Aircon",
     "body": "Hi there,\\n\\nI was looking at Acme Aircon's ...",
     "tool": "quote-builder"}

    The code adds the signature, the why-you're-receiving line and the
    unsubscribe link. Exit 0 when queued; 1 when it failed the check (fix every
    reason and run once more) or was dropped.
    """
    try:
        data = json.loads(file_.read_text(encoding="utf-8"))
    except ValueError as error:
        raise click.UsageError(f"{file_} is not valid JSON: {error}") from None
    if kind and isinstance(data, dict):
        data["kind"] = kind
    with db.session() as conn:
        try:
            result = queue_mod.queue(conn, lead_id, data)
        except queue_mod.QueueError as error:
            if as_json:
                _echo_json({"status": "refused", "reasons": [str(error)]})
            else:
                click.echo(str(error))
            sys.exit(1)
    if as_json:
        _echo_json(result.as_dict())
    elif result.status == "queued":
        click.echo(f"queued message {result.message_id}; it goes out in the send window from {result.send_after}")
    else:
        verdict = "fail: fix every reason below and queue once more" if result.status == "retry" else "dropped: failed twice, move on"
        click.echo(verdict)
        for reason in result.reasons:
            click.echo(f"  - {reason}")
    sys.exit(0 if result.status == "queued" else 1)


@outreach_group.command("follow-ups-due")
@click.option("--json", "as_json", is_flag=True)
def follow_ups_due(as_json) -> None:
    """Leads due a follow-up (only when reply detection is set up)."""
    with db.session() as conn:
        due = sync.follow_ups_due(conn)
    if as_json:
        _echo_json({"enabled": sync.follow_ups_on(), "due": due})
        return
    if not sync.follow_ups_on():
        click.echo("follow-ups are off: they need reply detection (OUTREACH_IMAP_*) and follow_ups.enabled")
        return
    for item in due:
        click.echo(f"lead {item['lead_id']:>5} {item['company']} ({item['domain']}), first email {item['first_sent']}: {item['first_subject']}")
    if not due:
        click.echo("none due")


@outreach_group.command("send-due")
def send_due() -> str | None:
    """Send at most one due email, if the window, caps and spacing allow."""
    with db.session() as conn:
        result = send.send_due(conn)
    click.echo(result.note)
    return result.summary


@outreach_group.command("sync")
def sync_cmd() -> str:
    """Suppression sync, bounces and complaints, replies, follow-ups, retention."""
    with db.session() as conn:
        summary = sync.run(conn)
    click.echo(summary)
    return summary


@outreach_group.command("requeue-shadow")
@click.option("--since", help="Only shadow emails sent on or after this date (YYYY-MM-DD).")
@click.option("--lead", "lead_ids", multiple=True, type=int, help="Only this lead; repeatable.")
@click.option("--dry-run", is_flag=True, help="List what would be requeued, change nothing.")
@click.option("--json", "as_json", is_flag=True)
def requeue_shadow(since, lead_ids, dry_run, as_json) -> None:
    """After the shadow trial: queue shadow emails for live sending.

    Runs only when live mode is ready. Each requeued email goes through every
    send-time check and the brand gate again, recomposed with the live
    unsubscribe token. Companies that are suppressed, on the do-not-contact
    list or already contacted live are left alone. Safe to run twice.
    """
    from jura_growth.agents.outreach import requeue

    if since:
        try:
            timeutil.parse(since)
        except ValueError:
            raise click.UsageError("--since must be a date, YYYY-MM-DD") from None
    with db.session() as conn:
        try:
            plan = requeue.requeue_shadow(conn, since=since, lead_ids=lead_ids, dry_run=dry_run)
        except requeue.RequeueError as error:
            click.echo(str(error))
            sys.exit(1)
    if as_json:
        _echo_json(plan.as_dict())
        return
    verb = "would requeue" if dry_run else "requeued"
    for item in plan.requeued:
        target = "" if dry_run else f" as message {item['message_id']}"
        click.echo(f"{verb} shadow message {item['shadow_id']}{target}: {item['domain']} ({item['subject']})")
    for item in plan.skipped:
        click.echo(f"left alone shadow message {item['shadow_id']} ({item['domain'] or 'lead ' + str(item['lead_id'])}): {item['reason']}")
    if not plan.requeued and not plan.skipped:
        click.echo("no shadow emails to requeue")
    else:
        click.echo(f"{len(plan.requeued)} {verb}, {len(plan.skipped)} left alone")


@outreach_group.command("queue-list")
@click.option("--all", "show_all", is_flag=True, help="Include sent, skipped and dropped messages.")
@click.option("--limit", default=50, show_default=True)
@click.option("--json", "as_json", is_flag=True)
def queue_list(show_all, limit, as_json) -> None:
    """Queued email (or every email with --all)."""
    sql = (
        "SELECT m.id, m.lead_id, m.kind, m.status, m.mode, m.send_after, m.sent_at, m.subject, m.tool_slug, m.error, "
        "l.company, l.domain FROM outreach_messages m JOIN leads l ON l.id = m.lead_id"
    )
    if not show_all:
        sql += " WHERE m.status = 'queued'"
    sql += " ORDER BY m.id DESC LIMIT ?"
    with db.session() as conn:
        rows = db.rows(conn, sql, (limit,))
    if as_json:
        _echo_json(rows)
        return
    for row in rows:
        when = row["sent_at"][:16] if row["sent_at"] else f"from {row['send_after']}"
        click.echo(f"{row['id']:>5} {row['status']:10} {row['kind']:9} {when:18} {row['domain']:28} {row['subject']}")
    if not rows:
        click.echo("nothing queued" if not show_all else "no messages")


@outreach_group.command("preview")
@click.argument("message_id", type=int)
@click.option("--html", "show_html", is_flag=True, help="Print the HTML part instead of the text.")
def preview(message_id, show_html) -> None:
    """Print a message in full, as it would go out now (or as it went out)."""
    with db.session() as conn:
        message = db.one(conn, "SELECT * FROM outreach_messages WHERE id = ?", (message_id,))
        if not message:
            raise click.UsageError(f"no message {message_id}")
        lead, row = queue_mod.recipient(conn, message["lead_id"])
        if message["sent_at"]:
            text, html, unsubscribe = message["body_text"], message["body_html"], None
        else:
            email = queue_mod.build(conn, lead, row, subject=message["subject"], body=message["draft_body"])
            text, html, unsubscribe = email.text, email.html, email.unsubscribe_url
    domain = send.sending_domain() or "<sending_domain not set>"
    click.echo(f"From:      {settings.SENDER_NAME} <{settings.get().get('from_local_part') or 'tingyu'}@{domain}>")
    click.echo(f"To:        {row['email']}  (listed on {row['source_url']})")
    click.echo(f"Reply-To:  {settings.REPLY_TO}")
    click.echo(f"Subject:   {message['subject']}")
    if unsubscribe:
        for key, value in compose.list_unsubscribe_headers(unsubscribe).items():
            click.echo(f"{key}: {value}")
    click.echo(f"Status:    {message['status']}" + (f" ({message['mode']}, {message['sent_at']})" if message["sent_at"] else f", sends from {message['send_after']}"))
    click.echo("")
    click.echo(html if show_html else text)


@outreach_group.command("suppress")
@click.argument("email_or_domain")
@click.option("--reason", type=click.Choice(["unsubscribe", "bounce", "complaint", "manual"]), default="manual", show_default=True)
def suppress(email_or_domain, reason) -> None:
    """Suppress an address or a whole domain and cancel anything queued for it."""
    value = email_or_domain.strip().lower()
    with db.session() as conn:
        if "@" in value:
            new = suppression.add(conn, email=value, reason=reason, source="cli:outreach")
            lead_ids = [r["lead_id"] for r in db.rows(conn, "SELECT lead_id FROM contacts WHERE email_hash = ?", (suppression.email_hash(value),))]
        else:
            domain = contact_rules.site_domain(value)
            new = suppression.add(conn, domain=domain, reason=reason, source="cli:outreach")
            lead_ids = [r["id"] for r in db.rows(conn, "SELECT id FROM leads WHERE domain = ?", (domain,))]
            lead_ids += [r["lead_id"] for r in db.rows(conn, "SELECT lead_id FROM contacts WHERE email LIKE ?", (f"%@{domain}",))]
        cancelled = store.cancel_queued(conn, lead_ids, f"suppressed by hand ({reason})")
        store.set_lead_status(conn, lead_ids, "suppressed")
    click.echo(("suppressed" if new else "already suppressed") + (f"; cancelled {cancelled} queued email" if cancelled else ""))


@outreach_group.command("unsubscribe-link")
@click.argument("email")
def unsubscribe_link(email) -> None:
    """Print the unsubscribe URL for EMAIL (to test the website's function)."""
    secret = config.secret("UNSUBSCRIBE_SECRET")
    if not secret:
        raise click.UsageError("UNSUBSCRIBE_SECRET is not set (.env); it must match the website's value")
    click.echo(compose.unsubscribe_url(email, secret))


@outreach_group.command("status")
@click.option("--json", "as_json", is_flag=True)
def status(as_json) -> None:
    """Mode, live-mode checks, caps, warm-up and queue."""
    with db.session() as conn:
        info = send.status(conn)
    if as_json:
        _echo_json(info)
        return
    click.echo(f"mode            {info['mode']}" + (f" (PAUSED: {info['paused']})" if info["paused"] else ""))
    click.echo(f"window          {info['window']} ({'open now' if info['in_window_now'] else 'closed now'})")
    click.echo(f"sent ({info['mode']})   today {info['sent']['today']}, 30 days {info['sent']['last_30_days']}, 365 days {info['sent']['last_365_days']}")
    click.echo(f"today           {info['warm_up']}; {info['left_today']} left" + (f" ({info['binding_limit']} reached)" if not info["left_today"] else ""))
    click.echo(f"queued          {info['queued']}")
    click.echo(f"tools           {', '.join(info['live_tools']) or info['registry_problem']}")
    click.echo(f"D1              {'configured' if info['d1_configured'] else 'not configured'}")
    click.echo(f"reply detection {'on' if info['reply_detection'] else 'off'}; follow-ups {'on' if info['follow_ups'] else 'off'}")
    click.echo(f"do-not-contact  {'present' if info['do_not_contact_list'] else 'missing'}")
    if info["live_problems"]:
        click.echo("live mode would refuse:")
        for problem in info["live_problems"]:
            click.echo(f"  - {problem}")
    else:
        click.echo("live mode: every pre-condition holds")
    click.echo(f"(as of {timeutil.stamp()})")
