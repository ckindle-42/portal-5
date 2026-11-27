from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from portal.modules.coding.tools import code_sandbox_mcp as sandbox


class _DockerProcess:
    returncode = 0

    async def communicate(self):
        return b"", b""


def _lab_network_inspect(
    *,
    network_id="a" * 64,
    driver="bridge",
    internal="false",
    lab_label="true",
    target_label="192.168.56.0/24",
    inter_container="false",
    subnet="172.30.0.0/24",
):
    return SimpleNamespace(
        returncode=0,
        stdout="|".join(
            (network_id, driver, internal, lab_label, target_label, inter_container, subnet)
        ),
    )


@pytest.mark.parametrize(
    ("first_id", "second_id"),
    [("team/alpha", "teamalpha"), ("a" * 48 + "x", "a" * 48 + "y")],
)
def test_session_directories_keep_distinct_ids_separate(monkeypatch, tmp_path, first_id, second_id):
    monkeypatch.setattr(sandbox, "SANDBOX_SESSIONS_DIR", tmp_path / "sessions")
    legacy_session = sandbox.SANDBOX_SESSIONS_DIR / "v2" / sandbox._safe_session_id(first_id)
    legacy_session.mkdir(parents=True)
    legacy_session.chmod(0o777)
    (legacy_session.parent / f"{legacy_session.name}.owner").write_text(first_id, encoding="utf-8")

    first = sandbox._session_dir(first_id)
    second = sandbox._session_dir(second_id)

    assert first != second
    assert {row["session_id"] for row in sandbox._list_sessions()} == {
        first_id,
        second_id,
    }
    assert first.stat().st_mode & 0o777 == 0o700
    assert second.stat().st_mode & 0o777 == 0o700
    assert first.stat().st_uid == os.getuid()
    assert first.stat().st_gid == os.getgid()


def test_reset_session_does_not_delete_a_distinct_session(monkeypatch, tmp_path):
    monkeypatch.setattr(sandbox, "SANDBOX_SESSIONS_DIR", tmp_path / "sessions")
    first = sandbox._session_dir("team/alpha")
    second = sandbox._session_dir("teamalpha")
    (second / "state").write_text("owned by teamalpha", encoding="utf-8")

    result = sandbox.reset_session("team/alpha")

    assert result["reset"] is True
    assert not first.exists()
    assert (second / "state").read_text(encoding="utf-8") == "owned by teamalpha"


