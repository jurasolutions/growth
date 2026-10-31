"""Fixtures and helpers shared by the scout and outreach tests.

Nothing here reaches the network: page fetches, DNS, Resend, Cloudflare and
IMAP are all replaced. `inputs/` and the site repo point at temporary folders.
"""

from __future__ import annotations

import json
from email.message import EmailMessage
from email.utils import format_datetime

import httpx
import pytest
import yaml

from jura_growth import config, paths, timeutil
from jura_growth.agents.outreach import queue as queue_mod
from jura_growth.agents.outreach import replies, send
from jura_growth.agents.scout import contact, leads, settings

MONDAY_10AM = "2026-10-26T10:00:00+08:00"

REGISTRY = [
    {"slug": "quote-builder", "name": "Quote builder", "description": "Turn a job into a PDF quote", "category": "Sales", "tier": "browser", "status": "live", "added": "2026-10-20", "prd": "APP-001"},
    {"slug": "invoice-checker", "name": "Invoice checker", "description": "Flag missing invoice details", "category": "Finance", "tier": "browser", "status": "live", "added": "2026-10-21", "prd": "APP-002"},
    {"slug": "timesheet-tidy", "name": "Timesheet tidy", "description": "Hours into a payroll summary", "category": "HR", "tier": "browser", "status": "live", "added": "2026-10-22", "prd": "APP-003"},
    {"slug": "delivery-order-maker", "name": "Delivery order maker", "description": "Orders into PDF delivery orders", "category": "Documents", "tier": "browser", "status": "live", "added": "2026-10-23", "prd": "APP-004"},
    {"slug": "booking-sheet", "name": "Booking sheet", "description": "A day's bookings in one table", "category": "Admin", "tier": "browser", "status": "live", "added": "2026-10-23", "prd": "APP-005"},
    {"slug": "receipt-sorter", "name": "Receipt sorter", "description": "Not live yet", "category": "Finance", "tier": "ai", "status": "draft", "added": "2026-10-24", "prd": "APP-006"},
]


def _refuse_network(request):
    raise AssertionError(f"unexpected network call in a test: {request.method} {request.url}")


def blocked_client(**kwargs) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(_refuse_network))


@pytest.fixture(autouse=True)
def scout_env(isolated, monkeypatch):
    return prepare_scout(isolated, monkeypatch)


