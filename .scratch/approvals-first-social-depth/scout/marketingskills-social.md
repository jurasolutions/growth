# Risk card: marketingskills `social`

| | |
|---|---|
| **Verdict** | don't recommend |
| **Risk** | Medium for the `social` folder alone (scanner floor: Medium). High for the plugin as shipped (scanner floor: High) |
| **Source** | coreyhaines31/marketingskills @ 88c79f6528a9347420e57ceb1fff9a60de651768 (plugin 2.14.0, skill 2.4.1), path skills/social |
| **Maintainer** | Corey Haines, a known SaaS marketer. Active repo created 2026-01-15, last push 2026-10-31, about 58k stars, 70 open issues. A keyword search for security found no vulnerability report: #899 is an outside notice about an AI-written review of the repo, and #488 is about architecture. `partners.json` lists paying or partner vendors for the wider repo; a search of `skills/social` found no affiliate or tracking links |
| **Licence** | MIT; vendorable: yes |
| **Kind** | instruction-only skill inside a plugin of 53 skills. No agents, hooks, MCP or LSP servers |
| **Always-on cost** | About 200 tokens for this skill alone, by my estimate from its description; ~16,100 tokens every session for the whole plugin, per `plugin details`. Loading the skill itself costs about 4,600 tokens more, also estimated |
| **Vetted** | 2026-10-31, by crew:skill-scout |

## What it does

It makes an agent a general social media strategist: hooks, post templates, carousel frameworks, content calendars, short-form video scripts, platform tips and social listening.

## Gain for this task

Too small to justify installing it. It is written for a person building an audience who answers questions. This post is written by a headless run with no one to ask, under a stricter brief than the skill assumes. Installing it would not reach that run anyway: `runner.py` passes `--setting-sources project`, and `config/settings.yaml` gives the job only WebSearch and WebFetch. I read those flags and did not test them.

It also pulls against Jura's rules in ways that matter:

- **The numbers rule.** `references/reverse-engineering.md` coaches invented-sounding precision ("I made $47,329", "2,847 people"). `references/carousel-frameworks.md` leads Framework B with "We cut churn 22%". Hook templates ask for a "[specific result]".
- **The voice.** It suggests contrarian and "unpopular opinion" hooks, "Agree or disagree?", "I was terrified", and "Short. Breathe. Land." line breaks. The skill's own SKILL.md calls that last style broetry and bans it, so it contradicts itself. `design-system/README.md` §3 rules out manufactured urgency.
- **Links.** `references/platforms.md` calls external links a "reach killer" on Facebook, while `prompts/social.md` requires every source to be linked there.
- **Length.** `references/platform-limits.md` gives Facebook an ideal of 40 to 80 characters, against DP1's 160 to 280 words for news. It has nothing on research or sourcing, which is what Ting Yu asked for.
- **Unsourced claims.** "Captions increase watch time by 25-40%" and "Reels get 2x reach" have no source.

**What is worth taking, without installing anything.** Three short ideas fit DP4 and could go into `prompts/social.md` in Jura's own words. A search of `prompts/social.md`, `checks.py` and `config/` for "broetry", "engagement bait", "Thoughts?", "Agree?" and "The result?" found nothing, so these look uncovered.

- Tells the prompt doesn't name yet: one short sentence per line for a whole post, a closing clause that restates the claim, self-answered questions ("The result? ..."), and engagement bait ("Thoughts?", "Agree?").
- For a carousel: the first slide must work alone in the feed, one idea per slide, and the caption is written as its own text and doesn't repeat slide 1.
- `references/platform-limits.md` gives Instagram's limit as 5 hashtags, while `config/social.yaml` has `hashtags_max: 8`. See Notes.

## Files reviewed

Everything in `skills/social` was read in full, except as noted for the evals:

