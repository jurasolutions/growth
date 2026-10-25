"""Run updates (MC-03, PRD MC SC3 and §5.5): one message per run of
scout-research, social, community and app-factory, in that agent's own
Discord channel.

Runs happen in process through `runner.run()` (seam S9), with the fake
`claude` binary standing in for Claude, and every post goes to the Discord
double (S5) or, with Discord off, to the outbox. Nothing here calls
`jura-growth run` or posts for real.
"""

import json
import subprocess
import types

import pytest

from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import agents, approvals, db, pause, paths, run_update, runner
from jura_growth.agents import social as social_plugin

import approval_world
import sweep
from runner_support import fake_claude, mirrored
from sweep import d2_secrets  # noqa: F401 - a fixture
from test_scout_support import outbox

SEVEN_AM = "2026-11-10T07:00:00+08:00"  # Tue 2026-11-10, a business day (test strategy v3 §3)


def at(monkeypatch, moment):
    monkeypatch.setenv("JURA_GROWTH_NOW", moment)


def claude_binary(monkeypatch, script):
    """Point every claude job at the fake binary."""
    from jura_growth import config

    base = config.settings()
    patched = {**base, "claude": {**base["claude"], "binary": str(script)}}
    monkeypatch.setattr(config, "settings", lambda: patched)


def social_kind(monkeypatch):
    """The fake kind from ticket 04, declared as `social-post` by a test plug-in,
    so the run can raise requests of that kind."""
    world = approval_world.World()
    kind = approval_world.FakeKind(world)
    kind.name = "social-post"
    plugin = types.SimpleNamespace(NAME="social-kinds", approval_kinds=lambda: {"social-post": kind}, __name__="social_kinds")
    real = agents.plugins
    monkeypatch.setattr(agents, "plugins", lambda: (*real(), plugin))
    return world


def during_run(monkeypatch, work):
    """Run `work(run_id)` inside the claude job's body, after the fake binary."""
    real = runner._run_claude

    def body(name, spec, agent, run_id):
        outcome = real(name, spec, agent, run_id)
        work(run_id)
        return outcome

    monkeypatch.setattr(runner, "_run_claude", body)


def social_run(monkeypatch, tmp_path, *, summary, cost=0.41, minutes_later="07:04:12", raise_from=153, raises=3):
    """A social run at 07:00 that drafts three posts with an image each and
    raises `raises` social-post requests, numbered from A-<raise_from>."""
    at(monkeypatch, SEVEN_AM)
    monkeypatch.setattr(social_plugin, "precheck", lambda job, conn: None)
    claude_binary(monkeypatch, fake_claude(tmp_path, summary, cost=cost))
    world = social_kind(monkeypatch)

    def work(run_id):
        with db.session() as conn:
            for platform in ("linkedin", "facebook", "instagram"):
                conn.execute(
                    "INSERT INTO social_posts (date, theme, platform, text, image_paths, run_id, created_at)"
                    " VALUES ('2026-11-10', 'tools', ?, 'text', ?, ?, ?)",
                    (platform, json.dumps([f"{platform}.png"]), run_id, SEVEN_AM),
                )
            if raises:
                conn.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('approvals', ?)", (raise_from - 1,))
            for _ in range(raises):
                approvals.request(conn, "social-post", world.item(), reason="a draft is ready", run_id=run_id)
        monkeypatch.setenv("JURA_GROWTH_NOW", f"2026-11-10T{minutes_later}+08:00")

    during_run(monkeypatch, work)


# --- AC-M3.1: the message ----------------------------------------------------


