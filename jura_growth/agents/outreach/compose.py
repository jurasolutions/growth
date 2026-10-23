"""Building an outreach email and the `email` brand channel (scout PRD §5.6).

The model writes the subject and the body. The code adds everything the law
and the PRD require, so those parts are certain:

    Ting Yu
    Jura Solutions · jurasolutions.sg

    You're receiving this because <Company> lists this address for business
    enquiries on <their site>. Not interested? Unsubscribe here: <link>, or
    reply "unsubscribe".

The unsubscribe token must match the website's Pages Function exactly:

    email_hash = sha256(email.strip().lower()) as lowercase hex
    sig        = base64url(HMAC-SHA256(key=UNSUBSCRIBE_SECRET, msg=email_hash)), no "=" padding
    token      = f"{email_hash}.{sig}"
    url        = https://jurasolutions.sg/unsubscribe?t=<token>

HTML is built from the text: paragraphs, jurasolutions.sg links with UTM
parameters (never on the unsubscribe link, never on anyone else's link), no
images and no tracking pixel.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from jura_growth import brand_check, caps, config, suppression
from jura_growth.agents.scout import registry, settings

SIGNATURE = f"{settings.SIGNATURE_NAME}\nJura Solutions · {settings.SITE}"
RECEIVING = "You're receiving this because {company} lists this address for business enquiries on {site}."
UNSUBSCRIBE_LINE = 'Not interested? Unsubscribe here: {link}, or reply "unsubscribe".'
# What the brand gate sees in place of the recipient's own site name: the
# email channel allows jurasolutions.sg links only, and the footer's mention of
# the company's own domain is code-generated from the verified source page.
SITE_PLACEHOLDER = "its website"
NO_SECRET_SIG = "UNSUBSCRIBE_SECRET-not-set"

GREETING_RE = re.compile(r"^(?:hi|hello|dear|good (?:morning|afternoon|day))\b[^.!?\n]{0,40}[,.]?\s*$", re.I)
JURA_LINK_RE = re.compile(r"(?:https?://)?(?:www\.)?jurasolutions\.sg(?:/[^\s<>()\[\]\"']*)?", re.I)
FOLLOW_UP_REF_RE = re.compile(
    r"\b(?:my (?:last |earlier |previous |first )?(?:note|email|message)|i wrote|wrote to you|"
    r"last week|earlier this|following up|a short follow-up|back in touch)\b",
    re.I,
)
STOPWORDS = frozenset(
    """about after again their there these those which while where would could should other
    through using every being since until under between before because company business businesses
    customers clients people website online page pages contact email phone their them they with
    from into have has had will your yours what when then than that this also more most some such
    only very just over each both many much make makes made""".split()
)


# --- the token -------------------------------------------------------------


def unsubscribe_token(email: str, secret: str) -> str:
    email_hash = suppression.email_hash(email)
    digest = hmac.new(secret.encode("utf-8"), email_hash.encode("utf-8"), hashlib.sha256).digest()
    sig = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return f"{email_hash}.{sig}"


def unsubscribe_url(email: str, secret: str | None = None) -> str:
    secret = secret if secret is not None else config.secret("UNSUBSCRIBE_SECRET")
    if not secret:
        return f"{settings.UNSUBSCRIBE_URL}?t={suppression.email_hash(email)}.{NO_SECRET_SIG}"
    return f"{settings.UNSUBSCRIBE_URL}?t={unsubscribe_token(email, secret)}"


def list_unsubscribe_headers(url: str) -> dict[str, str]:
    return {
        "List-Unsubscribe": f"<{url}>, <{settings.UNSUBSCRIBE_MAILTO}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }


# --- composing -------------------------------------------------------------


@dataclass
class Email:
    subject: str
    draft: str  # the model's body after tidying
    text: str  # the full plain-text email
    html: str
    check_text: str  # what the brand gate checks (site name masked)
    unsubscribe_url: str
    site: str


def tidy_draft(body: str) -> str:
    """Normalise line endings and drop a signature the model added anyway."""
    lines = body.replace("\r\n", "\n").replace("\r", "\n").strip().split("\n")
    while lines and (
        not lines[-1].strip()
        or lines[-1].strip().lower() in {"ting yu", "jura solutions", "ting yu, jura solutions"}
        or "jurasolutions.sg" == lines[-1].strip().lower()
        or lines[-1].strip().lower().startswith("jura solutions ·")
    ):
        lines.pop()
    text = "\n".join(line.rstrip() for line in lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def footer(company: str, site: str, link: str) -> str:
    return RECEIVING.format(company=company, site=site) + " " + UNSUBSCRIBE_LINE.format(link=link)


def compose(*, subject: str, body: str, company: str, site: str, email: str, secret: str | None = None) -> Email:
    subject = re.sub(r"\s+", " ", subject or "").strip()
    draft = tidy_draft(body or "")
    link = unsubscribe_url(email, secret)
    text = f"{draft}\n\n{SIGNATURE}\n\n{footer(company, site, link)}\n"
    check_text = f"{draft}\n\n{SIGNATURE}\n\n{footer(company, SITE_PLACEHOLDER, link)}\n"
    return Email(subject, draft, text, to_html(draft, company, site, link), check_text, link, site)


def with_utm(url: str) -> str:
    """Add UTM parameters to a jurasolutions.sg link (never the unsubscribe link)."""
    full = url if re.match(r"^https?://", url, re.I) else f"https://{url}"
    parts = urlsplit(full)
    host = (parts.hostname or "").lower()
    if not (host == settings.SITE or host.endswith("." + settings.SITE)) or parts.path.startswith("/unsubscribe"):
        return full
    query = dict(parse_qsl(parts.query))
    for key, value in settings.utm().items():
        query.setdefault(key, value)
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", urlencode(query), parts.fragment))


def _linkify(escaped: str) -> str:
    def anchor(match: re.Match) -> str:
        raw = html.unescape(match.group(0))
        trail = ""
        while raw and raw[-1] in ".,;:":
            trail = raw[-1] + trail
            raw = raw[:-1]
        href = html.escape(with_utm(raw), quote=True)
        return f'<a href="{href}" style="color:#0f5132;">{html.escape(raw)}</a>{html.escape(trail)}'

    return JURA_LINK_RE.sub(anchor, escaped)


def to_html(draft: str, company: str, site: str, link: str) -> str:
    paragraphs = [p for p in re.split(r"\n\s*\n", draft) if p.strip()]
    body = "\n".join(
        f"<p style=\"margin:0 0 16px;\">{_linkify(html.escape(p.strip())).replace(chr(10), '<br>')}</p>"
        for p in paragraphs
    )
    home = html.escape(with_utm(f"https://{settings.SITE}"), quote=True)
    signature = (
        f'<p style="margin:0 0 24px;">{html.escape(settings.SIGNATURE_NAME)}<br>'
        f'Jura Solutions · <a href="{home}" style="color:#0f5132;">{settings.SITE}</a></p>'
    )
    notice = (
        '<p style="margin:0;font-size:13px;color:#4e5852;">'
        + html.escape(RECEIVING.format(company=company, site=site))
        + f' Not interested? <a href="{html.escape(link, quote=True)}" style="color:#0f5132;">Unsubscribe here</a>, '
        + "or reply &quot;unsubscribe&quot;.</p>"
    )
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8"></head>\n'
        '<body style="margin:0;padding:24px;background:#ffffff;color:#363e39;'
        'font-family:\'DM Sans\',Helvetica,Arial,sans-serif;font-size:15px;line-height:1.55;">\n'
        f'<div style="max-width:560px;">\n{body}\n{signature}\n{notice}\n</div>\n</body></html>\n'
    )


# --- the email channel -----------------------------------------------------


def _split(text: str) -> tuple[str, str] | None:
    marker = "\n" + SIGNATURE
    index = text.find(marker)
    if index < 0:
        return None
    return text[:index].strip(), text[index + len(marker):].strip()


def word_count(text: str) -> int:
    return len([t for t in text.split() if re.search(r"\w", t)])


def _path_of(link: str) -> tuple[str, str]:
    full = link if re.match(r"^https?://", link, re.I) else f"https://{link}"
    parts = urlsplit(full)
    return (parts.hostname or "").lower().removeprefix("www."), parts.path.rstrip("/")


def first_line(draft: str) -> str:
    for paragraph in re.split(r"\n\s*\n", draft):
        lines = [l.strip() for l in paragraph.split("\n") if l.strip()]
        while lines and GREETING_RE.match(lines[0]):
            lines.pop(0)
        if lines:
            sentences = brand_check.sentences(" ".join(lines))
            return sentences[0] if sentences else ""
    return ""


def _name_forms(company: str) -> list[str]:
    forms = [company.strip()]
    words = re.findall(r"[\w'’&-]+", company)
    generic = {"the", "singapore", "global", "asia", "pacific", "group", "services", "service", "international", "holdings"}
    if words and len(words[0]) >= 4 and words[0].lower() not in generic:
        forms.append(words[0])
    return [f for f in forms if f]


def _observation_keywords(observations: list[str]) -> set[str]:
    words = set()
    for item in observations or []:
        for word in re.findall(r"[A-Za-z][A-Za-z'-]{4,}", item):
            lowered = word.lower()
            if lowered not in STOPWORDS:
                words.add(lowered)
    return words


def check_email(text: str, ctx: dict) -> list[brand_check.Issue]:
    """Rule 10 for the `email` channel: the PRD §5.6 parts and shape."""
    Issue = brand_check.Issue
    issues: list[Issue] = []
    kind = ctx.get("kind") or "first"
    company = ctx.get("company")
    subject = ctx.get("subject") or ""

    # Subject: present, no reply or forward prefix. (Questions and sentence
    # case are the core rules 5 and 8.)
    if not subject.strip():
        issues.append(Issue("channel", "The email needs a subject line"))
    elif re.match(r"^\s*(?:re|fwd?|aw|sv)\s*:", subject, re.I):
        issues.append(Issue("channel", "No “Re:” or “Fwd:” in the subject; it is a first contact", subject))

    parts = _split(text)
    if parts is None:
        issues.append(Issue("channel", "Missing the signature: “Ting Yu” and “Jura Solutions · jurasolutions.sg”"))
        return issues
    draft, tail = parts

    # Required parts in the footer.
    if company:
        receiving = RECEIVING.format(company=company, site="").rstrip(".").rstrip()
        if receiving not in tail:
            issues.append(Issue("channel", "Missing “You're receiving this because <Company> lists this address for business enquiries on <their site>.”"))
    elif "You're receiving this because" not in tail or "lists this address for business enquiries on" not in tail:
        issues.append(Issue("channel", "Missing the line saying why they are receiving this"))
    if not re.search(r"https://jurasolutions\.sg/unsubscribe\?t=[0-9a-f]{64}\.[A-Za-z0-9_-]+", tail):
        issues.append(Issue("channel", "Missing the unsubscribe link"))
    if 'or reply "unsubscribe"' not in tail:
        issues.append(Issue("channel", 'Missing “or reply "unsubscribe"”'))

    # The body the model wrote.
    if re.search(r"unsubscribe|you're receiving this", draft, re.I):
        issues.append(Issue("channel", "Leave the unsubscribe and why-you're-receiving lines out of the body; the code adds them"))
    words = word_count(draft)
    if words >= caps.OUTREACH_WORDS_MAX:
        issues.append(Issue("channel", f"The body is {words} words; keep it under {caps.OUTREACH_WORDS_MAX}"))

    tools = ctx.get("tools")
    if tools is None:
        tools = registry.live_slugs()
    tools = set(tools)
    chosen = ctx.get("tool")
    tool_links, index_links, other = [], [], []
    for link in brand_check.find_links(draft):
        host, path = _path_of(link)
        if host != settings.SITE:
            continue  # core rule 9 reports it
        if path == "/apps":
            index_links.append(link)
        elif path.startswith("/apps/"):
            tool_links.append((link, path.removeprefix("/apps/").split("/")[0]))
        else:
            other.append(link)
    if len(index_links) != 1:
        issues.append(Issue("channel", f"Link to jurasolutions.sg/apps exactly once (found {len(index_links)})"))
    if kind == "first" and len(tool_links) != 1:
        issues.append(Issue("channel", f"Link to exactly one tool at jurasolutions.sg/apps/<slug> (found {len(tool_links)})"))
    if kind == "follow_up" and len(tool_links) > 1:
        issues.append(Issue("channel", f"A follow-up mentions at most one tool (found {len(tool_links)})"))
    for link, slug in tool_links:
        if slug not in tools:
            issues.append(Issue("channel", f"/apps/{slug} is not a live tool in the site registry", link))
        elif chosen and slug != chosen:
            issues.append(Issue("channel", f"The tool link should be the chosen tool /apps/{chosen}", link))
    for link in other:
        issues.append(Issue("channel", "Only the tool link and jurasolutions.sg/apps in the body", link))

    # The first line is about this company.
    opening = first_line(draft)
    if not opening:
        issues.append(Issue("channel", "The email needs an opening line about the company"))
    elif company or ctx.get("observations"):
        lowered = opening.lower()
        named = company and any(form.lower() in lowered for form in _name_forms(company))
        keywords = _observation_keywords(ctx.get("observations") or [])
        observed = any(re.search(rf"\b{re.escape(k)}", lowered) for k in keywords)
        refers_back = kind == "follow_up" and FOLLOW_UP_REF_RE.search(opening)
        if not (named or observed or refers_back):
            issues.append(Issue("channel", "The first line should be about this company: name it or what you saw on its site", opening))
    return issues


def channel() -> brand_check.Channel:
    return brand_check.Channel(
        "email",
        allow_sources=False,
        check=check_email,
        description="Outreach email: jurasolutions.sg links only, PRD §5.6 parts",
    )
