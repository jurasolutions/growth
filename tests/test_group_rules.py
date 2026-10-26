"""Confirming a group's rules is a `group-rules` approval (ticket MC-05; MC §5.7 `group-rules` row,
§5.1 "Group rules"; test strategy v3 §4.1 AC-M10.6, §4.3 X2 and X9, §5.2 G37 for this kind).

`community set … rules=` and `community set … rules_confirmed=yes` raise the request; nothing in
Terminal confirms rules or sets open days. Ting Yu decides in #approvals through Dispatch, typing the
days (`/growth approve A-nnnn promo_days=… post_days=…`), and the decision sets `rules_confirmed` and
both days fields through `groups.set_fields`. Decisions come only through Dispatch (ADR 0004 as
amended 2026-10-26), so these tests decide with `aw.dispatch()` and the control actor. The gate
matrix for the kind runs through `gate_adapter_group_rules.py`.
"""

import pytest
from discord_double import discord_double  # noqa: F401 - a fixture
from sweep import d2_secrets  # noqa: F401 - a fixture
from click.testing import CliRunner

import approval_world as aw
from jura_growth import approvals, db, timeutil
from jura_growth.agents.community import group_rules
from jura_growth.agents.community import groups as groups_mod
from jura_growth.cli import cli

RULES = "Promo posts on Saturdays only."
DAYS = {"promo_days": "sat,sun", "post_days": "any"}


def invoke(*args):
    return CliRunner().invoke(cli, list(args), catch_exceptions=False)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", aw.CONTROL_ID)
    aw.at(monkeypatch, aw.NOW)


def researched(conn, name="SG F&B owners", slug="sgfnb", rules=RULES) -> int:
    """A group the community run found by web search, its rules as public sources state them."""
    status, group_id, messages = groups_mod.add(conn, {
        "channel": "facebook", "name": name, "url": f"https://www.facebook.com/groups/{slug}",
        "audience": "Singapore SME owners", "promo_rules": rules, "fit": "good fit",
        "fit_reason": "Owners asking each other about admin.", "source_urls": [f"https://example.sg/groups#{slug}"],
    })
    assert status == "added", messages
    conn.commit()
    return group_id


def requests(conn, group_id=None) -> list[approvals.Approval]:
    found = conn.execute("SELECT id FROM approvals WHERE kind = 'group-rules' ORDER BY id").fetchall()
    out = [aw.get(conn, approvals.format_id(r["id"])) for r in found]
    return [a for a in out if group_id is None or a.subject == group_rules.subject(group_id)]


def confirmation(conn, group_id) -> tuple:
    row = groups_mod.get(conn, group_id)
    return row["rules_confirmed"], row["promo_days_confirmed"], row["post_days_confirmed"]


# --- X9: `rules_confirmed=yes` raises a request and decides nothing ----------------------------------


def test_rules_confirmed_yes_raises_a_request_and_confirms_nothing(conn):
    group_id = researched(conn)
    result = invoke("community", "set", str(group_id), "rules_confirmed=yes")
    assert result.exit_code == 0, result.output
    [request] = requests(conn, group_id)
    assert request.status == "pending" and request.kind == "group-rules"
    assert request.id in result.output and "decide it in #approvals with promo_days=… post_days=…" in result.output
    assert confirmation(conn, group_id) == (0, None, None)


def raised(conn, group_id=None) -> approvals.Approval:
    group_id = group_id or researched(conn)
    assert invoke("community", "set", str(group_id), "rules_confirmed=yes").exit_code == 0
    [request] = [a for a in requests(conn, group_id) if a.status == "pending"]
    return request


# --- AC-M10.6: the days are typed in the decision, through `remote` ----------------------------------


