# Browser automation runs only in the publish job, scoped by domain

Status: accepted (2026-10-27, ticket BP-03 of `prd-jura-browser-publishing-2026-10-25.md`). Proposed 2026-10-25.

`claude -p` gets the Claude in Chrome tools only with `--chrome` (the 2026-10-25 spike). The runner
adds it only for jobs in `caps.BROWSER_JOBS` (`publish`), and raises if any other job asks, so a
settings change can't give it to another job. Page tools are allowed only through
`ClaudeInChromeDomain(<host>)` rules for the platforms' own hosts, never by tool name, because a
tool-name allow covers every site. The run has no `--add-dir` beyond its own scratch folder (amended
2026-10-30, below), no web search or fetch, and only its
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

## Amendment 2026-10-30 (rehearsal R1)

The publish run now gets `--add-dir` for its own scratch folder (`data/growth/work/publish/`) and
nothing else; `JURA_ROOT` is never added. The real Claude in Chrome upload tool refuses a file the
session may not read ("only files this session is allowed to read can be uploaded"), and the
approved image copies live there. The folder keeps every approval's copies and the live page text
earlier runs wrote, until `backup.prune_browser_work` removes them after 7 days. None of it is
secret, and the secret-file `Read` denies still apply; a `Read` deny also stops an upload
(rehearsal probe 4).

In the same rehearsal, the transcript audit learned the extension's real tab-context format:
`  • tabId <n>: "<title>" ("<url>")`, with a page-controlled title, a new tab shown as `("")`, and a
trailing `<system-reminder>` block. It reads only lines of exactly that shape, split on `\n`
alone, takes the address from the last `("…")`, and drops reminder blocks from the very end only
(code review rehearsal-fixes, SEC-B1, SEC-B2, SEC-N1). This closes code review 03 S-10.

## Amendment 2026-10-31 (inbox watch)

`publish` is no longer the only browser job, so this record's title no longer holds in full. `inbox-watch`
and `inbox-reply` join `caps.BROWSER_JOBS`, with their rules from the `inbox_browser` plug-in, and
everything above stays true of them: `--chrome` only for those jobs, page tools only by domain, no
`--add-dir` beyond their own scratch folder, and an audited transcript. All three take one `browser` lock in
the runner, and the two inbox jobs start in an empty folder rather than the repo. The audit gained `AuditRules`, and `audit.audit` without them behaves as before. ADR 0006 has the
reasons, and what a watch run is denied beyond this.
