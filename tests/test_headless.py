"""What a headless run may touch: secret files, the per-job command allowlist,
the folders a run may read, and secret values in CLI output.

Fake secret values only. Nothing here reads a real `.env`.
"""

import pytest
from click.testing import CliRunner

from jura_growth import config, paths
from jura_growth.cli import cli


def invoke(*args, input=None):
    return CliRunner().invoke(cli, list(args), input=input)


FAKE_ENV = (
    "DISCORD_WEBHOOK_ALERTS=https://discord.com/api/webhooks/111/FAKE-TOKEN-abc\n"
    "RESEND_API_KEY_OUTREACH=re_FAKEKEY123\n"
)


# --- secret files ------------------------------------------------------------


def test_check_file_refuses_an_env_file_and_echoes_no_secret(tmp_path):
    """Regression for audit F9: `check --file` used to quote a .env back."""
    fake = tmp_path / "fake.env"
    fake.write_text(FAKE_ENV)
    result = invoke("check", "--file", str(fake), "--json")
    assert result.exit_code != 0
    assert "refused" in result.output
    assert "FAKE-TOKEN-abc" not in result.output
    assert "re_FAKEKEY123" not in result.output


@pytest.mark.parametrize("name", [".env", ".env.local", "prod.env", ".dev.vars", "link-to-env.txt"])
def test_secret_files_are_refused_by_name_or_link(tmp_path, name):
    real = tmp_path / "real" / ".env"
    real.parent.mkdir()
    real.write_text(FAKE_ENV)
    target = tmp_path / name
    if name == "link-to-env.txt":
        target.symlink_to(real)
    else:
        target.write_text(FAKE_ENV)
    result = invoke("check", "--file", str(target))
    assert result.exit_code == 2 and "refused" in result.output
    assert "FAKE-TOKEN-abc" not in result.output


def test_the_configured_env_file_is_refused_whatever_its_name(tmp_path, monkeypatch):
    secrets = tmp_path / "growth-secrets.txt"
    secrets.write_text(FAKE_ENV)
    monkeypatch.setenv("JURA_GROWTH_ENV_FILE", str(secrets))
    config.reset_caches()
    result = invoke("check", "--file", str(secrets))
    assert result.exit_code == 2 and "refused" in result.output


FILE_COMMANDS = [
    ("check", "--file", "{f}"),
    ("check-copy", "{f}"),
    ("discord", "post", "alerts", "note", "--file", "{f}"),
    ("community", "add-group", "--file", "{f}"),
    ("community", "plan-add", "--file", "{f}"),
    ("scout", "add-lead", "--file", "{f}"),
    ("outreach", "queue", "--lead", "1", "--file", "{f}"),
    ("apps", "submit-prd", "{f}"),
    ("social", "render", "{f}", "--out", "{d}"),
    ("social", "submit", "{f}"),
]


@pytest.mark.parametrize("args", FILE_COMMANDS, ids=lambda a: " ".join(a[:2]))
def test_every_file_option_refuses_an_env_file(tmp_path, args):
    env = tmp_path / ".env"
    env.write_text(FAKE_ENV)
    out = tmp_path / "out"
    result = invoke(*[a.format(f=env, d=out) for a in args])
    assert result.exit_code == 2, result.output
    assert "refused" in result.output and "FAKE-TOKEN-abc" not in result.output
    assert outbox_files(tmp_path) == []


# --- the folders a run may use --------------------------------------------------


def test_a_run_may_only_use_its_own_folders(tmp_path, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_JOB", "social")
    draft = "A calm, plain sentence."
    elsewhere = tmp_path / "elsewhere" / "draft.md"
    other_job = paths.work_dir("community") / "draft.md"
    own = paths.work_dir("social") / "2026-10-26" / "draft.md"
    output = paths.outputs_dir() / "social" / "draft.md"
    for file in (elsewhere, other_job, own, output):
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(draft)

    for refused in (elsewhere, other_job):
        result = invoke("check", "--file", str(refused))
        assert result.exit_code == 2 and "a `social` run may only use files in" in result.output
    for allowed in (own, output):
        assert invoke("check", "--file", str(allowed)).output.strip() == "pass"


def test_terminal_use_still_reads_any_ordinary_file(tmp_path):
    draft = tmp_path / "anywhere" / "draft.md"
    draft.parent.mkdir()
    draft.write_text("A calm, plain sentence.")
    assert invoke("check", "--file", str(draft)).output.strip() == "pass"


def outbox_files(tmp_path):
    folder = tmp_path / "data" / "discord-outbox"
    return sorted(folder.iterdir()) if folder.exists() else []
