"""`bin/growth-remote`, the SSH forced command (seam S14; MC §4.7; ticket 11, AC-M10.3).

The wrapper is copied into a temp layout beside an argv recorder standing in for
`.venv/bin/jura-growth`, and run as a real process with `SSH_ORIGINAL_COMMAND` set. A sentinel
file shows whether any shell ran the words.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from jura_growth import paths

WRAPPER = paths.REPO_ROOT / "bin" / "growth-remote"

RECORDER = """#!{python}
import json, sys
from pathlib import Path
Path(__file__).with_name("argv.json").write_text(json.dumps(sys.argv[1:]))
sys.exit({code})
"""


@pytest.fixture
def layout(tmp_path):
    """<tmp>/repo/bin/growth-remote and <tmp>/repo/.venv/bin/jura-growth (the recorder)."""
    repo = tmp_path / "repo"
    (repo / "bin").mkdir(parents=True)
    shutil.copy2(WRAPPER, repo / "bin" / "growth-remote")
    venv = repo / ".venv" / "bin"
    venv.mkdir(parents=True)
    recorder = venv / "jura-growth"

    def record(code: int = 0) -> None:
        recorder.write_text(RECORDER.format(python=sys.executable, code=code))
        recorder.chmod(0o755)

    record()
    return {"repo": repo, "record": record, "argv": venv / "argv.json"}


def run(layout, command: str | None, cwd: Path | None = None):
    env = {k: v for k, v in os.environ.items() if k != "SSH_ORIGINAL_COMMAND"}
    if command is not None:
        env["SSH_ORIGINAL_COMMAND"] = command
    return subprocess.run([str(layout["repo"] / "bin" / "growth-remote")], capture_output=True, text=True,
                          env=env, cwd=cwd, timeout=60)


def recorded(layout) -> list[str] | None:
    path = layout["argv"]
    return json.loads(path.read_text()) if path.exists() else None


def test_the_words_reach_jura_growth_remote_split_without_a_shell(layout):
    words = ["--actor", "discord:111", "--ref", "123:dlv-7", "--json", "--", "approve", "A-0412", "it's", "fine, \"really\""]
    ran = run(layout, shlex.join(words))
    assert ran.returncode == 0, ran.stderr
    assert recorded(layout) == ["remote", *words]


def test_hostile_words_arrive_as_literal_words_and_run_nothing(layout, tmp_path):
    sentinel = tmp_path / "sentinel"
    words = ["--", "skip", "A-0001", ";", "touch", str(sentinel), "&&", f"$(touch {sentinel})", f"`touch {sentinel}`",
             f"a\ntouch {sentinel}", "|", f"> {sentinel}"]
    ran = run(layout, shlex.join(words), cwd=tmp_path)
    assert ran.returncode == 0, ran.stderr
    assert recorded(layout) == ["remote", *words]
    assert not sentinel.exists()


def test_unquoted_shell_text_is_only_split_into_words(layout, tmp_path):
    sentinel = tmp_path / "sentinel"
    ran = run(layout, f"-- status; touch {sentinel} && echo $(touch {sentinel}) `touch {sentinel}`\ntouch {sentinel}",
              cwd=tmp_path)
    assert ran.returncode == 0, ran.stderr
    argv = recorded(layout)
    assert argv[:3] == ["remote", "--", "status;"] and "$(touch" in argv and "`touch" in argv
    assert not sentinel.exists()


def test_jura_growths_exit_code_is_the_wrappers(layout):
    layout["record"](code=6)
    assert run(layout, "-- skip A-0001").returncode == 6


@pytest.mark.parametrize("command", [None, "", "   ", "-- approve A-0001 'unbalanced"], ids=["unset", "empty", "blank", "bad-quote"])
def test_no_command_or_one_that_cant_be_split_is_refused_and_runs_nothing(layout, command):
    ran = run(layout, command)
    assert ran.returncode == 2
    assert ran.stdout.startswith("refused:")
    assert recorded(layout) is None


def test_the_wrapper_never_invokes_a_shell():
    """E6: no shell, no eval, no subprocess: the words go to one exec of jura-growth."""
    source = WRAPPER.read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    for banned in ("sh -c", "bash -c", "eval", "shell=True", "os.system", "subprocess", "popen", "exec(", "os.execvp"):
        assert banned not in code.replace("os.execv(", ""), banned
    assert "os.execv(" in code and "shlex.split(" in code
    assert os.access(WRAPPER, os.X_OK)


def test_the_wrapper_runs_on_the_system_python():
    """Under the forced command PATH is the system's; the wrapper must run on macOS's own python3."""
    first = WRAPPER.read_text(encoding="utf-8").splitlines()[0]
    assert first == "#!/usr/bin/env -S python3 -I"
    source = WRAPPER.read_text(encoding="utf-8")
    assert not re.search(r"\bmatch\b .*:$|:=", source, re.M), "keep it to Python 3.9 syntax"
