"""App ideas wait for approval, and approval writes the build handoff (ticket MC-10,
MC §5.7 `app-build` row, §5.9 steps 1, 2, 5 to 7; test strategy v3 §4.1 AC-M9.1 to AC-M9.6,
AC-M9.10, AC-M9.11, §4.3 X2, X3, X7).

Decisions come only through Dispatch (ADR 0004 as amended 2026-10-26), so the tests decide with
`aw.dispatch()` and the control actor. The gate matrix for the kind runs through
`gate_adapter_app_build.py`.
"""

import hashlib
import json
import shutil

import pytest
from click.testing import CliRunner

import approval_world as aw
import mission_world as mw
from discord_double import discord_double  # noqa: F401 - the fixture
from sweep import d2_secrets  # noqa: F401 - the fixture
from gate_adapter_app_build import DispatchDouble, file_prd, prd_path
from jura_growth import approvals, config, db, log, mission, one_pager, pause, paths, timeutil
from jura_growth.agents.apps import builds
from jura_growth.cli import cli
from test_apps import GOOD, TODAY

REAL_PRD = paths.JURA_ROOT / "prd"
FILED = "prd-app-003-delivery-order-maker-2026-10-26.md"
PATH = f"prd/pending/apps/{FILED}"
BUILD_IT = "Build it: open Claude Code in `jurasolutions/` and say: build the approved PRD `{path}` (approval {id})"


def invoke(*args):
    return CliRunner().invoke(cli, list(args), catch_exceptions=False)


@pytest.fixture(autouse=True)
def prd_tree(tmp_path, monkeypatch):
    """A private prd/ (the template, APP-001 and APP-002), an empty site registry, the clock
    at 06:30 on Monday 26 October, and Ting Yu as the control user."""
    prd = tmp_path / "prd"
    (prd / "templates").mkdir(parents=True)
    (prd / "pending" / "apps").mkdir(parents=True)
    shutil.copy(REAL_PRD / "templates" / "prd-app-template.md", prd / "templates")
    for name in ("prd-app-001-quote-builder-2026-10-24.md", "prd-app-002-receipt-reader-2026-10-24.md"):
        shutil.copy(REAL_PRD / "pending" / "apps" / name, prd / "pending" / "apps")
    site = tmp_path / "site"
    (site / "src" / "apps").mkdir(parents=True)
    (site / "src" / "apps" / "registry.json").write_text("[]")
    monkeypatch.setenv("JURA_PRD_DIR", str(prd))
    monkeypatch.setenv("JURA_SITE_REPO", str(site))
    monkeypatch.setenv("JURA_GROWTH_NOW", f"{TODAY}T06:30:00+08:00")
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", aw.CONTROL_ID)
    config.reset_caches()
    return prd


def submit(tmp_path, text=GOOD, name="draft.md"):
    draft = tmp_path / name
    draft.write_text(text)
    return invoke("apps", "submit-prd", str(draft))


def filed_request(conn) -> approvals.Approval:
    [request] = [a for a in approvals.pending(conn) if a.kind == "app-build"]
    return request


def filed(tmp_path, conn) -> approvals.Approval:
    assert submit(tmp_path).exit_code == 0
    return filed_request(conn)


def dispatch_builds(monkeypatch, on: bool) -> None:
    patched = dict(config.settings())
    patched["approvals"] = {**(patched.get("approvals") or {}), "dispatch_builds": on}
    monkeypatch.setattr(config, "settings", lambda: patched)


# --- AC-M9.1: the 06:30 run files the PRD and the card posts ---------------------------


