"""The publish scenarios in the UAT harness (`uat.md` Part C; X13; BP-02a).

`social-post` seeds C1's pending Facebook card, `social-approved` C2's approved one, and
`claimed-not-closed` C2's unknown item. Each needs the UAT config folder inside the UAT folder,
where it puts Facebook in `browser` mode with a test page URL; it never touches the repo's config.
"""

from __future__ import annotations

import pytest
import yaml

from jura_growth import approvals, config, db, pause
from uat import seed


@pytest.fixture
def uat(tmp_path, monkeypatch):
    folder = tmp_path / "uat"
    folder.mkdir()
    for variable, name in (("JURA_GROWTH_DATA_DIR", "data"), ("JURA_GROWTH_OUTPUTS_DIR", "outputs"), ("JURA_PRD_DIR", "prd"),
                           ("JURA_GROWTH_CONFIG_DIR", "config")):
        monkeypatch.setenv(variable, str(folder / name))
    monkeypatch.setenv("JURA_GROWTH_NOW", "2026-11-10T10:00:00+08:00")
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", "111")
    config.reset_caches()
    return folder


def facebook_requests(conn) -> list[approvals.Approval]:
    return [approvals.Approval.from_row(r) for r in conn.execute("SELECT * FROM approvals WHERE kind = 'social-post'")]


def test_social_post_seeds_one_pending_facebook_card(uat):
    seed.seed(uat, scenario="social-post")
    social = yaml.safe_load((uat / "config" / "social.yaml").read_text())
    assert social["platforms"]["facebook"]["publish_mode"] == "browser"
    assert social["platforms"]["linkedin"]["publish_mode"] == "draft"
    with db.session() as conn:
        [request] = facebook_requests(conn)
        assert request.status == "pending" and request.decide_by == "2026-11-10T18:00:00+08:00"
        assert db.scalar(conn, "SELECT count(*) FROM publish_items") == 1


def test_social_approved_seeds_an_approved_unclaimed_card(uat):
    seed.seed(uat, scenario="social-approved")
    with db.session() as conn:
        [request] = facebook_requests(conn)
        assert request.status == "approved" and request.used_at is None


def test_claimed_not_closed_seeds_an_unknown_item_and_pauses_publish(uat):
    seed.seed(uat, scenario="claimed-not-closed")
    with db.session() as conn:
        assert db.scalar(conn, "SELECT state FROM publish_items") == "unknown"
        assert pause.is_paused(conn, "publish")


def test_a_publish_scenario_refuses_a_config_folder_outside_the_uat_folder(uat, monkeypatch):
    monkeypatch.delenv("JURA_GROWTH_CONFIG_DIR")
    with pytest.raises(seed.Refused, match="JURA_GROWTH_CONFIG_DIR"):
        seed.seed(uat, scenario="social-post")
    assert not (uat / "config").exists()
