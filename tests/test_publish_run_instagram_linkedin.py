"""The whole publish job for Instagram and LinkedIn with the fake `claude` binary (BP-04; seam S10;
datasets D11 and T).

`runner.run("publish")` in process, as `test_publish_run.py` runs it for the Facebook Page, with
the platform under test put in `browser` mode in the test's own `social.yaml`. Rows traced:
AC-P11.1 for both identities (a mismatch stops before any typing with `wrong-identity`, pauses
`publish` and alerts once), a clean post on each platform including an Instagram carousel day
with every slide in order (AC-P2.2, AC-P7.1, AC-P8.1), and the audit failing a carousel whose
slides went up out of order (AC-P9.3).
"""

from __future__ import annotations

from urllib.parse import urlsplit

import pytest

import publish_transcripts as t
import publish_world as pw
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import pause, paths
from test_publish_run import alerts, browser, chrome, claim, fake, item, run, run_row  # noqa: F401 - fake is a fixture

IG_POST = pw.INSTAGRAM_POST
LI_POST = pw.LINKEDIN_POST
WHERE = {"instagram": (pw.INSTAGRAM_URL, IG_POST, "Instagram"), "linkedin": (pw.LINKEDIN_URL, LI_POST, "LinkedIn page"),
         "facebook": (pw.PAGE_URL, t.POST, "Facebook Page")}
OWN_PAGE = {"instagram": "jura.solutions\nEdit profile\nCreate", "linkedin": "Jura Solutions\nAdmin view\nStart a post",
            "facebook": "Jura Solutions\nCreate post"}
SOMEONE_ELSE = {"instagram": "someone.else\nFollow\nMessage", "linkedin": "Start a post\nPosting as Someone Else"}
ALL = ("facebook", "instagram", "linkedin")


def browser_mode(fake, *platforms: str) -> None:
    def change(data):
        for name, spec in data["platforms"].items():
            spec["publish_mode"] = "browser" if name in platforms else "draft"
            if name in platforms:
                spec["page_url"] = WHERE[name][0]

    fake.social(change)


def approved_instagram(conn, fake, monkeypatch, *platforms: str):
    """An approved Instagram carousel for Thu 12 Nov, three slides, and 10:00 that day, with
    `platforms` (Instagram alone by default) in `browser` mode."""
    browser_mode(fake, *(platforms or ("instagram",)))
    pw.at(monkeypatch, "2026-11-12T07:05:00+08:00")
    found, approval = pw.approved(conn, monkeypatch, "instagram", day=pw.THURSDAY, images=pw.slides())
    pw.at(monkeypatch, "2026-11-12T10:00:00+08:00")
    return found, approval


@pytest.fixture
def instagram(conn, fake, monkeypatch):
    return approved_instagram(conn, fake, monkeypatch)


@pytest.fixture
def linkedin(conn, fake, monkeypatch):
    """An approved LinkedIn company page post for Tue 10 Nov, one image, and 10:00 that day."""
    browser_mode(fake, "linkedin")
    pw.at(monkeypatch, pw.MORNING)
    found, approval = pw.approved(conn, monkeypatch, "linkedin")
    pw.at(monkeypatch, pw.TEN)
    return found, approval


def post_steps(platform: str, uploads: list[list[str]], *, on: str | None = None, done_url: str | None = None) -> list[dict]:
    """A post of the claimed `platform` item, made on `on`'s page (the item's own by default) and
    recorded with `done_url` (the platform's post address by default)."""
    page_url, post_url, _ = WHERE[on or platform]
    done_url = done_url or WHERE[platform][1]
    return [
        *browser(t.created(), t.opened(page_url), t.page("get_page_text", {}, OWN_PAGE[platform], url=page_url),
                 t.page("computer", {"action": "left_click", "ref": "ref_5"}, "Clicked Create.", url=page_url)),
        *[chrome(t.page("file_upload", {"paths": paths_, "ref": "ref_20"}, "Uploaded.", url=page_url)) for paths_ in uploads],
        chrome(t.page("computer", {"action": "left_click", "ref": "ref_12"}, "Clicked.", url=page_url)),
        chrome(t.typed("{TEXT}") | {"result": "Typed.\n" + t.tab_context((t.TAB, page_url))}),
        *browser(t.page("computer", {"action": "left_click", "ref": "ref_30"}, "Clicked.", url=page_url),
                 t.opened(post_url)),
        chrome(t.page("get_page_text", {}, "{TEXT}", url=post_url)),
        {"write": "{A}-live.txt", "text": "{TEXT}"},
        {"cli": ["publish", "done", "{A}", "--url", done_url, "--live-text-file", "{WORK}/{A}-live.txt"]},
        chrome(t.closed()),
    ]


def stopped_steps(platform: str) -> list[dict]:
    page_url = WHERE[platform][0]
    return [
        *browser(t.created(), t.opened(page_url), t.page("get_page_text", {}, SOMEONE_ELSE[platform], url=page_url)),
        {"cli": ["publish", "stopped", "{A}", "--reason", "wrong-identity"]},
        chrome(t.closed()),
    ]


# --- clean posts ---------------------------------------------------------------------------------------


def test_an_instagram_carousel_posts_every_slide_in_order_and_reports_once(conn, fake, instagram, discord_double):
    found, approval = instagram
    fake.scenario([*claim(), *post_steps("instagram", [["{IMG1}", "{IMG2}", "{IMG3}"]])], "OK: posted {A} " + IG_POST)

    outcome = run()

    assert outcome.status == "ok", outcome
    handed = fake.cli[0]["output"]
    assert handed.count("instagram-") == 3
    row = item(conn, found)
    assert (row["state"], row["outcome"], row["post_url"], row["live_text_matches"]) == ("done", "posted", IG_POST, 1)
    [update] = discord_double.contents("social-drafts")
    assert approval.id in update and "Instagram" in update and IG_POST in update
    assert alerts(discord_double) == []
    assert not pause.is_paused(conn, "publish")


