# Code review 04: BP-04, Instagram and LinkedIn in the publish job

- **Branch:** `crew/browser-publishing-04-instagram-linkedin` at f18ceca (29f6fb6, 379bb40, dc0b4f0, 5399b23, f18ceca), compared with its merge-base b4f0895, the head of `crew/mission-control`. `git merge-tree` is clean against `crew/mission-control` (a fast-forward), `crew/browser-publishing-06-joins-as-the-page` (3cc8967) and `crew/browser-publishing-07-fixture-platform` (ff55fa4).
- **Ticket:** `.scratch/browser-publishing/issues/04-instagram-and-linkedin.md`. **Spec:** `prd/pending/prd-jura-browser-publishing-2026-10-25.md` §2 (SC1, SC7, SC9, SC11), §4.2, §4.3, §4.6, §4.7, §6 Q1. **Tests:** test strategy v3, the BP-04 rows (§4.2, §7, §11.2). **Lessons:** `reviews/code-review-03.md`.
- **Reviewed:** 2026-10-27. I read every changed file: `docs/social.md`, `audit.py`, `hosts.py`, `prompts/publish.md`, `tests/publish_fake.py` and the five changed test files. For context I also read `job.py`, `scope.py`, `kinds.read_social`, `claim._copy_images`, `settings.py` (identities and `page_url`), `config/social.yaml`, and the 06 and 07 diffs to the same modules.

## Verdict: changes-requested

One finding blocks: **B1**. With more than one platform in `browser` mode, the audit accepts every enabled platform's hosts for whatever item was claimed. So a run that claimed an approved Instagram carousel can post it on the LinkedIn company page, record it as done with an Instagram address, and finish `ok`, with no alert and no pause. BP-04 is the change that makes this possible: while only Facebook could be driven, the enabled hosts and the item's hosts were the same list.

The rest of the branch is sound. The host lists are exact. The carousel is handed out slide for slide and audited for order. Both identities stop before typing in the S10 runs. Every round-3 BP-03 protection still holds for the new platforms.

## Evidence

- **Full suite** in the developer worktree at f18ceca. Setup: `JURA_ROOT` set, temp data and outputs folders, the fake `claude`, the Discord double and no Chrome. `uv run --frozen pytest -p no:cacheprovider -o addopts="" -q -rs` printed **3015 passed in 114.28s**, 0 skipped. The worktree is still clean afterwards.
- **Pyright** (standards reviewer): `audit.py` and `hosts.py` 0 errors. `tests/test_publish_instagram_linkedin.py` adds 16 (nit N2).
- **Blocked paths:** `git diff --name-only b4f0895...` shows nothing under `inputs/`, `design-system/`, `.env` or the live `data/growth/`.
- **`repro_04.py`** calls `audit.audit` with `hosts` set to all three platforms' browser hosts, which is what `scope.browser_hosts()` returns with all three in `browser` mode. It printed:

  | Case | Result |
  |---|---|
  | Instagram item claimed; its caption typed and posted on `www.linkedin.com/company/…`, then `publish stopped` | `failures=[]` |
  | Instagram item claimed; caption and all three slides posted on the Facebook Page | `failures=[]` |
  | Carousel: slides 1 and 2 uploaded, slide 3's `file_upload` **errored**, then `publish done --url` | `failures=[]` |
  | The same, with slide 3's upload **denied** | `failures=[]` |
  | Clean three-slide carousel (control) | `failures=[]` |
  | `l.instagram.com`, `sg.linkedin.com`, `lnkd.in`, `www.instagram.com.evil.test`, `www.threads.net`, `www.microsoft.com`, `login.microsoftonline.com`, `scontent.cdninstagram.com`, `help.instagram.com`, `www.linkedin.com@evil.test` | all refused, both by `hosts.problem` and by the audit |

