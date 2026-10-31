"""What a watch run may record, and what its records come to (inbox watch PRD W2, W3, W5, S4; ADR 0006).

A watch run reads pages full of text anyone can write, so nothing it says is believed on its way in:

- `observe` takes a JSON list from a file in the run's scratch folder (N1). Every field is checked
  and a refusal gives a fixed reason, never what it was given. A person whose address is a look-alike
  is kept with no address (A10). A count that isn't a sane whole number changes nothing (A13).
- A message is **held** as `observed` until the run's checks: its text must appear in what a page
  returned to that run, within one result and with its lines together, or it is `unverified`, reported
  as such with no draft (N3). A tab's address or title isn't a page's words. A run that was killed
  never reached its checks, so what it recorded is unverified too. Held items go neither to a report
  nor to triage.
- A surface counts as read only if the run said so, read a page on that platform and passed its audit
  (F13). Anything else has failed, which is different from a quiet day.

The first good read of a surface is a silent baseline (F12), except a message known to be under 48
hours old that the Page hasn't answered. Counts on a post are told only when they rise, one message a
run (W3, R1).

A key is the comment id in the permalink where there is one, otherwise the first 120 alphanumerics
of the text plus how many times that text occurred in the thread as read (F7, N2). So a model's
spacing or a "See more" cut doesn't record a message twice, and "Hello?" on Monday and Thursday are
two messages.
"""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Iterable
from urllib.parse import parse_qs, unquote, urlencode, urlsplit, urlunsplit

from jura_growth import caps, config, db, discord, log, pause, timeutil, transcripts
from jura_growth.agents.inbox import settings, store
from jura_growth.agents.publish import audit, fixture, hosts
from jura_growth.agents.publish.commands import STOP_REASONS as PUBLISH_STOP_REASONS
from jura_growth.agents.publish.text import normal

AGENT = "inbox-browser"
PUBLISH = "publish"
PLATFORMS = ("facebook", "instagram")
OBSERVE_FILE_BYTES = caps.INBOX_OBSERVE_FILE_BYTES
MAX_COUNT = 1_000_000_000
MAX_OCCURRENCE = 10_000
KEY_CHARS = 120
READ_TOOLS = {audit.CHROME + "get_page_text", audit.CHROME + "read_page"}  # `find` is a model's retelling
RESUME = ("`jura-growth resume inbox-browser` and `jura-growth resume publish`, or /growth resume inbox-browser and "
          "/growth resume publish")


@dataclass(frozen=True)
class Surface:
    platform: str | None  # None: any platform, as a post can be on either
    label: str
    start: str | None = None  # where a read starts; None: the post's own address


# F5's surfaces. The addresses are where each read starts: the first-run check in the setup guide
# proves them, and a page that doesn't answer is recorded as a failed surface.
SURFACES: dict[str, Surface] = {
    "instagram-primary": Surface("instagram", "Instagram Primary", "https://www.instagram.com/direct/inbox/"),
    "instagram-general": Surface("instagram", "Instagram General", "https://www.instagram.com/direct/general/"),
    "instagram-requests": Surface("instagram", "Instagram Requests", "https://www.instagram.com/direct/requests/"),
    "instagram-activity": Surface("instagram", "Instagram activity", "https://www.instagram.com/notifications/"),
    "facebook-inbox": Surface("facebook", "the Page's inbox", "https://business.facebook.com/latest/inbox/all"),
    "facebook-spam": Surface("facebook", "the Page's Spam", "https://business.facebook.com/latest/inbox/spam"),
    "facebook-notifications": Surface("facebook", "the Page's notifications", "https://www.facebook.com/notifications"),
    "facebook-mentions": Surface("facebook", "the Page's mentions", "https://business.facebook.com/latest/notifications"),
    "posts": Surface(None, "Jura's recent posts"),
}
SOCIAL_SOURCES = store.SOCIAL_SOURCES
ATTACHMENTS = {
    "voice-note": "a voice note", "sticker": "a sticker", "photo": "a photo", "video": "a video", "gif": "a GIF",
    "file": "a file", "other": "something with no text",
}
# Closed, so a page's words can't reach an alert through the reason, and the publish job's own words,
# since they describe the same accounts. A deleted post or comment, a closed reply box and a group
# admin's removal or note aren't here: they are outcomes or reactions, and a run only stops for what
# is about the account (functional S4).
STOP_REASONS = {reason: PUBLISH_STOP_REASONS[reason] for reason in (
    "login", "captcha", "checkpoint", "warning", "restriction", "rate-limit", "wrong-identity",
)}
# First path segments that don't name a Page or an account, so they can't be someone else's.
_NEUTRAL_SEGMENTS = {
    "facebook": {"groups", "permalink.php", "story.php", "photo", "photo.php", "watch", "reel", "videos", "messages",
                 "latest", "notifications", "profile.php", "share"},
    "instagram": {"p", "reel", "reels", "tv", "direct", "notifications"},
}
_THREAD_QUERY = ("selected_item_id", "story_fbid", "fbid", "id", "v")
_COMMENT_QUERY = ("reply_comment_id", "comment_id")
_IG_COMMENT = re.compile(r"/c/(\d+)")
_KEPT_QUERY = (*_THREAD_QUERY, *_COMMENT_QUERY, "asset_id")
_PLAIN_VALUE = re.compile(r"[\w.-]+")
_LINK_MARKUP_IN_PATH = re.compile(r"[\[\]()]")
_UNSAFE_URL = re.compile(r"[\s<>\"`|^{}\\\x00-\x1f\x7f]")
_POST_LABEL = re.compile(r"P-\d{1,9}")
_OVER_CAP = "watch.over_cap."  # in `inbox_state`, per run, until its message is written
_OWN = "watch.own."  # likewise: what a run set aside as the Page's own
_BEHIND = "watch.behind."  # a surface a run couldn't finish recording, by run
_ANSWERED = "watch.answered."  # + an item: the run that says the Page has answered it, until its checks
# What `read_page`'s tree may put between the lines of one message: punctuation, refs and roles.
_TREE_GAP = (r"(?:[\W_]|ref_\w+|generic|text|statictext|span|div|paragraph|listitem|list|link|group|article|heading|"
             r"section|row|cell|button|\bp\b){0,40}?")
