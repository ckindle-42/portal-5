"""uv sync --check direction. A lock bump prints `- old` and `+ new` together.

Calling every `-` line "venv ahead" blocked `up`/`rebuild` from syncing after
the 2026-11-19 lock bump, and the preflight told mlx-transcribe the venv was
ahead when the lock was.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.venv_lock_direction import (
    LOCK_AHEAD,
    REINSTALL,
    VENV_AHEAD,
    classify_sync_diff,
    drift_message,
)

_ROOT = Path(__file__).resolve().parents[2]

_LOCK_AHEAD = """\
The environment is outdated; run `uv sync` to update the environment.
Would uninstall 2 packages
Would install 2 packages
 - certifi==2025.1.31
 + certifi==2026.10.23
 - pillow==12.2.0
 + pillow==13.0.0
"""

_VENV_AHEAD = """\
Would uninstall 1 package
Would install 1 package
 - transformers==5.16.1
 + transformers==4.57.6
"""


def test_version_replacements_with_minus_lines_are_lock_ahead():
    assert classify_sync_diff(_LOCK_AHEAD) == LOCK_AHEAD
    message = drift_message(LOCK_AHEAD)
    assert "lock is AHEAD" in message
    assert "venv is AHEAD" not in message


def test_a_downgrade_is_venv_ahead():
    assert classify_sync_diff(_VENV_AHEAD) == VENV_AHEAD
    assert "venv is AHEAD" in drift_message(VENV_AHEAD)


def test_removed_without_replacement_is_venv_ahead():
    text = " - mlx-vlm==0.3.0\n"
    assert classify_sync_diff(text) == VENV_AHEAD


def test_reinstall_tilde_is_not_venv_ahead():
    text = " ~ numpy==2.3.5\n"
    assert classify_sync_diff(text) == REINSTALL
    assert "venv is AHEAD" not in drift_message(REINSTALL)


def test_additions_only_are_lock_ahead():
    assert classify_sync_diff(" + pillow==13.0.0\n") == LOCK_AHEAD


def test_sync_helper_syncs_only_when_the_lock_is_ahead(tmp_path: Path) -> None:
    log = tmp_path / "uv-args"
    uv = tmp_path / "uv"
    uv.write_text(
        "#!/bin/bash\n"
        f'printf "%s\\n" "$*" >> "{log}"\n'
        'if [[ " $* " == *" --check "* ]]; then\n'
        '  echo "Would uninstall 1 package" >&2\n'
        '  echo " - certifi==2025.1.31" >&2\n'
        '  echo " + certifi==2026.10.23" >&2\n'
        "  exit 1\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    uv.chmod(0o755)
    script = (
        "set -euo pipefail\n"
        f"export HOME={tmp_path}\n"
        f"export PORTAL_ROOT={_ROOT}\n"
        f"export UV_BIN={uv}\n"
        f"source {_ROOT}/scripts/lib/venv_preflight.sh\n"
        "_sync_venv_when_lock_ahead\n"
    )
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "lock is AHEAD" in result.stdout
    recorded = log.read_text(encoding="utf-8").splitlines()
    assert any("--check" in line for line in recorded)
    assert any("--check" not in line and "--frozen" in line for line in recorded)


def test_sync_helper_refuses_when_the_venv_is_ahead(tmp_path: Path) -> None:
    log = tmp_path / "uv-args"
    uv = tmp_path / "uv"
    uv.write_text(
        "#!/bin/bash\n"
        f'printf "%s\\n" "$*" >> "{log}"\n'
        'echo " - transformers==5.16.1" >&2\n'
        'echo " + transformers==4.57.6" >&2\n'
        "exit 1\n",
        encoding="utf-8",
    )
    uv.chmod(0o755)
    script = (
        "set -euo pipefail\n"
        f"export HOME={tmp_path}\n"
        f"export PORTAL_ROOT={_ROOT}\n"
        f"export UV_BIN={uv}\n"
        f"source {_ROOT}/scripts/lib/venv_preflight.sh\n"
        "_sync_venv_when_lock_ahead\n"
    )
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "venv is AHEAD" in result.stderr
    assert "lock is AHEAD" not in result.stderr
    recorded = log.read_text(encoding="utf-8")
    assert recorded.count("\n") == 1
