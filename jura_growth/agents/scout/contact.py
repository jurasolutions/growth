"""Contact rules for the scout (PRD §5.2 step 5), enforced in code.

- The address must belong to the business: its domain is the company's
  website domain or a subdomain of it, or one of the free-mail providers in
  `FREE_MAIL_CONTACTS` (config may shorten that list, never add to it).
- The address must be one the business publishes on its own website. The
  source page must sit on the company's own domain, and the code fetches that
  page itself and confirms the exact address appears on it, after decoding the
  usual obfuscation: HTML entities, `mailto:` links (percent-encoded too),
  "info [at] acme [dot] sg" and its variants, and Cloudflare's email
  protection (`data-cfemail` and `/cdn-cgi/l/email-protection#<hex>`).
- Addresses are classified as role (info@, sales@, ...) or named.
- The mail domain must have an MX record. Nothing else is probed: no SMTP
  checks, no guessing.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit

import httpx

USER_AGENT = "Mozilla/5.0 (compatible; JuraScout/1.0; +https://jurasolutions.sg)"
MAX_PAGE_BYTES = 3_000_000

EMAIL_RE = re.compile(r"[a-z0-9][a-z0-9._%+-]*@[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}", re.I)
ADDRESS_RE = re.compile(r"^[a-z0-9][a-z0-9._%+-]*@[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}$")

# Enquiry role addresses, in order of preference.
ENQUIRY_ROLES = ("info", "enquiry", "enquiries", "enquire", "inquiry", "inquiries", "sales", "hello", "contact", "admin")
OTHER_ROLES = (
    "office", "general", "mail", "team", "reception", "service", "services", "support", "help",
    "booking", "bookings", "book", "orders", "order", "sales.sg", "sg", "singapore", "accounts",
    "account", "billing", "cs", "customerservice", "customer.service", "customercare", "care",
    "ask", "operations", "ops", "marketing", "projects", "quote", "quotes", "quotation",
    "rental", "events", "catering", "reservations", "reservation", "studio", "clinic",
    "frontdesk", "front.desk", "admissions", "enrol", "enroll", "hr", "careers", "jobs",
)
NOT_FOR_ENQUIRIES = ("careers", "jobs", "hr", "privacy", "dpo", "abuse", "noreply", "no-reply", "donotreply", "postmaster", "webmaster")

FREE_MAIL = frozenset(
    {
        "gmail.com", "googlemail.com", "yahoo.com", "yahoo.com.sg", "ymail.com", "hotmail.com",
        "hotmail.sg", "outlook.com", "outlook.sg", "live.com", "live.com.sg", "msn.com", "icloud.com",
        "me.com", "mac.com", "aol.com", "protonmail.com", "proton.me", "singnet.com.sg",
        "pacific.net.sg", "starhub.net.sg", "zoho.com", "gmx.com", "mail.com", "qq.com", "163.com",
    }
)

# The free-mail providers a small business may publish as its enquiry address
# (Ting Yu's decision, 2026-10-24). This is the ceiling: `free_mail_contacts`
# in config/scout.yaml may shorten it, never add to it.
FREE_MAIL_CONTACTS = ("gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "icloud.com", "singnet.com.sg")

# Hosts that are never a company's own website: social profiles, directories,
# marketplaces and link pages (PRD: no third-party lists or scraped directories).
NOT_OWN_SITE = (
    "facebook.com", "fb.com", "instagram.com", "linkedin.com", "twitter.com", "x.com", "tiktok.com",
    "youtube.com", "linktr.ee", "google.com", "goo.gl", "g.page", "business.site", "yelp.com",
    "yellowpages.com.sg", "sgpbusiness.com", "recordowl.com", "opencorporates.com", "bizfile.gov.sg",
    "carousell.sg", "carousell.com", "shopee.sg", "lazada.sg", "wa.me", "whatsapp.com",
    "hipages.com.sg", "renopedia.sg", "qanvast.com", "streetdirectory.com", "timable.com",
    "companies.sg", "sgcompany.sg", "dnb.com", "zoominfo.com", "apollo.io", "rocketreach.co",
    "crunchbase.com", "glassdoor.com", "jobstreet.com", "indeed.com", "mycareersfuture.gov.sg",
)


class ContactError(ValueError):
    """The address breaks a contact rule. The message says which."""


@dataclass
class PageCheck:
    url: str
    final_url: str = ""
    found: bool = False
    addresses: set[str] = field(default_factory=set)
    error: str = ""


# --- domains ---------------------------------------------------------------


def _split(url: str):
    candidate = url if re.match(r"^[a-z][a-z0-9+.-]*://", url or "", re.I) else f"https://{url}"
    return urlsplit(candidate)


def host_of(url: str) -> str:
    return (_split(url).hostname or "").lower().strip(".")


def is_site_root(url: str) -> bool:
    """True for a site's home page: no path beyond "/" and no query. A
    directory or marketplace listing sits at a path on someone else's site."""
    parts = _split(url)
    return parts.path in ("", "/") and not parts.query


