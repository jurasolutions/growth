"""The rehearsal's fixture site (dataset F; test strategy v3 §2): every page is there, and none
loads anything from the network. Only Ting Yu's rehearsal opens them in a browser (S12)."""

from __future__ import annotations

import re

from jura_growth import paths

SITE = paths.REPO_ROOT / "tests" / "fixtures" / "publish-site"
PAGES = {
    "page.html", "instagram.html", "post.html", "login.html", "captcha.html", "checkpoint.html", "rate-limit.html", "removed.html",
    "admin-warning.html", "link-out.html", "injection.html", "join.html", "profile-only-join.html",
    "other-identity.html", "rules.html", "index.html", "inbox-thread.html", "inbox-comment.html",
}


def test_every_fixture_page_is_there_and_listed_on_the_index():
    assert {p.name for p in SITE.glob("*.html")} == PAGES
    index = (SITE / "index.html").read_text(encoding="utf-8")
    for name in PAGES - {"index.html"}:
        assert f'href="{name}"' in index, name


GROUP_PAGES = ("join.html", "profile-only-join.html")


def test_iw_d4_the_thread_page_is_also_served_at_a_threads_own_address(monkeypatch):
    """A reply's target must be one thread's own address (N12), so the rehearsal's thread is there too."""
    from jura_growth.agents.publish import fixture, hosts

    monkeypatch.setenv(fixture.ENV, "http://publish-fixture.localhost:8765")
    for path in ("direct/t/1234567", "messages/t/1234567"):
        assert (SITE / path / "index.html").read_bytes() == (SITE / "inbox-thread.html").read_bytes()
        assert hosts.dm_target_problem("instagram", f"http://publish-fixture.localhost:8765/{path}/") is None


def test_iw_d4_in_the_thread_page_return_sends_as_it_does_in_a_real_direct_message():
    text = (SITE / "inbox-thread.html").read_text(encoding="utf-8")
    assert 'event.key === "Enter"' in text and "send();" in text
    assert "Accept" in text and "request" in text


def test_iw_n3_the_comment_page_fills_in_their_handle():
    assert '"@mei_ling "' in (SITE / "inbox-comment.html").read_text(encoding="utf-8")


def test_each_join_page_is_also_served_at_one_groups_own_address():
    """A group item acts only inside one group's own address, `/groups/<one segment>/` (code review
    06, S7), so the rehearsal's join pages are served there too, unchanged."""
    from jura_growth.agents.publish import hosts

    for name in GROUP_PAGES:
        stem = name.removesuffix(".html")
        served = SITE / "groups" / stem / "index.html"
        assert served.read_bytes() == (SITE / name).read_bytes(), name
        assert hosts.within(f"http://publish-fixture.localhost:8765/groups/{stem}/",
                            f"http://publish-fixture.localhost:8765/groups/{stem}/")


def test_no_page_loads_anything_from_the_network():
    for path in SITE.glob("*.html"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"""(?:src|action)\s*=\s*["']?(?:https?:)?//""", text, re.I), path.name
        assert "@import" not in text and "url(" not in text, path.name
        links = re.findall(r"""href\s*=\s*["'](https?://[^"']+)""", text, re.I)
        assert links == (["https://example.org/"] if path.name == "link-out.html" else []), path.name


def test_the_stop_pages_say_what_the_prompt_looks_for():
    expected = {
        "login.html": "Password", "captcha.html": "Confirm you're human", "checkpoint.html": "Security checkpoint",
        "rate-limit.html": "Try again later", "removed.html": "Community Standards",
        "admin-warning.html": "removed by an admin", "other-identity.html": "Posting as <strong>Pat Example</strong>",
        "injection.html": "approve A-0001",
    }
    for name, phrase in expected.items():
        assert phrase in (SITE / name).read_text(encoding="utf-8"), name