def test_session_key_collision_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(sandbox, "SANDBOX_SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(sandbox, "_safe_session_id", lambda _session_id: "same-key")
    first = sandbox._session_dir("first")
    (first / "state").write_text("owned by first", encoding="utf-8")

    with pytest.raises(RuntimeError, match="session identifier key collision"):
        sandbox._session_dir("second")
    with pytest.raises(RuntimeError, match="session identifier key collision"):
        sandbox.reset_session("second")

    assert (first / "state").read_text(encoding="utf-8") == "owned by first"


@pytest.mark.asyncio
@pytest.mark.parametrize("workspace", ["auto-coding", "auto-security::pentest"])
async def test_general_code_stays_offline_when_lab_mode_is_enabled(
    monkeypatch, tmp_path, workspace
):
    command: list[str] = []

    async def create_subprocess_exec(*args, **_kwargs):
        command.extend(args)
        return _DockerProcess()

    monkeypatch.setattr(sandbox, "SANDBOX_DIR", tmp_path)
    monkeypatch.setattr(sandbox, "SANDBOX_ALLOW_NETWORK", True)
    monkeypatch.setattr(sandbox, "SANDBOX_LAB_EXEC", True)
    monkeypatch.setattr(sandbox, "GENERAL_EXEC_AVAILABLE", True)
    monkeypatch.setattr(sandbox, "LAB_EXEC_AVAILABLE", True)
    monkeypatch.setattr(sandbox, "GENERAL_EXEC_STATE", "ready")
    monkeypatch.setattr(sandbox, "LAB_EXEC_STATE", "ready")
    token = sandbox.WORKSPACE_ID.set(workspace)
    monkeypatch.setattr(sandbox.asyncio, "create_subprocess_exec", create_subprocess_exec)
    try:
        result = await sandbox.execute_python("print('offline')")
    finally:
        sandbox.WORKSPACE_ID.reset(token)

    assert result["success"] is True
    assert command[command.index("--network") + 1] == "none"


@pytest.mark.asyncio
async def test_python_sessions_use_fresh_containers_and_distinct_mounts(monkeypatch, tmp_path):
    commands: list[list[str]] = []
    mount_metadata: list[dict[str, tuple[int, int, int]]] = []

    async def create_subprocess_exec(*args, **_kwargs):
        commands.append(list(args))
        mounts = {}
        for index, value in enumerate(args[:-1]):
            if value != "-v":
                continue
            source, target, *_ = args[index + 1].split(":")
            if target in {"/session", "/workspace", "/out"}:
                info = Path(source).stat()
                mounts[target] = (info.st_uid, info.st_gid, info.st_mode)
        mount_metadata.append(mounts)
        return _DockerProcess()

    monkeypatch.setattr(sandbox, "SANDBOX_DIR", tmp_path)
    monkeypatch.setattr(sandbox, "SANDBOX_SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(sandbox, "GENERAL_EXEC_AVAILABLE", True)
    monkeypatch.setattr(sandbox, "GENERAL_EXEC_STATE", "ready")
    monkeypatch.setattr(sandbox.asyncio, "create_subprocess_exec", create_subprocess_exec)

    first = await sandbox.execute_python("print('first')", session_id="uat_iso_a")
    second = await sandbox.execute_python("print('second')", session_id="uat_iso_b")

    assert first["success"] is True
    assert second["success"] is True
    assert [command[:3] for command in commands] == [
        ["docker", "run", "--rm"],
        ["docker", "run", "--rm"],
    ]
    mounts = [
        command[index + 1]
        for command in commands
        for index, value in enumerate(command[:-1])
        if value == "-v" and command[index + 1].endswith(":/session")
    ]
    assert len(mounts) == 2
    assert mounts[0] != mounts[1]
    for command, metadata in zip(commands, mount_metadata, strict=True):
        assert command[command.index("--user") + 1] == f"{os.getuid()}:{os.getgid()}"
        assert set(metadata) == {"/session", "/workspace", "/out"}
        assert {owner for owner, _, _ in metadata.values()} == {os.getuid()}
        assert {group for _, group, _ in metadata.values()} == {os.getgid()}
        assert all(mode & 0o002 == 0 for _, _, mode in metadata.values())


@pytest.mark.asyncio
async def test_exec_variant_uses_the_lab_network(monkeypatch, tmp_path):
    command: list[str] = []

    async def create_subprocess_exec(*args, **_kwargs):
        command.extend(args)
        return _DockerProcess()

    monkeypatch.setattr(sandbox, "SANDBOX_DIR", tmp_path)
    monkeypatch.setattr(sandbox, "SANDBOX_LAB_EXEC", True)
    monkeypatch.setattr(sandbox, "SANDBOX_LAB_IMAGE", "portal5-attack:latest")
    monkeypatch.setattr(sandbox, "LAB_EXEC_AVAILABLE", True)
    monkeypatch.setattr(sandbox, "LAB_EXEC_STATE", "ready")
    monkeypatch.setattr(sandbox.asyncio, "create_subprocess_exec", create_subprocess_exec)
    token = sandbox.WORKSPACE_ID.set("auto-security::purpleteam-exec")
    try:
        result = await sandbox.execute_bash("true")
    finally:
        sandbox.WORKSPACE_ID.reset(token)

    assert result["success"] is True
    assert command[command.index("--network") + 1] == sandbox.LAB_EXEC_NETWORK


@pytest.mark.asyncio
async def test_package_install_stays_offline_in_exec_variant(monkeypatch, tmp_path):
    command: list[str] = []

    async def create_subprocess_exec(*args, **_kwargs):
        command.extend(args)
        return _DockerProcess()

    monkeypatch.setattr(sandbox, "SANDBOX_LAB_EXEC", True)
    monkeypatch.setattr(sandbox.asyncio, "create_subprocess_exec", create_subprocess_exec)
    result = await sandbox._install_packages(tmp_path, "python:3.11-slim", "python", ["requests"])

    assert result["installed"] == ["requests"]
    assert command[command.index("--network") + 1] == "none"
    assert command[command.index("--user") + 1] == f"{os.getuid()}:{os.getgid()}"


def test_general_self_check_accepts_none_even_when_lab_mode_is_enabled(monkeypatch):
    calls: list[list[str]] = []

    def run(command, **_kwargs):
        calls.append(command)
        if command[1] == "create":
            return SimpleNamespace(returncode=0, stdout="container-id\n")
        if command[1] == "inspect":
            return SimpleNamespace(returncode=0, stdout="none\n")
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(sandbox, "SANDBOX_LAB_EXEC", True)
    monkeypatch.setattr(sandbox, "SANDBOX_ALLOW_NETWORK", False)
    monkeypatch.setattr(sandbox.subprocess, "run", run)

    sandbox._verify_general_network_isolation()

    assert calls[0][0:4] == ["docker", "create", "--network", "none"]
    assert calls[-1][0:3] == ["docker", "rm", "--force"]


def test_general_self_check_rejects_a_networked_container(monkeypatch):
    def run(command, **_kwargs):
        if command[1] == "create":
            return SimpleNamespace(returncode=0, stdout="container-id\n")
        if command[1] == "inspect":
            return SimpleNamespace(returncode=0, stdout="bridge\n")
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(sandbox.subprocess, "run", run)

    with pytest.raises(RuntimeError, match="network isolation"):
        sandbox._verify_general_network_isolation()


def test_startup_disables_only_general_executor_when_none_is_not_applied(monkeypatch):
    monkeypatch.setattr(sandbox, "SANDBOX_LAB_EXEC", True)
    monkeypatch.setattr(sandbox, "GENERAL_EXEC_AVAILABLE", True)
    monkeypatch.setattr(sandbox, "LAB_EXEC_AVAILABLE", False)
    monkeypatch.setattr(sandbox, "_provision_executor_images", lambda: None)
    monkeypatch.setattr(
        sandbox,
        "_verify_general_network_isolation",
        lambda: (_ for _ in ()).throw(RuntimeError("network=none was not applied")),
    )
    monkeypatch.setattr(sandbox, "_verify_lab_network_isolation", lambda: None)

    sandbox._verify_network_isolation()

    assert sandbox.GENERAL_EXEC_AVAILABLE is False
    assert sandbox.LAB_EXEC_AVAILABLE is True


def test_startup_disables_only_lab_executor_when_lab_firewall_check_fails(monkeypatch):
    monkeypatch.setattr(sandbox, "SANDBOX_LAB_EXEC", True)
    monkeypatch.setattr(sandbox, "GENERAL_EXEC_AVAILABLE", True)
    monkeypatch.setattr(sandbox, "LAB_EXEC_AVAILABLE", True)
    monkeypatch.setattr(sandbox, "_provision_executor_images", lambda: None)
    monkeypatch.setattr(sandbox, "_verify_general_network_isolation", lambda: None)
    monkeypatch.setattr(
        sandbox,
        "_verify_lab_network_isolation",
        lambda: (_ for _ in ()).throw(RuntimeError("lab firewall check failed")),
    )

    sandbox._verify_network_isolation()

    assert sandbox.GENERAL_EXEC_AVAILABLE is True
    assert sandbox.LAB_EXEC_AVAILABLE is False


def test_startup_keeps_both_executors_when_both_policies_pass(monkeypatch):
    checked: list[str] = []
    monkeypatch.setattr(sandbox, "SANDBOX_LAB_EXEC", True)
    monkeypatch.setattr(sandbox, "GENERAL_EXEC_AVAILABLE", False)
    monkeypatch.setattr(sandbox, "LAB_EXEC_AVAILABLE", False)
    monkeypatch.setattr(sandbox, "_provision_executor_images", lambda: None)
    monkeypatch.setattr(
        sandbox,
        "_verify_general_network_isolation",
        lambda: checked.append("general"),
    )
    monkeypatch.setattr(
        sandbox,
        "_verify_lab_network_isolation",
        lambda: checked.append("lab"),
    )

    sandbox._verify_network_isolation()

    assert checked == ["general", "lab"]
    assert sandbox.GENERAL_EXEC_AVAILABLE is True
    assert sandbox.LAB_EXEC_AVAILABLE is True


def test_executor_images_are_provisioned_before_isolation_checks(monkeypatch):
    calls: list[str] = []

    def run(command, **_kwargs):
        calls.append(" ".join(command))
        if command[1:3] == ["image", "inspect"] and command[-1] == "node:20-alpine":
            return SimpleNamespace(returncode=1, stdout="", stderr="missing")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(sandbox, "SANDBOX_LAB_EXEC", True)
    monkeypatch.setattr(sandbox, "SANDBOX_LAB_IMAGE", "portal5-attack:latest")
    monkeypatch.setattr(sandbox.subprocess, "run", run)
    monkeypatch.setattr(
        sandbox, "_verify_general_network_isolation", lambda: calls.append("general check")
    )
    monkeypatch.setattr(sandbox, "_verify_lab_network_isolation", lambda: None)

    sandbox._verify_network_isolation()

    assert "docker pull node:20-alpine" in calls
    assert calls.index("docker pull node:20-alpine") < calls.index("general check")
    for image in (sandbox.PYTHON_IMAGE, sandbox.NODE_IMAGE, sandbox.BASH_IMAGE, sandbox.PS_IMAGE):
        assert f"docker image inspect {image}" in calls
    assert "docker image inspect portal5-attack:latest" in calls


def test_missing_executor_image_pull_uses_bounded_backoff(monkeypatch):
    pull_attempts = 0
    waits: list[float] = []

    def run(command, **_kwargs):
        nonlocal pull_attempts
        if command[1:3] == ["image", "inspect"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="missing")
        if command[1] == "pull":
            pull_attempts += 1
            return SimpleNamespace(
                returncode=0 if pull_attempts == 3 else 1,
                stdout="",
                stderr="registry unavailable",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    for name in ("PYTHON_IMAGE", "NODE_IMAGE", "BASH_IMAGE", "PS_IMAGE"):
        monkeypatch.setattr(sandbox, name, "python:3.11-slim")
    monkeypatch.setattr(sandbox, "SANDBOX_LAB_EXEC", False)
    monkeypatch.setattr(sandbox.subprocess, "run", run)
    monkeypatch.setattr(sandbox.time, "sleep", waits.append)

    sandbox._provision_executor_images()

    assert pull_attempts == 3
    assert waits == [1, 2]


def test_missing_local_portal_image_waits_for_launcher_provisioning(monkeypatch):
    commands: list[list[str]] = []

    def run(command, **_kwargs):
        commands.append(command)
        if command[1] == "info":
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="missing")

    for name in ("PYTHON_IMAGE", "NODE_IMAGE", "BASH_IMAGE", "PS_IMAGE"):
        monkeypatch.setattr(sandbox, name, "portal5-sandbox-data:latest")
    monkeypatch.setattr(sandbox, "SANDBOX_LAB_EXEC", False)
    monkeypatch.setattr(sandbox.subprocess, "run", run)

    with pytest.raises(sandbox.ExecutorNotReadyError, match="awaiting launch provisioning"):
        sandbox._provision_executor_images()

    assert not any(command[1] == "pull" for command in commands)


def test_daemon_not_ready_leaves_executor_starting_until_a_later_check(monkeypatch):
    daemon_ready = False
    checked: list[str] = []

    def run(command, **_kwargs):
        if command[1] == "info" and not daemon_ready:
            return SimpleNamespace(returncode=1, stdout="", stderr="Cannot connect")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(sandbox, "SANDBOX_LAB_EXEC", False)
    monkeypatch.setattr(sandbox.subprocess, "run", run)
    monkeypatch.setattr(
        sandbox, "_verify_general_network_isolation", lambda: checked.append("general")
    )
    monkeypatch.setattr(sandbox, "_verify_lab_network_isolation", lambda: None)

    sandbox._verify_network_isolation()

    assert sandbox.GENERAL_EXEC_STATE == "starting"
    assert sandbox.GENERAL_EXEC_AVAILABLE is False
    assert sandbox._executor_unavailable(False)["error_type"] == "general_executor_starting"
    response = asyncio.run(sandbox.health_check(None))
    assert response.status_code == 503
    assert json.loads(response.body)["executors"]["general"]["state"] == "starting"
    assert checked == []

    daemon_ready = True
    sandbox._verify_network_isolation()

    assert sandbox.GENERAL_EXEC_STATE == "ready"
    assert sandbox.GENERAL_EXEC_AVAILABLE is True
    assert checked == ["general"]


def test_isolation_violation_disables_executor_and_degrades_health(monkeypatch):
    monkeypatch.setattr(sandbox, "SANDBOX_LAB_EXEC", False)
    monkeypatch.setattr(sandbox, "_provision_executor_images", lambda: None)
    monkeypatch.setattr(
        sandbox,
        "_verify_general_network_isolation",
        lambda: (_ for _ in ()).throw(sandbox.ExecutorIsolationError("network mode is bridge")),
    )

    sandbox._verify_network_isolation()
    response = asyncio.run(sandbox.health_check(None))
    payload = json.loads(response.body)

    assert sandbox.GENERAL_EXEC_STATE == "disabled"
    assert sandbox._executor_unavailable(False)["error_type"] == "general_executor_unavailable"
    assert response.status_code == 503
    assert payload["status"] == "degraded"
    assert payload["executors"]["general"]["state"] == "disabled"


def test_monitor_rechecks_disabled_executor_and_recovers(monkeypatch):
    class StopAfterTwoWaits:
        waits = 0

        def is_set(self):
            return self.waits >= 2

        def wait(self, _timeout):
            self.waits += 1

    checks = 0

    def check():
        nonlocal checks
        checks += 1
        if checks == 1:
            sandbox.GENERAL_EXEC_STATE = "disabled"
            sandbox.GENERAL_EXEC_AVAILABLE = False
        else:
            sandbox.GENERAL_EXEC_STATE = "ready"
            sandbox.GENERAL_EXEC_AVAILABLE = True

    monkeypatch.setattr(sandbox, "_verify_network_isolation", check)
    sandbox._executor_monitor_loop(StopAfterTwoWaits())

    assert checks == 2
    assert sandbox.GENERAL_EXEC_STATE == "ready"


def test_lab_self_check_accepts_only_firewalled_dedicated_network(monkeypatch, tmp_path):
    network_id = "a" * 64
    bridge = f"br-{network_id[:12]}"
    status_file = tmp_path / "lab-network-status"
    status_file.write_text(
        f"portal5-labexec-v1\n192.168.56.0/24\n{network_id}\n{bridge}\n", encoding="utf-8"
    )
    monkeypatch.setattr(sandbox, "SANDBOX_LAB_EXEC", True)
    monkeypatch.setattr(sandbox, "SANDBOX_LAB_TARGET_NETWORK", "192.168.56.0/24")
    monkeypatch.setattr(sandbox, "LAB_EXEC_STATUS_FILE", status_file)
    monkeypatch.setattr(sandbox.subprocess, "run", lambda *_args, **_kwargs: _lab_network_inspect())

    sandbox._verify_lab_network_isolation()


@pytest.mark.parametrize(
    ("receipt", "expected_state"),
    [("daemon-unavailable", "starting"), ("unavailable", "disabled")],
)
def test_lab_receipt_distinguishes_daemon_startup_from_firewall_failure(
    monkeypatch, tmp_path, receipt, expected_state
):
    status_file = tmp_path / "lab-network-status"
    status_file.write_text(f"{receipt}\n", encoding="utf-8")
    monkeypatch.setattr(sandbox, "SANDBOX_LAB_EXEC", True)
    monkeypatch.setattr(sandbox, "SANDBOX_LAB_TARGET_NETWORK", "192.168.56.0/24")
    monkeypatch.setattr(sandbox, "LAB_EXEC_STATUS_FILE", status_file)
    monkeypatch.setattr(sandbox, "_provision_executor_images", lambda: None)
    monkeypatch.setattr(sandbox, "_verify_general_network_isolation", lambda: None)

    sandbox._verify_network_isolation()

    assert expected_state == sandbox.LAB_EXEC_STATE


@pytest.mark.parametrize("target", ["", "0.0.0.0/0", "8.8.8.0/24", "10.0.0.0/8"])
def test_lab_self_check_refuses_missing_or_unsafe_target_cidr(monkeypatch, tmp_path, target):
    monkeypatch.setattr(sandbox, "SANDBOX_LAB_EXEC", True)
    monkeypatch.setattr(sandbox, "SANDBOX_LAB_TARGET_NETWORK", target)
    monkeypatch.setattr(sandbox, "LAB_EXEC_STATUS_FILE", tmp_path / "missing")

    with pytest.raises(RuntimeError, match="lab network isolation"):
        sandbox._verify_lab_network_isolation()


@pytest.mark.parametrize(
    "inspect",
    [
        _lab_network_inspect(lab_label="", target_label=""),
        _lab_network_inspect(inter_container="true"),
        _lab_network_inspect(driver="bridge", subnet="192.168.56.0/24"),
        _lab_network_inspect(internal="true"),
    ],
)
def test_lab_self_check_rejects_unisolated_or_overlapping_network(monkeypatch, tmp_path, inspect):
    network_id = "a" * 64
    status_file = tmp_path / "lab-network-status"
    status_file.write_text(
        f"portal5-labexec-v1\n192.168.56.0/24\n{network_id}\nbr-{network_id[:12]}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sandbox, "SANDBOX_LAB_EXEC", True)
    monkeypatch.setattr(sandbox, "SANDBOX_LAB_TARGET_NETWORK", "192.168.56.0/24")
    monkeypatch.setattr(sandbox, "LAB_EXEC_STATUS_FILE", status_file)
    monkeypatch.setattr(sandbox.subprocess, "run", lambda *_args, **_kwargs: inspect)

    with pytest.raises(RuntimeError, match="lab network isolation"):
        sandbox._verify_lab_network_isolation()


def test_dind_lab_startup_installs_target_only_firewall_rules(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    rule_log = tmp_path / "rules.log"
    status_dir = tmp_path / "status"
    commands = {
        "dockerd-entrypoint.sh": '#!/bin/sh\nprintf \'%s\\n\' "$@" >"$ENTRYPOINT_ARGS_FILE"\n'
        'until [ -s "$PORTAL5_LAB_STATUS_DIR/lab-network-status" ]; do sleep 0.01; done\n',
        "docker": """#!/bin/sh
case "$1:$2" in
    info:)
        count=0
        [ -f "$DOCKER_INFO_COUNT" ] && count=$(cat "$DOCKER_INFO_COUNT")
        count=$((count + 1))
        echo "$count" >"$DOCKER_INFO_COUNT"
        [ "$count" -ge 3 ] ;;
    network:ls) echo 'bridge host none portal5-labexec' ;;
    network:inspect)
        [ "$3" = '--format' ] || exit 0
        case "$4" in
            *IPAM.Config*)
                case "$5" in
                    bridge) echo '172.17.0.0/16' ;;
                    portal5-labexec) echo '172.19.0.0/16' ;;
                esac ;;
            *) echo 'abcdef0123456789|bridge|false|true|192.168.56.0/24|false' ;;
        esac ;;
esac
""",
        "ip": """#!/bin/sh
case "$*" in
    '-4 route show dev eth0') echo '172.29.0.0/16 dev eth0' ;;
    '-4 route show default dev eth0') echo 'default via 172.29.0.1 dev eth0' ;;
esac
""",
        "iptables": """#!/bin/sh
printf '%s\\n' "$*" >>"$RULE_LOG"
case "$*" in
    *' -C INPUT '*) grep -F -x -- '-w -I INPUT 1 -i br-abcdef012345 -j DROP' "$RULE_LOG" >/dev/null ;;
    *' -C DOCKER-USER '*) grep -F -x -- '-w -I DOCKER-USER 1 -j PORTAL5-LABEXEC' "$RULE_LOG" >/dev/null ;;
    *' -C FORWARD '*) grep -F -x -- '-w -I FORWARD 1 -j DOCKER-USER' "$RULE_LOG" >/dev/null ;;
    *' -C PORTAL5-LABEXEC '*)
        expected=$(printf '%s\\n' "$*" | sed 's/ -C / -A /')
        grep -F -x -- "$expected" "$RULE_LOG" >/dev/null ;;
esac
""",
        "ip6tables": """#!/bin/sh
printf '%s\\n' "$*" >>"$RULE6_LOG"
case "$*" in
    *' -C INPUT '*) grep -F -x -- '-w -I INPUT 1 -i br-abcdef012345 -j DROP' "$RULE6_LOG" >/dev/null ;;
    *' -C DOCKER-USER '*) grep -F -x -- '-w -I DOCKER-USER 1 -j PORTAL5-LABEXEC' "$RULE6_LOG" >/dev/null ;;
    *' -C FORWARD '*) grep -F -x -- '-w -I FORWARD 1 -j DOCKER-USER' "$RULE6_LOG" >/dev/null ;;
    *' -C PORTAL5-LABEXEC '*)
        expected=$(printf '%s\\n' "$*" | sed 's/ -C / -A /')
        grep -F -x -- "$expected" "$RULE6_LOG" >/dev/null ;;
esac
""",
    }
    for name, contents in commands.items():
        executable = bin_dir / name
        executable.write_text(contents, encoding="utf-8")
        executable.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "PORTAL5_LAB_STATUS_DIR": str(status_dir),
            "RULE_LOG": str(rule_log),
            "RULE6_LOG": str(tmp_path / "rules6.log"),
            "DOCKER_INFO_COUNT": str(tmp_path / "docker-info-count"),
            "SANDBOX_LAB_EXEC": "true",
            "LAB_TARGET_NETWORK": "192.168.56.0/24",
            "ENTRYPOINT_ARGS_FILE": str(tmp_path / "entrypoint-args"),
        }
    )
    script = Path("portal/modules/coding/tools/dind_lab_network.sh")
    result = subprocess.run(
        [
            "sh",
            str(script),
            "dockerd",
            "--host=unix:///var/run/docker.sock",
            "--host=tcp://0.0.0.0:2375",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "docker-info-count").read_text(encoding="utf-8").strip() == "3"
    assert (tmp_path / "entrypoint-args").read_text(encoding="utf-8").splitlines() == [
        "dockerd",
        "--host=unix:///var/run/docker.sock",
        "--host=tcp://0.0.0.0:2375",
    ]
    assert (status_dir / "lab-network-status").read_text(encoding="utf-8").splitlines() == [
        "portal5-labexec-v1",
        "192.168.56.0/24",
        "abcdef0123456789",
        "br-abcdef012345",
    ]
    rules = rule_log.read_text(encoding="utf-8").splitlines()
    assert "-w -A PORTAL5-LABEXEC -i br-abcdef012345 -d 172.29.0.0/16 -j DROP" in rules
    assert "-w -A PORTAL5-LABEXEC -i br-abcdef012345 -d 172.19.0.0/16 -j DROP" not in rules
    target_allow = rules.index(
        "-w -A PORTAL5-LABEXEC -i br-abcdef012345 -d 192.168.56.0/24 -j ACCEPT"
    )
    target_drop = rules.index("-w -A PORTAL5-LABEXEC -i br-abcdef012345 -j DROP")
    assert target_allow < target_drop
