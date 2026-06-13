"""SANDBOX_ALLOW_NETWORK flag — default-off posture + opt-in widening.

Asserts the source wiring without launching Docker (CI-safe).
"""
from pathlib import Path

SRC = Path("portal_mcp/execution/code_sandbox_mcp.py").read_text()


def test_flag_defined_default_off():
    assert 'SANDBOX_ALLOW_NETWORK = os.getenv("SANDBOX_ALLOW_NETWORK", "false")' in SRC


def test_network_conditional():
    assert '_net = "bridge" if SANDBOX_ALLOW_NETWORK else "none"' in SRC


def test_resource_envelope_conditional():
    assert "_cpus = SANDBOX_NET_CPUS if SANDBOX_ALLOW_NETWORK else" in SRC
    assert "_mem = SANDBOX_NET_MEMORY if SANDBOX_ALLOW_NETWORK else" in SRC


def test_timeout_cap_conditional():
    assert "SANDBOX_NET_TIMEOUT_MAX if SANDBOX_ALLOW_NETWORK else 120" in SRC


def test_health_reports_network_honestly():
    assert '"network": "bridge" if SANDBOX_ALLOW_NETWORK else "disabled"' in SRC
