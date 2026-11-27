"""Shared fake backend helper and alias-expiry contract for pipeline tests."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from portal.platform.inference.cluster_backends import BackendRegistry
from portal.platform.inference.config import load_portal_config


def _make_fake_backend():
    """Build a mock BackendRegistry suitable for TestClient tests."""
    reg = MagicMock(spec=BackendRegistry)
    be = MagicMock()
    be.id = "test-backend"
    be.group = "general"
    be.models = ["test-model"]
    be.type = "ollama"
    reg.list_healthy_backends.return_value = [be]
    reg.list_backends.return_value = [be]
    reg.get_backend_candidates.return_value = [be]
    reg.workspace_routes = {}
    return reg


def test_workspace_aliases_have_not_passed_their_removal_date() -> None:
    expired = {
        alias_id: alias.remove_after.isoformat()
        for alias_id, alias in load_portal_config().aliases.items()
        if alias.remove_after < date.today()
    }
    assert not expired, f"Expired workspace aliases: {expired}"
