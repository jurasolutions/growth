"""The `apps` commands through `jura-growth remote` (ticket 12, MC-11b; MC §5.9, §5.10, D6, D7).

Seam S8, as in `test_remote.py`: Dispatch's call through click's `CliRunner`, with the SSH origin
passed in process. The world is `test_app_releases.py`'s: a private `prd/` with the template, the
landing-page repository at `paths.site_repo()` (D13), the clock at Tuesday 10 November 10:02 and
Ting Yu as the control user. Test strategy v3 §4.1: AC-M9.2 (`apps handoffs`), AC-M9.7 to AC-M9.9
through remote, and AC-M10.1 for the four commands.
"""

from __future__ import annotations

import hashlib
import json
import shutil

import pytest
from click.testing import CliRunner

import approval_world as aw
import site_repo
from discord_double import discord_double  # noqa: F401 - the fixture
from gate_adapter_app_build import file_prd, prd_path
from test_app_releases import BRANCH, PREVIEW, PROJECT, TASK, done_prds, handed_off, pages_project, pending_prd, release_requests
from jura_growth import config, db, handoff_fit, origin, paths, remote as remote_mod
from jura_growth.agents.apps import builds, releases
from jura_growth.cli import cli
from jura_growth.origin import Origin

REAL_PRD = paths.JURA_ROOT / "prd"


def remote(words, *, origin_=None, actor=aw.CONTROL, ref=None, as_json=False):
    """Dispatch's call, after the forced command split the words."""
    argv = ["remote", "--actor", actor] if actor else ["remote"]
    if ref:
        argv += ["--ref", ref]
    if as_json:
        argv.append("--json")
    return CliRunner().invoke(cli, [*argv, "--", *words], obj={"origin": origin_ or Origin.ssh()})


def answer(result) -> dict:
    return json.loads(result.output)


@pytest.fixture(autouse=True)
def world(tmp_path, monkeypatch):
    prd = tmp_path / "prd"
    (prd / "templates").mkdir(parents=True)
    (prd / "pending" / "apps").mkdir(parents=True)
    shutil.copy(REAL_PRD / "templates" / "prd-app-template.md", prd / "templates")
    monkeypatch.setenv("JURA_PRD_DIR", str(prd))
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", aw.CONTROL_ID)
    aw.at(monkeypatch, aw.NOW)
    config.reset_caches()
    pages_project(monkeypatch, PROJECT)
    site_repo.make()
    return prd


def built_words(app_id: str, sha: str) -> list[str]:
    return ["apps", "built", app_id, "--task", TASK, "--branch", BRANCH, "--sha", sha, "--preview", PREVIEW]


# --- AC-M9.2 through remote: `apps handoffs`, and the `handoff` object Dispatch polls (D6) ----------


def test_handoffs_with_none_waiting_says_so_and_carries_an_empty_handoff(conn):
    result = remote(["apps", "handoffs"], as_json=True)
    body = answer(result)
    assert result.exit_code == 0 == body["exit_code"] and body["answer"] == "recorded"
    assert body["text"] == "No build handoffs are waiting."
    assert body["handoff"] == {"contract": 1, "handoffs": [], "more": 0}


def test_handoffs_carries_the_approved_prd_text_verbatim_and_lists_it_until_it_is_built(conn):
    app_id, approval = handed_off(conn)
    text = prd_path(app_id).read_text(encoding="utf-8")
    result = remote(["apps", "handoffs"], as_json=True)
    body = answer(result)
    assert result.exit_code == 0, result.output
    [entry] = body["handoff"]["handoffs"]
    assert entry["app_id"] == app_id and entry["approval"] == approval.id
    assert entry["handoff"] == {
        "repo": "landing-page", "base": "main", "prd_text": text,
        "prd_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "approval": approval.id,
    }
    assert body["handoff"]["more"] == 0
    assert app_id in body["text"] and approval.id in body["text"]
    assert len(body["text"]) <= remote_mod.TEXT_LIMIT
    assert remote(["apps", "built", *built_words(app_id, site_repo.branch(BRANCH))[2:]]).exit_code == 0
    assert answer(remote(["apps", "handoffs"], as_json=True))["handoff"]["handoffs"] == []


def test_handoffs_in_plain_text_is_the_listing_alone(conn):
    app_id, approval = handed_off(conn)
    result = remote(["apps", "handoffs"])
    assert result.exit_code == 0
    assert result.output.startswith(f"{app_id} ") and approval.id in result.output
    assert "prd_text" not in result.output and "{" not in result.output


