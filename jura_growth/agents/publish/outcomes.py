"""What a join, or a group screen, came to: `publish done <A-id> --outcome …` (browser publishing
PRD §4.6, §5.4, §5.7; BP-06).

These are outcomes, never stop signals: none of them alerts or pauses (BP §4.6).

- `requested`, `member`, `declined`: a join, or its membership answers, went in as the Jura Page.
  The group's `join_status` is set, and on `member` its `joined_as = page` (AC-P4.1, AC-P4.4).
- `questions`: the group asked membership questions and the run submitted nothing. The answers it
  drafted are brand-gated, and only if they pass do they become the join's answers item with its
  own `group-join` request (AC-P4.2). A failure raises nothing; the run may send fixed answers
  once more, and a second failure drops them (`gate.py`).
- `pages-not-allowed`, for any community item: the join or post screen offered no way to act as
  the Jura Page. The group is skipped for good, and every item still waiting for it is
  superseded, its card saying why (AC-P4.3).

The item must be one this run claimed. The one exception is `questions` sent again for the same
join by the run that met them, after the brand gate asked for a regeneration.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from jura_growth import approvals, db, gate, log, timeutil
from jura_growth.agents.publish import hosts, items

JOIN_OUTCOMES = ("requested", "member", "declined")
QUESTIONS = "questions"
PAGES_NOT_ALLOWED = "pages-not-allowed"
OUTCOMES = (*JOIN_OUTCOMES, QUESTIONS, PAGES_NOT_ALLOWED)
JOIN_KINDS = (items.JOIN_ITEM, items.ANSWERS_ITEM)
GROUP_KINDS = (items.COMMUNITY_POST_ITEM, *JOIN_KINDS)


class Refused(Exception):
    """The outcome can't be recorded for this item; nothing was written."""


@dataclass(frozen=True)
class Recorded:
    """What `record()` did: one line for the run, and the answers request it raised, if any."""

    line: str
    raised: approvals.Approval | None = None
    ok: bool = True


MAX_QUESTIONS = 10
MAX_QUESTION_CHARS = 500
MAX_ANSWER_CHARS = 1000


def read_answers(text: str) -> list[dict]:
    """The questions file (`q.json`): a list of `{"question": …, "answer": …}`, or that list as
    `{"questions": [...]}`. Every question needs its answer; at most ten, each of a sane length."""
    try:
        data = json.loads(text)
    except ValueError as error:
        raise Refused(f"the questions file isn't valid JSON: {error}") from None
    if isinstance(data, dict):
        data = data.get("questions")
    if not isinstance(data, list) or not data:
        raise Refused('the questions file must be a list of {"question": …, "answer": …}')
    if len(data) > MAX_QUESTIONS:
        raise Refused(f"at most {MAX_QUESTIONS} membership questions")
    pairs = []
    for number, pair in enumerate(data, start=1):
        question = pair.get("question") if isinstance(pair, dict) else None
        answer = pair.get("answer") if isinstance(pair, dict) else None
        if not isinstance(question, str) or not question.strip() or not isinstance(answer, str) or not answer.strip():
            raise Refused(f"question {number} needs its question and its answer, as text")
        if len(question) > MAX_QUESTION_CHARS or len(answer) > MAX_ANSWER_CHARS:
            raise Refused(f"question {number} is too long (questions up to {MAX_QUESTION_CHARS} characters, "
                          f"answers up to {MAX_ANSWER_CHARS})")
        pairs.append({"question": question, "answer": answer})
    return pairs


def gate_key(found: items.Item) -> str:
    """The brand gate's attempt counter for the answers drafted at `found`'s questions."""
    return f"publish:answers:{found.label}"


def _may_send_again(conn: sqlite3.Connection, found: items.Item, run_id: int | None) -> bool:
    """The run that met the questions, sending answers again after the brand gate failed them:
    the gate still holds a failed attempt for them (a pass clears it)."""
    return (found.state == "done" and found.outcome == QUESTIONS and run_id is not None and found.run_id == run_id
            and db.scalar(conn, "SELECT 1 FROM qa_attempts WHERE item_key = ?", (gate_key(found),)) is not None)


