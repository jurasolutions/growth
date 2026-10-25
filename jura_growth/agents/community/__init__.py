"""The community scout (prd-jura-community-scout-2026-10-24.md, blocks 1 and 2).

Every Monday at 07:30 SGT a headless run researches Singapore SME groups by
web search (never fetching facebook.com), records them with
`community add-group`, and, once Ting Yu has joined some good-fit groups,
drafts a weekly plan of value-first posts and reply ideas that he posts
himself. Nothing is ever posted to Facebook by code.

Commands: `jura-growth community context | add-group | groups | set |
plan-add | publish-plan | posted | removed | sync-ticks | summary | audit-run`.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

import click

from jura_growth import brand_check, db, discord, log, timeutil
from jura_growth.agents.community import groups as groups_mod
from jura_growth.agents.community import plan as plan_mod
from jura_growth.agents.community import rules as rules_mod
from jura_growth.agents.community import transcript

NAME = groups_mod.NAME
MIGRATIONS = Path(__file__).parent / "migrations"


# --- plug-in interface -------------------------------------------------------


def channels() -> dict[str, brand_check.Channel]:
    return {
        plan_mod.POST_CHANNEL: brand_check.Channel(
            plan_mod.POST_CHANNEL,
            check=plan_mod.post_channel_check,
            description="Facebook group post: 60-150 words, links only in the closing line with utm tags",
        ),
        plan_mod.REPLY_CHANNEL: brand_check.Channel(
            plan_mod.REPLY_CHANNEL,
            check=plan_mod.reply_channel_check,
            description="Helpful reply idea for a group thread: no links",
        ),
    }


def permissions(job: str):
    """The `jura-growth` commands `prompts/community.md` uses. Joining a
    group, confirming its rules and recording posts or removals (`set`,
    `posted`, `removed`) are Ting Yu's steps.

    The run may not fetch any blocked domain or its subdomains
    (`groups.fetch_denials()`)."""
    if job != "community":
        return None
    from jura_growth.headless import Permissions

    return Permissions(
        commands=(
            "community context", "community add-group", "community summary",
            "community plan-add", "community publish-plan", "social render", "check",
        ),
        disallowed_tools=groups_mod.fetch_denials(),
    )


def precheck(job: str, conn: sqlite3.Connection) -> str | None:
    return None  # the register part runs every Monday, even with nothing joined


def digest(conn: sqlite3.Connection, day: str) -> dict:
    counts = groups_mod.counts(conn)
    week = timeutil.iso_week(date.fromisoformat(day))
    planned = db.scalar(
        conn, "SELECT count(*) FROM community_posts WHERE week = ? AND kind = 'post' AND status != 'skipped'", (week,)
    ) or 0
    posted = db.scalar(
        conn, "SELECT count(*) FROM community_posts WHERE week = ? AND kind = 'post' AND status = 'posted'", (week,)
    ) or 0
    figures = {
        "community_groups": counts.get("total", 0),
        "community_good_fit": counts.get("good_fit", 0),
        "community_joined": counts.get("joined", 0),
        "community_posts_planned": planned,
        "community_posts_posted": posted,
    }
    lines, brief = [], []
    if counts.get("total"):
        lines.append(
            f"Community: {counts['total']} groups in the register ({counts['good_fit']} good fit, {counts['joined']} joined); "
            f"{week}: {planned} post{'s' if planned != 1 else ''} planned, {posted} posted."
        )
        brief.append(f"community: {posted} of {planned} posts done this week" if planned else f"community: {counts['total']} groups, {counts['joined']} joined")
    # Audit today's headless community runs: the run log must show no Facebook fetches.
    audits_clean = None
    for run in db.rows(
        conn,
        "SELECT id FROM runs WHERE agent = ? AND status IN ('ok', 'failed') AND substr(started_at, 1, 10) = ? ORDER BY id",
        (NAME, day),
    ):
        report = audit(run["id"])
        if report.get("transcript"):
            lines.append(f"Community run {run['id']} audit: {'clean' if report['clean'] else report['verdict']}")
            audits_clean = bool(report["clean"]) and audits_clean is not False
            if not report["clean"]:
                brief.append(f"community run {run['id']} audit not clean")
    figures["community_audit_clean"] = audits_clean
    return {"figures": figures, "lines": lines, "brief": brief}


RUN_UPDATE_CHANNEL = "community"


def run_update(conn: sqlite3.Connection, run) -> list[str]:
    """The "Produced:" items of a community run: groups it added to the
    register, and the posts and reply ideas it planned."""
    from jura_growth.run_update import count

    groups = db.scalar(conn, "SELECT count(*) FROM community_groups WHERE run_id = ?", (run.id,)) or 0
    planned = dict(
        (r["kind"], r["n"])
        for r in db.rows(conn, "SELECT kind, count(*) AS n FROM community_posts WHERE run_id = ? GROUP BY kind", (run.id,))
    )
    produced = []
    if groups:
        produced.append(count(groups, "new group"))
    if planned.get("post"):
        produced.append(count(planned["post"], "planned post"))
    if planned.get("reply_idea"):
        produced.append(count(planned["reply_idea"], "reply idea"))
    return produced


# --- commands ----------------------------------------------------------------


def register(cli: click.Group) -> None:
    cli.add_command(community)


@click.group("community")
def community() -> None:
    """The community scout: SME group register and weekly posting plans."""


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise click.BadParameter(f"{path} is not valid JSON: {error}") from None


@community.command("add-group")
@click.option("--file", "file_", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="JSON: one group, a list of groups, or {\"groups\": [...]}.")
def add_group_cmd(file_) -> str:
    """Add groups to the register (deduped by URL; no Facebook source URLs)."""
    data = _load_json(file_)
    if isinstance(data, dict):
        records = data["groups"] if "groups" in data else [data]
    else:
        records = data
    if not isinstance(records, list):
        raise click.BadParameter("expected a group object or a list of them")
    tally = {"added": 0, "duplicate": 0, "rejected": 0}
    with db.session() as conn:
        for index, record in enumerate(records, 1):
            status, group_id, messages = groups_mod.add(conn, record)
            tally[status] += 1
            name = record.get("name", "?") if isinstance(record, dict) else "?"
            head = f"{index}. {name}: {status}" + (f" as group {group_id}" if status == "added" else "")
            click.echo(head)
            for message in messages:
                click.echo(f"     - {message}")
    summary = f"{tally['added']} added, {tally['duplicate']} already known, {tally['rejected']} rejected"
    click.echo(summary)
    if tally["rejected"] and not tally["added"] and not tally["duplicate"]:
        sys.exit(1)
    return summary


@community.command("groups")
@click.option("--fit", type=click.Choice(list(groups_mod.FITS)))
@click.option("--joined", is_flag=True, help="Only joined groups.")
@click.option("--channel")
@click.option("--json", "as_json", is_flag=True)
def groups_cmd(fit, joined, channel, as_json) -> None:
    """The register."""
    with db.session() as conn:
        rows = groups_mod.all_groups(conn)
    rows = [r for r in rows if (not fit or r["fit"] == fit) and (not joined or r["joined"]) and (not channel or r["channel"] == channel)]
    if as_json:
        for r in rows:
            r["source_urls"] = json.loads(r.pop("source_urls_json") or "[]")
            r["rules_parsed"] = groups_mod.rules_for(r).as_dict()
        click.echo(json.dumps(rows, indent=2, ensure_ascii=False))
        return
    if not rows:
        click.echo("no groups in the register yet")
        return
    for r in rows:
        flags = ", ".join(f for f, on in (("joined", r["joined"]), ("rules confirmed", r["rules_confirmed"]), ("removed", r["removed"])) if on)
        click.echo(f"{r['id']:>4}  {r['name']}  [{r['channel']}, {r['fit']}" + (f", {flags}" if flags else "") + "]")
        click.echo(f"      {r['url']}")
        click.echo(f"      audience: {r['audience'] or '-'}; size: {r['size_hint'] or '-'}; activity: {r['active_hint'] or '-'}")
        rules = groups_mod.rules_for(r)
        click.echo(f"      rules: {r['promo_rules'] or '-'}  ->  {rules.summary()}"
                   + (f" ({rules_mod.TIMING_HINT})" if rules.mentions_timing else ""))
        click.echo(f"      fit: {r['fit_reason']}")
        click.echo(f"      utm_campaign: {r['slug']}; sources: {', '.join(json.loads(r['source_urls_json'] or '[]'))}")


@community.command("set", context_settings={"ignore_unknown_options": True})
@click.argument("group_id", type=int)
@click.argument("pairs", nargs=-1, required=True)
def set_cmd(group_id, pairs) -> None:
    """Update a group: joined=yes rules="..." rules_confirmed=yes promo_days=... post_days=... [fit=...] [notes=...].

    Confirming rules needs both day keys: each any, none, or days like sat,sun
    or mon-fri. New rules text clears the confirmed days."""
    with db.session() as conn:
        try:
            group = groups_mod.set_fields(conn, group_id, list(pairs))
        except groups_mod.GroupError as error:
            raise click.ClickException(str(error)) from None
    click.echo(
        f"group {group['id']} {group['name']}: fit {group['fit']}, joined {'yes' if group['joined'] else 'no'}, "
        f"rules confirmed {'yes' if group['rules_confirmed'] else 'no'}; rules: {group['promo_rules'] or '-'} "
        f"({groups_mod.rules_for(group).summary()})"
    )


@community.command("removed")
@click.argument("group_id", type=int)
@click.option("--reason", default="an admin removed a post or warned Ting Yu", show_default=True)
def removed_cmd(group_id, reason) -> None:
    """A group's admin removed a post or warned you: skip it for good."""
    with db.session() as conn:
        try:
            group = groups_mod.remove(conn, group_id, reason)
        except groups_mod.GroupError as error:
            raise click.ClickException(str(error)) from None
    click.echo(f"group {group['id']} {group['name']} is now skip, permanently; its planned posts are skipped")


