"""The community register: Singapore SME groups found by web search
(community scout PRD §5.1, §5.4, §5.5).

A group's own URL may be a facebook.com/groups link: it is recorded so Ting
Yu can open it, never fetched. Source URLs, the pages the facts came from,
must not be on Facebook's domains, because the run never fetches them.
"""

from __future__ import annotations

import json
import re
import sqlite3
from urllib.parse import urlsplit

from jura_growth import config, db, log, timeutil
from jura_growth.agents.community import rules as rules_mod

NAME = "community"
FITS = ("good fit", "possible", "skip")
CHANNELS = ("facebook", "linkedin", "telegram", "whatsapp", "sbf", "asme", "event", "forum", "other")
BLOCKED_DEFAULT = ("facebook.com", "fb.com", "fb.me", "fb.watch", "fbcdn.net", "facebook.net", "messenger.com")
FIELDS = ("channel", "name", "url", "audience", "size_hint", "active_hint", "promo_rules", "fit", "fit_reason", "notes", "source_urls")


class GroupError(ValueError):
    pass


def settings() -> dict:
    return config.agent_config("community")


class BlockedDomainError(ValueError):
    """A blocked_fetch_domains entry that isn't a bare domain. It would make
    deny rules that match no host, so nothing that reads the list carries on."""


BARE_DOMAIN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9-]{2,63}$")


def blocked_domains() -> tuple[str, ...]:
    """The one list of domains the community run may not fetch: Facebook's
    own, plus any in community.yaml. Each covers its subdomains too (the job's
    WebFetch denials, `is_blocked`, `community audit-run`).

    A configured entry must be a bare domain. Case, surrounding spaces, a
    leading "*." and a trailing dot are tidied (" *.Example.COM. " is
    example.com); a URL, path, port or anything else raises BlockedDomainError."""
    configured = []
    for entry in settings().get("blocked_fetch_domains") or ():
        domain = str(entry).strip().lower().removeprefix("*.").rstrip(".")
        if not BARE_DOMAIN_RE.match(domain):
            raise BlockedDomainError(
                f"config/community.yaml blocked_fetch_domains: {entry!r} is not a bare domain; "
                "write it as a host name only, like example.com (it covers every subdomain)"
            )
        configured.append(domain)
    return tuple(dict.fromkeys([*BLOCKED_DEFAULT, *configured]))


def fetch_denials() -> tuple[str, ...]:
    """Claude Code deny rules for every blocked domain. Claude Code matches
    `WebFetch(domain:x)` by exact host and `WebFetch(domain:*.x)` by subdomain
    only (2.1.310, checked with a headless probe), so each domain gets both."""
    return tuple(
        rule for domain in blocked_domains()
        for rule in (f"WebFetch(domain:{domain})", f"WebFetch(domain:*.{domain})")
    )


def host(url: str) -> str:
    candidate = url if re.match(r"^[a-z][a-z0-9+.-]*://", url, re.I) else f"https://{url}"
    try:
        return (urlsplit(candidate).hostname or "").lower()
    except ValueError:
        return ""


def is_blocked(url: str) -> bool:
    h = host(url)
    return any(h == d or h.endswith("." + d) for d in blocked_domains())


def url_key(url: str) -> str:
    """A URL reduced to what identifies the group: host without www/m/web, path."""
    parts = urlsplit(url.strip() if re.match(r"^https?://", url.strip(), re.I) else f"https://{url.strip()}")
    h = (parts.hostname or "").lower()
    for prefix in ("www.", "m.", "web.", "mbasic."):
        if h.startswith(prefix):
            h = h[len(prefix):]
    path = re.sub(r"/+$", "", parts.path or "").lower()
    return f"{h}{path}"


def slugify(name: str) -> str:
    slug = re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", name.lower())).strip("-")
    return slug[:40].rstrip("-") or "group"


def _unique_slug(conn: sqlite3.Connection, name: str) -> str:
    base = slugify(name)
    slug, n = base, 2
    while db.scalar(conn, "SELECT 1 FROM community_groups WHERE slug = ?", (slug,)):
        slug, n = f"{base}-{n}", n + 1
    return slug


