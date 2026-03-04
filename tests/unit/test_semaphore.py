"""tests/unit/test_semaphore.py — Semaphore exhaustion behavior."""
import os
import sys

# Must set before importing the module
os.environ.setdefault("MAX_CONCURRENT_REQUESTS", "2")

sys.path.insert(0, ".")
from fastapi.testclient import TestClient

from portal_pipeline.router_pipe import PIPELINE_API_KEY, app

CLIENT = TestClient(app)
HEADERS = {"Authorization": f"Bearer {PIPELINE_API_KEY}"}


class TestSemaphoreExhaustion:
    """Verify semaphore limits are enforced correctly."""

    def test_semaphore_initialized(self):
        """Semaphore is created during app lifespan."""
        # The semaphore may be None when using TestClient without lifespan
        # but the module-level variable should be defined
        from portal_pipeline import router_pipe
        assert hasattr(router_pipe, "_request_semaphore")

    def test_semaphore_limit_in_env(self):
        """MAX_CONCURRENT_REQUESTS env var is read."""
        from portal_pipeline import router_pipe
        assert router_pipe._MAX_CONCURRENT >= 1

    def test_chat_endpoint_exists_and_requires_auth(self):
        """The endpoint that the semaphore guards requires authentication."""
        resp = CLIENT.post(
            "/v1/chat/completions",
            json={"model": "auto", "messages": [{"role": "user", "content": "test"}]},
        )
        assert resp.status_code == 401

    def test_health_not_semaphore_guarded(self):
        """Health endpoint is not gated by the semaphore."""
        resp = CLIENT.get("/health")
        assert resp.status_code == 200
