# Risk card: diagram-design

| | |
|---|---|
| **Verdict** | don't recommend |
| **Risk** | Medium, provisional (scanner floor: Medium). The review stopped on fit, so this is not a clearance |
| **Source** | cathrynlavery/diagram-design @ 0cf73c3fcc56667ad91a9a04c439ac6ccfabc9d1 (2.6.136), path skills/diagram-design plus commands/ |
| **Maintainer** | Cathryn Lavery (LittleMight), an individual. Active repo created 2026-04-16, last push 2026-10-27, 409 commits, about 63k stars, 50 open issues, none about security in a keyword search. Not listed in the Anthropic official catalog |
| **Licence** | MIT; vendorable: yes |
| **Kind** | plugin: 7 skills, of which 6 are slash commands. No agents, hooks, MCP or LSP servers |
| **Always-on cost** | ~600 tokens every session; ~11.3k tokens each time the main skill fires |
| **Vetted** | 2026-10-31, by crew:skill-scout |

## What it does

It teaches an agent to hand-write self-contained HTML and inline SVG diagrams in 45 types, in its own editorial style. It can export them to SVG and PNG, and it can redraw draw.io, Mermaid and Excalidraw files.

## Gain for this task

None beyond what the branch already has. `jura_growth/agents/social/visuals.py` draws the three kinds PRD PC1 asks for (flow, compare, figure) from a checked JSON spec, using design-system tokens, an allow-listed set of Lucide icons, the repo's own Chrome renderer and the `social-card` brand check. That is a narrower tool, and it should be: the agent cannot get a card wrong in layout, colour or font.

This skill goes the other way, in four ways that matter here:

- The agent would write free-form SVG, so the words on a picture no longer pass through `CardSpec.body()` and PC2's brand check has a hole.
- Its default look (Instrument Serif, Geist, a coral accent) is a second type and colour set, which `jurasolutions/CLAUDE.md` forbids. Its skinning system could copy Jura's tokens in, but that keeps a parallel copy of a read-only design system.
- Its export needs Playwright and its own Chromium. The repo's fixed-size Chrome render does this job and checks the PNG's size.
- It would not reach the scheduled run at all. `runner.py` starts the job with `--setting-sources project` and `--permission-mode dontAsk`, and `config/settings.yaml` gives it only WebSearch and WebFetch. I read those flags and did not test them.

For a developer designing a fourth visual kind later, its taste rules are good reading (a target density, one or two focal elements, "would a paragraph do?"). The live ticket needs none of that, and `frontend-design` plus the design system already cover the work.

## Files reviewed

The footprint is 290 files in `skills/diagram-design` plus 6 in `commands/`. **I did not read every file.** Once the candidate failed on fit, a full read of 63 references and 220 HTML templates would not change the verdict. Anyone reopening this must finish that read first.

Read in full:

- `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`: manifest only, no hooks or servers
- `skills/diagram-design/scripts/export_png.py`: launches Playwright Chromium on a local file, screenshots the first SVG
- `commands/export-diagram.md`: says not to auto-install Playwright
- `PRIVACY.md` (first 30 lines): states no server and no telemetry, and names Google Fonts as the one outside recipient

Read in part:

- `skills/diagram-design/SKILL.md`: sections 0 to 10 read, sections 11 and 12 only by heading
- `skills/diagram-design/references/profiles.md`: lines matching paths and writes. It writes profiles to `~/.diagram-design/profiles/` and reads a project `.diagram-design` marker, which it treats as untrusted
- `skills/diagram-design/references/export.md`: lines matching Playwright
- `commands/doctor.md`, `import-drawio.md`, `import-excalidraw.md`, `import-mermaid.md`, `profile.md`: front matter, opening lines and lines matching Bash, curl, http or install. All declare Bash, and all but `doctor.md` also declare Write and Edit
- `skills/diagram-design/scripts/export_svg.py`: lines 25 to 45 and its imports

Checked by pattern only, not read:

- `scripts/drawio_extract.py`, `excalidraw_extract.py`, `mermaid_extract.py`, `self_check.py`: imports are standard library. No `subprocess`, `socket`, `requests`, `eval` or `exec`. `base64` and `zlib` in `drawio_extract.py` decode draw.io's own format
- `references/*.md` (other than the two above) and `assets/*.html`: searched for injection phrases, secret paths and install commands (no hits), for hidden Unicode (no files), and for external hosts (only fonts.googleapis.com, w3.org, purl.org, github.com, example.com, tabler.io and simpleicons.org). 12 HTML files have inline scripts; none uses `fetch`, XHR, `sendBeacon`, WebSocket, cookies, `localStorage` or `eval`, and none loads a script from elsewhere

## Red flags

- `network-call`, medium: `skills/diagram-design/scripts/export_svg.py:35`. A Google Fonts `@import` string written into exported SVGs. Bounded and disclosed in `PRIVACY.md`, but each render of a default diagram would call Google. The repo's own render has an offline mode.
- `telemetry`, medium, 24 hits in `assets/example-ridgeline*.html`, `assets/example-sequence*.html` and `references/type-line.md`. The ridgeline hits are the charting word "amplitude", and the sequence hits are an example diagram that draws an "analytics beacon". Neither is code that sends anything, but both keep the floor at Medium.

- `broad-tools`, medium, 6 hits: line 4 of every file in `commands/`. Each declares Bash, and all but `doctor.md` also declare Write and Edit. A separate floor of Medium.

No instruction aimed at a reviewer or agent was found in the parts read or searched.

## Notes

- Footprint scan of `skills/`: 290 files, 25 medium, 225 info, floor Medium. The info hits are mostly the font link in each template. `commands/`: 6 files, 6 medium, no high.
- Whole-clone scan, for context and not the floor: 695 files, 11 high, 135 medium. Ten highs are `IGNORE ALL PREVIOUS INSTRUCTIONS` strings in `scripts/fixtures/` and `scripts/verify-*-import.py`, plus `scripts/test-install-scan.py`, which look like adversarial test data for the import and install checks. The eleventh is an error message at `.github/workflows/auto-bump.yml:220`. I read these lines only as the scanner printed them. A marketplace install copies these files to disk, though the manifest doesn't load them.
- skills.sh audits, corroboration only: Socket pass, Snyk pass (low). Gen Agent Trust Hub says pass with the summary "AI Analysis failed", so count that one as no result.
- The on-disk clone is 68 MB, and `.github/` and `docs/` hold many screenshots.
- Layout engines (Mermaid CLI, D2) were considered without a clone: no layout problem exists for three to four boxes in a row, they would add a runtime, and their theming sits outside the design system.

## Conditions of use

If this is ever reopened: finish the file read, use it only for a developer's interactive design work, skill only, pinned to this commit, and never for anything rendered onto a Jura card.

## Install / uninstall

Nothing to install. For the record, a pinned install a human could run:

```
git clone https://github.com/cathrynlavery/diagram-design.git ~/plugins-pinned/diagram-design
git -C ~/plugins-pinned/diagram-design checkout 0cf73c3fcc56667ad91a9a04c439ac6ccfabc9d1
claude plugin marketplace add ~/plugins-pinned/diagram-design
claude plugin install diagram-design@diagram-design

claude plugin uninstall diagram-design@diagram-design
claude plugin marketplace remove diagram-design
```

For crew: leave it out.
