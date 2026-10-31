"""The one-pager's read model (MC §4.2, §5.3; ADR 0002).

A `Source` (the database path, the data, outputs and PRD folders, the clock and
the jobs) goes in; a `Snapshot` of plain data comes out. `health.strip()` and
`one_pager` build text from the snapshot, never from the database.

The read model never writes and never repairs:

- growth.db is opened `mode=ro` with `PRAGMA query_only = ON`, read in one go and
  closed before anything is rendered. A hot journal (`SQLITE_READONLY_ROLLBACK`)
  or a lock is the `UNFINISHED_WRITE` state, a missing file `MISSING`, a missing
  migration a name in `missing_migrations`. Rolling back the journal is left to
  the next ordinary open (`/growth status`).
- `approvals` rows are read with its own `SELECT`s. A request past its decide-by
  or use-by counts as lapsed by the clock, without writing; the one-pager job
  writes those transitions on its own connection before this runs (A17). No
  approval function and no kind's `content()` is called: either may supersede.
- No job lock is taken: a running run is judged by its row. Only the one-pager's
  post waits for a lock (`read_patiently`): it starts in the same minute as
  publish, and a held lock would post the bad-day picture.

Every string in a snapshot has been through `privacy.for_discord()`.
"""

from __future__ import annotations

import dataclasses
import json
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from jura_growth import agents, discord, health, paths, privacy, schedule, slots, timeutil
from jura_growth.timeutil import SGT

OK, MISSING, UNFINISHED_WRITE, UNREADABLE = "ok", "missing", "unfinished write", "unreadable"
DB_STATES = (OK, MISSING, UNFINISHED_WRITE, UNREADABLE)


@dataclass(frozen=True)
class DbWording:
    """How a database problem reads: `strip` is the health strip's item,
    with what to send (`{error}` or `{listed}` filled in), and
    `unavailable` stands in for a section growth.db couldn't fill."""

    strip: str
    unavailable: str


# One map, so the health strip and the one-pager word a state alike, and a
# new state can't reach only one of them (code review 08 ST-3).
DB_WORDING = {
    MISSING: DbWording("growth.db doesn't exist yet, so nothing has been recorded.",
                       "Nothing recorded yet: growth.db doesn't exist"),
    UNFINISHED_WRITE: DbWording("growth.db has an unfinished write. Send `/growth status` to clear it.",
                                "Not available: growth.db has an unfinished write"),
    UNREADABLE: DbWording("growth.db couldn't be read ({error}). Send `/growth status` to check it.",
                          "Not available: growth.db couldn't be read"),
}
NOT_MIGRATED = DbWording("growth.db isn't migrated yet ({listed}). Send `/growth status` to migrate it.",
                         "Not available: growth.db isn't migrated yet")
BUSY_TIMEOUT = 2  # seconds: scout-send writes every 10 minutes, so reads stay short
LOCK_PATIENCE, LOCK_RETRY = 60, 5  # seconds: how long the one-pager's post waits for a lock, and how often it asks
_BUSY = {"SQLITE_READONLY_ROLLBACK", "SQLITE_BUSY", "SQLITE_LOCKED"}


@dataclass(frozen=True)
class Source:
    db: Path
    data: Path
    outputs: Path
    prd: Path
    now: datetime
    jobs: Mapping[str, Mapping[str, Any]]
    installed: Callable[[str], bool] = schedule.installed
    days: int = 14  # the grid's width, ending today

    @classmethod
    def here(cls, *, installed: Callable[[str], bool] = schedule.installed) -> Source:
        """This engine's own folders, jobs and clock."""
        from jura_growth import config, timeutil

        return cls(
            db=paths.db_path(),
            data=paths.data_dir(),
            outputs=paths.outputs_dir(),
            prd=paths.prd_dir(),
            now=timeutil.now_sgt(),
            jobs=config.settings()["jobs"],
            installed=installed,
        )


