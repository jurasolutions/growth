"""The weekly posting plan (community scout PRD §5.2, §5.3).

`plan-add` checks a draft plan in code before anything is stored: the weekly
cap, the 14-day rotation, each group's rules for the day and for links, the
word range, distinct text between groups, and the closing-line link rules.
Only then does each item go through the brand gate (one regeneration).

`publish-plan` writes `outputs/growth/community/YYYY-Www.md` as a checklist
and posts it to #community. Ticked `- [x]` items in those files are read back
by `sync_ticks()` on the next run.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from jura_growth import brand_check, caps, db, discord, gate, images, log, paths, timeutil
from jura_growth.agents.community import groups as groups_mod
from jura_growth.agents.community import rules as rules_mod

NAME = groups_mod.NAME
POST_CHANNEL = "community-post"
REPLY_CHANNEL = "community-reply"
WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")
TICK_RE = re.compile(r"^\s*-\s*\[[xX]\]\s+.*?\bitem\s+(\d+)\b")
JURA_MENTION = re.compile(r"\bjura\b|jurasolutions", re.I)
TAGGING = re.compile(
    r"(?<![\w.@])@[A-Za-z][\w.]{1,}|\b(?:dm|pm|inbox|message|whatsapp|text) me\b|"
    r"\b(?:drop|leave|send|comment|share)\s+(?:me\s+)?(?:your|ur)\s+(?:email|e-mail|number|phone|contact|details)\b",
    re.I,
)


# --- settings and dates -------------------------------------------------------


def settings() -> dict:
    return groups_mod.settings()


def groups_per_week() -> int:
    return caps.effective(caps.COMMUNITY_GROUPS_PER_WEEK, settings().get("groups_per_week"))


def no_repeat_days() -> int:
    return max(caps.NO_REPEAT_DAYS, int(settings().get("no_repeat_days") or caps.NO_REPEAT_DAYS))


def words_range(kind: str) -> tuple[int, int]:
    key = "post_words" if kind == "post" else "reply_words"
    default = (60, 150) if kind == "post" else (10, 120)
    spec = settings().get(key) or {}
    return int(spec.get("min", default[0])), int(spec.get("max", default[1]))


def replies_range() -> tuple[int, int]:
    spec = settings().get("replies_per_week") or {}
    return int(spec.get("min", 2)), int(spec.get("max", 3))


def utm_source() -> str:
    return settings().get("utm_source", "facebook_group")


def current_week() -> str:
    return timeutil.iso_week()


def week_monday(week: str) -> date:
    m = WEEK_RE.match(week)
    if not m:
        raise ValueError(f"week must look like 2026-W44, not {week!r}")
    return date.fromisocalendar(int(m.group(1)), int(m.group(2)), 1)


def week_days(week: str) -> list[date]:
    monday = week_monday(week)
    return [monday + timedelta(days=i) for i in range(7)]


def resolve_day(value: str, week: str) -> date:
    value = str(value).strip()
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    key = value.lower()[:3]
    if key in rules_mod.WEEKDAYS:
        return week_days(week)[rules_mod.WEEKDAYS.index(key)]
    raise ValueError(f"day must be YYYY-MM-DD or a weekday name, not {value!r}")


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


# --- the toolbox registry (read directly; no dependency on the apps plug-in) --


def live_tools() -> tuple[set[str], bool]:
    """(live tool slugs, whether the registry could be read)."""
    path = paths.site_repo() / "src" / "apps" / "registry.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set(), False
    if isinstance(data, dict):
        data = data.get("apps", [])
    return {str(e.get("slug")) for e in data if isinstance(e, dict) and e.get("status") == "live"}, True


# --- text comparison ----------------------------------------------------------


def _normal_words(text: str) -> list[str]:
    stripped = text
    for link in brand_check.find_links(text):
        stripped = stripped.replace(link, " ")
    return re.findall(r"[a-z0-9']+", stripped.lower().replace("’", "'"))


def _sentences(text: str) -> set[str]:
    found = set()
    plain = text
    for link in brand_check.find_links(text):
        plain = plain.replace(link, " ")
    for sentence in brand_check.sentences(plain):
        words = re.findall(r"[a-z0-9']+", sentence.lower().replace("’", "'"))
        if len(words) >= 4:
            found.add(" ".join(words))
    return found


def similarity(a: str, b: str) -> float:
    def shingles(text: str) -> set[tuple[str, ...]]:
        words = _normal_words(text)
        return {tuple(words[i:i + 3]) for i in range(max(0, len(words) - 2))}

    sa, sb = shingles(a), shingles(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def text_overlap(a: str, b: str) -> str | None:
    """Why two texts read as the same text, or None."""
    shared = _sentences(a) & _sentences(b)
    if shared:
        return f"shares a sentence (\"{sorted(shared)[0][:80]}\")"
    score = similarity(a, b)
    if score > float(settings().get("max_similarity", 0.25)):
        return f"is too similar ({score:.2f} word-trigram overlap)"
    return None


# --- link rules ---------------------------------------------------------------


def link_problems(text: str, group: dict, *, tools: set[str], registry_ok: bool) -> list[str]:
    """The closing-line rules for a post that carries links."""
    problems = []
    links = brand_check.find_links(text)
    if not links:
        return problems
    lines = [l for l in text.strip().splitlines() if l.strip()]
    closing = lines[-1] if lines else ""
    for link in links:
        if link not in closing:
            problems.append(f"links belong only in the closing line: {link}")
    for index, line in enumerate(lines[:-1]):
        if JURA_MENTION.search(line):
            problems.append("mention Jura only in the closing line")
            break
    if len(links) > 2:
        problems.append(f"at most one tool link and jurasolutions.sg in the closing line (found {len(links)} links)")
    tool_links = 0
    for link in links:
        if not brand_check.is_jura(link):
            problems.append(f"links only to jurasolutions.sg: {link}")
            continue
        candidate = link if re.match(r"^https?://", link, re.I) else f"https://{link}"
        parts = urlsplit(candidate)
        query = parse_qs(parts.query)
        if query.get("utm_source") != [utm_source()]:
            problems.append(f"link needs utm_source={utm_source()}: {link}")
        if query.get("utm_campaign") != [group["slug"]]:
            problems.append(f"link needs utm_campaign={group['slug']} (this group's slug): {link}")
        path = parts.path.rstrip("/")
        if path in ("", "/apps"):
            continue
        m = re.fullmatch(r"/apps/([a-z0-9-]+)", path)
        if not m:
            problems.append(f"link to a toolbox tool (/apps/<slug>) or the home page, not {path}")
            continue
        tool_links += 1
        if registry_ok and m.group(1) not in tools:
            problems.append(f"/apps/{m.group(1)} isn't a live toolbox tool")
        if not registry_ok:
            problems.append("the toolbox registry can't be read, so link the home page or /apps instead of a tool")
    if tool_links > 1:
        problems.append("link one toolbox tool, not several")
    if tools and registry_ok and tool_links == 0 and not problems:
        problems.append("the closing line should link one relevant toolbox tool (" + ", ".join(sorted(tools)) + ")")
    return problems


# --- the plan -----------------------------------------------------------------


@dataclass
class Prepared:
    kind: str
    index: int
    group: dict | None
    day: date | None
    text: str
    question: str | None = None
    image_path: str | None = None
    sources: list[str] = field(default_factory=list)
    rules_ok: str | None = None
    rules_summary: str = ""
    existing_id: int | None = None  # identical item already stored


@dataclass
class PlanResult:
    ok: bool
    week: str
    lines: list[str] = field(default_factory=list)
    stored: list[int] = field(default_factory=list)
    retry: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.errors:
            return f"plan rejected: {len(self.errors)} problems"
        return f"{len(self.stored)} items planned for {self.week}; {len(self.retry)} to regenerate; {len(self.dropped)} dropped"


def stored_items(conn: sqlite3.Connection, week: str, kind: str | None = None) -> list[dict]:
    sql = "SELECT * FROM community_posts WHERE week = ? AND status != 'skipped'"
    params: tuple = (week,)
    if kind:
        sql += " AND kind = ?"
        params += (kind,)
    return db.rows(conn, sql + " ORDER BY id", params)


def prepare(conn: sqlite3.Connection, plan: dict, week: str | None = None) -> tuple[list[Prepared], list[str], str]:
    """Check a plan in code. Returns (items, errors, week)."""
    errors: list[str] = []
    if not isinstance(plan, dict):
        return [], ["the plan must be a JSON object with \"posts\" and \"replies\""], week or current_week()
    week = week or plan.get("week") or current_week()
    try:
        days_of_week = week_days(week)
    except ValueError as error:
        return [], [str(error)], week
    today = timeutil.today()
    tools, registry_ok = live_tools()
    eligible = {g["id"]: g for g in groups_mod.eligible(conn)}
    stored_posts = stored_items(conn, week, "post")
    stored_by_group = {p["group_id"]: p for p in stored_posts}
    recent_since = (today - timedelta(days=int(settings().get("compare_days", 28)))).isoformat()
    recent = db.rows(
        conn,
        "SELECT id, group_id, text FROM community_posts WHERE kind = 'post' AND status != 'skipped' AND created_at >= ?",
        (recent_since,),
    )
    low, high = words_range("post")
    items: list[Prepared] = []

    posts = plan.get("posts") or []
    replies = plan.get("replies") or []
    if not isinstance(posts, list) or not isinstance(replies, list):
        return [], ["\"posts\" and \"replies\" must be lists"], week
    seen_groups: set[int] = set()
    for index, raw in enumerate(posts):
        where = f"post {index + 1}"
        if not isinstance(raw, dict):
            errors.append(f"{where}: must be an object")
            continue
        try:
            group_id = int(raw.get("group_id"))
        except (TypeError, ValueError):
            errors.append(f"{where}: group_id is required")
            continue
        group = eligible.get(group_id)
        if group is None:
            found = groups_mod.get(conn, group_id)
            why = "doesn't exist" if not found else "isn't a joined, good-fit Facebook group" + (" (removed)" if found["removed"] else "")
            errors.append(f"{where}: group {group_id} {why}")
            continue
        where = f"post {index + 1} (group {group_id}, {group['name']})"
        text = str(raw.get("text") or "").strip()
        try:
            day = resolve_day(raw.get("day") or raw.get("planned_day") or "", week)
        except ValueError as error:
            errors.append(f"{where}: {error}")
            continue
        if day not in days_of_week:
            errors.append(f"{where}: {day} is not in {week} ({days_of_week[0]} to {days_of_week[-1]})")
        if day < today:
            errors.append(f"{where}: {day} is in the past")
        rules = groups_mod.rules_for(group)
        item = Prepared(
            "post", index, group, day, text,
            image_path=raw.get("image_path") or None,
            sources=[s for s in raw.get("sources") or [] if isinstance(s, str)],
            rules_ok=(raw.get("rules_ok") or "").strip() or None,
            rules_summary=rules.summary(),
        )

        if group_id in seen_groups:
            errors.append(f"{where}: one post per group per week")
        seen_groups.add(group_id)
        existing = stored_by_group.get(group_id)
        if existing:
            if existing["text"].strip() == text:
                item.existing_id = existing["id"]
                items.append(item)
                continue
            errors.append(f"{where}: already has item {existing['id']} planned for {week}; one post per group per week")

        # rotation: no group within the no-repeat window
        window = no_repeat_days()
        others = db.rows(
            conn,
            "SELECT id, planned_day, posted_at, week FROM community_posts WHERE group_id = ? AND kind = 'post' AND status != 'skipped'",
            (group_id,),
        )
        moments = [(o["id"], o["planned_day"]) for o in others if o["planned_day"]]
        moments += [(o["id"], o["posted_at"][:10]) for o in others if o["posted_at"]]
        if group.get("last_posted_at"):
            moments.append((None, group["last_posted_at"][:10]))
        for other_id, when in moments:
            gap = abs((day - date.fromisoformat(when)).days)
            if gap < window:
                ref = f"item {other_id}" if other_id else "its last post"
                errors.append(f"{where}: {ref} is on {when}, {gap} days away; no group repeats within {window} days")
                break

        # words
        count = word_count(text)
        if not low <= count <= high:
            errors.append(f"{where}: {count} words; posts are {low}–{high} words")

        # rules: links, promotion, day
        links = brand_check.find_links(text)
        promotional = bool(links) or bool(JURA_MENTION.search(text))
        if links:
            if not rules.known or not group["rules_confirmed"]:
                errors.append(
                    f"{where}: the group's rules are "
                    + ("unknown" if not rules.known else "not confirmed by Ting Yu yet")
                    + ", so write a value post with no link"
                )
            elif rules.no_promo:
                errors.append(f"{where}: the group's rules forbid promotion, so no link")
            elif rules.no_links:
                errors.append(f"{where}: the group's rules forbid links")
            else:
                errors += [f"{where}: {p}" for p in link_problems(text, group, tools=tools, registry_ok=registry_ok)]
        elif JURA_MENTION.search(text):
            lines = [l for l in text.strip().splitlines() if l.strip()]
            if any(JURA_MENTION.search(l) for l in lines[:-1]):
                errors.append(f"{where}: mention Jura only in the closing line")
        if rules.no_promo and JURA_MENTION.search(text):
            errors.append(f"{where}: the group's rules forbid promotion, so leave Jura out")
        problem = rules_mod.day_problem(rules, day.weekday(), promotional=promotional)
        if problem:
            errors.append(f"{where}: {day:%a %d %b} breaks the rules: {problem}")
        if rules.known and not rules.parsed and not item.rules_ok:
            errors.append(
                f"{where}: the group's rules (\"{rules.text[:80]}\") can't be read in code; "
                "add \"rules_ok\" saying why this day and this post fit them"
            )
        if TAGGING.search(text):
            errors.append(f"{where}: no tagging, DMs or asking for members' details")
        if item.image_path:
            problem = image_problem(item.image_path)
            if problem:
                errors.append(f"{where}: {problem}")
            else:
                item.image_path = str(paths.guard(item.image_path))
        items.append(item)

    # the weekly cap
    planned_groups = {p["group_id"] for p in stored_posts} | {i.group["id"] for i in items if i.kind == "post"}
    if len(planned_groups) > groups_per_week():
        errors.append(f"plan: {len(planned_groups)} groups this week; the cap is {groups_per_week()}")

    # distinct text between groups (this plan, this week's stored posts, recent posts)
    new_posts = [i for i in items if i.kind == "post" and i.existing_id is None]
    for a_index, a in enumerate(new_posts):
        for b in new_posts[a_index + 1:]:
            why = text_overlap(a.text, b.text)
            if why:
                errors.append(f"post {a.index + 1} and post {b.index + 1}: the text {why}; write each group's post fresh")
        for other in recent:
            if other["group_id"] == a.group["id"] and other["text"].strip() == a.text:
                continue
            why = text_overlap(a.text, other["text"])
            if why:
                errors.append(f"post {a.index + 1}: the text {why} with item {other['id']}; write it fresh")

    # reply ideas
    low_r, high_r = words_range("reply")
    stored_replies = stored_items(conn, week, "reply_idea")
    stored_reply_texts = {r["text"].strip(): r["id"] for r in stored_replies}
    new_replies: list[Prepared] = []
    for index, raw in enumerate(replies):
        where = f"reply idea {index + 1}"
        if not isinstance(raw, dict):
            errors.append(f"{where}: must be an object")
            continue
        text = str(raw.get("text") or "").strip()
        question = str(raw.get("question") or "").strip()
        group = None
        if raw.get("group_id") not in (None, ""):
            try:
                group = eligible.get(int(raw["group_id"]))
            except (TypeError, ValueError):
                group = None
            if group is None:
                errors.append(f"{where}: group {raw.get('group_id')} isn't a joined, good-fit group")
        item = Prepared("reply_idea", index, group, None, text, question=question,
                        sources=[s for s in raw.get("sources") or [] if isinstance(s, str)])
        if text in stored_reply_texts:
            item.existing_id = stored_reply_texts[text]
            items.append(item)
            continue
        if not question:
            errors.append(f"{where}: say which common question it answers (\"question\")")
        count = word_count(text)
        if not low_r <= count <= high_r:
            errors.append(f"{where}: {count} words; reply ideas are {low_r}–{high_r} words")
        if brand_check.find_links(text):
            errors.append(f"{where}: reply ideas carry no links")
        if TAGGING.search(text):
            errors.append(f"{where}: no tagging, DMs or asking for members' details")
        for other in new_replies:
            if _sentences(other.text) & _sentences(text):
                errors.append(f"{where}: shares a sentence with reply idea {other.index + 1}")
        new_replies.append(item)
        items.append(item)
    _, max_replies = replies_range()
    total_replies = len(stored_replies) + len(new_replies)
    if total_replies > max_replies:
        errors.append(f"plan: {total_replies} reply ideas this week; at most {max_replies}")
    return items, errors, week


def add(conn: sqlite3.Connection, plan: dict, week: str | None = None) -> PlanResult:
    items, errors, week = prepare(conn, plan, week)
    result = PlanResult(ok=not errors, week=week, errors=errors)
    if errors:
        log.event(conn, "community.plan.rejected", {"week": week, "errors": errors[:20]}, level="warning", agent=NAME)
        result.lines = [f"rejected: {len(errors)} problem{'s' if len(errors) != 1 else ''} (nothing stored; the brand check has not run)"]
        result.lines += [f"  - {e}" for e in errors]
        return result

    stored_replies = len(stored_items(conn, week, "reply_idea"))
    reply_slot = stored_replies
    for item in items:
        label = _label(item)
        if item.existing_id is not None:
            result.lines.append(f"{label}: already planned as item {item.existing_id}")
            continue
        if item.kind == "post":
            key = f"community:{week}:post:{item.group['id']}"
            channel = POST_CHANNEL
            context = {"group_slug": item.group["slug"]}
        else:
            key = f"community:{week}:reply:{reply_slot}"
            reply_slot += 1
            channel = REPLY_CHANNEL
            context = {}
        verdict = gate.gate(conn, key, item.text, agent=NAME, channel_name=channel, sources=item.sources, context=context)
        if verdict.status == "retry":
            result.retry.append(label)
            result.lines.append(f"{label}: brand check failed; fix every reason and send this item again")
            result.lines += [f"    - {r}" for r in verdict.result.reasons()]
            continue
        if verdict.status == "dropped":
            result.dropped.append(label)
            result.lines.append(f"{label}: failed the brand check twice; dropped")
            result.lines += [f"    - {r}" for r in verdict.result.reasons()]
            continue
        qa = {"brand": "pass", "attempt": verdict.attempts, "rules": item.rules_summary, "rules_ok": item.rules_ok, "sources": item.sources}
        cursor = conn.execute(
            "INSERT INTO community_posts (group_id, week, planned_day, kind, question, text, image_path, qa_json, status, run_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'planned', ?, ?)",
            (
                item.group["id"] if item.group else None, week, item.day.isoformat() if item.day else None,
                item.kind, item.question, item.text, item.image_path, json.dumps(qa), log.current_run_id(), timeutil.stamp(),
            ),
        )
        result.stored.append(cursor.lastrowid)
        result.lines.append(f"{label}: planned as item {cursor.lastrowid}")
    log.event(conn, "community.plan.added", {"week": week, "stored": result.stored, "retry": result.retry, "dropped": result.dropped}, agent=NAME)
    result.ok = not result.retry and not result.dropped
    return result


def _label(item: Prepared) -> str:
    if item.kind == "post":
        return f"post for group {item.group['id']} ({item.group['name']}) on {item.day:%a %d %b}"
    where = f" ({item.group['name']})" if item.group else ""
    return f"reply idea {item.index + 1}{where}"


# --- posted and ticks ---------------------------------------------------------


def mark_posted(conn: sqlite3.Connection, item_id: int, url: str | None = None, *, via: str = "command") -> dict:
    item = db.one(conn, "SELECT * FROM community_posts WHERE id = ?", (int(item_id),))
    if item is None:
        raise ValueError(f"no plan item {item_id}")
    if item["status"] == "skipped":
        raise ValueError(f"item {item_id} was skipped (its group was removed)")
    if url and not re.match(r"^https?://\S+$", url):
        raise ValueError("url must be a full http(s) link")
    now = timeutil.stamp()
    conn.execute(
        "UPDATE community_posts SET status = 'posted', posted_url = coalesce(?, posted_url), posted_at = coalesce(posted_at, ?), posted_via = coalesce(posted_via, ?) WHERE id = ?",
        (url, now, via, item_id),
    )
    if item["kind"] == "post" and item["group_id"]:
        when = item["planned_day"] if via == "checklist" and item["planned_day"] else timeutil.today_str()
        conn.execute(
            "UPDATE community_groups SET last_posted_at = max(coalesce(last_posted_at, ''), ?) WHERE id = ?",
            (when, item["group_id"]),
        )
    log.event(conn, "community.posted", {"item": item_id, "url": url, "via": via}, agent=NAME)
    return db.one(conn, "SELECT * FROM community_posts WHERE id = ?", (int(item_id),))


def plan_dir() -> Path:
    return paths.outputs_dir() / "community"


def sync_ticks(conn: sqlite3.Connection) -> list[int]:
    """Record every ticked `- [x]` item in the checklist files as posted."""
    recorded = []
    folder = plan_dir()
    if not folder.is_dir():
        return recorded
    for path in sorted(folder.glob("*-W*.md")):
        if not WEEK_RE.match(path.stem):
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            m = TICK_RE.match(line)
            if not m:
                continue
            item_id = int(m.group(1))
            row = db.one(conn, "SELECT status FROM community_posts WHERE id = ? AND week = ?", (item_id, path.stem))
            if row and row["status"] == "planned":
                mark_posted(conn, item_id, via="checklist")
                recorded.append(item_id)
    if recorded:
        log.event(conn, "community.ticks", {"recorded": recorded}, agent=NAME)
    return recorded


# --- the checklist ------------------------------------------------------------


def render(conn: sqlite3.Connection, week: str) -> str:
    monday = week_monday(week)
    posts = db.rows(
        conn,
        "SELECT p.*, g.name AS group_name, g.url AS group_url, g.promo_rules, g.rules_confirmed, "
        "g.promo_days_confirmed, g.post_days_confirmed "
        "FROM community_posts p JOIN community_groups g ON g.id = p.group_id "
        "WHERE p.week = ? AND p.kind = 'post' AND p.status != 'skipped' ORDER BY p.planned_day, p.id",
        (week,),
    )
    replies = db.rows(
        conn,
        "SELECT p.*, g.name AS group_name FROM community_posts p LEFT JOIN community_groups g ON g.id = p.group_id "
        "WHERE p.week = ? AND p.kind = 'reply_idea' AND p.status != 'skipped' ORDER BY p.id",
        (week,),
    )
    post_as = settings().get("post_as", "Ting Yu personally")
    out = [
        f"# Community plan, {week}",
        "",
        f"*Jura Solutions · week of Monday {monday:%d %B %Y} · written {timeutil.stamp()}*",
        "",
        f"Post these yourself, as {post_as}. Nothing here is posted automatically.",
        "When a post is up, tick its box (`- [x]`) or run `jura-growth community posted <item-id> [url]`.",
        "The next Monday run reads the ticks. If an admin removes a post or warns you, run",
        "`jura-growth community removed <group-id>` and that group is skipped for good.",
        "",
        "## Posts",
        "",
    ]
    if not posts:
        out += ["No posts planned this week.", ""]
    for p in posts:
        day = date.fromisoformat(p["planned_day"])
        box = "x" if p["status"] == "posted" else " "
        rules = groups_mod.rules_for(p)
        confirmed = "confirmed by you" if p["rules_confirmed"] else "not yet confirmed by you"
        qa = json.loads(p["qa_json"] or "{}")
        out += [
            f"### {day:%a %d %b} · {p['group_name']}",
            "",
            f"- [{box}] Post item {p['id']} on {day:%a %d %b} in [{p['group_name']}]({p['group_url']})"
            + (f" · posted {p['posted_url']}" if p["posted_url"] else ""),
            f"- Rules reminder: {p['promo_rules'] or 'unknown'} ({confirmed}"
            + (f"; {rules_mod.TIMING_HINT}" if rules.mentions_timing else "")
            + f"). Planned as: {rules.summary()}."
            + (f" Why this day fits: {qa['rules_ok']}" if qa.get("rules_ok") else ""),
            f"- Image: {p['image_path'] or 'none'}",
            "",
        ]
        out += [f"> {line}" if line.strip() else ">" for line in p["text"].splitlines()]
        out.append("")
    out += ["## Reply ideas", "", "Use these when someone asks the question. Replies carry no links.", ""]
    if not replies:
        out += ["None this week.", ""]
    for r in replies:
        box = "x" if r["status"] == "posted" else " "
        where = f" ({r['group_name']})" if r["group_name"] else ""
        out += [f"- [{box}] Reply idea item {r['id']}{where}, for: \"{r['question']}\"", ""]
        out += [f"> {line}" if line.strip() else ">" for line in r["text"].splitlines()]
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def image_problem(path: str) -> str | None:
    """Why `path` can't be a post's image, or None. Only a PNG that
    `paths.guard()` accepts (in a run, one from its own folders) is attached."""
    try:
        resolved = paths.guard(path)
    except paths.PathRefused as error:
        return f"image {path}: {error}"
    if not resolved.is_file():
        return f"image {path} doesn't exist"
    if images.png_size(resolved) is None:
        return f"image {path} is not a PNG"
    return None


def publish(conn: sqlite3.Connection, week: str | None = None) -> tuple[Path, discord.PostResult, int, int]:
    week = week or current_week()
    sync_ticks(conn)
    posts = stored_items(conn, week, "post")
    replies = stored_items(conn, week, "reply_idea")
    if not posts:
        raise ValueError(f"nothing planned for {week}; add posts with `jura-growth community plan-add` first")
    text = render(conn, week)
    target = paths.writable(plan_dir() / f"{week}.md")
    target.write_text(text, encoding="utf-8")
    images = []
    for p in posts:
        if not p["image_path"]:
            continue
        problem = image_problem(p["image_path"])
        if problem:  # changed since plan-add: never upload it
            log.event(conn, "community.image.skipped", {"item": p["id"], "problem": problem}, level="warning", agent=NAME)
        else:
            images.append(paths.guard(p["image_path"]))
    images = images[:10]
    message = discord_message(conn, week, target)
    result = discord.post(conn, "community", message, files=images, username="Jura growth · community")
    log.event(conn, "community.plan.published", {"week": week, "file": str(target), "posts": len(posts), "replies": len(replies)}, agent=NAME)
    return target, result, len(posts), len(replies)


def discord_message(conn: sqlite3.Connection, week: str, path: Path) -> str:
    posts = db.rows(
        conn,
        "SELECT p.id, p.planned_day, p.text, p.image_path, g.name, g.url, g.promo_rules FROM community_posts p "
        "JOIN community_groups g ON g.id = p.group_id WHERE p.week = ? AND p.kind = 'post' AND p.status != 'skipped' ORDER BY p.planned_day, p.id",
        (week,),
    )
    replies = stored_items(conn, week, "reply_idea")
    lines = [
        f"**Community plan {week}**: {len(posts)} post{'s' if len(posts) != 1 else ''} and {len(replies)} reply idea{'s' if len(replies) != 1 else ''}.",
        f"Checklist: `{path}`. Post them yourself, then tick the box or run `jura-growth community posted <item-id> [url]`.",
        "",
    ]
    for p in posts:
        day = date.fromisoformat(p["planned_day"])
        lines += [
            f"**{day:%a %d %b} · {p['name']}** (item {p['id']})",
            p["url"],
            f"Rules: {p['promo_rules'] or 'unknown'}",
            p["text"],
            "",
        ]
    if replies:
        lines.append("**Reply ideas** (no links)")
        for r in replies:
            lines += [f"Item {r['id']}, for \"{r['question']}\":", r["text"], ""]
    return "\n".join(lines).rstrip()


# --- brand channels -----------------------------------------------------------


def post_channel_check(text: str, ctx: dict) -> list[brand_check.Issue]:
    issues = []
    low, high = words_range("post")
    count = word_count(text)
    if not low <= count <= high:
        issues.append(brand_check.Issue("channel", f"Group posts are {low}–{high} words (found {count})"))
    if TAGGING.search(text):
        issues.append(brand_check.Issue("channel", "No tagging, DMs or asking for members' details", TAGGING.search(text).group(0)))
    links = brand_check.find_links(text)
    lines = [l for l in text.strip().splitlines() if l.strip()]
    closing = lines[-1] if lines else ""
    for link in links:
        if link not in closing:
            issues.append(brand_check.Issue("channel", "Links belong only in the closing line", link))
        if brand_check.is_jura(link):
            query = parse_qs(urlsplit(link if re.match(r"^https?://", link, re.I) else f"https://{link}").query)
            if query.get("utm_source") != [utm_source()]:
                issues.append(brand_check.Issue("channel", f"Jura links in group posts carry utm_source={utm_source()}", link))
            slug = ctx.get("group_slug")
            if not query.get("utm_campaign") or (slug and query.get("utm_campaign") != [slug]):
                issues.append(brand_check.Issue("channel", "Jura links carry utm_campaign=<group-slug>", link))
    return issues


def reply_channel_check(text: str, ctx: dict) -> list[brand_check.Issue]:
    issues = []
    low, high = words_range("reply")
    count = word_count(text)
    if not low <= count <= high:
        issues.append(brand_check.Issue("channel", f"Reply ideas are {low}–{high} words (found {count})"))
    for link in brand_check.find_links(text):
        issues.append(brand_check.Issue("channel", "Reply ideas carry no links", link))
    if TAGGING.search(text):
        issues.append(brand_check.Issue("channel", "No tagging, DMs or asking for members' details", TAGGING.search(text).group(0)))
    return issues
