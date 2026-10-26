"""The fixture platform: the publish job pointed at the local fixture site, for Ting Yu's
rehearsal R1 to R6 (BP-07; `uat.md` Part R; test strategy v3 §7).

`JURA_GROWTH_PUBLISH_FIXTURE_URL` (for example `http://publish-fixture.localhost:8765`) names the
fixture site, served on loopback from `tests/fixtures/publish-site/`. While it is set, it takes the
place of every platform's own hosts, so the rehearsal drives the real publish job, prompt and audit:

- the run's only domain rule is `ClaudeInChromeDomain(<fixture host>)` (`scope.browser_hosts`);
- every address the publish code accepts must be on the fixture, with the same scheme, host and
  port and no user name: a `page_url` (`hosts.problem`), `publish done --url`, `publish resolve
  --url` and every address the audit reads. Facebook's own hosts, and every other, are refused;
- `publish next` hands out only an item whose target is on the fixture (`claim`).

This module is the one place that decides whether the fixture may be used, in the guard style of
the UAT stubs (`uat_stub`, ticket 18):

- the URL must be `http://` on a loopback host (`localhost`, a `*.localhost` name, `127.0.0.1` or
  `::1`), with no user name, path, query or fragment;
- the data folder must be a temporary one (`uat_stub.temporary_data_problem`), so the fixture can
  never be switched on against the live `data/growth/`.

A refused fixture is never swapped for the real hosts: `active()` raises `FixtureRefused`, so the
publish precheck fails the run before Claude starts, the argv can't be built, and `publish next`
claims nothing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from jura_growth import uat_stub

ENV = "JURA_GROWTH_PUBLISH_FIXTURE_URL"
_LOOPBACK = ("localhost", "127.0.0.1", "::1")


class FixtureRefused(RuntimeError):
    pass


@dataclass(frozen=True)
class Fixture:
    """The fixture site: `scheme://host[:port]`."""

    scheme: str
    host: str
    port: int | None

    @property
    def base(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{self.scheme}://{host}" + (f":{self.port}" if self.port is not None else "")

    def url_problem(self, url: str | None) -> str | None:
        """Why `url` isn't an address on the fixture site, or None when it is. Names the host,
        never the rest of the address."""
        text = (url or "").strip()
        if not text:
            return "no URL given"
        try:
            parts = urlsplit(text)
            port = parts.port
        except ValueError:
            return "an address that isn't a URL"
        host = (parts.hostname or "").lower() or "an empty host"
        if parts.username is not None or parts.password is not None or "@" in parts.netloc:
            return f"the address on {host} carries a user name"
        if parts.scheme != self.scheme or host != self.host or port != self.port:
            return f"{host} isn't the fixture site ({self.base}): the fixture platform allows no other host"
        return None


def problem() -> str | None:
    """Why the fixture in `ENV` may not be used, or None (also None when it is unset)."""
    value = os.environ.get(ENV)
    if not value:
        return None
    try:
        parts = urlsplit(value.strip())
        parts.port  # noqa: B018 - raises on a malformed port
    except ValueError:
        return f"{ENV} isn't a URL: point it at the local fixture site (http://publish-fixture.localhost:<port>)"
    host = (parts.hostname or "").lower()
    loopback = host in _LOOPBACK or host.endswith(".localhost")
    bare = parts.path in ("", "/") and not parts.query and not parts.fragment
    if parts.scheme != "http" or not loopback or "@" in parts.netloc or not bare:
        return (f"{ENV} must be the local fixture site on a loopback host (http://publish-fixture.localhost:<port>), "
                f"not {value}")
    data = uat_stub.temporary_data_problem()
    return f"{ENV} is for the rehearsal only, and {data}" if data else None


def active() -> Fixture | None:
    """The fixture site, or None when `ENV` is unset. Raises `FixtureRefused` with the reason
    when it may not be used: never falls back to the platforms' own hosts."""
    refused = problem()
    if refused:
        raise FixtureRefused(refused)
    value = os.environ.get(ENV)
    if not value:
        return None
    parts = urlsplit(value.strip())
    return Fixture(parts.scheme, (parts.hostname or "").lower(), parts.port)


def target_problem(url: str | None) -> str | None:
    """With the fixture on, why `url` isn't on it; None when it is, or when the fixture is off.
    Raises `FixtureRefused` as `active()` does."""
    site = active()
    return site.url_problem(url) if site else None
