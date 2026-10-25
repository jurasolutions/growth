# Code review: ticket 02 (MC-02 redaction)

## Round 2 (fix round 1)

Branch `crew/mission-control-02-redaction` (26bb5da, a65c434, 7dd5034, e78da71, 6be40ed, 89f7285),
rebased onto `crew/mission-control` at 8bff848, which includes ticket 01. Compared with
`8bff848...`. Spec: `issues/02-redaction.md`; PRD §4.3, §4.4, SC11, SC12; test strategy v3.
Conductor ruling: Ting Yu's sender address appears only in `own_copy` previews. Line numbers are on
the branch.

### Verdict: changes-requested

There is one blocking finding, and the fix round introduced it. The `own_copy` exemption lets a
prospect's first name through the real outreach shadow preview, which runs every day. Both round 1
blocking findings are fixed.

### Evidence

- `uv run pytest` in the developer worktree: 1140 passed.
- The ticket files (`test_privacy`, `test_discord_redaction`, `test_discord_sweep`,
  `test_outreach_privacy`, `test_scout_leads`, `test_scout_contact*`): 191 passed.
- `git merge-tree` against `crew/mission-control`: clean. The README conflict is gone.
- Bypass script, run with a fake env file, a stub `config._keychain`, a `security` guard and the
  Discord double: results are quoted below. A scratch pytest file, loaded with the repo's
  `conftest` as a plug-in and kept outside the worktree, drove the real queue, send and shadow
  path. Nothing was posted, and the real Keychain, `.env` and live data were not read.

### Round 1 findings, rechecked

| Round 1 | Now |
|---|---|
| B1 names from the database | Fixed. `post()` calls `privacy.learn(conn)` (discord.py:165). The lead-reason reproduction is now masked, and a test covers it |
| B2 attachments | Fixed for text: content, names and outbox paths are masked. UTF-16 and other binaries are held back, and so is a PNG outside data or outputs. PNG is partly fixed: see S1 |
| S hash over the masked address | Fixed. `jane.tan@` and then `john.koh@` both delivered |
| S Ting Yu's address | Fixed per the ruling. It is `[removed]` outside `own_copy` |
| S phone shapes | Mostly fixed: dots, 2-2-2-2 and full-width are masked. See N1 |
| S two-letter names | Fixed. `Li Na`, `Wei Ng` and `Ng` are masked |
| S `%40` inside a URL | Fixed. The address becomes `j***%40example.com.sg` |
| S middle window of a secret | Fixed. `..uat_9Xq7Lm..` becomes `[redacted]` |
| S over-masking | Mostly fixed: multi-word company names are kept, `own_copy` is kept, and only reply lines of four words or more are registered. See S2 |
| S role list repeated | Fixed. `jura_growth/role_addresses.py` is shared, and `contact.kind_of` behaves as before |
| S README conflict | Fixed by the rebase |
| Standards nits | Fixed: docstrings, the `on_reset` type, the `_name_groups` name and a top-level import |

### Spec

**Blocking**

1. **The shadow preview shows a prospect's first name** (AC-M12.1: "a prospect's personal name
   planted in ... drafts ... none appears in Discord").
   - `send.py:402` passes `email.draft` as `own_copy`. Inside own copy, `privacy._mask` turns off
     single-name masking (`single_parts=not own`, privacy.py:193). Only a two-part name such as
     "Jane Tan" is still masked there.
   - The email brand channel doesn't drop a greeting by name yet. That is AC-M12.2, owned by
     MC-06.
   - Reproduced through the real path, with no hand seeding: lead contact
     `jane.tan@alderlogistics.sg`, body "Hi Jane,", then `queue.queue()` gave `queued` and
     `send.send_due()` posted `...\n\nHi Jane,\n\nI read on the Alder Logistics site...` to
     `#outreach-sent`.
   - In round 1 this was masked. `test_discord_sweep.py:158` still passes only because it doesn't
     pass the draft as `own_copy`.
   - Fix (recommended): inside own copy, still mask the name parts learned from named addresses.
     At least mask the parts of the recipient's own address, which the builder knows. Accept that
     "Mark your calendar" may read `[name removed]` in a preview until MC-06 drops drafts that
     name a person. Add a sweep test through `send.send_due` with "Hi Jane,".

**Should fix**