_SEE_MORE = re.compile(r"(?:\s*(?:…|\.\.\.))?\s*see more\s*$|\s*(?:…|\.\.\.)\s*more\s*$|\s*(?:…|\.\.\.)\s*$", re.I)


# --- the pages ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Page:
    url: str
    name: str
    problem: str | None  # why the address isn't this platform's page, or None
    asset_id: str = ""  # Business Suite's value for the Page, once the first-run check has recorded it


def pages() -> dict[str, Page]:
    """The Page and the account the watch reads, from `config/inbox.yaml` (N11): independent of
    `publish_mode`, because reading doesn't depend on posting through the browser."""
    configured = (config.agent_config("inbox") or {}).get("pages") or {}
    found = {}
    for platform in PLATFORMS:
        spec = configured.get(platform) or {}
        url = str(spec.get("url") or "")
        found[platform] = Page(url, str(spec.get("name") or ""), hosts.page_problem(platform, url), str(spec.get("asset_id") or ""))
    return found


def page_problems() -> list[str]:
    if fixture.active() is not None:
        return []
    return [f"{platform}'s page in config/inbox.yaml: {page.problem}" for platform, page in pages().items() if page.problem]


def _own_names() -> set[str]:
    return {_folded(page.name) for page in pages().values() if page.name}


def _folded(text: str) -> str:
    return normal(unicodedata.normalize("NFKC", text)).casefold()


# --- addresses and keys ---------------------------------------------------------------------------


def _first_segment(url: str) -> str:
    return next((segment for segment in unquote(urlsplit(url).path).split("/") if segment), "").lower()


def target_problem(platform: str, url: Any) -> str | None:
    """Why `url` can't be kept as where this person is, or None. Names nothing from the address."""
    if not isinstance(url, str) or not url:
        return "no address"
    if len(url) > store.TARGET_CHARS or _UNSAFE_URL.search(url) or not url.isprintable() or not _encodable(url):
        return "an address with characters no real one has"
    try:
        if _LINK_MARKUP_IN_PATH.search(urlsplit(url).path):
            return "an address with characters no real one has"
    except ValueError:
        return "an address that isn't a URL"
    site = fixture.active()
    if site is not None:
        return hosts.site_problem(url, site)
    found = hosts.url_problem(url, hosts.BROWSER_HOSTS[platform], f"{platform}'s hosts")
    if found:
        return found
    if hosts.odd_path(urlsplit(url).path):
        return "an address that climbs its own path"
    own = pages()[platform]
    first = _first_segment(url)
    if own.url and not own.problem and first not in _NEUTRAL_SEGMENTS[platform] and first != _first_segment(own.url):
        return "another Page's or account's address"
    return None


def _encodable(text: str) -> bool:
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:  # a lone surrogate, which JSON can carry and nothing else can
        return False
    return True


def may_open(url: str) -> bool:
    """Whether a watch run may ask for this address: a surface, a thread, or a post of Jura's or in a
    group. Not `l.php`, `/accounts/logout/` or anyone's profile. Another host is the audit's own finding."""
    if fixture.active() is not None:
        return True
    host = transcripts.host_of(url)
    platform = next((name for name in PLATFORMS if host in hosts.BROWSER_HOSTS[name]), None)
    return platform is None or target_problem(platform, url) is None


def comment_id(url: str) -> str:
    """The comment's own id in its permalink, or nothing."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    query = parse_qs(parts.query)
    for name in _COMMENT_QUERY:
        value = (query.get(name) or [""])[0]
        if value.isdigit():
            return value
    match = _IG_COMMENT.search(parts.path)
    return match.group(1) if match else ""


def thread_of(url: str) -> str:
    """The thread or post an address is in, whichever of the platform's hosts it came through: its
    path, and the query value that names a thread where the path doesn't (Business Suite)."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    path = _IG_COMMENT.split(parts.path, maxsplit=1)[0].rstrip("/")
    query = parse_qs(parts.query)
    named = [f"{name}={query[name][0]}" for name in _THREAD_QUERY if query.get(name)]
    return "?".join([path, "&".join(named)]) if named else path


def _key_text(text: str) -> str:
    """What identifies a text however a model told it: its first alphanumerics, with no "See more"."""
    folded = _SEE_MORE.sub("", _folded(text))
    letters = "".join(ch for ch in folded if ch.isalnum())[:KEY_CHARS]
    return letters or folded