def site_domain(url: str) -> str:
    return host_of(url).removeprefix("www.")


def on_domain(url: str, domain: str) -> bool:
    host = host_of(url)
    domain = domain.lower().removeprefix("www.")
    return bool(host and domain) and (host == domain or host.endswith("." + domain))


def is_third_party_host(domain: str) -> bool:
    domain = domain.lower()
    return any(domain == h or domain.endswith("." + h) for h in NOT_OWN_SITE)


def mail_domain(email: str) -> str:
    return email.rsplit("@", 1)[-1].lower()


def is_free_mail(email_or_domain: str) -> bool:
    return mail_domain(email_or_domain) in FREE_MAIL


def ownership_problem(email: str, domain: str, free_mail: tuple[str, ...]) -> str | None:
    """Why `email` can't be the business's own address, or None when it can be.

    The address must sit on the company's site domain (or a subdomain of it),
    or at one of the `free_mail` providers. A partner's or web designer's
    address on the company's site fails, and so does a company's address
    found on a directory, because the directory is then the "site".
    """
    if on_domain(mail_domain(email), domain) or mail_domain(email) in free_mail:
        return None
    allowed = f"on {domain} (or a subdomain of it)"
    if free_mail:
        allowed += f" or at a free-mail provider ({', '.join(free_mail)})"
    return f"{email} does not belong to the business: the address must be {allowed}"


def normalise_email(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"^mailto:", "", value, flags=re.I)
    value = unquote(value.split("?", 1)[0]).strip().strip("<>").lower()
    return value


def valid_email(value: str) -> bool:
    return bool(ADDRESS_RE.match(value or ""))


# --- classification --------------------------------------------------------


def local_part(email: str) -> str:
    return email.split("@", 1)[0].lower()


def kind_of(email: str) -> str:
    """`role` for a shared inbox (info@, sales@ ...), otherwise `named`."""
    local = local_part(email)
    base = re.sub(r"[\d_.-]+$", "", local) or local
    if local in ENQUIRY_ROLES or local in OTHER_ROLES or base in ENQUIRY_ROLES or base in OTHER_ROLES:
        return "role"
    return "named"


def is_enquiry_role(email: str) -> bool:
    local = local_part(email)
    base = re.sub(r"[\d_.-]+$", "", local) or local
    return local in ENQUIRY_ROLES or base in ENQUIRY_ROLES


def not_for_enquiries(email: str) -> bool:
    local = local_part(email)
    return any(local == word or local.startswith(word) for word in NOT_FOR_ENQUIRIES)


# --- decoding obfuscation --------------------------------------------------


def decode_cfemail(encoded: str) -> str | None:
    """Cloudflare email protection: the first byte is an XOR key for the rest."""
    encoded = encoded.strip()
    if len(encoded) < 4 or len(encoded) % 2 or not re.fullmatch(r"[0-9a-fA-F]+", encoded):
        return None
    key = int(encoded[:2], 16)
    try:
        return bytes(int(encoded[i : i + 2], 16) ^ key for i in range(2, len(encoded), 2)).decode("utf-8")
    except UnicodeDecodeError:
        return None


CF_ATTR_RE = re.compile(r"data-cfemail\s*=\s*[\"']?([0-9a-fA-F]+)", re.I)
CF_HREF_RE = re.compile(r"/cdn-cgi/l/email-protection[^\"'\s>]*#([0-9a-fA-F]+)", re.I)
MAILTO_RE = re.compile(r"mailto:([^\"'\s>?]+)", re.I)

