"""R1: one message in #mission-control per conversation, retried until it is delivered.

A message waiting for triage isn't due yet, because its report says what triage made of it. A person
can't be lost to that: triage ends in a report whatever it does (`triage.py`). An inbox item's
`reported_at` stays empty until Discord takes its message (technical review B7), and `report_due` runs in
the precheck and after a run, so a message Discord refused goes again on the next check and a delivered
one never does. Nothing is attempted with no webhook set, and the health strip counts what is waiting.

Everything a person wrote goes through `quoted`, the one builder, and sits inside one quote block,
which the conversation class carries (`privacy.py`). The frame around it is fixed text and record
fields, so nothing they wrote can pass as the engine's own words, close the quote or ping anyone.
Intake registers none of their words with `privacy.never_show`: that blanks any plain text the words
match, so a subject reading `evil.test` would hide the sender's domain in the frame.
"""

from __future__ import annotations

import json
import re
import sqlite3

from jura_growth import discord, log, privacy, timeutil
from jura_growth.agents.inbox import settings, store

CHANNEL = "mission-control"
USERNAME = "Jura growth · inbox"
FOLD_OLD_OVER = 5  # F12: more old messages than this fold into one report
FOLD_SHOWN = 40  # inbox items named in a fold before "and N more"
NAME_SHOWN = 80
SUBJECT_SHOWN = 160
CUT_NOTE = "(cut: the rest is in the mailbox)"
FLOOD_SHOWN = 10  # S15: reports in one run before the rest fold into a line
_SOCIAL_HEADINGS = {"facebook-comment": "Facebook comment", "facebook-dm": "Facebook message",
                    "instagram-comment": "Instagram comment", "instagram-dm": "Instagram message"}

_LINK_TARGET = re.compile(r"\]\(\s*<?\s*(\w+)://")
_SPOILER = re.compile(r"\|(?=\|)")
_ZERO_WIDTH_SPACE = chr(0x200b)
_NOT_A_BACKTICK = chr(0x02cb)


def _neutral(line: str) -> str:
    """One line of someone's text, unable to restyle anything or ping anyone (N5, A4, A5): no
    backticks to open a fence, no spoiler, no mention, and no masked link at any depth of nesting.
    A link target's address stays readable and can't be clicked, so what it is shows."""
    line = _LINK_TARGET.sub(lambda m: f"]\\({m.group(1)}[:]//", line).replace("](", "]\\(")
    line = _SPOILER.sub("|" + _ZERO_WIDTH_SPACE, line.replace("`", _NOT_A_BACKTICK))
    line = discord.defuse_mentions(line)
    return re.sub(r"^(\s*)(#{1,3}\s|-#\s)", r"\1\\\2", line)


def quoted(text: str) -> str:
    """`text` as a Discord quote: every line marked, whatever line break it used."""
    return "\n".join(f"> {_neutral(line)}".rstrip() for line in store.clean_text(text).split("\n"))


def _heading(item: dict) -> str:
    if item["source"] == "enquiry":
        return "Website enquiry"
    if item["source"] in _SOCIAL_HEADINGS:
        return _SOCIAL_HEADINGS[item["source"]]
    return "Answer to our email" if item["lead_id"] else "Email"


def _when(item: dict) -> str:
    stamp = item["received_at"] or item["recorded_at"]
    return timeutil.parse(stamp).astimezone(timeutil.SGT).strftime("%d %b %H:%M SGT")


def _extras(item: dict) -> list[str]:
    """Lines inside the quote about the message, not by the person: both are their own strings."""
    extras = []
    names = json.loads(item["attachments_json"] or "[]")
    if names:
        extras.append("(attached, not opened: " + ", ".join(names) + ")")
    copied = json.loads(item["thread_json"] or "{}").get("copied") or 0
    if copied:
        extras.append(f"(they copied {copied} other{'s' if copied != 1 else ''}: reply by hand if they need it)")
    return extras


def _block(items: list[dict], texts: list[str], cuts: list[bool]) -> str:
    """Everything they wrote, as stored, in one quote block: a conversation's messages in order."""
    newest = items[-1]
    lines = []
    if newest["sender_name"]:
        lines.append(f"From: {newest['sender_name'][:NAME_SHOWN]}")
    if newest["subject"]:
        lines.append(f"Subject: {newest['subject'][:SUBJECT_SHOWN]}")
    if lines:
        lines.append("")
    for number, (item, text, cut) in enumerate(zip(items, texts, cuts)):
        if number:
            lines += ["", f"(then, {_when(item)})"]
        lines.append(text if text else "(no text: see the mailbox)")
        if cut:
            lines.append(CUT_NOTE)
        lines += _extras(item)
    return quoted("\n".join(lines))


