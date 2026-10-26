# Browser automation runs only in the publish job, scoped by domain

Status: accepted (2026-10-27, ticket BP-03 of `prd-jura-browser-publishing-2026-10-25.md`). Proposed 2026-10-25.

`claude -p` gets the Claude in Chrome tools only with `--chrome` (the 2026-10-25 spike). The runner
adds it only for jobs in `caps.BROWSER_JOBS` (`publish`), and raises if any other job asks, so a
settings change can't give it to another job. Page tools are allowed only through
`ClaudeInChromeDomain(<host>)` rules for the platforms' own hosts, never by tool name, because a
tool-name allow covers every site. The run has no `--add-dir`, no web search or fetch, and only its
`publish` commands. It drives a dedicated Chrome profile signed in only to the accounts that act as
Jura, with the extension enabled only there (Ting Yu, 2026-10-25); no code can pin the profile, so
the prompt checks it first. Its transcript is audited for every host any tool result showed and for
typed text outside the approved content. The research jobs never get browser tools (ticket 02).
Rollback is removing the job from `BROWSER_JOBS`.

As built in BP-03: the rules come from the publish plug-in (`agents/publish/scope.py`), with one
domain rule per host in `hosts.BROWSER_HOSTS` for each platform this build drives that is in
`browser` mode; the audit is `agents/publish/audit.py`, run by the plug-in's `after_run` before the
run row is finished, so a failed audit fails the run and pauses `publish`. The host list stays
explicit until BP-01's check U18 shows how the domain rule treats subdomains.