def same_words(one: str, other: str) -> bool:
    """Whether two tellings are one message, as a key reads them: a "See more" and spacing don't count."""
    return bool(_key_text(one)) and _key_text(one) == _key_text(other)


def same_name(one: str, other: str) -> bool:
    return bool(_folded(one)) and _folded(one) == _folded(other)


def clean_link(url: str) -> str:
    """An address with only what names its thread or comment, in plain values, and no fragment. A page or a
    model chooses the rest, and this is what reaches Discord (code review 06, S-8)."""
    parts = urlsplit(url)
    query = [(name, value) for name, values in parse_qs(parts.query).items() if name in _KEPT_QUERY
             for value in values if _PLAIN_VALUE.fullmatch(value)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query, doseq=True), ""))


def without_comment(url: str) -> str:
    """The post a comment's permalink is on: a newer comment with no address of its own still belongs to it."""
    parts = urlsplit(clean_link(url))
    query = [(name, value) for name, values in parse_qs(parts.query).items() if name not in _COMMENT_QUERY for value in values]
    return urlunsplit((parts.scheme, parts.netloc, _IG_COMMENT.split(parts.path, maxsplit=1)[0], urlencode(query, doseq=True), ""))


def same_reply_place(url: str, place: str) -> bool:
    """Whether `url` is on the thread or post at `place`, on the same host and for the same Page: what holds a
    reply run to its claim, either kind (code review 06, SEC-1). A comment's own permalink is on its post."""
    try:
        if (urlsplit(url.strip()).hostname or "").lower() != (urlsplit(place.strip()).hostname or "").lower():
            return False
        return not hosts.odd_path(urlsplit(url.strip()).path) and thread_of(url.strip()) == thread_of(place.strip()) and hosts.same_asset(url, place)
    except ValueError:
        return False


# --- observe --------------------------------------------------------------------------------------


@dataclass
class Observed:
    """How one file went: counts, and refusals with a fixed reason. Nothing a page said."""

    recorded: int = 0
    duplicates: int = 0
    baseline: int = 0
    own: int = 0
    over_cap: int = 0
    surfaces: int = 0
    posts: int = 0
    refused: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def observe(conn: sqlite3.Connection, run_id: int, observations: list) -> Observed:
    """Record one file's observations, each committed on its own: what a run read stays recorded if
    it dies on the next page (F13). Never raises for what it was given."""
    result = Observed()
    counted: dict[str, int] = {}
    for index, given in enumerate(observations):
        try:
            problem = _one(conn, run_id, given, counted, result)
        except Exception as error:  # noqa: BLE001 - the file's later entries still count, its surface record above all
            log.event(conn, "inbox.observe_error", {"error": type(error).__name__}, level="warning", agent=AGENT)
            problem = "an observation that couldn't be read"
        if problem:
            result.refused.append({"index": index, "reason": problem})
    if result.over_cap or result.refused:
        log.event(conn, "inbox.observe_limited", {"over_cap": result.over_cap, "refused": len(result.refused)},
                  level="warning", agent=AGENT)
    return result


def _one(conn: sqlite3.Connection, run_id: int, given: Any, counted: dict, result: Observed) -> str | None:
    if not isinstance(given, dict):
        return "an observation that isn't an object"
    kind = given.get("type")
    if kind == "reaction":
        return _reaction(conn, run_id, given, counted, result)
    if kind == "surface":
        return _surface(conn, run_id, given, result)
    if kind == "post":
        return _post(conn, run_id, given, result)
    return "an unknown type: use reaction, surface or post"


def _bump(conn: sqlite3.Connection, key: str) -> None:
    store.set_state(conn, key, str(int(store.get_state(conn, key) or 0) + 1))


def _age(given: dict) -> float | None:
    value = given.get("age_hours")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value < 10**7:
        return None
    return value


def _count(value: Any) -> int | None:
    """A sane count, or None."""
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= MAX_COUNT else None


def _new_this_run(conn: sqlite3.Connection, run_id: int) -> int:
    return db.scalar(
        conn,
        f"SELECT count(*) FROM inbox_items WHERE source IN ({', '.join('?' * len(SOCIAL_SOURCES))}) "
        "AND state NOT IN (?, ?) AND json_extract(thread_json, '$.run') = ?",
        (*SOCIAL_SOURCES, store.BASELINE, store.OWN, run_id),
    ) or 0


def _told_under_other_key(conn: sqlite3.Connection, conversation: str, words_key: str, own_id: str, loose_key: str,
                          thread: str) -> bool:
    """The same words from the same person, once with a permalink and once without (notifications
    link a comment, and the post's page may not), or once with no address at all. Two different ids
    are two comments, and two different threads are two messages."""
    for row in db.rows(conn, "SELECT json_extract(thread_json, '$.comment_id') AS comment_id FROM inbox_items "
                             "WHERE conversation = ? AND json_extract(thread_json, '$.words_key') = ?",
                       (conversation, words_key)):
        if not own_id or not row["comment_id"]:
            return True
    for row in db.rows(conn, "SELECT json_extract(thread_json, '$.thread') AS thread FROM inbox_items "
                             "WHERE json_extract(thread_json, '$.loose_key') = ?", (loose_key,)):
        if not thread or not row["thread"]:
            return True
    return False


