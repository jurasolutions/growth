"""A local stand-in for Resend, for `.scratch/mission-control/uat.md` Part A (ticket 06; X13).

It listens on 127.0.0.1 only, prints one line for every email it is asked to send, and answers
like Resend: `{"id": "stub-<n>"}`, the same id again for a repeated `Idempotency-Key`. It sends
nothing anywhere. From the repo root, in the Part A window:

    uv run python -m tests.resend_stub [--port 8025]
    export JURA_GROWTH_RESEND_BASE_URL=http://127.0.0.1:8025

It refuses to start unless `JURA_GROWTH_DATA_DIR` is a temporary folder (made with `mktemp -d`)
outside `jurasolutions/`, and `send-due` refuses `JURA_GROWTH_RESEND_BASE_URL` on the same terms.
The suite never sends through it: tests use the Resend double.
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TextIO

from jura_growth.agents.outreach import send

PORT = 8025


def refusal() -> str | None:
    """Why the stub won't start, or None."""
    return send.temporary_data_problem()


def server(port: int = PORT, *, out: TextIO | None = None) -> ThreadingHTTPServer:
    """The stub, bound to 127.0.0.1 (`port` 0 picks a free one). Call `serve_forever()`."""
    out = out or sys.stdout
    ids: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - the http.server name
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                body = {}
            key = self.headers.get("Idempotency-Key") or ""
            repeat = key in ids
            ids.setdefault(key, f"stub-{len(ids) + 1}")
            to = ",".join(body.get("to") or [])
            note = " (repeat: same id, nothing new)" if repeat else ""
            print(f"POST {self.path} key={key} to={to} subject={body.get('subject', '')!r}{note}", file=out, flush=True)
            reply = json.dumps({"id": ids[key]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(reply)))
            self.end_headers()
            self.wfile.write(reply)

        def log_message(self, *args) -> None:  # the line above says it, without the Authorization header
            return

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A local stand-in for Resend, for the UAT harness.")
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args(argv)
    problem = refusal()
    if problem:
        print(f"refused: {problem}")
        return 2
    stub = server(args.port)
    print(f"Resend stub on http://127.0.0.1:{stub.server_address[1]}; set JURA_GROWTH_RESEND_BASE_URL to that. Ctrl-C stops it.")
    try:
        stub.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stub.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
