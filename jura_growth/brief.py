"""The morning picture: mission control at a glance (MC amendment 2026-10-31).

One image in #mission-control at 09:00 SGT, after the agents have drafted, that
reads at the size Discord shows it. Built from a `mission.Snapshot`, never from
the database, in the order Ting Yu acts on it:

- the verdict: how many things to decide and to fix;
- Decide: approval requests still waiting, soonest to lapse first;
- Fix: the health strip, one short line each (`health.strip(short=True)`);
- This morning: what each growth agent did and how many requests it raised;
- Yesterday: the figures the engine recorded, and what runs later today.

Exceptions only: a job that ran on time says so in its row and nowhere else. The
14-day grid stays available through `jura-growth one-pager --grid`.

Internal, for Ting Yu only, like the rest of the one-pager. Every string in a
snapshot is already masked; everything here is escaped before it reaches the
page. Colours and fonts are design-system tokens. Sizes are pixels because the
page is a fixed-size image: lists are capped and long lines clamped, so nothing
runs off it.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Callable, Mapping

from jura_growth import cards, health, images, mission, slots

WIDTH, HEIGHT = 1200, 1120
DECIDE_SHOWN, FIX_SHOWN = 4, 4


# --- what the picture says ------------------------------------------------------------------


def waiting(snapshot: mission.Snapshot) -> list[mission.Request]:
    """Requests still in time, soonest to lapse first."""
    found = [r for r in snapshot.approvals or () if r.reading == mission.Reading.WAITING]
    return sorted(found, key=lambda r: (r.decide_by, r.id))


def fixes(snapshot: mission.Snapshot) -> list[str]:
    """The health strip, each item on one short line."""
    return [item.splitlines()[0] for item in health.strip(snapshot, short=True)]


def verdict(snapshot: mission.Snapshot) -> str:
    to_decide, to_fix = len(waiting(snapshot)), len(fixes(snapshot))
    parts = ([f"{to_decide} to decide"] if to_decide else []) + ([f"{to_fix} to fix"] if to_fix else [])
    return (", ".join(parts) + ".") if parts else "Nothing needs you right now."


def by_when(at: datetime, now: datetime) -> str:
    """A decide-by, as short as it can be and still be read alone."""
    return f"today {at:%H:%M}" if at.date() == now.date() else f"{health.day_label(at)} {at:%H:%M}"


def short_reason(reason: str | None) -> str:
    """A skipped run's reason in a few words: paths cut to their last two parts, first sentence only."""
    if not reason:
        return ""
    trimmed = re.sub(r"(?:/[^/\s]+)+/([^/\s]+/[^/\s]+)", r"\1", reason)
    return trimmed.split(". ")[0].rstrip(".")


