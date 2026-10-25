# Scout note: the stdlib baseline, and what was rejected

Feature: mission-control. Vetted 2026-10-24 by crew:skill-scout.

The cards in this folder:

| Card | Verdict | Risk |
|---|---|---|
| `markdown-it-py.md` | recommend with conditions | Medium |
| `jinja2.md` | don't recommend | High (scanner floor) |
| `pytest-playwright.md` | don't recommend | High (scanner floor) |

## What is already installed

Nothing installed covers Python HTTP serving, HTML templating, markdown rendering or isolating untrusted HTML. The UI process is already covered:

- The design system first, then `frontend-design`.
- `crew:web-design-review` for UI review.
- `security-review` and mattpocock `code-review` for code review.
- Claude in Chrome or the built-in browser for a manual QA pass.

## The stdlib baseline

Recommended for every need except rendered markdown.

| Need | Stdlib route | Why it's enough here |
|---|---|---|
| HTTP serving | `http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)` with a `BaseHTTPRequestHandler` subclass that routes its own paths. A WSGI app on `wsgiref.simple_server` also works, and tests can call it directly | Python's docs say `http.server` "is not recommended for production". One user on loopback, GET only, is the case it suits. Never use `SimpleHTTPRequestHandler` over a data folder |
| HTML templating | One helper that runs `html.escape(value, quote=True)` on every value, plus a `str` subclass marking fragments that are already safe. `string.Template` for page skeletons, fed only safe fragments | The repo already works this way: `agents/social/render.py` `_fill` (escaped `{{x}}`, raw `{{{x}}}`) and `agents/outreach/compose.py`. `string.Template` alone never escapes, so never pass it a raw value |
| Markdown (PRDs, digests) | Escaped text in `<pre>` with `white-space: pre-wrap` | Safe and readable. Tables show as pipes, which is the case for `markdown-it-py.md` |
| Untrusted email HTML | Serve each body at its own route with `Content-Security-Policy: sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:`, and embed it as `<iframe sandbox src="…">` with no `allow-*` tokens | The browser enforces it, which is stronger than sanitising. Proved on this Mac (see Evidence). `outreach/compose.py` `to_html` uses only inline styles and links, no images, so the preview loses nothing. Links in the preview are inert, by design |
| Plain-text bodies, transcripts | `html.escape`; `json.loads` per JSONL line; reuse `jura_growth/transcripts.py` | Already in the repo |
| Images (social drafts) | `mimetypes.guess_type`, plus the path confinement below | — |
| Server tests | `http.client` against the server on port 0 in a thread, or the WSGI app called directly | Covers routes, status codes, headers, the Host check and escaping, with no browser |
| Browser tests | Headless Chrome through `subprocess`, reusing the `_chrome()` pattern from `agents/social/render.py`: `--dump-dom` for the sandbox check, `--screenshot --window-size=360,800` for layout | Proved on this Mac. Google Chrome is installed in `/Applications` |

## Guardrails the build needs, whatever it depends on

1. **Host header allowlist.** Accept only `127.0.0.1:<port>` and `localhost:<port>`, and answer anything else with 421. This blocks DNS rebinding, the realistic way a web page open in the same browser could read this server. Verified in the probe.
2. **Loopback, read-only.** Bind `127.0.0.1` only. Serve GET and HEAD, and answer 405 to everything else. No route changes state.
3. **Shell page headers.**
   - CSP: `default-src 'none'; style-src 'self'; img-src 'self' data:; frame-src 'self'; script-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`, plus the font hosts if the fonts question below is answered yes.
   - Also `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`.
4. **Email body route.** Use the sandbox CSP from the table, the same two headers, and an embedding `<iframe sandbox>` with no `allow-scripts` and no `allow-same-origin`.
5. **File serving by allowlist.**
   - Allowed roots: `outputs/growth/{social,community,digests}`, `data/growth/transcripts`, and from the design system `styles.css`, `tokens/*.css` and `assets/*.svg`.
   - Call `resolve()`, then check `is_relative_to(root)`, and refuse everything else.
   - Never serve from the repo root, where `.env` lives. Serve SVG with the sandbox CSP as well.
6. **SQLite, read-only and brief.**
   - Open `sqlite3.connect(f"file:{db}?mode=ro", uri=True)` with a short busy timeout, then fetch everything and close, once per request.
   - Don't call `db.connect()`: it creates folders, sets `journal_mode` and runs migrations.
   - Don't use `immutable=1`.
   - In rollback-journal mode, a reader's shared lock blocks a writer's commit, and `scout-send` writes every 10 minutes during business hours. Never hold a read open while rendering.
7. **Browser tests stay on loopback.** Use `--host-resolver-rules="MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"`. The existing `_chrome(offline=True)` uses `MAP * ~NOTFOUND`, which also blocks `127.0.0.1`: in the probe, no page loaded under it.
8. **Browser tests check the page loaded.** Assert the page loaded before asserting that a script didn't run. Otherwise the test passes on a blank page; the first version of the probe made exactly that mistake. Match the rendered attribute, not the script's source text, which `--dump-dom` also contains.