- **`test_zz_review_04.py`**, whole runs through `runner.run("publish")` with the fake `claude`. It runs from a scratch copy of `tests/`, so the worktree is untouched.

  | Case | Result |
  |---|---|
  | B1: all three platforms in `browser` mode, an Instagram carousel claimed, its caption posted on the LinkedIn company page, `publish stopped --reason unidentified` | argv carries all nine domain rules. Outcome `failed` **as a stop**, not an audit failure ("A-0001 stopped in run 1: unidentified …") |
  | **B1b:** the same, but slides and caption posted on LinkedIn, then `publish done --url https://www.instagram.com/jura-test-page` (the profile, not a post) | **`status=ok`, item `done`, `live_text_matches=1`, no alert, not paused** |
  | S1: slide 3's upload errors, the post is recorded as done | **`status=ok`, item `done`, not paused** |

## Standards

### Should fix

None.

### Nits

- **N1. Misleading name and message** (`audit.py:151-152`, `:231`). `posted` is set by any `publish done --url` call, including one that failed. Yet the finding says "the post was recorded as done with N of M …", and `docs/social.md:311` says "a post recorded as done". Rename it to `attempted_done`, or reword the message.
- **N2. 16 new pyright errors** in `tests/test_publish_instagram_linkedin.py:124-244`. They are Optional access on `pw.approved(...)` results and `json.loads(db.scalar(...))`. `docs/agents/crew.md` says "don't add new errors in files you touch". The older publish tests have the same pattern, so this is advisory; `assert x is not None` clears it.
- **N3. Duplicated test data.** `slides()` is in both `test_publish_instagram_linkedin.py:119` and `test_publish_run_instagram_linkedin.py:41`. `THURSDAY` is defined in both files. `IG_POST` is in `test_publish_audit.py:192` and the run test. Move them into `publish_world.py`, beside `pw.INSTAGRAM_URL`.
- **N4. Dead bindings.** The run test for out-of-order slides unpacks `found, approval = instagram` and uses neither.
- **N5. Possible data clump** (`audit.py:122-124`). `order`, `uploads = set(order)` and `sent` are three loose locals for one concern, and `uploads` repeats `order`. `_Fields` beside them shows the pattern.
- **N6. Possible shotgun surgery.** The host lists now live in `hosts.py`, in a prose table in `docs/social.md` and in the argv test. The test copy is a fair independent oracle. The docs table will drift; consider pointing at `hosts.BROWSER_HOSTS` instead.

## Spec

### Blocking

- **B1. A run can post one platform's approved item on another enabled platform, and the audit passes it.**
  - **Where:** `jura_growth/agents/publish/job.py` `_audit` passes `hosts=scope.browser_hosts()`, the hosts of every enabled platform. It should pass the hosts of the platform of the item the run claimed. The domain rules have to be the enabled union, because they are set before the claim. A run claims at most one item (`caps.PUBLISH_ITEMS_PER_RUN = 1`), so the audit is the only place the item's own platform can be enforced, and it doesn't.
  - **What follows:**
    - The caption is approved text, typed once into one field, so the typing check passes.
    - The slides are the claim's own copies, in order, so the upload check passes.
    - Every tab address is on an enabled host, so the host check passes.
    - In B1b, `publish done` takes the Instagram profile address (host-only check, S4) and the live text the run wrote. The run ends `ok` with no alert and no pause, while an unapproved post sits on the LinkedIn company page. A prompt injection in an Instagram comment, or plain model confusion, is enough to start it.
  - **Rules it breaks:**
    - PRD §4.2: "An approval covers one publish item with fixed content. Any change to the text, images, destination, posting identity … makes a new item that needs a new approval."
    - SC2: "No approval, no action".
    - AC-P9.3: the audit fails "a foreign URL". The ticket's AC-P7.2 row: hosts "accepted **for their own items**".
    - The brief's check that no rule reaches "other Meta or Microsoft hosts": an Instagram run reaches the Facebook hosts.
  - **Fix:**
    1. Audit against the hosts of the claimed items' platforms. Keep the enabled union only for a run that claimed nothing, where typing and uploads already fail.
    2. Go through a `scope` helper (for example `scope.browser_hosts(platforms=…)`), so 07's fixture override (`fixture.active()`) still replaces the real hosts. 07 changes the same `_audit` line, so expect a conflict at merge and coordinate.
    3. Add audit rows and a fake-claude run: an Instagram item claimed with its tab on `www.linkedin.com`, then on `www.facebook.com`, must fail and pause.