def _build(items: list[dict]) -> tuple[str, str]:
    """One conversation's report and the quote block in it, always one Discord message, measured
    masked: masking can lengthen text, and a piece past the limit would split the report. What
    goes first is the longest message's end, so one long mail can't crowd out a short one."""
    newest = items[-1]
    where = newest["sender_domain"] or newest["target"] or "an unknown sender"
    count = f", {len(items)} messages" if len(items) > 1 else ""
    high = " · **high priority**" if newest["priority"] == "high" else ""
    head = f"**{store.label(newest['id'])} · {_heading(newest)}{count}**{high} · {where}, {_when(newest)}"
    note = " ".join(dict.fromkeys(item["note"] for item in items if item["note"]))
    texts = [item["text"] for item in items]
    cuts = [bool(item["text_cut"]) for item in items]
    while True:
        block = _block(items, texts, cuts)
        content = "\n".join(part for part in (head, block, note) if part)
        over = len(privacy.for_discord(content, conversation=[block])) - discord.MAX_CONTENT
        if over <= 0 or not any(texts):
            return content, block
        longest = max(range(len(texts)), key=lambda number: len(texts[number]))
        texts[longest] = texts[longest][: max(0, len(texts[longest]) - over - len(CUT_NOTE) - 8)].rstrip()
        cuts[longest] = True


def _fold(items: list[dict]) -> str:
    """F12: a long absence reads as one message, and each still has an id and a domain."""
    shown = ", ".join(f"{store.label(i['id'])} {i['sender_domain'] or 'unknown'}" for i in items[:FOLD_SHOWN])
    more = f", and {len(items) - FOLD_SHOWN} more" if len(items) > FOLD_SHOWN else ""
    return (f"**{len(items)} older messages** arrived more than {settings.limit('old_after_hours')} hours ago. "
            f"No drafts: answer by hand if any still matters.\n{shown}{more}")


def _flood(groups: list[list[dict]]) -> str:
    """S15: what didn't fit in this run, as one line. It still names each by its id."""
    items = [group[-1] for group in groups]
    spam = sum(1 for item in items if item["class"] == "spam")
    marked = f", {spam} of them marked spam" if spam else ""
    shown = ", ".join(store.label(item["id"]) for item in items[:FOLD_SHOWN])
    more = f", and {len(items) - FOLD_SHOWN} more" if len(items) > FOLD_SHOWN else ""
    return f"**{len(items)} more** reactions in this check{marked}: {shown}{more}. See `/growth inbox list`."


def _in_turn(groups: list[list[dict]]) -> list[list[dict]]:
    """S15: spam goes last, so it is the first to fold."""
    return sorted(groups, key=lambda group: group[-1]["class"] == "spam")


def report_due(conn: sqlite3.Connection) -> int:
    """Post every report still owed, one per conversation (F8), and stop at the first Discord refuses:
    the rest wait for the next check, in order. Never raises for one bad row. Returns how many inbox
    items were delivered."""
    if not discord.webhook_set(CHANNEL):
        return 0
    due = store.unreported(conn)
    if not due:
        return 0
    privacy.load_for_masking(conn)  # this text came from outside, so every secret value is masked
    old = [i for i in due if i["stale"]]
    delivered = 0
    if len(old) > FOLD_OLD_OVER:
        due = [i for i in due if not i["stale"]]
        if not _post(conn, _fold(old), ()):
            return delivered
        store.mark_reported(conn, [i["id"] for i in old])
        delivered += len(old)
    groups: dict[str, list[dict]] = {}
    for item in due:
        groups.setdefault(item["conversation"], []).append(item)
    turns = _in_turn(list(groups.values()))
    shown, folded = (turns[:FLOOD_SHOWN], turns[FLOOD_SHOWN:]) if len(turns) > FLOOD_SHOWN else (turns, [])
    for group in shown:
        try:
            content, block = _build(group)
        except Exception as error:  # noqa: BLE001 - one bad row never holds up the rest
            log.event(conn, "inbox.report_refused", {"item": group[-1]["id"], "error": type(error).__name__}, level="warning", agent="inbox")
            continue
        if not _post(conn, content, (block,)):
            return delivered
        store.mark_reported(conn, [item["id"] for item in group])
        delivered += len(group)
    if folded and _post(conn, _flood(folded), ()):
        store.mark_reported(conn, [item["id"] for group in folded for item in group])
        delivered += sum(len(group) for group in folded)
    return delivered


def _post(conn: sqlite3.Connection, content: str, conversation: tuple[str, ...]) -> bool:
    return discord.post(conn, CHANNEL, content, username=USERNAME, dedupe=False, suppress_embeds=True,
                        conversation=conversation).delivered
