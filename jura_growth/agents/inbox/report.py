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
from typing import Callable

from datetime import timedelta

from jura_growth import approvals, caps, discord, log, privacy, timeutil
from jura_growth.agents.inbox import settings, store

CHANNEL = "mission-control"
USERNAME = "Jura growth · inbox"
FOLD_OLD_OVER = 5  # F12: more old messages than this fold into one report
FOLD_SHOWN = 40  # inbox items named in a fold before "and N more"
NAME_SHOWN = 80
SUBJECT_SHOWN = 160
CUT_NOTE = "(cut: the rest is in the mailbox)"
CUT_NOTE_SOCIAL = "(cut: the rest is in the thread)"
FLOOD_SHOWN = 10  # S15: reports in one run before the rest fold into a line
SOCIAL_HEADINGS = {"facebook-comment": "Facebook comment", "facebook-dm": "Facebook message",
                   "instagram-comment": "Instagram comment", "instagram-dm": "Instagram message"}
RUN_MESSAGE = store.RUN_MESSAGE

_LINK_TARGET = re.compile(r"\]\(\s*<?\s*(\w+)://")
_SPOILER = re.compile(r"\|(?=\|)")
_ZERO_WIDTH_SPACE = chr(0x200b)
_NOT_A_BACKTICK = chr(0x02cb)


def neutral(line: str) -> str:
    """One line of someone's text, unable to restyle anything or ping anyone (N5, A4, A5): no
    backticks to open a fence, no spoiler, no mention, and no masked link at any depth of nesting.
    A link target's address stays readable and can't be clicked, so what it is shows."""
    line = _LINK_TARGET.sub(lambda m: f"]\\({m.group(1)}[:]//", line).replace("](", "]\\(")
    line = _SPOILER.sub("|" + _ZERO_WIDTH_SPACE, line.replace("`", _NOT_A_BACKTICK))
    line = discord.defuse_mentions(line)
    return re.sub(r"^(\s*)(#{1,3}\s|-#\s)", r"\1\\\2", line)


def quoted(text: str) -> str:
    """`text` as a Discord quote: every line marked, whatever line break it used."""
    return "\n".join(f"> {neutral(line)}".rstrip() for line in store.clean_text(text).split("\n"))


def heading(item: dict) -> str:
    if item["source"] in SOCIAL_HEADINGS:
        return SOCIAL_HEADINGS[item["source"]]
    if item["source"] == RUN_MESSAGE:
        return "From the watch"
    if item["source"] == store.APP_USAGE:
        return "App usage"
    if item["source"] == store.EMAIL_SIGNAL:
        return "From the mail service"
    if item["source"] == store.ENGINE_NOTE:
        return "Inbox"
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
    copied = store.thread_of(item).get("copied") or 0
    if copied:
        extras.append(f"(they copied {copied} other{'s' if copied != 1 else ''}: reply by hand if they need it)")
    return extras


def no_text(item: dict) -> str:
    """Fixed words for a message with no text. No model guesses what a voice note says (F7)."""
    from jura_growth.agents.inbox import watch

    thread = json.loads(item["thread_json"] or "{}")
    if thread.get("from_reply_run"):
        return "(see thread)"
    return f"sent {watch.ATTACHMENTS.get(thread.get('attachment'), watch.ATTACHMENTS['other'])}, see thread"


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
        social = item["source"] in SOCIAL_HEADINGS
        lines.append(text if text else no_text(item) if social else "(no text: see the mailbox)")
        if cut:
            lines.append(CUT_NOTE_SOCIAL if social else CUT_NOTE)
        lines += _extras(item)
    return quoted("\n".join(lines))


def _fit(items: list[dict], over_by: Callable[[str], int]) -> str:
    """The quote block, cut until `over_by(block)` says it fits. What goes first is the longest
    message's end, so one long mail can't crowd out a short one."""
    texts = [item["text"] for item in items]
    cuts = [bool(item["text_cut"]) for item in items]
    while True:
        block = _block(items, texts, cuts)
        over = over_by(block)
        if over <= 0 or not any(texts):
            return block
        longest = max(range(len(texts)), key=lambda number: len(texts[number]))
        texts[longest] = texts[longest][: max(0, len(texts[longest]) - over - len(CUT_NOTE) - 8)].rstrip()
        cuts[longest] = True


def masked_length(text: str) -> int:
    """How long `text` is as a conversation piece on Discord: masking can lengthen it."""
    return len(privacy.for_discord(text, conversation=[text]))


def card_quote(items: list[dict], room: int) -> str:
    """What they said, for a card: cut to fit `room` characters as masked, because a card is always
    one message and its draft is never the part that gives way (technical review B8)."""
    block = _fit(items, lambda block: masked_length(block) - room)
    return block if masked_length(block) <= room else quoted(CUT_NOTE)


def shown_name(name: str) -> str:
    """A display name outside a quote block, unable to restyle anything or ping anyone."""
    return neutral(store.clean_line(name))[:NAME_SHOWN]


def shows_as_written(text: str) -> bool:
    """Whether `text` reaches a card byte for byte: nothing to neutralise, and nothing to mask."""
    return neutral(text) == text and privacy.for_discord(text, conversation=[text]) == text


