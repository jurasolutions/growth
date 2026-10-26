"""The fake `claude` binary for the whole publish job (test strategy v3 §2; seam S10).

`install(tmp_path, monkeypatch)` gives the test its own config folder (a copy of `config/` with
Facebook in `browser` mode and `claude.binary` pointed at the fake), used by this process and by
every `jura-growth` the fake starts, and returns a `Fake`. `fake.scenario(steps, result)` sets
what the next run does. No Claude, no Chrome, no network.

The fake, started by `runner.run("publish")`:

- records its argv (`argv.json`), stdin (`stdin.txt`) and `JURA_GROWTH_RUN_ID` (`run-id.txt`);
- plays the scenario's steps in order, printing stream-json records as Claude Code would:
  - `{"chrome": tool, "input": {...}, "result": "...", "error": false, "denied": false}`: a Claude
    in Chrome call and its result, as written; nothing is opened;
  - `{"cli": [...]}`: `jura-growth <words>` as a real subprocess with the runner's environment
    (so `JURA_GROWTH_JOB` enforcement runs for real), recorded as a Bash call. Discord is off in
    the child (`JURA_GROWTH_DISCORD=off`), so its alerts land in the outbox. After
    `publish next --json` it opens growth.db read-only and records, in `claims.json`, whether the
    approval was already used and the item claimed when the command returned (G21);
  - `{"write": name, "text": "..."}`: a file in the publish scratch folder, as the Write tool;
  - `{"tamper": path}`: makes `path` writable and overwrites it, as a run that rewrote an image
    copy would;
- ends with the scenario's `result` text.

Placeholders in any string: `{A}` the claimed A-id, `{TEXT}` the approved text, `{IMG1}` the first
image copy (`{IMG2}`, `{IMG3}` … the later ones, for a carousel), `{WORK}` the scratch folder.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import yaml

import publish_world as pw
from jura_growth import config, paths

SCRIPT = r'''
import json, os, sqlite3, subprocess, sys
from pathlib import Path

home = Path(os.environ["FAKE_CLAUDE_HOME"])
(home / "argv.json").write_text(json.dumps(sys.argv[1:]))
(home / "stdin.txt").write_text(sys.stdin.read())
(home / "run-id.txt").write_text(os.environ.get("JURA_GROWTH_RUN_ID", ""))
scenario = json.loads((home / "scenario.json").read_text())
work = Path(os.environ["JURA_GROWTH_DATA_DIR"]) / "work" / "publish"
values = {"{WORK}": str(work)}
counter = [0]

def fill(value):
    if isinstance(value, str):
        for key, replacement in values.items():
            value = value.replace(key, replacement)
        return value
    if isinstance(value, list):
        return [fill(v) for v in value]
    if isinstance(value, dict):
        return {k: fill(v) for k, v in value.items()}
    return value

def emit(name, given, result, error=False):
    counter[0] += 1
    tool_id = "toolu_fake_%04d" % counter[0]
    print(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": tool_id, "name": name, "input": given}]}}), flush=True)
    print(json.dumps({"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_id, "is_error": error,
         "content": [{"type": "text", "text": result}]}]}}), flush=True)
    return tool_id

denials = []
print(json.dumps({"type": "system", "subtype": "init", "tools": []}), flush=True)
for step in scenario["steps"]:
    step = fill(step)
    if "chrome" in step:
        name = "mcp__claude-in-chrome__" + step["chrome"]
        tool_id = emit(name, step.get("input", {}), step.get("result", "ok"), step.get("error", False) or step.get("denied", False))
        if step.get("denied"):
            denials.append({"tool_name": name, "tool_use_id": tool_id, "tool_input": step.get("input", {})})
    elif "cli" in step:
        env = dict(os.environ, JURA_GROWTH_DISCORD="off")
        done = subprocess.run(["jura-growth", *step["cli"]], capture_output=True, text=True, env=env)
        output = done.stdout + done.stderr
        with open(home / "cli.jsonl", "a") as log:
            log.write(json.dumps({"cli": step["cli"], "exit": done.returncode, "output": output}) + "\n")
        emit("Bash", {"command": "jura-growth " + " ".join(step["cli"])}, output, done.returncode != 0)
        if step["cli"][:2] == ["publish", "next"] and "--json" in step["cli"] and done.returncode == 0:
            handed = json.loads(done.stdout)
            if handed.get("due"):
                values["{A}"] = handed["approval"]
                values["{TEXT}"] = handed["text"]
                values["{IMG1}"] = handed["images"][0] if handed["images"] else ""
                for number, image in enumerate(handed["images"][1:], start=2):
                    values["{IMG%d}" % number] = image
                db = sqlite3.connect(Path(os.environ["JURA_GROWTH_DATA_DIR"]).joinpath("growth.db").resolve().as_uri() + "?mode=ro", uri=True)
                used = db.execute("SELECT used_at, used_by_run FROM approvals WHERE id = ?", (int(handed["approval"].split("-")[1]),)).fetchone()
                state = db.execute("SELECT state FROM publish_items WHERE label = ?", (handed["item"],)).fetchone()
                db.close()
                (home / "claims.json").write_text(json.dumps({"used_at": used[0], "used_by_run": used[1], "state": state[0]}))
    elif "tamper" in step:
        target = Path(step["tamper"])
        os.chmod(target, 0o644)
        target.write_bytes(b"not the approved image")
        emit("Write", {"file_path": str(target), "content": "(bytes)"}, "File written")
    elif "unlink" in step:
        Path(step["unlink"]).unlink()
        emit("Write", {"file_path": step["unlink"], "content": "(removed)"}, "File removed")
    elif "write" in step:
        target = work / step["write"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(step["text"])
        emit("Write", {"file_path": str(target), "content": "(text)"}, "File created")
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": fill(scenario["result"]),
                  "total_cost_usd": 0.09, "num_turns": counter[0], "permission_denials": denials}), flush=True)
'''


class Fake:
    def __init__(self, home: Path, config_dir: Path):
        self.home = home
        self.config_dir = config_dir

    def scenario(self, steps: list[dict], result: str = "OK: done") -> None:
        (self.home / "scenario.json").write_text(json.dumps({"steps": steps, "result": result}))
        for name in ("argv.json", "stdin.txt", "claims.json", "cli.jsonl"):
            (self.home / name).unlink(missing_ok=True)

    @property
    def started(self) -> bool:
        return (self.home / "argv.json").exists()

    @property
    def argv(self) -> list[str]:
        return json.loads((self.home / "argv.json").read_text())

    @property
    def claims(self) -> dict:
        return json.loads((self.home / "claims.json").read_text())

    @property
    def cli(self) -> list[dict]:
        path = self.home / "cli.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def social(self, change) -> None:
        """Rewrite this test's `social.yaml` (both processes read it)."""
        _rewrite(self.config_dir / "social.yaml", change)
        config.reset_caches()


def _rewrite(path: Path, change) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def install(tmp_path: Path, monkeypatch, *, browser: bool = True) -> Fake:
    home = tmp_path / "fake-claude"
    home.mkdir()
    script = home / "claude"
    script.write_text(f"#!{sys.executable}\n" + SCRIPT)
    script.chmod(0o755)
    config_dir = tmp_path / "config"
    shutil.copytree(paths.REPO_ROOT / "config", config_dir)

    def settings(data):
        data["claude"]["binary"] = str(script)

    def social(data):
        data["platforms"]["facebook"]["publish_mode"] = "browser" if browser else "draft"
        data["platforms"]["facebook"]["page_url"] = pw.PAGE_URL

    _rewrite(config_dir / "settings.yaml", settings)
    _rewrite(config_dir / "social.yaml", social)
    monkeypatch.setenv("JURA_GROWTH_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("FAKE_CLAUDE_HOME", str(home))
    config.reset_caches()
    return Fake(home, config_dir)
