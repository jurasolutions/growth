"""`jura-growth remote`: control commands from Dispatch (MC SC10, §4.7, §5.10; ticket 11, MC-11a).

Seam S8. Tests play Dispatch's side: `remote --actor discord:<id> --ref <msg>:<dlv> [--json] --
<words>` through click's `CliRunner`, with the SSH origin passed in process as `ctx.obj["origin"]`
(test strategy v3 §1, §2). Without one, `remote` runs the real `origin.detect_ssh()`, which
refuses here. The real subprocesses are at the end of this file; the wrapper's are in
`test_growth_remote.py` (S14).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

import approval_world as aw
from sweep import d2_secrets  # noqa: F401 - a fixture
from jura_growth import approvals, config, headless, origin, paths, remote as remote_mod
from jura_growth.cli import cli
from jura_growth.origin import Origin

ARGS = ["promo_days=sat,sun", "post_days=any"]


def remote(words, *, origin_=None, actor=aw.CONTROL, ref=None, as_json=False, obj=True):
    """Dispatch's call, after the forced command (`bin/growth-remote`) split the words."""
    argv = ["remote"]
    if actor:
        argv += ["--actor", actor]
    if ref:
        argv += ["--ref", ref]
    if as_json:
        argv.append("--json")
    argv += ["--", *words]
    return CliRunner().invoke(cli, argv, obj={"origin": origin_ or Origin.ssh()} if obj else None)


def answer(result) -> dict:
    return json.loads(result.output)


def events(conn) -> list[dict]:
    return aw.events(conn, "remote.command")


@pytest.fixture
def world(conn, monkeypatch):
    world = aw.install(monkeypatch)
    aw.prepare(conn)
    aw.at(monkeypatch, aw.NOW)
    return world


def raised(conn, world, text="Quotes that write themselves"):
    return aw.request(conn, aw.KIND, world.item(text))


# --- a control command runs ------------------------------------------------------------------


def test_status_runs_and_answers_with_its_text(world):
    result = remote(["status"])
    assert result.exit_code == 0, result.output
    assert "paused     nothing" in result.output


# --- AC-M10.2: anything else is refused ------------------------------------------------------


def test_run_social_is_refused(conn, world):
    result = remote(["run", "social"])
    assert result.exit_code == 2
    assert result.output.startswith("refused:")
    assert conn.execute("SELECT count(*) FROM runs").fetchone()[0] == 0


@pytest.mark.parametrize("words", [[], ["--help"], ["Status"], ["status", "now"], ["/growth", "status"]])
def test_an_empty_unknown_or_misshapen_command_is_refused(world, words):
    result = remote(words)
    assert result.exit_code == 2 and result.output.startswith("refused:"), result.output


# --- AC-M7.5: only the SSH origin --------------------------------------------------------------


def test_without_an_origin_in_process_the_real_check_refuses(world, monkeypatch):
    """No sshd above this suite, and no forced command: `detect_ssh()` refuses."""
    monkeypatch.delenv("SSH_ORIGINAL_COMMAND", raising=False)
    result = remote(["status"], obj=False)
    assert result.exit_code == 2 and result.output.startswith("refused:")
    assert "paused" not in result.output


@pytest.mark.parametrize("reason", [origin.NOT_DISPATCH, origin.IN_CLAUDE, origin.UNCHECKED])
def test_a_refused_origin_runs_nothing(conn, world, reason):
    result = remote(["pause", "all"], origin_=Origin.refused(reason))
    assert result.exit_code == 2 and result.output.startswith("refused:") and reason in result.output
    assert conn.execute("SELECT count(*) FROM pause_flags").fetchone()[0] == 0


# --- the consistency check: the control user only (AC-M7.6 for every command) -----------------


@pytest.mark.parametrize("actor", ["discord:999", None, "terminal:tingy", "discord:111 "])
def test_a_command_from_anyone_but_the_control_user_runs_nothing(conn, world, actor):
    result = remote(["pause", "all"], actor=actor)
    assert result.exit_code == 2 and result.output.startswith("refused:"), result.output
    assert conn.execute("SELECT count(*) FROM pause_flags").fetchone()[0] == 0


# --- AC-M7.1: never in a scheduled run -----------------------------------------------------------