def prepare_scout(tmp, monkeypatch):
    """What `scout_env` sets up, for code that isn't a test module (a gate adapter)."""
    inputs = tmp / "inputs"
    inputs.mkdir()
    (inputs / "icp.md").write_text("# ICP\n\n## Industries\n\n- logistics and delivery\n- events\n- property agencies\n")
    site = tmp / "site"
    (site / "src" / "apps").mkdir(parents=True)
    (site / "src" / "apps" / "registry.json").write_text(json.dumps(REGISTRY))
    monkeypatch.setenv("JURA_INPUTS_DIR", str(inputs))
    monkeypatch.setenv("JURA_SITE_REPO", str(site))
    for name in (
        "RESEND_API_KEY_OUTREACH", "UNSUBSCRIBE_SECRET", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID",
        "D1_DATABASE_ID", "OUTREACH_IMAP_HOST", "OUTREACH_IMAP_USER", "OUTREACH_IMAP_PASSWORD", "OUTREACH_IMAP_PORT",
        "ENQUIRY_IMAP_HOST", "ENQUIRY_IMAP_USER", "ENQUIRY_IMAP_PASSWORD", "ENQUIRY_IMAP_PORT",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(contact, "http_client", blocked_client)
    monkeypatch.setattr(send, "resend_client", blocked_client)
    monkeypatch.setattr(contact, "resolve_mx", lambda domain: [f"mx.{domain}"])

    def no_imap(host, port):
        raise AssertionError("unexpected IMAP connection in a test")

    monkeypatch.setattr(replies, "imap_factory", no_imap)
    monkeypatch.setattr(send, "chance", lambda: 0.0)
    configure(monkeypatch)
    return tmp


# The go-live settings every scout and outreach test starts from, whatever config/scout.yaml
# ships: shadow mode, no legal review, no sending domain, the code's default sender. A test
# that needs live sending (or any other value here) says so in its `configure(...)` call, so
# flipping the shipped file never changes what a behaviour test checks. The shipped values
# themselves are checked in test_outreach_approval.py.
TEST_BASELINE = {
    "mode": "shadow",
    "legal_review_done": False,
    "sending_domain": None,
    "from_local_part": "tingyu",
}


def configure(monkeypatch, **overrides) -> dict:
    """Use config/scout.yaml, with TEST_BASELINE and then `overrides` merged in."""
    base = yaml.safe_load((paths.config_dir() / "scout.yaml").read_text(encoding="utf-8")) or {}
    merged = settings._merge(settings._merge(base, TEST_BASELINE), overrides)
    monkeypatch.setattr(config, "agent_config", lambda agent: merged if agent == "scout" else {})
    return merged


def at(monkeypatch, moment: str) -> None:
    monkeypatch.setenv("JURA_GROWTH_NOW", moment)


def pages(mapping: dict) -> httpx.Client:
    """A client serving `{url: html}` (or `{url: (status, html)}`); anything else is 404."""

    def handler(request):
        key = str(request.url)
        value = mapping.get(key) or mapping.get(key.rstrip("/"))
        if value is None:
            return httpx.Response(404, text="not found")
        status, body = value if isinstance(value, tuple) else (200, value)
        return httpx.Response(status, text=body, headers={"content-type": "text/html; charset=utf-8"})

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def contact_page(email: str) -> str:
    return f"<html><body><h1>Contact us</h1><p>Email <a href='mailto:{email}'>{email}</a></p></body></html>"


NAMES = ["Alder", "Birch", "Cedar", "Dove", "Elm", "Fern", "Grove", "Hazel", "Iris", "Juniper", "Kestrel", "Linden",
         "Maple", "Nutmeg", "Olive", "Pine", "Quill", "Rowan", "Sage", "Teak", "Umber", "Violet", "Willow", "Yarrow", "Zinnia"]


def name_of(n: int) -> str:
    return NAMES[(n - 1) % len(NAMES)] + ("" if n <= len(NAMES) else f" {chr(64 + (n - 1) // len(NAMES))}")


def domain_of(n: int) -> str:
    return name_of(n).lower().replace(" ", "") + "logistics.sg"


def lead_data(n: int = 1, **overrides) -> dict:
    domain = overrides.pop("domain", domain_of(n))
    data = {
        "company": f"{name_of(n)} Logistics Pte Ltd",
        "website": f"https://www.{domain}",
        "industry": "logistics and delivery",
        "size_signal": "about 20 drivers on the team page",
        "what_they_do": "Same-day delivery for retailers",
        "observations": ["Delivery orders are signed on paper and scanned back each evening"],
        "source_urls": [f"https://www.{domain}/about"],
        "score": 72,
        "score_reasons": ["Logistics is in the ICP", "Paper delivery orders"],
        "tool": "delivery-order-maker",
        "contact": {"email": f"info@{domain}", "source_url": f"https://www.{domain}/contact"},
    }
    data.update(overrides)
    return data


def add(conn, data: dict, page_html: str | None = None):
    email = (data.get("contact") or {}).get("email")
    source = (data.get("contact") or {}).get("source_url")
    mapping = {source: page_html if page_html is not None else contact_page(email)} if source else {}
    return leads.add_lead(conn, data, client=pages(mapping))


def body_for(company: str, tool: str = "delivery-order-maker") -> str:
    return (
        "Hi there,\n\n"
        f"I read on the {company} site that delivery orders are signed on paper and scanned back to the "
        "office at the end of each day. We've made a free delivery order maker that fills in an order "
        f"from a few details and keeps it as a clean PDF: jurasolutions.sg/apps/{tool}\n\n"
        "It sits with our other small tools at jurasolutions.sg/apps. There's nothing to install, and what "
        "you enter stays in your browser.\n\n"
        "We're Jura Solutions, a small automation consultancy (jurasolutions.sg). If your team spends "
        "evenings retyping orders, I'd be glad to hear how it works today on a 30-minute call."
    )


def seed(conn, n: int = 1, *, queue: bool = True, **overrides) -> dict:
    """A lead with a verified address and (by default) a queued first email."""
    data = lead_data(n, **overrides)
    outcome = add(conn, data)
    assert outcome.status == "added", outcome.reasons
    result = {"lead_id": outcome.lead_id, "email": outcome.contact["email"], "domain": leads.contact.site_domain(data["website"])}
    if queue:
        name = leads.display_name(data["company"])
        queued = queue_mod.queue(
            conn,
            outcome.lead_id,
            {"subject": f"A free delivery order maker for {name}", "body": body_for(name), "tool": "delivery-order-maker"},
        )
        assert queued.status == "queued", queued.reasons
        result["message_id"] = queued.message_id
    return result


def outbox(channel: str | None = None) -> list[dict]:
    path = paths.data_dir() / "discord-outbox" / f"{timeutil.today_str()}.jsonl"
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return [r for r in rows if channel is None or r["channel"] == channel]


# --- D1 and Resend fakes ---------------------------------------------------


def d1_env(monkeypatch) -> None:
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cf-test-token-not-real")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("D1_DATABASE_ID", "db")


def fake_d1(monkeypatch, rows_or_handler) -> list:
    """Route cloudflare.query through a MockTransport serving `rows` (or a handler)."""
    from jura_growth import cloudflare

    calls = []
    real = getattr(cloudflare.query, "__wrapped__", cloudflare.query)

    def handler(request):
        calls.append(json.loads(request.content))
        if callable(rows_or_handler):
            return rows_or_handler(request)
        return httpx.Response(200, json={"success": True, "result": [{"results": list(rows_or_handler)}]})

    mock = httpx.Client(transport=httpx.MockTransport(handler))

    def query(sql, params=None, client=None):
        return real(sql, params, client=mock)

    query.__wrapped__ = real
    monkeypatch.setattr(cloudflare, "query", query)
    return calls


def buttons(monkeypatch, on: bool = True) -> None:
    """Set `approvals.discord_buttons` in the settings the code reads (ticket 15's switch)."""
    patched = dict(config.settings())
    patched["approvals"] = {**(patched.get("approvals") or {}), "discord_buttons": on}
    monkeypatch.setattr(config, "settings", lambda: patched)


def live_ready(monkeypatch, *, d1_rows=(), approval_buttons=True) -> list:
    """Every live-mode pre-condition holds. With `approval_buttons`, Ting Yu
    has checked the Discord buttons and set `approvals.discord_buttons: true`,
    the last line `live_problems()` lists (MC-06)."""
    configure(monkeypatch, mode="live", legal_review_done=True, sending_domain="hello.jurasolutions.sg")
    buttons(monkeypatch, approval_buttons)
    monkeypatch.setenv("RESEND_API_KEY_OUTREACH", "re_test_key_not_real_123456")
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "test-secret")
    d1_env(monkeypatch)
    (paths.inputs_dir() / "do-not-contact.csv").write_text("company,domain,reason\nZOLL Medical Singapore,,Ting Yu's choice\n")
    return fake_d1(monkeypatch, d1_rows)


