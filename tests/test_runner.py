"""The runner's traces and call sites (MC-01): the quiet-run trace, a
`NothingToDo` precheck, a quiet claude job's run id, the plug-in `after_run`
hook and the core run-update notification.

Every run happens in process on real or fake jobs in a patched config, as in
`tests/test_core.py`. Nothing here calls `jura-growth run`.
"""

import json
from types import SimpleNamespace

import pytest

from jura_growth import agents, config, db, paths, runner

from test_scout_support import MONDAY_10AM, at, outbox, scout_env, seed  # noqa: F401


def events(conn, kind):
    return [json.loads(row["payload_json"]) for row in conn.execute("SELECT payload_json FROM events WHERE kind = ? ORDER BY id", (kind,))]


def mirrored(kind):
    folder = paths.data_dir() / "runs"
    found = []
    for path in sorted(folder.glob("*.jsonl")) if folder.exists() else []:
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if record["kind"] == kind:
                found.append(record["payload"])
    return found


def run_rows(conn):
    return [dict(row) for row in conn.execute("SELECT * FROM runs ORDER BY id")]


# --- X1: the quiet-run trace -------------------------------------------------


def test_a_quiet_job_with_nothing_to_do_writes_one_run_quiet_and_no_run_row(monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    outcome = runner.run("scout-send")
    assert outcome.status == "ok"
    with db.session() as conn:
        assert run_rows(conn) == []
        assert events(conn, "run.quiet") == [{"job": "scout-send", "started_at": "2026-10-26T10:00:00+08:00"}]
    assert mirrored("run.quiet") == [{"job": "scout-send", "started_at": "2026-10-26T10:00:00+08:00"}]


def test_a_quiet_run_that_did_work_records_its_real_start(monkeypatch):
    from jura_growth.agents.outreach import send

    at(monkeypatch, MONDAY_10AM)
    with db.session() as conn:
        seed(conn, 1)
    real = send.send_due

    def slow_send(conn, **kwargs):
        result = real(conn, **kwargs)
        monkeypatch.setenv("JURA_GROWTH_NOW", "2026-10-26T10:04:30+08:00")  # the send took four and a half minutes
        return result

    monkeypatch.setattr(send, "send_due", slow_send)
    outcome = runner.run("scout-send")
    assert outcome.status == "ok" and outcome.summary.startswith("SHADOW message 1")
    with db.session() as conn:
        [row] = run_rows(conn)
        assert row["started_at"] == "2026-10-26T10:00:00+08:00"
        assert row["finished_at"] == "2026-10-26T10:04:30+08:00"
        assert events(conn, "run.quiet") == []


def _with_jobs(monkeypatch, **extra):
    base = config.settings()
    patched = {**base, "jobs": {**base["jobs"], **extra}}
    monkeypatch.setattr(config, "settings", lambda: patched)


def test_a_quiet_job_that_fails_writes_a_run_row_and_no_run_quiet(monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    _with_jobs(monkeypatch, broken={"agent": "outreach", "kind": "command", "command": ["no-such-command"], "quiet": True, "schedule": {"daily": "10:00"}})
    outcome = runner.run("broken")
    assert outcome.status == "failed" and "no-such-command" in outcome.error
    with db.session() as conn:
        assert [r["status"] for r in run_rows(conn)] == ["failed"]
        assert events(conn, "run.quiet") == []
    assert mirrored("run.quiet") == []


def test_a_quiet_job_that_is_skipped_writes_run_skipped_and_no_run_quiet(monkeypatch):
    from jura_growth import pause

    at(monkeypatch, MONDAY_10AM)
    with db.session() as conn:
        pause.pause(conn, "outreach", "testing", notify=False)
    assert runner.run("scout-send").status == "skipped"
    with db.session() as conn:
        assert run_rows(conn) == []
        assert [e["job"] for e in events(conn, "run.skipped")] == ["scout-send"]
        assert events(conn, "run.quiet") == []


def test_a_job_that_is_not_quiet_never_writes_run_quiet(monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    _with_jobs(monkeypatch, loud={"agent": "outreach", "kind": "command", "command": ["outreach", "send-due"], "schedule": {"daily": "10:00"}})
    assert runner.run("loud").status == "ok"
    assert runner.run("heartbeat").status == "ok"
    with db.session() as conn:
        assert [(r["job"], r["status"]) for r in run_rows(conn)] == [("loud", "ok"), ("heartbeat", "ok")]
        assert events(conn, "run.quiet") == []
    assert mirrored("run.quiet") == []


# --- NothingToDo -------------------------------------------------------------


def fake_plugin(monkeypatch, name="fake-agent", **hooks):
    """A plug-in for agent `name` with the given hooks, found by `agents.by_name`."""
    module = SimpleNamespace(NAME=name, **hooks)
    real = agents.by_name
    monkeypatch.setattr(agents, "by_name", lambda wanted: module if wanted == name else real(wanted))
    return module


@pytest.mark.parametrize("quiet", [False, True])
def test_a_nothing_to_do_precheck_writes_run_quiet_with_its_reason_and_no_run_row(monkeypatch, quiet):
    at(monkeypatch, MONDAY_10AM)
    fake_plugin(monkeypatch, precheck=lambda job, conn: agents.NothingToDo("nothing due"))
    _with_jobs(monkeypatch, fake={"agent": "fake-agent", "kind": "command", "command": ["heartbeat"], "quiet": quiet, "schedule": {"daily": "10:00"}})
    outcome = runner.run("fake")
    assert outcome.status == "ok"
    with db.session() as conn:
        assert run_rows(conn) == []
        assert events(conn, "run.quiet") == [{"job": "fake", "started_at": "2026-10-26T10:00:00+08:00", "reason": "nothing due"}]
        assert events(conn, "run.skipped") == []  # and no row: the job body (heartbeat) never ran


def test_any_other_precheck_string_is_still_a_skip(monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    fake_plugin(monkeypatch, precheck=lambda job, conn: "7 app PRDs already waiting")
    _with_jobs(monkeypatch, fake={"agent": "fake-agent", "kind": "command", "command": ["heartbeat"], "schedule": {"daily": "10:00"}})
    outcome = runner.run("fake")
    assert outcome.status == "skipped" and outcome.summary == "7 app PRDs already waiting"
    with db.session() as conn:
        assert [(r["status"], r["summary"]) for r in run_rows(conn)] == [("skipped", "7 app PRDs already waiting")]
        assert events(conn, "run.quiet") == []


# --- a quiet claude job ------------------------------------------------------


def fake_claude(tmp_path, result_text="OK: did the thing"):
    """A stand-in `claude` that records its environment's run id."""
    script = tmp_path / "fake-claude"
    record = {"type": "result", "subtype": "success", "is_error": False, "result": result_text, "total_cost_usd": 0.05}
    script.write_text(
        "#!/bin/sh\n"
        "cat > /dev/null\n"
        f'printf "%s" "$JURA_GROWTH_RUN_ID" > {tmp_path}/run-id.txt\n'
        f"echo '{json.dumps(record)}'\n"
    )
    script.chmod(0o755)
    return script


def claude_job(monkeypatch, tmp_path, *, quiet, agent="fake-agent"):
    base = config.settings()
    patched = {
        **base,
        "claude": {**base["claude"], "binary": str(fake_claude(tmp_path))},
        "jobs": {**base["jobs"], "fake": {"agent": agent, "kind": "claude", "prompt": "fake.md", "quiet": quiet, "schedule": {"daily": "06:00"}}},
    }
    monkeypatch.setattr(config, "settings", lambda: patched)
    (paths.prompts_dir() / "fake.md").write_text("Do the fake job.")


def test_a_quiet_claude_job_gets_its_run_row_before_claude_starts(monkeypatch, tmp_path):
    at(monkeypatch, MONDAY_10AM)
    claude_job(monkeypatch, tmp_path, quiet=True)
    outcome = runner.run("fake")
    assert outcome.status == "ok"
    with db.session() as conn:
        [row] = run_rows(conn)
    run_id = row["id"]
    assert (tmp_path / "run-id.txt").read_text() == str(run_id)
    transcripts = sorted(p.name for p in (paths.data_dir() / "transcripts").rglob("*.jsonl"))
    assert transcripts == [f"{run_id}-fake.jsonl"]
    assert "None" not in (tmp_path / "run-id.txt").read_text()


# --- the plug-in after_run hook ---------------------------------------------


def heartbeat_as(monkeypatch, agent="fake-agent"):
    _with_jobs(monkeypatch, fake={"agent": agent, "kind": "command", "command": ["heartbeat"], "schedule": {"daily": "10:00"}})


def test_a_failed_outcome_from_after_run_is_what_the_row_the_alert_and_auto_pause_record(monkeypatch):
    from jura_growth import pause

    at(monkeypatch, MONDAY_10AM)
    seen = []

    def after_run(conn, job, run_id, outcome):
        seen.append((job, run_id, outcome.status))
        return runner.Outcome("failed", summary=outcome.summary, error="audit: visited a host outside the rules")

    fake_plugin(monkeypatch, after_run=after_run)
    heartbeat_as(monkeypatch)
    for _ in range(3):
        outcome = runner.run("fake")
        assert outcome.status == "failed" and outcome.error == "audit: visited a host outside the rules"
    with db.session() as conn:
        rows = run_rows(conn)
        assert [(r["status"], r["error"]) for r in rows] == [("failed", "audit: visited a host outside the rules")] * 3
        assert seen == [("fake", r["id"], "ok") for r in rows]  # the hook saw the body's own outcome
        assert "3 failed runs" in pause.is_paused(conn, "fake-agent")
    alerts = [p["content"] for p in outbox("alerts")]
    assert sum("`fake` failed: audit: visited a host outside the rules" in a for a in alerts) == 3


def test_an_after_run_that_raises_leaves_the_outcome_and_logs_an_error(monkeypatch):
    at(monkeypatch, MONDAY_10AM)

    def after_run(conn, job, run_id, outcome):
        raise RuntimeError("audit broke")

    fake_plugin(monkeypatch, after_run=after_run)
    heartbeat_as(monkeypatch)
    outcome = runner.run("fake")
    assert outcome.status == "ok"
    with db.session() as conn:
        [row] = run_rows(conn)
        assert row["status"] == "ok"
        [error] = events(conn, "run.after_run_error")
        assert error["job"] == "fake" and "RuntimeError: audit broke" in error["error"]
        assert error["hook"] == "fake-agent.after_run"
    assert outbox("alerts") == []


def test_an_after_run_that_returns_none_keeps_the_outcome(monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    calls = []
    fake_plugin(monkeypatch, after_run=lambda conn, job, run_id, outcome: calls.append(job))
    heartbeat_as(monkeypatch)
    assert runner.run("fake").status == "ok"
    assert calls == ["fake"]


def test_after_run_is_not_called_for_a_skip(monkeypatch):
    from jura_growth import pause

    at(monkeypatch, MONDAY_10AM)
    calls = []
    fake_plugin(monkeypatch, after_run=lambda conn, job, run_id, outcome: calls.append(job))
    heartbeat_as(monkeypatch)
    with db.session() as conn:
        pause.pause(conn, "fake-agent", "testing", notify=False)
    assert runner.run("fake").status == "skipped"
    assert calls == []


# --- the core run-update notification ---------------------------------------


@pytest.fixture
def notified(monkeypatch):
    """Every call to the core notification, with what the run row said at
    that moment."""
    from jura_growth import run_update

    calls = []

    def record(conn, job, spec, run_id, outcome):
        row = None
        if conn is not None and run_id is not None:
            row = dict(conn.execute("SELECT status, finished_at FROM runs WHERE id = ?", (run_id,)).fetchone())
        calls.append({"conn": conn, "job": job, "agent": spec["agent"], "run_id": run_id, "status": outcome.status, "summary": outcome.summary, "row": row})

    monkeypatch.setattr(run_update, "after_run", record)
    return calls


def test_the_pause_file_never_notifies(monkeypatch, notified):
    paths.pause_file().write_text("holiday")
    assert runner.run("heartbeat").status == "skipped"
    assert notified == []


def test_the_lock_skip_notifies_once_without_opening_the_database(monkeypatch, notified):
    at(monkeypatch, MONDAY_10AM)

    def no_database(*args, **kwargs):
        raise AssertionError("the lock skip opened growth.db")

    with runner._lock("heartbeat") as held:
        assert held
        monkeypatch.setattr(db, "connect", no_database)
        outcome = runner.run("heartbeat")
    assert outcome.status == "skipped" and outcome.summary == "previous run still going"
    assert [(c["conn"], c["job"], c["run_id"], c["status"], c["summary"]) for c in notified] == [
        (None, "heartbeat", None, "skipped", "previous run still going")
    ]


def test_a_pause_flag_skip_notifies_once_with_its_skip_row(monkeypatch, notified):
    from jura_growth import pause

    at(monkeypatch, MONDAY_10AM)
    with db.session() as conn:
        pause.pause(conn, "heartbeat", "by hand", notify=False)
    assert runner.run("heartbeat").status == "skipped"
    [call] = notified
    assert call["conn"] is not None and call["status"] == "skipped" and "by hand" in call["summary"]
    assert call["row"]["status"] == "skipped"


def test_a_quiet_jobs_skip_notifies_once_without_a_run_id(monkeypatch, notified):
    from jura_growth import pause

    at(monkeypatch, MONDAY_10AM)
    with db.session() as conn:
        pause.pause(conn, "outreach", "by hand", notify=False)
    assert runner.run("scout-send").status == "skipped"
    assert [(c["job"], c["run_id"], c["status"]) for c in notified] == [("scout-send", None, "skipped")]


def test_a_schedule_skip_notifies_once(monkeypatch, notified):
    at(monkeypatch, "2026-12-25T16:45:00+08:00")
    assert runner.run("scout-sync").status == "skipped"
    [call] = notified
    assert call["status"] == "skipped" and "Christmas" in call["summary"] and call["row"]["status"] == "skipped"


def test_a_precheck_skip_notifies_once(monkeypatch, notified):
    at(monkeypatch, MONDAY_10AM)
    fake_plugin(monkeypatch, precheck=lambda job, conn: "7 app PRDs already waiting")
    heartbeat_as(monkeypatch)
    runner.run("fake")
    assert [(c["job"], c["status"], c["summary"]) for c in notified] == [("fake", "skipped", "7 app PRDs already waiting")]


def test_a_quiet_run_with_nothing_to_do_notifies_once(monkeypatch, notified):
    at(monkeypatch, MONDAY_10AM)
    runner.run("scout-send")
    assert [(c["job"], c["run_id"], c["status"]) for c in notified] == [("scout-send", None, "ok")]


def test_a_nothing_to_do_precheck_notifies_once(monkeypatch, notified):
    at(monkeypatch, MONDAY_10AM)
    fake_plugin(monkeypatch, precheck=lambda job, conn: agents.NothingToDo("nothing due"))
    heartbeat_as(monkeypatch)
    runner.run("fake")
    assert [(c["job"], c["run_id"], c["status"]) for c in notified] == [("fake", None, "ok")]


def test_a_finished_run_notifies_once_after_its_row_is_finished(monkeypatch, notified):
    at(monkeypatch, MONDAY_10AM)
    runner.run("heartbeat")
    [call] = notified
    assert call["job"] == "heartbeat" and call["status"] == "ok"
    assert call["row"]["status"] == "ok" and call["row"]["finished_at"]


def test_a_failed_run_notifies_once_after_the_alert_and_auto_pause(monkeypatch, notified):
    from jura_growth import pause

    at(monkeypatch, MONDAY_10AM)
    states = []
    fake_plugin(monkeypatch, after_run=lambda conn, job, run_id, outcome: runner.Outcome("failed", error="boom"))
    heartbeat_as(monkeypatch)
    for _ in range(3):
        runner.run("fake")
        with db.session() as conn:
            states.append((len([p for p in outbox("alerts") if "`fake` failed: boom" in p["content"]]), bool(pause.is_paused(conn, "fake-agent"))))
    assert [c["status"] for c in notified] == ["failed"] * 3
    assert all(c["row"]["status"] == "failed" for c in notified)
    assert states == [(1, False), (2, False), (3, True)]


def test_a_failing_notification_never_changes_the_run(monkeypatch):
    from jura_growth import run_update

    at(monkeypatch, MONDAY_10AM)

    def broken(conn, job, spec, run_id, outcome):
        raise RuntimeError("discord exploded")

    monkeypatch.setattr(run_update, "after_run", broken)
    assert runner.run("heartbeat").status == "ok"
    with runner._lock("heartbeat"):
        assert runner.run("heartbeat").summary == "previous run still going"
    with db.session() as conn:
        assert [r["status"] for r in run_rows(conn)] == ["ok"]
        [error] = events(conn, "run.after_run_error")
        assert error["hook"] == "run_update.after_run" and "discord exploded" in error["error"]
    lock_errors = [e for e in mirrored("run.after_run_error") if e["hook"] == "run_update.after_run"]
    assert len(lock_errors) == 2  # the finished run's (also in the table) and the lock skip's, mirror only