def test_the_factory_run_files_a_prd_and_an_app_build_card_posts_with_the_prd_attached(tmp_path, prd_tree, conn, discord_double, monkeypatch):
    run_id = log.start_run(conn, "app-factory", "app-factory")
    monkeypatch.setenv("JURA_GROWTH_RUN_ID", str(run_id))
    result = submit(tmp_path)
    assert result.exit_code == 0, result.output
    request = filed_request(conn)
    assert request.subject == "app:APP-003" and approvals.raised_by(conn, run_id) == [request]
    [card] = discord_double.posts("approvals")
    first, *rest = card.content.splitlines()
    assert first.startswith(f"**{request.id} · app build** · decide by Mon 2 Nov, 06:30 SGT")
    body = "\n".join(rest)
    assert "APP-003 Delivery order maker" in body
    assert "Make a delivery order with your logo and a signature box" in body  # the pitch
    assert "Tier: browser. Category: Documents." in body
    assert "Lead types it suits: wholesale and distribution, logistics and delivery, and field service businesses." in body
    assert [name for name, _ in card.files] == [FILED]
    assert card.files[0][1].decode("utf-8") == GOOD
    assert result.output.count(request.id) == 1  # the command says which request it raised


def test_no_message_carries_the_old_approved_build_line(tmp_path, conn, discord_double):
    """AC-M9.1: the "approved, build …" line is gone from every message. The PRD attached to the
    card still holds the template's own header and sign-off lines (see the report)."""
    assert submit(tmp_path).exit_code == 0
    assert discord_double.posts()
    assert not [r for r in discord_double.requests if "approved, build" in (r.content or "")]
    assert discord_double.posts("app-factory") == []  # the card replaces the old #app-factory post


# --- AC-M9.2 and AC-M9.3: approving writes the handoff ------------------------------------


def test_approving_claims_the_request_and_writes_one_handoff_in_the_same_transaction(tmp_path, prd_tree, conn):
    request = filed(tmp_path, conn)
    answer = aw.approve(conn, request, args={})
    assert answer.answer == "recorded"
    record = aw.get(conn, request.id)
    assert record.status == "approved" and record.used_at == record.decided_at
    [build] = db.rows(conn, "SELECT * FROM app_builds")
    file_bytes = (prd_tree / "pending" / "apps" / FILED).read_bytes()
    assert build["status"] == "handed_off" and build["app_id"] == "APP-003" and build["prd_path"] == PATH
    assert build["prd_sha256"] == hashlib.sha256(file_bytes).hexdigest()
    assert build["approval_id"] == request.id and build["approval_at"] == record.decided_at
    assert file_bytes == GOOD.encode()  # nothing about the approval went into the file
    assert [e["approval"] for e in aw.events(conn, "approval.used")] == [request.id]


def test_handoffs_json_carries_the_handoff_and_lists_it_until_it_is_built(tmp_path, conn):
    request = filed(tmp_path, conn)
    assert json.loads(invoke("apps", "handoffs", "--json").output)["handoffs"] == []
    aw.approve(conn, request, args={})
    payload = json.loads(invoke("apps", "handoffs", "--json").output)
    [entry] = payload["handoffs"]
    assert payload["contract"] == 1 and entry["app_id"] == "APP-003" and entry["approval"] == request.id
    assert entry["handoff"] == {
        "repo": "landing-page", "base": "main", "prd_text": GOOD,
        "prd_sha256": hashlib.sha256(GOOD.encode()).hexdigest(), "approval": request.id,
    }
    listing = invoke("apps", "handoffs").output
    assert "APP-003 Delivery order maker" in listing and request.id in listing and PATH in listing
    conn.execute("UPDATE app_builds SET status = 'built'")  # what ticket 10b's `apps built` does
    assert json.loads(invoke("apps", "handoffs", "--json").output)["handoffs"] == []
    assert invoke("apps", "handoffs").output.strip() == "No build handoffs are waiting."


def test_a_prd_changed_after_its_handoff_is_not_handed_out(tmp_path, prd_tree, conn):
    aw.approve(conn, filed(tmp_path, conn), args={})
    (prd_tree / "pending" / "apps" / FILED).write_text(GOOD + "One more line.\n")
    [entry] = json.loads(invoke("apps", "handoffs", "--json").output)["handoffs"]
    assert entry["handoff"] is None and "changed after it was approved" in entry["problem"]


