"""The fixture platform: the publish job pointed at the local fixture site, for Ting Yu's
rehearsal R1 to R6 (BP-07; `uat.md` Part R; test strategy v3 §7).

`JURA_GROWTH_PUBLISH_FIXTURE_URL` (for example `http://publish-fixture.localhost:8765`) names the
fixture site, served on loopback from `tests/fixtures/publish-site/`. While it is set, it takes the
place of every platform's own hosts, so the rehearsal drives the real publish job, prompt and audit:

- the run's only domain rule is `ClaudeInChromeDomain(<fixture host>)` (`scope.browser_hosts`);
- every address the publish code accepts must be on the fixture, with the same scheme, host and
  port and no user name (`hosts.site_problem`): a `page_url`, `publish done --url`, `publish
  resolve --url` and every address the audit reads. Facebook's own hosts, and every other, are
  refused;
- `publish next` hands out only an item whose target is on the fixture (`claim`).

This module decides whether the fixture may be used, through the UAT stubs' own loopback guard
(`uat_stub.loopback_problem`, ticket 18):

- the URL must be `http://` on `publish-fixture.localhost` or a loopback address literal
  (`127.0.0.1`, `[::1]`), read as a browser reads it (no backslash, percent-encoding, user name,
  whitespace or non-ASCII character), with no path, query or fragment. Not `localhost` or any other
  `*.localhost` name, so the page tools stay off every other local service (code review 07,
  SEC-n1). The domain rule names the host and its port, the way Chrome matches it (`scope.domain_rules`,
  rehearsal R1 2026-10-30);
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
ALLOWED_HOSTS = ("publish-fixture.localhost", "127.0.0.1", "::1")


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


def problem() -> str | None:
    """Why the fixture in `ENV` may not be used, or None (also None when it is unset)."""
    return uat_stub.loopback_problem(
        ENV, hosts=ALLOWED_HOSTS, bare=True, purpose="the rehearsal",
        expected="the local fixture site on a loopback host (http://publish-fixture.localhost:<port>)",
    )


def active() -> Fixture | None:
    """The fixture site, or None when `ENV` is unset. Raises `FixtureRefused` with the reason
    when it may not be used: never falls back to the platforms' own hosts."""
    refused = problem()
    if refused:
        raise FixtureRefused(refused)
    value = os.environ.get(ENV)
    if not value:
        return None
    parts = urlsplit(value)
    return Fixture(parts.scheme, parts.hostname or "", parts.port)