def test_a_linkedin_company_page_post_posts_and_reports_once(conn, fake, linkedin, discord_double):
    found, approval = linkedin
    fake.scenario([*claim(), *post_steps("linkedin", [["{IMG1}"]])], "OK: posted {A} " + LI_POST)

    outcome = run()

    assert outcome.status == "ok", outcome
    assert "ClaudeInChromeDomain(www.linkedin.com)" in " ".join(fake.argv)
    assert "facebook" not in " ".join(a for a in fake.argv if a.startswith("ClaudeInChromeDomain("))
    row = item(conn, found)
    assert (row["state"], row["post_url"], row["live_text_matches"]) == ("done", LI_POST, 1)
    [update] = discord_double.contents("social-drafts")
    assert approval.id in update and "LinkedIn page" in update and LI_POST in update
    assert alerts(discord_double) == []


# --- AC-P9.3: the carousel order is audited -------------------------------------------------------------


def test_carousel_slides_uploaded_out_of_order_fail_the_run_and_pause_publish(conn, fake, instagram, discord_double):
    fake.scenario([*claim(), *post_steps("instagram", [["{IMG2}", "{IMG1}", "{IMG3}"]])], "OK: posted {A}")

    outcome = run()

    assert outcome.status == "failed"
    assert "out of their approved order" in outcome.error
    assert pause.is_paused(conn, "publish")
    assert any("out of their approved order" in a for a in alerts(discord_double))
    assert not any("instagram-" in a for a in alerts(discord_double))  # never a path


def test_a_carousel_whose_last_slide_failed_to_upload_fails_the_run(conn, fake, instagram, discord_double):
    """Code review 04, S1: a failed upload never counts as a slide sent."""
    steps = post_steps("instagram", [["{IMG1}", "{IMG2}"]])
    failed = chrome(t.page("file_upload", {"paths": ["{IMG3}"], "ref": "ref_20"}, "Upload failed.", url=pw.INSTAGRAM_URL,
                           error=True))
    steps.insert(5, failed)
    fake.scenario([*claim(), *steps], "OK: posted {A}")

    outcome = run()

    assert outcome.status == "failed"
    assert "2 of its 3" in outcome.error
    assert pause.is_paused(conn, "publish")


# --- code review 04, B1: an item goes out only on its own platform ---------------------------------------


@pytest.mark.parametrize("other", ["linkedin", "facebook"])
def test_an_instagram_item_posted_on_another_enabled_platform_fails_the_run_and_pauses(
        conn, fake, monkeypatch, discord_double, other):
    """With every platform in `browser` mode, an Instagram carousel posted on the LinkedIn company
    page or the Facebook Page, and recorded with an Instagram post address, fails closed."""
    found, approval = approved_instagram(conn, fake, monkeypatch, *ALL)
    fake.scenario([*claim(), *post_steps("instagram", [["{IMG1}", "{IMG2}", "{IMG3}"]], on=other)], "OK: posted {A}")

    outcome = run()

    assert len([a for a in fake.argv if a.startswith("ClaudeInChromeDomain(")]) == 9  # the rules are the union
    assert outcome.status == "failed"
    host = urlsplit(WHERE[other][0]).hostname or ""
    assert host in outcome.error and "the publish hosts" in outcome.error
    assert pause.is_paused(conn, "publish")
    assert any(host in a for a in alerts(discord_double))


def test_a_done_url_that_isnt_an_instagram_post_leaves_the_item_unknown_and_pauses(conn, fake, monkeypatch, discord_double):
    """B1b: the post made on LinkedIn, then recorded with the Instagram profile's address."""
    found, _ = approved_instagram(conn, fake, monkeypatch, *ALL)
    steps = post_steps("instagram", [["{IMG1}", "{IMG2}", "{IMG3}"]], on="linkedin", done_url=pw.INSTAGRAM_URL)
    fake.scenario([*claim(), *steps], "OK: posted {A}")

    outcome = run()

    assert outcome.status == "failed"
    assert [c["exit"] for c in fake.cli if c["cli"][:2] == ["publish", "done"]] == [1]
    assert item(conn, found)["state"] == "unknown"
    assert "www.linkedin.com" in outcome.error  # and the audit names where it went
    assert pause.is_paused(conn, "publish")


# --- AC-P11.1: the wrong identity stops before any typing ----------------------------------------------


@pytest.mark.parametrize("platform", ["instagram", "linkedin"])
def test_the_wrong_identity_stops_before_any_typing_pauses_and_alerts_once(conn, fake, request, discord_double, platform):
    found, approval = request.getfixturevalue(platform)
    fake.scenario([*claim(), *stopped_steps(platform)], "FAIL: {A} wrong posting identity")

    outcome = run()

    assert outcome.status == "failed"
    row = item(conn, found)
    assert row["state"] == "stopped" and row["stop_reason"] == "wrong-identity"
    assert pause.is_paused(conn, "publish")
    sent = alerts(discord_double)
    assert len(sent) == 1 and approval.id in sent[0] and f"run {run_row(conn)['id']}" in sent[0]
    assert "someone" not in " ".join(sent).lower()  # never the page's text
    [update] = discord_double.contents("social-drafts")
    assert approval.id in update and WHERE[platform][2] in update and "wrong-identity" in update
    record = (paths.data_dir() / "transcripts").rglob("*-publish.jsonl")
    typed = [line for path in record for line in path.read_text().splitlines() if '"action": "type"' in line]
    assert typed == []
    assert not [c for c in fake.cli if c["cli"][:2] == ["publish", "done"]]
