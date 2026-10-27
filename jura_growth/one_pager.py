"""The one-pager's text (MC SC1, §5.4).

Built from a `mission.Snapshot`, never from the database, in this order: the
header, Needs you (the health strip), Approvals waiting, Today, Yesterday and
Ask me. `post()` sends `text()` to #mission-control through `discord.post()`,
which masks it and splits it only past 2,000 characters, with the 14-day grid
as a PNG on the last piece (`grid_html`, drawn by the core Chrome helper in
`images.py`). The 08:00 `one-pager` job and `/growth one-pager` both run
`jura-growth one-pager`; `--no-post` prints `messages()`, the same text masked
and split the same way.

The one-pager is for Ting Yu only and shows only figures the engine recorded.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import timedelta
from html import escape
from pathlib import Path

from jura_growth import discord, health, images, log, mission, paths, privacy, slots, timeutil

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
    # A section is missing with nothing else wrong only when its table is.
    problem = mission.db_problem(snapshot)
    return (problem or mission.NOT_MIGRATED).unavailable


def _approvals(snapshot: mission.Snapshot) -> list[str]:
    if snapshot.approvals is None:
        return [_unavailable(snapshot)]
    waiting = [r for r in snapshot.approvals if r.reading == mission.Reading.WAITING]
    if not waiting:
        return ["Nothing waiting"]
    following = snapshot.next_one_pager or snapshot.now + timedelta(days=1)
    counts = Counter(r.kind for r in waiting)
    lines = [", ".join(f"{kind} {counts[kind]}" for kind in sorted(counts))]
    oldest = min(waiting, key=lambda r: (r.requested_at, r.id))
    lines.append(
        f"Oldest: {oldest.id} ({oldest.kind}), waiting since {timeutil.when(oldest.requested_at)}, "
        f"decide by {timeutil.when(oldest.decide_by)}"
    )
    lapsing = sorted((r for r in waiting if r.decide_by < following), key=lambda r: (r.decide_by, r.id))
    if lapsing:
        lines.append("Lapsing before the next one-pager: " + ", ".join(f"{r.id} ({timeutil.when(r.decide_by)})" for r in lapsing))
    # Decisions are made in Discord only (Ting Yu, 2026-10-26): point there.
    lines.append(f"Decide in #approvals: {len(waiting)} waiting for you.")
    return lines


def _today(snapshot: mission.Snapshot) -> list[str]:
    if not snapshot.slots:
        return [_unavailable(snapshot)]
    today = snapshot.now.date()
    lines = []
    for (job, day), statuses in snapshot.slots.items():
        if day != today:
            continue
        if not statuses:
            lines.append(f"`{job}` no slot today")
        elif len(statuses) > SLOTS_LISTED:
            cell = slots.day_cell(statuses)
            lines.append(f"`{job}` " + ", ".join(f"{n} {status}" for status, n in cell.counts.items()))
        else:
            lines.append(f"`{job}` " + ", ".join(_slot(slot) for slot in statuses))
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


# --- the 14-day grid (MC §5.4 item 7, §4.1) -----------------------------------------------
#
# One cell per job per day: the day's worst slot status (`slots.day_cell`), so
# scout-send's and publish's many slots collapse to one cell, with how many
# slots had that status when the job has more than one that day. Every status
# is a word as well as a colour, and the legend says what each word means. The
# page links `design-system/styles.css`; every colour and font below is one of
# its tokens. Sizes are pixels because the page is a fixed-size image.

GRID_LABELS = {  # status: (the word in the cell, what the legend says it means)
    "failed": ("Fail", "failed"),
    "missed": ("Miss", "missed"),
    "running": ("Run", "still running"),
    "ok": ("OK", "ran"),
    "skipped": ("Skip", "skipped"),
    "due": ("Due", "due now"),
    "upcoming": ("Next", "later today"),
    "not installed": ("Off", "not installed"),
}
GRID_NO_SLOT = "·"
GRID_WIDTH = 1200
_PAD, _TITLE, _HEAD_ROW, _ROW, _LEGEND, _NOTE = 32, 76, 44, 34, 72, 40

_GRID_CSS = """
html, body { margin: 0; width: 100%; height: 100%; overflow: hidden; background: var(--white); }
.page { box-sizing: border-box; width: 100%; height: 100%; padding: var(--space-6); display: flex; flex-direction: column; }
.overline { font-family: var(--font-mono); font-size: var(--text-overline); letter-spacing: var(--tracking-overline);
  text-transform: uppercase; color: var(--text-brand); height: 20px; }
