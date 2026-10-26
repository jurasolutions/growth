"""App releases wait for a second approval, bound to the commit (MC §5.7 `app-release` row, §5.9
steps 3 and 4; ticket MC-10b).

A handed-off build (`builds.py`) is built on its own task branch from `main`, with a Cloudflare
Pages preview. Then:

- **`apps built`** (Dispatch D6, or Ting Yu after a hand build) records the task, the branch, its
  head commit and the preview on the build's `app_builds` row, and raises an `app-release` request,
  subject `app:APP-014`, over the app id, task id, branch and full commit SHA. A commit pushed
  later changes that content, so the request is superseded and a new one is raised for it
  (technical review N5).
- **`apps release-plan`** is the gated action. It claims the approved request (MC §4.6 A6) and
  stamps the row in one transaction, then prints the merge of exactly the approved commit into
  `main`. Ting Yu runs it by hand until Dispatch D7 can.
- **`apps released`** records the release once `main` of the landing-page repository contains the
  claimed commit (`git merge-base --is-ancestor`; it never fetches, pulls or writes), moves the
  PRD to `prd/done/apps/` with the ship date and a sign-off line naming both approvals, and marks
  the backlog row live.

Skip, no answer in 7 days, or an approval unused for 14 days all leave the build on its preview;
the one-pager lists it. `apps built` again asks again.
"""

from __future__ import annotations

import json
import re
import shlex
import sqlite3
import subprocess
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable
from urllib.parse import urlsplit

from jura_growth import approval_settings, approvals, db, log, paths, timeutil
from jura_growth.agents.apps import backlog, builds, catalog

KIND = "app-release"
TASK_RE = re.compile(r"^T-\d{4,}$")
SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
PREVIEW_HOST = ".pages.dev"
GIT_TIMEOUT = 30  # seconds


def subject(app_id: str) -> str:
    return builds.subject(app_id)


def short(sha: str) -> str:
    return sha[:7]


def current_build(conn: sqlite3.Connection, app_id: str) -> dict | None:
    """The app's unreleased build: handed off, or built and waiting for its release."""
    return db.one(conn, "SELECT * FROM app_builds WHERE app_id = ? AND status IN ('handed_off', 'built')", (app_id,))


def _built(conn: sqlite3.Connection, app_id: str) -> dict | None:
    row = current_build(conn, app_id)
    return row if row is not None and row["status"] == "built" else None


