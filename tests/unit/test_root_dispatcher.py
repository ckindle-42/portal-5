"""The root dispatcher (deploy/root/portal5-root) and its sudoers grant.

2026-11-16: root actions moved behind a root-owned dispatcher so automation never
stops for a sudo password. The repo carries the source so a reinstall is a copy,
not a recollection.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "deploy" / "root" / "portal5-root"
SUDOERS = ROOT / "deploy" / "root" / "sudoers-portal5-root"
README = ROOT / "deploy" / "root" / "README.md"


def test_wrapper_is_a_syntax_clean_root_script() -> None:
    assert WRAPPER.is_file(), "the dispatcher source belongs in deploy/root/"
    text = WRAPPER.read_text(encoding="utf-8")
    assert text.startswith("#!/bin/bash\n")
    assert "set -euo pipefail" in text
    assert subprocess.run(["/bin/bash", "-n", str(WRAPPER)]).returncode == 0


def test_wrapper_exposes_only_the_declared_actions() -> None:
    text = WRAPPER.read_text(encoding="utf-8")
    assert "install-powermetrics|uninstall-powermetrics" in text
    assert "launchctl-system)" in text
    assert "eval " not in text
    # No generic pass-through: the case is the whole interface.
    assert '"$@"' not in text

    rejected = subprocess.run(
        ["/bin/bash", str(WRAPPER), "restart-everything"], capture_output=True, text=True
    )
    assert rejected.returncode == 2
    assert "usage: portal5-root" in rejected.stdout


def test_launchctl_system_rejects_a_label_outside_portal5() -> None:
    result = subprocess.run(
        ["/bin/bash", str(WRAPPER), "launchctl-system", "com.evil.job"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "com.portal5.*" in result.stdout


def test_sudoers_grants_only_the_dispatcher() -> None:
    lines = [
        line
        for line in SUDOERS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert len(lines) == 1
    assert re.search(r"NOPASSWD:\s*/usr/local/sbin/portal5-root\s*$", lines[0])


def test_install_note_names_the_installed_paths_and_modes() -> None:
    note = README.read_text(encoding="utf-8")
    for expected in (
        "/usr/local/sbin/portal5-root",
        "/etc/sudoers.d/portal5-claude-root",
        "-o root -g wheel",
        "visudo -c",
        "sudo -n -l",
    ):
        assert expected in note, expected
