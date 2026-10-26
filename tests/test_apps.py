"""The app factory plug-in (app factory PRD §5.6, §5.7, block 4)."""

import json
import os
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from jura_growth import config, db, paths, runner, timeutil
from jura_growth.agents import apps as apps_plugin
from jura_growth.agents.apps import backlog, catalog, factory, inputs
from jura_growth.agents.apps import prd as prd_mod
from jura_growth.cli import cli

REAL_PRD = paths.JURA_ROOT / "prd"
TODAY = "2026-10-26"


def invoke(*args):
    return CliRunner().invoke(cli, list(args), catch_exceptions=False)


@pytest.fixture(autouse=True)
def prd_tree(tmp_path, monkeypatch):
    """A private copy of prd/ (template plus APP-001 and APP-002) and a site
    repo with an empty registry, with the clock on Monday 26 October."""
    prd = tmp_path / "prd"
    (prd / "templates").mkdir(parents=True)
    (prd / "pending" / "apps").mkdir(parents=True)
    shutil.copy(REAL_PRD / "templates" / "prd-app-template.md", prd / "templates")
    for name in ("prd-app-001-quote-builder-2026-10-24.md", "prd-app-002-receipt-reader-2026-10-24.md"):
        shutil.copy(REAL_PRD / "pending" / "apps" / name, prd / "pending" / "apps")
    site = tmp_path / "site"
    (site / "src" / "apps").mkdir(parents=True)
    (site / "src" / "apps" / "registry.json").write_text("[]")
    monkeypatch.setenv("JURA_PRD_DIR", str(prd))
    monkeypatch.setenv("JURA_SITE_REPO", str(site))
    monkeypatch.setenv("JURA_GROWTH_NOW", f"{TODAY}T06:30:00+08:00")
    for name in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "D1_DATABASE_ID"):
        monkeypatch.delenv(name, raising=False)
    config.reset_caches()
    return prd


GOOD = """\
# PRD — APP-003 Delivery order maker

*Domain: `jurasolutions/` | Created: 2026-10-26 | Author: app factory (for Ting Yu)*
*Status: **PENDING SIGN-OFF** | Tier: browser | Category: Documents*
*Follows: `prd/pending/prd-jura-app-factory-2026-10-24.md` (toolbox shell, limiter, conventions).*
*To build: approve its app-build request in #approvals (prd/pending/apps/prd-app-003-delivery-order-maker-2026-10-26.md)*

---

## 1. Problem

- **One line (also the page subtitle):** Make a delivery order with your logo and a signature
  box, ready to print or send as a PDF.
- **Who has this problem:** owners and admin staff at wholesale, logistics and trade businesses
  who type delivery orders in Word or write them by hand for every drop.
- **Why it helps Jura:** suits wholesale and distribution, logistics and delivery, and field
  service businesses. The custom version Jura would build creates each delivery order from the
  confirmed sales order, collects the signature on the driver's phone and files the signed copy
  against the invoice.

## 2. Success criteria

- [ ] Lines with no description are left off the delivery order, with a visible hint.
- [ ] The DO number is suggested as `DO-YYYYMMDD-01` and stays editable.
- [ ] The PDF opens in Chrome, Safari and Acrobat, fits A4 and paginates cleanly at 40 lines.
- [ ] The signature box prints received-by name, date and signature lines.
- [ ] Works at 360 px wide and on desktop; 44 px tap targets
- [ ] Keyboard usable; every input labelled; contrast passes the design system's tokens
- [ ] All copy passes `jura-growth check`
- [ ] Talk-to-us card links to the enquiry form with `?from=apps/delivery-order-maker`
- [ ] Usage counter increments on open and on completion

## 3. Scope

### In scope
- Business details and logo (PNG, JPG or SVG up to 1 MB, kept in the browser).
- Customer, delivery address, DO number, delivery date and the customer's PO reference.
- Line items: description, quantity and unit; add, remove, reorder.
- Signature box with received-by name, date and signature lines.
- A4 PDF made in the browser.

### Out of scope
- Prices and totals, e-signatures, sending email, anything stored on Jura's servers.

## 4. Constraints

- **Official sources:** None. A delivery order follows no statutory format.
- **Privacy:** everything the visitor types, including the logo, stays in your browser. Only the
  anonymous open and download counters are recorded.
- **Tier rules:** browser tools make no server calls. AI tools use the shared limiter, Turnstile,
  `claude-haiku-5-5`, and store nothing uploaded.
- Design system only; the visitor's branding on anything they export, not Jura's.

## 5. Proposed plan

### 5.1 User flow
1. Visitor opens `/apps/delivery-order-maker`: form on the left, live preview on the right.
2. Enters business and customer details, then the items.
3. Downloads the PDF or starts a new delivery order.
4. Below the tool, the talk-to-us card.

### 5.2 Copy
- Title: "Delivery order maker"
- Subtitle: "Make a delivery order with your logo and a signature box, ready to print or send as a PDF."
- Privacy note: "Everything you type stays in your browser. Nothing is sent to us."
- Empty items: "Add your first item to see the delivery order."
- Buttons: "Add item", "Download PDF", "New delivery order"
- Logo too big: "Please use a logo under 1 MB."
- Talk-to-us card: heading "Delivery orders made from your sales orders"; body "We can create
  each delivery order from the confirmed sale and file the signed copy for you."; button "Tell us
  how you deliver today"

### 5.3 Technical
- **Folder:** `src/apps/delivery-order-maker/`
- **Registry entry:** `{ slug: "delivery-order-maker", name: "Delivery order maker", description:
  "Delivery orders with your logo and a signature box, as a PDF.", category: "Documents", tier:
  "browser", status: "live", added: "<deploy date>", prd: "APP-003" }`
- **Dependencies:** the PDF library the quote builder already loads.
- **State:** React state only; nothing stored.

### 5.4 Done-check
Run the unit tests, open the local dev server, make a 5-line delivery order, download the PDF and
show Ting Yu. Deploy only after his go-ahead.

## 6. Open questions

None.

## 7. Sign-off

**Do not start building. This PRD requires explicit sign-off before any code is written.**

To proceed: approve its app-build request in #approvals. Approving hands this PRD to a builder,
who builds it on its own branch from `main` with a preview. Going live is a second approval, of
the exact commit. Once released, this file moves to `prd/done/apps/` with the ship date and both
approvals recorded.

Signed off by: ________________  Date: ____________
"""

