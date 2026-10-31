"""`jura-growth run <job>`: what launchd calls for every scheduled job.

In order: the PAUSE file (before touching the database), the agent's pause
flag, business days for business-day jobs, the agent's own precheck, a lock so
a slow run and its next slot never overlap, then the job itself.

A `command` job calls a `jura-growth` command in-process. A `claude` job runs
headless Claude Code (`claude -p`) with the job's prompt file and a tight tool
allowlist: read anything under jurasolutions/ except secret files, run the
job's own `jura-growth` commands (headless.py), write only in the job's
scratch folder, plus the job's own tools (web search and fetch).
No MCP servers, no user settings, and the full stream-json transcript kept
for audit. No spending ceiling: the runs use Ting Yu's Claude subscription,
not API billing, so `--max-budget-usd` is never passed. The timeout and each
job's own caps (leads, posts, emails) still hold.

Three failed runs in a row pause the agent (pause.check_auto_pause).

A quiet command job that finds nothing to do, and any job whose precheck
returns `agents.NothingToDo`, leaves a `run.quiet` event instead of a run row
(ADR 0001). After the job body the agent's `after_run` hook may replace the
outcome, before the row is finished. Every path except the PAUSE file ends
with one call to `run_update.after_run`; the lock skip passes `conn=None`.
Neither hook can change a run by raising: the error is logged as
`run.after_run_error`. A precheck that raises is a failed run, recorded,
alerted and counted toward auto-pause like any other (code review 03).
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import sqlite3
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

from jura_growth import agents, caps, config, db, discord, headless, holidays, locks, log, pause, paths, run_update, schedule, timeutil


class JobError(RuntimeError):
    pass


@dataclass
class Outcome:
    status: str  # ok, failed, skipped
    summary: str = ""
    error: str = ""
    cost_usd: float | None = None
    # True when the failure has already been posted to #alerts (a publish stop, by
    # `publish stopped` itself), so the runner doesn't post it a second time.
    alerted: bool = False


def jobs() -> dict[str, dict]:
    return config.settings()["jobs"]


def job(name: str) -> dict:
    try:
        return jobs()[name]
    except KeyError:
        raise JobError(f"unknown job {name!r}; known: {', '.join(jobs())}") from None


_lock = locks.held  # one lock per job


def run(name: str, *, ignore_schedule: bool = False) -> Outcome:
    spec = job(name)
    agent = spec["agent"]

    if pause.pause_file_active():
        reason = pause.is_paused(None, agent)
        log.mirror({"ts": timeutil.stamp(), "agent": agent, "level": "info", "kind": "run.skipped", "payload": {"job": name, "reason": reason}})
        return Outcome("skipped", reason)

    with _lock(name) as acquired:
        if not acquired:
            log.mirror({"ts": timeutil.stamp(), "agent": agent, "level": "info", "kind": "run.skipped", "payload": {"job": name, "reason": locks.STILL_GOING}})
            outcome = Outcome("skipped", locks.STILL_GOING)
            _run_update(None, name, spec, None, outcome)  # never opens growth.db
            return outcome

        conn = db.connect()
        try:
            return _run_locked(conn, name, spec, ignore_schedule)
        finally:
            conn.close()


def _run_locked(conn: sqlite3.Connection, name: str, spec: dict, ignore_schedule: bool) -> Outcome:
    agent = spec["agent"]
    # `quiet` means something only for a command job. A claude job spends
    # money and needs a run id (environment, transcript, `used_by_run`), so it
    # always gets its run row before Claude starts.
    quiet = bool(spec.get("quiet")) and spec["kind"] == "command"
    started_at = timeutil.stamp()
    module = agents.by_name(agent)

    reason = pause.is_paused(conn, agent)
    if not reason and not ignore_schedule:
        reason = _schedule_reason(spec)
    crashed = None
    if not reason:
        precheck = getattr(module, "precheck", None)
        try:
            reason = precheck(name, conn) if precheck else None
        except Exception as error:  # noqa: BLE001 - a broken precheck (a config typo) is a failed run
            crashed = Outcome("failed", error=f"precheck failed: {type(error).__name__}: {error}")
    if isinstance(reason, agents.NothingToDo):
        log.event(conn, "run.quiet", {"job": name, "started_at": started_at, "reason": str(reason)}, agent=agent)
        return _run_update(conn, name, spec, None, Outcome("ok", str(reason)))
    if reason:
        skip_id = None
        if quiet:
            log.event(conn, "run.skipped", {"job": name, "reason": reason}, agent=agent)
        else:
            skip_id = log.skip_run(conn, agent, name, reason)
        return _run_update(conn, name, spec, skip_id, Outcome("skipped", reason))

    _abandon_stale(conn)
    run_id = None if quiet else log.start_run(conn, agent, name)
    try:
        if crashed:
            outcome = crashed  # recorded like any failed run, with its row, alert and run update
        elif spec["kind"] == "command":
            outcome = _run_command(spec, agent, run_id, name)
        elif spec["kind"] == "claude":
            outcome = _run_claude(name, spec, agent, run_id)
        else:
            raise JobError(f"job {name} has unknown kind {spec['kind']!r}")
    except Exception as error:  # noqa: BLE001 - every failure is recorded
        outcome = Outcome("failed", error=f"{type(error).__name__}: {error}")

    # The plug-in's last word on a run that started (the publish audit can
    # fail it), before the row, the alert and auto-pause see the outcome.
    hook = None if crashed else getattr(module, "after_run", None)
    if hook:
        try:
            final = hook(conn, name, run_id, outcome)
            if isinstance(final, Outcome):
                outcome = final
        except Exception as error:  # noqa: BLE001 - the original outcome stands
            _hook_failed(conn, f"{agent}.after_run", name, agent, run_id, error)

    if quiet and run_id is None:
        if outcome.status == "ok" and not outcome.summary:
            # Nothing happened: no run row, but a trace, so the slot reads
            # as run rather than slept through (ADR 0001).
            log.event(conn, "run.quiet", {"job": name, "started_at": started_at}, agent=agent)
            return _run_update(conn, name, spec, None, outcome)
        run_id = log.start_run(conn, agent, name, started_at=started_at)
    log.finish_run(conn, run_id, outcome.status, summary=outcome.summary, error=outcome.error, cost_usd=outcome.cost_usd)

    if outcome.status == "failed":
        try:
            if not outcome.alerted:
                discord.alert(conn, f"`{name}` failed: {outcome.error[:500]}", agent=agent)
        finally:
            pause.check_auto_pause(conn, agent)  # whatever happened to the alert
    return _run_update(conn, name, spec, run_id, outcome)


def _run_update(conn: sqlite3.Connection | None, name: str, spec: dict, run_id: int | None, outcome: Outcome) -> Outcome:
    """Hand the run to `run_update.after_run`, once per run.
    Its errors are logged and the run's outcome is returned unchanged."""
    try:
        run_update.after_run(conn, name, spec, run_id, outcome)
    except Exception as error:  # noqa: BLE001
        _hook_failed(conn, "run_update.after_run", name, spec["agent"], run_id, error)
    return outcome