def _sentence(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def _plural(n: int, word: str, many: str | None = None) -> str:
    return f"{n} {word if n == 1 else many or word + 's'}"


# --- the five growth agents ---------------------------------------------------------------


def _scout(figures: Mapping) -> str:
    return f"{_plural(figures.get('leads_added', 0), 'new lead')} kept"


def _outreach(figures: Mapping) -> str:
    mode = figures.get("outreach_mode")
    return f"{_plural(figures.get('emails_queued', 0), 'email')} queued" + (f" ({mode})" if mode and mode != "live" else "")


def _social(figures: Mapping) -> str:
    return f"{_plural(figures.get('social_drafts_waiting', 0), 'draft')} waiting"


def _community(figures: Mapping) -> str:
    return f"{_plural(figures.get('community_posts_planned', 0), 'post')} planned"


def _apps(figures: Mapping) -> str:
    return str(figures.get("app_prd_today") or "No new PRD")


@dataclass(frozen=True)
class Agent:
    label: str
    job: str  # the job that drafts in the morning
    kinds: tuple[str, ...]  # the approval kinds it raises
    says: Callable[[Mapping], str]


AGENTS = (
    Agent("Scout", "scout-research", (), _scout),
    Agent("Outreach", "outreach-requests", ("outreach-email",), _outreach),
    Agent("Social", "social", ("social-post",), _social),
    Agent("Community", "community", ("group-rules", "group-join", "community-post"), _community),
    Agent("App factory", "app-factory", ("app-build", "app-release"), _apps),
)
STATUS_WORDS = {  # slot status: what the row's label says
    "failed": "Failed",
    "missed": "Missed",
    "running": "Still running",
    "ok": "Ran",
    "skipped": "Skipped",
    "due": "Due now",
    "upcoming": "Later",
    "not installed": "Not installed",
}


@dataclass(frozen=True)
class AgentRow:
    label: str
    status: str  # a slot status, or "none" with no slot today
    word: str
    detail: str
    to_approve: int


def agent_rows(snapshot: mission.Snapshot) -> list[AgentRow]:
    counts = Counter(r.kind for r in waiting(snapshot))
    figures = snapshot.morning.figures if snapshot.morning else {}
    return [_row(agent, snapshot.slots.get((agent.job, snapshot.now.date())), figures,
                 sum(counts[kind] for kind in agent.kinds)) for agent in AGENTS]


def _row(agent: Agent, statuses: list[slots.SlotStatus] | None, figures: Mapping, to_approve: int) -> AgentRow:
    if not statuses:
        return AgentRow(agent.label, "none", "Not today", "No run today", to_approve)
    status = slots.day_cell(statuses).status or "none"
    slot = next(s for s in statuses if s.status == status)
    if status == "ok":
        detail = agent.says(figures)
    elif status == "skipped":
        detail = short_reason(slot.reason)
    elif status in ("upcoming", "due"):
        detail = f"Due at {slot.at:%H:%M}"
    elif status == "running":
        detail = "Its drafts may land after this"
    else:
        detail = f"Its {slot.at:%H:%M} run"
    return AgentRow(agent.label, status, STATUS_WORDS[status], detail, to_approve)


# --- Yesterday, and later today -----------------------------------------------------------

LATER = (("publish", "Approved posts go out"), ("scout-send", "Approved emails send"), ("digest", "Digest"))


def later_today(snapshot: mission.Snapshot) -> list[str]:
    """What still runs today, from today's slots."""
    now, lines = snapshot.now, []
    for job, words in LATER:
        times = [s.at for s in snapshot.slots.get((job, now.date()), [])]
        if not times or times[-1] <= now:
            continue
        span = f"{times[0]:%H:%M}" if len(times) == 1 else f"{times[0]:%H:%M}–{times[-1]:%H:%M}"
        lines.append(f"{words} {span}")
    return lines


def yesterday_tiles(snapshot: mission.Snapshot) -> list[tuple[str, str]]:
    """(figure, label). A dash when the digest couldn't be read: never a guessed zero."""
    found = snapshot.yesterday
    if found is None:
        return [("–", label) for label in ("emails sent", "replies", "posts published", "Claude spend")]
    figures = found.figures
    return [
        (str(figures.get("emails_sent", 0)), "emails sent"),
        (str(figures.get("replies", 0)), "replies"),
        (str(figures.get("social_published", 0)), "posts published"),
        (f"US${found.spend:.2f}", "Claude spend"),
    ]


def yesterday_warning(snapshot: mission.Snapshot) -> str:
    figures = snapshot.yesterday.figures if snapshot.yesterday else {}
    named = (("unsubscribes", "unsubscribe"), ("bounces", "bounce"), ("complaints", "complaint"))
    return ", ".join(_plural(figures[key], word) for key, word in named if figures.get(key))


# --- the page -----------------------------------------------------------------------------

_CSS = """
html, body { margin: 0; width: 100%; height: 100%; overflow: hidden; background: var(--white); }
* { box-sizing: border-box; }
.page { width: 100%; height: 100%; padding: 44px 48px; display: flex; flex-direction: column; font-family: var(--font-body); color: var(--text-body); }
header { flex: none; padding-bottom: 28px; border-bottom: 4px solid var(--brand); }
.overline { font-family: var(--font-mono); font-size: 22px; color: var(--text-brand); }
h1 { margin: 8px 0 0; font-family: var(--font-display); font-weight: var(--weight-medium); font-size: 64px; line-height: 72px; color: var(--text-strong); }
.columns { flex: 1; min-height: 0; display: flex; gap: 48px; padding-top: 28px; }
.col { flex: 1 1 0; min-width: 0; min-height: 0; overflow: hidden; display: flex; flex-direction: column; gap: 28px; }
h2 { margin: 0 0 12px; font-family: var(--font-display); font-weight: var(--weight-medium); font-size: 34px; line-height: 42px; color: var(--text-strong); }
h2 .n { color: var(--text-muted); font-weight: var(--weight-regular); }
ul { list-style: none; margin: 0; padding: 0; }
li { padding: 10px 0; border-top: 1px solid var(--border-subtle); font-size: 28px; line-height: 36px; }
.clamp { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; overflow-wrap: anywhere; }
.one { -webkit-line-clamp: 1; }
.by { display: block; font-size: 24px; line-height: 30px; color: var(--text-muted); }
.more, .empty { font-size: 26px; line-height: 34px; color: var(--text-muted); padding-top: 10px; }
code { font-family: var(--font-mono); font-size: 25px; color: var(--text-strong); }
.row { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }
.name { font-weight: var(--weight-medium); color: var(--text-strong); white-space: nowrap; }
.word { flex: none; padding: 1px 12px; border-radius: var(--radius-xs); font-family: var(--font-mono); font-size: 23px; line-height: 32px; font-weight: var(--weight-medium); }
.detail { font-size: 25px; line-height: 32px; color: var(--text-muted); }
.ask { color: var(--text-brand); font-weight: var(--weight-medium); }
.s-failed { background: var(--danger-bg); color: var(--danger-fg); }
.s-missed { background: var(--warning-bg); color: var(--warning-fg); }
.s-running { background: var(--info-bg); color: var(--info-fg); }
.s-ok { background: var(--success-bg); color: var(--success-fg); }
.s-skipped, .s-not-installed { background: var(--warning-bg); color: var(--warning-fg); }
.s-due, .s-upcoming, .s-none { background: var(--neutral-100); color: var(--neutral-600); }
footer { flex: none; display: flex; gap: 48px; margin-top: 24px; padding-top: 24px; border-top: 1px solid var(--border-default); }
.tiles { flex: 1 1 0; min-width: 0; display: flex; justify-content: space-between; }
.figure { font-family: var(--font-display); font-weight: var(--weight-medium); font-size: 44px; line-height: 52px; color: var(--text-strong); }
.caption { font-size: 21px; line-height: 26px; color: var(--text-muted); }
.warn { margin-top: 6px; font-size: 23px; line-height: 28px; color: var(--warning-fg); }
.later { flex: 1 1 0; min-width: 0; font-size: 24px; line-height: 32px; }
.later div { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
h3 { margin: 0 0 8px; font-family: var(--font-display); font-weight: var(--weight-medium); font-size: 28px; line-height: 34px; color: var(--text-strong); }
"""


def _inline(text: str) -> str:
    """Escaped, with the strip's `code` spans drawn as code."""
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", escape(text))


def _more(hidden: int) -> str:
    return f'<p class="more">and {hidden} more</p>' if hidden > 0 else ""


def _decide(snapshot: mission.Snapshot) -> str:
    if snapshot.approvals is None:
        return f'<p class="empty">{escape(_unavailable(snapshot))}</p>'
    found = waiting(snapshot)
    if not found:
        return '<p class="empty">Nothing waiting for you.</p>'
    items = "".join(
        f'<li><span class="clamp one"><span class="name">{escape(_sentence(cards.label(r.kind)))}</span> {_inline(r.id)}</span>'
        f'<span class="clamp one detail">{_inline(_sentence(r.reason))}</span>'
        f'<span class="by">Decide by {escape(by_when(r.decide_by, snapshot.now))}</span></li>'
        for r in found[:DECIDE_SHOWN]
    )
    return f"<ul>{items}</ul>{_more(len(found) - DECIDE_SHOWN)}"


def _unavailable(snapshot: mission.Snapshot) -> str:
    problem = mission.db_problem(snapshot)
    return (problem or mission.NOT_MIGRATED).unavailable


def _fix(snapshot: mission.Snapshot) -> str:
    found = fixes(snapshot)
    if not found:
        return '<p class="empty">Nothing broken.</p>'
    items = "".join(f'<li><span class="clamp">{_inline(item)}</span></li>' for item in found[:FIX_SHOWN])
    return f"<ul>{items}</ul>{_more(len(found) - FIX_SHOWN)}"


def _agents(snapshot: mission.Snapshot) -> str:
    items = []
    for row in agent_rows(snapshot):
        css = row.status.replace(" ", "-")
        ask = f'<span class="ask"> · {row.to_approve} to approve</span>' if row.to_approve else ""
        items.append(
            f'<li><div class="row"><span class="name">{escape(row.label)}</span><span class="word s-{css}">{escape(row.word)}</span></div>'
            f'<div class="clamp one detail">{_inline(row.detail)}{ask}</div></li>'
        )
    return f"<ul>{''.join(items)}</ul>"


def _yesterday(snapshot: mission.Snapshot) -> str:
    tiles = "".join(f'<div><div class="figure">{escape(figure)}</div><div class="caption">{escape(label)}</div></div>'
                    for figure, label in yesterday_tiles(snapshot))
    warning = yesterday_warning(snapshot)
    note = f'<div class="warn">{escape(warning)}</div>' if warning else ""
    return f'<div class="tiles">{tiles}</div>{note}'


def _later(snapshot: mission.Snapshot) -> str:
    lines = later_today(snapshot) or ["Nothing else scheduled"]
    return "".join(f"<div>{escape(line)}</div>" for line in lines)


def html(snapshot: mission.Snapshot) -> str:
    now = snapshot.now
    decide_n = len(waiting(snapshot))
    fix_n = len(fixes(snapshot))
    styles = (images.design_system() / "styles.css").as_uri()
    return (
        '<!doctype html>\n<html lang="en-SG"><head><meta charset="utf-8"><title>Jura growth morning brief</title>'
        f'<meta name="viewport" content="width={WIDTH}, height={HEIGHT}">'
        f'<link rel="stylesheet" href="{escape(styles)}"><style>{_CSS}</style></head><body><main class="page">'
        f'<header><div class="overline">Jura growth · {escape(health.day_label(now))}, as of {now:%H:%M} SGT</div>'
        f"<h1>{escape(verdict(snapshot))}</h1></header>"
        '<div class="columns"><div class="col">'
        f'<section><h2>Decide in #approvals <span class="n">{decide_n}</span></h2>{_decide(snapshot)}</section>'
        f'<section><h2>Fix <span class="n">{fix_n}</span></h2>{_fix(snapshot)}</section>'
        '</div><div class="col">'
        f"<section><h2>This morning</h2>{_agents(snapshot)}</section>"
        "</div></div>"
        f'<footer><div style="flex:1 1 0;min-width:0"><h3>Yesterday</h3>{_yesterday(snapshot)}</div>'
        f'<div class="later"><h3>Later today</h3>{_later(snapshot)}</div></footer>'
        "</main></body></html>"
    )


def render(snapshot: mission.Snapshot, out: Path, *, chrome: images.Chrome, offline: bool = False) -> Path:
    """The picture as a PNG at `out`, through the core Chrome helper."""
    return images.screenshot(html(snapshot), out, WIDTH, HEIGHT, chrome=chrome, offline=offline)
