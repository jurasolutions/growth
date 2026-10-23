"""Reading and validating app PRDs against `prd/templates/prd-app-template.md`.

Two levels:

- `validate_shape(text)`: the template's shape. Header lines, Tier and
  Category values, the "To build:" line, sections 1 to 7 with their headings,
  the always-include success criteria, the copy and technical parts, and the
  sign-off gate sentence. The hand-written APP-001 and APP-002 pass this.

- `validate_factory(text, ctx)`: what a PRD written by the daily factory must
  also meet before `jura-growth apps submit-prd` files it: the template's
  exact author and wording, the next APP number, today's date, a new slug and
  name, a plain sentence-case name, the guardrails (as far as code can check
  them) and an "Official sources" line with a URL and a date checked whenever
  a rule is relied on.

The brand checker runs separately (`copy_items()` feeds it), so a structural
failure never uses up the item's one regeneration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from jura_growth import brand_check, copy_check

FACTORY_PRD = "prd/pending/prd-jura-app-factory-2026-10-24.md"
FACTORY_AUTHOR = "app factory (for Ting Yu)"
CATEGORIES = ("Sales", "Finance", "Admin", "HR", "Marketing", "Documents")
TIERS = ("browser", "ai")
GATE_SENTENCE = "Do not start building. This PRD requires explicit sign-off"
GATE_SENTENCE_FULL = "**Do not start building. This PRD requires explicit sign-off before any code is written.**"

SECTIONS: list[tuple[str, list[str]]] = [
    ("1. Problem", []),
    ("2. Success criteria", []),
    ("3. Scope", ["In scope", "Out of scope"]),
    ("4. Constraints", []),
    ("5. Proposed plan", ["5.1 User flow", "5.2 Copy", "5.3 Technical", "5.4 Done-check"]),
    ("6. Open questions", []),
    ("7. Sign-off", []),
]

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
H1_RE = re.compile(r"^# PRD — APP-(?P<num>\d{3}) (?P<name>\S.*?)\s*$")
DOMAIN_RE = re.compile(
    r"^\*Domain: `jurasolutions/` \| Created: (?P<created>\d{4}-\d{2}-\d{2}) \| Author: (?P<author>[^*|]+?)\*$"
)
STATUS_RE = re.compile(r"^\*Status: \*\*PENDING SIGN-OFF\*\* \| Tier: (?P<tier>[^|*]+?) \| Category: (?P<category>[^|*]+?)\*$")
FOLLOWS_RE = re.compile(r"^\*Follows: `(?P<follows>[^`]+)`(?: \([^)]*\))?\.?\*$")
BUILD_RE = re.compile(
    r"^\*To build: \"approved, build (?P<path>prd/pending/apps/prd-app-(?P<num>\d{3})-(?P<slug>[a-z0-9-]+?)-(?P<day>\d{4}-\d{2}-\d{2})\.md)\"\*$"
)
FILENAME_RE = re.compile(r"^prd-app-(?P<num>\d{3,})-(?P<slug>[a-z0-9-]+?)-(?P<day>\d{4}-\d{2}-\d{2})\.md$")

# Always-include success criteria (template §2): each needs these phrases.
ALWAYS_CRITERIA = [
    ("360 px and desktop, 44 px tap targets", [r"360\s*px", r"44\s*px"]),
    ("keyboard usable, every input labelled", [r"keyboard usable", r"every input labell?ed"]),
    ("all copy passes `jura-growth check`", [r"jura-growth check"]),
    ("talk-to-us card links to the enquiry form with `?from=apps/<slug>`", [r"\?from=apps/{slug}\b"]),
    ("usage counter increments on open and on completion", [r"usage counter increments on open"]),
]
STRICT_CRITERIA = [("contrast passes the design system's tokens", [r"contrast"])]


@dataclass
class Bullet:
    label: str  # the bold label, "" when there is none
    text: str  # everything after the label, continuation lines joined


@dataclass
class AppPrd:
    text: str
    number: int | None = None
    name: str = ""
    created: str = ""
    author: str = ""
    tier: str = ""
    category: str = ""
    follows: str = ""
    build_path: str = ""
    slug: str = ""
    sections: dict[str, str] = field(default_factory=dict)  # "## " heading -> body
    subsections: dict[str, str] = field(default_factory=dict)  # "### " heading -> body
    order: list[tuple[int, str]] = field(default_factory=list)  # (level, heading) as found

    @property
    def app_id(self) -> str:
        return f"APP-{self.number:03d}" if self.number is not None else ""

    @property
    def filename(self) -> str:
        return Path(self.build_path).name if self.build_path else ""

    def bullets(self, heading: str) -> list[Bullet]:
        body = self.sections.get(heading) or self.subsections.get(heading) or ""
        return parse_bullets(body)

    def bullet(self, heading: str, label: str) -> Bullet | None:
        wanted = label.lower()
        for b in self.bullets(heading):
            if b.label.lower().startswith(wanted):
                return b
        return None

    @property
    def one_line(self) -> str:
        b = self.bullet("1. Problem", "One line")
        return b.text if b else ""

    @property
    def who(self) -> str:
        b = self.bullet("1. Problem", "Who has this problem")
        return b.text if b else ""

    @property
    def why(self) -> str:
        b = self.bullet("1. Problem", "Why it helps Jura")
        return b.text if b else ""

    @property
    def official_sources(self) -> str:
        b = self.bullet("4. Constraints", "Official sources")
        return b.text if b else ""

    @property
    def privacy(self) -> str:
        b = self.bullet("4. Constraints", "Privacy")
        return b.text if b else ""

    def criteria(self) -> list[str]:
        return [b.text for b in parse_bullets(self.sections.get("2. Success criteria", ""), checkbox=True)]

    def copy(self) -> list[copy_check.Item]:
        return copy_items(self.subsections.get("5.2 Copy", ""))

    def copy_value(self, label: str) -> str | None:
        wanted = label.lower()
        for item in self.copy():
            if item.where.lower() == wanted:
                return item.text
        return None

    def registry_entry(self) -> dict[str, str]:
        b = self.bullet("5.3 Technical", "Registry entry")
        if not b:
            return {}
        return dict(re.findall(r"\b(\w+):\s*\"([^\"]*)\"", b.text))


# --- parsing ---------------------------------------------------------------


def parse(text: str) -> AppPrd:
    prd = AppPrd(text=text)
    lines = text.splitlines()
    header, body_start = _header(lines)
    for line in header:
        if m := H1_RE.match(line):
            prd.number, prd.name = int(m["num"]), m["name"].strip()
        elif m := DOMAIN_RE.match(line):
            prd.created, prd.author = m["created"], m["author"].strip()
        elif m := STATUS_RE.match(line):
            prd.tier, prd.category = m["tier"].strip(), m["category"].strip()
        elif m := FOLLOWS_RE.match(line):
            prd.follows = m["follows"]
        elif m := BUILD_RE.match(line):
            prd.build_path, prd.slug = m["path"], m["slug"]

    current_h2 = current_h3 = None
    buffer: list[str] = []

    def flush() -> None:
        content = "\n".join(buffer).strip("\n")
        if current_h3 is not None:
            prd.subsections[current_h3] = content
        elif current_h2 is not None:
            prd.sections[current_h2] = content

    in_fence = False
    for line in lines[body_start:]:
        if line.strip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and line.startswith("## "):
            flush()
            current_h2, current_h3, buffer = line[3:].strip(), None, []
            prd.order.append((2, current_h2))
            continue
        if not in_fence and line.startswith("### "):
            flush()
            current_h3, buffer = line[4:].strip(), []
            prd.order.append((3, current_h3))
            continue
        buffer.append(line)
    flush()
    # A section's own text is what comes before its first subsection; give
    # sections with subsections their full text too, for scanning.
    for heading, subs in SECTIONS:
        if subs and heading in prd.sections:
            prd.sections[heading] += "\n" + "\n".join(prd.subsections.get(s, "") for s in subs)
    return prd


def _header(lines: list[str]) -> tuple[list[str], int]:
    for index, line in enumerate(lines):
        if line.strip() == "---":
            return [l for l in lines[:index] if l.strip()], index + 1
    return [l for l in lines if l.strip() and not l.startswith("#" * 2)][:5], 0


def parse_bullets(body: str, *, checkbox: bool = False) -> list[Bullet]:
    """Top-level `- ` bullets, with indented continuation lines joined."""
    bullets: list[list[str]] = []
    for line in body.splitlines():
        if re.match(r"^- ", line):
            bullets.append([line[2:].strip()])
        elif bullets and (line.startswith(" ") or line.startswith("\t")) and line.strip():
            bullets[-1].append(line.strip())
        elif not line.strip():
            continue
        else:
            bullets.append(["\x00" + line.strip()])  # loose text, not a bullet
    found = []
    for parts in bullets:
        joined = " ".join(parts)
        if joined.startswith("\x00"):
            continue
        if checkbox:
            m = re.match(r"^\[[ xX]\]\s+(.*)$", joined)
            if not m:
                continue
            joined = m.group(1)
        m = re.match(r"^\*\*(?P<label>[^*]+?):?\*\*:?\s*(?P<rest>.*)$", joined)
        if m:
            found.append(Bullet(m["label"].rstrip(":").strip(), m["rest"].strip()))
        else:
            found.append(Bullet("", joined))
    return found


def copy_items(section: str) -> list[copy_check.Item]:
    """Every quoted string in a §5.2 Copy section, for the brand checker.

    `copy_check.items_from_markdown` reads one line per bullet and gives every
    string the bullet's label. App PRDs wrap long bullets and pack a card's
    heading, body and button into one bullet, so this unwraps each bullet and
    splits it into one labelled bullet per string first, then hands the result
    to `copy_check` so the heading and body rules stay the core's.
    """
    normalised = []
    for bullet in parse_bullets(section):
        label, rest = (bullet.label, bullet.text) if bullet.label else _split_label(bullet.text)
        if not label:
            continue
        for sub, quoted in _quoted_with_labels(rest):
            full = f"{label} {sub}".strip() if sub else label
            normalised.append(f'- {full}: "{quoted}"')
    if not normalised:
        return []
    return copy_check.items_from_markdown("### 5.2 Copy\n" + "\n".join(normalised) + "\n### end\n")


def _split_label(text: str) -> tuple[str, str]:
    m = re.match(r"^(?P<label>[^:\"“]+):\s*(?P<rest>.+)$", text)
    return (m["label"].strip(), m["rest"]) if m else ("", text)


def _quoted_with_labels(rest: str) -> list[tuple[str, str]]:
    found = []
    for m in re.finditer(r"(?P<pre>[^\"“]*?)[\"“](?P<q>[^\"”]*)[\"”]", rest):
        pre = re.sub(r"[^A-Za-z -]", " ", m["pre"]).strip()
        pre = re.sub(r"\s+", " ", pre)
        found.append((pre, m["q"].strip()))
    return [(sub, q) for sub, q in found if q]


def slugify(name: str) -> str:
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", name.lower())).strip("-")


def normalise_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


# --- shape -----------------------------------------------------------------


def validate_shape(text: str, *, strict: bool = False, categories: tuple[str, ...] = CATEGORIES) -> list[str]:
    """Problems with the template's shape. Empty means the shape is right."""
    prd = parse(text)
    errors: list[str] = []
    lines = text.splitlines()
    header, _ = _header(lines)

    # header lines, in order
    expected = [
        ("title line `# PRD — APP-NNN <Tool name>`", H1_RE),
        ("`*Domain: `jurasolutions/` | Created: YYYY-MM-DD | Author: …*`", DOMAIN_RE),
        ("`*Status: **PENDING SIGN-OFF** | Tier: … | Category: …*`", STATUS_RE),
        (f"`*Follows: `{FACTORY_PRD}` (…).*`", FOLLOWS_RE),
        ('`*To build: "approved, build prd/pending/apps/prd-app-NNN-<slug>-YYYY-MM-DD.md"*`', BUILD_RE),
    ]
    if len(header) != len(expected):
        errors.append(f"header: expected {len(expected)} lines before `---`, found {len(header)}")
    for index, (label, pattern) in enumerate(expected):
        if index >= len(header) or not pattern.match(header[index]):
            errors.append(f"header line {index + 1}: expected {label}")
    if "---" not in [l.strip() for l in lines]:
        errors.append("header: missing the `---` rule after the header")

    if prd.tier and prd.tier not in TIERS:
        errors.append(f"header: Tier must be browser or ai, not {prd.tier!r}")
    if prd.category and prd.category not in categories:
        errors.append(f"header: Category must be one of {', '.join(categories)}, not {prd.category!r}")
    if prd.follows and prd.follows != FACTORY_PRD:
        errors.append(f"header: Follows must name `{FACTORY_PRD}`")
    if strict and prd.author and prd.author != FACTORY_AUTHOR:
        errors.append(f"header: Author must be `{FACTORY_AUTHOR}`")
    if prd.build_path:
        m = BUILD_RE.match(f'*To build: "approved, build {prd.build_path}"*')
        if prd.number is not None and int(m["num"]) != prd.number:
            errors.append(f"header: the To build path says APP-{m['num']} but the title says {prd.app_id}")
        if prd.created and m["day"] != prd.created:
            errors.append(f"header: the To build path is dated {m['day']} but Created is {prd.created}")
        if prd.name and prd.slug != slugify(prd.name):
            errors.append(f"header: slug {prd.slug!r} should be {slugify(prd.name)!r}, made from the name")
    if prd.created:
        try:
            date.fromisoformat(prd.created)
        except ValueError:
            errors.append(f"header: Created {prd.created!r} is not a date")

    errors += _sections(prd)
    if errors and not prd.sections:
        return errors
    errors += _problem(prd, strict)
    errors += _criteria(prd, strict)
    errors += _scope(prd)
    errors += _constraints(prd, strict)
    errors += _plan(prd, strict)
    errors += _signoff(prd, strict)
    return errors


