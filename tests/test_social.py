"""The social content agent: rhythm, no-repeat, platform channels, the submit
flow end to end (Discord off, so the outbox is checked), skip and digest.

Rendering with real Chrome is in test_social_render.py; here `render.screenshot`
is replaced by a stub that writes a PNG header of the right size, so the
carousel and naming logic still runs.
"""

import json
import struct
import zlib
from datetime import date
from pathlib import Path

import pytest
from click.testing import CliRunner

from jura_growth import brand_check, config, db, digest, paths, runner, timeutil
from jura_growth.agents import social
from jura_growth.agents.social import checks, history, linkcheck, plan, render, rhythm, submit, toolbox
from jura_growth.agents.social.settings import load
from jura_growth.cli import cli

TUESDAY = "2026-10-27T07:05:00+08:00"
MONDAY = "2026-10-26T07:05:00+08:00"
WEDNESDAY = "2026-10-28T07:05:00+08:00"
SATURDAY = "2026-10-24T07:05:00+08:00"

IMDA = "https://www.imda.gov.sg/resources/press-releases/2026/sme-ai-programme"
SHEETS = "https://www.example.com/news/sheets-ai"

# --- fixture drafts ----------------------------------------------------------

TIP = {
    "linkedin.md": """Most small teams chase late invoices the same way. Someone notices, opens the accounting software, finds the invoice and writes a polite email. It works, but it depends on someone remembering.

This week, try handing the first reminder to your accounting software. Xero and QuickBooks both let you set an automatic reminder a few days after the due date. You write the message once, choose when it goes, and the software sends it for every unpaid invoice.

A few things help it land well:

- Keep the tone friendly. The first reminder is a nudge.
- Include the invoice number, the amount due and a payment link, so the customer can pay in one step.
- Decide who follows up by phone if the second reminder goes unanswered.

Your team still owns the relationship. The software only does the remembering.

If chasing payments takes up more of your week than it should, we're happy to look at the process with you: https://jurasolutions.sg

#SmallBusiness #Automation #Invoicing
""",
    "facebook.md": """Chasing late invoices by hand? Your accounting software can send the first reminder for you.

Xero and QuickBooks both let you set an automatic reminder a few days after the due date. Write the message once, include the invoice number and a payment link, and it goes out for every unpaid invoice. Your team still decides who follows up by phone.

The setting is already in the software you pay for, so there is nothing new to buy and nothing to install.

Picture a small trading firm where the office manager spends Friday afternoon writing the same polite email. With the reminder on, those emails go out on their own, and Friday goes back to the customers who need a real conversation.

This week, write one reminder in your own voice and switch it on for a single group of customers. Read what went out at the end of the week, then widen it.

More small automations like this: https://jurasolutions.sg

#SmallBusiness #Automation
""",
    "instagram.md": """Let your accounting software send the first invoice reminder.

Xero and QuickBooks both let you set an automatic reminder a few days after the due date. You write the message once, add the invoice number and a payment link, and it goes out for every unpaid invoice. Your team still decides when to pick up the phone.

The setting is already in the software you pay for, so there is nothing new to buy.

Picture a small trading firm where the office manager spends Friday afternoon writing the same polite email. With the reminder on, Friday goes back to the customers who need a real conversation.

This week, write one reminder in your own voice and switch it on for a single group of customers.

Link in bio for more small automations.

#SmallBusiness #Automation #Invoicing #Singapore
""",
    "sources.md": "",
    "card.json": json.dumps(
        {
            "layout": "headline",
            "headline": "Let your accounting software send the first invoice reminder",
            "subtitle": "Write the message once. It goes out for every unpaid invoice.",
            "visual": {
                "type": "flow",
                "caption": "How the first reminder runs",
                "steps": [
                    {"icon": "file-text", "label": "The invoice falls due"},
                    {"icon": "clock", "label": "A few days pass"},
                    {"icon": "mail", "label": "The reminder goes out"},
                ],
            },
            "items": [
                {"title": "Write the message once", "detail": "Add the invoice number and a payment link, so the customer can pay in one step.", "icon": "pen-line"},
                {"title": "Keep the phone call for your team", "detail": "Decide who follows up when a reminder goes unanswered.", "icon": "phone"},
            ],
        }
    ),
}

