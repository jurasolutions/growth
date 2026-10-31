"""Triage: what the model may do, and everything that holds whatever it does.

A person's words are hostile input and the model reads them, so nothing here trusts it. It gets the
waiting conversations from `hand_out` (`inbox pending --json`) and answers each with a class and maybe
a draft (`submit`, `inbox submit --file`). Its only output is that class and that draft, and the draft
goes to Ting Yu.

- **A conversation is the unit (F8):** every message from one person in one thread. The newest new
  message holds the draft, and one report lists them all. Someone who says "how much?" and then
  "thanks" still gets an answer about the price, because a class that carries no draft is refused
  while an earlier draft is open.
- **It can't hide a person (R3, F3):** no class it gives ends in silence. `noise` needs evidence in the
  headers, and mail with that evidence never reaches it, because the intake filed it already. So here
  `noise` only ever reports the person, saying that triage took it for noise.
- **It can't stall the mail (B5 rule 4):** each hand-out counts an attempt, and after two the
  conversation needs a hand reply. A conversation being retried goes out alone among retries, so a
  message that breaks a run can't take the others down with it. A run that died before asking for
  anything counts against what it would have been given.
- **One person can't suppress another (code review 02, SEC-2):** a run answers only what it was handed.
  Up to 10 strangers share a session, so an `opt-out` read beside other people's words isn't acted on:
  that conversation is read again alone, and only then does it suppress. It only ever suppresses the
  mail's own sender, never an address typed on the form or a sender the server says failed.
- **Its words stay out (S2):** `after_run` writes the run's summary from the records, and a failure
  there doesn't count toward auto-pause, so a bad message can't stop the mail.

What needs no model, `settle` does first: someone who opted out and wrote again, and a message with no
words in it. No approval is raised in the precheck, ever (N10).
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
from dataclasses import dataclass, field

from jura_growth import approvals, brand_check, caps, cards, db, discord, gate, log, paths, privacy, timeutil
from jura_growth.agents.inbox import checks, kinds, mail, report, settings, store
from jura_growth.agents.outreach import replies

AGENT = "inbox"
JOB = "inbox-check"
WITH_DRAFT = frozenset({"question", "interest", "request", "complaint", "correction", "comment", "data-request"})
NO_DRAFT = frozenset({"like", "emoji", "thanks", "kind-words", "out-of-office", "not-interested", "opt-out", "spam", "noise"})
CLASSES = WITH_DRAFT | NO_DRAFT
# Always high (D9). The prompt makes a threat, a refund, a legal matter or a named client high too.
ALWAYS_HIGH = frozenset({"complaint", "data-request"})
# These are never answered, so an earlier open draft doesn't force one (E2, E6). Not `noise`: it can be
# steered, and a question would lose its draft to it (F8).
NOT_ANSWERED_WHATEVER_CAME_BEFORE = frozenset({"opt-out", "not-interested", "spam"})
# Said by the person themselves, these stop every draft to that address, under any subject (E2; P-1).
CLOSES_THEIR_DRAFTS = frozenset({"opt-out", "not-interested"})
PRIORITIES = ("normal", "high")
LANGUAGES = ("English", "Chinese", "Malay", "Tamil", "Hindi", "Indonesian", "Tagalog", "Thai", "Vietnamese", "Japanese", "Korean",
             "French", "German", "Spanish", "Other")
MESSAGES_SHOWN = 20
SITE = f"https://{settings.JURA_DOMAIN}"

_LABEL = re.compile(r"^I-(\d{1,9})$")
_HANDED_OUT = "triage.handed_out"  # the run, and the conversations it was given
_READ_ALONE = "triage.read_alone."  # + a conversation: its opt-out waits for a session of its own
_FAILURE = "triage"  # the label its problem goes under on the health strip

_NOTE = {
    "like": "No reply needed: there is nothing in it to answer.",
    "emoji": "No reply needed: there is nothing in it to answer.",
    "thanks": "No reply needed: they said thanks.",
    "kind-words": "No reply needed: they said something kind, and it asks for nothing.",
    "out-of-office": "No reply needed: it's an out-of-office.",
    "not-interested": "No reply needed: they said not now, so nothing is drafted.",
    "spam": "It looks like spam or abuse, so nothing is drafted. The engine never hides, deletes or blocks anything: do that by hand if you agree.",
    "noise": "Triage took this for noise, but nothing in its headers says so, so it is reported. No draft: answer by hand if it needs one.",
}
_OPTED_OUT = "Triage read this as an opt-out, and the address is suppressed. No reply will be drafted. If that's wrong, `/growth inbox unsuppress {label}` lifts it."
_OPTED_OUT_SOCIAL = "They asked not to hear from Jura, so nothing is drafted."
_OPTED_OUT_UNPROVEN = ("Triage read this as an opt-out, but nothing shows this address is theirs to speak for, so it isn't suppressed. "
                       "No reply will be drafted. Suppress it by hand if it's right.")
_GAVE_UP = "Triage couldn't finish this one, so there is no draft. Answer by hand if it needs one."
_DROPPED = "Two drafts failed the brand check, so there is none. Answer by hand if it needs one."
_NO_WORDS = "There are no words in it to answer: see the mailbox or the thread."
_DRAFT_READY = "Next: a draft is ready, and a card follows in #approvals."
_WROTE_AGAIN = "They wrote again, so this draft is replaced."


# --- what needs no model ----------------------------------------------------------------


def settle(conn: sqlite3.Connection) -> int:
    """Everything waiting that needs no model: F14, a message with no words, and a conversation out
    of attempts. Returns how many were closed. Each ends needing a hand reply, and reports."""
    _settle_redrafts(conn)
    limit = caps.INBOX_TRIAGE_ATTEMPTS
    closed = 0
    for item in store.waiting_for_triage(conn):
        reason = kinds.suppressed_because(conn, item)
        if reason:
            note = kinds.opted_out_earlier(reason)
        elif not item["text"]:
            note = _NO_WORDS
        elif item["triage_attempts"] >= limit:
            note = _GAVE_UP
            log.event(conn, "inbox.triage_gave_up", {"item": item["id"]}, level="warning", agent=AGENT)
        else:
            continue
        with db.transaction(conn):
            # A sticker isn't an answer to anything, so a question's draft stands (F8).
            _close(conn, [item], store.NEEDS_HAND_REPLY, note=note, replaces_earlier=bool(item["text"]))
        closed += 1
    return closed


def waiting(conn: sqlite3.Connection) -> bool:
    return bool(_conversations(conn))


def note_without_its_verdict(note: str) -> str:
    """A note with triage's own last word taken out, when Ting Yu sends it back: the intake's warning stays."""
    for verdict in (*_NOTE.values(), _GAVE_UP, _DROPPED, _NO_WORDS, _DRAFT_READY, _OPTED_OUT_SOCIAL, _OPTED_OUT_UNPROVEN):
        note = note.replace(verdict, "")
    return " ".join(note.split())


def _redraft_note(conn: sqlite3.Connection, item: dict, what_happened: str) -> None:
    """His redraft came to nothing: the card stands as it was, and he hears so, once. Inside a transaction."""
    record = approvals.latest(conn, kinds.KIND, kinds.subject_of(item["id"]))
    number = record.id if record else store.label(item["id"])
    store.clear_ask(conn, item["id"])
    store.set_brand_failures(conn, [item["id"]], 0)
    store.engine_note(conn, f"redraft-{item['id']}", f"The redraft of {number} {what_happened}, so that card stays open as it was. "
                                                     f"Approve it, skip it, or `/growth inbox reword {number} <your words>`.")


def _settle_redrafts(conn: sqlite3.Connection) -> None:
    """A redraft he has since decided past, or that has used its attempts. Neither touches the card."""
    limit = caps.INBOX_TRIAGE_ATTEMPTS
    for item in store.asked_redrafts(conn):
        record = approvals.latest(conn, kinds.KIND, kinds.subject_of(item["id"]))
        with db.transaction(conn):
            if record is None or record.status != approvals.PENDING:
                store.clear_ask(conn, item["id"])
                log.event(conn, "inbox.redraft_dropped", {"item": item["id"]}, agent=AGENT)
            elif item["triage_attempts"] >= limit:
                _redraft_note(conn, item, "couldn't be finished")


# --- the hand-out -----------------------------------------------------------------------


def _conversations(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """Every conversation waiting, oldest first, with its waiting messages. A redraft he asked for counts
    as one, unless they have written since: the new message's draft answers that too, under his guidance."""
    new = store.waiting_for_triage(conn)
    written = {item["conversation"] for item in new}
    asked = [item for item in store.asked_redrafts(conn) if item["conversation"] not in written]
    return store.by_conversation(sorted([*new, *asked], key=lambda item: item["id"]))


