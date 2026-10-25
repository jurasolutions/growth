# 06 — A contact address must belong to the business

Status: ready-for-agent
Blocked by: -
Covers: scout B5

## Problem

The scout PRD allows "only an address the business publishes for enquiries on its own website" and never third-party lists or directories (§5.2.5, success criterion 3). The code checks only that the address appears on some page of the lead's domain (`leads.py:304-351`, `contact.py:52-60`). So `info@someoneelse.sg` on a partners page, or a web designer's address in a footer, is accepted, and the email footer then claims the company lists it. A directory missing from the deny list also passes as the company's own site.

## What to change

Accept an address only when its domain is the lead's site domain or a subdomain of it, or a free-mail provider that small businesses use. The free-mail rule is decided at the gate (see `crew-log.md`); default: allow a short, fixed list (gmail.com, outlook.com, hotmail.com, yahoo.com, icloud.com, singnet.com.sg) kept in `config/scout.yaml` and loaded so config can shorten it but code holds the ceiling. Record the rejection reason the same way other contact rejections are recorded.

## Acceptance criteria

- Repros `test_f4_unrelated_domain_address_is_accepted` and `test_f4b_unlisted_directory_passes_as_own_site` (in `audit/repro/test_review_repro.py`) become passing regression tests: both addresses are rejected.
- `hello@alder.com.sg` found on `alder.com.sg` and `sales@mail.alder.com.sg` are accepted.
- A free-mail address published on the company's own site is accepted, or rejected, according to the gate's decision.
- `uv run pytest` passes.

## Pointers

- `audit/code-review-02-scout.md` B5
- `jura_growth/agents/scout/leads.py:290-360`, `jura_growth/agents/scout/contact.py:40-70`, `config/scout.yaml`

## Comments

### 2026-10-25 developer: what the code still can't refuse

Fix round 1 (code review 06, Spec S1) added two rules. `add-lead` refuses a `website` with a
path or query, because a directory listing sits at a path on someone else's site. A named
address is swapped for a role address on the same page only when it is on the company's own
domain, and a free-mail address is never swapped. Review repros r1 and r2 no longer reproduce.
Two gaps remain, and code can't close them without a rule the ticket and G2 don't define:

1. **A directory recorded by its home page.** If the model gives an unlisted directory's home
   page as `website` (`https://www.sgbizlistings.sg`) and the listing as the source page, the
   path rule passes. The code then accepts a free-mail address on the listing. It also accepts
   the directory's own address (`info@sgbizlistings.sg`) if the model submits it directly. In
   that case the email goes to the directory, and its footer says the company lists the
   address. Nothing in code ties the website domain to the company. Dedupe by domain limits
   this to one lead per directory, because that lead then holds the directory's domain.
2. **Someone else's free-mail address on the company's own site.** A web designer's credit or
   a partner's Gmail address passes, because G2 allows the six free-mail providers wherever the
   company's site publishes them (review repro r3). Only the prompt guards this case. It now
   says the code doesn't check free mail, so the model must use one only when the business
   publishes it as its own enquiry contact.

Possible code rules, each needing a decision: require a free-mail contact's website domain to
share a distinctive word with the company name; or keep adding directories to
`contact.NOT_OWN_SITE` as they turn up. Meanwhile, every lead is posted to `#scout-leads` with
its domain, so Ting Yu can spot a directory domain during the shadow trial, before `mode: live`.
