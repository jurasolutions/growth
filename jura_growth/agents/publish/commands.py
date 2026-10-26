"""`jura-growth publish ...` (browser publishing PRD §5.7).

| Command | Who |
|---|---|
| `publish next [--json]` | the publish run: claims at most one item (`claim.py`) |
| `publish done <A-id> --url <url> --live-text-file <f>` | the publish run: records the post |
| `publish stopped <A-id> --reason <r>` | the publish run: records a stop signal |
| `publish queue [--json]` | Ting Yu: items, their state and their A-ids |
| `publish resolve <A-id> posted --url <url>` or `not-posted` | Ting Yu: settles an `unknown` item (in `headless.NEVER`) |

Every command takes the request's `A-nnnn` (MC §4.6 A1), never the `P-nnnn` label. None of them
decides anything: approving and skipping happen in #approvals. A stop and a live-text mismatch
pause `publish` for every item and alert; only Ting Yu resumes it.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from datetime import date
from pathlib import Path

import click

from jura_growth import approvals, caps, db, discord, log, pause, timeutil
from jura_growth.agents.publish import claim, fixture, hosts, items, kinds

# What the run may report as a stop signal (BP §4.6). A closed list, so a page's own words
# never reach an alert through the reason.
STOP_REASONS = {
    "login": "a login or password prompt",
    "captcha": "a CAPTCHA or a check that it's a person",
    "checkpoint": "a security checkpoint",
    "warning": "a warning from the platform",
    "restriction": "a restriction on the account",
    "rate-limit": "a rate-limit notice",
    "removed": "a notice that a post was removed or goes against the rules",
    "admin-warning": "a removal or warning from a group admin",
    "wrong-identity": "the page wasn't showing the expected posting identity",
    "unidentified": "something it couldn't identify on a step that would post",
}
RESUME = "`jura-growth resume publish` or /growth resume publish"
# What `publish next` tells the run to do with each kind of item.
STEPS = {items.SOCIAL_ITEM: "social post", items.COMMUNITY_POST_ITEM: "community post",
         items.JOIN_ITEM: "join the group", items.ANSWERS_ITEM: "submit the membership answers"}


def same_text(approved: str, live: str) -> bool:
    """The live text matches the approved text after Unicode NFC, collapsing whitespace and
    trimming (BP QA Q9); any other difference is a mismatch."""
    return _normal(approved) == _normal(live)


def _normal(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


SOCIAL_ONLY = ("for social posts only so far; a community post or join is recorded by the community "
               "publishing steps that follow (browser publishing#05 and #06)")


def _item_for(conn: sqlite3.Connection, typed: str) -> tuple[approvals.Approval, items.Item]:
    """The request `typed` names (A-nnnn only) and its publish item, of any kind."""
    record = approvals.get(conn, typed)
    found = items.of(conn, record.subject) if record else None
    if record is None or found is None or record.kind != items.APPROVAL_KINDS.get(found.kind):
        raise click.ClickException(f"there is no approval request {typed} for a publish item (type its A-nnnn)")
    return record, found


def _host_problem(platform: str, url: str) -> str | None:
    """`hosts.post_problem`, with a refused fixture platform (BP-07) as a reason, not a traceback."""
    try:
        return hosts.post_problem(platform, url)
    except fixture.FixtureRefused as refused:
        return str(refused)


def _where(found: items.Item) -> str:
    return f"{found.label}, {found.platform}, {found.day}"


def _mark_published(conn: sqlite3.Connection, found: items.Item, url: str, how: str) -> None:
    """The draft is published, through the social agent's own record. The post is live whatever
    the draft says now (skipped by hand after the claim, say), so that is logged, not refused."""
    from jura_growth.agents.social import history

    try:
        history.mark_published(conn, date.fromisoformat(found.day), found.platform, url, how=how)
    except ValueError as error:
        log.event(conn, "publish.draft_not_marked", {"item": found.label, "why": str(error)}, level="warning",
                  agent=items.AGENT)


def _post_cards(conn: sqlite3.Connection) -> None:
    """Post any card `publish next`'s sync raised, once its transaction has committed (A12)."""
    from jura_growth import cards

    cards.sweep_safely(conn)


@click.group("publish")
def publish() -> None:
    """The publish queue: approved posts for a browser run (browser publishing PRD)."""