@pytest.mark.parametrize("job", sorted(config.settings()["jobs"]))
def test_every_configured_job_is_refused(world, monkeypatch, job):
    monkeypatch.setenv("JURA_GROWTH_JOB", job)
    result = remote(["status"])
    assert result.exit_code == 2 and "refused:" in result.output
    assert "paused" not in result.output


def test_remote_refuses_a_run_on_its_own_without_never(world, monkeypatch):
    """Each layer alone (test strategy v3 §5.3)."""
    monkeypatch.setattr(headless, "NEVER", ())
    monkeypatch.setattr(headless, "may_use", lambda job, name: True)
    monkeypatch.setenv("JURA_GROWTH_JOB", "social")
    result = remote(["status"])
    assert result.exit_code == 2 and result.output.startswith("refused:")
    assert "paused" not in result.output


# --- AC-M10.4: one remote.command event per call -------------------------------------------------


def test_each_call_writes_one_event_with_the_actor_and_the_words(conn, world):
    remote(["status"], ref="m1:d1")
    remote(["run", "social"])
    first, second = events(conn)
    assert first["actor"] == aw.CONTROL and first["words"] == ["status"] and first["ref"] == "m1:d1"
    assert first["exit_code"] == 0 and first["answer"] == "recorded"
    assert second["words"] == ["run", "social"] and second["exit_code"] == 2 and second["answer"] == "refused"


def test_a_refused_origin_is_still_written_down(conn, world):
    remote(["status"], origin_=Origin.refused(origin.IN_CLAUDE), actor="discord:999")
    (event,) = events(conn)
    assert event["actor"] == "discord:999" and event["origin"] == "refused" and event["answer"] == "refused"


# --- AC-M10.1: each allowlisted command, its own exit code, at most 1,900 characters ------------


def _group(conn) -> int:
    from jura_growth.agents.community import groups as groups_mod

    status, group_id, messages = groups_mod.add(conn, {
        "channel": "facebook", "name": "SG SME owners", "url": "https://www.facebook.com/groups/sgsme",
        "audience": "Singapore SME owners", "size_hint": "not stated", "active_hint": "not stated",
        "promo_rules": "not stated in public sources", "fit": "good fit",
        "fit_reason": "Owners asking each other about admin and paperwork.",
        "source_urls": ["https://example.sg/best-groups#sgsme"],
    })
    assert status == "added", messages
    return group_id


def _table(conn, world):
    approval = raised(conn, world)
    skipped = raised(conn, world, "skip me")
    group_id = _group(conn)
    return [
        # (words, exit code, a phrase the answer carries)
        (["approvals"], 0, f"{approval.id} · fake"),
        (["approvals", "fake"], 0, f"{approval.id} · fake"),
        (["approve", approval.id, *ARGS], 0, f"{approval.id} approved."),
        (["community", "removed", str(group_id)], 0, "is now skip, permanently"),
        (["community", "removed", "999"], 1, "999"),
        (["outreach", "requeue-shadow", "--dry-run"], 1, "live sending is ready"),
        (["pause", "all", "holiday"], 0, "paused all"),
        (["resume", "all"], 0, "resumed all"),
        (["skip", skipped.id, "not", "now"], 0, f"{skipped.id} skipped."),
        (["social", "skip", "2026-11-10", "instagram"], 0, "won't be drafted"),
        (["social", "skip", "2026-11-10", "myspace"], 2, "refused:"),
        (["status"], 0, "paused     "),
    ]


def test_every_allowlisted_command_has_a_row_here(conn, world):
    covered = {remote_mod.match(words)[0] for words, _, _ in _table(conn, world)}
    assert covered == set(remote_mod.ALLOWLIST)


def test_each_allowlisted_command_exits_with_its_own_code_and_at_most_1900_characters(conn, world):
    for words, code, phrase in _table(conn, world):
        result = remote(words, as_json=True)
        body = answer(result)
        assert result.exit_code == code == body["exit_code"], (words, result.output)
        assert phrase in body["text"], (words, body["text"])
        assert len(body["text"]) <= remote_mod.TEXT_LIMIT
        assert body["ok"] is (code == 0)


def test_a_long_answer_is_cut_to_1900_characters_at_a_line(conn, world):
    remote(["pause", "all", "a reason that runs on " + "and on " * 400])
    result = remote(["status"])
    assert result.exit_code == 0
    assert len(result.output.rstrip("\n")) <= remote_mod.TEXT_LIMIT
    assert "and on and on" in result.output