- **S1. A PNG carries any chunk except four text chunks.** `images.without_text_chunks`
  (images.py:22-25) removes `tEXt`, `iTXt`, `zTXt` and `eXIf` only.
  - Reproduced: a PNG in the data folder with a private `prVt` chunk holding
    `re_uat_9Xq7Lm2Pz Jane Tan +65 9123 4567` went to the double unchanged. Its file name was
    masked.
  - "Only images the engine made" (`_engine_file`, discord.py:105) is wider than it sounds. The
    data folder includes each job's `work/` folder, and community `image_path` comes from the
    agent's own submission (`community/plan.py:316`).
  - Fix: keep only the chunks pixels need (`IHDR`, `PLTE`, `IDAT`, `IEND`, `tRNS`, `gAMA`,
    `cHRM`, `sRGB`, `iCCP`, `pHYs`) and drop the rest.
- **S2. Jura's own copy can still lose Ting Yu's name.** When contacts such as `ting.lim@` and
  `yu.hui@` are known, "Thanks for reading. Ting Yu, Jura Solutions" in own copy became
  `Thanks for reading. [name removed], Jura Solutions`.
  - Community posts go out "as Ting Yu personally" (`config/community.yaml:24`).
  - Fix: protect the owner's name, `settings.SIGNATURE_NAME`, as the companies are protected.

**Nit**

- N1. These phone shapes still get through: `9123 45 67`, `9123–4567` (en dash) and
  `9 1 2 3 4 5 6 7` (privacy.py:67). The AC value `+65 9123 4567` is masked.
- N2. `post(None, ...)` learns nothing from the database. In a fresh process,
  `post(None, "alerts", "Jane Tan said no")` went out as written. Today no caller passes `None`,
  but MC-03's lock-skip run update will (`conn=None`), so it should build only from fields that
  hold no names.
- N3. A lower-case single name is never masked, by design: `spoke to jane yesterday` goes out
  unchanged.
- N4. A two-word lead name whitelists that name everywhere. A sole proprietor whose
  `display_name` is "Jane Tan" would leave "Jane Tan" unmasked. Company names are "Allowed" in
  §4.4, so this is recorded only.
- N5. `never_show` matches case-insensitively but needs the exact spacing:
  `PLEASE  take us off your list`, with two spaces, gets through.
- N6. An upper-cased secret (`RE_UAT_9XQ7LM2PZ`) gets through. Nothing changes a secret's case
  today.
- N7. `[at]` and full-width `＠` addresses keep their domain. The name is masked once it has been
  learned.

### Standards

**Blocking:** none.

**Nit**

- `agents/scout/__init__.py` has three blank lines before `privacy_terms`.
- `agents/outreach/__init__.py` `privacy_terms` imports the scout plug-in's settings. That is the
  same plug-in-to-plug-in pattern outreach already uses, so it is noted only.

### Security

The review was done inline, with no fan-out. There is no new SQL beyond static `SELECT`s, no new
subprocess input, and every regex built from data goes through `re.escape`. PNG parsing checks
bounds and returns `None` on a short chunk.

- **Medium, PII to a third party** (confidence 9). Blocking 1: a prospect's first name in
  `#outreach-sent`.
- **Low.** S1: a PNG side channel through agent-supplied images. Reaching it needs a model that
  can write binary files into its work folder.

### Blocked paths

None. The diff touches no file under `inputs/`, `design-system/`, `.env` or live `data/growth/`,
and neither `tests/conftest.py` nor `jura_growth/agents/__init__.py`.

### UI

No UI files changed.

---

## Round 1 (a96d0ae, on 8228152)

Branch `crew/mission-control-02-redaction` (ab95e76, 0265c9e, b9e098a, a96d0ae), compared with
`8228152...` . Spec: `issues/02-redaction.md`; PRD §4.3, §4.4, SC11, SC12; test strategy v3 §2, §3, §4.1.
Line numbers are on the branch.

### Round 1 verdict: changes-requested

Two blocking findings. Both are acceptance criteria this ticket owns, and both were reproduced
against the Discord double with fake secrets and a fake Keychain.

### Evidence

- `uv run pytest` in the developer worktree: 1053 passed.
- The five ticket test files (`test_privacy`, `test_discord_redaction`, `test_discord_sweep`,
  `test_outreach_reply_privacy`, `test_scout_leads`): 129 passed.
- Trial merge onto `crew/mission-control` (8bff848, which now includes ticket 01), done in a
  throwaway worktree: the only conflict is `README.md`, and `uv run pytest` gives 1108 passed
  with 01's network guard on. The worktree was removed afterwards.
