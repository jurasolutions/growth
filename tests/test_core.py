import json
import os
import plistlib
import stat
from datetime import date
from pathlib import Path

import httpx
import pytest
from click.testing import CliRunner

from jura_growth import (
    backup,
    config,
    db,
    digest,
    discord,
    gate,
    holidays,
    log,
    pause,
    paths,
    runner,
    schedule,
    suppression,
    timeutil,
)
from jura_growth.cli import cli


def invoke(*args, input=None):
    return CliRunner().invoke(cli, list(args), input=input, catch_exceptions=False)


# --- database and log ------------------------------------------------------


def test_migrations_are_recorded_once(conn):
    ids = [r["id"] for r in db.rows(conn, "SELECT id FROM schema_migrations")]
    assert "core/0001_core.sql" in ids
    assert db.migrate(conn) == []


def test_events_are_append_only(conn):
    log.event(conn, "test.kind", {"a": 1})
    with pytest.raises(Exception):
        conn.execute("DELETE FROM events")
    with pytest.raises(Exception):
        conn.execute("UPDATE events SET kind = 'x'")


def test_log_test_writes_both_stores(isolated):
    result = invoke("log", "test")
    assert result.exit_code == 0
    mirror = paths.data_dir() / "runs" / f"{timeutil.today_str()}.jsonl"
    lines = [json.loads(l) for l in mirror.read_text().splitlines()]
    assert any(l["kind"] == "log.test" for l in lines)
    with db.session() as c:
        assert db.scalar(c, "SELECT count(*) FROM events WHERE kind = 'log.test'") == 1


def test_secrets_are_redacted_in_events(conn):
    log.event(conn, "x", {"api_key": "re_abcdefghijklmnopqrstu", "note": "see https://discord.com/api/webhooks/1/abc"})
    payload = db.scalar(conn, "SELECT payload_json FROM events WHERE kind = 'x'")
    assert "re_abc" not in payload and "webhooks/1" not in payload


def test_writes_to_inputs_are_refused():
    with pytest.raises(PermissionError):
        paths.writable(paths.JURA_ROOT / "inputs" / "icp.md")
    with pytest.raises(PermissionError):
        paths.writable(paths.JURA_ROOT / "design-system" / "x.css")


# --- secrets ---------------------------------------------------------------


def test_env_file_and_keychain(tmp_path, monkeypatch):
    env = tmp_path / "test.env"
    env.write_text("A_SECRET='value-one'\nB_SECRET=keychain:jura-growth-test-missing\n")
    env.chmod(0o600)
    monkeypatch.setenv("JURA_GROWTH_ENV_FILE", str(env))
    config.reset_caches()
    assert config.secret("A_SECRET") == "value-one"
    assert config.secret("B_SECRET") is None  # no such keychain item
    with pytest.raises(config.MissingSecret):
        config.require("NOT_SET_ANYWHERE")


# --- discord ---------------------------------------------------------------


def test_missing_webhook_goes_to_outbox(conn):
    result = discord.post(conn, "alerts", "hello")
    assert not result.delivered
    outbox = paths.data_dir() / "discord-outbox" / f"{timeutil.today_str()}.jsonl"
    assert json.loads(outbox.read_text().splitlines()[-1])["content"] == "hello"


def test_unknown_channel_is_refused(conn):
    with pytest.raises(ValueError):
        discord.post(conn, "general", "hi")


def test_webhook_post_and_dedupe(conn, monkeypatch):
    monkeypatch.delenv("JURA_GROWTH_DISCORD")
    monkeypatch.setenv("DISCORD_WEBHOOK_ALERTS", "https://discord.com/api/webhooks/1/secret")
    sent = []

    def handler(request):
        sent.append(request)
        return httpx.Response(204)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert discord.post(conn, "alerts", "same text", client=client).delivered
    again = discord.post(conn, "alerts", "same text", client=client)
    assert not again.delivered and again.reason == "already posted today"
    assert len(sent) == 1
    body = json.loads(sent[0].content)
    assert body["allowed_mentions"] == {"parse": []}


def test_webhook_error_hides_url(conn, monkeypatch):
    monkeypatch.delenv("JURA_GROWTH_DISCORD")
    monkeypatch.setenv("DISCORD_WEBHOOK_ALERTS", "https://discord.com/api/webhooks/1/secret")
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401)))
    result = discord.post(conn, "alerts", "x", client=client)
    assert not result.delivered and "secret" not in result.reason