def _hold_answered(conn: sqlite3.Connection, run_id: int, key: str, conversation: str, words_key: str) -> None:
    """A message already known, which the run now says the Page has answered. Held until its checks,
    like anything a run records, so a steered run can't close a card (`settle`)."""
    row = db.one(conn, "SELECT id FROM inbox_items WHERE key = ? OR (conversation = ? AND json_extract(thread_json, '$.words_key') = ?) "
                       "ORDER BY id LIMIT 1", (key, conversation, words_key))
    if row:
        store.set_state(conn, f"{_ANSWERED}{row['id']}", str(run_id))


def record_newer(conn: sqlite3.Connection, run_id: int, item: dict, text: str, occurrence: int, url: str) -> None:
    """A reply run read a newer message from this person on this thread (F9). It goes the way anything a
    run reads goes, held as `observed` until the run's checks, and in this item's conversation. A comment
    with no safe address of its own takes its post's, since a draft on it can only go there."""
    platform = store.platform_of(item)
    own_url = url and target_problem(platform, url) is None and thread_of(url) == thread_of(item["target"])
    target = url if own_url else item["target"] if store.is_dm(item) else without_comment(item["target"])
    given = {"source": item["source"], "surface": store.thread_of(item).get("surface") or "posts", "url": target, "author": item["sender_name"],
             "text": text, "occurrence": occurrence, "age_hours": 0, "answered": False}
    _reaction(conn, run_id, given, {}, Observed(), from_reply_run=True)


def _is_own(platform: str, author: str, address: Any) -> bool:
    """The Page's own words: its address where the page links the name, which a name can't borrow,
    and otherwise its name. Facebook names aren't unique, so what goes by name alone is counted."""
    own = pages()[platform]
    if isinstance(address, str) and address and own.url and not own.problem:
        try:
            return _first_segment(address) == _first_segment(own.url)
        except ValueError:
            return False
    return _folded(author) in _own_names()


def _reaction(conn: sqlite3.Connection, run_id: int, given: dict, counted: dict, result: Observed, *, from_reply_run: bool = False) -> str | None:
    source = given.get("source")
    if not isinstance(source, str) or source not in SOCIAL_SOURCES:
        return "an unknown source"
    platform = source.split("-", 1)[0]
    surface = given.get("surface")
    if not isinstance(surface, str) or surface not in SURFACES or SURFACES[surface].platform not in (None, platform):
        return "a surface that isn't one of this source's"
    author, text = given.get("author", ""), given.get("text", "")
    if not isinstance(author, str):
        return "an author that isn't text"
    if not isinstance(text, str):
        return "text that isn't text"
    attachment = given.get("attachment")
    if not text.strip():
        attachment = attachment if isinstance(attachment, str) and attachment in ATTACHMENTS else None
        if attachment is None:
            return "no text and no attachment type"
    occurrence = given.get("occurrence", 1)
    if isinstance(occurrence, bool) or not isinstance(occurrence, int) or not 1 <= occurrence <= MAX_OCCURRENCE:
        return "an occurrence that isn't a whole number from 1"
    url = given.get("url")
    target = clean_link(url) if isinstance(url, str) and target_problem(platform, url) is None else ""
    thread = thread_of(target) if target else ""
    who = _folded(author)
    what = _key_text(text) if text.strip() else f"attachment:{attachment}"
    same_words = store.text_key(source, thread, who, what)
    occurrence = max(occurrence, counted.get(same_words, 0) + 1)  # in case it forgot to count in this file
    counted[same_words] = occurrence
    own_id = comment_id(target)
    conversation = store.text_key(source, thread, who)
    words_key = store.text_key(source, thread, who, what, str(occurrence))
    key = store.text_key(source, "comment", own_id) if own_id else words_key
    loose_key = store.text_key(source, who, what, str(occurrence))
    age, answered = _age(given), given.get("answered") is True
    if store.known(conn, key) or _told_under_other_key(conn, conversation, words_key, own_id, loose_key, thread):
        result.duplicates += 1
        if answered:
            _hold_answered(conn, run_id, key, conversation, words_key)
        return None

    first = _first_read(conn, surface)
    too_old = age is not None and age >= settings.limit("old_after_hours")
    own = _is_own(platform, author, given.get("author_url"))
    # F12: on a surface's first read, only a message known to be fresh and unanswered is told.
    silent = own or (first and (answered or too_old or age is None))
    if not silent and _new_this_run(conn, run_id) >= settings.limit("observations_per_run"):
        result.over_cap += 1
        _bump(conn, _OVER_CAP + str(run_id))
        store.set_state(conn, _BEHIND + surface, str(run_id))
        return None
    outcome = store.record(conn, store.Reaction(
        source=source,
        key=key,
        conversation=conversation,
        sender_name=author,
        sender_domain=f"{platform}.com",
        text=text,
        target=target,
        thread={
            "run": run_id, "surface": surface, "thread": thread, "comment_id": own_id, "words_key": words_key,
            "loose_key": loose_key,
            "occurrence": occurrence, "attachment": attachment if not text.strip() else None, "age_hours": age,
            "answered": answered, "from_reply_run": from_reply_run,
        },
        state=store.OWN if own else store.BASELINE if silent else store.OBSERVED,
        stale=too_old,
        reported=silent,
    ))
    if isinstance(outcome, store.Duplicate):
        result.duplicates += 1
    elif own:
        result.own += 1
        _bump(conn, _OWN + str(run_id))
    elif silent:
        result.baseline += 1
    else:
        result.recorded += 1
    return None