NEWS = {
    "linkedin.md": f"""Two AI updates from this week that are worth a small business owner's attention.

IMDA has opened a new programme to help smaller firms try AI tools on everyday work, starting with document handling and customer replies. The official page sets out who can apply and what help is on offer: {IMDA}

Spreadsheet tools keep picking up AI help as well. Example News reports that Sheets can now suggest a formula from a plain sentence, such as "add up last month's unpaid invoices". {SHEETS}

What this means in practice: the first step into automation keeps getting smaller. You can try a narrow task on your own data before anything touches your accounts or your customers. Start with the job your team repeats most often and least enjoys.

If you'd like a second pair of eyes on where to begin, that's the work we do at https://jurasolutions.sg

#AI #SmallBusiness #Singapore
""",
    "facebook.md": f"""Two AI updates worth knowing about this week.

IMDA has opened a programme to help smaller firms try AI on everyday work, starting with document handling and customer replies. The official page sets out who can apply and what help is on offer: {IMDA}

Sheets can now suggest a formula from a plain sentence, according to Example News. You describe the sum you want and it drafts the formula for you to check: {SHEETS}

Both arrive as more firms ask where to begin, and both make that first step smaller. Picture a small clinic that keeps its monthly claims in a spreadsheet. The person who closes the month can describe the total in plain words and check the answer, with nothing touching the accounts. You stay in charge, because the person who knows the work reads every answer before it goes anywhere else.

This week, pick the task your team repeats most often and try it there first, on your own data. More ideas at https://jurasolutions.sg

#AI #SmallBusiness
""",
    "instagram.md": """Two AI updates worth knowing about this week.

IMDA has opened a programme to help smaller firms try AI on everyday work, starting with documents and customer replies.

Example News reports that Sheets can now suggest a formula from a plain sentence.

The first step into automation keeps getting smaller. You can try a narrow task on your own data before anything touches your customers.

Picture a small clinic that keeps its monthly claims in a spreadsheet. The person who closes the month can describe the total in plain words and check the answer. You stay in charge, because the person who knows the work reads every answer first.

This week, pick the task your team repeats most often and try it there first.

Link in bio for both stories.

#AI #SmallBusiness #Singapore #Automation
""",
    "sources.md": f"- {IMDA} | IMDA | 2026-10-23 | IMDA opens a new SME AI programme\n- {SHEETS} | Example News | 2026-10-22 | Sheets adds formula suggestions\n",
    "card.json": json.dumps(
        {
            "layout": "list",
            "headline": "Two AI updates worth a look this week",
            "subtitle": "What changed, and what it means for a small team.",
            "items": [
                {"title": "IMDA opens a programme for smaller firms trying AI", "detail": "It starts with documents and customer replies.", "source": "IMDA", "icon": "landmark"},
                {"title": "Sheets suggests formulas from a plain sentence", "detail": "Describe the sum you want and it drafts the formula.", "source": "Example News", "icon": "file-check"},
            ],
        }
    ),
}


def write(folder: Path, files: dict, **changes) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in {**files, **changes}.items():
        if text is None:
            (folder / name).unlink(missing_ok=True)
        else:
            (folder / name).write_text(text, encoding="utf-8")
    return folder


def fake_png(path: Path, width: int, height: int) -> None:
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    chunk = b"IHDR" + header
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + chunk + struct.pack(">I", zlib.crc32(chunk)))


@pytest.fixture
def env(isolated, monkeypatch, tmp_path):
    """A frozen Tuesday, a toolbox registry, working links, stub screenshots.

    Tuesday is pinned to the automation tip (its theme before 2026-10-30), so the flow tests
    stay about submit and not the calendar; the rhythm tests read the shipped config."""
    monkeypatch.setenv("JURA_GROWTH_NOW", TUESDAY)
    set_config(monkeypatch, rhythm={**config.agent_config("social")["rhythm"], "tue": "automation-tip"})
    site = tmp_path / "site"
    (site / "src" / "apps").mkdir(parents=True)
    (site / "src" / "apps" / "registry.json").write_text(
        json.dumps(
            [
                {"slug": "quote-builder", "name": "Quote builder", "description": "Turn a job into a clean PDF quote in a few minutes.",
                 "category": "Sales", "tier": "browser", "status": "live", "added": "2026-10-20", "prd": "APP-001"},
                {"slug": "receipt-reader", "name": "Receipt reader", "description": "Read a receipt photo into a tidy expense line.",
                 "category": "Finance", "tier": "ai", "status": "live", "added": "2026-10-22", "prd": "APP-002"},
                {"slug": "draft-tool", "name": "Draft tool", "description": "Not live yet.",
                 "category": "Admin", "tier": "browser", "status": "draft", "added": "2026-10-23", "prd": "APP-003"},
            ]
        )
    )
    monkeypatch.setenv("JURA_SITE_REPO", str(site))
    checked = []

    def links_ok(urls, client=None):
        checked.extend(urls)
        return [linkcheck.LinkStatus(u, 200, True) for u in urls]

    monkeypatch.setattr(linkcheck, "check_all", links_ok)
    shots = []

    def stub_screenshot(page, out, width, height, *, settings=None, offline=False):
        out = paths.writable(Path(out))
        fake_png(out, width, height)
        shots.append((out, page))
        return out

    monkeypatch.setattr(render, "screenshot", stub_screenshot)
    monkeypatch.setattr(render, "fonts_loaded", lambda page, settings=None: list(render.EXPECTED_FONTS))
    return {"tmp": tmp_path, "site": site, "links": checked, "shots": shots}


def set_config(monkeypatch, **social_overrides):
    real = config.agent_config

    def patched(agent):
        base = dict(real(agent))
        if agent == "social":
            base.update(social_overrides)
        return base

    monkeypatch.setattr(config, "agent_config", patched)


@pytest.fixture
def linkedin_on(monkeypatch):
    """LinkedIn switched back on over the shipped config (off since 2026-10-29), for the tests that
    cover every platform at once, so a switched-on platform stays covered. What a switched-off
    one gets is in test_social_linkedin_off.py and test_publish_linkedin_off.py."""
    real = config.agent_config

    def patched(agent):
        base = dict(real(agent))
        if agent == "social":
            platforms = {name: dict(spec or {}) for name, spec in (base.get("platforms") or {}).items()}
            platforms.setdefault("linkedin", {})["enabled"] = True
            base["platforms"] = platforms
        return base

    monkeypatch.setattr(config, "agent_config", patched)


