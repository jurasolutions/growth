"""`jura-growth`: every side effect in the growth engine goes through here.

Headless Claude runs may call this command and nothing else that changes
state, so the limits that matter (caps, suppression, the brand gate, pause
flags) live in code where a prompt can't talk its way past them.
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

import click

from jura_growth import (
    agents,
    backup as backup_mod,
    brand_check,
    config,
    copy_check,
    db,
    digest as digest_mod,
    discord,
    headless,
    holidays,
    log,
    pause as pause_mod,
    paths,
    runner,
    schedule as schedule_mod,
    suppression,
    timeutil,
)


class _Cli(click.Group):
    """Everything a command prints, errors included, has secret values masked
    (`config.redacted_output`), however it is invoked."""

    def main(self, *args, **kwargs):
        with config.redacted_output():
            return super().main(*args, **kwargs)


@click.group(cls=_Cli, context_settings={"help_option_names": ["-h", "--help"]})
def cli() -> None:
    """Jura growth engine."""
    config.reset_caches()


def main() -> None:
    with config.redacted_output():
        try:
            cli(prog_name="jura-growth")
        except Exception:  # noqa: BLE001 - print the traceback with secrets masked
            traceback.print_exc()
            sys.exit(1)


# --- check -----------------------------------------------------------------


@cli.command()
@click.argument("text", required=False)
@click.option("--file", "file_", type=click.Path(exists=True, dir_okay=False, path_type=Path), help="Read the text from a file.")
@click.option("--subject", help="Subject line (email).")
@click.option("--heading", "headings", multiple=True, help="A heading; repeatable.")
@click.option("--button", "buttons", multiple=True, help="A button label; repeatable.")
@click.option("--channel", "channel_name", help="Channel whose own rules apply (see `jura-growth channels`).")
@click.option("--source", "sources", multiple=True, help="A cited source URL; repeatable.")
@click.option("--proper-noun", "proper_nouns", multiple=True, help="A name the sentence-case check accepts.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
def check(text, file_, subject, headings, buttons, channel_name, sources, proper_nouns, as_json) -> None:
    """Brand-check TEXT (or --file, or stdin with "-"). Exit 1 on fail."""
    if file_:
        text = file_.read_text(encoding="utf-8")
    elif text == "-" or (text is None and not sys.stdin.isatty()):
        text = sys.stdin.read()
    text = text or ""
    result = brand_check.check(
        text,
        subject=subject,
        headings=headings,
        buttons=buttons,
        channel_name=channel_name,
        sources=sources,
        proper_nouns=proper_nouns,
    )
    if as_json:
        click.echo(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    elif result.passed:
        click.echo("pass")
    else:
        click.echo("fail")
        for reason in result.reasons():
            click.echo(f"  - {reason}")
    sys.exit(0 if result.passed else 1)


@cli.command("check-copy")
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--channel", "channel_name")
def check_copy(files, channel_name) -> None:
    """Brand-check every user-facing string in copy FILES (.js, .json, .md)."""
    failed = 0
    total = 0
    for path in files:
        for item, result in copy_check.check_file(path, channel_name):
            total += 1
            if not result.passed:
                failed += 1
                click.echo(f"{path}:{item.where}: {item.text[:90]!r}")
                for reason in result.reasons():
                    click.echo(f"    - {reason}")
    click.echo(f"{total - failed} of {total} strings pass")
    sys.exit(1 if failed else 0)


@cli.command()
def channels() -> None:
    """List brand-check channels."""
    for name, spec in sorted(brand_check.channels().items()):
        sources = "sources allowed" if spec.allow_sources else "jurasolutions.sg links only"
        click.echo(f"{name:24} {sources:28} {spec.description}")


# --- log, db ---------------------------------------------------------------


@cli.group("log")
def log_group() -> None:
    """The run log."""


@log_group.command("test")
def log_test() -> None:
    """Write a test event to the database and the JSONL mirror."""
    with db.session() as conn:
        log.event(conn, "log.test", {"note": "test event from `jura-growth log test`"})
        event_id = db.scalar(conn, "SELECT max(id) FROM events")
    click.echo(f"event {event_id} written to {paths.db_path()}")
    click.echo(f"mirrored to {paths.data_dir() / 'runs' / (timeutil.today_str() + '.jsonl')}")


@log_group.command("events")
@click.option("--limit", default=20, show_default=True)
@click.option("--kind", help="Only events whose kind starts with this.")
def log_events(limit, kind) -> None:
    """Show recent events."""
    with db.session() as conn:
        sql = "SELECT id, ts, agent, level, kind, payload_json FROM events"
        params: tuple = ()
        if kind:
            sql += " WHERE kind LIKE ?"
            params = (kind + "%",)
        sql += " ORDER BY id DESC LIMIT ?"
        for row in reversed(db.rows(conn, sql, params + (limit,))):
            click.echo(f"{row['id']:>6} {row['ts']} {row['agent'] or '-':12} {row['level']:7} {row['kind']:22} {row['payload_json'][:120]}")


@cli.group("db")
def db_group() -> None:
    """Database housekeeping."""


@db_group.command("migrate")
def db_migrate() -> None:
    conn = db.connect(migrate_now=False)
    applied = db.migrate(conn)
    conn.close()
    click.echo("\n".join(applied) if applied else "up to date")


@db_group.command("path")
def db_path() -> None:
    click.echo(paths.db_path())


@cli.command()
def backup() -> str:
    """Back up growth.db (kept 14 days) and prune old transcripts."""
    with db.session() as conn:
        target = backup_mod.backup(conn)
    click.echo(f"backup written: {target}")
    return f"backup written: {target.name}"


# --- discord ---------------------------------------------------------------


@cli.group("discord")
def discord_group() -> None:
    """Discord webhooks."""


@discord_group.command("test")
def discord_test() -> None:
    """Post a test message to every channel."""
    ok = True
    with db.session() as conn:
        for channel in discord.channels():
            result = discord.post(
                conn,
                channel,
                f"Test post from `jura-growth` to #{channel} at {timeutil.stamp()}.",
                username="Jura growth · setup",
                dedupe=False,
            )
            mark = "posted" if result.delivered else f"NOT POSTED ({result.reason})"
            ok = ok and result.delivered
            click.echo(f"#{channel:18} {mark}")
    sys.exit(0 if ok else 1)


@discord_group.command("post")
@click.argument("channel")
@click.argument("text")
@click.option("--file", "files", multiple=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
def discord_post(channel, text, files) -> None:
    """Post TEXT to CHANNEL (internal notes only; agent output has its own commands)."""
    with db.session() as conn:
        result = discord.post(conn, channel, text, files=list(files), username=f"Jura growth · {log.current_agent() or 'manual'}")
    click.echo("posted" if result.delivered else f"not posted: {result.reason}")


# --- pause, resume, status -------------------------------------------------


def _known_agents() -> list[str]:
    names = {spec["agent"] for spec in runner.jobs().values()}
    names |= {m.NAME for m in agents.plugins() if getattr(m, "NAME", None)}
    return sorted(names)


@cli.command()
@click.argument("agent")
@click.option("--reason", default="paused by hand", show_default=True)
def pause(agent, reason) -> None:
    """Pause AGENT, or `all`."""
    if agent != "all" and agent not in _known_agents():
        raise click.BadParameter(f"unknown agent; known: all, {', '.join(_known_agents())}")
    with db.session() as conn:
        pause_mod.pause(conn, agent, reason)
    click.echo(f"paused {agent}")


@cli.command()
@click.argument("agent")
def resume(agent) -> None:
    """Resume AGENT, or `all`. (The PAUSE file has to be deleted by hand.)"""
    with db.session() as conn:
        pause_mod.resume(conn, agent)
    click.echo(f"resumed {agent}")
    if pause_mod.pause_file_active():
        click.echo(f"note: {paths.pause_file()} still exists and pauses everything")


@cli.command()
def status() -> None:
    """Pause state, last runs, Discord setup and schedule."""
    click.echo(f"database   {paths.db_path()}")
    if pause_mod.pause_file_active():
        click.echo(f"PAUSE FILE {paths.pause_file()} (everything is paused)")
    with db.session() as conn:
        flags = pause_mod.flags(conn)
        click.echo("paused     " + (", ".join(f"{f['agent']} ({f['reason']})" for f in flags) if flags else "nothing"))
        click.echo("")
        click.echo(f"{'job':16} {'schedule':40} {'installed':10} last run")
        for name, spec in runner.jobs().items():
            last = db.one(conn, "SELECT status, started_at FROM runs WHERE job = ? ORDER BY id DESC LIMIT 1", (name,))
            last_text = f"{last['status']} {last['started_at']}" if last else "never"
            click.echo(f"{name:16} {schedule_mod.describe(spec):40} {'yes' if schedule_mod.installed(name) else 'no':10} {last_text}")
    click.echo("")
    configured = [c for c in discord.channels() if discord.webhook(c)]
    click.echo(f"discord    {len(configured)} of {len(discord.channels())} channel webhooks set")
    loaded = ", ".join(m.NAME for m in agents.plugins() if getattr(m, "NAME", None)) or "none"
    click.echo(f"agents     {loaded}")
    for name, error in agents.BROKEN.items():
        click.echo(f"BROKEN     agent plug-in {name}: {error}")
    note = holidays.coverage_warning()
    if note:
        click.echo(f"holidays   {note}")
    tz = schedule_mod.tz_note()
    if tz:
        click.echo(f"timezone   {tz}")


# --- run, schedule, heartbeat, digest --------------------------------------


@cli.command()
@click.argument("job")
@click.option("--ignore-schedule", is_flag=True, help="Run even on a weekend or holiday (manual runs).")
@click.option("--dry-run", is_flag=True, help="Print what would run, without running it.")
def run(job, ignore_schedule, dry_run) -> None:
    """Run a scheduled JOB now (what launchd calls)."""
    spec = runner.job(job)
    if dry_run:
        if spec["kind"] == "claude":
            argv, prompt = runner.claude_command(job, spec)
            click.echo(" ".join(argv))
            click.echo(f"\n(prompt: {len(prompt)} chars from prompts/{spec['prompt']}, sent on stdin)")
        else:
            click.echo("jura-growth " + " ".join(spec["command"]))
        return
    outcome = runner.run(job, ignore_schedule=ignore_schedule)
    click.echo(f"{job}: {outcome.status}" + (f": {outcome.summary}" if outcome.summary else "") + (f" ({outcome.error})" if outcome.error else ""))
    sys.exit(1 if outcome.status == "failed" else 0)


@cli.group("schedule")
def schedule_group() -> None:
    """launchd jobs."""


@schedule_group.command("list")
def schedule_list() -> None:
    for name, spec in runner.jobs().items():
        click.echo(f"{name:16} {spec['kind']:8} {schedule_mod.describe(spec)}")
    note = schedule_mod.tz_note()
    if note:
        click.echo(note)


@schedule_group.command("render")
@click.argument("jobs", nargs=-1)
def schedule_render(jobs) -> None:
    """Write plists to launchd/generated/ without installing them."""
    for path in schedule_mod.render(list(jobs) or None):
        click.echo(path)


@schedule_group.command("install")
@click.argument("jobs", nargs=-1)
def schedule_install(jobs) -> None:
    """Install and load JOBS (default: all) into launchd."""
    for name in schedule_mod.install(list(jobs) or None):
        click.echo(f"loaded {name}")


@schedule_group.command("uninstall")
@click.argument("jobs", nargs=-1)
def schedule_uninstall(jobs) -> None:
    """Unload and remove JOBS (default: all) from launchd."""
    removed = schedule_mod.uninstall(list(jobs) or None)
    click.echo("\n".join(f"removed {n}" for n in removed) if removed else "nothing installed")


@cli.command()
def heartbeat() -> str:
    """Post a heartbeat to #daily-digest (proves the scheduler is alive)."""
    with db.session() as conn:
        installed = sum(1 for name in runner.jobs() if schedule_mod.installed(name))
        text = f"Heartbeat {timeutil.stamp()}: the scheduler is running ({installed} of {len(runner.jobs())} jobs loaded)."
        result = discord.post(conn, "daily-digest", text, username="Jura growth · heartbeat", dedupe=False)
    click.echo(text if result.delivered else f"{text} (not posted: {result.reason})")
    return "heartbeat posted" if result.delivered else f"heartbeat not posted: {result.reason}"