# --- surfaces -------------------------------------------------------------------------------------


def _first_read(conn: sqlite3.Connection, surface: str) -> bool:
    return db.scalar(conn, "SELECT last_good_at FROM inbox_surfaces WHERE surface = ?", (surface,)) is None


def _surface(conn: sqlite3.Connection, run_id: int, given: dict, result: Observed) -> str | None:
    name = given.get("surface")
    if not isinstance(name, str) or name not in SURFACES:
        return "an unknown surface"
    said_ok = given.get("ok")
    if not isinstance(said_ok, bool):
        return "ok must be true or false"
    items = given.get("items", 0)
    if _count(items) is None:
        return "items must be a whole number from 0"
    now = timeutil.stamp()
    conn.execute(
        "INSERT INTO inbox_surfaces (surface, first_tried_at, last_run_id, said_ok, said_items, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (surface) DO UPDATE SET last_run_id = excluded.last_run_id, "
        "said_ok = excluded.said_ok, said_items = excluded.said_items, updated_at = excluded.updated_at",
        (name, now, run_id, int(said_ok), items, now),
    )
    result.surfaces += 1
    return None


@dataclass(frozen=True)
class PageReads:
    """What a run's Chrome really returned: each read's page text, and the platforms it read a page on."""

    results: tuple[str, ...] = ()
    platforms: frozenset[str] = frozenset()


def page_reads(transcript: transcripts.Transcript | None) -> PageReads:
    if transcript is None:
        return PageReads()
    parts: list[str] = []
    platforms: set[str] = set()
    for call in transcript.calls:
        if call.name not in READ_TOOLS or not call.ok:
            continue
        parts.append(audit.page_text(call.result))
        for _, url in audit.tab_addresses(call.result):
            host = transcripts.host_of(url)
            platforms |= {name for name in PLATFORMS if fixture.active() is not None or host in hosts.BROWSER_HOSTS[name]}
    return PageReads(tuple(parts), frozenset(platforms))


def finish_surfaces(conn: sqlite3.Connection, run_id: int, reads: PageReads) -> list[str]:
    """Settle every surface for this run: read only if the run said so and read a page on its
    platform. Returns the ones that failed. A surface with no record has failed (F13). A run whose
    audit failed passes no reads, so it restarts no clock and spends no baseline. A surface a flood
    stopped it finishing counts as read, and its last good read stays, so what wasn't recorded still
    looks new to the next run (A13)."""
    now = timeutil.stamp()
    failed = []
    for name, surface in SURFACES.items():
        row = db.one(conn, "SELECT * FROM inbox_surfaces WHERE surface = ?", (name,))
        said = row is not None and row["last_run_id"] == run_id and row["said_ok"]
        read = bool(reads.platforms) if surface.platform is None else surface.platform in reads.platforms
        ok = bool(said and read)
        if row is None:
            conn.execute("INSERT INTO inbox_surfaces (surface, first_tried_at, last_run_id, said_ok, updated_at) "
                         "VALUES (?, ?, ?, 0, ?)", (name, now, run_id, now))
        behind = store.get_state(conn, _BEHIND + name) == str(run_id)
        if behind:
            store.clear_state(conn, _BEHIND + name)
        if ok and behind:
            conn.execute("UPDATE inbox_surfaces SET read_ok = 1, updated_at = ? WHERE surface = ?", (now, name))
        elif ok:
            conn.execute("UPDATE inbox_surfaces SET read_ok = 1, last_good_at = ?, last_good_items = said_items, "
                         "updated_at = ? WHERE surface = ?", (now, now, name))
        else:
            conn.execute("UPDATE inbox_surfaces SET read_ok = 0, updated_at = ? WHERE surface = ?", (now, name))
            failed.append(name)
    return failed


def surface_reads(conn: sqlite3.Connection) -> list[dict]:
    """Each surface's latest state and last good read, for `inbox status` and the one-pager."""
    return db.rows(conn, "SELECT surface, first_tried_at, last_good_at, last_good_items, read_ok FROM inbox_surfaces ORDER BY surface")


def _window_on(day: date) -> tuple[datetime, datetime]:
    start, end = caps.INBOX_WATCH_WINDOW
    return (datetime.combine(day, time.fromisoformat(start), timeutil.SGT),
            datetime.combine(day, time.fromisoformat(end), timeutil.SGT))


def blind_hours(since: datetime, now: datetime) -> float:
    """How much of the time from `since` to `now` fell inside the watch's hours. The night isn't blind."""
    total = timedelta()
    day = since.astimezone(timeutil.SGT).date()
    last = now.astimezone(timeutil.SGT).date()
    while day <= last:
        start, end = _window_on(day)
        low, high = max(since, start), min(now, end)
        if high > low:
            total += high - low
        day += timedelta(days=1)
    return total.total_seconds() / 3600


