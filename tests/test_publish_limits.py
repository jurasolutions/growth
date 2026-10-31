"""The publish limits (BP §4.4, AC-P5.4; test strategy v3 §4.2 row AC-P5.4, E7).

Every limit lives in `caps.py`. `config/publish.yaml` may tighten one, never loosen it: a count
may only go down, the gap between actions may only grow, and the posting window may only narrow.
"""

from __future__ import annotations

from datetime import time

import pytest

from jura_growth import caps, config
from jura_growth.agents.publish import limits


def configure(monkeypatch, **publish):
    real = config.agent_config

    def patched(agent):
        return dict(publish) if agent == "publish" else real(agent)

    monkeypatch.setattr(config, "agent_config", patched)


def test_the_hard_values_are_in_caps():
    assert caps.BROWSER_JOBS == frozenset({"publish", "inbox-watch", "inbox-reply"})
    assert caps.COMMUNITY_POSTS_PER_DAY == 1
    assert caps.COMMUNITY_JOINS_PER_WEEK == 3
    assert caps.PUBLISH_ITEMS_PER_RUN == 1
    assert caps.PUBLISH_MINUTES_BETWEEN_ACTIONS == 20
    assert caps.PUBLISH_WINDOW == ("09:00", "18:00")


def test_with_nothing_configured_the_hard_values_apply(monkeypatch):
    configure(monkeypatch)
    assert limits.window() == (time(9, 0), time(18, 0))
    assert limits.minutes_between_actions() == 20
    assert limits.items_per_run() == 1
    assert limits.community_posts_per_day() == 1
    assert limits.community_joins_per_week() == 3


@pytest.mark.parametrize(
    "name, looser, tighter, hard, tight",
    [
        ("items_per_run", 5, 0, 1, 0),
        ("community_posts_per_day", 4, 0, 1, 0),
        ("community_joins_per_week", 10, 2, 3, 2),
        ("minutes_between_actions", 5, 45, 20, 45),  # a floor: shorter is looser
    ],
)
def test_a_looser_value_gives_the_hard_one_and_a_tighter_one_is_honoured(monkeypatch, name, looser, tighter, hard, tight):
    configure(monkeypatch, **{name: looser})
    assert getattr(limits, name)() == hard
    configure(monkeypatch, **{name: tighter})
    assert getattr(limits, name)() == tight


def test_a_wider_window_gives_the_hard_window_and_a_narrower_one_is_honoured(monkeypatch):
    configure(monkeypatch, window={"start": "08:00", "end": "20:00"})
    assert limits.window() == (time(9, 0), time(18, 0))
    configure(monkeypatch, window={"start": "10:00", "end": "16:00"})
    assert limits.window() == (time(10, 0), time(16, 0))
    configure(monkeypatch, window={"start": "07:00", "end": "16:00"})
    assert limits.window() == (time(9, 0), time(16, 0))


@pytest.mark.parametrize("window", [{"start": "16:00", "end": "10:00"}, {"start": "ten", "end": "16:00"}, "09:00-18:00"])
def test_a_window_that_makes_no_sense_is_refused(monkeypatch, window):
    configure(monkeypatch, window=window)
    with pytest.raises(limits.LimitsError):
        limits.window()


def test_the_shipped_config_only_tightens(monkeypatch):
    """`config/publish.yaml` as committed reads as the hard values."""
    assert limits.window() == (time(9, 0), time(18, 0))
    assert limits.minutes_between_actions() == 20
    assert limits.items_per_run() == 1