def validate(record: dict) -> tuple[dict, list[str]]:
    """A clean record and its problems (empty means it can be added)."""
    errors: list[str] = []
    if not isinstance(record, dict):
        return {}, ["each group must be a JSON object"]
    unknown = set(record) - set(FIELDS) - {"id", "sources"}
    if unknown:
        errors.append(f"unknown fields: {', '.join(sorted(unknown))}")
    clean = {k: (record.get(k).strip() if isinstance(record.get(k), str) else record.get(k)) for k in FIELDS}
    clean["channel"] = (clean.get("channel") or "facebook").lower()
    if clean["channel"] not in CHANNELS:
        errors.append(f"channel must be one of {', '.join(CHANNELS)}")
    if not clean.get("name"):
        errors.append("name is required")
    url = clean.get("url") or ""
    if not re.match(r"^https?://\S+$", url):
        errors.append("url must be the group's full http(s) link")
    elif clean["channel"] == "facebook":
        if not (host(url) in ("facebook.com",) or host(url).endswith(".facebook.com")) or "/groups/" not in url.lower():
            errors.append("a Facebook group's url must be its facebook.com/groups/... link (recorded, never fetched)")
    elif is_blocked(url):
        errors.append(f"a {clean['channel']} group's url can't be on a Facebook domain")
    fit = (clean.get("fit") or "").lower()
    if fit not in FITS:
        errors.append("fit must be \"good fit\", \"possible\" or \"skip\"")
    clean["fit"] = fit
    if not clean.get("fit_reason"):
        errors.append("fit_reason is required: say why it is or isn't a fit")
    if not clean.get("promo_rules"):
        errors.append("promo_rules is required: the stated promotion rules, or \"not stated in public sources\"")

    sources = record.get("source_urls", record.get("sources")) or []
    if isinstance(sources, str):
        sources = [sources]
    if not isinstance(sources, list):
        errors.append("source_urls must be a list")
        sources = []
    cleaned_sources = []
    for source in sources:
        source = str(source).strip()
        if not source:
            continue
        if is_blocked(source):
            errors.append(f"source URL on a Facebook domain is not allowed (the run never fetches Facebook): {source}")
            continue
        if not re.match(r"^https?://\S+$", source):
            errors.append(f"source must be a full http(s) URL: {source}")
            continue
        cleaned_sources.append(source)
    if not cleaned_sources and not any("Facebook domain" in e for e in errors):
        errors.append("source_urls needs at least one non-Facebook page the facts came from")
    clean["source_urls"] = cleaned_sources
    return clean, errors


def add(conn: sqlite3.Connection, record: dict) -> tuple[str, int | None, list[str]]:
    """("added" | "duplicate" | "rejected", group id, messages)."""
    clean, errors = validate(record)
    if errors:
        return "rejected", None, errors
    key = url_key(clean["url"])
    existing = db.one(conn, "SELECT id, name FROM community_groups WHERE url_key = ?", (key,))
    if existing is None:
        existing = db.one(
            conn,
            "SELECT id, name FROM community_groups WHERE lower(name) = lower(?) AND channel = ?",
            (clean["name"], clean["channel"]),
        )
    if existing:
        return "duplicate", existing["id"], [f"already in the register as group {existing['id']} ({existing['name']})"]
    now = timeutil.stamp()
    cursor = conn.execute(
        "INSERT INTO community_groups (channel, name, slug, url, url_key, audience, size_hint, active_hint, promo_rules, "
        "fit, fit_reason, notes, source_urls_json, run_id, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            clean["channel"], clean["name"], _unique_slug(conn, clean["name"]), clean["url"], key,
            clean.get("audience"), clean.get("size_hint"), clean.get("active_hint"), clean.get("promo_rules"),
            clean["fit"], clean["fit_reason"], clean.get("notes"), json.dumps(clean["source_urls"]),
            log.current_run_id(), now, now,
        ),
    )
    log.event(conn, "community.group.added", {"id": cursor.lastrowid, "name": clean["name"], "fit": clean["fit"]}, agent=NAME)
    return "added", cursor.lastrowid, []


SETTABLE = {
    "joined", "rules", "promo_rules", "rules_confirmed", "promo_days", "post_days",
    "fit", "fit_reason", "notes", "audience", "size_hint", "active_hint", "name",
}
DAY_COLUMNS = {"promo_days": "promo_days_confirmed", "post_days": "post_days_confirmed"}
YES = {"yes", "y", "true", "1", "on"}
NO = {"no", "n", "false", "0", "off"}


