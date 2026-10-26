"""Each platform's own hosts, and the check every recorded URL passes (AC-P7.2).

A page URL in `config/social.yaml` and a live post URL from `publish done` or `publish resolve`
must be `https://`, with no user name, password or port, on exactly one of the platform's hosts.
Look-alikes (`facebook.com.evil.test`, `https://www.facebook.com@evil.test`,
`evil.test/www.facebook.com`, `javascript:`) fail. For Instagram and LinkedIn the path must have
the right shape too: a post URL must be one post's own address (`post_problem`), and a
`page_url` the account's profile or the company page (`page_problem`).

Facebook's hosts are proved in BP-02a; BP-04 proves Instagram's and LinkedIn's.

`BROWSER_HOSTS` are the hosts a publish run's tab may be on: the publish job's
`ClaudeInChromeDomain(<host>)` rules (`scope.py`) and the hosts the transcript audit accepts
(`audit.py`). They are the post-URL hosts plus the ones the page tools need to post as the Page
(`business.facebook.com`, where a Page admin's composer may open). Instagram and LinkedIn need
nothing beyond their post-URL hosts: the composer, the identity check and the permalink are all
on `www.`, and the bare host only redirects there. Each is listed explicitly until BP-01's check
U18 shows how the domain rule treats subdomains. No image CDN (`*.fbcdn.net`, `*.cdninstagram.com`,
`media.licdn.com`), link shim (`l.facebook.com`, `l.instagram.com`, `lnkd.in`) or help host is
listed, because a run never opens one in its tab. `BROWSER_PLATFORMS` are the platforms this build
drives: Facebook from BP-03, Instagram and LinkedIn from BP-04.
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

HOSTS: dict[str, tuple[str, ...]] = {
    "facebook": ("www.facebook.com", "facebook.com", "m.facebook.com", "web.facebook.com"),
    "instagram": ("www.instagram.com", "instagram.com"),
    "linkedin": ("www.linkedin.com", "linkedin.com"),
}

BROWSER_PLATFORMS: tuple[str, ...] = ("facebook", "instagram", "linkedin")
BROWSER_HOSTS: dict[str, tuple[str, ...]] = {
    "facebook": (*HOSTS["facebook"], "business.facebook.com"),
    # The web composer for the Jura account and the post's permalink are both on these hosts.
    "instagram": HOSTS["instagram"],
    # The company page's admin view, its "Start a post" composer and the post's permalink.
    "linkedin": HOSTS["linkedin"],
}


# The shape of a post's own address and of the page a run posts to, per platform (code review 04,
# S4 and S5), judged on the path after percent-decoding; the query and fragment are ignored. A
# profile, a feed or a company page is never a post, and a person's profile is never the LinkedIn
# company page. Facebook's post addresses take several forms (`/posts/`, `story_fbid`, photo
# posts), so it has no shape here until rehearsal R1 records the one its Page posts get.
_INSTAGRAM_RESERVED = r"(?!(?:p|reel|reels|explore|accounts|direct|stories|tv|about|legal|web|developer)/?$)"
POST_PATHS: dict[str, tuple[re.Pattern[str], ...]] = {
    "instagram": (re.compile(r"/(?:p|reel)/[A-Za-z0-9_-]+/?"),),
    "linkedin": (re.compile(r"/feed/update/urn:li:(?:activity|share|ugcPost):\d+/?"),
                 re.compile(r"/posts/[^/]+-(?:activity|share|ugcPost)-\d+(?:-[A-Za-z0-9]+)?/?")),
}
PAGE_PATHS: dict[str, tuple[re.Pattern[str], ...]] = {
    "instagram": (re.compile(rf"/{_INSTAGRAM_RESERVED}[A-Za-z0-9._-]{{1,30}}/?"),),
    "linkedin": (re.compile(r"/company/[^/]+(?:/.*)?"),),
}
POST_NAMES = {"instagram": "an Instagram post's own address (/p/<code>/ or /reel/<code>/)",
              "linkedin": "a LinkedIn post's own address (/feed/update/urn:li:activity:<n>/, or a /posts/ address)"}
PAGE_NAMES = {"instagram": "an Instagram account's profile (/<account>/)",
              "linkedin": "a LinkedIn company page (/company/<page>/), never a person's profile"}


def problem(platform: str, url: str | None) -> str | None:
    """Why `url` isn't an address on `platform`, or None when it is. While the fixture platform is
    on (`fixture.py`, BP-07), every platform's only address is the fixture site."""
    from jura_growth.agents.publish import fixture

    site = fixture.active()
    if site is not None:
        return site.url_problem(url)
    allowed = HOSTS.get(platform)
    if not allowed:
        return f"{platform} has no known hosts"
    return url_problem(url, allowed, f"{platform}'s hosts ({', '.join(allowed)})")


def post_problem(platform: str, url: str | None) -> str | None:
    """Why `url` isn't the address of one post on `platform` (`publish done`, `publish resolve`),
    or None when it is: on the platform's hosts, and in its post shape (`POST_PATHS`)."""
    return problem(platform, url) or _shape(platform, url, POST_PATHS, POST_NAMES)


def page_problem(platform: str, url: str | None) -> str | None:
    """Why `url` isn't the page a run posts to on `platform` (`page_url`), or None when it is."""
    return problem(platform, url) or _shape(platform, url, PAGE_PATHS, PAGE_NAMES)


def _shape(platform: str, url: str | None, shapes: dict, names: dict) -> str | None:
    """The shape check, for an address on the platform's own hosts only (anything else was judged
    by `problem`). Names the host, never the path."""
    parts = urlsplit((url or "").strip())
    host = (parts.hostname or "").lower()
    if host not in HOSTS.get(platform, ()) or platform not in shapes:
        return None
    path = unquote(parts.path)
    if any(pattern.fullmatch(path) for pattern in shapes[platform]):
        return None
    return f"the address on {host} isn't {names[platform]}"


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