def outbox(day="2026-10-27") -> list[dict]:
    path = paths.data_dir() / "discord-outbox" / f"{day}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def rules(result):
    return {issue.rule for issue in result.issues}


def channel_messages(result):
    return [issue.message for issue in result.issues if issue.rule == "channel"]


# --- rhythm and theme ----------------------------------------------------------


@pytest.mark.parametrize(
    "day, theme",
    [
        (date(2026, 10, 26), "ai-this-week"),
        (date(2026, 10, 27), "ai-finding"),
        (date(2026, 10, 28), "from-the-toolbox"),
        (date(2026, 10, 29), "ai-fun-facts"),
        (date(2026, 10, 30), "ai-news"),
        (date(2026, 10, 31), "ai-good-read"),
        (date(2026, 11, 1), "automation-tip"),
    ],
)
def test_rhythm_picks_the_day_theme(day, theme):
    assert rhythm.theme_for(day, load()).id == theme


def test_fallbacks_are_the_next_themes_in_order():
    ids = [t.id for t in rhythm.fallbacks(date(2026, 10, 28), load())]
    assert ids == ["ai-fun-facts", "ai-news", "ai-good-read", "automation-tip", "ai-this-week", "ai-finding"]
    sunday = [t.id for t in rhythm.fallbacks(date(2026, 11, 1), load())]
    assert sunday[0] == "ai-this-week" and "automation-tip" not in sunday


def test_every_day_has_its_own_ai_or_automation_theme():
    settings = load()
    assert len(set(settings.rhythm.values())) == 7
    assert all(t.startswith("ai-") or "automation" in t or t == "from-the-toolbox" for t in settings.rhythm.values())


def test_weekend_switch(monkeypatch):
    assert rhythm.posting_allowed(date(2026, 10, 31), load()) is None
    set_config(monkeypatch, weekends=False)
    assert "weekend" in rhythm.posting_allowed(date(2026, 10, 31), load())
    assert rhythm.posting_allowed(date(2026, 10, 30), load()) is None


def test_carousel_days_and_publish_mode(monkeypatch):
    settings = load()
    ig = settings.platforms["instagram"]
    assert ig.carousel_on(date(2026, 10, 26)) and ig.carousel_on(date(2026, 10, 29))
    assert not ig.carousel_on(date(2026, 10, 27))
    assert not settings.platforms["linkedin"].carousel_on(date(2026, 10, 26))
    assert all(p.publish_mode == "draft" for p in settings.platforms.values())
    # `auto` was dropped for `browser` (browser publishing PRD §3.3); see test_publish_items.py.
    platforms = dict(config.agent_config("social")["platforms"])
    platforms["facebook"] = {**platforms["facebook"], "publish_mode": "auto"}
    set_config(monkeypatch, platforms=platforms)
    with pytest.raises(ValueError, match="draft or browser"):
        load()


def test_today_plan(env, conn):
    result = CliRunner().invoke(cli, ["social", "today", "--json"], catch_exceptions=False)
    data = json.loads(result.output)
    assert data["date"] == "2026-10-27" and data["theme"]["id"] == "automation-tip"
    assert data["platforms"]["instagram"]["links"] == "bio"
    assert data["toolbox"]["newest"]["slug"] == "receipt-reader"  # newest live; the draft tool is hidden
    assert [t["slug"] for t in data["toolbox"]["eligible"]] == ["receipt-reader", "quote-builder"]
    assert data["work_dir"].endswith("work/social/2026-10-27")
    text = CliRunner().invoke(cli, ["social", "today"]).output
    assert "Theme: automation-tip" in text and "jura-growth social submit" in text


def test_toolbox_registry_missing_makes_the_tool_theme_unavailable(env, conn, monkeypatch):
    monkeypatch.setenv("JURA_SITE_REPO", str(env["tmp"] / "nowhere"))
    monkeypatch.setenv("JURA_GROWTH_NOW", WEDNESDAY)
    data = plan.build(conn, timeutil.today())
    assert data["theme"]["id"] == "from-the-toolbox"
    assert "no toolbox registry" in data["theme"]["unavailable"]
    assert "UNAVAILABLE" in plan.render_text(data)


def test_toolbox_usage_ranks_most_used(env, conn):
    conn.execute("CREATE TABLE app_usage (day TEXT, app_slug TEXT, opens INTEGER, completions INTEGER)")
    conn.execute("INSERT INTO app_usage VALUES ('2026-10-25', 'quote-builder', 30, 9), ('2026-10-25', 'receipt-reader', 4, 1)")
    tools = toolbox.plan(conn, date(2026, 10, 27), {})
    assert tools["usage_available"] and tools["most_used"][0]["slug"] == "quote-builder"


# --- the no-repeat rule --------------------------------------------------------


def add_post(conn, day, platform="linkedin", urls=(), tool=None, theme="automation-tip", status="draft"):
    conn.execute(
        "INSERT INTO social_posts (date, theme, platform, text, source_urls, status, tool_slug, created_at) "
        "VALUES (?, ?, ?, 'x', ?, ?, ?, ?)",
        (day, theme, platform, json.dumps(list(urls)), status, tool, timeutil.stamp()),
    )


