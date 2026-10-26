"""Instagram and LinkedIn in the publish queue (BP-04; test strategy v3 §4.2 and §11.2, row BP-04).

The rows 02 proved for the Facebook Page, run again for the Jura Instagram account and the Jura
LinkedIn company page at the `social submit` and `publish next` / `publish done` seam (S7), with
the Discord double (S5):

- AC-P1.1 per platform: `social submit` with one platform in `browser` mode raises exactly one
  `social-post` request for it, and its `#social-drafts` message points at the card.
- AC-P1.3, the carousel row: on an Instagram carousel day the content covers every image's bytes
  in order, so a change in any image's bytes, or in their order, supersedes the request.
- AC-P5.1 line 1 per platform: a second item for the same platform and day is refused.
- AC-P7.2 for the new hosts: `www.instagram.com` and `www.linkedin.com` are accepted for their own
  items, and the look-alikes (and the other platforms' hosts) are refused. A post URL must also be
  a post's own address, not a profile or a feed (code review 04, S4).
- The LinkedIn `page_url` must be a company page, never a person's profile (code review 04, S5).

The clock is BP's default, Tue 2026-11-10, unless a test needs a carousel day (Mon or Thu).
"""

from __future__ import annotations

import json

import pytest

import publish_world as pw
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import approvals, db, pause, paths
from jura_growth.agents.publish import items, kinds
from jura_growth.agents.social import submit
from test_social import IG, LI, MONDAY, NEWS, TIP, env, write  # noqa: F401 - env is a fixture

NEW = ("instagram", "linkedin")
URLS = {"instagram": pw.INSTAGRAM_URL, "linkedin": pw.LINKEDIN_URL}
LABELS = {"instagram": "Instagram", "linkedin": "LinkedIn page"}
IDENTITIES = {"instagram": "the Jura Solutions Instagram account", "linkedin": "the Jura Solutions LinkedIn company page"}
VARIANTS = {"instagram": IG, "linkedin": LI}
IMAGES = {"instagram": "instagram-1080x1350.png", "linkedin": "linkedin-1200x627.png"}


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
    pw.at(monkeypatch, pw.TEN)


def next_json():
    result = pw.invoke("publish", "next", "--json")
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def live_file(text: str) -> str:
    path = paths.work_dir("publish") / "live.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def social_requests(conn) -> list[dict]:
    return db.rows(conn, "SELECT * FROM approvals WHERE kind = 'social-post' ORDER BY id")


def image_paths(conn, post: int) -> list[str]:
    stored = db.scalar(conn, "SELECT image_paths FROM social_posts WHERE id = ?", (post,))
    assert isinstance(stored, str)
    return json.loads(stored)


# --- AC-P1.1 per platform: one request, and the drafts message points at the card -----------------


@pytest.mark.parametrize("platform", NEW)
def test_submit_raises_exactly_one_social_post_request_for_the_platform_in_browser_mode(
        conn, env, monkeypatch, discord_double, platform):
    pw.at(monkeypatch, pw.MORNING)
    pw.social_config(monkeypatch, browser=(platform,))
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
    folder = write(paths.work_dir("social") / pw.DAY.isoformat(), TIP)

    assert submit.submit(conn, folder, offline=True).status == "delivered"

    rows = db.rows(conn, "SELECT * FROM publish_items")
    assert [(r["kind"], r["platform"], r["day"], r["state"]) for r in rows] == [("social_post", platform, "2026-11-10", "ready")]
    assert json.loads(rows[0]["content_json"])["posting_identity"] == IDENTITIES[platform]
    [request] = approvals.pending(conn)
    assert request.kind == "social-post" and request.subject == f"publish_item:{rows[0]['id']}"
    [card] = discord_double.posts("approvals")
    content = card.content or ""
    assert content.split("\n")[0] == f"**{request.id} · social post** · decide by Tue 10 Nov, 18:00 SGT"
    assert LABELS[platform] in content and URLS[platform] in content
    assert IDENTITIES[platform] in content
    assert VARIANTS[platform].strip() in content
    assert "Brand check: passed on attempt 1 of 2" in content
    assert [name for name, _ in card.files] == [IMAGES[platform]]

    mine = [p for p in discord_double.posts("social-drafts") if (p.content or "").startswith(f"**{LABELS[platform]}**")]
    assert len(mine) == 1
    pointer = mine[0].content or ""
    assert request.id in pointer and "#approvals" in pointer
    assert VARIANTS[platform].strip() not in pointer and mine[0].files == []
    others = [p for p in discord_double.posts("social-drafts")
              if (p.content or "").startswith(("**Facebook Page**", *(f"**{LABELS[o]}**" for o in NEW if o != platform)))]
    assert len(others) == 2 and all("post it by hand" in (p.content or "") and p.files for p in others)