def _sections(prd: AppPrd) -> list[str]:
    errors = []
    found_h2 = [h for level, h in prd.order if level == 2]
    wanted_h2 = [h for h, _ in SECTIONS]
    if found_h2 != wanted_h2:
        errors.append(
            "sections: expected exactly " + ", ".join(f"`## {h}`" for h in wanted_h2)
            + " in order; found " + (", ".join(f"`## {h}`" for h in found_h2) or "none")
        )
    current = None
    found_h3: dict[str, list[str]] = {}
    for level, heading in prd.order:
        if level == 2:
            current = heading
            found_h3.setdefault(current, [])
        elif current is not None:
            found_h3[current].append(heading)
    for heading, subs in SECTIONS:
        if heading in found_h3 and found_h3[heading] != subs:
            want = ", ".join(f"`### {s}`" for s in subs) or "no subsections"
            errors.append(f"section {heading}: expected {want}; found " + (", ".join(f"`### {s}`" for s in found_h3[heading]) or "none"))
    for heading, subs in SECTIONS:
        body = prd.subsections if subs else prd.sections
        for name in subs or [heading]:
            if name in body and not _meaningful(body[name]):
                errors.append(f"section {name}: is empty")
    return errors


def _meaningful(body: str) -> bool:
    stripped = re.sub(r"<[^>]+>", "", body).strip()
    return bool(re.search(r"[A-Za-z]{2}", stripped))