def _hook_failed(conn: sqlite3.Connection | None, hook: str, job: str, agent: str, run_id: int | None, error: Exception) -> None:
    """Record a hook's exception as `run.after_run_error`. Never raises: a
    hook can't change a run's outcome by failing."""
    try:
        log.event(
            conn,
            "run.after_run_error",
            {"job": job, "hook": hook, "error": f"{type(error).__name__}: {error}"[:500]},
            level="error",
            agent=agent,
            run_id=run_id,
        )
    except Exception:  # noqa: BLE001 - not even the log may break the run
        pass


def _schedule_reason(spec: dict) -> str | None:
    if schedule.business_days_only(spec.get("schedule", {})):
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
        if started > cutoff or locks.is_held(row["job"]):
            continue
        log.finish_run(conn, row["id"], "failed", error="abandoned: the process stopped before finishing")


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
    """The argv and the stdin prompt for a claude job (also used by --dry-run).

    A job in `caps.BROWSER_JOBS` that sets `browser: true` gets `--chrome`, and `--add-dir` for its own
    scratch folder only (ADR 0005, amended 2026-10-30): its plug-in's rules scope the Chrome tools by
    domain, and the files it needs are copied into that folder, which the upload tool must be able to read. Any other job that sets `browser` raises.
    Any job in `caps.THIRD_PARTY_TEXT_JOBS` adds only its scratch folder too: it holds a stranger's words.
    A job in `caps.CLEAN_CWD_JOBS` also has its file tools fenced to its working folders (`claude_cwd`)."""
    settings = config.settings()["claude"]
    browser = name in caps.BROWSER_JOBS
    if spec.get("browser") and not browser:
        raise JobError(f"job {name} sets browser: true, but only {', '.join(sorted(caps.BROWSER_JOBS))} may drive Chrome")
    prompt_file = paths.prompts_dir() / spec["prompt"]
    if not prompt_file.exists():
        raise JobError(f"prompt file missing: {prompt_file}")
    work = paths.writable(paths.work_dir(name) / ".keep").parent

    # Only the job's own jura-growth commands, and no secret files (headless.py).
    commands_allowed, commands_disallowed = headless.claude_rules(name)  # with the plug-in's tool rules
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
    argv = [
        settings.get("binary", "claude"),
        "-p",
        "--output-format", "stream-json",
        "--verbose",
        "--permission-mode", "dontAsk",
        "--strict-mcp-config",
        "--setting-sources", "project",
        "--no-session-persistence",
        # A browser job adds only its own scratch folder, where its image copies are, so the Chrome upload
        # tool may read them (rehearsal R1, 2026-10-30), and triage holds a stranger's words (inbox watch,
        # B4); every other job adds JURA_ROOT.
        "--add-dir", str(work) if name in caps.THIRD_PARTY_TEXT_JOBS else str(paths.JURA_ROOT),
        "--allowedTools", *allowed,
        "--disallowedTools", *disallowed,
    ]
    if browser and spec.get("browser"):
        argv.append("--chrome")
    if name in caps.CLEAN_CWD_JOBS:
        argv += ["--settings", json.dumps({"permissions": {"blockReadsOutsideWorkingDirectories": True}})]
    if spec.get("model") or settings.get("model"):
        argv += ["--model", spec.get("model") or settings["model"]]
    return argv, prompt_file.read_text(encoding="utf-8")


