"""The publish job's argv and settings (BP-03; AC-P9.1, AC-P9.2, X4, X8; seam S9).

Only `publish` gets `--chrome`, and only because it is in `caps.BROWSER_JOBS`; its page tools are
allowed only through `ClaudeInChromeDomain(<host>)` rules for the enabled platforms' hosts.
"""

from __future__ import annotations

import pytest

import publish_world as pw
from jura_growth import caps, config, runner, schedule
from runner_support import settings_with

CHROME = "mcp__claude-in-chrome__"
ALL_CLAUDE_JOBS = sorted(name for name, spec in config.settings()["jobs"].items() if spec["kind"] == "claude")


def argv(job, spec=None):
    built, _ = runner.claude_command(job, spec or config.settings()["jobs"][job])
    return built


def rules(built):
    start, middle = built.index("--allowedTools"), built.index("--disallowedTools")
    end = next((i for i in range(middle + 1, len(built)) if built[i].startswith("--")), len(built))
    return built[start + 1:middle], built[middle + 1:end]


# --- AC-P9.1: --chrome for one job only ----------------------------------------------------------


@pytest.mark.parametrize("job", ALL_CLAUDE_JOBS)
def test_only_publish_gains_chrome_and_browser_rules(job, monkeypatch):
    pw.social_config(monkeypatch)
    built = argv(job)
    text = " ".join(built)
    if job == "publish":
        assert "--chrome" in built
        assert "ClaudeInChromeDomain(" in text
    else:
        assert "--chrome" not in built
        assert CHROME not in text
        assert "ClaudeInChromeDomain" not in text


def test_a_job_outside_browser_jobs_that_asks_for_a_browser_raises(monkeypatch):
    settings_with(monkeypatch, fake={"browser": True})
    assert "fake" not in caps.BROWSER_JOBS
    with pytest.raises(runner.JobError, match="browser"):
        runner.claude_command("fake", config.settings()["jobs"]["fake"])


def test_community_keeps_its_facebook_fetch_denials():
    _, denied = rules(argv("community"))
    assert "WebFetch(domain:facebook.com)" in denied
    assert "WebFetch(domain:*.facebook.com)" in denied


# --- AC-P9.2: the publish argv -----------------------------------------------------------------


def test_publish_argv_keeps_the_runner_flags_and_has_no_add_dir(monkeypatch):
    pw.social_config(monkeypatch)
    built = argv("publish")
    for flag in ("--strict-mcp-config", "--setting-sources", "--no-session-persistence"):
        assert flag in built
    assert built[built.index("--permission-mode") + 1] == "dontAsk"
    assert built[built.index("--setting-sources") + 1] == "project"
    assert "--add-dir" not in built  # X8: images are copied into scratch instead


def test_publish_allows_only_the_tab_tools_by_name_and_one_domain_rule_per_facebook_host(monkeypatch):
    pw.social_config(monkeypatch)
    allowed, _ = rules(argv("publish"))
    by_name = sorted(r.removeprefix(CHROME) for r in allowed if r.startswith(CHROME))
    assert by_name == ["list_connected_browsers", "tabs_close_mcp", "tabs_context_mcp", "tabs_create_mcp"]
    domains = sorted(r[len("ClaudeInChromeDomain("):-1] for r in allowed if r.startswith("ClaudeInChromeDomain("))
    assert domains == sorted(["www.facebook.com", "facebook.com", "m.facebook.com", "web.facebook.com", "business.facebook.com"])
    assert not any("discord" in d for d in domains)
    assert "WebSearch" not in allowed and "WebFetch" not in allowed


def test_publish_has_no_domain_rule_for_a_platform_in_draft_mode(monkeypatch):
    pw.social_config(monkeypatch, browser=())
    allowed, _ = rules(argv("publish"))
    assert not [r for r in allowed if r.startswith("ClaudeInChromeDomain(")]


FACEBOOK_HOSTS = ["www.facebook.com", "facebook.com", "m.facebook.com", "web.facebook.com", "business.facebook.com"]
INSTAGRAM_HOSTS = ["www.instagram.com", "instagram.com"]
LINKEDIN_HOSTS = ["www.linkedin.com", "linkedin.com"]


def domains(built) -> list[str]:
    allowed, _ = rules(built)
    return [r[len("ClaudeInChromeDomain("):-1] for r in allowed if r.startswith("ClaudeInChromeDomain(")]