def _problem(prd: AppPrd, strict: bool) -> list[str]:
    errors = []
    bullets = prd.bullets("1. Problem")
    labels = [b.label for b in bullets]
    for wanted in ("One line", "Who has this problem", "Why it helps Jura"):
        if not any(l.lower().startswith(wanted.lower()) for l in labels):
            errors.append(f"§1: missing the **{wanted}:** bullet")
    if strict and len(bullets) != 3:
        errors.append(f"§1: expected exactly the three template bullets, found {len(bullets)}")
    one = prd.bullet("1. Problem", "One line")
    if one and strict and one.label.lower() != "one line (also the page subtitle)":
        errors.append("§1: the label must be **One line (also the page subtitle):**")
    if one and not one.text:
        errors.append("§1: the one line is empty")
    why = prd.why
    if why and re.search(r"\d", why):
        errors.append("§1: Why it helps Jura must carry no figures")
    if strict and why:
        count = len([s for s in brand_check.sentences(why) if re.search(r"[A-Za-z]", s)])
        if not 2 <= count <= 3:
            errors.append(f"§1: Why it helps Jura should be 2–3 sentences, found {count}")
    return errors


def _criteria(prd: AppPrd, strict: bool) -> list[str]:
    errors = []
    criteria = prd.criteria()
    if not criteria:
        return ["§2: no `- [ ]` acceptance criteria"]
    joined = "\n".join(criteria)
    wanted = ALWAYS_CRITERIA + (STRICT_CRITERIA if strict else [])
    always_hits = set()
    for label, patterns in wanted:
        compiled = [re.compile(p.replace("{slug}", re.escape(prd.slug or "<slug>")), re.I) for p in patterns]
        if not all(c.search(joined) for c in compiled):
            errors.append(f"§2: missing the always-include criterion: {label}")
        for index, criterion in enumerate(criteria):
            if any(c.search(criterion) for c in compiled):
                always_hits.add(index)
    specific = len(criteria) - len(always_hits)
    if specific < 2:
        errors.append(f"§2: needs at least 2 tool-specific criteria, found {specific}")
    return errors


