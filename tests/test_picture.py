"""The morning picture's words, on built snapshots (seam U; MB1, MB3, MB4, MB6, MB7, MB10).

No database and no Chrome: `picture.*` and `one_pager.summary()` on a `mission.Snapshot`. What the
page looks like is `test_picture_chrome.py`; the route from growth.db is `test_picture_read.py`.
"""

from __future__ import annotations

import html as html_mod
import re
from datetime import datetime, timedelta

import pytest

import picture_world as world
from jura_growth import approvals, health, images, mission, one_pager, picture, slots
from jura_growth.agents.apps import builds, releases
from jura_growth.timeutil import SGT
from test_one_pager_grid import _defined_tokens

NOW = world.NOW
DASH = "–"


def visible(page: str) -> str:
    body = page.split("<body>", 1)[1]
    return " ".join(html_mod.unescape(re.sub(r"<[^>]+>", " ", body)).split())


def row(snapshot: mission.Snapshot, label: str) -> picture.AgentRow:
    return next(r for r in picture.agent_rows(snapshot) if r.label == label)


def with_counts(requests: int = 0, fixes: int = 0, drafts: int = 0, replies: int = 0) -> mission.Snapshot:
    return world.snap(
        slots=world.morning(),
        approvals=tuple(world.request(n) for n in range(requests)),
        plugin_lines=tuple(f"Fix item {n}" for n in range(fixes)),
        morning=world.figures(social_drafts_by_hand=drafts),
        yesterday=world.figures(replies=replies),
    )


# --- MB1: the verdict --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "counts, words",
    [
        (dict(requests=2, fixes=1), "2 to decide, 1 to fix."),
        (dict(requests=2, fixes=1, drafts=1, replies=1), "2 to decide, 1 to fix, 1 to post by hand, 1 reply to read."),
        (dict(drafts=3, replies=2), "3 to post by hand, 2 replies to read."),
        (dict(requests=1), "1 to decide."),
        (dict(fixes=1), "1 to fix."),
        (dict(drafts=1), "1 to post by hand."),
        (dict(replies=1), "1 reply to read."),
        (dict(), "Nothing needs you right now."),
    ],
)
def test_the_verdict_counts_all_four_things(counts, words):
    assert picture.verdict(with_counts(**counts)) == words


@pytest.mark.parametrize("reading", [mission.Reading.WAITING, mission.Reading.APPROVED, mission.Reading.SKIPPED, mission.Reading.USED])
def test_an_answered_social_card_is_not_a_draft_to_post_by_hand(reading):
    """Final B2: a card means a `browser` platform, which publish posts. Only a draft on a
    `draft` platform is his to post, and that platform raises no card."""
    snapshot = world.snap(slots=world.morning(), morning=world.figures(social_drafts_waiting=1),
                          yesterday=world.figures(), approvals=(world.request(1, "social-post", reading=reading),))
    assert "to post by hand" not in picture.verdict(snapshot)


def test_a_card_for_one_platform_leaves_the_other_platforms_draft_to_post():
    snapshot = world.snap(slots=world.morning(), approvals=(world.request(1, "social-post"),),
                          morning=world.figures(social_drafts_waiting=2, social_drafts_by_hand=1), yesterday=world.figures())
    assert picture.verdict(snapshot) == "1 to decide, 1 to post by hand."


@pytest.mark.parametrize("fields", [
    dict(morning=None, yesterday=world.figures()),
    dict(morning=world.figures(), yesterday=None),
    dict(morning=mission.Yesterday("d", (), 0.0, {}), yesterday=mission.Yesterday("d", (), 0.0, {})),
])
def test_a_count_that_cant_be_read_never_says_nothing_needs_you(fields):
    words = picture.verdict(world.snap(slots=world.morning(), approvals=(), **fields))
    assert "Nothing needs you" not in words
    assert "couldn't be read" in words


def test_reply_detection_off_leaves_the_all_clear_possible():
    """It is a standing setting, off by choice: counting it as unknown would mean no all-clear, ever."""
    snapshot = world.snap(slots=world.morning(), approvals=(), morning=world.figures(),
                          yesterday=world.figures(reply_detection=False))
    assert picture.verdict(snapshot) == "Nothing needs you right now."


