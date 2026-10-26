"""Confirming a group's rules is an approval (MC §5.7 `group-rules` row, §5.1 "Group rules"; ticket MC-05).

A group's rules and its open days unlock links and posting days there, so Ting Yu confirms them in
#approvals, never in Terminal:

- `community set <id> rules=…` (rules Ting Yu read inside the group) and `community set <id>
  rules_confirmed=yes` (over the rules text now recorded) raise a `group-rules` request, subject
  `group:<id>`, over the group id and the rules text. Rules the community run found by web search
  raise nothing by themselves. `publish note-rules` raises one too, for rules a publish run saw
  inside the group (`note_seen`, browser publishing#06).
- **Approve** needs the open days typed in the decision: `/growth approve A-nnnn promo_days=…
  post_days=…`, each any, none, or days like sat,sun or mon-fri. It claims the request and sets
  `rules_confirmed` and both days fields through `groups.set_fields`, in the decision's own
  transaction (applied on decide). The card has no buttons.
- **Skip**, or no answer within 14 days: nothing changes. A group that wasn't confirmed stays
  unconfirmed, and posts there carry no link.
- **Changing the days.** `rules_confirmed=yes` on a group already confirmed raises a new request
  over the same rules; approving it replaces the days, and skipping it keeps the confirmation and
  days Ting Yu gave before (code review 05 S5, the conductor's decision).

Only the decision writes `rules_confirmed=yes` or a day: `community set` reads its words with the
same parser as `groups.set_fields` (`groups.parse_pairs`), refuses the days with a pointer to the
decision, and turns a yes, however it is spelled or quoted, into the request. `set_fields` itself
refuses those fields unless `on_approve` asks (`by_decision`). Confirmations made from Terminal
before this kind existed stand; `record_earlier_confirmations()` writes each down once, in a pass
that runs one time only.
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
RULES_KEYS = ("rules", "promo_rules")


def subject(group_id: int) -> str:
    return f"group:{int(group_id)}"


def group_id_of(subject: str) -> int:
    return int(subject.removeprefix("group:"))


def _rules_text(group: dict | None) -> str:
    """The group's rules as stored, trimmed, with no Unicode normalisation: the request's content
    hashes these exact bytes (ADR 0003 as amended)."""
    return ((group or {}).get("promo_rules") or "").strip()


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
    used_word = "applied"

    def content(self, conn: sqlite3.Connection, subject: str) -> bytes | None:
        group = _open(conn, subject)
        if group is None:
            return None
        return json.dumps({"group": group["id"], "rules": _rules_text(group)}, sort_keys=True, ensure_ascii=False).encode("utf-8")

    def preview(self, conn: sqlite3.Connection, subject: str) -> approvals.Preview:
        """The rules text only (MC §5.6); the card's answer line carries the typed form. No parsed
        days: showing the code's reading would invite approving it."""
        group = groups_mod.get(conn, group_id_of(subject))
        if group is None:
            return approvals.Preview(title=subject, text="The group is no longer in the register.", reason="")
        lines = (_rules_text(group) or "(no rules recorded)").splitlines()
        text = "\n".join([
            f"Rules: {lines[0]}" if len(lines) == 1 else "Rules:\n" + "\n".join(f"> {line}" for line in lines),
            "promo_days limits promotional posts and post_days limits every post. Each is any, none, or days "
            "like sat,sun or mon-fri.",
        ])
        return approvals.Preview(title=f"Group {group['id']} {group['name']}", text=text, reason="")

    def deadlines(self, conn: sqlite3.Connection, subject: str, now: datetime) -> approvals.Deadlines:
        return approvals.Deadlines(decide_by=now + timedelta(days=approval_settings.deadline(KIND, "decide_by_days")), use_by=None)

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
            group = groups_mod.set_parsed(conn, group_id, [("rules_confirmed", "yes"), *days.items()], by_decision=True)
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
    """Skip or no answer changes nothing: an unconfirmed group stays unconfirmed (its posts carry
    no link), and a confirmed one keeps the days it had."""
    log.event(conn, event, {"group": group_id_of(subject), "subject": subject}, agent=groups_mod.NAME)


# --- raising ------------------------------------------------------------------


def request(conn: sqlite3.Connection, group_id: int, *, reason: str, run_id: int | None = None) -> approvals.Approval | None:
    """Raise the group's request (A11: `community set` calls this, and `publish note-rules`
    through `note_seen`).
    Returns the live request when one is already waiting over the same rules."""
    return approvals.request(conn, KIND, subject(group_id), reason=reason, run_id=run_id)


def _raise_fresh(conn: sqlite3.Connection, group_id: int, reason: str) -> approvals.Approval | None:
    """`request()`, for when Ting Yu asked. If the waiting request had passed its decide-by,
    `request()` writes its expiry and returns it; the second call then finds nothing live and
    raises a new one."""
    made = request(conn, group_id, reason=reason)
    if made is not None and made.status == approvals.EXPIRED:
        made = request(conn, group_id, reason=reason)
    return made


MAX_SEEN_CHARS = 4000


