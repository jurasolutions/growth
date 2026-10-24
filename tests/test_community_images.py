"""A community plan's images: only a PNG from the run's own folders is ever
attached to #community. Regression for audit F3 (code review 03, C-S2)."""

import struct

from jura_growth import paths
from jura_growth.agents.community import plan as plan_mod
from test_community import frozen, good_plan, outbox, three  # noqa: F401 (fixtures)

PNG = (
    b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 1, 1)
    + b"\x08\x06\x00\x00\x00" + b"\x00" * 4
)


def png(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PNG)
    return path


def with_image(three, image):
    plan = good_plan(*three)
    plan["posts"][2]["image_path"] = str(image)
    return plan


def in_community_run(monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_JOB", "community")
    monkeypatch.setenv("JURA_GROWTH_AGENT", "community")


def test_an_image_outside_the_runs_folders_is_rejected_before_anything_is_uploaded(conn, three, tmp_path, monkeypatch):
    in_community_run(monkeypatch)
    image = png(tmp_path / "elsewhere" / "card.png")
    result = plan_mod.add(conn, with_image(three, image))
    assert not result.ok
    assert any("a `community` run may only use files in" in e for e in result.errors), result.errors
    assert plan_mod.stored_items(conn, "2026-W44", "post") == []
    assert outbox("community") == []


def test_a_secret_file_is_never_an_image(conn, three, tmp_path):
    secretish = tmp_path / "pretend-secret.env"
    secretish.write_text("NOT_A_REAL_SECRET=1\n")
    result = plan_mod.add(conn, with_image(three, secretish))
    assert not result.ok
    assert any("is a secrets file" in e for e in result.errors), result.errors
    assert outbox("community") == []


def test_an_image_must_be_a_png(conn, three, monkeypatch):
    in_community_run(monkeypatch)
    notes = paths.work_dir("community") / "notes.png"
    notes.parent.mkdir(parents=True, exist_ok=True)
    notes.write_text("not an image")
    result = plan_mod.add(conn, with_image(three, notes))
    assert not result.ok
    assert any("is not a PNG" in e for e in result.errors), result.errors


def test_a_png_from_the_runs_scratch_folder_is_attached(conn, three, monkeypatch):
    in_community_run(monkeypatch)
    image = png(paths.work_dir("community") / "card.png")
    result = plan_mod.add(conn, with_image(three, image))
    assert result.ok, result.lines
    plan_mod.publish(conn, "2026-W44")
    assert outbox("community")[-1]["files"] == [str(image.resolve())]


def test_publish_checks_each_image_again(conn, three, tmp_path, monkeypatch):
    """An image swapped for a link to a secret after plan-add is not uploaded."""
    in_community_run(monkeypatch)
    image = png(paths.work_dir("community") / "card.png")
    assert plan_mod.add(conn, with_image(three, image)).ok
    secret = tmp_path / ".env"
    secret.write_text("NOT_A_REAL_SECRET=1\n")
    image.unlink()
    image.symlink_to(secret)
    plan_mod.publish(conn, "2026-W44")
    assert outbox("community")[-1]["files"] == []