def test_long_messages_split_at_lines():
    text = "\n".join(f"line {i} " + "x" * 50 for i in range(100))
    pieces = discord.split(text)
    assert len(pieces) > 1 and all(len(p) <= 2000 for p in pieces)
    assert "".join(p + "\n" for p in pieces).count("line ") == 100


def test_discord_test_reports_missing_webhooks():
    result = invoke("discord", "test")
    assert result.exit_code == 1
    assert "#alerts" in result.output and "NOT POSTED" in result.output


# --- pause -----------------------------------------------------------------


def test_pause_resume_and_all(conn):
    assert pause.is_paused(conn, "scout") is None
    pause.pause(conn, "all", "testing")
    assert pause.is_paused(conn, "scout")
    assert pause.is_paused(conn, "digest") is None  # system jobs keep running
    pause.resume(conn, "all")
    assert pause.is_paused(conn, "scout") is None


def test_pause_file_pauses_everything_without_db(isolated):
    paths.pause_file().write_text("holiday")
    assert "holiday" in pause.is_paused(None, "scout")
    assert runner.run("heartbeat").status == "skipped"


def test_auto_pause_after_three_failures(conn):
    for _ in range(3):
        run_id = log.start_run(conn, "social", "social")
        log.finish_run(conn, run_id, "failed", error="boom")
    assert pause.check_auto_pause(conn, "social")
    assert "3 failed runs" in pause.is_paused(conn, "social")


def test_cli_pause_rejects_unknown_agent():
    result = CliRunner().invoke(cli, ["pause", "nobody"])
    assert result.exit_code != 0


# --- runner ----------------------------------------------------------------


def test_command_job_records_a_run(isolated):
    outcome = runner.run("heartbeat")
    assert outcome.status == "ok"
    with db.session() as c:
        row = db.one(c, "SELECT * FROM runs WHERE job = 'heartbeat'")
    assert row["status"] == "ok" and "heartbeat" in row["summary"]


