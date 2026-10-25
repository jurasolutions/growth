"""The community scout plug-in (community scout PRD, blocks 1 and 2)."""

import json
import re
import shlex
from pathlib import Path

import pytest
from click.testing import CliRunner

from jura_growth import brand_check, config, db, log, paths, timeutil
from jura_growth.agents import community as community_plugin
from jura_growth.agents.community import groups as groups_mod
from jura_growth.agents.community import plan as plan_mod
from jura_growth.agents.community import rules as rules_mod
from jura_growth.cli import cli

MONDAY = "2026-10-26"  # 2026-W44
MON_TO_FRI = ["mon", "tue", "wed", "thu", "fri"]


def invoke(*args):
    return CliRunner().invoke(cli, list(args), catch_exceptions=False)


@pytest.fixture(autouse=True)
def frozen(tmp_path, monkeypatch):
    site = tmp_path / "site"
    (site / "src" / "apps").mkdir(parents=True)
    (site / "src" / "apps" / "registry.json").write_text(
        json.dumps([{"slug": "quote-builder", "name": "Quote builder", "description": "Quotes", "category": "Sales",
                     "tier": "browser", "status": "live", "added": "2026-10-20", "prd": "APP-001"}])
    )
    monkeypatch.setenv("JURA_SITE_REPO", str(site))
    monkeypatch.setenv("JURA_PRD_DIR", str(tmp_path / "prd"))
    monkeypatch.setenv("JURA_GROWTH_NOW", f"{MONDAY}T07:30:00+08:00")
    config.reset_caches()


def group(name, url_slug, *, rules="not stated in public sources", fit="good fit", **extra):
    record = {
        "channel": "facebook",
        "name": name,
        "url": f"https://www.facebook.com/groups/{url_slug}",
        "audience": "Singapore SME owners",
        "size_hint": "not stated",
        "active_hint": "not stated",
        "promo_rules": rules,
        "fit": fit,
        "fit_reason": "Owners asking each other about admin and paperwork.",
        "source_urls": [f"https://example.sg/best-groups#{url_slug}"],
    }
    record.update(extra)
    return record


def joined(conn, record, *pairs):
    status, group_id, messages = groups_mod.add(conn, record)
    assert status == "added", messages
    groups_mod.set_fields(conn, group_id, ["joined=yes", *pairs])
    return groups_mod.get(conn, group_id)


POST_FNB = (
    "A quick tip for anyone still chasing supplier invoices at the end of the month. Pick one inbox "
    "address just for invoices and ask every supplier to use it. Then set a filter that labels each "
    "email by supplier name. When you sit down to pay, you open one folder, sort by date and work down "
    "the list. Nothing gets lost in a chat thread, and your accountant can be given read access to that "
    "folder alone. It takes an afternoon to set up and it keeps paying back every month.\n"
    "I run Jura Solutions, where we automate the repetitive parts of running a business. Our free quote "
    "builder is at https://jurasolutions.sg/apps/quote-builder?utm_source=facebook_group&utm_campaign={slug}"
)
POST_RENO = (
    "Many contractors send quotes as photos of a handwritten page over WhatsApp. Customers then lose "
    "them, and you end up resending the same details. A simple fix is a short quote template in a "
    "spreadsheet with your logo, the job address, a line for each item and a clear validity date. "
    "Export it as a PDF and send that file in the chat instead. The customer can forward it to a "
    "partner, and you keep a copy you can search later. When the job is confirmed, reuse the same lines "
    "for the invoice.\nI'm Ting Yu, and I run Jura Solutions, a team that automates admin work for small businesses."
)
POST_HOME = (
    "Keeping receipts tidy before tax season is easier than it sounds. Take a photo of each receipt "
    "the day you get it, and name the photo with the date and the shop. Keep one folder per month on "
    "your phone or computer. At month end, list them in a spreadsheet with the date, the shop, what it "
    "was for and the amount. Your bookkeeper will thank you, and you will spend far less time hunting "
    "through bags and drawers when the return is due. Small habits like this make the yearly filing a "
    "quiet afternoon."
)
REPLY_LATE = (
    "Keep it short and specific. Mention the invoice number, the amount due and the original due date, "
    "then ask when they expect to pay. A friendly second reminder a week later usually works. If it "
    "still stalls, a phone call tends to move things faster than another email."
)
REPLY_QUOTE = (
    "Your business name and contact details, the customer's name, a quote number and date, a clear list "
    "of items with quantities and prices, any discount, whether GST applies, and how long the quote is "
    "valid. Add your payment terms so there are no surprises later."
)


@pytest.fixture
def three(conn):
    """Three joined, good-fit test groups with different rules."""
    fnb = joined(conn, group("SG F&B owners", "sgfnb", rules="Promo posts on Saturdays only."),
                 "rules_confirmed=yes", "promo_days=sat", "post_days=any")
    reno = joined(conn, group("Singapore renovation contractors", "sgreno", rules="Be respectful to every member."),
                  "rules_confirmed=yes", "promo_days=any", "post_days=any")
    home = joined(conn, group("SG home business network", "sghome"), "promo_days=any", "post_days=any")
    return fnb, reno, home