def set_fields(conn: sqlite3.Connection, group_id: int, pairs: list[str]) -> dict:
    group = get(conn, group_id)
    if group is None:
        raise GroupError(f"no group {group_id}")
    updates: dict[str, object] = {}
    for pair in pairs:
        if "=" not in pair:
            raise GroupError(f"expected key=value, got {pair!r}")
        key, _, value = pair.partition("=")
        key, value = key.strip().lower(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if key not in SETTABLE:
            raise GroupError(f"can't set {key!r}; settable: {', '.join(sorted(SETTABLE))}")
        if key in ("joined", "rules_confirmed"):
            if value.lower() not in YES | NO:
                raise GroupError(f"{key} must be yes or no")
            updates[key] = 1 if value.lower() in YES else 0
        elif key == "fit":
            if value.lower() not in FITS:
                raise GroupError("fit must be \"good fit\", \"possible\" or \"skip\"")
            if group["removed"] and value.lower() != "skip":
                raise GroupError(f"group {group_id} was removed after an admin warning or removal; it stays skip")
            updates["fit"] = value.lower()
        elif key in ("rules", "promo_rules"):
            updates["promo_rules"] = value
        elif key in DAY_COLUMNS:
            try:
                updates[DAY_COLUMNS[key]] = rules_mod.days_text(rules_mod.read_days(value))
            except ValueError as error:
                raise GroupError(f"{key}: {error}") from None
        else:
            updates[key] = value
    if not updates:
        raise GroupError("nothing to set")
    if "promo_rules" in updates and updates["promo_rules"] != group["promo_rules"]:
        # days confirmed for the old text don't carry over to new text
        for column in DAY_COLUMNS.values():
            updates.setdefault(column, None)
    if updates.get("rules_confirmed") == 1:
        _check_days_confirmed({**group, **updates})
    updates["updated_at"] = timeutil.stamp()
    assignments = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(f"UPDATE community_groups SET {assignments} WHERE id = ?", (*updates.values(), group_id))
    log.event(conn, "community.group.set", {"id": group_id, **{k: v for k, v in updates.items() if k != "updated_at"}}, agent=NAME)
    return get(conn, group_id)


def _check_days_confirmed(group: dict) -> None:
    """Confirming a group's rules means saying which days are open, for every group:
    code never reads days out of the rules text. A later change of rules text clears
    the days, and the group has no open day until Ting Yu sets them again."""
    missing = [key for key, column in DAY_COLUMNS.items() if group.get(column) is None]
    if missing:
        raise GroupError(
            f"say which days are open for these rules (\"{group['promo_rules'] or 'unknown'}\") as well: "
            "promo_days=... post_days=..., each any, none, or days like sat,sun or mon-fri "
            f"(missing: {', '.join(missing)})"
        )


def remove(conn: sqlite3.Connection, group_id: int, reason: str) -> dict:
    group = get(conn, group_id)
    if group is None:
        raise GroupError(f"no group {group_id}")
    now = timeutil.stamp()
    conn.execute(
        "UPDATE community_groups SET fit = 'skip', removed = 1, fit_reason = ?, updated_at = ? WHERE id = ?",
        (f"removed: {reason} ({timeutil.today_str()})", now, group_id),
    )
    skipped = conn.execute(
        "UPDATE community_posts SET status = 'skipped' WHERE group_id = ? AND status = 'planned'", (group_id,)
    ).rowcount
    log.event(conn, "community.group.removed", {"id": group_id, "reason": reason, "planned_skipped": skipped}, level="warning", agent=NAME)
    return get(conn, group_id)


def get(conn: sqlite3.Connection, group_id: int) -> dict | None:
    return db.one(conn, "SELECT * FROM community_groups WHERE id = ?", (int(group_id),))


def all_groups(conn: sqlite3.Connection) -> list[dict]:
    return db.rows(conn, "SELECT * FROM community_groups ORDER BY id")


def eligible(conn: sqlite3.Connection) -> list[dict]:
    """Groups a weekly plan may use: Facebook, joined, good fit, not removed."""
    return db.rows(
        conn,
        "SELECT * FROM community_groups WHERE channel = 'facebook' AND joined = 1 AND fit = 'good fit' AND removed = 0 ORDER BY id",
    )


def counts(conn: sqlite3.Connection) -> dict:
    row = db.one(
        conn,
        "SELECT count(*) AS total, "
        "sum(fit = 'good fit') AS good_fit, sum(fit = 'possible') AS possible, sum(fit = 'skip') AS skip, "
        "sum(joined = 1) AS joined, sum(joined = 1 AND fit = 'good fit' AND removed = 0 AND channel = 'facebook') AS plannable "
        "FROM community_groups",
    ) or {}
    return {k: int(v or 0) for k, v in row.items()}


def rules_for(group: dict) -> rules_mod.Rules:
    """The group's rules, with the days Ting Yu confirmed. Plans, `context` and the
    checklist read rules only through this."""
    return rules_mod.confirm_days(
        rules_mod.parse(group.get("promo_rules")), group.get("promo_days_confirmed"), group.get("post_days_confirmed")
    )
