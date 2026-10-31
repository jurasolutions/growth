"""The morning picture: mission control at a glance (MB PRD 2026-10-31).

One image in #mission-control at 09:00 SGT, after the agents have drafted, that
reads at the size Discord shows it. Built from a `mission.Snapshot`, never from
the database, in the order Ting Yu acts on it:

- the verdict: how many things to decide, to fix, to post by hand and to read,
  which clears him only when every count could be read and is 0;
- Decide: approval requests still waiting, soonest to lapse first;
- Fix: the health strip, one short line each, with the action first;
- This morning: what each growth agent did and how many requests it raised;
- Yesterday: the figures the engine recorded, and what runs later today.

Exceptions only: a job that ran on time says so in its row and nowhere else. The
14-day grid stays available through `jura-growth one-pager --grid`.

The picture only states what the engine recorded. A figure it can't read is a
dash, slots it can't read are "Not available", and neither is ever a guessed
zero or "Not today".

Internal, for Ting Yu only, like the rest of the one-pager. Every string in a
snapshot is already masked; everything here is escaped before it reaches the
page, which holds no script. Colours and fonts are design-system tokens. Sizes
are pixels because the page becomes an image. Its height follows its content
(`render` measures it, then shoots), lists are capped and long lines clamped, and
a page over `MAX_HEIGHT` is refused rather than clipped: the long text goes instead.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from typing import Callable, Mapping

from jura_growth import cards, health, images, mission, slots

WIDTH, MAX_HEIGHT = 1200, 1600
DECIDE_SHOWN, FIX_SHOWN = 4, 4
DASH = "–"  # a figure that can't be read: never a guessed zero
NOT_AVAILABLE = "Not available"
DUE_GRACE = timedelta(minutes=5)  # a slot older than this with no trace didn't run


# --- what the picture says ------------------------------------------------------------------


def waiting(snapshot: mission.Snapshot) -> list[mission.Request]:
    """Requests still in time, soonest to lapse first."""
    found = [r for r in snapshot.approvals or () if r.reading == mission.Reading.WAITING]
    return sorted(found, key=lambda r: (r.decide_by, r.id))


def _overdue(snapshot: mission.Snapshot, slot: slots.SlotStatus) -> bool:
    """A slot whose time has passed with no trace. `slots.py` keeps it `due` until the next
    slot, which is right for a classifier and wrong for someone reading at 09:00. It also calls
    any slot before a job's first trace `not installed`, whatever launchd says, so a job that is
    installed and has never fired counts too, from its install on: slots before that aren't judged."""
    if snapshot.now - slot.at <= DUE_GRACE:
        return False
    if slot.status == "due":
        return True
    since = snapshot.installed_at.get(slot.job)
    return slot.status == "not installed" and snapshot.installs.get(slot.job) == health.INSTALLED and (since is None or slot.at >= since)


def _schedule_stale(snapshot: mission.Snapshot, job: str) -> bool:
    return snapshot.installs.get(job) in (health.OUT_OF_DATE, health.NOT_INSTALLED)


def _didnt_run(snapshot: mission.Snapshot) -> dict[str, str]:
    """Each growth agent whose slot passed with no trace, as far back as `health` looks for
    missed slots. Skipped for a job whose install state is off: its old-time runs land in the
    day before's slot until `schedule install`, and Fix already names it. Job: its Fix line."""
    now, lines = snapshot.now, {}
    since = health.previous_business_day_start(now)
    for agent in AGENTS:
        if _schedule_stale(snapshot, agent.job):
            continue
        passed = [s.at for (job, _), statuses in snapshot.slots.items() if job == agent.job
                  for s in statuses if s.at >= since and _overdue(snapshot, s)]
        if passed:
            latest = max(passed)
            when = "today" if latest.date() == now.date() else f"on {health.day_label(latest)}"
            lines[agent.job] = f"Check `{agent.job}`: no trace of its run {when}."
    return lines


def fixes(snapshot: mission.Snapshot) -> list[str]:
    """What needs fixing, each item with the action first. An item's first line is its own row on
    the page. Any more of it is for the message: a failed run's words in a quote, or a plug-in's detail.

    In the order that survives the cap of four: a pause, then the plug-ins' own lines, such as the
    ICP or a live-outreach blocker, then the rest of the strip in its order, and last a job that
    left no trace. A job with a "no trace" line needs no missed count as well."""
    silent = _didnt_run(snapshot)
    items = [item for item in health.strip(snapshot, short=True)
             if not any(item.startswith(f"Check `{job}`: it missed") for job in silent)]
    paused = (1 if snapshot.pause_file else 0) + len(snapshot.paused)
    plugins = [item for item in items[paused:] if item in snapshot.plugin_lines]
    rest = [item for item in items[paused:] if item not in snapshot.plugin_lines]
    return items[:paused] + plugins + rest + list(silent.values())


