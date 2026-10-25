"""Reviewer's reproductions for code-review-03 (read-only; runs in temp dirs only).

Reuses the repo's own fixtures: `isolated` points data, outputs, env file and
Discord at tmp_path; test_community's `frozen` fakes the site registry and the clock.
"""

import json
import sys
from pathlib import Path

REPO = Path("/Users/tingy/OneDrive/Desktop/projects/jurasolutions/repos/growth")
sys.path.insert(0, str(REPO / "tests"))

from conftest import isolated, conn  # noqa: E402,F401
from test_community import (  # noqa: E402,F401
    frozen, three, good_plan, invoke, outbox, REPLY_LATE, REPLY_QUOTE, MONDAY,
)

from jura_growth import brand_check, config, runner  # noqa: E402
from jura_growth.agents.community import plan as plan_mod  # noqa: E402
from jura_growth.agents.community import rules as rules_mod  # noqa: E402
from jura_growth.agents.community import groups as groups_mod  # noqa: E402
from jura_growth.agents.social import checks, drafts, render  # noqa: E402


# F1: negated day rules are read as permissions
def test_negated_day_rules_are_inverted():
    weekend_ban = rules_mod.parse("No promotion on weekends.")
    print("no promotion on weekends ->", weekend_ban.as_dict(), weekend_ban.summary())
    assert weekend_ban.parsed and weekend_ban.promo_days == frozenset({5, 6})
    assert rules_mod.day_problem(weekend_ban, 5, promotional=True) is None  # Saturday promo allowed
    assert rules_mod.day_problem(weekend_ban, 0, promotional=True) is not None  # Monday promo refused

    sunday_ban = rules_mod.parse("No posts on Sundays.")
    print("no posts on Sundays ->", sunday_ban.as_dict(), sunday_ban.summary())
    assert sunday_ban.parsed and sunday_ban.post_days == frozenset({6})
    assert rules_mod.day_problem(sunday_ban, 6, promotional=False) is None  # Sunday allowed
    assert rules_mod.day_problem(sunday_ban, 2, promotional=False) is not None  # Wednesday refused

    mixed = rules_mod.parse("Promotion allowed Monday to Friday. No links on weekends.")
    print("mixed ->", mixed.as_dict())
    assert mixed.promo_days == frozenset(range(7))


# F2: the community job's Facebook deny list is exact-host only
def test_facebook_deny_list_misses_listed_and_sub_domains():
    spec = config.settings()["jobs"]["community"]
    argv, _ = runner.claude_command("community", spec)
    denied = [a for a in argv if a.startswith("WebFetch(")]
    print("denied WebFetch rules:", denied)
    hosts = {a[len("WebFetch(domain:"):-1] for a in denied}
    missing = [d for d in groups_mod.blocked_domains() if d not in hosts]
    print("community.yaml blocked_fetch_domains not denied in settings.yaml:", missing)
    assert set(missing) == {"fb.watch", "fbcdn.net", "facebook.net", "messenger.com"}
    assert not any("*" in a for a in denied)


# F3: plan-add accepts any existing file as image_path and publish-plan attaches it
def test_image_path_can_be_any_file(conn, three, tmp_path):
    fnb, reno, home = three
    secretish = tmp_path / "pretend-secret.env"
    secretish.write_text("NOT_A_REAL_SECRET=1\n")
    plan = good_plan(fnb, reno, home)
    plan["posts"][2]["image_path"] = str(secretish)
    result = plan_mod.add(conn, plan)
    assert result.ok, result.lines
    plan_mod.publish(conn, "2026-W44")
    sent = outbox("community")[-1]["files"]
    print("files attached to #community:", sent)
    assert str(secretish) in sent


# F4: human-only fields can be set from inside a headless community run
def test_headless_run_can_mark_groups_joined(conn, monkeypatch):
    from test_community import group
    status, gid, _ = groups_mod.add(conn, group("Some SG group", "somesg"))
    conn.commit()
    monkeypatch.setenv("JURA_GROWTH_JOB", "community")
    monkeypatch.setenv("JURA_GROWTH_AGENT", "community")
    out = invoke("community", "set", str(gid), "joined=yes", "rules_confirmed=yes")
    print(out.output)
    assert out.exit_code == 0 and "joined yes" in out.output


# F5: a reply idea can get a third brand-gated attempt (positional gate keys)
def test_reply_idea_regeneration_leak(conn):
    bad = REPLY_LATE + " Act now!"
    first = plan_mod.add(conn, {"week": "2026-W44", "posts": [], "replies": [
        {"question": "How do I chase a late payment?", "text": bad},
        {"question": "What goes on a quotation?", "text": REPLY_QUOTE},
    ]})
    print("first:", first.summary)
    assert len(first.retry) == 1 and len(first.stored) == 1
    second = plan_mod.add(conn, {"week": "2026-W44", "replies": [{"question": "How do I chase a late payment?", "text": bad}]})
    print("second (should be dropped under the one-regeneration rule):", second.summary)
    assert second.retry and not second.dropped
    third = plan_mod.add(conn, {"week": "2026-W44", "replies": [{"question": "How do I chase a late payment?", "text": bad}]})
    print("third:", third.summary)
    assert third.dropped


# F6: grant/scheme detector misses common scheme words
def test_grant_detector_gaps():
    for phrase in ("the Jobs Growth Incentive", "the Senior Employment Credit", "CDC vouchers",
                   "the Market Readiness Assistance", "a new government rebate"):
        print(phrase, "->", bool(checks.GRANT_RE.search(phrase)))
        assert not checks.GRANT_RE.search(phrase)


# F7: the own-words check sees only double-quoted passages
def test_long_quote_detector_gaps():
    words = " ".join(["word"] * 20)
    assert checks.long_quotes(f"“{words}”", 12)
    assert not checks.long_quotes(f"‘{words}’", 12)
    assert not checks.long_quotes(f"'{words}'", 12)


# F8: sources.md refuses bracketed URLs the core link finder handles
def test_bracketed_source_url():
    url = "https://www.iras.gov.sg/taxes/goods-services-tax-(gst)/basic-concepts"
    print("brand_check.find_links:", brand_check.find_links(url))
    assert brand_check.find_links(url) == [url]
    sources, bracketed = drafts._parse(f"- {url} | IRAS | 2026-10-20 | GST")
    print("drafts._parse:", [s.url for s in sources], bracketed)
    assert bracketed


# F9: a five-item list card loses its fifth item from the Instagram carousel
def test_carousel_drops_fifth_item():
    spec, problems = render.CardSpec.parse({
        "layout": "list", "headline": "Five things",
        "items": [{"title": f"Item {i}", "detail": "d"} for i in range(1, 6)],
    })
    assert not problems
    slides = spec.slides(5)
    print("slides:", [s.headline for s in slides])
    assert len(slides) == 5 and "Item 5" not in [s.headline for s in slides]