### Should fix

- **S1. A failed or denied `file_upload` counts as a slide sent, so a carousel posted short passes.**
  - **Where:** `audit.py:182-191`. The upload bookkeeping runs before `if not call.ok: continue`, so `sent` takes the paths of an upload that errored or was denied. The "N of M approved images" check at `:230` then sees all three.
  - **Repro:** the S1 rows above. A whole run with slide 3's upload errored ends `ok`, the item is `done`, and nothing is paused.
  - **Rules it breaks:**
    - The audit docstring: "A run that went on to `publish done --url` must have sent every copy".
    - AC-P1.3: the approval covers "image bytes in order".
    - `docs/social.md:311`.
  - **Fix:**
    1. Keep the not-a-copy, repeat and order failures on every attempt.
    2. Add a path to `sent` only when the call succeeded.
    3. Add the errored and denied rows to the carousel table.
- **S2. `docs/social.md:205` records an undecided question as decided.**
  - It says weekends are "kept per BP §6 Q1".
  - PRD §6 Q1 says to keep weekends on "while only the Facebook Page is in `browser` mode … Decide again before Instagram and LinkedIn move to `browser` in BP-04". The ticket says "Question for Ting Yu before either platform moves to `browser`".
  - The only recorded answer is G2's "BP1 weekend posts kept" (`crew-log.md:50`), given for the Facebook-only case. Line 63 only says the question is "re-asked inside 04".
  - **Fix:** word it as open ("weekends are on; whether to keep them with three platforms in `browser` mode is Ting Yu's call before either moves") until he answers. See Questions.
- **S3. The new posting steps tell the run to click the upload button.**
  - **Where:** `prompts/publish.md`. The Instagram Post bullet says "click 'Create' … then 'Post', then 'Select from computer'". The LinkedIn bullet says attach "with the composer's media (photo) button".
  - Claude in Chrome's `file_upload` tool says not to click file-upload buttons, because that opens a native file picker the extension can't see or close. The tool wants the file input found with `find` or `read_page`, and its ref passed to `file_upload`.
  - As written, R1 is likely to stall on the picker. I couldn't reproduce this without Chrome; confirm it at R1.
  - Facebook's "attach the images with 'Photo/video'" (from 03) has the same shape and should get the same wording.
  - **Fix:** "find the composer's file input with `find`, then one `file_upload` with its ref; never click the upload button".
  - The same bullet asks for all slides "in one `file_upload` call". Five 1080×1350 PNGs may exceed the tool's per-call size limit. The audit already accepts uploads in several calls, in order, so let the prompt allow that too (N8).
- **S4. The post URL is checked by host only, so a profile address is recorded as the live post.**
  - **Where:** `publish done` (`hosts.problem`). In B1b, `https://www.instagram.com/jura-test-page` was recorded as the post URL.
  - The prompt names `https://www.instagram.com/p/<code>/` and `https://www.linkedin.com/feed/update/urn:li:activity:<n>/`, but code accepts any path. The AC-P7.2 accept table also takes `linkedin.com/posts/…-activity-…`, which the prompt never names. LinkedIn's "View post" can also land on `urn:li:share:` or `urn:li:ugcPost:`, and a model told one form may stop as `unidentified` on a valid post.
  - **Rules it breaks:** SC7, "Every post's live URL is recorded". The ticket's "their own live URL hosts".
  - **Fix:**
    1. Add a per-platform permalink shape to `hosts`: Instagram `/p/<code>/` (and `/reel/` if wanted); LinkedIn `/feed/update/urn:li:(activity|share|ugcPost):<n>/` and `/posts/…`. Refuse anything else in `done` and `resolve`.
    2. Name the same accepted forms in the prompt.
    3. Facebook's equivalent check is from 02a and is open to the same gap. Decide whether this ticket covers it.
