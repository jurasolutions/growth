"""Code raises requests; no command asks for one (MC §4.6 A11, test strategy v3 G34).

A request is raised only as a side effect of a gated command's own checks, never through a
generic "request an approval" command. Three checks, each generated from the code, so a new
command or a new call site is checked without editing this file:

- no CLI leaf (`headless.leaves(cli)`) takes both an approval kind and a subject;
- `approvals.request(` is called only from the raisers behind A11's commands (the allowlist below);
- the CLI leaves that reach `approvals.request` other than through the publish queue's `sync()`
  (A11 as amended 2026-10-27) are exactly the commands A11 lists.
"""

from __future__ import annotations

import ast
import inspect

import click
import pytest

import call_graph
from jura_growth import approvals, headless
from jura_growth.cli import cli

REQUEST = ("jura_growth.approvals", "request")
SYNC = ("jura_growth.agents.publish.items", "sync")

# A11's commands, as the leaves `headless.leaves(cli)` names them. `publish done` raises only for
# `--outcome questions`, and `community set` only for `rules=` and `rules_confirmed=yes`.
A11_COMMANDS = {
    "outreach queue",
    "outreach send-due",
    "outreach requeue-shadow",
    "apps submit-prd",
    "apps built",
    "social submit",
    "community publish-plan",
    "community propose-join",
    "publish done",
    "publish note-rules",
    "community set",
    "inbox submit",
    "inbox send-due",
    "inbox reword",
    "inbox reply-due",
}

# Every function whose body calls `approvals.request(`, and the A11 commands behind it.
RAISERS = {
    ("jura_growth.agents.outreach.approval", "raise_due"): "outreach queue, send-due, requeue-shadow",
    ("jura_growth.agents.apps.builds", "request"): "apps submit-prd (through the app factory)",
    ("jura_growth.agents.apps.releases", "report_built"): "apps built",
    ("jura_growth.agents.publish.items", "raise_request"):
        "social submit, community publish-plan, community propose-join, publish done --outcome questions, "
        "and the publish queue's sync()",
    ("jura_growth.agents.community.group_rules", "request"):
        "community set rules= and rules_confirmed=yes, publish note-rules",
    ("jura_growth.agents.inbox.kinds", "raise_request"): "inbox submit, inbox send-due, inbox reword",
}

KIND_NAMES = ("kind", "approval_kind", "kinds")
SUBJECT_NAMES = ("subject", "approval_subject", "subjects")


def takes_a_kind_and_a_subject(command: click.Command) -> bool:
    """Whether a command has a parameter for an approval kind and one for a subject. A choice
    parameter offering any registered kind's name counts as a kind, whatever it is called."""
    names = set(approvals.kinds())

    def is_kind(param: click.Parameter) -> bool:
        choices = getattr(param.type, "choices", None) or ()
        return (param.name or "") in KIND_NAMES or (param.name or "").endswith("_kind") or bool(names & set(choices))

    def is_subject(param: click.Parameter) -> bool:
        return (param.name or "") in SUBJECT_NAMES or (param.name or "").endswith("_subject")

    return any(map(is_kind, command.params)) and any(map(is_subject, command.params))


def leaves() -> list[tuple[str, click.Command]]:
    return list(headless.leaves(cli))


def callback_node(command: click.Command) -> call_graph.Node:
    original = inspect.unwrap(command.callback)
    return (original.__module__, original.__qualname__)


# --- no leaf takes a kind and a subject ---------------------------------------------------


@pytest.mark.parametrize("name,command", leaves(), ids=[name for name, _ in leaves()])
def test_no_cli_leaf_takes_both_a_kind_and_a_subject(name, command):
    assert not takes_a_kind_and_a_subject(command), f"`jura-growth {name}` looks like a generic request command"


def test_the_check_would_catch_a_generic_request_command():
    """The check above proves something: a command shaped like the one A11 forbids fails it."""

    @click.command()
    @click.argument("kind")
    @click.argument("subject")
    def generic(kind, subject):  # pragma: no cover - never invoked
        pass

    assert approvals.kinds(), "no approval kind is registered"

    @click.command()
    @click.option("--for", "for_", type=click.Choice(sorted(approvals.kinds())))
    @click.option("--approval-subject")
    def disguised(for_, approval_subject):  # pragma: no cover - never invoked
        pass

    assert takes_a_kind_and_a_subject(generic)
    assert takes_a_kind_and_a_subject(disguised)


def test_the_walk_sees_the_whole_cli():
    names = {name for name, _ in leaves()}
    assert {"approve", "skip", "remote", "approvals", "publish resolve"} <= names
    assert A11_COMMANDS <= names


# --- approvals.request( is called only from A11's raisers ---------------------------------


def request_call_sites() -> set[call_graph.Node]:
    graph = call_graph.graph()
    return {node for node in graph.callers_of(REQUEST) if node[0] != REQUEST[0]}


def literal_call_sites() -> set[call_graph.Node]:
    """`approvals.request(` as written, found without the call graph."""
    found = set()
    for name, module in call_graph.graph().modules.items():
        for qualname, function in module.functions.items():
            for node in ast.walk(function):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "request"
                        and isinstance(node.func.value, ast.Name) and node.func.value.id == "approvals"):
                    found.add((name, qualname))
    return found


def test_approvals_request_is_called_only_from_the_raisers_behind_a11s_commands():
    assert literal_call_sites() == set(RAISERS)
    assert request_call_sites() == set(RAISERS), "a new reference to approvals.request: add it to A11 or remove it"


# --- the leaves that raise are A11's ------------------------------------------------------


def test_every_leaf_callback_is_in_the_call_graph():
    graph = call_graph.graph()
    missing = [name for name, command in leaves() if callback_node(command) not in graph.edges]
    assert missing == []


def test_the_leaves_that_raise_a_request_are_exactly_a11s_commands():
    """Through the publish queue's `sync()`, which A11 (amended 2026-10-27) makes a raiser of its
    own, any publish command may raise a replacement request; every other path to
    `approvals.request` starts at one of A11's commands."""
    graph = call_graph.graph()
    raising = {
        name for name, command in leaves()
        if graph.reaches(callback_node(command), REQUEST, avoiding=frozenset({SYNC}))
    }
    assert raising == A11_COMMANDS


def test_the_sync_raiser_reaches_a_request_only_by_superseding_on_the_same_item():
    """A11's amendment: `sync()` raises through `raise_request()` alone."""
    graph = call_graph.graph()
    assert graph.reaches(SYNC, REQUEST)
    assert not graph.reaches(SYNC, REQUEST, avoiding=frozenset({("jura_growth.agents.publish.items", "raise_request")}))
