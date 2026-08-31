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


def test_warn_unset_thinking_mode_flags_unset_and_ignores_explicit():
    from portal.platform.inference.router.validation import warn_unset_thinking_mode

    saved = dict(WORKSPACES)
    WORKSPACES.clear()
    WORKSPACES.update(
        {
            "ws-unset": {"model_hint": "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k"},
            "ws-explicit-false": {
                "model_hint": "hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL",
                "think": False,
            },
            "ws-explicit-true": {
                "model_hint": "hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL",
                "think": True,
            },
            "ws-coder-exempt": {"model_hint": "qwen3-coder:30b-a3b-q4_K_M-ctx16k"},
            "ws-non-thinking": {"model_hint": "granite4.1:8b-ctx16k"},
            "ws-variant-unset": {
                # non-thinking base, no `think` — the variant swaps to a
                # thinking model without setting `think`, so it must be flagged.
                "model_hint": "granite4.1:8b",
                "variants": {"deep": {"model_hint": "qwen3.6:27b-q4_K_M"}},
            },
            "ws-variant-inherits-false": {
                "model_hint": "granite4.1:8b",
                "think": False,
                "variants": {"deep": {"model_hint": "qwen3.6:27b-q4_K_M"}},
            },
        }
    )
    try:
        flagged = {
            w.split("workspace=")[1].split(" ")[0].strip("'") for w in warn_unset_thinking_mode()
        }
        assert "ws-unset" in flagged
        assert "ws-variant-unset::deep" in flagged
        assert "ws-variant-inherits-false::deep" not in flagged
        assert "ws-explicit-false" not in flagged
        assert "ws-explicit-true" not in flagged
        assert "ws-coder-exempt" not in flagged
        assert "ws-non-thinking" not in flagged
    finally:
        WORKSPACES.clear()
        WORKSPACES.update(saved)


def test_no_production_workspace_has_unset_thinking_mode():
    """The live WORKSPACES dict — every thinking-capable workspace sets `think`."""
    from portal.platform.inference.router.validation import warn_unset_thinking_mode

    warnings = warn_unset_thinking_mode()
    assert warnings == [], "workspaces with unset think mode:\n  " + "\n  ".join(warnings)
