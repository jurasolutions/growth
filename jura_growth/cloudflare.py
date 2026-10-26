"""Read access to the website's D1 database through the Cloudflare API.

The site keeps two things the growth engine needs: the suppression list
(unsubscribes and Resend bounce and complaint webhooks) and anonymous toolbox
usage counts. Both live in D1 because the site writes them. The token needs
only D1 read and edit on that one database.
"""

from __future__ import annotations

import os

import httpx

from jura_growth import config, uat_stub

API = "https://api.cloudflare.com/client/v4"
# The UAT harness only (uat.md Part A, ticket 18): point D1 at the local stub,
# `uv run python -m tests.resend_stub`, together with Resend. `uat_stub` decides
# whether it may be used; a refused one is never sent to Cloudflare instead. The
# stub never sees the real token or ids.
BASE_ENV = uat_stub.D1_ENV
SECRETS = ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "D1_DATABASE_ID")
_STUB_CREDENTIALS = ("uat-stub", "uat", "uat")  # token, account, database


class D1Error(RuntimeError):
    pass


class D1StubRefused(D1Error, uat_stub.StubRefused):
    pass


def stub_problem() -> str | None:
    """Why `JURA_GROWTH_D1_BASE_URL` may not be used, or None (also None when unset)."""
    return uat_stub.url_problem(BASE_ENV)


def configured() -> bool:
    """Whether D1 can be asked: its three secrets are set, or a UAT stub URL is (a refused
    one counts, so the query fails loudly with the refusal instead of passing for unconfigured)."""
    if any(os.environ.get(variable) for variable in uat_stub.PAIR):
        return True
    return all(config.secret(n) for n in SECRETS)


def query(sql: str, params: list | None = None, *, client: httpx.Client | None = None) -> list[dict]:
    stub = uat_stub.base(BASE_ENV, D1StubRefused)
    if stub:
        (token, account, database), base = _STUB_CREDENTIALS, stub
    else:
        base = API
        token, account, database = (config.require(name) for name in SECRETS)
    url = f"{base}/accounts/{account}/d1/database/{database}/query"
    owns_client = client is None
    # No proxy from the environment for the stub: its traffic stays on this Mac.
    client = client or httpx.Client(timeout=30, trust_env=not stub)
    try:
        response = client.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json={"sql": sql, "params": params or []},
        )
    except httpx.HTTPError as error:
        raise D1Error(f"Cloudflare API unreachable: {type(error).__name__}") from None
    finally:
        if owns_client:
            client.close()
    try:
        body = response.json()
    except ValueError:
        raise D1Error(f"Cloudflare API answered {response.status_code} with no JSON") from None
    if response.status_code >= 300 or not body.get("success"):
        messages = "; ".join(e.get("message", "") for e in body.get("errors", [])) or response.status_code
        raise D1Error(f"D1 query failed: {messages}")
    results = body.get("result") or []
    return results[0].get("results", []) if results else []