## Design system: two remote loads to decide

`design-system/` is read-only, so both are CSP choices, not edits.

- **Fonts.** `tokens/fonts.css` `@import`s Google Fonts. Fetching it needs `fonts.googleapis.com` in `style-src` and `fonts.gstatic.com` in `font-src`. Blocked, the page falls back to the stacks in `tokens/typography.css` (Helvetica Neue, Arial, Menlo). Allowed, it makes one third-party request per page load and sends no data. This is a question for Ting Yu.
- **Lucide and other unpinned scripts.** `SKILL.md`'s setup line loads `https://unpkg.com/lucide@latest/dist/umd/lucide.js`, which is unpinned remote JavaScript. The `ui-kit` cards also load React, ReactDOM and Babel from unpkg. Mission control should load none of them: the page needs no JavaScript, and `script-src 'none'` keeps it that way. If a view needs an icon, inline the SVG from a pinned Lucide release, never `@latest`.

## Looked at and rejected

| Candidate | Source | Why not |
|---|---|---|
| nh3 0.3.7 | messense/nh3 (MIT; Rust `ammonia` bindings) | HTML sanitiser. The sandboxed route isolates email HTML in the browser, which is stronger than cleaning it, and `to_html` already escapes the model's text. It ships only compiled wheels, so it hits the same opaque-binary floor as MarkupSafe |
| bleach 6.4.0 | mozilla/bleach | Deprecated by Mozilla in January 2023 and on security fixes only. 13 advisories in its history |
| justhtml 3.15.0 | Emil Stenström (MIT, pure Python) | A young HTML5 parser and sanitiser with 11 advisories published in 2026 alone. Too new to be a security boundary |
| mistune 3.4.0 | lepture/mistune | 41 advisories in its history, many from 2026 |
| Python-Markdown 3.11.2 | Python-Markdown/markdown | Passes raw HTML through by design and needs a separate sanitiser |
| Flask; Starlette with uvicorn; bottle 0.13.4 | pallets, encode, bottlepy | Frameworks for routing that a GET-only page with about ten routes doesn't need. Flask brings Jinja2 and MarkupSafe (see `jinja2.md`). bottle is a single file with 4 CVEs in its history |
| Selenium 4.51.0 | SeleniumHQ | Its Selenium Manager downloads drivers and sends usage statistics to Plausible by default; `SE_AVOID_STATS=true` opts out. It is heavier than Playwright for the same job |
| `webapp-testing` skill | anthropics/skills @ dbd4588f9e1033efb41dad4bef2f7947c8993d44 (Apache-2.0) | It wraps Playwright, so the `pytest-playwright.md` risk applies. It produces standalone scripts, not pytest tests. Its `SKILL.md` tells the agent "DO NOT read the source" of its helper scripts and to run them as black boxes, which works against the crew's review rules |
| `playwright`, `chrome-devtools-mcp`, `browser-use` plugins | Official plugin catalog | Agent-driven browsers through MCP servers, which run outside the sandbox. They overlap with Claude in Chrome and the built-in browser for a manual QA pass, and they don't give repeatable tests |
| `security-guidance` plugin | Official plugin catalog (Anthropic) | Hooks on every edit plus an LLM diff review on Stop, across all repos. It overlaps `security-review` and mattpocock `code-review`, which the crew already runs |
| skills.sh results | Searches: playwright python, html sanitize, jinja, python http server, local dashboard, csp security headers | Nothing from a vendor or Anthropic. Two things to know about: `python-executor` listed under unrelated owners using the superpowers name (`101-skills/superpowers`, `magentosh/superpowers`), and a high-install `anti-detect-browser` skill. Name search surfaces both first |

## Evidence

- **CSP probe.** Scratch probe (`ThreadingHTTPServer` on `127.0.0.1:0`, headless Chrome `--dump-dom`, a temporary profile, a planted `<script>` setting `data-ran="yes"`):

  | Case | Planted script ran? |
  |---|---|
  | No CSP | yes |
  | `sandbox` CSP | no |
  | Shell page with `script-src 'none'` | no |

  A foreign `Host` header got a 421.
- **Offline rules.** Under `MAP * ~NOTFOUND`, no page loaded. With `EXCLUDE 127.0.0.1` added, the results matched the table above.
- **Scanner floors** (shipped footprints):

  | Package | Floor |
  |---|---|
  | markdown-it-py | Medium |
  | mdurl | Low |
  | Jinja2 | High |
  | MarkupSafe | High |
  | playwright | High |
  | pytest-playwright | Medium |
  | greenlet | High |
  | text-unidecode | High |
  | python-slugify | Medium |
  | pyee 14.0.0 | Low |

- **Wheels against source.** Every wheel matched its PyPI sha256 and was byte-identical to its pinned tag. The one exception is MarkupSafe's compiled `.so`.
- **OSV.** No advisory affects any pinned version (checked 2026-10-24).
