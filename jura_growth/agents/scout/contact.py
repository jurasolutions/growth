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
- Job boards, recruiters and job ads (a careers page on the company's own
  site included) are hiring evidence only (PRD §5.2a point 6): never a lead's
  website, never the page a contact address or form comes from.
- Addresses are classified as role (info@, sales@, ...) or named.
- The mail domain must have an MX record. Nothing else is probed: no SMTP
  checks, no guessing.
"""

from __future__ import annotations

import html
import posixpath
import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit

import httpx

from jura_growth import role_addresses
from jura_growth.role_addresses import (  # noqa: F401 - part of this module's interface
    ENQUIRY_ROLES,
    NOT_FOR_ENQUIRIES,
    OTHER_ROLES,
    is_enquiry_role,
    local_part,
    not_for_enquiries,
)

USER_AGENT = "Mozilla/5.0 (compatible; JuraScout/1.0; +https://jurasolutions.sg)"
MAX_PAGE_BYTES = 3_000_000

EMAIL_RE = re.compile(r"[a-z0-9][a-z0-9._%+-]*@[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}", re.I)
ADDRESS_RE = re.compile(r"^[a-z0-9][a-z0-9._%+-]*@[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}$")

# The role vocabulary lives in core, shared with what may appear in Discord.

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
    "crunchbase.com",
)

# Job boards and the hosted job-ad pages of applicant tracking systems (scout
# PRD §5.2a). Their pages are hiring evidence only: never a lead's website and
# never the source of a contact address.
JOB_BOARDS = (
    "mycareersfuture.gov.sg", "mycareersfuture.sg", "jobstreet.com", "jobstreet.com.sg", "indeed.com",
    "indeed.com.sg", "linkedin.com", "glassdoor.com", "glassdoor.sg", "jobsdb.com", "fastjobs.sg",
    "foundit.sg", "monster.com.sg", "careerjet.sg", "jora.com", "jooble.org", "grabjobs.co",
    "jobscentral.com.sg", "hiredly.com", "efinancialcareers.sg", "gumtree.sg", "nodeflair.com",
    "lever.co", "greenhouse.io", "workable.com", "myworkdayjobs.com", "smartrecruiters.com",
    "recruitee.com", "breezy.hr", "bamboohr.com", "zohorecruit.com", "careers-page.com",
    "glints.com", "stjobs.sg", "adzuna.sg", "kalibrr.com", "ashbyhq.com", "jobvite.com",
    "teamtailor.com", "personio.com", "personio.de", "manatal.com", "applytojob.com", "jazzhr.com",
)
# Recruitment agencies: an ad they place names their own inbox, never the
# hiring company's, so a recruiter's site is never the contact source for
# another company. A recruiter may still be a lead in its own right (its own
# enquiry address, on its own contact page). Any host with "recruit" in its
# name counts as a recruiter too.
RECRUITERS = (
    "recruitexpress.com.sg", "kellyservices.com.sg", "persolkelly.com.sg", "persolsingapore.com",
    "adecco.com.sg", "adecco.com", "randstad.com.sg", "manpower.com.sg", "manpowergroup.sg",
    "hays.com.sg", "michaelpage.com.sg", "pagepersonnel.com.sg", "robertwalters.com.sg",
    "roberthalf.com.sg", "gmprecruit.com", "trustrecruit.com.sg", "theoneglobal.com.sg",
    "achieversresources.com", "staffinggroup.sg",
)
NOT_OWN_SITE += JOB_BOARDS

# A careers or job-ad page, read from the words of its decoded, case-folded
# path, query and fragment (code review P1): any word starting with one of
# these stems, "job"/"jobs" (but not "job sheets" and the like), "join us",
# "join our team" and "work with us".
JOB_AD_STEMS = ("career", "vacanc", "recruit", "hiring", "viewjob", "joinus", "jobopening", "joblisting",
                "jobvacanc", "jobpost", "jobboard", "opportunit", "openings", "internship", "karriere", "kerjaya")
# Chinese jobs-page words, matched in the decoded text: recruitment, position, join us.
JOB_AD_CJK = ("招聘", "职位", "職位", "招募", "加入我们", "加入我們")
JOB_WORDS = frozenset({"job", "jobs"})
# "job" next to one of these is field-service paperwork or booking, not hiring:
# job sheets, job cards, a job request, book a job, our jobs (re-review R2).
JOB_PAPERWORK = frozenset({"sheet", "sheets", "card", "cards", "order", "orders", "ticket", "tickets", "costing",
                           "costs", "site", "sites", "report", "reports", "request", "requests", "quote", "quotes",
                           "booking", "bookings", "status", "tracking", "gallery"})
JOB_BEFORE_PAPERWORK = frozenset({"book", "our", "completed", "past", "recent", "submit"})
# Hire means rental in Singapore English: equipment hiring, car hiring.
RENTAL_WORDS = frozenset({"equipment", "car", "cars", "van", "vans", "lorry", "lorries", "truck", "trucks", "tool",
                          "tools", "crane", "cranes", "bus", "buses", "coach", "boat", "boats", "event", "party", "tent",
                          "tents", "machine", "machinery", "plant", "scaffold", "scaffolding", "generator", "venue"})
# "Vacancies" is read as employment unless a property word sits next to it
# (office vacancies, vacancies/units). The safer reading: a bare /vacancies is
# far more often a jobs page than a unit listing (re-review R2).
PROPERTY_WORDS = frozenset({"office", "offices", "unit", "units", "shop", "shops", "retail", "property", "properties",
                            "space", "spaces", "room", "rooms", "rental", "rentals", "lease", "industrial", "warehouse",
                            "tenancy", "tenant", "tenants", "commercial", "residential", "apartment", "apartments",
                            "condo", "condos", "flat", "flats"})
# Business, not employment: franchise opportunities, store openings.
NOT_HIRING_BEFORE = {"opportunit": frozenset({"business", "franchise", "partnership", "partner", "investment",
                                              "sponsorship"}),
                     "openings": frozenset({"store", "shop", "outlet", "branch", "grand"})}
JOB_AD_PHRASES = (("join", "us"), ("join", "our"), ("join", "the", "team"), ("work", "with", "us"), ("work", "for", "us"),
                  ("jawatan", "kosong"))
# "Join us for dinner" is an invitation, not a careers page.
NOT_AFTER_JOIN_US = frozenset({"for", "at", "on", "in", "to"})
# A host label is a careers label if any of its words is one of these, or starts
# with "career" or "recruit" (careers-sg., career-portal., jobs2.). `apply.` alone
# is not: application portals take admissions and loan enquiries too.
JOB_AD_LABEL_WORDS = frozenset({"careers", "career", "jobs", "job", "hiring", "recruit", "recruitment", "talent",
                                "karriere", "kerjaya", "vacancies"})
EVIDENCE_ONLY = "job boards, recruiters and job ads are evidence only, never a contact source"


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


def _under(domain: str, hosts) -> bool:
    domain = domain.lower().strip(".")
    return any(domain == h or domain.endswith("." + h) for h in hosts)


def is_recruiter(domain: str) -> bool:
    domain = domain.lower()
    return _under(domain, RECRUITERS) or "recruit" in domain.removesuffix(".sg").removesuffix(".com")


def is_job_board(domain: str) -> bool:
    return _under(domain, JOB_BOARDS)


def is_third_party_host(domain: str) -> bool:
    return _under(domain, NOT_OWN_SITE)


def _decoded(value: str) -> str:
    """Percent-decoded until it stops changing (so %2563 is "c" too), NFKC-normalised
    (full-width letters become plain ones) and case-folded."""
    for _ in range(5):
        decoded = unquote(value)
        if decoded == value:
            break
        value = decoded
    return unicodedata.normalize("NFKC", value).casefold()


def _page_text(url: str) -> str:
    """The decoded path (dot segments resolved), query and fragment."""
    parts = _split(url)
    path = _decoded(parts.path)
    if path:
        path = posixpath.normpath(path)
    return " ".join([path, _decoded(parts.query), _decoded(parts.fragment)])


def _label_is_careers(label: str) -> bool:
    words = [re.sub(r"\d+$", "", w) for w in re.split(r"[^0-9a-z]+", _decoded(label)) if w]
    return any(w in JOB_AD_LABEL_WORDS or w.startswith(("career", "recruit")) for w in words)


def _company_labels(host: str, domain: str | None) -> list[str]:
    """The host's labels left of the company's domain (or of the last two labels)."""
    if domain and on_domain(f"https://{host}", domain):
        rest = host[: -len(domain.lower().removeprefix("www."))].rstrip(".")
        return rest.split(".") if rest else []
    return host.split(".")[:-2]


def _job_word_is_hiring(words: list[str], i: int) -> bool:
    before = words[i - 1] if i else ""
    two_before = words[i - 2] if i > 1 else ""
    after = words[i + 1] if i + 1 < len(words) else ""
    if after in JOB_PAPERWORK or before in JOB_BEFORE_PAPERWORK:
        return False
    return not (before == "a" and two_before in {"book", "request", "submit"})


def _stem_is_hiring(words: list[str], i: int, stem: str) -> bool:
    before = words[i - 1] if i else ""
    after = words[i + 1] if i + 1 < len(words) else ""
    if stem == "hiring" and before in RENTAL_WORDS:
        return False
    if stem == "vacanc" and (before in PROPERTY_WORDS or after in PROPERTY_WORDS):
        return False
    return before not in NOT_HIRING_BEFORE.get(stem, ())


def is_job_ad_page(url: str, domain: str | None = None) -> bool:
    """A careers or job-ad page by any host label or its words, however it is spelled:
    careers-sg.acme.sg, /%63areers/, /careers.html, /jobs.php, /join-our-team,
    ?page=careers, /招聘, /jawatan-kosong ... Field-service and rental pages such as
    /book-a-job, /job-request and /equipment-hiring are not."""
    host = host_of(url)
    if host and any(_label_is_careers(label) for label in _company_labels(host, domain)):
        return True
    text = _page_text(url)
    if any(word in text for word in JOB_AD_CJK):
        return True
    words = [w for w in re.split(r"[^0-9a-z]+", text) if w]
    for i, word in enumerate(words):
        stem = next((s for s in JOB_AD_STEMS if word.startswith(s)), None)
        if stem and _stem_is_hiring(words, i, stem):
            return True
        if word in JOB_WORDS and _job_word_is_hiring(words, i):
            return True
        for phrase in JOB_AD_PHRASES:
            if tuple(words[i : i + len(phrase)]) == phrase:
                follows = words[i + len(phrase)] if i + len(phrase) < len(words) else ""
                if phrase != ("join", "us") or follows not in NOT_AFTER_JOIN_US:
                    return True
    return False


def job_ad_problem(url: str, domain: str | None = None) -> str | None:
    """Why `url` may not be the page a contact address or form comes from, or
    None (§5.2a point 6). The one rule for add-lead, `scout shortlist` and
    `scout check-contact`, applied to the submitted page and again to the page
    the code actually read after redirects:

    - a job board or an applicant tracking system;
    - a recruiter's site, unless the recruiter is the lead itself (`domain`);
    - a careers or job-ad page on any site, the company's own included.

    It refuses only the contact source: a lead whose site has a careers section
    is fine, as long as the address comes from another page."""
    host = host_of(url)
    if not host:
        return None
    if is_job_board(host):
        return f"{url} is on a job board: {EVIDENCE_ONLY}"
    if is_recruiter(host) and not (domain and on_domain(url, domain)):
        return f"{url} is on a recruiter's site: {EVIDENCE_ONLY}"
    if is_job_ad_page(url, domain):
        return f"{url} is a careers or job-ad page: {EVIDENCE_ONLY}"
    return None


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


def kind_of(email: str) -> str:
    """`role` for a shared inbox (info@, sales@ ...), otherwise `named`."""
    return "role" if role_addresses.is_role(email) else "named"


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
