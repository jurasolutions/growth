"""The gate-matrix adapter for `group-rules` (ticket MC-05).

`group-rules` is applied on decide (test strategy v3 §5.2): approving with the typed days claims the
request and sets `rules_confirmed` and both days fields inside the decision. The gated action
`attempt()` runs is every way Terminal could still try to confirm a group's rules outside a decision:
`community set <id> rules_confirmed=yes`, the same with the days, and the days alone. "Went out"
means `rules_confirmed` or either days field changed during an attempt. The decision's own change is
traced in `test_group_rules.py`.
"""

from __future__ import annotations

from click.testing import CliRunner

from jura_growth import approvals, db
from jura_growth.agents.community import group_rules
from jura_growth.agents.community import groups as groups_mod
from jura_growth.cli import cli

import approval_world as aw

RULES = "Promo posts on Saturdays only."
DAYS = {"promo_days": "sat,sun", "post_days": "any"}
ATTEMPTS = (
    ("rules_confirmed=yes",),
    ("rules_confirmed=yes", "promo_days=any", "post_days=any"),
    ("promo_days=any", "post_days=any"),
)


def _invoke(*args):
    return CliRunner().invoke(cli, list(args), catch_exceptions=False)


class GroupRulesAdapter:
    kind = group_rules.KIND
    agent = groups_mod.NAME
    applied_on_decide = True

    def __init__(self, *, conn, monkeypatch, tmp_path):
        self.conn = conn
        self.number = 0
        self.changed = 0
        monkeypatch.setenv("CONTROL_DISCORD_USER_ID", aw.CONTROL_ID)
        aw.at(monkeypatch, aw.NOW)

    def item(self, rules: str = RULES) -> str:
        """A joined group the community run found, with its rules recorded."""
        self.number += 1
        status, group_id, messages = groups_mod.add(self.conn, {
            "channel": "facebook", "name": f"SG owners {self.number}", "url": f"https://www.facebook.com/groups/sg{self.number}",
            "promo_rules": rules, "fit": "good fit", "fit_reason": "Owners asking about admin.",
            "source_urls": [f"https://example.sg/groups#sg{self.number}"],
        })
        assert status == "added", messages
        self.conn.execute("UPDATE community_groups SET joined = 1 WHERE id = ?", (group_id,))
        self.conn.commit()
        return group_rules.subject(group_id)

    def twin(self, subject: str) -> str:
        """Another group with the very same rules text."""
        return self.item(groups_mod.get(self.conn, group_rules.group_id_of(subject))["promo_rules"])

    def raise_request(self, subject: str) -> approvals.Approval:
        result = _invoke("community", "set", str(group_rules.group_id_of(subject)), "rules_confirmed=yes")
        assert result.exit_code == 0, result.output
        row = db.one(self.conn, "SELECT id FROM approvals WHERE kind = ? AND subject = ? AND status = 'pending'", (self.kind, subject))
        assert row is not None, subject
        return aw.get(self.conn, approvals.format_id(row["id"]))

    def approve(self, approval):
        return aw.approve(self.conn, approval, args=dict(DAYS))

    def skip(self, approval):
        return aw.skip(self.conn, approval)

    def _state(self, subject: str):
        group = groups_mod.get(self.conn, group_rules.group_id_of(subject))
        return group and (group["rules_confirmed"], group["promo_days_confirmed"], group["post_days_confirmed"])

    def attempt(self, subject: str) -> None:
        group_id = str(group_rules.group_id_of(subject))
        for pairs in ATTEMPTS:
            before = self._state(subject)
            _invoke("community", "set", group_id, *pairs)
            self.changed += self._state(subject) != before

    def went_out(self) -> int:
        return self.changed

    def seen_at_call(self) -> list[bool]:
        return []  # G21 and G22 don't apply: nothing goes out after the decision (§5.2)

    def change(self, subject: str) -> None:
        with db.transaction(self.conn):
            groups_mod.set_fields(self.conn, group_rules.group_id_of(subject), ["rules=Promo posts on Sundays only."])

    def remove(self, subject: str) -> None:
        with db.transaction(self.conn):
            groups_mod.remove(self.conn, group_rules.group_id_of(subject), "an admin removed a post")

    def switch(self, on: bool) -> None:
        """`group-rules` has no switch of its own; the pause flags are traced in its tests."""

    def fail_in_flight(self, on: bool) -> None:
        """Nothing is in flight: the change is made inside the decision."""

    def hook_ran(self, hook: str, subject: str) -> int:
        event = {"on_skip": "community.group.rules_skipped", "on_expire": "community.group.rules_expired"}.get(hook)
        if event is None:
            return 0  # a group-rules request can't lapse: approving applies it
        return len([e for e in aw.events(self.conn, event) if e["subject"] == subject])


ADAPTER = GroupRulesAdapter
