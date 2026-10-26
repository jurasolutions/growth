"""The community scenario in the UAT harness (`uat.md` Part C, C3; X13; BP-02b).

`community-plan` turns `community.browser` on in the UAT config folder, records G4 as joined as
the Jura Page, and plans a G4 post for the seeded day that mentions Jura, raising its
`community-post` card through the code `community publish-plan` uses. It needs `base` first.
"""

from __future__ import annotations

import pytest
import yaml

from jura_growth import approvals, config, db
from jura_growth.agents.publish import claim
from jura_growth.origin import Origin
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


def decide(conn, approval, **args):
    return approvals.decide(conn, approval.id, "approve", actor="discord:111", origin=Origin.ssh(), source_ref=None, args=args)


def test_community_plan_seeds_a_g4_card_that_c3_then_refuses_at_publish_next(uat):
    seed.seed(uat, scenario="base")
    seed.seed(uat, scenario="community-plan")
    community = yaml.safe_load((uat / "config" / "community.yaml").read_text())
    assert community["browser"] is True
    with db.session() as conn:
        assert db.scalar(conn, "SELECT joined_as FROM community_groups WHERE id = 4") == "page"
        [request] = approvals.pending(conn, "community-post")
        assert request.decide_by == "2026-11-10T18:00:00+08:00"
        assert decide(conn, request).answer == "recorded"
        refused = claim.next_item(conn)
        assert refused.item is None and any("rules aren't confirmed" in why for why in refused.why)
    seed.seed(uat, scenario="note-rules", group=4)
    with db.session() as conn:
        [rules] = approvals.pending(conn, "group-rules")
        assert decide(conn, rules, promo_days="sat", post_days="any").answer == "recorded"
        refused = claim.next_item(conn)
        assert refused.item is None
        assert any("promotion only on sat" in why for why in refused.why), refused.why
        assert approvals.get(conn, request.id).used_at is None


def test_community_plan_needs_base_first(uat):
    with pytest.raises(seed.Refused, match="seed `base` first"):
        seed.seed(uat, scenario="community-plan")
