"""Filing a factory-written app PRD: `jura-growth apps submit-prd`.

Order: the daily limits, the template and factory rules (`prd.py`), then the
brand gate with its one regeneration, then the file, the backlog, the
database row and the #app-factory post. A structural rejection never uses up
the brand gate's attempts.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from jura_growth import brand_check, db, discord, gate, log, paths, timeutil
from jura_growth.agents.apps import backlog, catalog
from jura_growth.agents.apps import prd as prd_mod

NAME = catalog.NAME
CHANNEL = "app-copy"


@dataclass
class Submission:
    ok: bool
    lines: list[str] = field(default_factory=list)
    app_id: str = ""
    name: str = ""
    path: str = ""
    status: str = ""  # filed, rejected, refused, retry, dropped, checked

    @property
    def summary(self) -> str:
        if self.ok and self.status == "filed":
            return f"{self.app_id} {self.name} written to {self.path}"
        return self.lines[0] if self.lines else self.status


def context(conn: sqlite3.Connection) -> prd_mod.FactoryContext:
    settings = catalog.settings()
    slugs, names = catalog.taken(conn)
    fetched = None
    run_id = log.current_run_id()
    if run_id is not None and settings.get("require_fetch_in_run", True):
        from jura_growth.agents.community import transcript

        found = transcript.for_run(run_id)
        if found is not None:
            fetched = found.fetched_urls()
    return prd_mod.FactoryContext(
        today=timeutil.today_str(),
        next_number=catalog.next_number(conn),
        taken_slugs=slugs,
        taken_names=names,
        official_domains=tuple(settings.get("extra_official_domains") or ()),
        source_max_age_days=int(settings.get("official_source_max_age_days", 7)),
        fetched_urls=fetched,
        name_words=tuple(settings.get("name_words") or ()),
        banned_name_words=tuple(settings.get("banned_name_words") or ()),
        categories=tuple(settings.get("categories") or prd_mod.CATEGORIES),
    )


def brand_parts(parsed: prd_mod.AppPrd) -> dict:
    """What the brand checker reads: every §5.2 string plus the §1 text."""
    body = [parsed.one_line, parsed.who, parsed.why, parsed.registry_entry().get("description", "")]
    headings = [parsed.name]
    for item in parsed.copy():
        (headings if item.kind == "heading" else body).append(item.text)
    sources = [u for u in prd_mod.official_urls(parsed.official_sources)]
    return {
        "text": "\n".join(t for t in body if t),
        "headings": [h for h in headings if h],
        "channel_name": CHANNEL,
        "sources": sources,
        "proper_nouns": [parsed.name],
    }


def rejections_today(conn: sqlite3.Connection) -> int:
    return db.scalar(
        conn,
        "SELECT count(*) FROM events WHERE kind = 'apps.submit.rejected' AND substr(ts, 1, 10) = ?",
        (timeutil.today_str(),),
    ) or 0


def submit(conn: sqlite3.Connection, text: str, *, dry_run: bool = False) -> Submission:
    today = timeutil.today_str()
    limit = catalog.limit_reason(conn, today)
    if limit:
        return Submission(False, [f"refused: {limit}"], status="refused")
    max_rejections = int(catalog.settings().get("max_rejections_per_day", 4))
    if not dry_run and rejections_today(conn) >= max_rejections:
        return Submission(False, [f"refused: {max_rejections} rejected submissions today; stop and report FAIL"], status="refused")

    ctx = context(conn)
    errors = prd_mod.validate_factory(text, ctx)
    parsed = prd_mod.parse(text)
    if errors:
        if not dry_run:
            log.event(conn, "apps.submit.rejected", {"app": parsed.app_id, "slug": parsed.slug, "errors": errors[:20]}, level="warning", agent=NAME)
        lines = [f"rejected: {len(errors)} problem{'s' if len(errors) != 1 else ''} with the PRD (the brand check has not run yet)"]
        lines += [f"  - {e}" for e in errors]
        if ctx.fetched_urls is None and log.current_run_id() is not None:
            lines.append("  (no transcript found for this run, so cited sources were not checked against fetches)")
        return Submission(False, lines, app_id=parsed.app_id, name=parsed.name, status="rejected")

    parts = brand_parts(parsed)
    if dry_run:
        result = brand_check.check(**parts)
        if not result.passed:
            return Submission(False, ["brand check: fail (dry run; no attempt used)"] + [f"  - {r}" for r in result.reasons()], status="checked")
        return Submission(True, [f"dry run: {parsed.app_id} {parsed.name} passes every check; submit it without --dry-run"], app_id=parsed.app_id, name=parsed.name, status="checked")

    verdict = gate.gate(conn, catalog.gate_key(today), parts.pop("text"), agent=NAME, **parts)
    if not verdict.passed:
        head = (
            "brand check: fail. Fix every reason below in one regeneration and submit once more"
            if verdict.status == "retry"
            else "brand check: fail again, so today's app PRD is dropped. Finish with FAIL"
        )
        return Submission(False, [head] + [f"  - {r}" for r in verdict.result.reasons()], app_id=parsed.app_id, name=parsed.name, status=verdict.status)

    target = paths.writable(catalog.pending_dir() / parsed.filename)
    if target.exists():
        return Submission(False, [f"refused: {target} already exists"], status="refused")
    target.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    relative = parsed.build_path
    entry = parsed.registry_entry()
    conn.execute(
        "INSERT INTO app_prds (app_id, slug, name, tier, category, path, day, run_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (parsed.app_id, parsed.slug, parsed.name, parsed.tier, parsed.category, relative, today, log.current_run_id(), timeutil.stamp()),
    )
    backlog.mark_written(
        name=parsed.name,
        slug=parsed.slug,
        app_id=parsed.app_id,
        prd_path=relative,
        tier=parsed.tier,
        category=parsed.category,
        does=entry.get("description", parsed.one_line),
    )
    message = discord_message(parsed)
    posted = discord.post(conn, "app-factory", message, username="Jura growth · app factory")
    log.event(conn, "apps.prd.written", {"app": parsed.app_id, "name": parsed.name, "path": relative, "discord": posted.delivered or posted.reason}, agent=NAME)
    lines = [
        f"filed: {parsed.app_id} {parsed.name} at {relative}",
        "backlog updated",
        "posted to #app-factory" if posted.delivered else f"#app-factory: {posted.reason}",
    ]
    return Submission(True, lines, app_id=parsed.app_id, name=parsed.name, path=relative, status="filed")


def pitch(parsed: prd_mod.AppPrd) -> tuple[str, str]:
    """(one-paragraph pitch, lead types) from the PRD's §1."""
    who = parsed.who.strip()
    if who and who[0].isupper() and who[1:2].islower():
        who = who[0].lower() + who[1:]
    why_sentences = brand_check.sentences(parsed.why)
    leads = ""
    rest = why_sentences
    if why_sentences and re.match(r"^suits\b", why_sentences[0], re.I):
        leads = re.sub(r"^suits\s+", "", why_sentences[0], flags=re.I).rstrip(".")
        rest = why_sentences[1:]
    one = parsed.one_line.strip()
    paragraph = " ".join(p for p in [one if one.endswith(".") else one + ".", f"It is for {who.rstrip('.')}." if who else "", *rest] if p)
    return paragraph, leads or parsed.why


def discord_message(parsed: prd_mod.AppPrd) -> str:
    paragraph, leads = pitch(parsed)
    return "\n".join(
        [
            f"**New app PRD: {parsed.app_id} {parsed.name}**",
            "",
            paragraph,
            "",
            f"Tier: {parsed.tier}. Category: {parsed.category}.",
            f"Lead types it suits: {leads}.",
            "",
            f"To build: open Claude Code in jurasolutions/ and say \"approved, build {parsed.build_path}\".",
        ]
    )


# --- the app-copy brand channel ---------------------------------------------

SAVING_CLAIM = re.compile(
    r"\bsav(?:e|es|ed|ing)\s+(?:you\s+|your\s+team\s+)?(?:time|hours?|money|days?|minutes?)\b|"
    r"\b(?:time|hours|money)\s+saved\b|\bin seconds\b|\bin no time\b|\binstantly\b",
    re.I,
)


def app_copy_check(text: str, ctx: dict) -> list[brand_check.Issue]:
    issues = []
    for source in [text, *ctx.get("headings", []), *ctx.get("buttons", [])]:
        for m in SAVING_CLAIM.finditer(source or ""):
            issues.append(brand_check.Issue("channel", "Tool pages must not claim time or money saved", m.group(0)))
    return issues
