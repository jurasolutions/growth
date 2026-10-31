"""What a watch run may do: its commands and its Chrome tools (inbox watch PRD, B2 and N11; ADR 0006).

The audit reports damage once it is done, and a watch reads hostile text on every page with the
accounts signed in. So a watch can't click at all: `computer`, `form_input`, `file_upload` and
`upload_image` are denied by name, which beats the domain allow. It reads with `navigate`,
`read_page`, `get_page_text` and `find`, and opens threads by the addresses it finds. `read_only`
in the audit stays as the second layer.

It names its own platforms, whatever `publish_mode` says in `config/social.yaml`: reading the Page
doesn't depend on posting to it through the browser.
"""

from __future__ import annotations

from jura_growth.agents.inbox.watch import PLATFORMS, may_open
from jura_growth.agents.publish import audit
from jura_growth.agents.publish import scope as publish_scope

WATCH_COMMANDS = ("inbox watch-targets", "inbox observe", "inbox stopped")
WATCH_DENIED = ("computer", "form_input", "file_upload", "upload_image")
WATCH_RULES = audit.AuditRules(next_word=None, stopped_word="inbox stopped", done_word=None, tool_word="inbox watch",
                               read_only=True, asked_check=may_open)


def permissions(job: str):
    from jura_growth.headless import Permissions

    if job != "inbox-watch":
        return None
    rules = publish_scope.domain_rules(PLATFORMS)  # first: a refused fixture raises before anything else
    denied = dict.fromkeys([*publish_scope.DENIED_TOOLS, *WATCH_DENIED])
    return Permissions(
        commands=WATCH_COMMANDS,
        allowed_tools=(*(publish_scope.CHROME + tool for tool in publish_scope.TAB_TOOLS), *rules),
        disallowed_tools=(*(publish_scope.CHROME + tool for tool in denied), *publish_scope.DENIED_OTHER),
    )


def hosts() -> tuple[str, ...]:
    """The hosts a watch run's tab may be on (the fixture's only, while it is on)."""
    return publish_scope.browser_hosts(PLATFORMS)
