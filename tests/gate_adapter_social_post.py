"""The gate-matrix adapter for `social-post` (BP-02a). The contract is in
`test_approval_gates.py`'s docstring.

- The gated action is `publish next` (`claim.next_item`); "went out" means it handed the item out.
  At hand-out the double reads the approval and the item on a fresh connection, as the fake
  `claude` binary does in BP-03 (G21, AC-M4.3): the record must already be used and the item
  `claimed`.
- An item is one `social_posts` draft and its publish item, in the next free platform and day
  whose posting window is still open (one draft per platform per day). All three platforms are
  in `browser` mode.
- `publish next` claims the oldest claimable item, not a named one, so `attempt` holds the other
  ready items back while it runs (their state, which the content doesn't cover), and puts them
  back after.
- The kind's switch is the platform's `publish_mode`: `draft` refuses without claiming.
- The in-flight marker is `publish_items.state = 'claimed'`; a temporary trigger makes it fail.
- An item is gone once its draft is posted by hand (`social published`).
"""

from __future__ import annotations

from datetime import date, timedelta

import approval_world as aw
import publish_world as pw
from jura_growth import approvals, db, timeutil
from jura_growth.agents.publish import claim, items
from jura_growth.agents.social import history

PLATFORMS = ("facebook", "linkedin", "instagram")
WHY = {"on_skip": "skipped", "on_expire": "expired", "on_lapse": "lapsed"}


class SocialPostAdapter:
    kind = items.SOCIAL_KIND
    agent = items.AGENT
    applied_on_decide = False

    def __init__(self, *, conn, monkeypatch, tmp_path):
        self.conn = conn
        self.monkeypatch = monkeypatch
        pw.social_config(monkeypatch, browser=PLATFORMS)
        monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
        aw.at(monkeypatch, aw.NOW)
        self.handed: list[dict] = []
        self._texts = 0

    # --- the world ------------------------------------------------------------------

    def _free_slot(self) -> tuple[date, str]:
        now = timeutil.now_sgt()
        day = now.date()
        while True:
            _, closes = pw.limits_window(day)
            if now < closes:
                for platform in PLATFORMS:
                    taken = db.scalar(self.conn, "SELECT 1 FROM social_posts WHERE date = ? AND platform = ?",
                                      (day.isoformat(), platform))
                    if not taken:
                        return day, platform
            day += timedelta(days=1)

    def item(self) -> str:
        day, platform = self._free_slot()
        self._texts += 1
        post = pw.draft(self.conn, platform, day=day, text=f"{pw.TEXT}\nPost {self._texts}.")
        made = items.create_social(self.conn, post, run_id=None, request=False)
        assert made.item is not None, made.why
        return made.item.subject

    def twin(self, subject: str) -> str:
        """A second item over the same draft: its content reads the same."""
        original = items.of(self.conn, subject)
        cursor = self.conn.execute(
            "INSERT INTO publish_items (label, kind, platform, ref, target_url, posting_identity, content_json, day, created_at)"
            " SELECT 'P-twin', kind, platform, ref, target_url, posting_identity, content_json, day, created_at"
            " FROM publish_items WHERE id = ?",
            (original.id,),
        )
        return items.subject_of(int(cursor.lastrowid or 0))

    def raise_request(self, subject: str) -> approvals.Approval:
        found = items.raise_request(self.conn, items.of(self.conn, subject), run_id=None)
        assert found is not None, subject
        return found

    def approve(self, record):
        return pw.decide(self.conn, record, "approve")

    def skip(self, record):
        return pw.decide(self.conn, record, "skip")

    def attempt(self, subject: str) -> None:
        mine = items.item_id(subject)
        held = [r["id"] for r in self.conn.execute("SELECT id FROM publish_items WHERE state = 'ready' AND id != ?", (mine,))]
        self.conn.executemany("UPDATE publish_items SET state = 'withdrawn' WHERE id = ?", [(i,) for i in held])
        try:
            run = pw.run(self.conn)
            handed = claim.next_item(self.conn, run_id=run)
        finally:
            self.conn.executemany("UPDATE publish_items SET state = 'ready' WHERE id = ? AND state = 'withdrawn'",
                                  [(i,) for i in held])
        if handed.item is not None:
            self.handed.append({"subject": handed.item.subject, **pw.fresh_state(handed.approval.id)})

    def went_out(self) -> int:
        return len(self.handed)

    def seen_at_call(self) -> list[bool]:
        return [bool(h["used_at"] and h["used_by_run"] and h["state"] == "claimed") for h in self.handed]

    def change(self, subject: str) -> None:
        item = items.of(self.conn, subject)
        self.conn.execute("UPDATE social_posts SET text = text || ' (changed)' WHERE id = ?", (item.ref_id,))

    def remove(self, subject: str) -> None:
        """Posted by hand: `social published`."""
        item = items.of(self.conn, subject)
        history.mark_published(self.conn, date.fromisoformat(item.day), item.platform, None)

    def switch(self, on: bool) -> None:
        pw.social_config(self.monkeypatch, browser=() if on else PLATFORMS)

    def fail_in_flight(self, on: bool) -> None:
        if on:
            self.conn.execute(
                "CREATE TEMP TRIGGER fail_in_flight BEFORE UPDATE OF state ON publish_items "
                "WHEN NEW.state = 'claimed' BEGIN SELECT RAISE(ABORT, 'in-flight marker failed'); END"
            )
        else:
            self.conn.execute("DROP TRIGGER IF EXISTS temp.fail_in_flight")

    def hook_ran(self, hook: str, subject: str) -> int:
        label = items.of(self.conn, subject).label
        return len([e for e in aw.events(self.conn, "publish.item_withdrawn") if e["item"] == label and e["why"] == WHY[hook]])


ADAPTER = SocialPostAdapter
