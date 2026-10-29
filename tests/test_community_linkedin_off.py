"""No LinkedIn groups in the community register while LinkedIn is switched off (Ting Yu,
2026-10-29: "drop the linkedin updates").

The register is where Jura finds groups to join and post in, so a LinkedIn group is refused while
`platforms.linkedin.enabled` is false in `config/social.yaml`, the one switch for Jura on LinkedIn.
Groups already in the register stay as they are.
"""

from __future__ import annotations

import publish_world as pw
from jura_growth.agents.community import groups

LINKEDIN_GROUP = {
    "channel": "linkedin", "name": "Singapore SME owners", "url": "https://www.linkedin.com/groups/123456/",
    "audience": "SME owners", "size_hint": "not stated", "active_hint": "not stated",
    "promo_rules": "not stated in public sources", "fit": "possible", "fit_reason": "Broad SME audience.",
    "source_urls": ["https://www.example.com/sme-groups"],
}


def test_a_linkedin_group_is_refused_while_linkedin_is_off(monkeypatch):
    pw.social_config(monkeypatch, browser=(), enabled=("facebook", "instagram"))
    _, errors = groups.validate(dict(LINKEDIN_GROUP))
    assert any("LinkedIn" in error for error in errors), errors


def test_a_linkedin_group_is_accepted_when_linkedin_is_switched_on(monkeypatch):
    pw.social_config(monkeypatch, browser=(), enabled=("linkedin", "facebook", "instagram"))
    _, errors = groups.validate(dict(LINKEDIN_GROUP))
    assert errors == []


def test_other_channels_are_unaffected(monkeypatch):
    pw.social_config(monkeypatch, browser=(), enabled=("facebook", "instagram"))
    telegram = {**LINKEDIN_GROUP, "channel": "telegram", "url": "https://t.me/sgsmeowners"}
    _, errors = groups.validate(telegram)
    assert errors == []