def record(conn: sqlite3.Connection, request: approvals.Approval, found: items.Item, outcome: str, *,
           url: str | None = None, answers: list[dict] | None = None, run_id: int | None = None) -> Recorded:
    """Record `outcome` for the claimed item. Call it inside a transaction; post any card it
    raised with `cards.sweep_safely()` once that has committed (MC §4.6 A12)."""
    from jura_growth.agents.community import groups as groups_mod

    if outcome not in OUTCOMES:
        raise Refused(f"the outcome must be one of {', '.join(OUTCOMES)}")
    if outcome in (*JOIN_OUTCOMES, QUESTIONS) and found.kind not in JOIN_KINDS:
        raise Refused(f"--outcome {outcome} is for a join or its membership answers")
    if outcome == PAGES_NOT_ALLOWED and found.kind not in GROUP_KINDS:
        raise Refused(f"--outcome {outcome} is for a group's join or post screen")
    if outcome == QUESTIONS and answers is None:
        raise Refused("--outcome questions needs the questions and the drafted answers")
    if outcome == QUESTIONS and _may_send_again(conn, found, run_id):
        return _answers(conn, request, found, answers or [], run_id)
    if found.state != "claimed":
        raise Refused(f"{request.id}'s item isn't claimed (it is {found.state})")
    if url and not hosts.same_place(url, found.target_url):
        raise Refused("--url isn't the claimed item's own group; leave it out, or give the group's own address")
    _finish(conn, found, outcome, url)
    log.event(conn, "publish.done", {"item": found.label, "approval": request.id, "outcome": outcome},
              agent=items.AGENT, run_id=run_id)
    if outcome == QUESTIONS:
        return _answers(conn, request, items.get(conn, found.id) or found, answers or [], run_id)
    if outcome == PAGES_NOT_ALLOWED:
        groups_mod.pages_not_allowed(conn, group_of(found))
        # Every item still waiting for the group is gone now (`group_kinds.gone`): its request is
        # superseded, with the reason on its card, and the item withdrawn (A3).
        items.sync(conn, run_id=run_id)
        return Recorded(f"{request.id}: {outcome}; the group is skipped for good, since {groups_mod.PAGES_NOT_ALLOWED}")
    groups_mod.record_join(conn, found.ref_id, outcome)
    return Recorded(f"{request.id}: {outcome}")


def _answers(conn: sqlite3.Connection, request: approvals.Approval, found: items.Item, answers: list[dict],
             run_id: int | None) -> Recorded:
    """Brand-gate the drafted answers and, if they pass, raise them as the join's answers item
    and request. The gate doesn't alert: the questions are an outcome, not a failure (BP §4.6);
    the run gets the reasons and may send fixed answers once more."""
    met = f"{request.id}: questions recorded; nothing was submitted."
    verdict = gate.gate(conn, gate_key(found), "\n\n".join(pair["answer"] for pair in answers), agent=items.AGENT,
                        alert=False)
    if not verdict.passed:
        reasons = "\n".join(f"  - {reason}" for reason in verdict.result.reasons())
        if verdict.status == "retry":
            return Recorded(f"{met} The answers failed the brand check, so nothing was raised. Fix every reason and "
                            f"send them once more with the same command:\n{reasons}", ok=False)
        return Recorded(f"{met} The answers failed the brand check twice, so they are dropped and nothing was "
                        f"raised:\n{reasons}", ok=False)
    join = found if found.kind == items.JOIN_ITEM else items.get(conn, found.parent_item or 0)
    if join is None:
        return Recorded(f"{met} Its join is missing, so no answers were raised.", ok=False)
    made = items.create_join_answers(conn, join, answers, run_id=run_id)
    if made.approval is None or made.item is None:
        return Recorded(f"{met} No answers were raised: {made.why}", ok=False)
    return Recorded(f"{met} The answers wait for Ting Yu's decision as {made.approval.id} ({made.item.label}) in "
                    f"#approvals; a later run submits them once approved.", made.approval)


def answers_request(conn: sqlite3.Connection, found: items.Item) -> approvals.Approval | None:
    """The request over the answers raised at `found`'s membership questions, if any."""
    join_id = found.id if found.kind == items.JOIN_ITEM else found.parent_item
    row = db.one(conn, "SELECT * FROM publish_items WHERE kind = ? AND parent_item = ? AND id != ? ORDER BY id DESC "
                       "LIMIT 1", (items.ANSWERS_ITEM, join_id, found.id))
    return items.latest_request(conn, items.Item.from_row(row)) if row else None


def claimed_in_group(conn: sqlite3.Connection, run_id: int, group_id: int) -> bool:
    """Whether run `run_id` claimed a community item in the group (`publish note-rules`)."""
    return db.scalar(
        conn, f"SELECT 1 FROM publish_items WHERE run_id = ? AND claimed_at IS NOT NULL AND kind IN "
              f"({', '.join('?' for _ in GROUP_KINDS)}) AND json_extract(content_json, '$.group') = ? LIMIT 1",
        (run_id, *GROUP_KINDS, int(group_id)),
    ) is not None


def group_of(found: items.Item) -> int:
    """The register's group a community item acts in."""
    return int(found.content["group"])


def _finish(conn: sqlite3.Connection, found: items.Item, outcome: str, url: str | None) -> None:
    conn.execute(
        "UPDATE publish_items SET state = 'done', outcome = ?, post_url = ?, finished_at = ? WHERE id = ? "
        "AND state = 'claimed'",
        (outcome, url, timeutil.stamp(), found.id),
    )