def test_the_handoff_answer_stays_within_64_kb_and_counts_what_waits_for_a_later_poll(conn):
    filler = "\n".join(f"- Filler line {n} to make the PRD long." for n in range(900))
    for number in (101, 102, 103):
        app_id = file_prd(number)
        path = prd_path(app_id)
        path.write_text(path.read_text() + filler)
        with db.transaction(conn):
            request = builds.request(conn, app_id, reason="test", run_id=None)
        assert aw.approve(conn, request, args={}).answer == "recorded"
    result = remote(["apps", "handoffs"], as_json=True)
    assert len(result.output.rstrip("\n").encode("utf-8")) <= remote_mod.JSON_LIMIT
    given = answer(result)["handoff"]
    assert given["handoffs"][0]["app_id"] == "APP-101"  # oldest first
    assert len(given["handoffs"]) + given["more"] == 3 and given["more"] >= 1
    for entry in given["handoffs"]:
        assert hashlib.sha256(entry["handoff"]["prd_text"].encode()).hexdigest() == entry["handoff"]["prd_sha256"]


def _approve_padded(conn, app_id: str, room: int) -> None:
    """Pad the handed-off PRD by `room` bytes, as if those were the bytes approved."""
    path = prd_path(app_id)
    path.write_text(path.read_text() + "y" * room)
    with db.transaction(conn):
        conn.execute("UPDATE app_builds SET prd_sha256 = ? WHERE app_id = ?",
                     (hashlib.sha256(path.read_bytes()).hexdigest(), app_id))


def test_a_prd_that_fits_alone_but_not_beside_remotes_text_holds_up_no_newer_handoff(conn):
    """Probe p9 (code review 12, S1): APP-101 would fit 64 KB on its own, but not beside remote's
    envelope. The plug-in and remote agree it is too large: it is named with its problem in both,
    and APP-102 is handed out on the same poll, every poll."""
    first, _ = handed_off(conn, 101)
    _approve_padded(conn, first, handoff_fit.JSON_LIMIT - handoff_fit.size(builds.handoffs_json(conn)) - 50)
    second, approval = handed_off(conn, 102)
    local = builds.handoffs_json(conn)
    assert [e["app_id"] for e in local["handoffs"]] == [first, second] and local["more"] == 0
    assert local["handoffs"][0]["problem"] == handoff_fit.TOO_LARGE
    for _ in range(2):
        result = remote(["apps", "handoffs"], as_json=True)
        assert len(result.output.rstrip("\n").encode("utf-8")) <= remote_mod.JSON_LIMIT
        given = answer(result)["handoff"]
        assert given == local  # remote's own fit is only the backstop: it changes nothing here
        big, small = given["handoffs"]
        assert big["handoff"] is None and big["problem"] == handoff_fit.TOO_LARGE
        assert small["handoff"]["approval"] == approval.id


def test_whatever_the_plugin_hands_out_fits_remotes_answer_unchanged(conn):
    """A PRD just inside the plug-in's limit still fits beside remote's longest text."""
    app_id, _ = handed_off(conn)
    _approve_padded(conn, app_id, handoff_fit.HANDOFF_LIMIT - handoff_fit.size(builds.handoffs_json(conn)) - 10)
    local = builds.handoffs_json(conn)
    assert local["handoffs"][0]["handoff"] is not None
    reply = remote_mod.Reply(0, "already-decided", "\u0001" * remote_mod.TEXT_LIMIT, handoff=local)
    encoded = remote_mod.payload(reply)
    assert len(encoded.encode("utf-8")) <= remote_mod.JSON_LIMIT
    assert json.loads(encoded)["handoff"] == local


# --- code review 12, S2: the bytes handed out are the bytes approved ----------------------------------


def test_a_prd_holding_a_secret_looking_value_is_withheld_with_its_problem(conn):
    """Probe p1: printing would mask the value, so the text sent wouldn't be the approved bytes."""
    app_id = file_prd(101)
    path = prd_path(app_id)
    path.write_text(path.read_text() + "\nKey for testing: sk-ant-abcdefghijklmnop0123\n")
    with db.transaction(conn):
        request = builds.request(conn, app_id, reason="test", run_id=None)
    assert aw.approve(conn, request, args={}).answer == "recorded"
    for given in (builds.handoffs_json(conn), answer(remote(["apps", "handoffs"], as_json=True))["handoff"]):
        [entry] = given["handoffs"]
        assert entry["app_id"] == app_id and entry["handoff"] is None
        assert "secret-looking" in entry["problem"]


