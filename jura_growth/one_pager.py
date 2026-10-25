"""The one-pager's text (MC SC1, §5.4).

Built from a `mission.Snapshot`, never from the database, in this order: the
header, Needs you (the health strip), Approvals waiting, Today, Yesterday and
Ask me. `messages()` is what goes to Discord: the text through
`privacy.for_discord()`, split by `discord.split()` only past 2,000
characters. `jura-growth one-pager --no-post` prints it; posting it to
#mission-control with the 14-day grid, and the 08:00 job, are ticket MC-09.

The one-pager is for Ting Yu only and shows only figures the engine recorded.
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from jura_growth import discord, health, mission, privacy, slots

ASK_ME = ("`/growth status`", "`/growth approvals`", "`/growth one-pager`", "`/growth pause <agent|all>`", "`/growth resume <agent|all>`")
SLOTS_LISTED = 3  # a job with more slots in a day shows counts per status instead


def text(snapshot: mission.Snapshot) -> str:
    now = snapshot.now
    parts = [f"**{health.day_label(now)}, as of {now:%H:%M} SGT**"]
    parts += _section("Needs you", _needs_you(snapshot))
    parts += _section("Approvals waiting", _approvals(snapshot))
    parts += _section("Today", _today(snapshot))
    parts += _section("Yesterday", _yesterday(snapshot))
    parts += _section("Ask me", [" · ".join(ASK_ME)])
    return "\n".join(parts)


def messages(snapshot: mission.Snapshot) -> list[str]:
    """The one-pager as Discord messages, masked and split."""
    return discord.split(privacy.for_discord(text(snapshot)))


def _section(name: str, lines: list[str]) -> list[str]:
    return ["", f"**{name}**", *lines]


def _needs_you(snapshot: mission.Snapshot) -> list[str]:
    items = health.strip(snapshot)
    if not items:
        return ["Nothing needs you"]
    lines = []
    for item in items:
        first, *rest = item.splitlines()
        lines += [f"- {first}", *rest]
    return lines


def _unavailable(snapshot: mission.Snapshot) -> str:
    if snapshot.db_state == mission.MISSING:
        return "Nothing recorded yet: growth.db doesn't exist"
    if snapshot.db_state == mission.UNFINISHED_WRITE:
        return "Not available: growth.db has an unfinished write"
    if snapshot.db_state == mission.UNREADABLE:
        return "Not available: growth.db couldn't be read"
    return "Not available: growth.db isn't migrated yet"


def _approvals(snapshot: mission.Snapshot) -> list[str]:
    if snapshot.approvals is None:
        return [_unavailable(snapshot)]
    waiting = [r for r in snapshot.approvals if r.state == mission.WAITING]
    following = snapshot.next_one_pager or snapshot.now + timedelta(days=1)
    last = snapshot.last_one_pager or snapshot.now - timedelta(days=1)
    lines = []
    if waiting:
        counts = Counter(r.kind for r in waiting)
        lines.append(", ".join(f"{kind} {counts[kind]}" for kind in sorted(counts)))
        oldest = min(waiting, key=lambda r: (r.requested_at, r.id))
        lines.append(
            f"Oldest: {oldest.id} ({oldest.kind}), waiting since {health.when(oldest.requested_at)}, "
            f"decide by {health.when(oldest.decide_by)}"
        )
        lapsing = sorted((r for r in waiting if r.decide_by < following), key=lambda r: (r.decide_by, r.id))
        if lapsing:
            lines.append("Lapsing before the next one-pager: " + ", ".join(f"{r.id} ({health.when(r.decide_by)})" for r in lapsing))
    else:
        lines.append("Nothing waiting")
    terminal = sorted(
        ((r.decided_at, r) for r in snapshot.approvals if r.decided_origin == "terminal" and r.decided_at and r.decided_at > last),
        key=lambda pair: (pair[0], pair[1].id),
    )
    if terminal:
        decided = (f"{r.id} {'skipped' if r.state == mission.SKIPPED else 'approved'}" for _, r in terminal)
        lines.append("Decided in Terminal since the last one-pager: " + ", ".join(decided))
    return lines


def _today(snapshot: mission.Snapshot) -> list[str]:
    if not snapshot.slots:
        return [_unavailable(snapshot)]
    today = snapshot.now.date()
    lines = []
    for (job, day), states in snapshot.slots.items():
        if day != today:
            continue
        if not states:
            lines.append(f"`{job}` no slot today")
        elif len(states) > SLOTS_LISTED:
            cell = slots.day_cell(states)
            lines.append(f"`{job}` " + ", ".join(f"{n} {status}" for status, n in cell.counts.items()))
        else:
            lines.append(f"`{job}` " + ", ".join(_slot(slot) for slot in states))
    return lines


def _slot(slot: slots.SlotStatus) -> str:
    reason = f" ({slot.reason})" if slot.status == "skipped" and slot.reason else ""
    return f"{slot.at:%H:%M} {slot.status}{reason}"


def _yesterday(snapshot: mission.Snapshot) -> list[str]:
    if snapshot.yesterday is None:
        return [_unavailable(snapshot)]
    lines = [f"- {line}" for line in snapshot.yesterday.lines] or ["- No agent figures recorded."]
    lines.append(f"Claude spend: US${snapshot.yesterday.spend:.2f} yesterday, US${snapshot.spend_today:.2f} so far today")
    return lines
