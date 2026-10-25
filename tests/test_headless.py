"""What a headless run may touch: secret files, the per-job command allowlist,
the folders a run may read, and secret values in CLI output.

Fake secret values only. Nothing here reads a real `.env`.
"""

import re

import pytest
from click.testing import CliRunner

from jura_growth import config, headless, paths, runner
from jura_growth.agents.community import groups as groups_mod
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


@pytest.mark.parametrize(
    "name",
    [".env", ".env.local", "prod.env", ".dev.vars", "link-to-env.txt", ".ENV", ".Env.Local", "PROD.ENV", ".DEV.VARS"],
)
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


def test_the_configured_env_file_is_refused_under_another_spelling_or_a_hard_link(tmp_path, monkeypatch):
    """macOS folders are case-insensitive: GROWTH-SECRETS.TXT opens growth-secrets.txt."""
    secrets = tmp_path / "growth-secrets.txt"
    secrets.write_text(FAKE_ENV)
    hard_link = tmp_path / "notes.txt"
    hard_link.hardlink_to(secrets)
    monkeypatch.setenv("JURA_GROWTH_ENV_FILE", str(secrets))
    config.reset_caches()
    for other in (tmp_path / "GROWTH-SECRETS.TXT", hard_link):
        result = invoke("check", "--file", str(other))
        assert result.exit_code == 2 and "refused" in result.output, other
        assert "FAKE-TOKEN-abc" not in result.output


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


# --- secret values in CLI output ------------------------------------------------


@pytest.fixture
def configured(tmp_path, monkeypatch):
    """A fake env file with two secrets, one of them in the (fake) Keychain."""
    env = tmp_path / "configured-secrets"
    env.write_text(
        "CLOUDFLARE_API_TOKEN=FAKEcfTOKENabcdef1234567890\n"
        "UNSUBSCRIBE_SECRET=keychain:jura-growth-fake\n"
        "OUTREACH_IMAP_HOST=imap.example.sg\n"
    )
    env.chmod(0o600)
    monkeypatch.setenv("JURA_GROWTH_ENV_FILE", str(env))
    monkeypatch.setattr(config, "_keychain", lambda service: "kcFAKEunsubscribe42" if service == "jura-growth-fake" else None)
    config.reset_caches()


def test_configured_secret_values_never_reach_cli_output(configured):
    text = "Our token is FAKEcfTOKENabcdef1234567890 and the secret is kcFAKEunsubscribe42."
    for args in (("check", text), ("check", "--json", text)):
        result = invoke(*args)
        assert result.exit_code == 1  # the numbers rule quotes the sentence back
        assert "FAKEcfTOKENabcdef1234567890" not in result.output
        assert "kcFAKEunsubscribe42" not in result.output
        assert "[redacted]" in result.output


def test_error_messages_are_redacted_too(configured):
    result = invoke("social", "today", "--date", "FAKEcfTOKENabcdef1234567890")
    assert result.exit_code == 2 and "is not a date" in result.output
    assert "FAKEcfTOKENabcdef1234567890" not in result.output


def test_only_secret_values_are_masked(configured):
    assert config.redact("imap.example.sg FAKEcfTOKENabcdef1234567890") == "imap.example.sg [redacted]"


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


# --- the per-job command allowlist ----------------------------------------------

GROUP = {
    "channel": "facebook",
    "name": "Some SG group",
    "url": "https://www.facebook.com/groups/somesg",
    "audience": "Singapore SME owners",
    "size_hint": "not stated",
    "active_hint": "not stated",
    "promo_rules": "not stated in public sources",
    "fit": "good fit",
    "fit_reason": "Owners asking each other about admin and paperwork.",
    "source_urls": ["https://example.sg/best-groups#somesg"],
}


def in_run(monkeypatch, job, agent):
    monkeypatch.setenv("JURA_GROWTH_JOB", job)
    monkeypatch.setenv("JURA_GROWTH_AGENT", agent)


def test_a_community_run_cannot_mark_a_group_joined(conn, monkeypatch):
    """Regression for audit F4: joining a group is Ting Yu's step."""
    _, group_id, _ = groups_mod.add(conn, GROUP)
    conn.commit()
    in_run(monkeypatch, "community", "community")
    result = invoke("community", "set", str(group_id), "joined=yes", "rules_confirmed=yes")
    assert result.exit_code == 2, result.output
    assert "refused: a `community` run may not use `jura-growth community set`" in result.output
    assert not groups_mod.get(conn, group_id)["joined"]