def test_story_repeat_inside_fourteen_days_is_refused(conn):
    add_post(conn, "2026-10-13", urls=["https://www.example.com/news/story/?utm_source=x"])
    problems = history.repeats(conn, date(2026, 10, 27), ["http://example.com/news/story"], None)
    assert problems and "2026-10-13" in problems[0]


def test_window_edges(conn):
    add_post(conn, "2026-10-10", urls=["https://a.example.com/x"])
    add_post(conn, "2026-10-11", platform="facebook", urls=["https://b.example.com/y"])
    day = date(2026, 10, 25)
    assert history.repeats(conn, day, ["https://a.example.com/x"], None) == []  # 15 days ago: free again
    assert history.repeats(conn, day, ["https://b.example.com/y"], None)  # 14 days ago: still blocked


def test_tool_repeat_is_refused_and_skipped_drafts_still_count(conn):
    add_post(conn, "2026-10-21", tool="quote-builder", status="skipped")
    assert history.repeats(conn, date(2026, 10, 27), [], "quote-builder")
    assert history.repeats(conn, date(2026, 10, 27), [], "receipt-reader") == []


def test_normalise_url():
    assert history.normalise_url("https://WWW.Example.com/a/b/?utm_medium=x&id=3#top") == "example.com/a/b?id=3"
    assert history.normalise_url("example.com/a") == history.normalise_url("http://example.com/a/")


# --- platform channels ---------------------------------------------------------


LI = TIP["linkedin.md"]
FB = TIP["facebook.md"]
IG = TIP["instagram.md"]


def check(text, platform, sources=(), **ctx):
    return brand_check.check(text, channel_name=f"social-{platform}", sources=list(sources), context=ctx)


@pytest.mark.parametrize("platform", ["linkedin", "facebook", "instagram"])
def test_fixture_variants_pass(platform):
    text = {"linkedin": LI, "facebook": FB, "instagram": IG}[platform]
    result = check(text, platform)
    assert result.passed, result.reasons()


@pytest.mark.parametrize("platform", ["linkedin", "facebook", "instagram"])
def test_news_variants_pass_with_their_sources(platform):
    result = check(NEWS[f"{platform}.md"], platform, [IMDA, SHEETS], theme={"news": True})
    assert result.passed, result.reasons()


def test_word_ranges():
    assert any("120–220 words" in m for m in channel_messages(check("Short post. https://jurasolutions.sg", "linkedin")))
    assert any("90–180 words" in m for m in channel_messages(check("Short post. https://jurasolutions.sg", "facebook")))
    long_caption = IG.replace("Link in bio", " ".join(["Your team keeps the credentials."] * 20) + " Link in bio")
    assert any("80–160 words" in m for m in channel_messages(check(long_caption, "instagram")))


def test_word_count_skips_links_and_hashtags():
    assert checks.word_count("Read this https://example.com/a/b today. #One #Two") == 3


def test_hashtag_limits_and_position():
    too_many = LI.replace("#SmallBusiness #Automation #Invoicing", "#SmallBusiness #Automation #Invoicing #Xero")
    assert any("at most 3 hashtags" in m for m in channel_messages(check(too_many, "linkedin")))
    assert any("at most 2 hashtags" in m for m in channel_messages(check(FB.replace("#Automation", "#Automation #Xero"), "facebook")))
    nine = IG.replace("#Singapore", "#Singapore #A #B #C")
    assert any("at most 8 hashtags" in m for m in channel_messages(check(nine, "instagram")))
    assert check(IG.replace("#Singapore", "#Singapore #Admin #Finance"), "instagram").passed  # exactly 8
    middle = LI.replace("This week, try", "This week #Automation, try")
    assert any("last line" in m for m in channel_messages(check(middle, "linkedin")))


def test_linkedin_and_facebook_need_a_link():
    no_link = FB.replace("More small automations like this: https://jurasolutions.sg", "More small automations soon.")
    assert any("carry a link" in m for m in channel_messages(check(no_link, "facebook")))


def test_every_listed_source_is_linked():
    one_missing = NEWS["linkedin.md"].replace(SHEETS, "")
    messages = channel_messages(check(one_missing, "linkedin", [IMDA, SHEETS], theme={"news": True}))
    assert any("Link every source" in m for m in messages)


def test_undeclared_third_party_link_fails():
    text = LI.replace("https://jurasolutions.sg", "https://jurasolutions.sg or https://other.example.org/page")
    assert any("sources.md" in m for m in channel_messages(check(text, "linkedin")))
    assert "links" in rules(check(text, "linkedin", [IMDA]))  # with sources declared, the core rule catches it


def test_news_posts_need_sources():
    assert any("News posts cite" in m for m in channel_messages(check(LI, "linkedin", theme={"news": True})))


def test_tool_posts_link_the_tool():
    url = "https://jurasolutions.sg/apps/quote-builder"
    assert any("Link the tool" in m for m in channel_messages(check(LI, "linkedin", tool_url=url)))
    linked = LI.replace("https://jurasolutions.sg\n", f"{url}?utm_source=linkedin\n")
    assert not channel_messages(check(linked, "linkedin", tool_url=url))


