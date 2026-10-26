"""App builds wait for approval (MC §5.7 `app-build` row, §5.9 steps 1, 2, 5 to 7; ticket MC-10).

The factory files a PRD in `prd/pending/apps/` and `apps submit-prd` raises an `app-build`
request for it, subject `app:APP-014`, over the PRD file's bytes. Ting Yu answers in #approvals:

- **Approve** claims the request and writes the build handoff (an `app_builds` row with the
  PRD's path and SHA-256, the request's id and date) in the decision's own transaction
  (`on_approve`). Dispatch polls `apps handoffs --json` and builds it on its own task branch from
  `main` (D6). Until `approvals.dispatch_builds` says Dispatch does, the answer and the one-pager
  say how to build it by hand ("Build it: …").
- **Skip** moves the PRD to `prd/skipped/apps/` with "Skipped by Ting Yu on <date>" at the top
  and drops the backlog idea for good.
- **Unanswered for 7 days**, the PRD moves there with "Expired unanswered on <date>" and the
  backlog idea rests for 30 days before the factory may offer it again.

A PRD changed by one byte after the request no longer matches it: the request is superseded, a
new one raised, and no handoff is written (MC §4.6 A3). `raise_waiting()` is the catch-up pass
(MC §5.9 step 7): it runs before every factory run and every `submit-prd`, and raises a request
only for a factory PRD that has never had one, so each PRD filed before requests existed gets
exactly one.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from jura_growth import approval_settings, approvals, db, log, paths, timeutil
from jura_growth.agents.apps import backlog, catalog
from jura_growth.agents.apps import prd as prd_mod

KIND = "app-build"
REPO = "landing-page"
BASE = "main"
JSON_LIMIT = 64 * 1024  # bytes of `apps handoffs --json` (technical review N5)
REST_DAYS = 30  # an idea whose PRD expired unanswered may come back after this many days


def subject(app_id: str) -> str:
    return f"app:{app_id}"


def app_id_of(subject: str) -> str:
    return subject.removeprefix("app:")


def pending_file(app_id: str) -> catalog.PrdFile | None:
    """The app's PRD in `prd/pending/apps/`, or None once it has left."""
    for found in catalog.prd_files():
        if found.state == "pending" and found.app_id == app_id:
            return found
    return None


# --- the kind -----------------------------------------------------------------


class AppBuild:
    """`app-build`: content is the PRD file's bytes; applied on decide."""

    name = KIND

    def content(self, conn: sqlite3.Connection, subject: str) -> bytes | None:
        found = pending_file(app_id_of(subject))
        if found is None:
            return None
        try:
            return found.path.read_bytes()
        except OSError:
            return None

    def preview(self, conn: sqlite3.Connection, subject: str) -> approvals.Preview:
        app_id = app_id_of(subject)
        found = pending_file(app_id)
        if found is None:
            return approvals.Preview(title=app_id, text="The PRD is no longer in prd/pending/apps/.", reason="")
        from jura_growth.agents.apps import factory

        parsed = prd_mod.parse(found.path.read_text(encoding="utf-8"))
        paragraph, leads = factory.pitch(parsed)
        text = "\n".join(
            [
                paragraph,
                f"Tier: {parsed.tier or found.tier}. Category: {parsed.category or found.category}.",
                f"Lead types it suits: {leads.rstrip('.')}.",
                f"PRD: `{catalog.rel(found.path)}` (attached). Approve hands it to a builder; skip drops the idea.",
            ]
        )
        return approvals.Preview(title=f"{found.app_id} {found.name}", text=text, reason="", files=(found.path,))

    def deadlines(self, conn: sqlite3.Connection, subject: str, now: datetime) -> approvals.Deadlines:
        return approvals.Deadlines(
            decide_by=now + timedelta(days=approval_settings.deadline(KIND, "decide_by_days")),
            use_by=now + timedelta(days=approval_settings.deadline(KIND, "use_by_days")),
        )

    def on_approve(self, conn: sqlite3.Connection, subject: str, args: dict[str, str]) -> str:
        build = hand_off(conn, subject, run_id=log.current_run_id())
        return answer_line(build)

    def on_skip(self, conn: sqlite3.Connection, subject: str) -> None:
        _set_aside(conn, subject, skipped=True)

    def on_expire(self, conn: sqlite3.Connection, subject: str) -> None:
        _set_aside(conn, subject, skipped=False)

    def superseded_note(self, conn: sqlite3.Connection, subject: str) -> str:
        if pending_file(app_id_of(subject)) is None:
            return "the PRD left prd/pending/apps/"
        return "the PRD changed"


# --- raising ------------------------------------------------------------------


def request(conn: sqlite3.Connection, app_id: str, *, reason: str, run_id: int | None) -> approvals.Approval | None:
    """Raise the app's request (A11: only `apps submit-prd` and the catch-up pass call this)."""
    return approvals.request(conn, KIND, subject(app_id), reason=reason, run_id=run_id)


