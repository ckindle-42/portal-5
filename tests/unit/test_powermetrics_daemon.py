"""Sample splitting in scripts/portal5-powermetrics.py (buffer leak regression)."""

import importlib.util
import plistlib
import subprocess
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "portal5-powermetrics.py"
_ROOT = _PATH.parents[1]
_spec = importlib.util.spec_from_file_location("portal5_powermetrics", _PATH)
pm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pm)


def test_root_launchdaemons_do_not_execute_user_writable_paths():
    root_daemons = []
    for plist_path in (_ROOT / "deploy/launchd").glob("*.plist"):
        with plist_path.open("rb") as stream:
            plist = plistlib.load(stream)
        if plist.get("UserName") == "root":
            root_daemons.append(plist_path.name)
            serialized = repr(plist)
            assert not any(
                marker in serialized
                for marker in ("__PORTAL_ROOT__", "__HOME__", "/Users/", "/.venv/")
            )
    assert root_daemons == ["com.portal5.powermetrics.plist"]


def test_powermetrics_launchdaemon_uses_root_owned_install_targets():
    plist_path = _ROOT / "deploy/launchd/com.portal5.powermetrics.plist"
    with plist_path.open("rb") as stream:
        args = plistlib.load(stream)["ProgramArguments"]
    assert args == ["/usr/bin/python3", "/usr/local/libexec/portal5-powermetrics"]

    services = (_ROOT / "scripts/lib/services.sh").read_text(encoding="utf-8")
    assert 'SCRIPT_DST="/usr/local/libexec/portal5-powermetrics"' in services
    assert 'sudo install -o root -g wheel -m 0755 "$SCRIPT_SRC" "$SCRIPT_DST"' in services
    # The plist is rendered, installed, and proven byte-identical to that render:
    # the live copy had drifted to the pre-a55e73caf /usr/local/bin layout.
    assert '_render_launchd_plist "$PLIST_SRC" "$PLIST_RENDERED"' in services
    assert 'sudo install -o root -g wheel -m 0644 "$PLIST_RENDERED" "$PLIST_DST"' in services
    assert 'cmp -s "$PLIST_RENDERED" "$PLIST_DST"' in services
    # The install check is readiness, not a ps pattern: launchd starts the job a
    # few seconds after bootstrap, and /usr/bin/python3 re-execs into the Xcode
    # interpreter before the script path appears in the command line.
    assert 'grep -q "[/]usr/local/libexec/portal5-powermetrics"' not in services
    assert '_launchd_reload_job "$PM_LABEL" "$PLIST_DST" system' in services
    assert '_unix_socket_answering "/tmp/portal5-powermetrics.sock"' in services


def _sample(cpu_mw: float) -> list[bytes]:
    # Shape of real `powermetrics -f plist` output: milliwatts as <real>,
    # combined_power = cpu + gpu + ane (must not be counted again).
    return [
        b'<?xml version="1.0" encoding="UTF-8"?>\n',
        b"<plist><dict><key>processor</key><dict>\n",
        f"<key>cpu_power</key><real>{cpu_mw}</real>\n".encode(),
        b"<key>gpu_power</key><real>26881.1</real>\n",
        b"<key>ane_power</key><real>0</real>\n",
        f"<key>combined_power</key><real>{cpu_mw + 26881.1}</real>\n".encode(),
        b"</dict></dict>\n",
        b"</plist>\n",
    ]


def test_nul_separated_samples_are_each_yielded():
    first = _sample(6553.71)
    second = _sample(2000.0)
    second[0] = b"\x00" + second[0]  # powermetrics puts a NUL between samples
    docs = list(pm.iter_plist_documents(first + second))
    assert len(docs) == 2
    assert pm.parse_plist_buffer(docs[1]) == {"cpu_w": 2.0, "gpu_w": 26.8811, "ane_w": 0.0}


def test_buffer_is_bounded_without_boundary(monkeypatch):
    monkeypatch.setattr(pm, "MAX_BUFFER_LINES", 10)
    lines = [b"<key>x</key>\n"] * 100 + _sample(500.0)
    docs = list(pm.iter_plist_documents(lines))
    assert len(docs) == 1
    assert len(docs[0].splitlines()) <= 10 + len(_sample(500.0))


def _stub(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _env(tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    return {
        "PATH": f"{bin_dir}:/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(tmp_path / "home"),
        "PORTAL_ROOT": str(_ROOT),
        "TMPDIR": str(tmp_path),
        "NC_COUNT": str(tmp_path / "nc-calls"),
        "SLEEP_LOG": str(tmp_path / "sleeps"),
    }


def _bash(script: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["/bin/bash", "-uc", script], capture_output=True, text=True, env=env)


def test_socket_probe_reports_ready_only_when_the_daemon_answers(tmp_path: Path) -> None:
    env = _env(tmp_path)
    _stub(
        tmp_path / "bin" / "nc",
        '#!/bin/bash\nn=$(cat "$NC_COUNT" 2>/dev/null || echo 0)\n'
        'echo $((n + 1)) > "$NC_COUNT"\n'
        '[ "$n" -ge 2 ] && { echo \'{"current_w": 1.0}\'; exit 0; }\nexit 1\n',
    )
    _stub(tmp_path / "bin" / "sleep", "#!/bin/bash\nexit 0\n")

    result = _bash(
        f'source "{_ROOT}/scripts/lib/util.sh"\n'
        "_unix_socket_answering /tmp/portal5-powermetrics.sock 10",
        env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert int((tmp_path / "nc-calls").read_text()) == 3


def test_socket_probe_gives_up_after_the_budget(tmp_path: Path) -> None:
    env = _env(tmp_path)
    _stub(tmp_path / "bin" / "nc", "#!/bin/bash\nexit 1\n")
    _stub(tmp_path / "bin" / "sleep", '#!/bin/bash\nprintf "%s\\n" "$*" >> "$SLEEP_LOG"\nexit 0\n')

    result = _bash(
        f'source "{_ROOT}/scripts/lib/util.sh"\n'
        "_unix_socket_answering /tmp/portal5-powermetrics.sock 4",
        env,
    )

    assert result.returncode != 0
    assert "waiting for /tmp/portal5-powermetrics.sock" in result.stdout
    assert (tmp_path / "sleeps").read_text().split() == ["2", "2"]


def test_root_hint_prefers_the_passwordless_dispatcher(tmp_path: Path) -> None:
    env = _env(tmp_path)
    dispatcher = tmp_path / "portal5-root"
    _stub(dispatcher, "#!/bin/bash\nexit 0\n")
    env["PORTAL5_ROOT_DISPATCHER"] = str(dispatcher)

    result = _bash(
        f'source "{_ROOT}/scripts/lib/util.sh"\n'
        '_portal5_root install-powermetrics "sudo ./launch.sh install-powermetrics"',
        env,
    )

    assert result.stdout == f"sudo -n {dispatcher} install-powermetrics"


def test_root_hint_falls_back_without_the_dispatcher(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env["PORTAL5_ROOT_DISPATCHER"] = str(tmp_path / "absent")

    result = _bash(
        f'source "{_ROOT}/scripts/lib/util.sh"\n'
        '_portal5_root install-powermetrics "sudo ./launch.sh install-powermetrics"',
        env,
    )

    assert result.stdout == "sudo ./launch.sh install-powermetrics"


def test_up_and_status_hints_use_the_root_dispatcher() -> None:
    util = (_ROOT / "scripts" / "lib" / "util.sh").read_text(encoding="utf-8")
    assert util.count("_portal5_root install-powermetrics") == 2
    assert "_portal5_root launchctl-system com.portal5.ollama" in util