def test_instagram_takes_no_links_and_says_link_in_bio():
    with_url = IG.replace("Link in bio for more small automations.", "Link in bio, or visit jurasolutions.sg.")
    assert any("no links" in m for m in channel_messages(check(with_url, "instagram")))
    without = IG.replace("Link in bio for more small automations.", "More small automations soon.")
    assert any("Link in bio" in m for m in channel_messages(check(without, "instagram")))


def test_markdown_is_refused():
    assert any("bold" in m for m in channel_messages(check(LI.replace("Keep the tone friendly", "**Keep the tone friendly**"), "linkedin")))
    linked = LI.replace("https://jurasolutions.sg", "[our site](https://jurasolutions.sg)")
    assert any("markdown link" in m for m in channel_messages(check(linked, "linkedin")))


def test_long_quotes_fail_and_short_ones_pass():
    quoted = LI.replace(
        "The first reminder is a nudge.",
        '“We are rolling out automatic reminders to every customer on every plan this month,” the company said.',
    )
    assert any("short phrase" in m for m in channel_messages(check(quoted, "linkedin")))
    short = LI.replace("The first reminder is a nudge.", 'Xero calls it "a gentle nudge".')
    assert not channel_messages(check(short, "linkedin"))


@pytest.mark.parametrize("phrase", ["the general election", "a tragic accident", "the death toll"])
def test_blocked_topics(phrase):
    text = LI.replace("The first reminder is a nudge.", f"Unlike {phrase}, this is small.")
    assert any("Off-limits" in m for m in channel_messages(check(text, "linkedin")))


GRANT = (
    "The Productivity Solutions Grant can cover part of the cost of pre-approved software for eligible firms. "
    "The details are on the official page: https://www.gobusiness.gov.sg/productivity-solutions-grant"
)


def test_grant_posts_need_the_eligibility_line_and_official_link():
    text = LI.replace("The first reminder is a nudge.", GRANT)
    messages = channel_messages(check(text, "linkedin", ["https://www.gobusiness.gov.sg/productivity-solutions-grant"]))
    assert any("current eligibility" in m for m in messages)
    fixed = text.replace("#SmallBusiness", "Check the official page for current eligibility.\n\n#SmallBusiness")
    assert not channel_messages(check(fixed, "linkedin", ["https://www.gobusiness.gov.sg/productivity-solutions-grant"]))
    no_official = LI.replace("The first reminder is a nudge.", "Ask about the grant. Check the official page for current eligibility.")
    assert any(".gov.sg" in m for m in channel_messages(check(no_official, "linkedin")))


@pytest.mark.parametrize(
    "sentence",
    [
        "We can help you secure the grant.",
        "Jura will get your PSG funding approved.",
        "We are a pre-approved vendor.",
        "This plan is guaranteed funding.",
    ],
)
def test_never_imply_jura_secures_funding(sentence):
    text = LI.replace("The first reminder is a nudge.", sentence + " Check the official page for current eligibility.")
    messages = channel_messages(check(text, "facebook"))
    assert any("secure or guarantee funding" in m for m in messages), messages


def test_were_is_not_we():
    text = LI.replace("The first reminder is a nudge.", "Some firms were pre-approved for the scheme. Check the official page for current eligibility.")
    assert not any("secure or guarantee" in m for m in channel_messages(check(text, "facebook")))


def test_card_channel():
    assert brand_check.check("Write it once.", headings=["Send the reminder first"], channel_name="social-card").passed
    assert "channel" in rules(brand_check.check("See https://example.com", headings=["A card"], channel_name="social-card"))
    assert "channel" in rules(brand_check.check("Plain #Tag", headings=["A card"], channel_name="social-card"))
    assert "question" in rules(brand_check.check("x", headings=["Still chasing invoices?"], channel_name="social-card"))
    assert "sentence-case" in rules(brand_check.check("x", headings=["Send The Reminder First"], channel_name="social-card"))


def test_channels_are_registered():
    names = set(brand_check.channels())
    assert {"social-linkedin", "social-facebook", "social-instagram", "social-card"} <= names


def test_card_spec_validation():
    spec, problems = render.CardSpec.parse({"layout": "list", "headline": "x" * 100, "items": ["one"]})
    assert any("90" in p for p in problems) and any("2 to 5 items" in p for p in problems)
    spec, problems = render.CardSpec.parse({"layout": "poster", "headline": "Hi"})
    assert any("layout" in p for p in problems)
    spec, problems = render.CardSpec.parse({"layout": "headline", "headline": "Fine", "subtitle": "Also fine."}, default_overline="Explainer")
    assert not problems and spec.overline == "Explainer"


# --- submit, end to end --------------------------------------------------------


def run_submit(conn, folder, **kwargs):
    return submit.submit(conn, folder, offline=True, **kwargs)