GST_URL = "https://www.iras.gov.sg/taxes/goods-services-tax-(gst)/basic-guide-to-gst/current-gst-rates"


def gst_checker(sources_line: str, *, estimate: bool = True) -> str:
    text = GOOD.replace("Delivery order maker", "GST checker").replace("delivery-order-maker", "gst-checker")
    text = text.replace("Category: Documents", "Category: Finance").replace('category: "Documents"', 'category: "Finance"')
    text = text.replace(
        "- **Official sources:** None. A delivery order follows no statutory format.",
        f"- **Official sources:** {sources_line}",
    )
    text = text.replace(
        "- A4 PDF made in the browser.",
        "- Add or remove GST from a price at the current IRAS standard rate, calculated in integer cents.",
    )
    if estimate:
        text = text.replace('- Logo too big: "Please use a logo under 1 MB."', '- Result note: "Estimate only. Check the rate on the IRAS website."')
    return text


def ctx(**overrides) -> prd_mod.FactoryContext:
    base = dict(
        today=TODAY, next_number=3, taken_slugs={}, taken_names={},
        name_words=tuple(catalog.settings().get("name_words") or ()),
        banned_name_words=tuple(catalog.settings().get("banned_name_words") or ()),
    )
    base.update(overrides)
    return prd_mod.FactoryContext(**base)


def write(tmp_path, text, name="draft.md") -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def outbox(channel):
    folder = paths.data_dir() / "discord-outbox"
    lines = []
    for file in sorted(folder.glob("*.jsonl")) if folder.exists() else []:
        lines += [json.loads(l) for l in file.read_text().splitlines()]
    return [l for l in lines if l["channel"] == channel]


# --- the template ----------------------------------------------------------


@pytest.mark.parametrize("name", ["prd-app-001-quote-builder-2026-10-24.md", "prd-app-002-receipt-reader-2026-10-24.md"])
def test_existing_app_prds_pass_the_template(name):
    text = (REAL_PRD / "pending" / "apps" / name).read_text()
    assert prd_mod.validate_shape(text) == []


def test_good_factory_prd_passes_every_rule():
    assert prd_mod.validate_shape(GOOD, strict=True) == []
    assert prd_mod.validate_factory(GOOD, ctx()) == []


