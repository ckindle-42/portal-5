"""Sandbox images: the refs the sandbox resolves, and `up` restoring a missing one.

Stubbed docker drives util.sh: the keep set is the sandbox/lab images the MCPs
resolve plus every image launch.sh builds, a missing image is rebuilt by its own
recipe, and DinD receives it with save | load. No live docker here.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_UTIL = _ROOT / "scripts" / "lib" / "util.sh"

_DOCKER_STUB = r"""#!/bin/bash
state="${PORTAL5_TEST_STATE:?}"
log="${state}/cmd.log"
case "$1" in
  inspect) cat "$state/dind_running"; exit 0 ;;
  image)
    case "$2" in
      inspect) grep -qx -- "$3" "$state/host_present" 2>/dev/null ;;
      *) exit 1 ;;
    esac ;;
  exec)
    if [ "$2" = "-i" ]; then
      cat >/dev/null
      echo "load:$(cat "$state/last_save")" >> "$log"
      exit 0
    fi
    case "$5" in
      inspect) grep -qx -- "$6" "$state/dind_present" 2>/dev/null ;;
      *) exit 1 ;;
    esac ;;
  build)
    ref=""; prev=""; has_file=0
    for arg in "$@"; do
      [ "$prev" = "-t" ] && ref="$arg"
      [ "$arg" = "-f" ] && has_file=1
      prev="$arg"
    done
    [ "$has_file" -eq 0 ] && cat >/dev/null
    if grep -qx -- "$ref" "$state/fail_build" 2>/dev/null; then
      echo "build failed: $ref" >&2
      exit 1
    fi
    echo "build:$ref" >> "$log"
    echo "$ref" >> "$state/host_present"
    exit 0 ;;
  save)
    echo "$2" > "$state/last_save"
    echo "save:$2" >> "$log"
    echo image-bytes
    exit 0 ;;
  *) exit 1 ;;
