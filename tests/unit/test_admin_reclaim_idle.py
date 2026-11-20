"""Tests for POST /admin/reclaim-idle body handling (handlers.py).

Covers: empty body (unbounded), ``{}`` (422), malformed JSON (400),
and a valid ``need_gib`` value (200).
"""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from portal.platform.inference.cluster_backends import BackendRegistry

PIPELINE_API_KEY = os.environ.get("PIPELINE_API_KEY", "test-pipeline-key-for-unit-tests")


def _make_fake_backend():
    """Build a mock BackendRegistry suitable for TestClient tests."""
    reg = MagicMock(spec=BackendRegistry)
    be = MagicMock()
    be.id = "test-backend"
    be.group = "general"
    be.models = ["test-model"]
    be.type = "ollama"
    be.url = "http://127.0.0.1:11434"
    reg.list_healthy_backends.return_value = [be]
    reg.list_backends.return_value = [be]
    reg.get_backend_candidates.return_value = [be]
    reg.workspace_routes = {}
    return reg


@pytest.fixture
def client():
    """FastAPI TestClient with a fake backend registry."""
    from fastapi.testclient import TestClient

    import portal.platform.inference.router.handlers as handlers_mod
    from portal.platform.inference.router_pipe import app

    handlers_mod.registry = _make_fake_backend()
    with TestClient(app) as test_client:
        yield test_client
    handlers_mod.registry = None


