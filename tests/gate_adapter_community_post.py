"""The gate-matrix adapter for `community-post` (BP-02b). The contract is in
`test_approval_gates.py`'s docstring.

- The gated action is `publish next` (`claim.next_item`); "went out" means it handed the item out.
  At hand-out the double reads the approval and the item on a fresh connection, as the fake
  `claude` binary does in BP-03 (G21, AC-M4.3): the record must already be used and the item
  `claimed`.
- An item is one planned post in its own group, joined as the Jura Page with its rules and days
  confirmed (any day open), on the first day whose posting window is still open. Each group is
  fresh, so no community cap stands in the way of the one claim a case makes.
- `publish next` claims the oldest claimable item, not a named one, so `attempt` holds the other
  ready items back while it runs, and puts them back after.
- The kind's switch is `browser` in `config/community.yaml`: off refuses without claiming.
- The in-flight marker is `publish_items.state = 'claimed'`; a temporary trigger makes it fail.
- A change edits the post's text; an item is gone once the post is posted by hand
  (`community posted`).
"""

from __future__ import annotations

from datetime import date, timedelta

import approval_world as aw
import publish_world as pw
from jura_growth import approvals, timeutil
from jura_growth.agents.community import plan
from jura_growth.agents.publish import claim, items

WHY = {"on_skip": "skipped", "on_expire": "expired", "on_lapse": "lapsed"}


def open_day() -> date:
    """Today, or tomorrow once today's posting window has closed."""
    now = timeutil.now_sgt()
    day = now.date()
    return day if now < pw.limits_window(day)[1] else day + timedelta(days=1)


def hold_others(conn, subject: str, action) -> None:
    """Run `action` with every other ready item set aside, then put them back."""
    mine = items.item_id(subject)
    held = [r["id"] for r in conn.execute("SELECT id FROM publish_items WHERE state = 'ready' AND id != ?", (mine,))]
    conn.executemany("UPDATE publish_items SET state = 'withdrawn' WHERE id = ?", [(i,) for i in held])
    try:
        action()
    finally:
        conn.executemany("UPDATE publish_items SET state = 'ready' WHERE id = ? AND state = 'withdrawn'", [(i,) for i in held])


class PublishGate:
    """What the three publish-queue adapters share: the claim, its double and its in-flight marker."""

    agent = items.AGENT
    applied_on_decide = False

    def __init__(self, *, conn, monkeypatch, tmp_path):
        self.conn = conn
        self.monkeypatch = monkeypatch
        pw.social_config(monkeypatch)
        pw.community_config(monkeypatch)
        monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
        aw.at(monkeypatch, aw.NOW)
        self.handed: list[dict] = []
        self.changes = 0

    def twin(self, subject: str) -> str:
        """A second item over the same post or group: its content reads the same."""
        cursor = self.conn.execute(
            "INSERT INTO publish_items (label, kind, platform, ref, parent_item, target_url, posting_identity, content_json,"
            " day, created_at) SELECT 'P-twin', kind, platform, ref, parent_item, target_url, posting_identity, content_json,"
            " day, created_at FROM publish_items WHERE id = ?",
            (items.item_id(subject),),
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
        def claim_once():
            handed = claim.next_item(self.conn, run_id=pw.run(self.conn))
            if handed.item is not None:
                self.handed.append({"subject": handed.item.subject, **pw.fresh_state(handed.approval.id)})

        hold_others(self.conn, subject, claim_once)

    def went_out(self) -> int:
        return len(self.handed)

    def seen_at_call(self) -> list[bool]:
        return [bool(h["used_at"] and h["used_by_run"] and h["state"] == "claimed") for h in self.handed]

    def switch(self, on: bool) -> None:
        pw.community_config(self.monkeypatch, browser=not on)

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


class CommunityPostAdapter(PublishGate):
    kind = items.COMMUNITY_POST_KIND

    def item(self) -> str:
        self.changes += 1
        post = pw.planned(self.conn, pw.group(self.conn), day=open_day(), text=f"{pw.GROUP_TEXT} Post {self.changes}.")
        made = items.create_community_post(self.conn, post, run_id=None, request=False)
        assert made.item is not None, made.why
        return made.item.subject

    def change(self, subject: str) -> None:
        item = items.of(self.conn, subject)
        self.conn.execute("UPDATE community_posts SET text = text || ' (changed)' WHERE id = ?", (item.ref_id,))

    def remove(self, subject: str) -> None:
        """Posted by hand: `community posted`."""
        plan.mark_posted(self.conn, items.of(self.conn, subject).ref_id)


ADAPTER = CommunityPostAdapter