def test_three_unset_settings_fit_their_row_and_four_move_to_a_second_line():
    three = picture.fixes(world.snap(gaps=tuple(health.Gap(f"SETTING_{n}") for n in range(3))))
    assert three == ["Set `SETTING_0`, `SETTING_1`, `SETTING_2`."]
    (four,) = picture.fixes(world.snap(gaps=tuple(health.Gap(f"SETTING_{n}") for n in range(4))))
    first, detail = four.split("\n")
    assert first == "Run `jura-growth status` for the 4 settings to set."
    assert detail == "Not set: `SETTING_0`, `SETTING_1`, `SETTING_2`, `SETTING_3`."
    assert "SETTING_0" not in picture.html(world.snap(gaps=tuple(health.Gap(f"SETTING_{n}") for n in range(4))))


def test_a_recorded_reply_shows_even_with_reply_detection_off():
    """B2: the flag is today's setting and the count is yesterday's. Off with a count of 0 reads as
    0 in the verdict (conductor's ruling), or he never gets an all-clear."""
    snapshot = world.snap(slots=world.morning(), approvals=(), morning=world.figures(),
                          yesterday=world.figures(replies=2, reply_detection=False))
    assert picture.verdict(snapshot) == "2 replies to read."
    assert dict((c, f) for f, c in picture.yesterday_tiles(snapshot))["replies"] == "2"


@pytest.mark.parametrize("label, gone", [
    ("Scout", "leads_added"), ("Outreach", "emails_queued"), ("Social", "social_drafts_waiting"),
    ("Community", "community_posts_planned"), ("App factory", "app_prd_today"),
])
def test_any_unread_morning_figure_qualifies_the_all_clear(label, gone):
    """S1: a row showing a dash under "Nothing needs you right now." would be too strong."""
    figures = {k: v for k, v in world.RECORDED.items() if k != gone}
    snapshot = world.snap(slots=world.morning(), approvals=(), morning=mission.Yesterday("d", (), 0.0, figures), yesterday=world.figures())
    assert picture.verdict(snapshot) == "Nothing to decide or fix, but some figures couldn't be read."


@pytest.mark.parametrize("gone", ["emails_sent", "replies", "social_published"])
def test_any_unread_yesterday_figure_qualifies_the_all_clear(gone):
    figures = {k: v for k, v in world.RECORDED.items() if k != gone}
    snapshot = world.snap(slots=world.morning(), approvals=(), morning=world.figures(), yesterday=mission.Yesterday("d", (), 0.0, figures))
    assert "couldn't be read" in picture.verdict(snapshot)


def test_spend_with_no_recorded_cost_qualifies_the_all_clear_and_shows_a_dash():
    """S4."""
    unrecorded = mission.Yesterday("d", (), 0.0, dict(world.RECORDED), spend_recorded=False)
    snapshot = world.snap(slots=world.morning(), approvals=(), morning=world.figures(), yesterday=unrecorded)
    assert dict((c, f) for f, c in picture.yesterday_tiles(snapshot))["Claude spend"] == DASH
    assert "couldn't be read" in picture.verdict(snapshot)


def test_a_job_that_didnt_run_stops_the_all_clear():
    snapshot = world.snap(world.NOW, slots=world.morning(social="due"), approvals=(), morning=world.figures(),
                          yesterday=world.figures())
    assert picture.verdict(snapshot) == "1 to fix."


# --- MB3: Decide and Fix ---------------------------------------------------------------------


def test_decide_lists_the_soonest_first_with_ties_by_id():
    soon, later = NOW + timedelta(hours=1), NOW + timedelta(hours=5)
    found = picture.waiting(world.snap(approvals=(world.request(3, decide_by=later), world.request(2, decide_by=soon), world.request(1, decide_by=later))))
    assert [r.id for r in found] == ["A-0002", "A-0001", "A-0003"]


def test_only_waiting_requests_are_listed():
    found = picture.waiting(world.snap(approvals=(world.request(1), world.request(2, reading=mission.Reading.APPROVED), world.request(3, reading=mission.Reading.LAPSED))))
    assert [r.id for r in found] == ["A-0001"]


def test_each_request_shows_its_kind_id_reason_and_decide_by():
    text = visible(picture.html(world.snap(approvals=(world.request(412, decide_by=NOW + timedelta(hours=7)),), slots=world.morning())))
    assert "Outreach email A-0412 Send to Acme Pte Ltd Decide by today 16:00" in text


def test_a_decide_by_on_another_day_names_the_day():
    assert picture.by_when(NOW + timedelta(days=1), NOW) == "Wed 11 Nov 09:00"
    assert picture.by_when(NOW + timedelta(hours=1), NOW) == "today 10:00"


