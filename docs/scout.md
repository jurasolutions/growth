# The scout and outreach agents

Built against `jurasolutions/prd/pending/prd-jura-scout-2026-10-24.md`, blocks 1–4. Two
plug-ins share one config file:

| Plug-in | Agent name | Does | Code |
|---|---|---|---|
| scout | `scout` | Research, qualification, contact rules, dedupe | `jura_growth/agents/scout/` |
| outreach | `outreach` | Email checks, queue, sending, sync, auto-pause | `jura_growth/agents/outreach/` |

Settings: `config/scout.yaml`. Hard limits: `jura_growth/caps.py`. Prompt:
`prompts/scout.md`. `jura-growth pause outreach` stops sending without stopping research.

## How a day runs (SGT, business days)

1. **09:00 `scout-research`** (headless Claude, no spending ceiling). Refuses to start when
   `inputs/icp.md` is missing, today's candidates are already ranked, today's shortlist is
   already kept, or `max_queue` emails are already waiting. The session asks
   `jura-growth scout today` for its industries, researches about 20 candidates with web search
   and fetch (job boards are a key source, see "Shortlist research" below), submits them all
   with `jura-growth scout shortlist`, and queues an email for each kept lead with
   `jura-growth outreach queue`. Kept leads post to `#scout-leads`. WebSearch and WebFetch are
   allowed for this job with no domain restriction, so job boards are reachable.
2. **09:30–16:30 `scout-send`** every 10 minutes (quiet: no run row when nothing happens).
   `jura-growth outreach send-due` sends at most one email per run.
3. **16:45 `scout-sync`**. `jura-growth outreach sync`: D1 suppression sync, bounces and
   complaints, reply detection (optional), follow-ups due, retention.
4. **17:30 digest** includes the scout and outreach figures.

## Commands

| Command | Does |
|---|---|
| `scout today [--json]` | Today's industries, candidates, shortlist, threshold, weights, queue room, live tools, follow-ups due |
| `scout check <domain\|address\|name>` | Exit 1 if already a lead, contacted, suppressed or on the do-not-contact list; `looked_at_before` shows a recent rejection and its score |
| `scout check-contact --website W --email E --source URL [--enquiry-contact] [--json]` | The contact rules alone, changing nothing (exit 1 = refused) |
| `scout shortlist --file <json> [--json]` | Submit the day's candidates; the code ranks them and keeps the best (the research run's only way to add leads) |
| `scout add-lead --file <json> [--json]` | Record one lead by hand; every contact rule is checked here (exit 1 = rejected). Not available to the research run |
| `scout leads [--days N] [--status S] [--json]` | Recent leads |
| `scout insights --days N --json` | `{"industries": {name: count}, "observations": [...]}` (the app factory reads it) |
| `scout tools [--json]` | Live tools from the site registry, with D1 usage counts when configured |
| `outreach queue --lead <id> --file <json> [--kind follow_up]` | Brand-gate and queue an email (exit 1 = fail or dropped) |
| `outreach follow-ups-due [--json]` | Leads due their one follow-up |
| `outreach send-due` | The send run (what `scout-send` calls) |
| `outreach sync` | The sync run (what `scout-sync` calls) |
| `outreach queue-list [--all] [--json]` | The queue, or every message |
| `outreach preview <id> [--html]` | The full email with headers, as it would go out now |
| `outreach suppress <email\|domain>` | Suppress and cancel anything queued for it |
| `outreach unsubscribe-link <email>` | The unsubscribe URL, to test the website's function |
| `outreach status [--json]` | Mode, every reason live mode would refuse, caps, warm-up, queue |
| `outreach requeue-shadow [--since YYYY-MM-DD] [--lead ID ...] [--dry-run]` | After the shadow trial: queue shadow emails for live sending (live mode only) |

## Block 1: research and the contact rules (code, not prompt)

`scout add-lead` rejects, in order:

