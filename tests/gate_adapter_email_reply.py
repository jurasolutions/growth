"""The gate-matrix adapter for `email-reply` (inbox watch ticket 03). The contract is in
`test_approval_gates.py`'s docstring.

- The gated action is `inbox send-due`; "went out" means the Resend double received a request. At
  call time the double reads the record on a fresh connection (G21).
- An item is one person's message with a draft ready for its card, `inbox_item:<id>`, as triage leaves
  it. `send-due` acts on every approved reply, not on one subject, so `attempt` narrows what is due.
- The kind's switch is `approvals.discord_buttons`, the way a decision reaches the engine at all.
- The in-flight marker is `inbox_items.send_attempts`; a temporary trigger makes it fail.
"""

from __future__ import annotations

import json

import httpx

from inbox_world import mailbox_env
from jura_growth import approvals, db, log, suppression
from jura_growth.agents.inbox import kinds, send, store
from jura_growth.agents.outreach import send as outreach_send

import approval_world as aw
from test_scout_support import buttons, decide, live_ready, prepare_scout

DRAFT = "We help with invoices and the copying between systems that follows. The first step is a short discovery call."


class EmailReplyAdapter:
    kind = kinds.KIND
    agent = "inbox"
    applied_on_decide = False

    def __init__(self, *, conn, monkeypatch, tmp_path):
        self.conn = conn
        self.monkeypatch = monkeypatch
        prepare_scout(tmp_path, monkeypatch)
        live_ready(monkeypatch)
        mailbox_env(monkeypatch, [])
        aw.at(monkeypatch, aw.NOW)
        self.sent: list[dict] = []
        self._next = 0
        monkeypatch.setattr(outreach_send, "resend_client", lambda: httpx.Client(transport=httpx.MockTransport(self._resend)))

    # --- the world ------------------------------------------------------------------

    def _resend(self, request: httpx.Request) -> httpx.Response:
        tags = json.loads(request.content)["tags"]
        item = int(next(t["value"] for t in tags if t["name"] == "item"))
        fresh = db.connect(migrate_now=False)
        try:
            row = fresh.execute(
                "SELECT used_at, used_by_run FROM approvals WHERE kind = ? AND subject = ? AND used_at IS NOT NULL",
                (self.kind, kinds.subject_of(item)),
            ).fetchone()
        finally:
            fresh.close()
        self.sent.append({"item": item, "used": bool(row and row["used_at"] and row["used_by_run"])})
        return httpx.Response(200, json={"id": f"re-reply-{len(self.sent)}"})

    def _record(self, *, conversation: str, address: str, key: str) -> int:
        recorded = store.record(self.conn, store.Reaction(
            source="email", key=key, conversation=conversation, sender_name="Priya Nair", sender_address=address,
            sender_domain=address.rsplit("@", 1)[1], subject="A question about invoices", text="Do you work with clinics?",
            thread={"message_id": "<theirs@clinic.example>", "in_reply_to": None, "references": [], "reply_to": address, "copied": 0,
                    "own_sender": True},
        ))
        store.update_triage(self.conn, recorded.item_id, state=store.TRIAGED, note="", kind="question", priority="normal",
                            language="English", draft=DRAFT, promised=False)
        return recorded.item_id

    def item(self) -> str:
        self._next += 1
        n = self._next
        return kinds.subject_of(self._record(conversation=f"c{n}", address=f"priya{n}@clinic{n}.example", key=f"k{n}"))

    def twin(self, subject: str) -> str:
        """Another conversation with the same person, word for word: what goes out reads the same."""
        original = store.get(self.conn, kinds.item_id_of(subject))
        self._next += 1
        n = self._next
        return kinds.subject_of(self._record(conversation=f"c{n}", address=original["sender_address"], key=f"k{n}"))

    def raise_request(self, subject: str) -> approvals.Approval:
        kinds.raise_due(self.conn)
        found = approvals.latest(self.conn, self.kind, subject)
        assert found is not None and found.live, subject
        return found

    def approve(self, record):
        return decide(self.conn, record, "approve", self.monkeypatch)

    def skip(self, record):
        return decide(self.conn, record, "skip", self.monkeypatch)

    def attempt(self, subject: str) -> None:
        run = log.start_run(self.conn, self.agent, "inbox-send")
        due = send.due
        keep = kinds.item_id_of(subject)
        with self.monkeypatch.context() as patch:
            patch.setenv("JURA_GROWTH_RUN_ID", str(run))
            patch.setattr(send, "due", lambda conn: [item for item in due(conn) if item["id"] == keep])
            send.send_due(self.conn)

    def went_out(self) -> int:
        return len(self.sent)

    def seen_at_call(self) -> list[bool]:
        return [s["used"] for s in self.sent]

    def change(self, subject: str) -> None:
        self.conn.execute("UPDATE inbox_items SET draft = draft || ' (changed)' WHERE id = ?", (kinds.item_id_of(subject),))

    def remove(self, subject: str) -> None:
        """They opted out: the address suppressed, so the reply is gone."""
        item = store.get(self.conn, kinds.item_id_of(subject))
        suppression.add(self.conn, email=item["sender_address"], reason="unsubscribe", source="reply")

    def switch(self, on: bool) -> None:
        buttons(self.monkeypatch, not on)

    def fail_in_flight(self, on: bool) -> None:
        if on:
            self.conn.execute(
                "CREATE TEMP TRIGGER fail_in_flight BEFORE UPDATE OF send_attempts ON inbox_items "
                "BEGIN SELECT RAISE(ABORT, 'in-flight marker failed'); END"
            )
        else:
            self.conn.execute("DROP TRIGGER IF EXISTS temp.fail_in_flight")

    def hook_ran(self, hook: str, subject: str) -> int:
        item = kinds.item_id_of(subject)
        return len([e for e in aw.events(self.conn, "inbox.approval_closed") if e["item"] == item and e["hook"] == hook])


ADAPTER = EmailReplyAdapter