def test_the_cut_holds_for_one_long_line_and_for_many_lines():
    text = remote_mod._cut("x" * 5000)
    assert len(text) <= remote_mod.TEXT_LIMIT and text.endswith("…\n(cut)")
    lines = remote_mod._cut("\n".join(f"line {n} " + "y" * 80 for n in range(100)))
    assert len(lines) <= remote_mod.TEXT_LIMIT and lines.splitlines()[-1].startswith("(cut: ")


# --- AC-M10.7: resume all with a PAUSE file -------------------------------------------------------


def test_resume_all_with_a_pause_file_resumes_the_agents_and_says_the_file_stays(conn, world):
    remote(["pause", "all"])
    paths.pause_file().write_text("stop everything")
    result = remote(["resume", "all"])
    assert result.exit_code == 0, result.output
    assert "resumed all" in result.output
    assert "The PAUSE file can only be removed on the Mac" in result.output
    assert paths.pause_file().exists()
    assert conn.execute("SELECT count(*) FROM pause_flags WHERE paused = 1").fetchone()[0] == 0


def test_resume_without_a_pause_file_says_nothing_about_it(world):
    assert "PAUSE file" not in remote(["resume", "all"]).output


# --- pause: the reason is words, never an option ---------------------------------------------------


def test_pause_takes_the_rest_as_its_reason_and_says_where_it_came_from(conn, world):
    remote(["pause", "social", "--help", "--reason", "x"])
    remote(["pause", "scout"])
    reasons = {r["agent"]: r["reason"] for r in conn.execute("SELECT agent, reason FROM pause_flags")}
    assert reasons == {"social": "--help --reason x", "scout": "paused from Discord"}


# --- requeue-shadow: only --since and --dry-run ------------------------------------------------------


def test_requeue_shadow_passes_since_and_dry_run_through(world, monkeypatch):
    from jura_growth.agents.outreach import requeue

    seen = {}

    def fake(conn, *, since, lead_ids, dry_run):
        seen.update(since=since, lead_ids=lead_ids, dry_run=dry_run)
        raise requeue.RequeueError("stopped by the test")

    monkeypatch.setattr(requeue, "requeue_shadow", fake)
    result = remote(["outreach", "requeue-shadow", "--since", "2026-11-01", "--dry-run"])
    assert result.exit_code == 1 and "stopped by the test" in result.output
    assert seen == {"since": "2026-11-01", "lead_ids": (), "dry_run": True}


@pytest.mark.parametrize("extra", [["--lead", "3"], ["--json"], ["--since"], ["--file=/etc/passwd"], ["now"]])
def test_requeue_shadow_refuses_anything_else(world, extra):
    result = remote(["outreach", "requeue-shadow", *extra])
    assert result.exit_code == 2 and result.output.startswith("refused:")


# --- AC-M10.3: hostile words are only words ------------------------------------------------------------


HOSTILE = [";", "&&", "$(touch {s})", "`touch {s}`", "a\ntouch {s}", "|", "> {s}", "--ref", "evil"]


def test_hostile_words_in_a_note_arrive_as_literal_words_and_run_nothing(conn, world, tmp_path):
    sentinel = tmp_path / "sentinel"
    approval = raised(conn, world)
    words = [w.format(s=sentinel) for w in HOSTILE]
    result = remote(["skip", approval.id, *words], ref="m1:d1")
    assert result.exit_code == 0, result.output
    assert not sentinel.exists()
    (note,) = aw.events(conn, "approval.note")
    assert note["note"] == " ".join(words)
    assert aw.record(conn, approval.id)["decision_ref"] == "m1:d1"


@pytest.mark.parametrize("ref", ["--help", "-x", "--ref=other"])
def test_a_ref_that_looks_like_an_option_is_only_a_ref(conn, world, ref):
    approval = raised(conn, world)
    result = remote(["skip", approval.id], ref=ref)
    assert result.exit_code == 0, result.output
    assert aw.record(conn, approval.id)["decision_ref"] == ref


@pytest.mark.parametrize("word", [";", "&&", "$(touch {s})", "`touch {s}`", "\ntouch {s}"])
def test_hostile_words_after_a_command_are_refused_and_run_nothing(world, tmp_path, word):
    sentinel = tmp_path / "sentinel"
    result = remote(["status", word.format(s=sentinel), "touch", str(sentinel)])
    assert result.exit_code == 2 and result.output.startswith("refused:")
    assert not sentinel.exists()