def test_remote_withholds_any_handoff_whose_text_doesnt_hash_to_its_sha(conn, monkeypatch):
    """The backstop: whatever changed the text on its way out, a mismatch is never handed out."""
    app_id, _ = handed_off(conn)
    real = builds.handoff

    def altered(build):
        given, problem = real(build)
        return ({**given, "prd_text": given["prd_text"] + "changed on the way out"}, problem)

    monkeypatch.setattr(builds, "handoff", altered)
    [entry] = answer(remote(["apps", "handoffs"], as_json=True))["handoff"]["handoffs"]
    assert entry["app_id"] == app_id and entry["handoff"] is None
    assert "doesn't match its approved SHA-256" in entry["problem"]


def test_handoffs_that_cant_be_read_as_json_fail_and_hand_nothing_out(conn, monkeypatch):
    handed_off(conn)

    def broken(conn):
        raise RuntimeError("unreadable")

    monkeypatch.setattr(builds, "handoffs_json", broken)
    result = remote(["apps", "handoffs"], as_json=True)
    body = answer(result)
    assert result.exit_code == 1 == body["exit_code"] and body["ok"] is False and "handoff" not in body
    assert "couldn't be read as JSON" in body["text"]


def test_a_real_process_answers_handoffs_with_the_handoff(conn, tmp_path, monkeypatch):
    """AC-M10.1's real process, for the one apps answer that carries more than text."""
    import os
    import subprocess
    import sys

    app_id, approval = handed_off(conn)
    env_file = tmp_path / "remote.env"
    env_file.write_text(f"CONTROL_DISCORD_USER_ID={aw.CONTROL_ID}\n")
    monkeypatch.setenv("JURA_GROWTH_ENV_FILE", str(env_file))
    monkeypatch.delenv("CONTROL_DISCORD_USER_ID", raising=False)
    monkeypatch.delenv("SSH_ORIGINAL_COMMAND", raising=False)
    child = str(paths.REPO_ROOT / "tests" / "remote_child.py")
    ran = subprocess.run([sys.executable, child, "remote", "--actor", aw.CONTROL, "--json", "--", "apps", "handoffs"],
                         capture_output=True, text=True, env=dict(os.environ), timeout=120)
    body = json.loads(ran.stdout)
    assert ran.returncode == 0 == body["exit_code"], ran.stdout + ran.stderr
    [entry] = body["handoff"]["handoffs"]
    assert entry["app_id"] == app_id and entry["handoff"]["approval"] == approval.id


def test_the_contract_documents_the_handoff_dispatch_polls():
    text = (paths.REPO_ROOT / "docs" / "dispatch-contract.md").read_text(encoding="utf-8")
    section = text.split("\n## The JSON answer\n", 1)[1].split("\n## ", 1)[0]
    assert "reserved" not in section
    for needed in ("`handoff` (only from `apps handoffs`)", '"repo": "landing-page"', '"base": "main"', '"prd_text"',
                   '"prd_sha256"', '"approval"', "`more`", "`problem`", "never for posting to Discord"):
        assert needed in section, needed


def test_only_commands_that_hand_off_carry_a_handoff(conn):
    assert "handoff" not in answer(remote(["status"], as_json=True))
    assert "handoff" not in answer(remote(["apps", "release-plan", "APP-999"], as_json=True))


# --- AC-M9.7 through remote: `apps built` --------------------------------------------------------------


def test_built_through_remote_raises_an_app_release_card_with_the_preview_and_the_short_sha(conn, discord_double):
    app_id, _ = handed_off(conn)
    sha = site_repo.branch(BRANCH)
    result = remote(built_words(app_id, sha), ref="m1:d1", as_json=True)
    body = answer(result)
    assert result.exit_code == 0 == body["exit_code"] and body["answer"] == "recorded", body
    [request] = release_requests(conn)
    assert request.status == "pending" and request.id in body["text"]
    [card] = discord_double.posts("approvals")[-1:]
    assert card.content.splitlines()[0].startswith(f"**{request.id} · app release**")
    assert PREVIEW in card.content and sha[:7] in card.content
    row = releases.current_build(conn, app_id)
    assert (row["task_id"], row["branch"], row["head_sha"], row["preview_url"]) == (TASK, BRANCH, sha, PREVIEW)