def test_on_a_carousel_day_the_instagram_card_carries_every_slide_in_order(conn, env, monkeypatch, discord_double):
    pw.at(monkeypatch, MONDAY)
    pw.social_config(monkeypatch, browser=("instagram",))
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
    folder = write(paths.work_dir("social") / "2026-10-26", NEWS)

    assert submit.submit(conn, folder, offline=True).status == "delivered"

    [row] = db.rows(conn, "SELECT * FROM publish_items")
    content = json.loads(row["content_json"])
    names = [image["path"].rsplit("/", 1)[-1] for image in content["images"]]
    assert names == ["instagram-1-of-3-1080x1350.png", "instagram-2-of-3-1080x1350.png", "instagram-3-of-3-1080x1350.png"]
    [card] = discord_double.posts("approvals")
    assert [name for name, _ in card.files] == names
    assert "3 images attached, posted in this order." in (card.content or "")


# --- AC-P1.3 the carousel row ----------------------------------------------------------------------


def change_slide_bytes(conn, post, number):
    pw.Path(image_paths(conn, post)[number - 1]).write_bytes(pw.png(1080, 1350, extra=b"a different slide"))


def change_slide_order(conn, post, order):
    current = image_paths(conn, post)
    conn.execute("UPDATE social_posts SET image_paths = ? WHERE id = ?",
                 (json.dumps([current[i - 1] for i in order]), post))


CAROUSEL_CHANGES = {
    "first slide's bytes": lambda conn, post: change_slide_bytes(conn, post, 1),
    "middle slide's bytes": lambda conn, post: change_slide_bytes(conn, post, 2),
    "last slide's bytes": lambda conn, post: change_slide_bytes(conn, post, 3),
    "two slides swapped": lambda conn, post: change_slide_order(conn, post, (1, 3, 2)),
    "slides rotated": lambda conn, post: change_slide_order(conn, post, (2, 3, 1)),
    "a slide dropped": lambda conn, post: change_slide_order(conn, post, (1, 2)),
}


@pytest.mark.parametrize("change", list(CAROUSEL_CHANGES))
def test_a_carousel_change_in_any_slides_bytes_or_their_order_supersedes_the_request(conn, world, monkeypatch, change):
    pw.social_config(monkeypatch, browser=("instagram",))
    pw.at(monkeypatch, "2026-11-12T07:05:00+08:00")
    found, approval = pw.approved(conn, monkeypatch, "instagram", day=pw.THURSDAY, images=pw.slides())
    assert approval is not None
    kind = kinds.SocialPost()
    before = kind.content(conn, approval.subject)
    assert before is not None and approvals.content_hash(before) == approval.content_hash

    CAROUSEL_CHANGES[change](conn, found.ref_id)
    after = kind.content(conn, approval.subject)
    assert after is not None and after != before

    pw.at(monkeypatch, "2026-11-12T10:00:00+08:00")
    pw.run(conn, monkeypatch=monkeypatch)
    assert pw.next_item(conn).item is None
    record = approvals.get(conn, approval.id)
    assert record is not None and record.status == "superseded"
    [fresh] = [a for a in approvals.pending(conn) if a.subject == approval.subject]
    assert fresh.supersedes == approval.number and fresh.content_hash == approvals.content_hash(after)


def test_an_unchanged_carousel_is_handed_out_slide_for_slide_in_order(conn, world, monkeypatch):
    pw.social_config(monkeypatch, browser=("instagram",))
    pw.at(monkeypatch, "2026-11-12T07:05:00+08:00")
    originals = pw.slides()
    _, approval = pw.approved(conn, monkeypatch, "instagram", day=pw.THURSDAY, images=originals)
    assert approval is not None
    pw.at(monkeypatch, "2026-11-12T10:00:00+08:00")
    pw.run(conn, monkeypatch=monkeypatch)

    handed = next_json()

    assert handed["due"] is True and handed["approval"] == approval.id and handed["platform"] == "instagram"
    assert [pw.Path(p).read_bytes() for p in handed["images"]] == [p.read_bytes() for p in originals]
    assert [pw.Path(p).name.split("-", 1)[0] for p in handed["images"]] == ["1", "2", "3"]