@pytest.mark.parametrize(
    "args",
    [
        ("outreach", "send-due"),
        ("outreach", "requeue-shadow"),
        ("outreach", "unsubscribe-link", "someone@example.sg"),
        ("outreach", "sync"),
    ],
    ids=lambda a: a[1],
)
def test_scout_research_cannot_reach_send_time_controls(monkeypatch, args):
    in_run(monkeypatch, "scout-research", "scout")
    result = invoke(*args)
    assert result.exit_code == 2, result.output
    assert f"may not use `jura-growth outreach {args[1]}`" in result.output


def test_a_run_may_use_the_commands_its_prompt_uses(monkeypatch):
    in_run(monkeypatch, "scout-research", "scout")
    result = invoke("outreach", "status")
    assert result.exit_code == 0, result.output
    assert "refused" not in result.output


def test_terminal_use_of_human_commands_is_unchanged(conn):
    _, group_id, _ = groups_mod.add(conn, GROUP)
    conn.commit()
    result = invoke("community", "set", str(group_id), "joined=yes")
    assert result.exit_code == 0, result.output
    assert groups_mod.get(conn, group_id)["joined"]


def test_an_unknown_job_may_run_nothing(monkeypatch):
    in_run(monkeypatch, "not-a-job", "nobody")
    assert invoke("status").exit_code == 2


# --- the claude job's own permission rules --------------------------------------

CLAUDE_JOBS = sorted(name for name, spec in config.settings()["jobs"].items() if spec["kind"] == "claude")
PROMPT_COMMAND = re.compile(r"jura-growth ([a-z][a-z-]*)(?: ([a-z][a-z-]*))?")


def rules(job):
    argv, _ = runner.claude_command(job, config.settings()["jobs"][job])
    start, middle = argv.index("--allowedTools"), argv.index("--disallowedTools")
    end = next((i for i in range(middle + 1, len(argv)) if argv[i].startswith("--")), len(argv))
    return argv[start + 1:middle], argv[middle + 1:end]


@pytest.mark.parametrize("job", CLAUDE_JOBS)
def test_claude_command_carries_the_jobs_allowlist(job):
    allowed, denied = rules(job)
    commands = headless.permissions(job).commands
    assert commands, f"{job} declares no commands"
    for command in commands:
        assert f"Bash(jura-growth {command}:*)" in allowed
        assert f"Bash(jura-growth {command}:*)" not in denied
    assert "Bash(jura-growth:*)" not in allowed
    assert all(r.startswith("Bash(jura-growth ") for r in allowed if r.startswith("Bash"))
    for never in ("run", "resume", "schedule install", "discord post"):
        assert f"Bash(jura-growth {never}:*)" in denied


@pytest.mark.parametrize("job", CLAUDE_JOBS)
def test_claude_command_denies_every_secret_file_under_jura_root(job):
    _, denied = rules(job)
    root = paths.JURA_ROOT
    for rule in (f"Read(/{root}/**/.env*)", f"Read(/{root}/**/*.env)", f"Read(/{root}/**/.dev.vars*)", f"Read(/{paths.env_file()})"):
        assert rule in denied


def test_claude_rules_refuse_human_and_other_jobs_commands():
    _, scout = rules("scout-research")
    for command in ("outreach send-due", "outreach requeue-shadow", "outreach unsubscribe-link", "outreach sync"):
        assert f"Bash(jura-growth {command}:*)" in scout
    _, community = rules("community")
    for command in ("community set", "community posted", "community removed", "social skip", "social published", "social submit"):
        assert f"Bash(jura-growth {command}:*)" in community


@pytest.mark.parametrize("job", CLAUDE_JOBS)
def test_every_command_a_prompt_uses_is_declared(job):
    """prompts/<job>.md is the source of the job's allowlist."""
    prompt = (paths.prompts_dir() / config.settings()["jobs"][job]["prompt"]).read_text()
    leaves = {name for name, _ in headless.leaves(cli)}
    used = set()
    for match in PROMPT_COMMAND.finditer(prompt):
        name = headless.command_name([w for w in match.groups() if w])
        if name in leaves:
            used.add(name)
    declared = set(headless.permissions(job).commands)
    assert used <= declared, f"{job}: the prompt uses {sorted(used - declared)}"
    assert declared <= leaves, f"{job}: declares unknown commands {sorted(declared - leaves)}"


def outbox_files(tmp_path):
    folder = tmp_path / "data" / "discord-outbox"
    return sorted(folder.iterdir()) if folder.exists() else []