# --- approvals: Ting Yu's decisions, as Dispatch delivers them (ADR 0004) --------------

CONTROL_ID = "111"  # CONTROL_DISCORD_USER_ID in the tests


def decide(conn, approval, decision: str = "approve", monkeypatch=None):
    """Ting Yu's decision on one request, through the only origin that decides."""
    from jura_growth import approvals
    from jura_growth.origin import Origin

    if monkeypatch is not None:
        monkeypatch.setenv("CONTROL_DISCORD_USER_ID", CONTROL_ID)
    return approvals.decide(conn, approval.id, decision, actor=f"discord:{CONTROL_ID}", origin=Origin.ssh(),
                            source_ref=None, args={})


def outreach_requests(conn, status: str | None = None) -> list:
    from jura_growth import approvals

    rows = conn.execute("SELECT * FROM approvals WHERE kind = 'outreach-email' ORDER BY id").fetchall()
    found = [approvals.Approval.from_row(r) for r in rows]
    return [a for a in found if status is None or a.status == status]


def approve_due(conn, monkeypatch) -> list:
    """The approval fixture for live sending (AC-M8.12): raise today's requests up to the
    remaining quota, as `send-due` would, and approve every pending one."""
    from jura_growth.agents.outreach import approval

    approval.raise_due(conn)
    answers = [decide(conn, a, "approve", monkeypatch) for a in outreach_requests(conn, "pending")]
    assert all(a.answer == "recorded" for a in answers), [a.text for a in answers]
    return answers