def test_a_missed_slot_line_holds_a_count_and_no_time():
    times = [slots.SlotStatus("scout-send", datetime(2026, 11, 9, 10, minute, tzinfo=SGT), "missed") for minute in (0, 10)]
    [line] = picture.fixes(world.snap(slots={("scout-send", times[0].at.date()): times}))
    assert "2 slots" in line and "scout-send" in line
    assert not re.search(r"\d\d:\d\d", line), line


def test_lists_stop_at_a_cap_and_say_how_many_more():
    text = visible(picture.html(world.worst()))
    assert "and 46 more" in text and "and 16 more" in text


# --- S1: the short wording puts the action first ----------------------------------------------

REQUEST_FAILURE = mission.Failure("community", datetime(2026, 11, 9, 7, 30, tzinfo=SGT), "boom")


@pytest.mark.parametrize("fields, starts", [
    (dict(pause_file="holiday"), "Delete the PAUSE file on the Mac"),
    (dict(paused=(("outreach", "3 failed runs in a row"),)), "Send `/growth resume outreach`"),
    (dict(failures=(REQUEST_FAILURE,)), "Check `community`"),
    (dict(drift=health.Drift("social", "07:30", "22:30", -9)), "Restart the Mac once: scheduled jobs run about 9 hours off (`social` due 07:30, ran 22:30)."),
    (dict(approvals=(world.request(412, "social-post", refused="Discord would mask part of the post", posted=False),)), "Let A-0412 lapse Tue 10 Nov, 16:00 SGT: it has no card"),
    (dict(undelivered=2), "Run `jura-growth discord test`"),
    (dict(installs={"backup": health.NOT_INSTALLED}), "Run `jura-growth schedule install`"),
    (dict(installs={"social": health.OUT_OF_DATE}), "Run `jura-growth schedule install` again"),
    (dict(gaps=(health.Gap("RESEND_API_KEY_OUTREACH"), health.Gap("UNSUBSCRIBE_SECRET"))), "Set `RESEND_API_KEY_OUTREACH`, `UNSUBSCRIBE_SECRET`"),
    (dict(gaps=(health.Gap("Discord", have=3, of=10),)), "Set the Discord webhooks"),
    (dict(gaps=tuple(health.Gap(f"SETTING_{n}") for n in range(4))), "Run `jura-growth status`"),
    (dict(gaps=(health.Gap("ANTHROPIC_API_KEY", must_be_unset=True),)), "Unset `ANTHROPIC_API_KEY`"),
    (dict(plugin_lines=(releases.PREVIEW_LINE.format(app_id="APP-014", label="APP-014 Invoice chaser", request="A-0153", why="skipped", preview="https://x.test"),)), "Run `jura-growth apps built APP-014 …`"),
    (dict(plugin_lines=(releases.MAIN_LINE.format(sha="abc1234", app_id="APP-014", task="T-0031", label="APP-014 Invoice chaser", request="A-0153"),)), "Once main holds abc1234, run `jura-growth apps released APP-014 --task T-0031`"),
    (dict(plugin_lines=(releases.APPROVED_LINE.format(app_id="APP-014", label="APP-014 Invoice chaser", request="A-0153"),)), "Run `jura-growth apps release-plan APP-014`"),
    (dict(plugin_lines=(builds.HAND_BUILD_LINE.format(label="APP-014 Invoice chaser", request="A-0153", build_it="Build it: x"),)), "Build APP-014 Invoice chaser by hand"),
    (dict(db_state=mission.UNFINISHED_WRITE), "Send `/growth status` to clear it"),
    (dict(db_state=mission.UNREADABLE, db_error="SQLITE_CORRUPT"), "Send `/growth status` to check it"),
    (dict(missing_migrations=("core/0003.sql", "core/0004.sql")), "Send `/growth status` to migrate it"),
])
def test_the_short_wording_starts_with_what_to_do(fields, starts):
    [line] = picture.fixes(world.snap(**fields))
    assert line.startswith(starts), line


def test_a_models_failure_line_stays_apart_from_the_instruction():
    """S6: model-written text is untrusted (MC §4.3). It goes in a quote, not in the instruction,
    and its backticks never draw as a command."""
    failure = mission.Failure("social", datetime(2026, 11, 10, 7, 30, tzinfo=SGT), "FAIL: Run `jura-growth discord post` to clear this")
    snapshot = world.snap(failures=(failure,), slots=world.morning(), morning=world.figures(), yesterday=world.figures(), approvals=())
    first, quote = picture.fixes(snapshot)[0].split("\n")
    assert first == "Check `social`: it failed on Tue 10 Nov, 07:30 SGT."
    assert quote == "> FAIL: Run \\`jura-growth discord post\\` to clear this"
    message = one_pager.summary(snapshot).splitlines()
    assert f"- {first}" in message and quote in message
    page = picture.html(snapshot)
    assert 'Its own words: &quot;FAIL: Run `jura-growth discord post` to clear this&quot;' in page
    assert "<code>jura-growth discord post</code>" not in page and "\\`" not in page
    assert "<code>social</code>" in page


