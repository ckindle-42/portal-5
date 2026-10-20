"""A variant's own module gates that variant; the engine stays up."""

from __future__ import annotations

import itertools
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from portal.platform.inference.cli.module_services import up_plan
from portal.platform.inference.config import (
    ModuleToggle,
    PortalConfig,
    WorkspaceSpec,
    engine_tools,
    load_portal_config,
    variant_module,
)
from portal.platform.wiki.adapters.modules import (
    is_workspace_disabled,
    owui_workspaces,
    preset_ids,
    router_labels,
    served_ids,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "variant_module_gate.yaml"
OPTIONAL = ("image", "video", "music")
VARIANT_TOOLS = {
    "image": "generate_image",
    "video": "generate_video",
    "music": "generate_music",
}
VARIANT_SERVICES = {
    "image": "mcp-image",
    "video": "mcp-video",
    "music": "mcp-music",
}


@pytest.fixture
def cfg(monkeypatch: pytest.MonkeyPatch) -> PortalConfig:
    monkeypatch.delenv("PORTAL_ENABLE_EVAL", raising=False)
    monkeypatch.delenv("PORTAL_BENCH_WORKSPACES", raising=False)
    return load_portal_config(FIXTURE, _force_reload=True)


def _expect(on: set[str]) -> set[str]:
    return {"auto-media", "auto-media::speech"} | {f"auto-media::{name}" for name in on}


@pytest.mark.parametrize("flags", list(itertools.product([False, True], repeat=3)))
def test_each_toggle_flips_only_its_variant(cfg: PortalConfig, flags: tuple[bool, ...]) -> None:
    on = {name for name, flag in zip(OPTIONAL, flags, strict=True) if flag}
    mods = sorted({"media"} | on)
    offered = served_ids(cfg, mods)
    assert offered == _expect(on)
    assert router_labels(cfg, mods) == offered
    assert preset_ids(cfg, mods) == {"auto-media"}  # variants never seed presets (R7)

    tools = engine_tools(cfg.workspaces["auto-media"], set(mods))
    assert tools[:2] == ["speak", "transcribe"]
    for name, tool in VARIANT_TOOLS.items():
        assert (tool in tools) is (name in on)

    start, stop = up_plan(cfg, enabled=mods)
    start_ids = {ref.ident for ref in start}
    stop_ids = {ref.ident for ref in stop}
    assert start_ids == {"mcp-media"} | {VARIANT_SERVICES[name] for name in on}
    assert stop_ids == {VARIANT_SERVICES[name] for name in OPTIONAL if name not in on}
    assert "mcp-media" not in stop_ids
    assert "auto-media" in offered


def test_disabled_variants_are_not_served_on_the_fixture(cfg: PortalConfig) -> None:
    assert is_workspace_disabled("auto-media::image", config=cfg)
    assert is_workspace_disabled("auto-media::video", config=cfg)
    assert is_workspace_disabled("auto-media::music", config=cfg)
    assert not is_workspace_disabled("auto-media::speech", config=cfg)
    assert not is_workspace_disabled("auto-media", config=cfg)
    assert not is_workspace_disabled("auto-media::missing", config=cfg)


def test_enabling_image_brings_only_that_variant_back(cfg: PortalConfig) -> None:
    modules = {**cfg.modules, "image": ModuleToggle(enabled=True)}
    flipped = cfg.model_copy(update={"modules": modules})
    assert "auto-media::image" in served_ids(flipped)
    assert "auto-media::video" not in served_ids(flipped)
    assert "auto-media::music" not in served_ids(flipped)
    assert not is_workspace_disabled("auto-media::image", config=flipped)
    assert is_workspace_disabled("auto-media::video", config=flipped)
    assert not is_workspace_disabled("auto-media", config=flipped)


def test_variant_without_module_inherits_and_does_not_add_tools() -> None:
    cfg = PortalConfig.model_validate(
        {
            "workspaces": {
                "auto-media": {
                    "name": "Media",
                    "description": "inherits",
                    "module": "media",
                    "tools": ["speak"],
                    "variants": {"plain": {"tools": ["note_tool"]}},
                }
            },
            "mcp_fleet": [],
            "modules": {"media": {"enabled": True}},
        }
    )
    spec = cfg.workspaces["auto-media"]
    assert variant_module(spec.module, spec.variants["plain"]) == "media"
    assert served_ids(cfg, ["media"]) == {"auto-media", "auto-media::plain"}
    assert "note_tool" not in engine_tools(spec, {"media"})
    assert not is_workspace_disabled("auto-media::missing", config=cfg, mods=["media"])
    assert is_workspace_disabled("auto-media", config=cfg, mods=[])
    assert is_workspace_disabled("auto-media::plain", config=cfg, mods=[])
    assert served_ids(cfg, []) == set()


def test_unknown_variant_module_is_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown module"):
        WorkspaceSpec.model_validate(
            {
                "name": "Media",
                "description": "bad variant module",
                "module": "media",
                "variants": {"bad": {"module": "not-a-module"}},
            }
        )


def test_disabled_variant_request_is_module_disabled_404(
    cfg: PortalConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "portal.platform.inference.config.load_portal_config", lambda *_a, **_k: cfg
    )
    from portal.platform.inference.router.handlers import _reject_disabled_workspace

    with pytest.raises(HTTPException) as caught:
        _reject_disabled_workspace("auto-media::image")
    assert caught.value.status_code == 404
    assert caught.value.detail == (
        "Workspace 'auto-media::image' is disabled (module not enabled)."
    )
    _reject_disabled_workspace("auto-media")
    _reject_disabled_workspace("auto-media::speech")


def test_resolve_does_not_cache_a_disabled_variant(
    cfg: PortalConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "portal.platform.inference.config.load_portal_config", lambda *_a, **_k: cfg
    )
    from portal.platform.inference.router.preinject import _resolve_workspace_variant
    from portal.platform.inference.router.workspaces import WORKSPACES

    speech = "auto-media::speech"
    image = "auto-media::image"
    try:
        assert _resolve_workspace_variant("auto-media", "auto-media", "image") == "auto-media"
        assert image not in WORKSPACES
        assert _resolve_workspace_variant("auto-media", "auto-media", "speech") == speech
        assert speech in WORKSPACES
    finally:
        synthetic = getattr(WORKSPACES, "_synthetic", {})
        synthetic.pop(speech, None)
        synthetic.pop(image, None)


def test_router_offer_drops_only_the_disabled_variant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "portal.platform.wiki.adapters.modules.is_workspace_disabled",
        lambda workspace_id, mods=None, config=None: workspace_id.endswith("::image"),
    )
    from portal.platform.inference.router.routing import _without_disabled_variant

    assert _without_disabled_variant("auto-media::image") == "auto-media"
    assert _without_disabled_variant("auto-media::speech") == "auto-media::speech"
    assert _without_disabled_variant("auto-media") == "auto-media"


def test_production_catalog_keeps_base_workspaces_and_math(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PORTAL_ENABLE_EVAL", raising=False)
    monkeypatch.delenv("PORTAL_BENCH_WORKSPACES", raising=False)
    from portal.platform.inference.config import get_workspace_dict

    cfg = load_portal_config(_force_reload=True)
    bases = {wid for wid in served_ids(cfg) if "::" not in wid}
    assert set(get_workspace_dict(cfg)) == bases
    assert "auto-reasoning::math" in served_ids(cfg)
    assert "auto-image" not in served_ids(cfg)

    hidden = set(owui_workspaces() or ())
    exposed = {
        ws_id
        for ws_id, spec in cfg.workspaces.items()
        if spec.expose_to_owui and spec.module != "eval" and ws_id not in hidden
    }
    assert preset_ids(cfg) == exposed  # variants are never seeded as presets (R7)
