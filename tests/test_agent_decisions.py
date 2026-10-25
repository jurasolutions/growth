"""A headless run can't decide (AC-M7.7; gate case G13 layer 3; ticket 04b).

For each configured claude job, the runner starts a fake `claude` binary in place of Claude Code.
It calls `jura-growth approve A-0001` as a real subprocess with the environment the runner gave
it, so the `JURA_GROWTH_JOB` refusal runs for real. The call exits 2 and A-0001 stays pending.
"""

from __future__ import annotations

import pytest

import approval_world as aw
from jura_growth import agents, config, runner
from runner_support import settings_with

CLAUDE_JOBS = sorted(name for name, spec in config.settings()["jobs"].items() if spec["kind"] == "claude")


def test_the_four_claude_jobs_are_all_covered():
    assert {"app-factory", "social", "scout-research", "community"} <= set(CLAUDE_JOBS)


def fake_claude_that_approves(tmp_path, approval_id: str):
    script = tmp_path / "fake-claude-approves"
    script.write_text(
        "#!/bin/sh\n"
        "cat > /dev/null\n"
        f"jura-growth approve {approval_id} > {tmp_path}/approve.out 2>&1\n"
        f"echo $? > {tmp_path}/approve.rc\n"
        f'printf "%s" "$JURA_GROWTH_JOB" > {tmp_path}/job.txt\n'
        "echo '{\"type\": \"result\", \"subtype\": \"success\", \"is_error\": false, \"result\": \"OK: tried to approve\", \"total_cost_usd\": 0.01}'\n"
    )
    script.chmod(0o755)
    return script


@pytest.mark.parametrize("job", CLAUDE_JOBS)
def test_a_claude_job_that_tries_to_approve_is_refused(conn, monkeypatch, tmp_path, job):
    world = aw.install(monkeypatch)
    aw.at(monkeypatch, aw.NOW)
    approval = aw.request(conn, aw.KIND, world.item())
    assert approval.id == "A-0001"
    module = agents.by_name(config.settings()["jobs"][job]["agent"])
    monkeypatch.setattr(module, "precheck", lambda job_name, conn: None)  # every job gets as far as Claude
    settings_with(monkeypatch, binary=str(fake_claude_that_approves(tmp_path, approval.id)))

    runner.run(job, ignore_schedule=True)

    assert (tmp_path / "job.txt").read_text() == job, "the fake claude never ran"
    assert (tmp_path / "approve.rc").read_text().strip() == "2"
    assert "refused:" in (tmp_path / "approve.out").read_text()
    assert aw.record(conn, approval.id)["status"] == "pending"
