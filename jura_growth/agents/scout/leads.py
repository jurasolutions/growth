"""Adding a lead (`jura-growth scout add-lead`), with the PRD §5.2 rules in code.

In order, and the first failure rejects the lead:

 1. The record is complete: company, own website, industry, 1–3 observations,
    source URLs (one on the company's own site), score 0–100 with reasons.
 2. ICP exclusions code can tell: government domains (.gov.sg), websites
    that are social profiles, directories or marketplaces, and a website with
    a path or query (a listing page, not the company's own home page).
 3. Not already known: a lead with this domain, a domain in
    `contacted_domains`, a suppressed domain or address, or a row in
    `inputs/do-not-contact.csv` (by company name or domain).
 4. Score at or above the threshold (60, config may raise it).
 5. Today's shortlist not yet full (`research.shortlist`, §5.2a).
 6. The contact: never from a job board, a recruiter or a job ad (§5.2a
    point 6: they are evidence only). An address that belongs to the business (on its website
    domain or a subdomain of it, or at an allowed free-mail provider), which
    the code finds on a source page of the company's own site (see
    contact.py), with an MX record. A role address on the same page is
    preferred over a named one on the company's domain; a free-mail address
    is never swapped. A contact form only gives `channel = form`.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import timedelta

import httpx

from jura_growth import db, discord, log, privacy, suppression, timeutil
from jura_growth.agents.scout import contact, dnc, registry, scoring, settings

USERNAME = "Jura growth · scout"
GOVERNMENT_SUFFIXES = ("gov.sg", "mil.sg")
SUFFIX_RE = re.compile(
    r"[\s,]+(?:pte\.?\s*ltd\.?|pte\.?\s*limited|private\s+limited|ltd\.?|limited|llp|llc|inc\.?|sdn\.?\s*bhd\.?)\s*$",
    re.I,
)
COUNTRY_TAG_RE = re.compile(r"\s*\((?:s|sg|singapore)\)\s*$", re.I)


class LeadError(ValueError):
    pass


@dataclass
class Outcome:
    status: str  # added, rejected
    reasons: list[str] = field(default_factory=list)
    lead_id: int | None = None
    channel: str | None = None
    contact: dict | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "lead_id": self.lead_id,
            "channel": self.channel,
            "contact": self.contact,
            "reasons": self.reasons,
            "notes": self.notes,
        }


def _mask(text: str) -> str:
    return re.sub(r"[\w.+%-]+@(?=[\w-]+\.)", "…@", text or "")


def display_name(company: str) -> str:
    name = company.strip()
    previous = None
    while previous != name:
        previous = name
        name = SUFFIX_RE.sub("", name).strip()
        name = COUNTRY_TAG_RE.sub("", name).strip()
    return name or company.strip()


def is_government(domain: str) -> bool:
    return any(domain == s or domain.endswith("." + s) for s in GOVERNMENT_SUFFIXES)


# --- what's already known --------------------------------------------------


def known_reasons(
    conn: sqlite3.Connection, *, company: str | None, domain: str | None, emails: list[str] = ()
) -> list[str]:
    """Every reason this company may not be added or contacted."""
    reasons = []
    domains = [d for d in [domain] if d]
    domains += [contact.mail_domain(e) for e in emails if not contact.is_free_mail(e)]
    domains = list(dict.fromkeys(domains))
    for d in domains:
        lead = db.one(conn, "SELECT id, company FROM leads WHERE domain = ?", (d,))
        if lead:
            reasons.append(f"already a lead: {lead['company']} (lead {lead['id']}, {d})")
        lead = db.one(
            conn,
            "SELECT l.id, l.company FROM contacts c JOIN leads l ON l.id = c.lead_id WHERE c.email LIKE ?",
            (f"%@{d}",),
        )
        if lead and not any(f"lead {lead['id']}," in r for r in reasons):
            reasons.append(f"already a lead by address domain: {lead['company']} (lead {lead['id']})")
        if db.one(conn, "SELECT 1 FROM contacted_domains WHERE domain = ?", (d,)):
            reasons.append(f"{d} has been contacted before")
        why = suppression.is_domain_suppressed(conn, d)
        if why:
            reasons.append(f"{d} is suppressed ({why})")
    for email in emails:
        why = suppression.is_suppressed(conn, email)
        if why:
            reasons.append(f"{email} is suppressed ({why})")
    entry = dnc.match(company, domains)
    if entry:
        label = entry.company or entry.domain
        reasons.append(f"on inputs/do-not-contact.csv ({label}{': ' + entry.reason if entry.reason else ''})")
    return reasons


def check(conn: sqlite3.Connection, value: str) -> dict:
    """What the scout knows about a domain, website or company name."""
    looks_like_domain = "." in value and " " not in value.strip()
    domain = contact.site_domain(value) if looks_like_domain else None
    emails = [contact.normalise_email(value)] if "@" in value else []
    if emails:
        domain = None
    reasons = known_reasons(conn, company=None if looks_like_domain else value, domain=domain, emails=emails)
    if domain and is_government(domain):
        reasons.append("government domain (ICP exclusion)")
    if domain and contact.is_third_party_host(domain):
        reasons.append(f"{domain} is a social, directory or marketplace site, not a company website")
    rejected = db.one(conn, "SELECT reason, score, rejected_at FROM scout_rejections WHERE domain = ?", (domain or "",))
    return {
        "value": value,
        "domain": domain,
        "known": bool(reasons),
        "reasons": reasons,
        "looked_at_before": (
            {"reason": rejected["reason"], "score": rejected["score"], "on": rejected["rejected_at"][:10]} if rejected else None
        ),
    }


# --- adding ----------------------------------------------------------------


def _strings(value, name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise LeadError(f"`{name}` must be a list of strings")
    return [v.strip() for v in value if v and v.strip()]


def remember_rejection(conn, *, domain: str, company: str, reason: str, score: int | None) -> None:
    """Record a company looked at and not kept, with its score, for `rejection_months`."""
    conn.execute(
        "INSERT INTO scout_rejections (domain, company, reason, score, rejected_at) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT (domain) DO UPDATE SET company = excluded.company, reason = excluded.reason, "
        "score = excluded.score, rejected_at = excluded.rejected_at",
        (domain, company, reason, score, timeutil.stamp()),
    )


def _reject(conn, outcome: Outcome, reason: str, *, domain: str | None, company: str, remember: bool = True,
            score: int | None = None) -> Outcome:
    outcome.status = "rejected"
    outcome.reasons.append(reason)
    if remember and domain:
        remember_rejection(conn, domain=domain, company=company, reason=reason, score=score)
    log.event(conn, "scout.rejected", {"domain": domain, "reason": _mask(reason)}, agent="scout")
    return outcome


def added_today(conn: sqlite3.Connection, day: str | None = None) -> int:
    return db.scalar(
        conn, "SELECT count(*) FROM leads WHERE substr(created_at, 1, 10) = ?", (day or timeutil.today_str(),)
    ) or 0


@dataclass
class Record:
    """A lead record that passed the structural checks (`parse`)."""

    data: dict
    company: str
    website: str
    domain: str
    industry: str
    observations: list[str]
    sources: list[str]
    reasons: list[str]
    score: int
    raw_contact: dict
    email: str
    hiring_evidence: list[dict]
    comparison: str | None
    breakdown: dict | None
    notes: list[str]


def parse(data) -> Record:
    """Check a lead record's shape, with no side effects. Raises `LeadError`."""
    if not isinstance(data, dict):
        raise LeadError("the lead file must hold one JSON object")
    notes: list[str] = []
    company = str(data.get("company") or "").strip()
    website = str(data.get("website") or "").strip()
    industry = str(data.get("industry") or "").strip()
    observations = _strings(data.get("observations"), "observations")
    sources = _strings(data.get("source_urls"), "source_urls")
    reasons = _strings(data.get("score_reasons"), "score_reasons")
    missing = [
        name
        for name, value in (("company", company), ("website", website), ("industry", industry),
                            ("observations", observations), ("source_urls", sources), ("score_reasons", reasons))
        if not value
    ]
    if missing:
        raise LeadError("missing: " + ", ".join(missing))
    if len(observations) > 3:
        notes.append("kept the first 3 observations")
        observations = observations[:3]
    try:
        score = int(data.get("score"))
    except (TypeError, ValueError):
        raise LeadError("`score` must be a whole number from 0 to 100") from None
    if not 0 <= score <= 100:
        raise LeadError("`score` must be from 0 to 100")

    domain = contact.site_domain(website)
    if not domain or "." not in domain:
        raise LeadError("`website` must be the company's own website URL")
    if not website.lower().startswith(("http://", "https://")):
        website = f"https://{website}"

    raw_contact = data.get("contact") or {}
    if not isinstance(raw_contact, dict):
        raise LeadError("`contact` must be an object: {email, source_url} or {form_url}")
    email = contact.normalise_email(str(raw_contact.get("email") or ""))

    try:
        evidence, evidence_notes = scoring.hiring_evidence(data.get("hiring_evidence"))
        comparison = scoring.comparison(data.get("comparison"))
        breakdown = scoring.breakdown(data.get("score_breakdown"), score, evidence=evidence, has_email=bool(email))
    except scoring.ScoringError as error:
        raise LeadError(str(error)) from None
    return Record(data, company, website, domain, industry, observations, sources, reasons, score, raw_contact,
                  email, evidence, comparison, breakdown, notes + evidence_notes)