def blind_lines(conn: sqlite3.Connection) -> list[str]:
    """F13: the surfaces with no good read for over 3 hours of the watch's hours, as one line. Reads only."""
    try:
        rows = surface_reads(conn)
    except sqlite3.OperationalError:  # not migrated yet: nothing has been read
        return []
    now = timeutil.now_sgt()
    blind = []
    for row in rows:
        surface = SURFACES.get(row["surface"])
        if surface is None:
            continue
        since = timeutil.parse(row["last_good_at"] or row["first_tried_at"])
        if blind_hours(since, now) >= caps.INBOX_BLIND_SURFACE_HOURS:
            good = f"last good read {since:%d %b %H:%M}" if row["last_good_at"] else "never read"
            blind.append(f"{surface.label} ({good})")
    if not blind:
        return []
    return ["Inbox watch can't read " + ", ".join(blind) + ": a person there may be going unseen, so check by hand."]


# --- posts ----------------------------------------------------------------------------------------


def _post_cutoff() -> str:
    return timeutil.stamp(timeutil.now_sgt() - timedelta(days=caps.INBOX_WATCH_POST_DAYS))


_PUBLISHED = ("p.state = 'done' AND p.outcome = 'posted' AND p.post_url IS NOT NULL AND p.finished_at >= ? "
              "AND p.platform IN ('facebook', 'instagram') AND p.kind IN ('social_post', 'community_post')")


def targets(conn: sqlite3.Connection) -> dict:
    """What a run reads: the pages, the surfaces, and the least recently read posts Jura published in
    the last 30 days (F6), so every post is reached over a day and notifications catch the rest."""
    since = {row["surface"]: row["last_good_at"] for row in surface_reads(conn)}
    posts = db.rows(
        conn,
        f"SELECT p.label AS item, p.platform, p.kind, p.post_url AS url FROM publish_items p "
        f"LEFT JOIN inbox_watch_posts w ON w.publish_item = p.id WHERE {_PUBLISHED} AND w.gone_at IS NULL "
        "ORDER BY w.last_read_at IS NOT NULL, w.last_read_at, p.finished_at DESC, p.id DESC LIMIT ?",
        (_post_cutoff(), settings.limit("watch_posts_per_run")),
    )
    return {
        "pages": {name: {"url": page.url, "name": page.name} for name, page in pages().items()},
        "surfaces": [{"surface": name, "label": surface.label, "start": surface.start, "since": since.get(name)}
                     for name, surface in SURFACES.items()],
        "posts": posts,
    }


def _post(conn: sqlite3.Connection, run_id: int, given: dict, result: Observed) -> str | None:
    label = given.get("item")
    if not isinstance(label, str) or not _POST_LABEL.fullmatch(label):
        return "an item that isn't a post's label"
    row = db.one(conn, f"SELECT p.id FROM publish_items p WHERE p.label = ? AND {_PUBLISHED}", (label, _post_cutoff()))
    if row is None:
        return f"a post Jura didn't publish in the last {caps.INBOX_WATCH_POST_DAYS} days"
    item = row["id"]
    read_this_run = db.scalar(conn, "SELECT count(*) FROM inbox_watch_posts WHERE last_run_id = ? AND publish_item != ?", (run_id, item)) or 0
    if read_this_run >= settings.limit("watch_posts_per_run"):
        return "more posts than a run may read"
    now = timeutil.stamp()
    if given.get("gone") is True:
        # Held until the run's checks: a steered run must not drop a post, so `post_lines` settles it.
        conn.execute(
            "INSERT INTO inbox_watch_posts (publish_item, gone_said_run, last_read_at, last_run_id) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (publish_item) DO UPDATE SET gone_said_run = excluded.gone_said_run, "
            "last_read_at = excluded.last_read_at, last_run_id = excluded.last_run_id",
            (item, run_id, now, run_id),
        )
        result.posts += 1
        return None
    reactions, shares = _count(given.get("reactions")), _count(given.get("shares"))
    if reactions is None or shares is None:
        return "reactions and shares must be whole numbers from 0"
    comments, page_comments = given.get("comments", 0), given.get("page_comments", 0)
    if _count(comments) is None or _count(page_comments) is None:
        return "comments and page_comments must be whole numbers from 0"
    conn.execute(
        "INSERT INTO inbox_watch_posts (publish_item, reactions, shares, comments, page_comments, last_read_at, last_run_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (publish_item) DO UPDATE SET reactions = excluded.reactions, "
        "shares = excluded.shares, comments = excluded.comments, page_comments = excluded.page_comments, "
        "gone_at = NULL, gone_told = 0, gone_said_run = NULL, "  # a later read found it: it was never gone
        "last_read_at = excluded.last_read_at, last_run_id = excluded.last_run_id",
        (item, reactions, shares, comments, page_comments, now, run_id),
    )
    result.posts += 1
    return None


def _rise(count: int, then: int, one: str, many: str) -> str | None:
    gained = count - then
    if gained <= 0:
        return None
    return f"{gained} new {one if gained == 1 else many}, now {count}"


