"""The gate-matrix adapter for `app-build` (ticket MC-10), and the kind's own builders.

`app-build` is applied on decide (test strategy v3 §5.2): approving claims the request and writes
the build handoff inside the decision. The gated action `attempt()` runs is that same handoff
writer, `builds.hand_off`, outside a decision, so every refusal case shows the writer can't hand a
build off without an approved, unused request over the PRD's current bytes. `went_out()` counts
the handoffs `attempt()` wrote; the decision's own handoff is traced in `test_app_builds.py`.

`DispatchDouble` stands in for Dispatch (D6): it polls `apps handoffs --json` on its own read-only
connection and records, at call time, whether each handoff's approval is already used (AC-M4.3).
"""

from __future__ import annotations

from jura_growth import approvals, db, mission, paths
from jura_growth.agents.apps import backlog, builds

import approval_world as aw
from test_apps import GOOD

DAY = "2026-10-26"


def prd_text(number: int, *, name: str | None = None, slug: str | None = None, day: str = DAY) -> str:
    """A factory PRD for APP-<number>, built from `test_apps.GOOD` (APP-003)."""
    name = name or f"Delivery order maker {number}"
    slug = slug or f"delivery-order-maker-{number}"
    text = GOOD.replace("APP-003", f"APP-{number:03d}").replace("prd-app-003", f"prd-app-{number:03d}")
    text = text.replace("delivery-order-maker", slug).replace("Delivery order maker", name)
    return text.replace("2026-10-26", day)


def file_prd(number: int, **given) -> str:
    """File a factory PRD in `prd/pending/apps/` and mark the backlog, as `submit-prd` does.
    Returns the app id."""
    day = given.get("day", DAY)
    name = given.get("name") or f"Delivery order maker {number}"
    slug = given.get("slug") or f"delivery-order-maker-{number}"
    folder = paths.prd_dir() / "pending" / "apps"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"prd-app-{number:03d}-{slug}-{day}.md"
    path.write_text(prd_text(number, name=name, slug=slug, day=day), encoding="utf-8")
    app_id = f"APP-{number:03d}"
    backlog.mark_written(name=name, slug=slug, app_id=app_id, prd_path=f"prd/pending/apps/{path.name}", tier="browser",
                         category="Documents", does="Delivery orders with your logo.")
    return app_id


def prd_path(app_id: str):
    found = builds.pending_file(app_id)
    assert found is not None, app_id
    return found.path


class DispatchDouble:
    """Polls the handoffs as Dispatch does, on a read-only connection of its own."""

    def __init__(self):
        self.seen: list[dict] = []

    def poll(self) -> list[dict]:
        fresh = mission.open_read_only(paths.db_path())
        try:
            handoffs = builds.handoffs_json(fresh)["handoffs"]
            for entry in handoffs:
                row = fresh.execute("SELECT used_at FROM approvals WHERE id = ?", (approvals.parse_id(entry["approval"]),)).fetchone()
                self.seen.append({"app_id": entry["app_id"], "used": bool(row and row["used_at"])})
        finally:
            fresh.close()
        return handoffs


class AppBuildAdapter:
    kind = builds.KIND
    agent = "app-factory"
    applied_on_decide = True

    def __init__(self, *, conn, monkeypatch, tmp_path):
        self.conn = conn
        self.number = 100
        self.wrote = 0
        self.dispatch = DispatchDouble()
        monkeypatch.setenv("CONTROL_DISCORD_USER_ID", aw.CONTROL_ID)
        aw.at(monkeypatch, aw.NOW)

    def item(self) -> str:
        self.number += 1
        return builds.subject(file_prd(self.number))

    def twin(self, subject: str) -> str:
        """Another app whose PRD file holds the very same bytes."""
        self.number += 1
        source = prd_path(builds.app_id_of(subject))
        twin = source.with_name(source.name.replace(f"prd-app-{builds.app_id_of(subject)[4:]}", f"prd-app-{self.number:03d}"))
        twin.write_bytes(source.read_bytes())
        return builds.subject(f"APP-{self.number:03d}")

    def raise_request(self, subject: str) -> approvals.Approval:
        with db.transaction(self.conn):
            raised = builds.request(self.conn, builds.app_id_of(subject), reason="the app factory filed it", run_id=None)
        assert raised is not None, subject
        return raised

    def approve(self, approval):
        return aw.approve(self.conn, approval, args={})

    def skip(self, approval):
        return aw.skip(self.conn, approval)

    def attempt(self, subject: str) -> None:
        before = self._handoffs()
        with db.transaction(self.conn):
            try:
                builds.hand_off(self.conn, subject, run_id=aw.run(self.conn))
            except approvals.NotApproved:
                pass
        self.wrote += self._handoffs() - before
        self.dispatch.poll()

    def _handoffs(self) -> int:
        return db.scalar(self.conn, "SELECT count(*) FROM app_builds") or 0

    def went_out(self) -> int:
        return self.wrote

    def seen_at_call(self) -> list[bool]:
        return [seen["used"] for seen in self.dispatch.seen]

    def change(self, subject: str) -> None:
        path = prd_path(builds.app_id_of(subject))
        path.write_bytes(path.read_bytes() + b" ")  # one byte (AC-M9.4)

    def remove(self, subject: str) -> None:
        prd_path(builds.app_id_of(subject)).unlink()

    def switch(self, on: bool) -> None:
        """`app-build` has no switch of its own: Dispatch's polling is `approvals.dispatch_builds`,
        which changes the answer's wording, never whether a handoff is written."""

    def fail_in_flight(self, on: bool) -> None:
        if on:
            self.conn.execute(
                "CREATE TEMP TRIGGER fail_handoff BEFORE INSERT ON app_builds BEGIN SELECT RAISE(ABORT, 'handoff write failed'); END"
            )
        else:
            self.conn.execute("DROP TRIGGER IF EXISTS temp.fail_handoff")

    def hook_ran(self, hook: str, subject: str) -> int:
        event = {"on_skip": "apps.prd.skipped", "on_expire": "apps.prd.expired"}.get(hook)
        if event is None:
            return 0  # an app-build can't lapse: approving claims it
        return len([e for e in aw.events(self.conn, event) if e["subject"] == subject])


ADAPTER = AppBuildAdapter