def _chosen(conn: sqlite3.Connection) -> list[list[dict]]:
    """What a run is given. One read alone, if an opt-out waits for that (SEC-2). Otherwise, B5 rule 4:
    at most one conversation that has been tried before, so a message that breaks a run can only
    break its own, then what fits."""
    limit = settings.limit("triage_per_run")
    waiting_now = _conversations(conn)
    for conversation, _ in store.with_prefix(conn, _READ_ALONE):
        if conversation in waiting_now:
            return [waiting_now[conversation]]
    every = list(waiting_now.values())
    retries = [c for c in every if any(item["triage_attempts"] for item in c)]
    fresh = [c for c in every if not any(item["triage_attempts"] for item in c)]
    return (retries[:1] + fresh)[:limit]


def _open_draft(conn: sqlite3.Connection, conversation: str, waiting_ids: set[int]) -> dict | None:
    """An earlier message's draft still waiting to go, or still on a card."""
    open_states = (store.TRIAGED, store.WAITING)
    earlier = [item for item in store.in_conversation(conn, conversation)
               if item["state"] in open_states and item["id"] not in waiting_ids]
    return earlier[-1] if earlier else None


def _channel(item: dict) -> str:
    return "inbox-email" if item["source"] in store.MAIL_SOURCES else "inbox-social"