def good_plan(fnb, reno, home):
    return {
        "week": "2026-W44",
        "posts": [
            {"group_id": fnb["id"], "day": "2026-10-31", "text": POST_FNB.format(slug=fnb["slug"])},
            {"group_id": reno["id"], "day": "tuesday", "text": POST_RENO,
             "rules_ok": "The rules only ask members to be respectful; a helpful post on a weekday fits."},
            {"group_id": home["id"], "day": "2026-10-28", "text": POST_HOME},
        ],
        "replies": [
            {"group_id": fnb["id"], "question": "How do I chase a late payment without sounding rude?", "text": REPLY_LATE},
            {"question": "What should go on a quotation?", "text": REPLY_QUOTE},
        ],
    }


def outbox(channel):
    folder = paths.data_dir() / "discord-outbox"
    lines = []
    for file in sorted(folder.glob("*.jsonl")) if folder.exists() else []:
        lines += [json.loads(l) for l in file.read_text().splitlines()]
    return [l for l in lines if l["channel"] == channel]


# --- rules parsing ---------------------------------------------------------
#
# Ting Yu decided (code review 07) that a group's open days are always his to
# set: no group is plannable until `community set <id> promo_days=...
# post_days=...`, whatever its rules text says. Code only flags rules that
# mention timing, as a hint to read them carefully; the hint never opens a day.

PHRASINGS = [line for line in (Path(__file__).parent / "community_rule_phrasings.txt").read_text().splitlines() if line.strip()]


@pytest.mark.parametrize("text", PHRASINGS)
def test_no_rules_text_opens_a_day_until_ting_yu_confirms_the_days(text):
    """Every phrasing from the three code review 07 rounds and their probes."""
    group = {"promo_rules": text, "promo_days_confirmed": None, "post_days_confirmed": None}
    rules = groups_mod.rules_for(group)
    assert not rules.days_confirmed
    assert "promo_days" in rules.summary() and "post_days" in rules.summary()
    for weekday in range(7):
        assert rules_mod.day_problem(rules, weekday, promotional=False)
        assert rules_mod.day_problem(rules, weekday, promotional=True)


@pytest.mark.parametrize(
    "text, known, parsed, no_promo, no_links",
    [
        ("No promotion. No links.", True, True, True, True),
        ("You cannot share links.", True, True, False, True),
        ("Promotion is allowed, but you must not spam.", True, True, True, False),
        ("Self-promotion is welcome", True, True, False, False),
        ("Be kind and respectful", True, False, False, False),
        ("not stated in public sources", False, True, False, False),
        ("", False, True, False, False),
    ],
)
def test_rules_with_no_day_parse_as_before(text, known, parsed, no_promo, no_links):
    rules = rules_mod.parse(text)
    assert (rules.known, rules.parsed) == (known, parsed)
    assert (rules.no_promo, rules.no_links) == (no_promo, no_links)
    assert not rules.mentions_timing and rules.promo_days is None and rules.post_days is None


@pytest.mark.parametrize(
    "text",
    [
        "promo Saturdays only",
        "No posts on Sundays.",
        # code review 07 round 3: R3-B1, days the strict day words miss
        "Self-promo is welcome on #SelfPromoSaturday.",
        "Promotion allowed in the #FridayPromo thread only.",
        "Promo allowed on wknds only.",
        "Self-promotion ok on wkends.",
        "Promo is fine on weeknights only.",
        "Ads welcome on week days.",
        # R3-S1: frequency and holiday rules
        "Promotion allowed once a week.",
        "Self-promo allowed on the 1st of every month.",
        "Promo allowed on public holidays only.",
    ],
)
def test_rules_that_mention_timing_are_flagged(text):
    assert rules_mod.parse(text).mentions_timing


@pytest.mark.parametrize(
    "text",
    [
        "Promotion only on Saturdays, no links.",
        "Promo on Saturdays, no links.",
        "No links, promo on Fridays.",
        "Never post links, promo thread on Sundays.",
    ],
)
def test_a_links_ban_beside_a_day_rule_is_kept(text):
    """Confirming days doesn't confirm links: the closing line's link stays refused."""
    assert rules_mod.parse(text).no_links


@pytest.mark.parametrize("text", ["No links on weekends.", "Members can't post links on weekends."])
def test_a_links_ban_on_some_days_is_left_to_the_confirmed_days(text):
    assert not rules_mod.parse(text).no_links


@pytest.mark.parametrize(
    "value, days",
    [
        ("any", None),
        ("none", frozenset()),
        ("mon-fri", frozenset(range(5))),
        ("Mon to Fri", frozenset(range(5))),
        ("weekdays", frozenset(range(5))),
        ("sat,sun", frozenset({5, 6})),
        ("Saturday and Sunday", frozenset({5, 6})),
        ("fri", frozenset({4})),
    ],
)
def test_read_days(value, days):
    assert rules_mod.read_days(value) == days


@pytest.mark.parametrize("value", ["", "funday", "fri and public holidays", "not sunday", "wknds"])
def test_read_days_refuses_anything_else(value):
    with pytest.raises(ValueError):
        rules_mod.read_days(value)


