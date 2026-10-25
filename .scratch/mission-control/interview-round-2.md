# Mission control — interview round 2

Round 1 decisions are in `crew-log.md` ("conductor (G0, interview round 1)"). Ting Yu has delegated
these six to the crew. Each has the conductor's recommendation; the tech lead decides.

**Q8 — How the server runs.** (a) On demand: `jura-growth mission-control` starts it and opens the
browser; closing the terminal stops it. (b) Always on: a launchd job (installed like the others,
KeepAlive) starts it at login, so a bookmark to `http://127.0.0.1:<port>` always works.
Recommendation: (b) plus (a), with a fixed port in `settings.yaml`.

**Q9 — Refresh.** Home and any page of a run still `running` reload every 60 seconds; finished
run pages don't. Recommendation: yes.

**Q10 — Fonts.** `design-system/styles.css` loads Outfit, DM Sans and IBM Plex Mono from Google
Fonts. Allow that for the page shell, never inside the email viewer. Recommendation: yes (the skill
scout says the same, `scout/baseline-and-rejected.md`).

**Q11 — App PRDs.** (a) Add `markdown-it-py` in its `js-default` mode as the one new dependency
(scout card `scout/markdown-it-py.md`), or (b) show PRDs as preformatted text with no new
dependency. Recommendation: (a).

**Q12 — Redaction.** Transcripts and event payloads written before ticket 01 lands could hold a
leaked secret. Mission control replaces configured secret values and common token shapes with
`[redacted]` before display, reusing the redaction ticket 01 adds
(`../growth-blocker-fixes/issues/01-headless-runs-keep-secrets-and-human-steps.md`).
Recommendation: yes.

**Q13 — Width.** The design system says mobile-first, test at 360px. Mission control is only ever
seen on this Mac. Recommendation: lay it out for a desktop window, but nothing breaks down to 360px,
44px targets, tokens only, white first and green sparingly.