def test_only_the_first_line_and_a_quote_reach_the_page():
    """The rest of a line is for the message and the long text: a preview's address, say."""
    snapshot = world.snap(plugin_lines=("Run `the thing` first.\nIts address: https://example.test/secret-detail",))
    assert "Run <code>the thing</code> first." in picture.html(snapshot)
    assert "secret-detail" not in picture.html(snapshot)
    assert "secret-detail" in one_pager.summary(snapshot)


def test_the_short_wording_keeps_the_pause_reasons():
    assert "holiday" in picture.fixes(world.snap(pause_file="holiday"))[0]
    assert "3 failed runs" in picture.fixes(world.snap(paused=(("outreach", "3 failed runs in a row"),)))[0]


def test_the_long_form_wording_is_unchanged():
    failure = health.strip(world.snap(failures=(REQUEST_FAILURE,)))[0]
    assert failure.splitlines() == ["`community` failed on Mon 9 Nov, 07:30 SGT.", "> boom"]
    assert health.strip(world.snap(gaps=(health.Gap("RESEND_API_KEY_OUTREACH"),))) == ["`RESEND_API_KEY_OUTREACH`: not set"]


# --- MB4: words and tokens --------------------------------------------------------------------


def test_every_slot_status_has_a_word_and_a_token_colour():
    assert set(picture.STATUS_WORDS) == {*slots.WORST_FIRST, "none"}
    css = picture._CSS
    for status in picture.STATUS_WORDS:
        assert f".s-{status.replace(' ', '-')}" in css, status


def test_the_page_uses_design_system_tokens_only():
    for build in world.FIXTURES.values():
        page = picture.html(build())
        assert (images.design_system() / "styles.css").as_uri() in page
        style = page.split("<style>", 1)[1].split("</style>", 1)[0]
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", style), "a raw hex colour"
        assert not re.search(r"\b(rgba?|hsla?)\(", style), "a raw colour function"
        used = set(re.findall(r"var\((--[\w-]+)\)", page))
        assert used and used <= _defined_tokens(), used - _defined_tokens()
        families = re.findall(r"font-family\s*:\s*([^;}\"]+)", page)
        assert families and all(family.strip().startswith("var(--font-") for family in families), families


def test_the_status_words_read_on_the_page():
    text = visible(picture.html(world.snap(slots=world.morning(scout_research="failed", social="skipped", app_factory="running"))))
    for word in ("Failed", "Skipped", "Still running", "Ran"):
        assert word in text


# --- MB6: a passed slot, and no slot ---------------------------------------------------------


AT_0730 = NOW.replace(hour=7, minute=30)


@pytest.mark.parametrize("minutes, word, detail", [
    (0, "Due now", "Due at 07:30"),
    (5, "Due now", "Due at 07:30"),
    (6, "Didn't run", "No trace of its 07:30 run"),
    (90, "Didn't run", "No trace of its 07:30 run"),
])
def test_a_slot_with_no_trace_reads_by_how_long_ago_it_was(minutes, word, detail):
    now = AT_0730 + timedelta(minutes=minutes)
    found = row(world.snap(now, slots=world.morning(now=now, social="due"), morning=world.figures()), "Social")
    assert (found.word, found.detail) == (word, detail)


def test_a_slot_that_passed_with_no_trace_gains_a_fix_line():
    lines = picture.fixes(world.snap(slots=world.morning(social="due"), morning=world.figures()))
    assert len(lines) == 1 and "`social`" in lines[0] and "no trace" in lines[0]
    assert not re.search(r"\d\d:\d\d", lines[0]), "a count or a name, no timestamps"


def test_a_slot_still_within_five_minutes_gains_no_fix_line():
    now = AT_0730 + timedelta(minutes=5)
    assert picture.fixes(world.snap(now, slots=world.morning(now=now, social="due"))) == []