def test_confirmed_days_are_the_only_days_that_count():
    rules = rules_mod.confirm_days(rules_mod.parse("No promotion on weekends."), "mon-fri", "any")
    assert rules.parsed and rules.days_confirmed
    assert rules_mod.day_names(rules.promo_days) == MON_TO_FRI and rules.post_days is None
    assert rules_mod.day_problem(rules, 5, promotional=True)  # Saturday with a closing line
    assert rules_mod.day_problem(rules, 5, promotional=False) is None  # a value post is fine
    assert rules_mod.day_problem(rules, 0, promotional=True) is None
    assert rules.summary() == "promotion only on mon, tue, wed, thu, fri"

    sunday = rules_mod.confirm_days(rules_mod.parse("No posts on Sundays."), "any", "mon-sat")
    assert rules_mod.day_problem(sunday, 6, promotional=False)
    assert rules_mod.day_problem(sunday, 2, promotional=False) is None
    assert sunday.summary() == "posts only on mon, tue, wed, thu, fri, sat"

    unreadable = rules_mod.confirm_days(rules_mod.parse("Be kind and respectful"), "any", "any")
    assert unreadable.days_confirmed and not unreadable.parsed  # the plan still needs rules_ok


def test_confirmed_promotion_days_lift_a_blanket_ban_and_none_means_no_promotion():
    thread = rules_mod.confirm_days(rules_mod.parse("No promotion. Promo thread on Sundays."), "sun", "any")
    assert not thread.no_promo and rules_mod.day_names(thread.promo_days) == ["sun"]
    never = rules_mod.confirm_days(rules_mod.parse("Promo on Fridays, no DMs."), "none", "any")
    assert never.no_promo and never.summary() == "no promotion"
    quiet = rules_mod.confirm_days(rules_mod.parse("No posts on weekdays. No posts on weekends."), "none", "none")
    assert quiet.summary() == "no posts on any day; no promotion"
    assert rules_mod.day_problem(quiet, 2, promotional=False) == "the group allows no posts on any day"


def test_days_count_only_when_both_are_confirmed():
    half = rules_mod.confirm_days(rules_mod.parse("No promotion on weekends."), "mon-fri", None)
    assert not half.days_confirmed
    assert rules_mod.day_problem(half, 0, promotional=False)


# --- the register (block 1) ------------------------------------------------


def test_add_group_records_and_dedupes(conn):
    status, group_id, _ = groups_mod.add(conn, group("SG SME owners", "sgsme"))
    assert status == "added"
    row = groups_mod.get(conn, group_id)
    assert row["slug"] == "sg-sme-owners" and row["fit"] == "good fit" and not row["joined"]
    assert groups_mod.add(conn, group("Another name", "sgsme"))[0] == "duplicate"
    variant = group("SG SME owners again", "sgsme")
    variant["url"] = "https://m.facebook.com/groups/sgsme/"
    assert groups_mod.add(conn, variant)[0] == "duplicate"


@pytest.mark.parametrize("source", ["https://www.facebook.com/groups/sgsme/about", "https://fb.com/groups/x", "https://m.facebook.com/x", "https://fb.me/abc"])
def test_facebook_source_urls_are_rejected(conn, source):
    status, _, messages = groups_mod.add(conn, group("SG SME owners", "sgsme", source_urls=[source]))
    assert status == "rejected" and any("Facebook domain" in m for m in messages)


@pytest.mark.parametrize(
    "change, wanted",
    [
        ({"fit": "great"}, "fit must be"),
        ({"fit_reason": ""}, "fit_reason"),
        ({"source_urls": []}, "at least one"),
        ({"url": "https://example.sg/group"}, "facebook.com/groups"),
        ({"promo_rules": ""}, "promo_rules"),
    ],
)
def test_add_group_validates(conn, change, wanted):
    status, _, messages = groups_mod.add(conn, group("SG SME owners", "sgsme", **change))
    assert status == "rejected" and any(wanted in m for m in messages)


def test_other_channels_can_be_stored(conn):
    record = group("SBF SME Committee events", "x", channel="sbf", url="https://www.sbf.org.sg/events")
    assert groups_mod.add(conn, record)[0] == "added"


def test_add_group_command_takes_a_batch(tmp_path):
    file = tmp_path / "groups.json"
    file.write_text(json.dumps([group("SG SME owners", "a"), group("Bad", "b", source_urls=["https://facebook.com/x"])]))
    result = invoke("community", "add-group", "--file", str(file))
    assert result.exit_code == 0 and "1 added, 0 already known, 1 rejected" in result.output


def test_set_uses_the_prd_syntax(conn):
    _, group_id, _ = groups_mod.add(conn, group("SG SME owners", "sgsme", fit="possible"))
    result = invoke("community", "set", str(group_id), "joined=yes", "rules=promo Saturdays only", "fit=good fit", "notes=Joined 26 Oct",
                    "rules_confirmed=yes", "promo_days=sat", "post_days=any")
    assert result.exit_code == 0, result.output
    assert "promotion only on sat" in result.output
    row = groups_mod.get(conn, group_id)
    assert row["joined"] == 1 and row["rules_confirmed"] == 1 and row["fit"] == "good fit"
    assert row["promo_rules"] == "promo Saturdays only" and row["notes"] == "Joined 26 Oct"
    assert (row["promo_days_confirmed"], row["post_days_confirmed"]) == ("sat", "any")
    assert invoke("community", "set", str(group_id), "joined=maybe").exit_code != 0


