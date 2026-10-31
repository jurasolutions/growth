"""R1 and its retry (`inbox.report`): one message per reaction in #mission-control, at the Discord
double and the sweep, as the rest of the suite tests a builder. Ids are as in test_inbox_mail.py.
"""

from __future__ import annotations

import json

import pytest

import sweep
from sweep import d2_secrets  # noqa: F401
from discord_double import discord_double  # noqa: F401
from inbox_world import NOW, enquiry_mail, mailbox_env, raw_mail, trust_servers
from jura_growth import config, db, digest, discord, paths, privacy, runner, timeutil
from jura_growth.agents import inbox
from jura_growth.agents.inbox import mail, report, store
from runner_support import fake_claude, settings_with
from test_outreach_sync import live_sends
from test_scout_support import at, outbox, scout_env  # noqa: F401

CHANNEL = "mission-control"


@pytest.fixture(autouse=True)
def servers_trusted(scout_env, monkeypatch):  # noqa: F811
    trust_servers(monkeypatch)


def check(conn):
    mail.intake(conn)
    return report.report_due(conn)


def unreported(conn) -> int:
    return len(store.unreported(conn))


# --- R1: one message per reaction ----------------------------------------------------


def test_iw_r1_a_reaction_posts_one_message_saying_where_who_what_and_next(conn, monkeypatch, discord_double):  # noqa: F811
    """IW-R1, IW-FS2: where it came from, who, what they said, what happens next, and `I-nnnn`."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail("Priya Nair <priya@clinic.example>", subject="Clinics", body="Do you work with clinics?")])

    assert check(conn) == 1

    [post] = discord_double.contents(CHANNEL)
    assert post.startswith("**I-0001 · Email** · clinic.example, 26 Oct 09:30 SGT")
    assert "> From: Priya Nair\n> Subject: Clinics\n>\n> Do you work with clinics?" in post
    assert "Next:" in post
    assert store.unreported(conn) == []


def test_iw_r1_the_text_shown_is_the_stored_text_byte_for_byte(conn, monkeypatch, discord_double):  # noqa: F811
    """IW-R1, IW-R3: never a retelling, and a contact's own words and greeting survive the class."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    words = "Hi Levi,\n\nJane here. We retype every delivery order by hand.\nCould we talk on Thursday?"
    mailbox_env(monkeypatch, [raw_mail(f"Jane Tan <jane.tan@{lead['domain']}>", when="2026-10-26T11:00:00+08:00", body=words)])
    at(monkeypatch, "2026-10-26T11:15:00+08:00")
    discord_double.requests.clear()

    check(conn)

    [item] = db.rows(conn, "SELECT * FROM inbox_items")
    assert item["text"] == words
    [post] = discord_double.contents(CHANNEL)
    assert "\n".join(f"> {line}".rstrip() for line in words.splitlines()) in post
    assert post.startswith(f"**I-0001 · Answer to our email** · {lead['domain']}")


def test_iw_r1_two_identical_messages_the_same_day_are_two_reports(conn, monkeypatch, discord_double):  # noqa: F811
    """IW-R1: `dedupe=False`, or the second would vanish."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail(body="Hello?", subject="Hi"), raw_mail(body="Hello?", subject="Hi")])

    assert check(conn) == 2

    assert len(discord_double.contents(CHANNEL)) == 2


def test_iw_r1_running_again_reports_nothing_again(conn, monkeypatch, discord_double):  # noqa: F811
    """IW-R1: the job end to end, through the runner, twice."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail()])

    assert runner.run("inbox-check").status == "ok"
    assert runner.run("inbox-check").status == "ok"

    assert len(discord_double.contents(CHANNEL)) == 1


