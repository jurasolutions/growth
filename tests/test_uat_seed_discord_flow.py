"""The Discord flow's harness items (`.scratch/approvals-first-social-depth/reviews/uat.md`, H1 to H7).

Ting Yu rehearses approvals first on the fixture, with no live post and no Dispatch UAT key. These
cases run each scenario he types at the seed's own seam, `seed.seed` and `seed.main`, with the
Discord double listening where a card or a feed line is the point.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

import site_repo
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import approvals, config, db, health, mission, paths
from jura_growth.agents.apps import prd
from jura_growth.agents.social import checks, linkcheck, render
from jura_growth.cli import cli
from test_social import fake_png
from uat import seed

TUESDAY = "2026-11-10"
SATURDAY = date(2026, 11, 14)
FIXTURE = "http://publish-fixture.localhost:8765"
SAMPLE = Path(seed.__file__).parent / "social-day"


@pytest.fixture
def uat(tmp_path, monkeypatch):
    """The `uat.md` window: every folder under one temp folder, the clock at Tue 10 Nov, 10:00."""
    folder = tmp_path / "uat"
    folder.mkdir()
    for variable, name in (("JURA_GROWTH_DATA_DIR", "data"), ("JURA_GROWTH_OUTPUTS_DIR", "outputs"), ("JURA_PRD_DIR", "prd"),
                           ("JURA_GROWTH_CONFIG_DIR", "config")):
        monkeypatch.setenv(variable, str(folder / name))
    monkeypatch.setenv("JURA_GROWTH_NOW", f"{TUESDAY}T10:00:00+08:00")
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", "111")
    config.reset_caches()
    return folder


def uat_settings(folder) -> dict:
    return yaml.safe_load((folder / "config" / "settings.yaml").read_text())


# --- H7: a plain webhook can't carry buttons ------------------------------------------------------


def test_the_uat_config_copy_turns_the_buttons_off_and_the_repos_keeps_them(uat):
    seed.seed(uat)
    assert uat_settings(uat)["approvals"]["post_buttons"] is False
    shipped = yaml.safe_load((paths.REPO_ROOT / "config" / "settings.yaml").read_text())
    assert shipped["approvals"]["post_buttons"] is True


@pytest.fixture
def stub_chrome(monkeypatch):
    """Pictures of the right size with no Chrome; the real render is its own case below."""

    def screenshot(page, out, width, height, *, settings=None, offline=False):
        out = paths.writable(Path(out))
        fake_png(out, width, height)
        return out

    monkeypatch.setattr(render, "screenshot", screenshot)
    monkeypatch.setattr(render, "fonts_loaded", lambda page, settings=None: list(render.EXPECTED_FONTS))


def card_for(double, platform_label: str) -> str:
    """Every piece of the platform's card, joined: a long card splits over two messages."""
    posts = double.contents("approvals")
    [start] = [index for index, text in enumerate(posts) if platform_label in text.split("\n")[0] + text.split("\n")[1]]
    following = [text for text in posts[start + 1:] if not text.startswith("**A-")]
    return "\n".join([posts[start], *following[:1]])


# --- H1: a pending two-platform day, through the real `social submit` ------------------------------


def test_the_sample_is_the_longest_post_each_platform_takes():
    assert checks.word_count((SAMPLE / "facebook.md").read_text()) == 280
    assert checks.word_count((SAMPLE / "instagram.md").read_text()) == 240


def test_social_day_raises_two_pending_cards_through_the_real_submit(discord_double, uat, stub_chrome):
    seed.seed(uat, scenario="social-day")
    with db.session() as conn:
        requests = db.rows(conn, "SELECT kind, status, decide_by FROM approvals ORDER BY id")
        assert [(r["kind"], r["status"]) for r in requests] == [("social-post", "pending")] * 2
        assert {r["decide_by"] for r in requests} == {f"{TUESDAY}T17:00:00+08:00"}
        posts = db.rows(conn, "SELECT platform, theme FROM social_posts ORDER BY platform")
        assert posts == [{"platform": "facebook", "theme": "ai-news"}, {"platform": "instagram", "theme": "ai-news"}]
        assert db.scalar(conn, "SELECT count(*) FROM social_submissions") == 1  # submit's own record
    assert discord_double.posts("social-drafts") == []
    assert not any(post.components for post in discord_double.posts("approvals"))  # H7


