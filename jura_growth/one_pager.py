"""The one-pager's text (MC SC1, §5.4).

Built from a `mission.Snapshot`, never from the database, in this order: the
header, Needs you (the health strip), each plug-in's own section, Approvals
waiting, Today, Yesterday and Ask me. `post()` sends `text()` to #mission-control
through `discord.post()`, which masks it and splits it only past 2,000 characters.

Amended 2026-10-31: what goes to #mission-control is the morning picture
(`picture.py`) with a short message (`summary()`), which also carries a plug-in's
section when it has something to tell, as Replies waiting does for what is waiting.
`text()` is the long form: `--no-post` prints it, and it goes out instead when the
picture can't be drawn.
The 14-day grid (`grid_html`) is no longer posted, because it can't be read at
the size Discord shows it; `jura-growth one-pager --grid` draws it to a file.
The 09:00 `one-pager` job and `/growth one-pager` both run `jura-growth one-pager`.

The one-pager is for Ting Yu only and shows only figures the engine recorded.
"""

from __future__ import annotations

import dataclasses
import sqlite3
from collections import Counter
from datetime import timedelta
from html import escape
from pathlib import Path

from jura_growth import cards, discord, health, images, log, mission, paths, picture, privacy, run_update, slots, timeutil

ASK_ME = ("`/growth status`", "`/growth approvals`", "`/growth inbox list`", "`/growth one-pager`", "`/growth pause <agent|all>`",
          "`/growth resume <agent|all>`")
# Today shows these jobs as counts per status, whatever their slot count,
# and lists every other job slot by slot (MC §5.4.4; code review 08 S-4).
COUNTED_JOBS = frozenset({"scout-send", "publish", "inbox-check", "inbox-send", "inbox-watch", "inbox-reply"})
# A Fix line in the message: long enough for any real wording, and short enough that
# four of them and the rest fit one message, which is what carries the picture.
SUMMARY_FIX_LIMIT = 360


def text(snapshot: mission.Snapshot) -> str:
    now = snapshot.now
    parts = [f"**{health.day_label(now)}, as of {now:%H:%M} SGT**"]
    parts += _section("Needs you", _needs_you(snapshot))
    for name, lines in snapshot.plugin_sections:
        parts += _section(name, list(lines))
    parts += _section("Approvals waiting", _approvals(snapshot))
    parts += _section("Today", _today(snapshot))
    parts += _section("Yesterday", _yesterday(snapshot))
    parts += _section("Ask me", [" · ".join(ASK_ME)])
    return "\n".join(parts)


def summary(snapshot: mission.Snapshot) -> str:
    """The message that carries the picture: enough to act on from a notification, then any plug-in's
    section with something to tell. Past 2,000 characters `discord.post` splits it at a line, with the
    picture on the last piece."""
    now = snapshot.now
    lines = [f"**{health.day_label(now)}, as of {now:%H:%M} SGT**", picture.verdict(snapshot)]
    found = picture.waiting(snapshot)
    if found:
        counts = Counter(cards.label(r.kind) for r in found)
        soonest = found[0]
        lines.append(
            "Decide in #approvals: " + ", ".join(f"{kind} {counts[kind]}" for kind in sorted(counts))
            + f". Soonest: {soonest.id}, by {picture.by_when(soonest.decide_by, now)}."
        )
    fixes = picture.fixes(_markdown_safe(snapshot))
    lines += [f"- {discord.shortened(item, SUMMARY_FIX_LIMIT)}" for item in fixes[:picture.FIX_SHOWN]]
    if len(fixes) > picture.FIX_SHOWN:
        lines.append(f"- and {len(fixes) - picture.FIX_SHOWN} more: run `jura-growth one-pager --no-post` on the Mac")
    lines.append(" · ".join(ASK_ME[:2]))
    for name, found_lines in snapshot.plugin_sections:
        if found_lines and name not in snapshot.quiet_sections:
            lines += _section(name, list(found_lines))
    return "\n".join(lines)


def _markdown_safe(snapshot: mission.Snapshot) -> mission.Snapshot:
    """The snapshot with the text others wrote made safe for Discord markdown: `[Approve
    here](https://…)` would otherwise be a live link, which suppressing embeds doesn't stop.
    Only for the message: the page has no links, and its text is escaped."""
    safe = run_update.untrusted_line
    return dataclasses.replace(
        snapshot,
        pause_file=safe(snapshot.pause_file) if snapshot.pause_file else None,
        paused=tuple((agent, safe(reason)) for agent, reason in snapshot.paused),
        plugin_lines=tuple(safe(line) for line in snapshot.plugin_lines),
    )


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


def _approvals(snapshot: mission.Snapshot) -> list[str]:
    if snapshot.approvals is None:
        return [mission.unavailable(snapshot)]
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
        return [mission.unavailable(snapshot)]
    today = snapshot.now.date()
    lines = []
    for (job, day), statuses in snapshot.slots.items():
        if day != today:
            continue
        if not statuses:
            lines.append(f"`{job}` no slot today")
        elif job in COUNTED_JOBS:
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
        return [mission.unavailable(snapshot)]
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
        else f'<p class="note">{escape(mission.unavailable(snapshot))}</p>'
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
    day, replaced by a later one that day), or None and why not."""
    out = paths.one_pager_dir() / f"grid-{snapshot.now:%Y-%m-%d}.png"
    return _drawn(lambda: render_grid(snapshot, out, chrome=images.Chrome(images.DEFAULT_CHROME), offline=OFFLINE))


def picture_png(snapshot: mission.Snapshot) -> tuple[Path | None, str | None]:
    """The morning picture drawn to `data/growth/one-pager/picture-<day>.png`, with
    its page beside it as `.html` to open on the Mac; or None and why not."""
    folder = paths.one_pager_dir()
    day = f"{snapshot.now:%Y-%m-%d}"

    def draw() -> Path:
        png = picture.render(snapshot, folder / f"picture-{day}.png", chrome=images.Chrome(images.DEFAULT_CHROME), offline=OFFLINE)
        paths.writable(folder / f"picture-{day}.html").write_text(picture.html(snapshot), encoding="utf-8")
        return png

    return _drawn(draw)


def _drawn(draw) -> tuple[Path | None, str | None]:
    try:
        return draw(), None
    except images.RenderError as error:
        return None, str(error)
    except Exception as error:  # noqa: BLE001 - the text goes out without the picture
        return None, f"{type(error).__name__}: {error}"


def post(conn: sqlite3.Connection | None, snapshot: mission.Snapshot) -> discord.PostResult:
    """The morning picture to #mission-control with its short message. Never
    deduplicated: asked for twice, it posts twice (MC §5.10). When the picture
    can't be drawn, the long text goes instead and says why."""
    png, problem = picture_png(snapshot)
    if png:
        content = summary(snapshot)
    else:
        log.event(conn, "one_pager.picture_failed", {"error": problem}, level="warning")
        content = f"{text(snapshot)}\n\n(The picture couldn't be drawn: {problem})"
    return discord.post(conn, CHANNEL, content, files=[png] if png else [], username=USERNAME, dedupe=False,
                        suppress_embeds=True)
