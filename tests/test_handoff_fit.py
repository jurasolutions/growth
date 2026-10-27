"""One limit, one measure and one policy for the build handoffs in an answer (code review 12, S1
and the standards finding). `apps handoffs --json` and `remote --json` both fit with
`handoff_fit.fit()`; the cases here are the policy, and `test_remote_apps.py` has it end to end.
"""

from __future__ import annotations

from jura_growth import handoff_fit, remote
from jura_growth.agents.apps import builds

LIMIT = handoff_fit.JSON_LIMIT


def entry(app_id: str, text_bytes: int) -> dict:
    return {"app_id": app_id, "approval": f"A-{app_id[-3:]}",
            "handoff": {"repo": "landing-page", "base": "main", "prd_text": "x" * text_bytes, "prd_sha256": "0" * 64}}


def plain(payload: dict) -> dict:
    return {"contract": 1, **payload}


def ids(fitted: dict) -> list[str]:
    return [e["app_id"] for e in fitted["handoffs"]]


def test_everything_that_fits_is_handed_out_oldest_first():
    fitted = handoff_fit.fit([entry("APP-101", 1000), entry("APP-102", 1000)], wrap=plain)
    assert ids(fitted) == ["APP-101", "APP-102"] and fitted["more"] == 0
    assert all(e["handoff"] for e in fitted["handoffs"])


def test_one_that_fits_alone_but_not_beside_earlier_ones_waits_for_a_later_poll():
    fitted = handoff_fit.fit([entry("APP-101", 40_000), entry("APP-102", 40_000), entry("APP-103", 100)], wrap=plain)
    assert ids(fitted) == ["APP-101", "APP-103"] and fitted["more"] == 1


def test_one_too_large_for_any_answer_is_named_with_its_problem_and_holds_nothing_up():
    """Probe p9: the oversized oldest handoff never stands in front of a newer one."""
    fitted = handoff_fit.fit([entry("APP-101", LIMIT), entry("APP-102", 100)], wrap=plain)
    assert ids(fitted) == ["APP-101", "APP-102"] and fitted["more"] == 0
    first, second = fitted["handoffs"]
    assert first["handoff"] is None and first["problem"] == handoff_fit.TOO_LARGE
    assert second["handoff"]["prd_text"] == "x" * 100


def test_one_too_large_behind_a_buildable_one_is_named_now_not_left_waiting():
    fitted = handoff_fit.fit([entry("APP-101", 1000), entry("APP-102", LIMIT)], wrap=plain)
    assert ids(fitted) == ["APP-101", "APP-102"] and fitted["handoffs"][1]["problem"] == handoff_fit.TOO_LARGE


def test_entries_without_a_handoff_count_as_staying_when_judging_too_large():
    """Problem entries never leave on their own, so a handoff that fits only without them is too large."""
    stuck = [{"app_id": f"APP-1{n:02d}", "handoff": None, "problem": "the PRD can't be read " + "z" * 2000} for n in range(10)]
    big = entry("APP-200", LIMIT - 10_000)
    assert handoff_fit.size(plain({"handoffs": [big], "more": 11})) <= LIMIT  # alone, it would fit
    fitted = handoff_fit.fit([*stuck, big], wrap=plain)
    assert fitted["handoffs"][-1]["app_id"] == "APP-200" and fitted["handoffs"][-1]["handoff"] is None
    assert fitted["more"] == 0


def test_more_carries_on_from_an_earlier_fit_and_the_answer_stays_within_the_limit():
    fitted = handoff_fit.fit([entry("APP-101", 50_000), entry("APP-102", 50_000)], wrap=plain, more=3)
    assert fitted["more"] == 4
    assert handoff_fit.size(plain(fitted)) <= LIMIT


def test_the_envelope_holds_remotes_answer_at_its_largest():
    """Text at its longest and each character at its widest once escaped, the longest answer."""
    inner = {"contract": 1, "handoffs": [], "more": 999}
    longest = max(remote.ANSWER_FOR_EXIT.values(), key=len)
    for char in ("\u0001", "\"", "\U0001F600", "x"):
        reply = remote.Reply(7, longest, char * remote.TEXT_LIMIT, handoff=inner)
        outer = len(remote.payload(reply).encode("utf-8"))
        assert outer - handoff_fit.size(inner) <= handoff_fit.ENVELOPE, char
    assert handoff_fit.HANDOFF_LIMIT == handoff_fit.JSON_LIMIT - handoff_fit.ENVELOPE


def test_the_plugin_and_remote_share_the_one_limit_and_the_one_problem_text():
    assert builds.JSON_LIMIT == remote.JSON_LIMIT == handoff_fit.JSON_LIMIT == 64 * 1024
    assert not hasattr(builds, "_size")
    assert "too large" in handoff_fit.TOO_LARGE
