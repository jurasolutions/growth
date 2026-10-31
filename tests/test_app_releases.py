"""App releases wait for a second approval, bound to the commit (ticket MC-10b, MC SC9, §5.7
`app-release` row, §5.9 steps 3 and 4; test strategy v3 §4.1 AC-M9.7 to AC-M9.9, §4.3 X2, X3).

A handed-off build is reported with `apps built`, which raises an `app-release` request over the
app id, task id, branch and head commit SHA. `apps release-plan` claims it and prints the merge of
exactly that SHA; `apps released` records the release only once `main` of the landing-page
repository (D13, a temp repo at `paths.site_repo()`) contains it. The gate matrix for the kind runs
through `gate_adapter_app_release.py`.
"""

import json
import re
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

import approval_world as aw
import mission_world as mw
import site_repo
from discord_double import discord_double  # noqa: F401 - the fixture
from sweep import d2_secrets  # noqa: F401 - the fixture
from gate_adapter_app_build import file_prd
from jura_growth import approvals, cards, config, db, mission, one_pager, paths, timeutil
from jura_growth.agents.apps import backlog, builds, catalog, releases
from jura_growth.cli import cli

REAL_PRD = paths.JURA_ROOT / "prd"
TASK = "T-0031"
BRANCH = "claude/T-0031-paynow-qr"
PROJECT = "jura-site"
PREVIEW = "https://claude-t-0031-paynow-qr.jura-site.pages.dev"


def invoke(*args):
    return CliRunner().invoke(cli, list(args), catch_exceptions=False)


@pytest.fixture(autouse=True)
def world(tmp_path, monkeypatch):
    """A private prd/ with the template, the landing-page repository (D13), the clock at
    Tuesday 10 November 10:02 and Ting Yu as the control user."""
    prd = tmp_path / "prd"
    (prd / "templates").mkdir(parents=True)
    (prd / "pending" / "apps").mkdir(parents=True)
    shutil.copy(REAL_PRD / "templates" / "prd-app-template.md", prd / "templates")
    monkeypatch.setenv("JURA_PRD_DIR", str(prd))
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", aw.CONTROL_ID)
    aw.at(monkeypatch, aw.NOW)
    config.reset_caches()
    pages_project(monkeypatch, PROJECT)
    site_repo.make()
    return prd


def pages_project(monkeypatch, name):
    """`pages_project` in config/apps.yaml: the landing page's Cloudflare Pages project."""
    real = catalog.settings
    monkeypatch.setattr(catalog, "settings", lambda: {**real(), "pages_project": name})


def handed_off(conn, number: int = 101) -> tuple[str, approvals.Approval]:
    """An approved, handed-off build: a factory PRD, its app-build request, approved."""
    app_id = file_prd(number)
    with db.transaction(conn):
        request = builds.request(conn, app_id, reason="the app factory filed it", run_id=None)
    assert aw.approve(conn, request, args={}).answer == "recorded"
    return app_id, aw.get(conn, request.id)


def built(app_id: str, sha: str, *, task: str = TASK, branch: str = BRANCH, preview: str = PREVIEW):
    return invoke("apps", "built", app_id, "--task", task, "--branch", branch, "--sha", sha, "--preview", preview)


def release_requests(conn) -> list[approvals.Approval]:
    return [aw.get(conn, approvals.format_id(r["id"])) for r in conn.execute(
        "SELECT id FROM approvals WHERE kind = 'app-release' ORDER BY id")]


# --- AC-M9.7: `apps built` raises the release request --------------------------------------------


def test_built_raises_an_app_release_card_with_the_preview_link_and_the_short_sha(conn, discord_double):
    app_id, _ = handed_off(conn)
    sha = site_repo.branch(BRANCH)
    result = built(app_id, sha)
    assert result.exit_code == 0, result.output
    [request] = release_requests(conn)
    assert request.status == "pending" and request.subject == f"app:{app_id}"
    assert result.output.count(request.id) == 1
    [card] = discord_double.posts("approvals")[-1:]
    first, *rest = card.content.splitlines()
    assert first.startswith(f"**{request.id} · app release** · decide by ")
    body = "\n".join(rest)
    assert PREVIEW in body and sha[:7] in body and sha not in body
    assert BRANCH in body and TASK in body


def test_built_on_a_build_that_was_never_handed_off_exits_1_and_raises_nothing(conn, discord_double):
    app_id = file_prd(101)  # filed, never approved
    result = built(app_id, site_repo.branch(BRANCH))
    assert result.exit_code == 1
    assert "handed off" in result.output
    assert release_requests(conn) == []
    assert discord_double.posts("approvals") == []


