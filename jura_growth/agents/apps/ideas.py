"""Ting Yu's own toolbox ideas (`jura-growth apps idea`, `apps hold-idea`).

`apps idea <text>` adds one backlog row with `source: ting-yu`, the text verbatim in `does`, a
name from the text and the date and actor. It writes nothing else: the factory still writes the
PRD, and the `app-build` and `app-release` decisions still gate the build. It is a control
command from Discord (`remote.ALLOWLIST`) and never a scheduled run's (`headless.NEVER`).

The factory picks these ideas before any other candidate, oldest first (`queue`, shown as
`ting_yu_ideas` in `apps context --json`). One that fails a check is held (`hold`): the reason
goes in the row's notes and in that day's digest, and the idea becomes an ordinary candidate.
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
_EDGE = " \t\r\n.,;:!?\"'()[]{}"


class Refused(Exception):
    """The idea isn't added. `code` is the exit code: 2 for the text itself, 1 for a clash."""

    def __init__(self, text: str, code: int):
        super().__init__(text)
        self.text, self.code = text, code


@dataclass
class Added:
    row: dict
    ahead: int  # Ting Yu's open ideas older than this one, which the factory picks first


def name_for(text: str) -> str:
    """The part before the first ":" when there is one, else the first few words, in sentence
    case. The factory may rename it to meet its name rules (`submit-prd --idea`)."""
    before, colon, after = text.partition(":")
    name = before.strip(_EDGE) if colon else ""
    if not name or len(name) > NAME_MAX:
        name = " ".join((after if colon and not before.strip(_EDGE) else text).split()[:NAME_WORDS])
    name = " ".join(name.strip(_EDGE).split())
    return name[:1].upper() + name[1:]


def slug_for(name: str) -> str:
    slug = prd_mod.slugify(name)
    if len(slug) > SLUG_MAX:
        slug = slug[:SLUG_MAX].rsplit("-", 1)[0]
    return slug


def clash(conn: sqlite3.Connection, *, name: str, slug: str) -> str | None:
    """What the idea would duplicate, by the catalog's slug and name checks: any backlog row,
    then anything live, pending or built (`catalog.taken`)."""
    wanted = prd_mod.normalise_name(name)
    for row in backlog.load():
        if (row.get("slug") or prd_mod.slugify(row["name"])) == slug or prd_mod.normalise_name(row["name"]) == wanted:
            status = row.get("status") or "idea"
            return f"{row['name']} (backlog: {status}{', ' + row['app_id'] if row.get('app_id') else ''})"
    slugs, names = catalog.taken(conn)
    if slug in slugs:
        return f"the slug {slug} ({slugs[slug]})"
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
    if not slug:
        raise Refused("refused: the idea needs some words to name it", 2)
    clashes = clash(conn, name=name, slug=slug)
    if clashes:
        raise Refused(f'not added: "{name}" ({slug}) clashes with {clashes}. Send it with a different name before a colon.', 1)
    today = timeutil.today_str()
    rows = backlog.load()
    ahead = len(queue(rows))
    row = {"name": name, "slug": slug, "does": text, "status": "idea", "source": SOURCE, "added": today,
           "actor": actor, "notes": f"Sent by Ting Yu with `apps idea` on {today}."}
    rows.append(row)
    backlog.save(rows)
    return Added(row, ahead)


def is_open(row: dict) -> bool:
    """An idea of Ting Yu's that the factory hasn't written or held."""
    status = row.get("effective_status") or row.get("status") or "idea"
    return row.get("source") == SOURCE and status == "idea" and not row.get("held") and not backlog.resting(row)


def queue(rows: list[dict]) -> list[dict]:
    """Ting Yu's open ideas, oldest first (rows without a date last, in file order)."""
    return sorted((r for r in rows if is_open(r)), key=lambda r: str(r.get("added") or "9999-12-31"))


def hold(*, slug: str, reason: str) -> dict:
    """Today's pick of Ting Yu's idea failed a check: the reason goes in its notes, and it stops
    being picked first. It stays an idea, so it is still an ordinary candidate."""
    reason = " ".join(reason.split())
    if not reason:
        raise Refused("refused: say why it wasn't picked: --reason <text>", 1)
    rows = backlog.load()
    row = next((r for r in rows if r.get("slug") == slug), None)
    if row is None or row.get("source") != SOURCE:
        raise Refused(f"not held: {slug} isn't an idea of Ting Yu's in the backlog", 1)
    if row.get("held"):
        raise Refused(f"not held: {slug} was already held on {row['held']}", 1)
    if (row.get("status") or "idea") != "idea":
        raise Refused(f"not held: {slug} is {row.get('status')}, not an idea", 1)
    today = timeutil.today_str()
    row.update(held=today, held_reason=reason,
               notes=f"{(row.get('notes') or '').strip()} Not picked first on {today}: {reason}".strip())
    backlog.save(rows)
    return row


def held_on(day: str) -> list[dict]:
    return [r for r in backlog.load() if r.get("source") == SOURCE and str(r.get("held") or "") == day]


def link_problem(slug: str) -> str | None:
    """Why `submit-prd --idea <slug>` can't mark that row, or None."""
    row = next((r for r in backlog.load() if r.get("slug") == slug), None)
    if row is None or (row.get("status") or "idea") != "idea" or backlog.resting(row):
        return f"idea: {slug!r} isn't an open idea in the backlog, so the PRD can't be filed against it"
    return None


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
        lines.append(f"{count} first; the app factory writes one PRD a day at 06:30 SGT, oldest first.")
    else:
        lines.append("The app factory picks it at its next run (06:30 SGT).")
    lines.append("Its PRD comes to #approvals as an app-build request; nothing is built before you approve it.")
    return "\n".join(lines)
