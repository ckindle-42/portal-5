"""Tests for portal.platform.inference.config schema validation.

Verifies that deliberately broken portal.yaml inputs raise at load time with
precise messages rather than silently delivering invalid state.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from portal.platform.inference.config import (
    Model,
    PortalConfig,
    WorkspaceSpec,
    get_workspace_dict,
    load_portal_config,
    merge_workspace_variant,
)

REPO = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(autouse=True)
def _restore_real_config():
    """Restore the real portal.yaml cache after each test in this file.

    Tests here intentionally reload with minimal/broken YAML fixtures.
    The autouse fixture ensures no cache pollution bleeds to other test files.
    """
    yield
    load_portal_config(_force_reload=True)


def _load_minimal(tmp_path: Path, overrides: dict) -> dict:
    """Build a minimal valid portal.yaml dict and apply overrides."""
    base = {
        "ollama_url": "http://localhost:11434",
        "mcp_fleet": [
            {
                "id": "documents",
                "name": "portal-documents",
                "module": "documents",
                "port": 8913,
                "expose_to_pipeline": True,
                "expose_to_ide": True,
            }
        ],
        "workspaces": {
            "auto": {
                "name": "Auto",
                "description": "Auto router",
                "module": "general",
                "tools": [],
                "expose_to_owui": True,
                "enable_web_search": False,
            }
        },
    }
    base.update(overrides)
    return base


def test_valid_minimal_config(tmp_path: Path) -> None:
    """A minimal well-formed portal.yaml loads without error."""
    raw = _load_minimal(tmp_path, {})
    cfg = PortalConfig.model_validate(raw)
    assert "auto" in cfg.workspaces
    assert cfg.mcp_fleet[0].id == "documents"


def test_stack_down_only_workspace_level_and_variant_override(tmp_path: Path) -> None:
    """stack_down_only is accepted at workspace level and inside a variant dict;
    the runtime dict stays byte-equal for workspaces that do not set it."""
    raw = _load_minimal(
        tmp_path,
        {
            "workspaces": {
                "auto": {
                    "name": "Auto",
                    "description": "Auto router",
                    "module": "general",
                },
                "ide": {
                    "name": "IDE",
                    "description": "IDE lane",
                    "module": "general",
                    "stack_down_only": True,
                    "variants": {"heavy": {"stack_down_only": True}},
                },
            }
        },
    )
    cfg = PortalConfig.model_validate(raw)
    assert cfg.workspaces["ide"].stack_down_only is True
    assert cfg.workspaces["ide"].variants["heavy"]["stack_down_only"] is True
    assert cfg.workspaces["auto"].stack_down_only is None

    dumped = get_workspace_dict(cfg)
    assert "stack_down_only" not in dumped["auto"]
    assert dumped["ide"]["stack_down_only"] is True
    assert "variants" not in dumped["ide"]
    # The variant override flows through the same merge the serving path uses.
    merged = merge_workspace_variant(dumped["ide"], cfg.workspaces["ide"].variants["heavy"])
    assert merged["stack_down_only"] is True


def test_thinking_budget_workspace_and_variant_schema(tmp_path: Path) -> None:
    raw = _load_minimal(
        tmp_path,
        {
            "workspaces": {
                "auto": {
                    "name": "Auto",
                    "description": "Auto router",
                    "module": "general",
                    "thinking_budget": 4096,
                    "variants": {"deep": {"thinking_budget": 8192}},
                }
            }
        },
    )
    cfg = PortalConfig.model_validate(raw)
    workspace = cfg.workspaces["auto"]
    assert workspace.thinking_budget == 4096
    assert workspace.variants["deep"]["thinking_budget"] == 8192
    assert (
        merge_workspace_variant(get_workspace_dict(cfg)["auto"], workspace.variants["deep"])[
            "thinking_budget"
        ]
        == 8192
    )


@pytest.mark.parametrize("budget", [0, -1, True, "4096"])
def test_thinking_budget_must_be_a_positive_integer(budget: object) -> None:
    with pytest.raises(ValueError):
        WorkspaceSpec.model_validate(
            {
                "name": "Budget",
                "description": "Budget",
                "module": "general",
                "thinking_budget": budget,
            }
        )
    with pytest.raises(ValueError):
        WorkspaceSpec.model_validate(
            {
                "name": "Budget",
                "description": "Budget",
                "module": "general",
                "variants": {"invalid": {"thinking_budget": budget}},
            }
        )


def test_duplicate_port_raises(tmp_path: Path) -> None:
    """Two MCP servers sharing a port must fail validation with a clear message."""
    raw = _load_minimal(
        tmp_path,
        {
            "mcp_fleet": [
                {
                    "id": "a",
                    "name": "svc-a",
                    "module": "general",
                    "port": 9000,
                    "expose_to_pipeline": True,
                    "expose_to_ide": True,
                },
                {
                    "id": "b",
                    "name": "svc-b",
                    "module": "general",
                    "port": 9000,
                    "expose_to_pipeline": True,
                    "expose_to_ide": True,
                },
            ]
        },
    )
    with pytest.raises(Exception, match="9000"):
        PortalConfig.model_validate(raw)


def test_duplicate_id_raises(tmp_path: Path) -> None:
    """Two MCP servers with the same id must fail validation."""
    raw = _load_minimal(
        tmp_path,
        {
            "mcp_fleet": [
                {
                    "id": "dup",
                    "name": "svc-a",
                    "module": "general",
                    "port": 9001,
                    "expose_to_pipeline": True,
                    "expose_to_ide": True,
                },
                {
                    "id": "dup",
                    "name": "svc-b",
                    "module": "general",
                    "port": 9002,
                    "expose_to_pipeline": True,
                    "expose_to_ide": True,
                },
            ]
        },
    )
    with pytest.raises(Exception, match="dup"):
        PortalConfig.model_validate(raw)


def test_workspace_missing_name_raises(tmp_path: Path) -> None:
    """A workspace without a name must fail pydantic validation."""
    raw = _load_minimal(
        tmp_path,
        {
            "workspaces": {
                "bad": {
                    "description": "no name",
                    "tools": [],
                    "expose_to_owui": True,
                    "enable_web_search": False,
                }
            }
        },
    )
    with pytest.raises(Exception, match="name"):
        PortalConfig.model_validate(raw)


def test_load_portal_config_uses_cache(tmp_path: Path) -> None:
    """load_portal_config returns the same object on repeated calls (cache)."""
    a = load_portal_config()
    b = load_portal_config()
    assert a is b


def test_load_portal_config_force_reload(tmp_path: Path) -> None:
    """_force_reload=True bypasses the cache (used in tests)."""
    a = load_portal_config()
    b = load_portal_config(_force_reload=True)
    # Different object, but same data
    assert a is not b
    assert set(a.workspaces.keys()) == set(b.workspaces.keys())


def test_load_portal_config_bad_yaml_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A syntactically invalid YAML file raises RuntimeError with a clear message."""
    bad_yaml = tmp_path / "portal.yaml"
    bad_yaml.write_text(": bad: yaml: {{{")

    with pytest.raises((RuntimeError, Exception)):
        load_portal_config(path=bad_yaml, _force_reload=True)


