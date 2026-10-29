"""One way to show a time in Discord (final code review St7).

Cards, the health strip, the one-pager and the publish items all show a moment as the cards
always have: `Tue 10 Nov, 16:30 SGT`.
"""

from datetime import datetime, timezone

from jura_growth import cards, health, timeutil


def test_a_time_shown_in_discord_reads_the_way_a_card_shows_it():
    assert timeutil.when(datetime(2026, 11, 10, 16, 30, tzinfo=timeutil.SGT)) == "Tue 10 Nov, 16:30 SGT"


def test_a_stored_stamp_or_a_time_in_another_zone_is_shown_in_sgt_without_a_leading_zero():
    assert timeutil.when("2026-11-03T08:30:00+00:00") == "Tue 3 Nov, 16:30 SGT"
    assert timeutil.when(datetime(2026, 11, 2, 23, 5, tzinfo=timezone.utc)) == "Tue 3 Nov, 07:05 SGT"


def test_cards_and_health_keep_no_formatter_of_their_own():
    for module, name in ((cards, "when"), (cards, "when_at"), (health, "when")):
        assert not hasattr(module, name), f"{module.__name__}.{name}"
