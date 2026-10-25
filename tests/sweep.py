"""The sweep: nothing planted reaches Discord (AC-M11.1, AC-M12.1).

A ticket that builds a Discord message plants `SECRETS` or `PERSONAL` (or both, through
`planted()`) in the rows, files and outputs its builder reads, runs the builder with the
Discord double, then calls

    assert_clean(discord_double, outbox_dir(), planted())

from its own test file. Nobody edits a shared list here: a ticket with its own planted value
builds its own `Planted`.

`assert_clean` first asserts that the double received the marker, so a sweep over a path that
posted nothing fails instead of passing by default.
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from jura_growth import config, paths

MARKER = "sweep-marker-7c1f"

# Dataset D2 (test strategy v3 §3).
RESEND_KEY = "re_uat_9Xq7Lm2Pz"
KEYCHAIN_VALUE = "kc_uat_44Lw"
AWKWARD = 'pw&<"Zq81xT9'
SECRETS = (RESEND_KEY, KEYCHAIN_VALUE, AWKWARD)
ENV_FILE = (
    f"RESEND_API_KEY_OUTREACH={RESEND_KEY}\n"
    "UNSUBSCRIBE_SECRET=keychain:jura-growth-uat\n"
    f"OUTREACH_IMAP_PASSWORD='{AWKWARD}'\n"
    "CONTROL_DISCORD_USER_ID=111\n"
)
KEYCHAIN = {"jura-growth-uat": KEYCHAIN_VALUE}

# Dataset D3.
NAMED_ADDRESS = "jane.tan@example.com.sg"
MASKED_ADDRESS = "j***@example.com.sg"
SOURCE_PAGE = "https://example.com.sg/about-us"
PHONE = "+65 9123 4567"
PERSON = "Jane Tan"  # recognised through the named contact: plant `NAMED_ADDRESS` as a contact too
PERSONAL = (NAMED_ADDRESS, PHONE, PERSON)
# A reply's body is never stored, and no agent reads the mailbox: it exists only in the process
# that checked for replies, which registers it (`privacy.never_show`). Plant it there.
REPLY = "Please take us off your list"


@dataclass
class Planted:
    marker: str = MARKER
    secrets: tuple[str, ...] = ()
    personal: tuple[str, ...] = ()
    expected: tuple[str, ...] = field(default_factory=tuple)  # must reach the double, as written

    def text(self) -> str:
        """One string holding every planted value, to put wherever a builder reads text."""
        return " ".join([self.marker, *self.secrets, *self.personal])


@pytest.fixture
def d2_secrets(tmp_path, monkeypatch):
    """The D2 env file and the Keychain double (test strategy v3 §2): `keychain:jura-growth-uat`
    resolves to `KEYCHAIN_VALUE`, and a real `security` call fails the test. Import it next to
    `discord_double` to use it."""
    env = tmp_path / "uat.env"
    env.write_text(ENV_FILE)
    env.chmod(0o600)
    monkeypatch.setenv("JURA_GROWTH_ENV_FILE", str(env))
    monkeypatch.setattr(config, "_keychain", KEYCHAIN.get)
    real_run = subprocess.run

    def run(args, *rest, **kwargs):
        assert not (isinstance(args, (list, tuple)) and args and args[0] == "security"), "the real Keychain was asked"
        return real_run(args, *rest, **kwargs)

    monkeypatch.setattr(subprocess, "run", run)
    config.reset_caches()


def planted(*, secrets: bool = True, personal: bool = True) -> Planted:
    return Planted(secrets=SECRETS if secrets else (), personal=PERSONAL if personal else ())


def outbox_dir() -> Path:
    return paths.data_dir() / "discord-outbox"


def assert_clean(double, outbox, planted: Planted) -> None:
    """No planted value, in any form, in anything the double saw or the outbox holds."""
    seen = double.texts()
    assert any(planted.marker in text for text in seen), (
        f"the Discord double never received the marker {planted.marker!r}: the sweep checked nothing"
    )
    haystacks = seen + _outbox_texts(outbox)
    for value in planted.secrets:
        for needle in _secret_needles(value):
            found = [h for h in haystacks if needle in h]
            assert not found, f"a piece of a planted secret ({needle!r}) reached Discord: {found[0][:300]!r}"
    for value in planted.personal:
        for pattern in _personal_patterns(value):
            found = [h for h in haystacks if pattern.search(h)]
            assert not found, f"planted personal data ({value!r}) reached Discord: {found[0][:300]!r}"
    for value in planted.expected:
        assert any(value in text for text in seen), f"{value!r} never reached the Discord double"


def _outbox_texts(outbox) -> list[str]:
    if outbox is None:
        return []
    if isinstance(outbox, (list, tuple)):
        return [json.dumps(record, ensure_ascii=False) for record in outbox] + [
            str(record.get("content", "")) for record in outbox
        ]
    path = Path(outbox)
    files = sorted(path.glob("*")) if path.is_dir() else [path] if path.exists() else []
    texts = []
    for file in files:
        raw = file.read_text(encoding="utf-8", errors="replace")
        texts.append(raw)
        for line in raw.splitlines():
            if line.strip():
                texts.append(str(json.loads(line).get("content", "")))
    return texts


def _secret_needles(value: str) -> set[str]:
    """The value raw, URL-encoded, HTML- and JSON-escaped, and every 8-character piece of each."""
    quoted = urllib.parse.quote(value, safe="")
    forms = {value, quoted, quoted.lower(), urllib.parse.quote_plus(value), html.escape(value), json.dumps(value)[1:-1]}
    needles = set(forms)
    for form in forms:
        needles |= {form[i : i + 8] for i in range(len(form) - 7)}
    return needles


def _personal_patterns(value: str) -> list[re.Pattern]:
    patterns = [re.compile(rf"(?<!\w){re.escape(value)}(?!\w)", re.I)]
    digits = re.sub(r"\D", "", value)
    if len(digits) >= 8:  # a phone number, however it is spaced
        patterns.append(re.compile(r"[\s()+-]*".join(digits[-8:])))
    return patterns
