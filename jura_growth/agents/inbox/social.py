"""The `social-reply` approval kind (PRD D1, D2, D4, D5, D7; ADR 0003). Agent `inbox-browser`, subject
`inbox_item:<id>`: the newest message in a conversation, which holds the draft.

It lives beside `watch` and is declared by the `inbox_browser` plug-in, whose pause flag stops it.

- **Content** is every byte that decides what a run does: the platform, who it acts as, the target, whether
  it is a comment or a DM, whose words it answers, the reply and the frame. A change to any of them after
  approval supersedes the request.
- **Gone** (`content` is None) means a reply mustn't go: they wrote again with words in it, the target
  doesn't hold up, or the draft has a line break, because Return sends in a DM.
- **Where a reply can go.** A DM's target must be one thread's own address (N12), and anything else is an
  item to answer by hand. A comment's target is held to its host, and the read-back holds it to its post.
- **A Request** (Instagram's folder for people who don't follow Jura) needs Accept before a reply can go.
  Approving authorises that one click, for that thread only, and the card says so (F5).
- **The switch** reads the `publish` flag: the two share the accounts, so a stop signal stops this too.

The bottom of this file answers for a reply of either kind, so `triage` and `steer` needn't know which.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass

from jura_growth import approval_settings, approvals, caps, cards, db, pause, timeutil
from jura_growth.agents.inbox import kinds as email_kinds
from jura_growth.agents.inbox import report, store, watch
from jura_growth.agents.publish import hosts

KIND = "social-reply"
AGENT = watch.AGENT
PUBLISH = watch.PUBLISH
FRAME_VERSION = "inbox-social-1"
REQUESTS = "instagram-requests"  # the surface where a thread needs Accept before a reply can go (F5)
_LINE_BREAK = re.compile(r"[\r\n\x0b\x0c\x85  ]")
_WROTE_AGAIN = "they wrote again"
_NOT_A_THREAD = "The watch couldn't keep this thread's own address, so a reply can't be bound to it. Answer by hand if it needs one."
_TOO_LONG = "The draft and its card won't fit one Discord message, so there is no card. Answer by hand if it needs one."
# What can't count as them writing again: what isn't proved to be theirs, or what was only ever a baseline.
_NOT_WRITING = (store.NOISE, store.UNVERIFIED, store.BASELINE, store.OWN)


def wrote_again(conn: sqlite3.Connection, item: dict) -> bool:
    """A newer message in the conversation with words in it (D5). One a run has just recorded and not yet
    checked counts, because holding back costs nothing. A sticker doesn't, and nor does an unproved one."""
    return any(other["id"] > item["id"] and other["text"] and other["state"] not in _NOT_WRITING
               for other in store.in_conversation(conn, item["conversation"]))


@dataclass(frozen=True)
class Reply:
    """One social reply, exactly as a run would post it now."""

    item_id: int
    platform: str
    identity: str
    target: str
    kind: str  # comment or dm
    author: str
    answers: str
    text: str
    accept_request: bool

    def content_bytes(self) -> bytes:
        """No Unicode normalisation: two drafts with different bytes never hash alike (ADR 0003)."""
        value = {"platform": self.platform, "identity": self.identity, "target": self.target, "kind": self.kind, "author": self.author,
                 "answers": self.answers, "text": self.text, "accept_request": self.accept_request, "frame": FRAME_VERSION}
        return json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")

    def content_hash(self) -> str:
        return approvals.content_hash(self.content_bytes())


def target_problem(item: dict) -> str | None:
    """Why this item's target can't take a reply: re-read from the row, whatever put it there (A10, N12)."""
    platform = store.platform_of(item)
    target = item["target"]
    found = watch.target_problem(platform, target)
    if found:
        return found
    if watch.clean_link(target) != target:
        return "an address with more on it than the watch keeps"
    page_asset = watch.pages()[platform].asset_id
    if page_asset and hosts.asset_ids(target) not in ([], [page_asset]):
        return "another Page's address in Business Suite"
    return hosts.dm_target_problem(platform, target) if store.is_dm(item) else None