@pytest.mark.parametrize("rules", ["No promotion on weekends.", "Be kind and respectful.", "not stated in public sources"])
def test_confirming_rules_needs_the_open_days_for_every_group(conn, rules):
    _, group_id, _ = groups_mod.add(conn, group("SG cafe owners", "sgcafe", rules=rules))
    refused = invoke("community", "set", str(group_id), "joined=yes", "rules_confirmed=yes")
    assert refused.exit_code != 0
    assert "promo_days=" in refused.output and "post_days=" in refused.output
    assert groups_mod.get(conn, group_id)["rules_confirmed"] == 0
    assert invoke("community", "set", str(group_id), "rules_confirmed=yes", "promo_days=any").exit_code != 0
    assert invoke("community", "set", str(group_id), "promo_days=funday").exit_code != 0

    done = invoke("community", "set", str(group_id), "rules_confirmed=yes", "promo_days=Mon to Fri", "post_days=any")
    assert done.exit_code == 0, done.output
    assert groups_mod.get(conn, group_id)["promo_days_confirmed"] == "mon,tue,wed,thu,fri"


def test_new_rules_text_clears_the_confirmed_days(conn):
    _, group_id, _ = groups_mod.add(conn, group("SG cafe owners", "sgcafe", rules="No promotion on weekends."))
    groups_mod.set_fields(conn, group_id, ["rules_confirmed=yes", "promo_days=mon-fri", "post_days=any"])
    row = groups_mod.set_fields(conn, group_id, ["rules=Promo on Saturdays only."])
    assert row["promo_days_confirmed"] is None and row["post_days_confirmed"] is None
    assert not groups_mod.rules_for(row).days_confirmed
    kept = groups_mod.set_fields(conn, group_id, ["rules=Promo on Fridays only.", "promo_days=fri", "post_days=any"])
    assert kept["promo_days_confirmed"] == "fri"


def test_summary_posts_to_community_and_says_nobody_joined(conn):
    groups_mod.add(conn, group("SG SME owners", "sgsme"))
    result = invoke("community", "summary")
    assert result.exit_code == 0
    [message] = outbox("community")
    assert "1 groups in the register" in message["content"] and "no posting plan this week" in message["content"]


def test_the_summary_hint_is_a_command_community_set_accepts(conn):
    """Ting Yu copies this line from #community into Terminal, so it must pass `community set`'s checks."""
    _, group_id, _ = groups_mod.add(conn, group("SG SME owners", "sgsme"))
    summary = invoke("community", "summary", "--no-post").output
    [hint] = re.findall(r"`(jura-growth community set [^`]*)`", summary)
    filled = re.sub(r"<[^>]*>", "any", hint.replace("<id>", str(group_id)))
    result = invoke(*shlex.split(filled)[1:])
    assert result.exit_code == 0, result.output
    row = groups_mod.get(conn, group_id)
    assert row["joined"] == 1 and row["rules_confirmed"] == 1
    assert (row["promo_days_confirmed"], row["post_days_confirmed"]) == ("any", "any")


def test_set_help_names_the_day_keys():
    help_text = invoke("community", "set", "--help").output
    assert "promo_days=" in help_text and "post_days=" in help_text


# --- the weekly plan (block 2) ---------------------------------------------


def test_block_2_done_when(conn, three, tmp_path):
    """A plan for 3 test groups has 3 different texts that pass the checker and
    respect each group's rules; a ticked item is recorded on the next run."""
    fnb, reno, home = three
    result = plan_mod.add(conn, good_plan(fnb, reno, home))
    assert result.ok and not result.errors, result.lines
    assert len(result.stored) == 5
    posts = plan_mod.stored_items(conn, "2026-W44", "post")
    texts = [p["text"] for p in posts]
    assert len(set(texts)) == 3
    for p in posts:
        qa = json.loads(p["qa_json"])
        assert qa["brand"] == "pass"
    # the Saturday-only group got its closing line on a Saturday; the unknown-rules group has no link
    by_group = {p["group_id"]: p for p in posts}
    assert by_group[fnb["id"]]["planned_day"] == "2026-10-31"
    assert not brand_check.find_links(by_group[home["id"]]["text"])

    file, posted, n_posts, n_replies = plan_mod.publish(conn)
    assert file == paths.outputs_dir() / "community" / "2026-W44.md" and (n_posts, n_replies) == (3, 2)
    checklist = file.read_text()
    first = posts[0]["id"]
    assert f"- [ ] Post item {first} " in checklist and "Rules reminder" in checklist
    assert outbox("community") and "Community plan 2026-W44" in outbox("community")[0]["content"]

    # Ting Yu ticks the first item; the next run (context) records it
    file.write_text(checklist.replace(f"- [ ] Post item {first} ", f"- [x] Post item {first} "))
    view = json.loads(invoke("community", "context", "--json").output)
    assert view["ticks_recorded"] == [first]
    row = db.one(conn, "SELECT status, posted_via FROM community_posts WHERE id = ?", (first,))
    assert row == {"status": "posted", "posted_via": "checklist"}
    assert invoke("community", "sync-ticks").output.strip() == "no new ticks"
    # republishing keeps the tick
    plan_mod.publish(conn)
    assert f"- [x] Post item {first} " in file.read_text()


