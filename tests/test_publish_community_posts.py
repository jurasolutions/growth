"""Community posts as the Jura Page at the publish commands (seam S7; dataset D10; ticket BP-05).

Rows traced: AC-P6.2 (a removal or an admin warning in a group also runs `community removed`),
and the post half of `publish done` and `publish resolve` for a community post: the live post's
own address inside its group, the `community_posts` row set to `posted` with `posted_via =
'browser'` (BP §5.6), and the live-text check. The clock is BP's default, Tue 2026-11-10.
"""

from __future__ import annotations

import json

import pytest

import publish_world as pw
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import approvals, db, pause
from jura_growth.agents.community import groups as community_groups


@pytest.fixture
def world(monkeypatch):
    pw.social_config(monkeypatch)
    pw.community_config(monkeypatch)
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
    pw.at(monkeypatch, pw.TEN)


def next_json() -> dict:
    result = pw.invoke("publish", "next", "--json")
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def group_of(conn, group_id: int) -> dict:
    found = community_groups.get(conn, group_id)
    assert found is not None, group_id
    return found


def post_row(conn, post_id: int) -> dict:
    found = db.one(conn, "SELECT * FROM community_posts WHERE id = ?", (post_id,))
    assert found is not None, post_id
    return found


def claimed_post(conn, monkeypatch, group_id: int | None = None):
    """An approved community post in a group joined as the Page, claimed by a publish run."""
    found, request = pw.community_item(conn, group_id)
    assert pw.decide(conn, request, monkeypatch=monkeypatch).answer == "recorded"
    run = pw.run(conn, monkeypatch=monkeypatch)
    handed = next_json()
    assert handed["approval"] == request.id and handed["step"] == "community post", handed
    return found, request, run


# --- AC-P6.2 a removal or an admin warning in a group -----------------------------------------------


@pytest.mark.parametrize("reason", ["admin-warning", "removed"])
def test_a_removal_or_admin_warning_in_a_group_also_removes_the_group(conn, world, monkeypatch, discord_double, reason):
    group_id = pw.group(conn)
    found, request, run = claimed_post(conn, monkeypatch, group_id)
    later = pw.planned(conn, group_id, day=pw.DAY.replace(day=24))

    result = pw.invoke("publish", "stopped", request.id, "--reason", reason)

    assert result.exit_code == 0, result.output
    assert pw.item_row(conn, found.id)["state"] == "stopped"
    assert pause.is_paused(conn, "publish")
    group = group_of(conn, group_id)
    assert group["removed"] == 1 and group["fit"] == "skip"  # skipped for good, as `community removed` does
    assert post_row(conn, later)["status"] == "skipped"
    [alert] = [c for c in discord_double.contents("alerts") if request.id in c]
    assert f"Group {group_id} is now skipped for good" in alert
    assert db.scalar(conn, "SELECT count(*) FROM events WHERE kind = 'community.group.removed' AND run_id = ?",
                     (run,)) == 1


def test_a_removed_group_stays_skipped_and_its_waiting_cards_are_superseded(conn, world, monkeypatch):
    group_id = pw.group(conn)
    _, request, _ = claimed_post(conn, monkeypatch, group_id)
    _, waiting = pw.community_item(conn, group_id, day=pw.DAY.replace(day=24))

    pw.invoke("publish", "stopped", request.id, "--reason", "admin-warning")

    record = approvals.get(conn, waiting.id)
    assert record is not None and record.status == approvals.SUPERSEDED
    result = pw.invoke("community", "set", str(group_id), "fit=good fit")
    assert result.exit_code != 0 and "stays skip" in result.output


@pytest.mark.parametrize("reason", ["login", "wrong-identity", "rate-limit", "unidentified"])
def test_other_stops_in_a_group_leave_the_group_as_it_was(conn, world, monkeypatch, reason):
    group_id = pw.group(conn)
    _, request, _ = claimed_post(conn, monkeypatch, group_id)

    pw.invoke("publish", "stopped", request.id, "--reason", reason)

    group = group_of(conn, group_id)
    assert group["removed"] == 0 and group["fit"] == "good fit"


def test_a_removal_on_the_page_itself_removes_no_group(conn, world, monkeypatch):
    group_id = pw.group(conn)
    _, request = pw.approved(conn, monkeypatch)
    pw.run(conn, monkeypatch=monkeypatch)
    assert next_json()["approval"] == request.id

    result = pw.invoke("publish", "stopped", request.id, "--reason", "removed")

    assert result.exit_code == 0, result.output
    assert group_of(conn, group_id)["removed"] == 0


# --- the post's own address and its live text (BP §5.6, §5.7; AC-P7.1 to AC-P7.3 for a group post) ----------


def own_post(conn, group_id: int, number: str = "1234567890") -> str:
    return f"{group_of(conn, group_id)['url']}/posts/{number}/"


def done(request, url: str, live: str, tmp_path):
    path = tmp_path / f"{request.id}-live.txt"
    path.write_text(live, encoding="utf-8")
    return pw.invoke("publish", "done", request.id, "--url", url, "--live-text-file", str(path))