def test_built_moves_the_handoff_off_the_list_waiting_for_a_builder(conn):
    app_id, _ = handed_off(conn)
    assert [b["app_id"] for b in builds.open_handoffs(conn)] == [app_id]
    assert built(app_id, site_repo.branch(BRANCH)).exit_code == 0
    assert builds.open_handoffs(conn) == []


@pytest.mark.parametrize(
    "field, value",
    [
        ("sha", "1a2b3c4"),  # short: the request binds the full commit
        ("sha", "z" * 40),
        ("task", "0031"),
        ("branch", "claude/T-0031 paynow; rm -rf ~"),
        ("branch", "-delete"),
        ("preview", "http://claude-t-0031.jura-site.pages.dev"),
        ("preview", "https://jurasolutions.sg/apps/paynow-qr"),
        ("preview", "https://evil.example/?x=.pages.dev"),
        # code review 10b, B1: a masked link, or anything else Discord would render as Markdown
        ("preview", "https://x.jura-site.pages.dev/ [open the preview](https://evil.example/login)"),
        ("preview", "https://x.jura-site.pages.dev/[a](https://evil.example)"),
        ("preview", "https://x.jura-site.pages.dev/apps/<b>"),
        ("preview", "https://x.jura-site.pages.dev/apps/`x`"),
        ("preview", "https://x.jura-site.pages.dev/apps/_x_"),
        ("preview", "https://x.jura-site.pages.dev/apps/x?y=1"),
        ("preview", "https://x.jura-site.pages.dev/apps/x#y"),
        ("preview", " https://x.jura-site.pages.dev"),
        ("preview", "https://x.jura-site.pages.dev\nhttps://evil.example"),
        ("preview", "https://X.jura-site.pages.dev"),
        # S1: only the landing page's own project, and only a preview of it
        ("preview", "https://not-jura.pages.dev"),
        ("preview", "https://x.not-jura.pages.dev"),
        ("preview", "https://x.jura-site-not.pages.dev"),
        ("preview", "https://jura-site.pages.dev"),  # production, not a preview
        ("preview", "https://a.b.jura-site.pages.dev"),
    ],
)
def test_built_refuses_what_it_cannot_bind_or_show_safely(conn, field, value):
    app_id, _ = handed_off(conn)
    given = {"sha": site_repo.branch(BRANCH), "task": TASK, "branch": BRANCH, "preview": PREVIEW, field: value}
    result = built(app_id, given["sha"], task=given["task"], branch=given["branch"], preview=given["preview"])
    assert result.exit_code == 1, result.output
    assert release_requests(conn) == []
    assert [b["app_id"] for b in builds.open_handoffs(conn)] == [app_id]  # still waiting for its build


def test_the_card_shows_the_preview_as_plain_text_and_says_it_follows_the_branch(conn, discord_double):
    """Code review 10b, B1 and N2."""
    app_id, _ = handed_off(conn)
    sha = site_repo.branch(BRANCH)
    preview = f"{PREVIEW}/apps/paynow-qr/"
    assert built(app_id, sha, preview=preview).exit_code == 0
    [card] = [p for p in discord_double.posts("approvals") if "· app release**" in (p.content or "")]
    lines = card.content.splitlines()
    assert f"Preview: {preview}" in lines
    assert any(f"the release is commit {sha[:7]}" in line and "latest push" in line for line in lines)


def test_the_shipped_config_pins_the_landing_page_pages_project_and_turns_dispatch_builds_on():
    """The landing page's Cloudflare Pages project is `landing-page`; Dispatch still doesn't poll
    build handoffs until Ting Yu turns it on."""
    import yaml

    from jura_growth import approval_settings, paths

    shipped = yaml.safe_load((paths.config_dir() / "apps.yaml").read_text(encoding="utf-8"))
    assert shipped["pages_project"] == "landing-page-eq7"  # the pages.dev name, not the project name
    assert releases.PROJECT_RE.fullmatch(shipped["pages_project"])
    assert releases.preview_pattern("landing-page-eq7").fullmatch("https://claude-t-0031-x.landing-page-eq7.pages.dev")
    assert approval_settings.switch("dispatch_builds") is True


def test_without_the_pages_project_set_no_preview_is_accepted(conn, monkeypatch):
    """S1: the project comes from config/apps.yaml; unset, `apps built` refuses and says what to set."""
    pages_project(monkeypatch, None)
    app_id, _ = handed_off(conn)
    result = built(app_id, site_repo.branch(BRANCH))
    assert result.exit_code == 1 and "pages_project" in result.output
    assert release_requests(conn) == []