def test_a_mention_in_an_answer_pings_nobody(conn, world):
    remote(["pause", "all", "@everyone", "<@123>", "@here"])
    output = remote(["status"]).output
    assert "@everyone" not in output and "<@123>" not in output and "@here" not in output


# --- decisions through remote (AC-M6.1, AC-M6.2, AC-M7.6, G12, G16, G30, G33) ------------------------


def test_an_approval_through_remote_records_the_actor_the_origin_growths_time_the_hash_and_the_ref(conn, world):
    approval = raised(conn, world)
    result = remote(["approve", approval.id, *ARGS], ref="1234567890:dlv-77")
    assert result.exit_code == 0, result.output
    record = aw.record(conn, approval.id)
    assert record["decided_by"] == "discord:111" and record["decided_origin"] == "ssh"
    assert record["decided_at"] == "2026-11-10T10:02:15+08:00"
    assert record["decision_ref"] == "1234567890:dlv-77"
    (event,) = aw.events(conn, "approval.approved")
    assert event["actor"] == "discord:111" and event["origin"] == "ssh" and event["ref"] == "1234567890:dlv-77"
    assert event["hash"] == approval.content_hash and event["at"] == "2026-11-10T10:02:15+08:00"


def test_the_same_ref_twice_through_remote_is_recorded_once_and_answers_the_same(conn, world):
    approval = raised(conn, world)
    first = remote(["approve", approval.id, *ARGS], ref="m1:d1", as_json=True)
    second = remote(["approve", approval.id, *ARGS], ref="m1:d1", as_json=True)
    assert first.exit_code == second.exit_code == 0
    assert answer(first) == answer(second)
    assert len(aw.events(conn, "approval.approved")) == 1


def test_a_stranger_through_remote_is_refused_logged_and_the_request_stays_pending(conn, world):
    approval = raised(conn, world)
    result = remote(["approve", approval.id, *ARGS], actor="discord:999", as_json=True)
    assert result.exit_code == 2 and answer(result)["answer"] == "refused"
    assert aw.record(conn, approval.id)["status"] == "pending"
    (event,) = events(conn)
    assert event["actor"] == "discord:999" and event["answer"] == "refused"


def test_the_key_value_grammar_reaches_on_approve_with_both_arguments(conn, world):
    approval = raised(conn, world)
    result = remote(["approve", approval.id, "promo_days=sat,sun", "post_days=any", "looks", "good"])
    assert result.exit_code == 0, result.output
    ((_, subject, args, status, in_transaction),) = world.ran("on_approve")
    assert subject == approval.subject and args == {"promo_days": "sat,sun", "post_days": "any"}
    assert status == "approved" and in_transaction


@pytest.mark.parametrize("args", [[], ["promo_days=sat,sun"], ["post_days=any"], ["promo_days=", "post_days=any"]])
def test_an_approval_without_its_arguments_is_refused(conn, world, args):
    approval = raised(conn, world)
    result = remote(["approve", approval.id, *args], as_json=True)
    assert result.exit_code == 2 and answer(result)["answer"] == "refused", result.output
    assert aw.record(conn, approval.id)["status"] == "pending"
    assert world.ran("on_approve") == []


def _decided_states(conn, world):
    made = {"recorded": raised(conn, world), "expired": raised(conn, world, "expires")}
    superseded = raised(conn, world, "changes")
    world.items[superseded.subject] += " (changed)"
    made["superseded"] = superseded
    decided = raised(conn, world, "decided")
    aw.skip(conn, decided)
    made["already-decided"] = decided
    used = raised(conn, world, "used")
    aw.approve(conn, used)
    assert world.act(conn, used.subject, run_id=aw.run(conn)) is None
    made["already-used"] = used
    return made


