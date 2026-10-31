"""QA 01 harness: one `/growth <text>` from Discord, as Dispatch and bin/growth-remote carry it.

usage: drive.py <label> <text typed after /growth>

Dispatch: words = [--actor, discord:<id>, --ref, <ref>, --json, --, *text.split()],
          ssh command = shlex.join(words)
growth-remote: shlex.split(SSH_ORIGINAL_COMMAND) -> jura-growth remote <words>
Here the last hop runs the real click CLI in this (fresh) process with the SSH origin passed in
process, because origin.detect_ssh() needs a root sshd ancestor. Prints a markdown block.
"""

import contextlib
import difflib
import io
import json
import os
import re
import shlex
import sys
import uuid

from jura_growth.cli import cli
from jura_growth.origin import Origin
from jura_growth.agents.apps import backlog

label, typed = sys.argv[1], sys.argv[2]
actor = os.environ.get("QA_ACTOR") or f"discord:{os.environ['CONTROL_DISCORD_USER_ID']}"
ref = f"{uuid.uuid4().int % 10**18}:{uuid.uuid4().int % 10**6}"
words = ["--actor", actor, "--ref", ref, "--json", "--", *typed.split()]
ssh_command = shlex.join(words)
argv = shlex.split(ssh_command, posix=True)

before = backlog.path().read_text(encoding="utf-8") if backlog.path().exists() else ""
out = io.StringIO()
with contextlib.redirect_stdout(out):
    try:
        cli.main(args=["remote", *argv], prog_name="jura-growth", standalone_mode=True, obj={"origin": Origin.ssh()})
        code = 0
    except SystemExit as stop:
        code = stop.code if isinstance(stop.code, int) else 0
after = backlog.path().read_text(encoding="utf-8") if backlog.path().exists() else ""
raw = out.getvalue()
try:
    body = json.loads(raw)
except ValueError:
    body = {"unparsed": raw}
text = body.get("text", raw)
diff = "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), "backlog before", "backlog after", n=0))

voice = []
if "!" in text:
    voice.append("exclamation mark")
if re.search("[\U0001F300-\U0001FAFF☀-➿]", text):
    voice.append("emoji")
if re.search(r"(?<!@)@(everyone|here)\b", text) or re.search(r"<@(?!​)", text):
    voice.append("LIVE MENTION")
digits = sorted(set(re.findall(r"\d[\d:.,-]*", text)))

print(f"### {label}\n")
print(f"- typed in Discord: `/growth {typed}`")
print(f"- ssh command (shlex.join): `{ssh_command}`")
print(f"- process exit code: {code}; JSON exit_code: {body.get('exit_code')}; answer: {body.get('answer')}; ok: {body.get('ok')}")
print(f"- voice lint: {', '.join(voice) or 'clean'}; figures in reply: {', '.join(digits) or 'none'}")
print("\nReply as Ting Yu reads it:\n\n```text\n" + text + "\n```\n")
print("Backlog diff:\n\n```diff\n" + (diff or "(unchanged)\n") + "```\n")
