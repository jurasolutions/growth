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