1. Incomplete records: company, website, industry, 1–3 observations, source URLs (one on the
   company's own site), a 0–100 score with written reasons.
2. Websites that are social profiles, directories, marketplaces, job boards or recruiters
   (`contact.NOT_OWN_SITE`, `JOB_BOARDS`, `RECRUITERS`, and any host with "recruit" in its
   name), government domains (`.gov.sg`, `.mil.sg`), and a website with a path or query:
   `https://directory.sg/acme` is a listing, not the company's home page.
3. Anything already known: a lead with the domain (or the address's domain), a domain in
   `contacted_domains`, a suppressed address or domain, or a row in
   `inputs/do-not-contact.csv` (company name as whole words, or domain and its subdomains).
4. Scores below 60 (config may raise the threshold, never lower it).
5. More than the day's shortlist (`research.shortlist`, 10; code ceiling 10 in `caps.py`).
6. The address: its source page (and a contact form) may never be on a job board, a
   recruiter's site or a careers or job-ad page, the company's own included
   (`contact.job_ad_problem`): job boards are evidence only. It must be an enquiry address
   (not careers@, noreply@ ...), it must belong
   to the business (on the website's domain or a subdomain of it, or at one of the free-mail
   providers in `free_mail_contacts`: gmail.com, outlook.com, hotmail.com, yahoo.com,
   icloud.com, singnet.com.sg; config may shorten that list, never add to it), its source
   page must be on the company's own domain, and **the code fetches that page and finds the exact
   address on it**, after decoding HTML entities, `mailto:` (percent-encoded too),
   `info [at] acme [dot] sg` and its bracket and word variants, and Cloudflare email
   protection (`data-cfemail` and `/cdn-cgi/l/email-protection#<hex>`, XOR with the first
   byte). Redirects off the domain fail. A named address on the company's domain is refused
   when the same page lists an enquiry role address on that domain (the role address is used
   instead). A free-mail address is never swapped for another. Otherwise a named address
   needs `"enquiry_contact": true`. Then an MX lookup (dnspython), and nothing else.
7. A contact form only gives `channel = form`: never emailed, listed in the digest.

Rejections for exclusions, low scores, suppression, contacted domains and the do-not-contact
list, and candidates passed over for rank, are remembered in `scout_rejections` (domain,
company name, score and reason) for 12 months, so `scout check` can say "looked at before" and
`scout shortlist` skips them. Duplicates and address failures are not.

## Shortlist research, with job boards (PRD §5.2a)

Each research run compares about `research.candidates` companies (20; code ceiling 40) across
the day's industries and keeps the best of them by score, up to `research.shortlist` a day
(10; code ceiling 10). Job boards are a key source: MyCareersFuture, JobStreet, Indeed,
LinkedIn Jobs, Glassdoor and the company's own careers page. Hiring for admin, accounts,
operations, data-entry, customer-service or document-processing roles is a strong sign of
manual work.

**The weights** (`scoring.WEIGHTS`, also in `scout today --json`). Every candidate in a batch
carries `score_breakdown`, and the code checks each factor against its weight and that they add
up to the score. Hiring points need hiring evidence; address points need a contact address.

| Factor | Key | Points |
|---|---|---|
| Industry fit | `industry_fit` | 20 |
| Size fit (about 5–200 staff) | `size_fit` | 15 |
| Hiring signals from job boards and careers pages | `hiring_signals` | 30 |
| Paperwork signals seen on the company's own site | `paperwork_signals` | 20 |
| How specific and checkable the observations are | `specific_observations` | 5 |
| A published enquiry address | `enquiry_address` | 10 |

**Hiring evidence** is a list of postings, `{url, title, seen (YYYY-MM-DD, not in the future),
duties: [...]}`, at most 10 a lead, with no email address anywhere in it. Its URLs may be on
job boards: they are evidence only, and the contact rule above still refuses a job board as a
contact source. **The comparison** is one line, at most 280 characters, on why the lead ranks
where it does; every candidate at or above the threshold needs one.

**`scout shortlist`**, in order:

1. The whole batch is checked first: every candidate's record (as add-lead checks it), a
   breakdown on each, a comparison at or above the threshold, no company twice, at most
   `research.candidates`. One bad candidate refuses the batch and nothing is recorded.
2. A day is ranked once (`scout_rankings`). A kept lead can't be taken back, so a second batch
   could only keep the best of itself, never the best of the day; it is refused. The research
   precheck also skips a day already ranked.
3. A company in `scout_rejections` from the last 12 months is skipped.
4. The rest are ranked by score, highest first; ties keep the submitted order.
5. In rank order, each goes through every add-lead rule while the shortlist has room. One refused
   on its contact or as already known gives its place to the next. Once the shortlist is full,
   each remaining candidate at or above the threshold is recorded as "researched, not kept:
   ranked N of M; today's shortlist of 10 was full", with its score. A weak day keeps fewer; it
   never pads.

`scout check-contact` runs the same contact rules with no side effects, so the session can
confirm an address before the batch rather than lose a candidate to it.

Kept leads store `hiring_evidence_json`, `comparison` and `score_breakdown_json`. Their
`#scout-leads` post adds "Why kept: <comparison>" and "Hiring: <strongest posting>" (the most
recently seen, then the one naming the most duties). The digest adds the day's ranking and one
line per kept lead with the same two facts.

**Keeping more never sends more.** The send caps (warm-up, daily ceiling, rolling caps), the
window, random spacing, the bounce and complaint auto-pause, Ting Yu's approval of each live
email and the `max_queue` research skip are unchanged. `tests/test_scout_shortlist.py` keeps
and queues ten leads and shows the first live day still sends five. Event logs
never carry a full address (`…@domain`); addresses live only in `contacts`.

## Block 2: the email

The model writes `subject` and `body`. The code appends:

```
Ting Yu
Jura Solutions · jurasolutions.sg

You're receiving this because <Company> lists this address for business enquiries on <their
site>. Not interested? Unsubscribe here: <link>, or reply "unsubscribe".
```

`<their site>` is the host of the verified source page. The `email` brand channel (links to
jurasolutions.sg only) adds these checks to the core rules:

- under 120 words in the body (excluding signature and footer);
- exactly one link to a live `/apps/<slug>` tool from the site registry (the chosen one), and
  exactly one to `/apps`; no other links (follow-ups: the `/apps` link and at most one tool);
- the signature, the why-you're-receiving line with this company's name, the unsubscribe link
  and `or reply "unsubscribe"`;
- a subject that isn't empty and has no `Re:`/`Fwd:` (questions and sentence case are core
  rules 5 and 8);
- a first line that names the company (its name or first distinctive word) or uses a keyword
  from its observations (follow-ups may instead refer back to the first email);
- no unsubscribe text in the body itself;
- no guesses about the company's people or workload ("stretched thin", "short-staffed",
  "overworked", "struggling", "your last admin left"). A public job posting may be mentioned
  as a plain fact, never linked (PRD §5.2a point 5).

