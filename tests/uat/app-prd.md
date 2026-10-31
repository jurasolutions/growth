# PRD — {app_id} {name}

*Domain: `jurasolutions/` | Created: {day} | Author: app factory (for Ting Yu)*
*Status: **PENDING SIGN-OFF** | Tier: browser | Category: Documents*
*Follows: `prd/pending/prd-jura-app-factory-2026-10-24.md` (toolbox shell, limiter, conventions).*
*To build: approve its app-build request in #approvals (prd/pending/apps/prd-app-{number}-{slug}-{day}.md)*

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
- [ ] Talk-to-us card links to the enquiry form with `?from=apps/{slug}`
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
1. Visitor opens `/apps/{slug}`: form on the left, live preview on the right.
2. Enters business and customer details, then the items.
3. Downloads the PDF or starts a new delivery order.
4. Below the tool, the talk-to-us card.

### 5.2 Copy
- Title: "{name}"
- Subtitle: "Make a delivery order with your logo and a signature box, ready to print or send as a PDF."
- Privacy note: "Everything you type stays in your browser. Nothing is sent to us."
- Empty items: "Add your first item to see the delivery order."
- Buttons: "Add item", "Download PDF", "New delivery order"
- Logo too big: "Please use a logo under 1 MB."
- Talk-to-us card: heading "Delivery orders made from your sales orders"; body "We can create
  each delivery order from the confirmed sale and file the signed copy for you."; button "Tell us
  how you deliver today"

### 5.3 Technical
- **Folder:** `src/apps/{slug}/`
- **Registry entry:** `{ slug: "{slug}", name: "{name}", description:
  "Delivery orders with your logo and a signature box, as a PDF.", category: "Documents", tier:
  "browser", status: "live", added: "<deploy date>", prd: "{app_id}" }`
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