@community.command("context")
@click.option("--json", "as_json", is_flag=True)
@click.option("--week", help="Plan week, default this week (2026-W44).")
def context_cmd(as_json, week) -> None:
    """Everything the weekly run needs, in one call (records checklist ticks first)."""
    week = week or plan_mod.current_week()
    with db.session() as conn:
        ticks = plan_mod.sync_ticks(conn)
        everything = groups_mod.all_groups(conn)
        eligible = []
        today = timeutil.today()
        days = plan_mod.week_days(week)
        for g in groups_mod.eligible(conn):
            rules = groups_mod.rules_for(g)
            last = db.scalar(
                conn,
                "SELECT max(coalesce(posted_at, planned_day)) FROM community_posts WHERE group_id = ? AND kind = 'post' AND status != 'skipped'",
                (g["id"],),
            )
            last = max(filter(None, [last and last[:10], g["last_posted_at"] and g["last_posted_at"][:10]]), default=None)
            ok_days = []
            for d in days if rules.days_confirmed else []:  # no open day until Ting Yu sets them
                if d < today:
                    continue
                if last and abs((d - date.fromisoformat(last)).days) < plan_mod.no_repeat_days():
                    continue
                ok_days.append({
                    "date": d.isoformat(),
                    "weekday": rules_mod.WEEKDAYS[d.weekday()],
                    "value_post": rules_mod.day_problem(rules, d.weekday(), promotional=False) is None,
                    "with_closing_line": not rules.no_promo
                    and rules_mod.day_problem(rules, d.weekday(), promotional=True) is None,
                })
            eligible.append({
                "id": g["id"], "name": g["name"], "url": g["url"], "slug": g["slug"], "audience": g["audience"],
                "promo_rules": g["promo_rules"], "rules_confirmed": bool(g["rules_confirmed"]), "rules": rules.as_dict(),
                "rules_summary": rules.summary(),
                "link_allowed": rules.known and bool(g["rules_confirmed"]) and not rules.no_promo and not rules.no_links,
                "needs_rules_ok": rules.known and not rules.parsed,
                "last_suggested": last, "days_open": ok_days, "notes": g["notes"],
            })
        planned = plan_mod.stored_items(conn, week)
        recent = db.rows(
            conn,
            "SELECT id, group_id, week, text FROM community_posts WHERE kind = 'post' AND created_at >= ? ORDER BY id DESC",
            (timeutil.stamp(timeutil.days_ago(int(plan_mod.settings().get("compare_days", 28)))),),
        )
        counts = groups_mod.counts(conn)
    tools, registry_ok = plan_mod.live_tools()
    from jura_growth.cli import cli as root

    social = root.commands.get("social")
    view = {
        "today": timeutil.today_str(),
        "week": week,
        "week_days": {rules_mod.WEEKDAYS[i]: d.isoformat() for i, d in enumerate(days)},
        "limits": {
            "groups_per_week": plan_mod.groups_per_week(),
            "no_repeat_days": plan_mod.no_repeat_days(),
            "post_words": plan_mod.words_range("post"),
            "reply_words": plan_mod.words_range("reply"),
            "replies_per_week": plan_mod.replies_range(),
            "utm": f"utm_source={plan_mod.utm_source()}&utm_campaign=<group slug>",
        },
        "post_as": plan_mod.settings().get("post_as"),
        "ticks_recorded": ticks,
        "register": counts,
        "groups": [
            {"id": g["id"], "channel": g["channel"], "name": g["name"], "url": g["url"], "fit": g["fit"],
             "joined": bool(g["joined"]), "removed": bool(g["removed"])}
            for g in everything
        ],
        "eligible": eligible,
        "planned_this_week": [{k: p[k] for k in ("id", "group_id", "kind", "planned_day", "status", "text")} for p in planned],
        "recent_post_texts": recent,
        "toolbox_live": sorted(tools),
        "toolbox_registry_readable": registry_ok,
        "image_renderer": bool(social is not None and "render" in getattr(social, "commands", {})),
    }
    if as_json:
        click.echo(json.dumps(view, indent=2, ensure_ascii=False, default=str))
        return
    click.echo(f"week {week}; register {counts.get('total', 0)} groups, {counts.get('plannable', 0)} joined and good fit")
    click.echo(f"ticks recorded: {ticks or 'none'}")
    for g in eligible:
        click.echo(f"  {g['id']} {g['name']}: {g['rules_summary']}; open days {[d['weekday'] for d in g['days_open']]}")


