"""Offline checks for the pipeline tool-carry flip.

curl, docker and git are shims. PORTAL_HEALTH_URL points at a closed port so a
script that ignores the shim fails fast and does not call the live pipeline.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "pipeline_tool_carry.sh"

FAKE_CURL = """\
#!/usr/bin/env bash
nfile="${TOOL_CARRY_CURL_COUNT:?}"
n=0
[ -f "$nfile" ] && n=$(cat "$nfile")
n=$((n + 1))
printf '%s' "$n" >"$nfile"
if [ "${TOOL_CARRY_FAIL_BEFORE:-0}" = 1 ]; then
    exit 22
fi
sha="${TOOL_CARRY_SHA:-abc1234}"
if [ "$n" -gt 1 ] && [ -n "${TOOL_CARRY_SHA_AFTER:-}" ]; then
    sha="$TOOL_CARRY_SHA_AFTER"
fi
if [ "$n" -gt 1 ] && [ "${TOOL_CARRY_FAIL_AFTER:-0}" = 1 ]; then
    exit 22
fi
printf '{"status":"ok","build_sha":"%s"}\\n' "$sha"
"""

FAKE_DOCKER = """\
#!/usr/bin/env bash
log="${TOOL_CARRY_LOG:?}"
state="${TOOL_CARRY_STATE:?}"
{
    printf 'PWD=%s\\n' "$PWD"
    printf 'ARGV=%s\\n' "$*"
    printf 'CARRY=%s\\n' "${PORTAL_TOOL_RESULT_CARRY:-}"
    printf 'PIPELINE_API_KEY=%s\\n' "${PIPELINE_API_KEY:-}"
    printf -- '---\\n'
} >>"$log"

case "$1" in
inspect)
    if [ "${TOOL_CARRY_INSPECT_RC:-0}" != 0 ]; then
        exit "$TOOL_CARRY_INSPECT_RC"
    fi
    if [ -n "${TOOL_CARRY_INSPECT_AFTER:-}" ] && [ -f "${state}.recreated" ]; then
        cat "$TOOL_CARRY_INSPECT_AFTER"
    else
        cat "${TOOL_CARRY_INSPECT:?}"
    fi
    ;;
exec)
    if [ -n "${TOOL_CARRY_PRINTENV+x}" ]; then
        printf '%s\\n' "$TOOL_CARRY_PRINTENV"
    elif [ -f "${state}.carry" ]; then
        cat "${state}.carry"
    fi
    exit "${TOOL_CARRY_EXEC_RC:-0}"
    ;;
compose)
    printf '%s\\n' "${PORTAL_TOOL_RESULT_CARRY:-}" >"${state}.carry"
    : >"${state}.recreated"
    exit "${TOOL_CARRY_COMPOSE_RC:-0}"
    ;;
*)
    echo "unexpected docker args: $*" >&2
    exit 99
    ;;
