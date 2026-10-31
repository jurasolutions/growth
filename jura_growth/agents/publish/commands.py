"""`jura-growth publish ...` (browser publishing PRD §5.7).

| Command | Who |
|---|---|
| `publish next [--json]` | the publish run: claims at most one item (`claim.py`) |
| `publish done <A-id> --url <url> --live-text-file <f>` | the publish run: records the post |
| `publish done <A-id> --outcome <o> [--url <group url>] [--file <q.json>]` | the publish run: what a join or a group screen came to (`outcomes.py`) |
| `publish stopped <A-id> --reason <r>` | the publish run: records a stop signal |
| `publish note-rules <group-id> --file <f>` | the publish run: rules seen inside a group, raising a `group-rules` request |
| `publish queue [--json]` | Ting Yu: items, their state and their A-ids |
| `publish resolve <A-id> posted --url <url>` or `not-posted` | Ting Yu: settles an `unknown` item (in `headless.NEVER`) |

Every command takes the request's `A-nnnn` (MC §4.6 A1), never the `P-nnnn` label. None of them
decides anything: approving and skipping happen in #approvals. A stop and a live-text mismatch
pause `publish` for every item and alert; only Ting Yu resumes it. A join's outcomes (membership
questions, a group that takes only personal profiles) neither alert nor pause (BP §4.6).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date
from pathlib import Path

import click

from jura_growth import approvals, caps, db, discord, log, pause, timeutil
from jura_growth.agents import GROWTH, LISTED, YOU, PendingItem
from jura_growth.agents.publish import claim, fixture, hosts, items, kinds, outcomes
from jura_growth.agents.publish import text as text_mod

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


# The live text matches the approved text after Unicode NFC, collapsing whitespace and trimming
# (BP QA Q9), the one normal form the transcript audit uses too (`text.py`).
same_text = text_mod.same
normal = text_mod.normal


POSTS = (items.SOCIAL_ITEM, items.COMMUNITY_POST_ITEM)
POSTS_ONLY = "for posts only: a join is recorded with --outcome"


def _item_for(conn: sqlite3.Connection, typed: str) -> tuple[approvals.Approval, items.Item]:
    """The request `typed` names (A-nnnn only) and its publish item, of any kind."""
    record = approvals.get(conn, typed)
    found = items.of(conn, record.subject) if record else None
    if record is None or found is None or record.kind != items.APPROVAL_KINDS.get(found.kind):
        raise click.ClickException(f"there is no approval request {typed} for a publish item (type its A-nnnn)")
    return record, found


def _host_problem(found: items.Item, url: str | None) -> str | None:
    """Why `url` isn't the live address of `found`'s post: one post on its platform
    (`hosts.post_problem`), or, for a community post, one post inside its own group
    (`hosts.group_post_problem`, BP-05). A refused fixture platform (BP-07) is a reason, not a
    traceback."""
    try:
        if found.kind == items.COMMUNITY_POST_ITEM:
            return hosts.group_post_problem(url, found.target_url)
        return hosts.post_problem(found.platform, url)
    except fixture.FixtureRefused as refused:
        return str(refused)


def _where(found: items.Item) -> str:
    return f"{found.label}, {found.platform}, {found.day}"


def _mark_published(conn: sqlite3.Connection, found: items.Item, url: str, how: str) -> None:
    """The draft is published, through its agent's own record: the social draft, or the planned
    community post (`posted`, with `posted_url`, `posted_at` and `posted_via = 'browser'`, BP §5.6).
    The post is live whatever the draft says now (skipped by hand after the claim, say), so that
    is logged, not refused."""
    from jura_growth.agents.community import plan as plan_mod
    from jura_growth.agents.social import history

    try:
        if found.kind == items.COMMUNITY_POST_ITEM:
            plan_mod.mark_posted(conn, found.ref_id, url, via="browser")
        else:
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
@click.option("--url", help="The live post's address, on the platform's own host; with --outcome, the group's.")
@click.option("--live-text-file", "live_text_file", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="The post's text as it reads live, saved in the run's scratch folder.")
@click.option("--outcome", type=click.Choice(outcomes.OUTCOMES),
              help="What a join, or a group's join or post screen, came to (instead of a post).")
@click.option("--file", "answers_file", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="With --outcome questions: the questions and the drafted answers, as JSON.")
def done(approval_id, url, live_text_file, outcome, answers_file) -> str:
    """Record that a claimed item was posted, or what its join came to (--outcome)."""
    if outcome is not None:
        return _done_outcome(approval_id, outcome, url, live_text_file, answers_file)
    if not url or live_text_file is None:
        raise click.UsageError("a post needs --url and --live-text-file; a join needs --outcome")
    if answers_file is not None:
        raise click.UsageError("--file goes with --outcome questions")
    live = live_text_file.read_text(encoding="utf-8")
    with db.session() as conn:
        record, found = _item_for(conn, approval_id)
        if found.kind not in POSTS:
            raise click.ClickException(f"refused: publish done --url is {POSTS_ONLY}")
        if found.state != "claimed":
            raise click.ClickException(f"{record.id}'s item isn't claimed (it is {found.state})")
        wrong = _host_problem(found, url)
        if wrong:
            raise click.ClickException(f"refused: {wrong}")
        matches = same_text(found.content["text"], live)
        with db.transaction(conn):
            conn.execute(
                "UPDATE publish_items SET state = 'done', outcome = 'posted', post_url = ?, live_text_hash = ?, "
                "live_text_matches = ?, finished_at = ? WHERE id = ? AND state = 'claimed'",
                (url, hashlib.sha256(normal(live).encode("utf-8")).hexdigest(), int(matches), timeutil.stamp(), found.id),
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


def _done_outcome(approval_id: str, outcome: str, url: str | None, live_text_file, answers_file) -> str:
    """`publish done <A-id> --outcome …` (`outcomes.py`): no alert, no pause."""
    if live_text_file is not None:
        raise click.UsageError("--live-text-file is for a post, not --outcome")
    asks = outcome == outcomes.QUESTIONS
    if asks and answers_file is None:
        raise click.UsageError("--outcome questions needs --file <q.json>")
    if not asks and answers_file is not None:
        raise click.UsageError("only --outcome questions takes --file")
    if url:
        wrong = hosts.problem(items.COMMUNITY_PLATFORM, url)
        if wrong:
            raise click.ClickException(f"refused: {wrong}")
    try:
        answers = outcomes.read_answers(answers_file.read_text(encoding="utf-8")) if answers_file else None
    except (outcomes.Refused, UnicodeDecodeError) as refusal:
        raise click.ClickException(f"refused: {refusal}") from None
    with db.session() as conn:
        record, found = _item_for(conn, approval_id)
        try:
            with db.transaction(conn):
                recorded = outcomes.record(conn, record, found, outcome, url=url, answers=answers,
                                           run_id=log.current_run_id())
        except outcomes.Refused as refusal:
            raise click.ClickException(f"refused: {refusal}") from None
        _post_cards(conn)
    click.echo(recorded.line)
    if not recorded.ok:
        raise SystemExit(1)
    return recorded.line


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
            removed = outcomes.remove_group(conn, found, reason, run_id=run_id)
        _post_cards(conn)
        where = f"in run {run_id}" if run_id is not None else "outside a run"
        text = f"Publishing stopped at {record.id} ({_where(found)}) {where}: {STOP_REASONS[reason]}."
        if removed is not None:
            text += (f" Group {removed} is now skipped for good, as `community removed` does: its planned posts "
                     f"are skipped and its waiting cards superseded.")
        if run_id is not None:
            text += f" The run's transcript keeps what the page showed for {caps.BROWSER_TRANSCRIPT_DAYS} days."
        text += f"\nNothing more is posted or joined until you resume it: {RESUME}."
        discord.alert(conn, text, agent=items.AGENT)
    click.echo(f"{record.id}: stopped ({reason}); publish is paused")
    return f"{record.id} stopped"


@publish.command("note-rules")
@click.argument("group_id", type=int)
@click.option("--file", "rules_file", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="The group's rules exactly as the group shows them, as plain text.")
def note_rules(group_id, rules_file) -> str:
    """Record the rules a run saw inside a group, and ask Ting Yu to confirm them (group-rules).

    Only the publish run that claimed an item in that group may call it: the rules replace the
    researched ones, and a change clears any confirmation, so Ting Yu decides again."""
    from jura_growth.agents.community import group_rules
    from jura_growth.agents.community import groups as groups_mod

    run_id = log.current_run_id()
    try:
        text = rules_file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise click.ClickException("refused: the rules file isn't UTF-8 text") from None
    with db.session() as conn:
        if run_id is None or not outcomes.claimed_in_group(conn, run_id, group_id):
            raise click.ClickException(f"refused: only a publish run that claimed an item in group {group_id} "
                                       f"records the rules seen there")
        try:
            with db.transaction(conn):
                raised = group_rules.note_seen(conn, group_id, text, run_id=run_id)
        except groups_mod.GroupError as error:
            raise click.ClickException(f"refused: {error}") from None
        _post_cards(conn)
    if raised is None:
        line = f"group {group_id}: the rules seen are the ones Ting Yu confirmed; nothing to decide"
    else:
        line = f"group {group_id}: rules recorded; Ting Yu confirms them and the open days as {raised.id} in #approvals"
    click.echo(line)
    return line


def _request_word(conn: sqlite3.Connection, found: items.Item) -> tuple[approvals.Approval | None, str]:
    used = items.claimed_request(conn, found)
    if used is not None:
        return used, "claimed"
    latest = items.latest_request(conn, found)
    return latest, (latest.status if latest else "no request")


PENDING_SHOWN = 5  # open items `pending` lists before "and N more"


def pending_items(conn: sqlite3.Connection) -> list[PendingItem]:
    """`pending`'s lines for the open items, on the read model's read-only connection. An item whose
    outcome is unknown, or a claim no run will close, is Ting Yu's to settle; the rest are growth's."""
    rows = [items.Item.from_row(r) for r in conn.execute(
        "SELECT * FROM publish_items WHERE state IN ('unknown', 'ready', 'claimed') ORDER BY day, id")]
    found, open_lines = [], []
    for item in rows:
        record, word = _request_word(conn, item)
        if item.state == "unknown" or items.stale_claim(conn, item):
            found.append(PendingItem(YOU, _settle_line(item, record)))
        else:
            open_lines.append(f"{_where(item)}: ready (request {word})" if item.state == "ready" else f"{_where(item)}: {item.state}")
    found += [PendingItem(GROWTH, line, order=LISTED) for line in open_lines[:PENDING_SHOWN]]
    if len(open_lines) > PENDING_SHOWN:
        found.append(PendingItem(GROWTH, f"and {len(open_lines) - PENDING_SHOWN} more: send `/growth publish queue`", order=LISTED))
    return found


def _settle_line(item: items.Item, record: approvals.Approval | None) -> str:
    why = "the outcome is unknown" if item.state == "unknown" else "no run will finish its claim"
    if record is None:
        return f"{_where(item)}: {why}, and it has no request on record."
    not_posted = f"`/growth publish resolve {record.id} not-posted`"
    if item.kind not in POSTS:  # `publish resolve` takes only not-posted for a join
        return f"{_where(item)}: {why}. Check the group, then send {not_posted}."
    return f"{_where(item)}: {why}. Check the page, then send `/growth publish resolve {record.id} posted --url <url>` or {not_posted}."


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
        if outcome == "posted" and found.kind not in POSTS:
            raise click.ClickException(f"refused: resolve posted is {POSTS_ONLY}. Check the group, then settle "
                                       f"{record.id} as not-posted, or record what happened by hand")
        if outcome == "posted":
            wrong = _host_problem(found, url)
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

