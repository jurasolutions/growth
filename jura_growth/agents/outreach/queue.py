"""Queueing an email (`jura-growth outreach queue --lead <id> --file <json>`).

The file holds what the model wrote: {"subject", "body", "tool"?, "kind"?}.
The code checks the lead can be emailed, picks up the tool from the site
registry, appends the signature and footer, and runs the brand gate (one
regeneration, then the item drops). Only a pass is queued.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

from jura_growth import caps, config, db, gate, log, suppression, timeutil
from jura_growth.agents.outreach import approval, compose, store, sync
from jura_growth.agents.scout import contact as contact_rules
from jura_growth.agents.scout import dnc, registry, settings


# Message statuses that don't hold the company's one first email (or follow-up).
INACTIVE = "('dropped', 'cancelled', 'skipped', 'failed', 'requeued')"


class QueueError(ValueError):
    pass


@dataclass
class Queued:
    status: str  # queued, retry, dropped
    message_id: int | None = None
    reasons: list[str] = field(default_factory=list)
    send_after: str | None = None
    approval: str | None = None  # the A-nnnn request raised for it in live mode, if there was room

    def as_dict(self) -> dict:
        return {"status": self.status, "message_id": self.message_id, "reasons": self.reasons, "send_after": self.send_after,
                "approval": self.approval}


def site_of(source_url: str) -> str:
    return contact_rules.site_domain(source_url)


def recipient(conn: sqlite3.Connection, lead_id: int) -> tuple[dict, dict]:
    lead = db.one(conn, "SELECT * FROM leads WHERE id = ?", (lead_id,))
    if not lead:
        raise QueueError(f"no lead {lead_id}")
    if lead["channel"] != "email":
        raise QueueError(f"lead {lead_id} has no published enquiry address (channel {lead['channel']}); it is not emailed")
    row = db.one(conn, "SELECT * FROM contacts WHERE lead_id = ? ORDER BY id LIMIT 1", (lead_id,))
    if not row:
        raise QueueError(f"lead {lead_id} has no contact address")
    return lead, row


def blockers(conn: sqlite3.Connection, lead: dict, row: dict, kind: str) -> list[str]:
    """Reasons this email may not be queued or sent: suppression (address and
    domain), the do-not-contact list, the lead's state, and the per-company
    rule (one first email and one follow-up, ever)."""
    found = []
    email = row["email"]
    mail_domain = contact_rules.mail_domain(email)
    why = suppression.is_suppressed(conn, email)
    if why:
        found.append(f"{email} is suppressed ({why})")
    why = suppression.is_domain_suppressed(conn, lead["domain"])
    if why:
        found.append(f"{lead['domain']} is suppressed ({why})")
    entry = dnc.match(lead["company"], [lead["domain"], mail_domain])
    if entry:
        found.append(f"on inputs/do-not-contact.csv ({entry.company or entry.domain})")
    if lead["status"] in store.FINAL_LEAD_STATUSES:
        found.append(f"lead {lead['id']} is {lead['status']}")
    # Live sends only: a shadow send contacted no one. (In shadow mode the
    # unique index still holds one active first email per company.)
    sent = {
        r["kind"]: r["n"]
        for r in db.rows(
            conn,
            "SELECT kind, count(*) AS n FROM outreach_messages WHERE lead_id = ? AND mode = 'live' "
            "AND sent_at IS NOT NULL GROUP BY kind",
            (lead["id"],),
        )
    }
    if kind == "first":
        if sent.get("first", 0) >= caps.OUTREACH_FIRST_EMAILS_PER_COMPANY:
            found.append(f"lead {lead['id']} has had its first email")
        for domain in {lead["domain"], mail_domain}:
            if not contact_rules.is_free_mail(domain) and store.contacted(conn, domain):
                found.append(f"{domain} has been contacted before")
    elif sent.get("follow_up", 0) >= caps.OUTREACH_FOLLOW_UPS_PER_COMPANY:
        found.append(f"lead {lead['id']} has had its follow-up")
    return found


def build(conn: sqlite3.Connection, lead: dict, row: dict, *, subject: str, body: str, secret: str | None = None) -> compose.Email:
    return compose.compose(
        subject=subject,
        body=body,
        company=lead["display_name"],
        site=site_of(row["source_url"]),
        email=row["email"],
        secret=secret if secret is not None else config.secret("UNSUBSCRIBE_SECRET"),
    )


def check_args(lead: dict, email: compose.Email, *, kind: str, tool: str | None) -> dict:
    """The brand-check arguments for an outreach email (gate and pre-checks alike)."""
    return {
        "subject": email.subject,
        "channel_name": "email",
        "proper_nouns": [lead["company"], lead["display_name"]],
        "context": {
            "company": lead["display_name"],
            "observations": json.loads(lead["observations_json"] or "[]"),
            "tools": registry.live_slugs(),
            "tool": tool,
            "kind": kind,
            "recipient": email.to,
        },
    }


def gate_email(conn: sqlite3.Connection, item_key: str, lead: dict, email: compose.Email, *, kind: str, tool: str | None, alert: bool = True) -> gate.GateResult:
    return gate.gate(
        conn, item_key, email.check_text, agent=store.AGENT, alert=alert, **check_args(lead, email, kind=kind, tool=tool)
    )


def queue(conn: sqlite3.Connection, lead_id: int, data: dict) -> Queued:
    if not isinstance(data, dict):
        raise QueueError("the email file must hold one JSON object: {subject, body, tool?, kind?}")
    kind = str(data.get("kind") or "first").strip().replace("-", "_")
    if kind not in ("first", "follow_up"):
        raise QueueError("`kind` must be first or follow_up")
    subject = str(data.get("subject") or "").strip()
    body = str(data.get("body") or "").strip()
    if not subject or not body:
        raise QueueError("the email file needs `subject` and `body`")

    lead, row = recipient(conn, lead_id)
    if lead["status"] in store.FINAL_LEAD_STATUSES:
        raise QueueError(f"lead {lead_id} is {lead['status']}; nothing more is sent to it")

    found = blockers(conn, lead, row, kind)
    if kind == "first":
        existing = db.one(
            conn,
            "SELECT id, status FROM outreach_messages WHERE lead_id = ? AND kind = 'first' "
            f"AND status NOT IN {INACTIVE}",
            (lead_id,),
        )
        if existing:
            found.append(f"lead {lead_id} already has a first email (message {existing['id']}, {existing['status']})")
    else:
        problem = sync.follow_up_problem(conn, lead_id)
        if problem:
            found.append(problem)
    if found:
        raise QueueError("not queued: " + "; ".join(dict.fromkeys(found)))

    tools, problem = registry.load()
    slug = str(data.get("tool") or lead["tool_slug"] or "").strip() or None
    if kind == "first":
        if not tools:
            raise QueueError(f"not queued: no tool available to link to ({problem})")
        if not slug:
            raise QueueError("not queued: pick a tool (`tool` in the file); see `jura-growth scout tools`")
        if slug not in {t["slug"] for t in tools}:
            raise QueueError(f"not queued: {slug!r} is not a live tool in the site registry")
    elif slug and slug not in {t["slug"] for t in tools}:
        slug = None

    email = build(conn, lead, row, subject=subject, body=body)
    item_key = f"outreach:{lead_id}:{kind}"
    verdict = gate_email(conn, item_key, lead, email, kind=kind, tool=slug)
    store.record_qa(conn, item_key, verdict.passed, verdict.result.reasons())
    qa = {"queue": {"status": verdict.status, "attempt": verdict.attempts, "issues": verdict.result.as_dict()["issues"]}}

    if verdict.status == "retry":
        return Queued("retry", reasons=verdict.result.reasons())

    now = timeutil.stamp()
    if verdict.status == "dropped":
        cursor = conn.execute(
            "INSERT INTO outreach_messages (lead_id, contact_id, kind, tool_slug, subject, draft_body, body_text, body_html, "
            "qa_json, send_after, queued_at, status, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'dropped', ?)",
            (lead_id, row["id"], kind, slug, email.subject, email.draft, email.text, email.html, json.dumps(qa),
             timeutil.today_str(), now, "failed the brand check twice"),
        )
        if kind == "first":
            store.set_lead_status(conn, [lead_id], "qa_dropped")
        return Queued("dropped", message_id=cursor.lastrowid, reasons=verdict.result.reasons())

    send_after = timeutil.today()
    if kind == "follow_up":
        first_sent = db.scalar(
            conn, "SELECT sent_at FROM outreach_messages WHERE lead_id = ? AND kind = 'first' AND mode = 'live'", (lead_id,)
        )
        earliest = store.add_business_days(timeutil.parse(first_sent).date(), settings.follow_up_days())
        send_after = max(send_after, earliest)
    cursor = conn.execute(
        "INSERT INTO outreach_messages (lead_id, contact_id, kind, tool_slug, subject, draft_body, body_text, body_html, "
        "qa_json, send_after, queued_at, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued')",
        (lead_id, row["id"], kind, slug, email.subject, email.draft, email.text, email.html, json.dumps(qa),
         send_after.isoformat(), now),
    )
    if kind == "first":
        store.set_lead_status(conn, [lead_id], "queued")
    message_id = int(cursor.lastrowid or 0)
    log.event(conn, "outreach.queued", {"message": message_id, "lead": lead_id, "kind": kind, "tool": slug}, agent=store.AGENT)
    # Live mode: a request for it, and for anything older still waiting, if
    # it is due today and today's quota has room (A14); then the cards (A12).
    approval.raise_due(conn)
    request = approval.live_request(conn, message_id)
    approval.post_cards(conn)
    return Queued("queued", message_id=message_id, send_after=send_after.isoformat(), approval=request.id if request else None)
