"""Unit-test-specific pytest configuration.

Isolates unit tests from environment pollution introduced during collection.

Root cause: test_prompt_signal_overlap.py imports portal5_acceptance_v6, which
calls _load_env() at module level. That reads .env and sets env vars — including
PROMETHEUS_MULTIPROC_DIR=/dev/shm/portal_metrics — before the first test runs.
When TestClient starts the app lifespan, the lifespan calls
os.makedirs(PROMETHEUS_MULTIPROC_DIR) which fails on macOS (/dev/shm is not a
writable user directory). Unit tests don't use prometheus multiprocess mode;
clearing the var here after collection (session fixture runs before first test)
prevents the lifespan crash.
"""

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _unit_env_isolation() -> None:
    """Remove env vars that portal5_acceptance_v6._load_env() injects during collection."""
    os.environ.pop("PROMETHEUS_MULTIPROC_DIR", None)