@community.command("plan-add")
@click.option("--file", "file_", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help='JSON: {"week": "2026-W44", "posts": [...], "replies": [...]}.')
@click.option("--week", help="Plan week, default the file's week or this week.")
def plan_add_cmd(file_, week) -> str:
    """Add posts and reply ideas to a week's plan (checked in code, then brand-gated)."""
    plan = _load_json(file_)
    with db.session() as conn:
        plan_mod.sync_ticks(conn)
        result = plan_mod.add(conn, plan, week)
    for line in result.lines:
        click.echo(line)
    click.echo(result.summary)
    if not result.ok:
        sys.exit(1)
    return result.summary


@community.command("publish-plan")
@click.option("--week", help="Plan week, default this week.")
def publish_plan_cmd(week) -> str:
    """Write outputs/growth/community/YYYY-Www.md and post it to #community."""
    with db.session() as conn:
        try:
            target, posted, posts, replies = plan_mod.publish(conn, week)
        except ValueError as error:
            raise click.ClickException(str(error)) from None
    click.echo(f"checklist: {target}")
    click.echo("posted to #community" if posted.delivered else f"#community: {posted.reason}")
    summary = f"plan published: {posts} posts, {replies} reply ideas ({target.name})"
    click.echo(summary)
    return summary


@community.command("posted")
@click.argument("item_id", type=int)
@click.argument("url", required=False)
def posted_cmd(item_id, url) -> None:
    """Record that you posted plan item ITEM_ID (optionally its URL)."""
    with db.session() as conn:
        try:
            item = plan_mod.mark_posted(conn, item_id, url)
        except ValueError as error:
            raise click.ClickException(str(error)) from None
    click.echo(f"item {item['id']} recorded as posted" + (f" ({item['posted_url']})" if item["posted_url"] else ""))


