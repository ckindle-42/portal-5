from __future__ import annotations

import importlib
import sys
import types

import pytest


class _FakeServer:
    def __init__(self, *_args, **_kwargs):
        pass

    def tool(self):
        return lambda function: function

    def custom_route(self, *_args, **_kwargs):
        return lambda function: function


@pytest.fixture
def cad_module(monkeypatch):
    fake = types.ModuleType("mcp.server")
    fake.MCPServer = _FakeServer
    monkeypatch.setitem(sys.modules, "mcp.server", fake)
    sys.modules.pop("portal.modules.cad.tools.cad_render_mcp", None)
    return importlib.import_module("portal.modules.cad.tools.cad_render_mcp")


def _clean_validation():
    return {
        "watertight": True,
        "manifold_ok": True,
        "printable": True,
        "printability": [],
        "problems": [],
        "bounding_box": {"x": 10, "y": 10, "z": 10},
    }


@pytest.mark.asyncio
async def test_clean_geometry_succeeds_once(cad_module, monkeypatch, tmp_path):
    monkeypatch.setattr(cad_module, "_out_dir", lambda: tmp_path)
    monkeypatch.setattr(cad_module, "_compile_scad", lambda *_args, **_kwargs: (True, "", False))
    monkeypatch.setattr(cad_module, "validate_mesh", lambda *_args: _clean_validation())
    monkeypatch.setattr(cad_module, "_render_mesh_to_png", lambda *_args, **_kwargs: "smoke")
    result = await cad_module.generate_scad(
        {"base": {"type": "box", "dimensions": {"width": 10, "depth": 10, "height": 10}}}
    )
    assert result["attempts"] == 1
    assert result["retry_log"] == []


@pytest.mark.asyncio
async def test_repairable_validation_failure_enters_loop(cad_module, monkeypatch, tmp_path):
    monkeypatch.setattr(cad_module, "_out_dir", lambda: tmp_path)
    monkeypatch.setattr(cad_module, "_compile_scad", lambda *_args, **_kwargs: (True, "", False))
    monkeypatch.setattr(cad_module, "validate_mesh", lambda *_args: _clean_validation())
    monkeypatch.setattr(cad_module, "_render_mesh_to_png", lambda *_args, **_kwargs: "smoke")
    result = await cad_module.generate_scad(
        {
            "base": {"type": "box", "dimensions": {"width": 10, "depth": 10, "height": 10}},
            "hole": {
                "diameter": 2,
                "face": "top",
                "offset_from": "center",
                "offset_x": 0,
                "offset_y": 0,
            },
        }
    )
    assert result["attempts"] == 2
    assert result["validation"]["printable"] is True
    assert result["retry_log"][0]["stage"] == "validation"


@pytest.mark.asyncio
async def test_intent_error_is_not_repaired(cad_module):
    result = await cad_module.generate_scad(
        {
            "base": {"type": "box", "dimensions": {"width": 10, "depth": 10, "height": 2}},
            "holes": [
                {
                    "diameter": 20,
                    "face": "top",
                    "offset_from": "center",
                    "offset_x": 0,
                    "offset_y": 0,
                }
            ],
        },
        max_retries=9,
    )
    assert result["attempts"] == 1
    assert result["error_category"] == "intent_error"
    assert "exceeds" in result["error_detail"]["suggestion"]


@pytest.mark.asyncio
async def test_validation_loop_stops_at_max_retries(cad_module):
    result = await cad_module.generate_scad(
        {
            "base": {"type": "box", "dimensions": {"width": 10, "depth": 10, "height": 10}},
            "features": [
                {
                    "type": "hole",
                    "diameter": 2,
                    "face": "top_of_standoff_1",
                    "offset_from": "center",
                    "offset_x": 0,
                    "offset_y": 0,
                }
            ],
        },
        max_retries=1,
    )
    assert result["attempts"] == 2
    assert len(result["retry_log"]) == 2
