"""The social agent with LinkedIn switched off (Ting Yu, 2026-10-29: "drop the linkedin updates").

Jura no longer drafts for LinkedIn. The platform is switched off with `platforms.linkedin.enabled:
false` in `config/social.yaml`, not ripped out, so these tests check that a switched-off platform
gets no draft, no file, no image, no #social-drafts message, no setup cover and no place in the
digest or `social skip all`. Each has a twin, or a test in test_social.py, showing that a
switched-on platform still gets all of these. Publishing is in test_publish_linkedin_off.py.
"""

from __future__ import annotations

import json
from datetime import date

from click.testing import CliRunner

import publish_world as pw
from jura_growth import db, paths
from jura_growth.agents import social
from jura_growth.agents.social import plan, render, submit
from jura_growth.agents.social.settings import load
from jura_growth.cli import cli
from test_social import TIP, env, outbox, write  # noqa: F401 - env is a fixture

EVERY = ("linkedin", "facebook", "instagram")
WITHOUT_LINKEDIN = ("facebook", "instagram")
TUESDAY = date(2026, 10, 27)


def linkedin_off(monkeypatch):
    pw.social_config(monkeypatch, browser=(), enabled=WITHOUT_LINKEDIN)


def linkedin_on(monkeypatch):
    pw.social_config(monkeypatch, browser=(), enabled=EVERY)


# --- the shipped switch -----------------------------------------------------------------------


def test_the_shipped_config_turns_linkedin_off_and_keeps_facebook_and_instagram():
    settings = load()
    assert settings.platforms["linkedin"].enabled is False
    assert [p.name for p in settings.enabled_platforms()] == list(WITHOUT_LINKEDIN)


# --- the plan and the run's files ---------------------------------------------------------------


def test_the_plan_lists_only_the_enabled_platforms_and_their_files(env, conn, monkeypatch):
    linkedin_off(monkeypatch)
    built = plan.build(conn, TUESDAY)
    assert list(built["platforms"]) == list(WITHOUT_LINKEDIN)
    text = plan.render_text(built)
    assert "linkedin" not in text.lower()
    assert "  facebook.md  instagram.md  sources.md  card.json" in text.splitlines()


def test_the_plan_still_lists_linkedin_and_its_file_when_it_is_switched_on(env, conn, monkeypatch):
    linkedin_on(monkeypatch)
    text = plan.render_text(plan.build(conn, TUESDAY))
    assert "  linkedin.md  facebook.md  instagram.md  sources.md  card.json" in text.splitlines()


def test_the_plan_names_a_file_only_for_a_platform_still_to_draft(env, conn, monkeypatch):
    linkedin_off(monkeypatch)
    CliRunner().invoke(cli, ["social", "skip", "2026-10-27", "instagram"], catch_exceptions=False)
    text = plan.render_text(plan.build(conn, TUESDAY))
    assert "  facebook.md  sources.md  card.json" in text.splitlines()


def test_submit_drafts_renders_and_posts_nothing_for_linkedin(env, conn, monkeypatch):
    """A leftover linkedin.md in the folder is ignored: no row, no image, no output file and no
    #social-drafts message."""
    linkedin_off(monkeypatch)
    folder = write(paths.work_dir("social") / "2026-10-27", TIP)
    outcome = submit.submit(conn, folder, offline=True)
    assert outcome.status == "delivered", outcome.text()

    assert [r["platform"] for r in db.rows(conn, "SELECT platform FROM social_posts ORDER BY platform")] == \
        ["facebook", "instagram"]
    assert set(outcome.images) == set(WITHOUT_LINKEDIN)
    assert not [shot for shot, _ in env["shots"] if "linkedin" in shot.name]
    out = paths.outputs_dir() / "social" / "2026-10-27"
    assert not (out / "linkedin.md").exists()
    assert "linkedin" not in outcome.text().lower()
    posts = [m for m in outbox() if m["channel"] == "social-drafts"]
    assert len(posts) == 3  # Facebook, Instagram, then sources and the folder
    assert not [m for m in posts if "linkedin" in m["content"].lower()]


# --- images on their own --------------------------------------------------------------------------


def test_setup_images_render_no_linkedin_cover_while_it_is_off(env, monkeypatch, tmp_path):
    linkedin_off(monkeypatch)
    names = [path.name for path in render.render_setup(tmp_path / "setup", settings=load(), offline=True)]
    assert not [name for name in names if "linkedin" in name]
    assert "facebook-cover-1640x624.png" in names and "profile-1080x1080.png" in names


def test_setup_images_render_the_linkedin_cover_when_it_is_switched_on(env, monkeypatch, tmp_path):
    linkedin_on(monkeypatch)
    names = [path.name for path in render.render_setup(tmp_path / "setup", settings=load(), offline=True)]
    assert "linkedin-cover-1128x191.png" in names


def card_spec(tmp_path):
    spec = tmp_path / "card.json"
    spec.write_text(json.dumps({"layout": "headline", "headline": "Let your accounting software send the first reminder"}))
    return spec


def test_social_render_defaults_to_the_enabled_platforms_sizes(env, monkeypatch, tmp_path):
    linkedin_off(monkeypatch)
    result = CliRunner().invoke(cli, ["social", "render", str(card_spec(tmp_path)), "--out", str(tmp_path / "o"), "--offline"])
    assert result.exit_code == 0, result.output
    assert "linkedin" not in result.output
    assert "facebook-1200x630.png" in result.output and "instagram-1080x1350.png" in result.output


def test_social_render_still_renders_a_linkedin_size_when_asked_by_name(env, monkeypatch, tmp_path):
    linkedin_off(monkeypatch)
    result = CliRunner().invoke(
        cli, ["social", "render", str(card_spec(tmp_path)), "--out", str(tmp_path / "o"), "--size", "linkedin", "--offline"])
    assert result.exit_code == 0, result.output
    assert "linkedin-1200x627.png" in result.output


# --- what Ting Yu sees: the digest and `social skip all` ----------------------------------------


def test_the_digest_counts_no_linkedin_draft_while_it_is_off(env, conn, monkeypatch):
    linkedin_off(monkeypatch)
    for platform in EVERY:
        pw.draft(conn, platform, day=TUESDAY)
    found = social.digest(conn, "2026-10-27")
    assert found["figures"]["social_drafts_waiting"] == 2
    assert "linkedin" not in " ".join(found["lines"]).lower()


def test_skip_all_skips_only_the_enabled_platforms(env, conn, monkeypatch):
    linkedin_off(monkeypatch)
    result = CliRunner().invoke(cli, ["social", "skip", "2026-10-28", "all"], catch_exceptions=False)
    assert "linkedin" not in result.output
    assert sorted(r["platform"] for r in db.rows(conn, "SELECT platform FROM social_skips")) == ["facebook", "instagram"]


def test_skip_all_still_covers_linkedin_when_it_is_switched_on(env, conn, monkeypatch):
    linkedin_on(monkeypatch)
    CliRunner().invoke(cli, ["social", "skip", "2026-10-28", "all"], catch_exceptions=False)
    assert sorted(r["platform"] for r in db.rows(conn, "SELECT platform FROM social_skips")) == sorted(EVERY)
