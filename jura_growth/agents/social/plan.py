"""`jura-growth social today`: everything the 07:00 run needs to choose and
write the day's post, in one place."""

from __future__ import annotations

import sqlite3
from datetime import date

from jura_growth import caps, paths
from jura_growth.agents.social import history, rhythm, submit, toolbox, visuals
from jura_growth.agents.social.settings import Settings, load


def build(conn: sqlite3.Connection, day: date, settings: Settings | None = None) -> dict:
    settings = settings or load()
    theme = rhythm.theme_for(day, settings)
    used_tools = history.used_tools(conn, day)
    tools = toolbox.plan(conn, day, used_tools)
    active, notes = submit.active_platforms(conn, day, settings)
    stop = rhythm.posting_allowed(day, settings)
    if not stop and not active:
        stop = "every platform is already drafted or skipped today"
    if not stop and history.gated_attempts(conn, day) >= 2:
        stop = "today's brand-checked submissions are used up"

    def theme_info(t) -> dict:
        info = {
            "id": t.id, "label": t.label, "brief": t.brief, "layout": t.layout, "news": t.news,
            "sources": {"min": t.min_sources, "max": t.max_sources, "max_age_days": t.max_source_age_days},
            "needs_tool": t.needs_tool,
            "words": {p.name: list(settings.words_for(p.name, t.id)) for p in settings.enabled_platforms()},
            "carousel": t.carousel,
            "min_items": t.min_items,
            "needs_visual": t.needs_visual,
        }
        if t.needs_tool and not tools["eligible"]:
            info["unavailable"] = tools["note"] or f"every live tool was featured in the last {caps.NO_REPEAT_DAYS} days"
        repeat = history.theme_repeat(conn, day, t.id, settings.theme_gap_days)
        if repeat:
            info["unavailable"] = repeat
        return info

    work = paths.work_dir("social") / day.isoformat()
    recent = history.recent(conn, day)
    by_day: dict[str, dict] = {}
    for row in recent:
        entry = by_day.setdefault(row["date"], {"date": row["date"], "theme": row["theme"], "platforms": [], "tool": None, "sources": []})
        entry["platforms"].append(f"{row['platform']} ({row['status']})")
        entry["tool"] = entry["tool"] or row["tool_slug"]
        for url in row["source_urls"]:
            if url not in entry["sources"]:
                entry["sources"].append(url)

    return {
        "date": day.isoformat(),
        "weekday": day.strftime("%A"),
        "stop": stop,
        "theme": theme_info(theme),
        "fallbacks": [theme_info(t) for t in rhythm.fallbacks(day, settings)],
        "platforms": {
            name: {
                "label": p.label,
                "words": list(p.words),
                "hashtags_max": p.hashtags_max,
                "links": p.links,
                "image": p.size,
                "carousel_today": p.carousel_on(day) or theme.carousel,
                "carousel_max": p.carousel_max,
                "publish_mode": p.publish_mode,
                "to_draft": name in active,
            }
            for name, p in settings.platforms.items()
            if p.enabled
        },
        "notes": notes + list(settings.warnings),
        "weekends": settings.weekends,
        "eligibility_line": settings.eligibility_line,
        "max_quote_words": settings.max_quote_words,
        "no_repeat_days": caps.NO_REPEAT_DAYS,
        "theme_gap_days": settings.theme_gap_days,
        "history": list(by_day.values()),
        "used_story_urls": sorted({url for _, url in history.used_stories(conn, day).values()}),
        "used_tools": used_tools,
        "toolbox": tools,
        "site": settings.site,
        "icons": visuals.icon_names(),
        "work_dir": str(work),
        "submit": f"jura-growth social submit {work}",
    }


