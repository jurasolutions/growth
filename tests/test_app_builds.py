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
from gate_adapter_app_build import DispatchDouble, file_prd, prd_path
from jura_growth import approvals, config, db, log, mission, one_pager, pause, paths
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