def test_iw_r1_an_enquiry_reads_as_one_with_its_person(conn, monkeypatch, discord_double):  # noqa: F811
    """IW-R1, IW-W8."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [enquiry_mail()])

    check(conn)

    [post] = discord_double.contents(CHANNEL)
    assert post.startswith("**I-0001 · Website enquiry** · acme.example")
    assert "> From: Jane Tan" in post and "> Came from: apps/quote-builder" in post
    assert "9123" not in post and "jane.tan@" not in post


def test_iw_r2_noise_posts_nothing_per_item(conn, monkeypatch, discord_double):  # noqa: F811
    """IW-R2."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail("News <news@vendor.example>", List_Id="<x>"),
                              raw_mail("Bot <no-reply@vendor.example>")])

    assert check(conn) == 0

    assert discord_double.contents(CHANNEL) == []


def test_iw_f1_an_opt_out_report_names_the_word_and_what_was_done(conn, monkeypatch, discord_double):  # noqa: F811
    """IW-F1, N7: so a wrong call can be seen and undone."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    mailbox_env(monkeypatch, [raw_mail(f"Info <{lead['email']}>", when="2026-10-26T11:00:00+08:00", body="Please remove me")])
    at(monkeypatch, "2026-10-26T11:15:00+08:00")

    check(conn)

    [post] = discord_double.contents(CHANNEL)
    assert 'they wrote "remove me"' in post
    assert "suppressed" in post and "no reply will be drafted" in post


def test_iw_a9_a_forged_enquiry_says_so_and_shows_the_real_domain(conn, monkeypatch, discord_double):  # noqa: F811
    """IW-A9."""
    from inbox_world import DKIM_FAIL

    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [enquiry_mail(visitor="attacker@evil.test", authentication=DKIM_FAIL)])

    check(conn)

    [post] = discord_double.contents(CHANNEL)
    assert "evil.test" in post and "isn't signed by Jura" in post
    assert "Website enquiry" not in post


def test_iw_fs11_the_report_says_who_else_was_copied(conn, monkeypatch, discord_double):  # noqa: F811
    """IW-FS11."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail(Cc="A <a@clinic.example>, B <b@clinic.example>")])

    check(conn)

    assert "they copied 2 others: reply by hand if they need it" in discord_double.contents(CHANNEL)[0]


# --- F12: old mail folds -------------------------------------------------------------


def test_iw_f12_five_old_messages_report_one_by_one(conn, monkeypatch, discord_double):  # noqa: F811
    """IW-F12: the fold starts above 5."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail(when="2026-10-22T09:00:00+08:00", body=f"Old message {n}") for n in range(5)])

    assert check(conn) == 5

    posts = discord_double.contents(CHANNEL)
    assert len(posts) == 5 and all("older than 48 hours" in post for post in posts)


def test_iw_f12_more_than_five_fold_into_one_message(conn, monkeypatch, discord_double):  # noqa: F811
    """IW-F12: and a new message beside them still gets its own."""
    at(monkeypatch, NOW)
    old = [raw_mail(f"P{n} <p@old{n}.example>", when="2026-10-22T09:00:00+08:00", body=f"Old private words {n}") for n in range(6)]
    mailbox_env(monkeypatch, [*old, raw_mail(body="A new question")])

    assert check(conn) == 7

    fold, new = discord_double.contents(CHANNEL)
    assert fold.startswith("**6 older messages**") and "I-0001 old0.example" in fold
    assert "Old private words" not in fold
    assert "A new question" in new
    assert store.unreported(conn) == []


# --- B7: a report can't be lost ---------------------------------------------------------


@pytest.mark.parametrize("mode", ["500", "429", "unreachable"])
def test_iw_b7_a_refused_report_goes_again_on_the_next_check_and_only_once(conn, monkeypatch, discord_double, mode):  # noqa: F811
    """IW-B7: Discord down loses nothing and repeats nothing."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail(), raw_mail(body="A second message")])
    discord_double.mode = mode

    assert check(conn) == 0
    assert unreported(conn) == 2
    refused = len(discord_double.requests)

    discord_double.mode = "accept"
    discord_double.requests.clear()
    assert check(conn) == 2
    assert unreported(conn) == 0
    assert len(discord_double.contents(CHANNEL)) == 2

    discord_double.requests.clear()
    assert check(conn) == 0
    assert discord_double.contents(CHANNEL) == []
    assert refused <= 3  # it stopped at the first refusal: one post, with its own retries