The gate sees the footer with the recipient's site masked as "its website", because the email
channel allows jurasolutions.sg links only and the site name is code-generated from the
verified page. The gate runs at queue time (one regeneration, then the item drops) and again
at send time on the exact text sent.

**Unsubscribe token** (must match the website):

```
email_hash = sha256(email.strip().lower()) as lowercase hex      (suppression.email_hash)
sig        = base64url(HMAC-SHA256(key=UNSUBSCRIBE_SECRET, msg=email_hash)) without "=" padding
token      = f"{email_hash}.{sig}"
url        = https://jurasolutions.sg/unsubscribe?t=<token>
```

Test vector (`tests/test_outreach_email.py`): email `info@acme-aircon.sg`, secret
`jura-test-secret-2026` gives
`3e7f8903444b297047849d51c51d0872460db95817c314d72ea201f381258ba8.EP0Tuk-Ys4HLJC8W75A3xVyxnI3_pNqXpJlcQGS38ns`.

Headers on every live send: `List-Unsubscribe: <url>, <mailto:info@jurasolutions.sg?subject=unsubscribe>`
and `List-Unsubscribe-Post: List-Unsubscribe=One-Click`. HTML is built from the text:
paragraphs, jurasolutions.sg links with `utm_source=outreach&utm_medium=email&utm_campaign=scout`
(never on the unsubscribe link, never on another site), no images, no tracking pixel. The plain
text keeps clean links.

