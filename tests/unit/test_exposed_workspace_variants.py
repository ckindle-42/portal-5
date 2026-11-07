"""Workspace variants marked expose_to_owui: model list, presets, serving resolution.

TASK_EXPOSE_WORKSPACE_VARIANTS: commit 4574ba310 turned auto-compliance::reading,
auto-coding::bigfix and auto-coding::cad into variants with expose_to_owui: true,
but neither the Pipeline /v1/models list nor sync-config exported them.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from portal.platform.inference import sync_config
from portal.platform.inference.config import WorkspaceSpec, load_portal_config
from portal.platform.inference.router import handlers
from portal.platform.inference.router.preinject import _resolve_workspace_variant
from portal.platform.inference.router.workspaces import WORKSPACES
from portal.platform.inference.sync_config import emit_owui_presets
from portal.platform.wiki.adapters import modules

EXPOSED_IDS = ("auto-compliance::reading", "auto-coding::bigfix", "auto-coding::cad")


# ── Pipeline /v1/models ───────────────────────────────────────────────────────


def _model_entries(monkeypatch) -> dict[str, dict]:
    monkeypatch.setattr(handlers, "_verify_key", lambda _authorization: None)
    data = asyncio.run(handlers.list_models(authorization=None))["data"]
    return {entry["id"]: entry for entry in data}


def test_exposed_variants_reach_the_model_list(monkeypatch) -> None:
    by_id = _model_entries(monkeypatch)
    for synthetic_id in EXPOSED_IDS:
        assert synthetic_id in by_id, f"{synthetic_id} missing from /v1/models"
    specs = load_portal_config().workspaces
    reading = by_id["auto-compliance::reading"]
    assert reading["name"] == specs["auto-compliance"].variants["reading"]["name"]
    assert reading["description"] == specs["auto-compliance"].variants["reading"]["description"]
    bigfix = by_id["auto-coding::bigfix"]
    assert bigfix["category"] == "coding"
    assert bigfix["tools"] == specs["auto-coding"].variants["bigfix"]["tools"]
    assert bigfix["is_benchmark"] is False


def test_unexposed_variants_stay_out_of_the_model_list(monkeypatch) -> None:
    by_id = _model_entries(monkeypatch)
    assert "auto-daily::gemma-fast" not in by_id  # expose_to_owui: false
    assert "auto-coding::laguna" not in by_id  # no explicit flag — not a declaration
    assert "auto-audio::image" not in by_id  # image module disabled


def test_base_workspaces_unchanged_in_the_model_list(monkeypatch) -> None:
    by_id = _model_entries(monkeypatch)
    for ws_id in ("auto-coding", "auto-compliance", "auto-daily", "bench-quick-smoke"):
        base = WORKSPACES.get(ws_id)
        if base is None:
            continue
        entry = by_id[ws_id]
        assert entry["name"] == base["name"]
        assert entry["tools"] == base.get("tools", [])
        assert entry["is_benchmark"] == ws_id.startswith("bench-")


# ── sync-config OWUI presets ──────────────────────────────────────────────────


def _ws(name: str, expose: bool, variants: dict | None = None) -> WorkspaceSpec:
    return WorkspaceSpec(
        name=name,
        description=name,
        module="general",
        expose_to_owui=expose,
        tools=[],
        owui_system_prompt="base prompt",
        enable_web_search=False,
        variants=variants or {},
    )


def test_exposed_variant_gets_a_preset(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(sync_config, "REPO", tmp_path)
    monkeypatch.setattr(modules, "owui_workspaces", lambda _mods=None: [])
    monkeypatch.setattr(modules, "is_workspace_disabled", lambda _wid, **_kw: False)
    config = SimpleNamespace(
        workspaces={
            "auto-coding": _ws(
                "Code",
                True,
                variants={
                    "bigfix": {
                        "expose_to_owui": True,
                        "name": "BigFix",
                        "tools": ["execute_python"],
                    },
                    "laguna": {"name": "Laguna"},
                },
            ),
            "plain": _ws("Plain", True),
        }
    )
    assert emit_owui_presets(config) == (3, 0, 0)
    ws_dir = tmp_path / "imports" / "openwebui" / "workspaces"
    files = sorted(path.name for path in ws_dir.glob("workspace_*.json"))
    assert files == [
        "workspace_auto_coding.json",
        "workspace_auto_coding_bigfix.json",
        "workspace_plain.json",
    ]
    bigfix = json.loads((ws_dir / "workspace_auto_coding_bigfix.json").read_text())
    assert bigfix["id"] == "auto-coding::bigfix"
    assert bigfix["name"] == "BigFix"
    assert bigfix["params"]["model"] == "auto-coding::bigfix"
    assert bigfix["params"]["system"] == "base prompt"  # inherited from the base
    assert bigfix["meta"]["toolIds"] == ["server:mcp:portal_code"]
    assert bigfix["params"]["function_calling"] == "native"
    bundle_ids = [row["id"] for row in json.loads((ws_dir / "workspaces_all.json").read_text())]
    assert "auto-coding::bigfix" in bundle_ids
    assert "auto-coding::laguna" not in bundle_ids
    assert emit_owui_presets(config) == (0, 0, 0)  # idempotent


def test_variant_without_flag_or_module_disabled_gets_no_preset(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(sync_config, "REPO", tmp_path)
    monkeypatch.setattr(modules, "owui_workspaces", lambda _mods=None: [])
    monkeypatch.setattr(modules, "is_workspace_disabled", lambda _wid, **_kw: True)
    config = SimpleNamespace(
        workspaces={
            "auto-x": _ws(
                "X",
                True,
                variants={
                    "off": {"expose_to_owui": False, "name": "Off"},
                    "hidden": {"expose_to_owui": True, "name": "Hidden"},
                },
            )
        }
    )
    created, _updated, _removed = emit_owui_presets(config)
    ws_dir = tmp_path / "imports" / "openwebui" / "workspaces"
    assert created == 1  # the base only
    assert sorted(path.name for path in ws_dir.glob("workspace_*.json")) == [
        "workspace_auto_x.json"
    ]
    bundle_ids = [row["id"] for row in json.loads((ws_dir / "workspaces_all.json").read_text())]
    assert bundle_ids == ["auto-x"]


# ── Serving path (verification — this path predates the fix) ──────────────────


def test_synthetic_variant_id_resolves_to_variant_serving_fields() -> None:
    resolved = _resolve_workspace_variant("probe", "auto-compliance", "reading")
    assert resolved == "auto-compliance::reading"
    expected_hint = (
        load_portal_config().workspaces["auto-compliance"].variants["reading"]["model_hint"]
    )
    assert WORKSPACES[resolved]["model_hint"] == expected_hint
    assert WORKSPACES[resolved]["name"] == "⚖️ Portal Compliance Reading"


def test_old_alias_addresses_the_synthetic_id() -> None:
    from portal.platform.inference.model_addressing import is_addressable, workspace_model_hint

    assert load_portal_config().aliases["compliance-reading"].to == "auto-compliance::reading"
    expected_hint = (
        load_portal_config().workspaces["auto-compliance"].variants["reading"]["model_hint"]
    )
    assert is_addressable("auto-compliance::reading")
    assert is_addressable("compliance-reading")
    assert workspace_model_hint("auto-compliance::reading") == expected_hint
