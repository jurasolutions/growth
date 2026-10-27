# Risk card: Jinja2 (with MarkupSafe)

| | |
|---|---|
| **Verdict** | don't recommend |
| **Risk** | High (scanner floor: High) |
| **Source** | pallets/jinja @ 15206881c006c79667fe5154fe80c01c65410679 (3.1.6), path `src/jinja2/`; its dependency pallets/markupsafe @ ece26078ec168ebac69f02877238e68d4b376c91 (3.0.4), path `src/markupsafe/` |
| **Maintainer** | Pallets, the Flask maintainers, led by David Lord. Jinja dates from 2008 and the repo from 2010 (11.8k stars). Both wheels are published through GitHub trusted publishing and carry PyPI attestations (`pallets/jinja` and `pallets/markupsafe`, workflow `publish.yaml`). Highly credible |
| **Licence** | BSD-3-Clause (both); vendorable: yes |
| **Kind** | Python library (runtime dependency) |
| **Always-on cost** | 0 tokens |
| **Vetted** | 2026-10-24, by crew:skill-scout |

## What it does

Jinja2 is a template engine. It compiles template files to Python code and runs that code. MarkupSafe supplies the `Markup` string type and HTML escaping. With autoescaping on, every `{{ value }}` is escaped unless it's explicitly marked safe.

## Gain for this task

Jinja2 offers escape-by-default and template inheritance: one layout shared by about eight views. That gain is real but small here, because the repo already does HTML templating with the standard library:

- `jura_growth/agents/outreach/compose.py` builds every outreach email's HTML with `html.escape`.
- `jura_growth/agents/social/render.py` has `_fill`, a ten-line filler that escapes `{{name}}` and leaves `{{{name}}}` raw.

Extending that pattern into a small escape-by-default helper (see `baseline-and-rejected.md`) gives the same property with no new dependency. MarkupSafe's own pure-Python escape, `_native.py`, is five `str.replace` calls, the same work as `html.escape(s, quote=True)`.

## Files reviewed

Shipped footprint, checked against PyPI's sha256:

- `jinja2-3.1.6-py3-none-any.whl` (sha256 `85ece4451f492d0c13c5dd7c13a64681a86afae63a5f347908daf103ce6d2f67`): 25 Python files, 14,425 lines, byte-identical to `src/jinja2/` at the tag.
- `markupsafe-3.0.4-cp312-cp312-macosx_11_0_arm64.whl` (sha256 `0930db9bdc62d22944e10b066448bb65dc9abe9112880c7cab8da54db4284d5f`): identical to `src/markupsafe/` at the tag, plus the compiled `_speedups.cpython-312-darwin.so`.

Read in full:

- `_identifier.py`, parsed with `ast` rather than imported: `import re` plus a single `re.compile` of a 694-character Unicode class (the lexer's identifier pattern).
- `defaults.py`.
- `loaders.py` `split_template_path`, which rejects `..` and path separators.
- `utils.py` `select_autoescape`.
- The compile and run path: `environment.py:1228` (`exec`) and `debug.py:145` (traceback rewriting).
- `bccache.py`, which is opt-in. It uses pickle and marshal against a cache folder only when you configure a bytecode cache.
- `markupsafe/__init__.py`, `_native.py` and `_speedups.c` (200 lines).

The remaining ~12,000 lines (compiler, parser, lexer, runtime, filters, ext, sandbox) were reviewed by import and call inventory, not line by line. Every import is from the standard library. There is no socket, subprocess or HTTP use, and no network calls.

## Red flags

Scanner, shipped footprint:

- **High `obfuscation`, `jinja2/_identifier.py:5`.** This is the generated Unicode identifier regex. Reading accounts for it (see above), but the floor stands.
- **High `opaque-file`, `markupsafe/_speedups.cpython-312-darwin.so` (50,656 bytes).** This is a compiled C extension and can't be read. Its source, `_speedups.c`, ships alongside it, but only the attestation ties the binary to that source. MarkupSafe 3.0.4 publishes no pure-Python wheel, only the sdist and platform wheels.
- **Medium `network-call` ×3.** All are documentation URLs: `bccache.py:339`, `bccache.py:340`, `filters.py:1035`.

By reading:

- **Autoescape is off by default.** `Environment(autoescape=False)` is the default at `environment.py:312`, and `Template` defaults the same way at `environment.py:1186`. One missed `autoescape=True` turns every view into an XSS sink for scraped and model-written text.
- **Templates compile to Python and run through `exec`.** That is by design, and safe only while templates are trusted repo files. A template built from data (`from_string` on model or scraped text) is code execution.

## Notes

- Advisory history: 10 CVEs. The recent ones are CVE-2025-27516 (sandbox `|attr` bypass), CVE-2024-56326 and CVE-2024-56201 (sandbox breakouts), and CVE-2024-22195 and CVE-2024-34064 (`xmlattr` XSS). All are fixed in 3.1.6. OSV lists none affecting 3.1.6 or MarkupSafe 3.0.4 (checked 2026-10-24). The sandbox issues matter only when attackers control template source. The `xmlattr` issues matter when untrusted keys reach `|xmlattr`.
- 3.1.6 is from 2025-03-05, and the jinja repo was last pushed on 2025-06-14.
- Whole-clone scan, outside the footprint:
  - `tests/res/package.zip`: opaque, a loader test fixture.
  - `tests/test_loader.py:164`: an encoded test string.
  - 12 `network-call` hits in `docs/` and `scripts/`.
  - In the MarkupSafe clone, `.devcontainer/on-create-command.sh:7` pipes the uv installer to `sh`. This runs in the dev container only and doesn't ship.
- Building MarkupSafe from source (`no-binary-package = ["markupsafe"]`) would replace the opaque `.so` with one compiled locally from the 200-line C file. The `_identifier.py` hit would still hold the floor at High.

## Conditions of use

These apply only if you choose to override this card:

- `Environment(loader=FileSystemLoader(<the package's templates folder>), autoescape=True, undefined=StrictUndefined)`.
- No `from_string` on data.
- `|safe` only on the markdown renderer's output.
- No `|xmlattr`, and no bytecode cache.
- Pinned to 3.1.6 and 3.0.4 through `uv.lock`.

## Install / uninstall

Not recommended. If you decide to take it anyway, run this from `jurasolutions/repos/growth`:

```
uv add "jinja2==3.1.6"
uv remove jinja2
```

For crew: leave it out.