def _is_public(item: dict) -> bool:
    return item["source"].endswith("-comment")


def _platform(item: dict) -> str | None:
    return None if item["source"] in store.MAIL_SOURCES else item["source"].split("-")[0]


def _message(item: dict) -> dict:
    return {
        "id": store.label(item["id"]),
        "new": item["state"] == store.NEW or bool(item["asked_at"]),
        "received": item["received_at"] or item["recorded_at"],
        "subject": item["subject"],
        "text": item["text"],
        "cut_at_the_limit": bool(item["text_cut"]),
        "attachments_not_opened": json.loads(item["attachments_json"] or "[]"),
    }


def _shown(conn: sqlite3.Connection, items: list[dict]) -> dict:
    newest = items[-1]
    every = store.history(conn, newest["conversation"])
    earlier = _open_draft(conn, newest["conversation"], {item["id"] for item in items if item["state"] == store.NEW})
    asked_of = [item for item in [*store.in_conversation(conn, newest["conversation"])] if item["asked_at"]]
    return {
        "id": store.label(newest["id"]),
        "channel": _channel(newest),
        "public": _is_public(newest),
        "platform": _platform(newest),
        "source": newest["source"],
        "sender_name": newest["sender_name"],
        "sender_domain": newest["sender_domain"],
        "answers_our_outreach": newest["lead_id"] is not None,
        "guidance": next((item["guidance"] for item in reversed([*asked_of, *items]) if item["guidance"]), None),
        "must_draft": earlier is not None or bool(asked_of),
        "earlier_draft": earlier["draft"] if earlier else None,
        "brand_failures": max(item["brand_failures"] for item in items),
        "messages": [_message(item) for item in every[-MESSAGES_SHOWN:]],
    }


def _grounds() -> dict:
    """What a draft may say about Jura (E4). It lives outside what this session can read (B4), so it
    is printed for it. Nothing is copied."""
    from jura_growth.agents.social import toolbox

    file = paths.inputs_dir() / "services.md"
    tools, _ = toolbox.load()
    return {
        "services": file.read_text(encoding="utf-8") if file.exists() else "",
        "toolbox": [{"name": tool.name, "url": tool.url(SITE), "description": tool.description} for tool in tools],
        "approved_claims": list(brand_check.approved_phrases()),
    }


def _given_to_run(conn: sqlite3.Connection, run_id: int | None) -> list[str] | None:
    """The conversations this run was handed, or None if it hasn't been handed any."""
    raw = store.get_state(conn, _HANDED_OUT)
    record = json.loads(raw) if raw else None
    return record["conversations"] if record and run_id is not None and record["run"] == run_id else None


