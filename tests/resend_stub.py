"""A local stand-in for Resend and D1, for `.scratch/mission-control/uat.md` Part A (tickets 06
and 18; X13).

It listens on 127.0.0.1 only, prints one line for every email it is asked to send, and answers
like Resend: `{"id": "stub-<n>"}`, the same id again for a repeated `Idempotency-Key`. It sends
nothing anywhere. It also answers D1 queries from an empty in-memory copy of the website's
`suppression` and `app_usage` tables (`tests/d1_stub.py`), printing one line for each, so the
suppression sync and the D1 checks never reach Cloudflare. From the repo root, in the Part A
window:

    uv run python -m tests.resend_stub [--port 8025]
    export JURA_GROWTH_RESEND_BASE_URL=http://127.0.0.1:8025
    export JURA_GROWTH_D1_BASE_URL=http://127.0.0.1:8025

It refuses to start unless `JURA_GROWTH_DATA_DIR` is a temporary folder (made with `mktemp -d`)
outside `jurasolutions/`, and the engine refuses both base URLs on the same terms. The suite never
sends through it: tests use the Resend and D1 doubles.
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TextIO

from jura_growth import paths

try:
    import d1_stub  # under pytest, tests/ is on the path
except ModuleNotFoundError:
    from tests import d1_stub  # `uv run python -m tests.resend_stub` from the repo root

PORT = 8025


def refusal() -> str | None:
    """Why the stub won't start, or None."""
    return paths.temporary_data_problem()


def server(port: int = PORT, *, out: TextIO | None = None, suppression: list[dict] = (),
           app_usage: list[dict] = ()) -> ThreadingHTTPServer:
    """The stub, bound to 127.0.0.1 (`port` 0 picks a free one). Call `serve_forever()`.
    `suppression` and `app_usage` are D1 rows to start with (from the command line, none)."""
    out = out or sys.stdout
    ids: dict[str, str] = {}
    d1 = d1_stub.D1(suppression=suppression, app_usage=app_usage)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - the http.server name
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                body = {}
            if d1.handles(self.path):
                status, answer = d1.answer(body)
                print(f"D1 {self.path} sql={body.get('sql', '')!r} params={body.get('params') or []} -> {status}",
                      file=out, flush=True)
                self._reply(status, answer)
                return
            key = self.headers.get("Idempotency-Key") or ""
            repeat = key in ids
            ids.setdefault(key, f"stub-{len(ids) + 1}")
            to = ",".join(body.get("to") or [])
            note = " (repeat: same id, nothing new)" if repeat else ""
            print(f"POST {self.path} key={key} to={to} subject={body.get('subject', '')!r}{note}", file=out, flush=True)
            self._reply(200, {"id": ids[key]})

        def _reply(self, status: int, answer: dict) -> None:
            reply = json.dumps(answer).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(reply)))
            self.end_headers()
            self.wfile.write(reply)

        def log_message(self, *args) -> None:  # the lines above say it, without the Authorization header
            return

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A local stand-in for Resend and D1, for the UAT harness.")
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args(argv)
    problem = refusal()
    if problem:
        print(f"refused: {problem}")
        return 2
    stub = server(args.port)
    print(f"Resend and D1 stub on http://127.0.0.1:{stub.server_address[1]}; set JURA_GROWTH_RESEND_BASE_URL and "
          "JURA_GROWTH_D1_BASE_URL to that. Ctrl-C stops it.")
    try:
        stub.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stub.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
