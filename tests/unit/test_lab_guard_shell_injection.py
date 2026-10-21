"""Mechanical grader for BRIEF_LAB_GUARD_SHELL_INJECTION.md.

Verifies dispatch_blue_response/verify_defense reject shell-metacharacter
payloads in `ip`/`username` BEFORE they reach _lab_mcp_call, while still
dispatching valid values. Mocks _lab_mcp_call — no lab/network/Docker
required, no stack dependency.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from portal.modules.security.core.lab import dispatch_blue_response, verify_defense

INJECTION_IPS = [
    "10.10.11.50; rm -rf /tmp",
    "10.10.11.50 && whoami",
    "$(whoami)",
    "`id`",
    "10.10.11.50' OR '1'='1",
    "10.10.11.50|cat /etc/passwd",
]

INJECTION_USERNAMES = [
    "administrator && del /f /s /q C:\\",
    "a' ; whoami #",
    "admin`id`",
    "$(whoami)",
    "admin|net user hacker /add",
    "admin\nnet user hacker /add",
]

VALID_IP = "10.10.11.50"
VALID_USERNAME = "jdoe"


@pytest.fixture(autouse=True)
def _lab_exec_available():
    with patch("portal.modules.security.core.lab._LAB_EXEC_AVAILABLE", True):
        yield


@pytest.mark.parametrize("bad_ip", INJECTION_IPS)
def test_dispatch_block_ip_rejects_injection_without_calling_sandbox(bad_ip):
    with patch("portal.modules.security.core.lab._lab_mcp_call") as mock_call:
        result = dispatch_blue_response("block_ip", {"ip": bad_ip})
    mock_call.assert_not_called()
    assert result["ok"] is False


@pytest.mark.parametrize("bad_username", INJECTION_USERNAMES)
def test_dispatch_disable_account_rejects_injection_without_calling_sandbox(bad_username):
    with patch("portal.modules.security.core.lab._lab_mcp_call") as mock_call:
        result = dispatch_blue_response("disable_account", {"username": bad_username})
    mock_call.assert_not_called()
    assert result["ok"] is False


@pytest.mark.parametrize("bad_ip", INJECTION_IPS)
def test_verify_defense_block_ip_rejects_injection_without_calling_sandbox(bad_ip):
    with patch("portal.modules.security.core.lab._lab_mcp_call") as mock_call:
        result = verify_defense("block_ip", {"ip": bad_ip})
    mock_call.assert_not_called()
    assert result["verified"] is False


@pytest.mark.parametrize("bad_username", INJECTION_USERNAMES)
def test_verify_defense_disable_account_rejects_injection_without_calling_sandbox(bad_username):
    with patch("portal.modules.security.core.lab._lab_mcp_call") as mock_call:
        result = verify_defense("disable_account", {"username": bad_username})
    mock_call.assert_not_called()
    assert result["verified"] is False


def test_dispatch_block_ip_still_dispatches_valid_ip():
    with patch("portal.modules.security.core.lab._lab_mcp_call") as mock_call:
        mock_call.return_value = {"output": "ok", "elapsed_s": 0.1}
        dispatch_blue_response("block_ip", {"ip": VALID_IP})
    mock_call.assert_called_once()
    assert VALID_IP in mock_call.call_args.args[0]


def test_dispatch_disable_account_still_dispatches_valid_username():
    with patch("portal.modules.security.core.lab._lab_mcp_call") as mock_call:
        mock_call.return_value = {"output": "ok", "elapsed_s": 0.1}
        dispatch_blue_response("disable_account", {"username": VALID_USERNAME})
    mock_call.assert_called_once()
    assert VALID_USERNAME in mock_call.call_args.args[0]


def test_dispatch_revoke_tgt_untouched():
    with patch("portal.modules.security.core.lab._lab_mcp_call") as mock_call:
        mock_call.return_value = {"output": "ok", "elapsed_s": 0.1}
        result = dispatch_blue_response("revoke_tgt", {})
    mock_call.assert_called_once()
    assert result["ok"] is True