# --- AC-P5.1 line 1 per platform ------------------------------------------------------------------


@pytest.mark.parametrize("platform", NEW)
def test_line_1_a_second_item_for_the_same_platform_and_day_is_refused(conn, world, monkeypatch, platform):
    pw.social_config(monkeypatch, browser=(platform,))
    found, request = pw.approved(conn, monkeypatch, platform)
    assert request is not None
    assert next_json()["approval"] == request.id
    assert pw.invoke("publish", "stopped", request.id, "--reason", "login").exit_code == 0
    pause.resume(conn, "publish")
    second = items.create_social(conn, found.ref_id, run_id=None)
    assert second.approval is not None
    pw.decide(conn, second.approval)
    pw.at(monkeypatch, "2026-11-10T11:00:00+08:00")

    refused = next_json()

    assert refused["due"] is False
    assert any(f"{platform} already had its post claimed for 2026-11-10" in r for r in refused["reasons"])
    record = approvals.get(conn, second.approval.id)
    assert record is not None and not record.used_at


# --- AC-P7.2 the new hosts, and S4 the post's own address ----------------------------------------------


ACCEPTED = {
    "instagram": [
        pw.INSTAGRAM_POST, "https://instagram.com/p/C0deAbc123/", "https://www.instagram.com/p/C0de_Abc-123",
        "https://www.instagram.com/p/C0deAbc123/?img_index=1", "https://www.instagram.com/reel/C0deAbc123/",
    ],
    "linkedin": [
        pw.LINKEDIN_POST, "https://www.linkedin.com/feed/update/urn:li:share:7254000000000000001/",
        "https://www.linkedin.com/feed/update/urn:li:ugcPost:7254000000000000002",
        "https://linkedin.com/posts/jura-solutions_automation-activity-7254000000000000000-abcd",
    ],
}
REFUSED = {
    "instagram": [
        "https://instagram.com.evil.test/p/1/", "https://www.instagram.com@evil.test/p/1/",
        "https://evil.test/www.instagram.com/p/1/", "javascript:alert(1)", "http://www.instagram.com/p/1/",
        "https:///p/1/", "https://www.instagram.com:8443/p/1/", "https://l.instagram.com/?u=https://evil.test",
        "https://scontent.cdninstagram.com/v/t51/1.jpg", "https://www.facebook.com/jura-test-page/posts/1",
        "https://www.linkedin.com/feed/update/urn:li:activity:1/",
        # S4: on the host, but not a post's own address
        pw.INSTAGRAM_URL, "https://www.instagram.com/", "https://www.instagram.com/explore/",
        "https://www.instagram.com/p/", "https://www.instagram.com/p/C0deAbc123/comments/",
        "https://www.instagram.com/jura-test-page/p/C0deAbc123/",
    ],
    "linkedin": [
        "https://linkedin.com.evil.test/feed/update/1/", "https://www.linkedin.com@evil.test/feed/update/1/",
        "https://evil.test/www.linkedin.com/feed/update/1/", "javascript:alert(1)",
        "http://www.linkedin.com/feed/update/1/", "https:///feed/update/1/", "https://www.linkedin.com:8443/feed/update/1/",
        "https://lnkd.in/abc123", "https://media.licdn.com/dms/image/1.jpg", "https://sg.linkedin.com/company/jura",
        "https://www.instagram.com/p/C0deAbc123/", "https://www.facebook.com/jura-test-page/posts/1",
        # S4: on the host, but not a post's own address
        pw.LINKEDIN_URL, "https://www.linkedin.com/company/jura-test-page/posts/", "https://www.linkedin.com/feed/",
        "https://www.linkedin.com/in/someone/", "https://www.linkedin.com/feed/update/urn:li:activity:abc/",
        "https://www.linkedin.com/feed/update/urn:li:member:7254000000000000000/",
        "https://www.linkedin.com/posts/someone_a-post",
    ],
}


