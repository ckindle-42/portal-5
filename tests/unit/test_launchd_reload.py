"""launchd reload: bootout → wait until gone → bootstrap (retry) → verify.

2026-11-16 live: `./launch.sh install-omlx` bootstrapped before launchd had
finished tearing the booted-out job down, printed
`Bootstrap failed: 5: Input/output error`, and oMLX stayed down (:8085 refused)
until the orchestrator bootstrapped by hand ~30 s later. The rendered plist was
valid; only the ordering was wrong. An install must also never leave the job
down: the previous plist is the fallback.
"""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LABEL = "com.portal5.omlx"
TEMPLATE = ROOT / "deploy" / "launchd" / f"{LABEL}.plist"
_DARWIN = pytest.mark.skipif(sys.platform != "darwin", reason="launchd plists are macOS-only")

# A launchctl with real state: `bootout` can leave the job loaded for N further
# `print`s (the live race), `bootstrap` refuses while it is still loaded, and a
# `fails` counter injects "error 5" attempts.
_FAKE_LAUNCHCTL = """#!/bin/bash
printf '%s\\n' "$*" >> "$CALL_LOG"
cmd="${1:-}"
case "$cmd" in
  print)
    label="${2##*/}"
    if [ -f "$STATE/$label.drain" ]; then
      n=$(cat "$STATE/$label.drain")
      if [ "$n" -gt 0 ]; then echo $((n - 1)) > "$STATE/$label.drain"
      else rm -f "$STATE/$label.drain" "$STATE/$label.loaded"; fi
    fi
    [ -f "$STATE/$label.loaded" ] || exit 1
    printf '\\tstate = running\\n'
    ;;
  bootout)
    label="${2##*/}"
    [ "${TEARDOWN_STUCK:-0}" = "1" ] && exit 0
    if [ "${TEARDOWN_PRINTS:-0}" -gt 0 ]; then
      echo "$TEARDOWN_PRINTS" > "$STATE/$label.drain"
    else
      rm -f "$STATE/$label.loaded"
    fi
    ;;
  bootstrap)
    label="$(/usr/bin/plutil -extract Label raw -o - "$3" 2>/dev/null)"
    if [ -f "$STATE/$label.loaded" ]; then
      echo "Bootstrap failed: 5: Input/output error" >&2
      exit 5
    fi
    fails=$(cat "$STATE/fails" 2>/dev/null || echo 0)
    if [ "$fails" -gt 0 ]; then
      echo $((fails - 1)) > "$STATE/fails"
      echo "${BOOTSTRAP_ERROR:-Bootstrap failed: 5: Input/output error}" >&2
      exit "${BOOTSTRAP_STATUS:-5}"
    fi
    touch "$STATE/$label.loaded"
    ;;
esac
exit 0
"""


def _stub(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _plist_text(program: str) -> str:
    cfg = {"Label": LABEL, "ProgramArguments": [program], "RunAtLoad": True}
    return plistlib.dumps(cfg, fmt=plistlib.FMT_XML).decode()


def _env(
    tmp_path: Path, *, venv: bool = True, loaded: bool = False, **extra: str
) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    if venv:
        (home / "omlx-live" / "venv" / "bin").mkdir(parents=True, exist_ok=True)
        _stub(home / "omlx-live" / "venv" / "bin" / "python", "#!/bin/bash\nexit 0\n")
    if loaded:
        (state / f"{LABEL}.loaded").write_text("", encoding="utf-8")
    _stub(bin_dir / "launchctl", _FAKE_LAUNCHCTL)
    _stub(
        bin_dir / "curl",
        '#!/bin/bash\n[ "${HEALTH_OK:-1}" = "1" ] && exit 0\nexit 7\n',
    )
    _stub(bin_dir / "sleep", '#!/bin/bash\nprintf "%s\\n" "$*" >> "$SLEEP_LOG"\nexit 0\n')
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(home),
        "PORTAL_ROOT": str(ROOT),
        "OMLX_VENV_PATH": str(home / "omlx-live" / "venv"),
        "TMPDIR": str(tmp_path),
        "STATE": str(state),
        "CALL_LOG": str(tmp_path / "calls"),
        "SLEEP_LOG": str(tmp_path / "sleeps"),
    }
    env.update(extra)
    return env


def _bash(script: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["/bin/bash", "-uc", script], capture_output=True, text=True, env=env)


def _calls(tmp_path: Path) -> list[str]:
    log = tmp_path / "calls"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _bootstraps(tmp_path: Path) -> list[str]:
    return [call for call in _calls(tmp_path) if call.startswith("bootstrap")]


def _sleeps(tmp_path: Path) -> list[str]:
    log = tmp_path / "sleeps"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def test_race_predicate_accepts_a_bare_exit_5(tmp_path: Path) -> None:
    env = _env(tmp_path)
    script = f"""
source "{ROOT}/scripts/lib/util.sh"
_launchd_is_race 5 "" && echo "race"
_launchd_is_race 37 "" || echo "not-race"
"""

    result = _bash(script, env)

    assert result.returncode == 0, result.stderr
    assert "race" in result.stdout and "not-race" in result.stdout


