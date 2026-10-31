"""App releases wait for a second approval, bound to the commit (MC §5.7 `app-release` row, §5.9
steps 3 and 4; ticket MC-10b).

A handed-off build (`builds.py`) is built on its own task branch from `main`, with a Cloudflare
Pages preview. Then:

- **`apps built`** (Dispatch D6, or Ting Yu after a hand build) records the task, the branch, its
  head commit and the preview on the build's `app_builds` row, and raises an `app-release` request,
  subject `app:APP-014`, over the app id, task id, branch, full commit SHA and preview link. A
  commit pushed later, or another preview link, changes that content, so the request is superseded
  and a new one is raised for it (technical review N5; code review 10b, S2). The preview must be a
  bare preview link of the landing page's own Pages project (`pages_project` in
  `config/apps.yaml`), so the card can only ever link there (code review 10b, B1 and S1).
- **`apps release-plan`** is the gated action. It claims the approved request (MC §4.6 A6) and
  stamps the row in one transaction, then prints the merge of exactly the approved commit into
  `main`. Ting Yu runs it by hand until Dispatch D7 can. Run again while the build still hashes
  to the claimed request, it prints the same merge with no new claim, so a lost answer can be
  fetched again.
- **`apps released`** records the release once the branch `main` of the landing-page repository
  contains the claimed commit (`git merge-base --is-ancestor <sha> refs/heads/main`; it never
  fetches, pulls or writes), moves the PRD to `prd/done/apps/` with the ship date and a sign-off
  line naming both approvals, and marks the backlog row live.

Skip, no answer in 7 days, or an approval unused for 14 days all leave the build on its preview;
the one-pager lists it. `apps built` again asks again.
"""

from __future__ import annotations

import json
import re
import shlex
import sqlite3
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from jura_growth import approvals, db, discord, log, paths, timeutil
from jura_growth.agents import LISTED, YOU, PendingItem
from jura_growth.agents.apps import backlog, builds, catalog

KIND = "app-release"
MAIN = "refs/heads/main"  # never the bare name, which a tag `main` would shadow (code review 10b, S3)
TASK_RE = re.compile(r"^T-\d{4,}$")
SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
PROJECT_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,56}[a-z0-9])?")
GIT_TIMEOUT = 30  # seconds


def short(sha: str) -> str:
    return sha[:7]


def current_build(conn: sqlite3.Connection, app_id: str) -> dict | None:
    """The app's unreleased build: handed off, or built and waiting for its release."""
    return db.one(conn, "SELECT * FROM app_builds WHERE app_id = ? AND status IN ('handed_off', 'built')", (app_id,))


def _built(conn: sqlite3.Connection, app_id: str) -> dict | None:
    row = current_build(conn, app_id)
    return row if row is not None and row["status"] == "built" else None


