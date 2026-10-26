"""Publish transcripts are kept 7 days, other jobs' 30 (BP §4.7, X5).

A publish transcript holds third-party page text, so the nightly backup prunes it sooner.
"""

from __future__ import annotations

from datetime import date, timedelta

from jura_growth import backup, paths


def transcript(day: date, name: str):
    path = paths.data_dir() / "transcripts" / day.isoformat() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n")
    return path


def test_publish_transcripts_go_after_7_days_and_the_rest_after_30(monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", "2026-11-30T23:30:00+08:00")
    today = date(2026, 11, 30)
    kept_publish = transcript(today - timedelta(days=7), "41-publish.jsonl")
    old_publish = transcript(today - timedelta(days=8), "40-publish.jsonl")
    social_same_day = transcript(today - timedelta(days=8), "39-social.jsonl")
    kept_social = transcript(today - timedelta(days=30), "20-social.jsonl")
    old_social = transcript(today - timedelta(days=31), "10-social.jsonl")

    backup.prune_transcripts()

    assert kept_publish.exists() and social_same_day.exists() and kept_social.exists()
    assert not old_publish.exists()
    assert not old_social.exists()


def test_config_may_shorten_publish_retention_but_never_lengthen_it(monkeypatch):
    from jura_growth import config

    monkeypatch.setenv("JURA_GROWTH_NOW", "2026-11-30T23:30:00+08:00")
    today = date(2026, 11, 30)
    base = config.settings()
    for days, survives in ((60, False), (3, False)):
        patched = {**base, "retention": {**base["retention"], "browser_transcripts_days": days}}
        monkeypatch.setattr(config, "settings", lambda patched=patched: patched)
        path = transcript(today - timedelta(days=8 if days == 60 else 4), "50-publish.jsonl")
        backup.prune_transcripts()
        assert path.exists() is survives, days
