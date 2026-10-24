"""`jura-growth run <job>`: what launchd calls for every scheduled job.

In order: the PAUSE file (before touching the database), the agent's pause
flag, business days for business-day jobs, the agent's own precheck, a lock so
a slow run and its next slot never overlap, then the job itself.

A `command` job calls a `jura-growth` command in-process. A `claude` job runs
headless Claude Code (`claude -p`) with the job's prompt file and a tight tool
allowlist: read anything under jurasolutions/, run `jura-growth`, write only
in the job's scratch folder, plus the job's own tools (web search and fetch).
No MCP servers, no user settings, a per-run spending ceiling, and the full
stream-json transcript kept for audit.

Three failed runs in a row pause the agent (pause.check_auto_pause).
"""

from __future__ import annotations

import fcntl
import json
import os
import shlex
import sqlite3
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

from jura_growth import agents, config, db, discord, headless, holidays, log, pause, paths, timeutil

BUSINESS_DAY_KINDS = ("business_days", "business_days_every")


class JobError(RuntimeError):
    pass


@dataclass
class Outcome:
    status: str  # ok, failed, skipped
    summary: str = ""
    error: str = ""
    cost_usd: float | None = None


def jobs() -> dict[str, dict]:
    return config.settings()["jobs"]


def job(name: str) -> dict:
    try:
        return jobs()[name]
    except KeyError:
        raise JobError(f"unknown job {name!r}; known: {', '.join(jobs())}") from None


