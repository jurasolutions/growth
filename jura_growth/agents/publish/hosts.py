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

from jura_growth.agents.publish import fixture

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


def _path(url: str) -> str:
    """`url`'s path, lower-cased, with no query, fragment or trailing slash."""
    return urlsplit(url.strip()).path.rstrip("/").lower()


# One group's own address: `/groups/<one segment>`, with an optional trailing slash (code review
# 06, S7). The segment is a group's id or its name in the address, never `.` or `..`, and holds no
# percent-encoding, `;` or anything else a path could be bent with.
_GROUP_PATH = re.compile(r"/groups/([A-Za-z0-9._-]+)/?")
GROUP_SHAPE = "one group's own address, https://www.facebook.com/groups/<group>/"


def group_url_problem(url: str | None) -> str | None:
    """Why `url` isn't one Facebook group's own address, or None when it is: `https://` on
    Facebook's hosts (or, while the fixture platform is on, an address on the fixture site), with
    the path `/groups/<one segment>[/]` and no query or fragment. The register holds only such
    addresses (`community.groups.validate`), and an item never acts in a group whose address
    isn't one (`group_kinds.gone`). Names the host, never the path."""
    text = (url or "").strip()
    try:
        parts = urlsplit(text)
    except ValueError:
        return "an address that isn't a URL"
    site = fixture.active()
    if site is not None and (parts.hostname or "").lower() == site.host:
        wrong = site_problem(text, site)
    else:
        wrong = url_problem(text, HOSTS["facebook"], f"Facebook's hosts ({', '.join(HOSTS['facebook'])})")
    if wrong:
        return wrong
    match = _GROUP_PATH.fullmatch(parts.path)
    if "?" in text or "#" in text or match is None or match.group(1) in (".", ".."):
        return f"the address on {(parts.hostname or '').lower()} isn't {GROUP_SHAPE}"
    return None


# One post's own address inside a group (BP-05): `/groups/<group>/posts/<n>` or
# `/groups/<group>/permalink/<n>`, with an optional trailing slash. The query and fragment don't count.
_GROUP_POST_PATH = re.compile(r"/groups/([A-Za-z0-9._-]+)/(?:posts|permalink)/([0-9]+)/?")
GROUP_POST_SHAPE = "one post's own address in the item's group, /groups/<group>/posts/<number>/"


def group_post_problem(url: str | None, group_url: str) -> str | None:
    """Why `url` isn't one post's own address inside the group at `group_url` (`publish done` and
    `publish resolve` for a community post), or None when it is: on Facebook's hosts (the fixture
    site while it is on), and in the shape `/groups/<that group>/posts/<number>/` or
    `/permalink/<number>/`. Another group's post, the group's own page, the Page's timeline and a
    path with `.` or `..` are all refused. Names the host, never the path."""
    wrong = problem("facebook", url)
    if wrong:
        return wrong
    parts = urlsplit((url or "").strip())
    match = _GROUP_POST_PATH.fullmatch(parts.path)
    if match is None or not within(url or "", group_url) or match.group(1) in (".", ".."):
        return f"the address on {(parts.hostname or '').lower()} isn't {GROUP_POST_SHAPE}"
    return None


def within(url: str, place: str) -> bool:
    """Whether `url` is `place` or a page under it, on any of the same platform's hosts: a group's
    own address (`/groups/<id>`), its posts, members or About. The query and fragment don't count;
    the path must match whole segments, so `/groups/a-10` isn't inside `/groups/a-1`. It fails
    closed on a `place` that isn't one group's own path, and on a `url` with a `.` or `..`
    segment (code review 06, S7 and N10). The host is checked separately (`url_problem`)."""
    try:
        path, root = _path(url), _path(place)
        raw = urlsplit(url.strip()).path
    except ValueError:
        return False
    if not _GROUP_PATH.fullmatch(root) or any(segment in (".", "..") for segment in raw.split("/")):
        return False
    return path == root or path.startswith(root + "/")


def same_place(url: str, place: str) -> bool:
    """`url` is exactly `place` (`publish done --outcome --url`): the same host and path, whatever
    the query, fragment or trailing slash."""
    try:
        return (urlsplit(url.strip()).hostname or "").lower() == (urlsplit(place.strip()).hostname or "").lower() \
            and _path(url) == _path(place)
    except ValueError:
        return False


def problem(platform: str, url: str | None) -> str | None:
    """Why `url` isn't an address on `platform`, or None when it is. While the fixture platform is
    on (`fixture.py`, BP-07), every platform's only address is the fixture site. Raises
    `fixture.FixtureRefused` when the fixture is set but refused."""
    site = fixture.active()
    if site is not None:
        return site_problem(url, site)
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


def site_problem(url: str | None, site: fixture.Fixture) -> str | None:
    """Why `url` isn't an address on the fixture site (its scheme, its host and its port), naming
    the fixture so the refusal says why, or None when it is."""
    problem = url_problem(url, (site.host,), f"the fixture site's hosts ({site.host})", scheme=site.scheme,
                          port=site.port)
    return f"{problem} (the fixture platform allows only {site.base})" if problem else None


def fixture_target_problem(url: str | None) -> str | None:
    """While the fixture platform is on, why `url` isn't on the fixture site; None when it is, or
    when the fixture is off. Raises as `fixture.active()` does."""
    site = fixture.active()
    return site_problem(url, site) if site is not None else None


def url_problem(url: str | None, allowed: tuple[str, ...] | list[str], named: str = "the allowed hosts", *,
                scheme: str = "https", port: int | None = None) -> str | None:
    """Why `url` isn't a `scheme://` address with no user name or password, on exactly one of
    `allowed` and on `port` (no port, by default), or None when it is. The one check for post URLs
    (`problem`), for the fixture site (`site_problem`) and for the addresses a publish run's tab
    went to (`audit.py`). A backslash, which a browser reads as `/` (code review 07, B1), is
    refused anywhere. It names the host, never the rest of the address."""
    text = (url or "").strip()
    if not text:
        return "no URL given"
    try:
        parts = urlsplit(text)
        given = parts.port
    except ValueError:
        return "an address that isn't a URL"
    host = (parts.hostname or "").lower() or "an empty host"
    if "\\" in text:
        return f"the address on {host} holds a backslash"
    if parts.scheme != scheme:
        return f"{host} isn't an {scheme}:// address"
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        return f"the address on {host} carries a user name"
    if given != port:
        return f"the address on {host} names a port" if port is None else f"the address on {host} isn't on port {port}"
    if host not in allowed:
        return f"{host} isn't one of {named}"
    return None
