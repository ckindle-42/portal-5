"""Test the workspace hint validator."""

from unittest.mock import MagicMock

from portal.platform.inference.router_pipe import WORKSPACES, _validate_workspace_hints


def _mock_registry(backends: list[tuple[str, str, list[str]]], routes: dict[str, list[str]]):
    """Build a mock registry. backends = [(id, group, models), ...]."""
    reg = MagicMock()
    be_objs = []
    for bid, grp, models in backends:
        b = MagicMock()
        b.id = bid
        b.group = grp
        b.models = models
        be_objs.append(b)
    reg.list_backends.return_value = be_objs
    reg.workspace_routes = routes
    return reg


def test_validator_passes_when_hints_resolve():
    reg = _mock_registry(
        backends=[
            ("ollama-coding", "coding", ["qwen3-coder:30b"]),
        ],
        routes={"auto-coding": ["coding", "general"]},
    )
    saved = dict(WORKSPACES)
    WORKSPACES.clear()
    WORKSPACES["auto-coding"] = {
        "name": "test",
        "description": "test",
        "model_hint": "qwen3-coder:30b",
        "tools": [],
    }
    try:
        errors = _validate_workspace_hints(reg)
        assert errors == []
    finally:
        WORKSPACES.clear()
        WORKSPACES.update(saved)


def test_validator_catches_missing_hint():
    reg = _mock_registry(
        backends=[("ollama-coding", "coding", ["qwen3-coder:30b"])],
        routes={"auto-coding": ["coding"]},
    )
    saved = dict(WORKSPACES)
    WORKSPACES.clear()
    WORKSPACES["auto-coding"] = {
        "name": "test",
        "description": "test",
        "model_hint": "nonexistent:99b",
        "tools": [],
    }
    try:
        errors = _validate_workspace_hints(reg)
        assert len(errors) == 1
        assert "nonexistent:99b" in errors[0]
    finally:
        WORKSPACES.clear()
        WORKSPACES.update(saved)


def test_validator_catches_real_workspaces_dict():
    """Smoke test against the actual WORKSPACES dict and backends.yaml.

    Run with PORTAL_ENABLE_EVAL=1 to also exercise the bench-* tier (60
    hints fixed 2026-07-18: not stale/pruned models, just a missing
    workspace_routing group assignment for the whole eval module plus a
    handful of bare-tag hints missing an explicit :latest suffix — see
    KNOWN_LIMITATIONS.md's now-removed PORTAL_ENABLE_EVAL entry history).
    """
    from portal.platform.inference.cluster_backends import BackendRegistry

    reg = BackendRegistry()
    errors = _validate_workspace_hints(reg)
    assert errors == [], "Hint validation regressions:\n  " + "\n  ".join(errors)