@community.command("sync-ticks")
def sync_ticks_cmd() -> None:
    """Record ticked `- [x]` items in the checklist files as posted."""
    with db.session() as conn:
        recorded = plan_mod.sync_ticks(conn)
    click.echo(f"recorded as posted: {', '.join(map(str, recorded))}" if recorded else "no new ticks")


@community.command("summary")
@click.option("--no-post", is_flag=True, help="Print it without posting to #community.")
def summary_cmd(no_post) -> str:
    """Post the register summary to #community (what this run found)."""
    run_id = log.current_run_id()
    with db.session() as conn:
        counts = groups_mod.counts(conn)
        new = db.rows(conn, "SELECT * FROM community_groups WHERE run_id = ? ORDER BY id", (run_id,)) if run_id else []
        if not run_id:
            new = db.rows(conn, "SELECT * FROM community_groups WHERE substr(created_at, 1, 10) = ? ORDER BY id", (timeutil.today_str(),))
        text = register_summary(counts, new)
        if no_post:
            click.echo(text)
            return "summary printed"
        result = discord.post(conn, "community", text, username="Jura growth · community")
    click.echo(text)
    click.echo("\nposted to #community" if result.delivered else f"\n#community: {result.reason}")
    return f"register summary: {counts.get('total', 0)} groups, {len(new)} new"