def test_submit_delivers_everything(env, conn, linkedin_on):
    folder = write(paths.work_dir("social") / "2026-10-27", TIP)
    outcome = run_submit(conn, folder)
    assert outcome.status == "delivered", outcome.text()
    out = paths.outputs_dir() / "social" / "2026-10-27"
    for name in ("linkedin.md", "facebook.md", "instagram.md", "card.json", "qa.json"):
        assert (out / name).exists(), name
    sizes = {p: [render.png_size(f) for f in files] for p, files in outcome.images.items()}
    # Instagram carries the card and one slide per item, on any day (DP3).
    assert sizes == {"linkedin": [(1200, 627)], "facebook": [(1200, 630)], "instagram": [(1080, 1350)] * 3}

    rows = db.rows(conn, "SELECT * FROM social_posts ORDER BY platform")
    assert [r["platform"] for r in rows] == ["facebook", "instagram", "linkedin"]
    assert all(r["status"] == "draft" and r["theme"] == "automation-tip" for r in rows)
    assert json.loads(rows[2]["image_paths"])[0].endswith("linkedin-1200x627.png")
    assert json.loads(rows[2]["qa_json"])["passed"] is True

    posts = [m for m in outbox() if m["channel"] == "social-drafts"]
    assert len(posts) == 4  # one per platform, then sources and the folder
    assert posts[0]["content"].startswith("**LinkedIn page**") and len(posts[0]["files"]) == 1
    assert TIP["linkedin.md"].strip() in posts[0]["content"]
    assert "skip 2026-10-27" in posts[-1]["content"]
    assert not [m for m in outbox() if m["channel"] == "alerts"]


def test_submit_monday_news_with_carousel(env, conn, monkeypatch, linkedin_on):
    monkeypatch.setenv("JURA_GROWTH_NOW", MONDAY)
    folder = write(paths.work_dir("social") / "2026-10-26", NEWS)
    outcome = run_submit(conn, folder)
    assert outcome.status == "delivered", outcome.text()
    assert len(outcome.images["instagram"]) == 3  # the card, then one slide per item
    assert outcome.images["instagram"][1].name == "instagram-2-of-3-1080x1350.png"
    assert set(env["links"]) == {IMDA, SHEETS}
    ig_post = next(m for m in outbox("2026-10-26") if m["content"].startswith("**Instagram**"))
    assert len(ig_post["files"]) == 3 and "carousel" in ig_post["content"]
    footer = outbox("2026-10-26")[-1]["content"]
    assert f"<{IMDA}>" in footer
    assert json.loads(db.scalar(conn, "SELECT source_urls FROM social_posts WHERE platform = 'linkedin'")) == [IMDA, SHEETS]


def test_brand_failure_allows_one_regeneration(env, conn, linkedin_on):
    folder = paths.work_dir("social") / "2026-10-27"
    write(folder, TIP, **{"facebook.md": FB.replace("for you.", "for you!")})
    first = run_submit(conn, folder)
    assert first.status == "retry" and first.exit_code == 1
    assert "exclamation" in first.text() and "attempt 1 of 2" in first.text()
    assert db.scalar(conn, "SELECT count(*) FROM social_posts") == 0
    assert any(m["channel"] == "alerts" and "regenerating once" in m["content"] for m in outbox())

    write(folder, TIP)
    second = run_submit(conn, folder)
    assert second.status == "delivered", second.text()
    assert db.scalar(conn, "SELECT count(*) FROM social_posts") == 3


def test_second_failure_drops_only_that_variant(env, conn, linkedin_on):
    folder = paths.work_dir("social") / "2026-10-27"
    bad = FB.replace("for you.", "for you!")
    write(folder, TIP, **{"facebook.md": bad})
    assert run_submit(conn, folder).status == "retry"
    outcome = run_submit(conn, folder)
    assert outcome.status == "partial"
    assert outcome.variants["facebook"].status == "dropped"
    assert sorted(r["platform"] for r in db.rows(conn, "SELECT platform FROM social_posts")) == ["instagram", "linkedin"]
    assert not (paths.outputs_dir() / "social" / "2026-10-27" / "facebook.md").exists()
    third = run_submit(conn, folder)
    assert third.status in ("used-up", "nothing")


def test_nothing_passes_posts_no_draft_today(env, conn):
    folder = paths.work_dir("social") / "2026-10-27"
    broken = {name: text.replace("invoice", "invoice!") for name, text in TIP.items() if name.endswith(".md")}
    write(folder, TIP, **broken)
    assert run_submit(conn, folder).status == "retry"
    outcome = run_submit(conn, folder)
    assert outcome.status == "dropped"
    no_draft = [m for m in outbox() if m["channel"] == "social-drafts"]
    assert len(no_draft) == 1 and no_draft[0]["content"].startswith("**No draft today**")
    assert social.precheck("social", conn)  # the 07:00 job won't run again today