@dataclass(frozen=True)
class Snapshot:
    now: datetime
    db_state: str
    db_error: str | None = None  # the SQLite error name when growth.db couldn't be read
    missing_migrations: tuple[str, ...] = ()
    days: tuple[date, ...] = ()
    slots: dict[tuple[str, date], list[slots.SlotStatus]] = field(default_factory=dict)  # empty without a runs table
    installs: dict[str, str] = field(default_factory=dict)  # job: health.INSTALLED, OUT_OF_DATE or NOT_INSTALLED
    approvals: tuple[Request, ...] | None = None  # None when the approvals table isn't there
    last_one_pager: datetime | None = None  # the scheduled one before now: "since the last one-pager"
    next_one_pager: datetime | None = None
    pause_file: str | None = None  # its reason, when the PAUSE file is there
    paused: tuple[tuple[str, str], ...] = ()  # (agent, reason)
    failures: tuple[Failure, ...] = ()
    undelivered: int = 0  # Discord posts not delivered since the last one-pager
    outbox: int = 0  # outbox messages saved since the last one-pager
    gaps: tuple[health.Gap, ...] = ()
    plugin_lines: tuple[str, ...] = ()  # plug-ins' own "Needs you" lines (their health(conn) hook)
    broken: tuple[str, ...] = ()  # plug-ins that failed to load
    yesterday: Yesterday | None = None
    spend_today: float = 0.0
    morning: Yesterday | None = None  # today's figures so far, for the morning picture


def db_problem(snapshot: Snapshot) -> DbWording | None:
    """What is wrong with growth.db, worded from `DB_WORDING` with the
    details filled in, or None when nothing is. A state with no wording
    raises KeyError rather than reading as unmigrated."""
    if snapshot.db_state != OK:
        wording = DB_WORDING[snapshot.db_state]
        return DbWording(wording.strip.format(error=snapshot.db_error), wording.unavailable)
    if snapshot.missing_migrations:
        names = list(snapshot.missing_migrations)
        listed = ", ".join(names[:3]) + (f" and {len(names) - 3} more" if len(names) > 3 else "")
        return DbWording(NOT_MIGRATED.strip.format(listed=listed), NOT_MIGRATED.unavailable)
    return None


@dataclass(frozen=True)
class Failure:
    """A failed run: the latest finished run of its job, or one in the last 24 hours."""

    job: str
    at: datetime
    error: str | None


@dataclass(frozen=True)
class Yesterday:
    """The digest's figure lines for yesterday (`digest.build()`), and its spend."""

    day: str
    lines: tuple[str, ...]
    spend: float
    figures: Mapping[str, Any] = field(default_factory=dict)  # the plug-ins' figures, strings masked


class Reading:
    """A request reading (CONTEXT.md): what an approval request means now,
    judged by the clock (MC §4.2). A stored status doesn't change until
    something writes it, so a pending request past its decide-by already
    reads as lapsed here. Kept apart from `approvals`' stored statuses, so
    the two vocabularies can't be compared by mistake (code review 08 ST-2)."""

    WAITING, LAPSED, APPROVED, LAPSED_UNUSED, USED, SKIPPED, SUPERSEDED = (
        "waiting", "lapsed", "approved", "lapsed unused", "used", "skipped", "superseded",
    )
    ALL = (WAITING, LAPSED, APPROVED, LAPSED_UNUSED, USED, SKIPPED, SUPERSEDED)


@dataclass(frozen=True)
class Request:
    """One approval request as the one-pager needs it."""

    id: str  # A-nnnn
    kind: str
    reading: str  # one of Reading.ALL
    requested_at: datetime
    decide_by: datetime
    use_by: datetime | None
    posted: bool
    close_reason: str | None
    reason: str = ""  # why the engine asked: the row's own words, no kind's content()


# The one-pager job's own schedule (config/settings.yaml); without the job, its planned 09:00.
ONE_PAGER_JOB, ONE_PAGER_DEFAULT = "one-pager", {"daily": "09:00"}
ONE_PAGER_GRACE = timedelta(hours=1)  # a slot this recent is the one-pager being built now
ONE_PAGER_LOOKBACK = timedelta(days=7)  # "since the last one-pager" never reaches further back