- Bypass attempts used a scratch script, the Discord double, a temp env file and a stub
  `config._keychain`. A `subprocess.run` guard failed on any `security` call. Nothing was posted.
  Results are quoted under each finding.

### Standards

**Blocking:** none.

**Should fix**

- `jura_growth/privacy.py:44` `ROLE_LOCAL_PARTS` and `is_role_address()` repeat
  `agents/scout/contact.py` (`ENQUIRY_ROLES`, `OTHER_ROLES`, `NOT_FOR_ENQUIRIES`, and the base-strip
  rule in `kind_of`). This is a reuse finding: the test at `tests/test_privacy.py:145` only notices
  drift after it happens. Move the role vocabulary into a core module that both import. A plug-in
  may import core; core must not import a plug-in by name (README, plug-in interface).
- `README.md:165` and the end-of-file paragraph conflict with ticket 01's README edits, now on
  `crew/mission-control`. Rebase onto 8bff848 and keep both sets of rows.

**Nit**

- The docstrings of `config.load_secrets_for_masking` (config.py:178) and the `privacy` module
  name "the one-pager, run updates and approval cards" as callers. None of those exist yet. The
  real callers are `digest.run`, `discord.alert` and `discord post`.
- `discord.py:103-105` says "no Keychain lookup here", but `alert()` in the same module
  (discord.py:145) does Keychain lookups through `load_for_masking`. Say that `alert` is a
  builder.
- `config._reset_hooks: list` and `on_reset(forget)` are untyped. Use `list[Callable[[], None]]`.
- `privacy._people` holds name parts, not people. A name like `_name_parts_seen` would say what it
  holds.
- The lazy `from jura_growth import agents` at privacy.py:124 doesn't break any import cycle.
- `tests/sweep.py:135` `_secret_needles` and `config._encoded_forms` use different `quote_plus`
  and `json.dumps` arguments. That is right for a test oracle, but add a comment saying the
  difference is intended.

### Spec

**Blocking**

1. **Names leak from existing posts, because `post()` never learns the named contacts**
   (AC-M12.1: "a prospect's personal name planted in summaries ... none appears in Discord",
   which this ticket owns for existing posts).
   - `discord.post()` (discord.py:106) masks only the names it already knows.
     `privacy.remember_people(conn)` runs only through `load_for_masking`, which only `alert`,
     `digest.run` and `discord post` call.
   - These paths never learn the contacts: the scout lead post (`scout/leads.py:389`), the
     outreach shadow and live previews (`outreach/send.py:381`, through `store.post`), social
     submit, community (`community/__init__.py:384`, `plan.py:676`), the app factory, the
     heartbeat and pause-resume.
   - Reproduced: a lead whose contact is `jane.tan@example.com.sg` and whose top score reason says
     "Jane Tan, the director, still keys in every invoice". `leads._post_lead` sent
     `top reason: Jane Tan, the director, ...` to the double.
   - `tests/test_discord_sweep.py:161` seeds `privacy.remember_address` by hand, which hides the
     gap, and no sweep plants `PERSON` in a lead post or a draft.
   - Fix: `post()` calls `privacy.remember_people(conn)`, which reads the database and never the
     Keychain, so AC-M11.3 still holds. Add sweep tests that plant `PERSON` in a lead's reason and
     in a shadow draft, without seeding the name by hand.