BROKEN = {
    "missing section": lambda t: t.replace("## 6. Open questions\n\nNone.\n\n", ""),
    "renamed section": lambda t: t.replace("## 2. Success criteria", "## 2. Acceptance"),
    "extra section": lambda t: t.replace("## 6. Open questions", "## 5b. Risks\n\nSome.\n\n## 6. Open questions"),
    "missing subsection": lambda t: t.replace("### 5.4 Done-check", "Done-check:"),
    "bad tier": lambda t: t.replace("Tier: browser", "Tier: web"),
    "bad category": lambda t: t.replace("Category: Documents", "Category: Logistics"),
    "no to-build line": lambda t: t.replace('*To build: approve its app-build request in #approvals (prd/pending/apps/prd-app-003-delivery-order-maker-2026-10-26.md)*\n', ""),
    "to-build wrong number": lambda t: t.replace("(prd/pending/apps/prd-app-003-delivery-order-maker-2026-10-26.md)*", "(prd/pending/apps/prd-app-004-delivery-order-maker-2026-10-26.md)*"),
    "old to-build line": lambda t: t.replace(
        "*To build: approve its app-build request in #approvals (prd/pending/apps/prd-app-003-delivery-order-maker-2026-10-26.md)*",
        '*To build: "approved, build prd/pending/apps/prd-app-003-delivery-order-maker-2026-10-26.md"*'),
    "old sign-off reply": lambda t: t.replace(
        "To proceed: approve its app-build request in #approvals.",
        'To proceed: reply "approved, build prd/pending/apps/prd-app-003-delivery-order-maker-2026-10-26.md".'),
    "to-build wrong date": lambda t: t.replace("Created: 2026-10-26", "Created: 2026-10-25"),
    "slug not from name": lambda t: t.replace("# PRD — APP-003 Delivery order maker", "# PRD — APP-003 Delivery note maker"),
    "no gate sentence": lambda t: t.replace("**Do not start building. This PRD requires explicit sign-off before any code is written.**", "Build when ready."),
    "missing 360 px criterion": lambda t: t.replace("- [ ] Works at 360 px wide and on desktop; 44 px tap targets\n", ""),
    "missing usage criterion": lambda t: t.replace("- [ ] Usage counter increments on open and on completion\n", ""),
    "wrong from slug": lambda t: t.replace("?from=apps/delivery-order-maker", "?from=apps/delivery"),
    "missing official sources": lambda t: t.replace("- **Official sources:** None. A delivery order follows no statutory format.\n", ""),
    "missing registry entry": lambda t: t.replace("- **Registry entry:**", "- **Entry:**"),
    "registry entry wrong prd": lambda t: t.replace('prd: "APP-003"', 'prd: "APP-030"'),
    "no talk-to-us button": lambda t: t.replace('; button "Tell us\n  how you deliver today"', ""),
    "subtitle differs from one line": lambda t: t.replace('Subtitle: "Make a delivery order', 'Subtitle: "Create a delivery order'),
    "no one line": lambda t: t.replace("**One line (also the page subtitle):**", "**Summary:**"),
}


@pytest.mark.parametrize("label", sorted(BROKEN))
def test_broken_variants_fail(label):
    broken = BROKEN[label](GOOD)
    assert broken != GOOD, "the mutation must change the text"
    assert prd_mod.validate_shape(broken, strict=True), label


def test_the_template_says_a_build_starts_with_its_app_build_request_not_a_typed_reply():
    """Ticket 10b: the template's "To build:" header and §7 point at the `app-build` request in
    #approvals, so the PRD attached to its card no longer says "approved, build …" (AC-M9.1)."""
    template = (REAL_PRD / "templates" / "prd-app-template.md").read_text()
    assert "approved, build" not in template
    assert "*To build: approve its app-build request in #approvals (prd/pending/apps/prd-app-NNN-<slug>-YYYY-MM-DD.md)*" in template
    assert "To proceed: approve its app-build request in #approvals." in template
    assert "approved, build" not in GOOD


def test_a_prd_filed_before_the_new_header_still_reads_but_the_factory_needs_the_new_one():
    """APP-001 to APP-003 keep the old header (their bytes are what was asked about); the parser
    still reads it, and only a new factory PRD must use the template's new wording."""
    old = BROKEN["old sign-off reply"](BROKEN["old to-build line"](GOOD))
    parsed = prd_mod.parse(old)
    assert parsed.build_path == "prd/pending/apps/prd-app-003-delivery-order-maker-2026-10-26.md"
    assert parsed.slug == "delivery-order-maker"
    assert prd_mod.validate_shape(old) == []
    assert any("To build" in e for e in prd_mod.validate_shape(old, strict=True))
    assert any("§7" in e for e in prd_mod.validate_shape(BROKEN["old sign-off reply"](GOOD), strict=True))