def test_load_portal_config_schema_error_raises(tmp_path: Path) -> None:
    """A schema error (duplicate port) surfaces as RuntimeError from load_portal_config."""
    raw = {
        "mcp_fleet": [
            {
                "id": "a",
                "name": "svc-a",
                "module": "general",
                "port": 9000,
                "expose_to_pipeline": True,
                "expose_to_ide": True,
            },
            {
                "id": "b",
                "name": "svc-b",
                "module": "general",
                "port": 9000,
                "expose_to_pipeline": True,
                "expose_to_ide": True,
            },
        ],
        "workspaces": {
            "auto": {
                "name": "Auto",
                "description": "x",
                "module": "general",
                "tools": [],
                "expose_to_owui": True,
                "enable_web_search": False,
            }
        },
    }
    p = tmp_path / "portal.yaml"
    p.write_text(yaml.dump(raw))
    with pytest.raises((RuntimeError, Exception), match="9000"):
        load_portal_config(path=p, _force_reload=True)


def test_ollama_url_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """OLLAMA_URL env var overrides the yaml value."""
    raw = {
        "ollama_url": "http://docker-internal:11434",
        "mcp_fleet": [],
        "workspaces": {
            "auto": {
                "name": "Auto",
                "description": "x",
                "module": "general",
                "tools": [],
                "expose_to_owui": True,
                "enable_web_search": False,
            }
        },
    }
    p = tmp_path / "portal.yaml"
    p.write_text(yaml.dump(raw))
    monkeypatch.setenv("OLLAMA_URL", "http://custom-host:11434")
    cfg = load_portal_config(path=p, _force_reload=True)
    assert cfg.ollama_url == "http://custom-host:11434"
    monkeypatch.delenv("OLLAMA_URL", raising=False)


