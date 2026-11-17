"""launchd installs render the repo template, and `up` sees a stale install.

Live trace on main c3b8a78d4 (2026-11-16): the installed com.portal5.omlx
LaunchAgent was a verbatim copy of deploy/launchd/com.portal5.omlx.plist —
__OMLX_VENV__ and __HOME__ intact — while launchd still ran the previously
rendered program, so nothing failed until the next login. The root powermetrics
daemon's plist predated the /usr/local/libexec layout for the same reason: no
installer path re-rendered it.
"""

from __future__ import annotations

import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "deploy" / "launchd" / "com.portal5.omlx.plist"
_DARWIN = pytest.mark.skipif(sys.platform != "darwin", reason="launchd plists are macOS-only")


def _stub(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _env(tmp_path: Path, *, venv: bool = True, **extra: str) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    if venv:
        (home / "omlx-live" / "venv" / "bin").mkdir(parents=True, exist_ok=True)
        _stub(home / "omlx-live" / "venv" / "bin" / "python", "#!/bin/bash\nexit 0\n")
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(home),
        "PORTAL_ROOT": str(ROOT),
        "OMLX_VENV_PATH": str(home / "omlx-live" / "venv"),
        "TMPDIR": str(tmp_path),
        "CALL_LOG": str(tmp_path / "calls"),
    }
    env.update(extra)
    return env


def _bash(script: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["/bin/bash", "-uc", script], capture_output=True, text=True, env=env)


def test_render_launchd_plist_substitutes_every_token(tmp_path: Path) -> None:
    dst = tmp_path / "rendered.plist"
    result = _bash(
        f'source "{ROOT}/scripts/lib/util.sh"\n_render_launchd_plist "{TEMPLATE}" "{dst}"',
        _env(tmp_path),
    )

    assert result.returncode == 0, result.stderr
    text = dst.read_text(encoding="utf-8")
    assert "__OMLX_VENV__" not in text and "__HOME__" not in text

    env = _env(tmp_path)
    venv = env["OMLX_VENV_PATH"]
    cfg = plistlib.loads(dst.read_bytes())
    assert cfg["ProgramArguments"][0] == f"{venv}/bin/python"
    assert cfg["EnvironmentVariables"]["OMLX_VENV_PATH"] == venv
    assert cfg["WorkingDirectory"] == env["HOME"]
    assert cfg["ProcessType"] == "Standard"


def test_render_launchd_plist_refuses_a_token_it_cannot_substitute(tmp_path: Path) -> None:
    src = tmp_path / "template.plist"
    src.write_text("<plist><string>__UV_DIR__:/usr/bin</string></plist>\n", encoding="utf-8")
    dst = tmp_path / "rendered.plist"

    result = _bash(
        f'source "{ROOT}/scripts/lib/util.sh"\n_render_launchd_plist "{src}" "{dst}"',
        _env(tmp_path),
    )

    assert result.returncode != 0
    assert not dst.exists(), "an unrenderable template must not be installed"


def test_copied_raw_template_does_not_match_the_rendered_copy(tmp_path: Path) -> None:
    copied = tmp_path / "copied.plist"
    copied.write_bytes(TEMPLATE.read_bytes())
    rendered = tmp_path / "rendered.plist"
    script = f"""
source "{ROOT}/scripts/lib/util.sh"
_render_launchd_plist "{TEMPLATE}" "{rendered}"
_launchd_plist_matches com.portal5.omlx "{copied}"; echo "copied=$?"
_launchd_plist_matches com.portal5.omlx "{rendered}"; echo "rendered=$?"
_launchd_plist_matches com.portal5.omlx "{tmp_path}/absent.plist"; echo "absent=$?"
"""

    result = _bash(script, _env(tmp_path))

    assert result.returncode == 0, result.stderr
    assert "copied=1" in result.stdout
    assert "rendered=0" in result.stdout
    assert "absent=1" in result.stdout


@_DARWIN
def test_up_names_the_installer_when_the_omlx_agent_was_not_rendered(tmp_path: Path) -> None:
    env = _env(tmp_path)
    agent = Path(env["HOME"]) / "Library" / "LaunchAgents" / "com.portal5.omlx.plist"
    agent.parent.mkdir(parents=True)

    agent.write_bytes(TEMPLATE.read_bytes())
    stale = _bash(f'source "{ROOT}/scripts/lib/util.sh"\n_warn_omlx_plist_drift', env)
    assert "differs from the rendered repo copy" in stale.stdout
    assert "./launch.sh install-omlx" in stale.stdout

    _bash(
        f'source "{ROOT}/scripts/lib/util.sh"\n_render_launchd_plist "{TEMPLATE}" "{agent}"',
        env,
    )
    current = _bash(f'source "{ROOT}/scripts/lib/util.sh"\n_warn_omlx_plist_drift', env)
    assert current.stdout.strip() == ""

    agent.unlink()
    missing = _bash(f'source "{ROOT}/scripts/lib/util.sh"\n_warn_omlx_plist_drift', env)
    assert "installed plist missing" in missing.stdout


def test_ensure_native_services_checks_the_omlx_agent_plist() -> None:
    util = (ROOT / "scripts" / "lib" / "util.sh").read_text(encoding="utf-8")
    body = util.split("_ensure_native_services() {", 1)[1]
    assert "_warn_omlx_plist_drift" in body


@_DARWIN
def test_install_omlx_stops_when_the_venv_interpreter_is_missing(tmp_path: Path) -> None:
    env = _env(tmp_path, venv=False)
    _stub(
        tmp_path / "bin" / "launchctl",
        '#!/bin/bash\nprintf "%s\\n" "$*" >> "$CALL_LOG"\nexit 0\n',
    )
    script = f"""
source "{ROOT}/scripts/lib/util.sh"
source "{ROOT}/scripts/lib/services.sh"
_launch_install_omlx
"""

    result = _bash(script, env)

    assert result.returncode != 0
    assert "omlx_venv_install.py" in result.stdout
    agent = Path(env["HOME"]) / "Library" / "LaunchAgents" / "com.portal5.omlx.plist"
    assert not agent.exists()