esac
"""

FAKE_GIT = """\
#!/usr/bin/env bash
printf '%s\\n' "${TOOL_CARRY_MAIN:?}/.git"
"""


def _container_env(*, carry: str = "false", omlx: str = "omlx-key") -> str:
    return json.dumps(
        [
            "PIPELINE_API_KEY=secret",
            f"OMLX_API_KEY={omlx}",
            f"PORTAL_TOOL_RESULT_CARRY={carry}",
            "PATH=/usr/local/bin:/usr/bin",
        ]
    )


def _layout(tmp_path: Path, env_text: str = "PIPELINE_API_KEY=secret\n") -> dict[str, Path]:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    curl = bindir / "curl"
    curl.write_text(FAKE_CURL)
    curl.chmod(0o755)
    docker = bindir / "docker"
    docker.write_text(FAKE_DOCKER)
    docker.chmod(0o755)
    git = bindir / "git"
    git.write_text(FAKE_GIT)
    git.chmod(0o755)
    env_file = tmp_path / "repo.env"
    env_file.write_text(env_text)
    compose = tmp_path / "compose"
    compose.mkdir()
    inspect = tmp_path / "container.json"
    inspect.write_text(_container_env())
    return {
        "curl": curl,
        "docker": docker,
        "git": git,
        "env": env_file,
        "compose": compose,
        "inspect": inspect,
        "log": tmp_path / "docker.log",
        "count": tmp_path / "curl.count",
        "state": tmp_path / "carry.state",
    }


def _run(
    tmp_path: Path,
    *args: str,
    extra: dict[str, str] | None = None,
    env_text: str = "PIPELINE_API_KEY=secret\n",
    wired: bool = True,
) -> subprocess.CompletedProcess[str]:
    paths = _layout(tmp_path, env_text)
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("PORTAL_", "TOOL_CARRY_"))
    }
    env.update(
        {
            "PORTAL_DOCKER": str(paths["docker"]),
            "PORTAL_CURL": str(paths["curl"]),
            "PORTAL_GIT": str(paths["git"]),
            "PORTAL_HEALTH_URL": "http://127.0.0.1:9/health",
            "PORTAL_HEALTH_WAIT_S": "0",
            "PORTAL_HEALTH_INTERVAL_S": "0",
            "TOOL_CARRY_LOG": str(paths["log"]),
            "TOOL_CARRY_CURL_COUNT": str(paths["count"]),
            "TOOL_CARRY_STATE": str(paths["state"]),
            "TOOL_CARRY_INSPECT": str(paths["inspect"]),
            "TOOL_CARRY_SHA": "abc1234",
        }
    )
    if wired:
        env["PORTAL_ENV_FILE"] = str(paths["env"])
        env["PORTAL_COMPOSE_DIR"] = str(paths["compose"])
    if extra:
        env.update(extra)
    result = subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    result.paths = paths  # type: ignore[attr-defined]
    return result


def test_pipeline_tool_carry_has_valid_shell_syntax() -> None:
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_pipeline_tool_carry_sources_the_env_file_before_compose(tmp_path: Path) -> None:
    result = _run(tmp_path, "on", env_text="PIPELINE_API_KEY=from-file\n")
    assert result.returncode == 0, result.stdout + result.stderr
    log = result.paths["log"].read_text(encoding="utf-8")  # type: ignore[attr-defined]
    assert "PIPELINE_API_KEY=from-file" in log
    assert "PIPELINE_API_KEY=secret" not in log


def test_on_rewrites_only_the_flag_and_recreates_the_pipeline(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "on",
        env_text="# keep\nPIPELINE_API_KEY=secret\nPORTAL_TOOL_RESULT_CARRY=false\nOTHER=1\n",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    env_file = result.paths["env"]  # type: ignore[attr-defined]
    assert env_file.read_text(encoding="utf-8") == (
        "# keep\nPIPELINE_API_KEY=secret\nOTHER=1\nPORTAL_TOOL_RESULT_CARRY=true\n"
    )
    log = result.paths["log"].read_text(encoding="utf-8")  # type: ignore[attr-defined]
    assert f"PWD={result.paths['compose']}" in log  # type: ignore[attr-defined]
    assert "ARGV=compose up -d --no-deps --force-recreate portal-pipeline" in log
    assert "ARGV=exec portal5-pipeline printenv PORTAL_TOOL_RESULT_CARRY" in log
    assert "CARRY=true" in log
    assert "--build" not in log
    assert "build_sha=abc1234" in result.stdout
    assert not (result.paths["compose"] / ".env").exists()  # type: ignore[attr-defined]


def test_the_container_env_is_fingerprinted_before_and_after(tmp_path: Path) -> None:
    result = _run(tmp_path, "on")
    assert result.returncode == 0, result.stdout + result.stderr
    log = result.paths["log"].read_text(encoding="utf-8")  # type: ignore[attr-defined]
    assert log.count("ARGV=inspect --format {{json .Config.Env}} portal5-pipeline") == 2


def test_off_sets_false(tmp_path: Path) -> None:
    result = _run(tmp_path, "off", env_text="PORTAL_TOOL_RESULT_CARRY=true\n")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.paths["env"].read_text(encoding="utf-8") == "PORTAL_TOOL_RESULT_CARRY=false\n"  # type: ignore[attr-defined]


def test_both_env_files_keep_their_other_keys(tmp_path: Path) -> None:
    paths = _layout(tmp_path, "PIPELINE_API_KEY=secret\n")
    compose_env = paths["compose"] / ".env"
    compose_env.write_text("COMPOSE_KEY=kept\n", encoding="utf-8")
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("PORTAL_", "TOOL_CARRY_"))
    }
    env.update(
        {
            "PORTAL_ENV_FILE": str(paths["env"]),
            "PORTAL_COMPOSE_DIR": str(paths["compose"]),
            "PORTAL_DOCKER": str(paths["docker"]),
            "PORTAL_CURL": str(paths["curl"]),
            "PORTAL_GIT": str(paths["git"]),
            "PORTAL_HEALTH_URL": "http://127.0.0.1:9/health",
            "PORTAL_HEALTH_WAIT_S": "0",
            "PORTAL_HEALTH_INTERVAL_S": "0",
            "TOOL_CARRY_LOG": str(paths["log"]),
            "TOOL_CARRY_CURL_COUNT": str(paths["count"]),
            "TOOL_CARRY_STATE": str(paths["state"]),
            "TOOL_CARRY_INSPECT": str(paths["inspect"]),
            "TOOL_CARRY_SHA": "abc1234",
        }
    )
    result = subprocess.run(
        ["bash", str(SCRIPT), "on"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert paths["env"].read_text(encoding="utf-8") == (
        "PIPELINE_API_KEY=secret\nPORTAL_TOOL_RESULT_CARRY=true\n"
    )
    assert compose_env.read_text(encoding="utf-8") == (
        "COMPOSE_KEY=kept\nPORTAL_TOOL_RESULT_CARRY=true\n"
    )


def test_the_same_env_file_is_written_once(tmp_path: Path) -> None:
    paths = _layout(tmp_path, "PIPELINE_API_KEY=secret\nPORTAL_TOOL_RESULT_CARRY=false\n")
    compose_env = paths["compose"] / ".env"
    compose_env.symlink_to(paths["env"])
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("PORTAL_", "TOOL_CARRY_"))
    }
    env.update(
        {
            "PORTAL_ENV_FILE": str(paths["env"]),
            "PORTAL_COMPOSE_DIR": str(paths["compose"]),
            "PORTAL_DOCKER": str(paths["docker"]),
            "PORTAL_CURL": str(paths["curl"]),
            "PORTAL_GIT": str(paths["git"]),
            "PORTAL_HEALTH_URL": "http://127.0.0.1:9/health",
            "PORTAL_HEALTH_WAIT_S": "0",
            "PORTAL_HEALTH_INTERVAL_S": "0",
            "TOOL_CARRY_LOG": str(paths["log"]),
            "TOOL_CARRY_CURL_COUNT": str(paths["count"]),
            "TOOL_CARRY_STATE": str(paths["state"]),
            "TOOL_CARRY_INSPECT": str(paths["inspect"]),
        }
    )
    result = subprocess.run(
        ["bash", str(SCRIPT), "off"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    text = paths["env"].read_text(encoding="utf-8")
    assert text.count("PORTAL_TOOL_RESULT_CARRY=") == 1
    assert text.endswith("PORTAL_TOOL_RESULT_CARRY=false\n")


def test_a_missing_env_file_is_not_created(tmp_path: Path) -> None:
    paths = _layout(tmp_path)
    missing = tmp_path / "no-such.env"
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("PORTAL_", "TOOL_CARRY_"))
    }
    env.update(
        {
            "PORTAL_ENV_FILE": str(missing),
            "PORTAL_COMPOSE_DIR": str(paths["compose"]),
            "PORTAL_DOCKER": str(paths["docker"]),
            "PORTAL_CURL": str(paths["curl"]),
            "PORTAL_GIT": str(paths["git"]),
            "PORTAL_HEALTH_URL": "http://127.0.0.1:9/health",
            "TOOL_CARRY_LOG": str(paths["log"]),
            "TOOL_CARRY_CURL_COUNT": str(paths["count"]),
            "TOOL_CARRY_STATE": str(paths["state"]),
            "TOOL_CARRY_INSPECT": str(paths["inspect"]),
        }
    )
    result = subprocess.run(
        ["bash", str(SCRIPT), "on"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 2
    assert "env file missing" in result.stderr
    assert not missing.exists()
    assert not paths["log"].exists()


def test_the_main_checkout_supplies_the_env_file_and_compose_dir(tmp_path: Path) -> None:
    main = tmp_path / "main"
    (main / "deploy" / "portal-5").mkdir(parents=True)
    (main / ".git").mkdir()
    (main / ".env").write_text("PIPELINE_API_KEY=main-secret\n", encoding="utf-8")
    result = _run(
        tmp_path,
        "on",
        env_text="PIPELINE_API_KEY=worktree-secret\n",
        extra={"TOOL_CARRY_MAIN": str(main)},
        wired=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (main / ".env").read_text(encoding="utf-8") == (
        "PIPELINE_API_KEY=main-secret\nPORTAL_TOOL_RESULT_CARRY=true\n"
    )
    assert result.paths["env"].read_text(encoding="utf-8") == "PIPELINE_API_KEY=worktree-secret\n"  # type: ignore[attr-defined]
    log = result.paths["log"].read_text(encoding="utf-8")  # type: ignore[attr-defined]
    assert f"PWD={main / 'deploy' / 'portal-5'}" in log
    assert "PIPELINE_API_KEY=main-secret" in log


def test_health_down_refuses_before_any_write(tmp_path: Path) -> None:
    before = "PIPELINE_API_KEY=secret\n"
    result = _run(tmp_path, "on", env_text=before, extra={"TOOL_CARRY_FAIL_BEFORE": "1"})
    assert result.returncode == 1
    assert "health unreachable" in result.stderr
    assert result.paths["env"].read_text(encoding="utf-8") == before  # type: ignore[attr-defined]
    assert not result.paths["log"].exists()  # type: ignore[attr-defined]


def test_an_unreadable_container_env_refuses_before_any_write(tmp_path: Path) -> None:
    before = "PIPELINE_API_KEY=secret\n"
    result = _run(tmp_path, "on", env_text=before, extra={"TOOL_CARRY_INSPECT_RC": "1"})
    assert result.returncode == 1
    assert "cannot read the running pipeline container env" in result.stderr
    assert result.paths["env"].read_text(encoding="utf-8") == before  # type: ignore[attr-defined]
    log = result.paths["log"].read_text(encoding="utf-8")  # type: ignore[attr-defined]
    assert "ARGV=compose" not in log


def test_a_changed_build_sha_fails_and_restores_the_flag(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "on",
        env_text="PIPELINE_API_KEY=secret\nPORTAL_TOOL_RESULT_CARRY=false\n",
        extra={"TOOL_CARRY_SHA_AFTER": "bbbb222"},
    )
    assert result.returncode == 1
    assert "build_sha changed (abc1234 -> bbbb222)" in result.stderr
    assert "restored PORTAL_TOOL_RESULT_CARRY=false" in result.stderr
    assert result.paths["env"].read_text(encoding="utf-8") == (  # type: ignore[attr-defined]
        "PIPELINE_API_KEY=secret\nPORTAL_TOOL_RESULT_CARRY=false\n"
    )


def test_a_printenv_mismatch_fails_and_restores_the_flag(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "on",
        env_text="PIPELINE_API_KEY=secret\nPORTAL_TOOL_RESULT_CARRY=false\n",
        extra={"TOOL_CARRY_PRINTENV": "false"},
    )
    assert result.returncode == 1
    assert "want true" in result.stderr
    assert result.paths["env"].read_text(encoding="utf-8") == (  # type: ignore[attr-defined]
        "PIPELINE_API_KEY=secret\nPORTAL_TOOL_RESULT_CARRY=false\n"
    )


def test_a_flag_absent_before_is_dropped_again_on_failure(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "on",
        env_text="PIPELINE_API_KEY=secret\n",
        extra={"TOOL_CARRY_PRINTENV": "false"},
    )
    assert result.returncode == 1
    assert result.paths["env"].read_text(encoding="utf-8") == "PIPELINE_API_KEY=secret\n"  # type: ignore[attr-defined]


def test_a_container_env_change_recreates_again_with_the_old_flag(tmp_path: Path) -> None:
    after = tmp_path / "after.json"
    after.write_text(_container_env(omlx=""), encoding="utf-8")
    result = _run(
        tmp_path,
        "on",
        env_text="PIPELINE_API_KEY=secret\nPORTAL_TOOL_RESULT_CARRY=false\n",
        extra={"TOOL_CARRY_INSPECT_AFTER": str(after)},
    )
    assert result.returncode == 1
    assert "changed across the recreate" in result.stderr
    assert "OMLX_API_KEY" in result.stderr
    log = result.paths["log"].read_text(encoding="utf-8")  # type: ignore[attr-defined]
    blocks = [block for block in log.split("---\n") if block.strip()]
    compose_blocks = [block for block in blocks if "ARGV=compose up" in block]
    assert ["CARRY=true" in block for block in compose_blocks] == [True, False]
    assert result.paths["env"].read_text(encoding="utf-8") == (  # type: ignore[attr-defined]
        "PIPELINE_API_KEY=secret\nPORTAL_TOOL_RESULT_CARRY=false\n"
    )


def test_a_bad_argument_is_usage(tmp_path: Path) -> None:
    result = _run(tmp_path, "maybe")
    assert result.returncode == 2
    assert "usage:" in result.stderr
    assert result.paths["env"].read_text(encoding="utf-8") == "PIPELINE_API_KEY=secret\n"  # type: ignore[attr-defined]