def test_business_day_jobs_skip_holidays(isolated, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", "2026-12-25T09:00:00+08:00")
    assert runner.run("scout-sync").status == "skipped"
    with db.session() as c:
        assert "Christmas" in db.scalar(c, "SELECT summary FROM runs WHERE job = 'scout-sync'")


def test_paused_agent_is_skipped(isolated):
    with db.session() as c:
        pause.pause(c, "heartbeat", "testing", notify=False)
    assert runner.run("heartbeat").status == "skipped"


def _fake_claude(tmp_path, result_text, *, is_error=False):
    script = tmp_path / "fake-claude"
    record = {"type": "result", "subtype": "success", "is_error": is_error, "result": result_text, "total_cost_usd": 0.12}
    script.write_text(
        "#!/bin/sh\n"
        f"cat > {tmp_path}/stdin.txt\n"
        f"echo '{{\"type\": \"system\", \"argv\": \"'\"$*\"'\"}}'\n"
        f"echo '{json.dumps(record)}'\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def _settings_with(monkeypatch, **claude):
    base = config.settings()
    patched = dict(base)
    patched["claude"] = {**base["claude"], **claude}
    patched["jobs"] = {
        **base["jobs"],
        "fake": {"agent": "fake-agent", "kind": "claude", "prompt": "fake.md", "tools": ["WebSearch"], "schedule": {"daily": "06:00"}},
    }
    monkeypatch.setattr(config, "settings", lambda: patched)


def test_claude_job_runs_headless_with_allowlist(isolated, monkeypatch, tmp_path):
    fake = _fake_claude(tmp_path, "OK: wrote one thing")
    _settings_with(monkeypatch, binary=str(fake))
    prompt = paths.prompts_dir() / "fake.md"
    prompt.write_text("Do the fake job.")
    try:
        outcome = runner.run("fake")
    finally:
        prompt.unlink()
    assert outcome.status == "ok" and outcome.cost_usd == 0.12
    stdin = (tmp_path / "stdin.txt").read_text()
    assert "Do the fake job." in stdin and "Run context" in stdin


def test_claude_command_is_locked_down(monkeypatch):
    _settings_with(monkeypatch)
    prompt = paths.prompts_dir() / "fake.md"
    prompt.write_text("x")
    try:
        argv, _ = runner.claude_command("fake", config.settings()["jobs"]["fake"])
    finally:
        prompt.unlink()
    joined = " ".join(argv)
    for flag in ("--permission-mode dontAsk", "--strict-mcp-config", "--setting-sources project", "--max-budget-usd"):
        assert flag in joined
    assert "Bash(jura-growth:*)" in argv
    assert "Bash(jura-growth resume:*)" in argv  # disallowed
    assert not any(a == "Bash" or a.startswith("Bash(*") for a in argv)


def test_claude_fail_summary_marks_run_failed(isolated, monkeypatch, tmp_path):
    fake = _fake_claude(tmp_path, "FAIL: no ICP file")
    _settings_with(monkeypatch, binary=str(fake))
    prompt = paths.prompts_dir() / "fake.md"
    prompt.write_text("x")
    try:
        outcome = runner.run("fake")
    finally:
        prompt.unlink()
    assert outcome.status == "failed"


# --- schedule --------------------------------------------------------------


def test_slots_for_each_shape():
    assert schedule.sgt_slots({"daily": "17:30"}) == [(None, 17, 30)]
    assert len(schedule.sgt_slots({"business_days": "09:00"})) == 5
    every = schedule.sgt_slots({"business_days_every": {"start": "09:30", "end": "16:30", "minutes": 10}})
    assert len(every) == 43 * 5
    assert schedule.sgt_slots({"weekly": {"day": "mon", "time": "07:30"}}) == [(1, 7, 30)]


def test_plist_is_valid(isolated):
    paths_out = schedule.render(["digest", "community"])
    data = plistlib.loads(paths_out[1].read_bytes())
    assert data["Label"] == "sg.jurasolutions.growth.community"
    assert data["ProgramArguments"][-2:] == ["run", "community"]
    if schedule.local_offset().total_seconds() == 8 * 3600:
        assert data["StartCalendarInterval"] == [{"Hour": 7, "Minute": 30, "Weekday": 1}]


def test_timezone_conversion(monkeypatch):
    from datetime import timedelta

    monkeypatch.setattr(schedule, "local_offset", lambda: timedelta(hours=0))
    # Monday 07:30 SGT is Sunday 23:30 UTC.
    assert schedule.to_local((1, 7, 30)) == {"Hour": 23, "Minute": 30, "Weekday": 0}


# --- digest, backup --------------------------------------------------------


def test_digest_writes_summary_and_brief_line(isolated):
    runner.run("heartbeat")
    result = invoke("digest")
    assert result.exit_code == 0
    summary = json.loads((paths.data_dir() / "daily-summary.json").read_text())
    assert summary["brief_line"].startswith("Jura growth, ")
    assert summary["runs"]["heartbeat"]["ok"] == 1
    assert (paths.outputs_dir() / "digests" / f"{timeutil.today_str()}.md").exists()


def test_backup_keeps_fourteen_days(isolated, conn):
    folder = paths.data_dir() / "backups"
    folder.mkdir(parents=True)
    for day in range(1, 21):
        (folder / f"growth-2026-10-{day:02d}.db").write_text("old")
    os.environ["JURA_GROWTH_NOW"] = "2026-10-24T23:30:00+08:00"
    try:
        target = backup.backup(conn)
    finally:
        del os.environ["JURA_GROWTH_NOW"]
    names = sorted(f.name for f in folder.glob("growth-*.db"))
    assert target.name == "growth-2026-10-24.db"
    assert names[0] == "growth-2026-10-11.db" and len(names) == 11  # 11th to 20th plus 24th


# --- suppression and the gate ----------------------------------------------


def test_suppression_by_email_hash_and_domain(conn):
    suppression.add(conn, email_hash_value=suppression.email_hash("Info@Acme.sg"), reason="unsubscribe", source="test")
    assert suppression.is_suppressed(conn, "info@acme.sg") == "unsubscribe"
    suppression.add(conn, domain="blocked.sg", reason="manual", source="test")
    assert suppression.is_suppressed(conn, "sales@blocked.sg") == "manual (domain)"
    assert suppression.is_suppressed(conn, "hello@other.sg") is None
    # learning the address later fills it in
    suppression.add(conn, email="info@acme.sg", reason="unsubscribe", source="test")
    assert db.scalar(conn, "SELECT email FROM suppression WHERE email_hash = ?", (suppression.email_hash("info@acme.sg"),)) == "info@acme.sg"


def test_gate_allows_one_regeneration_then_drops(conn):
    first = gate.gate(conn, "email:1", "Act now!", agent="scout")
    assert first.status == "retry"
    second = gate.gate(conn, "email:1", "Still urgent!", agent="scout")
    assert second.status == "dropped"
    third = gate.gate(conn, "email:1", "A calm note.", agent="scout")
    assert third.status == "dropped"


def test_gate_pass_clears_attempts(conn):
    assert gate.gate(conn, "post:1", "Act now!", agent="social").status == "retry"
    assert gate.gate(conn, "post:1", "A calm note.", agent="social").passed


# --- holidays --------------------------------------------------------------


def test_business_days():
    assert not holidays.is_business_day(date(2026, 11, 9))  # Deepavali observed
    assert not holidays.is_business_day(date(2026, 10, 24))  # Saturday
    assert holidays.is_business_day(date(2026, 10, 26))
    assert holidays.next_business_day(date(2026, 12, 24)) == date(2026, 12, 28)
    assert holidays.coverage_warning(date(2027, 12, 1)) is not None
    assert holidays.coverage_warning(date(2026, 12, 1)) is None


# --- CLI check -------------------------------------------------------------


def test_check_command_exit_codes():
    assert invoke("check", "A calm, plain sentence.").exit_code == 0
    failed = invoke("check", "Amazing!")
    assert failed.exit_code == 1 and "exclamation" in failed.output
    assert invoke("check", "-", input="Plain text from stdin.").exit_code == 0


# --- fixes from the agents' reports ----------------------------------------


def test_urls_keep_balanced_parentheses():
    from jura_growth.brand_check import find_links

    url = "https://www.iras.gov.sg/taxes/goods-services-tax-(gst)/basics-of-gst"
    assert url in find_links(f"See {url} for the rate.")
    assert url in find_links(f"See [the IRAS page]({url}).")


def test_documents_are_interface_quantities():
    from jura_growth.brand_check import check

    assert "numbers" not in {i.rule for i in check("Merge up to 20 PDFs into one file.").issues}


def test_fail_line_anywhere_fails_the_run():
    assert runner._judge("Did some work.\nFAIL: no ICP file", 0.1, "x", None).status == "failed"
    assert runner._judge("**FAIL:** could not reach IRAS", 0.1, "x", None).status == "failed"
    assert runner._judge("OK: wrote APP-004", 0.1, "x", None).status == "ok"
    assert runner._judge("SKIP: nothing to do", 0.1, "x", None).status == "ok"


def test_stale_sweep_ignores_frozen_clock_and_held_locks(isolated, conn, monkeypatch):
    run_id = log.start_run(conn, "social", "social")  # started now, real clock
    monkeypatch.setenv("JURA_GROWTH_NOW", "2030-01-01T00:00:00+08:00")
    runner._abandon_stale(conn)
    assert db.scalar(conn, "SELECT status FROM runs WHERE id = ?", (run_id,)) == "running"
    conn.execute("UPDATE runs SET started_at = '2026-01-01T00:00:00+08:00' WHERE id = ?", (run_id,))
    with runner._lock("social") as held:
        assert held
        runner._abandon_stale(conn)
        assert db.scalar(conn, "SELECT status FROM runs WHERE id = ?", (run_id,)) == "running"
    runner._abandon_stale(conn)
    assert db.scalar(conn, "SELECT status FROM runs WHERE id = ?", (run_id,)) == "failed"


def test_markdown_copy_reads_wrapped_bullets_and_inline_labels():
    from jura_growth.copy_check import items_from_markdown

    source = (
        "### 5.2 Copy\n"
        "- Subtitle: \"Make a clean quote with your logo and send it as\n"
        "  a PDF in a few minutes.\"\n"
        "- Talk-to-us card: heading \"Quotes, jobs and invoices, entered once\"; body \"We can connect\n"
        "  your quoting to your jobs.\"; button \"Tell us how you quote today\"\n"
        "\n### 5.3 Technical\n"
    )
    items = {(i.text, i.kind) for i in items_from_markdown(source)}
    assert ("Make a clean quote with your logo and send it as a PDF in a few minutes.", "body") in items
    assert ("Quotes, jobs and invoices, entered once", "heading") in items
    assert ("We can connect your quoting to your jobs.", "body") in items
    assert ("Tell us how you quote today", "heading") in items
