"""R1: one message in #mission-control for every reaction, retried until it is delivered.

An item's `reported_at` stays empty until Discord takes its message (technical review B7), and
`report_due` runs in the precheck and after a run, so a message Discord refused goes again on the
next check and a delivered one never does. Nothing is attempted with no webhook set, and the
health strip counts what is waiting.

Everything a person wrote goes through `quoted`, the one builder, and sits inside one quote block,
which the conversation class carries (`privacy.py`). The frame around it is fixed text and record
fields, so nothing they wrote can pass as the engine's own words, close the quote or ping anyone.
"""

from __future__ import annotations

import json
import re
import sqlite3

from jura_growth import discord, log, privacy, timeutil
from jura_growth.agents.inbox import store

CHANNEL = "mission-control"
USERNAME = "Jura growth · inbox"
FOLD_OLD_OVER = 5  # F12: more old messages than this fold into one report
NAME_SHOWN = 80
SUBJECT_SHOWN = 160
CUT_NOTE = "(cut: the rest is in the mailbox)"
NEXT_NEW = "Next: no draft yet in this build. Answer in the mailbox if it needs one."

_LINES = re.compile(r"\r\n|[\r\n\x0b\x0c\x85  ]")
_MASKED_LINK = re.compile(r"\[([^\]\n]*)\]\(\s*<?([^)\s>]*)>?[^)\n]*\)")


def _defang(url: str) -> str:
    return re.sub(r"^(\w+)://", r"\1[:]//", url)


def _neutral(line: str) -> str:
    """One line of someone's text, unable to restyle anything or ping anyone (N5, A4, A5): no
    backticks to open a fence, no mention, and a masked link showing where it really goes."""
    line = _MASKED_LINK.sub(lambda m: f"[{m.group(1)}] ({_defang(m.group(2))})", line)
    line = line.replace("`", "ˋ").replace("||", "|​|")
    line = re.sub(r"@(everyone|here)", "@​\\1", line).replace("<@", "<@​").replace("<#", "<#​")
    return re.sub(r"^(\s*)(#{1,3}\s|-#\s)", r"\1\\\2", line)


def quoted(text: str) -> str:
    """`text` as a Discord quote: every line marked, whatever line break it used."""
    return "\n".join(f"> {_neutral(line)}".rstrip() for line in _LINES.split(text))


def _heading(item: dict) -> str:
    if item["source"] == "enquiry":
        return "Website enquiry"
    return "Reply to our email" if item["lead_id"] else "Email"


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


def _block(item: dict, text: str, cut: bool) -> str:
    lines = []
    if item["sender_name"]:
        lines.append(f"From: {item['sender_name'][:NAME_SHOWN]}")
    if item["subject"]:
        lines.append(f"Subject: {item['subject'][:SUBJECT_SHOWN]}")
    if lines:
        lines.append("")
    lines.append(text if text else "(no text: see the mailbox)")
    if cut:
        lines.append(CUT_NOTE)
    return quoted("\n".join([*lines, *_extras(item)]))


def build(item: dict) -> tuple[str, str]:
    """The report's text and the quote block in it, always one Discord message, measured masked:
    masking can lengthen text, and a piece past the limit would split the report."""
    where = item["sender_domain"] or "an unknown sender"
    head = f"**{store.label(item['id'])} · {_heading(item)}** · {where}, {_when(item)}"
    note = item["note"] or (NEXT_NEW if item["state"] == store.NEW else "")
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
    shown = ", ".join(f"{store.label(i['id'])} {i['sender_domain'] or 'unknown'}" for i in items[:40])
    more = f", and {len(items) - 40} more" if len(items) > 40 else ""
    return (f"**{len(items)} older messages** arrived more than 48 hours ago. No drafts: answer by hand if any "
            f"still matters.\n{shown}{more}")


def report_due(conn: sqlite3.Connection) -> int:
    """Post every report still owed, and stop at the first Discord refuses: the rest wait for the
    next check, in order. Never raises for one bad item. Returns how many were delivered."""
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
        if not _post(conn, content, (block,)):
            break
        store.mark_reported(conn, [item["id"]])
        delivered += 1
    return delivered


def _post(conn: sqlite3.Connection, content: str, conversation: tuple[str, ...]) -> bool:
    return discord.post(conn, CHANNEL, content, username=USERNAME, dedupe=False, suppress_embeds=True,
                        conversation=conversation).delivered
