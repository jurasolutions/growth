"""R1: one message in #mission-control for every reaction, retried until it is delivered.

An inbox item's `reported_at` stays empty until Discord takes its message (technical review B7), and
`report_due` runs in the precheck and after a run, so a message Discord refused goes again on the
next check and a delivered one never does. Nothing is attempted with no webhook set, and the
health strip counts what is waiting.

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
CUT_NOTE_SOCIAL = "(cut: the rest is in the thread)"
NEXT_NEW = "Next: no draft yet in this build. Answer in the mailbox if it needs one."
NEXT_NEW_SOCIAL = "Next: no draft yet in this build. Answer on the platform if it needs one."
SOCIAL_HEADINGS = {"facebook-comment": "Facebook comment", "facebook-dm": "Facebook message",
                   "instagram-comment": "Instagram comment", "instagram-dm": "Instagram message"}
RUN_MESSAGE = store.RUN_MESSAGE

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
    if item["source"] in SOCIAL_HEADINGS:
        return SOCIAL_HEADINGS[item["source"]]
    if item["source"] == RUN_MESSAGE:
        return "From the watch"
    if item["source"] == "enquiry":
        return "Website enquiry"
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


def _no_text(item: dict) -> str:
    """Fixed words for a message with no text. No model guesses what a voice note says (F7)."""
    from jura_growth.agents.inbox import watch

    kind = json.loads(item["thread_json"] or "{}").get("attachment")
    return f"sent {watch.ATTACHMENTS.get(kind, watch.ATTACHMENTS['other'])}, see thread"


def _block(item: dict, text: str, cut: bool) -> str:
    lines = []
    if item["sender_name"]:
        lines.append(f"From: {item['sender_name'][:NAME_SHOWN]}")
    if item["subject"]:
        lines.append(f"Subject: {item['subject'][:SUBJECT_SHOWN]}")
    if lines:
        lines.append("")
    social = item["source"] in SOCIAL_HEADINGS
    lines.append(text if text else _no_text(item) if social else "(no text: see the mailbox)")
    if cut:
        lines.append(CUT_NOTE_SOCIAL if social else CUT_NOTE)
    return quoted("\n".join([*lines, *_extras(item)]))


def build(item: dict) -> tuple[str, str]:
    """The report's text and the quote block in it, always one Discord message, measured masked:
    masking can lengthen text, and a piece past the limit would split the report."""
    if item["source"] == RUN_MESSAGE:
        return f"**{store.label(item['id'])} · {_heading(item)}** · {_when(item)}\n{item['note']}", ""
    where = item["sender_domain"] or "an unknown sender"
    head = f"**{store.label(item['id'])} · {_heading(item)}** · {where}, {_when(item)}"
    if item["target"]:
        head += f"\nOpen: <{item['target']}>"
    new = NEXT_NEW_SOCIAL if item["source"] in SOCIAL_HEADINGS else NEXT_NEW
    note = item["note"] or (new if item["state"] == store.NEW else "")
    text = item["text"]
    cut = bool(item["text_cut"])
    while True:
        block = _block(item, text, cut)
        content = "\n".join(part for part in (head, block, note) if part)
        over = len(privacy.for_discord(content, conversation=[block])) - discord.MAX_CONTENT
        if over <= 0 or not text:
            return content, block
        text = text[: max(0, len(text) - over - len(CUT_NOTE) - 8)].rstrip()
        cut = True


def _fold(items: list[dict]) -> str:
    """F12: a long absence reads as one message, and each still has an id and a domain."""
    shown = ", ".join(f"{store.label(i['id'])} {i['sender_domain'] or 'unknown'}" for i in items[:FOLD_SHOWN])
    more = f", and {len(items) - FOLD_SHOWN} more" if len(items) > FOLD_SHOWN else ""
    return (f"**{len(items)} older messages** arrived more than {settings.limit('old_after_hours')} hours ago. "
            f"No drafts: answer by hand if any still matters.\n{shown}{more}")


def report_due(conn: sqlite3.Connection) -> int:
    """Post every report still owed, and stop at the first Discord refuses: the rest wait for the
    next check, in order. Never raises for one bad row. Returns how many were delivered."""
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
    for item in due:
        try:
            content, block = build(item)
        except Exception as error:  # noqa: BLE001 - one bad row never holds up the rest
            log.event(conn, "inbox.report_refused", {"item": item["id"], "error": type(error).__name__}, level="warning", agent="inbox")
            continue
        if not _post(conn, content, (block,) if block else ()):
            break
        store.mark_reported(conn, [item["id"]])
        delivered += 1
    return delivered


def _post(conn: sqlite3.Connection, content: str, conversation: tuple[str, ...]) -> bool:
    return discord.post(conn, CHANNEL, content, username=USERNAME, dedupe=False, suppress_embeds=True,
                        conversation=conversation).delivered