def _to_post_by_hand(snapshot: mission.Snapshot) -> int | None:
    """Today's drafts on platforms in `draft` mode, or None if the figure can't be read. A platform
    in `browser` mode goes through a card and publish, answered or not, so its draft is never his to
    post. Today's only, by decision: a daily post from an earlier day shouldn't go out."""
    return (snapshot.morning.figures if snapshot.morning else {}).get("social_drafts_by_hand")


def _replies_to_read(snapshot: mission.Snapshot) -> int | None:
    """Yesterday's replies, or None if the figure can't be read. A recorded reply always counts.
    Reply detection off with none recorded reads as 0: it is a standing setting, and it mustn't
    rule out the all-clear for good. The tile says a dash."""
    figures = snapshot.yesterday.figures if snapshot.yesterday else {}
    return figures.get("replies") or (0 if figures.get("reply_detection") is False else figures.get("replies"))


def _unread(day: mission.Yesterday | None, keys: tuple[str, ...]) -> bool:
    return day is None or any(key not in day.figures for key in keys)


def _some_figure_unread(snapshot: mission.Snapshot) -> bool:
    """A figure on the page reads as a dash, so the verdict can't say all is well without it."""
    yesterday = snapshot.yesterday
    return _unread(snapshot.morning, MORNING_FIGURES) or _unread(yesterday, YESTERDAY_FIGURES) or not (yesterday and yesterday.spend_recorded)


def verdict(snapshot: mission.Snapshot) -> str:
    by_hand, replies = _to_post_by_hand(snapshot), _replies_to_read(snapshot)
    parts = [
        *([f"{n} to decide"] if (n := len(waiting(snapshot))) else []),
        *([f"{n} to fix"] if (n := len(fixes(snapshot))) else []),
        *([f"{by_hand} to post by hand"] if by_hand else []),
        *([f"{health._plural(replies, 'reply', 'replies')} to read"] if replies else []),
    ]
    if parts:
        return ", ".join(parts) + "."
    if _some_figure_unread(snapshot):
        return "Nothing to decide or fix, but some figures couldn't be read."
    return "Nothing needs you right now."


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


def _counted(figures: Mapping, key: str, word: str, then: str) -> str:
    """"3 new leads kept", or a dash when the figure isn't there."""
    found = figures.get(key)
    return DASH if found is None else f"{health._plural(found, word)} {then}"


# --- the five growth agents ---------------------------------------------------------------


# The figures the page draws: without one of them, a row or a tile reads as a dash.
MORNING_FIGURES = ("leads_added", "emails_queued", "social_drafts_waiting", "social_drafts_by_hand", "community_posts_planned", "app_prd_today")
YESTERDAY_FIGURES = ("emails_sent", "replies", "social_published")


def _scout(figures: Mapping) -> str:
    return _counted(figures, "leads_added", "new lead", "kept")


def _outreach(figures: Mapping) -> str:
    mode = figures.get("outreach_mode")
    queued = _counted(figures, "emails_queued", "email", "queued")
    return queued + (f" ({mode})" if mode and mode != "live" and queued != DASH else "")


def _social(figures: Mapping) -> str:
    return _counted(figures, "social_drafts_waiting", "draft", "waiting")


def _community(figures: Mapping) -> str:
    return _counted(figures, "community_posts_planned", "post", "planned")


def _apps(figures: Mapping) -> str:
    return str(figures["app_prd_today"] or "No new PRD") if "app_prd_today" in figures else DASH


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
    "none": "Not today",
}
DIDNT_RUN, OUT_OF_DATE, UNAVAILABLE, NOT_JUDGED = "didnt run", "out of date", "unavailable", "not judged"  # rows no slot status covers


@dataclass(frozen=True)
class AgentRow:
    label: str
    status: str  # a slot status, "none" with no slot today, or one of the four above
    word: str
    detail: str
    to_approve: int


def agent_rows(snapshot: mission.Snapshot) -> list[AgentRow]:
    counts = Counter(r.kind for r in waiting(snapshot))
    figures = snapshot.morning.figures if snapshot.morning else {}
    return [_row(snapshot, agent, figures, sum(counts[kind] for kind in agent.kinds)) for agent in AGENTS]


