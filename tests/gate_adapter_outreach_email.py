"""The gate-matrix adapter for `outreach-email` (ticket 06). The contract is in
`test_approval_gates.py`'s docstring.

- The gated action is `send-due` in live mode; "went out" means the Resend double received a
  request. At call time the double reads the record on a fresh connection (G21).
- An item is one lead's queued first email, `outreach_message:<id>`, raised through `queue`.
- `send-due` and `queue` act on every email due today, not on one subject, so `attempt` and the
  raising calls hold the other queued emails back a day (their `send_after`, which the content
  doesn't cover) while they run, and put them back after.
- The kind's switch is the live gate: with `approvals.discord_buttons` off, live `send-due`
  refuses before any claim. Shadow mode is the kind's `switched_off` too, but in shadow mode
  `send-due` records an approved email as a shadow send by design (AC-M8.10), which would use
  the item up; `test_outreach_decisions.py` tests that switch at the `use()` seam.
- The in-flight marker is `outreach_messages.attempts`; a temporary trigger makes it fail.
"""

from __future__ import annotations

from contextlib import contextmanager

import httpx

from jura_growth import approvals, db, log
from jura_growth.agents.outreach import approval, send, store

import approval_world as aw
from test_scout_support import buttons, decide, live_ready, prepare_scout, seed

LATER = "9999-12-31"


class OutreachEmailAdapter:
    kind = approval.KIND
    agent = store.AGENT
    applied_on_decide = False

    def __init__(self, *, conn, monkeypatch, tmp_path):
        self.conn = conn
        self.monkeypatch = monkeypatch
        prepare_scout(tmp_path, monkeypatch)
        live_ready(monkeypatch)
        aw.at(monkeypatch, aw.NOW)
        self.sent: list[dict] = []
        self._next = 0
        monkeypatch.setattr(send, "resend_client", lambda: httpx.Client(transport=httpx.MockTransport(self._resend)))

    # --- the world ------------------------------------------------------------------

    def _resend(self, request: httpx.Request) -> httpx.Response:
        message = int(next(t["value"] for t in __import__("json").loads(request.content)["tags"] if t["name"] == "message"))
        fresh = db.connect(migrate_now=False)
        try:
            row = fresh.execute(
                "SELECT used_at, used_by_run FROM approvals WHERE kind = ? AND subject = ? AND used_at IS NOT NULL",
                (self.kind, approval.subject_of(message)),
            ).fetchone()
        finally:
            fresh.close()
        self.sent.append({"message": message, "used": bool(row and row["used_at"] and row["used_by_run"])})
        return httpx.Response(200, json={"id": f"re-msg-{len(self.sent)}"})

    @contextmanager
    def _alone(self, subject: str | None):
        """Hold every other queued email back a day while the block runs."""
        keep = approval.message_id(subject) if subject else None
        held = self.conn.execute(
            "SELECT id, send_after FROM outreach_messages WHERE status = 'queued' AND id IS NOT ?", (keep,)
        ).fetchall()
        self.conn.executemany("UPDATE outreach_messages SET send_after = ? WHERE id = ?", [(LATER, r["id"]) for r in held])
        try:
            yield
        finally:
            self.conn.executemany("UPDATE outreach_messages SET send_after = ? WHERE id = ? AND send_after = ?",
                                  [(r["send_after"], r["id"], LATER) for r in held])

    def item(self) -> str:
        self._next += 1
        with self._alone(None):
            message = seed(self.conn, self._next)["message_id"]
        return approval.subject_of(message)

    def twin(self, subject: str) -> str:
        """The same lead's follow-up, word for word: the same recipient, subject and draft."""
        original = db.one(self.conn, "SELECT * FROM outreach_messages WHERE id = ?", (approval.message_id(subject),))
        twin = self.conn.execute(
            "INSERT INTO outreach_messages (lead_id, contact_id, kind, tool_slug, subject, draft_body, body_text, body_html, "
            "send_after, queued_at, status) VALUES (?, ?, 'follow_up', ?, ?, ?, ?, ?, ?, ?, 'queued')",
            (original["lead_id"], original["contact_id"], original["tool_slug"], original["subject"], original["draft_body"],
             original["body_text"], original["body_html"], original["send_after"], original["queued_at"]),
        ).lastrowid
        return approval.subject_of(twin)

    def raise_request(self, subject: str) -> approvals.Approval:
        message = approval.message_id(subject)
        found = approval.live_request(self.conn, message)
        if found is None:
            with self._alone(subject):
                approval.raise_due(self.conn)
            found = approval.live_request(self.conn, message)
        assert found is not None, subject
        return found

    def approve(self, record):
        return decide(self.conn, record, "approve", self.monkeypatch)

    def skip(self, record):
        return decide(self.conn, record, "skip", self.monkeypatch)

    def attempt(self, subject: str) -> None:
        run = log.start_run(self.conn, self.agent, "scout-send")
        self.monkeypatch.setenv("JURA_GROWTH_RUN_ID", str(run))
        try:
            with self._alone(subject):
                send.send_due(self.conn)
        finally:
            self.monkeypatch.delenv("JURA_GROWTH_RUN_ID", raising=False)

    def went_out(self) -> int:
        return len(self.sent)

    def seen_at_call(self) -> list[bool]:
        return [s["used"] for s in self.sent]

    def change(self, subject: str) -> None:
        self.conn.execute("UPDATE outreach_messages SET draft_body = draft_body || ' (changed)' WHERE id = ?",
                          (approval.message_id(subject),))

    def remove(self, subject: str) -> None:
        """An unsubscribe: the address suppressed, the lead closed, the queued email cancelled."""
        lead = db.scalar(self.conn, "SELECT lead_id FROM outreach_messages WHERE id = ?", (approval.message_id(subject),))
        store.cancel_queued(self.conn, [lead], "suppressed (unsubscribe)")
        store.set_lead_status(self.conn, [lead], "unsubscribed")

    def switch(self, on: bool) -> None:
        buttons(self.monkeypatch, not on)

    def fail_in_flight(self, on: bool) -> None:
        if on:
            self.conn.execute(
                "CREATE TEMP TRIGGER fail_in_flight BEFORE UPDATE OF attempts ON outreach_messages "
                "BEGIN SELECT RAISE(ABORT, 'in-flight marker failed'); END"
            )
        else:
            self.conn.execute("DROP TRIGGER IF EXISTS temp.fail_in_flight")

    def hook_ran(self, hook: str, subject: str) -> int:
        why = {"on_skip": "skipped by Ting Yu", "on_expire": "not approved in time",
               "on_lapse": "approved but the limits didn't reach it"}[hook]
        message = approval.message_id(subject)
        return len([e for e in aw.events(self.conn, "outreach.approval_closed") if e["message"] == message and e["why"] == why])


ADAPTER = OutreachEmailAdapter
