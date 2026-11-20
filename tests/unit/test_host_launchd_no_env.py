"""Host launchd jobs export named dotenv keys and never source .env."""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
import textwrap
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_LAUNCHD = _ROOT / "deploy" / "launchd"

# Program text that pulls the whole dotenv into the process environment.
_SOURCE_MARKERS = (
    ". ./.env",
    "source .env",
    'source "$ENV_FILE"',
    'source "$PORTAL_ROOT/.env"',
    "set -a",
)


def _program(plist: Path) -> str:
    args = plistlib.loads(plist.read_bytes())["ProgramArguments"]
    return "\n".join(str(item) for item in args)


def test_launchd_templates_do_not_source_dotenv():
    offenders = []
    for plist in sorted(_LAUNCHD.glob("*.plist")):
        program = _program(plist)
        if any(marker in program for marker in _SOURCE_MARKERS):
            offenders.append(plist.name)
    assert offenders == []


def test_engine_update_exports_only_the_keys_the_job_reads(tmp_path: Path):
    command = _program(_LAUNCHD / "com.portal5.engine-update.plist")
    assert "portal_export_dotenv_keys .env " in command
    listed = command.split("portal_export_dotenv_keys .env ", 1)[1].split(" &&", 1)[0].split()
    assert listed == [
        "PUSHOVER_API_TOKEN",
        "PUSHOVER_USER_KEY",
        "ENGINE_CONTRACT_OLLAMA_URL",
        "ENGINE_CONTRACT_OMLX_URL",
        "OMLX_VENV_PATH",
    ]
    root = tmp_path / "portal"
    root.mkdir()
    (root / "scripts" / "lib").mkdir(parents=True)
    (root / "scripts" / "lib" / "host_dotenv.sh").write_text(
        (_ROOT / "scripts" / "lib" / "host_dotenv.sh").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (root / ".env").write_text(
        "\n".join(
            [
                "PUSHOVER_API_TOKEN=push-token",
                "PUSHOVER_USER_KEY=push-user",
                "OMLX_VENV_PATH=/opt/omlx/venv",
                "PROMETHEUS_MULTIPROC_DIR=/dev/shm/portal_metrics",
                "PIPELINE_API_KEY=must-not-leak",
                'ENGINE_CONTRACT_OLLAMA_URL=""',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    prefix = command.split(" && exec ", 1)[0].replace("__PORTAL_ROOT__", str(root))
    result = subprocess.run(
        ["/bin/bash", "-c", f"cd {root} && {prefix}; exec /usr/bin/env"],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
    )
    exported = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    assert exported["PUSHOVER_API_TOKEN"] == "push-token"
    assert exported["PUSHOVER_USER_KEY"] == "push-user"
    assert exported["OMLX_VENV_PATH"] == "/opt/omlx/venv"
    assert "PROMETHEUS_MULTIPROC_DIR" not in exported
    assert "PIPELINE_API_KEY" not in exported
    assert "ENGINE_CONTRACT_OLLAMA_URL" not in exported


def test_generated_media_launchers_do_not_source_dotenv():
    text = (_ROOT / "scripts" / "lib" / "services.sh").read_text(encoding="utf-8")
    assert text.count("portal_export_dotenv_keys") >= 3
    assert 'set -a; [ -f "\\$PORTAL_ROOT/.env" ]' not in text
    assert ". \\$PORTAL_ROOT/.env" not in text


def test_launch_sh_portal_commands_use_the_project_interpreter():
    text = (_ROOT / "launch.sh").read_text(encoding="utf-8")
    assert "python3 -m portal" not in text
    assert text.count('"$PORTAL_ROOT/.venv/bin/python" -m portal.platform.inference.cli') >= 11
    util = (_ROOT / "scripts" / "lib" / "util.sh").read_text(encoding="utf-8")
    services = (_ROOT / "scripts" / "lib" / "services.sh").read_text(encoding="utf-8")
    assert 'py="$(command -v python3)"' not in util
    assert 'portal_py="$(command -v python3)"' not in services


def test_metrics_import_survives_a_missing_multiproc_dir(tmp_path: Path):
    """The 11-20 engine-update crash: Gauge mmap open of a container dir on macOS."""
    missing = tmp_path / "not-a-dir"
    missing.write_text("file", encoding="utf-8")
    target = missing / "portal_metrics"
    script = textwrap.dedent(
        """
        import os, sys
        os.environ["PROMETHEUS_MULTIPROC_DIR"] = sys.argv[1]
        import portal.platform.inference.router.metrics as metrics
        from prometheus_client import values
        print("ENV", os.environ.get("PROMETHEUS_MULTIPROC_DIR", ""))
        print("CLASS", values.ValueClass.__name__)
        print("GAUGE", metrics._concurrent_requests._name)
        """
    )
    env = os.environ.copy()
    env.pop("PROMETHEUS_MULTIPROC_DIR", None)
    env.pop("prometheus_multiproc_dir", None)
    result = subprocess.run(
        [sys.executable, "-c", script, str(target)],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=_ROOT,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "ENV \n" in result.stdout or result.stdout.splitlines()[-3] == "ENV "
    assert "CLASS MutexValue" in result.stdout
    assert "disabling multiprocess mode" in result.stderr


def test_metrics_import_creates_a_missing_multiproc_dir(tmp_path: Path):
    target = tmp_path / "fresh" / "portal_metrics"
    script = textwrap.dedent(
        """
        import os, sys
        os.environ["PROMETHEUS_MULTIPROC_DIR"] = sys.argv[1]
        import portal.platform.inference.router.metrics  # noqa: F401
        from prometheus_client import values
        print("ENV", os.environ.get("PROMETHEUS_MULTIPROC_DIR", ""))
        print("CLASS", values.ValueClass.__name__)
        """
    )
    env = os.environ.copy()
    env.pop("PROMETHEUS_MULTIPROC_DIR", None)
    result = subprocess.run(
        [sys.executable, "-c", script, str(target)],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=_ROOT,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert target.is_dir()
    assert f"ENV {target}" in result.stdout
    assert "CLASS MmapedValue" in result.stdout
    assert "created missing PROMETHEUS_MULTIPROC_DIR" in result.stderr