def register_summary(counts: dict, new: list[dict]) -> str:
    lines = [
        f"**Community register, {timeutil.today_str()}**",
        f"{counts.get('total', 0)} groups in the register ({counts.get('good_fit', 0)} good fit, "
        f"{counts.get('possible', 0)} possible, {counts.get('skip', 0)} skip); {counts.get('joined', 0)} joined. "
        f"{len(new)} added this run. Found by web search only; no Facebook page was opened.",
        "",
    ]
    for g in new:
        lines.append(f"- [{g['id']}] **{g['name']}** ({g['channel']}, {g['fit']}): {g['audience'] or 'audience not stated'}")
        lines.append(f"  rules: {g['promo_rules'] or 'unknown'}; {g['fit_reason']}")
        lines.append(f"  {g['url']}")
    if not counts.get("plannable"):
        lines += [
            "",
            "No group is marked joined and good fit yet, so there is no posting plan this week. Join the good-fit "
            "groups you want (as yourself), read their rules inside, then run:",
            "`jura-growth community set <id> joined=yes rules=\"<the rules as the group states them>\" rules_confirmed=yes "
            "promo_days=<days> post_days=<days>`",
            "Each `<days>` is any, none, or days like sat,sun or mon-fri: promo_days for promotional posts, "
            "post_days for every post.",
        ]
    return "\n".join(lines)


@community.command("audit-run")
@click.argument("run_id", type=int)
@click.option("--json", "as_json", is_flag=True)
def audit_run_cmd(run_id, as_json) -> None:
    """Scan a run's transcript for any fetch of a blocked domain or its subdomains.

    The blocked domains are Facebook's own plus blocked_fetch_domains in
    config/community.yaml."""
    report = audit(run_id)
    with db.session() as conn:
        log.event(conn, "community.audit", {k: v for k, v in report.items() if k != "calls"}, agent=NAME,
                  level="info" if report.get("clean") else "warning")
    if as_json:
        click.echo(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        click.echo(report["verdict"])
        for line in report.get("details", []):
            click.echo(f"  - {line}")
    sys.exit(0 if report.get("clean") else 1)


def audit(run_id: int) -> dict:
    path = transcript.find(run_id)
    if path is None:
        return {"run_id": run_id, "clean": False, "verdict": f"run {run_id}: no transcript found under data/growth/transcripts/", "details": []}
    found = transcript.read(path)
    blocked = groups_mod.blocked_domains()
    offending, refused = [], []
    for call in found.calls:
        urls = [u for u in call.urls() if transcript.on_domains(u, blocked)]
        if not urls:
            continue
        entry = f"{call.name} {', '.join(urls)}" + (f" ({call.error_text[:100]})" if call.error_text else "")
        (refused if call.denied or call.ok is False else offending).append(entry)
    searches = len(found.by_name("WebSearch"))
    fetches = found.by_name("WebFetch")
    hosts = sorted({transcript.host_of(str(c.input.get("url", ""))) for c in fetches if c.ok})
    clean = not offending and found.result is not None
    if offending:
        verdict = f"run {run_id}: NOT CLEAN. {len(offending)} fetch{'es' if len(offending) != 1 else ''} of a Facebook domain"
    elif found.result is None:
        verdict = f"run {run_id}: incomplete transcript (no final result record), so it can't be called clean"
    else:
        verdict = (
            f"run {run_id}: clean. {searches} web searches and {len(fetches)} page fetches, none to "
            f"{', '.join(blocked[:3])} or other Facebook domains"
            + (f"; {len(refused)} attempt{'s' if len(refused) != 1 else ''} refused by the permission rules" if refused else "")
            + "."
        )
    details = [f"fetched: {e}" for e in offending] + [f"refused: {e}" for e in refused]
    if hosts:
        details.append("hosts fetched: " + ", ".join(h for h in hosts if h))
    return {
        "run_id": run_id,
        "transcript": str(path),
        "clean": clean,
        "verdict": verdict,
        "web_searches": searches,
        "web_fetches": len(fetches),
        "offending": offending,
        "refused": refused,
        "details": details,
    }
