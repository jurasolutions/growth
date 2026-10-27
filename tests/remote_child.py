"""`jura-growth`, as a real process, with the SSH origin passed in process (seam S8).

The suite can't start `sshd`, and no variable or flag can grant an origin, so a test that needs a
real process to get past the origin check runs this file instead of `jura-growth`:

    python tests/remote_child.py remote --actor discord:111 -- status

It hands the root command `ctx.obj["origin"] = Origin.ssh()`, the same in-process seam the
`CliRunner` tests use; everything after that (the allowlist, the command, the masking, the exit
code) runs for real. The real origin check is `test_origin.py` and `test_origin_processes.py`.
"""

from __future__ import annotations

import sys

from jura_growth import config
from jura_growth.cli import cli
from jura_growth.origin import Origin

if __name__ == "__main__":
    with config.redacted_output():
        cli.main(args=sys.argv[1:], prog_name="jura-growth", obj={"origin": Origin.ssh()})