DISPATCH_ANSWERS = [
    # (case, decision, answer, exit code, the start of the text)
    ("unknown id", "approve", "unknown-id", 7, "There is no approval request A-9999."),
    ("expired", "approve", "expired", 3, "{expired} expired: not approved in time."),
    ("superseded", "skip", "superseded", 4, "{superseded} was superseded by "),
    ("already decided", "approve", "already-decided", 5, "{already-decided} was already skipped."),
    ("already used", "skip", "already-used", 6, "{already-used} was already used at "),
    ("no origin", "approve", "refused", 2, "refused: " + origin.NOT_DISPATCH),
    ("a stranger", "skip", "refused", 2, "refused: discord:999 isn't the control user."),
    ("missing days", "approve", "refused", 2, "refused: say promo_days=… post_days=…."),
    ("recorded", "approve", "recorded", 0, "{recorded} approved."),
    ("recorded", "skip", "recorded", 0, "{recorded} skipped."),
]


@pytest.mark.parametrize("case, decision, expected, code, text", DISPATCH_ANSWERS, ids=[f"{c[0]}-{c[1]}" for c in DISPATCH_ANSWERS])
def test_dispatch_answers(conn, world, monkeypatch, case, decision, expected, code, text):
    """Test strategy v3 §5.3, "Dispatch answers": one table over every answer."""
    made = _decided_states(conn, world)
    ids = {name.replace("-", "_"): approval.id for name, approval in made.items()}
    target = {"unknown id": "A-9999", "expired": ids["expired"], "superseded": ids["superseded"],
              "already decided": ids["already_decided"], "already used": ids["already_used"]}.get(case, ids["recorded"])
    if case == "expired":
        aw.at(monkeypatch, made["expired"].decide_by)
    args = ARGS if decision == "approve" and case != "missing days" else []
    kwargs = {}
    if case == "no origin":
        kwargs["origin_"] = Origin.refused(origin.NOT_DISPATCH)
    if case == "a stranger":
        kwargs["actor"] = "discord:999"
    result = remote([decision, target, *args], ref=f"m-{case}:d", as_json=True, **kwargs)
    body = answer(result)
    assert (body["answer"], body["exit_code"], result.exit_code) == (expected, code, code), body
    assert body["text"].startswith(text.replace("-", "_").format(**ids) if "{" in text else text), body["text"]
    assert body["contract"] == 1 and body["ok"] is (code == 0)


@pytest.mark.parametrize("typed", ["P-0042", "publish_item:42", "42", "fake_item:1"])
def test_only_an_a_id_names_a_request_through_remote(conn, world, typed):
    approval = raised(conn, world)
    result = remote(["approve", typed, *ARGS], as_json=True)
    assert answer(result)["answer"] == "unknown-id" and result.exit_code == 7
    assert aw.record(conn, approval.id)["status"] == "pending"


# --- AC-M5.4 through /growth approvals -------------------------------------------------------------


def test_thirty_pending_through_remote_lists_the_fifteen_soonest_then_the_rest(conn, world):
    made = []
    for n in range(30):
        world.decide_in = timedelta(hours=60 - n)
        made.append(raised(conn, world, f"item {n}"))
    result = remote(["approvals"], as_json=True)
    body = answer(result)
    assert result.exit_code == 0
    soonest = [a.id for a in reversed(made)][:15]
    lines = body["text"].splitlines()
    assert [line.split(" · ")[0] for line in lines[:15]] == soonest
    assert lines[15] == "and 15 more: /growth approvals fake"
    assert [item["id"] for item in body["approvals"]] == soonest
    assert body["approvals"][0] == {"id": soonest[0], "kind": "fake", "decide_by": made[-1].decide_by,
                                    "title": f"fake item {made[-1].subject}", "args": ["promo_days", "post_days"]}


# --- AC-M10.5: the --json answer ----------------------------------------------------------------------


def test_the_json_answer_has_the_contract_shape(world):
    body = answer(remote(["status"], as_json=True))
    assert set(body) == {"contract", "ok", "answer", "exit_code", "text"}
    assert body["contract"] == 1 and body["ok"] is True and body["answer"] == "recorded" and body["exit_code"] == 0


def test_a_refused_command_answers_refused_in_json(world):
    body = answer(remote(["run", "social"], as_json=True))
    assert body == {"contract": 1, "ok": False, "answer": "refused", "exit_code": 2, "text": body["text"]}
    assert body["text"].startswith("refused:")


def test_the_json_answer_stays_under_64_kb():
    reply = remote_mod.Reply(0, "recorded", "x", approvals=[{"id": f"A-{n:04d}", "kind": "k" * 1000} for n in range(200)])
    encoded = remote_mod.payload(reply)
    assert len(encoded.encode("utf-8")) <= remote_mod.JSON_LIMIT
    assert 0 < len(json.loads(encoded)["approvals"]) < 200