def test_built_through_remote_takes_its_values_in_either_spelling_and_any_order(conn):
    app_id, _ = handed_off(conn)
    sha = site_repo.branch(BRANCH)
    words = ["apps", "built", f"--sha={sha}", "--preview", PREVIEW, app_id, f"--branch={BRANCH}", "--task", TASK]
    result = remote(words)
    assert result.exit_code == 0, result.output
    assert releases.current_build(conn, app_id)["head_sha"] == sha


def test_built_through_remote_on_a_build_never_handed_off_exits_1_and_raises_nothing(conn, discord_double):
    app_id = file_prd(101)  # filed, never approved
    result = remote(built_words(app_id, site_repo.branch(BRANCH)), as_json=True)
    body = answer(result)
    assert result.exit_code == 1 == body["exit_code"] and body["ok"] is False and body["answer"] == "refused"
    assert "handed off" in body["text"]
    assert release_requests(conn) == [] and discord_double.posts("approvals") == []


@pytest.mark.parametrize("change", [
    "no sha", "sha twice", "an unknown option", "two ids", "no id", "a value-less option", "a short option",
])
def test_built_through_remote_refuses_anything_but_its_own_grammar(conn, change):
    app_id, _ = handed_off(conn)
    sha = site_repo.branch(BRANCH)
    words = built_words(app_id, sha)
    words = {
        "no sha": [w for w in words if w not in ("--sha", sha)],
        "sha twice": [*words, "--sha", sha],
        "an unknown option": [*words, "--file=/etc/hosts"],
        "two ids": [*words, "APP-102"],
        "no id": [w for w in words if w != app_id],
        "a value-less option": [*words[:-1]],  # --preview with nothing after it
        "a short option": [*words, "-x"],
    }[change]
    result = remote(words, as_json=True)
    body = answer(result)
    assert result.exit_code == 2 and body["answer"] == "refused" and body["text"].startswith("refused:"), body
    assert release_requests(conn) == []


def test_a_value_that_looks_like_an_option_is_only_a_value(conn):
    """`--branch -delete` reaches `apps built` as the branch `-delete`, which it refuses itself."""
    app_id, _ = handed_off(conn)
    words = built_words(app_id, site_repo.branch(BRANCH))
    words[words.index("--branch") + 1] = "-delete"
    result = remote(words)
    assert result.exit_code == 1, result.output
    assert release_requests(conn) == []


# --- AC-M9.8 through remote: `apps release-plan` -------------------------------------------------------


def approved_release(conn) -> tuple[str, str, object]:
    app_id, _ = handed_off(conn)
    sha = site_repo.branch(BRANCH)
    assert remote(built_words(app_id, sha)).exit_code == 0
    [request] = release_requests(conn)
    assert aw.approve(conn, request, args={}).answer == "recorded"
    return app_id, sha, request


def test_release_plan_through_remote_claims_then_answers_with_the_merge_of_the_approved_sha_only(conn):
    app_id, sha, request = approved_release(conn)
    later = site_repo.commit_on(BRANCH)
    result = remote(["apps", "release-plan", app_id], as_json=True)
    body = answer(result)
    assert result.exit_code == 0 == body["exit_code"] and body["answer"] == "recorded", body
    assert aw.get(conn, request.id).used_at
    merges = [line.strip() for line in body["text"].splitlines() if "git merge" in line]
    assert merges == [f'git merge --no-ff -m "Release {app_id} (approval {request.id})" {sha}']
    assert later not in body["text"] and len(body["text"]) <= remote_mod.TEXT_LIMIT
    assert f"jura-growth apps released {app_id} --task {TASK}" in body["text"]


def test_release_plan_through_remote_with_nothing_approved_exits_1_and_gives_nothing_to_run(conn):
    app_id, _ = handed_off(conn)
    assert remote(built_words(app_id, site_repo.branch(BRANCH))).exit_code == 0  # pending, not approved
    for target in (app_id, "APP-999"):
        body = answer(remote(["apps", "release-plan", target], as_json=True))
        assert body["exit_code"] == 1 and body["answer"] == "refused" and "git " not in body["text"]
    assert aw.claims(conn) == 1  # only the app-build handoff's claim


@pytest.mark.parametrize("words", [["apps", "release-plan"], ["apps", "release-plan", "APP-101", "now"]])
def test_release_plan_through_remote_takes_one_id(conn, words):
    result = remote(words)
    assert result.exit_code == 2 and result.output.startswith("refused:")


# --- AC-M9.9 through remote: `apps released` -------------------------------------------------------------