@pytest.mark.parametrize("platform, url", [(p, u) for p in NEW for u in ACCEPTED[p]])
def test_the_new_platforms_post_addresses_are_accepted_for_their_own_items(conn, world, monkeypatch, platform, url):
    pw.social_config(monkeypatch, browser=(platform,))
    found, request = pw.approved(conn, monkeypatch, platform)
    assert request is not None
    next_json()
    result = pw.invoke("publish", "done", request.id, "--url", url, "--live-text-file", live_file(pw.TEXT))
    assert result.exit_code == 0, result.output
    row = pw.item_row(conn, found.id)
    assert (row["state"], row["post_url"]) == ("done", url)
    assert db.scalar(conn, "SELECT published_url FROM social_posts WHERE id = ?", (found.ref_id,)) == url


@pytest.mark.parametrize("platform, url", [(p, u) for p in NEW for u in REFUSED[p]])
def test_look_alikes_other_hosts_and_non_post_addresses_exit_1_and_record_nothing(conn, world, monkeypatch, platform, url):
    pw.social_config(monkeypatch, browser=(platform,))
    found, request = pw.approved(conn, monkeypatch, platform)
    assert request is not None
    next_json()
    result = pw.invoke("publish", "done", request.id, "--url", url, "--live-text-file", live_file(pw.TEXT))
    assert result.exit_code == 1
    assert pw.item_row(conn, found.id)["state"] == "claimed"


@pytest.mark.parametrize("platform, url, settles", [
    ("instagram", pw.INSTAGRAM_URL, False), ("instagram", pw.INSTAGRAM_POST, True),
    ("linkedin", pw.LINKEDIN_URL, False), ("linkedin", pw.LINKEDIN_POST, True),
])
def test_resolve_posted_takes_only_a_posts_own_address(conn, world, monkeypatch, platform, url, settles):
    pw.social_config(monkeypatch, browser=(platform,))
    found, request = pw.approved(conn, monkeypatch, platform)
    assert request is not None
    next_json()
    conn.execute("UPDATE publish_items SET state = 'unknown' WHERE id = ?", (found.id,))
    conn.commit()

    result = pw.invoke("publish", "resolve", request.id, "posted", "--url", url)

    assert (result.exit_code == 0) is settles, result.output
    assert pw.item_row(conn, found.id)["state"] == ("done" if settles else "unknown")


# --- S5 the page each platform posts to -----------------------------------------------------------


@pytest.mark.parametrize("platform, url", [
    ("instagram", "https://instagram.com.evil.test/jura"), ("instagram", "https://www.linkedin.com/company/jura"),
    ("linkedin", "https://www.linkedin.com@evil.test/company/jura"), ("linkedin", "https://www.instagram.com/jura"),
    ("linkedin", "https://www.linkedin.com/in/ting-yu/"), ("linkedin", "https://www.linkedin.com/feed/"),
    ("linkedin", "https://www.linkedin.com/"), ("linkedin", "https://www.linkedin.com/company/"),
    ("instagram", "https://www.instagram.com/p/C0deAbc123/"), ("instagram", "https://www.instagram.com/explore/"),
    ("instagram", "https://www.instagram.com/"),
])
def test_a_page_url_that_isnt_the_platforms_own_page_raises_no_item(conn, monkeypatch, platform, url):
    pw.social_config(monkeypatch, browser=(platform,), urls={platform: url})
    pw.at(monkeypatch, pw.TEN)
    made = items.create_social(conn, pw.draft(conn, platform), run_id=None)
    assert made.item is None and "page_url" in made.why
    assert social_requests(conn) == []


@pytest.mark.parametrize("platform, url", [
    ("linkedin", "https://www.linkedin.com/company/jura-solutions"),
    ("linkedin", "https://www.linkedin.com/company/105000000/admin/page-posts/published/"),
    ("instagram", "https://www.instagram.com/jura.solutions/"), ("instagram", "https://www.instagram.com/jura_solutions"),
])
def test_a_company_page_or_an_account_profile_is_a_page_url(conn, monkeypatch, platform, url):
    pw.social_config(monkeypatch, browser=(platform,), urls={platform: url})
    pw.at(monkeypatch, pw.TEN)
    made = items.create_social(conn, pw.draft(conn, platform), run_id=None)
    assert made.item is not None, made.why