def claude_cwd(name: str) -> Path:
    """Where a claude job starts. For a job in `caps.CLEAN_CWD_JOBS`, an empty folder of its own: a
    read-only Bash command run from the repo can read `.env`. It isn't the scratch folder, because
    the session can write there, and Claude Code loads `.claude/settings.json` and `CLAUDE.md` from
    where it starts, so a steered run could leave rules for the next one. No rule lets it write
    here, and the folder is emptied before each run."""
    if name not in caps.CLEAN_CWD_JOBS:
        return paths.REPO_ROOT
    folder = paths.data_dir() / "work" / f"{name}.cwd"
    if folder.exists():
        shutil.rmtree(folder)
    return paths.writable(folder / ".keep").parent


def _preamble(name: str, spec: dict, run_id: int | None) -> str:
    moment = timeutil.now_sgt()
    work = paths.work_dir(name)
    return (
        "# Run context\n\n"
        f"- Job: `{name}` (agent `{spec['agent']}`), run {run_id}\n"
        f"- Now: {moment.strftime('%A')} {timeutil.stamp(moment)} SGT\n"
        f"- Scratch folder: `{work}`. It is the only place you can write files.\n"
        f"{_commands_line(name)}"
        "- Jura Solutions only. Never read `taskwise-*` or ZenexFlow folders. No Notion, no Zapier.\n"
        "- `inputs/` and `design-system/` are read-only.\n"
        "- Finish with a one to three line summary that starts with `OK:` if the run did its job, "
        "`SKIP:` if there was nothing to do, or `FAIL:` if it could not.\n\n---\n\n"
    )


def _commands_line(name: str) -> str:
    """The job's own `jura-growth` commands, the only ones this run may use
    (headless.permissions), so the preamble never invites a refused call."""
    commands = [c for c in headless.permissions(name).commands if not headless.never(c)]
    if not commands:
        return "- This job may run no jura-growth commands; anything you try is refused.\n"
    listed = ", ".join(f"`jura-growth {command}`" for command in commands)
    return (
        "- Every side effect (database, files outside scratch, email) goes through this job's own commands, "
        f"and any other command is refused: {listed}. Add `--help` to one of them for its options.\n"
    )


def _run_claude(name: str, spec: dict, agent: str, run_id: int | None) -> Outcome:
    argv, prompt = claude_command(name, spec)
    timeout = int(spec.get("timeout_minutes") or config.settings()["claude"].get("timeout_minutes", 30)) * 60
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
            cwd=claude_cwd(name),
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
    # A third-party-text job's commands and denied writes can hold a stranger's words, and this log
    # is never pruned: the tool and a length, and the transcript keeps the rest for its 7 days.
    third_party = name in caps.THIRD_PARTY_TEXT_JOBS
    denials = [
        {"tool": d.get("tool_name"), "input_chars": len(str(d.get("tool_input", "")))} if third_party
        else {"tool": d.get("tool_name"), "input": str(d.get("tool_input", ""))[:200]}
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
    return _judge(text, cost, agent, run_id, third_party=third_party)


def _judge(text: str, cost: float | None, agent: str, run_id: int | None, *, third_party: bool = False) -> Outcome:
    """A run fails if any line of its summary starts with FAIL:. A summary with
    no OK:/SKIP:/FAIL: prefix at all is recorded as ok but flagged."""
    lines = [line.strip().lstrip("*_`> ").upper() for line in text.splitlines() if line.strip()]
    if any(line.startswith("FAIL:") for line in lines):
        failing = next(l for l in text.splitlines() if l.strip().lstrip("*_`> ").upper().startswith("FAIL:"))
        return Outcome("failed", summary=text[:2000], error=failing.strip()[:500], cost_usd=cost)
    if not any(line.startswith(("OK:", "SKIP:")) for line in lines):
        said = {"summary_chars": len(text)} if third_party else {"summary": text[:300]}
        log.event(None, "claude.unprefixed", said, level="warning", agent=agent, run_id=run_id)
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