In shadow mode without `UNSUBSCRIBE_SECRET`, the link carries a visible placeholder
signature. Live mode refuses to start without the secret, and every email is recomposed from
its draft at send time, so the real token is always the one sent.

## Blocks 3 and 4: sending

`outreach send-due`, in order:

1. Pause flags (outreach, all, the PAUSE file).
2. Window: 09:30–16:30 SGT, business days from `config/sg-public-holidays.yaml`. Outside it,
   nothing. Queued email simply waits, so whatever is unsent at 16:30 rolls to the next
   business day.
3. Mode: `shadow` (default) or `live`. Live refuses, with one `#alerts` post a day listing
   every reason, unless `mode: live`, `legal_review_done: true`, `sending_domain` is
   jurasolutions.sg or a subdomain, `RESEND_API_KEY_OUTREACH` and `UNSUBSCRIBE_SECRET` are set,
   `inputs/do-not-contact.csv` exists and D1 is configured.
4. Caps, counted per mode: per day 20, rolling 30 days 600, rolling 365 days 8,000, warm-up
   (5 a day for days 1–7, 10 for days 8–14, then 20, from the first send in that mode), one
   email per run. Config may lower any of them. In live mode `send.warmup_start` can only
   delay the warm-up: it counts from the later of that date and the first live send, so a
   date in the past changes nothing. A live send also needs 10 minutes since the last live
   send (`caps.OUTREACH_MINUTES_BETWEEN_LIVE_SENDS`, counted in whole clock minutes, not
   configurable), so calling `send-due` back to back can't send twice. Shadow sends have no
   gap. Each `send-due` holds `data/growth/locks/outreach-send.lock` from these checks to the
   record of the send, so a second one started meanwhile skips and the gap and caps hold for
   parallel calls too.
5. Random spacing: this slot sends with probability `min(quota left, emails due) ÷ slots
   left`. The last slot is certain, so the day's quota goes out, spread across the window.
6. D1 suppression sync. A failed sync pauses outreach. No D1: a logged warning in shadow, a
   refusal in live.
7. Per message: suppression (address and domain), do-not-contact, `contacted_domains`, one
   first email and one follow-up per company ever (counted on live sends; a unique index also
   keeps one active first email per company), the brand gate again.
8. Shadow: status `shadow`, posted to `#outreach-sent` as **SHADOW** with the subject and body;
   Resend is never called, and nothing goes into `contacted_domains` (no one was contacted). Live: `POST https://api.resend.com/emails` with the outreach key,
   from `"Ting Yu, Jura Solutions" <tingyu@<sending_domain>>`, Reply-To
   info@jurasolutions.sg, text and HTML, the unsubscribe headers and an `Idempotency-Key`; the
   domain goes into `contacted_domains`; `#outreach-sent` gets the domain, subject and first
   line.

Resend 401/403, quota 429 and domain 422 errors pause outreach. 5xx and rate limits retry
(the message fails after three tries). Other 4xx errors fail the message.

### After the shadow trial: requeue-shadow

A shadow email was never delivered, so its company was never contacted.
`jura-growth outreach requeue-shadow` turns shadow first emails back into queued live
candidates:

- It refuses unless live sending is ready (`outreach status` shows every pre-condition
  holding), so it can't run in shadow mode.
- It leaves alone any company that is suppressed (address or domain), on the do-not-contact
  list, in `contacted_domains`, finished (replied, unsubscribed ...), already holding an
  active first email, or whose email fails the brand check as it stands now (for example its
  tool was unpublished). Each is listed with the reason.
- The shadow row keeps its record (mode `shadow`, sent time) with status `requeued`; a new
  queued row (`requeued_from`) is recomposed with the live unsubscribe token and goes through
  the whole send run: window, live caps and warm-up, spacing, the D1 sync, every per-message
  check and the brand gate.
