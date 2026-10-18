"""WFE unit tests run offline."""

import ipaddress
import socket

import pytest


@pytest.fixture(autouse=True)
def _offline_wfe(monkeypatch, tmp_path_factory):
    from tests.wfe import campaign, eval_mode, runner

    localhost_connects = []
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def is_localhost(address):
        if not isinstance(address, tuple) or not address:
            return False
        host = str(address[0]).strip("[]").lower()
        if host == "localhost":
            return True
        try:
            return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
        except ValueError:
            return False

    def block_localhost_connect(sock, address):
        if is_localhost(address):
            localhost_connects.append(address)
            raise ConnectionRefusedError(f"WFE unit tests may not connect to localhost: {address}")
        return real_connect(sock, address)

    def block_localhost_connect_ex(sock, address):
        if is_localhost(address):
            localhost_connects.append(address)
            return 111
        return real_connect_ex(sock, address)

    monkeypatch.setattr(socket.socket, "connect", block_localhost_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", block_localhost_connect_ex)

    # Evaluation-scope seeding and cleanup POST to live MCP ports; tests stub or record them.
    monkeypatch.setattr(eval_mode, "eval_post", lambda url, body: None)
    # Production-mode rows stage under OUTPUT_ROOT: never the developer's real ~/AI_Output.
    monkeypatch.setattr(eval_mode, "OUTPUT_ROOT", tmp_path_factory.mktemp("ai_output"))
    fixed = {"ollama_version": "test", "host": "test"}
    monkeypatch.setattr(campaign, "env_fingerprint", lambda *a, **k: dict(fixed))
    monkeypatch.setattr(runner, "env_fingerprint", lambda *a, **k: dict(fixed))
    monkeypatch.setattr(runner, "_ollama_can_think", lambda *a, **k: False)
    # The developer's tree is often dirty; tests of the gate patch this themselves.
    monkeypatch.setattr(campaign, "instrument_dirty", lambda: [])
    head = campaign._git("rev-parse", "HEAD").strip()
    monkeypatch.setattr(campaign, "deployed_build", lambda: head)
    monkeypatch.setattr(campaign, "deployed_services", lambda: {})
    yield
    if localhost_connects:
        pytest.fail(
            f"WFE unit test attempted a real localhost socket connection: {localhost_connects}",
            pytrace=False,
        )
