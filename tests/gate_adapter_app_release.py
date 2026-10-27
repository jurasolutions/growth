"""The gate-matrix adapter for `app-release` (ticket MC-10b). The contract is in
`test_approval_gates.py`'s docstring.

- An item is an app whose build was handed off (an `app_builds` row, written directly so no
  `app-build` claim is counted) with a commit on its own task branch in the temp landing-page
  repository (D13). `raise_request` reports it with `releases.report_built`, as `apps built` does.
- The gated action is `apps release-plan`; "went out" means a distinct merge command was printed. The
  printer is a double that reads, at call time and on a fresh connection, whether the claim is
  committed (G21).
- The content is the app id, task id, branch and head SHA: `change` moves the build to a newer
  commit on its branch (G9 "release SHA"); `remove` withdraws the build.
- The kind's switch is the landing-page repository itself: without it and its `main`, there is
  nothing to merge into, so the plan refuses before any claim.
- The in-flight marker is `app_builds.release_planned_at`; a temporary trigger makes it fail.
"""

from __future__ import annotations

from jura_growth import approvals, db, paths
from jura_growth.agents.apps import builds, catalog, releases

import approval_world as aw
import site_repo


class AppReleaseAdapter:
    kind = releases.KIND
    agent = "app-factory"
    applied_on_decide = False

    def __init__(self, *, conn, monkeypatch, tmp_path):
        self.conn = conn
        self.monkeypatch = monkeypatch
        self.site = site_repo.make()
        self.nowhere = tmp_path / "no-landing-page"
        self.number = 200
        self.builds: dict[str, dict] = {}
        self.printed: list[dict] = []
        monkeypatch.setenv("CONTROL_DISCORD_USER_ID", aw.CONTROL_ID)
        aw.at(monkeypatch, aw.NOW)
        real = catalog.settings
        monkeypatch.setattr(catalog, "settings", lambda: {**real(), "pages_project": "jura-site"})

    # --- the world ------------------------------------------------------------------------------

    def _hand_off(self) -> str:
        self.number += 1
        app_id = f"APP-{self.number:03d}"
        self.conn.execute(
            "INSERT INTO app_builds (app_id, prd_path, prd_sha256, approval_id, approval_at, handed_off_at) VALUES (?, ?, ?, ?, ?, ?)",
            (app_id, f"prd/pending/apps/prd-app-{self.number:03d}-tool-2026-11-01.md", "ab" * 32, f"A-9{self.number:03d}",
             aw.NOW, aw.NOW),
        )
        task = f"T-{self.number:04d}"
        branch = f"claude/{task}-tool"
        self.builds[app_id] = {
            "task": task, "branch": branch, "sha": site_repo.branch(branch, file=f"{app_id}.txt"),
            "preview": f"https://claude-{task.lower()}-tool.jura-site.pages.dev",
        }
        return app_id

    def _emit(self, line: str) -> None:
        if "git merge" not in line:
            return
        fresh = db.connect(migrate_now=False)
        try:
            row = fresh.execute("SELECT used_at, used_by_run FROM approvals WHERE kind = ? AND used_at IS NOT NULL "
                                "ORDER BY used_at DESC LIMIT 1", (self.kind,)).fetchone()
        finally:
            fresh.close()
        self.printed.append({"line": line, "used": bool(row and row["used_at"] and row["used_by_run"])})

    # --- the contract ----------------------------------------------------------------------------

    def item(self) -> str:
        return builds.subject(self._hand_off())

    def twin(self, subject: str) -> str:
        """Another app built from the very same task, branch and commit, never reported."""
        source = self.builds[builds.app_id_of(subject)]
        twin = self._hand_off()
        self.builds[twin] = dict(source)
        self.conn.execute(
            "UPDATE app_builds SET status = 'built', task_id = ?, branch = ?, head_sha = ?, preview_url = ? WHERE app_id = ?",
            (source["task"], source["branch"], source["sha"], source["preview"], twin),
        )
        return builds.subject(twin)

    def raise_request(self, subject: str) -> approvals.Approval:
        app_id = builds.app_id_of(subject)
        made = self.builds[app_id]
        outcome = releases.report_built(self.conn, app_id, task=made["task"], branch=made["branch"], sha=made["sha"],
                                        preview=made["preview"], run_id=None)
        assert outcome.ok and outcome.approval is not None, outcome.lines
        return outcome.approval

    def approve(self, approval):
        return aw.approve(self.conn, approval, args={})

    def skip(self, approval):
        return aw.skip(self.conn, approval)

    def attempt(self, subject: str) -> None:
        releases.plan_release(self.conn, builds.app_id_of(subject), run_id=aw.run(self.conn), emit=self._emit)

    def went_out(self) -> int:
        """Distinct merges printed. A retry prints the same merge of the same SHA again under the
        same claim (final review Sp3), which releases nothing new, so it isn't a second effect."""
        return len({p["line"] for p in self.printed})

    def seen_at_call(self) -> list[bool]:
        return [p["used"] for p in self.printed]

    def change(self, subject: str) -> None:
        app_id = builds.app_id_of(subject)
        newer = site_repo.commit_on(self.builds[app_id]["branch"], file=f"{app_id}-later.txt")
        self.conn.execute("UPDATE app_builds SET head_sha = ? WHERE app_id = ? AND status = 'built'", (newer, app_id))

    def remove(self, subject: str) -> None:
        self.conn.execute("DELETE FROM app_builds WHERE app_id = ?", (builds.app_id_of(subject),))

    def switch(self, on: bool) -> None:
        self.monkeypatch.setenv("JURA_SITE_REPO", str(self.nowhere if on else self.site))
        assert paths.site_repo() == (self.nowhere if on else self.site)

    def fail_in_flight(self, on: bool) -> None:
        if on:
            self.conn.execute(
                "CREATE TEMP TRIGGER fail_plan BEFORE UPDATE OF release_planned_at ON app_builds "
                "BEGIN SELECT RAISE(ABORT, 'release plan write failed'); END"
            )
        else:
            self.conn.execute("DROP TRIGGER IF EXISTS temp.fail_plan")

    def hook_ran(self, hook: str, subject: str) -> int:
        event = {"on_skip": "apps.release.skipped", "on_expire": "apps.release.expired", "on_lapse": "apps.release.lapsed"}[hook]
        return len([e for e in aw.events(self.conn, event) if e["subject"] == subject])


ADAPTER = AppReleaseAdapter