def test_the_handoffs_json_stays_within_64_kb(conn, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", aw.NOW)
    filler = "\n".join(f"- Filler line {n} to make the PRD long." for n in range(900))
    for number in (101, 102, 103):
        app_id = file_prd(number)
        path = prd_path(app_id)
        path.write_text(path.read_text() + filler)
        with db.transaction(conn):
            request = builds.request(conn, app_id, reason="test", run_id=None)
        assert request is not None and aw.approve(conn, request, args={}).answer == "recorded"
    output = invoke("apps", "handoffs", "--json").output
    payload = json.loads(output)
    assert len(output.encode()) <= builds.JSON_LIMIT
    assert len(payload["handoffs"]) + payload["more"] == 3 and payload["more"] >= 1
    assert payload["handoffs"][0]["app_id"] == "APP-101"  # oldest first


@pytest.mark.parametrize("on", [False, True], ids=["dispatch_builds false", "dispatch_builds true"])
def test_the_answer_and_the_one_pager_say_how_it_gets_built(tmp_path, conn, monkeypatch, on):
    """AC-M9.3 and the test strategy's Q6: both values of `approvals.dispatch_builds`."""
    dispatch_builds(monkeypatch, on)
    request = filed(tmp_path, conn)
    answer = aw.approve(conn, request, args={})
    build_it = BUILD_IT.format(path=PATH, id=request.id)
    snapshot = mission.read(mw.source(now=f"{TODAY}T08:00:00+08:00"))
    [line] = [line for line in snapshot.plugin_lines if "APP-003" in line]
    assert "Build handoff waiting for a builder: APP-003 Delivery order maker" in line
    assert line in one_pager.text(snapshot)
    if on:
        assert answer.text == f"{request.id} approved. Handed to Dispatch: it builds APP-003 on its own branch from main."
        assert "Build it" not in line and request.id in line
    else:
        assert answer.text == f"{request.id} approved. {build_it}"
        assert build_it in line


def test_dispatch_sees_the_handoff_only_after_the_claim_commits(tmp_path, conn, monkeypatch):
    """AC-M4.3 and G21 for app-build: the claim and the row commit together, and Dispatch can't
    list a handoff before that commit."""
    request = filed(tmp_path, conn)
    double = DispatchDouble()
    during: list = []
    real = builds.hand_off

    def hand_off_then_poll(*args, **kwargs):
        written = real(*args, **kwargs)
        during.append(double.poll())
        return written

    monkeypatch.setattr(builds, "hand_off", hand_off_then_poll)
    assert aw.approve(conn, request, args={}).answer == "recorded"
    assert during == [[]]
    assert [h["app_id"] for h in double.poll()] == ["APP-003"]
    assert double.seen == [{"app_id": "APP-003", "used": True}]


def test_a_prd_edited_between_the_claim_and_the_handoff_is_never_handed_out(tmp_path, prd_tree, conn, monkeypatch):
    """Code review 10, B1 (repro R1): the handoff carries exactly the bytes the claimed approval
    covers. An edit that lands after the claim refuses the decision and rolls it back; the next
    decision finds the content changed and raises a new request."""
    request = filed(tmp_path, conn)
    target = prd_tree / "pending" / "apps" / FILED
    real_use = approvals.use

    def use_then_edit(*args, **kwargs):
        claimed = real_use(*args, **kwargs)
        target.write_text(GOOD + "Edited after the claim.\n")
        return claimed

    monkeypatch.setattr(approvals, "use", use_then_edit)
    answer = aw.approve(conn, request, args={})
    assert answer.answer == "refused" and "changed" in answer.text
    assert db.scalar(conn, "SELECT count(*) FROM app_builds") == 0 and aw.claims(conn) == 0
    assert json.loads(invoke("apps", "handoffs", "--json").output)["handoffs"] == []
    monkeypatch.setattr(approvals, "use", real_use)
    assert aw.approve(conn, request, args={}).answer == "superseded"
    assert filed_request(conn).content_hash == hashlib.sha256(target.read_bytes()).hexdigest()


def test_a_failed_handoff_write_rolls_the_decision_back(tmp_path, conn):
    """G22 for app-build: the row and the claim commit together or neither does; the request is
    still pending and can be approved again."""
    request = filed(tmp_path, conn)
    conn.execute("CREATE TEMP TRIGGER fail_handoff BEFORE INSERT ON app_builds BEGIN SELECT RAISE(ABORT, 'disk full'); END")
    answer = aw.approve(conn, request, args={})
    assert answer.answer == "refused" and "handoff" in answer.text
    record = aw.get(conn, request.id)
    assert record.status == "pending" and record.used_at is None
    assert db.scalar(conn, "SELECT count(*) FROM app_builds") == 0 and aw.claims(conn) == 0
    conn.execute("DROP TRIGGER temp.fail_handoff")
    assert aw.approve(conn, request, args={}).answer == "recorded"
    assert db.scalar(conn, "SELECT count(*) FROM app_builds") == 1


def test_an_app_build_takes_no_decision_arguments(tmp_path, conn):
    """G37 for app-build: an argument is refused and nothing is recorded."""
    request = filed(tmp_path, conn)
    answer = aw.approve(conn, request, args={"post_days": "any"})
    assert answer.answer == "refused" and "doesn't take post_days" in answer.text
    assert aw.get(conn, request.id).status == "pending" and db.scalar(conn, "SELECT count(*) FROM app_builds") == 0
    assert aw.events(conn, "approval.approved") == []


def test_a_prd_changed_by_one_byte_is_not_handed_off_and_a_new_request_is_raised(tmp_path, prd_tree, conn):
    """AC-M9.4 (G9 for app-build)."""
    request = filed(tmp_path, conn)
    target = prd_tree / "pending" / "apps" / FILED
    target.write_bytes(target.read_bytes() + b" ")
    assert aw.approve(conn, request, args={}).answer == "superseded"
    assert aw.get(conn, request.id).status == "superseded"
    assert db.scalar(conn, "SELECT count(*) FROM app_builds") == 0 and aw.claims(conn) == 0
    fresh = filed_request(conn)
    assert fresh.supersedes == request.number and fresh.subject == "app:APP-003"
    assert fresh.content_hash == hashlib.sha256(target.read_bytes()).hexdigest()


# --- AC-M9.5 and AC-M9.6: skipped for good, or unanswered and back after 30 days ---------------


def good_on(day: str, number: int = 3) -> str:
    """GOOD as the factory would write it on `day`, as APP-<number>."""
    return GOOD.replace("2026-10-26", day).replace("APP-003", f"APP-{number:03d}").replace("prd-app-003", f"prd-app-{number:03d}")


def at(monkeypatch, moment: str) -> None:
    monkeypatch.setenv("JURA_GROWTH_NOW", moment)


def backlog_row(slug: str) -> dict:
    view = json.loads(invoke("apps", "context", "--json").output)
    return next(r for r in view["backlog"] if r["slug"] == slug)


def test_a_skipped_prd_moves_to_skipped_and_its_idea_never_comes_back(tmp_path, prd_tree, conn, monkeypatch):
    """AC-M9.5."""
    at(monkeypatch, "2026-11-10T06:30:00+08:00")
    assert submit(tmp_path, good_on("2026-11-10")).exit_code == 0
    request = filed_request(conn)
    at(monkeypatch, "2026-11-10T09:15:00+08:00")
    assert aw.skip(conn, request).answer == "recorded"
    name = "prd-app-003-delivery-order-maker-2026-11-10.md"
    moved = prd_tree / "skipped" / "apps" / name
    assert not (prd_tree / "pending" / "apps" / name).exists()
    first, blank, *rest = moved.read_text().splitlines()
    assert first.startswith("Skipped by Ting Yu on 2026-11-10") and blank == ""
    assert "\n".join(rest) + "\n" == good_on("2026-11-10")
    at(monkeypatch, "2026-11-11T06:30:00+08:00")
    assert backlog_row("delivery-order-maker")["effective_status"] == "dropped"
    again = submit(tmp_path, good_on("2026-11-11", number=4))
    assert again.exit_code == 1 and "delivery-order-maker" in again.output


def test_a_skip_that_rolls_back_leaves_the_prd_and_the_backlog_as_they_were(tmp_path, prd_tree, conn):
    """Code review 10, N4: the PRD moves and the backlog changes only once the decision commits."""
    request = filed(tmp_path, conn)
    before = backlog_row("delivery-order-maker")
    conn.execute(
        "CREATE TEMP TRIGGER fail_decision BEFORE INSERT ON approval_decisions BEGIN SELECT RAISE(ABORT, 'disk full'); END"
    )
    with pytest.raises(Exception, match="disk full"):
        aw.skip(conn, request)
    assert aw.get(conn, request.id).status == "pending"
    assert (prd_tree / "pending" / "apps" / FILED).exists()
    assert not (prd_tree / "skipped" / "apps" / FILED).exists()
    assert backlog_row("delivery-order-maker") == before
    conn.execute("DROP TRIGGER temp.fail_decision")
    assert aw.skip(conn, request).answer == "recorded"
    assert (prd_tree / "skipped" / "apps" / FILED).exists() and backlog_row("delivery-order-maker")["effective_status"] == "dropped"


def test_an_unanswered_prd_expires_and_its_idea_is_offered_again_from_day_30(tmp_path, prd_tree, conn, monkeypatch):
    """AC-M9.6: not offered on day 29 after the expiry, offered and filed again on day 30."""
    at(monkeypatch, "2026-11-10T06:30:00+08:00")
    assert submit(tmp_path, good_on("2026-11-10")).exit_code == 0
    request = filed_request(conn)
    expired = aw.at(monkeypatch, request.decide_by)  # 2026-11-17 06:30
    approvals.expire_due(conn, expired)
    assert aw.get(conn, request.id).status == "expired"
    moved = prd_tree / "skipped" / "apps" / "prd-app-003-delivery-order-maker-2026-11-10.md"
    assert moved.read_text().startswith("Expired unanswered on 2026-11-17")
    at(monkeypatch, "2026-12-16T06:30:00+08:00")  # day 29
    assert backlog_row("delivery-order-maker")["effective_status"] != "idea"
    assert submit(tmp_path, good_on("2026-12-16", number=4)).exit_code == 1
    at(monkeypatch, "2026-12-17T06:30:00+08:00")  # day 30
    assert backlog_row("delivery-order-maker")["effective_status"] == "idea"
    result = submit(tmp_path, good_on("2026-12-17", number=4))
    assert result.exit_code == 0, result.output
    assert [a.subject for a in approvals.pending(conn) if a.kind == "app-build"] == ["app:APP-004"]


# --- AC-M9.10: the waiting pile, and AC-M9.11: the one-off pass ------------------------------


def raise_for(conn, app_id: str) -> approvals.Approval:
    with db.transaction(conn):
        raised = builds.request(conn, app_id, reason="the app factory filed it", run_id=None)
    assert raised is not None
    return raised


def test_seven_prds_waiting_for_a_decision_stop_the_factory(tmp_path, conn):
    """AC-M9.10."""
    from jura_growth import runner
    from jura_growth.agents import apps as apps_plugin

    requests = [raise_for(conn, file_prd(number)) for number in range(101, 108)]
    reason = apps_plugin.precheck("app-factory", conn)
    assert reason and reason.startswith("7 app PRDs waiting for an app-build decision")
    assert runner.run("app-factory", ignore_schedule=True).status == "skipped"
    refused = submit(tmp_path)
    assert refused.exit_code == 1 and "waiting for an app-build decision" in refused.output
    assert aw.approve(conn, requests[0], args={}).answer == "recorded"  # handed off: no longer waiting
    assert apps_plugin.precheck("app-factory", conn) is None


def test_the_one_off_pass_raises_one_request_for_each_factory_prd_already_pending(conn, discord_double):
    """AC-M9.11: Ting Yu's own PRDs (APP-001, APP-002) get none, and a second pass raises none,
    even after one of them is handed off."""
    from jura_growth.agents import apps as apps_plugin

    file_prd(3, slug="pdf-merge-and-split", name="PDF merge and split")
    file_prd(4, slug="payslip-maker", name="Payslip maker")
    assert apps_plugin.precheck("app-factory", conn) is None
    raised = [a for a in approvals.pending(conn) if a.kind == "app-build"]
    assert sorted(a.subject for a in raised) == ["app:APP-003", "app:APP-004"]
    assert len(discord_double.posts("approvals")) == 2
    aw.approve(conn, raised[0], args={})
    apps_plugin.precheck("app-factory", conn)
    assert builds.raise_waiting(conn) == []
    assert db.scalar(conn, "SELECT count(*) FROM approvals WHERE kind = 'app-build'") == 2
    assert len(discord_double.posts("approvals")) == 2


# --- X2, X3 and X7 for this kind ------------------------------------------------------------------


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
def test_an_app_build_has_seven_days_to_decide_and_one_day_to_use(conn, monkeypatch, zone, name):
    """X2: whatever the machine's time zone."""
    zone(name)
    aw.at(monkeypatch, aw.NOW)
    request = raise_for(conn, file_prd(101))
    assert request.decide_by == aw.later(aw.NOW, days=7) == "2026-11-17T10:02:15+08:00"
    approved_at = "2026-11-12T09:00:00+08:00"
    aw.at(monkeypatch, approved_at)
    aw.approve(conn, request, args={})
    assert aw.get(conn, request.id).use_by == "2026-11-13T09:00:00+08:00"


def test_a_configured_app_build_deadline_may_shorten_and_never_lengthen(conn, monkeypatch):
    """X3 for this kind: the deadlines come from the `approvals:` block, capped by caps.py."""
    aw.at(monkeypatch, aw.NOW)
    patched = dict(config.settings())
    patched["approvals"] = {"deadlines": {"app-build": {"decide_by_days": 3, "use_by_days": 5}}}
    monkeypatch.setattr(config, "settings", lambda: patched)
    shorter = raise_for(conn, file_prd(101))
    assert shorter.decide_by == aw.later(aw.NOW, days=3)
    aw.approve(conn, shorter, args={})
    assert aw.get(conn, shorter.id).use_by == aw.later(aw.NOW, days=1)  # 5 reads as the cap, 1
    patched["approvals"] = {"deadlines": {"app-build": {"decide_by_days": 30}}}
    assert raise_for(conn, file_prd(102)).decide_by == aw.later(aw.NOW, days=7)


def test_the_app_build_migrations_change_no_existing_row(tmp_path, monkeypatch):
    """X7: a database at main's app-factory schema migrates through `app_builds` and the
    reusable slug with every row as it was."""
    from jura_growth.agents import apps as apps_plugin

    old = tmp_path / "apps-at-main"
    old.mkdir()
    shutil.copy(apps_plugin.MIGRATIONS / "0001_app_factory.sql", old / "0001_app_factory.sql")
    with monkeypatch.context() as patch:
        patch.setattr(apps_plugin, "MIGRATIONS", old)
        conn = db.connect(tmp_path / "old.db")
    for n, slug in ((3, "pdf-merge-and-split"), (4, "payslip-maker")):
        conn.execute(
            "INSERT INTO app_prds (app_id, slug, name, tier, category, path, day, run_id, created_at) VALUES (?, ?, ?, 'browser', 'Documents', ?, '2026-10-24', NULL, ?)",
            (f"APP-{n:03d}", slug, slug.replace("-", " ").capitalize(), f"prd/pending/apps/prd-app-{n:03d}-{slug}-2026-10-24.md", aw.NOW),
        )
    tables = [r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
    before = {t: db.rows(conn, f"SELECT * FROM {t}") for t in tables if t != "schema_migrations"}
    assert db.migrate(conn) == ["app-factory/0002_app_builds.sql", "app-factory/0003_app_prds_slug_reusable.sql"]
    assert {t: db.rows(conn, f"SELECT * FROM {t}") for t in before} == before
    assert db.scalar(conn, "SELECT count(*) FROM app_builds") == 0
    conn.execute(
        "INSERT INTO app_prds (app_id, slug, name, tier, category, path, day, created_at) VALUES ('APP-005', 'payslip-maker', 'Payslip maker', 'browser', 'HR', 'x', '2026-12-17', ?)",
        (aw.NOW,),
    )  # the slug can be proposed again under a new number
    conn.close()


def test_no_plugin_migration_names_a_decision_column():
    """G31 for this kind: approval state lives only in `approvals` (MC §4.6 A2)."""
    import re

    from jura_growth.agents import apps as apps_plugin

    for path in apps_plugin.MIGRATIONS.glob("*.sql"):
        assert not re.search(r"decided|approved|approver|decide_by|use_by|used_at", path.read_text()), path.name


# --- the sweep over app-build cards (AC-M11.1, AC-M12.1) ----------------------------------------------


def test_an_app_build_card_and_its_edit_carry_nothing_planted(conn, discord_double, d2_secrets, monkeypatch):
    from sweep import MARKER, NAMED_ADDRESS, PHONE, RESEND_KEY, SOURCE_PAGE, assert_clean, outbox_dir, planted
    from jura_growth import cards, timeutil

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
    app_id = file_prd(101)
    path = prd_path(app_id)
    inline = f"{MARKER} for Jane Tan at {NAMED_ADDRESS} or {PHONE}, key {RESEND_KEY}"
    text = path.read_text().replace("Make a delivery order with your logo", f"{inline}. Make a delivery order with your logo", 1)
    text = text.replace("Who has this problem:** owners", f"Who has this problem:** {inline}, owners", 1)
    path.write_text(text.replace("## 6. Open questions\n", "## 6. Open questions\n\n" + planted().text() + "\n"))
    request = raise_for(conn, app_id)
    assert cards.sweep(conn) == 1
    aw.approve(conn, request, args={})
    cards.sweep(conn)  # the card's first line, edited
    assert [r.method for r in discord_double.requests].count("PATCH") == 1
    assert_clean(discord_double, outbox_dir(), planted())


def test_without_the_apps_plugin_nothing_is_handed_off_or_expired(conn, monkeypatch):
    """AC-M4.7 for app-build: a kind whose plug-in failed to load fails closed."""
    from jura_growth import agents

    request = raise_for(conn, file_prd(101))
    real = agents.plugins()
    monkeypatch.setattr(agents, "plugins", lambda: tuple(m for m in real if getattr(m, "NAME", "") != "app-factory"))
    with db.transaction(conn):
        with pytest.raises(approvals.NotApproved) as refused:
            builds.hand_off(conn, request.subject)
    assert refused.value.reason == "unknown-kind"
    assert aw.approve(conn, request, args={}).answer == "refused"
    assert approvals.expire_due(conn, timeutil.parse(aw.later(request.decide_by, days=1))) == []
    assert aw.get(conn, request.id).status == "pending" and prd_path("APP-101").exists()
    assert db.scalar(conn, "SELECT count(*) FROM app_builds") == 0


@pytest.mark.parametrize("name", ["prompts/app-factory.md", "docs/app-factory.md"])
def test_the_prompt_and_docs_no_longer_say_a_build_starts_with_approved_build(name):
    """MC §4.9: the approval in #approvals is the sign-off. "approved, build" survives only where
    a file quotes the template's own "To build:" header line, which `prd.py` still checks."""
    text = (paths.REPO_ROOT / name).read_text(encoding="utf-8")
    assert [line for line in text.splitlines() if "approved, build" in line and "To build:" not in line] == []
    assert "#approvals" in text and "app-build" in text


@pytest.mark.parametrize("brake", ["PAUSE file", "paused agent"])
def test_a_paused_factory_refuses_the_approval_without_claiming(tmp_path, conn, brake):
    """AC-M4.6 for a kind applied on decide: the decision is refused and the request waits."""
    request = filed(tmp_path, conn)
    if brake == "PAUSE file":
        paths.pause_file().write_text("stop\n")
    else:
        pause.pause(conn, "app-factory", "by hand", notify=False)
    answer = aw.approve(conn, request, args={})
    assert answer.answer == "refused" and "paused" in answer.text
    assert aw.get(conn, request.id).status == "pending" and aw.claims(conn) == 0
    assert db.scalar(conn, "SELECT count(*) FROM app_builds") == 0
    if brake == "PAUSE file":  # G19: once the brake clears, the same request can be approved
        paths.pause_file().unlink()
    else:
        pause.resume(conn, "app-factory")
    assert aw.approve(conn, request, args={}).answer == "recorded"
    assert db.scalar(conn, "SELECT count(*) FROM app_builds") == 1 and aw.claims(conn) == 1