@_DARWIN
def test_waits_for_the_bootout_to_finish_before_bootstrapping(tmp_path: Path) -> None:
    env = _env(tmp_path, loaded=True, TEARDOWN_PRINTS="3")
    plist = tmp_path / "new.plist"
    plist.write_text(_plist_text("/usr/bin/true"), encoding="utf-8")

    result = _bash(
        f"""
source "{ROOT}/scripts/lib/util.sh"
_launchd_reload_job {LABEL} "{plist}" "gui/$(id -u)"
""",
        env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    calls = _calls(tmp_path)
    assert len(_bootstraps(tmp_path)) == 1, calls
    assert calls.index(_bootstraps(tmp_path)[0]) > calls.index(f"bootout gui/{os.getuid()}/{LABEL}")
    assert sum(1 for call in calls if call.startswith("print")) >= 4


@_DARWIN
def test_retries_bootstrap_error_5_with_backoff(tmp_path: Path) -> None:
    env = _env(tmp_path)
    (tmp_path / "state" / "fails").write_text("2", encoding="utf-8")
    plist = tmp_path / "new.plist"
    plist.write_text(_plist_text("/usr/bin/true"), encoding="utf-8")

    result = _bash(
        f"""
source "{ROOT}/scripts/lib/util.sh"
_launchd_reload_job {LABEL} "{plist}" "gui/$(id -u)"
""",
        env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert len(_bootstraps(tmp_path)) == 3
    assert _sleeps(tmp_path) == ["1", "2"]


def test_refuses_to_bootstrap_over_a_job_that_will_not_unload(tmp_path: Path) -> None:
    env = _env(tmp_path, loaded=True, TEARDOWN_STUCK="1")
    plist = tmp_path / "new.plist"
    plist.write_text(_plist_text("/usr/bin/true"), encoding="utf-8")

    result = _bash(
        f"""
source "{ROOT}/scripts/lib/util.sh"
_launchd_reload_job {LABEL} "{plist}" "gui/$(id -u)"
""",
        env,
    )

    assert result.returncode != 0
    assert _bootstraps(tmp_path) == []
    assert "still loaded 30s after bootout" in result.stdout


def test_does_not_retry_a_bootstrap_error_that_is_not_the_race(tmp_path: Path) -> None:
    env = _env(tmp_path)
    (tmp_path / "state" / "fails").write_text("1", encoding="utf-8")
    plist = tmp_path / "new.plist"
    plist.write_text(_plist_text("/usr/bin/true"), encoding="utf-8")

    result = _bash(
        f"""
source "{ROOT}/scripts/lib/util.sh"
_launchd_reload_job {LABEL} "{plist}" "gui/$(id -u)" "" "" 10
""",
        env
        | {
            "BOOTSTRAP_ERROR": "Bootstrap failed: 37: Operation already in progress",
            "BOOTSTRAP_STATUS": "37",
        },
    )

    assert result.returncode != 0
    assert len(_bootstraps(tmp_path)) == 1
    assert "Operation already in progress" in result.stderr


@_DARWIN
def test_health_failure_restores_the_previous_plist(tmp_path: Path) -> None:
    env = _env(tmp_path, loaded=True, HEALTH_OK="0")
    installed = tmp_path / "installed.plist"
    installed.write_text(_plist_text("/usr/bin/true"), encoding="utf-8")
    previous = tmp_path / "previous.plist"
    previous.write_text(_plist_text("/usr/bin/false"), encoding="utf-8")

    result = _bash(
        f"""
source "{ROOT}/scripts/lib/util.sh"
_launchd_reload_job {LABEL} "{installed}" "gui/$(id -u)" \
    "http://127.0.0.1:8085/health" "{previous}" 4
""",
        env,
    )

    assert result.returncode != 0
    assert installed.read_bytes() == previous.read_bytes()
    assert "restored the previous plist" in result.stdout
    assert len(_bootstraps(tmp_path)) == 2


@_DARWIN
def test_failed_install_puts_the_previous_plist_back_on_disk(tmp_path: Path) -> None:
    env = _env(tmp_path)
    (tmp_path / "state" / "fails").write_text("99", encoding="utf-8")
    installed = tmp_path / "installed.plist"
    installed.write_text(_plist_text("/usr/bin/true"), encoding="utf-8")
    previous = tmp_path / "previous.plist"
    previous.write_text(_plist_text("/usr/bin/false"), encoding="utf-8")

    result = _bash(
        f"""
source "{ROOT}/scripts/lib/util.sh"
_launchd_reload_job {LABEL} "{installed}" "gui/$(id -u)" "" "{previous}" 4
""",
        env,
    )

    assert result.returncode != 0
    assert installed.read_bytes() == previous.read_bytes()
    assert "did not load either" in result.stdout


@_DARWIN
def test_install_omlx_survives_the_live_bootout_race(tmp_path: Path) -> None:
    env = _env(tmp_path, loaded=True, TEARDOWN_PRINTS="2")
    (tmp_path / "state" / "fails").write_text("1", encoding="utf-8")
    agent = Path(env["HOME"]) / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    agent.parent.mkdir(parents=True)
    agent.write_text(_plist_text("/usr/bin/true"), encoding="utf-8")

    result = _bash(
        f"""
source "{ROOT}/scripts/lib/util.sh"
source "{ROOT}/scripts/lib/services.sh"
_launch_install_omlx
""",
        env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "✅" in result.stdout and "❌" not in result.stdout
    cfg = plistlib.loads(agent.read_bytes())
    assert cfg["ProgramArguments"][0] == f"{env['OMLX_VENV_PATH']}/bin/python"
    assert len(_bootstraps(tmp_path)) == 2