def raise_waiting(conn: sqlite3.Connection, *, run_id: int | None = None) -> list[approvals.Approval]:
    """The catch-up pass (MC §5.9 step 7, AC-M9.11): one request for each factory PRD in
    `prd/pending/apps/` that has never had one and isn't handed off. It runs every time it is
    called but raises at most once per PRD: a PRD with any request on record, whatever became
    of it, is left alone."""
    raised: list[approvals.Approval] = []
    for found in catalog.prd_files():
        if found.state != "pending" or found.author != prd_mod.FACTORY_AUTHOR:
            continue
        on_record = db.scalar(conn, "SELECT count(*) FROM approvals WHERE kind = ? AND subject = ?", (KIND, subject(found.app_id)))
        handed_off = db.scalar(conn, "SELECT count(*) FROM app_builds WHERE app_id = ?", (found.app_id,))
        if on_record or handed_off:
            continue
        with db.transaction(conn):
            made = request(conn, found.app_id, reason=f"the app factory filed {found.app_id} on {found.day}, before requests began",
                           run_id=run_id)
        if made is not None:
            raised.append(made)
    return raised


# --- the handoff ----------------------------------------------------------------


def hand_off(conn: sqlite3.Connection, subject: str, *, run_id: int | None = None) -> dict:
    """The gated action: claim the request, then write the handoff, in the caller's
    `db.transaction(conn)` (the decision's, through `on_approve`). Raises
    `approvals.NotApproved` unless the request is approved, unused and still over the PRD's
    current bytes. Dispatch reads the row only after the transaction commits.

    The row carries the claimed approval's hash, never a hash of its own: the file is read once
    more here and must still hold exactly those bytes, so an edit that lands between the claim
    and this read refuses the handoff and rolls the claim back (code review 10, B1)."""
    approval = approvals.use(conn, KIND, subject, run_id=run_id)
    app_id = app_id_of(subject)
    found = pending_file(app_id)
    try:
        data = found.path.read_bytes() if found is not None else None
    except OSError:
        data = None
    if data is None:  # content() matched a moment ago, so this is a race with a file move
        raise approvals.NotApproved("superseded", f"the PRD for {app_id} left prd/pending/apps/", approval)
    if approvals.content_hash(data) != approval.content_hash:
        raise approvals.NotApproved("superseded", f"the PRD for {app_id} changed after it was claimed, so it isn't handed off",
                                    approval)
    now = timeutil.stamp()
    build = {
        "app_id": app_id,
        "prd_path": catalog.rel(found.path),
        "prd_sha256": approval.content_hash,
        "approval_id": approval.id,
        "approval_at": approval.decided_at or now,
        "handed_off_at": now,
    }
    try:
        conn.execute(
            "INSERT INTO app_builds (app_id, prd_path, prd_sha256, approval_id, approval_at, handed_off_at) "
            "VALUES (:app_id, :prd_path, :prd_sha256, :approval_id, :approval_at, :handed_off_at)",
            build,
        )
    except sqlite3.Error as error:
        # The caller's transaction rolls the claim back with it (G22), and a decision answers
        # `refused` instead of failing.
        raise approvals.NotApproved("unwritten", f"the build handoff couldn't be written ({error}), so nothing was claimed",
                                    approval) from error
    log.event(conn, "apps.build.handed_off", {k: build[k] for k in ("app_id", "prd_path", "approval_id")}, agent=catalog.NAME)
    return build


def build_it(prd_path: str, approval_id: str) -> str:
    """How Ting Yu builds it by hand until Dispatch polls the handoffs (AC-M9.3)."""
    return f"Build it: open Claude Code in `jurasolutions/` and say: build the approved PRD `{prd_path}` (approval {approval_id})"


def answer_line(build: dict) -> str:
    """What the decision answer adds once the handoff is written."""
    if approval_settings.switch("dispatch_builds"):
        return f"Handed to Dispatch: it builds {build['app_id']} on its own branch from {BASE}."
    return build_it(build["prd_path"], build["approval_id"])


# --- reading the handoffs -------------------------------------------------------------


def open_handoffs(conn: sqlite3.Connection) -> list[dict]:
    """Handoffs waiting for a builder, oldest first."""
    rows = db.rows(conn, "SELECT * FROM app_builds WHERE status = 'handed_off' ORDER BY id")
    names = {r["app_id"]: r["name"] for r in db.rows(conn, "SELECT app_id, name FROM app_prds")}
    for row in rows:
        row["name"] = names.get(row["app_id"]) or _file_name(row["app_id"])
    return rows


def _file_name(app_id: str) -> str:
    found = pending_file(app_id)
    return found.name if found else ""


def prd_file(prd_path: str) -> Path:
    """A handoff's PRD on disk, from its path relative to jurasolutions/."""
    relative = Path(prd_path)
    if relative.parts and relative.parts[0] == "prd":
        return paths.prd_dir().joinpath(*relative.parts[1:])
    return paths.JURA_ROOT / relative