def test_cap_of_three_groups_a_week(conn, three):
    fnb, reno, home = three
    extra = joined(conn, group("SG logistics owners", "sglog"))
    plan = good_plan(fnb, reno, home)
    plan["posts"].append({"group_id": extra["id"], "day": "2026-10-29", "text": POST_HOME.replace("receipts", "delivery notes")})
    result = plan_mod.add(conn, plan)
    assert not result.ok and any("the cap is 3" in e for e in result.errors)
    assert plan_mod.stored_items(conn, "2026-W44") == []


def test_config_may_lower_the_cap_not_raise_it(monkeypatch):
    monkeypatch.setattr(groups_mod, "settings", lambda: {"groups_per_week": 9, "no_repeat_days": 3})
    assert plan_mod.groups_per_week() == 3 and plan_mod.no_repeat_days() == 14
    monkeypatch.setattr(groups_mod, "settings", lambda: {"groups_per_week": 2})
    assert plan_mod.groups_per_week() == 2


def test_no_group_repeats_within_fourteen_days(conn, three):
    fnb, reno, home = three
    assert plan_mod.add(conn, {"week": "2026-W44", "posts": [{"group_id": home["id"], "day": "2026-10-28", "text": POST_HOME}]}).ok
    # the following Monday is 5 days later
    later = {"week": "2026-W45", "posts": [{"group_id": home["id"], "day": "2026-11-02", "text": POST_RENO.split("\n")[0]}]}
    result = plan_mod.add(conn, later)
    assert any("no group repeats within 14 days" in e for e in result.errors)
    # 14 days on, it may come round again
    ok_day = {"week": "2026-W46", "posts": [{"group_id": home["id"], "day": "2026-11-11", "text": POST_RENO.split("\n")[0]}]}
    assert not any("repeats" in e for e in plan_mod.prepare(conn, ok_day)[1])


def test_promotion_on_a_forbidden_day_is_rejected(conn, three):
    fnb, reno, home = three
    plan = {"posts": [{"group_id": fnb["id"], "day": "2026-10-27", "text": POST_FNB.format(slug=fnb["slug"])}]}
    assert any("promotion only on sat" in e for e in plan_mod.add(conn, plan).errors)
    value_only = POST_HOME  # no link, no Jura mention: fine on a Tuesday
    assert plan_mod.add(conn, {"posts": [{"group_id": fnb["id"], "day": "2026-10-27", "text": value_only}]}).ok


def test_unknown_or_unconfirmed_rules_mean_no_link(conn, three):
    fnb, reno, home = three
    with_link = POST_FNB.format(slug=home["slug"])
    result = plan_mod.add(conn, {"posts": [{"group_id": home["id"], "day": "2026-10-31", "text": with_link}]})
    assert any("rules are unknown" in e for e in result.errors)
    groups_mod.set_fields(conn, fnb["id"], ["rules_confirmed=no"])
    result = plan_mod.add(conn, {"posts": [{"group_id": fnb["id"], "day": "2026-10-31", "text": POST_FNB.format(slug=fnb["slug"])}]})
    assert any("not confirmed" in e for e in result.errors)


def test_unreadable_rules_need_a_stated_reason(conn, three):
    fnb, reno, home = three
    plan = {"posts": [{"group_id": reno["id"], "day": "2026-10-27", "text": POST_RENO}]}
    assert any("rules_ok" in e for e in plan_mod.add(conn, plan).errors)


@pytest.mark.parametrize("words, ok", [(59, False), (60, True), (150, True), (151, False)])
def test_post_word_range(conn, three, words, ok):
    fnb, reno, home = three
    vocabulary = (POST_HOME + " " + POST_RENO.split("\n")[0]).split()
    text = " ".join(vocabulary[:words])
    errors = plan_mod.prepare(conn, {"posts": [{"group_id": home["id"], "day": "2026-10-28", "text": text}]})[1]
    assert (not any("words; posts are" in e for e in errors)) == ok


def test_texts_must_differ_between_groups(conn, three):
    fnb, reno, home = three
    shared = "Keep one folder per month on your phone or computer."
    plan = {"posts": [
        {"group_id": home["id"], "day": "2026-10-28", "text": POST_HOME},
        {"group_id": reno["id"], "day": "2026-10-27", "text": POST_RENO.replace("Export it as a PDF", shared + " Export it as a PDF"),
         "rules_ok": "Respectful helpful post."},
    ]}
    assert any("shares a sentence" in e for e in plan_mod.add(conn, plan).errors)
    reworded = POST_HOME.replace("Keeping receipts tidy", "Keeping your receipts neat").replace("Small habits", "Little habits")
    plan = {"posts": [
        {"group_id": home["id"], "day": "2026-10-28", "text": POST_HOME},
        {"group_id": fnb["id"], "day": "2026-10-29", "text": reworded},
    ]}
    assert any("shares a sentence" in e or "too similar" in e for e in plan_mod.add(conn, plan).errors)
    assert plan_mod.similarity(POST_HOME, POST_RENO) < 0.1