def post_lines(conn: sqlite3.Connection, run_id: int) -> list[str]:
    """What this run's post counts have to tell, and remember that it told it: a count only when it
    rose (W3), reactions and shares only (S8), and comments the page counts that nobody recorded
    (B2). A post's first read tells nothing, because everything would read as having risen."""
    rows = db.rows(
        conn,
        "SELECT w.*, p.label, p.platform, p.post_url FROM inbox_watch_posts w JOIN publish_items p ON p.id = w.publish_item "
        "WHERE w.last_run_id = ? ORDER BY p.id",
        (run_id,),
    )
    posts_read_before = not _first_read(conn, "posts")
    lines = []
    for row in rows:
        where = f"{row['label']} on {row['platform'].capitalize()}"
        if row["gone_said_run"] == run_id:
            if not row["gone_told"]:
                lines.append(f"{where} isn't there any more: a group admin or the platform may have removed it. <{row['post_url']}>")
            conn.execute("UPDATE inbox_watch_posts SET gone_at = COALESCE(gone_at, ?), gone_told = 1, gone_said_run = NULL "
                         "WHERE publish_item = ?", (timeutil.stamp(), row["publish_item"]))
            continue
        if row["gone_at"]:
            continue
        first = row["told_reactions"] is None
        said = [] if first else [
            _rise(row["reactions"], row["told_reactions"], "reaction", "reactions"),
            _rise(row["shares"], row["told_shares"], "share", "shares"),
        ]
        recorded = db.scalar(
            conn,
            "SELECT count(*) FROM inbox_items WHERE source IN ('facebook-comment', 'instagram-comment') "
            "AND state != ? AND json_extract(thread_json, '$.thread') = ?",
            (store.OWN, thread_of(row["post_url"])),
        ) or 0
        unread = max(0, row["comments"] - row["page_comments"] - recorded)
        if unread > row["told_unread"] and (posts_read_before or not first):
            said.append(f"{unread} comment{'s' if unread != 1 else ''} the watch couldn't read: check by hand")
        conn.execute(
            "UPDATE inbox_watch_posts SET told_reactions = reactions, told_shares = shares, told_unread = ? WHERE publish_item = ?",
            (unread, row["publish_item"]),
        )
        said = [text for text in said if text]
        if said:
            lines.append(f"{where}: {'. '.join(said)}. <{row['post_url']}>")
    return lines


def over_cap_lines(conn: sqlite3.Connection, run_id: int) -> list[str]:
    """A flood is bounded, and never silently (A13): what wasn't recorded is read again next run."""
    key = _OVER_CAP + str(run_id)
    over = store.get_state(conn, key)
    if not over:
        return []
    store.clear_state(conn, key)
    return [f"The watch stopped at {settings.limit('observations_per_run')} new messages this run. "
            f"{over} more wait for the next run, oldest unread first."]


def own_lines(conn: sqlite3.Connection, run_id: int) -> list[str]:
    """What went by the Page's name alone is counted, once, because Facebook names aren't unique (R3)."""
    key = _OWN + str(run_id)
    count = int(store.get_state(conn, key) or 0)
    if not count:
        return []
    store.clear_state(conn, key)
    return [f"The watch set aside {count} message{'s' if count != 1 else ''} signed as the Page itself. If you didn't "
            "write them, someone may be impersonating the Page, so check the Page's inbox and recent posts."]


def record_run_message(conn: sqlite3.Connection, run_id: int, lines: list[str]) -> None:
    """One message a run for everything that isn't a person's own message (R1). It goes to no triage."""
    if not lines:
        return
    key = store.text_key("watch-run", str(run_id))
    store.record(conn, store.Reaction(source=store.RUN_MESSAGE, key=key, conversation=key, state=store.REPORTED,
                                      note="\n".join(lines), thread={"run": run_id}))


# --- settling what a run recorded ------------------------------------------------------------------


@dataclass
class Settled:
    states: dict[str, int] = field(default_factory=dict)


def _comparable(text: str) -> str:
    """Text as compared with a page: a model's spacing and a page's markup don't count."""
    return " ".join(unicodedata.normalize("NFKC", store.clean_text(text)).casefold().split())


def words_on_page(text: str, results: Iterable[str]) -> bool:
    """Whether `text` appears in one result, its lines in order and together. Between them only what
    `read_page`'s tree puts there may fall, so words scattered through a page aren't a message (N3, B2)."""
    lines = [_comparable(line) for line in text.split("\n") if line.strip()]
    if not lines:
        return True
    pattern = re.compile(_TREE_GAP.join(re.escape(line) for line in lines))
    return any(pattern.search(_comparable(result)) for result in results)


def after_words(text: str, result: str) -> str | None:
    """What a page goes on to say after `text`, as `words_on_page` reads it, or None when `text` isn't there."""
    lines = [_comparable(line) for line in text.split("\n") if line.strip()]
    if not lines:
        return None
    page = _comparable(result)
    match = re.compile(_TREE_GAP.join(re.escape(line) for line in lines)).search(page)
    return page[match.end():] if match else None


def said_on_page(words: str, page_says: str) -> bool:
    return bool(_comparable(words)) and _comparable(words) in page_says


def name_beside(name: str, text: str, result: str) -> bool:
    """Whether `name` is on the line that holds `text` or one of the few before it: who a page says wrote it."""
    want, who = _comparable(text), _comparable(name)
    lines = [line for line in result.split("\n") if line.strip()]
    for number, line in enumerate(lines):
        if want and who and want in _comparable(line):
            if any(who in _comparable(near) for near in lines[max(0, number - 3):number + 1]):
                return True
    return False