def hand_out(conn: sqlite3.Connection) -> dict:
    """What the model reads, as `inbox pending --json` prints it. A run's first call counts an
    attempt for each conversation it is given, and a second look shows the same ones, less what it
    has handed in. Outside a run nothing is counted, since nothing can break."""
    run_id = log.current_run_id()
    given = _given_to_run(conn, run_id)
    if given is not None:
        waiting_now = _conversations(conn)
        chosen = [waiting_now[conversation] for conversation in given if conversation in waiting_now]
    else:
        chosen = _chosen(conn)
    if run_id is not None and given is None:
        with db.transaction(conn):
            store.count_attempt(conn, [item["id"] for items in chosen for item in items])
            store.set_state(conn, _HANDED_OUT, json.dumps({"run": run_id, "conversations": [items[-1]["conversation"] for items in chosen]}))
    return {
        "scratch": str(paths.work_dir(JOB)),
        "classes_with_a_draft": sorted(WITH_DRAFT),
        "classes_without_a_draft": sorted(NO_DRAFT),
        "languages": list(LANGUAGES),
        "grounds": _grounds(),
        "conversations": [_shown(conn, items) for items in chosen],
    }


# --- the answer -------------------------------------------------------------------------


@dataclass
class Submitted:
    """What `inbox submit` says. `exit_code` 0 is taken, 1 is a brand refusal (it may use its one
    regeneration, or it has just been dropped), 2 is a mistake to fix, which uses up nothing."""

    exit_code: int
    lines: list[str] = field(default_factory=list)

    def text(self) -> str:
        return "\n".join(self.lines)


def _refused(*problems: str) -> Submitted:
    return Submitted(2, ["refused, fix this and submit again:", *[f"  - {problem}" for problem in problems]])


def _one_of(value, allowed) -> bool:
    return isinstance(value, str) and value in allowed


def _shape(payload) -> list[str]:
    if not isinstance(payload, dict):
        return ["the file holds one JSON object"]
    problems = []
    if not isinstance(payload.get("id"), str) or not _LABEL.match(payload["id"]):
        problems.append("`id` is the conversation's id, like I-0007")
    if not _one_of(payload.get("class"), CLASSES):
        problems.append(f"`class` is one of: {', '.join(sorted(CLASSES))}")
    if not _one_of(payload.get("priority", "normal"), PRIORITIES):
        problems.append("`priority` is normal or high")
    if not _one_of(payload.get("language", "English"), LANGUAGES):
        problems.append(f"`language` is one of: {', '.join(LANGUAGES)}")
    if not isinstance(payload.get("draft") or "", str):
        problems.append("`draft` is text")
    return problems


def submit(conn: sqlite3.Connection, payload) -> Submitted:
    """Store one conversation's class and draft, and leave it ready for its report and its card."""
    problems = _shape(payload)
    if problems:
        return _refused(*problems)
    found = store.get(conn, int(payload["id"].removeprefix("I-")))
    conversation = store.in_conversation(conn, found["conversation"]) if found else []
    items = [i for i in conversation if i["state"] == store.NEW] or [i for i in conversation if i["state"] == store.WAITING and i["asked_at"]]
    if not found or not items:
        return _refused(f"{payload['id']} has nothing waiting: `inbox pending --json` lists what does")
    run_id = log.current_run_id()
    given = _given_to_run(conn, run_id)
    if run_id is not None and found["conversation"] not in (given or ()):
        return _refused(f"{payload['id']} wasn't handed to this run: only what `inbox pending --json` printed may be answered")

    kind = payload["class"]
    draft = store.clean_text(payload.get("draft") or "").strip()
    if kind in NO_DRAFT and draft:
        return _refused(f"class {kind} carries no draft (E1): remove it, or choose a class that does")
    if kind in WITH_DRAFT and not draft:
        return _refused(f"class {kind} needs a draft (E1)")
    if items[-1]["asked_at"] and kind in NO_DRAFT:
        return _refused(f"Ting Yu asked for a draft on {payload['id']}: class it for what they need, with one, not {kind}")
    earlier = _open_draft(conn, found["conversation"], {item["id"] for item in items if item["state"] == store.NEW})
    if earlier and kind in NO_DRAFT - NOT_ANSWERED_WHATEVER_CAME_BEFORE:
        return _refused(f"an earlier message in this conversation still needs an answer (F8): class it for that, "
                        f"with a draft that answers all of it, not {kind}")
    reason = kinds.suppressed_because(conn, items[-1])
    if reason:  # they were suppressed after the hand-out
        with db.transaction(conn):
            _close(conn, items, store.NEEDS_HAND_REPLY, note=kinds.opted_out_earlier(reason))
        return Submitted(0, [f"{payload['id']}: this address is suppressed, so it needs a hand reply"])

    if kind in WITH_DRAFT:
        return _with_draft(conn, payload, items, kind, draft)
    if kind == "opt-out" and given is not None and len(given) > 1:
        return _read_alone(conn, payload, items)
    _without_draft(conn, payload, items, kind)
    return Submitted(0, [f"OK: {payload['id']} classed {kind}"])