@pytest.mark.parametrize(
    "closing, wanted",
    [
        ("Our free quote builder is at https://jurasolutions.sg/apps/quote-builder?utm_source=facebook_group&utm_campaign=wrong", "utm_campaign=sg-f-b-owners"),
        ("Our free quote builder is at https://jurasolutions.sg/apps/quote-builder?utm_campaign=sg-f-b-owners", "utm_source=facebook_group"),
        ("Jura Solutions builds tools like the one at https://example.com/quote?utm_source=facebook_group&utm_campaign=sg-f-b-owners", "jurasolutions.sg"),
        ("I run Jura Solutions. See https://jurasolutions.sg/apps/payslip-maker?utm_source=facebook_group&utm_campaign=sg-f-b-owners", "isn't a live toolbox tool"),
        ("I run Jura Solutions. See https://jurasolutions.sg/contact?utm_source=facebook_group&utm_campaign=sg-f-b-owners", "toolbox tool"),
    ],
)
def test_closing_line_link_rules(conn, three, closing, wanted):
    fnb, _, _ = three
    body = POST_FNB.split("\n")[0]
    errors = plan_mod.prepare(conn, {"posts": [{"group_id": fnb["id"], "day": "2026-10-31", "text": body + "\n" + closing}]})[1]
    assert any(wanted in e for e in errors), errors


def test_links_and_jura_only_in_the_closing_line(conn, three):
    fnb, _, _ = three
    first, closing = POST_FNB.format(slug=fnb["slug"]).split("\n")
    moved = f"{closing}\n{first}"
    errors = plan_mod.prepare(conn, {"posts": [{"group_id": fnb["id"], "day": "2026-10-31", "text": moved}]})[1]
    assert any("closing line" in e for e in errors)


def test_reply_ideas_carry_no_links(conn, three):
    fnb, reno, home = three
    plan = {"replies": [{"question": "Where can I make a quote?", "text": REPLY_QUOTE + " Try jurasolutions.sg/apps/quote-builder for a start."}]}
    assert any("no links" in e for e in plan_mod.add(conn, plan).errors)


def test_brand_failure_stores_the_rest_and_allows_one_regeneration(conn, three):
    fnb, reno, home = three
    plan = good_plan(fnb, reno, home)
    plan["posts"][2]["text"] = POST_HOME.replace("quiet afternoon.", "quiet afternoon. Act now!")
    result = plan_mod.add(conn, plan)
    assert not result.ok and len(result.retry) == 1 and len(result.stored) == 4
    again = plan_mod.add(conn, {"week": "2026-W44", "posts": [plan["posts"][2]]})
    assert again.dropped
    fixed = plan_mod.add(conn, {"week": "2026-W44", "posts": [{**plan["posts"][2], "text": POST_HOME}]})
    assert fixed.dropped  # the gate key is per group per week: dropped means dropped
    # resubmitting stored items is harmless
    assert plan_mod.add(conn, {"week": "2026-W44", "posts": plan["posts"][:2]}).ok


def test_posted_and_removed(conn, three):
    fnb, reno, home = three
    result = plan_mod.add(conn, good_plan(fnb, reno, home))
    item = result.stored[0]
    out = invoke("community", "posted", str(item), "https://www.facebook.com/groups/sgfnb/posts/1")
    assert out.exit_code == 0
    row = db.one(conn, "SELECT status, posted_url, posted_via FROM community_posts WHERE id = ?", (item,))
    assert row == {"status": "posted", "posted_url": "https://www.facebook.com/groups/sgfnb/posts/1", "posted_via": "command"}
    assert invoke("community", "removed", str(home["id"])).exit_code == 0
    gone = groups_mod.get(conn, home["id"])
    assert gone["fit"] == "skip" and gone["removed"] == 1
    assert db.scalar(conn, "SELECT status FROM community_posts WHERE group_id = ? AND kind = 'post'", (home["id"],)) == "skipped"
    assert invoke("community", "set", str(home["id"]), "fit=good fit").exit_code != 0
    assert home["id"] not in [g["id"] for g in groups_mod.eligible(conn)]


def test_context_lists_open_days_and_link_permission(conn, three):
    fnb, reno, home = three
    view = json.loads(invoke("community", "context", "--json").output)
    eligible = {g["id"]: g for g in view["eligible"]}
    assert eligible[fnb["id"]]["link_allowed"] and not eligible[home["id"]]["link_allowed"]
    assert eligible[reno["id"]]["needs_rules_ok"]
    sat = next(d for d in eligible[fnb["id"]]["days_open"] if d["weekday"] == "sat")
    tue = next(d for d in eligible[fnb["id"]]["days_open"] if d["weekday"] == "tue")
    assert sat["with_closing_line"] and not tue["with_closing_line"] and tue["value_post"]
    assert view["toolbox_live"] == ["quote-builder"] and view["limits"]["groups_per_week"] == 3


