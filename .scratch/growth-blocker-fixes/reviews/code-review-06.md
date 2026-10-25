# Code review 06: a contact address must belong to the business

- **Branch:** `crew/growth-blocker-fixes-06-contact-domain` (b9485ea, 869a76d)
- **Fixed point:** `crew/growth-blocker-fixes` (01ce0e9), which is also the merge-base
- **Spec:** `issues/06-contact-address-belongs-to-business.md`, the G2 free-mail decision in `crew-log.md`, audit B5 in `audit/code-review-02-scout.md`, scout PRD §5.2 step 5 and success criterion 3
- **Files read:** `config/scout.yaml`, `docs/scout.md`, `jura_growth/agents/scout/contact.py`, `leads.py`, `settings.py`, `prompts/scout.md`, `tests/test_scout_leads.py`. That is every file in the diff. Line numbers below are from the worktree.

## Verdict: approve

There are no blocking findings. The branch does what the ticket's "What to change" section asks for, and it meets every acceptance criterion:

- F4 and F4b now fail on the branch, so the defect is gone. They pass on the base, so the defect was real. Both are kept as regression tests at `tests/test_scout_leads.py:62` and `:124`.
- Addresses on the company's own domain and on its subdomains are accepted.
- The six G2 free-mail providers are accepted. Other providers are refused.
- Config can shorten the provider list but never extend it.
- `uv run pytest` passes.

**B5 is only partly closed.** The rule now ties the address to the domain in the lead's `website` field. Nothing ties that domain to the company. A directory missing from the deny list therefore still passes as the company's own site in two cases: when the address on the listing is free mail, or when the address is the directory's own. Spec S1 below has the details. This is a consequence of the G2 free-mail decision and of the audit's assumption that "this one rule also closes the directory hole". It is not a defect in how this branch was built. Closing it needs a rule that neither the ticket nor G2 defines, so I am sending it back as a question and not blocking on it. Live sending stays off until someone sets `mode: live`, so this has to be settled before the switch to live, not before this merge.

**The docs commit 869a76d should stay.** `docs/scout.md:61-65` is where the add-lead rules are written down, and without this commit it would be out of date. The prompt change saves the model from spending tries on addresses the code will refuse. The commit is small and separate from the code commit. One sentence in it overclaims; see Spec S2.

## Standards

### Blocking

None.

### Should fix

- **Standards S1. `contact.py:115-119`: `on_mail_domain` duplicates `contact.on_domain` (`contact.py:96-99`).** The body is the same "equals the domain, or ends with `.` plus the domain" test, applied to the mail domain instead of to `host_of(url)`. `on_mail_domain(e, d)` gives the same result as `on_domain(mail_domain(e), d)`; I checked 9 cases, including lookalikes, `www.`, mixed case and an empty domain. The reuse rule says not to add a second copy of an existing helper. Fix: call `on_domain(mail_domain(email), domain)` inside `ownership_problem`, or move the suffix test into one private helper that both functions use. The same test is also written out by hand at `leads.py:330-334`, which is older code; using the shared helper there would stop the copies drifting apart.

### Nits

- **Standards N1. `contact.py:56`: the `FREE_MAIL_CONTACTS` ceiling is not in `caps.py`.** Three places say hard limits live there: `docs/agents/crew.md` ("Hard limits live in `jura_growth/caps.py`; a config value may lower a limit, never raise it"), the README's "Writing an agent plug-in" section ("its hard limits in `caps.py`"), and `config/scout.yaml:4-5`. The new comment at `config/scout.yaml:86-91` now points to `contact.FREE_MAIL_CONTACTS`. There is precedent for this: `settings.DAILY_TARGET_MAX` and `SCORE_THRESHOLD_MIN` are ceilings kept outside `caps.py`, and the developer stayed out of `caps.py` on purpose because ticket 05 edits it. Fix: move the ceiling once 05 has merged, or reword `config/scout.yaml:4-5` so it names both places.
- **Standards N2. `contact.py:44` and `:56`: `FREE_MAIL` (26 providers) and `FREE_MAIL_CONTACTS` (the 6 allowed) sit side by side.** The names don't say which list is which. Nothing checks that the six are a subset of the 26; they are today, which I verified. A name like `ALLOWED_FREE_MAIL`, plus a one-line test of the subset, would make both points clear.
- **Standards N3. `contact.py:122`: the default `free_mail=FREE_MAIL_CONTACTS` is never used.** The only caller, `leads.py:311`, always passes the setting. This is possible speculative generality. Make the argument required.
- **Standards N4. `tests/test_scout_leads.py`: the new helpers are tested only through `add()`.** The other contact helpers have unit tests in `tests/test_scout_contact.py`.

