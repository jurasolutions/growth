"""`jura-growth social ...`"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import click

from jura_growth import brand_check, db, paths, timeutil
from jura_growth.agents.social import history, plan as plan_mod, render, submit as submit_mod
from jura_growth.agents.social.settings import PLATFORMS, load


def _day(value: str | None) -> date:
    if not value or value == "today":
        return timeutil.today()
    if value == "tomorrow":
        return timeutil.today() + timedelta(days=1)
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise click.BadParameter(f"{value!r} is not a date (YYYY-MM-DD, today or tomorrow)") from None


@click.group("social")
def social() -> None:
    """Daily LinkedIn, Facebook and Instagram drafts (social PRD)."""


@social.command()
@click.option("--date", "day", help="SGT date (default today).")
@click.option("--json", "as_json", is_flag=True)
def today(day, as_json) -> None:
    """Today's theme, platform rules, 14-day history and toolbox tools."""
    with db.session() as conn:
        plan = plan_mod.build(conn, _day(day))
    click.echo(json.dumps(plan, indent=2, ensure_ascii=False) if as_json else plan_mod.render_text(plan))


@social.command()
@click.argument("folder", type=click.Path(file_okay=False, path_type=Path))
@click.option("--theme", "theme_id", help="Theme id, when today's doesn't fit and you take the next one.")
@click.option("--offline", is_flag=True, help="Render without the web fonts or network (testing).")
def submit(folder, theme_id, offline) -> str:
    """Check, render, save, log and post the drafts in FOLDER."""
    from jura_growth.agents.publish.fixture import FixtureRefused

    with db.session() as conn:
        try:
            outcome = submit_mod.submit(conn, folder, theme_id=theme_id, offline=offline)
        except FixtureRefused as refused:  # the publish rehearsal's fixture platform, set but refused (BP-07)
            raise click.ClickException(f"refused: {refused}") from None
    click.echo(outcome.text())
    if outcome.exit_code:
        sys.exit(outcome.exit_code)
    return outcome.lines[0] if outcome.lines else outcome.status