def test_context_opens_no_day_until_ting_yu_confirms_the_days(conn):
    waiting = joined(conn, group("SG cafe owners", "sgcafe", rules="No promotion on weekends."))
    no_day = joined(conn, group("SG florists", "sgflorists", rules="Self-promotion is welcome."))
    rules_only = joined(conn, group("SG printers", "sgprinters", rules="Self-promo is welcome on #SelfPromoSaturday."))
    no_promo = joined(conn, group("SG tutors", "sgtutors", rules="No self-promo."), "rules_confirmed=yes", "promo_days=any", "post_days=any")
    weekend = joined(conn, group("SG bakery owners", "sgbakery", rules="No promotion on weekends."),
                     "rules_confirmed=yes", "promo_days=mon-fri", "post_days=any")
    sunday = joined(conn, group("SG tuition centres", "sgtuition", rules="No posts on Sundays."),
                    "rules_confirmed=yes", "promo_days=any", "post_days=mon-sat")
    view = json.loads(invoke("community", "context", "--json").output)
    eligible = {g["id"]: g for g in view["eligible"]}

    for still_closed in (waiting, no_day, rules_only):
        closed = eligible[still_closed["id"]]
        assert not closed["rules"]["days_confirmed"] and closed["days_open"] == []
        assert "promo_days" in closed["rules_summary"]
    assert not eligible[rules_only["id"]]["link_allowed"]
    assert eligible[waiting["id"]]["rules"]["mentions_timing"] and not eligible[no_day["id"]]["rules"]["mentions_timing"]
    assert not any(d["with_closing_line"] for d in eligible[no_promo["id"]]["days_open"])
    assert all(d["value_post"] for d in eligible[no_promo["id"]]["days_open"])

    promo = {d["weekday"]: d for d in eligible[weekend["id"]]["days_open"]}
    assert promo["mon"]["with_closing_line"] and not promo["sat"]["with_closing_line"] and not promo["sun"]["with_closing_line"]
    assert promo["sat"]["value_post"]
    assert eligible[weekend["id"]]["rules_summary"] == "promotion only on mon, tue, wed, thu, fri"
    assert eligible[weekend["id"]]["link_allowed"] and not eligible[weekend["id"]]["needs_rules_ok"]

    posts = {d["weekday"]: d for d in eligible[sunday["id"]]["days_open"]}
    assert not posts["sun"]["value_post"] and not posts["sun"]["with_closing_line"] and posts["sat"]["value_post"]


def test_checklist_plans_only_on_the_days_ting_yu_confirmed(conn):
    waiting = joined(conn, group("SG cafe owners", "sgcafe", rules="No promotion on weekends."))
    weekend = joined(conn, group("SG bakery owners", "sgbakery", rules="No promotion on weekends."),
                     "rules_confirmed=yes", "promo_days=mon-fri", "post_days=any")
    sunday = joined(conn, group("SG tuition centres", "sgtuition", rules="No posts on Sundays."),
                    "rules_confirmed=yes", "promo_days=any", "post_days=mon-sat")
    closing_line = POST_FNB.format(slug=weekend["slug"])
    refused = plan_mod.add(conn, {"week": "2026-W44", "posts": [
        {"group_id": weekend["id"], "day": "saturday", "text": closing_line},
        {"group_id": sunday["id"], "day": "sunday", "text": POST_HOME},
        {"group_id": waiting["id"], "day": "monday", "text": POST_RENO.split("\n")[0], "rules_ok": "A weekday value post."},
    ]})
    assert any("Sat 31 Oct breaks the rules" in e for e in refused.errors), refused.errors
    assert any("Sun 01 Nov breaks the rules" in e for e in refused.errors), refused.errors
    assert any("Mon 26 Oct breaks the rules" in e and "hasn't confirmed" in e for e in refused.errors), refused.errors

    planned = plan_mod.add(conn, {"week": "2026-W44", "posts": [
        {"group_id": weekend["id"], "day": "monday", "text": closing_line},
        {"group_id": sunday["id"], "day": "saturday", "text": POST_HOME},
    ]})
    assert planned.ok, planned.lines
    file, *_ = plan_mod.publish(conn)
    checklist = file.read_text()
    assert "Planned as: promotion only on mon, tue, wed, thu, fri." in checklist
    assert "Planned as: posts only on mon, tue, wed, thu, fri, sat." in checklist
    assert checklist.count("the rules mention timing, so check the day against them") == 2


def test_brand_channels():
    assert brand_check.check(REPLY_LATE, channel_name="community-reply").passed
    assert not brand_check.check(REPLY_LATE + " See jurasolutions.sg", channel_name="community-reply").passed
    assert not brand_check.check("Too short to be a post.", channel_name="community-post").passed
    dm = POST_HOME + " DM me for the template."
    assert any("DMs" in r for r in brand_check.check(dm, channel_name="community-post").reasons())


# --- audit-run ---------------------------------------------------------------


def _transcript(run_id, calls, denials=()):
    path = paths.data_dir() / "transcripts" / MONDAY / f"{run_id}-community.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [{"type": "system", "subtype": "init"}]
    for index, (name, tool_input, ok) in enumerate(calls):
        tid = f"t{index}"
        records.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": tid, "name": name, "input": tool_input}]}})
        records.append({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "is_error": not ok,
                                                                 "content": "ok" if ok else "Permission to use WebFetch has been denied."}]}})
    records.append({"type": "result", "subtype": "success", "is_error": False, "result": "SKIP: none joined", "total_cost_usd": 0.4,
                    "permission_denials": [{"tool_name": "WebFetch", "tool_use_id": d, "tool_input": {}} for d in denials]})
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return path


