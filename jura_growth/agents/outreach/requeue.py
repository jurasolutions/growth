"""After the shadow trial: `jura-growth outreach requeue-shadow`.

A shadow send was recorded and posted, never delivered, so the company was
never contacted. Once live mode is ready, Ting Yu reviews the shadow emails and
requeues the ones he is happy with. Each becomes a new queued first email that
goes through the whole send run like any other: window, caps, warm-up,
spacing, the D1 sync, suppression, do-not-contact, `contacted_domains`, the
per-company rule, and the brand gate on the text recomposed with the live
unsubscribe token.

- Refuses unless `send.live_problems()` is empty, so it can't run in shadow.
- Never touches a lead that is suppressed, on the do-not-contact list, already
  contacted live (`contacted_domains`), finished (replied, unsubscribed ...),
  or that already has an active first email.
- Skips an email that fails the brand check as it stands now, so it can't be
  dropped at send time (and count towards the two-failures pause).
- Idempotent: the shadow row becomes `requeued` and points to nothing new on a
  second run; only `shadow` rows are candidates.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

from jura_growth import brand_check, db, log, timeutil
from jura_growth.agents.outreach import queue, send, store


class RequeueError(RuntimeError):
    pass


@dataclass
class Plan:
    requeued: list[dict] = field(default_factory=list)  # {shadow_id, message_id, lead_id, domain, subject}
    skipped: list[dict] = field(default_factory=list)  # {shadow_id, lead_id, domain, reason}
    dry_run: bool = False

    def as_dict(self) -> dict:
        return {"dry_run": self.dry_run, "requeued": self.requeued, "skipped": self.skipped}


def candidates(conn: sqlite3.Connection, *, since: str | None = None, lead_ids=()) -> list[dict]:
    sql = (
        "SELECT * FROM outreach_messages WHERE kind = 'first' AND mode = 'shadow' AND status = 'shadow'"
    )
    params: list = []
    if since:
        sql += " AND substr(sent_at, 1, 10) >= ?"
        params.append(since)
    if lead_ids:
        sql += f" AND lead_id IN ({','.join('?' * len(lead_ids))})"
        params += list(lead_ids)
    return db.rows(conn, sql + " ORDER BY sent_at, id", tuple(params))


def _problem(conn: sqlite3.Connection, message: dict) -> tuple[str | None, dict | None, dict | None]:
    try:
        lead, row = queue.recipient(conn, message["lead_id"])
    except queue.QueueError as error:
        return str(error), None, None
    found = queue.blockers(conn, lead, row, "first")
    if lead["status"] != "shadow_sent" and not found:
        found.append(f"lead {lead['id']} is {lead['status']}")
    active = db.one(
        conn,
        f"SELECT id, status FROM outreach_messages WHERE lead_id = ? AND kind = 'first' AND status NOT IN {queue.INACTIVE} "
        "AND id != ?",
        (lead["id"], message["id"]),
    )
    if active:
        found.append(f"lead {lead['id']} already has a first email (message {active['id']}, {active['status']})")
    if found:
        return "; ".join(dict.fromkeys(found)), lead, row
    email = queue.build(conn, lead, row, subject=message["subject"], body=message["draft_body"])
    result = brand_check.check(email.check_text, **queue.check_args(lead, email, kind="first", tool=message["tool_slug"]))
    if not result.passed:
        return "fails the brand check now: " + "; ".join(result.reasons()[:4]), lead, row
    return None, lead, row


def requeue_shadow(conn: sqlite3.Connection, *, since: str | None = None, lead_ids=(), dry_run: bool = False) -> Plan:
    problems = send.live_problems()
    if problems:
        raise RequeueError(
            "requeue-shadow runs only when live sending is ready; live mode would refuse:\n- " + "\n- ".join(problems)
        )
    plan = Plan(dry_run=dry_run)
    today = timeutil.today_str()
    for message in candidates(conn, since=since, lead_ids=lead_ids):
        reason, lead, row = _problem(conn, message)
        domain = lead["domain"] if lead else None
        if reason:
            plan.skipped.append({"shadow_id": message["id"], "lead_id": message["lead_id"], "domain": domain, "reason": store.mask(reason)})
            continue
        item = {"shadow_id": message["id"], "lead_id": lead["id"], "domain": domain, "subject": message["subject"]}
        if dry_run:
            plan.requeued.append({**item, "message_id": None})
            continue
        email = queue.build(conn, lead, row, subject=message["subject"], body=message["draft_body"])
        qa = json.loads(message["qa_json"] or "{}")
        qa["requeued"] = {"from": message["id"], "at": timeutil.stamp()}
        with db.transaction(conn):
            conn.execute(
                "UPDATE outreach_messages SET status = 'requeued', error = ? WHERE id = ? AND status = 'shadow'",
                (f"requeued for live sending on {today}", message["id"]),
            )
            cursor = conn.execute(
                "INSERT INTO outreach_messages (lead_id, contact_id, kind, tool_slug, subject, draft_body, body_text, "
                "body_html, qa_json, send_after, queued_at, status, requeued_from) "
                "VALUES (?, ?, 'first', ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?)",
                (lead["id"], row["id"], message["tool_slug"], message["subject"], message["draft_body"], email.text,
                 email.html, json.dumps(qa), today, timeutil.stamp(), message["id"]),
            )
            store.set_lead_status(conn, [lead["id"]], "queued")
        plan.requeued.append({**item, "message_id": cursor.lastrowid})
    if not dry_run:
        log.event(
            conn,
            "outreach.requeued",
            {"requeued": [(i["shadow_id"], i["message_id"]) for i in plan.requeued], "skipped": len(plan.skipped)},
            agent=store.AGENT,
        )
    return plan