def _row(snapshot: mission.Snapshot, agent: Agent, figures: Mapping, to_approve: int) -> AgentRow:
    def row(status: str, word: str, detail: str = "") -> AgentRow:
        return AgentRow(agent.label, status, word, detail, to_approve)

    if not snapshot.slots:
        return row(UNAVAILABLE, NOT_AVAILABLE)
    statuses = snapshot.slots.get((agent.job, snapshot.now.date()))
    if not statuses:
        return row("none", STATUS_WORDS["none"])
    status = slots.day_cell(statuses).status or "none"
    slot = next(s for s in statuses if s.status == status)
    if _overdue(snapshot, slot):
        return _overdue_row(snapshot, agent, slot, row)
    if status == "not installed" and snapshot.installs.get(agent.job) == health.INSTALLED:
        return _installed_row(snapshot, agent, slot, row)
    if status == "ok":
        detail = agent.says(figures)
    elif status == "skipped":
        detail = short_reason(slot.reason)
    elif status in ("upcoming", "due"):
        detail = f"Due at {slot.at:%H:%M}"
    elif status == "running":
        detail = "Its drafts may land after this"
    elif status == "not installed":
        detail = "No run on record yet"
    else:
        detail = f"Its {slot.at:%H:%M} run"
    return row(status, STATUS_WORDS[status], detail)


def _installed_row(snapshot: mission.Snapshot, agent: Agent, slot: slots.SlotStatus, row) -> AgentRow:
    """The classifier's "not installed" on a job launchd does have: a slot from before its install,
    which isn't judged, or a first slot still to come."""
    since = snapshot.installed_at.get(agent.job)
    if since is not None and slot.at < since:
        return row(NOT_JUDGED, "Not judged", f"Installed {by_when(since, snapshot.now)}")
    status = "upcoming" if slot.at > snapshot.now else "due"
    return row(status, STATUS_WORDS[status], f"Due at {slot.at:%H:%M}")


def _overdue_row(snapshot: mission.Snapshot, agent: Agent, slot: slots.SlotStatus, row) -> AgentRow:
    state = snapshot.installs.get(agent.job)
    if state == health.OUT_OF_DATE:
        return row(OUT_OF_DATE, "Out of date", "Run `jura-growth schedule install` again")
    if state == health.NOT_INSTALLED:
        return row("not installed", STATUS_WORDS["not installed"], "Run `jura-growth schedule install`")
    return row(DIDNT_RUN, "Didn't run", f"No trace of its {slot.at:%H:%M} run")


# --- Yesterday, and later today -----------------------------------------------------------

# Windows, not outcomes: the schedule can't say a post or an email will go out.
LATER = (("publish", "Posting window"), ("scout-send", "Send window"), ("digest", "Digest"))


def later_today(snapshot: mission.Snapshot) -> list[str]:
    """What still runs today, from today's slots."""
    if not snapshot.slots:
        return [NOT_AVAILABLE]
    now, lines = snapshot.now, []
    for job, words in LATER:
        times = [s.at for s in snapshot.slots.get((job, now.date()), [])]
        if not times or times[-1] <= now:
            continue
        span = f"{times[0]:%H:%M}" if len(times) == 1 else f"{times[0]:%H:%M}–{times[-1]:%H:%M}"
        lines.append(f"{words} {span}")
    return lines


TILE_CAPTIONS = (("emails sent", "email sent"), ("replies", "reply"), ("social posts", "social post"))
SPEND_CAPTION = "Claude spend"


def _tile(figures: Mapping, key: str) -> str:
    found = figures.get(key)
    return DASH if found is None else str(found)


def yesterday_tiles(snapshot: mission.Snapshot) -> list[tuple[str, str]]:
    """(figure, caption). A dash for anything that can't be read: never a guessed zero. With
    reply detection off, a day with no reply recorded can't say 0, and one with a reply still shows it."""
    found = snapshot.yesterday
    if found is None:
        return [(DASH, many) for many, _ in TILE_CAPTIONS] + [(DASH, SPEND_CAPTION)]
    figures = found.figures
    replies = DASH if figures.get("reply_detection") is False and not figures.get("replies") else _tile(figures, "replies")
    values = (_tile(figures, "emails_sent"), replies, _tile(figures, "social_published"))
    tiles = [(value, one if value == "1" else many) for value, (many, one) in zip(values, TILE_CAPTIONS)]
    return tiles + [(f"US${found.spend:,.2f}" if found.spend_recorded else DASH, SPEND_CAPTION)]


