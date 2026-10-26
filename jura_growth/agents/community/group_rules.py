"""Confirming a group's rules is an approval (MC §5.7 `group-rules` row, §5.1 "Group rules"; ticket MC-05).

A group's rules and its open days unlock links and posting days there, so Ting Yu confirms them in
#approvals, never in Terminal:

- `community set <id> rules=…` (rules Ting Yu read inside the group) and `community set <id>
  rules_confirmed=yes` (over the rules text now recorded) raise a `group-rules` request, subject
  `group:<id>`, over the group id and the rules text. Rules the community run found by web search
  raise nothing by themselves. `publish note-rules` raises one too (browser publishing).
- **Approve** needs the open days typed in the decision: `/growth approve A-nnnn promo_days=…
  post_days=…`, each any, none, or days like sat,sun or mon-fri. It claims the request and sets
  `rules_confirmed` and both days fields through `groups.set_fields`, in the decision's own
  transaction (applied on decide). The card has no buttons.
- **Skip**, or no answer within 14 days: the rules stay unconfirmed, and posts there carry no link.

`community set` never sets `rules_confirmed=yes` or a days field itself (`set_by_hand`): days given
there are refused with a pointer to the decision. Confirmations made from Terminal before this kind
existed stand; `record_earlier_confirmations()` writes each down once as an event.
"""

from __future__ import annotations

import json
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta

from jura_growth import approval_settings, approvals, db, log
from jura_growth.agents.community import groups as groups_mod
from jura_growth.agents.community import rules as rules_mod

KIND = "group-rules"
DAY_KEYS = ("promo_days", "post_days")
TYPED = "promo_days=… post_days=…"
DAYS_HELP = f"refused: say the days: {TYPED}, each any, none, or days like sat,sun or mon-fri."


def subject(group_id: int) -> str:
    return f"group:{int(group_id)}"


def group_id_of(subject: str) -> int:
    return int(subject.removeprefix("group:"))


def _rules_text(group: dict | None) -> str:
    return unicodedata.normalize("NFC", ((group or {}).get("promo_rules") or "").strip())


def _open(conn: sqlite3.Connection, subject: str) -> dict | None:
    """The group, while it can still have its rules confirmed: there, not removed, with rules text."""
    group = groups_mod.get(conn, group_id_of(subject))
    if group is None or group["removed"] or not _rules_text(group):
        return None
    return group


# --- the kind -----------------------------------------------------------------


class GroupRules:
    """`group-rules`: content is the group id and its rules text; applied on decide."""

    name = KIND
    decision_args = DAY_KEYS
    args_help = DAYS_HELP

    def content(self, conn: sqlite3.Connection, subject: str) -> bytes | None:
        group = _open(conn, subject)
        if group is None:
            return None
        return json.dumps({"group": group["id"], "rules": _rules_text(group)}, sort_keys=True, ensure_ascii=False).encode("utf-8")

    def preview(self, conn: sqlite3.Connection, subject: str) -> approvals.Preview:
        """The rules text only, and the typed form (MC §5.6). No parsed days: showing the code's
        reading would invite approving it."""
        group = groups_mod.get(conn, group_id_of(subject))
        if group is None:
            return approvals.Preview(title=subject, text="The group is no longer in the register.", reason="")
        lines = (_rules_text(group) or "(no rules recorded)").splitlines()
        text = "\n".join([
            f"Rules: {lines[0]}" if len(lines) == 1 else "Rules:\n" + "\n".join(f"> {line}" for line in lines),
            f"Say which days are open for these rules: {TYPED}, each any, none, or days like sat,sun or mon-fri. "
            "promo_days limits promotional posts; post_days limits every post.",
        ])
        return approvals.Preview(title=f"Group {group['id']} {group['name']}", text=text, reason="")

    def deadlines(self, conn: sqlite3.Connection, subject: str, now: datetime) -> approvals.Deadlines:
        return approvals.Deadlines(decide_by=now + timedelta(days=approval_settings.deadline(KIND, "decide_by_days")), use_by=None)

    used_word = "applied"

    def on_approve(self, conn: sqlite3.Connection, subject: str, args: dict[str, str]) -> str:
        """Claim the request and set `rules_confirmed` and both days, inside the decision. Days
        that can't be read refuse the whole decision (BadArgs), so nothing is recorded."""
        days = {}
        for key in DAY_KEYS:
            try:
                days[key] = rules_mod.days_text(rules_mod.read_days(args.get(key) or ""))
            except ValueError as error:
                raise approvals.BadArgs(f"{DAYS_HELP} ({key}: {error})") from None
        approvals.use(conn, KIND, subject, run_id=log.current_run_id())
        group_id = group_id_of(subject)
        try:
            group = groups_mod.set_fields(conn, group_id, ["rules_confirmed=yes", *(f"{k}={v}" for k, v in days.items())])
        except groups_mod.GroupError as error:
            raise approvals.BadArgs(f"refused: {error}") from None
        return f"Group {group_id}'s rules are confirmed: {groups_mod.rules_for(group).summary()}."

    def on_skip(self, conn: sqlite3.Connection, subject: str) -> None:
        _set_aside(conn, subject, "community.group.rules_skipped")

    def on_expire(self, conn: sqlite3.Connection, subject: str) -> None:
        _set_aside(conn, subject, "community.group.rules_expired")

    def superseded_note(self, conn: sqlite3.Connection, subject: str) -> str:
        group = groups_mod.get(conn, group_id_of(subject))
        if group is None or group["removed"]:
            return "the group was removed"
        if not _rules_text(group):
            return "the rules text was cleared"
        return "the rules text changed"


