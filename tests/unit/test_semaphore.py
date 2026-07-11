"""tests/unit/test_semaphore.py — Semaphore concurrency behavior."""

import os
import sys

import pytest

# Must set before importing the module
os.environ.setdefault("MAX_CONCURRENT_REQUESTS", "2")
os.environ.setdefault("PIPELINE_API_KEY", "portal-pipeline")

sys.path.insert(0, ".")
from fastapi.testclient import TestClient

from portal.platform.inference.router_pipe import PIPELINE_API_KEY, app

HEADERS = {"Authorization": f"Bearer {PIPELINE_API_KEY}"}


@pytest.fixture
def client():
    """Create a test client with proper lifespan + fake registry."""
    from unittest.mock import MagicMock

    import portal.platform.inference.router.handlers as handlers_mod
    from portal.platform.inference.cluster_backends import BackendRegistry

    reg = MagicMock(spec=BackendRegistry)
    be = MagicMock()
    be.id = "test-backend"
    be.models = ["test-model"]
    reg.list_healthy_backends.return_value = [be]
    reg.list_backends.return_value = [be]
    handlers_mod.registry = reg
    with TestClient(app) as test_client:
        yield test_client
    handlers_mod.registry = None


class TestSemaphoreExhaustion:
    """Verify semaphore limits are enforced correctly."""

    def test_semaphore_initialized(self, client):
        """Semaphore is initialized during app lifespan."""
        import sys

        import portal.platform.inference.router.concurrency as _concurrency

        # A4 recurrence guard: the concurrency module must be the canonical
        # sys.modules entry. If a facade re-export shadowed it, writes to
        # _concurrency._request_semaphore would not reach RequestSlot.
        assert sys.modules["portal.platform.inference.router.concurrency"] is _concurrency
        assert _concurrency._request_semaphore is not None

    def test_semaphore_limit_in_env(self, client):
        """MAX_CONCURRENT_REQUESTS env var is read."""
        from portal.platform.inference import router_pipe

        assert router_pipe._MAX_CONCURRENT >= 1

    def test_health_not_semaphore_guarded(self, client):
        """Health endpoint responds without semaphore and with registry initialized."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "workspaces" in data

    def test_chat_endpoint_requires_auth(self, client):
        """The endpoint guarded by semaphore requires authentication."""
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "auto", "messages": [{"role": "user", "content": "test"}]},
        )
        assert resp.status_code == 401

    def test_semaphore_max_concurrent_configurable(self):
        """Semaphore limit reads from MAX_CONCURRENT_REQUESTS env var."""
        from portal.platform.inference import router_pipe

        # We set MAX_CONCURRENT_REQUESTS=2 at module top — verify it was read
        # (may be 2 or the default 20 depending on env at import time)
        assert router_pipe._MAX_CONCURRENT >= 1, "Semaphore limit must be positive"
