# Risk card: pytest-playwright (with playwright)

| | |
|---|---|
| **Verdict** | don't recommend |
| **Risk** | High (scanner floor: High) |
| **Source** | microsoft/playwright-pytest @ 80d7569debc94f648e39ba2d2ccb2a580283894a (v0.10.0), path `pytest-playwright/pytest_playwright/`; microsoft/playwright-python @ bcb9debb4f3a9bb22f954e0f71e4c5b512ad7142 (v1.64.1), path `playwright/` |
| **Maintainer** | Microsoft's Playwright team. playwright-python dates from 2020 (15k stars), and its wheels carry PyPI attestations from `microsoft/playwright-python` (workflow `publish.yml`). pytest-playwright 0.10.0 has no attestation |
| **Licence** | Apache-2.0 (both); vendorable: yes, but this is a dev dependency, not something to vendor |
| **Kind** | Python libraries (dev dependency): a pytest plugin, plus a client bundling a Node.js runtime and driver |
| **Always-on cost** | 0 tokens |
| **Vetted** | 2026-10-24, by crew:skill-scout |

## What it does

Playwright's Python package drives a bundled Node.js driver: `playwright/driver/node` plus several megabytes of bundled JavaScript. The driver launches Chromium, Firefox or WebKit. Those browsers are either downloaded from Microsoft's CDN by `playwright install` or, with `channel="chrome"`, taken from the installed Google Chrome. pytest-playwright adds `page`, `browser` and `context` fixtures and the matching command-line options.

## Gain for this task

Playwright would give repeatable browser tests for the two things only a browser can prove:

1. The sandboxed email preview never runs script.
2. The page lays out at 360px.

Both are already reachable without it:

- **The browser is already wired up.** The repo drives headless Chrome through `subprocess` in `jura_growth/agents/social/render.py` (`chrome_path()`, `_chrome()`, `screenshot()`).
- **The sandbox proof already works.** A scratch probe on this Mac (2026-10-24) put headless Chrome's `--dump-dom` against a stdlib server. A planted script ran when the page had no CSP header and was blocked once the `sandbox` CSP was added.
- **Screenshots at 360px** come from the existing `screenshot()` helper.

What remains is a nicer API (selectors, auto-waits, `expect`), not a new capability. Playwright earns its weight on pages with their own JavaScript, and mission control has none.

## Files reviewed

Shipped footprint, every wheel checked against PyPI's sha256:

- **`pytest_playwright-0.10.0-py3-none-any.whl`** (sha256 `8314d1af726e2c15531635902ece3ee47ed83f5a75c937a7eda8686d3dae6c0d`). `__init__.py` and `pytest_playwright.py` (1,095 lines) were read in full and are identical to the tag.
- **`playwright-1.64.1-py3-none-macosx_11_0_arm64.whl`** (sha256 `59f7b041284ce8d1b72098ae50ca48a2d83692eec25154ab5ba79d4b6b4fe8a9`; 43 MB compressed, 194 files):
  - The Python layer (`_impl/`, `sync_api/`, `async_api/`) was reviewed by grep. `_impl/_driver.py` and `_impl/_transport.py` start the Node driver and read `PLAYWRIGHT_NODEJS_PATH` and `DEBUGP`.
  - `driver/node` is a 116.9 MB binary and was not readable.
  - `driver/package/lib/coreBundle.js` (3.4 MB) and `utilsBundle.js` (2.9 MB) are minified bundles and could not be read in full.
  - `webp_codec.wasm` is opaque.
  - Installer scripts sit under `driver/package/bin/`.
- **Transitive dependencies:**
  - greenlet 3.5.6: compiled.
  - pyee 14.0.0: pure Python. Playwright pins `pyee<15`, although 15.0.0 is the newest release.
  - python-slugify 9.1.3.
  - text-unidecode 1.3: ships `data.bin`, a 311 KB opaque table.

## Red flags

Scanner, shipped footprint (playwright wheel floor High, 717 findings):

- High `opaque-large-file`, `playwright/driver/node`: 116.9 MB, not read.
- High `opaque-file`, `driver/package/lib/webp_codec.wasm`.
- High `obfuscation` ×209 in `driver/package`: the minified bundles.
- High `config-tamper`, `driver/package/bin/install_webkit_wsl.ps1:26`: appends a `PATH` export to `~/.profile`. It's the WSL WebKit installer, never run on macOS, but it ships.
- High `secret-path-read`, `coreBundle.js:72390`: `dotenv.config({ path: "playwright.env" })` loads a `playwright.env` from the working directory.
- High `secret-path-read`, `coreBundle.js:75185`: reads `PLAYWRIGHT_MCP_EXTENSION_TOKEN`. The driver now bundles Playwright's MCP server code.
- Medium `telemetry` ×5: protocol type comments, a Firefox preference, and a comment at `_impl/_waiter.py:62`. Grep found no telemetry sender in the Python layer, but the bundles can't be fully read.
- Medium `auto-update` and `injection-phrase`, one each, in the bundles: a polling comment and an install-location log line.
- Transitive: greenlet's compiled `.so` files (high `opaque-file` ×5), text-unidecode's `data.bin` (high `opaque-file`), and python-slugify's `__version__.py:5` (medium `network-call`, a URL).
- pytest-playwright: medium `unpinned-remote-package` at `pytest_playwright.py:809`, which is a comment.

By reading:

- **About 123 MB of the driver can't be accounted for by reading.** That alone is the rubric's definition of High.
- **pytest-playwright loads into every test run.** It registers through a `pytest11` entry point, so once installed it loads into every `uv run pytest`, not only browser tests.
- **It deletes a folder at the start of every session.** The autouse session fixture `delete_output_dir` (`pytest_playwright.py:95–113`) runs `shutil.rmtree` on `--output`. That defaults to `test-results`, relative to the working directory.
- **playwright 1.64.1 is very new.** It was published on 2026-10-22, two days before this vetting.

## Notes

- OSV lists no advisories for any of these packages (checked 2026-10-24).
- `playwright install` downloads browsers from `cdn.playwright.dev` and `playwright.download.prss.microsoft.com` into `~/Library/Caches/ms-playwright`. `channel="chrome"` avoids the download.
- Whole-clone scan of playwright-python, outside the footprint:
  - `.azure-pipelines/publish-docker.yml:91` writes an `.npmrc`. This is CI only.
  - `tests/assets/` holds `.pfx` client certificates and a minified React fixture.
  - `tests/` has 318 `network-call` hits.
- The playwright-pytest clone's floor is Medium, from the same comment.
- Anthropic's `webapp-testing` skill wraps this same library. See `baseline-and-rejected.md`.

## Conditions of use

These apply only if you choose to override this card:

- Dev dependency group only.
- `channel="chrome"`, and never run `playwright install`.
- Browser tests carry a `browser` marker and are excluded by default (`-m "not browser"` in `addopts`). The plugin itself still loads on every run.
- `--output` pointed at a temporary folder in `addopts`.
- Host-resolver rules so the browser reaches only `127.0.0.1`.
- Take a release only after it has been out for a week. Today that means 1.64.0 (2026-10-13), not 1.64.1.

## Install / uninstall

Not recommended. If you decide to take it anyway, run this from `jurasolutions/repos/growth`:

```
uv add --dev "pytest-playwright==0.10.0" "playwright==1.64.1"
uv remove --dev pytest-playwright playwright
```

For crew: leave it out.
