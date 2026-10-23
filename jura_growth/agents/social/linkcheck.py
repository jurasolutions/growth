"""Do the source links work? Block 1's done-when asks for working source links.

A link that answers 404 or 410, or can't be reached at all (no such host,
refused, bad certificate), sends the draft back. Sites that turn scripts away
(401, 403, 429), are briefly down (5xx) or are slow to answer are accepted
with a note, because a reader's browser will usually get through.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36 jura-growth-linkcheck"
)
BROKEN = {404, 410}


@dataclass
class LinkStatus:
    url: str
    status: int | None
    ok: bool
    note: str = ""


def check(url: str, client: httpx.Client) -> LinkStatus:
    try:
        response = client.get(url)
    except httpx.TimeoutException:
        return LinkStatus(url, None, True, "timed out; accepted")
    except httpx.HTTPError as error:
        return LinkStatus(url, None, False, f"unreachable ({type(error).__name__})")
    status = response.status_code
    if status < 400:
        return LinkStatus(url, status, True)
    if status in BROKEN:
        return LinkStatus(url, status, False, f"answers {status}")
    return LinkStatus(url, status, True, f"answers {status} to scripts; accepted")


def check_all(urls: list[str], *, client: httpx.Client | None = None, timeout: float = 15.0) -> list[LinkStatus]:
    owns = client is None
    client = client or httpx.Client(
        timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"}
    )
    try:
        return [check(url, client) for url in urls]
    finally:
        if owns:
            client.close()