def test_each_card_shows_the_post_exactly_with_its_sources_and_pictures_in_order(discord_double, uat, stub_chrome):
    seed.seed(uat, scenario="social-day")
    for label, sample in (("Facebook Page", "facebook.md"), ("Instagram", "instagram.md")):
        card = card_for(discord_double, label)
        for paragraph in (SAMPLE / sample).read_text().strip().split("\n\n"):
            assert paragraph in card  # word for word, so nothing on it was masked
        assert card.count("```") % 2 == 0
    assert "https://www.example.com/press/invoice-reader" in card_for(discord_double, "Instagram")  # its sources
    assert "https://news.example.org/ai/invoice-reader-review" in card_for(discord_double, "Instagram")
    files = [name for post in discord_double.posts("approvals") for name, _ in post.files]
    assert files == ["facebook-1200x630.png", *[f"instagram-{n}-of-4-1080x1350.png" for n in (1, 2, 3, 4)]]


def test_the_sample_is_dated_the_day_it_is_seeded_so_a_news_theme_takes_it(uat, stub_chrome):
    seed.seed(uat, scenario="social-day")
    sources = (uat / "outputs" / "social" / TUESDAY / "sources.md").read_text()
    assert sources.count(TUESDAY) == 2 and "{today}" not in sources


def test_the_links_are_never_fetched(uat, stub_chrome, monkeypatch):
    def refuse(urls, client=None):
        raise AssertionError("a UAT seed fetched a source link")

    monkeypatch.setattr(linkcheck, "check_all", refuse)
    seed.seed(uat, scenario="social-day")
    assert yaml.safe_load((uat / "config" / "social.yaml").read_text())["verify_links"] is False


