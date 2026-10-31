"""The gate-matrix adapter for `social-reply` (inbox watch ticket 06). The contract is in
`test_approval_gates.py`'s docstring.

- The gated action is `inbox reply-due` then `inbox reply-next`: "went out" means it handed the reply's
  text out. At hand-out the double reads the record on a fresh connection, as the fake `claude` does (G21).
- An item is one person's direct message with a draft ready for its card, `inbox_item:<id>`, as triage
  leaves it. `reply-next` claims the first approved reply, not a named one, so `attempt` narrows what is
  due, and reports a clean read of that thread.
- The kind's switch reads the `publish` flag: the two share the accounts, so a stop signal stops this too.
- The in-flight marker is `inbox_items.send_attempts`; a temporary trigger makes it fail.
- An item is gone once the Page has answered it by hand.
"""

from __future__ import annotations

import approval_world as aw
import publish_world as pw
from jura_growth import approvals, db, log, pause
from jura_growth.agents.inbox import kinds, reply_run, social, store
from test_scout_support import buttons

DRAFT = "We help with invoices and the copying between systems that follows. The first step is a short discovery call."
SAID = "Do you work with clinics?"
NAME = "Priya Nair"


def thread(n: int) -> str:
    return f"https://www.instagram.com/direct/t/{7000 + n}/"


class SocialReplyAdapter:
    kind = social.KIND
    agent = social.AGENT
    applied_on_decide = False

    def __init__(self, *, conn, monkeypatch, tmp_path):
        self.conn = conn
        self.monkeypatch = monkeypatch
        buttons(monkeypatch)
        monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
        aw.at(monkeypatch, aw.NOW)
        self.sent: list[dict] = []
        self._next = 0

    # --- the world ------------------------------------------------------------------

    def _record(self, *, conversation: str, url: str, key: str) -> int:
        recorded = store.record(self.conn, store.Reaction(
            source="instagram-dm", key=key, conversation=conversation, sender_name=NAME, sender_domain="instagram.com", text=SAID,
            target=url, thread={"surface": "instagram-primary", "occurrence": 1},
        ))
        store.update_triage(self.conn, recorded.item_id, state=store.TRIAGED, note="", kind="question", priority="normal",
                            language="English", draft=DRAFT, promised=False)
        return recorded.item_id

    def item(self) -> str:
        self._next += 1
        n = self._next
        return kinds.subject_of(self._record(conversation=f"c{n}", url=thread(n), key=f"k{n}"))

    def twin(self, subject: str) -> str:
        """Another conversation with the same person, word for word, on the same thread."""
        original = store.get(self.conn, kinds.item_id_of(subject))
        self._next += 1
        n = self._next
        return kinds.subject_of(self._record(conversation=f"c{n}", url=original["target"], key=f"k{n}"))

    def raise_request(self, subject: str) -> approvals.Approval:
        social.raise_due(self.conn)
        found = approvals.latest(self.conn, self.kind, subject)
        assert found is not None and found.live, subject
        return found

    def approve(self, record):
        return pw.decide(self.conn, record, "approve", self.monkeypatch)

    def skip(self, record):
        return pw.decide(self.conn, record, "skip", self.monkeypatch)

    def _clean_read(self, item_id: int):
        record = approvals.latest(self.conn, self.kind, kinds.subject_of(item_id))
        return reply_run.read_of({"approval": record.id if record else "A-0000", "target": "found", "acting_as": "jura_solutions", "author": NAME,
                                  "newest_from_them": SAID, "page_answered": False})

    def attempt(self, subject: str) -> None:
        run = log.start_run(self.conn, self.agent, "inbox-reply")
        keep = kinds.item_id_of(subject)
        due = reply_run.due
        with self.monkeypatch.context() as patch:
            patch.setattr(reply_run, "due", lambda conn: [item for item in due(conn) if item["id"] == keep])
            patch.setattr(reply_run, "why_not_now", lambda conn, *, run_id: None)  # the gap is its own test
            reply_run.hand_out(self.conn, run_id=run)
            handed = reply_run.next_reply(self.conn, self._clean_read(keep), run_id=run)
        if handed.get("due"):
            fresh = db.connect(migrate_now=False)
            try:
                row = fresh.execute("SELECT used_at, used_by_run FROM approvals WHERE kind = ? AND subject = ? AND used_at IS NOT NULL",
                                    (self.kind, subject)).fetchone()
            finally:
                fresh.close()
            self.sent.append({"used": bool(row and row["used_at"] and row["used_by_run"])})

    def went_out(self) -> int:
        return len(self.sent)

    def seen_at_call(self) -> list[bool]:
        return [s["used"] for s in self.sent]

    def change(self, subject: str) -> None:
        self.conn.execute("UPDATE inbox_items SET draft = draft || ' Changed.' WHERE id = ?", (kinds.item_id_of(subject),))

    def remove(self, subject: str) -> None:
        store.close_and_tell(self.conn, kinds.item_id_of(subject), store.ANSWERED_BY_HAND, "The Page answered.")

    def switch(self, on: bool) -> None:
        if on:
            pause.pause(self.conn, social.PUBLISH, "a stop signal", notify=False)
        else:
            pause.resume(self.conn, social.PUBLISH)

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


ADAPTER = SocialReplyAdapter
