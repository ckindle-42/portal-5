"""Lab-exec posture selection for the code sandbox MCP.

Pure flag/logic tests — no Docker, no network. Each test reimports the module
under a fresh env so module-level posture constants re-resolve.
"""

from __future__ import annotations

import importlib
import sys

MOD = "portal.modules.coding.tools.code_sandbox_mcp"


def _reload(monkeypatch, **env):
    for k in (
        "SANDBOX_LAB_EXEC",
        "SANDBOX_ALLOW_NETWORK",
        "SANDBOX_LAB_IMAGE",
        "LAB_TARGET_DC",
        "LAB_TARGET_META3_WIN",
        "LAB_META3_USER",
        "LAB_META3_PASS",
    ):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    sys.modules.pop(MOD, None)
    return importlib.import_module(MOD)


def test_default_posture_locked_down(monkeypatch):
    m = _reload(monkeypatch)
    assert m.SANDBOX_LAB_EXEC is False
    assert m.SANDBOX_ALLOW_NETWORK is False
    assert m._resolve_image(m.BASH_IMAGE) == m.BASH_IMAGE


def test_lab_exec_uses_attack_image(monkeypatch):
    m = _reload(
        monkeypatch,
        SANDBOX_LAB_EXEC="true",
        SANDBOX_LAB_IMAGE="reg/attack:latest",
    )
    assert m.SANDBOX_LAB_EXEC is True
    assert m._resolve_image(m.PYTHON_IMAGE) == "reg/attack:latest"


def test_lab_exec_without_image_falls_back(monkeypatch):
    m = _reload(monkeypatch, SANDBOX_LAB_EXEC="true")
    # Empty SANDBOX_LAB_IMAGE -> default image retained (warns at runtime).
    assert m._resolve_image(m.BASH_IMAGE) == m.BASH_IMAGE


def test_lab_exec_injects_target_env(monkeypatch):
    m = _reload(
        monkeypatch,
        SANDBOX_LAB_EXEC="true",
        LAB_TARGET_DC="10.0.0.10",
        LAB_TARGET_META3_WIN="10.0.0.13",
        LAB_META3_USER="meta3-user",
        LAB_META3_PASS="meta3-pass",
    )
    assert m.SANDBOX_LAB_TARGET_DC == "10.0.0.10"
    assert m.SANDBOX_LAB_TARGET_META3 == "10.0.0.13"
    assert m.SANDBOX_LAB_META3_USER == "meta3-user"
    assert m.SANDBOX_LAB_META3_PASS == "meta3-pass"


def test_lab_exec_meta3_credentials_have_documented_defaults(monkeypatch):
    m = _reload(monkeypatch, SANDBOX_LAB_EXEC="true")
    assert m.SANDBOX_LAB_META3_USER == "vagrant"
    assert m.SANDBOX_LAB_META3_PASS == "vagrant"