def _read_alone(conn: sqlite3.Connection, payload: dict, items: list[dict]) -> Submitted:
    """SEC-2: this session held other people's words too, and one of them may have asked for this. So
    it acts on nothing, and the conversation gets one more read in a session of its own."""
    with db.transaction(conn):
        store.set_state(conn, f"{_READ_ALONE}{items[-1]['conversation']}", timeutil.stamp())
        store.set_attempts(conn, [item["id"] for item in items], caps.INBOX_TRIAGE_ATTEMPTS - 1)
        log.event(conn, "inbox.opt_out_read_again", {"item": items[-1]["id"]}, agent=AGENT)
    return Submitted(0, [f"OK: {payload['id']} noted. It is read again on its own next time, so leave it"])


def _without_draft(conn: sqlite3.Connection, payload: dict, items: list[dict], kind: str) -> None:
    newest = items[-1]
    with db.transaction(conn):
        if kind == "opt-out":
            if store.thread_of(newest).get("own_sender"):
                replies.honour_opt_out(conn, newest["sender_address"], newest["lead_id"], newest["key"])
                note = _OPTED_OUT.format(label=store.label(newest["id"]))
            else:
                note = _OPTED_OUT_UNPROVEN if newest["sender_address"] else _OPTED_OUT_SOCIAL
        else:
            note = _NOTE[kind]
        _close(conn, items, store.REPORTED, note=note, kind=kind, priority=payload.get("priority", "normal"))
        if kind in CLOSES_THEIR_DRAFTS and (store.thread_of(newest).get("own_sender") or newest["source"] == "enquiry"):
            kinds.close_drafts_to(conn, newest)  # never on a forged sender's word (SEC-6)
        log.event(conn, "inbox.triaged", {"item": newest["id"], "class": kind}, agent=AGENT)


def draft_problems(conn: sqlite3.Connection, newest: dict, draft: str, *, high: bool) -> list[brand_check.Issue]:
    """Everything that stops `draft` going on `newest`'s card: the brand channel, and anything masking
    would change, whoever wrote it."""
    every = store.history(conn, newest["conversation"])
    their_words = "\n".join(part for item in every for part in (item["subject"], item["text"]) if part)
    context = {"sender_name": newest["sender_name"], "their_words": their_words, "public": _is_public(newest),
               "platform": _platform(newest), "high": high}
    issues = list(brand_check.check(draft, channel_name=_channel(newest), context=context).issues)
    privacy.load_for_masking(conn)
    if privacy.for_discord(draft, conversation=[draft]) != draft:  # B3: the card must show the exact bytes
        issues.append(brand_check.Issue("channel", "It holds a phone number, a person's address or a secret, which would be masked on the card"))
    return issues


def _redrafted(conn: sqlite3.Connection, payload: dict, item: dict, kind: str, draft: str, high: bool) -> Submitted:
    """The redraft he asked for. In one transaction the new request is raised and the old card closes
    (S1), so a failure anywhere leaves the card he has."""
    candidate = {**item, "draft": draft, "class": kind, "priority": "high" if high else item["priority"]}
    reply = kinds.reply_of(candidate)
    if reply is None or not kinds.card_fits(conn, candidate, reply):
        return _brand_failed(conn, payload, [item], [brand_check.Issue("channel", "It won't fit on one card with what they said")])
    with db.transaction(conn):
        store.update_draft(conn, item["id"], draft, promised=high or checks.promises_a_reply(draft), kind=kind,
                           priority="high" if high else None, language=payload.get("language"))
        kinds.raise_request(conn, kinds.subject_of(item["id"]), reason=kinds.reason_of(candidate))
        log.event(conn, "inbox.triaged", {"item": item["id"], "class": kind}, agent=AGENT)
    cards.sweep_safely(conn)
    return Submitted(0, [f"OK: {payload['id']} redrafted"])


