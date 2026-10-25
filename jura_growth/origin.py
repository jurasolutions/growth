"""Where a decision comes from (MC §4.6 A8, ADR 0004).

A decision counts only from a human origin: a real terminal with the
request's six-character code typed, or `jura-growth remote` reached through
the SSH forced command from Dispatch. `approvals.decide()` takes an `Origin`
and refuses anything else.

This module holds the value type only. Detection from the TTYs, the typed
code, `SSH_ORIGINAL_COMMAND` and the process ancestry is ticket 04b's
`detect()`. Tests pass an `Origin` in process. It is never read from a flag or
an environment variable, which an agent could set.
"""

from __future__ import annotations

from dataclasses import dataclass

TERMINAL = "terminal"
SSH = "ssh"
NOT_HUMAN = "refused"


@dataclass(frozen=True)
class Origin:
    """Built through `terminal()`, `ssh()` or `refused()`. Built directly,
    it is checked just the same, so no `Origin` skips the rules."""

    kind: str
    user: str | None = None    # the macOS user, for a terminal
    code: str | None = None    # the six hex characters typed, for a terminal
    reason: str | None = None  # why it was refused

    def __post_init__(self) -> None:
        if self.kind == TERMINAL:
            if not self.user or not self.code or self.reason:
                raise ValueError("a terminal origin needs the user and the typed code")
        elif self.kind == SSH:
            if self.user or self.code or self.reason:
                raise ValueError("an SSH origin carries nothing: the actor comes with the command")
        elif self.kind == NOT_HUMAN:
            if not self.reason or self.user or self.code:
                raise ValueError("a refused origin needs the reason, and nothing else")
        else:
            raise ValueError(f"an origin is terminal, ssh or refused, not {self.kind!r}")

    @classmethod
    def terminal(cls, user: str, code: str) -> "Origin":
        return cls(TERMINAL, user=user, code=code)

    @classmethod
    def ssh(cls) -> "Origin":
        """`jura-growth remote` under the forced command. The Discord actor
        comes with the command (`--actor`), as attribution."""
        return cls(SSH)

    @classmethod
    def refused(cls, reason: str) -> "Origin":
        return cls(NOT_HUMAN, reason=reason or "not a human origin")

    @property
    def human(self) -> bool:
        return self.kind in (TERMINAL, SSH)