def reply_of(item: dict) -> Reply | None:
    """The reply this inbox item would post, or None when it can't be posted as it stands."""
    if item["source"] not in store.SOCIAL_SOURCES or not item["draft"] or _LINE_BREAK.search(item["draft"]):
        return None
    if target_problem(item):
        return None
    platform = store.platform_of(item)
    return Reply(item["id"], platform, watch.pages()[platform].name, item["target"], "dm" if store.is_dm(item) else "comment",
                 item["sender_name"], item["text"], item["draft"], store.thread_of(item).get("surface") == REQUESTS)


# --- the card ------------------------------------------------------------------------------------


REPLY_HOURS = f"{caps.INBOX_REPLY_WINDOW[0]} to {caps.INBOX_REPLY_WINDOW[1]}"


def _card_lines(item: dict, reply: Reply, record: approvals.Approval | None) -> tuple[list[str], list[str]]:
    """The card's text around what they said: what comes before the quote, and after."""
    number = record.id if record else "A-nnnn"
    place = "under their comment" if reply.kind == "comment" else "in their thread"
    before = [f"Goes {place} on {reply.platform.capitalize()}, as {reply.identity}: <{reply.target}>"]
    if item["priority"] == "high":
        by = f": answer it by {timeutil.when(record.decide_by)}" if record else ""
        before.insert(0, f"**High priority**{by}.")
    language = email_kinds.language_line(item["language"])
    if language:
        before.append(language)
    if reply.accept_request:
        before.append("It came in as a message request, so approving also accepts the request, for this thread only.")
    after = [
        "Draft, exactly as it goes out:",
        f"> {reply.text}",
        f"Template: {FRAME_VERSION}.",
        f"Approve: posts on the next reply run, {REPLY_HOURS}.",
        "Skip: nothing goes out. Use this too if you've answered by hand.",
        f"Change: `/growth inbox redraft {number} <guidance>` or `/growth inbox reword {number} <your words>`.",
    ]
    return before, after


def card_fits(item: dict, reply: Reply) -> bool:
    before, after = _card_lines(item, reply, None)
    return email_kinds.room_for_quote(item, before, after) >= report.masked_length(report.quoted(report.CUT_NOTE_SOCIAL))


# --- the kind ------------------------------------------------------------------------------------


def switched_off(conn: sqlite3.Connection) -> str | None:
    """Why no reply can go now."""
    if not approval_settings.switch("discord_buttons"):
        return "the approval buttons aren't set up, so a reply can't be approved"
    held = pause.is_paused(conn, PUBLISH)
    if held:
        return f"publish is paused, and the two share the accounts: {held}"
    problems = watch.page_problems()
    return "; ".join(problems) if problems else None


class SocialReply(email_kinds.ReplyKind):
    """The kind `approvals` asks about every social `inbox_item:<id>`."""

    name = KIND
    agent = AGENT
    used_word = "posted"
    # Inert until approvals-first lands (technical review, "Merging"): `feed.py` reads them with getattr.
    feed_channel = "mission-control"
    feed_approved = f"It posts on the next reply run, {REPLY_HOURS}."

    def content(self, conn: sqlite3.Connection, subject: str) -> bytes | None:
        item = email_kinds.item_of(conn, subject)
        if item is None or item["state"] not in (store.WAITING, store.SENDING):
            return None
        reply = reply_of(item)
        if reply is None or wrote_again(conn, item):
            return None
        return reply.content_bytes()

    def preview(self, conn: sqlite3.Connection, subject: str) -> approvals.Preview:
        """D1: what they said, who and where, the draft exactly as it goes out, and each answer's next step."""
        item = email_kinds.item_of(conn, subject)
        reply = reply_of(item) if item else None
        if item is None or reply is None:
            raise LookupError(f"no reply for {subject}")
        before, after = _card_lines(item, reply, approvals.latest(conn, KIND, subject))
        quote = report.card_quote(email_kinds.unanswered(conn, item), email_kinds.room_for_quote(item, before, after))
        return approvals.Preview(title=email_kinds.title_of(item), reason=email_kinds.reason_of(item), text="\n".join([*before, quote, *after]))

    def switched_off(self, conn: sqlite3.Connection, subject: str) -> str | None:
        return switched_off(conn)

    def superseded_note(self, conn: sqlite3.Connection, subject: str) -> str | None:
        item = email_kinds.item_of(conn, subject)
        if item is None:
            return None
        if item["state"] == store.ANSWERED_BY_HAND:
            return "answered by hand"
        if item["state"] == store.CLOSED:
            return "the target went away"
        if item["state"] == store.NEEDS_HAND_REPLY:
            return "a reply run couldn't go on: answer by hand if it matters"
        return _WROTE_AGAIN if wrote_again(conn, item) or item["state"] == store.SUPERSEDED else None