def test_repeated_story_is_refused_without_using_the_regeneration(env, conn, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", MONDAY)
    add_post(conn, "2026-10-20", urls=[IMDA + "?utm_source=newsletter"], theme="ai-this-week")
    folder = write(paths.work_dir("social") / "2026-10-26", NEWS)
    outcome = run_submit(conn, folder)
    assert outcome.status == "repeat" and "2026-10-20" in outcome.text()
    assert history.gated_attempts(conn, date(2026, 10, 26)) == 0


def test_broken_source_link_is_refused(env, conn, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", MONDAY)
    monkeypatch.setattr(
        linkcheck, "check_all",
        lambda urls, client=None: [linkcheck.LinkStatus(u, 404 if u == SHEETS else 200, u != SHEETS, "answers 404") for u in urls],
    )
    folder = write(paths.work_dir("social") / "2026-10-26", NEWS)
    outcome = run_submit(conn, folder)
    assert outcome.status == "invalid" and SHEETS in outcome.text()


def test_linkcheck_statuses():
    import httpx

    def handler(request):
        if request.url.path == "/slow":
            raise httpx.ReadTimeout("slow", request=request)
        if request.url.path == "/nohost":
            raise httpx.ConnectError("nodename nor servname provided", request=request)
        return httpx.Response({"/ok": 200, "/gone": 404, "/blocked": 403}[request.url.path])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    urls = [f"https://x.example/{p}" for p in ("ok", "gone", "blocked", "slow", "nohost")]
    found = {s.url.rsplit("/", 1)[1]: s.ok for s in linkcheck.check_all(urls, client=client)}
    assert found == {"ok": True, "gone": False, "blocked": True, "slow": True, "nohost": False}


def test_news_sources_need_dates_and_must_be_recent(env, conn, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", MONDAY)
    folder = paths.work_dir("social") / "2026-10-26"
    write(folder, NEWS, **{"sources.md": f"- {IMDA} | IMDA\n- {SHEETS} | Example News | 2026-10-01 | Old\n"})
    text = run_submit(conn, folder).text()
    assert "published date" in text and "last 7 days" in text


def test_missing_files_are_refused(env, conn):
    folder = write(paths.work_dir("social") / "2026-10-27", TIP, **{"instagram.md": None, "card.json": "{not json"})
    outcome = run_submit(conn, folder)
    assert outcome.status == "invalid" and outcome.exit_code == 2
    assert "instagram.md is missing" in outcome.text() and "not valid JSON" in outcome.text()


def test_tool_theme(env, conn, monkeypatch, linkedin_on):
    monkeypatch.setenv("JURA_GROWTH_NOW", WEDNESDAY)
    url = "https://jurasolutions.sg/apps/quote-builder"
    folder = paths.work_dir("social") / "2026-10-28"
    files = {
        **TIP,
        "linkedin.md": LI.replace("https://jurasolutions.sg\n", f"{url}\n"),
        "facebook.md": FB.replace("https://jurasolutions.sg", url),
        "card.json": json.dumps({"layout": "tool", "tool": "quote-builder"}),
    }
    write(folder, files, **{"facebook.md": FB})  # Facebook forgets the tool link
    first = run_submit(conn, folder)
    assert first.status == "retry" and "Link the tool" in first.text()
    write(folder, files)
    outcome = run_submit(conn, folder)
    assert outcome.status == "delivered", outcome.text()
    assert db.scalar(conn, "SELECT count(*) FROM social_posts WHERE tool_slug = 'quote-builder'") == 3
    page = env["shots"][0][1]
    assert "jurasolutions.sg/apps/quote-builder" in page and "Try it free" in page
    # the next day the tool is not free to feature
    monkeypatch.setenv("JURA_GROWTH_NOW", "2026-10-29T07:00:00+08:00")
    assert [t["slug"] for t in plan.build(conn, timeutil.today())["toolbox"]["eligible"]] == ["receipt-reader"]


def test_tool_theme_without_a_tool_card_is_refused(env, conn, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", WEDNESDAY)
    folder = write(paths.work_dir("social") / "2026-10-28", TIP)
    outcome = run_submit(conn, folder)
    assert outcome.status == "invalid" and "tool card" in outcome.text()
    fallback = run_submit(conn, folder, theme_id="automation-tip")
    assert fallback.status == "delivered", fallback.text()
    assert json.loads(db.scalar(conn, "SELECT qa_json FROM social_posts LIMIT 1"))["theme_fallback"] is True


def test_a_theme_posted_in_the_last_two_days_is_unavailable_and_refused(env, conn, monkeypatch):
    # Monday took Tuesday's theme as a fallback; on Tuesday the same kind of post is off the menu.
    add_post(conn, "2026-10-26", platform="facebook", theme="automation-tip")
    data = plan.build(conn, timeutil.today())
    assert data["theme"]["id"] == "automation-tip"
    assert "posted on 2026-10-26" in data["theme"]["unavailable"]
    assert "UNAVAILABLE" in plan.render_text(data)
    outcome = run_submit(conn, write(paths.work_dir("social") / "2026-10-27", TIP))
    assert outcome.status == "repeat" and "doesn't come back within 2 days" in outcome.text()
    assert history.gated_attempts(conn, timeutil.today()) == 0  # no regeneration used
    # Two days later it is free again.
    monkeypatch.setenv("JURA_GROWTH_NOW", "2026-10-29T07:05:00+08:00")
    assert history.theme_repeat(conn, timeutil.today(), "automation-tip", 2) is None


def test_todays_own_drafts_dont_block_a_second_submission(env, conn):
    add_post(conn, "2026-10-27", platform="facebook", theme="automation-tip")
    assert history.theme_repeat(conn, timeutil.today(), "automation-tip", 2) is None
    assert "unavailable" not in plan.build(conn, timeutil.today())["theme"]


def test_theme_gap_zero_switches_the_variety_rule_off(env, conn, monkeypatch):
    add_post(conn, "2026-10-26", platform="facebook", theme="automation-tip")
    set_config(monkeypatch, theme_gap_days=0)
    assert "unavailable" not in plan.build(conn, timeutil.today())["theme"]
    assert run_submit(conn, write(paths.work_dir("social") / "2026-10-27", TIP)).status == "delivered"


def test_two_runs_pick_different_stories(env, conn, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", MONDAY)
    assert run_submit(conn, write(paths.work_dir("social") / "2026-10-26", NEWS)).status == "delivered"
    monkeypatch.setenv("JURA_GROWTH_NOW", TUESDAY)
    again = write(paths.work_dir("social") / "2026-10-27", NEWS)
    assert run_submit(conn, again, theme_id="ai-this-week").status == "repeat"


def test_render_failure_still_delivers_text(env, conn, monkeypatch):
    def fail(*args, **kwargs):
        raise render.RenderError("Google Chrome not found at /nowhere")

    monkeypatch.setattr(render, "screenshot", fail)
    outcome = run_submit(conn, write(paths.work_dir("social") / "2026-10-27", TIP))
    assert outcome.status == "delivered" and not outcome.images
    assert "images not rendered" in outcome.text()
    assert any(m["channel"] == "alerts" for m in outbox())


# --- skip, published, history, no-draft ------------------------------------------


def invoke(*args):
    return CliRunner().invoke(cli, list(args), catch_exceptions=False)


def test_skip_before_the_draft(env, conn, linkedin_on):
    assert "won't be drafted" in invoke("social", "skip", "2026-10-27", "instagram").output
    outcome = run_submit(conn, write(paths.work_dir("social") / "2026-10-27", TIP, **{"instagram.md": None}))
    assert outcome.status == "delivered", outcome.text()
    assert sorted(r["platform"] for r in db.rows(conn, "SELECT platform FROM social_posts")) == ["facebook", "linkedin"]


def test_skip_after_the_draft_and_published(env, conn, linkedin_on):
    run_submit(conn, write(paths.work_dir("social") / "2026-10-27", TIP))
    assert "marked skipped" in invoke("social", "skip", "today", "facebook").output
    assert db.scalar(conn, "SELECT status FROM social_posts WHERE platform = 'facebook'") == "skipped"
    invoke("social", "published", "2026-10-27", "linkedin", "--url", "https://www.linkedin.com/feed/update/1")
    row = db.one(conn, "SELECT status, published_url FROM social_posts WHERE platform = 'linkedin'")
    assert row == {"status": "published", "published_url": "https://www.linkedin.com/feed/update/1"}
    assert "already published" in invoke("social", "skip", "2026-10-27", "linkedin").output
    out = invoke("social", "history").output
    assert "2026-10-27 facebook  skipped" in out and "live: https://www.linkedin.com" in out


def test_no_draft_command(env, conn):
    result = invoke("social", "no-draft", "no AI news worth a post")
    assert result.exit_code == 0
    assert outbox()[-1]["content"].startswith("**No draft today**")
    assert social.precheck("social", conn)


# --- digest and precheck ----------------------------------------------------------


def test_digest_figures(env, conn, linkedin_on):
    assert social.digest(conn, "2026-10-27")["figures"]["social_drafts_waiting"] == 0
    run_submit(conn, write(paths.work_dir("social") / "2026-10-27", TIP))
    part = social.digest(conn, "2026-10-27")
    assert part["figures"] == {"social_drafts_waiting": 3, "social_skipped": 0, "social_published": 0}
    assert part["brief"] == ["3 social drafts waiting"]
    history.skip(conn, date(2026, 10, 27), "instagram", "test")
    history.mark_published(conn, date(2026, 10, 27), "linkedin", None)
    part = social.digest(conn, "2026-10-27")
    assert part["figures"] == {"social_drafts_waiting": 1, "social_skipped": 1, "social_published": 1}
    assert part["brief"] == ["1 social draft waiting"]
    summary = digest.build(conn, "2026-10-27")
    assert "1 social draft waiting" in summary["brief_line"]


def test_digest_reports_no_draft(env, conn):
    submit.post_no_draft(conn, date(2026, 10, 27), "nothing passed")
    part = social.digest(conn, "2026-10-27")
    assert part["brief"] == ["no social draft today"] and "nothing passed" in part["lines"][0]


def test_precheck(env, conn, monkeypatch):
    assert social.precheck("social", conn) is None
    assert social.precheck("community", conn) is None
    run_submit(conn, write(paths.work_dir("social") / "2026-10-27", TIP))
    assert "already" in social.precheck("social", conn)
    monkeypatch.setenv("JURA_GROWTH_NOW", "2026-10-31T07:00:00+08:00")
    set_config(monkeypatch, weekends=False)
    assert "weekend" in social.precheck("social", conn)


def test_runner_skips_the_job_once_drafts_are_in(env, conn):
    run_submit(conn, write(paths.work_dir("social") / "2026-10-27", TIP))
    outcome = runner.run("social")
    assert outcome.status == "skipped" and "already" in outcome.summary


def test_migration_is_recorded(conn):
    ids = {r["id"] for r in db.rows(conn, "SELECT id FROM schema_migrations")}
    assert "social/0001_social.sql" in ids
