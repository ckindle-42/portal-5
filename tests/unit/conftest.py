"""Unit-test-specific pytest configuration.

Ensures prometheus_client can initialize on platforms without /dev/shm
(e.g. macOS) by setting PROMETHEUS_MULTIPROC_DIR to a valid temp directory
before any test module imports. Also patches lifespan background tasks
that fail during fixture teardown.
"""

import os
import tempfile
from pathlib import Path


def pytest_configure(config) -> None:
    """Set up PROMETHEUS_MULTIPROC_DIR before collection begins.

    prometheus_client initialises mmap-backed metric files at import time.
    On Linux this defaults to /dev/shm; on macOS that path does not exist
    and import crashes with FileNotFoundError. Create a temp directory that
    works cross-platform.
    """
    if "PROMETHEUS_MULTIPROC_DIR" not in os.environ:
        mp_dir = Path(tempfile.gettempdir()) / "portal5_pytest_metrics"
        mp_dir.mkdir(parents=True, exist_ok=True)
        os.environ["PROMETHEUS_MULTIPROC_DIR"] = str(mp_dir)

    # Prevent lifespan background tasks (health loop, state save) from
    # being created during TestClient teardown — they fail in test mode.
    os.environ["UNIT_TEST_MODE"] = "1"