def handoff(build: dict) -> tuple[dict | None, str | None]:
    """The `handoff` object Dispatch builds from, or why it can't be handed out: the text it
    gets is exactly the text Ting Yu approved, or nothing."""
    try:
        data = prd_file(build["prd_path"]).read_bytes()
    except OSError:
        return None, "the PRD file can't be read"
    if approvals.content_hash(data) != build["prd_sha256"]:
        return None, "the PRD changed after it was approved; it isn't handed out"
    return {
        "repo": REPO,
        "base": BASE,
        "prd_text": data.decode("utf-8"),
        "prd_sha256": build["prd_sha256"],
        "approval": build["approval_id"],
    }, None


def handoffs_json(conn: sqlite3.Connection) -> dict:
    """`apps handoffs --json`, oldest first, within `JSON_LIMIT` bytes. What doesn't fit is
    counted in `more` and comes on a later poll, once the earlier ones are built."""
    payload: dict = {"contract": 1, "handoffs": [], "more": 0}
    for build in open_handoffs(conn):
        given, problem = handoff(build)
        entry = {
            "app_id": build["app_id"],
            "name": build["name"],
            "prd_path": build["prd_path"],
            "approval": build["approval_id"],
            "approval_at": build["approval_at"],
            "handed_off_at": build["handed_off_at"],
            "handoff": given,
        }
        if problem:
            entry["problem"] = problem
        trial = {**payload, "handoffs": [*payload["handoffs"], entry]}
        if _size(trial) > JSON_LIMIT:
            if not payload["handoffs"] and given is not None:  # one PRD too big for any answer
                entry = {**entry, "handoff": None, "problem": f"the PRD is too large to hand out in one answer ({JSON_LIMIT // 1024} KB)"}
                trial = {**payload, "handoffs": [entry]}
                if _size(trial) <= JSON_LIMIT:
                    payload = trial
                    continue
            payload["more"] += 1
            continue
        payload = trial
    return payload


def _size(payload: dict) -> int:
    return len(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))


def health_lines(conn: sqlite3.Connection) -> list[str]:
    """The one-pager's "build handoffs waiting for a builder" lines (MC §5.4). `conn` is the read
    model's read-only connection."""
    if not db.scalar(conn, "SELECT count(*) FROM sqlite_master WHERE type = 'table' AND name = 'app_builds'"):
        return []
    dispatch = approval_settings.switch("dispatch_builds")
    lines = []
    for build in open_handoffs(conn):
        label = f"{build['app_id']} {build['name']}".strip()
        if dispatch:
            lines.append(f"Build handoff waiting for a builder: {label} (handed to Dispatch, approval {build['approval_id']}).")
        else:
            lines.append(f"Build handoff waiting for a builder: {label}. {build_it(build['prd_path'], build['approval_id'])}.")
    return lines


# --- skip and expiry ----------------------------------------------------------------


def _set_aside(conn: sqlite3.Connection, subject: str, *, skipped: bool) -> None:
    """Move the PRD to `prd/skipped/apps/` with why at the top, and update the backlog, once
    the decision or expiry that called this commits (`db.after_commit`): a transaction that
    rolls back leaves the PRD and the backlog as they were (code review 10, N4)."""
    app_id = app_id_of(subject)
    record = db.one(conn, "SELECT id, decide_by FROM approvals WHERE kind = ? AND subject = ? ORDER BY id DESC LIMIT 1",
                    (KIND, subject))
    shown = approvals.format_id(record["id"]) if record else "none"
    if skipped:
        day = timeutil.today_str()
        why = f"Skipped by Ting Yu on {day} (approval {shown})."
    else:
        day = timeutil.parse(record["decide_by"]).astimezone(timeutil.SGT).date().isoformat() if record else timeutil.today_str()
        why = f"Expired unanswered on {day} (approval {shown})."
    found = pending_file(app_id)
    target = catalog.skipped_dir() / found.path.name if found is not None else None
    slug = found.slug if found else None
    name = found.name if found else None

    def apply() -> None:
        try:
            if found is not None and target is not None and found.path.exists():
                # The skipped copy is written before the pending file goes, so the PRD is never lost.
                paths.writable(target).write_text(f"{why}\n\n{found.path.read_text(encoding='utf-8')}", encoding="utf-8")
                found.path.unlink()
            if skipped:
                backlog.drop(app_id=app_id, slug=slug, name=name, note=why)
            else:
                reopens = (datetime.fromisoformat(day) + timedelta(days=REST_DAYS)).date().isoformat()
                backlog.rest(app_id=app_id, slug=slug, name=name, note=why, reopens=reopens)
        except Exception as error:  # noqa: BLE001 - the decision has committed; say what is left to do
            log.event(conn, "apps.prd.set_aside_failed", {"app_id": app_id, "approval": shown, "why": why,
                                                          "error": f"{type(error).__name__}: {error}"},
                      level="error", agent=catalog.NAME)

    log.event(conn, "apps.prd.skipped" if skipped else "apps.prd.expired",
              {"app_id": app_id, "subject": subject, "approval": shown,
               "moved_to": catalog.rel(target) if target is not None else None}, agent=catalog.NAME)
    if not db.after_commit(conn, apply):
        apply()
