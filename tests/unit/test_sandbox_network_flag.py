"""SANDBOX_ALLOW_NETWORK flag — default-off posture + opt-in widening.

Asserts the source wiring without launching Docker (CI-safe).
"""

from pathlib import Path

SRC = Path("portal_mcp/execution/code_sandbox_mcp.py").read_text()


def test_flag_defined_default_off():
    assert 'SANDBOX_ALLOW_NETWORK = os.getenv("SANDBOX_ALLOW_NETWORK", "false")' in SRC


def test_network_conditional():
    # lab-exec is a superset of ALLOW_NETWORK — both use bridge; only default uses none.
    assert "_network_on = SANDBOX_ALLOW_NETWORK or SANDBOX_LAB_EXEC" in SRC
    assert '_net = "bridge" if _network_on else "none"' in SRC


def test_resource_envelope_conditional():
    # Three-tier envelope: lab-exec (widest) > allow-network > default (locked-down).
    assert "_cpus, _mem = SANDBOX_LAB_CPUS, SANDBOX_LAB_MEMORY" in SRC
    assert "_cpus, _mem = SANDBOX_NET_CPUS, SANDBOX_NET_MEMORY" in SRC


def test_timeout_cap_conditional():
    assert "SANDBOX_NET_TIMEOUT_MAX if SANDBOX_ALLOW_NETWORK else 120" in SRC


def test_health_reports_network_honestly():
    # Lab-exec also routes through bridge — both flags enable bridge
    assert '"network": "bridge" if SANDBOX_ALLOW_NETWORK or SANDBOX_LAB_EXEC else "disabled"' in SRC


def test_writable_root_tmpfs_for_pip():
    assert "/root:size=256m,exec" in SRC


def test_pythonpath_set_for_user_installs():
    assert "PYTHONPATH=/root/.local/lib/python3.11/site-packages" in SRC