@cli.command()
@click.option("--date", "day", help="SGT date, default today.")
@click.option("--no-post", is_flag=True, help="Write the files without posting to Discord.")
def digest(day, no_post) -> str:
    """Write today's summary and post it to #daily-digest."""
    with db.session() as conn:
        summary = digest_mod.run(conn, day, post=not no_post)
    click.echo(digest_mod.render(summary))
    click.echo("")
    click.echo(summary["brief_line"])
    return summary["brief_line"]


# --- suppression -----------------------------------------------------------


@cli.group("suppression")
def suppression_group() -> None:
    """The shared do-not-send list."""


@suppression_group.command("add")
@click.argument("email_or_domain")
@click.option("--reason", type=click.Choice(["unsubscribe", "bounce", "complaint", "manual"]), default="manual", show_default=True)
def suppression_add(email_or_domain, reason) -> None:
    """Suppress an address, or a whole domain."""
    with db.session() as conn:
        if "@" in email_or_domain:
            new = suppression.add(conn, email=email_or_domain, reason=reason, source="cli")
        else:
            new = suppression.add(conn, domain=email_or_domain, reason=reason, source="cli")
    click.echo("suppressed" if new else "already suppressed")


@suppression_group.command("check")
@click.argument("email")
def suppression_check(email) -> None:
    with db.session() as conn:
        reason = suppression.is_suppressed(conn, email)
    click.echo(f"suppressed: {reason}" if reason else "not suppressed")
    sys.exit(1 if reason else 0)


# --- agent plug-ins --------------------------------------------------------

for _module in agents.plugins():
    _register = getattr(_module, "register", None)
    if _register:
        _register(cli)

headless.install(cli)