def test_approve_without_days_through_remote_is_refused_and_with_them_it_sets_the_days(conn):
    from test_remote import remote

    request = raised(conn)
    group_id = group_rules.group_id_of(request.subject)
    refused = remote(["approve", request.id], ref="m1:d1")
    assert refused.exit_code != 0
    assert "say the days: promo_days=… post_days=…" in refused.output
    assert aw.get(conn, request.id).status == "pending" and confirmation(conn, group_id) == (0, None, None)

    done = remote(["approve", request.id, "promo_days=sat,sun", "post_days=any"], ref="m2:d2")
    assert done.exit_code == 0, done.output
    assert aw.get(conn, request.id).status == "approved"
    assert confirmation(conn, group_id) == (1, "sat,sun", "any")
    [changed] = [e for e in aw.events(conn, "community.group.set") if e["id"] == group_id]
    assert changed["rules_confirmed"] == 1 and changed["promo_days_confirmed"] == "sat,sun"


def test_the_same_words_typed_in_terminal_are_refused_with_the_pointer(conn):
    request = raised(conn)
    result = invoke("approve", request.id, "promo_days=sat,sun", "post_days=any")
    assert result.exit_code == 2 and "#approvals" in result.output
    assert aw.get(conn, request.id).status == "pending"
    assert confirmation(conn, group_rules.group_id_of(request.subject)) == (0, None, None)


@pytest.mark.parametrize("args", [{}, {"promo_days": "sat"}, {"post_days": "any"}, {"promo_days": "", "post_days": "any"},
                                  {"promo_days": "funday", "post_days": "any"}, {"promo_days": "sat", "post_days": "most days"}])
def test_missing_or_unreadable_days_are_refused_and_nothing_is_recorded(conn, args):
    """G37 for group-rules: refused with the text, nothing recorded, no event."""
    request = raised(conn)
    answer = aw.approve(conn, request, args=args)
    assert answer.answer == "refused" and "say the days: promo_days=… post_days=…" in answer.text
    assert aw.get(conn, request.id).status == "pending"
    assert aw.events(conn, "approval.approved") == [] and aw.claims(conn) == 0
    assert confirmation(conn, group_rules.group_id_of(request.subject)) == (0, None, None)


def test_approving_applies_the_days_once_inside_the_decision_and_closes_the_request(conn):
    request = raised(conn)
    answer = aw.approve(conn, request, args={"promo_days": "Mon to Fri", "post_days": "none"})
    assert answer.answer == "recorded"
    record = aw.get(conn, request.id)
    assert record.used_at and record.decided_by == aw.CONTROL  # applied on decide: nothing claims it later
    assert confirmation(conn, group_rules.group_id_of(request.subject)) == (1, "mon,tue,wed,thu,fri", "none")
    again = aw.approve(conn, record, args=DAYS)
    assert again.answer == "already-used" and "applied" in again.text
    assert confirmation(conn, group_rules.group_id_of(request.subject)) == (1, "mon,tue,wed,thu,fri", "none")


# --- X9: what `community set` refuses, and what raises a request -------------------------------------


@pytest.mark.parametrize("pairs", [
    ["rules_confirmed=yes", "promo_days=sat", "post_days=any"],
    ["joined=yes", "rules_confirmed=yes", "promo_days=sat"],
    ["post_days=any"],
    ["promo_days=sat", "post_days=any", "notes=read the rules"],
])
def test_days_given_in_community_set_are_refused_with_the_pointer_and_nothing_changes(conn, pairs):
    group_id = researched(conn)
    before = groups_mod.get(conn, group_id)
    result = invoke("community", "set", str(group_id), *pairs)
    assert result.exit_code != 0
    assert "decide it in #approvals with promo_days=… post_days=…" in result.output
    assert groups_mod.get(conn, group_id) == before and requests(conn) == []


def test_the_pointer_names_the_request_already_waiting(conn):
    request = raised(conn)
    result = invoke("community", "set", str(group_rules.group_id_of(request.subject)), "promo_days=sat", "post_days=any")
    assert result.exit_code != 0 and f"decide {request.id} in #approvals" in result.output