def _scope(prd: AppPrd) -> list[str]:
    errors = []
    for name in ("In scope", "Out of scope"):
        if name in prd.subsections and not parse_bullets(prd.subsections[name]):
            errors.append(f"§3 {name}: needs at least one bullet")
    return errors


def _constraints(prd: AppPrd, strict: bool) -> list[str]:
    errors = []
    labels = [b.label.lower() for b in prd.bullets("4. Constraints")]
    required = ["Official sources", "Privacy"] + (["Tier rules"] if strict else [])
    for wanted in required:
        if wanted.lower() not in labels:
            errors.append(f"§4: missing the **{wanted}:** bullet")
    if strict and not re.search(r"design system only", prd.sections.get("4. Constraints", ""), re.I):
        errors.append("§4: missing the \"Design system only\" constraint")
    if strict and prd.privacy:
        if prd.tier == "browser" and not re.search(r"stays in (?:your|the visitor's) browser", prd.privacy, re.I):
            errors.append("§4 Privacy: a browser tool must say it \"stays in your browser\"")
        if prd.tier == "ai" and not re.search(r"discard|not stored|n't store|not store|nothing (?:is )?stored", prd.privacy, re.I):
            errors.append("§4 Privacy: an AI tool must say uploads are discarded and nothing is stored")
    return errors