def test_publish_done_records_a_group_post_and_marks_the_planned_post_posted(conn, world, monkeypatch, tmp_path,
                                                                              discord_double):
    group_id = pw.group(conn)
    found, request, run = claimed_post(conn, monkeypatch, group_id)
    url = own_post(conn, group_id)

    result = done(request, url, pw.GROUP_TEXT, tmp_path)

    assert result.exit_code == 0, result.output
    row = pw.item_row(conn, found.id)
    assert (row["state"], row["outcome"], row["post_url"], row["live_text_matches"]) == ("done", "posted", url, 1)
    post = post_row(conn, found.ref_id)
    assert (post["status"], post["posted_url"], post["posted_via"]) == ("posted", url, "browser")
    assert post["posted_at"].startswith("2026-11-10")
    assert group_of(conn, group_id)["last_posted_at"] == "2026-11-10"
    record = approvals.get(conn, request.id)
    assert record is not None and record.used_by_run == run
    assert not pause.is_paused(conn, "publish") and discord_double.contents("alerts") == []


def test_the_permalink_form_of_a_group_post_is_its_own_address_too(conn, world, monkeypatch, tmp_path):
    group_id = pw.group(conn)
    _, request, _ = claimed_post(conn, monkeypatch, group_id)

    result = done(request, f"{group_of(conn, group_id)['url']}/permalink/987654321/?__cft__=x", pw.GROUP_TEXT, tmp_path)

    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("where", [
    "another group's post", "the group's own address", "the page timeline", "a page post", "a look-alike host",
    "a dot segment", "no post number", "a longer group name",
])
def test_publish_done_refuses_any_address_that_isnt_a_post_inside_the_items_own_group(
        conn, world, monkeypatch, tmp_path, where):
    group_id = pw.group(conn)
    other = pw.group(conn)
    found, request, _ = claimed_post(conn, monkeypatch, group_id)
    own = group_of(conn, group_id)["url"]
    url = {
        "another group's post": own_post(conn, other),
        "the group's own address": own,
        "the page timeline": pw.PAGE_URL,
        "a page post": f"{pw.PAGE_URL}/posts/123456789",
        "a look-alike host": own.replace("www.facebook.com", "www.facebook.com.evil.test") + "/posts/1/",
        "a dot segment": f"{own}/../{group_of(conn, other)['url'].rsplit('/', 1)[1]}/posts/1/",
        "no post number": f"{own}/posts/",
        "a longer group name": f"{own}0/posts/1/",
    }[where]

    result = done(request, url, pw.GROUP_TEXT, tmp_path)

    assert result.exit_code == 1, result.output
    assert "refused" in result.output
    assert pw.item_row(conn, found.id)["state"] == "claimed"
    assert post_row(conn, found.ref_id)["status"] == "planned"


def test_live_text_that_differs_from_the_approved_post_alerts_and_pauses(conn, world, monkeypatch, tmp_path,
                                                                        discord_double):
    group_id = pw.group(conn)
    found, request, _ = claimed_post(conn, monkeypatch, group_id)

    result = done(request, own_post(conn, group_id), pw.GROUP_TEXT + " Call 9123 4567.", tmp_path)

    assert result.exit_code == 0, result.output
    assert pw.item_row(conn, found.id)["live_text_matches"] == 0
    assert post_row(conn, found.ref_id)["status"] == "posted"  # it is live, whatever it says
    assert pause.is_paused(conn, "publish")
    [alert] = [c for c in discord_double.contents("alerts") if request.id in c]
    assert "doesn't match" in alert and "9123" not in alert


# --- AC-P10.1 and AC-P10.2 for a group post: Ting Yu settles an unknown one --------------------------------


def unknown_post(conn, monkeypatch, group_id: int):
    found, request, _ = claimed_post(conn, monkeypatch, group_id)
    conn.execute("UPDATE publish_items SET state = 'unknown' WHERE id = ?", (found.id,))  # as `after_run` leaves it
    monkeypatch.delenv("JURA_GROWTH_RUN_ID")  # Ting Yu, not a run
    return found, request


def test_ting_yu_settles_an_unknown_group_post_as_posted_with_its_own_address(conn, world, monkeypatch):
    group_id = pw.group(conn)
    found, request = unknown_post(conn, monkeypatch, group_id)
    url = own_post(conn, group_id)

    result = pw.invoke("publish", "resolve", request.id, "posted", "--url", url)

    assert result.exit_code == 0, result.output
    row = pw.item_row(conn, found.id)
    assert (row["state"], row["outcome"], row["post_url"]) == ("done", "posted", url)
    post = post_row(conn, found.ref_id)
    assert (post["status"], post["posted_url"], post["posted_via"]) == ("posted", url, "browser")


def test_settling_a_group_post_refuses_an_address_outside_its_group(conn, world, monkeypatch):
    group_id = pw.group(conn)
    found, request = unknown_post(conn, monkeypatch, group_id)

    result = pw.invoke("publish", "resolve", request.id, "posted", "--url", own_post(conn, pw.group(conn)))

    assert result.exit_code == 1 and "refused" in result.output
    assert pw.item_row(conn, found.id)["state"] == "unknown"