@pytest.mark.parametrize("browser, expected", [
    (("instagram",), INSTAGRAM_HOSTS),
    (("linkedin",), LINKEDIN_HOSTS),
    (("facebook", "instagram", "linkedin"), FACEBOOK_HOSTS + INSTAGRAM_HOSTS + LINKEDIN_HOSTS),
])
def test_bp04_one_domain_rule_per_host_of_each_platform_in_browser_mode(monkeypatch, browser, expected):
    """AC-P9.2 for the new hosts: exactly each enabled platform's own hosts, once each. No CDN,
    link-shim, short-link or help host, and never a Discord host."""
    pw.social_config(monkeypatch, browser=browser)
    found = domains(argv("publish"))
    assert sorted(found) == sorted(expected)
    assert len(found) == len(set(found))
    for host in found:
        assert not any(word in host for word in ("discord", "cdn", "fbcdn", "licdn", "lnkd", "l.instagram", "static"))


def test_bp04_a_platform_in_draft_mode_opens_none_of_its_hosts(monkeypatch):
    pw.social_config(monkeypatch, browser=("facebook",))
    text = " ".join(domains(argv("publish")))
    assert "instagram" not in text and "linkedin" not in text


NAMED_DENIES = ("javascript_tool", "read_network_requests", "read_console_messages", "shortcuts_execute",
                "shortcuts_list", "gif_creator", "switch_browser", "select_browser", "browser_batch", "resize_window")


def test_publish_denies_the_risky_tools_by_name(monkeypatch):
    pw.social_config(monkeypatch)
    _, denied = rules(argv("publish"))
    for tool in NAMED_DENIES:
        assert CHROME + tool in denied
    assert "WebSearch" in denied and "WebFetch" in denied


def test_publish_denies_file_upload_when_the_next_item_has_no_image(conn, monkeypatch):
    pw.social_config(monkeypatch)
    pw.at(monkeypatch, pw.TEN)
    _, denied = rules(argv("publish"))
    assert CHROME + "file_upload" in denied  # nothing approved: nothing to upload


def test_publish_allows_file_upload_when_the_approved_item_has_an_image(conn, monkeypatch):
    pw.social_config(monkeypatch)
    pw.at(monkeypatch, pw.MORNING)
    pw.approved(conn, monkeypatch)
    conn.commit()
    pw.at(monkeypatch, pw.TEN)
    _, denied = rules(argv("publish"))
    assert CHROME + "file_upload" not in denied


def test_publish_bash_is_only_its_own_publish_commands(monkeypatch):
    pw.social_config(monkeypatch)
    allowed, _ = rules(argv("publish"))
    bash = {r for r in allowed if r.startswith("Bash(") and not r.endswith("--help)")}
    commands = {r[len("Bash(jura-growth "):].removesuffix(")").removesuffix(":*") for r in bash}
    assert commands <= {"publish next", "publish done", "publish stopped", "publish note-rules"}
    assert {"publish next", "publish done", "publish stopped"} <= commands


# --- X4: the job's settings and schedule -------------------------------------------------------


def test_the_publish_job_is_a_quiet_browser_claude_job_after_community():
    jobs = config.settings()["jobs"]
    spec = jobs["publish"]
    assert spec["agent"] == "publish" and spec["kind"] == "claude" and spec["prompt"] == "publish.md"
    assert spec["quiet"] is True and spec["browser"] is True and spec["run_update"] == "claimed-only"
    names = list(jobs)
    assert names.index("publish") == names.index("community") + 1


def test_the_publish_schedule_is_every_20_minutes_from_0900_to_1740_every_day():
    shape = config.settings()["jobs"]["publish"]["schedule"]
    slots = schedule.sgt_slots(shape)
    assert len(slots) == 27
    assert all(day is None for day, _, _ in slots)  # weekends included
    assert slots[0][1:] == (9, 0) and slots[-1][1:] == (17, 40)
    assert not schedule.business_days_only(shape)
    assert schedule.describe(config.settings()["jobs"]["publish"]) == "daily 09:00–17:40, every 20 min"


# --- the one --chrome, and ADR 0005 ------------------------------------------------------------


def test_chrome_flag_appears_only_in_the_runners_browser_jobs_branch():
    from jura_growth import paths

    found = []
    for path in sorted((paths.REPO_ROOT / "jura_growth").rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if '"--chrome"' in line or "'--chrome'" in line:
                found.append((path.relative_to(paths.REPO_ROOT).as_posix(), line.strip()))
    assert found == [("jura_growth/runner.py", 'argv.append("--chrome")')]
    source = (paths.REPO_ROOT / "jura_growth" / "runner.py").read_text(encoding="utf-8")
    branch = source[source.index('argv.append("--chrome")') - 80:source.index('argv.append("--chrome")')]
    assert "if browser and spec.get(\"browser\"):" in branch


def test_adr_0005_is_accepted():
    from jura_growth import paths

    adr = paths.REPO_ROOT / "docs" / "adr" / "0005-browser-automation-runs-only-in-the-publish-job.md"
    status = next(line for line in adr.read_text(encoding="utf-8").splitlines() if line.startswith("Status:"))
    assert status.startswith("Status: accepted")