def test_strict_mode_needs_the_template_wording():
    text = GOOD.replace("Author: app factory (for Ting Yu)", "Author: someone")
    assert prd_mod.validate_shape(text) == []
    assert any("Author" in e for e in prd_mod.validate_shape(text, strict=True))
    text = GOOD.replace("; contrast passes the design system's tokens", "")
    assert any("contrast" in e for e in prd_mod.validate_shape(text, strict=True))


def test_copy_items_unwrap_and_split_bullets():
    parsed = prd_mod.parse(GOOD)
    copy = {i.where: (i.kind, i.text) for i in parsed.copy()}
    assert copy["Talk-to-us card heading"] == ("heading", "Delivery orders made from your sales orders")
    assert copy["Talk-to-us card body"][1].startswith("We can create each delivery order")
    assert copy["Talk-to-us card button"] == ("heading", "Tell us how you deliver today")
    real = prd_mod.parse((REAL_PRD / "pending" / "apps" / "prd-app-001-quote-builder-2026-10-24.md").read_text())
    assert any(i.text.startswith("We can connect your quoting") for i in real.copy())


# --- numbering, duplicates, names ------------------------------------------


def test_numbering_scans_pending_done_and_registry(prd_tree, conn):
    assert catalog.next_number(conn) == 3
    (prd_tree / "done" / "apps").mkdir(parents=True)
    (prd_tree / "done" / "apps" / "prd-app-007-old-tool-2026-10-01.md").write_text("# PRD — APP-007 Old tool\n")
    assert catalog.next_number(conn) == 8
    catalog.registry_path().write_text(json.dumps([{"slug": "x", "name": "X", "status": "live", "prd": "APP-010"}]))
    assert catalog.next_number(conn) == 11


def test_wrong_number_and_date_are_rejected():
    errors = prd_mod.validate_factory(GOOD, ctx(next_number=4))
    assert any("APP-004" in e for e in errors)
    errors = prd_mod.validate_factory(GOOD, ctx(today="2026-10-27"))
    assert any("today" in e for e in errors)


def test_duplicates_of_live_pending_and_backlog_are_rejected(conn):
    slugs, names = catalog.taken(conn)
    assert "quote-builder" in slugs and "receipt reader" in names  # pending PRDs and backlog rows
    clash = GOOD.replace("Delivery order maker", "Quote builder").replace("delivery-order-maker", "quote-builder")
    errors = prd_mod.validate_factory(clash, ctx(taken_slugs=slugs, taken_names=names))
    assert any(e.startswith("duplicate: the slug") for e in errors)
    assert any(e.startswith("duplicate: the name") for e in errors)
    catalog.registry_path().write_text(json.dumps([{"slug": "delivery-order-maker", "name": "Delivery order maker", "status": "live", "prd": "APP-009"}]))
    slugs, names = catalog.taken(conn)
    assert any("duplicate" in e for e in prd_mod.validate_factory(GOOD, ctx(taken_slugs=slugs, taken_names=names)))
    # a backlog idea that has no PRD yet is the expected pick, not a duplicate
    assert "invoice-builder" not in slugs


@pytest.mark.parametrize("name", ["Quotely", "InvoiceFlow", "Invoice Builder", "Smart invoice", "IRAS filing helper", "Receipt genie", "Tool 2"])
def test_names_must_be_plain_sentence_case(name):
    assert prd_mod.name_problems(name, ctx())


@pytest.mark.parametrize("name", ["Invoice builder", "PayNow QR maker", "PDF merge and split", "Time-saved calculator", "Meeting notes tidier"])
def test_plain_names_pass(name):
    assert prd_mod.name_problems(name, ctx()) == []


# --- guardrails and official sources ---------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "- Tells you whether your contract is enforceable, as legal advice.",
        "- Suggests a diagnosis from the symptoms an employee reports.",
        "- Recommends an investment portfolio for the business's spare cash.",
        "- Produces an official receipt in the IRAS format.",
        "- Sign in with Google to keep your delivery orders.",
    ],
)
def test_guardrails_block_advice_government_and_logins(line):
    text = GOOD.replace("- A4 PDF made in the browser.", line)
    assert any(e.startswith("guardrail") for e in prd_mod.validate_factory(text, ctx()))