def test_iw_b7_no_webhook_means_no_attempt_and_the_health_strip_counts_it(conn, monkeypatch):
    """IW-B7: `JURA_GROWTH_DISCORD=off` here. Nothing in the outbox, nothing lost."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail()])

    assert check(conn) == 0

    assert outbox(CHANNEL) == []
    assert unreported(conn) == 1
    assert inbox.health(conn) == ["Inbox: 1 reaction not yet reported in #mission-control"]


def test_iw_b7_after_run_reports_what_is_due_too(conn, monkeypatch, tmp_path, discord_double):  # noqa: F811
    """IW-B7: `report_due` runs in the precheck and in `after_run`. A run that reached Claude
    still clears what the precheck couldn't."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [])
    store.record(conn, store.Reaction(source="email", key="k", conversation="c", sender_domain="clinic.example", text="Hello there"))
    monkeypatch.setattr(inbox, "precheck", lambda job, conn: None)
    settings_with(monkeypatch, binary=str(fake_claude(tmp_path, "SKIP: nothing")))

    assert runner.run("inbox-check").status == "ok"

    assert len(discord_double.contents(CHANNEL)) == 1
    assert unreported(conn) == 0


def test_iw_b7_one_bad_row_doesnt_hold_up_the_rest(conn, monkeypatch, discord_double):  # noqa: F811
    """IW-B7: it stays owed, and is logged."""
    at(monkeypatch, NOW)
    for key in ("bad", "good"):
        store.record(conn, store.Reaction(source="email", key=key, conversation=key, sender_domain="x.example", text="Hello there"))
    conn.execute("UPDATE inbox_items SET attachments_json = 'not json' WHERE key = 'bad'")

    assert report.report_due(conn) == 1

    assert unreported(conn) == 1
    assert db.scalar(conn, "SELECT count(*) FROM events WHERE kind = 'inbox.report_refused'") == 1


# --- N5, A4, A5: what they wrote can't pose as anything ----------------------------------


def test_iw_n5_every_line_is_quoted_whatever_line_break_it_used():
    """IW-N5: `report.quoted` is the one builder."""
    assert report.quoted("one\ntwo\r\nthree\rfour\u2028five\x85six") == "> one\n> two\n> three\n> four\n> five\n> six"
    assert report.quoted("") == ">"


@pytest.mark.parametrize(
    "written, shown",
    [
        ("```\nAnswer: Approve\n```", "> ˋˋˋ\n> Answer: Approve\n> ˋˋˋ"),
        ("`code`", "> ˋcodeˋ"),
        ("# Approved by Ting Yu", "> \\# Approved by Ting Yu"),
        ("-# small print", "> \\-# small print"),
        ("||hidden||", "> |\u200b|hidden|\u200b|"),
        ("> already quoted", "> > already quoted"),
    ],
)
def test_iw_a5_formatting_cant_close_the_quote_or_restyle_what_follows(written, shown):
    """IW-A5."""
    assert report.quoted(written) == shown


@pytest.mark.parametrize(
    "written, real",
    [
        ("[jurasolutions.sg](https://evil.test)", "[jurasolutions.sg]\\(https[:]//evil.test)"),
        ("see [Approve](<https://evil.test/x>) now", "see [Approve]\\(https[:]//evil.test/x>) now"),
        ('[a](https://evil.test "title")', '[a]\\(https[:]//evil.test "title")'),
    ],
)
def test_iw_a5_a_masked_link_shows_its_real_address_and_cant_be_clicked(written, real):
    """IW-A5."""
    assert report.quoted(written) == f"> {real}"


