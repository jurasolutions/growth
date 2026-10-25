# Code review 02: the community job can't fetch any Facebook host

- **Branch:** `crew/growth-blocker-fixes-02-community-blocks-facebook` at `e35c1e5` (one commit)
- **Fixed point:** `4a7859e` (merge-base with `crew/growth-blocker-fixes`)
- **Spec:** `issues/02-community-blocks-all-of-facebook.md`, audit finding C-B2 (`audit/code-review-03-social-community.md`)
- **Files read:** all seven changed files: `README.md`, `config/community.yaml`, `config/settings.yaml`,
  `docs/community.md`, `jura_growth/agents/community/__init__.py`, `jura_growth/agents/community/groups.py`
  and `tests/test_community_fetch_block.py`. I also read the unchanged `jura_growth/runner.py`
  `claude_command` and `jura_growth/headless.py` `Permissions` / `claude_rules`.

## Verdict: approve

There are no blocking findings. The fix does what C-B2 asked for. I ran a live probe on `.invalid`
hosts, and it confirms the two rules each domain now gets cover the apex and every depth of
subdomain. The other jobs' argv is byte-for-byte unchanged. Two should-fix items remain. Neither
reopens a Facebook host, because `groups.BLOCKED_DEFAULT` is always added.

## Evidence (run by the reviewer)

| Command | Result |
|---|---|
| `uv run pytest -p no:cacheprovider` in the developer worktree (JURA_ROOT set, temp data and outputs dirs) | **707 passed** in 26.5s |
| argv for every claude job, built at `4a7859e` (from `git archive`) and at `e35c1e5`, then diffed with the repo path normalised | `app-factory`, `social` and `scout-research` are **identical**. On `community`, the exact `www.`, `m.` and `web.facebook.com` rules are gone. Added: `*.facebook.com`, `*.fb.com`, `*.fb.me`, plus `fb.watch`, `fbcdn.net`, `facebook.net` and `messenger.com`, each with its `*.` rule |
| `claude -p` 2.1.310, `--permission-mode dontAsk`, haiku, deny rules `WebFetch(domain:*.probe.invalid)` and `WebFetch(domain:other.invalid)` | denied: `a.probe.invalid`, `other.invalid`. **Not** denied (DNS failure): `probe.invalid`, `x.other.invalid`. So `*.d` covers subdomains only, `d` covers the exact host only, and both rules are needed, as the developer said |
| Same probe, rules `*.probe.invalid` and `probe.invalid` | denied: `b.a.probe.invalid` (two levels deep), `A.PROBE.INVALID` (upper case) and `probe.invalid.` (trailing dot) |
| `blocked_fetch_domains` given `https://instagram.com`, `"tiktok.com/"` and `"threads.net:443"` in a temp config copy | rules `WebFetch(domain:https://instagram.com)`, `WebFetch(domain:*.https://instagram.com)`, `WebFetch(domain:tiktok.com/)` and `WebFetch(domain:threads.net:443)`. `is_blocked` returns False for `www.instagram.com`, `tiktok.com` and `threads.net`. No error or warning (see SP1) |

## Standards

No documented standard is broken. The deny rules reach the argv through the existing
`Permissions.disallowed_tools` hook (`headless.py:57,134`). `runner.py` and `headless.py` are
untouched, so the core still never imports the community agent by name (README, "the core never
imports them by name"). The commit message and docs follow the voice rules on the operating card.

- **should fix (reuse) ST1**: `tests/test_community_fetch_block.py:17-21`. `webfetch_denials()`
  repeats the argv slicing in `rules(job)` at `tests/test_headless.py:267-271`, including the same
  `next(... startswith("--"))` scan. `:71` slices `--allowedTools` again by hand. Import or share
  `rules()`. Lines 18, 69 and 72 spell out `config.settings()["jobs"][job]`, which
  `runner.job(name)` (`runner.py:53`) already provides.
- **nit ST2**: `tests/test_community_fetch_block.py:46-54` and `:76-82` repeat the same five-step
  setup: copy the config to a temp folder, edit `blocked_fetch_domains`, set
  `JURA_GROWTH_CONFIG_DIR`, then `reset_caches()`. A small fixture would remove the copy.
- **nit ST3**: `tests/test_community_fetch_block.py:24`. `FACEBOOK_DOMAINS` is a third copy of
  `groups.BLOCKED_DEFAULT` (`groups.py:22`) and of the `community.yaml` list. Pinning it guards
  against the default shrinking, which is fine, but say so in the test. Otherwise it is a copy that
  can drift. (Fowler: Duplicated Code, a judgement call.)
- **nit ST4**: the rule pair `WebFetch(domain:d)` / `WebFetch(domain:*.d)` is built in
  `community/__init__.py:68-71` and rebuilt in four places in the test. The "exact host /
  subdomain only" explanation appears three times (`__init__.py:56-58`, test module docstring,
  `docs/community.md:10-12`). A `groups.fetch_denials()` next to `is_blocked` would keep the
  domain-to-rule knowledge in one place, and the test could call it. (Fowler: Feature Envy, a
  judgement call.)