@pytest.mark.parametrize("rules", ["", None])
def test_rules_confirmed_yes_without_rules_text_is_refused(conn, rules):
    group_id = researched(conn)
    conn.execute("UPDATE community_groups SET promo_rules = ? WHERE id = ?", (rules, group_id))
    conn.commit()
    result = invoke("community", "set", str(group_id), "joined=yes", "rules_confirmed=yes")
    assert result.exit_code != 0 and f"set the rules first: community set {group_id} rules=…" in result.output
    assert requests(conn) == [] and groups_mod.get(conn, group_id)["joined"] == 0


def test_rules_text_and_the_confirmation_in_one_command_raise_one_request_over_the_new_text(conn):
    group_id = researched(conn, rules="not stated in public sources")
    result = invoke("community", "set", str(group_id), "joined=yes", f"rules={RULES}", "rules_confirmed=yes")
    assert result.exit_code == 0, result.output
    [request] = requests(conn, group_id)
    assert request.content_hash == approvals.content_hash(group_rules.GroupRules().content(conn, request.subject))
    assert b"Saturdays" in group_rules.GroupRules().content(conn, request.subject)
    row = groups_mod.get(conn, group_id)
    assert row["joined"] == 1 and row["promo_rules"] == RULES and row["rules_confirmed"] == 0


def test_rules_set_by_ting_yu_raise_a_request(conn):
    group_id = researched(conn, rules="not stated in public sources")
    result = invoke("community", "set", str(group_id), f"rules={RULES}")
    assert result.exit_code == 0, result.output
    [request] = requests(conn, group_id)
    assert request.status == "pending" and request.id in result.output
    assert confirmation(conn, group_id) == (0, None, None)


def test_researched_rules_never_raise_a_request(conn, tmp_path):
    import json

    file = tmp_path / "groups.json"
    file.write_text(json.dumps([{
        "channel": "facebook", "name": "SG cafe owners", "url": "https://www.facebook.com/groups/sgcafe",
        "promo_rules": RULES, "fit": "good fit", "fit_reason": "Owners asking about admin.",
        "source_urls": ["https://example.sg/groups#sgcafe"],
    }]))
    assert invoke("community", "add-group", "--file", str(file)).exit_code == 0
    researched(conn, name="SG florists", slug="sgflorists")
    assert invoke("community", "set", "1", "joined=yes", "notes=joined today").exit_code == 0
    assert requests(conn) == []


def test_a_second_confirmation_returns_the_request_already_waiting(conn):
    first = raised(conn)
    group_id = group_rules.group_id_of(first.subject)
    again = invoke("community", "set", str(group_id), "rules_confirmed=yes")
    assert again.exit_code == 0 and first.id in again.output
    assert [r.id for r in requests(conn, group_id)] == [first.id]
    assert len(aw.events(conn, "approval.requested")) == 1


def test_new_rules_text_unconfirms_the_group_and_supersedes_the_request_with_a_new_one(conn):
    first = raised(conn)
    group_id = group_rules.group_id_of(first.subject)
    aw.approve(conn, first, args=DAYS)
    assert confirmation(conn, group_id) == (1, "sat,sun", "any")
    result = invoke("community", "set", str(group_id), "rules=No promotion at all.")
    assert result.exit_code == 0, result.output
    assert confirmation(conn, group_id) == (0, None, None)
    [second] = [r for r in requests(conn, group_id) if r.status == "pending"]
    assert second.id != first.id and second.id in result.output


def test_unconfirming_by_hand_still_works_and_raises_nothing(conn):
    first = raised(conn)
    group_id = group_rules.group_id_of(first.subject)
    aw.approve(conn, first, args=DAYS)
    assert invoke("community", "set", str(group_id), "rules_confirmed=no").exit_code == 0
    assert groups_mod.get(conn, group_id)["rules_confirmed"] == 0 and len(requests(conn, group_id)) == 1