def test_a_monday_community_slot_that_left_no_trace_reaches_fix_on_monday_and_the_day_after():
    monday = datetime(2026, 11, 16, 8, 0, tzinfo=SGT)
    missed = {("community", monday.date()): [world.slot("community", "due", at=monday)]}
    on_monday = world.snap(monday + timedelta(hours=1), slots=missed)
    assert row(on_monday, "Community").word == "Didn't run"
    assert [line for line in picture.fixes(on_monday) if "`community`" in line]
    tuesday = world.snap(monday + timedelta(days=1), slots={**missed, ("community", monday.date() + timedelta(days=1)): []})
    assert "Mon 16 Nov" in " ".join(picture.fixes(tuesday))
    wednesday = world.snap(monday + timedelta(days=2), slots=missed)
    assert picture.fixes(wednesday) == []


@pytest.mark.parametrize("state", [health.OUT_OF_DATE, health.NOT_INSTALLED])
def test_a_job_whose_schedule_isnt_current_gains_no_didnt_run_line(state):
    """Between the pull and `schedule install`, old-time runs land in yesterday's slot. Fix already
    says what to do about the job, once."""
    snapshot = world.snap(slots=world.morning(social="due"), installs={"social": state})
    assert [line for line in picture.fixes(snapshot) if "no trace" in line] == []
    found = row(snapshot, "Social")
    assert found.word != "Didn't run"
    assert "schedule install" in found.detail


INSTALLED = {"outreach-requests": health.INSTALLED}


def never_ran(status: str = "not installed", **fields) -> mission.Snapshot:
    """`outreach-requests` on its first mornings: the classifier calls a slot before a job's first
    trace "not installed", whatever launchd says."""
    base = dict(slots=world.morning(outreach_requests=status), morning=world.figures(), yesterday=world.figures(), approvals=(), installs=INSTALLED)
    return world.snap(**{**base, **fields})


def test_an_installed_job_that_has_never_left_a_trace_reads_didnt_run():
    """B1: the row, Fix and the verdict can't contradict each other."""
    snapshot = never_ran()
    assert (row(snapshot, "Outreach").word, row(snapshot, "Outreach").detail) == ("Didn't run", "No trace of its 08:30 run")
    assert picture.fixes(snapshot) == ["Check `outreach-requests`: no trace of its run today."]
    assert picture.verdict(snapshot) == "1 to fix."


def test_a_slot_from_before_the_install_is_not_judged_so_install_day_stays_clean():
    snapshot = never_ran(installed_at={"outreach-requests": NOW.replace(hour=8, minute=45)})
    assert (row(snapshot, "Outreach").word, row(snapshot, "Outreach").detail) == ("Not judged", "Installed today 08:45")
    assert picture.fixes(snapshot) == []
    assert picture.verdict(snapshot) == "Nothing needs you right now."


def test_a_slot_after_the_install_with_no_trace_is_judged():
    snapshot = never_ran(installed_at={"outreach-requests": NOW.replace(hour=8, minute=0)})
    assert row(snapshot, "Outreach").word == "Didn't run"
    assert len(picture.fixes(snapshot)) == 1


def test_a_job_that_isnt_installed_keeps_its_one_fix_line():
    snapshot = never_ran(installs={"outreach-requests": health.NOT_INSTALLED})
    assert row(snapshot, "Outreach").word == "Not installed"
    assert [line for line in picture.fixes(snapshot) if "no trace" in line] == []


def test_an_installed_job_with_a_run_on_record_never_reads_not_installed():
    """Final S1: install at 10:00; the job ran at its old time that morning; asked at 10:10."""
    now = NOW.replace(hour=10, minute=10)
    snapshot = world.snap(now, slots=world.morning(now=now, social="not installed"), morning=world.figures(),
                          yesterday=world.figures(), approvals=(), installs={"social": health.INSTALLED},
                          installed_at={"social": NOW.replace(hour=10, minute=0)})
    assert (row(snapshot, "Social").word, row(snapshot, "Social").detail) == ("Not judged", "Installed today 10:00")
    assert picture.fixes(snapshot) == []


def test_an_installed_job_before_its_first_slot_reads_as_coming():
    now = NOW.replace(hour=8, minute=0)
    snapshot = never_ran(slots=world.morning(now=now, outreach_requests="not installed"))
    early = world.snap(now, slots=snapshot.slots, installs=INSTALLED)
    assert (row(early, "Outreach").word, row(early, "Outreach").detail) == ("Later", "Due at 08:30")
    moment = NOW.replace(hour=8, minute=33)
    soon = world.snap(moment, slots=world.morning(now=moment, outreach_requests="not installed"), installs=INSTALLED)
    assert (row(soon, "Outreach").word, row(soon, "Outreach").detail) == ("Due now", "Due at 08:30")


def test_a_job_launchd_doesnt_have_still_reads_not_installed():
    snapshot = never_ran(installs={"outreach-requests": health.NOT_INSTALLED}, installed_at={"outreach-requests": NOW.replace(hour=8, minute=45)})
    assert row(snapshot, "Outreach").word == "Not installed"