def open_read_only(path: Path) -> sqlite3.Connection:
    """growth.db for reading only. The first query raises on a hot journal."""
    conn = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True, timeout=BUSY_TIMEOUT)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def read(source: Source) -> Snapshot:
    """Everything the one-pager shows, read once. Never raises for the
    database's state: that is `db_state`."""
    now = source.now.astimezone(SGT)
    days = tuple(now.date() - timedelta(days=n) for n in reversed(range(source.days)))
    scheduled, following = one_pager_times(now, source.jobs)
    installs = health.install_states(source.jobs, source.installed)
    conn, state, error = _connect(Path(source.db))
    try:
        privacy.load_for_masking(conn)  # the rows and files were written by other processes
        last, facts = scheduled, {}
        if conn is not None:
            try:
                last = _last_one_pager(conn, now, scheduled)
                facts = _from_db(conn, source, now, days, installs, last)
            except sqlite3.Error as failure:
                last, facts, state, error = scheduled, {}, _state_of(failure), _error_name(failure)
        return Snapshot(
            now,
            state,
            error,
            days=days,
            installs=installs,
            last_one_pager=last,
            next_one_pager=following,
            pause_file=_pause_file(),
            gaps=tuple(health.setup_gaps()),
            broken=tuple(_clean(f"{name} ({problem[:120]})") for name, problem in agents.BROKEN.items()),
            outbox=_outbox(discord.outbox_dir(Path(source.data)), last),
            **facts,
        )
    finally:
        if conn is not None:
            conn.close()


def read_patiently(source: Source, *, sleep: Callable[[float], None] = time.sleep) -> Snapshot:
    """`read`, retried while growth.db is locked, for up to `LOCK_PATIENCE` seconds. Past
    that, the snapshot that says so. For the one-pager's post only: `/growth status` and
    `--no-post` should stay quick."""
    waited = 0.0
    while True:
        snapshot = read(source)
        if snapshot.db_state != UNFINISHED_WRITE or waited + LOCK_RETRY > LOCK_PATIENCE:
            return snapshot
        sleep(LOCK_RETRY)
        waited += LOCK_RETRY + BUSY_TIMEOUT  # each read may itself wait for the lock


def _connect(path: Path) -> tuple[sqlite3.Connection | None, str, str | None]:
    """The read-only connection, already past its first query, or why not."""
    if not path.exists():
        return None, MISSING, None
    try:
        conn = open_read_only(path)
    except sqlite3.Error as error:
        return None, _state_of(error), _error_name(error)
    try:
        conn.execute("SELECT count(*) FROM sqlite_master").fetchone()  # a hot journal or a lock shows here
    except sqlite3.Error as error:
        conn.close()
        return None, _state_of(error), _error_name(error)
    return conn, OK, None


def _state_of(error: sqlite3.Error) -> str:
    return UNFINISHED_WRITE if _error_name(error) in _BUSY or "locked" in str(error) else UNREADABLE


def _error_name(error: sqlite3.Error) -> str:
    return getattr(error, "sqlite_errorname", None) or type(error).__name__


def _pause_file() -> str | None:
    path = paths.pause_file()
    if not path.exists():
        return None
    try:
        reason = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        reason = ""
    return _clean(reason[:200]) or "PAUSE file present"


def _outbox(folder: Path, since: datetime) -> int:
    """Messages saved to the Discord outbox since the last one-pager."""
    after = since.isoformat(timespec="seconds")
    return sum(
        1
        for day, path in _day_files(folder)
        if day >= since.date()
        for line in _jsonl(path)
        if str(line.get("ts", "")) > after
    )


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def _missing_migrations(conn: sqlite3.Connection, tables: set[str]) -> tuple[str, ...]:
    from jura_growth import db  # the migration list only; never db's connections

    done = {row[0] for row in conn.execute("SELECT id FROM schema_migrations")} if "schema_migrations" in tables else set()
    expected = [f"{owner}/{file.name}" for owner, folder in db.migration_sets() for file in sorted(folder.glob("*.sql"))]
    return tuple(m for m in expected if m not in done)


