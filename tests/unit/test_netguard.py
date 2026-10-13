"""The unit-test offline boundary holds; a test's own local server still works."""

from __future__ import annotations

import os
import socket
import subprocess
import sys

import netguard
import pytest


@pytest.mark.live_port_ok
@pytest.mark.parametrize(
    "addr",
    [
        ("10.255.255.1", 80),
        ("host.docker.internal", 11434),
        ("example.com", 443),
        ("127.0.0.1", 11434),
        ("localhost", 9099),
    ],
)
def test_refused(addr):
    s = socket.socket()
    try:
        with pytest.raises(ConnectionRefusedError):
            s.connect(addr)
    finally:
        s.close()
    assert (addr[0], addr[1]) in netguard.HITS


def test_a_test_may_reach_its_own_local_server():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    assert port not in netguard.SERVICE_PORTS
    c = socket.socket()
    try:
        c.connect(("127.0.0.1", port))
    finally:
        c.close()
        srv.close()


@pytest.mark.live_port_ok
def test_python_subprocess_is_inside_the_boundary():
    code = (
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('127.0.0.1', 11434), timeout=2)\n"
        "    print('CONNECTED')\n"
        "except ConnectionRefusedError as e:\n"
        "    print('REFUSED', e)\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=os.environ
    )
    assert out.stdout.startswith("REFUSED"), out.stdout + out.stderr
    log = open(os.environ["PORTAL_NETGUARD_LOG"]).read()
    assert "127.0.0.1 11434" in log


def test_service_ports_come_from_config():
    assert {9099, 11434} <= netguard.SERVICE_PORTS
    assert 8927 in netguard.SERVICE_PORTS