2. **Attachments and their names are not masked** (AC-M11.1: "nor any 8-character piece of
   one, appears in any Discord payload, attachment or outbox file").
   - `post()` masks `content` and `username` only. `_send` uploads `file.name` and
     `file.read_bytes()` as they are (discord.py:170-171), and `_outbox` stores the raw paths
     (discord.py:227).
   - Reproduced: a file named `jane.tan@example.com.sg notes.txt`, holding both D2 secrets, the
     phone number and "Jane Tan", went to the double unchanged.
   - Fix: mask attachment names in the payload and in the outbox. Run text attachments through
     `for_discord`, or refuse anything that isn't an image. Add a sweep test with D2 and D3
     planted in an attachment.

**Should fix**

3. **The dedupe hash covers the masked address.** PRD §4.4 says "The content hash still covers
   the full address". AC-M11.3 asks only for `config.redact()` before the hash.
   - discord.py:106-108 hashes after the full `for_discord()`.
   - Reproduced: "Shadow draft to jane.tan@example.com.sg" and then "... john.koh@example.com.sg"
     on the same channel. The second was dropped as "already posted today".
   - Fix: hash `config.redact(content)` and send `for_discord(content)`.
4. **Ting Yu's own contact details are masked, not removed.** §4.4 puts them under "Never". The
   row at `tests/test_privacy.py:34` expects `Ting Yu: t***@jurasolutions.sg`, and nothing
   recognises his details. See question 1.
5. **Common phone shapes get through** (`privacy.py:62` `PHONE_RE`). Reproduced:
   `call 9123.4567`, `call 91 23 45 67` and full-width `９１２３ ４５６７` all came out unchanged.
   The sweep's own pattern (`sweep.py:149`) would flag the second, so a later ticket's sweep can
   trip on it.
6. **Short names and names with no matching address get through.**
   - `MIN_NAME_PART = 3` (privacy.py:68) drops Ng, Li, Ho, Oh and Yu, which are common surnames
     in the target market. Reproduced: `Li Na runs ops` came out unchanged, and `Wei Ng` became
     `[name removed] Ng`.
   - A name that doesn't appear in an address (contact `jt@...`, text "Jane Lim") isn't masked.
     This is partly inherent, but state it as a known limit in the module docstring.
7. **A named address with an encoded `@` inside a URL goes out whole.**
   `https://x.sg/?email=jane.tan%40example.com.sg` came out unchanged. `EMAIL_RE` doesn't treat
   `%40` as `@`, and `_outside_urls` (privacy.py:171) protects the URL. Decode `%40` and `&#64;`
   before matching addresses.
8. **A piece from the middle of a secret is not masked.** The AC says "any 8-character piece".
   `_pieces_pattern` (config.py:273) masks only prefixes and suffixes. Reproduced:
   `..uat_9Xq7Lm..` came out unchanged. Mask every window of 8 or more characters of each token.
9. **Allowed content gets masked.** §4.4 allows company names and "the text ... of Jura's own
   outgoing posts and emails", and says "an email preview is exact".
   - Once the contacts are loaded, `Mark your calendar, Tan Holdings Pte Ltd` became
     `[name removed] your calendar, [name removed] Holdings Pte Ltd`.
   - `replies.py:184` registers every reply line of 8 or more characters, so lines such as
     "Best regards" or "Thank you for" are removed, case-insensitively, from every later post in
     that process.
   - Fixing finding 1 widens this, and approval-card previews (04b, 06) will feel it. Limit name
     masking to text that isn't Jura's own outgoing copy, or exempt the learned company names.

**Nit**

- `FINANCE_LINE_RE` (privacy.py:66) misses `personalfinance` and `personal%2Dfinance`.
- An address that starts with `_` is not recognised: `_jane.tan@example.com.sg` became
  `_jane.[name removed]@example.com.sg`.
- `sweep.PERSONAL` (sweep.py:51) leaves out the reply text, Ting Yu's details and
  `personal-finance` from dataset D3. Those are covered only by unit rows.
- Not scope creep: the `named_addresses` hook and the encoded-form and piece masking in
  `redact()` are what AC-M11.1 and AC-M12.1 need. The masked lead wording at `leads.py:378`
  follows §4.4.

### Security

The review was done inline: the fan-out budget went on the two review axes. There is no new SQL
(the `named_addresses` query is static), no new subprocess input (Keychain service names come
from env and `.env`, which are trusted), and every regex built from data uses `re.escape`.

- **Medium, PII exposure to a third party** (confidence 9). Blocking finding 1: prospects' names
  reach Discord, a service outside Singapore, from the daily scout lead posts and outreach
  previews.
- **Medium, secret and PII exposure through attachments** (confidence 8). Blocking finding 2.
  Today's callers attach rendered images, and `discord` is refused to agents (`headless.NEVER`).
  The exposure is the human CLI `--file` and any later builder that attaches text.
- **Low.** A hostile reply can register strings that blank parts of later posts in the
  reply-check process (`replies.py:168,184`). That is an integrity problem, not a leak.

### Blocked paths

None. The diff touches no file under `inputs/`, `design-system/`, `.env` or live `data/growth/`,
and neither `tests/conftest.py` nor `jura_growth/agents/__init__.py`, which ticket 01 owns.

### UI

No UI files changed, so no web design review was needed.

### Questions for Ting Yu

1. Does "Ting Yu's own contact details" (§4.4, "Never") include the outreach sender
   `tingyu@jurasolutions.sg`, which is part of Jura's own outgoing email (§4.4, "Allowed")?
   **Recommended:** remove his phone number and any address other than the published sender.
   Keep `tingyu@jurasolutions.sg` as written in previews of Jura's own email, and remove it
   everywhere else.