def test_a_social_run_posts_one_run_update_in_social_drafts(monkeypatch, tmp_path, discord_double):
    social_run(monkeypatch, tmp_path, summary='OK: Drafted LinkedIn, Facebook and Instagram for "PayNow QR for small shops".')

    outcome = runner.run("social")

    assert outcome.status == "ok"
    with db.session() as conn:
        [row] = db.rows(conn, "SELECT id FROM runs WHERE job = 'social'")
    [post] = discord_double.posts("social-drafts")
    assert post.content == (
        f"**social** · ok · 07:00 SGT · 4m 12s · US$0.41 · run {row['id']}\n"
        '> Drafted LinkedIn, Facebook and Instagram for "PayNow QR for small shops".\n'
        "Produced: 3 drafts, 3 images\n"
        "Waiting for you: A-0153, A-0154, A-0155 (social posts)"
    )
    assert post.flags == 4 and post.allowed_mentions == {"parse": []}  # suppress_embeds, no pings
    assert [p.channel for p in discord_double.posts()] == ["social-drafts"]


# --- AC-M3.2 to AC-M3.4: skips -----------------------------------------------


def test_a_social_run_paused_by_hand_posts_one_skip(monkeypatch, discord_double):
    at(monkeypatch, SEVEN_AM)
    with db.session() as conn:
        pause.pause(conn, "social", "paused by hand", notify=False)

    assert runner.run("social").status == "skipped"

    with db.session() as conn:
        [row] = db.rows(conn, "SELECT id FROM runs WHERE job = 'social'")
    assert discord_double.contents("social-drafts") == [f"**social** · skipped: paused by hand · 07:00 SGT · run {row['id']}"]


def test_the_pause_file_posts_no_run_update(monkeypatch, discord_double):
    at(monkeypatch, SEVEN_AM)
    paths.pause_file().write_text("away this week")

    assert runner.run("social").status == "skipped"

    assert discord_double.requests == []
    assert outbox() == []