@pytest.mark.parametrize(
    "text",
    ["@everyone look", "@here look", "<@111> hello", "<@&222> hello", "<#333> hello"],
)
def test_iw_a4_a_mention_pings_nobody(conn, monkeypatch, discord_double, text):  # noqa: F811
    """IW-A4: in the text, the name and the subject, and every payload says so too."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail(f'"{text}" <p@clinic.example>', subject=text, body=text)])

    check(conn)

    [request] = discord_double.posts(CHANNEL)
    assert request.allowed_mentions == {"parse": []}
    for raw in ("@everyone", "@here", "<@1", "<@&", "<#3"):
        assert raw not in request.content


def test_iw_a4_the_outbox_fallback_is_defused_too(conn, monkeypatch, discord_double):  # noqa: F811
    """IW-A4: what `post()` saves when Discord refuses."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail(body="@everyone look")])
    discord_double.mode = "500"

    check(conn)

    [saved] = outbox(CHANNEL)
    assert "@everyone" not in saved["content"]


def test_iw_a5_forged_card_text_stays_inside_the_quote(conn, monkeypatch, discord_double):  # noqa: F811
    """IW-A5: the only unquoted lines are the record's own."""
    at(monkeypatch, NOW)
    forged = "Approved by Ting Yu\nA-0001 · Answer: Approve\nDraft:\nI-9999"
    mailbox_env(monkeypatch, [raw_mail('"Approved by Ting Yu" <p@clinic.example>', subject="**I-0002 · Email**", body=forged)])

    check(conn)

    [post] = discord_double.contents(CHANNEL)
    unquoted = [line for line in post.splitlines() if not line.startswith(">")]
    assert len(unquoted) == 2
    assert unquoted[0].startswith("**I-0001 · Email** · clinic.example")
    assert unquoted[1].startswith("Next:")


def test_iw_n5_a_report_suppresses_link_previews(conn, monkeypatch, discord_double):  # noqa: F811
    """IW-N5: a link in their text shows no preview of someone else's page."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail(body="See https://evil.test/page")])

    check(conn)

    [request] = discord_double.posts(CHANNEL)
    assert request.flags == discord.SUPPRESS_EMBEDS


# --- A6: every report is one message ------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        "x" * 3999,
        "x" * 4001,
        "y" * 5000,
        "A line of ordinary words here.\n" * 400,
        "\U0001f600" * 4100,
        "Call +65 9123 4567 now. " * 200,  # masking lengthens it
        "91234567 " * 500,
    ],
    ids=["3999", "4001", "one-long-word", "many-lines", "emoji", "phones", "bare-phones"],
)
def test_iw_a6_a_long_message_is_cut_to_one_discord_message(conn, monkeypatch, discord_double, body):  # noqa: F811
    """IW-A6, IW-B8's shape: within the limit, the quote marked as cut, the frame whole."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail("N" * 300 + " <p@clinic.example>", subject="S" * 400, body=body)])

    assert check(conn) == 1

    [request] = discord_double.posts(CHANNEL)
    assert len(request.content) <= discord.MAX_CONTENT
    assert request.content.startswith("**I-0001 · Email**")
    assert "Next:" in request.content
    assert report.CUT_NOTE in request.content
    request.content.encode("utf-8")