def _from_db(
    conn: sqlite3.Connection, source: Source, now: datetime, days: tuple[date, ...], installs: dict[str, str], last: datetime
) -> dict:
    """Every fact the database holds, each table only if it is there. A
    lock or a hot journal raises out of here (the snapshot's `db_state`)."""
    tables = _tables(conn)
    since = last.isoformat(timespec="seconds")
    facts: dict[str, Any] = {"missing_migrations": _missing_migrations(conn, tables)}
    if "runs" in tables:
        records = _records(conn, tables, Path(source.data) / "runs", set(source.jobs), days[0])
        loaded = {job for job, state in installs.items() if state != health.NOT_INSTALLED}
        found = slots.classify(source.jobs, records, now, days, installed=loaded)
        facts["slots"] = {key: [_clean_slot(slot) for slot in statuses] for key, statuses in found.items()}
        facts["failures"] = _failures(conn, now)
        facts["yesterday"], facts["spend_today"] = _yesterday(conn, now)
        facts["morning"] = _morning(conn, now)
    if "pause_flags" in tables:
        rows = conn.execute("SELECT agent, reason FROM pause_flags WHERE paused = 1 ORDER BY agent").fetchall()
        facts["paused"] = tuple((_clean(row["agent"]), _clean(row["reason"] or "paused")) for row in rows)
    if "discord_posts" in tables:
        facts["undelivered"] = conn.execute("SELECT count(*) FROM discord_posts WHERE delivered = 0 AND ts > ?", (since,)).fetchone()[0]
    if "approvals" in tables:
        facts["approvals"] = _requests(conn, now, last_one_pager=last)
    facts["plugin_lines"] = _plugin_lines(conn)
    return facts


def _failures(conn: sqlite3.Connection, now: datetime) -> tuple[Failure, ...]:
    day_ago = (now - timedelta(days=1)).isoformat(timespec="seconds")
    rows = conn.execute(
        "SELECT job, started_at, error FROM runs WHERE status = 'failed' AND ("
        " id IN (SELECT max(id) FROM runs WHERE status IN ('ok', 'failed') GROUP BY job) OR started_at >= ?)"
        " ORDER BY started_at, id",
        (day_ago,),
    ).fetchall()
    return tuple(Failure(_clean(row["job"]), timeutil.parse(row["started_at"]).astimezone(SGT), _clean((row["error"] or "")[:300]) or None) for row in rows)


def _yesterday(conn: sqlite3.Connection, now: datetime) -> tuple[Yesterday | None, float]:
    from jura_growth import digest  # build() and spend() only read

    day = (now.date() - timedelta(days=1)).isoformat()
    today = digest.spend(conn, now.date().isoformat())
    try:
        summary = digest.build(conn, day)
    except sqlite3.Error as error:
        if _state_of(error) == UNFINISHED_WRITE:
            raise
        return None, today  # a core table the digest reads isn't there yet
    return _digest_day(day, summary), today


def _morning(conn: sqlite3.Connection, now: datetime) -> Yesterday | None:
    """Today's figures so far, read the way yesterday's are."""
    from jura_growth import digest

    day = now.date().isoformat()
    try:
        return _digest_day(day, digest.build(conn, day))
    except sqlite3.Error as error:
        if _state_of(error) == UNFINISHED_WRITE:
            raise
        return None


def _digest_day(day: str, summary: Mapping[str, Any]) -> Yesterday:
    figures = {key: _masked(value) for key, value in summary["figures"].items()}
    return Yesterday(day, tuple(_clean(line) for line in summary["lines"]), float(summary["claude_cost_usd"] or 0.0), figures)