def test_a_job_launchd_says_nothing_about_is_not_judged():
    snapshot = never_ran(installs={})
    assert row(snapshot, "Outreach").word == "Not installed"
    assert picture.fixes(snapshot) == []


def test_a_slot_still_to_come_is_not_judged():
    now = NOW.replace(hour=8, minute=0)
    snapshot = never_ran(slots=world.morning(now=now, outreach_requests="not installed"))
    early = world.snap(now, **{k: getattr(snapshot, k) for k in ("slots", "morning", "yesterday", "approvals", "installs")})
    assert picture.fixes(early) == []


def test_a_job_silent_for_days_is_one_fix_line():
    today, day_before = NOW, NOW - timedelta(days=1)
    silent = {(job, at.date()): [world.slot(job, "not installed", at=at)] for job, at in
              (("outreach-requests", today.replace(hour=8, minute=30)), ("outreach-requests", day_before.replace(hour=8, minute=30)))}
    snapshot = world.snap(slots=silent, installs=INSTALLED)
    assert picture.fixes(snapshot) == ["Check `outreach-requests`: no trace of its run today."]


def test_a_job_silent_two_mornings_is_one_fix_line():
    """Final S2: "no trace" names the job, so its missed count would only add to the verdict."""
    today, yesterday = NOW.date(), (NOW - timedelta(days=1)).date()
    snapshot = world.snap(
        slots={("social", yesterday): [world.slot("social", "missed", at=NOW.replace(hour=7, minute=30) - timedelta(days=1))],
               ("social", today): [world.slot("social", "due", at=NOW.replace(hour=7, minute=30))]},
        morning=world.figures(), yesterday=world.figures(), approvals=(), installs={"social": health.INSTALLED},
    )
    assert picture.fixes(snapshot) == ["Check `social`: no trace of its run today."]
    assert picture.verdict(snapshot) == "1 to fix."


def test_a_missed_slot_with_no_trace_line_keeps_its_count():
    yesterday = NOW - timedelta(days=1)
    snapshot = world.snap(slots={("scout-send", yesterday.date()): [world.slot("scout-send", "missed", at=yesterday)]})
    assert len(picture.fixes(snapshot)) == 1 and "missed 1 slot" in picture.fixes(snapshot)[0]


def test_later_today_names_windows_and_promises_nothing():
    """Final S4: the schedule alone can't say a post will go out."""
    text = " ".join(picture.later_today(world.typical()))
    assert "go out" not in text and "send " not in text.lower().replace("send window", "")


def test_real_items_come_ahead_of_setup_chores_and_no_trace_lines():
    """QA E15, conductor's ruling: the ICP line or a live-outreach blocker can't fall under
    "and N more" because a job left no trace or a schedule is out of date."""
    blocker, icp = "Run `jura-growth outreach status`: 1 thing stops live outreach.", "Put the ICP in inputs/icp.md."
    snapshot = world.snap(
        slots=world.morning(social="due", app_factory="due"),
        installs={"backup": health.NOT_INSTALLED, "heartbeat": health.OUT_OF_DATE, "social": health.INSTALLED, "app-factory": health.INSTALLED},
        gaps=(health.Gap("Discord", have=3, of=10), health.Gap("RESEND_API_KEY_OUTREACH")),
        plugin_lines=(blocker, icp),
    )
    found = picture.fixes(snapshot)
    assert found[:2] == [blocker, icp]
    assert [line for line in found if "no trace" in line] == found[-2:]
    assert len(found) == 8


def test_the_pause_still_comes_first():
    snapshot = world.snap(pause_file="holiday", paused=(("social", "by hand"),), plugin_lines=("A plug-in line.",))
    found = picture.fixes(snapshot)
    assert found[0].startswith("Delete the PAUSE file") and found[1].startswith("Send `/growth resume social`")
    assert found[2] == "A plug-in line."


def test_a_passed_slot_stays_due_in_the_classifier():
    """The word changes on the picture only: `slots.py` keeps its `due`."""
    assert "due" in slots.WORST_FIRST
    assert row(world.snap(slots=world.morning(social="due")), "Social").status != "due"


def test_no_slot_today_says_so_once():
    found = row(world.snap(slots=world.morning(community=None)), "Community")
    assert (found.word, found.detail) == ("Not today", "")
    text = visible(picture.html(world.snap(slots=world.morning(community=None))))
    assert text.count("Not today") == 1 and "No run today" not in text