def yesterday_warning(snapshot: mission.Snapshot) -> str:
    if snapshot.yesterday is None:
        return ""
    figures = snapshot.yesterday.figures
    named = (("unsubscribes", "unsubscribe"), ("bounces", "bounce"), ("complaints", "complaint"))
    parts = [health._plural(figures[key], word) for key, word in named if figures.get(key)]
    lapsed = sum(1 for r in snapshot.approvals or () if r.reading == mission.Reading.LAPSED)
    return ", ".join(parts + ([f"{lapsed} lapsed unanswered"] if lapsed else []))


# --- the page -----------------------------------------------------------------------------

_CSS = """
html, body { margin: 0; background: var(--white); }
* { box-sizing: border-box; }
.page { width: 100%; padding: 44px 48px; display: flex; flex-direction: column; font-family: var(--font-body); color: var(--text-body); }
header { padding-bottom: 28px; border-bottom: 4px solid var(--brand); }
h1 { margin: 0; font-family: var(--font-display); font-weight: var(--weight-medium); font-size: 60px; line-height: 76px; text-wrap: balance; color: var(--text-strong); }
.overline { margin-top: 8px; font-family: var(--font-mono); font-size: 22px; line-height: 30px; color: var(--text-brand); }
.columns { display: flex; gap: 48px; padding-top: 28px; }
.columns > section { flex: 1 1 0; min-width: 0; }
.morning { padding-top: 28px; }
h2 { margin: 0 0 12px; font-family: var(--font-display); font-weight: var(--weight-medium); font-size: 34px; line-height: 42px; color: var(--text-strong); }
h2 .n { color: var(--text-muted); font-weight: var(--weight-regular); }
ul { list-style: none; margin: 0; padding: 0; }
li { padding: 10px 0; border-top: 1px solid var(--border-subtle); font-size: 28px; line-height: 36px; }
.clamp { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 3; overflow: hidden; overflow-wrap: anywhere; }
.one { -webkit-line-clamp: 1; }
.by { display: block; font-size: 24px; line-height: 30px; color: var(--text-muted); }
.more, .empty { margin: 0; font-size: 26px; line-height: 34px; color: var(--text-muted); padding-top: 10px; }
code { font-family: var(--font-mono); font-size: 25px; line-height: 1; color: var(--text-strong); }
.row { display: flex; align-items: baseline; gap: 16px; }
.name { font-weight: var(--weight-medium); color: var(--text-strong); white-space: nowrap; }
.row .name { flex: none; width: 170px; }
.word { flex: none; width: 214px; text-align: center; padding: 1px 12px; border-radius: var(--radius-xs); font-family: var(--font-mono); font-size: 23px; line-height: 32px; font-weight: var(--weight-medium); }
.detail { font-size: 25px; line-height: 32px; color: var(--text-muted); }
.row .detail { flex: 1 1 0; min-width: 0; }
.ask { flex: none; color: var(--text-brand); font-weight: var(--weight-medium); font-size: 25px; line-height: 32px; }
.s-failed { background: var(--danger-bg); color: var(--danger-fg); }
.s-missed, .s-didnt-run { background: var(--warning-bg); color: var(--warning-fg); }
.s-running { background: var(--info-bg); color: var(--info-fg); }
.s-ok { background: var(--success-bg); color: var(--success-fg); }
.s-skipped, .s-not-installed, .s-out-of-date { background: var(--warning-bg); color: var(--warning-fg); }
.s-due, .s-upcoming, .s-none, .s-unavailable, .s-not-judged { background: var(--neutral-100); color: var(--neutral-600); }
footer { display: flex; gap: 48px; margin-top: 24px; padding-top: 24px; border-top: 1px solid var(--border-default); }
.yesterday { flex: 1 1 0; min-width: 0; }
.later { flex: none; width: 400px; font-size: 24px; line-height: 32px; }
.tiles { display: flex; flex-wrap: wrap; gap: 8px 20px; }
.figure { font-family: var(--font-display); font-weight: var(--weight-medium); font-size: 40px; line-height: 50px; color: var(--text-strong); }
.caption { font-size: 21px; line-height: 26px; color: var(--text-muted); }
.warn { margin-top: 6px; font-size: 23px; line-height: 28px; color: var(--warning-fg); }
h3 { margin: 0 0 8px; font-family: var(--font-display); font-weight: var(--weight-medium); font-size: 28px; line-height: 34px; color: var(--text-strong); }
"""


def _inline(text: str) -> str:
    """Escaped, with the strip's `code` spans drawn as code."""
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", escape(text))