## Spec

### Blocking

None.

### Should fix

- **Spec S1. An unlisted directory still passes as the company's own site.**
  - **Spec lines:** the ticket says "A directory missing from the deny list also passes as the company's own site". The PRD says "Never use third-party lists, data brokers or scraped directories" (§5.2.5). G2 says free mail is allowed when it is "published on the company's own site".
  - **What the code checks:** `contact.py:130` accepts any address at an allowed free-mail provider. `leads.py:317` accepts any source page on the `website` domain. Neither check can tell a directory from the company's own site.
  - **What I reproduced** (all on the branch; the test file is in the reviewer's scratchpad, see Evidence):
    - **r1. Free mail on a directory.** The website and source page are `https://www.sgbizlistings.sg/alder-logistics`, and the contact is `alderlogistics@gmail.com` with `"enquiry_contact": true`. The lead is **added**, with `leads.domain = sgbizlistings.sg`.
    - **r2. The directory's own address replaces it.** Same lead, but the directory's footer also shows `info@sgbizlistings.sg`. The role-address swap at `leads.py:328-337` replaces the gmail address with `info@sgbizlistings.sg`. The lead is **added**, so the email would go to the directory, with a footer saying Alder Logistics lists that address. That false claim is exactly the harm B5 describes. The model can also reach this state by submitting the directory's own address directly.
    - **r3. A web designer's free-mail address.** A designer's gmail address in the company's footer is accepted. G2 allows this, but the ticket names this case as one to refuse.
  - **What is limited:** dedupe by domain means each unlisted directory can produce at most one lead.
  - **What is missing:** no test covers the free-mail or directory-own-address variants.
  - **Fix:** this needs a decision; see the question in the protocol report. Possible fixes: refuse a `website` that has a path beyond `/` (listings sit at a path, a company's own site at its root); refuse the role swap when the submitted address is free mail; for free-mail contacts, require the website domain to share a distinctive word with the company name. Whatever the user decides, record the remaining risk in ticket 06.
- **Spec S2. `prompts/scout.md:23-24` claims more than the code does.** It says "A partner's, supplier's or web designer's address on their site is not theirs, and the code refuses it." That is wrong when the address is free mail (`contact.py:130`, repro r3). In that case the prompt is the only guard, and it tells the model the code is guarding. Fix: say the code refuses an address on another business's domain, and that a free-mail address passes the code, so the model should use one only when the business publishes it as its own contact. The text in `docs/scout.md:61-65` is accurate.

### Nits

- **Spec N1. `settings.py:150-152`: `free_mail_contacts:` with no value turns on all six providers.** YAML reads an empty value as null, and the code treats null as "use the ceiling" (repro r4). The comment at `config/scout.yaml:90` only says that `[]` refuses free mail. Someone who writes the key with no value probably means "none". The ceiling still holds. Fix: say what null does in the comment, or treat null like `[]`.
- **Spec N2. `leads.py:324-326`: when an address isn't found, the hint lists every address on the page,** including ones the new rule refuses, such as a partner's `info@someoneelse.sg` (repro r6). The prompt at `prompts/scout.md:112` tells the model it may resubmit once with one of them, so that try is wasted. Fix: filter the hint through `ownership_problem`. This overlaps audit S1.
- **Spec N3. The rejection path is right but untested.** The new rejection goes through the same path as the other contact rejections (`leads.py:250`, `_reject(..., remember=False)`), as the ticket asks: the reason goes in the outcome, the `scout.rejected` event masks the local part (I verified `…@someoneelse.sg`), and no `scout_rejections` row is written. No test checks the event or the missing row.
- **Spec N4. A site on a subdomain refuses addresses on the parent domain.** For example, `sg.alder.com` refuses `info@alder.com` (repro r5). This is what the ticket says, and it errs on the safe side. Noted only; no change needed.
- **Entry paths: no finding.** `leads.py:289` is the only write to `contacts`. There is no `UPDATE contacts`, and `leads.domain` never changes after insert, so the rule covers every way an address gets in. Existing rows are not re-checked, but there are 0 leads so far.

## Security

There are no high or medium findings, and nothing is blocking. The skill's own diff header used the wrong range (main against the base), so I applied the pass to the ticket 06 diff above. I ran it inline, because the brief caps sub-agents at two and the code review had already used both.

- **Input handling.** The address passes `valid_email` (`ADDRESS_RE`, `leads.py:307`) before the new check runs. The branch adds no new SQL, shell, file or network path. The ownership check runs before the page fetch, so a refused address never triggers an outbound request.
- **Personal data.** The new rejection text holds the address. The event log masks its local part (`leads.py:170`, `_mask`; verified). The text returned to the CLI caller is unmasked, the same as the existing contact rejections.
- **Config.** It is read with `yaml.safe_load` (`config.py:40`). Config cannot widen the provider list (`settings.py:147-156`; tests at `tests/test_scout_leads.py:108-121`).
- **Consent and recipient control.** The remaining directory and free-mail path (Spec S1) is an existing gap in a personal-data control. This branch narrows it and does not create it, so it is reported under Spec.

## Blocked paths

None touched. The diff changes only `config/`, `docs/`, `jura_growth/agents/scout/`, `prompts/` and `tests/`. Nothing under `jurasolutions/inputs/`, `jurasolutions/design-system/`, `.env` or the live `jurasolutions/data/growth/` changed.

## Evidence

All of these were run in the developer's worktree, with `JURA_ROOT` set and the data and outputs folders pointed at fresh `mktemp -d` folders.

- `uv run --frozen pytest` -> 534 passed in 18.38s.
- `uv run --frozen pytest tests/test_scout_leads.py` -> 53 passed.
- Audit repros `test_f4` and `test_f4b`: on the base 01ce0e9, 2 passed (the defect is present); on the branch 869a76d, 2 failed (the defect is gone).
- Reviewer repros r1 to r6 on the branch -> 6 passed, so all six findings reproduce. File: `/private/tmp/claude-501/-Users-tingy-OneDrive-Desktop-projects-jurasolutions-repos-growth/d6daf64b-57e5-467e-9f34-aee2699f7f0f/scratchpad/review06/wt/test_review06.py`. The scratchpad belongs to this session, so the key repro is copied below.
- `pyright` on the three touched scout modules: 12 errors on the base, 12 on the branch, so nothing new.
- Importing `settings`, `contact`, `leads`, `cli` and `scout` in a fresh interpreter -> all ok, so the new import of `contact` into `settings` creates no cycle.
- `git merge-tree` of this branch with ticket 04 (which also edits `prompts/scout.md`) and with ticket 05 (`config/scout.yaml`, `docs/scout.md`) -> both clean.

The r1 and r2 repro, using the helpers in `tests/test_scout_support.py`:

```python
DIR = "https://www.sgbizlistings.sg/alder-logistics"
data = lead_data(1, website=DIR, source_urls=[DIR],
                 contact={"email": "alderlogistics@gmail.com", "source_url": DIR, "enquiry_contact": True})
assert add(conn, data).status == "added"                       # r1
page = ("<p>Email alderlogistics@gmail.com</p>"
        "<footer>Contact the directory: info@sgbizlistings.sg</footer>")
assert add(conn, data, page_html=page).contact["email"] == "info@sgbizlistings.sg"   # r2 (fresh db)
```