def _next_step(newest: dict) -> str:
    """S2: the two commands he can type, on the report they are for. A suppressed person's note already
    says how to lift it, and a draft is refused until he does."""
    label = store.label(newest["id"])
    if newest["state"] == store.NEEDS_HAND_REPLY:
        return f"`/growth inbox done {label}` clears it once you have."
    if newest["state"] == store.REPORTED and newest["text"] and not newest["suppressed_by_this"]:
        return f"Want a reply anyway? `/growth inbox draft {label} [guidance]`"
    return ""


def _build(items: list[dict]) -> tuple[str, str]:
    """One conversation's report and the quote block in it, always one Discord message, measured
    masked: masking can lengthen text, and a piece past the limit would split the report."""
    newest = items[-1]
    if newest["source"] in store.NO_PERSON_SOURCES:
        high = " · **high priority**" if newest["priority"] == "high" else ""
        return f"**{store.label(newest['id'])} · {heading(newest)}**{high} · {_when(newest)}\n{newest['note']}", ""
    where = newest["sender_domain"] or "an unknown sender"
    count = f", {len(items)} messages" if len(items) > 1 else ""
    high = " · **high priority**" if newest["priority"] == "high" else ""
    head = f"**{store.label(newest['id'])} · {heading(newest)}{count}**{high} · {where}, {_when(newest)}"
    if newest["target"]:
        head += f"\nOpen: <{newest['target']}>"
    note = " ".join(dict.fromkeys(item["note"] for item in items if item["note"]))
    hint = _next_step(newest)

    def whole(block: str) -> str:
        return "\n".join(part for part in (head, block, note, hint) if part)

    block = _fit(items, lambda block: len(privacy.for_discord(whole(block), conversation=[block])) - discord.MAX_CONTENT)
    return whole(block), block


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
    """S15, D9: spam goes last, so it is the first to fold, and a high item shows first."""
    return sorted(groups, key=lambda group: (group[-1]["class"] == "spam", group[-1]["priority"] != "high"))


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
    turns = _in_turn(list(store.by_conversation(due).values()))
    shown, folded = (turns[:FLOOD_SHOWN], turns[FLOOD_SHOWN:]) if len(turns) > FLOOD_SHOWN else (turns, [])
    for group in shown:
        try:
            content, block = _build(group)
        except Exception as error:  # noqa: BLE001 - one bad row never holds up the rest
            log.event(conn, "inbox.report_refused", {"item": group[-1]["id"], "error": type(error).__name__}, level="warning", agent="inbox")
            continue
        if not _post(conn, content, (block,) if block else ()):
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


# --- #alerts for a high item (S7) ------------------------------------------------------------------


def _alert_text(conn: sqlite3.Connection, item: dict, *, again: bool) -> str:
    """Their domain and the fixed words for it, never what they said: this channel notifies. A conversation
    gets one line, for its newest high message."""
    label = store.label(item["id"])
    what = "a spam complaint" if item["source"] == store.EMAIL_SIGNAL else item["class"].replace("-", " ") if item["class"] else "a message"
    who = item["sender_domain"] or "an unknown sender"
    record = approvals.latest_for_subject(conn, store.approval_subject(item["id"]))
    if record and record.status == approvals.PENDING:
        action = f"Decide {record.id} in #approvals by {timeutil.when(record.decide_by)}."
    elif item["state"] == store.TRIAGED:
        action = "Its card follows in #approvals."
    elif item["state"] == store.NEEDS_HAND_REPLY:
        action = f"It needs a hand reply, then `/growth inbox done {label}`."
    else:
        action = "See #mission-control."
    first = f"{label} is still undecided after {caps.INBOX_HIGH_REPEAT_HOURS} hours" if again else f"{label} is high priority"
    return f"{first}: {what} from {who} ({heading(item)}). {action}"


def _still_undecided(conn: sqlite3.Connection, item: dict) -> bool:
    if item["state"] != store.WAITING:
        return True
    record = approvals.latest_for_subject(conn, store.approval_subject(item["id"]))
    return record is None or record.status == approvals.PENDING


def alert_high(conn: sqlite3.Connection) -> int:
    """Each high conversation once at once, and once more at 24 hours if he hasn't decided (S7). An
    alert Discord refuses goes again at the next check, and nothing is attempted with no webhook set."""
    if not discord.webhook_set("alerts"):
        return 0
    sent = 0
    for items in store.by_conversation(store.high_not_yet_alerted(conn)).values():
        if not discord.alert(conn, _alert_text(conn, items[-1], again=False), agent="inbox").delivered:
            return sent
        store.mark_alerted(conn, [item["id"] for item in items])
        sent += 1
    cutoff = timeutil.stamp(timeutil.now_sgt() - timedelta(hours=caps.INBOX_HIGH_REPEAT_HOURS))
    for items in store.by_conversation(store.high_alerted_before(conn, cutoff)).values():
        if not _still_undecided(conn, items[-1]):
            continue
        if not discord.alert(conn, _alert_text(conn, items[-1], again=True), agent="inbox").delivered:
            return sent
        store.mark_alerted(conn, [item["id"] for item in items], repeat=True)
        sent += 1
    return sent