- **S5. A LinkedIn company page and a personal profile look the same to code.**
  - `items.create_social` checks `page_url` only with `hosts.problem`, so `https://www.linkedin.com/in/<person>/` is accepted as the LinkedIn target. The posting identity is the free-text "the Jura Solutions LinkedIn company page".
  - AC-P11.1 then rests on the prompt alone, and the S10 tests script the stop, so they prove the plumbing, not the judgement. R6 is the only real check.
  - **Rules it breaks:** PRD §4.3, "Social posts go out as … the Jura LinkedIn company page". The prompt's own Target line: "an address on `www.linkedin.com` under `/company/`".
  - **Fix:** refuse a LinkedIn `page_url` whose path doesn't start with `/company/` when an item is made. Optionally also refuse an Instagram `page_url` that isn't a single-segment profile path.

### Nits

- **N7. Stop-signal bullets.** No platform bullet names `unidentified` (the general table covers it), and the Facebook bullet leaves out `warning`. The Facebook Stop signals bullet is new in 03's section. That is small scope creep, consistent with the rest; keep it.
- **N8.** The prompt's "one `file_upload` call" for a five-slide carousel: see S3.
- **N9. Host list choices, both defensible.**
  - No image CDN host is listed, which narrows PRD §4.7's example list ("the image CDN hosts"). Record it in the PRD's §4.7 or the ADR when U18 reports.
  - The domain rules include the bare `instagram.com` and `linkedin.com`. If U18 shows that a bare-domain rule covers subdomains, the permission reaches `*.instagram.com` and `*.linkedin.com`, though never another company's hosts. The audit's exact match is the backstop meanwhile.

## Security

The `security-review` skill's injected diff was taken from the wrong base: my own worktree's branch against `main`. So I worked through its method by hand on `b4f0895...crew/browser-publishing-04-instagram-linkedin`, with the repros above. The two review axes already used the brief's two-agent fan-out.

| Check | Result |
|---|---|
| Host rules exact, no wildcard | **Yes.** `HOSTS` and `BROWSER_HOSTS` list `www.` and bare hosts only. CDN, link-shim, short-link, help, country, Threads and Microsoft hosts are refused by `hosts.problem` and the audit (repro). argv has exactly one rule per host of each enabled platform, and none for a platform in `draft` mode (`test_publish_argv.py`). No Discord host. |
| Cross-platform reach within one run | **Not enforced** (B1, authorisation bypass of the per-item approval). Confidence 9: reproduced end to end. |
| LinkedIn company page vs personal profile | Prompt only (S5). The composer check and the never-switch rule are in the prompt, and the S10 stop path works for both platforms. |
| Instagram carousel order and caption bytes | `publish next` hands out every slide's checked bytes in order (`test_an_unchanged_carousel_is_handed_out_slide_for_slide_in_order`). A change in any slide's bytes or order supersedes (6 cases). Uploads out of order or repeated fail. A failed upload counts as sent (S1). The caption is judged whole per field against the approved text, after NFC and whitespace collapse, as in 03. |
| Round-3 BP-03 protections on the new platforms | **Hold.** `job.after_run` and `failed_closed` are unchanged and platform-agnostic. The trailing-tab-context parser is unchanged. The new audit code can't raise: `order[len(sent)]` is reached only for an unsent copy, so the index is in range, and the copies have distinct numbered paths. New findings name an image index and counts, never a path (asserted in `test_publish_audit.py` and in the run test). The wrong-identity alert and update never quote the page (asserted for both platforms). The JSON-bomb and checks-raise tests still pass in the 3015. |
| Secrets, SQL, subprocess, file paths | No new surface. `publish_fake.py` is test-only. |

## Blocked paths

None. The diff touches only `docs/`, `jura_growth/`, `prompts/` and `tests/`.

## Questions for Ting Yu

1. **Weekend posts with three platforms in `browser` mode (BP §6 Q1, asked again here).** With `weekends: true`, Saturday and Sunday bring up to three approval cards each. *Recommended:* keep weekends on. Switch to `weekends: false` (no weekend drafts on any platform) if three weekend cards prove too many. A per-platform weekend rule would be new scope.
