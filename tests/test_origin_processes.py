"""Decisions refused in real processes (seam S13; MC3 as amended 2026-10-26; code review 04b S1).

Terminal decisions are off: `jura-growth approve` and `skip` refuse whatever terminal they run in.
The regression is the reviewer's own probe: an orphaned `/usr/bin/expect`, adopted by launchd so no
`claude` process is above it, gives `approve` a real terminal and types the first six hex
characters of the content hash. It used to record a Terminal decision. It must now be refused,
with Claude Code's environment markers set and with them stripped.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

import approval_world as aw
import origin_child
from jura_growth import agents, db, origin

CHILD = str(Path(__file__).parent / "origin_child.py")
REFUSAL = f"refused: {origin.TERMINAL_OFF}."


@pytest.fixture
def item(conn, monkeypatch):
    monkeypatch.setattr(agents, "plugins", origin_child.plugins_with_kind(aw.REAL_PLUGINS))
    aw.at(monkeypatch, aw.NOW)
    subject = "file_item:1"
    origin_child.write_item(subject, "Quotes that write themselves")
    return aw.request(conn, origin_child.KIND, subject)


def status(approval) -> dict:
    with db.session() as fresh:
        return aw.record(fresh, approval.id)


def environment(*, markers: bool) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in origin.CLAUDE_MARKERS}
    if markers:
        env.update(CLAUDECODE="1", CLAUDE_CODE_ENTRYPOINT="cli")
    return env


def orphaned_expect(tmp_path: Path, words: list[str], typed: str, *, markers: bool) -> dict:
    """The probe from code review 04b, step 4: `( expect … & )`. Returns the command's exit
    status, what it printed, and the parent pid expect had once the subshell was gone."""
    log, ppid, done = tmp_path / "probe.log", tmp_path / "probe.ppid", tmp_path / "probe.status"
    script = tmp_path / "probe.exp"
    spawn = " ".join(f"{{{word}}}" for word in [sys.executable, CHILD, *words])
    script.write_text(
        "set timeout 30\n"
        "log_user 0\n"
        f"for {{set i 0}} {{$i < 250}} {{incr i}} {{ if {{[string trim [exec /bin/ps -o ppid= -p [pid]]] == 1}} break; after 20 }}\n"
        f"set f [open {{{ppid}}} w]; puts $f [string trim [exec /bin/ps -o ppid= -p [pid]]]; close $f\n"
        f"log_file -a -noappend {{{log}}}\n"  # -a: log what log_user 0 keeps off the screen
        f"spawn {spawn}\n"
        f'expect {{ "code (" {{ send "{typed}\\r"; exp_continue }} eof }}\n'
        "set result [wait]\n"
        "log_file\n"  # closes the log, so it is complete before the status appears
        f"set f [open {{{done}.part}} w]; puts $f [lindex $result 3]; close $f\n"
        f"file rename {{{done}.part}} {{{done}}}\n"
    )
    subprocess.run(["/bin/sh", "-c", f"( /usr/bin/expect -f '{script}' & )"], env=environment(markers=markers), check=True, timeout=30)
    end = time.time() + 60
    while not done.exists():
        assert time.time() < end, "the orphaned expect never finished"
        time.sleep(0.05)
    return {"exit": int(done.read_text().strip()), "output": log.read_text(), "ppid": ppid.read_text().strip()}


def test_without_a_terminal_a_decision_is_refused_and_points_to_approvals(item):
    ran = subprocess.run(
        [sys.executable, CHILD, "approve", item.id],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, env=environment(markers=False), timeout=60,
    )
    assert ran.returncode == 2, ran.stdout + ran.stderr
    assert ran.stdout.strip() == REFUSAL
    assert status(item)["status"] == "pending"


@pytest.mark.parametrize("markers", [True, False], ids=["claude-markers", "markers-stripped"])
@pytest.mark.parametrize("decision", ["approve", "skip"])
def test_the_orphaned_expect_probe_is_refused(item, tmp_path, markers, decision):
    ran = orphaned_expect(tmp_path, [decision, item.id], item.content_hash[:6], markers=markers)
    assert ran["ppid"] == "1", "the probe didn't leave the test's process tree, so it proves nothing"
    assert ran["exit"] == 2, ran["output"]
    assert REFUSAL in ran["output"]
    assert "code (" not in ran["output"], "nothing asks for a code any more"
    record = status(item)
    assert record["status"] == "pending" and record["decided_by"] is None


@pytest.mark.parametrize("markers", [True, False], ids=["claude-markers", "markers-stripped"])
def test_the_forced_command_variable_alone_is_not_the_dispatch_origin(tmp_path, markers):
    """`detect_ssh()` in a real process with `SSH_ORIGINAL_COMMAND` set but no sshd above it."""
    env = environment(markers=markers)
    env["SSH_ORIGINAL_COMMAND"] = "approve A-0001"
    ran = subprocess.run(
        [sys.executable, "-c", "import json; from jura_growth import origin; o = origin.detect_ssh(); print(json.dumps([o.kind, o.reason]))"],
        capture_output=True, text=True, env=env, timeout=60,
    )
    kind, reason = json.loads(ran.stdout)
    assert kind == origin.NOT_HUMAN
    if markers:
        assert reason == origin.IN_CLAUDE
    else:
        # Stripped, the ancestry decides: a `claude` above this suite, or no sshd at all.
        assert reason in (origin.IN_CLAUDE, origin.NOT_DISPATCH)
