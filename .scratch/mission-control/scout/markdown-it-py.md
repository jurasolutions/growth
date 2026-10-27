# Risk card: markdown-it-py

| | |
|---|---|
| **Verdict** | recommend with conditions |
| **Risk** | Medium (scanner floor: Medium) |
| **Source** | executablebooks/markdown-it-py @ 36c5f547144df2d01970a5792d68c71a3380b227 (v4.2.0), path `markdown_it/`; its one dependency executablebooks/mdurl @ 596bf1c8752de45fa576a52c315d6d8cc5bb1a4e (0.1.2), path `src/mdurl/` |
| **Maintainer** | The Executable Books project (the team behind Jupyter Book and MyST), lead maintainer Chris Sewell. It is a close port of markdown-it, the JavaScript CommonMark parser by Vitaly Puzrin and Alex Kocharin. mdurl is by Taneli Hukkinen, author of tomli (the basis of the stdlib `tomllib`). The repo dates from 2020, has 1.4k stars and was last pushed on 2026-10-19 |
| **Licence** | MIT (both); vendorable: yes |
| **Kind** | Python library (runtime dependency). It also installs a `markdown-it` console script in `.venv/bin` |
| **Always-on cost** | 0 tokens (nothing loads into an agent's context) |
| **Vetted** | 2026-10-24, by crew:skill-scout |

## What it does

It parses CommonMark plus GitHub-style tables and strikethrough, and renders HTML. Mission control would use it to render app PRDs and daily digests. That input is untrusted: headless Claude runs write it, drawing on web content.

## Gain for this task

PRDs and digests read as formatted documents instead of preformatted text. That matters because Jura's PRDs lean on tables: `prd-jura-app-factory-2026-10-24.md` has 28 table lines and the growth foundation PRD has 20. The stdlib baseline (escaped text in a `<pre>` block) is safe and readable, but it shows tables as pipes and dashes. Nothing installed renders markdown.

## Files reviewed

Shipped footprint, checked against PyPI's sha256:

- `markdown_it_py-4.2.0-py3-none-any.whl` (sha256 `9f7ebbcd14fe59494226453aed97c1070d83f8d24b6fc3a3bcf9a38092641c4a`): 66 Python files, 7,325 lines. `diff -rq` against `markdown_it/` at the pinned tag found no differences.
- `mdurl-0.1.2-py3-none-any.whl` (sha256 `84008a41e51615a49fc9966191ff91509e3c40b939176e643fd50a5c2196b8f8`): 6 files, 552 lines, identical to `src/mdurl/` at the tag.

Read in full:

- `main.py`: presets, `validateLink`, `normalizeLink`, `render`.
- `presets/__init__.py`, `presets/default.py`, `presets/commonmark.py`, `presets/zero.py`.
- `common/normalize_url.py`: the URL scheme blocklist.
- `common/utils.py` (`escapeHtml`) and `renderer.py` (`renderAttrs`): attribute values are escaped and always double-quoted.
- `rules_block/html_block.py:44` and `rules_inline/html_inline.py:16`: both return early unless `options["html"]` is set.
- `rules_core/linkify.py`: gated on both the `linkify` option and the optional `linkify_it` module.
- `parser_block.py`, `parser_inline.py`, `parser_core.py`: the rule tables.
- `cli/parse.py`: reads files and stdin, writes to stdout only.

The other rule files were reviewed by import and call inventory. The whole package imports only `argparse`, `codecs`, `collections`, `contextlib`, `dataclasses`, `functools`, `html`, `inspect`, `logging`, `pathlib`, `re`, `sys`, `textwrap`, `typing`, `unicodedata`, `urllib.parse`, `warnings` and `mdurl`. It has no subprocess, socket, HTTP, `eval`/`exec`, environment reads or file writes.

Other contents:

- `port.yaml` is a data record of the JavaScript port. No code loads it.
- `main.py:17` tries `import linkify_it` at load time and does nothing if it's absent. It isn't installed here.
- Entry point: `markdown-it = markdown_it.cli.parse:main`.

## Red flags

Scanner, shipped footprint: six medium `network-call` hits. All six are URLs in docstrings or comments, with no call behind them: `common/html_blocks.py:2`, `common/utils.py:100`, `common/utils.py:245`, `main.py:110`, `presets/__init__.py:16`, `renderer.py:54`. They set the floor at Medium.

By reading:

- **The default constructor is unsafe for this input.** `MarkdownIt()` with no arguments loads the `commonmark` preset, which sets `"html": True` and passes raw HTML, `<script>` included, straight through to the output. `gfm-like` and `gfm-like2` do the same. Only `js-default` (alias `default`) turns raw HTML off.
- **Neither wheel has a PyPI attestation.** Both were uploaded with a maintainer token rather than trusted publishing. Both are byte-identical to their tagged source, so the residual risk is that a future release could differ. An exact pin plus `uv.lock` hashes covers the vetted version.

## Notes

- Advisory history: CVE-2023-26302 and CVE-2023-26303 (crashes on malformed input), fixed in 2.2.0. OSV lists nothing affecting 4.2.0 or mdurl 0.1.2 (checked 2026-10-24).
- `validateLink` blocks `javascript:`, `vbscript:`, `file:` and `data:` URLs, except `data:image/gif|png|jpeg|webp`.
- The `js-default` preset enables every registered rule (tables and strikethrough included), keeps `linkify` and `typographer` off, and sets a nesting limit of 100.
- 4.2.0 was published on 2026-05-07, so it has had five months in use.
- Whole-clone scan: markdown-it-py's floor is Medium, with further `network-call` hits in `docs/` (4), `tests/` (6) and `scripts/` (1). The mdurl clone's 38 hits are all in `tests/`. None of these ship.

## Conditions of use

- Construct the parser only as `MarkdownIt("js-default")`. Never use the no-argument constructor, the `commonmark`, `gfm-like` or `gfm-like2` presets, or an `{"html": True}` options update.
- One module owns the parser instance, so the preset is set in exactly one place.
- A test feeds `<script>…</script>`, `<img src=x onerror=…>` and `[x](javascript:alert(1))`, and asserts that all three come out inert.
- No plugins (`mdit-py-plugins`), no `linkify` extra, and no custom `validateLink` that loosens the default.
- Rendered output goes only into the shell page, under its `script-src 'none'` CSP, never into the email-preview route.
- Pin exactly, keep the `uv.lock` hashes, and re-vet on upgrade.

## Install / uninstall

Run from `jurasolutions/repos/growth`. This pulls in mdurl 0.1.2:

```
uv add "markdown-it-py==4.2.0"
uv remove markdown-it-py
```

For crew: leave it out. This is a jura-growth runtime dependency, not a crew skill.