def test_the_card_posts_when_the_command_ends_with_the_rules_and_the_typed_form_and_no_buttons(conn, discord_double, monkeypatch):
    from jura_growth import config

    patched = dict(config.settings())
    patched["approvals"] = {**(patched.get("approvals") or {}), "post_buttons": True}
    monkeypatch.setattr(config, "settings", lambda: patched)
    request = raised(conn)
    (card,) = discord_double.posts("approvals")
    assert card.components is None
    assert RULES in card.content and "SG F&B owners" in card.content
    assert f"/growth approve {request.id} promo_days=… post_days=…" in card.content
    assert "sat, sun" not in card.content and "promotion only on" not in card.content  # no parsed days
    assert aw.get(conn, request.id).posted_at


# --- skip, expiry, supersede, brakes (MC §5.7 row; G3, G5, G9, G19 for a kind applied on decide) -----


def context_entry(group_id: int) -> dict:
    import json

    view = json.loads(invoke("community", "context", "--json").output)
    return next(g for g in view["eligible"] if g["id"] == group_id)


def test_a_skip_leaves_the_rules_unconfirmed_and_posts_there_carry_no_link(conn):
    request = raised(conn)
    group_id = group_rules.group_id_of(request.subject)
    assert invoke("community", "set", str(group_id), "joined=yes").exit_code == 0
    assert aw.skip(conn, request).answer == "recorded"
    assert confirmation(conn, group_id) == (0, None, None)
    entry = context_entry(group_id)
    assert not entry["link_allowed"] and entry["days_open"] == []
    assert len([e for e in aw.events(conn, "community.group.rules_skipped") if e["group"] == group_id]) == 1


def test_an_unanswered_request_expires_after_14_days_as_a_skip(conn, monkeypatch):
    request = raised(conn)
    group_id = group_rules.group_id_of(request.subject)
    assert request.decide_by == aw.later(aw.NOW, days=14)
    now = aw.at(monkeypatch, request.decide_by)
    approvals.expire_due(conn, now)
    assert aw.get(conn, request.id).status == "expired"
    assert confirmation(conn, group_id) == (0, None, None)
    assert len([e for e in aw.events(conn, "community.group.rules_expired") if e["group"] == group_id]) == 1
    assert aw.approve(conn, request, args=DAYS).answer == "expired"
    assert confirmation(conn, group_id) == (0, None, None)


def test_confirming_again_after_an_unanswered_request_lapsed_raises_a_new_one(conn, monkeypatch):
    request = raised(conn)
    group_id = group_rules.group_id_of(request.subject)
    aw.at(monkeypatch, request.decide_by)  # past its decide-by, with the lapse not yet written
    result = invoke("community", "set", str(group_id), "rules_confirmed=yes")
    assert result.exit_code == 0, result.output
    assert aw.get(conn, request.id).status == "expired"
    [fresh] = [r for r in requests(conn, group_id) if r.status == "pending"]
    assert fresh.id in result.output and "decide it in #approvals" in result.output


def test_rules_changed_before_the_decision_supersede_it_and_set_nothing(conn):
    """G9 for a kind applied on decide: the approve answers superseded and a new request waits."""
    request = raised(conn)
    group_id = group_rules.group_id_of(request.subject)
    with db.transaction(conn):
        groups_mod.set_fields(conn, group_id, ["rules=Promo posts on Sundays only."])
    answer = aw.approve(conn, request, args=DAYS)
    assert answer.answer == "superseded"
    assert confirmation(conn, group_id) == (0, None, None)
    [fresh] = [r for r in requests(conn, group_id) if r.status == "pending"]
    assert fresh.supersedes == request.number and fresh.content_hash != request.content_hash
    assert aw.claims(conn) == 0


def test_a_removed_group_supersedes_its_request(conn):
    """G25: the item is gone."""
    request = raised(conn)
    group_id = group_rules.group_id_of(request.subject)
    with db.transaction(conn):
        groups_mod.remove(conn, group_id, "an admin removed a post")
    approvals.expire_due(conn, timeutil.now_sgt())
    record = aw.get(conn, request.id)
    assert record.status == "superseded" and requests(conn, group_id) == [record]
    refused = invoke("community", "set", str(group_id), "rules_confirmed=yes")
    assert refused.exit_code != 0 and "removed" in refused.output


