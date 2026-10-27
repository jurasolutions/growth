"""The network guard proves itself (test strategy v3 §2, AC-M15.1).

No test may reach anything but loopback. A refused lookup or connection
raises, and is recorded, so a test that swallows the error still fails.
"""

import socket

import pytest


def test_a_lookup_and_a_connection_outside_loopback_are_refused_and_recorded(network_guard):
    with pytest.raises(PermissionError, match="discord.com"):
        socket.getaddrinfo("discord.com", 443)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        with pytest.raises(PermissionError, match="1.1.1.1"):
            sock.connect(("1.1.1.1", 443))
    recorded = network_guard.take()
    assert len(recorded) == 2
    assert recorded[0].startswith("socket.getaddrinfo discord.com")
    assert recorded[1].startswith("socket.connect 1.1.1.1:443")


def test_a_swallowed_refusal_is_still_recorded(network_guard):
    try:
        socket.create_connection(("example.com", 80), timeout=1)
    except OSError:
        pass
    assert [r.split()[0] for r in network_guard.take()] == ["socket.getaddrinfo"]


def test_a_localhost_subdomain_may_be_looked_up(network_guard):
    """The rehearsal fixture site's host. Whether this Mac's resolver
    answers is its own business; the guard lets the lookup through."""
    try:
        socket.getaddrinfo("publish-fixture.localhost", 80)
    except socket.gaierror:
        pass
    assert network_guard.take() == []


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_loopback_is_allowed(network_guard, host):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        family = socket.AF_INET
        info = socket.getaddrinfo(host, port, family, socket.SOCK_STREAM)
        with socket.create_connection(info[0][4][:2], timeout=2):
            pass
    assert network_guard.take() == []


def test_unix_sockets_are_allowed(network_guard, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # a relative path: tmp_path is longer than AF_UNIX allows
    path = "s"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(path)
        server.listen(1)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(path)
    assert network_guard.take() == []