def add_lead(conn: sqlite3.Connection, data: dict, *, client: httpx.Client | None = None) -> Outcome:
    return keep(conn, parse(data), client=client)


def keep(conn: sqlite3.Connection, record: Record, *, client: httpx.Client | None = None) -> Outcome:
    """Apply the rules to a parsed record and add it as a lead, or say why not."""
    outcome = Outcome("rejected", notes=list(record.notes))
    data, company, domain, website, score = record.data, record.company, record.domain, record.website, record.score
    observations, sources, reasons = record.observations, record.sources, record.reasons
    raw_contact, email, industry = record.raw_contact, record.email, record.industry

    if contact.is_third_party_host(domain):
        return _reject(conn, outcome, f"{domain} is a social, directory, marketplace, job board or recruiter site, not the company's own website", domain=domain, company=company, score=score)
    if is_government(domain):
        return _reject(conn, outcome, f"{domain} is a government domain (ICP exclusion)", domain=domain, company=company, score=score)
    if not contact.is_site_root(website):
        return _reject(
            conn, outcome,
            f"the website {website} has a path or query; give the company's own home page (https://{domain}). "
            "A listing on another site is not the company's website",
            domain=domain, company=company, remember=False,
        )
    if not any(contact.on_domain(url, domain) for url in sources):
        return _reject(conn, outcome, f"no source URL is on the company's own website ({domain})", domain=domain, company=company, remember=False)

    emails = [email] if email else []

    known = known_reasons(conn, company=company, domain=domain, emails=emails)
    if known:
        duplicate = any(r.startswith("already a lead") for r in known)
        return _reject(conn, outcome, "; ".join(known), domain=domain, company=company, remember=not duplicate, score=score)

    threshold = settings.score_threshold()
    if score < threshold:
        return _reject(conn, outcome, f"score {score} is below {threshold}", domain=domain, company=company, score=score)

    shortlist = settings.shortlist()
    if added_today(conn) >= shortlist:
        return _reject(conn, outcome, f"today's shortlist of {shortlist} leads is already kept", domain=None, company=company)

    tool_slug = str(data.get("tool") or "").strip() or None
    if tool_slug and tool_slug not in registry.live_slugs():
        outcome.notes.append(f"tool {tool_slug!r} is not live in the site registry; no tool recorded")
        tool_slug = None

    channel, status, form_url, contact_row = "none", "no_contact", None, None
    if email:
        verdict = _verify_email(conn, outcome, email, raw_contact, domain, client)
        if isinstance(verdict, str):
            return _reject(conn, outcome, verdict, domain=domain, company=company, remember=False)
        contact_row = verdict
        channel, status = "email", "new"
    elif raw_contact.get("form_url"):
        form_url = str(raw_contact["form_url"]).strip()
        ad = contact.job_ad_problem(form_url)
        if ad:
            return _reject(conn, outcome, ad, domain=domain, company=company, remember=False)
        if not contact.on_domain(form_url, domain):
            return _reject(conn, outcome, f"the contact form must be on the company's own website ({domain})", domain=domain, company=company, remember=False)
        channel, status = "form", "form_only"

    now = timeutil.stamp()
    with db.transaction(conn):
        cursor = conn.execute(
            "INSERT INTO leads (company, display_name, domain, website, industry, size_signal, summary, "
            "observations_json, source_urls_json, score, score_reasons, channel, form_url, tool_slug, status, "
            "hiring_evidence_json, comparison, score_breakdown_json, run_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                company,
                str(data.get("display_name") or "").strip() or display_name(company),
                domain,
                website,
                industry,
                str(data.get("size_signal") or "").strip() or None,
                str(data.get("what_they_do") or data.get("summary") or "").strip() or None,
                json.dumps(observations, ensure_ascii=False),
                json.dumps(sources, ensure_ascii=False),
                score,
                json.dumps(reasons, ensure_ascii=False),
                channel,
                form_url,
                tool_slug,
                status,
                json.dumps(record.hiring_evidence, ensure_ascii=False),
                record.comparison,
                json.dumps(record.breakdown) if record.breakdown is not None else None,
                log.current_run_id(),
                now,
                now,
            ),
        )
        lead_id = cursor.lastrowid
        if contact_row:
            conn.execute(
                "INSERT INTO contacts (lead_id, email, email_hash, source_url, kind, mx_ok, verified_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
                (lead_id, contact_row["email"], suppression.email_hash(contact_row["email"]),
                 contact_row["source_url"], contact_row["kind"], now, now),
            )
        conn.execute("DELETE FROM scout_rejections WHERE domain = ?", (domain,))

    outcome.status = "added"
    outcome.lead_id = lead_id
    outcome.channel = channel
    outcome.contact = contact_row or ({"form_url": form_url} if form_url else None)
    log.event(conn, "scout.lead", {"lead": lead_id, "domain": domain, "channel": channel, "score": score}, agent="scout")
    _post_lead(conn, lead_id)
    return outcome


