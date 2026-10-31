"""`jura-growth social submit <dir>`: from drafts in the scratch folder to an
approval card in #approvals (or #social-drafts, for a platform in draft mode).

In order:

1. Which platforms still need a post today (weekend switch, skips, the one
   post per platform per day cap).
2. The folder: the variants, sources.md, card.json, and what the theme needs:
   sources, their dates and sites, the tool, the layout, the card's items and
   picture, and every figure on the card tied to the post (`drafts.theme_problems`).
3. The 14-day no-repeat rule for story URLs and tools.
4. Source links must work.
5. The brand gate on each variant (`social-<platform>`) and on the card's
   words (`social-card`). The first gated submission of the day that fails
   anywhere delivers nothing and lists every reason, so one regeneration can
   fix them all. The second is final: what passes is delivered and what fails
   is dropped. There is no third.
6. Images, the output folder and `social_posts` rows. If nothing passes, "No
   draft today" with the reason.
7. For each platform in `browser` mode, a publish item and its `social-post`
   approval card in #approvals (browser publishing PRD §5.4). The card carries
   the post, its images and its sources; #social-drafts hears only what became
   of it (Ting Yu, 2026-10-31: `feed.py`, and the publish run's update). A
   platform in browser mode that can't get an item (no page_url set, or its
   posting window has closed) gets a note in #social-drafts saying why, and
   never a request to post by hand.
8. A platform in `draft` mode gets one #social-drafts message with its images,
   to post by hand.

Steps 1 to 4 refuse without using up the regeneration; they are mistakes to
correct, not brand failures.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from jura_growth import db, discord, gate, log, paths, timeutil
from jura_growth.agents.social import checks, drafts, history, linkcheck, render, rhythm
from jura_growth.agents.social.settings import Settings, load

USERNAME = "Jura growth · social"
CHANNEL = "social-drafts"


@dataclass
class VariantResult:
    platform: str
    status: str  # pass, retry, dropped
    issues: list[str] = field(default_factory=list)
    words: int = 0
    hashtags: int = 0
    attempt: int = 0

    def as_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class Outcome:
    status: str  # nothing, invalid, repeat, used-up, retry, delivered, partial, dropped
    lines: list[str] = field(default_factory=list)
    folder: Path | None = None
    variants: dict[str, VariantResult] = field(default_factory=dict)
    images: dict[str, list[Path]] = field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        if self.status in ("delivered", "partial", "nothing"):
            return 0
        if self.status == "invalid":
            return 2
        return 1

    def text(self) -> str:
        return "\n".join(self.lines)


def active_platforms(conn: sqlite3.Connection, day: date, settings: Settings) -> tuple[list[str], list[str]]:
    """(platforms still to draft today, notes on the rest)."""
    skipped = history.skipped_platforms(conn, day)
    drafted = history.drafted_platforms(conn, day)
    active, notes = [], []
    for platform in settings.enabled_platforms():
        if platform.name in skipped:
            notes.append(f"{platform.name}: skipped for {day} ({skipped[platform.name] or 'no reason given'})")
        elif platform.name in drafted:  # caps.SOCIAL_POSTS_PER_PLATFORM_PER_DAY, held by a unique index
            notes.append(f"{platform.name}: already drafted for {day}")
        else:
            active.append(platform.name)
    return active, notes


def submit(
    conn: sqlite3.Connection,
    folder: Path,
    *,
    theme_id: str | None = None,
    offline: bool = False,
    link_client=None,
) -> Outcome:
    settings = load()
    day = timeutil.today()

    reason = rhythm.posting_allowed(day, settings)
    if reason:
        return Outcome("nothing", [f"Nothing to submit: {reason}."])
    active, notes = active_platforms(conn, day, settings)
    if not active:
        return Outcome("nothing", ["Nothing to submit: every platform is done or skipped today.", *notes])

    today_theme = rhythm.theme_for(day, settings)
    try:
        theme = settings.theme(theme_id) if theme_id else today_theme
    except ValueError as error:
        return Outcome("invalid", [f"Refused: {error}"])
    same_kind = history.theme_repeat(conn, day, theme.id, settings.theme_gap_days)
    if same_kind:
        return Outcome("repeat", [
            "Refused (take the next theme `today` lists; this didn't use your regeneration):",
            f"  - {theme.label} was {same_kind}",
        ])

    sub = drafts.load(folder, active, theme=theme)
    problems = sub.problems + (drafts.theme_problems(sub, theme, day) if not sub.problems else [])
    if problems:
        return Outcome("invalid", ["Refused (fix these and submit again; this didn't use your regeneration):", *[f"  - {p}" for p in problems]])
    card = sub.card
    tool = card.tool_info if card and card.tool else None

    repeated = history.repeats(conn, day, sub.urls, tool.slug if tool else None)
    if repeated:
        return Outcome("repeat", ["Refused (pick a different story or tool; this didn't use your regeneration):", *[f"  - {p}" for p in repeated]])

    link_notes = []
    if settings.verify_links and sub.urls:
        statuses = linkcheck.check_all(sub.urls, client=link_client)
        broken = [s for s in statuses if not s.ok]
        if broken:
            return Outcome(
                "invalid",
                ["Refused: these source links don't work (find a working page; this didn't use your regeneration):",
                 *[f"  - {s.url} ({s.note})" for s in broken]],
            )
        link_notes = [f"{s.url}: {s.status}" + (f" ({s.note})" if s.note else "") for s in statuses]

    attempt = history.gated_attempts(conn, day) + 1
    if attempt > gate.MAX_ATTEMPTS:
        return Outcome("used-up", [f"Refused: today's {gate.MAX_ATTEMPTS} brand-checked submissions are used. Nothing more is drafted today."])
    final = attempt == gate.MAX_ATTEMPTS

    context = {
        "theme": {"id": theme.id, "news": theme.news, "needs_tool": theme.needs_tool},
        "tool_url": tool.url(settings.site) if tool else None,
    }
    results: dict[str, VariantResult] = {}
    for platform in active:
        text = sub.variants[platform]
        verdict = gate.gate(
            conn, f"social:{day}:{platform}", text, agent="social", alert=False,
            channel_name=f"social-{platform}", sources=sub.urls, context=context,
        )
        results[platform] = VariantResult(
            platform,
            "dropped" if verdict.status == "retry" and final else verdict.status,
            verdict.result.reasons(),
            checks.word_count(text),
            len(checks.hashtags(text)),
            verdict.attempts,
        )
    verdict = gate.gate(
        conn, f"social:{day}:card", card.body(), agent="social", alert=False, channel_name="social-card",
        headings=card.headings(), sources=sub.urls, proper_nouns=card.proper_nouns, context=context,
    )
    card_result = VariantResult("card", "dropped" if verdict.status == "retry" and final else verdict.status, verdict.result.reasons(), attempt=verdict.attempts)
    every = {**results, "card": card_result}
    failed = {name: r for name, r in every.items() if r.status != "pass"}
    issues = {name: r.issues for name, r in failed.items()}

    if failed and not final:
        history.record_submission(conn, day, attempt=attempt, status="retry", theme=theme.id, issues=issues)
        discord.alert(conn, _alert_text(day, failed, "regenerating once"), agent="social")
        lines = [f"Brand check: attempt {attempt} of {gate.MAX_ATTEMPTS}. Nothing was delivered."]
        lines += _verdict_lines(every)
        lines += ["", "Fix every reason above in one regeneration, then run `jura-growth social submit` again.",
                  "The next submission is final: anything that fails then is dropped."]
        return Outcome("retry", lines, variants=results)

    passing = [p for p in active if results[p].status == "pass"]
    if not passing:
        reason = "every variant failed the brand check twice: " + "; ".join(
            f"{name}: {r.issues[0] if r.issues else r.status}" for name, r in failed.items() if name != "card"
        )
        history.record_submission(conn, day, attempt=attempt, status="dropped", theme=theme.id, reason=reason, issues=issues)
        discord.alert(conn, _alert_text(day, failed, "dropped"), agent="social")
        post_no_draft(conn, day, reason, record=False)
        return Outcome("dropped", ["Nothing passed. “No draft today” has been posted with the reasons.", *_verdict_lines(every)], variants=results)

    out = paths.writable(paths.outputs_dir() / "social" / day.isoformat() / ".keep").parent
    images: dict[str, list[Path]] = {}
    notes_for_ting: list[str] = list(settings.warnings)
    fonts: list[str] = []
    if card_result.status == "pass":
        sizes = [(p, settings.platforms[p].width, settings.platforms[p].height) for p in passing]
        carousel = {}
        ig = settings.platforms["instagram"]
        if "instagram" in passing and (ig.carousel_on(day) or theme.carousel) and card.carousel is not False:
            carousel["instagram"] = ig.carousel_max
        try:
            if not offline:
                fonts = render.fonts_loaded(render.build_html(card, 1200, 627, settings=settings), settings=settings)
                missing = [f for f in render.EXPECTED_FONTS if f not in fonts]
                if missing:
                    notes_for_ting.append(f"web fonts didn't load ({', '.join(missing)}); the images use fallback fonts")
            images = render.render_spec(card, sizes, out, carousel=carousel, settings=settings, offline=offline)
        except render.RenderError as error:
            notes_for_ting.append(f"images not rendered: {error}")
            discord.alert(conn, f"Social images for {day} were not rendered: {error}", agent="social")
    else:
        notes_for_ting.append("no images: the card's words failed the brand check twice")

    dropped = [p for p in active if results[p].status != "pass"]
    status = "partial" if dropped or card_result.status != "pass" else "delivered"
    _write_outputs(out, sub, card, theme, passing, results, card_result, images, attempt, fonts, link_notes, notes_for_ting)
    _log_rows(conn, day, theme.id, passing, sub, results, images, tool.slug if tool else None, attempt, theme.id != today_theme.id, fonts)
    requests = _raise_publish_items(conn, day, passing, settings, notes_for_ting)
    history.record_submission(conn, day, attempt=attempt, status=status, theme=theme.id, issues=issues)
    log.event(
        conn, "social.delivered",
        {"date": day.isoformat(), "theme": theme.id, "platforms": passing, "dropped": dropped, "folder": str(out)},
        agent="social",
    )
    _post(conn, day, theme, settings, passing, sub, images, out, dropped, results, notes_for_ting, requests)
    if requests:
        from jura_growth import cards

        cards.sweep_safely(conn)  # A12: the cards go out once their requests have committed
    if dropped:
        discord.alert(conn, _alert_text(day, {p: results[p] for p in dropped}, "dropped"), agent="social")

    lines = [f"Delivered to #{'approvals' if len(requests) == len(passing) else CHANNEL}: "
             f"{', '.join(passing)} ({theme.label}) in {out}"]
    lines += [f"Approval requested: {platform} as {approval.id} in #approvals" for platform, approval in requests.items()]
    if dropped:
        lines.append(f"Dropped after the brand check: {', '.join(dropped)}")
    lines += _verdict_lines(every)
    for platform, files in images.items():
        lines.append(f"  {platform} images: " + ", ".join(f"{f.name}" for f in files))
    lines += [f"Note: {n}" for n in notes_for_ting]
    lines += notes
    return Outcome(status, lines, out, results, images)


def post_no_draft(conn: sqlite3.Connection, day: date, reason: str, *, record: bool = True) -> None:
    if record:
        history.record_submission(conn, day, attempt=0, status="no-draft", reason=reason)
    log.event(conn, "social.no_draft", {"date": day.isoformat(), "reason": reason}, agent="social")
    discord.post(conn, CHANNEL, f"**No draft today** ({day.strftime('%A %-d %B')}): {reason}", username=USERNAME)


# --- helpers -----------------------------------------------------------------


def _verdict_lines(every: dict[str, VariantResult]) -> list[str]:
    lines = []
    for name, result in every.items():
        detail = f" ({result.words} words, {result.hashtags} hashtags)" if name != "card" else ""
        lines.append(f"  {name}: {result.status}{detail}")
        lines += [f"    - {reason}" for reason in result.issues]
    return lines


def _alert_text(day: date, failed: dict[str, VariantResult], verdict: str) -> str:
    out = [f"Brand check failed for the {day} social drafts ({verdict}):"]
    for name, result in failed.items():
        out += [f"- {name}: {reason}" for reason in result.issues[:4]]
    return "\n".join(out)[:1800]


def _write_outputs(out, sub, card, theme, passing, results, card_result, images, attempt, fonts, link_notes, notes) -> None:
    for platform in passing:
        (out / f"{platform}.md").write_text(sub.variants[platform].rstrip() + "\n", encoding="utf-8")
    if sub.sources_text:
        (out / "sources.md").write_text(sub.sources_text.rstrip() + "\n", encoding="utf-8")
    (out / "card.json").write_text(json.dumps(card.as_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    qa_path = out / "qa.json"
    entries = json.loads(qa_path.read_text(encoding="utf-8")) if qa_path.exists() else []
    entries.append(
        {
            "ts": timeutil.stamp(),
            "attempt": attempt,
            "theme": theme.id,
            "variants": {name: r.as_dict() for name, r in results.items()},
            "card": card_result.as_dict(),
            "images": {p: [str(f) for f in files] for p, files in images.items()},
            "image_sizes": {p: [list(render.png_size(f)) for f in files] for p, files in images.items()},
            "fonts_loaded": fonts,
            "source_links": link_notes,
            "notes": notes,
        }
    )
    qa_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _log_rows(conn, day, theme_id, passing, sub, results, images, tool_slug, attempt, fallback, fonts) -> None:
    now = timeutil.stamp()
    with db.transaction(conn):
        for platform in passing:
            result = results[platform]
            qa = {"passed": True, "attempt": attempt, "issues": [], "words": result.words,
                  "hashtags": result.hashtags, "theme_fallback": fallback, "fonts_loaded": fonts}
            conn.execute(
                "INSERT INTO social_posts (date, theme, platform, text, image_paths, source_urls, qa_json, status, "
                "tool_slug, run_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?)",
                (
                    day.isoformat(), theme_id, platform, sub.variants[platform],
                    json.dumps([str(f) for f in images.get(platform, [])]),
                    json.dumps(sub.urls), json.dumps(qa), tool_slug, log.current_run_id(), now,
                ),
            )


def _raise_publish_items(conn, day, passing, settings, notes) -> dict:
    """{platform: its pending request} for each passing platform in browser mode."""
    browser = [p for p in passing if settings.platforms[p].browser]
    if not browser:
        return {}
    from jura_growth.agents.publish import items as publish_items

    raised = {}
    with db.transaction(conn):
        for platform in browser:
            post = db.one(conn, "SELECT id FROM social_posts WHERE date = ? AND platform = ?", (day.isoformat(), platform))
            if post is None:
                continue  # every passing platform has its row (_log_rows), so this never happens
            made = publish_items.create_social(conn, post["id"], run_id=log.current_run_id())
            if made.approval is not None and made.approval.status == "pending":
                raised[platform] = made.approval
            else:
                notes.append(f"{platform} is in browser mode but got no approval card: {made.why or 'no request raised'}")
    return raised


def _post(conn, day, theme, settings, passing, sub, images, out, dropped, results, notes, requests=None) -> None:
    when = day.strftime("%A %-d %B %Y")
    requests = requests or {}
    by_hand = []
    for platform in passing:
        rules = settings.platforms[platform]
        if platform in requests or rules.browser:
            continue  # its card in #approvals carries the post; without a card, `notes` below says why
        by_hand.append(platform)
        files = images.get(platform, [])
        size = f"{rules.width}×{rules.height}"
        if len(files) > 1:
            pictures = f"{len(files)} images ({size}): post them as one carousel, in order."
        elif files:
            pictures = f"Image attached ({size})."
        else:
            pictures = "No image."
        header = f"**{rules.label}** · {when} · {theme.label}\n{pictures} Copy the text below and post it by hand."
        body = sub.variants[platform].strip()
        content = f"{header}\n```\n{body}\n```"
        if len(content) > discord.MAX_CONTENT:
            content = f"{header}\n\n{body}"
        discord.post(conn, CHANNEL, content, files=files[: discord.MAX_FILES], username=USERNAME, own_copy=(body,))

    footer = []
    if by_hand:
        if sub.urls:
            footer.append("**Sources**")
            footer += [f"- <{url}>" for url in sub.urls]
        rel = out
        try:
            rel = out.relative_to(paths.JURA_ROOT)
        except ValueError:
            pass
        footer.append(f"Saved in `{rel}`.")
    if dropped:
        footer.append("Dropped after the brand check: " + ", ".join(dropped) + " (reasons in #alerts).")
    footer += [f"Note: {n}" for n in notes]
    if by_hand:
        footer.append(f"Not posting one? `jura-growth social skip {day} <platform>`. Posted it? `jura-growth social published {day} <platform> --url <link>`.")
    if footer:
        discord.post(conn, CHANNEL, "\n".join(footer), username=USERNAME)