def encode(row: dict) -> bytes:
    """The canonical content of a release: what `main` will receive, and from where."""
    fields = {"app_id": row["app_id"], "branch": row["branch"], "sha": row["head_sha"], "task_id": row["task_id"]}
    text = json.dumps(fields, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return unicodedata.normalize("NFC", text).encode("utf-8")


def app_name(conn: sqlite3.Connection, app_id: str) -> str:
    name = db.scalar(conn, "SELECT name FROM app_prds WHERE app_id = ?", (app_id,))
    if name:
        return name
    found = builds.pending_file(app_id)
    return found.name if found else ""


# --- the landing-page repository (read only) -----------------------------------------------------


def _git(*args: str) -> subprocess.CompletedProcess | None:
    """`git -C <site repo> …`, for reading only. None when git can't run at all."""
    try:
        return subprocess.run(["git", "-C", str(paths.site_repo()), *args], capture_output=True, text=True,
                              timeout=GIT_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError):
        return None


def site_ready() -> bool:
    """The landing-page repository is a git checkout with a `main` branch."""
    done = _git("rev-parse", "--verify", "--quiet", "refs/heads/main^{commit}")
    return done is not None and done.returncode == 0


def on_main(sha: str) -> bool | None:
    """Whether `main` contains `sha`: True, False, or None when git can't tell (no repository, or
    a commit it has never fetched). Never fetches, pulls or writes."""
    done = _git("merge-base", "--is-ancestor", sha, "main")
    if done is None:
        return None
    return {0: True, 1: False}.get(done.returncode)


# --- the kind --------------------------------------------------------------------------------------


class AppRelease:
    """`app-release`: content is the app id, task id, branch and head commit; claimed later, by
    `apps release-plan`."""

    name = KIND
    used_word = "claimed"

    def content(self, conn: sqlite3.Connection, subject: str) -> bytes | None:
        row = _built(conn, builds.app_id_of(subject))
        return encode(row) if row is not None else None

    def preview(self, conn: sqlite3.Connection, subject: str) -> approvals.Preview:
        app_id = builds.app_id_of(subject)
        row = _built(conn, app_id)
        title = f"{app_id} {app_name(conn, app_id)}".strip()
        if row is None:
            return approvals.Preview(title=title, text="The build is no longer waiting for a release.", reason="")
        text = "\n".join(
            [
                f"Preview: {row['preview_url']}",
                f"Commit: {short(row['head_sha'])} on `{row['branch']}` (task {row['task_id']}).",
                f"Approve, then `jura-growth apps release-plan {app_id}` prints the merge of exactly this commit into main. "
                "Skip keeps it on its preview.",
            ]
        )
        return approvals.Preview(title=f"{title}: release to jurasolutions.sg", text=text, reason="")

    def deadlines(self, conn: sqlite3.Connection, subject: str, now: datetime) -> approvals.Deadlines:
        return approvals.Deadlines(
            decide_by=now + timedelta(days=approval_settings.deadline(KIND, "decide_by_days")),
            use_by=now + timedelta(days=approval_settings.deadline(KIND, "use_by_days")),
        )

    def switched_off(self, conn: sqlite3.Connection, subject: str) -> str | None:
        """The release has nowhere to go without the landing-page repository and its `main`."""
        if site_ready():
            return None
        return f"the landing-page repository isn't at {paths.site_repo()} with a main branch, so there is nothing to merge into"

    def on_skip(self, conn: sqlite3.Connection, subject: str) -> None:
        _stays_on_preview(conn, subject, "skipped")

    def on_expire(self, conn: sqlite3.Connection, subject: str) -> None:
        _stays_on_preview(conn, subject, "expired")

    def on_lapse(self, conn: sqlite3.Connection, subject: str) -> None:
        _stays_on_preview(conn, subject, "lapsed")

    def superseded_note(self, conn: sqlite3.Connection, subject: str) -> str:
        if _built(conn, builds.app_id_of(subject)) is None:
            return "the build is no longer waiting for a release"
        return "a newer commit was reported for the build"


def _stays_on_preview(conn: sqlite3.Connection, subject: str, why: str) -> None:
    app_id = builds.app_id_of(subject)
    row = _built(conn, app_id)
    log.event(conn, f"apps.release.{why}", {"app_id": app_id, "subject": subject,
                                           "sha": row["head_sha"] if row else None}, agent=catalog.NAME)


# --- `apps built` ------------------------------------------------------------------------------------


@dataclass
class Outcome:
    ok: bool
    lines: list[str] = field(default_factory=list)
    approval: approvals.Approval | None = None


def check_build(*, task: str, branch: str, sha: str, preview: str) -> list[str]:
    """Why these can't be bound to a release request, or shown on its card and in a merge command."""
    problems = []
    if not TASK_RE.fullmatch(task):
        problems.append(f"--task must be a Dispatch task id like T-0031, not {task!r}")
    if not BRANCH_RE.fullmatch(branch) or ".." in branch or branch.endswith((".lock", "/")):
        problems.append("--branch must be a plain branch name like claude/T-0031-paynow-qr")
    if not SHA_RE.fullmatch(sha.lower()):
        problems.append("--sha must be the branch's full head commit SHA (40 hex characters)")
    parts = urlsplit(preview)
    host = parts.hostname or ""
    if parts.scheme != "https" or parts.username or parts.password or parts.port or not host.endswith(PREVIEW_HOST) \
            or not re.fullmatch(r"[a-z0-9.-]+", host):
        problems.append(f"--preview must be the branch's https://…{PREVIEW_HOST} preview link")
    return problems


def report_built(conn: sqlite3.Connection, app_id: str, *, task: str, branch: str, sha: str, preview: str,
                 run_id: int | None) -> Outcome:
    """`apps built`: record the build on its handoff row and raise its `app-release` request (A11).
    Refuses a build that was never handed off."""
    problems = check_build(task=task, branch=branch, sha=sha, preview=preview)
    if problems:
        return Outcome(False, [f"refused: {p}" for p in problems])
    sha = sha.lower()
    with db.transaction(conn):
        row = current_build(conn, app_id)
        if row is None:
            return Outcome(False, [f"refused: {app_id} has no build handed off, so there is nothing to release. "
                                   "Its app-build request must be approved first."])
        reported = {**row, "task_id": task, "branch": branch, "head_sha": sha}
        claimed = claimed_release(conn, app_id)
        if row["status"] == "built" and claimed is not None and claimed.content_hash == approvals.content_hash(encode(reported)):
            return Outcome(True, [f"{claimed.id} already covers {app_id} at {short(sha)} and its merge was handed out. "
                                  f"Once main holds it, run `jura-growth apps released {app_id} --task {task}`."], claimed)
        conn.execute(
            "UPDATE app_builds SET status = 'built', task_id = ?, branch = ?, head_sha = ?, preview_url = ?, built_at = ? "
            "WHERE id = ?",
            (task, branch, sha, preview, timeutil.stamp(), row["id"]),
        )
        log.event(conn, "apps.build.built", {"app_id": app_id, "task": task, "branch": branch, "sha": sha}, agent=catalog.NAME)
        reason = f"{task} built {app_id} on {branch}"
        request = approvals.request(conn, KIND, subject(app_id), reason=reason, run_id=run_id)
        if request is not None and request.status == approvals.EXPIRED:  # the old one lapsed just now; ask again
            request = approvals.request(conn, KIND, subject(app_id), reason=reason, run_id=run_id)
    assert request is not None  # the row is built, so the content exists
    if request.status == approvals.APPROVED:
        follow = f"It is approved: run `jura-growth apps release-plan {app_id}` for the merge."
    else:
        follow = "Approve it in #approvals to release it; until then it stays on its preview."
    return Outcome(True, [f"{request.id}: release of {app_id} at {short(sha)} from {branch} ({task}). {follow}"], request)


# --- `apps release-plan` -----------------------------------------------------------------------------


def plan_release(conn: sqlite3.Connection, app_id: str, *, run_id: int | None,
                 emit: Callable[[str], None]) -> Outcome:
    """`apps release-plan`, the gated action (A6). In one transaction it claims the approved
    `app-release` request and stamps `release_planned_at` on the build; only after that commits
    does `emit` get the merge of exactly the approved commit. On a refusal nothing is emitted, and
    any lapse or supersede the claim found is kept."""
    refusal: str | None = None
    try:
        with db.transaction(conn):
            try:
                approval = approvals.use(conn, KIND, subject(app_id), run_id=run_id)
            except approvals.NotApproved as refused:
                refusal = refused.text
            else:
                row = _built(conn, app_id)
                assert row is not None  # use() just matched its content
                conn.execute("UPDATE app_builds SET release_planned_at = ? WHERE id = ?", (timeutil.stamp(), row["id"]))
                log.event(conn, "apps.release.planned", {"app_id": app_id, "approval": approval.id, "sha": row["head_sha"]},
                          agent=catalog.NAME)
    except sqlite3.Error as error:
        refusal = f"the release plan couldn't be recorded ({error}), so nothing was claimed"
    if refusal is not None:
        return Outcome(False, [f"refused: {refusal}. There is no merge to run."])
    lines = merge_plan(app_id, row, approval)
    for line in lines:
        emit(line)
    return Outcome(True, lines, approval)


def merge_plan(app_id: str, row: dict, approval: approvals.Approval) -> list[str]:
    """The commands Ting Yu runs by hand (until Dispatch D7): fetch the task branch, then merge
    exactly the approved commit into `main`, never the branch, whose head may have moved."""
    repo = shlex.quote(str(paths.site_repo()))
    branch = shlex.quote(row["branch"])
    return [
        f"{approval.id} claimed: release {app_id} at {short(row['head_sha'])} from {row['branch']} ({row['task_id']}).",
        "Merge exactly this commit into main of the landing-page repository, then record the release:",
        f"  cd {repo}",
        f"  git fetch origin {branch}",
        "  git switch main",
        "  git pull --ff-only origin main",
        f'  git merge --no-ff -m "Release {app_id} (approval {approval.id})" {row["head_sha"]}',
        "  git push origin main",
        f"  jura-growth apps released {app_id} --task {row['task_id']}",
    ]


# --- `apps released` ----------------------------------------------------------------------------------


SIGNED_BLANK = re.compile(r"^Signed off by: _+[ \t]+Date: _+[ \t]*$", re.M)


def record_released(conn: sqlite3.Connection, app_id: str, *, task: str) -> Outcome:
    """`apps released`: the completion write (A6). It needs the request `release-plan` claimed,
    still over the build's commit, and `main` of the landing-page repository containing that
    commit; it never re-checks a deadline. Then the build is `released`, the PRD moves to
    `prd/done/apps/` with the ship date and both approvals, and the backlog row goes live."""
    row = db.one(conn, "SELECT * FROM app_builds WHERE app_id = ? AND task_id = ? ORDER BY id DESC LIMIT 1", (app_id, task))
    if row is None or row["status"] not in ("built", "released"):
        return Outcome(False, [f"refused: {app_id} has no build reported under {task}; `apps built` reports one."])
    if row["status"] == "released":
        return Outcome(True, [f"{app_id} was already recorded as released on {row['released_at'][:10]}."])
    claimed = claimed_release(conn, app_id)
    if claimed is None:
        return Outcome(False, [f"refused: {app_id} has no claimed app-release request. Approve its release in #approvals, "
                               f"then run `jura-growth apps release-plan {app_id}` and the merge it prints."])
    sha = row["head_sha"]
    if claimed.content_hash != approvals.content_hash(encode(row)):
        return Outcome(False, [f"refused: {claimed.id} covers another commit than the one reported for {app_id} "
                               f"({short(sha)}); approve the release of the new commit first."])
    contained = on_main(sha)
    if contained is None:
        return Outcome(False, [f"refused: git can't tell whether main of {paths.site_repo()} contains {short(sha)}. "
                               "Pull main after the merge, then run this again."])
    if not contained:
        return Outcome(False, [f"refused: main of {paths.site_repo()} doesn't contain {short(sha)} yet. "
                               f"Run the merge `apps release-plan` printed for {claimed.id}, then this again."])
    found = builds.pending_file(app_id)
    with db.transaction(conn):
        done = conn.execute(
            "UPDATE app_builds SET status = 'released', released_at = ? WHERE id = ? AND status = 'built' AND head_sha = ?",
            (timeutil.stamp(), row["id"], sha),
        ).rowcount
        if done:
            log.event(conn, "apps.release.recorded", {"app_id": app_id, "task": task, "sha": sha, "approval": claimed.id,
                                                       "build_approval": row["approval_id"]}, agent=catalog.NAME)
    if not done:
        return Outcome(False, [f"refused: the build of {app_id} changed while this ran; run it again."])
    lines = [f"Recorded: {app_id} released at {short(sha)} ({task}), approvals {row['approval_id']} and {claimed.id}."]
    try:
        moved = _file_done(found, row, claimed)
    except OSError as error:
        log.event(conn, "apps.prd.done_move_failed", {"app_id": app_id, "error": f"{type(error).__name__}: {error}"},
                  level="error", agent=catalog.NAME)
        moved = None
        lines.append(f"The PRD couldn't be moved to prd/done/apps/ ({type(error).__name__}); move it by hand.")
    if moved is not None:
        lines.append(f"PRD moved to {moved}.")
    elif found is None:
        lines.append("Its PRD isn't in prd/pending/apps/, so nothing was moved.")
    return Outcome(True, lines, claimed)


def _day(stamp: str | None) -> str:
    return timeutil.parse(stamp).astimezone(timeutil.SGT).date().isoformat() if stamp else "?"


def _file_done(found: catalog.PrdFile | None, row: dict, release: approvals.Approval) -> str | None:
    """Move the PRD to `prd/done/apps/`: the ship date on top, both approvals on the sign-off
    line. The done copy is written before the pending file goes, so the PRD is never lost."""
    if found is None or not found.path.exists():
        return None
    today = timeutil.today_str()
    shipped = (f"*Shipped on {today}: released to jurasolutions.sg from `{row['branch']}` at {short(row['head_sha'])} "
               f"(task {row['task_id']}).*")
    signed = (f"Signed off by: Ting Yu in #approvals, build approval {row['approval_id']} ({_day(row['approval_at'])}) and "
              f"release approval {release.id} ({_day(release.decided_at)})  Date: {today}")
    text = found.path.read_text(encoding="utf-8")
    text, filled = SIGNED_BLANK.subn(lambda _: signed, text, count=1)
    if not filled:
        text = text.rstrip("\n") + f"\n\n{signed}\n"
    target = paths.writable(catalog.done_dir() / found.path.name)
    target.write_text(f"{shipped}\n\n{text}", encoding="utf-8")
    found.path.unlink()
    relative = catalog.rel(target)
    backlog.release(app_id=found.app_id, slug=found.slug, name=found.name, prd_path=relative,
                    note=f"Released on {today} at {short(row['head_sha'])} (approval {release.id}).")
    return relative


def claimed_release(conn: sqlite3.Connection, app_id: str) -> approvals.Approval | None:
    """The app's latest `app-release` request, when it has been claimed by `release-plan`."""
    row = db.one(conn, "SELECT id FROM approvals WHERE kind = ? AND subject = ? ORDER BY id DESC LIMIT 1",
                 (KIND, subject(app_id)))
    latest = approvals.get(conn, approvals.format_id(row["id"])) if row else None
    return latest if latest is not None and latest.used_at else None