def _with_draft(conn: sqlite3.Connection, payload: dict, items: list[dict], kind: str, draft: str) -> Submitted:
    newest = items[-1]
    high = payload.get("priority") == "high" or kind in ALWAYS_HIGH or (newest["state"] == store.WAITING and newest["priority"] == "high")
    issues = draft_problems(conn, newest, draft, high=high)
    if issues:
        return _brand_failed(conn, payload, items, issues)
    if newest["state"] == store.WAITING:
        return _redrafted(conn, payload, newest, kind, draft, high)

    language = payload.get("language", "English")
    parts = ["High priority." if high else "", kinds.language_line(language), _DRAFT_READY]
    with db.transaction(conn):
        _close(conn, items[:-1], store.REPORTED, kind=kind, priority="high" if high else "normal", language=language)
        _close(conn, [newest], store.TRIAGED, note=" ".join(part for part in parts if part), kind=kind,
               priority="high" if high else "normal", language=language, draft=draft,
               promised=high or checks.promises_a_reply(draft))
        log.event(conn, "inbox.triaged", {"item": newest["id"], "class": kind}, agent=AGENT)
    _raise_its_card(conn, newest["id"])
    return Submitted(0, [f"OK: {payload['id']} classed {kind}, draft kept"])


def _raise_its_card(conn: sqlite3.Connection, item_id: int) -> None:
    """Where a fresh draft's request is raised, and never in the precheck (N10). The card goes up once
    it has committed. A failure here can't undo the draft just handed in: the next send slot does it."""
    try:
        if kinds.raise_due(conn):
            cards.sweep_safely(conn)
    except Exception as error:  # noqa: BLE001
        log.event(conn, "inbox.raise_failed", {"item": item_id, "error": type(error).__name__}, level="warning", agent=AGENT)


def _brand_failed(conn: sqlite3.Connection, payload: dict, items: list[dict], issues: list[brand_check.Issue]) -> Submitted:
    """D8, the repo's rule: fix every reason in one regeneration. A second failure drops the draft.
    The same rule as `gate.gate`, and not through it, because that logs and alerts each reason with its
    excerpt, and an excerpt of this draft can hold what a stranger steered. Here only the rule's name
    is logged, and the alert is fixed text."""
    label = payload["id"]
    tries = max(item["brand_failures"] for item in items) + 1
    rules = sorted({issue.rule for issue in issues})
    redraft = items[-1]["state"] == store.WAITING
    with db.transaction(conn):
        store.set_brand_failures(conn, [item["id"] for item in items], tries)
        log.event(conn, "inbox.draft_refused", {"item": items[-1]["id"], "try": tries, "rules": rules}, agent=AGENT)
        if tries >= gate.MAX_ATTEMPTS and redraft:
            _redraft_note(conn, items[-1], "failed the brand check twice")
        elif tries >= gate.MAX_ATTEMPTS:
            _close(conn, items, store.NEEDS_HAND_REPLY, note=_DROPPED, kind=payload["class"])
    listed = [f"  - {issue}" for issue in issues]
    if tries < gate.MAX_ATTEMPTS:
        return Submitted(1, [f"{label}: the brand check refused this draft. Fix every reason in one regeneration:", *listed])
    if redraft:
        return Submitted(1, [f"{label}: the brand check refused this draft again, so it is dropped. Don't try again.", *listed])
    discord.alert(conn, f"{store.label(items[-1]['id'])}: two drafts failed the brand check, so it needs a hand reply.", agent=AGENT)
    return Submitted(1, [f"{label}: the brand check refused this draft again, so it is dropped. Don't try again.", *listed])