def test_a_new_preview_after_the_approval_supersedes_it(conn):
    """S2: the preview link is part of what Ting Yu approved, so it can't be swapped afterwards."""
    app_id, sha, request = approved_release(conn)
    other = "https://claude-t-0031-paynow-qr-v2.jura-site.pages.dev"
    result = built(app_id, sha, preview=other)
    assert result.exit_code == 0
    old, new = release_requests(conn)
    assert old.status == "superseded" and new.status == "pending" and new.supersedes == old.number
    assert invoke("apps", "release-plan", app_id).exit_code == 1


def test_built_refuses_a_commit_main_already_contains(conn):
    """N1: there is nothing to release, so no request is raised."""
    app_id, _ = handed_off(conn)
    result = built(app_id, site_repo.main_head())
    assert result.exit_code == 1 and "main already contains" in result.output
    assert release_requests(conn) == []


def test_built_again_with_the_same_commit_keeps_the_one_request(conn, discord_double):
    app_id, _ = handed_off(conn)
    sha = site_repo.branch(BRANCH)
    assert built(app_id, sha).exit_code == 0
    again = built(app_id, sha)
    assert again.exit_code == 0
    [request] = release_requests(conn)
    assert request.id in again.output
    assert len([p for p in discord_double.posts("approvals") if "· app release**" in (p.content or "")]) == 1


def test_built_with_a_new_commit_supersedes_the_request_and_raises_one_for_the_new_sha(conn):
    """N5: the request covers the commit, so commits pushed after it need a request of their own."""
    app_id, _ = handed_off(conn)
    first = site_repo.branch(BRANCH)
    assert built(app_id, first).exit_code == 0
    later = site_repo.commit_on(BRANCH)
    assert built(app_id, later).exit_code == 0
    old, new = release_requests(conn)
    assert old.status == "superseded" and new.status == "pending" and new.supersedes == old.number
    assert releases.current_build(conn, app_id)["head_sha"] == later


# --- Final review St1: the hash covers the exact bytes (ADR 0003 as amended) ------------------------


