"""Ting Yu's own toolbox ideas (`jura-growth apps idea`, `apps hold-idea`).

`apps idea <text>` adds one backlog row with `source: ting-yu`, the text verbatim in `does`, a
name from the text and the date and actor. It writes nothing else: the factory still writes the
PRD, and the `app-build` and `app-release` decisions still gate the build. It is a control
command from Discord (`remote.ALLOWLIST`) and never a scheduled run's (`headless.NEVER`).

The factory picks these ideas before any other candidate, oldest first (`queue`, shown as
`ting_yu_ideas` in `apps context --json`), and `submit-prd` holds it to that (`binding`): while
the oldest waits, a PRD is filed against it or not at all, unless it was held today. One that
fails a check is held (`hold`): the reason goes in the row's notes and in that day's digest, and
the idea becomes an ordinary candidate.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from jura_growth import timeutil
from jura_growth.agents.apps import backlog, catalog
from jura_growth.agents.apps import prd as prd_mod

SOURCE = "ting-yu"
MAX_LENGTH = 500
NAME_WORDS = 5  # the factory's name rule allows a few plain words; the factory may rename it
NAME_MAX = 60
SLUG_MAX = 60  # `validate_factory`'s slug limit
REASON_MAX = 300
NAME_MARK = ": "  # a colon and a space, so a web address or a time (06:30) doesn't name it
_EDGE = " \t\r\n.,;:!?\"'"
_LATIN = re.compile(r"[A-Za-z]")
BUSY = "refused: the backlog is busy (another command is writing it); try again in a minute"
NO_LATIN = ("refused: a name needs Latin letters for its web address. "
            "Put one before a colon, like `Leave form maker: …`")


class Refused(Exception):
    """Nothing is written. `code` is the exit code: 2 for the text itself, 1 for the backlog's
    state (a clash, an idea that can't be held)."""

    def __init__(self, text: str, code: int):
        super().__init__(text)
        self.text, self.code = text, code


@dataclass
class Added:
    row: dict
    ahead: int  # Ting Yu's open ideas older than this one, which the factory picks first


# --- the name -------------------------------------------------------------------------------------


def name_for(text: str) -> str:
    """The part before the first ": " when there is one, else the first few words, in sentence
    case and at most `NAME_MAX` characters, cut at a word. The factory may rename it to meet its
    name rules (`submit-prd --idea`)."""
    before, mark, after = text.partition(NAME_MARK)
    name = before.strip(_EDGE) if mark else ""
    if not name:
        name = " ".join((after if mark else text).split()[:NAME_WORDS])
    name = " ".join(name.strip(_EDGE).split())
    if len(name) > NAME_MAX:
        head = name[: NAME_MAX + 1]
        name = (head.rsplit(" ", 1)[0] if " " in head else name[:NAME_MAX]).strip(_EDGE) or name[:NAME_MAX]
    return name[:1].upper() + name[1:]


def slug_for(name: str) -> str:
    slug = prd_mod.slugify(name)
    if len(slug) > SLUG_MAX:
        slug = slug[:SLUG_MAX].rsplit("-", 1)[0]
    return slug


# --- adding one ----------------------------------------------------------------------------------


def clash(conn: sqlite3.Connection, rows: list[dict], *, name: str, slug: str) -> str | None:
    """What the idea would duplicate, by the catalog's slug and name checks: any backlog row
    (`backlog.find`), then anything live, pending or built (`catalog.taken`)."""
    row = backlog.find(rows, slug=slug, name=name)
    if row is not None:
        status = row.get("status") or "idea"
        return f"{row['name']} (backlog: {status}{', ' + row['app_id'] if row.get('app_id') else ''})"
    slugs, names = catalog.taken(conn)
    if slug in slugs:
        return f"the slug {slug} ({slugs[slug]})"
    wanted = prd_mod.normalise_name(name)
    if wanted in names:
        return f"the name {name} ({names[wanted]})"
    return None


def add(conn: sqlite3.Connection, text: str, *, actor: str) -> Added:
    text = text.strip()
    if not text:
        raise Refused("refused: say the idea: `apps idea <text>`", 2)
    if len(text) > MAX_LENGTH:
        raise Refused(f"refused: the idea is {len(text)} characters; keep it to {MAX_LENGTH}", 2)
    name = name_for(text)
    slug = slug_for(name)
    if not slug or not _LATIN.search(name):  # "2026", "<@123>" and "123 456" too
        raise Refused(NO_LATIN, 2)
    with backlog.locked():  # the check and the write see the same file
        rows = backlog.load()
        clashes = clash(conn, rows, name=name, slug=slug)
        if clashes:
            raise Refused(f'not added: "{name}" ({slug}) clashes with {clashes}. '
                          "Send it with a different name before a colon.", 1)
        today = timeutil.today_str()
        ahead = len(queue(rows))
        row = {"name": name, "slug": slug, "does": text, "status": "idea", "source": SOURCE, "added": today,
               "actor": actor, "notes": f"Sent by Ting Yu with `apps idea` on {today}."}
        rows.append(row)
        backlog.save(rows)
    return Added(row, ahead)


def reply(added: Added) -> str:
    row = added.row
    lines = [
        "Added to the app backlog:",
        f"  name    {row['name']}",
        f"  slug    {row['slug']}",
        f"  status  {row['status']} (source: {row['source']}, added {row['added']} by {row['actor']})",
        f"  does    {row['does']}",
    ]
    if added.ahead:
        count = f"{added.ahead} older idea{'s' if added.ahead != 1 else ''} of yours come{'s' if added.ahead == 1 else ''}"
        lines.append(f"{count} first; the app factory writes at most one PRD a day at 06:30 SGT, oldest first.")
    else:
        lines.append("The app factory picks it at its next run (06:30 SGT).")
    lines.append("Its PRD comes to #approvals as an app-build request; nothing is built before you approve it.")
    return "\n".join(lines)


# --- the queue ------------------------------------------------------------------------------------


def is_open(row: dict) -> bool:
    """An idea of Ting Yu's that the factory hasn't written or held."""
    status = row.get("effective_status") or row.get("status") or "idea"
    return row.get("source") == SOURCE and status == "idea" and not row.get("held") and not backlog.resting(row)


def queue(rows: list[dict]) -> list[dict]:
    """Ting Yu's open ideas, oldest first (rows without a date last, in file order)."""
    return sorted((r for r in rows if is_open(r)), key=lambda r: str(r.get("added") or "9999-12-31"))


def held_on(rows: list[dict], day: str) -> list[dict]:
    return [r for r in rows if r.get("source") == SOURCE and str(r.get("held") or "") == day]


def sentence(reason: str) -> str:
    """The reason as one sentence: a full stop added only when it doesn't end in one already."""
    reason = reason.rstrip()
    return reason if reason.endswith((".", "!", "?", "…")) else reason + "."


def view(rows: list[dict]) -> list[dict]:
    """The rows with the status `apps context` shows (`backlog.effective`): a PRD file or a live
    registry entry with the row's slug wins over the file. The queue's head is always judged on
    this view, so the code and the factory's `ting_yu_ideas` agree on which idea is first."""
    return backlog.effective(rows, prd_files=catalog.prd_files(), live=catalog.live_apps())


def binding(*, prd_slug: str, prd_name: str, idea: str | None) -> tuple[str | None, list[str]]:
    """(the slug of Ting Yu's row a PRD is filed against, or None; the problems).

    `--idea` may name only the oldest open idea of his, and not when his row would then share a
    name or slug with another row. Without `--idea`, a PRD with that idea's own name or slug is
    bound to it; while it waits unheld, no other PRD may be filed, unless one of his ideas was
    held today. So a seed or factory row is never renamed, and the link doesn't rest on the
    prompt remembering the flag."""
    rows = backlog.load()
    shown = view(rows)
    waiting = queue(shown)
    if idea:
        found = next((r for r in shown if r["slug"] == idea), None)
        if found is None or not is_open(found):
            return None, [f"idea: {idea!r} isn't an open idea of Ting Yu's, so the PRD can't be filed against it"]
        if waiting[0]["slug"] != idea:  # an open idea is always in the queue
            return None, [f"idea: Ting Yu's ideas are filed oldest first, and {waiting[0]['slug']} comes first"]
        other = backlog.find([r for r in rows if r.get("slug") != idea], slug=prd_slug, name=prd_name)
        if other is not None:
            return None, [f"duplicate: {prd_name!r} ({prd_slug}) is already a backlog row ({other['name']}, "
                          f"{other.get('status') or 'idea'}); choose another name for Ting Yu's idea"]
        return idea, []
    if not waiting:
        return None, []
    slug = waiting[0]["slug"]
    if backlog.find([waiting[0]], slug=prd_slug, name=prd_name) is not None:
        return slug, []
    if held_on(rows, timeutil.today_str()):
        return None, []  # one of his ideas was held today: the next one may wait for tomorrow
    return None, [f"idea: Ting Yu's idea {slug} comes first. File its PRD with `--idea {slug}`, or hold it with "
                  f"`apps hold-idea {slug} --reason <why>` if it fails a check, before filing another"]


# --- holding one -----------------------------------------------------------------------------------


def _reason(text: str) -> str:
    reason = " ".join(text.split())
    if len(reason) > REASON_MAX:
        reason = reason[: REASON_MAX - 1].rsplit(" ", 1)[0].rstrip(_EDGE) + "…"
    return reason


def hold(*, slug: str, reason: str) -> dict:
    """Today's pick of Ting Yu's oldest idea failed a check, or its PRD couldn't be filed: the
    reason (at most `REASON_MAX` characters) goes in its notes, and it stops being picked first.
    It stays an idea, so it is still an ordinary candidate. There is no undo; Ting Yu clears
    `held` in the file by hand."""
    reason = _reason(reason)
    if not reason:
        raise Refused("refused: say why it wasn't picked: --reason <text>", 2)
    with backlog.locked():
        rows = backlog.load()
        row = next((r for r in rows if r.get("slug") == slug), None)
        if row is None or row.get("source") != SOURCE:
            raise Refused(f"not held: {slug} isn't an idea of Ting Yu's in the backlog", 1)
        if row.get("held"):
            raise Refused(f"not held: {slug} was already held on {row['held']}", 1)
        shown = view(rows)
        found = next(r for r in shown if r["slug"] == slug)
        if not is_open(found):
            raise Refused(f"not held: {slug} is {found['effective_status']}, not an open idea", 1)
        head = queue(shown)[0]["slug"]
        if head != slug:
            raise Refused(f"not held: {head} comes first; hold only the oldest of Ting Yu's ideas", 1)
        today = timeutil.today_str()
        row.update(held=today, held_reason=reason, notes=backlog._note(row, f"Not picked first on {today}: {reason}"))
        backlog.save(rows)
    return row