def test_guardrails_ignore_negations_and_out_of_scope():
    text = GOOD.replace("- A4 PDF made in the browser.", "- No sign-in needed; works without an account.")
    assert not any(e.startswith("guardrail") for e in prd_mod.validate_factory(text, ctx()))
    assert "sign-in" not in prd_mod.scan_text(prd_mod.parse(GOOD.replace("e-signatures", "sign-in")))


def test_statutory_calculator_needs_estimate_label_and_source():
    fetched = [GST_URL]
    good = gst_checker(f"IRAS GST rates page, {GST_URL}, checked 2026-10-26.")
    assert prd_mod.validate_factory(good, ctx(fetched_urls=fetched)) == []
    no_label = gst_checker(f"IRAS, {GST_URL}, checked 2026-10-26.", estimate=False)
    assert any("estimate" in e for e in prd_mod.validate_factory(no_label, ctx(fetched_urls=fetched)))


@pytest.mark.parametrize(
    "line, wanted",
    [
        ("None.", "says None"),
        (f"IRAS, {GST_URL}.", "date you checked"),
        ("Rate from https://www.example.com/gst-rates, checked 2026-10-26.", "official page"),
        (f"IRAS, {GST_URL}, checked 2026-09-01.", "more than"),
        (f"IRAS, {GST_URL}, checked 2026-10-26.", "not fetched in this run"),
    ],
)
def test_official_sources_need_url_date_and_a_fetch(line, wanted):
    errors = prd_mod.validate_factory(gst_checker(line), ctx(fetched_urls=[]))
    assert any(wanted in e for e in errors), errors


def test_receipt_reader_style_none_with_reason_is_fine():
    parsed = prd_mod.parse((REAL_PRD / "pending" / "apps" / "prd-app-002-receipt-reader-2026-10-24.md").read_text())
    assert prd_mod.source_problems(parsed, ctx()) == []


def test_app_copy_channel_blocks_saving_claims():
    from jura_growth import brand_check

    assert not brand_check.check("Make delivery orders in seconds and save hours every week.", channel_name="app-copy").passed
    assert brand_check.check("Make a delivery order with your logo.", channel_name="app-copy").passed


# --- submit-prd, the limits and the digest ---------------------------------


def test_submit_prd_files_updates_backlog_and_raises_an_app_build_request(tmp_path, prd_tree):
    """The card itself is in `test_app_builds.py` (AC-M9.1); the old #app-factory post is gone."""
    result = invoke("apps", "submit-prd", str(write(tmp_path, GOOD)))
    assert result.exit_code == 0, result.output
    target = prd_tree / "pending" / "apps" / "prd-app-003-delivery-order-maker-2026-10-26.md"
    assert target.read_text() == GOOD
    row = next(r for r in backlog.load() if r["name"] == "Delivery order maker")
    assert row["status"] == "prd-pending" and row["app_id"] == "APP-003"
    assert backlog.path().exists()
    assert outbox("app-factory") == []
    assert "approval request A-0001 raised" in result.output
    with db.session() as c:
        assert db.scalar(c, "SELECT app_id FROM app_prds") == "APP-003"
        assert db.scalar(c, "SELECT subject FROM approvals WHERE kind = 'app-build'") == "app:APP-003"


def test_dry_run_files_nothing(tmp_path, prd_tree):
    result = invoke("apps", "submit-prd", "--dry-run", str(write(tmp_path, GOOD)))
    assert result.exit_code == 0 and "passes every check" in result.output
    assert not (prd_tree / "pending" / "apps" / "prd-app-003-delivery-order-maker-2026-10-26.md").exists()
    assert outbox("app-factory") == []


def test_one_a_day(tmp_path, conn):
    assert apps_plugin.precheck("app-factory", conn) is None
    assert invoke("apps", "submit-prd", str(write(tmp_path, GOOD))).exit_code == 0
    reason = apps_plugin.precheck("app-factory", conn)
    assert reason and "already written today" in reason and "APP-003" in reason
    second = GOOD.replace("APP-003", "APP-004").replace("prd-app-003", "prd-app-004")
    second = second.replace("Delivery order maker", "Price list maker").replace("delivery-order-maker", "price-list-maker")
    result = invoke("apps", "submit-prd", str(write(tmp_path, second, "second.md")))
    assert result.exit_code == 1 and "one a day" in result.output
    # the scheduled job skips without starting Claude, and says why
    outcome = runner.run("app-factory", ignore_schedule=True)
    assert outcome.status == "skipped" and "already written today" in outcome.summary
    part = apps_plugin.digest(conn, TODAY)
    assert part["brief"] == ["app PRD: APP-003 Delivery order maker"]
    assert part["figures"]["app_prd_today"] == "APP-003 Delivery order maker"