def _plan(prd: AppPrd, strict: bool) -> list[str]:
    errors = []
    flow = prd.subsections.get("5.1 User flow", "")
    steps = re.findall(r"^\d+\.\s+\S", flow, re.M)
    if "5.1 User flow" in prd.subsections and len(steps) < 2:
        errors.append("§5.1: the user flow needs numbered steps")
    if strict and prd.slug and f"/apps/{prd.slug}" not in flow:
        errors.append(f"§5.1: the flow should start from `/apps/{prd.slug}`")

    copy = prd.copy()
    labels = [item.where.lower() for item in copy]
    if "5.2 Copy" in prd.subsections:
        for wanted in ("title", "subtitle", "privacy note"):
            if wanted not in labels:
                errors.append(f"§5.2: missing the {wanted} string")
        if not any(l.startswith("button") for l in labels):
            errors.append("§5.2: missing the button labels")
        for part in ("heading", "body", "button"):
            if not any(l.startswith("talk-to-us card") and l.endswith(part) for l in labels):
                errors.append(f"§5.2: the talk-to-us card needs a {part}")
        title = prd.copy_value("Title")
        if title is not None and prd.name and title != prd.name:
            errors.append(f"§5.2: Title {title!r} should be the tool name {prd.name!r}")
        subtitle = prd.copy_value("Subtitle")
        if subtitle is not None and prd.one_line and _flat(subtitle) != _flat(prd.one_line):
            errors.append("§5.2: Subtitle should be the §1 one line, word for word")
        if prd.tier == "ai" and not any(re.search(r"tries|limit", l) for l in labels):
            errors.append("§5.2: an AI tool needs the try-limit messages")
        if strict:
            body = next((i.text for i in copy if i.where.lower() == "talk-to-us card body"), "")
            if body and len(brand_check.sentences(body)) != 1:
                errors.append("§5.2: the talk-to-us card body should be one sentence")

    tech = prd.subsections.get("5.3 Technical", "")
    if "5.3 Technical" in prd.subsections:
        folder = prd.bullet("5.3 Technical", "Folder")
        if not folder:
            errors.append("§5.3: missing the **Folder:** bullet")
        elif prd.slug and f"src/apps/{prd.slug}/" not in folder.text:
            errors.append(f"§5.3: Folder should be `src/apps/{prd.slug}/`")
        entry = prd.registry_entry()
        if not entry:
            errors.append("§5.3: missing the **Registry entry:** bullet")
        else:
            want = {"slug": prd.slug, "name": prd.name, "category": prd.category, "tier": prd.tier, "status": "live", "prd": prd.app_id}
            for key, value in want.items():
                if value and entry.get(key) != value:
                    errors.append(f"§5.3: registry entry {key} should be {value!r}, found {entry.get(key)!r}")
            if not entry.get("description"):
                errors.append("§5.3: registry entry needs a description")
        if strict:
            for wanted in ("Dependencies", "State"):
                if not prd.bullet("5.3 Technical", wanted):
                    errors.append(f"§5.3: missing the **{wanted}:** bullet")
        if prd.tier == "ai":
            needs = [
                (rf"functions/api/apps/{re.escape(prd.slug)}\b", f"the function path `functions/api/apps/{prd.slug}`"),
                (r"max_tokens", "`max_tokens`"),
                (r"claude-haiku-5-5", "the model `claude-haiku-5-5`"),
                (r"system prompt", "the full system prompt"),
                (r"schema", "the output schema"),
            ]
            for pattern, label in needs:
                if not re.search(pattern, tech, re.I):
                    errors.append(f"§5.3: an AI tool must give {label}")
    return errors


