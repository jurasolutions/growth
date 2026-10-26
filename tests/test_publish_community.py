"""Community posts and group joins in the publish queue, with no browser (BP-02b).

Test strategy v3 §4.2 and §4.3, the BP-02b rows: X7 (the `community_groups` columns), AC-P3.4 (the
`group-join` deadlines), AC-P1.3 (community fields and answers), AC-P5.1 lines 2 to 5 and 8 to 10,
and AC-P5.3's `community.browser` switch, at the claim (`claim.next_item`, seam S7) and at the
kinds' `content()` and `deadlines()`. The gate matrix runs through `gate_adapter_community_post.py`,
`gate_adapter_group_join.py` and `gate_adapter_group_join_answers.py`. The clock is BP's default,
Tue 2026-11-10 (ISO week 46, Mon 2026-11-09 to Sun 2026-11-15).
"""

from __future__ import annotations

import shutil

import pytest

import publish_world as pw
from jura_growth import db
from jura_growth.agents import community


@pytest.fixture
def world(monkeypatch):
    pw.social_config(monkeypatch)
    pw.community_config(monkeypatch)
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
    pw.at(monkeypatch, pw.TEN)


# --- X7 the community_groups migration adds only ---------------------------------------------------


def _columns(conn, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def test_the_community_groups_migration_changes_no_existing_row(tmp_path, monkeypatch):
    current = community.MIGRATIONS
    older = tmp_path / "community-migrations"
    older.mkdir()
    for name in ("0001_community.sql", "0002_confirmed_days.sql"):
        shutil.copy(current / name, older / name)
    monkeypatch.setattr(community, "MIGRATIONS", older)
    path = tmp_path / "before.db"
    old = db.connect(path)
    for number, flag in ((1, 1), (2, 0)):  # a legacy joined group and one never joined
        old.execute(
            "INSERT INTO community_groups (id, name, slug, url, url_key, promo_rules, fit, fit_reason, joined, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'no links', 'good fit', 'owners', ?, '2026-11-02', '2026-11-02')",
            (number, f"G{number}", f"g{number}", f"https://www.facebook.com/groups/g{number}", f"facebook.com/groups/g{number}", flag),
        )
    old.commit()
    columns = _columns(old, "community_groups")
    before = sorted(tuple(r) for r in old.execute("SELECT * FROM community_groups"))
    old.close()
    monkeypatch.setattr(community, "MIGRATIONS", current)
    new = db.connect(path)
    try:
        after = sorted(tuple(r) for r in new.execute(f"SELECT {', '.join(columns)} FROM community_groups"))
        assert after == before
        read = {r["id"]: (r["joined_as"], r["pages_allowed"], r["join_status"])
                for r in db.rows(new, "SELECT * FROM community_groups")}
        assert read == {1: ("profile", "unknown", None), 2: ("none", "unknown", None)}
    finally:
        new.close()


def test_community_set_records_how_a_group_was_joined(conn, world):
    """BP §4.3: Ting Yu can join as the Page by hand and run `community set <id> joined_as=page`."""
    legacy = pw.group(conn, joined_as=None)
    conn.commit()
    assert db.one(conn, "SELECT joined_as FROM community_groups WHERE id = ?", (legacy,))["joined_as"] == "profile"
    for value, joined in (("page", 1), ("none", 0), ("profile", 1)):
        result = pw.invoke("community", "set", str(legacy), f"joined_as={value}")
        assert result.exit_code == 0, result.output
        row = db.one(conn, "SELECT joined_as, joined FROM community_groups WHERE id = ?", (legacy,))
        assert (row["joined_as"], row["joined"]) == (value, joined)
    assert pw.invoke("community", "set", str(legacy), "joined=no").exit_code == 0
    assert db.one(conn, "SELECT joined_as FROM community_groups WHERE id = ?", (legacy,))["joined_as"] == "none"
    refused = pw.invoke("community", "set", str(legacy), "joined_as=friend")
    assert refused.exit_code != 0 and "joined_as must be none, profile or page" in refused.output