## Spec

| Acceptance criterion | Status |
|---|---|
| Every domain in the blocked list has its apex and subdomains denied, with a test per domain | **met**: `test_the_community_job_denies_each_facebook_apex_and_its_subdomains` and `test_every_domain_in_the_plugins_list_is_denied`. The live probe confirms the rule semantics |
| The ticket asks to check that Claude Code honours `*.x`, and to say which approach was chosen | **met**: the commit message records 2.1.310 and the `.invalid` dontAsk probe. The PR body doesn't exist yet; carry the same text into it at G4 |
| Adding a domain to the plug-in's list blocks it with no edit to `settings.yaml` | **met for a bare domain** (test at `:45`). Not met for a URL-shaped entry: see SP1 |
| Other jobs' WebFetch access is unchanged | **met**: reviewer argv diff, plus `test_other_jobs_webfetch_access_is_unchanged` |
| `uv run pytest` passes | **met**: 707 passed |
| Correct the comments so they say what the code does | **partial**: see SP2 |

- **should fix SP1**: `jura_growth/agents/community/groups.py:39-42`. The new normalisation only
  strips spaces, case, a leading `*.` and dots. An entry written as a URL (`https://instagram.com`),
  with a path (`tiktok.com/`) or with a port (`threads.net:443`) produces deny rules that match no
  host. `is_blocked` and `community audit-run` miss it too, and nothing warns. Reproduced above.
  This breaks the docstring's own promise ("A configured entry is read as a bare lowercase domain")
  and the spirit of "Adding a domain to the plug-in's list blocks it". It is not blocking, because
  the Facebook domains always come from `BLOCKED_DEFAULT`. Fix: run each entry through `host()`
  (`groups.py:46`). Then raise a config error for anything still holding `/`, `:`, whitespace or
  no dot, rather than failing open. Add one test.
- **should fix SP2**: `jura_growth/agents/community/__init__.py:414`. The `audit-run` docstring,
  which `--help` prints, still says "any fetch of facebook.com or fb.com domains". The command now
  checks every domain in `blocked_domains()` and their subdomains. The ticket asks that comments say
  what the code does.
- **scope**: the loose-input normalisation and its test, and the README and `docs/community.md`
  rewrites, go beyond the ticket. They are small and reasonable.

### Other routes to Facebook from the community job

The brief asked whether anything besides WebFetch can still reach a Facebook host.

- The job's tools are `WebSearch`, `WebFetch` and its own `jura-growth` commands only. Running under
  `--permission-mode dontAsk` with `--strict-mcp-config`, it has no general Bash, no curl and no MCP.
- `social render` loads local `file://` templates and design-system assets. Card text is
  HTML-escaped (`social/render.py:213-216,244-245`), and there is no remote image field. `check`
  makes no network calls. `image_path` must be a local PNG that passes `paths.guard()`.
- The httpx link check (`social linkcheck`) is reachable only through `social submit`, which is not
  in the community job's `permissions()` (`community/__init__.py:64-67`). Claude Code denies it, and
  `headless.may_use` refuses it in code. The community job can't reach it.
- **nit / note (not new in this diff)**: `community summary` and `publish-plan` post
  facebook.com/groups links to Discord without suppressing embeds (`community/__init__.py:382`,
  `plan.py:673`). Discord's own servers may fetch those pages for link previews. That is not the run
  fetching Facebook, so PRD §3 and §4 hold, but Ting Yu may want `suppress_embeds` on those posts.
  It belongs in a later ticket.

## Security

The full diff `4a7859e...e35c1e5` was reviewed inline, with no findings at confidence 8 or above.

- The change narrows egress and widens no access. The argv is passed as a list with no shell, and
  configured entries can only land inside the `--disallowedTools` list. An entry can't start with
  `--`, because every rule begins `WebFetch(`, so it can't inject a flag or an allow rule.
- SP1's fail-open needs a human to write `config/community.yaml`, which is trusted input. It is a
  correctness issue, not an exploitable one.
- No secrets, auth, SQL, money or personal data are touched.

## Blocked paths

None touched. The diff changes only `README.md`, `config/`, `docs/`, `jura_growth/` and `tests/`.
It does not touch `inputs/`, `design-system/`, `.env` or the live `data/growth/`. The tests and
probes used temp folders and `.invalid` hosts only.

## UI

No UI files changed, so no web-design review was needed.