def test_prds_with_no_app_build_request_are_not_in_the_waiting_pile(tmp_path, prd_tree, conn):
    """MC §5.9 step 6: the pile counts PRDs waiting for an `app-build` decision. Ting Yu's own
    PRDs never get a request, so seven of them don't stop the factory; AC-M9.10 is in
    `test_app_builds.py`."""
    for n in range(3, 8):
        (prd_tree / "pending" / "apps" / f"prd-app-{n:03d}-tool-{n}-2026-10-20.md").write_text(f"# PRD — APP-{n:03d} Tool\n")
    assert apps_plugin.precheck("app-factory", conn) is None
    assert invoke("apps", "submit-prd", str(write(tmp_path, GOOD.replace("APP-003", "APP-008").replace("prd-app-003", "prd-app-008")))).exit_code == 0


def test_brand_failure_allows_one_regeneration_then_drops(tmp_path, conn):
    bad = GOOD.replace('- Empty items: "Add your first item to see the delivery order."', '- Empty items: "Add your first item and save hours!"')
    first = invoke("apps", "submit-prd", str(write(tmp_path, bad)))
    assert first.exit_code == 1 and "regeneration" in first.output and "exclamation" in first.output
    second = invoke("apps", "submit-prd", str(write(tmp_path, bad)))
    assert second.exit_code == 1 and "dropped" in second.output
    assert "dropped" in apps_plugin.precheck("app-factory", conn)
    assert not list((paths.prd_dir() / "pending" / "apps").glob("prd-app-003-*"))


def test_structural_rejection_does_not_use_the_brand_attempt(tmp_path, conn):
    broken = BROKEN["missing 360 px criterion"](GOOD)
    result = invoke("apps", "submit-prd", str(write(tmp_path, broken)))
    assert result.exit_code == 1 and "brand check has not run" in result.output
    assert db.scalar(conn, "SELECT count(*) FROM qa_attempts") == 0
    assert invoke("apps", "submit-prd", str(write(tmp_path, GOOD))).exit_code == 0


PRIVATE = {
    # code review 12, Q1: what the privacy filter would change never goes into a PRD
    "a named address": "Asked by jane.tan@example.com during a call.",
    "a phone number": "Call the owner on 9123 4567 to check the wording.",
    "a secret-looking value": "Test key: sk-ant-abcdefghijklmnop0123",
}


@pytest.mark.parametrize("label", sorted(PRIVATE))
@pytest.mark.parametrize("dry_run", [False, True], ids=["submit", "dry run"])
def test_a_prd_the_privacy_filter_would_change_is_rejected_before_the_brand_check(tmp_path, conn, label, dry_run):
    private = PRIVATE[label]
    text = GOOD.replace("## 2. Success criteria", f"{private}\n\n## 2. Success criteria")
    line = text.splitlines().index(private) + 1
    result = invoke("apps", "submit-prd", *(["--dry-run"] if dry_run else []), str(write(tmp_path, text)))
    assert result.exit_code == 1, result.output
    assert "brand check has not run" in result.output and f"line {line}" in result.output
    assert "a person's name or address, a phone number or a secret-looking value" in result.output
    assert private not in result.output and "jane.tan" not in result.output and "sk-ant-" not in result.output
    assert not list((paths.prd_dir() / "pending" / "apps").glob("prd-app-003-*"))
    assert db.scalar(conn, "SELECT count(*) FROM qa_attempts") == 0
    assert db.scalar(conn, "SELECT count(*) FROM approvals") == 0


def test_the_good_prd_is_unchanged_by_the_privacy_filter(tmp_path):
    assert invoke("apps", "submit-prd", "--dry-run", str(write(tmp_path, GOOD))).exit_code == 0