- It is idempotent: a second run finds nothing to requeue.
- `--dry-run` lists what it would do; `--since` and `--lead` narrow it to the emails you
  reviewed and are happy with.

### Sync, replies and follow-ups

- **D1 contract.** The site's `suppression` table is an append-only log with one row per
  event:

  ```sql
  CREATE TABLE suppression (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_hash TEXT NOT NULL,
    email TEXT,
    reason TEXT NOT NULL CHECK (reason IN ('unsubscribe', 'bounce', 'complaint', 'manual')),
    source TEXT NOT NULL,
    resend_email_id TEXT,
    created_at TEXT NOT NULL
  );
  CREATE INDEX suppression_email_hash ON suppression (email_hash);
  ```

  - Every unsubscribe, bounce and complaint inserts a new row, even for an address that is
    already in the table. Rows are never updated or deleted. `AUTOINCREMENT` keeps ids from
    being reused, so the sync's cursor can't skip an event.
  - Sources are unsubscribe-link, unsubscribe-post and resend-webhook. `email` is empty for
    unsubscribes, which only see the hash. `created_at` is for people reading the table; the
    sync doesn't use it.
  - `suppression.sync_from_d1` asks for the rows after the last id it processed (kept in
    `sync_cursors`) and copies each address into the local list. Outreach then acts on every
    event, whether or not the address was already suppressed. It matches `resend_email_id` to
    `outreach_messages.resend_id` (or the hash to `contacts.email_hash`), marks the message
    and lead bounced, complained or unsubscribed, and cancels anything queued. A later,
    weaker event never overwrites a complaint or a bounce on the lead.
  - The local copy, outreach's changes and the cursor move commit together, so each event is
    processed once. A failed sync keeps nothing from the batch, pauses outreach, and the next
    sync tries the batch again.
  - A row without an `id`, as in the old table keyed on `email_hash`, fails the sync, so
    outreach stays paused until the site's table matches this contract.
  - The event the cursor points at must come back from D1 unchanged. If it is missing or
    different, the table was recreated or rewritten behind the cursor and new events could
    sit under old ids, so the sync fails and outreach pauses with an alert. An upsert on an
    older row can't be seen this way, which is why plain inserts are part of the contract.
  - To recover once the site's table is right again, clear the cursor
    (`sqlite3 data/growth/growth.db "DELETE FROM sync_cursors WHERE name = 'd1:suppression'"`)
    and `jura-growth resume outreach`. The next sync replays the whole table once, so an old
    complaint pauses outreach one more time; resume again after it.
  - Start the site's table empty. Copying old rows into it replays them on the first sync
    (Discord posts again, and an old complaint pauses outreach once).
- **Reply detection** (optional; on when `OUTREACH_IMAP_HOST`, `_USER` and `_PASSWORD` are
  set): read-only IMAP (EXAMINE, BODY.PEEK) over the last 45 days. Only replies from
  addresses we emailed count. Stored: lead, contact, received time and a hash of the
  Message-ID. No bodies or subjects are stored. A reply's own text (quoted text removed) is
  read in memory for "unsubscribe", "remove" or "stop", which suppresses the address.
  Auto-replies are ignored. Replies post to `#outreach-replies` and cancel any follow-up.
- **Follow-ups**: only with reply detection on. One per company, at least 5 business days
  after a live first email with no reply. `outreach follow-ups-due` lists them; the 09:00
  session writes and queues them; the reply check runs again just before each follow-up goes.
- **Retention**: leads that never replied are deleted 24 months after they were found (their
  contacts and messages go too); the domain stays in `contacted_domains`. Suppression is kept
  indefinitely.

### Auto-pause (§5.7)

Outreach pauses and posts to `#alerts` on any complaint, including one from an address that
had already unsubscribed; a bounce rate above 3% over the last
50 live sends (the denominator stays 50 while there are fewer, so two bounces pause; checked
when a new bounce arrives); two brand-check failures in a row (counted since the last resume, so
an email that fails its regeneration pauses outreach); any Resend auth, quota or domain error;
a failed suppression sync. `jura-growth resume outreach` restarts it.