def test_a_row_says_how_many_requests_it_has_waiting():
    snapshot = world.snap(slots=world.morning(), approvals=(world.request(1, "group-join"), world.request(2, "community-post"), world.request(3, "app-build")))
    assert row(snapshot, "Community").to_approve == 2
    assert row(snapshot, "App factory").to_approve == 1
    assert row(snapshot, "Outreach").to_approve == 0
    assert "2 to approve" in visible(picture.html(snapshot))


def test_every_registered_approval_kind_has_one_row():
    """Risk 5: a kind no row owns would be waiting with nowhere to show."""
    owned = [kind for agent in picture.AGENTS for kind in agent.kinds]
    assert sorted(owned) == sorted(set(owned))
    assert set(approvals.kinds()) <= set(owned), set(approvals.kinds()) - set(owned)


def test_a_skip_shows_a_short_reason():
    found = row(world.snap(slots={**world.morning(), ("social", NOW.date()): [world.slot("social", "skipped", reason="/Users/me/data/inputs/icp.md is missing. Write it first.")]}), "Social")
    assert found.detail == "inputs/icp.md is missing"


# --- MB7: dashes, never a guessed zero ----------------------------------------------------------


@pytest.mark.parametrize("label, gone", [
    ("Scout", "leads_added"), ("Outreach", "emails_queued"), ("Social", "social_drafts_waiting"),
    ("Community", "community_posts_planned"), ("App factory", "app_prd_today"),
])
def test_a_figure_that_cant_be_read_shows_a_dash_in_its_row(label, gone):
    figures = {k: v for k, v in world.RECORDED.items() if k != gone}
    found = row(world.snap(slots=world.morning(), morning=mission.Yesterday("d", (), 0.0, figures)), label)
    assert (found.word, found.detail) == ("Ran", DASH)


@pytest.mark.parametrize("label", list(world.JOBS))
def test_no_morning_figures_show_a_dash_in_every_row(label):
    assert row(world.snap(slots=world.morning(), morning=None), label).detail == DASH


def test_a_recorded_zero_still_shows_zero():
    snapshot = world.quiet()
    assert row(snapshot, "Scout").detail == "0 new leads kept"
    assert row(snapshot, "Social").detail == "0 drafts waiting"
    assert row(snapshot, "App factory").detail == "No new PRD"
    assert [figure for figure, _ in picture.yesterday_tiles(snapshot)] == ["0", "0", "0", "US$0.00"]


@pytest.mark.parametrize("gone, caption", [("emails_sent", "emails sent"), ("replies", "replies"), ("social_published", "social posts")])
def test_a_tile_that_cant_be_read_shows_a_dash(gone, caption):
    figures = {k: v for k, v in world.RECORDED.items() if k != gone}
    tiles = dict((c, f) for f, c in picture.yesterday_tiles(world.snap(yesterday=mission.Yesterday("d", (), 0.0, figures))))
    assert tiles[caption] == DASH
    assert tiles["Claude spend"] == "US$0.00"


def test_reply_detection_off_shows_a_dash_for_replies():
    tiles = dict((c, f) for f, c in picture.yesterday_tiles(world.snap(yesterday=world.figures(reply_detection=False))))
    assert tiles["replies"] == DASH
    assert tiles["emails sent"] == "0"


def test_yesterday_unread_is_four_dashes_and_no_warning():
    snapshot = world.snap(yesterday=None, approvals=(world.request(1, reading=mission.Reading.LAPSED),))
    assert [figure for figure, _ in picture.yesterday_tiles(snapshot)] == [DASH] * 4
    assert picture.yesterday_warning(snapshot) == ""


def test_slots_that_cant_be_read_say_not_available_everywhere():
    snapshot = world.snap(db_state=mission.UNFINISHED_WRITE)
    assert [(r.word, r.detail) for r in picture.agent_rows(snapshot)] == [("Not available", "")] * 5
    assert picture.later_today(snapshot) == ["Not available"]
    text = visible(picture.html(snapshot))
    assert "Not today" not in text and "Nothing else scheduled" not in text


@pytest.mark.parametrize("snapshot", [world.database_locked(), world.database_missing()], ids=["locked", "missing"])
def test_the_decide_heading_shows_a_dash_when_approvals_cant_be_read(snapshot):
    """B3: "Decide in #approvals 0" above "Not available" was a guessed zero."""
    page = picture.html(snapshot)
    assert '<h2>Decide in #approvals <span class="n">–</span></h2>' in page
    assert '<span class="n">0</span>' not in page.split("</h2>", 1)[0]