def _close(conn: sqlite3.Connection, items: list[dict], state: str, *, note: str = "", kind: str | None = None,
           priority: str | None = None, language: str | None = None, draft: str | None = None, promised: bool = False,
           replaces_earlier: bool = True) -> None:
    """These messages are done with triage, and unless told otherwise any earlier draft in their
    conversation is replaced: never send it over a newer message (D5)."""
    if not items:
        return
    ids = [item["id"] for item in items]
    store.clear_state(conn, f"{_READ_ALONE}{items[-1]['conversation']}")
    for item in store.in_conversation(conn, items[-1]["conversation"]) if replaces_earlier else ():
        if item["state"] in (store.TRIAGED, store.WAITING) and item["id"] < min(ids):
            store.update_triage(conn, item["id"], state=store.SUPERSEDED, note=_WROTE_AGAIN, draft=item["draft"], kind=item["class"],
                                priority=item["priority"], language=item["language"], promised=bool(item["promised"]))
    for item in items:
        said = " ".join(part for part in (item["note"], note) if part)  # the intake's warning stays
        store.update_triage(conn, item["id"], state=state, note=said, kind=kind, priority=priority, language=language, draft=draft,
                            promised=promised)


# --- after a run ------------------------------------------------------------------------


def _attempt_for_a_run_that_never_asked(conn: sqlite3.Connection, run_id: int | None) -> bool:
    """A run that died before `inbox pending` was given nothing, so nothing counted, and those
    messages would wait unreported for as long as it keeps dying. It counts against what it would
    have been given. This goes past B5 rule 4's "bumped at hand-out" to serve R3: nobody waits
    unreported through an outage, though each may then be reported with no draft."""
    if run_id is None or _given_to_run(conn, run_id) is not None:
        return False
    ids = [item["id"] for items in _chosen(conn) for item in items]
    with db.transaction(conn):
        store.count_attempt(conn, ids)
    return bool(ids)


def _clear_scratch() -> None:
    """Their drafts have been handed in, and the next session holds someone else's words. The
    transcript keeps the run for its 7 days."""
    folder = paths.work_dir(JOB)
    for entry in folder.iterdir() if folder.exists() else ():
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def after_run(conn: sqlite3.Connection, run_id: int | None, outcome):
    """The run's last word. The model's summary, its `FAIL:` line and anything it quoted never reach
    the run row, #alerts or a run update (S2): these words are ours, from the records. A failure
    alerts once a day and leaves the run `ok`, so it can't add up to an auto-pause (B5, S10)."""
    from jura_growth import runner

    never_asked = _attempt_for_a_run_that_never_asked(conn, run_id)
    settle(conn)
    report.report_due(conn)
    report.alert_high(conn)
    _clear_scratch()
    done = db.scalar(conn, "SELECT count(*) FROM events WHERE kind = 'inbox.triaged' AND run_id = ?", (run_id,)) or 0
    left = len(_conversations(conn))
    failed = outcome.status == "failed" or never_asked
    summary = f"triage: {done} conversation{'s' if done != 1 else ''} classed, {left} waiting"
    if failed:
        summary += "; the run didn't finish"
        log.event(conn, "inbox.triage_failed", {"classed": done, "waiting": left}, level="warning", agent=AGENT, run_id=run_id)
        mail.problem(conn, _FAILURE, "A triage run didn't finish. What it didn't reach gets one more try, then a report asking for a hand reply.",
                     "triage")
    else:
        mail.cleared(conn, _FAILURE)
    return runner.Outcome("ok", summary=summary, cost_usd=outcome.cost_usd)


def failed_closed(conn: sqlite3.Connection, run_id: int | None, outcome, error: Exception):
    """The outcome when the checks themselves broke: the model's words still stay out, and nothing
    counts toward auto-pause. Each step is tried, and none can change that."""
    from jura_growth import runner

    name = type(error).__name__
    problem = f"The checks after a triage run couldn't finish ({name}). The next check tries again."
    for step in (
        lambda: log.event(conn, "inbox.triage_checks_failed", {"error": name}, level="error", agent=AGENT, run_id=run_id),
        lambda: mail.problem(conn, _FAILURE, problem, name),
        lambda: report.report_due(conn),
    ):
        try:
            step()
        except Exception:  # noqa: BLE001 - the outcome below stands whatever happens here
            pass
    return runner.Outcome("ok", summary=f"triage: the checks after run {run_id} couldn't finish ({name})",
                          cost_usd=getattr(outcome, "cost_usd", None))
