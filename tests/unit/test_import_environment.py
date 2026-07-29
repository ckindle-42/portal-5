"""Importing security benchmark helpers must not mutate process environment."""

from __future__ import annotations

import os
import subprocess
import sys


def test_security_data_import_does_not_load_dotenv_into_process_environment():
    child_env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PROMETHEUS_MULTIPROC_DIR", "UNIT_TEST_MODE"}
    }
    script = """
import os

before = dict(os.environ)
import portal.modules.security.core._data  # noqa: F401
added = sorted(set(os.environ) - set(before))
changed = sorted(k for k in before if os.environ.get(k) != before[k])
if added or changed:
    raise SystemExit(f"environment mutated: added={added}, changed={changed}")
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=os.getcwd(),
        env=child_env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr or result.stdout