esac
"""


def _state(tmp_path: Path, *, host: list[str], dind: list[str], dind_running: bool = True) -> Path:
    state = tmp_path / "state"
    stubs = tmp_path / "stubs"
    state.mkdir()
    stubs.mkdir()
    (stubs / "docker").write_text(_DOCKER_STUB)
    (stubs / "docker").chmod(0o755)
    (state / "host_present").write_text("".join(f"{ref}\n" for ref in host))
    (state / "dind_present").write_text("".join(f"{ref}\n" for ref in dind))
    (state / "dind_running").write_text("true" if dind_running else "false")
    return state


def _run(tmp_path: Path, state: Path, body: str, env_extra: dict[str, str] | None = None):
    env = {
        "PATH": f"{tmp_path / 'stubs'}:{os.environ['PATH']}",
        "HOME": str(tmp_path / "home"),
        "PORTAL5_TEST_STATE": str(state),
        "PORTAL_ROOT": str(tmp_path),
        **(env_extra or {}),
    }
    return subprocess.run(
        ["bash", "-c", f"source {_UTIL}; {body}"],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )


def _cmd_log(state: Path) -> list[str]:
    log = state / "cmd.log"
    return log.read_text().splitlines() if log.exists() else []


def test_required_images_resolve_like_the_sandbox(tmp_path):
    state = _state(tmp_path, host=[], dind=[])
    env = {
        "SANDBOX_LAB_EXEC": "true",
        "SANDBOX_LAB_IMAGE": "portal5-attack:latest",
        "SANDBOX_PS_IMAGE": "mcr.microsoft.com/powershell:lts-alpine-3.17",
    }
    result = _run(tmp_path, state, "_sandbox_images required", env)
    refs = result.stdout.split()

    assert refs == [
        "portal5-sandbox-data:latest",
        "mcr.microsoft.com/powershell:lts-alpine-3.17",
        "portal5-binresearch:latest",
        "portal5-attack:latest",
    ]


def test_required_images_omit_the_lab_image_while_lab_exec_is_off(tmp_path):
    state = _state(tmp_path, host=[], dind=[])
    result = _run(
        tmp_path, state, "_sandbox_images required", {"SANDBOX_LAB_IMAGE": "portal5-attack:latest"}
    )

    assert result.stdout.split() == [
        "portal5-sandbox-data:latest",
        "portal5-pwsh:latest",
        "portal5-binresearch:latest",
    ]


def test_up_restores_local_executor_images_before_the_health_gate():
    launch = (_ROOT / "launch.sh").read_text(encoding="utf-8")
    up_body = launch.split("  up)", 1)[1].split("\n    ;;", 1)[0]

    assert up_body.index("_ensure_sandbox_images") < up_body.index("_wait_up_health")


def test_up_rebuilds_a_missing_sandbox_image_and_loads_it_into_dind(tmp_path):
    state = _state(tmp_path, host=["portal5-pwsh:latest"], dind=["portal5-pwsh:latest"])
    result = _run(tmp_path, state, "_ensure_sandbox_images")
    log = _cmd_log(state)

    assert result.returncode == 0, result.stderr
    assert "build:portal5-sandbox-data:latest" in log
    assert "save:portal5-sandbox-data:latest" in log
    assert "load:portal5-sandbox-data:latest" in log


def test_up_rebuilds_the_lab_image_only_when_lab_exec_names_it(tmp_path):
    state = _state(
        tmp_path,
        host=["portal5-pwsh:latest", "portal5-sandbox-data:latest", "portal5-binresearch:latest"],
        dind=["portal5-pwsh:latest", "portal5-sandbox-data:latest", "portal5-binresearch:latest"],
    )
    result = _run(
        tmp_path,
        state,
        "_ensure_sandbox_images",
        {"SANDBOX_LAB_EXEC": "true", "SANDBOX_LAB_IMAGE": "portal5-attack:latest"},
    )

    assert result.returncode == 0, result.stderr
    assert "build:portal5-attack:latest" in _cmd_log(state)


def test_up_does_not_build_the_lab_image_while_lab_exec_is_off(tmp_path):
    state = _state(
        tmp_path,
        host=["portal5-pwsh:latest", "portal5-sandbox-data:latest", "portal5-binresearch:latest"],
        dind=["portal5-pwsh:latest", "portal5-sandbox-data:latest", "portal5-binresearch:latest"],
    )
    result = _run(tmp_path, state, "_ensure_sandbox_images")

    assert result.returncode == 0, result.stderr
    assert "build:portal5-attack:latest" not in _cmd_log(state)


def test_up_only_loads_into_dind_when_the_image_is_absent_there(tmp_path):
    state = _state(
        tmp_path,
        host=["portal5-pwsh:latest", "portal5-sandbox-data:latest", "portal5-binresearch:latest"],
        dind=["portal5-pwsh:latest"],
    )
    result = _run(tmp_path, state, "_ensure_sandbox_images")
    log = _cmd_log(state)

    assert result.returncode == 0, result.stderr
    assert "save:portal5-pwsh:latest" not in log
    assert "save:portal5-sandbox-data:latest" in log
    assert "save:portal5-binresearch:latest" in log


def test_rebuild_always_rebuilds_pwsh_and_sandbox_data(tmp_path):
    state = _state(
        tmp_path,
        host=["portal5-pwsh:latest", "portal5-sandbox-data:latest", "portal5-binresearch:latest"],
        dind=["portal5-pwsh:latest", "portal5-sandbox-data:latest", "portal5-binresearch:latest"],
    )
    result = _run(tmp_path, state, "_ensure_sandbox_images --rebuild")
    log = _cmd_log(state)

    assert result.returncode == 0, result.stderr
    assert "build:portal5-pwsh:latest" in log
    assert "build:portal5-sandbox-data:latest" in log
    assert "build:portal5-binresearch:latest" not in log
    # A rebuilt image must reach DinD even when an older copy is already there.
    assert "load:portal5-pwsh:latest" in log
    assert "load:portal5-sandbox-data:latest" in log


def test_ensure_warns_and_fails_when_dind_is_not_running(tmp_path):
    state = _state(tmp_path, host=[], dind=[], dind_running=False)
    result = _run(tmp_path, state, "_ensure_sandbox_images")

    assert result.returncode != 0
    assert "portal5-dind is not running" in result.stdout + result.stderr
    assert _cmd_log(state) == []


def test_a_failed_opt_in_image_build_warns_but_does_not_stop_up(tmp_path):
    state = _state(tmp_path, host=["portal5-pwsh:latest"], dind=["portal5-pwsh:latest"])
    (state / "fail_build").write_text("portal5-binresearch:latest\n")
    result = _run(tmp_path, state, "_ensure_sandbox_images")

    assert result.returncode == 0
    assert "portal5-binresearch:latest is missing and could not be built" in result.stderr
    assert "load:portal5-sandbox-data:latest" in _cmd_log(state)


def test_a_failed_required_image_build_stops_up(tmp_path):
    state = _state(tmp_path, host=["portal5-pwsh:latest"], dind=["portal5-pwsh:latest"])
    (state / "fail_build").write_text("portal5-sandbox-data:latest\n")
    result = _run(tmp_path, state, "_ensure_sandbox_images")

    assert result.returncode != 0
    assert "portal5-sandbox-data:latest is missing and could not be built" in result.stderr
