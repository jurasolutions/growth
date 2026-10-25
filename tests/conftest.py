import ipaddress
import os
import shutil
import sys
import urllib.parse

import pytest

from jura_growth import config, paths


class WriteGuard:
    """Refuses writes into the repo and anywhere under `jurasolutions/`.

    Installed as an audit hook for the whole session, so it also covers
    collection and fixtures. A refused write raises PermissionError before it
    happens, and is recorded, so a test that swallows the error still fails.
    Opening a SQLite file there is refused too, even read-only: an open rolls
    back a stale journal. Python bytecode and pytest's cache may still be
    written. Subprocesses are outside the hook, so tests give them temp folders.
    """

    # event: (indexes of the path arguments, index of the dir_fd argument)
    EVENTS = {
        "open": ((0,), None),
        "os.mkdir": ((0,), 2),
        "os.remove": ((0,), 1),
        "os.rmdir": ((0,), 1),
        "os.rename": ((0, 1), 2),
        "os.truncate": ((0,), None),
        "os.utime": ((0,), 3),
        "os.chmod": ((0,), 2),
        "os.symlink": ((1,), 2),
        "os.link": ((1,), 3),
        "shutil.rmtree": ((0,), 1),
        "sqlite3.connect": ((0,), None),
    }
    WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
    CACHES = {"__pycache__", ".pytest_cache"}

    def __init__(self, *roots):
        self.roots = sorted({os.path.realpath(root) for root in roots})
        self.violations: list[str] = []

    def take(self) -> list[str]:
        found, self.violations = self.violations, []
        return found

    def _protected(self, value) -> str | None:
        if isinstance(value, bytes):
            value = os.fsdecode(value)
        if not isinstance(value, (str, os.PathLike)) or str(value) in ("", ":memory:"):
            return None
        if isinstance(value, str) and value.startswith("file:"):  # a SQLite URI: judge the file it names
            value = urllib.parse.unquote(urllib.parse.urlsplit(value).path)
            if value in ("", ":memory:"):
                return None
        target = os.path.realpath(value)
        if not any(target == root or target.startswith(root + os.sep) for root in self.roots):
            return None
        if self.CACHES & set(target.split(os.sep)):
            return None
        return target

    def hook(self, event, args):
        if event not in self.EVENTS:
            return
        indexes, dir_fd = self.EVENTS[event]
        if dir_fd is not None and len(args) > dir_fd and args[dir_fd] not in (None, -1):
            return  # relative to an open folder, as inside shutil.rmtree
        if event == "open":
            mode, flags = args[1], args[2]
            if not (isinstance(mode, str) and set(mode) & set("wax+")) and not (isinstance(flags, int) and flags & self.WRITE_FLAGS):
                return
        for index in indexes:
            target = self._protected(args[index]) if len(args) > index else None
            if target is None or (event == "os.mkdir" and os.path.isdir(target)):
                continue
            self.violations.append(f"{event} {target}")
            raise PermissionError(f"tests must not write into the repo or jurasolutions/: {event} {target}")


GUARD = WriteGuard(paths.REPO_ROOT, paths.JURA_ROOT)
sys.addaudithook(GUARD.hook)


class NetworkGuard:
    """Refuses every lookup and connection that isn't loopback.

    Installed as a second audit hook for the whole session, on
    `socket.getaddrinfo` and `socket.connect`, so no test can reach Discord,
    Resend, Cloudflare, IMAP or any other real service by mistake. A refusal
    raises PermissionError and is recorded, so a test that swallows the error
    still fails. Unix sockets and the loopback addresses and names are
    allowed. Subprocesses are outside the hook, as for the write guard.
    """

    LOOPBACK_NAMES = {"localhost", "localhost.", "ip6-localhost", "ip6-loopback"}

    def __init__(self):
        self.violations: list[str] = []

    def take(self) -> list[str]:
        found, self.violations = self.violations, []
        return found

    @classmethod
    def _loopback(cls, host) -> bool:
        if host is None:
            return True  # a passive lookup for binding: no remote host
        if isinstance(host, bytes):
            host = host.decode("ascii", "replace")
        host = str(host).strip().lower()
        if host in cls.LOOPBACK_NAMES or host.endswith(".localhost") or host.endswith(".localhost."):
            return True
        try:
            return ipaddress.ip_address(host.split("%")[0]).is_loopback
        except ValueError:
            return False

    def hook(self, event, args):
        if event == "socket.getaddrinfo":
            host, port = args[0], args[1]
        elif event == "socket.connect":
            address = args[1]
            if not isinstance(address, tuple):
                return  # a Unix socket path
            host, port = address[0], address[1]
        else:
            return
        if self._loopback(host):
            return
        if isinstance(host, bytes):
            host = host.decode("ascii", "replace")
        target = f"{host}:{port}" if port not in (None, "", 0) else str(host)
        self.violations.append(f"{event} {target}")
        raise PermissionError(f"tests must not reach the network: {event} {target}")


NETWORK = NetworkGuard()
sys.addaudithook(NETWORK.hook)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Every test gets its own data, outputs and launchd folders, no Discord
    and no secrets, so nothing touches jurasolutions/data or the live server."""
    monkeypatch.setenv("JURA_GROWTH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("JURA_GROWTH_OUTPUTS_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("JURA_GROWTH_PAUSE_FILE", str(tmp_path / "PAUSE"))
    monkeypatch.setenv("JURA_GROWTH_ENV_FILE", str(tmp_path / "no.env"))
    monkeypatch.setenv("JURA_GROWTH_LAUNCH_AGENTS", str(tmp_path / "LaunchAgents"))
    monkeypatch.setenv("JURA_GROWTH_PLIST_DIR", str(tmp_path / "plists"))
    # A private copy of prompts/, so a test can add a prompt for a fake job.
    shutil.copytree(paths.REPO_ROOT / "prompts", tmp_path / "prompts")
    monkeypatch.setenv("JURA_GROWTH_PROMPTS_DIR", str(tmp_path / "prompts"))
    monkeypatch.setenv("JURA_GROWTH_DISCORD", "off")
    # Never read the real inputs/, PRD folders or website registry from a test.
    # Tests that need them build their own and set these again.
    monkeypatch.setenv("JURA_INPUTS_DIR", str(tmp_path / "inputs"))
    monkeypatch.setenv("JURA_PRD_DIR", str(tmp_path / "prd"))
    monkeypatch.setenv("JURA_SITE_REPO", str(tmp_path / "site"))
    for name in ("JURA_GROWTH_RUN_ID", "JURA_GROWTH_AGENT", "JURA_GROWTH_JOB", "JURA_GROWTH_NOW"):
        monkeypatch.delenv(name, raising=False)
    config.reset_caches()
    GUARD.take()
    NETWORK.take()
    yield tmp_path
    config.reset_caches()
    refused = GUARD.take()
    reached = NETWORK.take()
    if refused:
        pytest.fail("this test wrote into the repo or jurasolutions/:\n  " + "\n  ".join(refused))
    if reached:
        pytest.fail("this test reached for the network outside loopback:\n  " + "\n  ".join(reached))


@pytest.fixture
def write_guard():
    """The session's write guard. A test that provokes it on purpose calls
    `write_guard.take()` so its own refusals don't fail it."""
    return GUARD


@pytest.fixture
def network_guard():
    """The session's network guard. A test that provokes it on purpose calls
    `network_guard.take()` so its own refusals don't fail it."""
    return NETWORK


@pytest.fixture
def conn():
    from jura_growth import db

    connection = db.connect()
    yield connection
    connection.close()
