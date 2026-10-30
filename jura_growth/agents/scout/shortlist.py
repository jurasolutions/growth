"""A ranked batch of candidates (`jura-growth scout shortlist`, PRD §5.2a).

The research run gathers about `research.candidates` companies, scores each
with the §5.2a weights, and submits them all at once. The code, not the
model, decides which are kept. A day is ranked once (`scout_rankings`): a kept
lead can't be taken back, so a second batch could only keep the best of itself,
never the best of the day.

1. The batch is checked whole first (`leads.parse` for every candidate, a
   score breakdown on each, a comparison on each at or above the threshold,
   no company twice, no more than `research.candidates`). One bad candidate
   refuses the batch and changes nothing.
2. A company researched within `retention.rejection_months` is skipped: it was
   looked at and not kept, and isn't researched again.
3. The rest are ranked by score, highest first; equal scores keep the order
   they were submitted in.
4. In rank order, each goes through every add-lead rule (`leads.assess`) while
   today's shortlist has room. One refused on its contact or as already known
   gives its place to the next. Once the day's `research.shortlist` leads are
   kept, every remaining candidate at or above the threshold is recorded as
   researched, not kept, with its rank and score.

So kept leads are always the best of the day's candidates. Keeping a lead
sends nothing: the outreach caps, the warm-up and Ting Yu's approval decide that.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

import httpx

from jura_growth import db, log, timeutil
from jura_growth.agents.scout import leads, settings
from jura_growth.agents.scout.leads import LeadError


@dataclass
class Batch:
    shortlist: int
    threshold: int
    candidates: list[dict] = field(default_factory=list)

    @property
    def kept(self) -> list[dict]:
        return [c for c in self.candidates if c["status"] == "kept"]

    def as_dict(self) -> dict:
        return {
            "shortlist": self.shortlist,
            "threshold": self.threshold,
            "kept": self.kept,
            "candidates": self.candidates,
        }


def _validate(data) -> list[leads.Record]:
    if not isinstance(data, dict) or not isinstance(data.get("candidates"), list):
        raise LeadError('the file must hold {"candidates": [<lead>, ...]}, every candidate researched today')
    raw = data["candidates"]
    if not raw:
        raise LeadError("`candidates` is empty")
    limit = settings.candidates()
    if len(raw) > limit:
        raise LeadError(f"{len(raw)} candidates; submit at most {limit} candidates a run (`research.candidates`)")
    threshold = settings.score_threshold()
    records, seen, problems = [], {}, []
    for n, item in enumerate(raw, start=1):
        label = f"candidate {n}" + (f" ({item.get('company')})" if isinstance(item, dict) and item.get("company") else "")
        try:
            record = leads.parse(item)
        except LeadError as error:
            problems.append(f"{label}: {error}")
            continue
        if record.breakdown is None:
            problems.append(f"{label}: `score_breakdown` is required, with the points for each §5.2a factor")
        if record.score >= threshold and not record.comparison:
            problems.append(f"{label}: `comparison` is required at or above the threshold: one line on how it compares")
        if record.domain in seen:
            problems.append(f"{label}: {record.domain} is in the batch twice (also candidate {seen[record.domain]})")
        seen.setdefault(record.domain, n)
        records.append(record)
    if problems:
        # Every reason at once, so one rewrite fixes them all (code review N2).
        raise LeadError(f"nothing was recorded; fix {'all of these' if len(problems) > 1 else 'this'}:\n- " + "\n- ".join(problems))
    return records


def _researched_before(conn: sqlite3.Connection, domain: str) -> dict | None:
    return db.one(
        conn, "SELECT reason, score, rejected_at FROM scout_rejections WHERE domain = ? AND rejected_at >= ?",
        (domain, leads.rejection_cutoff()),
    )


def ranked_today(conn: sqlite3.Connection) -> dict | None:
    return db.one(conn, "SELECT * FROM scout_rankings WHERE day = ?", (timeutil.today_str(),))


def submit(conn: sqlite3.Connection, data, *, client: httpx.Client | None = None) -> Batch:
    """Rank the day's candidates and keep the best. All or nothing (code review S2):
    first every check, fetch and lookup with nothing written, then every write in
    one short transaction. A batch cut off part-way records nothing and leaves
    the day open, so the next run ranks it in full."""
    records = _validate(data)
    _refuse_if_ranked(conn)
    batch = Batch(shortlist=settings.shortlist(), threshold=settings.score_threshold())
    entries = []
    for record in records:
        entry = {
            "rank": None, "company": record.company, "domain": record.domain, "score": record.score,
            "status": None, "lead_id": None, "reasons": [], "notes": [],
        }
        before = _researched_before(conn, record.domain)
        if before:
            score = f", score {before['score']}" if before["score"] is not None else ""
            entry["status"] = "skipped"
            entry["reasons"] = [f"researched on {before['rejected_at'][:10]}{score} and not kept: {before['reason']}"]
        entries.append((record, entry))

    # Phase 1: decide, writing nothing. The network work (each kept candidate's
    # contact page and MX record) happens here, outside any transaction.
    ranked = sorted((pair for pair in entries if pair[1]["status"] is None), key=lambda pair: -pair[0].score)
    total, kept, addresses = len(ranked), leads.added_today(conn), {}
    decisions: list[tuple[leads.Record, dict, leads.Outcome]] = []
    for rank, (record, entry) in enumerate(ranked, start=1):
        entry["rank"] = rank
        if record.score >= batch.threshold and kept >= batch.shortlist:
            decisions.append((record, entry, _passed_over(rank, total, batch.shortlist)))
            continue
        outcome = leads.assess(conn, record, client=client, kept_today=kept)
        address = (outcome.contact or {}).get("email") if outcome.status == "ok" else None
        if address and address in addresses:
            outcome.status, outcome.pending = "rejected", {"domain": record.domain, "remember": None}
            outcome.reasons.append(f"{address} is also the address of {addresses[address]} in this batch")
        elif address:
            addresses[address] = record.company
        if outcome.status == "ok":
            kept += 1
        entry["notes"] = outcome.notes
        decisions.append((record, entry, outcome))

    # Phase 2: write it all at once.
    with db.transaction(conn):
        _refuse_if_ranked(conn)  # another run may have ranked the day meanwhile
        for record, entry, outcome in decisions:
            # A lead added by hand meanwhile counts too, so the day never passes the
            # shortlist (re-review R8).
            if outcome.status == "ok" and leads.added_today(conn) >= batch.shortlist:
                outcome = _passed_over(entry["rank"], total, batch.shortlist)
            if outcome.status == PASSED_OVER:
                leads.remember_rejection(conn, domain=record.domain, company=record.company,
                                         reason=outcome.reasons[0], score=record.score)
                entry["status"], entry["reasons"] = "not_kept", outcome.reasons
                continue
            leads.apply(conn, record, outcome)
            if outcome.status == "added":
                entry["status"], entry["lead_id"] = "kept", outcome.lead_id
            else:
                entry["status"] = "not_kept" if record.score < batch.threshold else "rejected"
                entry["reasons"] = outcome.reasons
        kept_now = sum(1 for _, e in entries if e["status"] == "kept")
        conn.execute(
            "INSERT INTO scout_rankings (day, ranked_at, run_id, candidates, kept) VALUES (?, ?, ?, ?, ?)",
            (timeutil.today_str(), timeutil.stamp(), log.current_run_id(), len(records), kept_now),
        )
        log.event(conn, "scout.shortlist", {"candidates": len(records), "kept": kept_now}, agent="scout")

    # Kept first, by rank; then the rest by rank; skipped last.
    order = {"kept": 0, "not_kept": 1, "rejected": 1, "skipped": 2}
    batch.candidates = sorted((e for _, e in entries), key=lambda e: (order[e["status"]], e["rank"] or 0))
    for entry in batch.kept:  # posts go out only once the batch is committed
        leads.post_lead(conn, entry["lead_id"])
    return batch


PASSED_OVER = "passed_over"


def _passed_over(rank: int, total: int, shortlist: int) -> leads.Outcome:
    reason = (
        f"researched, not kept: ranked {rank} of {total} on {timeutil.today_str()}; "
        f"today's shortlist of {shortlist} was full"
    )
    return leads.Outcome(PASSED_OVER, reasons=[reason])


def _refuse_if_ranked(conn: sqlite3.Connection) -> None:
    done = ranked_today(conn)
    if done:
        raise LeadError(
            f"today's candidates were ranked at {done['ranked_at'][11:16]} ({done['kept']} kept of "
            f"{done['candidates']}); a day is ranked once, so these wait for the next run"
        )