def settle(conn: sqlite3.Connection, run_id: int | None, results: Iterable[str], *, trusted: bool) -> Settled:
    """Move every held item on (N3). This run's are checked against what its pages returned, and
    any other held item's run was killed before its checks. `trusted` False: the run's audit failed,
    so nothing it recorded can be cleared. A person always stays visible: every state here reports."""
    settled = Settled()
    results = tuple(results)
    old_after = settings.limit("old_after_hours")
    for item in db.rows(conn, "SELECT * FROM inbox_items WHERE state = ? ORDER BY id", (store.OBSERVED,)):
        thread = json.loads(item["thread_json"] or "{}")
        state, note = store.NEW, ""
        if not trusted or thread.get("run") != run_id or not words_on_page(item["text"], results):
            state = store.UNVERIFIED
            note = "Unverified: this wasn't in what the page returned to the run, so there's no draft. Read the thread yourself."
            if thread.get("from_reply_run"):  # a run's word for a person's message, which never needs quoting (code review 06, S-9)
                note = "A reply run said they wrote again, and its pages didn't show it, so what it said isn't kept. Read the thread yourself."
                conn.execute("UPDATE inbox_items SET text = '' WHERE id = ?", (item["id"],))
        elif thread.get("answered"):
            state = store.ANSWERED_BY_HAND
            note = "The Page had already answered this, so there's no draft."
        elif not item["target"]:
            state = store.NEEDS_HAND_REPLY
            note = "The watch couldn't keep a safe address for this. Find it on the platform and answer by hand if it matters."
        elif not item["text"]:
            state = store.NEEDS_HAND_REPLY
            note = "There's no text to draft from: open the thread, and answer by hand if it matters."
        elif item["stale"]:
            state = store.REPORTED
            note = f"It's older than {old_after} hours: answer by hand if it still matters."
        conn.execute("UPDATE inbox_items SET state = ?, note = ?, updated_at = ? WHERE id = ?",
                     (state, note, timeutil.stamp(), item["id"]))
        settled.states[state] = settled.states.get(state, 0) + 1
    _settle_answered(conn, run_id, results, trusted=trusted)
    return settled


def _settle_answered(conn: sqlite3.Connection, run_id: int | None, results: tuple[str, ...], *, trusted: bool) -> None:
    """The Page answered something still open (a hand reply from his phone): it closes, and he hears so
    again, because he may still think it waits on him. Only a run that passed its checks can say so, and
    its pages must have shown the message. What is on its way already is left to its own outcome."""
    for name, said_by in store.with_prefix(conn, _ANSWERED):
        store.clear_state(conn, _ANSWERED + name)
        item = store.get(conn, int(name)) if name.isdigit() else None
        if item is None or not trusted or said_by != str(run_id) or item["state"] not in (store.NEW, store.TRIAGED, store.WAITING):
            continue
        if words_on_page(item["text"], results):
            store.close_and_tell(conn, item["id"], store.ANSWERED_BY_HAND, "The Page has answered this by hand, so it is closed, and no draft goes.")


def settle_orphans(conn: sqlite3.Connection) -> Settled:
    """Called with the job and browser locks held, so no live run can own a held item."""
    return settle(conn, None, (), trusted=False)


# --- a stop signal --------------------------------------------------------------------------------


def stopped_reason(conn: sqlite3.Connection, run_id: int) -> str | None:
    row = db.one(conn, "SELECT payload_json FROM events WHERE kind = 'inbox.stopped' AND run_id = ? ORDER BY id LIMIT 1", (run_id,))
    return json.loads(row["payload_json"]).get("reason") if row else None


def stop(conn: sqlite3.Connection, run_id: int | None, reason: str) -> None:
    """A stop signal (S4): pauses `inbox-browser` and `publish`, since they share the accounts, and
    alerts once. Only Ting Yu resumes: `resume` is in `headless.NEVER`."""
    already = run_id is not None and stopped_reason(conn, run_id) is not None
    with db.transaction(conn):
        log.event(conn, "inbox.stopped", {"reason": reason}, level="warning", agent=AGENT, run_id=run_id)
        for agent in (AGENT, PUBLISH):
            pause.pause(conn, agent, f"a browser run stopped: {reason}", notify=False)
    if already:
        return
    where = f"in run {run_id}" if run_id is not None else "outside a run"
    text = f"A browser run stopped {where}: {STOP_REASONS[reason]}. Watching, social replies and publishing are paused."
    if run_id is not None:
        text += f" The run's transcript keeps what the page showed for {caps.BROWSER_TRANSCRIPT_DAYS} days."
    discord.alert(conn, f"{text}\nA page's words can trigger a stop, so check the account first. Nothing more happens on "
                        f"these accounts until you resume both: {RESUME}.", agent=AGENT)


def parse_file(raw: bytes) -> list:
    """An observation file's list, or ValueError with fixed words."""
    try:
        found = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise ValueError("the file isn't JSON text") from None
    if not isinstance(found, list):
        raise ValueError("the file must hold a JSON list")
    return found


def status_lines(conn: sqlite3.Connection) -> list[str]:
    """Each surface's last good read, by its fixed name."""
    found = {row["surface"]: row for row in surface_reads(conn)}
    lines = []
    for name, surface in SURFACES.items():
        row = found.get(name)
        if row is not None:
            lines.append(f"{surface.label}: last good read {row['last_good_at'] or 'never'}")
    return lines
