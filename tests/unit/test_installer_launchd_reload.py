"""Installer launchd reloads wait out the bootout teardown before bootstrapping.

Live 2026-11-20 (main 96559014b): install-music/mflux/video-mlx each ended
"Bootstrap failed: 5: Input/output error … service is not loaded" — bootstrap
was issued inside the previous bootout's teardown window. All three now reload
through the shared _launchd_reload_job, driven here by a stubbed launchctl.
"""

import re
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_UTIL = _ROOT / "scripts/lib/util.sh"
_SERVICES = _ROOT / "scripts/lib/services.sh"

_LAUNCHCTL_STUB = """#!/bin/bash
state="${PORTAL5_TEST_STATE}"
case "$1" in
  print)
    if [ -f "$state/started" ]; then echo "state = running"; exit 0; fi
    ticks="$(cat "$state/teardown" 2>/dev/null || echo 0)"
    if [ "$ticks" -gt 0 ]; then echo $((ticks - 1)) > "$state/teardown"; exit 0; fi
    exit 1 ;;
  bootout)
    printf '%s' "$(cat "$state/teardown_ticks" 2>/dev/null || echo 2)" > "$state/teardown"
    exit 0 ;;
  bootstrap)
    n="$(cat "$state/bootstrap_calls" 2>/dev/null || echo 0)"
    echo $((n + 1)) > "$state/bootstrap_calls"
    if [ "$n" -lt "$(cat "$state/fail_until" 2>/dev/null || echo 0)" ]; then
      code="$(cat "$state/race_code" 2>/dev/null || echo 5)"
      case "$code" in
        37) msg="Bootstrap failed: 37: Operation already in progress" ;;
        *) msg="Bootstrap failed: 5: Input/output error" ;;
      esac
      echo "$msg" >&2
      echo "$msg" >> "$state/log"
      exit "$code"
    fi
    touch "$state/started"
    exit 0 ;;
esac
exit 1
"""

_CURL_STUB = """#!/bin/sh
[ -f "${PORTAL5_TEST_STATE}/health_down" ] && exit 7
exit 0
"""


def _reload(tmp_path: Path, budget: str = "60") -> subprocess.CompletedProcess:
    stubs = tmp_path / "stubs"
    state = tmp_path / "state"
    stubs.mkdir(exist_ok=True)
    state.mkdir(exist_ok=True)
    for name, body in (
        ("launchctl", _LAUNCHCTL_STUB),
        ("curl", _CURL_STUB),
        ("sleep", "#!/bin/sh\nexit 0\n"),
    ):
        stub = stubs / name
        stub.write_text(body)
        stub.chmod(0o755)
    script = (
        f'source "{_UTIL}"\n'
        f"_launchd_reload_job com.portal5.music '{tmp_path}/music.plist'"
        f' "gui/$(id -u)" "http://127.0.0.1:8912/health" "" "{budget}"\n'
        'echo "rc=$?"\n'
    )
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        timeout=120,
        env={
            "PATH": f"{stubs}:/usr/bin:/bin:/usr/sbin:/sbin",
            "PORTAL5_TEST_STATE": str(state),
        },
    )


def _state(tmp_path: Path) -> Path:
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    return state


def _bootstrap_calls(tmp_path: Path) -> int:
    counter = _state(tmp_path) / "bootstrap_calls"
    return int(counter.read_text()) if counter.exists() else 0


def test_bootstrap_retries_out_the_bootout_teardown_window(tmp_path):
    (tmp_path / "state").mkdir()
    (_state(tmp_path) / "teardown_ticks").write_text("2")
    (_state(tmp_path) / "fail_until").write_text("1")
    (_state(tmp_path) / "race_code").write_text("5")

    proc = _reload(tmp_path)

    assert "rc=0" in proc.stdout, proc.stderr
    assert _bootstrap_calls(tmp_path) == 2
    log = (_state(tmp_path) / "log").read_text()
    assert "Bootstrap failed: 5: Input/output error" in log


def test_bootstrap_retry_covers_error_37(tmp_path):
    (tmp_path / "state").mkdir()
    (_state(tmp_path) / "fail_until").write_text("1")
    (_state(tmp_path) / "race_code").write_text("37")

    proc = _reload(tmp_path)

    assert "rc=0" in proc.stdout, proc.stderr
    assert _bootstrap_calls(tmp_path) == 2
    log = (_state(tmp_path) / "log").read_text()
    assert "Bootstrap failed: 37: Operation already in progress" in log


def test_an_unracy_job_bootstraps_once(tmp_path):
    proc = _reload(tmp_path)

    assert "rc=0" in proc.stdout, proc.stderr
    assert _bootstrap_calls(tmp_path) == 1


def test_a_bootstrap_that_never_succeeds_fails_loudly_and_bounded(tmp_path):
    (tmp_path / "state").mkdir()
    (_state(tmp_path) / "fail_until").write_text("99")

    proc = _reload(tmp_path)

    assert "rc=1" in proc.stdout
    assert _bootstrap_calls(tmp_path) == 5
    # The shared helper reports on stdout; the launchctl error reaches stderr.
    assert "repair: launchctl bootstrap" in proc.stdout
    assert "Bootstrap failed: 5: Input/output error" in proc.stderr


def test_a_health_that_never_comes_up_fails_loudly(tmp_path):
    (tmp_path / "state").mkdir()
    (_state(tmp_path) / "health_down").write_text("")

    proc = _reload(tmp_path, budget="4")

    assert "rc=1" in proc.stdout
    assert "repair: launchctl bootstrap" in proc.stdout


def test_the_race_matcher_covers_both_teardown_errors_and_nothing_else():
    script = (
        f'source "{_UTIL}"\n'
        '_launchd_is_race 5 "Bootstrap failed: 5: Input/output error" && echo r5\n'
        '_launchd_is_race 37 "Bootstrap failed: 37: Operation already in progress" && echo r37\n'
        "_launchd_is_race 5 '' && echo c5\n"
        "_launchd_is_race 37 '' && echo c37\n"
        "_launchd_is_race 1 'Bootstrap failed: 1: Operation not permitted' || echo n1\n"
    )
    proc = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=60)
    assert proc.stdout.split() == ["r5", "r37", "c5", "c37", "n1"]


def _bash_function(source: str, name: str) -> str:
    start = source.index(f"{name}() {{")
    return source[start : source.index("\n}\n", start)]


def test_all_three_installers_reload_through_the_shared_helper_with_health():
    services = _SERVICES.read_text(encoding="utf-8")
    reloader = _bash_function(services, "_launchd_reload_or_fail")
    assert "_launchd_reload_job" in reloader
    # The teardown race is retried in exactly one place, the shared helper.
    assert "launchctl bootstrap" not in reloader
    found = dict(
        re.findall(
            r'_launchd_reload_or_fail (com\.portal5[\w.-]+) "\$PLIST"'
            r' "(http://127\.0\.0\.1:\$\{[A-Z_]+\}/health)"',
            services,
        )
    )
    assert found == {
        "com.portal5.music": "http://127.0.0.1:${MUSIC_PORT}/health",
        "com.portal5.mflux": "http://127.0.0.1:${MX_PORT}/health",
        "com.portal5.video-mlx": "http://127.0.0.1:${VX_PORT}/health",
    }
