"""The gate-matrix adapter for the fake kind (ticket MC-04a), and the
reference for every kind's own `gate_adapter_<kind>.py`. The contract is in
`test_approval_gates.py`'s docstring."""

from jura_growth import approvals

import approval_world as aw


class FakeAdapter:
    kind = aw.KIND
    agent = aw.AGENT
    applied_on_decide = False

    def __init__(self, *, conn, monkeypatch, tmp_path):
        self.conn = conn
        self.world = aw.install(monkeypatch)
        aw.prepare(conn)
        aw.at(monkeypatch, aw.NOW)

    def item(self) -> str:
        return self.world.item()

    def twin(self, subject: str) -> str:
        """Another item whose content would read the same."""
        return self.world.item(self.world.items[subject])

    def raise_request(self, subject: str) -> approvals.Approval:
        return approvals.request(self.conn, self.kind, subject, reason="a test asked", run_id=None)

    def approve(self, approval):
        return aw.approve(self.conn, approval)

    def skip(self, approval):
        return aw.skip(self.conn, approval)

    def attempt(self, subject: str) -> None:
        self.world.act(self.conn, subject, run_id=aw.run(self.conn))

    def went_out(self) -> int:
        return len(self.world.sent)

    def seen_at_call(self) -> list[bool]:
        return [bool(sent["used_at"] and sent["used_by_run"]) for sent in self.world.sent]

    def change(self, subject: str) -> None:
        self.world.items[subject] += " (changed)"

    def remove(self, subject: str) -> None:
        del self.world.items[subject]

    def switch(self, on: bool) -> None:
        self.world.switch = "the fake switch is on" if on else None

    def fail_in_flight(self, on: bool) -> None:
        self.world.fail_in_flight = on

    def hook_ran(self, hook: str, subject: str) -> int:
        return len(self.world.ran(hook, subject))


ADAPTER = FakeAdapter