def test_the_release_content_is_the_exact_bytes_with_no_unicode_normalisation():
    row = {"app_id": "APP-014", "branch": "claude/T-0031-café", "preview_url": "https://x.jura-site.pages.dev",
           "head_sha": "a" * 40, "task_id": "T-0031"}
    composed = {**row, "branch": "claude/T-0031-café"}
    assert releases.encode(row) != releases.encode(composed)
    fields = {"app_id": "APP-014", "branch": row["branch"], "preview": row["preview_url"], "sha": row["head_sha"],
              "task_id": "T-0031"}
    assert releases.encode(row) == json.dumps(fields, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


# --- AC-M9.8: `apps release-plan` claims, then prints the merge of exactly that commit ---------------


def approved_release(conn) -> tuple[str, str, approvals.Approval]:
    app_id, _ = handed_off(conn)
    sha = site_repo.branch(BRANCH)
    assert built(app_id, sha).exit_code == 0
    [request] = release_requests(conn)
    assert aw.approve(conn, request, args={}).answer == "recorded"
    return app_id, sha, aw.get(conn, request.id)


HEX40 = re.compile(r"\b[0-9a-f]{40}\b")


def test_release_plan_claims_the_approval_and_prints_the_merge_of_the_approved_sha_only(conn):
    app_id, sha, request = approved_release(conn)
    later = site_repo.commit_on(BRANCH)  # pushed after the approval: never part of the plan
    result = invoke("apps", "release-plan", app_id)
    assert result.exit_code == 0, result.output
    assert aw.get(conn, request.id).used_at  # claimed
    merges = [line.strip() for line in result.output.splitlines() if "git merge" in line]
    assert merges == [f'git merge --no-ff -m "Release {app_id} (approval {request.id})" {sha}']
    assert set(HEX40.findall(result.output)) == {sha} and later not in result.output
    assert f"jura-growth apps released {app_id} --task {TASK}" in result.output
    assert str(paths.site_repo()) in result.output
    assert releases.current_build(conn, app_id)["release_planned_at"]


def test_release_plan_with_no_approved_release_exits_1_and_prints_nothing_to_run(conn):
    app_id, _ = handed_off(conn)
    assert built(app_id, site_repo.branch(BRANCH)).exit_code == 0  # pending, not approved
    for target in (app_id, "APP-999"):
        result = invoke("apps", "release-plan", target)
        assert result.exit_code == 1
        assert "git " not in result.output and "refused" in result.output
    assert aw.claims(conn) == 1  # only the app-build handoff's claim


def test_release_plan_a_second_time_prints_the_same_merge_without_a_new_claim(conn):
    """Final review Sp3: a lost answer can be fetched again. The retry isn't a second use (A6,
    ADR 0003): the merge names a fixed SHA, so printing it again releases nothing new."""
    app_id, sha, request = approved_release(conn)
    first = invoke("apps", "release-plan", app_id)
    assert first.exit_code == 0
    used = aw.get(conn, request.id)
    planned = releases.current_build(conn, app_id)["release_planned_at"]
    claimed_events = aw.claims(conn)

    again = invoke("apps", "release-plan", app_id)

    assert again.exit_code == 0 and again.output == first.output
    assert aw.get(conn, request.id) == used  # no new claim: the same use, the same run
    assert releases.current_build(conn, app_id)["release_planned_at"] == planned
    assert aw.claims(conn) == claimed_events


def test_release_plan_after_its_claim_refuses_once_the_build_no_longer_hashes_to_it(conn):
    """The re-print is only for the build the claim covers: a newer commit reported after the
    claim gets a new request, and no merge until that one is approved."""
    app_id, sha, request = approved_release(conn)
    assert invoke("apps", "release-plan", app_id).exit_code == 0
    newer = site_repo.commit_on(BRANCH)
    assert built(app_id, newer).exit_code == 0

    again = invoke("apps", "release-plan", app_id)

    assert again.exit_code == 1 and "git merge" not in again.output
    assert sha not in again.output and newer not in again.output


def test_release_plan_refuses_a_release_whose_branch_moved_on_after_the_approval(conn):
    """G9 through the command: a newer commit reported for the build supersedes the approval."""
    app_id, _, request = approved_release(conn)
    assert built(app_id, site_repo.commit_on(BRANCH)).exit_code == 0
    result = invoke("apps", "release-plan", app_id)
    assert result.exit_code == 1 and "git merge" not in result.output
    assert aw.get(conn, request.id).status == "superseded"


# --- AC-M9.9: `apps released` checks main, then records the release ----------------------------------


def pending_prd(app_id: str):
    found = builds.pending_file(app_id)
    return found.path if found else None


def done_prds():
    folder = catalog.done_dir()
    return sorted(folder.glob("prd-app-*.md")) if folder.is_dir() else []


def test_released_with_no_claimed_release_exits_1_and_the_prd_stays_in_pending(conn):
    app_id, _ = handed_off(conn)
    assert invoke("apps", "released", app_id, "--task", TASK).exit_code == 1  # not even built
    sha = site_repo.branch(BRANCH)
    assert built(app_id, sha).exit_code == 0
    [request] = release_requests(conn)
    site_repo.merge(sha)  # merged by hand with no approval: still not a release
    assert invoke("apps", "released", app_id, "--task", TASK).exit_code == 1  # pending
    aw.approve(conn, request, args={})
    result = invoke("apps", "released", app_id, "--task", TASK)  # approved, never claimed by release-plan
    assert result.exit_code == 1 and "release-plan" in result.output
    assert pending_prd(app_id) is not None and done_prds() == []
    assert releases.current_build(conn, app_id)["status"] == "built"


def test_released_when_main_lacks_the_approved_sha_exits_1_and_the_prd_stays_in_pending(conn):
    app_id, sha, _ = approved_release(conn)
    assert invoke("apps", "release-plan", app_id).exit_code == 0
    later = site_repo.commit_on(BRANCH)
    site_repo.merge(later)  # main has the branch's newer head, but not via the approved merge...
    site_repo.git(paths.site_repo(), "reset", "-q", "--hard", "HEAD~1")  # ...undone: main has neither
    result = invoke("apps", "released", app_id, "--task", TASK)
    assert result.exit_code == 1 and sha[:7] in result.output
    assert pending_prd(app_id) is not None and done_prds() == []
    assert releases.current_build(conn, app_id)["status"] == "built"


def test_released_refuses_another_task(conn):
    app_id, sha, _ = approved_release(conn)
    assert invoke("apps", "release-plan", app_id).exit_code == 0
    site_repo.merge(sha)
    assert invoke("apps", "released", app_id, "--task", "T-0099").exit_code == 1
    assert pending_prd(app_id) is not None


def test_released_records_the_release_and_moves_the_prd_to_done_with_both_approvals(conn, monkeypatch):
    app_id, build_approval = handed_off(conn)
    sha = site_repo.branch(BRANCH)
    assert built(app_id, sha).exit_code == 0
    [release] = release_requests(conn)
    aw.at(monkeypatch, "2026-11-12T09:30:00+08:00")
    aw.approve(conn, release, args={})
    assert invoke("apps", "release-plan", app_id).exit_code == 0
    site_repo.merge(sha)
    aw.at(monkeypatch, "2026-11-13T11:00:00+08:00")
    source = pending_prd(app_id)
    original = source.read_text()
    result = invoke("apps", "released", app_id, "--task", TASK)
    assert result.exit_code == 0, result.output
    row = db.one(conn, "SELECT * FROM app_builds WHERE app_id = ?", (app_id,))
    assert row["status"] == "released" and row["released_at"].startswith("2026-11-13T11:00")
    assert pending_prd(app_id) is None and not source.exists()
    [done] = done_prds()
    assert done.name == source.name
    text = done.read_text()
    assert text.splitlines()[0] == (f"*Shipped on 2026-11-13: released to jurasolutions.sg from `{BRANCH}` at {sha[:7]} "
                                    f"(task {TASK}).*")
    signed = (f"Signed off by: Ting Yu in #approvals, build approval {build_approval.id} (2026-11-10) and "
              f"release approval {release.id} (2026-11-12)  Date: 2026-11-13")
    assert signed in text.splitlines()
    assert "Signed off by: ____" not in text
    assert text.replace(signed, "Signed off by: ________________  Date: ____________").split("\n", 2)[2] == original
    [row] = [r for r in backlog.load() if r.get("app_id") == app_id]
    assert row["status"] == "live" and row["prd"] == f"prd/done/apps/{done.name}"
    assert [f.state for f in catalog.prd_files() if f.app_id == app_id] == ["done"]
    again = invoke("apps", "released", app_id, "--task", TASK)
    assert again.exit_code == 0 and "already" in again.output
    assert invoke("apps", "built", app_id, "--task", TASK, "--branch", BRANCH, "--sha", sha, "--preview", PREVIEW).exit_code == 1


def test_a_tag_named_main_does_not_stand_in_for_the_main_branch(conn):
    """S3: `released` checks refs/heads/main, so a tag `main` holding the commit counts for nothing."""
    app_id, sha, _ = approved_release(conn)
    assert invoke("apps", "release-plan", app_id).exit_code == 0
    site_repo.git(paths.site_repo(), "tag", "main", sha)
    result = invoke("apps", "released", app_id, "--task", TASK)
    assert result.exit_code == 1 and pending_prd(app_id) is not None


def test_released_updates_the_backlog_even_when_the_prd_is_not_in_pending(conn):
    """S6: §5.9 step 4 updates the backlog whether or not the PRD file is there to move."""
    app_id, sha, _ = approved_release(conn)
    assert invoke("apps", "release-plan", app_id).exit_code == 0
    site_repo.merge(sha)
    pending_prd(app_id).unlink()
    result = invoke("apps", "released", app_id, "--task", TASK)
    assert result.exit_code == 0 and "isn't in prd/pending/apps/" in result.output
    [row] = [r for r in backlog.load() if r.get("app_id") == app_id]
    assert row["status"] == "live"


def test_a_failed_backlog_write_is_reported_as_that_not_as_a_failed_move(conn, monkeypatch):
    """S7: the PRD has moved; only the backlog is left to do by hand."""
    app_id, sha, _ = approved_release(conn)
    assert invoke("apps", "release-plan", app_id).exit_code == 0
    site_repo.merge(sha)

    def refuse(**_):
        raise OSError("disk full")

    monkeypatch.setattr(backlog, "release", refuse)
    result = invoke("apps", "released", app_id, "--task", TASK)
    assert result.exit_code == 0
    assert "PRD moved to prd/done/apps/" in result.output and "couldn't be moved" not in result.output
    assert "backlog couldn't be updated" in result.output
    assert len(done_prds()) == 1 and pending_prd(app_id) is None
    assert [e["app_id"] for e in aw.events(conn, "apps.backlog.release_failed")] == [app_id]
    assert aw.events(conn, "apps.prd.done_move_failed") == []


def test_released_only_reads_the_temp_landing_page_repository(conn, tmp_path, monkeypatch):
    """The write guard doesn't cover subprocesses, so the test checks every git call: each runs
    against the repository under tmp_path, and none fetches, pulls, merges, pushes or writes."""
    app_id, sha, _ = approved_release(conn)
    assert invoke("apps", "release-plan", app_id).exit_code == 0
    site_repo.merge(sha)
    calls = []
    real = releases.subprocess.run

    def spy(args, **kwargs):
        calls.append(list(args))
        return real(args, **kwargs)

    monkeypatch.setattr(releases.subprocess, "run", spy)
    assert invoke("apps", "released", app_id, "--task", TASK).exit_code == 0
    assert calls
    for call in calls:
        assert call[:2] == ["git", "-C"]
        assert Path(call[2]).resolve().is_relative_to(tmp_path.resolve())
        assert call[3] in ("merge-base", "rev-parse")
    assert ["git", "-C", str(paths.site_repo()), "merge-base", "--is-ancestor", sha, "refs/heads/main"] in calls


# --- skip, expiry and lapse leave it on its preview, listed in the one-pager (MC §5.7) ---------------


def one_pager_lines(app_id: str, now: str) -> list[str]:
    snapshot = mission.read(mw.source(now=now))
    found = [line for line in snapshot.plugin_lines if app_id in line and "Build handoff" not in line]
    assert all(line in one_pager.text(snapshot) for line in found)
    return found


@pytest.mark.parametrize("ending", ["skipped", "expired", "lapsed"])
def test_a_release_not_taken_stays_on_its_preview_and_the_one_pager_lists_it(conn, monkeypatch, ending):
    app_id, _ = handed_off(conn)
    sha = site_repo.branch(BRANCH)
    assert built(app_id, sha).exit_code == 0
    [request] = release_requests(conn)
    if ending == "skipped":
        assert aw.skip(conn, request).answer == "recorded"
        now = aw.NOW
    elif ending == "expired":
        now = request.decide_by
        approvals.expire_due(conn, timeutil.parse(now))
    else:
        aw.approve(conn, request, args={})
        now = aw.get(conn, request.id).use_by
        approvals.expire_due(conn, timeutil.parse(now))
    assert aw.get(conn, request.id).status == ("skipped" if ending == "skipped" else "expired")
    assert len([e for e in aw.events(conn, f"apps.release.{ending}") if e["subject"] == request.subject]) == 1
    row = releases.current_build(conn, app_id)
    assert row["status"] == "built" and row["head_sha"] == sha  # still on its preview
    assert pending_prd(app_id) is not None and site_repo.main_head() != sha
    [line] = one_pager_lines(app_id, now)
    assert line.startswith(f"App on its preview: {app_id} ") and PREVIEW in line and request.id in line
    assert {"skipped": "skipped", "expired": "expired unanswered", "lapsed": "approved, but its merge was never printed"}[ending] in line
    assert f"jura-growth apps built {app_id}" in line  # how to ask again
    again = built(app_id, sha)
    assert again.exit_code == 0
    assert [r.status for r in release_requests(conn)][-1] == "pending"


def test_the_one_pager_says_what_an_approved_or_claimed_release_waits_for(conn):
    app_id, sha, request = approved_release(conn)
    [line] = one_pager_lines(app_id, aw.NOW)
    assert line.startswith(f"App release approved: {app_id} ") and f"jura-growth apps release-plan {app_id}" in line
    assert invoke("apps", "release-plan", app_id).exit_code == 0
    [line] = one_pager_lines(app_id, aw.NOW)
    assert line.startswith(f"App release waiting for main: {app_id} ") and sha[:7] in line
    assert f"jura-growth apps released {app_id} --task {TASK}" in line
    site_repo.merge(sha)
    assert invoke("apps", "released", app_id, "--task", TASK).exit_code == 0
    assert one_pager_lines(app_id, aw.NOW) == []


def test_the_one_pager_judges_deadlines_by_the_clock_before_the_lapse_is_written(conn, monkeypatch):
    """S4 (ADR 0002): an approval past its use-by, or a request past its decide-by, reads as lapsed
    even before `expire_due` writes it, so the one-pager never points at a command that refuses."""
    app_id, _, request = approved_release(conn)
    use_by = aw.get(conn, request.id).use_by
    aw.at(monkeypatch, aw.later(use_by, seconds=-1))
    [line] = one_pager_lines(app_id, aw.later(use_by, seconds=-1))
    assert line.startswith("App release approved:")
    aw.at(monkeypatch, use_by)
    [line] = one_pager_lines(app_id, use_by)
    assert line.startswith("App on its preview:") and "approved, but its merge was never printed" in line
    assert aw.get(conn, request.id).status == "approved"  # nothing was written

    other, _ = handed_off(conn, 102)
    assert built(other, site_repo.branch("claude/T-0032-other", file="other.txt"), task="T-0032",
                 branch="claude/T-0032-other", preview="https://claude-t-0032-other.jura-site.pages.dev").exit_code == 0
    pending = release_requests(conn)[-1]
    assert one_pager_lines(other, use_by) == []  # still waiting: the approvals list has it
    aw.at(monkeypatch, pending.decide_by)
    [line] = one_pager_lines(other, pending.decide_by)
    assert line.startswith("App on its preview:") and "expired unanswered" in line


# --- AC-M4.7 and the sweep ------------------------------------------------------------------------------


def test_without_the_apps_plugin_no_release_is_planned_or_expired(conn, monkeypatch):
    """AC-M4.7 for app-release: a kind whose plug-in failed to load fails closed."""
    from jura_growth import agents

    app_id, _ = handed_off(conn)
    assert built(app_id, site_repo.branch(BRANCH)).exit_code == 0
    [request] = release_requests(conn)
    real = agents.plugins()
    monkeypatch.setattr(agents, "plugins", lambda: tuple(m for m in real if getattr(m, "NAME", "") != "app-factory"))
    outcome = releases.plan_release(conn, app_id, run_id=None, emit=pytest.fail)
    assert not outcome.ok and "no loaded plug-in" in outcome.lines[0]
    assert approvals.expire_due(conn, timeutil.parse(aw.later(request.decide_by, days=1))) == []
    assert aw.get(conn, request.id).status == "pending"


def test_an_app_release_card_and_its_edits_carry_nothing_planted(conn, discord_double, d2_secrets):
    """AC-M11.1 and AC-M12.1 over this ticket's messages: the release card, and its first line
    edited when approved and when claimed."""
    from sweep import AWKWARD, KEYCHAIN_VALUE, MARKER, NAMED_ADDRESS, PHONE, RESEND_KEY, SOURCE_PAGE, assert_clean, outbox_dir, planted

    conn.execute(
        "INSERT INTO leads (id, company, display_name, domain, website, industry, score, score_reasons, channel,"
        " status, created_at, updated_at) VALUES (233, 'Example Pte Ltd', 'Example', 'example.com.sg',"
        " 'https://example.com.sg', 'logistics', 78, '[]', 'email', 'new', ?, ?)",
        (timeutil.stamp(), timeutil.stamp()),
    )
    conn.execute(
        "INSERT INTO contacts (lead_id, email, email_hash, source_url, kind, mx_ok, verified_at, created_at)"
        " VALUES (233, ?, 'h', ?, 'named', 1, ?, ?)",
        (NAMED_ADDRESS, SOURCE_PAGE, timeutil.stamp(), timeutil.stamp()),
    )
    name = f"Order maker {MARKER} for Jane Tan at {NAMED_ADDRESS} or {PHONE} key {RESEND_KEY} {KEYCHAIN_VALUE} {AWKWARD}"
    app_id = file_prd(101, name=name, slug="order-maker")
    with db.transaction(conn):
        build_request = builds.request(conn, app_id, reason="the app factory filed it", run_id=None)
    aw.approve(conn, build_request, args={})
    sha = site_repo.branch(BRANCH)
    assert built(app_id, sha).exit_code == 0
    [request] = release_requests(conn)
    aw.approve(conn, request, args={})
    cards.sweep(conn)
    assert invoke("apps", "release-plan", app_id).exit_code == 0
    release_cards = [p for p in discord_double.posts("approvals") if "· app release**" in (p.content or "")]
    assert len(release_cards) == 1 and PREVIEW in release_cards[0].content
    assert [r.method for r in discord_double.requests].count("PATCH") == 2  # approved, then claimed
    assert_clean(discord_double, outbox_dir(), planted())


# --- X2 and X3: seven days to decide, fourteen to use ----------------------------------------------


@pytest.fixture
def zone(monkeypatch):
    import os
    import time

    before = os.environ.get("TZ")

    def set_zone(name: str) -> None:
        monkeypatch.setenv("TZ", name)
        time.tzset()

    yield set_zone
    if before is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = before
    time.tzset()


@pytest.mark.parametrize("name", ["Asia/Singapore", "UTC", "America/New_York"])
def test_an_app_release_has_seven_days_to_decide_and_fourteen_to_use(conn, monkeypatch, zone, name):
    """X2: whatever the machine's time zone."""
    zone(name)
    app_id, _ = handed_off(conn)
    assert built(app_id, site_repo.branch(BRANCH)).exit_code == 0
    [request] = release_requests(conn)
    assert request.decide_by == aw.later(aw.NOW, days=7) == "2026-11-17T10:02:15+08:00"
    aw.at(monkeypatch, "2026-11-12T09:00:00+08:00")
    assert aw.approve(conn, request, args={}).answer == "recorded"
    assert aw.get(conn, request.id).use_by == "2026-11-26T09:00:00+08:00"


def test_a_configured_app_release_deadline_may_shorten_and_never_lengthen(conn, monkeypatch):
    """X3 for this kind: the deadlines come from the `approvals:` block, capped by caps.py."""
    patched = dict(config.settings())
    patched["approvals"] = {"deadlines": {"app-release": {"decide_by_days": 3, "use_by_days": 30}}}
    monkeypatch.setattr(config, "settings", lambda: patched)
    app_id, _ = handed_off(conn)
    assert built(app_id, site_repo.branch(BRANCH)).exit_code == 0
    [request] = release_requests(conn)
    assert request.decide_by == aw.later(aw.NOW, days=3)
    aw.approve(conn, request, args={})
    assert aw.get(conn, request.id).use_by == aw.later(aw.NOW, days=14)  # 30 reads as the cap, 14


# --- the migration ----------------------------------------------------------------------------------


def test_the_release_migration_changes_no_existing_handoff(tmp_path, monkeypatch):
    """X7-style: a database at ticket 10's schema, with a handoff waiting, migrates through 0004
    with the row as it was; the new columns start empty."""
    from jura_growth.agents import apps as apps_plugin

    old = tmp_path / "apps-at-10"
    old.mkdir()
    for name in ("0001_app_factory.sql", "0002_app_builds.sql", "0003_app_prds_slug_reusable.sql"):
        shutil.copy(apps_plugin.MIGRATIONS / name, old / name)
    with monkeypatch.context() as patch:
        patch.setattr(apps_plugin, "MIGRATIONS", old)
        conn = db.connect(tmp_path / "old.db")
    conn.execute(
        "INSERT INTO app_builds (app_id, prd_path, prd_sha256, approval_id, approval_at, handed_off_at) "
        "VALUES ('APP-003', 'prd/pending/apps/x.md', ?, 'A-0007', ?, ?)",
        ("ab" * 32, aw.NOW, aw.NOW),
    )
    before = db.rows(conn, "SELECT * FROM app_builds")
    assert db.migrate(conn) == ["app-factory/0004_app_builds_release.sql"]
    after = db.rows(conn, "SELECT * FROM app_builds")
    assert [{k: row[k] for k in before[0]} for row in after] == before
    added = set(after[0]) - set(before[0])
    assert added == {"task_id", "branch", "head_sha", "preview_url", "built_at", "release_planned_at", "released_at"}
    assert all(after[0][k] is None for k in added)
    conn.close()


def test_one_unreleased_build_per_app(conn):
    app_id, _ = handed_off(conn)
    assert built(app_id, site_repo.branch(BRANCH)).exit_code == 0
    with pytest.raises(Exception, match="UNIQUE"):
        conn.execute(
            "INSERT INTO app_builds (app_id, prd_path, prd_sha256, approval_id, approval_at, handed_off_at) "
            "VALUES (?, 'x', 'y', 'A-9999', ?, ?)",
            (app_id, aw.NOW, aw.NOW),
        )


# --- what the feed hears (functional S3) ---------------------------------------------------------


def test_an_approved_release_names_its_next_step_and_the_claim_stays_silent(conn, discord_double):
    app_id, _ = handed_off(conn)
    sha = site_repo.branch(BRANCH)
    assert built(app_id, sha).exit_code == 0
    [request] = release_requests(conn)
    aw.approve(conn, request, args={})
    cards.sweep(conn)
    [line] = [m for m in discord_double.contents("app-factory") if request.id in m]
    assert f"`/growth apps release-plan {app_id}`" in line and line.startswith(f"**{request.id} approved**")
    assert invoke("apps", "release-plan", app_id).exit_code == 0
    cards.sweep(conn)
    assert len([m for m in discord_double.contents("app-factory") if request.id in m]) == 1


def test_a_recorded_release_posts_one_released_line(conn, discord_double):
    app_id, sha, _ = approved_release(conn)
    assert invoke("apps", "release-plan", app_id).exit_code == 0
    site_repo.merge(sha)
    before = len(discord_double.contents("app-factory"))
    assert invoke("apps", "released", app_id, "--task", TASK).exit_code == 0
    [line] = discord_double.contents("app-factory")[before:]
    assert line.startswith(f"**{app_id} released**") and sha[:7] in line and TASK in line
    assert invoke("apps", "released", app_id, "--task", TASK).exit_code == 0  # already recorded
    assert len(discord_double.contents("app-factory")) == before + 1
