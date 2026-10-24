# 02 — The community job can't fetch any Facebook host

Status: ready-for-agent
Blocked by: 01 (both change `runner.claude_command`)
Covers: community C-B2

## Problem

The community PRD rules out fetching facebook.com (§3, §4). The deny list in `config/settings.yaml:93-99` names six exact hosts, and Claude Code 2.1.286 matches `WebFetch(domain:…)` by exact host. So `mbasic.facebook.com`, `business.facebook.com`, `l.facebook.com`, locale subdomains, `fb.watch`, `fbcdn.net`, `facebook.net` and `messenger.com` stay fetchable. `config/community.yaml:26-28` lists more domains than the deny list and claims the deny list covers them.

## What to change

- Give the blocked domains one source: the community plug-in's list (`groups.blocked_domains()`). The runner builds the job's WebFetch denials from it through a plug-in hook, never by importing the community agent by name.
- Deny each apex and every subdomain. First check, with `claude --help` or a real dry run, whether Claude Code 2.1.286 honours `WebFetch(domain:*.facebook.com)`. If it doesn't, enforce the block another way that a headless run can't get around (for example a project-level PreToolUse hook that `--setting-sources project` loads), and say which one you chose in the PR body.
- Correct the comments in `config/community.yaml` and `config/settings.yaml` so they say what the code does.

## Acceptance criteria

- For every domain in the blocked list, the community job's argv (or hook) denies the apex and its subdomains; a test asserts it for each domain (repro `test_facebook_deny_list_misses_listed_and_sub_domains` passes as a regression test).
- Adding a domain to the plug-in's list blocks it with no edit to `settings.yaml`.
- Other jobs' WebFetch access is unchanged.
- `uv run pytest` passes.

## Pointers

- `audit/code-review-03-social-community.md` C-B2
- `jura_growth/runner.py:218-256`, `jura_growth/agents/community/__init__.py:404-445`, `config/settings.yaml:88-100`, `config/community.yaml:22-30`