def test_with_the_fixture_on_the_pages_are_the_fixture_composers(uat, stub_chrome, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_PUBLISH_FIXTURE_URL", FIXTURE)
    seed.seed(uat, scenario="social-day")
    with db.session() as conn:
        targets = [r["target_url"] for r in db.rows(conn, "SELECT target_url FROM publish_items ORDER BY platform")]
    assert targets == [f"{FIXTURE}/page.html", f"{FIXTURE}/instagram.html"]


def test_without_the_fixture_the_pages_are_still_never_the_real_ones(uat, stub_chrome):
    seed.seed(uat, scenario="social-day")
    with db.session() as conn:
        targets = {r["target_url"] for r in db.rows(conn, "SELECT target_url FROM publish_items")}
    shipped = yaml.safe_load((paths.REPO_ROOT / "config" / "social.yaml").read_text())["platforms"]
    assert len(targets) == 2
    assert not targets & {shipped["facebook"]["page_url"], shipped["instagram"]["page_url"]}


def test_a_day_seeded_after_base_still_gets_both_cards(discord_double, uat, stub_chrome):
    """`base` holds a named contact's address, and the masking layer learns names from addresses."""
    seed.seed(uat)
    seed.seed(uat, scenario="social-day")
    assert len([text for text in discord_double.contents("approvals") if text.startswith("**A-")]) == 2


def test_s10_facebook_set_to_draft_mode_stays_in_draft_mode(discord_double, uat, stub_chrome):
    seed.seed(uat)
    social = uat / "config" / "social.yaml"
    data = yaml.safe_load(social.read_text())
    data["platforms"]["facebook"]["publish_mode"] = "draft"
    social.write_text(yaml.safe_dump(data))
    seed.seed(uat, scenario="social-day")
    assert any("post it by hand" in text for text in discord_double.contents("social-drafts"))
    with db.session() as conn:
        assert [r["platform"] for r in db.rows(conn, "SELECT platform FROM publish_items")] == ["instagram"]


def test_a_theme_the_sample_doesnt_fit_is_refused_with_submits_reason(uat, stub_chrome):
    with pytest.raises(seed.Refused, match="layout"):
        seed.seed(uat, scenario="social-day", theme="ai-this-week")


def test_the_theme_comes_from_the_command_line(uat, stub_chrome, capsys):
    assert seed.main([str(uat), "--scenario", "social-day", "--theme", "ai-finding", "--today", TUESDAY]) == 0
    assert "Approval requested: instagram as A-" in capsys.readouterr().out
    with db.session() as conn:
        assert {r["theme"] for r in db.rows(conn, "SELECT theme FROM social_posts")} == {"ai-finding"}


def test_social_day_needs_the_uat_config_folder_and_leaves_the_repos_alone(uat, stub_chrome, monkeypatch):
    monkeypatch.delenv("JURA_GROWTH_CONFIG_DIR")
    with pytest.raises(seed.Refused, match="JURA_GROWTH_CONFIG_DIR"):
        seed.seed(uat, scenario="social-day")


def test_a_seeded_day_other_than_the_clocks_is_refused(uat, stub_chrome):
    """`social submit` dates its rows from the clock, so `--today` can't move them."""
    with pytest.raises(seed.Refused, match="JURA_GROWTH_NOW"):
        seed.seed(uat, scenario="social-day", today=date(2026, 11, 11))


def test_social_day_renders_real_pictures(uat):
    """Real Chrome, offline, as `test_social_cards_real_chrome.py` runs it: no skip."""
    seed.seed(uat, scenario="social-day", offline=True)
    folder = uat / "outputs" / "social" / TUESDAY
    assert render.png_size(folder / "facebook-1200x630.png") == (1200, 630)
    slides = sorted(folder.glob("instagram-*-of-4-1080x1350.png"))
    assert len(slides) == 4 and {render.png_size(slide) for slide in slides} == {(1080, 1350)}
    assert all(slide.stat().st_size > 10_000 for slide in slides)  # a page, not an empty frame


# --- H2: a decision through the code Dispatch reaches, with no Dispatch UAT key --------------------


def request_ids(kind: str = "social-post") -> list[str]:
    with db.session() as conn:
        return [approvals.format_id(r["id"]) for r in db.rows(conn, "SELECT id FROM approvals WHERE kind = ? ORDER BY id", (kind,))]


def status_of(approval_id: str) -> str:
    with db.session() as conn:
        return approvals.get(conn, approval_id).status


def test_decide_approves_edits_the_card_and_posts_the_feed_line(discord_double, uat, stub_chrome, capsys):
    seed.seed(uat, scenario="social-day")
    facebook, instagram = request_ids()
    assert seed.main([str(uat), "--scenario", "decide", "--approval", facebook, "--decision", "approve"]) == 0
    assert capsys.readouterr().out.startswith(f"{facebook} approved.")
    assert status_of(facebook) == "approved" and status_of(instagram) == "pending"
    with db.session() as conn:
        assert approvals.get(conn, facebook).decided_by == "discord:111"
        assert approvals.get(conn, facebook).decided_origin == "ssh"
    [line] = discord_double.contents("social-drafts")
    assert line.startswith(f"**{facebook} approved** · ")
    assert "by 18:00 SGT" in line


def test_decide_skips_and_the_other_card_stays(discord_double, uat, stub_chrome, capsys):
    seed.seed(uat, scenario="social-day")
    facebook, instagram = request_ids()
    assert seed.main([str(uat), "--scenario", "decide", "--approval", facebook, "--decision", "skip"]) == 0
    assert f"{facebook} skipped." in capsys.readouterr().out
    assert status_of(facebook) == "skipped" and status_of(instagram) == "pending"
    [line] = discord_double.contents("social-drafts")
    assert line.startswith(f"**{facebook} skipped** · ")


def test_s6_a_tap_after_the_deadline_answers_expired_and_says_nothing_will_post(discord_double, uat, stub_chrome, monkeypatch, capsys):
    seed.seed(uat, scenario="social-day")
    facebook, _ = request_ids()
    monkeypatch.setenv("JURA_GROWTH_NOW", f"{TUESDAY}T17:01:00+08:00")
    assert seed.main([str(uat), "--scenario", "decide", "--approval", facebook, "--decision", "approve"]) == 0
    answer = capsys.readouterr().out
    assert "expired" in answer and "approved." not in answer
    assert status_of(facebook) == "expired"
    assert not any("goes out" in text for text in discord_double.contents("social-drafts"))


def test_s5_unanswered_cards_expire_at_the_digest_with_a_line_each(discord_double, uat, stub_chrome, monkeypatch):
    seed.seed(uat, scenario="social-day")
    facebook, instagram = request_ids()
    monkeypatch.setenv("JURA_GROWTH_NOW", f"{TUESDAY}T18:05:00+08:00")
    assert CliRunner().invoke(cli, ["digest"]).exit_code == 0
    assert status_of(facebook) == "expired" and status_of(instagram) == "expired"
    assert "Publishing: 0 posted, 0 skipped, 2 expired" in discord_double.contents("daily-digest")[0]
    lines = discord_double.contents("social-drafts")
    assert [line.split(" · ")[0] for line in lines] == [f"**{facebook} expired**", f"**{instagram} expired**"]
    assert all(line.endswith("\nNot approved in time.") for line in lines)
    edits = [r.content or "" for r in discord_double.requests if r.method == "PATCH" and r.channel == "approvals"]
    assert sum("Expired: not approved in time" in edit for edit in edits) == 2


def test_s8_a_paused_publish_is_named_on_the_feed_line(discord_double, uat, stub_chrome):
    seed.seed(uat, scenario="social-day")
    facebook, _ = request_ids()
    assert CliRunner().invoke(cli, ["pause", "publish"]).exit_code == 0
    seed.seed(uat, scenario="decide", approval=facebook, decision="approve")
    assert discord_double.contents("social-drafts")[-1].endswith("Publishing is paused, so nothing goes out until you resume it.")


def test_s2_a_card_edits_to_say_who_approved_it(discord_double, uat, stub_chrome):
    seed.seed(uat, scenario="social-day")
    facebook, _ = request_ids()
    seed.seed(uat, scenario="decide", approval=facebook, decision="approve")
    [edit, *_] = [r.content or "" for r in discord_double.requests if r.method == "PATCH" and r.channel == "approvals"]
    assert edit.startswith(f"**{facebook} · social post** · Approved by Ting Yu, 10:00 SGT")


@pytest.mark.parametrize("given, why", [({"decision": "approve"}, "--approval"), ({"approval": "A-0001"}, "--decision"),
                                        ({"approval": "A-0001", "decision": "maybe"}, "approve or skip")])
def test_decide_says_what_it_is_missing(uat, given, why):
    with pytest.raises(seed.Refused, match=why):
        seed.seed(uat, scenario="decide", **given)


def test_decide_needs_the_control_user_so_the_answer_can_be_attributed(uat, stub_chrome, monkeypatch):
    seed.seed(uat, scenario="social-day")
    facebook, _ = request_ids()
    monkeypatch.delenv("CONTROL_DISCORD_USER_ID")
    with pytest.raises(seed.Refused, match="CONTROL_DISCORD_USER_ID"):
        seed.seed(uat, scenario="decide", approval=facebook, decision="approve")
    assert status_of(facebook) == "pending"


def test_decide_answers_for_an_id_that_isnt_there(uat, capsys):
    seed.seed(uat)
    assert seed.main([str(uat), "--scenario", "decide", "--approval", "A-9999", "--decision", "skip"]) == 0
    assert "There is no approval request A-9999" in capsys.readouterr().out


def test_decide_refuses_a_folder_that_isnt_temporary():
    live = paths.JURA_ROOT / "data" / "growth"
    with pytest.raises(seed.Refused, match="temporary"):
        seed.seed(live, scenario="decide", approval="A-0001", decision="approve")


# --- H3 and H4: an app PRD and its build ------------------------------------------------------------


def test_app_prd_files_a_factory_prd_and_raises_its_card_with_the_prd_attached(discord_double, uat, capsys):
    assert seed.main([str(uat), "--scenario", "app-prd", "--today", TUESDAY]) == 0
    assert capsys.readouterr().out == "A-0001: APP-101 Birch delivery order maker\n"  # the A-id to decide
    [path] = (uat / "prd" / "pending" / "apps").glob(f"prd-app-*-{TUESDAY}.md")
    assert prd.validate_shape(path.read_text(), strict=True) == []
    [approval] = request_ids("app-build")
    assert status_of(approval) == "pending"
    [card] = [post for post in discord_double.posts("approvals") if (post.content or "").startswith(f"**{approval} ")]
    assert [name for name, _ in card.files] == [path.name]


def test_each_app_prd_is_a_new_app_so_a_second_can_be_skipped_after_the_first_is_approved(uat):
    seed.seed(uat, scenario="app-prd")
    seed.seed(uat, scenario="app-prd")
    assert len(request_ids("app-build")) == 2
    assert len(list((uat / "prd" / "pending" / "apps").glob("prd-app-*.md"))) == 2


def test_app_prd_after_base_leaves_base_s_own_prd_alone(uat):
    seed.seed(uat)
    seed.seed(uat, scenario="app-prd")
    assert len(request_ids("app-build")) == 1
    assert len(list((uat / "prd" / "pending" / "apps").glob("prd-app-014-*.md"))) == 1


def test_a1_approving_an_app_prd_hands_it_to_dispatch_in_one_feed_line(discord_double, uat, capsys):
    seed.seed(uat, scenario="app-prd")
    [approval] = request_ids("app-build")
    seed.seed(uat, scenario="decide", approval=approval, decision="approve")
    [line] = discord_double.contents("app-factory")
    assert line.startswith(f"**{approval} approved** · APP-")
    assert "Handed to Dispatch" in line
    assert "open Claude Code" not in line
    with db.session() as conn:
        assert db.scalar(conn, "SELECT count(*) FROM app_builds WHERE status = 'handed_off'") == 1


def test_a2_skipping_an_app_prd_sets_it_aside(discord_double, uat):
    seed.seed(uat, scenario="app-prd")
    [approval] = request_ids("app-build")
    seed.seed(uat, scenario="decide", approval=approval, decision="skip")
    assert discord_double.contents("app-factory")[0].startswith(f"**{approval} skipped** · APP-")
    [path] = (uat / "prd" / "skipped" / "apps").glob("prd-app-*.md")
    assert path.read_text().startswith(f"Skipped by Ting Yu on {TUESDAY}")


@pytest.fixture
def site_inside(uat, monkeypatch):
    """The window's `JURA_SITE_REPO`, which `app-built` makes its stand-in repository in."""
    monkeypatch.setenv("JURA_SITE_REPO", str(uat / "site"))
    return uat / "site"


def test_app_built_raises_the_release_request_over_a_stand_in_commit(discord_double, uat, site_inside):
    seed.seed(uat, scenario="app-prd")
    [build] = request_ids("app-build")
    seed.seed(uat, scenario="decide", approval=build, decision="approve")
    seed.seed(uat, scenario="app-built")
    [release] = request_ids("app-release")
    assert status_of(release) == "pending"
    with db.session() as conn:
        row = db.one(conn, "SELECT * FROM app_builds")
    assert row["status"] == "built" and row["task_id"] == f"T-0{row['app_id'][4:]}"
    assert row["preview_url"].endswith(".landing-page-eq7.pages.dev")
    assert site_repo.git(site_inside, "rev-parse", row["branch"]) == row["head_sha"]
    assert site_repo.git(site_inside, "rev-parse", "main") != row["head_sha"]  # nothing is on main yet


def test_a3_approving_the_release_names_what_is_next(discord_double, uat, site_inside):
    seed.seed(uat, scenario="app-prd")
    [build] = request_ids("app-build")
    seed.seed(uat, scenario="decide", approval=build, decision="approve")
    seed.seed(uat, scenario="app-built")
    [release] = request_ids("app-release")
    seed.seed(uat, scenario="decide", approval=release, decision="approve")
    line = discord_double.contents("app-factory")[-1]
    assert line.startswith(f"**{release} approved** · ")
    assert "/growth apps release-plan APP-" in line


def test_app_built_takes_the_newest_handoff_or_the_app_named(uat, site_inside):
    for _ in range(2):
        seed.seed(uat, scenario="app-prd")
    first, second = request_ids("app-build")
    for approval in (first, second):
        seed.seed(uat, scenario="decide", approval=approval, decision="approve")
    with db.session() as conn:
        older, newer = (r["app_id"] for r in db.rows(conn, "SELECT app_id FROM app_builds ORDER BY id"))
    seed.seed(uat, scenario="app-built", app=older)
    seed.seed(uat, scenario="app-built")
    with db.session() as conn:
        assert {r["app_id"] for r in db.rows(conn, "SELECT app_id FROM app_builds WHERE status = 'built'")} == {older, newer}


def test_app_built_needs_a_handoff(uat, site_inside):
    with pytest.raises(seed.Refused, match="no build handed off"):
        seed.seed(uat, scenario="app-built")


def test_app_built_never_touches_a_site_repo_outside_the_uat_folder(uat, tmp_path, monkeypatch):
    seed.seed(uat, scenario="app-prd")
    [approval] = request_ids("app-build")
    seed.seed(uat, scenario="decide", approval=approval, decision="approve")
    monkeypatch.setenv("JURA_SITE_REPO", str(tmp_path / "elsewhere"))
    with pytest.raises(seed.Refused, match="JURA_SITE_REPO"):
        seed.seed(uat, scenario="app-built")
    assert not (tmp_path / "elsewhere").exists()
    monkeypatch.delenv("JURA_SITE_REPO")
    with pytest.raises(seed.Refused, match="JURA_SITE_REPO"):
        seed.seed(uat, scenario="app-built")


# --- H5: the schedule check's run rows (SC1) -----------------------------------------------------------


def needs_you() -> list[str]:
    return health.strip(mission.read(mission.Source.here(installed=lambda job: True)))


def test_drift_seeds_the_rows_that_flag_steady_drift_at_the_real_slots(uat):
    seed.seed(uat, scenario="drift")
    with db.session() as conn:
        social = db.rows(conn, "SELECT started_at FROM runs WHERE job = 'social' ORDER BY id DESC")
        pager = db.rows(conn, "SELECT started_at FROM runs WHERE job = 'one-pager' ORDER BY id DESC")
    assert [r["started_at"] for r in social] == ["2026-11-09T22:30:00+08:00", "2026-11-08T22:31:00+08:00"]
    assert [r["started_at"] for r in pager] == ["2026-11-09T00:00:00+08:00", "2026-11-08T00:00:00+08:00"]
    [line] = [item for item in needs_you() if "hours off" in item]
    assert "about 9 hours off" in line and "Restart the Mac once" in line


def test_late_wake_seeds_two_days_waking_at_the_same_time_and_says_nothing(uat):
    seed.seed(uat, scenario="late-wake")
    with db.session() as conn:
        rows = db.rows(conn, "SELECT job, started_at FROM runs ORDER BY id DESC")
    assert {r["job"] for r in rows} == {"social", "app-factory"} and len(rows) == 4
    assert {r["started_at"][11:16] for r in rows} == {"09:30"}
    assert not [item for item in needs_you() if "hours off" in item]


@pytest.mark.parametrize("scenario", ["drift", "late-wake"])
def test_the_schedule_rows_are_dated_back_from_the_seeded_day_on_a_saturday_too(uat, monkeypatch, scenario):
    monkeypatch.setenv("JURA_GROWTH_NOW", "2026-11-14T10:00:00+08:00")
    seed.seed(uat, scenario=scenario, today=SATURDAY)
    with db.session() as conn:
        days = {r["started_at"][:10] for r in db.rows(conn, "SELECT started_at FROM runs")}
    assert days == {"2026-11-13", "2026-11-12"}


# --- H6: social runs daily, so only outreach waits for a business day ------------------------------


@pytest.mark.parametrize("scenario", ["social-post", "community-plan"])
def test_a_saturday_is_fine_for_everything_but_outreach(uat, monkeypatch, scenario):
    monkeypatch.setenv("JURA_GROWTH_NOW", "2026-11-14T10:00:00+08:00")
    seed.seed(uat, today=SATURDAY)  # `base`, which Parts S, A and C start from
    seed.seed(uat, scenario=scenario, today=SATURDAY)
    with db.session() as conn:
        [request] = db.rows(conn, "SELECT status FROM approvals")
        assert request["status"] == "pending"


@pytest.mark.parametrize("scenario", ["outreach-live", "edit-draft", "shadow-trial"])
def test_the_outreach_scenarios_refuse_a_saturday_and_seed_nothing(uat, scenario):
    with pytest.raises(seed.Refused, match="weekend"):
        seed.seed(uat, scenario=scenario, today=SATURDAY, lead=233)
    assert not (uat / "data" / "growth.db").exists()
