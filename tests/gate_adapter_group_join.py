"""The gate-matrix adapter for `group-join`, the join itself (BP-02b). The answers step has its own
adapter, `gate_adapter_group_join_answers.py`. The contract is in `test_approval_gates.py`.

- The gated action is `publish next`, as for `community-post` (`gate_adapter_community_post.py`
  holds what the publish adapters share: the double, the held-back items, the switch and the
  in-flight marker).
- An item is a join proposed for a fresh good-fit group nobody has joined. The matrix raises more
  joins than one ISO week's proposal cap allows, so the adapter leaves the proposal count at zero;
  that cap is tested in `test_publish_community.py`. Each case claims at most one join, so the
  claim's own weekly cap never stands in the way.
- A change edits the group's URL (the join's destination); an item is gone once the group is
  removed (`community removed`).
"""

from __future__ import annotations

import publish_world as pw
from gate_adapter_community_post import PublishGate
from jura_growth import db
from jura_growth.agents.community import groups as groups_mod
from jura_growth.agents.publish import items


class GroupJoinAdapter(PublishGate):
    kind = items.JOIN_KIND

    def __init__(self, *, conn, monkeypatch, tmp_path):
        super().__init__(conn=conn, monkeypatch=monkeypatch, tmp_path=tmp_path)
        monkeypatch.setattr(items, "proposals_in_week", lambda conn, day: 0)

    def join(self) -> items.Item:
        made = items.create_join(self.conn, pw.not_joined(self.conn), run_id=None, request=False)
        assert made.item is not None, made.why
        return made.item

    def item(self) -> str:
        return self.join().subject

    def _group(self, subject: str) -> int:
        return items.of(self.conn, subject).ref_id

    def change(self, subject: str) -> None:
        self.changes += 1
        self.conn.execute("UPDATE community_groups SET url = url || ? WHERE id = ?", (f"-{self.changes}", self._group(subject)))

    def remove(self, subject: str) -> None:
        with db.atomic(self.conn):
            groups_mod.remove(self.conn, self._group(subject), "an admin removed a post")


ADAPTER = GroupJoinAdapter