def check_contact(conn: sqlite3.Connection, *, website: str, email: str, source: str, enquiry_contact: bool = False,
                  client: httpx.Client | None = None) -> dict:
    """`scout check-contact`: the contact rules alone, with no record written."""
    domain = contact.site_domain(website)
    outcome = Outcome("rejected")
    email = contact.normalise_email(email)
    raw = {"email": email, "source_url": source, "enquiry_contact": enquiry_contact}
    if not domain or "." not in domain:
        verdict = "`--website` must be the company's own website URL"
    elif contact.is_third_party_host(domain):
        verdict = f"{domain} is a social, directory, marketplace, job board or recruiter site, not the company's own website"
    else:
        verdict = _verify_email(conn, outcome, email, raw, domain, client)
    if isinstance(verdict, str):
        return {"ok": False, "email": email, "kind": None, "source_url": source, "reason": verdict, "notes": outcome.notes}
    return {"ok": True, "email": verdict["email"], "kind": verdict["kind"], "source_url": verdict["source_url"],
            "reason": None, "notes": outcome.notes}


def _verify_email(conn, outcome: Outcome, email: str, raw: dict, domain: str, client) -> dict | str:
    """The contact row to store, or the reason the address is refused."""
    if not contact.valid_email(email):
        return f"{email!r} is not an email address"
    if contact.not_for_enquiries(email):
        return f"{email} is not an enquiry address"
    not_theirs = contact.ownership_problem(email, domain, settings.free_mail_contacts())
    if not_theirs:
        return not_theirs
    source = str(raw.get("source_url") or "").strip()
    if not source:
        return "an email contact needs `source_url`: the page on the company's own site that lists it"
    ad = contact.job_ad_problem(source)
    if ad:
        return ad
    if not contact.on_domain(source, domain):
        return f"the source page {source} is not on the company's own website ({domain})"

    page = contact.verify_on_page(email, source, domain, client=client)
    if page.error:
        return f"could not verify {email}: {page.error}"
    if not page.found:
        listed = sorted(a for a in page.addresses if not contact.not_for_enquiries(a))
        hint = f" Addresses that page does publish: {', '.join(listed)}." if listed else ""
        return f"unverified: {email} does not appear on {source}.{hint}"

    kind = contact.kind_of(email)
    if kind == "named":
        # Only an address on the company's own domain is swapped for a role
        # address there. A free-mail address is never swapped: when the "site"
        # is a directory, its role address is the directory's own.
        roles = []
        if contact.on_domain(contact.mail_domain(email), domain):
            roles = sorted(
                a for a in page.addresses
                if contact.is_enquiry_role(a) and contact.on_domain(contact.mail_domain(a), domain)
            )
        if roles:
            outcome.notes.append(f"used the role address {roles[0]} from the same page instead of {email}")
            email, kind = roles[0], "role"
        elif not settings.get().get("allow_named_contacts", True):
            return f"{email} is a named address and config allows role addresses only"
        elif raw.get("enquiry_contact") is not True:
            return (
                f"{email} is a named address. Use it only if the site publishes it as the enquiry contact, "
                'and say so with "enquiry_contact": true'
            )

    again = known_reasons(conn, company=None, domain=None, emails=[email])
    if again:
        return "; ".join(again)
    taken = db.one(conn, "SELECT lead_id FROM contacts WHERE email_hash = ?", (suppression.email_hash(email),))
    if taken:
        return f"{email} is already recorded for lead {taken['lead_id']}"
    ok, why = contact.mx_check(contact.mail_domain(email))
    if not ok:
        return f"no mail delivery for {email}: {why}"
    return {"email": email, "source_url": str(page.final_url or source), "kind": kind}