def _set_aside(conn: sqlite3.Connection, subject: str, event: str) -> None:
    """Skip or no answer: the rules stay unconfirmed, and posts there carry no link (as before)."""
    log.event(conn, event, {"group": group_id_of(subject), "subject": subject}, agent=groups_mod.NAME)


# --- raising ------------------------------------------------------------------


def request(conn: sqlite3.Connection, group_id: int, *, reason: str, run_id: int | None = None) -> approvals.Approval | None:
    """Raise the group's request (A11: only `community set` and `publish note-rules` call this).
    Returns the live request when one is already waiting over the same rules."""
    return approvals.request(conn, KIND, subject(group_id), reason=reason, run_id=run_id)


def _raise(conn: sqlite3.Connection, group_id: int, reason: str) -> approvals.Approval | None:
    """Ting Yu asked: a request that lapsed unanswered is written as expired, and a new one raised."""
    made = request(conn, group_id, reason=reason)
    if made is not None and made.status == approvals.EXPIRED:
        made = request(conn, group_id, reason=reason)
    return made


EARLIER = "community.group.rules_confirmed_earlier"


def record_earlier_confirmations(conn: sqlite3.Connection) -> list[int]:
    """The one-off pass (X9): a group whose rules were confirmed from Terminal before this kind
    existed keeps its confirmation, and it is written down once as an event. A group confirmed
    through a decision has its own approval record and is left alone. It runs before every
    community run and every `community set`, and writes each group at most once. Returns the
    groups it recorded."""
    rows = db.rows(
        conn,
        "SELECT * FROM community_groups g WHERE g.rules_confirmed = 1 "
        "AND NOT EXISTS (SELECT 1 FROM approvals a WHERE a.kind = ? AND a.subject = 'group:' || g.id AND a.used_at IS NOT NULL) "
        "AND NOT EXISTS (SELECT 1 FROM events e WHERE e.kind = ? AND json_extract(e.payload_json, '$.group') = g.id) "
        "ORDER BY g.id",
        (KIND, EARLIER),
    )
    for group in rows:
        log.event(conn, EARLIER, {
            "group": group["id"], "rules": group["promo_rules"], "promo_days": group["promo_days_confirmed"],
            "post_days": group["post_days_confirmed"], "how": "confirmed from Terminal before group-rules approvals",
        }, agent=groups_mod.NAME)
    return [group["id"] for group in rows]


# --- `community set` ------------------------------------------------------------


@dataclass(frozen=True)
class SetOutcome:
    group: dict
    approval: approvals.Approval | None


def _pointer(approval: approvals.Approval | None) -> str:
    return f"decide {approval.id if approval is not None else 'it'} in #approvals with {TYPED}"


def _keys(pairs: list[str]) -> list[tuple[str, str, str]]:
    found = []
    for pair in pairs:
        if "=" not in pair:
            raise groups_mod.GroupError(f"expected key=value, got {pair!r}")
        key, _, value = pair.partition("=")
        found.append((key.strip().lower(), value.strip(), pair))
    return found


def set_by_hand(conn: sqlite3.Connection, group_id: int, pairs: list[str]) -> SetOutcome:
    """`community set`: apply Ting Yu's fields, and raise a request where the rules need his
    decision. Call it inside `db.transaction(conn)`; post the cards after the commit."""
    group = groups_mod.get(conn, group_id)
    if group is None:
        raise groups_mod.GroupError(f"no group {group_id}")
    parsed = _keys(pairs)
    live = _waiting(conn, group_id)
    if any(key in DAY_KEYS for key, _, _ in parsed):
        raise groups_mod.GroupError(
            "refused: open days are set only by a decision. Run community set "
            f"{group_id} rules_confirmed=yes, then {_pointer(live)}"
        )
    confirm = any(key == "rules_confirmed" and value.lower() in groups_mod.YES for key, value, _ in parsed)
    rest = [pair for key, value, pair in parsed if not (key == "rules_confirmed" and value.lower() in groups_mod.YES)]
    new_text = next((value for key, value, _ in reversed(parsed) if key in ("rules", "promo_rules")), None)
    if confirm and not (new_text if new_text is not None else _rules_text(group)):
        raise groups_mod.GroupError(f"set the rules first: community set {group_id} rules=…")
    if confirm and group["removed"]:
        raise groups_mod.GroupError(f"group {group_id} was removed, so there are no rules to confirm")
    if rest:
        group = groups_mod.set_fields(conn, group_id, rest)
    approval = None
    if confirm:
        approval = _raise(conn, group_id, "you asked to confirm these rules (community set rules_confirmed=yes)")
    elif new_text is not None and not group["rules_confirmed"]:
        approval = _raise(conn, group_id, "you recorded these rules (community set rules=…)")
    return SetOutcome(group, approval)


def _waiting(conn: sqlite3.Connection, group_id: int) -> approvals.Approval | None:
    row = db.one(
        conn, "SELECT id FROM approvals WHERE kind = ? AND subject = ? AND status = 'pending' ORDER BY id DESC LIMIT 1",
        (KIND, subject(group_id)),
    )
    return approvals.get(conn, approvals.format_id(row["id"])) if row else None


def answer(outcome: SetOutcome) -> str | None:
    """The line `community set` adds when a request is waiting."""
    if outcome.approval is None:
        return None
    if outcome.approval.status != approvals.PENDING:
        return f"{outcome.approval.id} is {outcome.approval.status}; nothing is waiting for a decision."
    return f"{outcome.approval.id}: decide it in #approvals with {TYPED}"