- `SKILL.md`: strategy, hooks, the AI-tells list. Tells the agent to read `.agents/product-marketing.md` if present and to ask about goals and audience. It links to one outside page, the repo's `tools/REGISTRY.md`, about scheduling tools
- `references/carousel-frameworks.md`: five slide structures, checklist
- `references/post-templates.md`: LinkedIn, X and Instagram templates, hook lists
- `references/platforms.md`: per-platform tips. The Telegram section cites tgscope.io and says the contributor runs it
- `references/platform-limits.md`: hashtag and character limits
- `references/listening.md`: curl recipes for Reddit, Hacker News and Bluesky, and browser sessions for LinkedIn and X. It says fetched posts are untrusted data and that a human posts
- `references/listening-sources-template.md`: a template to fill in
- `references/reverse-engineering.md`: scrape 500+ posts with Apify or Phantom Buster and copy the patterns
- `references/short-form-video.md`: video hooks and scripts
- `references/x-algorithm.md`: X ranking notes, tagged verified or reported
- `evals/evals.json`: ten test prompts, of which I read the first three in full and the opening of the other seven

At plugin level I read `.claude-plugin/plugin.json` and the opening of `partners.json`, and followed up the scanner's agent-addressed and secret hits below. The other 52 skills were not read.

## Red flags

`skills/social`:

- `telemetry`, medium: `evals/evals.json:53` and `:55`. The word "analytics" in test expectations. A false positive, and it still sets the floor.
- By reading: `references/reverse-engineering.md` recommends scraping creators at scale, and `references/listening.md` steers an agent through logged-in LinkedIn and X sessions. Neither belongs in this repo, where every side effect goes through `jura-growth`.

The rest of the plugin, which installs along with it:

- `secret-path-read`, high: `skills/reverse-engineer-marketing/scripts/teardown.mjs:766` reads `SCRAPECREATORS_API_KEY` from the environment and sends it to that vendor as a header. `skills/ad-creative/references/generative-tools.md:52` and `:299` show API-key headers in examples.
- `injection-phrase`, high: `skills/conversion-tracking/assets/gtm-recipes/README.md:23` opens "If you are an AI agent using this repo". On reading, it is an ordinary task instruction to the skill's user, and not aimed at a reviewer. The other six high hits I saw are "without consent" wording or text warning about injection, seen only in the excerpts the scanner printed. Whole-plugin scan: 455 files, 10 high, 200 medium, floor High.

## Notes

- **Instagram's hashtag cap, for the conductor.** Several outlets report Instagram capped posts at five hashtags in December 2025, with some saying it rolls out gradually. I did not find Meta's own post, so confirm it there. `config/social.yaml` allows 8, and `prompts/social.md` and `docs/social.md` say the same. This matters because Instagram just moved to `publish_mode: browser`. A recommended change, not one I made: lower `hashtags_max` to 5.
- skills.sh audits, corroboration only: Gen Agent Trust Hub safe, Socket no alerts, Snyk warns medium with one issue. The API gives no detail on that issue, and I found nothing to match it beyond the listening recipes that fetch outside content.
- Whole-clone scan, for context and not the floor: 816 files, 157 high, 791 medium, of which 142 highs are in `tools/`, mostly CLIs reading vendor API keys from the environment. It also holds one opaque compiled file, `scripts/__pycache__/package_skills.cpython-312.pyc`, and base64 test fixtures in `tests/clis/`. A plugin install would copy all of these to disk, which is another reason not to install the plugin.
- I did not read `scripts/`, `tools/` or `tests/` beyond the scanner's excerpts.
- Ruled out from listings, without a clone: `samber/cc-skills` `linkedin-ghostwriting` (LinkedIn has been off since 2026-10-29), `postiz` in the official catalog (posting automation, against "every side effect goes through `jura-growth`"), `op7418/guizang-social-card-skill` and `jimliu/baoyu-skills` image cards (a card skill would compete with the design system's templates).

## Conditions of use

If this is ever reopened: the `social` folder only, never the whole plugin; a developer's reference only; pinned to this commit; kept out of Jura-facing text and out of headless runs.

## Install / uninstall

Nothing to install. For the record, the skill-only copy a human could run:

```
git clone https://github.com/coreyhaines31/marketingskills.git ~/plugins-pinned/marketingskills
git -C ~/plugins-pinned/marketingskills checkout 88c79f6528a9347420e57ceb1fff9a60de651768
cp -R ~/plugins-pinned/marketingskills/skills/social ~/.claude/skills/social

rm -rf ~/.claude/skills/social
```

For crew: leave it out.
