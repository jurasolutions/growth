"""Each platform's own hosts, and the check every recorded URL passes (AC-P7.2).

A page URL in `config/social.yaml` and a live post URL from `publish done` or `publish resolve`
must be `https://`, with no user name, password or port, on exactly one of the platform's hosts.
Look-alikes (`facebook.com.evil.test`, `https://www.facebook.com@evil.test`,
`evil.test/www.facebook.com`, `javascript:`) fail.

Facebook's hosts are proved in BP-02a; BP-04 proves Instagram's and LinkedIn's, and BP-03 turns
the same lists into the publish job's `ClaudeInChromeDomain` rules.
"""

from __future__ import annotations

from urllib.parse import urlsplit

HOSTS: dict[str, tuple[str, ...]] = {
    "facebook": ("www.facebook.com", "facebook.com", "m.facebook.com", "web.facebook.com"),
    "instagram": ("www.instagram.com", "instagram.com"),
    "linkedin": ("www.linkedin.com", "linkedin.com"),
}


def problem(platform: str, url: str | None) -> str | None:
    """Why `url` isn't an address on `platform`, or None when it is."""
    allowed = HOSTS.get(platform)
    if not allowed:
        return f"{platform} has no known hosts"
    text = (url or "").strip()
    if not text:
        return "no URL given"
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        return f"{text!r} isn't a URL"
    if parts.scheme != "https":
        return f"{text!r} isn't an https:// address"
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        return f"{text!r} carries a user name"
    if port is not None:
        return f"{text!r} names a port"
    host = (parts.hostname or "").lower()
    if host not in allowed:
        return f"{host or 'an empty host'} isn't one of {platform}'s hosts ({', '.join(allowed)})"
    return None