def test_the_decide_heading_shows_a_real_zero():
    assert '<h2>Decide in #approvals <span class="n">0</span></h2>' in picture.html(world.quiet())


def test_later_today_lists_what_is_still_to_come():
    assert picture.later_today(world.typical()) == ["Posting window 10:00–16:00", "Send window 09:30", "Digest 17:30"]
    assert picture.later_today(world.quiet()) == []
    assert "Nothing else scheduled" in visible(picture.html(world.quiet()))


# --- Yesterday's warnings ---------------------------------------------------------------------


def test_unsubscribes_bounces_and_complaints_are_named_only_when_there_are_some():
    assert picture.yesterday_warning(world.quiet()) == ""
    snapshot = world.snap(yesterday=world.figures(unsubscribes=1, bounces=2, complaints=3))
    assert picture.yesterday_warning(snapshot) == "1 unsubscribe, 2 bounces, 3 complaints"


def test_requests_that_lapsed_since_the_last_one_pager_are_named():
    snapshot = world.snap(yesterday=world.figures(bounces=1), approvals=(world.request(1, reading=mission.Reading.LAPSED), world.request(2, reading=mission.Reading.LAPSED), world.request(3)))
    assert picture.yesterday_warning(snapshot) == "1 bounce, 2 lapsed unanswered"


def test_a_tile_of_one_is_captioned_in_the_singular():
    tiles = picture.yesterday_tiles(world.snap(yesterday=world.figures(emails_sent=1, replies=1, social_published=1)))
    assert tiles[:3] == [("1", "email sent"), ("1", "reply"), ("1", "social post")]


def test_each_tile_is_captioned_on_its_own():
    """N4: the captions ran together, and "posts published" read a figure that excludes community posts."""
    captions = [caption for _, caption in picture.yesterday_tiles(world.quiet())]
    assert captions == ["emails sent", "replies", "social posts", "Claude spend"]
    assert re.search(r"\.tiles \{[^}]*\bgap:", picture._CSS)


# --- MB10: the message ---------------------------------------------------------------------------


def test_the_message_holds_the_header_verdict_counts_soonest_and_fix_lines():
    text = one_pager.summary(world.typical())
    lines = text.splitlines()
    assert lines[0] == "**Tue 10 Nov, as of 09:00 SGT**"
    assert lines[1] == picture.verdict(world.typical())
    assert "Decide in #approvals: outreach email 1, social post 1. Soonest: A-0413, by today 12:00." in lines
    assert "- Send `/growth resume social` to resume. Paused: 3 failed runs in a row." in lines
    assert lines[-1] == "`/growth status` · `/growth approvals`"


def test_the_message_never_splits_from_the_picture():
    text = one_pager.summary(world.worst())
    assert len(text) <= 2000
    assert text.count("\n- ") == picture.FIX_SHOWN + 1  # four lines, and the "and N more" line
    assert "- and 16 more: run `jura-growth one-pager --no-post` on the Mac" in text


def test_the_message_shows_ordinary_fix_lines_in_full_and_cuts_only_the_longest():
    lines = tuple(f"Plain item {n} of an ordinary length, with its instruction at the end." for n in range(4))
    text = one_pager.summary(world.snap(plugin_lines=lines))
    for line in lines:
        assert f"- {line}" in text
    many = tuple(health.Gap(f"SETTING_NUMBER_{n:03d}") for n in range(40))
    long = one_pager.summary(world.snap(gaps=many))
    assert "SETTING_NUMBER_000" in long and "SETTING_NUMBER_039" not in long and "…" in long


LINK = "[Approve here](https://example.test/x)"


@pytest.mark.parametrize("fields", [
    dict(pause_file=f"Away {LINK}"),
    dict(paused=(("outreach", f"Away {LINK}"),)),
    dict(plugin_lines=(f"Away {LINK}",)),
], ids=["PAUSE file", "pause reason", "plug-in line"])
def test_no_live_masked_link_reaches_the_message(fields):
    """Suppressing embeds doesn't stop a masked link. The page has no links at all, so it keeps
    the text as it was written."""
    snapshot = world.snap(**fields)
    message = one_pager.summary(snapshot)
    assert LINK not in message and "[Approve here]\\(https://example.test/x)" in message
    assert html_mod.escape(LINK) in picture.html(snapshot)


def test_the_message_says_so_when_nothing_is_waiting():
    text = one_pager.summary(world.quiet())
    assert text.splitlines()[:2] == ["**Tue 10 Nov, as of 09:00 SGT**", "Nothing needs you right now."]
    assert "Decide in" not in text
