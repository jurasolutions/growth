"""The factory's outside inputs: toolbox usage from the site's D1 database and
what the scout has learned about leads.

Neither is required. Usage reads "not configured" until the Cloudflare
secrets are set, and scout insights fall back from the scout's own command to
its `leads` table, then to nothing.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import timedelta

from jura_growth import cloudflare, db, timeutil


def usage(days: int = 7) -> dict:
    """Opens and completions per app over the last `days` SGT days."""
    if not cloudflare.configured():
        return {"status": "not configured", "days": days, "rows": []}
    since = (timeutil.today() - timedelta(days=days - 1)).isoformat()
    try:
        rows = cloudflare.query(
            "SELECT app_slug, SUM(opens) AS opens, SUM(completions) AS completions FROM app_usage "
            "WHERE day >= ? GROUP BY app_slug ORDER BY opens DESC",
            [since],
        )
    except cloudflare.D1Error as error:
        return {"status": f"unavailable: {error}", "days": days, "rows": []}
    return {"status": "ok", "days": days, "since": since, "rows": rows}


def scout_insights(conn: sqlite3.Connection, days: int = 30) -> dict:
    """Industries and observations from the last `days` days of scout leads."""
    from_command = _from_scout_command(days)
    if from_command is not None:
        return {"source": "jura-growth scout insights", "days": days, **from_command}
    from_table = _from_leads_table(conn, days)
    if from_table is not None:
        return {"source": "leads table", "days": days, **from_table}
    return {"source": "none (the scout has no leads yet)", "days": days, "industries": {}, "observations": []}


def _from_scout_command(days: int) -> dict | None:
    from click.testing import CliRunner

    from jura_growth.cli import cli

    scout = cli.commands.get("scout")
    if scout is None or "insights" not in getattr(scout, "commands", {}):
        return None
    try:
        result = CliRunner().invoke(cli, ["scout", "insights", "--days", str(days), "--json"])
    except Exception:  # noqa: BLE001 - the scout's problems never stop the factory
        return None
    if result.exit_code != 0:
        return None
    try:
        data = json.loads(result.output)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    return {"industries": data.get("industries") or {}, "observations": data.get("observations") or []}


def _from_leads_table(conn: sqlite3.Connection, days: int) -> dict | None:
    exists = db.scalar(conn, "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'leads'")
    if not exists:
        return None
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(leads)")}
    if not {"industry", "created_at"} <= columns:
        return None
    since = timeutil.stamp(timeutil.days_ago(days))
    select = "industry" + (", observations_json" if "observations_json" in columns else "")
    rows = db.rows(conn, f"SELECT {select} FROM leads WHERE created_at >= ? ORDER BY created_at DESC", (since,))
    industries: dict[str, int] = {}
    observations: list[dict] = []
    for row in rows:
        industry = (row.get("industry") or "unknown").strip()
        industries[industry] = industries.get(industry, 0) + 1
        try:
            found = json.loads(row.get("observations_json") or "[]")
        except ValueError:
            found = []
        for note in found if isinstance(found, list) else []:
            if len(observations) < 60:
                observations.append({"industry": industry, "observation": note if isinstance(note, str) else json.dumps(note)})
    return {"industries": dict(sorted(industries.items(), key=lambda kv: -kv[1])), "observations": observations}
