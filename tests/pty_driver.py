"""Run a command under a fresh pseudo-terminal, outside the test's own process tree (seam S13).

The suite may itself run under Claude Code, which `origin.detect()` rightly refuses as an
ancestor. So the driver forks and lets its parent exit at once: the child is adopted by launchd
(pid 1) and its new session has no `claude` above it, as in Ting Yu's own Terminal. With
`under_claude`, it then puts a process whose command name is `claude` between itself and the
command, which is the case the check must refuse.

    python tests/pty_driver.py '{"argv": [...], "type": "3f9a1c", "result": "/tmp/x.json", "under_claude": false}'

When the command prints a prompt asking for a code, the driver types `type` and Enter. It writes
`{"exit": <code>, "output": <text>}` to `result` when the command ends.
"""

from __future__ import annotations

import json
import os
import pty
import select
import subprocess
import sys
import time


def run_under_pty(spec: dict) -> None:
    pid, fd = pty.fork()
    if pid == 0:
        os.execv(spec["argv"][0], spec["argv"])
    output, typed = b"", False
    end = time.time() + 60
    while time.time() < end:
        ready, _, _ = select.select([fd], [], [], 0.2)
        if not ready:
            continue
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            break  # the command ended and closed the terminal
        if not chunk:
            break
        output += chunk
        if not typed and spec.get("type") is not None and b"code (" in output:
            os.write(fd, (spec["type"] + "\n").encode())
            typed = True
    _, status = os.waitpid(pid, 0)
    result = {"exit": os.waitstatus_to_exitcode(status), "output": output.decode("utf-8", "replace")}
    partial = spec["result"] + ".part"
    with open(partial, "w", encoding="utf-8") as handle:
        json.dump(result, handle)
    os.replace(partial, spec["result"])


def main() -> None:
    if sys.argv[1] == "--pty":
        run_under_pty(json.loads(sys.argv[2]))
        return
    spec = json.loads(sys.argv[1])
    if os.fork() > 0:
        os._exit(0)
    os.setsid()
    deadline = time.time() + 10
    while os.getppid() != 1 and time.time() < deadline:
        time.sleep(0.01)
    if spec.get("under_claude"):
        # argv[0] is what `ps -o comm=` shows on macOS.
        subprocess.call(["claude", os.path.abspath(__file__), "--pty", json.dumps(spec)], executable=sys.executable)
    else:
        run_under_pty(spec)
    os._exit(0)


if __name__ == "__main__":
    main()
