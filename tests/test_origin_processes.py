"""The human origin, checked in real processes (seam S13; AC-M7.2 to AC-M7.4, AC-M6.4's real path).

Each test raises a request in process, then runs `jura-growth approve` as a real subprocess: with
stdin from `/dev/null`, or under a real pseudo-terminal from the standard library's `pty`, with
and without an ancestor whose command name is `claude`. See `pty_driver.py` for why the
pseudo-terminal runs outside the test's own process tree.
"""

from __future__ import annotations

import json
import os
import pwd
import subprocess
import sys
import time
from pathlib import Path

import pytest

import approval_world as aw
import origin_child
from jura_growth import agents, db

TESTS = Path(__file__).parent
CHILD = str(TESTS / "origin_child.py")
DRIVER = str(TESTS / "pty_driver.py")


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


def under_pty(tmp_path, words, *, typed, under_claude=False) -> dict:
    result = tmp_path / f"pty-{time.monotonic_ns()}.json"
    spec = {"argv": [sys.executable, CHILD, *words], "type": typed, "result": str(result), "under_claude": under_claude}
    subprocess.run([sys.executable, DRIVER, json.dumps(spec)], check=True, env=dict(os.environ), timeout=30)
    end = time.time() + 60
    while not result.exists():
        assert time.time() < end, "the pseudo-terminal run never finished"
        time.sleep(0.05)
    return json.loads(result.read_text())


def test_without_a_terminal_a_decision_is_refused_and_the_request_stays_pending(item):
    ran = subprocess.run(
        [sys.executable, "-m", "jura_growth", "approve", item.id],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=dict(os.environ),
        timeout=60,
    )
    assert ran.returncode == 2, ran.stdout + ran.stderr
    assert "decisions need a terminal or the Dispatch link" in ran.stdout
    assert status(item)["status"] == "pending"


def test_under_a_real_terminal_a_wrong_code_is_refused(item, tmp_path):
    ran = under_pty(tmp_path, ["approve", item.id], typed="000000")
    assert ran["exit"] == 2, ran["output"]
    assert "refused:" in ran["output"] and "code" in ran["output"]
    assert status(item)["status"] == "pending"


def test_under_a_real_terminal_the_right_code_records_the_terminal_decision(item, tmp_path):
    ran = under_pty(tmp_path, ["approve", item.id], typed=item.code)
    assert ran["exit"] == 0, ran["output"]
    assert f"{item.id} approved." in ran["output"]
    record = status(item)
    assert record["status"] == "approved"
    assert record["decided_origin"] == "terminal"
    assert record["decided_by"] == f"terminal:{pwd.getpwuid(os.getuid()).pw_name}"


def test_under_a_real_terminal_skip_with_the_right_code_records_the_skip(item, tmp_path):
    ran = under_pty(tmp_path, ["skip", item.id, "wrong", "one"], typed=item.code)
    assert ran["exit"] == 0, ran["output"]
    assert status(item)["status"] == "skipped"


def test_under_a_real_terminal_a_claude_ancestor_is_refused_before_any_code_is_asked(item, tmp_path):
    ran = under_pty(tmp_path, ["approve", item.id], typed=item.code, under_claude=True)
    assert ran["exit"] == 2, ran["output"]
    assert "a decision can't come from inside a Claude session" in ran["output"]
    assert "code (" not in ran["output"]
    assert status(item)["status"] == "pending"
