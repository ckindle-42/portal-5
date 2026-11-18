"""Unit tests for scenario x container matrix (synthetic/dry-run — no Docker)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from portal.modules.security.core.matrix import (
    _expand_vulhub_globs,
)


@pytest.fixture(autouse=True)
def _no_real_ssh(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default: no vulhub envs resolve on the (unmocked) host — never make a real ssh call
    in the unit suite. Tests that need fixture matches override with _fake_host_exec_factory.
    """
    monkeypatch.setattr(
        "scripts.lab_host._host_exec", lambda cmd, timeout=20: {"ok": True, "output": ""}
    )


class TestVulhubGlobExpansion:
    """_expand_vulhub_globs always resolves via _host_exec against the live host — never
    a local glob. These tests mock _host_exec with a fixture tree standing in for LXC 112."""

    def test_expansion_calls_host_exec_not_local_glob(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression guard: resolution must go through _host_exec (the host), never a
        local filesystem glob — this is the wrong-machine bug the task fixes."""
        # Local fixture tree exists on disk, but _host_exec is mocked to report nothing —
        # if the code fell back to local glob.glob, it would still find these local dirs.
        d = tmp_path / "fastjson" / "CVE-local-only"
        d.mkdir(parents=True)
        (d / "docker-compose.yml").write_text("version: '3'\n")

        calls: list[str] = []

        def _tracking_empty(cmd: str, timeout: int = 20) -> dict[str, Any]:
            calls.append(cmd)
            return {"ok": True, "output": ""}

        monkeypatch.setattr("scripts.lab_host._host_exec", _tracking_empty)
        result = _expand_vulhub_globs(["fastjson/*"], tmp_path)
        assert calls, "_expand_vulhub_globs must call _host_exec"
        assert result == [], "must not fall back to local glob when host reports no matches"
