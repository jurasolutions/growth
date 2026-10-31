"""What the inbox tests share: raw mail, a strict IMAP double and the mailbox environment.

The double is the proof of W1: it answers only what a read needs. `select` without `readonly`,
any fetch that isn't `BODY.PEEK`, and every verb that changes a mailbox (`store`, `copy`, `move`,
`expunge`, `append`, `delete`, `create`, `rename`, `uid`) fail the test. Everything real about
the mail stays real: the code parses raw bytes, as it does from a server.
"""

from __future__ import annotations

import imaplib
import re
import sqlite3
from datetime import datetime
from email.message import EmailMessage
from email.utils import format_datetime, parsedate_to_datetime

from jura_growth import timeutil
from jura_growth.agents.outreach import replies

NOW = "2026-10-26T10:00:00+08:00"
DKIM_PASS = "mx.example.test; dkim=pass header.d=jurasolutions.sg; spf=pass"
DKIM_FAIL = "mx.example.test; dkim=fail header.d=jurasolutions.sg; spf=fail"

_serial = {"n": 0}


def raw_mail(sender: str = "Priya Nair <priya@clinic.example>", *, when: str = "2026-10-26T09:30:00+08:00",
             body: str = "Do you work with clinics?", subject: str = "A question about invoices",
             message_id: str | None = None, **headers) -> bytes:
    """One message as a server would hand it over. Extra keywords are headers, with `_` as `-`."""
    _serial["n"] += 1
    message = EmailMessage()
    message["From"] = sender
    message["To"] = "levi@jurasolutions.sg"
    message["Subject"] = subject
    message["Date"] = format_datetime(timeutil.parse(when))
    message["Message-ID"] = message_id or f"<m{_serial['n']}@mail.example>"
    for name, value in headers.items():
        message[name.replace("_", "-")] = value
    message.set_content(body)
    return message.as_bytes()


def enquiry_mail(*, name: str = "Jane Tan", visitor: str = "jane.tan@acme.example", message: str = "We retype every invoice.",
                 came_from: str | None = "apps/quote-builder", phone: str = "+65 9123 4567",
                 authentication: str = DKIM_PASS, **kwargs) -> bytes:
    """What `landing-page/functions/submit.js` sends, as it reaches the mailbox."""
    lines = [f"Name: {name}", f"Work email: {visitor}", f"Contact number: {phone}", "Company: Acme"]
    lines += [f"Came from: {came_from}"] if came_from else []
    lines += ["", "What they would like to automate:", message]
    return raw_mail("Jura Solutions <no_reply@jurasolutions.sg>", subject=f"Enquiry from {name} (Acme)",
                    body="\n".join(lines), Reply_To=visitor, Authentication_Results=authentication, **kwargs)


def triage_all(conn: sqlite3.Connection, kind: str = "thanks") -> int:
    """What triage does when it finds nothing to draft, for each waiting conversation, as `inbox submit`
    would, so a test about the report needn't start a run. Returns how many it answered."""
    from jura_growth.agents.inbox import store, triage

    newest = {item["conversation"]: item for item in store.waiting_for_triage(conn)}
    for item in newest.values():
        outcome = triage.submit(conn, {"id": store.label(item["id"]), "class": kind})
        assert outcome.exit_code == 0, outcome.text()
    return len(newest)


def trust_servers(monkeypatch, *servers: str) -> None:
    """As if `auth_servers` in `config/inbox.yaml` named these, by default the ids this file's mail
    uses. Patched where it is read, because the scout tests' `configure` replaces `agent_config`."""
    named = frozenset(servers or ("mx.example.test", "mx.zoho.com"))
    monkeypatch.setattr(replies, "_auth_servers", lambda: named)


class Forbidden(AssertionError):
    pass


