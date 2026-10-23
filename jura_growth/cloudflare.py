"""Read access to the website's D1 database through the Cloudflare API.

The site keeps two things the growth engine needs: the suppression list
(unsubscribes and Resend bounce and complaint webhooks) and anonymous toolbox
usage counts. Both live in D1 because the site writes them. The token needs
only D1 read and edit on that one database.
"""

from __future__ import annotations

import httpx

from jura_growth import config

API = "https://api.cloudflare.com/client/v4"


class D1Error(RuntimeError):
    pass


def configured() -> bool:
    return all(config.secret(n) for n in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "D1_DATABASE_ID"))


def query(sql: str, params: list | None = None, *, client: httpx.Client | None = None) -> list[dict]:
    token = config.require("CLOUDFLARE_API_TOKEN")
    account = config.require("CLOUDFLARE_ACCOUNT_ID")
    database = config.require("D1_DATABASE_ID")
    url = f"{API}/accounts/{account}/d1/database/{database}/query"
    owns_client = client is None
    client = client or httpx.Client(timeout=30)
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