@contextmanager
def _lock(name: str) -> Iterator[bool]:
    path = paths.writable(paths.data_dir() / "locks" / f"{name}.lock")
    handle = open(path, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        yield False
        return
    try:
        yield True
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def run(name: str, *, ignore_schedule: bool = False) -> Outcome:
    spec = job(name)
    agent = spec["agent"]

    if pause.pause_file_active():
        reason = pause.is_paused(None, agent)
        log.mirror({"ts": timeutil.stamp(), "agent": agent, "level": "info", "kind": "run.skipped", "payload": {"job": name, "reason": reason}})
        return Outcome("skipped", reason)

    with _lock(name) as acquired:
        if not acquired:
            log.mirror({"ts": timeutil.stamp(), "agent": agent, "level": "info", "kind": "run.skipped", "payload": {"job": name, "reason": "previous run still going"}})
            return Outcome("skipped", "previous run still going")

        conn = db.connect()
        try:
            return _run_locked(conn, name, spec, ignore_schedule)
        finally:
            conn.close()


def _run_locked(conn: sqlite3.Connection, name: str, spec: dict, ignore_schedule: bool) -> Outcome:
    agent = spec["agent"]
    quiet = bool(spec.get("quiet"))

    reason = pause.is_paused(conn, agent)
    if not reason and not ignore_schedule:
        reason = _schedule_reason(spec)
    if not reason:
        module = agents.by_name(agent)
        precheck = getattr(module, "precheck", None) if module else None
        reason = precheck(name, conn) if precheck else None
    if reason:
        if quiet:
            log.event(conn, "run.skipped", {"job": name, "reason": reason}, agent=agent)
        else:
            log.skip_run(conn, agent, name, reason)
        return Outcome("skipped", reason)

    _abandon_stale(conn)
    run_id = None if quiet else log.start_run(conn, agent, name)
    try:
        if spec["kind"] == "command":
            outcome = _run_command(spec, agent, run_id, name)
        elif spec["kind"] == "claude":
            outcome = _run_claude(name, spec, agent, run_id)
        else:
            raise JobError(f"job {name} has unknown kind {spec['kind']!r}")
    except Exception as error:  # noqa: BLE001 - every failure is recorded
        outcome = Outcome("failed", error=f"{type(error).__name__}: {error}")

    if quiet and run_id is None:
        if outcome.status == "ok" and not outcome.summary:
            return outcome  # nothing happened; no run row
        run_id = log.start_run(conn, agent, name)
    log.finish_run(conn, run_id, outcome.status, summary=outcome.summary, error=outcome.error, cost_usd=outcome.cost_usd)

    if outcome.status == "failed":
        discord.alert(conn, f"`{name}` failed: {outcome.error[:500]}", agent=agent)
        pause.check_auto_pause(conn, agent)
    return outcome


def _schedule_reason(spec: dict) -> str | None:
    kinds = set(spec.get("schedule", {}))
    if kinds & set(BUSINESS_DAY_KINDS):
        today = timeutil.today()
        if not holidays.is_business_day(today):
            name = holidays.holiday(today)
            return f"not a business day ({name})" if name else "not a business day (weekend)"
    return None


def _abandon_stale(conn: sqlite3.Connection) -> None:
    """Mark runs left 'running' by a killed process as failed.

    Uses the real clock, never a frozen JURA_GROWTH_NOW, and leaves alone any
    run whose job lock is still held: that process is alive.
    """
    limit = int(config.settings()["claude"].get("timeout_minutes", 30)) + 15
    cutoff = datetime.now(timeutil.SGT) - timedelta(minutes=limit)
    for row in conn.execute("SELECT id, job, started_at FROM runs WHERE status = 'running'").fetchall():
        try:
            started = timeutil.parse(row["started_at"])
        except ValueError:
            continue
        if started > cutoff or _lock_held(row["job"]):
            continue
        log.finish_run(conn, row["id"], "failed", error="abandoned: the process stopped before finishing")


def _lock_held(name: str) -> bool:
    path = paths.data_dir() / "locks" / f"{name}.lock"
    if not path.exists():
        return False
    with open(path, "a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(handle, fcntl.LOCK_UN)
    return False


# --- command jobs ----------------------------------------------------------


@contextmanager
def _run_env(run_id: int | None, agent: str, job_name: str) -> Iterator[None]:
    saved = {k: os.environ.get(k) for k in ("JURA_GROWTH_RUN_ID", "JURA_GROWTH_AGENT", "JURA_GROWTH_JOB")}
    if run_id is not None:
        os.environ["JURA_GROWTH_RUN_ID"] = str(run_id)
    os.environ["JURA_GROWTH_AGENT"] = agent
    os.environ["JURA_GROWTH_JOB"] = job_name
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _run_command(spec: dict, agent: str, run_id: int | None, job_name: str) -> Outcome:
    from jura_growth.cli import cli

    with _run_env(run_id, agent, job_name):
        try:
            result = cli.main(list(spec["command"]), prog_name="jura-growth", standalone_mode=False)
        except SystemExit as exit_:
            if exit_.code not in (0, None):
                return Outcome("failed", error=f"exited with {exit_.code}")
            result = None
    if isinstance(result, int) and result != 0:
        return Outcome("failed", error=f"exited with {result}")
    return Outcome("ok", summary=result if isinstance(result, str) else "")


# --- claude jobs -----------------------------------------------------------


def claude_command(name: str, spec: dict) -> tuple[list[str], str]:
    """The argv and the stdin prompt for a claude job (also used by --dry-run)."""
    settings = config.settings()["claude"]
    prompt_file = paths.prompts_dir() / spec["prompt"]
    if not prompt_file.exists():
        raise JobError(f"prompt file missing: {prompt_file}")
    work = paths.writable(paths.work_dir(name) / ".keep").parent

    # Only the job's own jura-growth commands, and no secret files (headless.py).
    commands_allowed, commands_disallowed = headless.claude_rules(name)
    allowed = [
        *commands_allowed,
        f"Write(/{work}/**)",
        f"Edit(/{work}/**)",
        *spec.get("tools", []),
    ]
    disallowed = [
        *commands_disallowed,
        *spec.get("disallowed_tools", []),
    ]
    budget = spec.get("max_budget_usd", settings.get("max_budget_usd", 3.0))
    argv = [
        settings.get("binary", "claude"),
        "-p",
        "--output-format", "stream-json",
        "--verbose",
        "--permission-mode", "dontAsk",
        "--strict-mcp-config",
        "--setting-sources", "project",
        "--no-session-persistence",
        "--add-dir", str(paths.JURA_ROOT),
        "--max-budget-usd", str(budget),
        "--allowedTools", *allowed,
        "--disallowedTools", *disallowed,
    ]
    if spec.get("model") or settings.get("model"):
        argv += ["--model", spec.get("model") or settings["model"]]
    return argv, prompt_file.read_text(encoding="utf-8")


def _preamble(name: str, spec: dict, run_id: int | None) -> str:
    moment = timeutil.now_sgt()
    work = paths.work_dir(name)
    return (
        "# Run context\n\n"
        f"- Job: `{name}` (agent `{spec['agent']}`), run {run_id}\n"
        f"- Now: {moment.strftime('%A')} {timeutil.stamp(moment)} SGT\n"
        f"- Scratch folder: `{work}`. It is the only place you can write files.\n"
        "- Every side effect (database, Discord, files outside scratch, email) goes through "
        "`jura-growth`. Run `jura-growth --help` and `jura-growth <group> --help` for the commands.\n"
        "- Jura Solutions only. Never read `taskwise-*` or ZenexFlow folders. No Notion, no Zapier.\n"
        "- `inputs/` and `design-system/` are read-only.\n"
        "- Finish with a one to three line summary that starts with `OK:` if the run did its job, "
        "`SKIP:` if there was nothing to do, or `FAIL:` if it could not.\n\n---\n\n"
    )


def _run_claude(name: str, spec: dict, agent: str, run_id: int | None) -> Outcome:
    argv, prompt = claude_command(name, spec)
    timeout = int(config.settings()["claude"].get("timeout_minutes", 30)) * 60
    transcript = paths.writable(
        paths.data_dir() / "transcripts" / timeutil.today_str() / f"{run_id}-{name}.jsonl"
    )
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join([str(paths.REPO_ROOT / ".venv" / "bin"), env.get("PATH", "")])
    env.update(JURA_GROWTH_RUN_ID=str(run_id), JURA_GROWTH_AGENT=agent, JURA_GROWTH_JOB=name)

    conn_note = {"job": name, "argv": shlex.join(argv[:3]) + " …", "transcript": str(transcript)}
    log.event(None, "claude.start", conn_note, agent=agent, run_id=run_id)
    with open(transcript, "w", encoding="utf-8") as out:
        process = subprocess.Popen(
            argv,
            cwd=paths.REPO_ROOT,
            stdin=subprocess.PIPE,
            stdout=out,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        try:
            _, stderr = process.communicate(_preamble(name, spec, run_id) + prompt, timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            return Outcome("failed", error=f"timed out after {timeout // 60} minutes")

    result = _final_result(transcript)
    if result is None:
        return Outcome("failed", error=f"no result from claude (exit {process.returncode}): {(stderr or '')[-400:]}")
    text = (result.get("result") or "").strip()
    cost = result.get("total_cost_usd")
    denials = [
        {"tool": d.get("tool_name"), "input": str(d.get("tool_input", ""))[:200]}
        for d in result.get("permission_denials") or []
    ]
    log.event(
        None,
        "claude.result",
        {"job": name, "turns": result.get("num_turns"), "cost_usd": cost, "denials": denials},
        agent=agent,
        run_id=run_id,
    )
    if result.get("is_error") or process.returncode != 0:
        return Outcome("failed", summary=text[:2000], error=f"claude {result.get('subtype', 'error')}", cost_usd=cost)
    return _judge(text, cost, agent, run_id)


def _judge(text: str, cost: float | None, agent: str, run_id: int | None) -> Outcome:
    """A run fails if any line of its summary starts with FAIL:. A summary with
    no OK:/SKIP:/FAIL: prefix at all is recorded as ok but flagged."""
    lines = [line.strip().lstrip("*_`> ").upper() for line in text.splitlines() if line.strip()]
    if any(line.startswith("FAIL:") for line in lines):
        failing = next(l for l in text.splitlines() if l.strip().lstrip("*_`> ").upper().startswith("FAIL:"))
        return Outcome("failed", summary=text[:2000], error=failing.strip()[:500], cost_usd=cost)
    if not any(line.startswith(("OK:", "SKIP:")) for line in lines):
        log.event(None, "claude.unprefixed", {"summary": text[:300]}, level="warning", agent=agent, run_id=run_id)
    return Outcome("ok", summary=text[:2000], cost_usd=cost)


def _final_result(transcript: Path) -> dict | None:
    final = None
    with open(transcript, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get("type") == "result":
                final = record
    return final