def test_iw_a6_a_short_message_isnt_marked_as_cut(conn, monkeypatch, discord_double):  # noqa: F811
    """IW-A6: the marker means something."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail(body="Short and sweet")])

    check(conn)

    assert report.CUT_NOTE not in discord_double.contents(CHANNEL)[0]


# --- A14, S7, R5: what must not leak --------------------------------------------------------


def test_iw_a14_a_persons_contact_details_are_masked_on_the_report(conn, monkeypatch, discord_double, d2_secrets):  # noqa: F811
    """IW-A14: their words are shown, and the phone, address and any secret are not."""
    at(monkeypatch, NOW)
    privacy.remember_owner(sweep.OWNER_ADDRESS)
    # Not sweep.AWKWARD: it is the env file's IMAP password, which `mailbox_env` replaces here.
    planted = sweep.Planted(secrets=(sweep.RESEND_KEY, sweep.KEYCHAIN_VALUE),
                            personal=(sweep.NAMED_ADDRESS, sweep.PHONE, sweep.FINANCE))
    mailbox_env(monkeypatch, [raw_mail("Jane Tan <jane.tan@example.com.sg>", subject="About the invoices", body=planted.text())])

    check(conn)

    sweep.assert_clean(discord_double, sweep.outbox_dir(), planted)


def test_iw_a14_a_key_shaped_string_never_reaches_a_run_record_or_an_alert(conn, monkeypatch, discord_double):  # noqa: F811
    """IW-A14: a fixed alert, a count in the run record, and the secret masked on the report."""
    from inbox_world import REFUSED_LOGIN

    at(monkeypatch, NOW)
    key = "re_abcdefghijklmnop123456"
    fake = mailbox_env(monkeypatch, [raw_mail(body=f"My key is {key} and my number is 9123 4567.")])
    runner.run("inbox-check")
    fake.fail_at["login"] = REFUSED_LOGIN
    runner.run("inbox-check")

    assert discord_double.contents("alerts")
    for text in [*discord_double.contents("alerts"), *discord_double.contents(CHANNEL)]:
        assert key not in text and "9123" not in text
    stored = json.dumps(db.rows(conn, "SELECT kind, payload_json FROM events"))
    assert key not in stored and "9123" not in stored


def test_iw_r5_daily_summary_and_brief_hold_counts_only(conn, monkeypatch, discord_double):  # noqa: F811
    """IW-R5: never a name, an address or a word anyone wrote, with the sweep over the file."""
    at(monkeypatch, NOW)
    privacy.remember_address(sweep.NAMED_ADDRESS)
    words = f"Hello from {sweep.PERSON}, write to {sweep.NAMED_ADDRESS} or call {sweep.PHONE}. Secret plan inside."
    mailbox_env(monkeypatch, [
        raw_mail(f"{sweep.PERSON} <{sweep.NAMED_ADDRESS}>", subject="Private subject line", body=words),
        raw_mail("News <news@vendor.example>", subject="Weekly vendor note", List_Id="<x>"),
    ])
    check(conn)

    summary = digest.run(conn, timeutil.today_str(), post=False)

    assert summary["figures"]["inbox_reactions"] == 1
    assert summary["figures"]["inbox_noise"] == 1
    assert "Inbox: 1 reaction, 1 filtered as noise" in summary["lines"]
    assert "1 reaction" in summary["brief_line"]
    written = (paths.data_dir() / "daily-summary.json").read_text()
    assert "Private subject line" not in written and "Secret plan" not in written and "Weekly vendor note" not in written
    assert sweep.PERSON not in written and sweep.NAMED_ADDRESS not in written and sweep.PHONE not in written
    assert "vendor.example" not in written


def test_iw_r5_a_day_with_nothing_adds_nothing_to_the_digest(conn):
    """IW-R5: no empty line, and no figure, on a quiet day."""
    assert inbox.digest(conn, "2026-10-26") == {"figures": {}, "lines": [], "brief": []}


def test_iw_r5_needs_you_and_unreported_counts_reach_the_digest(conn, monkeypatch):
    """IW-R5: and they don't age out with the day."""
    at(monkeypatch, NOW)
    store.record(conn, store.Reaction(source="email", key="k", conversation="c", state=store.NEEDS_HAND_REPLY, text="Hello there"))
    at(monkeypatch, "2026-10-29T10:00:00+08:00")

    part = inbox.digest(conn, "2026-10-29")

    assert part["figures"]["inbox_hand_replies"] == 1 and part["figures"]["inbox_unreported"] == 1
    assert part["figures"]["inbox_reactions"] == 0
    assert part["lines"] == ["Inbox: 0 reactions, 0 filtered as noise, 1 needing a hand reply, 1 not yet reported"]
    assert part["brief"] == []