class TestAdminReclaimIdleBody:
    """POST /admin/reclaim-idle — body parsing, validation, and unbounded."""

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {PIPELINE_API_KEY}"}

    # ── empty body: unbounded (200) ──────────────────────────────────

    def test_empty_body_returns_200_with_unbounded(self, client):
        """No body → unbounded → 200 with unloads/residents shape."""
        mock_guard = MagicMock()
        mock_guard.reclaim_idle_memory = AsyncMock(return_value={"unloads": [], "residents": []})
        mock_guard.GUARD = mock_guard

        with patch("portal.platform.inference.load_guard") as lg_mod:
            lg_mod.GUARD = mock_guard
            resp = client.post(
                "/admin/reclaim-idle",
                content=b"",
                headers=self._auth(),
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "unloads" in body
        assert "residents" in body
        mock_guard.reclaim_idle_memory.assert_awaited_once()
        call_args = mock_guard.reclaim_idle_memory.await_args
        assert call_args[0][1] == float("inf")

    def test_no_content_returns_200(self, client):
        """No content at all → empty body → unbounded → 200."""
        mock_guard = MagicMock()
        mock_guard.reclaim_idle_memory = AsyncMock(return_value={"unloads": [], "residents": []})
        mock_guard.GUARD = mock_guard

        with patch("portal.platform.inference.load_guard") as lg_mod:
            lg_mod.GUARD = mock_guard
            resp = client.post(
                "/admin/reclaim-idle",
                headers=self._auth(),
            )

        assert resp.status_code == 200

    # ── malformed JSON: 400 ──────────────────────────────────────────

    def test_malformed_json_returns_400(self, client):
        """Non-JSON body → 400 with clear detail."""
        mock_guard = MagicMock()
        mock_guard.GUARD = mock_guard

        with patch("portal.platform.inference.load_guard") as lg_mod:
            lg_mod.GUARD = mock_guard
            resp = client.post(
                "/admin/reclaim-idle",
                content=b"not-json",
                headers=self._auth(),
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid JSON body"

    def test_json_array_returns_400(self, client):
        """A JSON array is not a dict → 400."""
        mock_guard = MagicMock()
        mock_guard.GUARD = mock_guard

        with patch("portal.platform.inference.load_guard") as lg_mod:
            lg_mod.GUARD = mock_guard
            resp = client.post(
                "/admin/reclaim-idle",
                content=b"[1, 2, 3]",
                headers=self._auth(),
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Request body must be a JSON object"

    # ── empty object: 422 ────────────────────────────────────────────

    def test_empty_object_returns_422(self, client):
        """``{}`` → need_gib missing → 422."""
        mock_guard = MagicMock()
        mock_guard.GUARD = mock_guard

        with patch("portal.platform.inference.load_guard") as lg_mod:
            lg_mod.GUARD = mock_guard
            resp = client.post(
                "/admin/reclaim-idle",
                content=b"{}",
                headers=self._auth(),
            )

        assert resp.status_code == 422
        assert resp.json()["detail"] == "need_gib must be a positive finite number"

    # ── invalid need_gib: 422 ────────────────────────────────────────

    def test_negative_need_gib_returns_422(self, client):
        mock_guard = MagicMock()
        mock_guard.GUARD = mock_guard

        with patch("portal.platform.inference.load_guard") as lg_mod:
            lg_mod.GUARD = mock_guard
            resp = client.post(
                "/admin/reclaim-idle",
                content=json.dumps({"need_gib": -1}),
                headers=self._auth(),
            )

        assert resp.status_code == 422

    def test_zero_need_gib_returns_422(self, client):
        mock_guard = MagicMock()
        mock_guard.GUARD = mock_guard

        with patch("portal.platform.inference.load_guard") as lg_mod:
            lg_mod.GUARD = mock_guard
            resp = client.post(
                "/admin/reclaim-idle",
                content=json.dumps({"need_gib": 0}),
                headers=self._auth(),
            )

        assert resp.status_code == 422

    def test_inf_need_gib_returns_422(self, client):
        mock_guard = MagicMock()
        mock_guard.GUARD = mock_guard

        with patch("portal.platform.inference.load_guard") as lg_mod:
            lg_mod.GUARD = mock_guard
            resp = client.post(
                "/admin/reclaim-idle",
                content=json.dumps({"need_gib": float("inf")}),
                headers=self._auth(),
            )

        assert resp.status_code == 422

    def test_nan_need_gib_returns_422(self, client):
        mock_guard = MagicMock()
        mock_guard.GUARD = mock_guard

        with patch("portal.platform.inference.load_guard") as lg_mod:
            lg_mod.GUARD = mock_guard
            resp = client.post(
                "/admin/reclaim-idle",
                content=json.dumps({"need_gib": float("nan")}),
                headers=self._auth(),
            )

        assert resp.status_code == 422

    def test_string_need_gib_returns_422(self, client):
        mock_guard = MagicMock()
        mock_guard.GUARD = mock_guard

        with patch("portal.platform.inference.load_guard") as lg_mod:
            lg_mod.GUARD = mock_guard
            resp = client.post(
                "/admin/reclaim-idle",
                content=json.dumps({"need_gib": "10"}),
                headers=self._auth(),
            )

        assert resp.status_code == 422

    # ── valid need_gib: 200 ─────────────────────────────────────────

    def test_valid_need_gib_returns_200(self, client):
        """``{"need_gib": 10}`` → 200, passes 10 GiB in bytes."""
        mock_guard = MagicMock()
        mock_guard.reclaim_idle_memory = AsyncMock(return_value={"unloads": [], "residents": []})
        mock_guard.GUARD = mock_guard

        with patch("portal.platform.inference.load_guard") as lg_mod:
            lg_mod.GUARD = mock_guard
            resp = client.post(
                "/admin/reclaim-idle",
                content=json.dumps({"need_gib": 10}),
                headers=self._auth(),
            )

        assert resp.status_code == 200
        mock_guard.reclaim_idle_memory.assert_awaited_once()
        call_args = mock_guard.reclaim_idle_memory.await_args
        assert call_args[0][1] == 10 * 1024**3

    def test_float_need_gib_returns_200(self, client):
        """``{"need_gib": 2.5}`` → 200, passes 2.5 GiB in bytes."""
        mock_guard = MagicMock()
        mock_guard.reclaim_idle_memory = AsyncMock(return_value={"unloads": [], "residents": []})
        mock_guard.GUARD = mock_guard

        with patch("portal.platform.inference.load_guard") as lg_mod:
            lg_mod.GUARD = mock_guard
            resp = client.post(
                "/admin/reclaim-idle",
                content=json.dumps({"need_gib": 2.5}),
                headers=self._auth(),
            )

        assert resp.status_code == 200
        mock_guard.reclaim_idle_memory.assert_awaited_once()
        call_args = mock_guard.reclaim_idle_memory.await_args
        assert call_args[0][1] == 2.5 * 1024**3