@social.command("render")
@click.argument("spec_file", metavar="SPEC", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--out", "out_dir", required=True, type=click.Path(file_okay=False, path_type=Path), help="Folder for the PNGs.")
@click.option(
    "--size", "sizes", multiple=True,
    help=f"A named size ({', '.join(render.SIZES)}) or WIDTHxHEIGHT; repeatable. Default: linkedin, facebook, instagram.",
)
@click.option("--carousel", type=int, default=1, show_default=True, help="Slides for portrait sizes (cover plus items).")
@click.option("--source", "sources", multiple=True, help="A source URL the card's figures come from; repeatable.")
@click.option("--prefix", default="", help="Filename prefix.")
@click.option("--offline", is_flag=True, help="Don't load the web fonts (no network).")
def render_cmd(spec_file, out_dir, sizes, carousel, sources, prefix, offline) -> None:
    """Render a card SPEC (JSON) to PNG, after a brand check of its words."""
    spec, problems = render.load_spec(spec_file)
    if problems:
        click.echo("refused:\n" + "\n".join(f"  - {p}" for p in problems))
        sys.exit(2)
    result = brand_check.check(
        spec.body(), headings=spec.headings(), channel_name="social-card", sources=sources, proper_nouns=spec.proper_nouns
    )
    if not result.passed:
        click.echo("refused: the card's words fail the brand check")
        for reason in result.reasons():
            click.echo(f"  - {reason}")
        sys.exit(1)
    plan = []
    for size in sizes or ("linkedin", "facebook", "instagram"):
        if size in render.SIZES:
            plan.append((size, *render.SIZES[size]))
        else:
            try:
                width, height = (int(v) for v in size.lower().split("x"))
            except ValueError:
                raise click.BadParameter(f"unknown size {size!r}") from None
            plan.append((f"{width}x{height}", width, height))
    portrait = {name: carousel for name, w, h in plan if h > w and carousel > 1}
    try:
        made = render.render_spec(spec, plan, out_dir, carousel=portrait, offline=offline, prefix=prefix)
    except render.RenderError as error:
        click.echo(f"render failed: {error}")
        sys.exit(1)
    for files in made.values():
        for path in files:
            width, height = render.png_size(path)
            click.echo(f"{path}  {width}×{height}")



@social.command()
@click.argument("day", metavar="DATE")
@click.argument("platform", type=click.Choice([*PLATFORMS, "all"]))
@click.option("--reason", default="skipped by hand", show_default=True)
def skip(day, platform, reason) -> None:
    """Don't post PLATFORM's draft for DATE (YYYY-MM-DD, today or tomorrow)."""
    target = _day(day)
    chosen = PLATFORMS if platform == "all" else (platform,)
    with db.session() as conn:
        for name in chosen:
            try:
                outcome = history.skip(conn, target, name, reason)
            except ValueError as error:
                click.echo(f"{name}: {error}")
                continue
            click.echo(f"{target} {name}: {outcome}")


@social.command()
@click.argument("day", metavar="DATE")
@click.argument("platform", type=click.Choice(PLATFORMS))
@click.option("--url", help="The live post's address.")
def published(day, platform, url) -> None:
    """Record that PLATFORM's draft for DATE went out (posted by hand)."""
    with db.session() as conn:
        try:
            history.mark_published(conn, _day(day), platform, url)
        except ValueError as error:
            raise click.ClickException(str(error)) from None
    click.echo(f"{day} {platform}: published" + (f" ({url})" if url else ""))


@social.command("no-draft")
@click.argument("reason")
def no_draft(reason) -> str:
    """Post “No draft today” with REASON to #social-drafts."""
    day = timeutil.today()
    with db.session() as conn:
        if history.drafted_platforms(conn, day):
            raise click.ClickException("drafts were already delivered today")
        submit_mod.post_no_draft(conn, day, reason)
    click.echo(f"No draft today: {reason}")
    return f"no draft today: {reason}"


@social.command("history")
@click.option("--days", default=14, show_default=True)
@click.option("--json", "as_json", is_flag=True)
def history_cmd(days, as_json) -> None:
    """Posts from the last DAYS days."""
    with db.session() as conn:
        rows = history.recent(conn, timeutil.today(), days)
    if as_json:
        click.echo(json.dumps(rows, indent=2, ensure_ascii=False, default=str))
        return
    if not rows:
        click.echo(f"no social posts in the last {days} days")
        return
    for row in rows:
        tool = f" tool={row['tool_slug']}" if row["tool_slug"] else ""
        click.echo(f"{row['date']} {row['platform']:9} {row['status']:9} {row['theme']}{tool}")
        for url in row["source_urls"]:
            click.echo(f"    {url}")
        if row["published_url"]:
            click.echo(f"    live: {row['published_url']}")


@social.command("setup-images")
@click.option("--out", "out_dir", type=click.Path(file_okay=False, path_type=Path), help="Default: outputs/growth/setup/social-images/")
@click.option("--offline", is_flag=True)
def setup_images(out_dir, offline) -> None:
    """Render the profile picture and the LinkedIn and Facebook covers."""
    out_dir = out_dir or paths.outputs_dir() / "setup" / "social-images"
    spec = render.CardSpec(layout="headline", **render.SETUP_COPY)
    result = brand_check.check(spec.body(), headings=spec.headings(), channel_name="social-card")
    if not result.passed:
        raise click.ClickException("setup copy fails the brand check: " + "; ".join(result.reasons()))
    for path in render.render_setup(out_dir, settings=load(), offline=offline):
        width, height = render.png_size(path)
        click.echo(f"{path}  {width}×{height}")


def register(cli: click.Group) -> None:
    cli.add_command(social)
