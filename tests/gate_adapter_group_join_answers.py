"""The gate-matrix adapter for `group-join`'s membership-answers step (BP-02b; test strategy v3
§5.2: "seven kinds, plus the `group-join` answers step"). The contract is in
`test_approval_gates.py`.

- An item is the answers for a fresh join (raised without a request of its own, so the join's
  `group-join` request never enters a case's counts), as `publish done --outcome questions` will
  raise them in browser publishing#06.
- A change is the run reporting the questions again with a different answer: the answers waiting
  for that join are replaced in the item, and the core sees the content change.
- An item is gone once the group is removed (`community removed`).
"""

from __future__ import annotations

import publish_world as pw
from gate_adapter_group_join import GroupJoinAdapter
from jura_growth.agents.publish import items


class GroupJoinAnswersAdapter(GroupJoinAdapter):
    kind = items.JOIN_KIND

    def item(self) -> str:
        made = items.create_join_answers(self.conn, self.join(), pw.QUESTIONS, run_id=None, request=False)
        assert made.item is not None, made.why
        return made.item.subject

    def change(self, subject: str) -> None:
        self.changes += 1
        answers = items.of(self.conn, subject)
        join = items.get(self.conn, answers.parent_item)
        changed = [dict(pw.QUESTIONS[0]), {**pw.QUESTIONS[1], "answer": f"Yes, every one of them ({self.changes})."}]
        made = items.create_join_answers(self.conn, join, changed, run_id=None, request=False)
        assert made.item is not None and made.item.id == answers.id, made.why


ADAPTER = GroupJoinAnswersAdapter