class StrictIMAP:
    """A mailbox that can only be read, and that says so loudly."""

    def __init__(self, inbox: list[bytes] | None = None, junk: list[bytes] | None = None,
                 junk_name: str | None = "Junk"):
        self.folders = {"INBOX": list(inbox or [])}
        self.junk_name = junk_name
        if junk_name:
            self.folders[junk_name] = list(junk or [])
        self.current = "INBOX"
        self.verbs: list[str] = []
        self.selected: list[tuple[str, bool]] = []
        self.searches: list[tuple] = []
        self.fetch_specs: list[str] = []
        self.body_fetches = 0
        self.fail_at: dict[str, Exception] = {}
        self.refuse_headers = False  # a NO on the header FETCH
        self.refuse_bodies = False  # a NO on the body FETCH
        self.bodies_instead: dict[int, bytes] = {}  # the numbers shifted: this body answers that number
        self.watching: sqlite3.Connection | None = None
        self.logged_out = False

    @property
    def messages(self) -> list[bytes]:
        return self.folders["INBOX"]

    def watch(self, conn: sqlite3.Connection) -> None:
        """From now on, every network call fails if `conn` holds a transaction open (B5 rule 2)."""
        self.watching = conn

    def _call(self, verb: str) -> None:
        self.verbs.append(verb)
        if self.watching is not None and self.watching.in_transaction:
            raise AssertionError(f"a transaction was open across the network, at {verb}")
        if verb in self.fail_at:
            raise self.fail_at[verb]

    def login(self, user, password):
        self._call("login")
        return "OK", [b"logged in"]

    def list(self, *args):
        self._call("list")
        lines = [b'(\\HasNoChildren) "/" "INBOX"']
        if self.junk_name:
            lines.append(b'(\\HasNoChildren \\Junk) "/" "' + self.junk_name.encode() + b'"')
        return "OK", lines

    def select(self, mailbox="INBOX", readonly=False):
        self._call("select")
        if not readonly:
            raise Forbidden(f"select({mailbox!r}) without readonly: only EXAMINE is allowed")
        name = mailbox.strip('"')
        self.selected.append((name, readonly))
        if name not in self.folders:
            return "NO", [b"no such folder"]
        self.current = name
        return "OK", [str(len(self.folders[name])).encode()]

    def search(self, charset, *criteria):
        self._call("search")
        self.searches.append(criteria)
        since = None
        if len(criteria) >= 2 and criteria[0] == "SINCE":
            since = datetime.strptime(criteria[1], "%d-%b-%Y").date()
        found = []
        for number, raw in enumerate(self.folders[self.current], 1):
            match = re.search(rb"^Date: (.+)$", raw.split(b"\n\n", 1)[0], re.M)
            when = None
            if match:
                try:
                    when = parsedate_to_datetime(match.group(1).decode().strip()).date()
                except (TypeError, ValueError):
                    when = None
            if since is None or when is None or when >= since:
                found.append(str(number).encode())
        return "OK", [b" ".join(found)]

    def fetch(self, numbers, spec):
        self._call("fetch")
        self.fetch_specs.append(spec)
        if "PEEK" not in spec:
            raise Forbidden(f"fetch without BODY.PEEK marks mail read: {spec}")
        if self.refuse_headers if "HEADER.FIELDS" in spec else self.refuse_bodies:
            return "NO", [b"try again later"]
        partial = re.search(r"<0\.(\d+)>", spec)
        parts: list = []
        for number in str(numbers).split(","):
            raw = self.folders[self.current][int(number) - 1]
            if "HEADER.FIELDS" in spec:
                head = re.split(rb"\r?\n\r?\n", raw, maxsplit=1)[0] + b"\n\n"
                meta = f"{int(number)} (RFC822.SIZE {len(raw)} BODY[HEADER.FIELDS (FROM)] {{{len(head)}}}".encode()
                parts += [(meta, head), b")"]
            else:
                self.body_fetches += 1
                raw = self.bodies_instead.get(int(number), raw)
                sent = raw[: int(partial.group(1))] if partial else raw
                parts += [(f"{int(number)} (BODY[] {{{len(sent)}}}".encode(), sent), b")"]
        return "OK", parts

    def logout(self):
        self.logged_out = True
        return "BYE", [b""]

    def __getattr__(self, name):
        if name in {"store", "copy", "move", "expunge", "append", "delete", "create", "rename", "uid", "close",
                    "subscribe", "unsubscribe", "sort", "thread"}:
            raise Forbidden(f"the mailbox stays read-only: {name} was called")
        raise AttributeError(name)


REFUSED_LOGIN = imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Invalid credentials")


def mailbox_env(monkeypatch, inbox: list[bytes] | None = None, *, junk: list[bytes] | None = None,
                second: StrictIMAP | None = None, junk_name: str | None = "Junk") -> StrictIMAP:
    """The Reply-To mailbox set up with a strict double, and the second one if given."""
    monkeypatch.setenv("OUTREACH_IMAP_HOST", "imap.example.test")
    monkeypatch.setenv("OUTREACH_IMAP_USER", "levi@jurasolutions.sg")
    monkeypatch.setenv("OUTREACH_IMAP_PASSWORD", "app-password-not-real")
    fake = StrictIMAP(inbox, junk, junk_name)
    boxes = {"imap.example.test": fake}
    if second is not None:
        monkeypatch.setenv("ENQUIRY_IMAP_HOST", "imap.enquiry.test")
        monkeypatch.setenv("ENQUIRY_IMAP_USER", "info@jurasolutions.sg")
        monkeypatch.setenv("ENQUIRY_IMAP_PASSWORD", "other-password-not-real")
        boxes["imap.enquiry.test"] = second
    monkeypatch.setattr(replies, "imap_factory", lambda host, port: boxes[host])
    return fake