@publish.command("next")
@click.option("--json", "as_json", is_flag=True)
def next_cmd(as_json) -> str:
    """Claim the next approved item, if one is due, and print exactly what to post."""
    with db.session() as conn:
        handed = claim.next_item(conn, run_id=log.current_run_id())
        _post_cards(conn)
    if handed.item is None or handed.approval is None:
        if as_json:
            click.echo(json.dumps({"due": False, "reasons": handed.why}, indent=2, ensure_ascii=False))
        else:
            click.echo(claim.NOTHING_DUE)
            for reason in handed.why:
                click.echo(f"  - {reason}")
        return claim.NOTHING_DUE
    found, content = handed.item, handed.item.content
    out = {
        "due": True,
        "approval": handed.approval.id,
        "item": found.label,
        "kind": kinds.kind_of(found),
        "step": STEPS[found.kind],
        "platform": found.platform,
        "group": content.get("group"),
        "target_url": content["target_url"],
        "posting_identity": content["posting_identity"],
        "day": content.get("day", found.day),
        "text": content.get("text"),
        "images": [str(path) for path in handed.images],
        "answers": content.get("answers"),
    }
    if as_json:
        click.echo(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        click.echo(f"{out['approval']} · {out['step']} · {out['item']}")
        click.echo(f"Platform: {out['platform']}\nAct as: {out['posting_identity']}\nOpen: {out['target_url']}\nDay: {out['day']}")
        if out["text"] is not None:
            click.echo("Images, in order:" if out["images"] else "No image.")
            for path in out["images"]:
                click.echo(f"  {path}")
            click.echo("Text, exactly as approved, between the lines:\n---")
            click.echo(out["text"].rstrip("\n"))
            click.echo("---")
        for pair in out["answers"] or []:
            click.echo(f"Question: {pair['question']}\nAnswer, exactly as approved: {pair['answer']}")
    return f"claimed {out['approval']}"


@publish.command()
@click.argument("approval_id", metavar="A-ID")
@click.option("--url", required=True, help="The live post's address, on the platform's own host.")
@click.option("--live-text-file", "live_text_file", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="The post's text as it reads live, saved in the run's scratch folder.")
def done(approval_id, url, live_text_file) -> str:
    """Record that a claimed item was posted."""
    live = live_text_file.read_text(encoding="utf-8")
    with db.session() as conn:
        record, found = _item_for(conn, approval_id)
        if found.kind != items.SOCIAL_ITEM:
            raise click.ClickException(f"refused: publish done --url is {SOCIAL_ONLY}")
        if found.state != "claimed":
            raise click.ClickException(f"{record.id}'s item isn't claimed (it is {found.state})")
        wrong = _host_problem(found.platform, url)
        if wrong:
            raise click.ClickException(f"refused: {wrong}")
        matches = same_text(found.content["text"], live)
        with db.transaction(conn):
            conn.execute(
                "UPDATE publish_items SET state = 'done', outcome = 'posted', post_url = ?, live_text_hash = ?, "
                "live_text_matches = ?, finished_at = ? WHERE id = ? AND state = 'claimed'",
                (url, hashlib.sha256(_normal(live).encode("utf-8")).hexdigest(), int(matches), timeutil.stamp(), found.id),
            )
            _mark_published(conn, found, url, "browser")
            log.event(conn, "publish.done", {"item": found.label, "approval": record.id, "url": url,
                                              "live_text_matches": matches}, agent=items.AGENT)
            if not matches:
                pause.pause(conn, items.AGENT, f"the live text of {record.id} doesn't match what was approved", notify=False)
        if not matches:
            discord.alert(conn, f"{record.id} ({_where(found)}) went out, but the live text doesn't match the approved "
                                f"text. Check the post: {url}\nPublishing is paused for every item until you resume it: "
                                f"{RESUME}.", agent=items.AGENT)
    click.echo(f"{record.id}: posted, {url}" + ("" if matches else " (live text doesn't match; publish paused)"))
    return f"{record.id} posted"


@publish.command()
@click.argument("approval_id", metavar="A-ID")
@click.option("--reason", required=True, type=click.Choice(list(STOP_REASONS)), help="The stop signal the page showed.")
def stopped(approval_id, reason) -> str:
    """Record a stop signal: the item stops and publishing pauses for every item.

    There is no screenshot file (BP §4.6 as amended): the alert names the run, whose transcript
    keeps what the page showed for 7 days. This is the stop's only alert: the runner doesn't
    post the failed run again (`job.after_run`)."""
    run_id = log.current_run_id()
    with db.session() as conn:
        record, found = _item_for(conn, approval_id)
        if found.state != "claimed":
            raise click.ClickException(f"{record.id}'s item isn't claimed (it is {found.state})")
        with db.transaction(conn):
            conn.execute(
                "UPDATE publish_items SET state = 'stopped', stop_reason = ?, finished_at = ? WHERE id = ? AND state = 'claimed'",
                (reason, timeutil.stamp(), found.id),
            )
            log.event(conn, "publish.stopped", {"item": found.label, "approval": record.id, "reason": reason},
                      level="warning", agent=items.AGENT, run_id=run_id)
            pause.pause(conn, items.AGENT, f"{record.id} stopped: {reason}", notify=False)
        where = f"in run {run_id}" if run_id is not None else "outside a run"
        text = f"Publishing stopped at {record.id} ({_where(found)}) {where}: {STOP_REASONS[reason]}."
        if run_id is not None:
            text += f" The run's transcript keeps what the page showed for {caps.BROWSER_TRANSCRIPT_DAYS} days."
        text += f"\nNothing more is posted or joined until you resume it: {RESUME}."
        discord.alert(conn, text, agent=items.AGENT)
    click.echo(f"{record.id}: stopped ({reason}); publish is paused")
    return f"{record.id} stopped"


def _request_word(conn: sqlite3.Connection, found: items.Item) -> tuple[approvals.Approval | None, str]:
    used = items.claimed_request(conn, found)
    if used is not None:
        return used, "claimed"
    latest = items.latest_request(conn, found)
    return latest, (latest.status if latest else "no request")


@publish.command()
@click.option("--json", "as_json", is_flag=True)
def queue(as_json) -> None:
    """Every publish item, its state and its A-id."""
    with db.session() as conn:
        rows = [items.Item.from_row(r) for r in conn.execute("SELECT * FROM publish_items ORDER BY day, id")]
        listed = []
        for found in rows:
            record, word = _request_word(conn, found)
            listed.append({
                "item": found.label, "approval": record.id if record else None, "kind": found.kind,
                "platform": found.platform, "day": found.day, "state": found.state, "request": word,
                "outcome": found.outcome, "post_url": found.post_url, "stop_reason": found.stop_reason,
            })
    if as_json:
        click.echo(json.dumps({"items": listed}, indent=2, ensure_ascii=False))
        return
    if not listed:
        click.echo("no publish items")
        return
    for entry in listed:
        detail = f"{entry['state']} ({entry['request']})" if entry["state"] == "ready" else entry["state"]
        extra = entry["post_url"] or entry["stop_reason"] or entry["outcome"] or ""
        click.echo(f"{entry['item']}  {entry['approval'] or '-'}  {entry['platform']}  {entry['day']}  {detail}"
                   + (f"  {extra}" if extra else ""))


@publish.command()
@click.argument("approval_id", metavar="A-ID")
@click.argument("outcome", type=click.Choice(["posted", "not-posted"]))
@click.option("--url", help="With posted: the live post's address.")
def resolve(approval_id, outcome, url) -> str:
    """Settle an item whose outcome is unknown: it was posted (with its URL), or it wasn't.

    Also a claim nobody will close: one whose run has ended without `after_run` settling it (the
    process was killed), or one made in Terminal with no run."""
    with db.session() as conn:
        record, found = _item_for(conn, approval_id)
        if not (found.state == "unknown" or items.stale_claim(conn, found)):
            raise click.ClickException(f"{record.id}'s item isn't unknown (it is {found.state}); nothing to settle")
        settles = found.state
        if outcome == "posted" and found.kind != items.SOCIAL_ITEM:
            raise click.ClickException(f"refused: resolve posted is {SOCIAL_ONLY}. Check the group, then settle "
                                       f"{record.id} as not-posted, or record what happened by hand")
        if outcome == "posted":
            wrong = _host_problem(found.platform, url)
            if wrong:
                raise click.ClickException(f"refused: posted needs --url, the post's own address on {found.platform}: {wrong}")
        with db.transaction(conn):
            if outcome == "posted":
                conn.execute("UPDATE publish_items SET state = 'done', outcome = 'posted', post_url = ?, finished_at = ? "
                             "WHERE id = ? AND state = ?", (url, timeutil.stamp(), found.id, settles))
                _mark_published(conn, found, url, "browser, settled by Ting Yu")
            else:
                conn.execute("UPDATE publish_items SET state = 'withdrawn', outcome = 'not-posted', finished_at = ? "
                             "WHERE id = ? AND state = ?", (timeutil.stamp(), found.id, settles))
            log.event(conn, "publish.resolved", {"item": found.label, "approval": record.id, "outcome": outcome, "url": url},
                      agent=items.AGENT)
    click.echo(f"{record.id}: settled as {outcome}" + (f" ({url})" if url and outcome == "posted" else ""))
    return f"{record.id} {outcome}"


def register(cli: click.Group) -> None:
    cli.add_command(publish)