def test_audit_run_clean(conn):
    run_id = log.start_run(conn, "community", "community")
    _transcript(run_id, [
        ("WebSearch", {"query": "site:facebook.com groups Singapore SME owners"}, True),
        ("WebFetch", {"url": "https://example.sg/best-facebook-groups", "prompt": "list"}, True),
        ("Bash", {"command": "jura-growth community add-group --file groups.json"}, True),
    ])
    result = invoke("community", "audit-run", str(run_id))
    assert result.exit_code == 0 and "clean. 1 web searches and 1 page fetches" in result.output


def test_audit_run_reports_refused_attempts_as_still_clean(conn):
    run_id = log.start_run(conn, "community", "community")
    _transcript(run_id, [("WebFetch", {"url": "https://www.facebook.com/groups/sgsme", "prompt": "rules"}, False)], denials=["t0"])
    result = invoke("community", "audit-run", str(run_id))
    assert result.exit_code == 0 and "1 attempt refused" in result.output


@pytest.mark.parametrize(
    "call",
    [
        ("WebFetch", {"url": "https://www.facebook.com/groups/sgsme/about", "prompt": "rules"}, True),
        ("WebFetch", {"url": "https://fb.com/groups/x", "prompt": "x"}, True),
        ("Bash", {"command": "curl -s https://m.facebook.com/groups/sgsme"}, True),
    ],
)
def test_audit_run_catches_facebook_fetches(conn, call):
    run_id = log.start_run(conn, "community", "community")
    _transcript(run_id, [call])
    result = invoke("community", "audit-run", str(run_id))
    assert result.exit_code == 1 and "NOT CLEAN" in result.output


def test_audit_run_without_a_transcript_fails():
    assert invoke("community", "audit-run", "999").exit_code == 1


# --- digest and precheck -----------------------------------------------------


def test_digest_figures(conn, three):
    fnb, reno, home = three
    result = plan_mod.add(conn, good_plan(fnb, reno, home))
    plan_mod.mark_posted(conn, result.stored[0])
    part = community_plugin.digest(conn, MONDAY)
    assert part["figures"]["community_groups"] == 3 and part["figures"]["community_joined"] == 3
    assert part["figures"]["community_posts_planned"] == 3 and part["figures"]["community_posts_posted"] == 1
    assert "3 groups in the register (3 good fit, 3 joined)" in part["lines"][0]
    assert part["brief"] == ["community: 1 of 3 posts done this week"]
    assert community_plugin.precheck("community", conn) is None


def test_digest_audits_todays_community_run(conn):
    run_id = log.start_run(conn, "community", "community")
    _transcript(run_id, [("WebSearch", {"query": "sg sme groups"}, True)])
    log.finish_run(conn, run_id, "ok", summary="SKIP: none joined")
    part = community_plugin.digest(conn, MONDAY)
    assert f"Community run {run_id} audit: clean" in part["lines"]


def test_transcript_reader_tolerates_system_records(conn):
    """Real stream-json has system records whose `message` is a string, and a
    `permission_denied` record naming the refused tool call."""
    run_id = log.start_run(conn, "community", "community")
    path = _transcript(run_id, [("WebFetch", {"url": "https://www.facebook.com/groups/x", "prompt": "rules"}, False)])
    lines = path.read_text().splitlines()
    lines.insert(1, json.dumps({"type": "system", "subtype": "permission_denied", "tool_name": "WebFetch",
                                "tool_use_id": "t0", "message": "Permission to use WebFetch has been denied"}))
    lines.insert(1, json.dumps({"type": "rate_limit_event", "message": "plain text"}))
    path.write_text("\n".join(lines) + "\n")
    from jura_growth.agents.community import transcript

    found = transcript.read(path)
    assert found.calls[0].denied and found.fetched_urls() == []
    result = invoke("community", "audit-run", str(run_id))
    assert result.exit_code == 0 and "1 attempt refused" in result.output


def test_audit_run_ignores_facebook_urls_written_as_data(conn):
    """A heredoc that writes group records (with their facebook.com/groups
    links) to a file is not a fetch; a curl in the same transcript is."""
    run_id = log.start_run(conn, "community", "community")
    heredoc = "cat > /tmp/groups.json <<'EOF'\n[{\"url\": \"https://www.facebook.com/groups/sgsme\"}]\nEOF"
    _transcript(run_id, [("Bash", {"command": heredoc}, False), ("Write", {"file_path": "/x/groups.json", "content": "https://www.facebook.com/groups/a"}, True)])
    result = invoke("community", "audit-run", str(run_id))
    assert result.exit_code == 0 and "refused" not in result.output
    run_id = log.start_run(conn, "community", "community")
    _transcript(run_id, [("Bash", {"command": heredoc + "\ncurl https://www.facebook.com/groups/sgsme"}, True)])
    assert invoke("community", "audit-run", str(run_id)).exit_code == 1