h1 { font-family: var(--font-display); font-size: 26px; line-height: 40px; height: 56px; color: var(--text-strong); }
.note { font-family: var(--font-body); font-size: 16px; line-height: 40px; color: var(--text-muted); }
table { width: 100%; table-layout: fixed; border-collapse: separate; border-spacing: 3px; margin: 0 -3px; }
th { font-family: var(--font-mono); font-weight: var(--weight-regular); color: var(--text-muted); font-size: var(--text-overline); }
thead th { height: 38px; line-height: 15px; text-align: center; }
thead th.job, tbody th { width: 168px; text-align: left; }
tbody th { font-size: var(--text-caption); color: var(--text-strong); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
thead th.today { color: var(--text-brand); font-weight: var(--weight-medium); }
td.cell { height: 28px; padding: 0; text-align: center; border-radius: var(--radius-xs); font-family: var(--font-mono);
  font-size: var(--text-caption); font-weight: var(--weight-medium); white-space: nowrap; border: 1px solid transparent; }
.count { font-weight: var(--weight-regular); margin-left: 4px; }
.legend { margin-top: auto; height: 48px; display: flex; flex-wrap: wrap; align-content: flex-end; gap: 8px 20px;
  font-family: var(--font-body); font-size: var(--text-caption); color: var(--text-body); }
.key { display: inline-block; min-width: 40px; padding: 2px 6px; margin-right: 6px; text-align: center;
  border-radius: var(--radius-xs); font-family: var(--font-mono); font-size: var(--text-overline); font-weight: var(--weight-medium);
  border: 1px solid transparent; }
.s-failed { background: var(--danger-bg); color: var(--danger-fg); }
.s-missed { background: var(--warning-bg); color: var(--warning-fg); }
.s-running { background: var(--info-bg); color: var(--info-fg); }
.s-ok { background: var(--success-bg); color: var(--success-fg); }
.s-skipped { background: var(--neutral-100); color: var(--neutral-600); }
td.s-due, span.s-due { background: var(--white); color: var(--info-fg); border-color: var(--info-fg); }
td.s-upcoming, span.s-upcoming { background: var(--white); color: var(--text-muted); border-color: var(--border-subtle); }
.s-not-installed { background: var(--neutral-50); color: var(--text-faint); }
.s-none { background: var(--white); color: var(--text-faint); }
"""


def grid_size(snapshot: mission.Snapshot) -> tuple[int, int]:
    rows = len({job for job, _ in snapshot.slots})
    height = 2 * _PAD + _TITLE + _LEGEND + (_HEAD_ROW + _ROW * rows if rows else _NOTE)
    return GRID_WIDTH, height


def grid_html(snapshot: mission.Snapshot) -> str:
    """The grid page, checked before it is drawn (X14)."""
    now = snapshot.now
    jobs = list(dict.fromkeys(job for job, _ in snapshot.slots))
    title = f"{len(snapshot.days)} days to {health.day_label(now)}, as of {now:%H:%M} SGT"
    head = "".join(
        f'<th class="day{" today" if day == now.date() else ""}">{day:%a}<br>{day.day}</th>' for day in snapshot.days
    )
    rows = []
    for job in jobs:
        tds = "".join(_grid_cell(job, day, snapshot.slots.get((job, day), [])) for day in snapshot.days)
        rows.append(f"<tr><th>{escape(job)}</th>{tds}</tr>")
    body = (
        f'<table><thead><tr><th class="job">Job</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table>'
        if jobs
        else f'<p class="note">{escape(_unavailable(snapshot))}</p>'
    )
    keys = [(status.replace(" ", "-"), *GRID_LABELS[status]) for status in slots.WORST_FIRST]
    keys.append(("none", GRID_NO_SLOT, "no slot that day"))
    legend = "".join(
        f'<span class="item"><span class="key s-{css}">{escape(label)}</span>{escape(meaning)}</span>' for css, label, meaning in keys
    )
    width, height = grid_size(snapshot)
    styles = (images.design_system() / "styles.css").as_uri()
    return (
        '<!doctype html>\n<html lang="en-SG"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width={width}, height={height}">'
        f'<link rel="stylesheet" href="{escape(styles)}"><style>{_GRID_CSS}</style></head>'
        f'<body><main class="page"><div class="overline">Jura growth · mission control</div><h1>{escape(title)}</h1>'
        f'{body}<footer class="legend">{legend}</footer></main></body></html>'
    )


def _grid_cell(job: str, day, statuses: list[slots.SlotStatus]) -> str:
    cell = slots.day_cell(statuses)
    if cell.status is None:
        css, status, inner = "none", "none", GRID_NO_SLOT
    else:
        css, status = cell.status.replace(" ", "-"), cell.status
        inner = escape(GRID_LABELS[status][0])
        if len(statuses) > 1:
            inner += f'<span class="count">{cell.counts[status]}</span>'
    return f'<td class="cell s-{css}" data-job="{escape(job)}" data-day="{day.isoformat()}" data-status="{escape(status)}">{inner}</td>'


def render_grid(snapshot: mission.Snapshot, out: Path, *, chrome: images.Chrome, offline: bool = False) -> Path:
    """The grid as a PNG at `out`, through the core Chrome helper."""
    width, height = grid_size(snapshot)
    return images.screenshot(grid_html(snapshot), out, width, height, chrome=chrome, offline=offline)


# --- posting to #mission-control (MC SC1) ---------------------------------------------------

CHANNEL = "mission-control"
USERNAME = "Jura growth · mission control"
# Off in production, so the design system's web fonts load. The tests switch it
# on: there Chrome's host resolver is off and the page can't reach the network.
OFFLINE = False


def grid_png(snapshot: mission.Snapshot) -> tuple[Path | None, str | None]:
    """The grid drawn to `data/growth/one-pager/grid-<day>.png` (one file a
    day, replaced by a later one-pager that day), or None and why not."""
    out = paths.one_pager_dir() / f"grid-{snapshot.now:%Y-%m-%d}.png"
    try:
        return render_grid(snapshot, out, chrome=images.Chrome(images.DEFAULT_CHROME), offline=OFFLINE), None
    except images.RenderError as error:
        return None, str(error)
    except Exception as error:  # noqa: BLE001 - the text goes out without the picture
        return None, f"{type(error).__name__}: {error}"


def post(conn: sqlite3.Connection, snapshot: mission.Snapshot) -> discord.PostResult:
    """The one-pager to #mission-control: the text, split only past 2,000
    characters, and the grid on the last piece (`discord.post` attaches files
    there). Never deduplicated: asked for twice, it posts twice (MC §5.10).
    When the grid can't be drawn, the text still goes and says why."""
    content = text(snapshot)
    png, problem = grid_png(snapshot)
    if problem:
        log.event(conn, "one_pager.grid_failed", {"error": problem}, level="warning")
        content += f"\n\n(The 14-day grid couldn't be drawn: {problem})"
    return discord.post(conn, CHANNEL, content, files=[png] if png else [], username=USERNAME, dedupe=False,
                        suppress_embeds=True)