# ── Model schema tests (TASK_LIFT_HF_REGISTRY_TO_PORTAL_YAML_V1) ──────────────


def test_model_schema_minimal() -> None:
    """Only hf_id + ollama_name are required."""
    m = Model.model_validate({"hf_id": "foo/bar", "ollama_name": "my-tag"})
    assert m.hf_id == "foo/bar"
    assert m.ollama_name == "my-tag"
    assert m.actual_repo == "foo/bar"  # defaults to hf_id
    assert m.filename is None
    assert m.gated is False
    assert m.retired is False


def test_model_schema_full() -> None:
    """All fields populate correctly."""
    m = Model.model_validate(
        {
            "hf_id": "foo/bar",
            "actual_repo": "baz/qux",
            "filename": "model.gguf",
            "ollama_name": "my-tag",
            "gated": True,
            "retired": True,
        }
    )
    assert m.hf_id == "foo/bar"
    assert m.actual_repo == "baz/qux"
    assert m.filename == "model.gguf"
    assert m.ollama_name == "my-tag"
    assert m.gated is True
    assert m.retired is True


def test_model_schema_actual_repo_defaults_to_hf_id() -> None:
    """actual_repo falls back to hf_id when omitted."""
    m = Model.model_validate({"hf_id": "foo/bar", "ollama_name": "tag"})
    assert m.actual_repo == "foo/bar"


def test_model_schema_retired_default_false() -> None:
    """retired defaults to False."""
    m = Model.model_validate({"hf_id": "x/y", "ollama_name": "tag"})
    assert m.retired is False


def test_model_schema_rejects_unknown_fields() -> None:
    """extra=forbid should reject unknown keys."""
    from pydantic import ValidationError as PydanticValidationError

    with pytest.raises(PydanticValidationError):
        Model.model_validate({"hf_id": "x/y", "ollama_name": "tag", "not_a_field": 42})


def test_portal_config_models_default_empty_list() -> None:
    """PortalConfig.models defaults to empty list."""
    cfg = PortalConfig.model_validate(
        {
            "workspaces": {
                "auto": {
                    "name": "Auto",
                    "description": "x",
                    "module": "general",
                    "tools": [],
                    "expose_to_owui": True,
                    "enable_web_search": False,
                }
            },
            "mcp_fleet": [],
        }
    )
    assert cfg.models == []


def test_context_inject_flags_reach_runtime_dict() -> None:
    """auto-daily's inject_memory/memory_writeback must reach the runtime
    WORKSPACES dict. The M1 pydantic migration silently dropped these keys
    (WorkspaceSpec never declared them, extra=ignore), leaving
    router/context_inject.py permanently inert in production while
    config_validate.py still blessed them. Regression guard: the schema must
    carry them through, and non-declaring workspaces must not gain the keys.

    auto_rag was removed from auto-daily by TASK_RAG_COMPOSITION_SEAM_V1 P1
    [GATE] (c) — the feature never ran — so no workspace declares it now; the
    schema still lists it (config.py) for when the gate is answered."""
    from portal.platform.inference.config import get_workspace_dict

    ws = get_workspace_dict(load_portal_config(_force_reload=True))
    daily = ws["auto-daily"]
    assert daily.get("inject_memory") is True
    assert daily.get("auto_rag") is not True
    assert daily.get("memory_writeback") is True

    coding = ws["auto-coding"]
    for key in (
        "inject_memory",
        "auto_rag",
        "memory_writeback",
        "memory_writeback_all",
        "inject_temporal_context",
    ):
        assert key not in coding