def fake_resend(monkeypatch, responder=None) -> list:
    sent = []

    def handler(request):
        sent.append(request)
        if responder:
            return responder(request)
        return httpx.Response(200, json={"id": f"re-msg-{len(sent)}"})

    monkeypatch.setattr(send, "resend_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    return sent


# --- IMAP fake -------------------------------------------------------------


def reply_message(sender: str, *, when: str, body: str, subject: str = "Re: A free tool", auto: str | None = None, message_id: str | None = None) -> bytes:
    message = EmailMessage()
    message["From"] = f"Someone <{sender}>"
    message["To"] = "levi@jurasolutions.sg"
    message["Subject"] = subject
    message["Date"] = format_datetime(timeutil.parse(when))
    message["Message-ID"] = message_id or f"<{abs(hash((sender, when, body)))}@example.test>"
    if auto:
        message["Auto-Submitted"] = auto
    message.set_content(body)
    return message.as_bytes()


class FakeIMAP:
    def __init__(self, messages: list[bytes]):
        self.messages = messages
        self.readonly = None
        self.logged_in = False
        self.fetch_specs: list[str] = []

    def login(self, user, password):
        self.logged_in = True
        return "OK", [b"logged in"]

    def select(self, mailbox, readonly=False):
        self.readonly = readonly
        return "OK", [str(len(self.messages)).encode()]

    def search(self, charset, *criteria):
        return "OK", [b" ".join(str(i + 1).encode() for i in range(len(self.messages)))]

    def fetch(self, numbers, spec):
        self.fetch_specs.append(spec)
        parts = []
        for number in str(numbers).split(","):
            raw = self.messages[int(number) - 1]
            if "HEADER.FIELDS" in spec:
                headers = raw.split(b"\n\n", 1)[0] + b"\n\n"
                meta = f"{int(number)} (RFC822.SIZE {len(raw)} BODY[HEADER.FIELDS (FROM DATE)] {{{len(headers)}}}".encode()
                parts += [(meta, headers), b")"]
            else:
                meta = f"{int(number)} (BODY[] {{{len(raw)}}}".encode()
                parts += [(meta, raw), b")"]
        return "OK", parts

    def logout(self):
        return "BYE", [b""]


def imap_env(monkeypatch, messages: list[bytes]) -> FakeIMAP:
    monkeypatch.setenv("OUTREACH_IMAP_HOST", "imap.example.test")
    monkeypatch.setenv("OUTREACH_IMAP_USER", "levi@jurasolutions.sg")
    monkeypatch.setenv("OUTREACH_IMAP_PASSWORD", "app-password")
    fake = FakeIMAP(messages)
    monkeypatch.setattr(replies, "imap_factory", lambda host, port: fake)
    return fake