def encode(row: dict) -> bytes:
    """The canonical content of a release: what `main` will receive, from where, and the preview
    Ting Yu was shown, as their exact bytes with no Unicode normalisation (ADR 0003 as amended)."""
    fields = {"app_id": row["app_id"], "branch": row["branch"], "preview": row["preview_url"], "sha": row["head_sha"],
              "task_id": row["task_id"]}
    return json.dumps(fields, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


# --- the preview link --------------------------------------------------------------------------------


def pages_project() -> str | None:
    """The landing page's Cloudflare Pages project (`pages_project` in config/apps.yaml), or None
    while it isn't set or isn't a plain project name."""
    value = catalog.settings().get("pages_project")
    return value if isinstance(value, str) and PROJECT_RE.fullmatch(value) else None


def preview_pattern(project: str) -> re.Pattern:
    """A preview of `project` and nothing else: `https://<alias>.<project>.pages.dev`, optionally
    with a plain path. The alphabet has no whitespace and no Markdown character, so the link shows
    on the card exactly as written and can't carry a masked link elsewhere (code review 10b, B1)."""
    return re.compile(rf"https://[a-z0-9](?:[a-z0-9-]{{0,61}}[a-z0-9])?\.{re.escape(project)}\.pages\.dev(?:/[a-z0-9./-]*)?")


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
    done = _git("rev-parse", "--verify", "--quiet", f"{MAIN}^{{commit}}")
    return done is not None and done.returncode == 0


def on_main(sha: str) -> bool | None:
    """Whether the branch `main` contains `sha`: True, False, or None when git can't tell (no
    repository, or a commit it has never fetched). Never fetches, pulls or writes."""
    done = _git("merge-base", "--is-ancestor", sha, MAIN)
    if done is None:
        return None
    return {0: True, 1: False}.get(done.returncode)


# --- the kind --------------------------------------------------------------------------------------


class AppRelease:
    """`app-release`: content is the app id, task id, branch, head commit and preview; claimed
    later, by `apps release-plan`."""

    name = KIND
    used_word = "claimed"

    def feed_approved(self, conn: sqlite3.Connection, subject: str) -> str:
        return f"Next: `/growth apps release-plan {builds.app_id_of(subject)}` prints the merge of exactly this commit."

    def content(self, conn: sqlite3.Connection, subject: str) -> bytes | None:
        row = _built(conn, builds.app_id_of(subject))
        return encode(row) if row is not None else None

    def preview(self, conn: sqlite3.Connection, subject: str) -> approvals.Preview:
        app_id = builds.app_id_of(subject)
        row = _built(conn, app_id)
        title = f"{app_id} {builds.app_name(conn, app_id)}".strip()
        if row is None:
            return approvals.Preview(title=title, text="The build is no longer waiting for a release.", reason="")
        sha = short(row["head_sha"])
        text = "\n".join(
            [
                f"Preview: {row['preview_url']}",
                f"Commit: {sha} on `{row['branch']}` (task {row['task_id']}). The preview shows the branch's latest push; "
                f"the release is commit {sha} only.",
                f"Approve, then `jura-growth apps release-plan {app_id}` prints the merge of exactly this commit into main. "
                "Skip keeps it on its preview.",
            ]
        )
        return approvals.Preview(title=f"{title}: release to jurasolutions.sg", text=text, reason="")

    def deadlines(self, conn: sqlite3.Connection, subject: str, now: datetime) -> approvals.Deadlines:
        return builds.day_deadlines(KIND, now)

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
        return "a newer commit or preview was reported for the build"


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
    project = pages_project()
    if project is None:
        problems.append("pages_project isn't set in config/apps.yaml: set it to the landing page's Cloudflare Pages "
                        "project, so a preview link can be checked")
    elif not preview_pattern(project).fullmatch(preview):
        problems.append(f"--preview must be a bare preview link of the {project} Pages project, like "
                        f"https://<branch>.{project}.pages.dev, in lower case, with nothing else")
    return problems


def report_built(conn: sqlite3.Connection, app_id: str, *, task: str, branch: str, sha: str, preview: str,
                 run_id: int | None) -> Outcome:
    """`apps built`: record the build on its handoff row and raise its `app-release` request (A11).
    Refuses a build that was never handed off, and a commit `main` already contains."""
    problems = check_build(task=task, branch=branch, sha=sha, preview=preview)
    if problems:
        return Outcome(False, [f"refused: {p}" for p in problems])
    sha = sha.lower()
    if on_main(sha):
        return Outcome(False, [f"refused: main already contains {short(sha)}, so there is nothing to release. "
                               "Report the task branch's own head commit."])
    with db.transaction(conn):
        row = current_build(conn, app_id)
        if row is None:
            return Outcome(False, [f"refused: {app_id} has no build handed off, so there is nothing to release. "
                                   "Its app-build request must be approved first."])
        reported = {**row, "task_id": task, "branch": branch, "head_sha": sha, "preview_url": preview}
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
        request = approvals.request(conn, KIND, builds.subject(app_id), reason=reason, run_id=run_id)
        if request is not None and request.status == approvals.EXPIRED:  # the old one lapsed just now; ask again
            request = approvals.request(conn, KIND, builds.subject(app_id), reason=reason, run_id=run_id)
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
    `app-release` request and stamps `release_planned_at` on the build, its in-flight marker;
    only after that commits does `emit` get the merge of exactly the approved commit. On a refusal
    nothing is emitted, and any lapse or supersede the claim found is kept.

    A retry after the claim, while the build still hashes to the claimed request, gets the same
    merge again with no new claim: the answer may have been lost on its way back, and the merge
    names a fixed SHA, so printing it again releases nothing new (A6, ADR 0003; final review Sp3)."""
    refusal: str | None = None
    claimed: tuple[dict, approvals.Approval] | None = None
    try:
        with db.transaction(conn):
            again = _planned(conn, app_id)
            if again is not None:
                log.event(conn, "apps.release.plan_repeated", {"app_id": app_id, "approval": again[1].id,
                                                               "sha": again[0]["head_sha"]}, agent=catalog.NAME)
                claimed = again
            else:
                try:
                    approval = approvals.use(conn, KIND, builds.subject(app_id), run_id=run_id)
                except approvals.NotApproved as refused:
                    refusal = refused.text
                else:
                    row = _built(conn, app_id)
                    assert row is not None  # use() just matched its content
                    conn.execute("UPDATE app_builds SET release_planned_at = ? WHERE id = ?", (timeutil.stamp(), row["id"]))
                    log.event(conn, "apps.release.planned", {"app_id": app_id, "approval": approval.id,
                                                             "sha": row["head_sha"]}, agent=catalog.NAME)
                    claimed = (row, approval)
    except sqlite3.Error as error:
        claimed, refusal = None, f"the release plan couldn't be recorded ({error}), so nothing was claimed"
    if claimed is None:
        return Outcome(False, [f"refused: {refusal}. There is no merge to run."])
    row, approval = claimed
    lines = merge_plan(app_id, row, approval)
    for line in lines:
        emit(line)
    return Outcome(True, lines, approval)


def _planned(conn: sqlite3.Connection, app_id: str) -> tuple[dict, approvals.Approval] | None:
    """The built row and its `app-release` request when `release-plan` already claimed it and the
    build still hashes to it: the case where the same merge may be printed again."""
    row = _built(conn, app_id)
    claimed = claimed_release(conn, app_id)
    if row is None or claimed is None or not row["release_planned_at"]:
        return None
    if claimed.content_hash != approvals.content_hash(encode(row)):
        return None
    return row, claimed


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
    still over the build's content, and the branch `main` of the landing-page repository
    containing the commit; it never re-checks a deadline. Then the build is `released`, the PRD
    moves to `prd/done/apps/` with the ship date and both approvals, and the backlog row goes live,
    whether or not the PRD was there to move."""
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
        return Outcome(False, [f"refused: {claimed.id} covers another commit or preview than the one reported for {app_id} "
                               f"({short(sha)}); approve the release of the new one first."])
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
    moved = None
    if found is None or not found.path.exists():
        lines.append("Its PRD isn't in prd/pending/apps/, so nothing was moved.")
    else:
        try:
            moved = _file_done(found, row, claimed)
            lines.append(f"PRD moved to {moved}.")
        except OSError as error:
            log.event(conn, "apps.prd.done_move_failed", {"app_id": app_id, "error": f"{type(error).__name__}: {error}"},
                      level="error", agent=catalog.NAME)
            lines.append(f"The PRD couldn't be moved to prd/done/apps/ ({type(error).__name__}); move it by hand.")
    try:
        backlog.release(app_id=app_id, slug=found.slug if found else None, name=found.name if found else None,
                        prd_path=moved, note=f"Released on {timeutil.today_str()} at {short(sha)} (approval {claimed.id}).")
    except Exception as error:  # noqa: BLE001 - the release is recorded; say what is left to do
        log.event(conn, "apps.backlog.release_failed", {"app_id": app_id, "error": f"{type(error).__name__}: {error}"},
                  level="error", agent=catalog.NAME)
        lines.append(f"The backlog couldn't be updated ({type(error).__name__}); mark {app_id} live in app-backlog.yaml by hand.")
    # The action's own report, as #outreach-sent and the publish run's update are (FD2).
    from jura_growth.agents import apps  # the plug-in imports this module

    discord.post(conn, apps.RUN_UPDATE_DISCORD_CHANNEL, f"**{app_id} released** · {builds.app_name(conn, app_id)} is live at {short(sha)} ({task}).",
                 username="Jura growth · apps", dedupe=False, suppress_embeds=True)
    return Outcome(True, lines, claimed)


def _file_done(found: catalog.PrdFile, row: dict, release: approvals.Approval) -> str:
    """Move the PRD to `prd/done/apps/`: the ship date on top, both approvals on the sign-off
    line. The done copy is written before the pending file goes, so the PRD is never lost."""
    today = timeutil.today_str()
    shipped = (f"*Shipped on {today}: released to jurasolutions.sg from `{row['branch']}` at {short(row['head_sha'])} "
               f"(task {row['task_id']}).*")
    decided = builds.sgt_day(release.decided_at) if release.decided_at else "?"
    signed = (f"Signed off by: Ting Yu in #approvals, build approval {row['approval_id']} ({builds.sgt_day(row['approval_at'])}) "
              f"and release approval {release.id} ({decided})  Date: {today}")
    text = found.path.read_text(encoding="utf-8")
    text, filled = SIGNED_BLANK.subn(lambda _: signed, text, count=1)
    if not filled:
        text = text.rstrip("\n") + f"\n\n{signed}\n"
    target = paths.writable(catalog.done_dir() / found.path.name)
    target.write_text(f"{shipped}\n\n{text}", encoding="utf-8")
    found.path.unlink()
    return catalog.rel(target)


# --- the one-pager -------------------------------------------------------------------------------------


# Fix lines: the action first, and on the first line what fits three rows of the morning picture.
# The picture stops at the first line; the message and the long text carry the rest.
PREVIEW_LINE = "Run `jura-growth apps built {app_id} …` to ask again. {label} is on its preview.\n{request} {why}: {preview}"
MAIN_LINE = "Once main holds {sha}, run `jura-growth apps released {app_id} --task {task}`.\n{label} waits for main: its merge was printed for {request}."
APPROVED_LINE = "Run `jura-growth apps release-plan {app_id}` for the merge. {label} is approved ({request})."
NEVER_PRINTED = "approved, but its merge was never printed"


# What a built app not yet released is waiting for: the one classification behind the one-pager and
# `pending`, so the two can't disagree.
WAITING, APPROVED, CLAIMED, ON_PREVIEW, NO_REQUEST = "waiting", "approved", "claimed", "on its preview", "no request"


@dataclass(frozen=True)
class Unreleased:
    """One built app not yet released. `why` says what left it on its preview. `request` is None
    only for `NO_REQUEST`."""

    state: str
    row: dict
    label: str
    request: approvals.Approval | None
    why: str = ""


def unreleased(conn: sqlite3.Connection) -> list[Unreleased]:
    """Built apps not yet released (MC §5.4, §5.7), oldest build first: left on their preview by a
    skip, an expiry or a lapse; approved and waiting for `release-plan`; claimed and waiting for
    main; with a request still waiting for a decision; or with no live request at all, which
    `apps built` shouldn't leave behind. `conn` may be the read model's read-only connection:
    deadlines are judged against the clock, whether or not the lapse has been written yet (ADR
    0002; code review 10b, S4)."""
    now = timeutil.now_sgt()
    found = []
    for row in db.rows(conn, "SELECT * FROM app_builds WHERE status = 'built' ORDER BY id"):
        app_id = row["app_id"]
        label = f"{app_id} {builds.app_name(conn, app_id)}".strip()
        latest = approvals.latest(conn, KIND, builds.subject(app_id))
        if latest is None or latest.status == approvals.SUPERSEDED:
            found.append(Unreleased(NO_REQUEST, row, label, None))
            continue
        state, why = _reading(latest, now)
        found.append(Unreleased(state, row, label, latest, why))
    return found


def _reading(latest: approvals.Approval, now: datetime) -> tuple[str, str]:
    if latest.status == approvals.PENDING:
        return (WAITING, "") if now < timeutil.parse(latest.decide_by) else (ON_PREVIEW, "expired unanswered")
    if latest.status == approvals.APPROVED and latest.used_at:
        return CLAIMED, ""
    if latest.status == approvals.APPROVED:
        return (APPROVED, "") if latest.use_by is None or now < timeutil.parse(latest.use_by) else (ON_PREVIEW, NEVER_PRINTED)
    if latest.status == approvals.SKIPPED:
        return ON_PREVIEW, "skipped"
    return ON_PREVIEW, NEVER_PRINTED if latest.decided_at else "expired unanswered"


def health_lines(conn: sqlite3.Connection) -> list[str]:
    """The one-pager's lines for `unreleased`. A request still waiting for a decision is already
    in the approvals list, and an app with no live request has no line here."""
    columns = {r[1] for r in conn.execute("PRAGMA table_info(app_builds)")}  # 0004's columns, not just the table
    if "head_sha" not in columns:
        return []
    lines = []
    for app in unreleased(conn):
        if app.request is None:
            continue
        row, app_id, request = app.row, app.row["app_id"], app.request.id
        if app.state == CLAIMED:
            lines.append(MAIN_LINE.format(sha=short(row["head_sha"]), app_id=app_id, task=row["task_id"], label=app.label, request=request))
        elif app.state == APPROVED:
            lines.append(APPROVED_LINE.format(app_id=app_id, label=app.label, request=request))
        elif app.state == ON_PREVIEW:
            lines.append(PREVIEW_LINE.format(app_id=app_id, label=app.label, request=request, why=app.why, preview=row["preview_url"]))
    return lines


# `pending`: the same states, read in Discord, so each says what to send.
PENDING_APPROVED = "{label} is approved ({request}){until}. Send `/growth apps release-plan {app_id}` for the merge."
PENDING_MERGE = ("{label} waits for main: {request} is claimed at {sha}. Run the merge, then send "
                 "`/growth apps released {app_id} --task {task}`. `/growth apps release-plan {app_id}` shows the merge again.")
PENDING_RECORD = "{label} is on main at {sha} ({request}). Send `/growth apps released {app_id} --task {task}` to record it."
ASK_AGAIN = "`/growth apps built {app_id} --task {task} --branch {branch} --sha {sha} --preview {preview}`"
PENDING_PREVIEW = "{label} stays on its preview: {request} {why}. {preview} To ask again, send " + ASK_AGAIN + "."
PENDING_NO_REQUEST = "{label} is built but has no release request on record. To ask for one, send " + ASK_AGAIN + "."
PREVIEWS_SHOWN = 3  # at about 330 characters each, more would push other lines out of a Discord answer


def pending_items(conn: sqlite3.Connection) -> list[PendingItem]:
    """`pending`'s lines for `unreleased`, each holding Ting Yu's next step. A release that can still
    go comes first. What was left on its preview comes after every other next step, newest first and
    capped, because a skipped build stays `built` for good. A request still waiting is in the
    approvals section, so it isn't listed twice. Without 0004's columns this raises, so `pending`
    says what it couldn't read."""
    conn.execute("SELECT head_sha, preview_url, task_id, branch FROM app_builds LIMIT 0")
    apps = unreleased(conn)
    items = [PendingItem(YOU, _pending_text(app)) for app in apps if app.state in (APPROVED, CLAIMED, NO_REQUEST)]
    left = [app for app in reversed(apps) if app.state == ON_PREVIEW]
    items += [PendingItem(YOU, _pending_text(app), order=LISTED) for app in left[:PREVIEWS_SHOWN]]
    more = len(left) - PREVIEWS_SHOWN
    if more > 0:
        stays = "stays on its preview" if more == 1 else "stay on their previews"
        items.append(PendingItem(YOU, f"and {more} more {stays}.", order=LISTED))
    return items


def _pending_text(app: Unreleased) -> str:
    row, request = app.row, app.request
    ask = {"app_id": row["app_id"], "task": row["task_id"], "branch": row["branch"], "sha": row["head_sha"], "preview": row["preview_url"]}
    if request is None:
        return PENDING_NO_REQUEST.format(label=app.label, **ask)
    fields = {"label": app.label, "app_id": row["app_id"], "request": request.id, "task": row["task_id"]}
    if app.state == APPROVED:
        until = f", until {timeutil.when(request.use_by)}" if request.use_by else ""
        return PENDING_APPROVED.format(**fields, until=until)
    if app.state == CLAIMED:
        # Git can't tell before the merge fetches the task branch: its commit isn't here yet.
        line = PENDING_RECORD if on_main(row["head_sha"]) else PENDING_MERGE
        return line.format(**fields, sha=short(row["head_sha"]))
    return PENDING_PREVIEW.format(label=app.label, request=request.id, why=app.why, **ask)


def claimed_release(conn: sqlite3.Connection, app_id: str) -> approvals.Approval | None:
    """The app's latest `app-release` request, when it has been claimed by `release-plan`."""
    latest = approvals.latest(conn, KIND, builds.subject(app_id))
    return latest if latest is not None and latest.used_at else None