@pytest.mark.parametrize("brake", ["PAUSE file", "paused agent"])
def test_a_paused_community_agent_refuses_the_approval_until_the_brake_clears(conn, brake):
    """G19 (AC-M4.6) for a kind applied on decide: refused and not claimed, then recorded."""
    from jura_growth import pause, paths

    request = raised(conn)
    group_id = group_rules.group_id_of(request.subject)
    if brake == "PAUSE file":
        paths.pause_file().write_text("stop\n")
    else:
        pause.pause(conn, "community", "by hand", notify=False)
    answer = aw.approve(conn, request, args=DAYS)
    assert answer.answer == "refused" and "paused" in answer.text
    assert aw.get(conn, request.id).status == "pending" and aw.claims(conn) == 0
    assert confirmation(conn, group_id) == (0, None, None)
    if brake == "PAUSE file":
        paths.pause_file().unlink()
    else:
        pause.resume(conn, "community")
    assert aw.approve(conn, request, args=DAYS).answer == "recorded"
    assert confirmation(conn, group_id) == (1, "sat,sun", "any")


def test_without_the_community_plugin_nothing_is_confirmed_or_expired(conn, monkeypatch):
    """AC-M4.7 for group-rules: a kind whose plug-in failed to load fails closed."""
    from jura_growth import agents

    request = raised(conn)
    real = agents.plugins()
    monkeypatch.setattr(agents, "plugins", lambda: tuple(m for m in real if getattr(m, "NAME", "") != "community"))
    assert aw.approve(conn, request, args=DAYS).answer == "refused"
    assert approvals.expire_due(conn, timeutil.parse(aw.later(request.decide_by, days=1))) == []
    assert aw.get(conn, request.id).status == "pending"
    assert confirmation(conn, group_rules.group_id_of(request.subject)) == (0, None, None)


# --- X2: the deadlines, whatever the machine's time zone ---------------------------------------------


@pytest.fixture
def zone(monkeypatch):
    import os
    import time

    before = os.environ.get("TZ")

    def set_zone(name: str) -> None:
        monkeypatch.setenv("TZ", name)
        time.tzset()

    yield set_zone
    if before is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = before
    time.tzset()


@pytest.mark.parametrize("name", ["Asia/Singapore", "UTC", "America/New_York"])
def test_a_group_rules_request_has_14_days_to_decide_and_applies_on_decide(conn, monkeypatch, zone, name):
    zone(name)
    aw.at(monkeypatch, aw.NOW)
    request = raised(conn)
    assert request.decide_by == "2026-11-24T10:02:15+08:00" and request.use_by is None
    aw.at(monkeypatch, "2026-11-24T10:02:14+08:00")
    assert aw.approve(conn, request, args=DAYS).answer == "recorded"
    record = aw.get(conn, request.id)
    assert record.use_by is None and record.used_at == "2026-11-24T10:02:14+08:00"


def test_a_configured_group_rules_deadline_may_shorten_and_never_lengthen(conn, monkeypatch):
    """X3 for this kind."""
    from jura_growth import config

    patched = dict(config.settings())
    patched["approvals"] = {"deadlines": {"group-rules": {"decide_by_days": 5}}}
    monkeypatch.setattr(config, "settings", lambda: patched)
    assert raised(conn).decide_by == aw.later(aw.NOW, days=5)
    patched["approvals"] = {"deadlines": {"group-rules": {"decide_by_days": 30}}}
    assert raised(conn, researched(conn, name="SG florists", slug="sgflorists")).decide_by == aw.later(aw.NOW, days=14)


# --- the sweep over group-rules cards (AC-M11.1, AC-M12.1) ---------------------------------------------