def test_released_through_remote_without_a_claimed_release_exits_1_and_the_prd_stays(conn):
    app_id, sha, _ = approved_release(conn)  # approved, never claimed by release-plan
    site_repo.merge(sha)
    body = answer(remote(["apps", "released", app_id, "--task", TASK], as_json=True))
    assert body["exit_code"] == 1 and "release-plan" in body["text"]
    assert pending_prd(app_id) is not None and done_prds() == []


def test_released_through_remote_when_main_lacks_the_sha_exits_1_and_the_prd_stays(conn):
    app_id, sha, _ = approved_release(conn)
    assert remote(["apps", "release-plan", app_id]).exit_code == 0
    body = answer(remote(["apps", "released", app_id, "--task", TASK], as_json=True))
    assert body["exit_code"] == 1 and sha[:7] in body["text"]
    assert pending_prd(app_id) is not None and done_prds() == []
    assert releases.current_build(conn, app_id)["status"] == "built"


def test_released_through_remote_records_the_release_and_moves_the_prd_to_done(conn):
    app_id, build_approval = handed_off(conn)
    sha = site_repo.branch(BRANCH)
    assert remote(built_words(app_id, sha)).exit_code == 0
    [release] = release_requests(conn)
    aw.approve(conn, release, args={})
    assert remote(["apps", "release-plan", app_id]).exit_code == 0
    site_repo.merge(sha)
    result = remote(["apps", "released", f"--task={TASK}", app_id], as_json=True)
    body = answer(result)
    assert result.exit_code == 0 == body["exit_code"] and body["answer"] == "recorded", body
    assert build_approval.id in body["text"] and release.id in body["text"]
    assert releases.current_build(conn, app_id) is None
    assert db.one(conn, "SELECT status FROM app_builds WHERE app_id = ?", (app_id,))["status"] == "released"
    [done] = done_prds()
    assert pending_prd(app_id) is None
    signed = [line for line in done.read_text().splitlines() if line.startswith("Signed off by:")]
    assert len(signed) == 1 and f"build approval {build_approval.id}" in signed[0]
    assert f"release approval {release.id}" in signed[0]
    assert done.read_text().startswith("*Shipped on 2026-11-10:")


@pytest.mark.parametrize("words", [["apps", "released", "APP-101"], ["apps", "released", "APP-101", "--task"],
                                   ["apps", "released", "APP-101", "--task", "T-0031", "--force"]])
def test_released_through_remote_takes_one_id_and_its_task(conn, words):
    result = remote(words)
    assert result.exit_code == 2 and result.output.startswith("refused:")


# --- ticket 11's checks hold for every apps command ---------------------------------------------------


def _each_command(conn) -> list[list[str]]:
    app_id, sha, _ = approved_release(conn)
    return [["apps", "handoffs"], built_words(app_id, sha), ["apps", "release-plan", app_id],
            ["apps", "released", app_id, "--task", TASK]]


@pytest.mark.parametrize("who", ["a refused origin", "a stranger", "no actor", "a scheduled run"])
def test_no_apps_command_runs_for_anyone_but_the_control_user_through_dispatch(conn, monkeypatch, who):
    commands = _each_command(conn)
    kwargs = {"a refused origin": {"origin_": Origin.refused(origin.IN_CLAUDE)}, "a stranger": {"actor": "discord:999"},
              "no actor": {"actor": None}}.get(who, {})
    if who == "a scheduled run":
        monkeypatch.setenv("JURA_GROWTH_JOB", "app-factory")
    before = conn.execute("SELECT count(*) FROM approvals WHERE used_at IS NOT NULL").fetchone()[0]
    for words in commands:
        result = remote(words, as_json=True, **kwargs)
        assert result.exit_code == 2 and "refused" in result.output, (words, result.output)
        assert "git merge" not in result.output and "prd_text" not in result.output
        if who != "a scheduled run":  # headless.NEVER refuses that one before remote answers in JSON
            body = answer(result)
            assert body["answer"] == "refused" and "handoff" not in body, (words, body)
    assert conn.execute("SELECT count(*) FROM approvals WHERE used_at IS NOT NULL").fetchone()[0] == before
    assert len(release_requests(conn)) == 1


def test_each_apps_command_writes_one_remote_event_with_its_words_and_no_output(conn):
    commands = _each_command(conn)
    for words in commands:
        remote(words, ref="m9:d9")
    logged = aw.events(conn, "remote.command")[-len(commands):]
    assert [e["words"] for e in logged] == commands
    assert all(set(e) == {"actor", "words", "ref", "origin", "answer", "exit_code"} for e in logged)
    assert "git merge" not in json.dumps(logged) and "prd_text" not in json.dumps(logged)