def _signoff(prd: AppPrd, strict: bool) -> list[str]:
    errors = []
    body = prd.sections.get("7. Sign-off", "")
    if "7. Sign-off" not in prd.sections:
        return errors
    if GATE_SENTENCE not in body:
        errors.append(f"§7: missing the sign-off gate sentence \"{GATE_SENTENCE}.\"")
    elif strict and GATE_SENTENCE_FULL not in body:
        errors.append(f"§7: use the template's gate sentence exactly: {GATE_SENTENCE_FULL}")
    if strict:
        if prd.build_path and f'reply "approved, build {prd.build_path}"' not in body:
            errors.append(f'§7: should say To proceed: reply "approved, build {prd.build_path}"')
        if not re.search(r"^Signed off by: _+\s+Date: _+\s*$", body, re.M):
            errors.append("§7: missing the `Signed off by: ____  Date: ____` line")
    return errors


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().rstrip(".").lower()


# --- factory rules ---------------------------------------------------------


@dataclass
class FactoryContext:
    today: str
    next_number: int
    taken_slugs: dict[str, str]  # slug -> where it is taken ("live", "APP-001 pending", ...)
    taken_names: dict[str, str]  # normalised name -> where
    official_domains: tuple[str, ...] = ()
    source_max_age_days: int = 7
    fetched_urls: list[str] | None = None  # successful WebFetch URLs in this run; None = not checked
    name_words: tuple[str, ...] = ()
    banned_name_words: tuple[str, ...] = ()
    categories: tuple[str, ...] = CATEGORIES