_OPEN = r"[\[\(\{<]"
_CLOSE = r"[\]\)\}>]"
BRACKET_AT_RE = re.compile(rf"\s*{_OPEN}\s*(?:at|@)\s*{_CLOSE}\s*", re.I)
BRACKET_DOT_RE = re.compile(rf"\s*{_OPEN}\s*(?:dot|\.)\s*{_CLOSE}\s*", re.I)
SPACED_AT_RE = re.compile(r"(\w)\s+@\s+(\w)")
# "info at acme dot sg": only with at least one "dot", so "visit us at acme.sg"
# never turns into an address.
WORDY_RE = re.compile(r"\b([a-z0-9][\w.+-]*)\s+at\s+([a-z0-9-]+(?:\s+dot\s+[a-z0-9-]+)+)\b", re.I)
MIXED_DOT_RE = re.compile(r"@([a-z0-9-]+(?:\s+dot\s+[a-z0-9-]+)+)\b", re.I)


def _dots(value: str) -> str:
    return re.sub(r"\s+dot\s+", ".", value, flags=re.I)


def _deobfuscate(text: str) -> str:
    text = BRACKET_AT_RE.sub("@", text)
    text = BRACKET_DOT_RE.sub(".", text)
    text = SPACED_AT_RE.sub(r"\1@\2", text)
    text = WORDY_RE.sub(lambda m: f"{m.group(1)}@{_dots(m.group(2))}", text)
    return MIXED_DOT_RE.sub(lambda m: "@" + _dots(m.group(1)), text)


def addresses_in(page: str) -> set[str]:
    """Every address a visitor could read on the page, decoded."""
    unescaped = html.unescape(page)
    views = [
        unescaped,
        re.sub(r"<[^>]+>", "", unescaped),  # info<span>@</span>acme.sg
        re.sub(r"<[^>]+>", " ", unescaped),
    ]
    views += [_deobfuscate(v) for v in views[1:]]
    found: set[str] = set()
    for view in views:
        found |= {m.group(0).lower().rstrip(".") for m in EMAIL_RE.finditer(view)}
    for m in MAILTO_RE.finditer(unescaped):
        candidate = normalise_email(m.group(1))
        if valid_email(candidate):
            found.add(candidate)
    for pattern in (CF_ATTR_RE, CF_HREF_RE):
        for m in pattern.finditer(page):
            decoded = decode_cfemail(m.group(1))
            if decoded and valid_email(decoded.lower()):
                found.add(decoded.lower())
    return found


# --- fetching the source page ----------------------------------------------


def http_client() -> httpx.Client:
    """The client used to fetch source pages (tests replace it)."""
    return httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT})


def fetch_addresses(url: str, domain: str, *, client: httpx.Client | None = None) -> PageCheck:
    check = PageCheck(url)
    owns = client is None
    client = client or http_client()
    try:
        response = client.get(url)
    except httpx.HTTPError as error:
        check.error = f"could not fetch {url} ({type(error).__name__})"
        return check
    finally:
        if owns:
            client.close()
    check.final_url = str(response.url)
    if response.status_code != 200:
        check.error = f"{url} answered {response.status_code}"
        return check
    if not on_domain(check.final_url, domain):
        check.error = f"{url} redirected off {domain} to {host_of(check.final_url)}"
        return check
    content_type = response.headers.get("content-type", "text/html").lower()
    if not any(t in content_type for t in ("html", "text", "xml")):
        check.error = f"{url} is not a web page ({content_type})"
        return check
    body = response.content[:MAX_PAGE_BYTES].decode(response.encoding or "utf-8", errors="replace")
    check.addresses = addresses_in(body)
    return check


def verify_on_page(email: str, url: str, domain: str, *, client: httpx.Client | None = None) -> PageCheck:
    """Fetch `url` and confirm `email` is published there."""
    check = fetch_addresses(url, domain, client=client)
    check.found = not check.error and email.lower() in check.addresses
    return check


# --- MX --------------------------------------------------------------------


def resolve_mx(domain: str) -> list[str]:
    """MX hosts for `domain`. Raises dns.exception.DNSException types."""
    import dns.resolver

    answers = dns.resolver.resolve(domain, "MX", lifetime=10)
    return [str(r.exchange).rstrip(".") for r in answers]


def mx_check(domain: str) -> tuple[bool, str]:
    import dns.exception
    import dns.resolver

    try:
        hosts = resolve_mx(domain)
    except dns.resolver.NXDOMAIN:
        return False, f"{domain} does not exist"
    except dns.resolver.NoAnswer:
        return False, f"{domain} has no MX record"
    except dns.exception.DNSException as error:
        return False, f"MX lookup for {domain} failed ({type(error).__name__})"
    if not hosts or all(h in ("", ".") for h in hosts):
        return False, f"{domain} publishes a null MX (accepts no mail)"
    return True, ""