def test_cited_source_must_be_fetched_in_the_run(tmp_path, monkeypatch, conn):
    from jura_growth import log

    run_id = log.start_run(conn, "app-factory", "app-factory")
    transcript = paths.data_dir() / "transcripts" / TODAY / f"{run_id}-app-factory.jsonl"
    transcript.parent.mkdir(parents=True)
    records = [
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "WebFetch", "input": {"url": GST_URL, "prompt": "rate"}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "The GST rate is 9%"}]}},
    ]
    transcript.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    monkeypatch.setenv("JURA_GROWTH_RUN_ID", str(run_id))
    other = gst_checker(f"IRAS, {GST_URL.replace('current-gst-rates', 'other-page')}, checked 2026-10-26.")
    result = invoke("apps", "submit-prd", str(write(tmp_path, other)))
    assert result.exit_code == 1 and "not fetched in this run" in result.output
    good = gst_checker(f"IRAS GST rates page, {GST_URL}, checked 2026-10-26.")
    result = invoke("apps", "submit-prd", str(write(tmp_path, good)))
    assert result.exit_code == 0, result.output


# --- status, context, backlog ----------------------------------------------


def test_backlog_seed_has_the_twenty_ideas():
    rows = backlog.load()
    assert len(rows) == 20
    by_name = {r["name"]: r for r in rows}
    assert by_name["Quote builder"]["app_id"] == "APP-001" and by_name["Quote builder"]["status"] == "prd-pending"
    assert by_name["Receipt reader"]["app_id"] == "APP-002" and by_name["Receipt reader"]["tier"] == "ai"
    assert all(r.get("tier") in ("browser", "ai") and r.get("notes") and r.get("status") for r in rows)
    assert {r["name"] for r in rows if r["tier"] == "ai"} == {
        "Receipt reader", "Email reply helper", "Job ad writer", "Meeting notes tidier", "Social caption kit", "Business card reader",
    }


def test_status_handles_a_missing_registry(monkeypatch, tmp_path):
    monkeypatch.setenv("JURA_SITE_REPO", str(tmp_path / "nowhere"))
    result = invoke("apps", "status")
    assert result.exit_code == 0
    assert "next number    APP-003" in result.output and "not found" in result.output


def test_context_json_has_everything_the_prompt_needs():
    result = invoke("apps", "context", "--json")
    assert result.exit_code == 0
    view = json.loads(result.output)
    assert view["next_number"] == "APP-003" and view["waiting"] == {"count": 0, "max": 7}
    assert view["usage"]["status"] == "not configured"
    assert {"industries", "observations", "source"} <= set(view["scout_insights"])
    assert len(view["backlog"]) == 20 and view["limit_reason"] is None
    assert Path(view["files"]["template"]).exists()


def test_scout_insights_fall_back_to_the_leads_table(monkeypatch):
    import sqlite3

    monkeypatch.setattr(inputs, "_from_scout_command", lambda days: None)
    mem = sqlite3.connect(":memory:")
    mem.row_factory = sqlite3.Row
    mem.execute("CREATE TABLE leads (industry TEXT, observations_json TEXT, created_at TEXT)")
    mem.execute("INSERT INTO leads VALUES ('logistics', '[\"orders by WhatsApp\"]', ?)", (timeutil.stamp(),))
    mem.execute("INSERT INTO leads VALUES ('logistics', '[]', ?)", (timeutil.stamp(),))
    mem.execute("INSERT INTO leads VALUES ('events', '[]', '2020-01-01T00:00:00+08:00')")
    found = inputs.scout_insights(mem, 30)
    assert found["source"] == "leads table" and found["industries"] == {"logistics": 2}
    assert found["observations"] == [{"industry": "logistics", "observation": "orders by WhatsApp"}]
    empty = sqlite3.connect(":memory:")
    empty.row_factory = sqlite3.Row
    assert inputs.scout_insights(empty, 30)["industries"] == {}


def test_usage_reads_d1_when_configured(monkeypatch):
    from jura_growth import cloudflare

    monkeypatch.setattr(cloudflare, "configured", lambda: True)
    monkeypatch.setattr(cloudflare, "query", lambda sql, params: [{"app_slug": "quote-builder", "opens": 5, "completions": 2}])
    found = inputs.usage(7)
    assert found["status"] == "ok" and found["rows"][0]["app_slug"] == "quote-builder" and found["since"] == "2026-10-20"


def test_digest_without_a_run_says_so(conn):
    part = apps_plugin.digest(conn, TODAY)
    assert part["figures"]["app_prd_today"] is None and part["brief"] == ["no app PRD today"]
