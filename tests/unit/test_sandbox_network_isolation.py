from __future__ import annotations

from types import SimpleNamespace

import pytest

from portal.modules.coding.tools import code_sandbox_mcp as sandbox


class _DockerProcess:
    returncode = 0

    async def communicate(self):
        return b"", b""


@pytest.mark.asyncio
async def test_code_execution_stays_offline_when_network_flags_are_enabled(monkeypatch, tmp_path):
    command: list[str] = []

    async def create_subprocess_exec(*args, **_kwargs):
        command.extend(args)
        return _DockerProcess()

    monkeypatch.setattr(sandbox, "SANDBOX_DIR", tmp_path)
    monkeypatch.setattr(sandbox, "SANDBOX_ALLOW_NETWORK", True)
    monkeypatch.setattr(sandbox, "SANDBOX_LAB_EXEC", True)
    monkeypatch.setattr(sandbox.asyncio, "create_subprocess_exec", create_subprocess_exec)

    result = await sandbox._run_in_docker("python:3.11-slim", ["python3", "/code"], "pass", 1)

    assert result["success"] is True
    assert command[command.index("--network") + 1] == "none"


@pytest.mark.asyncio
async def test_package_install_container_stays_offline(monkeypatch, tmp_path):
    command: list[str] = []

    async def create_subprocess_exec(*args, **_kwargs):
        command.extend(args)
        return _DockerProcess()

    monkeypatch.setattr(sandbox, "SANDBOX_PIP_INSTALL_ENABLED", True)
    monkeypatch.setattr(sandbox.asyncio, "create_subprocess_exec", create_subprocess_exec)

    result = await sandbox._install_packages(tmp_path, "python:3.11-slim", "python", ["requests"])

    assert result["installed"] == ["requests"]
    assert command[command.index("--network") + 1] == "none"


@pytest.mark.parametrize("setting", ["SANDBOX_ALLOW_NETWORK", "SANDBOX_LAB_EXEC"])
def test_startup_isolation_check_refuses_network_opt_ins(monkeypatch, setting):
    monkeypatch.setattr(sandbox, setting, True)
    monkeypatch.setattr(
        sandbox.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("Docker must not run for an unsafe configuration"),
    )

    with pytest.raises(RuntimeError, match="network isolation"):
        sandbox._verify_network_isolation()


def test_startup_isolation_check_refuses_daemon_that_did_not_apply_none_network(
    monkeypatch,
):
    calls: list[list[str]] = []

    def run(command, **_kwargs):
        calls.append(command)
        if command[1] == "create":
            return SimpleNamespace(stdout="container-id\n")
        if command[1] == "inspect":
            return SimpleNamespace(stdout="bridge\n")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(sandbox, "SANDBOX_ALLOW_NETWORK", False)
    monkeypatch.setattr(sandbox, "SANDBOX_LAB_EXEC", False)
    monkeypatch.setattr(sandbox.subprocess, "run", run)

    with pytest.raises(RuntimeError, match="network isolation"):
        sandbox._verify_network_isolation()

    assert calls[0][0:4] == ["docker", "create", "--network", "none"]
    assert calls[-1][0:3] == ["docker", "rm", "--force"]


def test_startup_isolation_check_accepts_daemon_none_network(monkeypatch):
    calls: list[list[str]] = []

    def run(command, **_kwargs):
        calls.append(command)
        if command[1] == "create":
            return SimpleNamespace(stdout="container-id\n")
        if command[1] == "inspect":
            return SimpleNamespace(stdout="none\n")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(sandbox, "SANDBOX_ALLOW_NETWORK", False)
    monkeypatch.setattr(sandbox, "SANDBOX_LAB_EXEC", False)
    monkeypatch.setattr(sandbox.subprocess, "run", run)

    sandbox._verify_network_isolation()

    assert calls[0][0:4] == ["docker", "create", "--network", "none"]
    assert calls[-1][0:3] == ["docker", "rm", "--force"]