def test_every_answer_is_from_the_closed_enum_with_one_exit_code_each():
    assert set(remote_mod.ANSWER_FOR_EXIT.values()) == set(approvals.ANSWERS)
    assert len(remote_mod.ANSWER_FOR_EXIT) == len(approvals.ANSWERS)


# --- docs/dispatch-contract.md says what the code does (AC-M10.5, ticket review N8) -------------------

CONTRACT_DOC = paths.REPO_ROOT / "docs" / "dispatch-contract.md"


def _rows(heading: str) -> list[list[str]]:
    text = CONTRACT_DOC.read_text(encoding="utf-8")
    section = text.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]
    rows = [line for line in section.splitlines() if line.startswith("| ") and not line.startswith("| ---")]
    split = (re.split(r"(?<!\\)\|", row.strip().strip("|")) for row in rows[1:])  # "\|" is a pipe inside a cell
    return [[cell.strip().replace("\\|", "|") for cell in cells] for cells in split]


def test_the_contracts_answer_table_is_the_codes_enum_and_exit_codes():
    table = {row[0].strip("`"): int(row[1]) for row in _rows("Answers and exit codes")}
    assert table == {answer: code for code, answer in remote_mod.ANSWER_FOR_EXIT.items()}
    assert list(table) == list(approvals.ANSWERS)


def test_the_contracts_command_rows_follow_the_allowlist_in_order():
    usages = [row[0].strip("`") for row in _rows("Commands")]
    assert usages == [entry.usage for entry in remote_mod.ALLOWLIST.values()]


def test_adr_0004_is_accepted_and_the_setup_guide_restricts_the_key():
    """Exit criteria E12 and E6 (test strategy v3 §11.1); the guide is drafted in the feature folder."""
    adr = paths.REPO_ROOT / "docs" / "adr" / "0004-decisions-come-only-from-a-human-origin.md"
    status = next(line for line in adr.read_text(encoding="utf-8").splitlines() if line.startswith("Status:"))
    assert status.startswith("Status: accepted")
    guide = paths.REPO_ROOT / ".scratch" / "mission-control" / "setup" / "remote-control.md"
    assert 'restrict,command="' in guide.read_text(encoding="utf-8")


def test_the_contract_names_its_version_its_limits_and_the_json_fields():
    text = CONTRACT_DOC.read_text(encoding="utf-8")
    for needed in ('"contract": 1', "1,900", "64 KB", "--ref", "--actor discord:", "shlex.join", "growth:approve:A-",
                   "restrict,command=", *(f"| D{n} |" for n in range(1, 10))):
        assert needed in text, needed


# --- AC-M10.2, generated: every other leaf, and every command that takes a path ---------------------


def _leaves() -> dict[str, object]:
    return dict(headless.leaves(cli))


NOT_ALLOWED = sorted(name for name in _leaves() if name not in remote_mod.ALLOWLIST)
TAKES_A_PATH = sorted(
    name for name, command in _leaves().items() if any(isinstance(p.type, click.Path) for p in command.params)
)


def test_the_generated_lists_are_not_empty_and_name_run_social():
    assert "run" in NOT_ALLOWED and "check-copy" in TAKES_A_PATH and "remote" in NOT_ALLOWED
    assert remote_mod.match(["status"])[0] == "status"


@pytest.mark.parametrize("name", NOT_ALLOWED)
def test_every_leaf_not_on_the_allowlist_is_refused(conn, world, name):
    result = remote([*name.split(), "x"], as_json=True)
    body = answer(result)
    assert result.exit_code == 2 and body["answer"] == "refused"
    assert body["text"].startswith("refused:") and "isn't a control command" in body["text"]


@pytest.mark.parametrize("name", TAKES_A_PATH)
def test_every_command_that_takes_a_path_is_refused(world, name):
    result = remote([*name.split(), "/etc/hosts"])
    assert result.exit_code == 2 and result.output.startswith("refused:")


def test_no_allowlisted_command_takes_a_path():
    leaves = _leaves()
    for name in remote_mod.ALLOWLIST:
        assert name in leaves, f"{name} is on the allowlist but isn't a command"
        assert name not in TAKES_A_PATH, name