def test_a_group_rules_card_and_its_edit_carry_nothing_planted(conn, discord_double, d2_secrets):
    from sweep import MARKER, NAMED_ADDRESS, PHONE, RESEND_KEY, SOURCE_PAGE, assert_clean, outbox_dir, planted

    conn.execute(
        "INSERT INTO leads (id, company, display_name, domain, website, industry, score, score_reasons, channel,"
        " status, created_at, updated_at) VALUES (233, 'Example Pte Ltd', 'Example', 'example.com.sg',"
        " 'https://example.com.sg', 'logistics', 78, '[]', 'email', 'new', ?, ?)",
        (timeutil.stamp(), timeutil.stamp()),
    )
    conn.execute(
        "INSERT INTO contacts (lead_id, email, email_hash, source_url, kind, mx_ok, verified_at, created_at)"
        " VALUES (233, ?, 'h', ?, 'named', 1, ?, ?)",
        (NAMED_ADDRESS, SOURCE_PAGE, timeutil.stamp(), timeutil.stamp()),
    )
    rules = f"{MARKER}: ask Jane Tan at {NAMED_ADDRESS} or {PHONE} first, key {RESEND_KEY}. Promo on Saturdays.\n{planted().text()}"
    group_id = researched(conn, name=f"SG owners {MARKER} {PHONE}", rules=rules)
    request = raised(conn, group_id)
    assert aw.get(conn, request.id).posted_at
    assert aw.approve(conn, request, args=DAYS).answer == "recorded"
    from jura_growth import cards

    cards.sweep(conn)  # the card's first line, edited
    assert [r.method for r in discord_double.requests].count("PATCH") == 1
    assert_clean(discord_double, outbox_dir(), planted())


# --- X9: confirmations made before this kind stand, recorded once --------------------------------------


def test_earlier_confirmations_stand_and_are_recorded_once_as_an_event(conn):
    from jura_growth.agents import community as community_plugin

    earlier = researched(conn)
    legacy = researched(conn, name="SG printers", slug="sgprinters")
    with db.transaction(conn):  # as Terminal did before group-rules existed (ticket 07, and before it)
        groups_mod.set_fields(conn, earlier, ["rules_confirmed=yes", "promo_days=sat", "post_days=any"])
        conn.execute("UPDATE community_groups SET rules_confirmed = 1 WHERE id = ?", (legacy,))
    decided = raised(conn, researched(conn, name="SG florists", slug="sgflorists"))
    aw.approve(conn, decided, args=DAYS)
    before = {g: groups_mod.get(conn, g) for g in (earlier, legacy)}

    assert community_plugin.precheck("community", conn) is None
    assert invoke("community", "set", str(earlier), "notes=checked").exit_code == 0
    community_plugin.precheck("community", conn)

    recorded = aw.events(conn, "community.group.rules_confirmed_earlier")
    assert sorted(e["group"] for e in recorded) == [earlier, legacy]
    by_group = {e["group"]: e for e in recorded}
    assert by_group[earlier]["rules"] == RULES and by_group[earlier]["promo_days"] == "sat"
    assert by_group[legacy]["promo_days"] is None
    after = {g: groups_mod.get(conn, g) for g in (earlier, legacy)}
    assert {g: (r["rules_confirmed"], r["promo_days_confirmed"]) for g, r in after.items()} == {
        g: (r["rules_confirmed"], r["promo_days_confirmed"]) for g, r in before.items()}
    assert requests(conn, earlier) == [] and requests(conn, legacy) == []


# --- what Ting Yu is told ---------------------------------------------------------------------------


def test_an_unconfirmed_group_points_to_the_decision_never_to_days_in_community_set(conn):
    import re

    from jura_growth.agents.community import rules as rules_mod

    group_id = researched(conn)
    assert invoke("community", "set", str(group_id), "joined=yes").exit_code == 0
    problem = rules_mod.day_problem(groups_mod.rules_for(groups_mod.get(conn, group_id)), 5, promotional=False)
    for told in (problem, context_entry(group_id)["rules_summary"], invoke("community", "groups").output):
        assert "#approvals" in told and "promo_days=" in told, told
        assert not re.search(r"community set \S+ [^,;`\n]*(?:promo|post)_days=", told), told  # one command's words
