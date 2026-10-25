"""Shared helpers for tests that run jobs through `runner.run()` in process:
a fake `claude` binary, a patched job list and the JSONL mirror."""

import json
import stat

from jura_growth import config, paths

FAKE_CLAUDE_JOB = {"agent": "fake-agent", "kind": "claude", "prompt": "fake.md", "tools": ["WebSearch"], "schedule": {"daily": "06:00"}}


def fake_claude(tmp_path, result_text, *, is_error=False):
    """A stand-in `claude` binary. It saves its stdin to `stdin.txt` and the
    `JURA_GROWTH_RUN_ID` it was given to `run-id.txt` in `tmp_path`, and
    prints a stream-json transcript ending in `result_text`."""
    script = tmp_path / "fake-claude"
    record = {"type": "result", "subtype": "success", "is_error": is_error, "result": result_text, "total_cost_usd": 0.12}
    script.write_text(
        "#!/bin/sh\n"
        f"cat > {tmp_path}/stdin.txt\n"
        f'printf "%s" "$JURA_GROWTH_RUN_ID" > {tmp_path}/run-id.txt\n'
        f"echo '{{\"type\": \"system\", \"argv\": \"'\"$*\"'\"}}'\n"
        f"echo '{json.dumps(record)}'\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def settings_with(monkeypatch, *, fake=None, jobs=None, **claude):
    """config/settings.yaml with `claude` settings merged in, a claude job
    `fake` (with `fake` overrides merged into it), and `jobs` added last."""
    base = config.settings()
    patched = dict(base)
    patched["claude"] = {**base["claude"], **claude}
    patched["jobs"] = {**base["jobs"], "fake": {**FAKE_CLAUDE_JOB, **(fake or {})}, **(jobs or {})}
    monkeypatch.setattr(config, "settings", lambda: patched)
    return patched


def mirrored(kind):
    """The payloads of every `kind` event in the JSONL mirror, oldest first."""
    folder = paths.data_dir() / "runs"
    found = []
    for path in sorted(folder.glob("*.jsonl")) if folder.exists() else []:
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if record["kind"] == kind:
                found.append(record["payload"])
    return found