@pytest.mark.parametrize("name", ["run", "schedule", "discord", "db", "backup", "check", "suppression", "social render"])
def test_the_prd_never_list_is_off_the_allowlist(name):
    assert not any(entry == name or entry.startswith(name + " ") for entry in remote_mod.ALLOWLIST)


def test_the_allowlist_is_sorted_one_entry_per_line():
    """Ticket review N8: later tickets add rows in hunks of their own."""
    assert list(remote_mod.ALLOWLIST) == sorted(remote_mod.ALLOWLIST)
    source = Path(remote_mod.__file__).read_text(encoding="utf-8")
    block = source[source.index("ALLOWLIST: dict[str, Entry] = {"):].split("\n}\n", 1)[0].splitlines()[1:]
    assert [line.split('"')[1] for line in block] == list(remote_mod.ALLOWLIST)


# --- AC-M11.1, AC-M12.1: nothing planted reaches the answer; AC-M10.4: no output in the event ---------


class _Answers:
    """The sweep's double: what remote printed is what Dispatch would post."""

    def __init__(self):
        self.seen: list[str] = []

    def texts(self) -> list[str]:
        return self.seen


@pytest.fixture
def planted_reason(world, d2_secrets):
    from sweep import FINANCE, NAMED_ADDRESS, PERSON, PHONE, SECRETS, Planted

    planted = Planted(secrets=SECRETS, personal=(NAMED_ADDRESS, PHONE, PERSON, FINANCE))
    assert remote(["pause", "all", planted.text()]).exit_code == 0
    return planted


def test_the_sweep_finds_nothing_planted_in_remote_answers(conn, planted_reason):
    import sweep

    seen = _Answers()
    for words in (["status"], ["resume", "all"], ["run", "social", sweep.RESEND_KEY]):
        result = remote(words)
        seen.seen.append(result.output)
        seen.seen.append(remote(words, as_json=True).output)
    sweep.assert_clean(seen, None, planted_reason)


def test_the_event_holds_the_words_and_never_the_output(conn, planted_reason):
    output = remote(["status"]).output
    assert planted_reason.marker in output
    event = events(conn)[-1]
    assert event["words"] == ["status"]
    assert planted_reason.marker not in json.dumps(event)
    assert set(event) == {"actor", "words", "ref", "origin", "answer", "exit_code"}


# --- AC-M10.1: real processes, one per exit class ----------------------------------------------------

CHILD = str(Path(__file__).parent / "remote_child.py")


@pytest.fixture
def process_env(tmp_path, monkeypatch) -> dict[str, str]:
    """Every data variable on temp folders (conftest), and the control user in a temp env file."""
    env_file = tmp_path / "remote.env"
    env_file.write_text("CONTROL_DISCORD_USER_ID=111\n")
    monkeypatch.setenv("JURA_GROWTH_ENV_FILE", str(env_file))
    monkeypatch.delenv("CONTROL_DISCORD_USER_ID", raising=False)
    monkeypatch.delenv("SSH_ORIGINAL_COMMAND", raising=False)
    return dict(os.environ)


def _child(env, *words):
    return subprocess.run([sys.executable, CHILD, "remote", "--actor", "discord:111", "--json", "--", *words],
                          capture_output=True, text=True, env=env, timeout=120)


def test_a_real_process_without_an_sshd_ancestor_exits_2(process_env):
    ran = subprocess.run(["uv", "run", "--no-sync", "jura-growth", "remote", "--actor", "discord:111", "--json", "--", "status"],
                         cwd=paths.REPO_ROOT, capture_output=True, text=True, env=process_env, timeout=120)
    body = json.loads(ran.stdout)
    assert ran.returncode == 2 == body["exit_code"] and body["answer"] == "refused", ran.stdout + ran.stderr
    assert "paused" not in body["text"]


@pytest.mark.parametrize("words, code", [(["status"], 0), (["community", "removed", "999"], 1), (["run", "social"], 2)],
                         ids=["ok", "failed", "refused"])
def test_a_real_process_exits_with_each_class(process_env, words, code):
    ran = _child(process_env, *words)
    body = json.loads(ran.stdout)
    assert ran.returncode == code == body["exit_code"], ran.stdout + ran.stderr
    assert len(body["text"]) <= remote_mod.TEXT_LIMIT and body["ok"] is (code == 0)
    assert "paused     nothing" in body["text"] if code == 0 else body["text"]
