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
from jura_growth.agents.apps import builds, catalog

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


def claimed_release(conn: sqlite3.Connection, app_id: str) -> approvals.Approval | None:
    """The app's latest `app-release` request, when it has been claimed by `release-plan`."""
    row = db.one(conn, "SELECT id FROM approvals WHERE kind = ? AND subject = ? ORDER BY id DESC LIMIT 1",
                 (KIND, subject(app_id)))
    latest = approvals.get(conn, approvals.format_id(row["id"])) if row else None
    return latest if latest is not None and latest.used_at else None
