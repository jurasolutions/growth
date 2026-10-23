"""Contact rules: finding the address on the page, obfuscation, role vs named, MX."""

import dns.resolver
import httpx
import pytest

from jura_growth.agents.scout import contact

from test_scout_support import pages, scout_env  # noqa: F401


def cf_encode(email: str, key: int = 0x5A) -> str:
    return f"{key:02x}" + "".join(f"{ord(ch) ^ key:02x}" for ch in email)


# --- decoding --------------------------------------------------------------


def test_cloudflare_decoding_round_trips():
    encoded = cf_encode("info@acme.sg")
    assert contact.decode_cfemail(encoded) == "info@acme.sg"
    assert contact.decode_cfemail("zz") is None
    assert contact.decode_cfemail("abc") is None


@pytest.mark.parametrize(
    "html, expected",
    [
        ("<p>Email us: info@acme.sg</p>", "info@acme.sg"),
        ("<a href='mailto:Sales@Acme.SG'>Write to us</a>", "sales@acme.sg"),
        ("<a href='mailto:info%40acme.sg?subject=Hi'>Email</a>", "info@acme.sg"),
        ("<p>info [at] acme [dot] sg</p>", "info@acme.sg"),
        ("<p>info(at)acme(dot)com(dot)sg</p>", "info@acme.com.sg"),
        ("<p>info {at} acme {dot} sg</p>", "info@acme.sg"),
        ("<p>enquiry at acme dot sg</p>", "enquiry@acme.sg"),
        ("<p>hello @ acme.sg</p>", "hello@acme.sg"),
        ("<p>info@acme dot sg</p>", "info@acme.sg"),
        ("<p>&#105;&#110;&#102;&#111;&#64;&#97;&#99;&#109;&#101;&#46;&#115;&#103;</p>", "info@acme.sg"),
        ("<p>info<span>@</span>acme.sg</p>", "info@acme.sg"),
        (
            f'<a href="/cdn-cgi/l/email-protection" class="__cf_email__" data-cfemail="{cf_encode("info@acme.sg")}">[email&#160;protected]</a>',
            "info@acme.sg",
        ),
        (f'<a href="/cdn-cgi/l/email-protection#{cf_encode("admin@acme.sg", 0x21)}">Email us</a>', "admin@acme.sg"),
    ],
)
def test_addresses_are_decoded(html, expected):
    assert expected in contact.addresses_in(html)


def test_plain_at_in_prose_is_not_an_address():
    found = contact.addresses_in("<p>Visit us at acme.sg or call us at the office.</p>")
    assert not any(a.startswith("us@") for a in found)


# --- the page check --------------------------------------------------------


def test_address_found_on_its_own_page():
    client = pages({"https://acme.sg/contact": "<p>Write to info [at] acme [dot] sg</p>"})
    check = contact.verify_on_page("info@acme.sg", "https://acme.sg/contact", "acme.sg", client=client)
    assert check.found and not check.error


def test_address_missing_from_page_is_unverified():
    client = pages({"https://acme.sg/contact": "<p>Write to sales@acme.sg</p>"})
    check = contact.verify_on_page("info@acme.sg", "https://acme.sg/contact", "acme.sg", client=client)
    assert not check.found and "sales@acme.sg" in check.addresses


def test_page_errors_and_redirects_off_domain():
    assert contact.verify_on_page("info@acme.sg", "https://acme.sg/contact", "acme.sg", client=pages({})).error

    def handler(request):
        if request.url.host == "acme.sg":
            return httpx.Response(301, headers={"location": "https://directory.example/acme"})
        return httpx.Response(200, text="<p>info@acme.sg</p>", headers={"content-type": "text/html"})

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    check = contact.verify_on_page("info@acme.sg", "https://acme.sg/contact", "acme.sg", client=client)
    assert not check.found and "redirected off" in check.error


def test_on_domain_and_third_party_hosts():
    assert contact.on_domain("https://www.acme.sg/contact", "acme.sg")
    assert contact.on_domain("https://shop.acme.sg/x", "acme.sg")
    assert not contact.on_domain("https://acme.sg.evil.com/x", "acme.sg")
    assert not contact.on_domain("https://notacme.sg/x", "acme.sg")
    assert contact.is_third_party_host("facebook.com")
    assert contact.is_third_party_host("m.yellowpages.com.sg")
    assert not contact.is_third_party_host("acme.sg")


# --- classification and MX -------------------------------------------------


@pytest.mark.parametrize("email", ["info@acme.sg", "enquiries@acme.sg", "sales@acme.sg", "hello@acme.sg", "admin@acme.sg", "info2@acme.sg"])
def test_role_addresses(email):
    assert contact.kind_of(email) == "role"


@pytest.mark.parametrize("email", ["jane.tan@acme.sg", "weiming@acme.sg", "jtan@acme.sg"])
def test_named_addresses(email):
    assert contact.kind_of(email) == "named"


def test_addresses_not_for_enquiries():
    assert contact.not_for_enquiries("careers@acme.sg")
    assert contact.not_for_enquiries("noreply@acme.sg")
    assert not contact.not_for_enquiries("info@acme.sg")


def test_mx_check(monkeypatch):
    monkeypatch.setattr(contact, "resolve_mx", lambda d: ["mx1.acme.sg"])
    assert contact.mx_check("acme.sg") == (True, "")

    def nxdomain(d):
        raise dns.resolver.NXDOMAIN()

    monkeypatch.setattr(contact, "resolve_mx", nxdomain)
    ok, why = contact.mx_check("nowhere.sg")
    assert not ok and "does not exist" in why

    def no_answer(d):
        raise dns.resolver.NoAnswer()

    monkeypatch.setattr(contact, "resolve_mx", no_answer)
    assert contact.mx_check("acme.sg")[0] is False
    monkeypatch.setattr(contact, "resolve_mx", lambda d: [""])
    assert "null MX" in contact.mx_check("acme.sg")[1]