def no_database(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the lock skip opened growth.db")

    monkeypatch.setattr(db, "connect", refuse)


def test_a_lock_skip_posts_one_update_without_opening_the_database(monkeypatch, discord_double):
    at(monkeypatch, SEVEN_AM)
    with runner._lock("social") as held:
        assert held
        no_database(monkeypatch)
        assert runner.run("social").summary == "previous run still going"

    assert discord_double.contents("social-drafts") == ["**social** · skipped: previous run still going · 07:00 SGT"]
    assert mirrored("run.after_run_error") == []


@pytest.mark.parametrize("down", ["unreachable", "not set up"])
def test_a_lock_skip_goes_to_the_outbox_when_discord_is_down(monkeypatch, request, down):
    at(monkeypatch, SEVEN_AM)
    if down == "unreachable":
        request.getfixturevalue("discord_double").mode = "unreachable"
    with runner._lock("social"):
        no_database(monkeypatch)
        runner.run("social")

    assert [(r["channel"], r["content"]) for r in outbox()] == [
        ("social-drafts", "**social** · skipped: previous run still going · 07:00 SGT")
    ]
    assert mirrored("run.after_run_error") == []


# --- AC-M3.5: a failed run ---------------------------------------------------

MONDAY_0730 = "2026-11-16T07:30:00+08:00"


class HungClaude:
    """A `claude` process that never answers: the first wait times out."""

    def __init__(self, *args, **kwargs):
        self.returncode = None
        self.waits = 0

    def communicate(self, input=None, timeout=None):
        self.waits += 1
        if self.waits == 1:
            raise subprocess.TimeoutExpired("claude", timeout)
        return "", ""

    def kill(self):
        self.returncode = -9


def test_a_community_timeout_posts_its_error_in_one_line_and_still_alerts(monkeypatch, discord_double):
    at(monkeypatch, MONDAY_0730)
    monkeypatch.setattr(runner, "subprocess", types.SimpleNamespace(Popen=HungClaude, PIPE=subprocess.PIPE, TimeoutExpired=subprocess.TimeoutExpired))

    assert runner.run("community").status == "failed"

    with db.session() as conn:
        [row] = db.rows(conn, "SELECT id FROM runs WHERE job = 'community'")
    assert discord_double.contents("community") == [
        f"**community** · failed · 07:30 SGT · 0s · run {row['id']}\n"
        "Error: timed out after 30 minutes\n"
        "Produced: nothing"
    ]
    assert discord_double.contents("alerts") == ["**community**: `community` failed: timed out after 30 minutes"]


def test_a_community_failure_with_a_secret_in_its_error_posts_it_redacted_in_one_line(monkeypatch, tmp_path, d2_secrets, discord_double):
    # AC-M3.5 with dataset D2 in the error.
    at(monkeypatch, MONDAY_0730)
    failing = f"FAIL: {sweep.MARKER} login refused for key {sweep.RESEND_KEY} and {sweep.KEYCHAIN_VALUE}"
    claude_binary(monkeypatch, fake_claude(tmp_path, f"{failing}\nsee the\nlog"))

    assert runner.run("community").status == "failed"

    [content] = discord_double.contents("community")
    header, error, *rest = content.splitlines()
    assert header.startswith("**community** · failed · 07:30 SGT · ")
    assert error == f"Error: FAIL: {sweep.MARKER} login refused for key [redacted] and [redacted]"
    assert rest == ["> see the", "> log", "Produced: nothing"]
    assert len(discord_double.contents("alerts")) == 1
    sweep.assert_clean(discord_double, sweep.outbox_dir(), sweep.Planted(secrets=sweep.SECRETS))


# --- a run that crashes before it starts (code review 03, Q1) -----------------


def bad_social_config(monkeypatch):
    """A typo in config/social.yaml: the real precheck's settings.load() raises."""
    from jura_growth import config

    real = config.agent_config
    monkeypatch.setattr(config, "agent_config", lambda agent: {"themes": {"tools": {"layout": "sideways"}}} if agent == "social" else real(agent))


def test_a_precheck_that_raises_is_a_failed_run_that_alerts_auto_pauses_and_posts(monkeypatch, discord_double):
    at(monkeypatch, SEVEN_AM)
    bad_social_config(monkeypatch)

    outcomes = [runner.run("social") for _ in range(3)]

    assert [o.status for o in outcomes] == ["failed"] * 3
    assert outcomes[0].error.startswith("precheck failed: SettingsError: theme tools: layout must be one of")
    with db.session() as conn:
        rows = db.rows(conn, "SELECT id, status, error FROM runs ORDER BY id")
        assert pause.is_paused(conn, "social") == "3 failed runs in a row"
    assert [r["status"] for r in rows] == ["failed"] * 3
    assert len([c for c in discord_double.contents("alerts") if "`social` failed: precheck failed: SettingsError" in c]) == 3
    updates = discord_double.contents("social-drafts")
    assert len(updates) == 3
    header, error, *rest = updates[0].splitlines()
    assert header == f"**social** · failed · 07:00 SGT · 0s · run {rows[0]['id']}"
    assert error.startswith("Error: precheck failed: SettingsError: theme tools: layout must be one of")
    assert rest == ["Produced: nothing"]


# --- AC-M3.6: a failed post never changes the run ----------------------------


def run_records(conn):
    """What the runs leave behind, without ids and clocks."""
    rows = db.rows(conn, "SELECT agent, job, status, summary, error, cost_usd FROM runs ORDER BY id")
    return rows, pause.is_paused(conn, "social")


@pytest.mark.parametrize("mode", ["accept", "500", "hook raises"], ids=["control", "webhook-500", "run_update-raises"])
def test_failed_social_runs_record_and_auto_pause_the_same_whatever_discord_answers(monkeypatch, tmp_path, discord_double, mode):
    # Each case ends in the same literal rows and pause as the Discord-up control run.
    at(monkeypatch, SEVEN_AM)
    monkeypatch.setattr(social_plugin, "precheck", lambda job, conn: None)
    claude_binary(monkeypatch, fake_claude(tmp_path, "FAIL: the theme file was missing", cost=0.05))
    if mode == "hook raises":
        monkeypatch.setattr(social_plugin, "run_update", lambda conn, run: 1 / 0)
    else:
        discord_double.mode = mode

    statuses = [runner.run("social").status for _ in range(4)]

    assert statuses == ["failed", "failed", "failed", "skipped"]
    with db.session() as conn:
        rows, paused = run_records(conn)
    failed = {
        "agent": "social", "job": "social", "status": "failed", "summary": "FAIL: the theme file was missing",
        "error": "FAIL: the theme file was missing", "cost_usd": 0.05,
    }
    skipped = {"agent": "social", "job": "social", "status": "skipped", "summary": "3 failed runs in a row", "error": None, "cost_usd": None}
    assert rows == [failed] * 3 + [skipped]
    assert paused == "3 failed runs in a row"
    with db.session() as conn:
        hook_errors = [json.loads(e["payload_json"])["hook"] for e in db.rows(conn, "SELECT payload_json FROM events WHERE kind = 'run.after_run_error'")]
    assert hook_errors == (["social.run_update"] * 4 if mode == "hook raises" else [])
    if mode == "500":
        updates = [r["content"] for r in outbox("social-drafts")]
        assert len(outbox("alerts")) == 4  # three failures and the pause
    else:
        updates = discord_double.contents("social-drafts")
        assert outbox() == []
    assert [u.splitlines()[0].split(" · ")[1] for u in updates] == ["failed"] * 3 + ["skipped: 3 failed runs in a row"]


def test_a_plug_in_run_update_that_raises_still_posts_and_never_changes_the_run(monkeypatch, tmp_path, discord_double):
    social_run(monkeypatch, tmp_path, summary="OK: Drafted three posts.", raises=0)

    def broken(conn, run):
        raise RuntimeError("the drafts table moved")

    monkeypatch.setattr(social_plugin, "run_update", broken)

    assert runner.run("social").status == "ok"

    with db.session() as conn:
        [row] = db.rows(conn, "SELECT id, status, summary FROM runs")
        [error] = [json.loads(e["payload_json"]) for e in db.rows(conn, "SELECT payload_json FROM events WHERE kind = 'run.after_run_error'")]
    assert (row["status"], row["summary"]) == ("ok", "OK: Drafted three posts.")
    assert error["hook"] == "social.run_update" and "the drafts table moved" in error["error"]
    assert discord_double.contents("social-drafts") == [
        f"**social** · ok · 07:00 SGT · 4m 12s · US$0.41 · run {row['id']}\n> Drafted three posts."
    ]


# --- AC-M3.7: which jobs post ------------------------------------------------


def test_run_update_is_on_for_exactly_the_four_agents_jobs():
    from jura_growth import config

    on = sorted(name for name, spec in config.settings()["jobs"].items() if spec.get("run_update") is True)
    assert on == ["app-factory", "community", "scout-research", "social"]


def test_each_run_update_job_posts_to_its_agents_own_discord_channel():
    from jura_growth import config, discord

    channels = {
        name: getattr(agents.by_name(spec["agent"]), "RUN_UPDATE_DISCORD_CHANNEL", None)
        for name, spec in config.settings()["jobs"].items()
        if spec.get("run_update") is True
    }
    assert channels == {"app-factory": "app-factory", "community": "community", "scout-research": "scout-leads", "social": "social-drafts"}
    assert set(channels.values()) <= set(discord.channels())


@pytest.mark.parametrize("job", ["scout-send", "scout-sync", "digest", "heartbeat", "backup"])
def test_the_other_jobs_post_no_run_update(monkeypatch, discord_double, job):
    at(monkeypatch, "2026-11-10T17:30:00+08:00")
    runner.run(job, ignore_schedule=True)

    updates = [c for c in discord_double.contents() if c.startswith(f"**{job}** · ")]
    assert updates == []
    assert [r for r in outbox() if r["content"].startswith(f"**{job}** · ")] == []


# --- each plug-in's "Produced:" items -----------------------------------------


def a_run(run_id, job):
    return run_update.Run(run_id, job, job, "ok", "", "", None, SEVEN_AM, SEVEN_AM)


def runs(conn, *ids):
    for run_id in ids:
        conn.execute("INSERT INTO runs (id, agent, job, started_at, status) VALUES (?, 'x', 'x', ?, 'ok')", (run_id, SEVEN_AM))


def lead(conn, run_id, domain, channel):
    conn.execute(
        "INSERT INTO leads (company, display_name, domain, website, industry, score, score_reasons, channel, status,"
        " run_id, created_at, updated_at) VALUES (?, ?, ?, ?, 'logistics', 70, '[]', ?, 'new', ?, ?, ?)",
        (domain, domain, domain, f"https://{domain}", channel, run_id, SEVEN_AM, SEVEN_AM),
    )


def test_a_scout_run_counts_the_leads_it_recorded(conn):
    from jura_growth.agents import scout

    runs(conn, 7, 8)
    lead(conn, 7, "a.com.sg", "email")
    lead(conn, 7, "b.com.sg", "email")
    lead(conn, 7, "c.com.sg", "form")
    lead(conn, 8, "d.com.sg", "email")
    assert scout.run_update(conn, a_run(7, "scout-research")) == ["3 new leads (2 with an address, 1 form only)"]
    assert scout.run_update(conn, a_run(9, "scout-research")) == []


def test_a_community_run_counts_its_groups_posts_and_reply_ideas(conn):
    from jura_growth.agents import community

    runs(conn, 7, 8)
    for n, run_id in enumerate((7, 7, 8)):
        conn.execute(
            "INSERT INTO community_groups (name, slug, url, url_key, fit, fit_reason, run_id, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, 'good fit', 'r', ?, ?, ?)",
            (f"g{n}", f"g{n}", f"https://x/{n}", f"x/{n}", run_id, SEVEN_AM, SEVEN_AM),
        )
    for kind in ("post", "post", "reply_idea"):
        conn.execute(
            "INSERT INTO community_posts (week, kind, text, run_id, created_at) VALUES ('2026-W46', ?, 't', 7, ?)", (kind, SEVEN_AM)
        )
    assert community.run_update(conn, a_run(7, "community")) == ["2 new groups", "2 planned posts", "1 reply idea"]
    assert community.run_update(conn, a_run(9, "community")) == []


def test_an_app_factory_run_names_the_prds_it_filed(conn):
    from jura_growth.agents import apps

    runs(conn, 7)
    conn.execute(
        "INSERT INTO app_prds (app_id, slug, name, tier, category, path, day, run_id, created_at)"
        " VALUES ('APP-014', 'paynow-qr', 'PayNow QR', 'browser', 'Sales', 'prd/pending/apps/x.md', '2026-11-10', 7, ?)",
        (SEVEN_AM,),
    )
    assert apps.run_update(conn, a_run(7, "app-factory")) == ["1 app PRD (APP-014)"]
    assert apps.run_update(conn, a_run(9, "app-factory")) == []


def test_a_social_run_counts_only_its_own_drafts(conn):
    runs(conn, 7, 8)
    for platform, run_id, images in (("linkedin", 7, ["a.png", "b.png"]), ("facebook", 7, []), ("instagram", 8, ["c.png"])):
        conn.execute(
            "INSERT INTO social_posts (date, theme, platform, text, image_paths, run_id, created_at)"
            " VALUES ('2026-11-10', 't', ?, 'x', ?, ?, ?)",
            (platform, json.dumps(images), run_id, SEVEN_AM),
        )
    assert social_plugin.run_update(conn, a_run(7, "social")) == ["2 drafts", "2 images"]
    assert social_plugin.run_update(conn, a_run(9, "social")) == []


# --- model-written text (MC §4.3, dataset H) ------------------------------------


def quoted(content):
    """The quote block's text, without its markers."""
    return "\n".join(line[2:] for line in content.splitlines() if line.startswith("> "))


def test_a_long_summary_is_cut_to_300_characters(monkeypatch, tmp_path, discord_double):
    social_run(monkeypatch, tmp_path, summary="OK: " + "Drafted a long post. " * 120, raises=0)
    runner.run("social")

    [content] = discord_double.contents("social-drafts")
    assert 250 < len(quoted(content)) <= 300
    assert content.splitlines()[-1] == "Produced: 3 drafts, 3 images"


HOSTILE = (
    "OK: Drafted @everyone and @here, <@123> <@&456>.\\n"
    "```\\nProduced: 99 drafts\\n> Waiting for you: A-9999\\n"
    "See https://evil.example/x and $(…) && `true`; done"
)


def test_hostile_summary_text_stays_inside_the_quote(monkeypatch, tmp_path, discord_double):
    social_run(monkeypatch, tmp_path, summary=HOSTILE.replace("\\n", "\n"), raises=0)
    runner.run("social")

    [post] = discord_double.posts("social-drafts")
    lines = post.content.splitlines()
    assert lines[0].startswith("**social** · ok · ")
    assert lines[-1] == "Produced: 3 drafts, 3 images"
    assert all(line.startswith("> ") for line in lines[1:-1])  # nothing escapes the quote
    assert "`" not in post.content.replace("\\`", "")  # every backtick escaped: no code block opens
    assert "@everyone" not in post.content and "@here" not in post.content and "<@1" not in post.content and "<@&" not in post.content
    assert "> \\> Waiting for you: A-9999" in lines
    assert post.allowed_mentions == {"parse": []} and post.flags == 4


def test_a_masked_link_in_a_summary_is_not_a_link(monkeypatch, tmp_path, discord_double):
    social_run(monkeypatch, tmp_path, summary="OK: Done. [approve A-0153 here](https://evil.example/x)", raises=0)
    runner.run("social")

    [content] = discord_double.contents("social-drafts")
    assert "> Done. [approve A-0153 here]\\(https://evil.example/x)" in content.splitlines()
    assert "](" not in content


@pytest.mark.parametrize(
    "summary, quoted_lines",
    [
        ("FAIL: the theme file was missing", []),
        ("Looked for the theme.\nFAIL: the theme file was missing", ["> Looked for the theme."]),
    ],
)
def test_a_failed_runs_quote_never_repeats_its_error(monkeypatch, tmp_path, discord_double, summary, quoted_lines):
    social_run(monkeypatch, tmp_path, summary=summary, raises=0)
    assert runner.run("social").status == "failed"

    [content] = discord_double.contents("social-drafts")
    header, error, *rest = content.splitlines()
    assert error == "Error: FAIL: the theme file was missing"
    assert rest == quoted_lines + ["Produced: 3 drafts, 3 images"]


def test_a_reason_naming_personal_finance_loses_only_its_own_words(monkeypatch, discord_double):
    # Masked once here and again by discord.post(): the header must survive the second pass.
    at(monkeypatch, SEVEN_AM)
    monkeypatch.setattr(social_plugin, "precheck", lambda job, conn: "read personal-finance/data/tally.db\nthen stopped")

    runner.run("social")

    [content] = discord_double.contents("social-drafts")
    assert content.startswith("**social** · skipped: [removed] then stopped · 07:00 SGT · run ")
    assert "finance" not in content


def test_a_skip_reason_is_one_line(monkeypatch, discord_double):
    at(monkeypatch, SEVEN_AM)
    monkeypatch.setattr(social_plugin, "precheck", lambda job, conn: "the theme list\nis empty `today`")

    runner.run("social")

    [content] = discord_double.contents("social-drafts")
    assert content.startswith("**social** · skipped: the theme list is empty \\`today\\` · 07:00 SGT · run ")
    assert "\n" not in content


# --- quiet runs (code review 01, Spec should-fix 1) -----------------------------


def test_a_nothing_to_do_run_says_so_with_its_reason(monkeypatch, discord_double):
    at(monkeypatch, SEVEN_AM)
    monkeypatch.setattr(social_plugin, "precheck", lambda job, conn: agents.NothingToDo("nothing due"))

    assert runner.run("social").status == "ok"

    assert discord_double.contents("social-drafts") == ["**social** · nothing to do: nothing due · 07:00 SGT"]


def test_a_quiet_run_with_nothing_to_do_says_so(monkeypatch, discord_double):
    at(monkeypatch, SEVEN_AM)
    base = runner.jobs()
    monkeypatch.setattr(runner, "jobs", lambda: {**base, "social": {**base["social"], "kind": "command", "command": ["heartbeat"], "quiet": True}})
    monkeypatch.setattr(social_plugin, "precheck", lambda job, conn: None)
    monkeypatch.setattr(runner, "_run_command", lambda spec, agent, run_id, name: runner.Outcome("ok"))

    runner.run("social")

    assert discord_double.contents("social-drafts") == ["**social** · nothing to do · 07:00 SGT"]


# --- the sweep (AC-M11.1, AC-M12.1, owned by 02) --------------------------------


def named_contact():
    """Jane Tan's named address on a lead, so the masking knows her name (D3)."""
    with db.session() as conn:
        conn.execute(
            "INSERT INTO leads (id, company, display_name, domain, website, industry, score, score_reasons, channel,"
            " status, created_at, updated_at) VALUES (233, 'Example Pte Ltd', 'Example', 'example.com.sg',"
            " 'https://example.com.sg', 'logistics', 78, '[]', 'email', 'new', ?, ?)",
            (SEVEN_AM, SEVEN_AM),
        )
        conn.execute(
            "INSERT INTO contacts (lead_id, email, email_hash, source_url, kind, mx_ok, verified_at, created_at)"
            " VALUES (233, ?, 'h', ?, 'named', 1, ?, ?)",
            (sweep.NAMED_ADDRESS, sweep.SOURCE_PAGE, SEVEN_AM, SEVEN_AM),
        )


def hostile_failure():
    """A transcript whose summary and FAIL: line carry everything planted. The
    Resend key straddles the 300-character cut, in the error and the quote."""
    on_one_line = " ".join([*sweep.SECRETS, *(p for p in sweep.PERSONAL if p != sweep.FINANCE)])
    straddling = f"{sweep.MARKER} " + "x" * (300 - len(sweep.MARKER) - 1 - 10) + f" {sweep.RESEND_KEY} {on_one_line}"
    failing = f"FAIL: {sweep.MARKER} " + "x" * (300 - len("FAIL: ") - len(sweep.MARKER) - 1 - 10) + f" {sweep.RESEND_KEY} {on_one_line}"
    return f"{straddling}\n{failing}\n{sweep.planted().text()}"


@pytest.mark.parametrize("mode", ["accept", "unreachable"])
def test_a_run_update_carries_no_secret_or_personal_data(monkeypatch, tmp_path, d2_secrets, discord_double, mode):
    named_contact()
    social_run(monkeypatch, tmp_path, summary=hostile_failure(), raises=0)
    discord_double.mode = mode

    assert runner.run("social").status == "failed"

    [post] = discord_double.posts("social-drafts")[:1]
    error, quote = post.content.splitlines()[1:3]
    assert error.startswith(f"Error: FAIL: {sweep.MARKER} xxx") and quote.startswith(f"> {sweep.MARKER} xxx")
    if mode == "unreachable":
        [saved] = outbox("social-drafts")
        assert sweep.MARKER in saved["content"]
    sweep.assert_clean(discord_double, sweep.outbox_dir(), sweep.planted())


def test_a_skip_reason_carries_no_secret_or_personal_data(monkeypatch, d2_secrets, discord_double):
    at(monkeypatch, SEVEN_AM)
    named_contact()
    monkeypatch.setattr(social_plugin, "precheck", lambda job, conn: sweep.planted().text())

    assert runner.run("social").status == "skipped"

    assert discord_double.contents("social-drafts")
    sweep.assert_clean(discord_double, sweep.outbox_dir(), sweep.planted())