def note_seen(conn: sqlite3.Connection, group_id: int, text: str, *, run_id: int | None) -> approvals.Approval | None:
    """`publish note-rules`: rules a publish run saw inside the group (browser publishing PRD
    §5.4, X10). They are recorded as the group's rules and raise one `group-rules` request, so
    Ting Yu confirms them and the open days. Rules he already confirmed, seen unchanged, raise
    nothing; rules that differ clear the old confirmation and days, as `community set rules=…`
    does. Returns the live request, or None when nothing needs deciding. Call it inside a
    transaction; post the card once that has committed (A12)."""
    seen = unicodedata.normalize("NFC", text.strip())
    if not seen:
        raise groups_mod.GroupError("the rules file is empty")
    if len(seen) > MAX_SEEN_CHARS:
        raise groups_mod.GroupError(f"the rules seen are longer than {MAX_SEEN_CHARS} characters")
    group = groups_mod.get(conn, group_id)
    if group is None:
        raise groups_mod.GroupError(f"no group {group_id}")
    if group["removed"]:
        raise groups_mod.GroupError(f"group {group_id} was removed, so there are no rules to confirm")
    # The same words with other line breaks or spacing are the same rules (code review 06, S3):
    # two copies taken from a page rarely match byte for byte.
    same = _collapsed(seen) == _collapsed(_rules_text(group))
    if same and group["rules_confirmed"]:
        log.event(conn, "community.group.rules_seen", {"id": group_id, "changed": False}, agent=groups_mod.NAME, run_id=run_id)
        return None
    if not same:
        groups_mod.set_parsed(conn, group_id, [("rules", seen)])
    log.event(conn, "community.group.rules_seen", {"id": group_id, "changed": True}, agent=groups_mod.NAME, run_id=run_id)
    return request(conn, group_id, reason="a publish run saw these rules inside the group", run_id=run_id)


def _collapsed(text: str) -> str:
    return " ".join(text.split())


EARLIER = "community.group.rules_confirmed_earlier"
EARLIER_DONE = "community.group.rules_confirmed_earlier.done"


def record_earlier_confirmations(conn: sqlite3.Connection) -> list[int]:
    """The one-off pass (X9): each group whose rules were confirmed from Terminal before this kind
    existed keeps its confirmation, and is written down once as an event. A group confirmed
    through a decision has its own approval record and is left alone. The pass runs one time
    only: it writes `EARLIER_DONE` when it finishes, and does nothing once that exists, so a later
    `rules_confirmed = 1` without a decision is never written down as history (code review 05 S4).
    Call it inside a transaction. Returns the groups it recorded."""
    if db.scalar(conn, "SELECT 1 FROM events WHERE kind = ? LIMIT 1", (EARLIER_DONE,)):
        return []
    rows = db.rows(
        conn,
        "SELECT * FROM community_groups g WHERE g.rules_confirmed = 1 "
        "AND NOT EXISTS (SELECT 1 FROM approvals a WHERE a.kind = ? AND a.subject = 'group:' || g.id AND a.used_at IS NOT NULL) "
        "ORDER BY g.id",
        (KIND,),
    )
    for group in rows:
        log.event(conn, EARLIER, {
            "group": group["id"], "rules": group["promo_rules"], "promo_days": group["promo_days_confirmed"],
            "post_days": group["post_days_confirmed"], "how": "confirmed from Terminal before group-rules approvals",
        }, agent=groups_mod.NAME)
    recorded = [group["id"] for group in rows]
    log.event(conn, EARLIER_DONE, {"groups": recorded}, agent=groups_mod.NAME)
    return recorded


# --- `community set` ------------------------------------------------------------


@dataclass(frozen=True)
class SetOutcome:
    group: dict
    approval: approvals.Approval | None


def _pointer(approval: approvals.Approval | None) -> str:
    return f"decide {approval.id if approval is not None else 'it'} in #approvals with {TYPED}"


def set_by_hand(conn: sqlite3.Connection, group_id: int, pairs: list[str]) -> SetOutcome:
    """`community set`: apply Ting Yu's fields, and raise a request where the rules need his
    decision. Call it inside `db.transaction(conn)`; post the cards after the commit."""
    group = groups_mod.get(conn, group_id)
    if group is None:
        raise groups_mod.GroupError(f"no group {group_id}")
    parsed = groups_mod.parse_pairs(pairs)
    if any(key in DAY_KEYS for key, _ in parsed):
        waiting = next(iter(approvals.pending(conn, KIND, subject(group_id))), None)
        raise groups_mod.GroupError(
            "refused: open days are set only by a decision. Run community set "
            f"{group_id} rules_confirmed=yes, then {_pointer(waiting)}"
        )
    for key, value in parsed:
        if key == "rules_confirmed" and value.lower() not in groups_mod.YES | groups_mod.NO:
            raise groups_mod.GroupError("rules_confirmed must be yes or no")
    confirm = any(groups_mod.is_gated(key, value) for key, value in parsed)
    rest = [(key, value) for key, value in parsed if not groups_mod.is_gated(key, value)]
    new_text = next((value for key, value in reversed(parsed) if key in RULES_KEYS), None)
    if confirm and not (new_text if new_text is not None else _rules_text(group)):
        raise groups_mod.GroupError(f"set the rules first: community set {group_id} rules=…")
    if confirm and group["removed"]:
        raise groups_mod.GroupError(f"group {group_id} was removed, so there are no rules to confirm")
    if rest:
        group = groups_mod.set_parsed(conn, group_id, rest)
    approval = None
    if confirm:
        approval = _raise_fresh(conn, group_id, "you asked to confirm these rules (community set rules_confirmed=yes)")
    elif new_text is not None and not group["rules_confirmed"]:
        approval = _raise_fresh(conn, group_id, "you recorded these rules (community set rules=…)")
    return SetOutcome(group, approval)


def answer(outcome: SetOutcome) -> str | None:
    """The line `community set` adds when a request is waiting."""
    if outcome.approval is None:
        return None
    if outcome.approval.status != approvals.PENDING:
        return f"{outcome.approval.id} is {outcome.approval.status}; nothing is waiting for a decision."
    return f"{outcome.approval.id}: decide it in #approvals with {TYPED}"