def kinds() -> dict[str, SocialReply]:
    return {KIND: SocialReply()}


# --- raising and settling -----------------------------------------------------------------------


def read_again(conn: sqlite3.Connection) -> None:
    """Judge every open request by the clock and what would go out now, and bring the cards up to date."""
    approvals.expire_due(conn)
    cards.sweep_safely(conn)


def raise_due(conn: sqlite3.Connection) -> list[approvals.Approval]:
    """A request for each social draft that has none yet. Returns those raised. A draft that can't have a
    card ends needing a hand reply, and one with a newer message waits for triage to replace it."""
    if switched_off(conn) or pause.is_paused(conn, AGENT):
        return []
    raised = []
    for item in store.drafts_without_a_card(conn, store.SOCIAL_SOURCES):
        with db.transaction(conn):
            reply = reply_of(item)
            if reply is None:
                store.set_item_state(conn, item["id"], store.NEEDS_HAND_REPLY, note=_NOT_A_THREAD)
                continue
            if wrote_again(conn, item):
                continue
            if not card_fits(item, reply):
                store.set_item_state(conn, item["id"], store.NEEDS_HAND_REPLY, note=_TOO_LONG)
                continue
            store.set_item_state(conn, item["id"], store.WAITING)
            found = email_kinds.raise_request(conn, email_kinds.subject_of(item["id"]), reason=email_kinds.reason_of(item), kind=KIND)
            if found is not None:
                raised.append(found)
    return raised


def settle_waiting(conn: sqlite3.Connection) -> None:
    email_kinds.settle_waiting(conn, SocialReply())


# --- either kind ---------------------------------------------------------------------------------


def kind_of(item: dict) -> str:
    return KIND if item["source"] in store.SOCIAL_SOURCES else email_kinds.KIND


def latest_for(conn: sqlite3.Connection, item: dict) -> approvals.Approval | None:
    return approvals.latest(conn, kind_of(item), email_kinds.subject_of(item["id"]))


def raise_for(conn: sqlite3.Connection, item: dict, *, reason: str) -> approvals.Approval | None:
    return email_kinds.raise_request(conn, email_kinds.subject_of(item["id"]), reason=reason, kind=kind_of(item))


def card_problem(conn: sqlite3.Connection, candidate: dict) -> str | None:
    """Why this draft can't go on a card, in Ting Yu's words, or None. For a reply of either kind."""
    if candidate["source"] in store.SOCIAL_SOURCES:
        reply = reply_of(candidate)
        if reply is None:
            return "It can't be posted to that thread, or it has a line break."
        return None if card_fits(candidate, reply) else "It won't fit on one card with what they said. Shorten it."
    found = email_kinds.reply_of(candidate)
    if found is None:
        return "It has no single address to answer."
    return None if email_kinds.card_fits(conn, candidate, found) else "It won't fit on one card with what they said. Shorten it."
