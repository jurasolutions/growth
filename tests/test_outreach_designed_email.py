"""Scout PRD §5.6a: the designed email, Levi's signature, the call ask, and the
brand checker's required parts (amended 2026-10-31)."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

from click.testing import CliRunner

from jura_growth import brand_check
from jura_growth.agents.outreach import compose, send
from jura_growth.agents.scout import settings
from jura_growth.cli import cli

SECRET = "jura-test-secret-2026"
CALL_URL = "https://jurasolutions.sg/?from=outreach#contact"
MARK_URL = "https://jurasolutions.sg/email/jura-mark-96.png"
TOOLS = {"quote-builder", "invoice-checker"}

GOOD = (
    "Hi there,\n\n"
    "I was looking at Acme Aircon's servicing packages and saw that customers request quotes through a "
    "form and wait for a reply. We've made a free quote builder that turns a job into a clean PDF quote in "
    "a few minutes: jurasolutions.sg/apps/quote-builder\n\n"
    "It's one of a growing set of small tools at jurasolutions.sg/apps. No sign-up, and what you type "
    "stays in your browser.\n\n"
    "We're Jura Solutions, a small automation consultancy (jurasolutions.sg). If copying the same details "
    "between systems takes up part of your week, I'd be glad to hear how it works on a 30-minute call."
)


def make(body=GOOD, *, company="Acme Aircon", subject="A free quote builder for Acme Aircon"):
    return compose.compose(subject=subject, body=body, company=company, site="acmeaircon.sg",
                           email="info@acmeaircon.sg", secret=SECRET)


def gate(body=GOOD, **ctx):
    email = make(body)
    context = {"company": "Acme Aircon", "tools": TOOLS, "tool": "quote-builder", "kind": "first"} | ctx
    return brand_check.check(email.check_text, subject=email.subject, channel_name="email",
                             proper_nouns=["Acme Aircon"], context=context)


# --- a tiny HTML reader ------------------------------------------------------


class Node:
    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.parent, self.children, self.text = tag, dict(attrs), parent, [], ""

    def all_text(self) -> str:
        """The text as a reader sees it: block elements stand apart."""
        return self.text + "".join(
            (" " if c.tag in BLOCK else "") + c.all_text() + (" " if c.tag in BLOCK else "") + c.tail
            for c in self.children
        )

    tail = ""

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()

    def ancestors(self):
        node = self.parent
        while node is not None:
            yield node
            node = node.parent


VOID = {"meta", "img", "br", "hr", "link"}
BLOCK = {"p", "td", "tr", "table", "div", "br", "title", "style"}


class Tree(HTMLParser):
    def __init__(self, source: str):
        super().__init__(convert_charrefs=True)
        self.root = Node("root", [], None)
        self.at = self.root
        self.last = None
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.at)
        self.at.children.append(node)
        self.last = None
        if tag not in VOID:
            self.at = node
        else:
            self.last = node

    def handle_endtag(self, tag):
        node = self.at
        while node is not None and node.tag != tag:
            node = node.parent
        if node is not None and node.parent is not None:
            self.last = node
            self.at = node.parent

    def handle_data(self, data):
        if self.last is not None and self.last.parent is self.at:
            self.last.tail += data
        else:
            self.at.text += data

    def find(self, tag=None, **attrs):
        return [n for n in self.root.walk() if (tag is None or n.tag == tag)
                and all(n.attrs.get(k) == v for k, v in attrs.items())]

    def body(self) -> Node:
        return self.find("body")[0]


def visible_words(text: str) -> list[str]:
    """Words a reader sees, with links taken out (an href and a URL in the
    text are the same link written two ways)."""
    text = brand_check.URL_RE.sub(" ", text)
    text = brand_check.BARE_DOMAIN_RE.sub(" ", text)
    return re.findall(r"[A-Za-z0-9@'’.-]*[A-Za-z0-9]", text)


def link(tree: Tree, text: str, within: Node | None = None) -> Node:
    nodes = within.walk() if within is not None else tree.root.walk()
    found = [a for a in nodes if a.tag == "a" and a.all_text().strip() == text]
    assert len(found) == 1, f"expected one link reading {text!r}, found {len(found)}"
    return found[0]


# --- 1. the sender -----------------------------------------------------------


def test_sender_is_levi():
    assert settings.SENDER_NAME == "Levi Ting, Jura Solutions"
    assert settings.REPLY_TO == "levi@jurasolutions.sg"
    assert settings.SIGNATURE_NAME == "Levi Ting"


def test_from_address_uses_the_configured_local_part(monkeypatch):
    monkeypatch.setattr(settings, "get", lambda: {**settings.DEFAULTS, "from_local_part": "levi", "sending_domain": "jurasolutions.sg"})
    assert send.from_address() == '"Levi Ting, Jura Solutions" <levi@jurasolutions.sg>'


# --- 2. the plain-text part --------------------------------------------------


def test_plain_text_signature_exactly():
    assert compose.SIGNATURE == (
        "Levi Ting\n"
        "Principal Consultant\n"
        "Jura Solutions\n"
        "AUTOMATION CONSULTANCY\n"
        "levi@jurasolutions.sg\n"
        "jurasolutions.sg\n"
        "\n"
        f"We automate the repetitive parts of running a business. Book a discovery session → {CALL_URL}"
    )


def test_plain_text_order_body_button_signature_footer():
    email = make()
    body_at = email.text.index("I was looking at Acme Aircon")
    call_at = email.text.index(f"Book a 30-minute call: {CALL_URL}")
    sig_at = email.text.index(compose.SIGNATURE)
    footer_at = email.text.index("You're receiving this because Acme Aircon")
    assert body_at < call_at < sig_at < footer_at
    assert "Ting Yu" not in email.text


def test_model_sign_off_is_dropped():
    email = make(GOOD + "\n\nLevi Ting\nPrincipal Consultant\nJura Solutions")
    assert email.draft == GOOD
    assert email.text.count("Levi Ting") == 1


# --- 3. the HTML part --------------------------------------------------------


def test_call_button_links_the_enquiry_page_from_outreach():
    tree = Tree(make().html)
    button = link(tree, "Book a 30-minute call")
    href = urlsplit(button.attrs["href"])
    assert (href.scheme, href.netloc, href.path, href.fragment) == ("https", "jurasolutions.sg", "/", "contact")
    assert parse_qs(href.query)["from"] == ["outreach"]
    style = button.attrs["style"].replace(" ", "")
    assert "color:#ffffff" in style and "text-decoration:none" in style
    cell = next(a for a in button.ancestors() if a.tag == "td")
    assert "#0f5132" in (cell.attrs.get("style", "") + cell.attrs.get("bgcolor", "")).lower()


def test_signature_block_fields_exactly():
    tree = Tree(make().html)
    [mark] = tree.find("img")
    assert mark.attrs["src"] == MARK_URL and mark.attrs["alt"] == "Jura Solutions"
    assert mark.attrs["width"] == "48" and mark.attrs["height"] == "48"
    signature = next(n for n in tree.root.walk() if n.attrs.get("id") == "signature")
    words = re.sub(r"\s+", " ", signature.all_text()).strip()
    assert words == (
        "Levi Ting Principal Consultant Jura Solutions AUTOMATION CONSULTANCY "
        "levi@jurasolutions.sg jurasolutions.sg "
        "We automate the repetitive parts of running a business. Book a discovery session →"
    )
    name = next(n for n in signature.walk() if n.all_text().strip() == "Levi Ting" and n.tag != "a")
    assert "font-weight:600" in name.attrs.get("style", "").replace(" ", "") or name.tag in ("strong", "b")
    jura = next(n for n in signature.walk() if n.tag in ("strong", "b", "span") and n.all_text() == "Jura")
    assert jura.tag in ("strong", "b") or "font-weight:600" in jura.attrs.get("style", "").replace(" ", "")
    rule = next(n for n in signature.walk() if n.attrs.get("id") == "signature-rule")
    assert "#0f5132" in rule.attrs.get("style", "").lower()
    assert link(tree, "levi@jurasolutions.sg", signature).attrs["href"] == "mailto:levi@jurasolutions.sg"
    assert link(tree, "jurasolutions.sg", signature).attrs["href"].startswith("https://jurasolutions.sg/?utm_source=outreach")
    session = link(tree, "Book a discovery session →")
    assert session.attrs["href"].startswith("https://jurasolutions.sg/?from=outreach") and session.attrs["href"].endswith("#contact")
    hairline = next(n for n in signature.walk() if n.attrs.get("id") == "signature-hairline")
    assert "border-top:1px solid #dfe3e0" in hairline.attrs["style"].replace(": ", ":")


def test_footer_in_small_grey_text_below_the_signature():
    html_text = make().html
    tree = Tree(html_text)
    footer = next(n for n in tree.root.walk() if n.attrs.get("id") == "footer")
    style = footer.attrs["style"].replace(" ", "")
    assert "font-size:13px" in style and "color:#6f7973" in style
    text = re.sub(r"\s+", " ", footer.all_text())
    assert "You're receiving this because Acme Aircon lists this address for business enquiries on acmeaircon.sg." in text
    assert 'or reply "unsubscribe"' in text
    assert link(tree, "Unsubscribe here").attrs["href"] == compose.unsubscribe_url("info@acmeaircon.sg", SECRET)
    assert link(tree, "jurasolutions.sg/privacy").attrs["href"] == "https://jurasolutions.sg/privacy"
    assert html_text.index('id="signature"') < html_text.index('id="footer"')


def test_plain_text_carries_the_same_words_and_links():
    email = make()
    tree = Tree(email.html)
    assert visible_words(tree.body().all_text()) == visible_words(email.text)
    hrefs = {a.attrs["href"].split("?")[0].split("#")[0] for a in tree.find("a")}
    for href in hrefs:
        if href.startswith("mailto:"):
            assert href.removeprefix("mailto:") in email.text
        else:
            assert href.removeprefix("https://") in email.text, href


def test_one_column_600px_table_layout_with_inline_styles():
    html_text = make().html
    tree = Tree(html_text)
    assert "max-width:600px" in html_text.replace(" ", "")
    assert all(t.attrs.get("role") == "presentation" for t in tree.find("table"))
    assert not tree.find("div", **{}) or all("style" in d.attrs for d in tree.find("div"))
    for node in tree.body().walk():
        if node.tag in ("table", "td", "p", "a", "img", "span", "strong", "div"):
            assert node.attrs.get("style"), f"<{node.tag}> has no inline style"
    assert tree.find("meta", name="viewport") and tree.find("meta", name="color-scheme")


def test_holds_up_in_dark_mode_and_on_a_phone():
    html_text = make().html
    style = Tree(html_text).find("style")[0].all_text()
    assert "prefers-color-scheme: dark" in style and "[data-ogsc]" in style
    assert re.search(r"@media[^{]*max-width:\s*600px", style)


def test_no_svg_attachment_or_tracking_pixel():
    email = make()
    lowered = email.html.lower()
    assert "<svg" not in lowered and ".svg" not in lowered and "data:" not in lowered and "cid:" not in lowered
    images = Tree(email.html).find("img")
    assert [i.attrs["src"] for i in images] == [MARK_URL]
    assert len(email.html.encode("utf-8")) < 20_000


def test_no_phone_number_in_any_part():
    email = make()
    phone = re.compile(r"(?:\+\s?65[\s-]?)?\b[3689]\d{3}[\s-]?\d{4}\b|tel:", re.I)
    for part in (email.subject, email.text, email.html, compose.SIGNATURE):
        assert not phone.search(part), phone.search(part)
        assert "9276" not in part and "+65" not in part


def test_resend_payload_has_no_attachments():
    from jura_growth.agents.scout import settings as scout_settings

    payload = send.resend_payload({"id": 7}, {"email": "info@acmeaircon.sg"}, make())
    assert "attachments" not in payload and payload["reply_to"] == scout_settings.REPLY_TO


# --- 4. the brand checker's required parts -----------------------------------


def has(result, fragment):
    return any(fragment in r for r in result.reasons())


def test_good_email_passes_and_is_under_150_words():
    result = gate()
    assert result.passed, result.reasons()
    assert compose.word_count(GOOD) < 150


def test_missing_the_toolbox_fails():
    body = GOOD.replace("small tools at jurasolutions.sg/apps.", "small tools we keep.")
    assert has(gate(body), "jurasolutions.sg/apps exactly once")


def test_missing_the_call_ask_fails():
    body = GOOD.replace("I'd be glad to hear how it works on a 30-minute call.", "reply and tell me how it works.")
    assert has(gate(body), "30-minute call")


def test_missing_the_website_fails():
    body = GOOD.replace(" (jurasolutions.sg)", "")
    assert has(gate(body), "Mention the website")


def test_over_150_words_fails():
    body = GOOD + "\n\n" + " ".join(["We map the process first and keep the documentation with you."] * 5)
    assert has(gate(body), "keep it under 150")


def test_missing_call_button_fails_when_checked_raw():
    email = make()
    without = email.check_text.replace(compose.CALL_LINE + "\n\n", "")
    assert any("call button" in i.message for i in compose.check_email(without, {"company": "Acme Aircon", "tools": TOOLS, "tool": "quote-builder"}))


def test_old_signature_is_missing_the_signature():
    old = GOOD + "\n\nTing Yu\nJura Solutions · jurasolutions.sg\n\nfooter"
    assert any("Missing the signature" in i.message for i in compose.check_email(old, {"company": "Acme Aircon"}))


# --- 5. the preview ----------------------------------------------------------


def test_sample_command_writes_html_and_text(tmp_path):
    result = CliRunner().invoke(cli, ["outreach", "sample", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    html_text = (tmp_path / "sample.html").read_text(encoding="utf-8")
    text = (tmp_path / "sample.txt").read_text(encoding="utf-8")
    assert "Book a 30-minute call" in html_text and f"Book a 30-minute call: {CALL_URL}" in text
    assert compose.SIGNATURE in text and str(tmp_path / "sample.html") in result.output
    assert "brand check: pass" in result.output


def test_sample_screenshots_say_so_without_chrome(tmp_path, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_CHROME", str(tmp_path / "no-chrome-here"))
    result = CliRunner().invoke(cli, ["outreach", "sample", "--out", str(tmp_path), "--screenshots"])
    assert result.exit_code == 1 and "no screenshots: Google Chrome not found" in result.output
    assert (tmp_path / "sample.html").exists()


# --- 6. privacy: Levi's name and address are the sender's own ------------------


def test_privacy_keeps_the_sender_name_and_reply_to(conn):
    from jura_growth.agents import outreach

    terms = outreach.privacy_terms(conn)
    assert "Levi Ting" in terms["kept_names"] and "Ting Yu" in terms["kept_names"]
    assert "levi@jurasolutions.sg" in terms["owner_addresses"]
