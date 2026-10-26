"""Each platform's own hosts, and the check every recorded URL passes (AC-P7.2).

A page URL in `config/social.yaml` and a live post URL from `publish done` or `publish resolve`
must be `https://`, with no user name, password or port, on exactly one of the platform's hosts.
Look-alikes (`facebook.com.evil.test`, `https://www.facebook.com@evil.test`,
`evil.test/www.facebook.com`, `javascript:`) fail.

Facebook's hosts are proved in BP-02a; BP-04 proves Instagram's and LinkedIn's.

`BROWSER_HOSTS` are the hosts a publish run's tab may be on: the publish job's
`ClaudeInChromeDomain(<host>)` rules (`scope.py`) and the hosts the transcript audit accepts
(`audit.py`). They are the post-URL hosts plus the ones the page tools need to post as the Page
(`business.facebook.com`, where a Page admin's composer may open). Each is listed explicitly
until BP-01's check U18 shows how the domain rule treats subdomains; image CDN hosts are not
listed, because a run never opens one in its tab. Only the platforms in `BROWSER_PLATFORMS` are
driven in this build: BP-04 adds Instagram and LinkedIn.
"""

from __future__ import annotations

from urllib.parse import urlsplit

HOSTS: dict[str, tuple[str, ...]] = {
    "facebook": ("www.facebook.com", "facebook.com", "m.facebook.com", "web.facebook.com"),
    "instagram": ("www.instagram.com", "instagram.com"),
    "linkedin": ("www.linkedin.com", "linkedin.com"),
}

BROWSER_PLATFORMS: tuple[str, ...] = ("facebook",)
BROWSER_HOSTS: dict[str, tuple[str, ...]] = {
    "facebook": (*HOSTS["facebook"], "business.facebook.com"),
}


def problem(platform: str, url: str | None) -> str | None:
    """Why `url` isn't an address on `platform`, or None when it is."""
    allowed = HOSTS.get(platform)
    if not allowed:
        return f"{platform} has no known hosts"
    return url_problem(url, allowed, f"{platform}'s hosts ({', '.join(allowed)})")


def url_problem(url: str | None, allowed: tuple[str, ...] | list[str], named: str = "the allowed hosts") -> str | None:
    """Why `url` isn't an `https://` address with no user name, password or port on exactly one
    of `allowed`, or None when it is. The one check for post URLs (`problem`) and for the
    addresses a publish run's tab went to (`audit.py`). It names the host, never the rest of the
    address."""
    text = (url or "").strip()
    if not text:
        return "no URL given"
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        return "an address that isn't a URL"
    host = (parts.hostname or "").lower() or "an empty host"
    if parts.scheme != "https":
        return f"{host} isn't an https:// address"
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        return f"the address on {host} carries a user name"
    if port is not None:
        return f"the address on {host} names a port"
    if host not in allowed:
        return f"{host} isn't one of {named}"
    return None