### Digest figures

`emails_sent`, `emails_shadow`, `replies`, `unsubscribes`, `bounces`, `complaints`,
`emails_queued`, `leads_added`, `leads_form_only`, a line listing today's form-only leads, the
day's ranking ("Scout ranked 20 candidates and kept 7 (shortlist 10)") and one line per kept
lead with its comparison and strongest hiring evidence.

## Setup

### Before shadow mode (blocks 1–3)

1. Edit `outputs/growth/setup/icp-draft.md` and move it to `inputs/icp.md`. Keep the
   `## Industries` bullets: they drive the rotation.
2. Create `inputs/do-not-contact.csv` from `outputs/growth/setup/do-not-contact.example.csv`
   (header `company,domain,reason`). Optional in shadow, required for live.
3. Make sure the site registry exists with live tools
   (`<JURA_SITE_REPO>/src/apps/registry.json`, default `jurasolutions/repos/landing-page`;
   the landing-page repo must have the toolbox merged or checked out). Without live tools,
   leads are recorded but no email is queued. Check with `jura-growth scout tools`.
4. Discord webhooks for `#scout-leads`, `#outreach-sent`, `#outreach-replies` and `#alerts`
   (until then posts go to `data/growth/discord-outbox/`).
5. Optional but recommended: the D1 secrets, so unsubscribes from shadow testing sync.
6. `jura-growth schedule install scout-research scout-send scout-sync`.
7. Run three business days. Read `#outreach-sent`, `outreach queue-list --all` and
   `outreach preview <id>`; tune `inputs/icp.md`, `prompts/scout.md` or `config/scout.yaml`.

### Go-live checklist (block 4)

- [ ] A Singapore lawyer's view on the Spam Control Act's address-harvesting provision (PRD
      open question 1). Then `legal_review_done: true`.
- [ ] Sending domain decided (open question 2), verified in Resend (SPF, DKIM, DMARC), and set
      as `sending_domain`.
- [ ] `RESEND_API_KEY_OUTREACH`: a sending-only key for that domain.
- [ ] `UNSUBSCRIBE_SECRET` set to exactly the website's value. Check one link:
      `jura-growth outreach unsubscribe-link you@yourdomain` and open it; the next
      `outreach sync` should show the unsubscribe.
- [ ] The site's `/unsubscribe` page and function, `/api/resend-webhook` (bounced, complained,
      signature-verified), D1 `suppression` table (append-only, as in the D1 contract above)
      and the privacy notice are live.
- [ ] `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `D1_DATABASE_ID` set;
      `jura-growth outreach sync` reports suppressions without an error.
- [ ] `inputs/do-not-contact.csv` exists.
- [ ] Open question 5: decide whether the footer shows a registered business name and UEN
      (not built in; the footer would need a code change).
- [ ] Optional: `OUTREACH_IMAP_*` for reply detection and follow-ups (open question 3).
- [ ] `jura-growth outreach status` shows "every pre-condition holds" once `mode: live` is set.
- [ ] After the shadow trial, review and requeue the shadow emails you're happy with:
      `jura-growth outreach queue-list --all` and `outreach preview <id>` to review, then
      `jura-growth outreach requeue-shadow --dry-run`, then run it for real (narrow it with
      `--lead ID` or `--since YYYY-MM-DD`). They go out under the live warm-up caps.
- [ ] Watch the first live day: at most 5 sends, spread across the window. Test a complaint
      from Resend's dashboard or a test webhook: outreach pauses; `jura-growth resume outreach`.

## Tests

`uv run pytest tests/test_scout*.py tests/test_outreach*.py`. No network: page fetches, DNS,
Resend (httpx MockTransport), Cloudflare (MockTransport) and IMAP (a fake class) are replaced;
the clock is frozen with `JURA_GROWTH_NOW`; `inputs/` and the site repo point at temporary
folders.
