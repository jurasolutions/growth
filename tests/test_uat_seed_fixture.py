"""The rehearsal scenarios in the UAT harness (`uat.md` Part R, R1 to R6; BP-07).

`fixture-post --page <page>` seeds an approved Facebook item whose target is that fixture page,
and `fixture-join --page <page>` an approved join for a group whose address is that fixture page.
Both need the fixture platform switched on (`JURA_GROWTH_PUBLISH_FIXTURE_URL`), and the seed
refuses without it, or with one its guard refuses.
"""

from __future__ import annotations

import pytest
import yaml

from jura_growth import approvals, config, db
from jura_growth.agents.publish import claim
from uat import seed

FIXTURE = "http://publish-fixture.localhost:8765"


@pytest.fixture
def uat(tmp_path, monkeypatch):
    folder = tmp_path / "uat"
    folder.mkdir()
    for variable, name in (("JURA_GROWTH_DATA_DIR", "data"), ("JURA_GROWTH_OUTPUTS_DIR", "outputs"), ("JURA_PRD_DIR", "prd"),
                           ("JURA_GROWTH_CONFIG_DIR", "config")):
        monkeypatch.setenv(variable, str(folder / name))
    monkeypatch.setenv("JURA_GROWTH_NOW", "2026-11-10T10:00:00+08:00")
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", "111")
    monkeypatch.setenv("JURA_GROWTH_PUBLISH_FIXTURE_URL", FIXTURE)
    config.reset_caches()
    return folder


def test_iw_d4_fixture_reply_seeds_an_approved_reply_at_the_sites_own_thread_address(uat):
    from jura_growth.agents.inbox import reply_run, social

    seed.seed(uat, scenario="fixture-reply")
    with db.session() as conn:
        request = only_request(conn, social.KIND)
        assert request.status == "approved" and request.used_at is None
        [item] = reply_run.due(conn)
        assert item["target"] == f"{FIXTURE}/direct/t/1234567/"
        assert social.reply_of(item) is not None


def only_request(conn, kind: str) -> approvals.Approval:
    [row] = conn.execute("SELECT * FROM approvals WHERE kind = ?", (kind,)).fetchall()
    return approvals.Approval.from_row(row)


@pytest.mark.parametrize("page", ["page.html", "login.html", "link-out.html", "injection.html", "other-identity.html"])
def test_fixture_post_seeds_an_approved_item_on_that_fixture_page(uat, page):
    seed.seed(uat, scenario="fixture-post", page=page)
    social = yaml.safe_load((uat / "config" / "social.yaml").read_text())
    assert social["platforms"]["facebook"]["publish_mode"] == "browser"
    assert social["platforms"]["facebook"]["page_url"] == f"{FIXTURE}/{page}"
    with db.session() as conn:
        request = only_request(conn, "social-post")
        assert request.status == "approved" and request.used_at is None
        [item] = claim.claimable(conn)  # what the rehearsal's run will claim
        assert item.target_url == f"{FIXTURE}/{page}"


def test_fixture_post_defaults_to_the_composer(uat):
    seed.seed(uat, scenario="fixture-post")
    with db.session() as conn:
        [item] = claim.claimable(conn)
        assert item.target_url == f"{FIXTURE}/page.html"


@pytest.mark.parametrize("page", ["join.html", "profile-only-join.html"])
def test_fixture_join_seeds_an_approved_join_for_a_group_on_that_fixture_page(uat, page):
    seed.seed(uat, scenario="fixture-join", page=page)
    with db.session() as conn:
        request = only_request(conn, "group-join")
        assert request.status == "approved" and request.used_at is None
        [item] = claim.claimable(conn)
        assert item.target_url == f"{FIXTURE}/groups/{page.removesuffix('.html')}/"  # one group's own address


@pytest.mark.parametrize("scenario", ["fixture-post", "fixture-join"])
def test_the_rehearsal_scenarios_refuse_without_the_fixture(uat, monkeypatch, scenario):
    monkeypatch.delenv("JURA_GROWTH_PUBLISH_FIXTURE_URL")
    with pytest.raises(seed.Refused, match="JURA_GROWTH_PUBLISH_FIXTURE_URL"):
        seed.seed(uat, scenario=scenario)


def test_the_rehearsal_scenarios_refuse_a_fixture_the_guard_refuses(uat, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_PUBLISH_FIXTURE_URL", "http://publish-fixture.example:8765")
    with pytest.raises(seed.Refused, match="loopback"):
        seed.seed(uat, scenario="fixture-post")


@pytest.mark.parametrize("page", ["nope.html", "../README.md", "index.html", "https://www.facebook.com/x"])
def test_only_a_fixture_page_can_be_named(uat, page):
    with pytest.raises(seed.Refused, match="fixture page"):
        seed.seed(uat, scenario="fixture-post", page=page)


def test_the_command_line_takes_the_page(uat, capsys):
    assert seed.main([str(uat), "--scenario", "fixture-post", "--page", "captcha.html", "--today", "2026-11-10"]) == 0
    assert "seeded fixture-post" in capsys.readouterr().out