def render_text(plan: dict) -> str:
    out = [f"Social plan for {plan['weekday']} {plan['date']} (SGT)", ""]
    if plan["stop"]:
        out += [f"STOP: {plan['stop']}. Nothing to write today; end the run with SKIP.", ""]

    theme = plan["theme"]
    out.append(f"Theme: {theme['id']} ({theme['label']}). {theme['brief']}")
    out.append(f"  Card layout: {theme['layout']}")
    words = ", ".join(f"{name} {pair[0]}–{pair[1]}" for name, pair in theme["words"].items())
    out.append(f"  Words: {words}")
    if theme["min_items"]:
        out.append(f"  Card items with a detail: at least {theme['min_items']}, one Instagram slide each")
    if theme["needs_visual"]:
        out.append("  Picture: required. A `visual` on a headline card, an `icon` on every item")
    src = theme["sources"]
    if theme["news"]:
        out.append(
            f"  News: {src['min']}–{src['max']} sources, each with its published date; stories from the last "
            f"{src['max_age_days'] or 2} days"
        )
    elif src["min"]:
        out.append(f"  Sources: {src['min']}–{src['max']}; link every one you list")
    elif src["max"]:
        out.append(f"  Sources: optional, at most {src['max']}; link every one you list")
    else:
        out.append("  Sources: none needed")
    if theme.get("unavailable"):
        out.append(f"  UNAVAILABLE today: {theme['unavailable']}. Take the next theme below.")
    out.append("  If nothing good fits, take the next theme, in this order:")
    for t in plan["fallbacks"]:
        flag = f" (unavailable: {t['unavailable']})" if t.get("unavailable") else ""
        fits = ", ".join(f"{name} {pair[0]}–{pair[1]}" for name, pair in t["words"].items())
        out.append(f"    {t['id']}: {t['brief']} Words: {fits}.{flag}")
    out.append("  Pass `--theme <id>` to submit when you use one of these.")

    out += ["", "Platforms (word ranges here are the platform's own; the theme's above win):"]
    for name, p in plan["platforms"].items():
        links = "links in the post" if p["links"] == "post" else "write “Link in bio”, no URL"
        tags = f"up to {p['hashtags_max']} hashtags on the last line"
        carousel = f", carousel of up to {p['carousel_max']} today" if p["carousel_today"] else ""
        todo = "" if p["to_draft"] else "  [not drafting today]"
        out.append(f"  {name:10} {p['words'][0]}–{p['words'][1]} words, {tags}, {links}, image {p['image']}{carousel}{todo}")
    for note in plan["notes"]:
        out.append(f"  note: {note}")

    out += ["", f"Last {plan['no_repeat_days']} days (no story URL or tool may repeat; no theme within "
            f"{plan['theme_gap_days']} days; vary the subject and angle from these):"]
    if plan["history"]:
        for entry in plan["history"]:
            tool = f" tool {entry['tool']}" if entry["tool"] else ""
            out.append(f"  {entry['date']} {entry['theme']}{tool}: {', '.join(entry['platforms'])}")
            out += [f"      {url}" for url in entry["sources"]]
    else:
        out.append("  nothing posted yet")

    tools = plan["toolbox"]
    out += ["", f"Toolbox ({tools['registry']}):"]
    if tools["note"]:
        out.append(f"  {tools['note']}")
    else:
        newest = tools["newest"]
        out.append(f"  newest: {newest['slug']} “{newest['name']}” ({newest['category']}, {newest['tier']}, added {newest['added']})")
        if tools["usage_available"]:
            for t in tools["most_used"]:
                out.append(f"  most used (30 days): {t['slug']} ({t['uses_30_days']})")
        else:
            out.append("  usage counts: not available here; go by newest")
        eligible = ", ".join(t["slug"] for t in tools["eligible"]) or "none"
        out.append(f"  free to feature today: {eligible}")
        for t in tools["eligible"][:3]:
            out.append(f"    {t['slug']}: {t['description']} {plan['site']}/apps/{t['slug']}")

    out += ["", "Icons for `visual` and `items` (nothing else is accepted):", "  " + " ".join(plan["icons"])]

    out += [
        "",
        f"Write your drafts in {plan['work_dir']}/",
        # A file per platform still to draft today: a platform switched off (LinkedIn, since
        # 2026-10-29) isn't in the plan at all.
        "  " + "  ".join([*(f"{name}.md" for name, p in plan["platforms"].items() if p["to_draft"]),
                          "sources.md", "card.json"]),
        f"Then run: {plan['submit']}",
    ]
    return "\n".join(out)