def _more(hidden: int) -> str:
    return f'<p class="more">and {hidden} more</p>' if hidden > 0 else ""


def _decide(snapshot: mission.Snapshot) -> str:
    if snapshot.approvals is None:
        return f'<p class="empty">{escape(mission.unavailable(snapshot))}</p>'
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


def _fix(found: list[str]) -> str:
    if not found:
        return '<p class="empty">Nothing broken.</p>'
    items = "".join(f'<li><span class="clamp">{_fix_row(item)}</span></li>' for item in found[:FIX_SHOWN])
    return f"<ul>{items}</ul>{_more(len(found) - FIX_SHOWN)}"


def _fix_row(item: str) -> str:
    """An item's first line, then a run's own words apart from it. Those are the model's, so
    they never draw as a command: a code span comes only from the engine's wording. The
    backslashes `untrusted_line` adds are for Discord."""
    first, *rest = item.splitlines()
    quote = next((line[2:] for line in rest if line.startswith("> ")), "")
    if not quote:
        return _inline(first)
    plain = re.sub(r"\\(.)", r"\1", quote)
    return _inline(first) + " Its own words: " + escape('"' + plain + '"')


def _agents(snapshot: mission.Snapshot) -> str:
    items = []
    for row in agent_rows(snapshot):
        css = row.status.replace(" ", "-")
        ask = f'<span class="ask">{row.to_approve} to approve</span>' if row.to_approve else ""
        items.append(
            f'<li><div class="row"><span class="name">{escape(row.label)}</span><span class="word s-{css}">{escape(row.word)}</span>'
            f'<span class="clamp one detail">{_inline(row.detail)}</span>{ask}</div></li>'
        )
    return f"<ul>{''.join(items)}</ul>"


def _yesterday(snapshot: mission.Snapshot) -> str:
    tiles = "".join(f'<div><div class="figure">{escape(figure)}</div><div class="caption">{escape(caption)}</div></div>'
                    for figure, caption in yesterday_tiles(snapshot))
    warning = yesterday_warning(snapshot)
    note = f'<div class="warn">{escape(warning)}</div>' if warning else ""
    return f'<div class="tiles">{tiles}</div>{note}'


def _later(snapshot: mission.Snapshot) -> str:
    lines = later_today(snapshot) or ["Nothing else scheduled"]
    return "".join(f'<div class="clamp one">{escape(line)}</div>' for line in lines)


def html(snapshot: mission.Snapshot) -> str:
    """The page. Measuring it is `render`'s job, on a private copy: this holds no script."""
    now = snapshot.now
    found_fixes = fixes(snapshot)
    styles = (images.design_system() / "styles.css").as_uri()
    return (
        '<!doctype html>\n<html lang="en-SG"><head><meta charset="utf-8"><title>Jura growth morning picture</title>'
        f'<meta name="viewport" content="width={WIDTH}">'
        f'<link rel="stylesheet" href="{escape(styles)}"><style>{_CSS}</style></head><body><main class="page">'
        f"<header><h1>{escape(verdict(snapshot))}</h1>"
        f'<div class="overline">Jura growth · {escape(health.day_label(now))}, as of {now:%H:%M} SGT</div></header>'
        '<div class="columns">'
        f'<section class="decide"><h2>Decide in #approvals <span class="n">{DASH if snapshot.approvals is None else len(waiting(snapshot))}</span></h2>{_decide(snapshot)}</section>'
        f'<section class="fix"><h2>Fix <span class="n">{len(found_fixes)}</span></h2>{_fix(found_fixes)}</section>'
        "</div>"
        f'<section class="morning"><h2>This morning</h2>{_agents(snapshot)}</section>'
        f'<footer><div class="yesterday"><h3>Yesterday</h3>{_yesterday(snapshot)}</div>'
        f'<div class="later"><h3>Later today</h3>{_later(snapshot)}</div></footer>'
        "</main></body></html>"
    )


def render(snapshot: mission.Snapshot, out: Path, *, chrome: images.Chrome, offline: bool = False) -> Path:
    """The picture as a PNG at `out`, exactly as tall as its content. A page over `MAX_HEIGHT`
    raises `RenderError`, so it is never clipped: the caller sends the long text instead."""
    page = html(snapshot)
    height = images.measure_height(page, WIDTH, chrome=chrome, offline=offline)
    if height > MAX_HEIGHT:
        raise images.RenderError(f"the picture would be {height} px tall, over the {MAX_HEIGHT} px maximum")
    return images.screenshot(page, out, WIDTH, height, chrome=chrome, offline=offline)