def _masked(value: Any) -> Any:
    """A figure with every string in it masked, however deep."""
    if isinstance(value, str):
        return _clean(value)
    if isinstance(value, Mapping):
        return {key: _masked(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_masked(item) for item in value]
    return value


def _plugin_lines(conn: sqlite3.Connection) -> tuple[str, ...]:
    """Each plug-in's `health(conn)` lines, given the read-only connection."""
    lines: list[str] = []
    for module in agents.plugins():
        hook = getattr(module, "health", None)
        if not callable(hook):
            continue
        try:
            found: Any = hook(conn)
            lines += [_clean(str(line)) for line in found or () if line]
        except Exception as error:  # noqa: BLE001 - one plug-in never breaks the one-pager
            lines.append(_clean(f"{getattr(module, 'NAME', 'a plug-in')}: its health check failed ({type(error).__name__})"))
    return tuple(lines)


def one_pager_times(now: datetime, jobs: Mapping[str, Mapping[str, Any]]) -> tuple[datetime, datetime]:
    """From the schedule alone: the one-pager this one reports since, and the
    next scheduled one.

    A scheduled one-pager always starts a little after its slot (launchd,
    start-up, `expire_due()`), so a slot less than `ONE_PAGER_GRACE` ago is
    this one-pager itself and the window starts at the slot before it (code
    review 08, B-1). An on-request one-pager later in the day reports since
    that morning's."""
    shape = (jobs.get(ONE_PAGER_JOB) or {}).get("schedule") or ONE_PAGER_DEFAULT
    times = [at for offset in range(-8, 9) for at in slots.slot_times(shape, now.date() + timedelta(days=offset))]
    before = [at for at in times if at <= now - ONE_PAGER_GRACE]
    after = [at for at in times if at > now]
    return (before[-1] if before else now - timedelta(days=1)), (after[0] if after else now + timedelta(days=1))


def _last_one_pager(conn: sqlite3.Connection, now: datetime, scheduled: datetime) -> datetime:
    """When the last one-pager went out: the start of the latest `one-pager`
    run that finished ok, so a day the Mac slept through doesn't drop what
    happened then. Without one in the last week, the scheduled time. The run
    still going (this one) isn't ok yet, so it never counts."""
    if "runs" not in _tables(conn):
        return scheduled
    found = conn.execute(
        "SELECT max(started_at) FROM runs WHERE job = ? AND status = 'ok' AND started_at < ?",
        (ONE_PAGER_JOB, now.isoformat(timespec="seconds")),
    ).fetchone()[0]
    if not found:
        return scheduled
    ran = timeutil.parse(found).astimezone(SGT)
    return ran if ran >= now - ONE_PAGER_LOOKBACK else scheduled


# --- approval requests ----------------------------------------------------------------


def _requests(conn: sqlite3.Connection, now: datetime, *, last_one_pager: datetime) -> tuple[Request, ...]:
    """Live requests, and those decided or closed since the last one-pager.
    Its own SELECT: approvals.py may supersede on a read, which is a write."""
    since = last_one_pager.isoformat(timespec="seconds")
    rows = conn.execute(
        "SELECT id, kind, status, requested_at, decide_by, use_by, decided_at, used_at, posted_at, close_reason, reason"
        " FROM approvals WHERE (status IN ('pending', 'approved') AND used_at IS NULL) OR decided_at > ? OR closed_at > ?"
        " ORDER BY requested_at, id",
        (since, since),
    ).fetchall()
    return tuple(_request(row, now) for row in rows)


def _request(row: sqlite3.Row, now: datetime) -> Request:
    decide_by = timeutil.parse(row["decide_by"]).astimezone(SGT)
    use_by = timeutil.parse(row["use_by"]).astimezone(SGT) if row["use_by"] else None
    status = row["status"]
    if status == "pending":
        reading = Reading.WAITING if now < decide_by else Reading.LAPSED
    elif status == "approved" and row["used_at"]:
        reading = Reading.USED
    elif status == "approved":
        reading = Reading.APPROVED if use_by is None or now < use_by else Reading.LAPSED_UNUSED
    elif status == "expired":
        reading = Reading.LAPSED_UNUSED if row["decided_at"] else Reading.LAPSED  # expired after a yes, or unanswered
    else:
        reading = Reading.SKIPPED if status == "skipped" else Reading.SUPERSEDED
    return Request(
        id=f"A-{row['id']:04d}",
        kind=_clean(row["kind"]),
        reading=reading,
        requested_at=timeutil.parse(row["requested_at"]).astimezone(SGT),
        decide_by=decide_by,
        use_by=use_by,
        posted=row["posted_at"] is not None,
        close_reason=_clean_or_none(row["close_reason"]),
        reason=_clean(row["reason"] or ""),
    )


# --- records for the slot classifier (MC §4.5) -------------------------------------

TRACES = (slots.SKIPPED, slots.QUIET)  # the record kinds the mirror holds


def _records(conn: sqlite3.Connection, tables: set[str], mirror: Path, jobs: set[str], first: date) -> list[slots.Record]:
    """Each record once: those on the days shown, plus the latest before them
    for each job. Without that earlier record the classifier would call a job
    installed before the window "not installed" (code review 07, S-5).

    Runs, and the skip rows of jobs that aren't quiet, come from `runs`;
    `run.skipped` and `run.quiet` from `events` and the JSONL mirror, which
    hold the same record twice (the PAUSE-file and lock skips reach only the
    mirror). The dedupe key is `Record.key` (MC §4.5)."""
    start = _stamp(first)
    found: dict[tuple, slots.Record] = {}

    def add(make: Callable[[Any], slots.Record], row: Any) -> None:
        record = _record(make, row)
        if record is not None:
            found.setdefault(record.key, record)

    run_columns = "SELECT job, started_at, status, summary FROM runs"
    for row in conn.execute(f"{run_columns} WHERE started_at >= ?", (start,)):
        add(slots.Record.from_run, row)
    for row in conn.execute(f"{run_columns} WHERE id IN (SELECT max(id) FROM runs WHERE started_at < ? GROUP BY job)", (start,)):
        add(slots.Record.from_run, row)
    if "events" in tables:
        kinds = ",".join("?" * len(TRACES))
        event_columns = f"SELECT kind, ts, payload_json FROM events WHERE kind IN ({kinds})"
        for row in conn.execute(f"{event_columns} AND ts >= ?", (*TRACES, start)):
            add(slots.Record.from_event, row)
        latest = f"SELECT max(id) FROM events WHERE kind IN ({kinds}) AND ts < ? GROUP BY json_extract(payload_json, '$.job')"
        for row in conn.execute(f"{event_columns} AND id IN ({latest})", (*TRACES, *TRACES, start)):
            add(slots.Record.from_event, row)
    for line in _mirror_since(mirror, first):
        add(slots.Record.from_event, line)

    covered = {record.job for record in found.values() if record.at < timeutil.midnight(first)}
    for line in _mirror_before(mirror, first, jobs - covered):
        add(slots.Record.from_event, line)
    return list(found.values())


def _record(make: Callable[[Any], slots.Record], row: Any) -> slots.Record | None:
    try:
        record = make(row)
        record.at  # noqa: B018 - a stamp that doesn't parse is dropped here, not in the classifier
        return record
    except (KeyError, TypeError, ValueError):
        return None


def _day_files(folder: Path) -> list[tuple[date, Path]]:
    found = []
    try:
        for path in folder.glob("*.jsonl"):
            try:
                found.append((date.fromisoformat(path.stem), path))
            except ValueError:
                continue
    except OSError:
        return []
    return sorted(found)


def _jsonl(path: Path) -> Iterator[dict]:
    """The JSON objects in a JSONL file (the mirror, the outbox). A line cut
    short by a crash is skipped."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for raw in text.splitlines():
        try:
            line = json.loads(raw)
        except ValueError:
            continue
        if isinstance(line, dict):
            yield line


def _lines(path: Path) -> Iterator[dict]:
    """The trace lines of one mirror file."""
    for line in _jsonl(path):
        if line.get("kind") in TRACES and isinstance(line.get("payload"), dict) and isinstance(line.get("ts"), str):
            yield line


def _mirror_since(folder: Path, first: date) -> Iterator[dict]:
    """Trace lines in the files from `first` on. A line lands in a later
    day's file when its transaction commits after midnight, never an earlier one."""
    for day, path in _day_files(folder):
        if day >= first:
            yield from _lines(path)


def _mirror_before(folder: Path, first: date, wanted: set[str]) -> Iterator[dict]:
    """The latest trace before `first` for each job in `wanted`, reading
    older files newest first and stopping once every job has one."""
    wanted = set(wanted)
    for day, path in reversed(_day_files(folder)):
        if not wanted:
            return
        if day >= first:
            continue
        latest: dict[str, dict] = {}
        for line in _lines(path):
            job = line["payload"].get("job")
            if job in wanted and (job not in latest or line["ts"] > latest[job]["ts"]):
                latest[job] = line
        yield from latest.values()
        wanted -= set(latest)


def _stamp(day: date) -> str:
    return timeutil.midnight(day).isoformat(timespec="seconds")


# --- redaction ------------------------------------------------------------------------


def _clean(text: str) -> str:
    return privacy.for_discord(text) if text else text


def _clean_or_none(text: str | None) -> str | None:
    return _clean(text) if text else None


def _clean_slot(slot: slots.SlotStatus) -> slots.SlotStatus:
    """A slot as the one-pager may show it: its reason masked, and without
    the raw records behind it."""
    return dataclasses.replace(slot, reason=_clean_or_none(slot.reason), records=())