GUARDRAILS = {
    "legal advice": r"legal advice|legal opinion|\blawyers?\b|solicitors?|will (?:writer|maker)|litigation|\bsue\b|court claims?",
    "medical advice": r"medical(?! (?:leave|certificates?|claims?))|diagnos\w*|symptoms?|prescri\w*|dosage|treatment plans?|health advice|clinical advice",
    "financial advice": r"financial advice|investment|invest(?:ing)? advice|stock (?:picks?|tips?)|portfolio|trading signals?|crypto\w*|loan eligibility|credit scores?|retirement planning|insurance (?:advice|recommendations?)|tax advice|tax planning|financial planning",
    "imitating a government service": r"official (?:form|document|certificate|receipt|letter|notice)s?|government[- ]approved|approved by (?:IRAS|MOM|CPF|ACRA|MAS)|endorsed by|on behalf of (?:IRAS|MOM|CPF|ACRA|MAS|the government)|submit(?:s|ted)? (?:it |them )?(?:directly )?to (?:IRAS|MOM|CPF|ACRA|MAS)|e-?filing|singpass|corppass|bizfile|myinfo",
    "accounts or third-party logins": r"sign[- ]?in|log[- ]?in|sign[- ]?up|create an account|user accounts?|oauth|third[- ]party logins?|connect (?:your|to) (?:google|xero|quickbooks|facebook|instagram|shopify|bank|stripe)",
    "stored customer data": r"(?:save|store)s? (?:it|them|the \w+|their \w+|customer \w+)? ?(?:on|in) (?:our|the|jura's) (?:server|database)s?|customer database",
}
GOVERNMENT_NAME = re.compile(r"\b(?:IRAS|MOM|CPF|ACRA|MAS|HDB|ICA|gov|government|official|ministry|e-?filing|singpass|corppass)\b", re.I)
NEGATION = re.compile(r"\b(?:no|not|never|without|nothing|none|n't|isn't|doesn't|don't|won't)\b[^.;]{0,30}$", re.I)
STATUTORY = re.compile(
    r"\b(?:GST|CPF|SDL|levy|levies|income tax|stamp duty|withholding tax|property tax|contribution rates?|"
    r"IRAS|MOM|CPF Board|ACRA|MAS|statutory|public holidays?|minimum wage|overtime pay|leave entitlements?|"
    r"PayNow|SGQR|itemised payslip|Employment Act)\b",
    re.I,
)
STATUTORY_CALCULATION = re.compile(
    r"\b(?:CPF|SDL|levy|levies|income tax|stamp duty|withholding tax|property tax|contributions?|overtime pay)\b", re.I
)
CALCULATOR = re.compile(r"calculat\w*|checker|estimat\w*|work(?:s|ing)? out|how much", re.I)
DATE_RES = [
    (re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"), "%Y-%m-%d"),
    (re.compile(r"\b(\d{1,2} (?:January|February|March|April|May|June|July|August|September|October|November|December) \d{4})\b"), "%d %B %Y"),
]


def validate_factory(text: str, ctx: FactoryContext) -> list[str]:
    """Shape (strict) plus the factory's own rules. Empty means file it."""
    errors = validate_shape(text, strict=True, categories=ctx.categories)
    prd = parse(text)
    if prd.number is None or not prd.slug:
        return errors

    wanted = f"APP-{ctx.next_number:03d}"
    if prd.app_id != wanted:
        errors.append(f"numbering: this must be {wanted}, the next free number (found {prd.app_id})")
    if prd.created != ctx.today:
        errors.append(f"date: Created and the file name must be today, {ctx.today} (found {prd.created})")
    if not SLUG_RE.match(prd.slug) or len(prd.slug) > 60:
        errors.append(f"slug: {prd.slug!r} must be lower-case words joined by hyphens, under 60 characters")
    if prd.slug in ctx.taken_slugs:
        errors.append(f"duplicate: the slug {prd.slug!r} is already taken ({ctx.taken_slugs[prd.slug]})")
    taken_name = ctx.taken_names.get(normalise_name(prd.name))
    if taken_name:
        errors.append(f"duplicate: the name {prd.name!r} is already taken ({taken_name})")

    errors += name_problems(prd.name, ctx)
    errors += guardrail_problems(prd)
    errors += source_problems(prd, ctx)
    return errors


def name_problems(name: str, ctx: FactoryContext) -> list[str]:
    errors = []
    words = name.split()
    if not 1 <= len(words) <= 5:
        errors.append(f"name: keep it to a few plain words (found {len(words)})")
    if re.search(r"\d", name):
        errors.append("name: no figures in the name")
    if re.search(r"[^A-Za-z \-]", name):
        errors.append("name: letters, spaces and hyphens only")
    problem = brand_check.sentence_case_problem(name)
    if problem:
        errors.append(f"name: should be sentence case ({problem}), like \"Quote builder\"")
    if GOVERNMENT_NAME.search(name):
        errors.append("name: must not name a government agency or sound official")
    nouns = set(_proper_nouns())
    allowed = {w.lower() for w in ctx.name_words}
    dictionary = _dictionary()
    for index, word in enumerate(words):
        for part in word.split("-"):
            if not part:
                continue
            if part in nouns or (part.isupper() and 2 <= len(part) <= 5):
                continue
            if re.search(r"[a-z][A-Z]", part) or (index > 0 and part[0].isupper()):
                errors.append(f"name: {part!r} reads as an invented brand word; use plain words")
                continue
            lower = part.lower()
            if lower in {w.lower() for w in ctx.banned_name_words}:
                errors.append(f"name: {part!r} is not a plain tool name word")
                continue
            if lower in allowed:
                continue
            if dictionary and not _in_dictionary(lower, dictionary):
                errors.append(f"name: {part!r} is not a plain English word; use plain words, like \"Invoice builder\"")
    return errors


@lru_cache(maxsize=None)
def _proper_nouns() -> tuple[str, ...]:
    from jura_growth import config

    return tuple(config.read_lines("proper_nouns.txt"))


@lru_cache(maxsize=None)
def _dictionary() -> frozenset[str]:
    path = Path("/usr/share/dict/words")
    if not path.exists():
        return frozenset()
    return frozenset(w.strip().lower() for w in path.read_text(encoding="utf-8", errors="ignore").splitlines())


def _in_dictionary(word: str, dictionary: frozenset[str]) -> bool:
    candidates = {word}
    for suffix, replacement in (("ies", "y"), ("ier", "y"), ("es", ""), ("s", ""), ("ers", ""), ("er", ""), ("ing", ""), ("ed", ""), ("ed", "e"), ("er", "e"), ("ing", "e")):
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            candidates.add(word[: -len(suffix)] + replacement)
    return any(c in dictionary for c in candidates)


def scan_text(prd: AppPrd) -> str:
    """What the guardrails read: the name, the one line, in-scope features,
    the user flow and the copy. Out-of-scope lists are left out, since they
    say what the tool won't do."""
    parts = [prd.name, prd.one_line, prd.subsections.get("In scope", ""), prd.subsections.get("5.1 User flow", "")]
    parts += [item.text for item in prd.copy()]
    return "\n".join(parts)


def _hits(pattern: str, text: str) -> list[str]:
    """Whole-word matches of `pattern`, leaving out negated ones ("no sign-in",
    "without an account", "login-free")."""
    found = []
    for m in re.finditer(rf"\b(?:{pattern})\b(?!-free)", text, re.I):
        before = text[max(0, m.start() - 40): m.start()]
        if NEGATION.search(before):
            continue
        found.append(m.group(0))
    return found


def guardrail_problems(prd: AppPrd) -> list[str]:
    errors = []
    text = scan_text(prd)
    tech = prd.subsections.get("5.3 Technical", "")
    for label, pattern in GUARDRAILS.items():
        target = text + ("\n" + tech if label in ("accounts or third-party logins", "stored customer data") else "")
        hits = _hits(pattern, target)
        if hits:
            errors.append(f"guardrail: no {label} tools (found \"{hits[0]}\")")
    if is_statutory_calculator(prd):
        if not any(re.search(r"\bestimates?\b", item.text, re.I) for item in prd.copy()):
            errors.append("guardrail: a statutory calculator must label its result an estimate in the §5.2 copy")
    return errors


def relies_on_rule(prd: AppPrd) -> list[str]:
    """Statutory or official rules the tool appears to depend on."""
    text = "\n".join([prd.name, prd.one_line, prd.subsections.get("In scope", ""), prd.subsections.get("5.3 Technical", "")])
    found: dict[str, str] = {}
    for m in STATUTORY.finditer(text):
        if not NEGATION.search(text[max(0, m.start() - 40): m.start()]):
            found.setdefault(m.group(0).lower(), m.group(0))
    return sorted(found.values(), key=str.lower)


def is_statutory_calculator(prd: AppPrd) -> bool:
    if not relies_on_rule(prd):
        return False
    if CALCULATOR.search(prd.name) or CALCULATOR.search(prd.one_line):
        return True
    # GST on a quote or invoice is the visitor's own rate times their own
    # amounts, so it is a document tool. Working out a contribution, levy or
    # tax is a statutory calculation.
    for bullet in parse_bullets(prd.subsections.get("In scope", "")):
        if CALCULATOR.search(bullet.text) and STATUTORY_CALCULATION.search(bullet.text):
            return True
    return False


FULL_URL = re.compile(r"https?://[^\s<>\"'\[\]`]+", re.I)


def official_urls(text: str) -> list[str]:
    """Full URLs in `text`. Unlike the brand checker's link finder this keeps
    parentheses inside a URL, as IRAS uses ("goods-services-tax-(gst)")."""
    found = []
    for m in FULL_URL.finditer(text):
        url = m.group(0).rstrip(".,;:")
        while url.endswith(")") and url.count("(") < url.count(")"):
            url = url[:-1].rstrip(".,;:")
        found.append(url)
    return found


def is_official(url: str, domains: tuple[str, ...]) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    if host == "gov.sg" or host.endswith(".gov.sg"):
        return True
    return any(host == d or host.endswith("." + d) for d in domains)


def dates_in(text: str) -> list[date]:
    found = []
    for pattern, fmt in DATE_RES:
        for m in pattern.finditer(text):
            try:
                found.append(datetime.strptime(m.group(1), fmt).date())
            except ValueError:
                continue
    return found


def source_problems(prd: AppPrd, ctx: FactoryContext) -> list[str]:
    errors = []
    line = prd.official_sources
    rules = relies_on_rule(prd)
    says_none = bool(re.match(r"^none\b", line.strip(), re.I))
    if says_none:
        explained = re.search(r"\b(?:not|no|only)\b", line[4:], re.I)
        if rules and not explained:
            errors.append(
                "official sources: the tool relies on " + ", ".join(rules)
                + " but the Official sources line says None; cite the official page and the date checked"
            )
        return errors
    if not line:
        return errors  # the shape check already reports the missing bullet
    urls = official_urls(line)
    official = [u for u in urls if is_official(u, ctx.official_domains)]
    if not official:
        errors.append("official sources: cite the official page (IRAS, MOM, CPF Board, MAS or ACRA) as a full https:// URL")
    today = date.fromisoformat(ctx.today)
    checked = [d for d in dates_in(line) if d <= today]
    if not checked:
        errors.append("official sources: give the date you checked the source, as YYYY-MM-DD")
    elif (today - max(checked)).days > ctx.source_max_age_days:
        errors.append(f"official sources: the date checked ({max(checked)}) is more than {ctx.source_max_age_days} days old; check it again today")
    if ctx.fetched_urls is not None:
        fetched = {_url_key(u) for u in ctx.fetched_urls}
        for url in official:
            if _url_key(url) not in fetched:
                errors.append(f"official sources: {url} was not fetched in this run; open it with WebFetch and confirm the rule before citing it")
    return errors


def _url_key(url: str) -> str:
    parts = urlsplit(url if re.match(r"^https?://", url, re.I) else f"https://{url}")
    host = (parts.hostname or "").lower().removeprefix("www.")
    return f"{host}{parts.path.rstrip('/')}"