def _post_lead(conn: sqlite3.Connection, lead_id: int) -> None:
    lead = db.one(conn, "SELECT * FROM leads WHERE id = ?", (lead_id,))
    reasons = json.loads(lead["score_reasons"])
    row = db.one(conn, "SELECT email, kind, source_url FROM contacts WHERE lead_id = ?", (lead_id,))
    if row and row["kind"] == "role":
        reach = f"{row['email']} (role address), listed on {row['source_url']}"
    elif row:
        reach = f"{privacy.masked_address(row['email'])} (named address), listed on {row['source_url']}"
    elif lead["form_url"]:
        reach = f"contact form only: {lead['form_url']} (not emailed)"
    else:
        reach = "no published enquiry address (not emailed)"
    text = (
        f"**New lead {lead_id}: {lead['company']}** ({lead['domain']})\n"
        f"{lead['industry']} · score {lead['score']} · top reason: {reasons[0] if reasons else '-'}\n"
        f"Contact: {reach}\n"
        f"Tool: {lead['tool_slug'] or 'none picked yet'}"
    )
    discord.post(conn, "scout-leads", text, username=USERNAME)


# --- reading ---------------------------------------------------------------


def insights(conn: sqlite3.Connection, days: int) -> dict:
    """Industries and observations from recent leads (the app factory reads this)."""
    since = timeutil.stamp(timeutil.now_sgt() - timedelta(days=days))
    rows = db.rows(
        conn, "SELECT industry, observations_json FROM leads WHERE created_at >= ? ORDER BY created_at DESC", (since,)
    )
    industries: dict[str, int] = {}
    observations: list[str] = []
    seen: set[str] = set()
    for row in rows:
        industries[row["industry"]] = industries.get(row["industry"], 0) + 1
        for item in json.loads(row["observations_json"] or "[]"):
            key = item.strip().lower()
            if key and key not in seen and len(observations) < 200:
                seen.add(key)
                observations.append(item.strip())
    return {"industries": dict(sorted(industries.items(), key=lambda kv: (-kv[1], kv[0]))), "observations": observations}


def recent(conn: sqlite3.Connection, *, days: int = 14, status: str | None = None) -> list[dict]:
    since = timeutil.stamp(timeutil.now_sgt() - timedelta(days=days))
    sql = (
        "SELECT l.id, l.company, l.display_name, l.domain, l.industry, l.score, l.channel, l.status, l.tool_slug, "
        "l.observations_json, l.form_url, l.created_at, c.email, c.kind, c.source_url FROM leads l "
        "LEFT JOIN contacts c ON c.lead_id = l.id WHERE l.created_at >= ?"
    )
    params: list = [since]
    if status:
        sql += " AND l.status = ?"
        params.append(status)
    sql += " ORDER BY l.id"
    found = db.rows(conn, sql, tuple(params))
    for row in found:
        row["observations"] = json.loads(row.pop("observations_json") or "[]")
    return found
