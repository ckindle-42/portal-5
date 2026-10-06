"""generate_part: IR -> build123d script -> bridge build/finalize (bridge mocked)."""

from __future__ import annotations

import importlib
import sys
import types

import pytest


class _FakeServer:
    def __init__(self, *_a, **_k):
        pass

    def tool(self):
        return lambda fn: fn

    def custom_route(self, *_a, **_k):
        return lambda fn: fn


@pytest.fixture
def cad(monkeypatch):
    fake = types.ModuleType("mcp.server")
    fake.MCPServer = _FakeServer
    monkeypatch.setitem(sys.modules, "mcp.server", fake)
    sys.modules.pop("portal.modules.cad.tools.cad_render_mcp", None)
    return importlib.import_module("portal.modules.cad.tools.cad_render_mcp")


PLATE = {"base": {"type": "box", "dimensions": {"width": 40, "depth": 30, "height": 5}}}


async def test_design_error_uses_generate_scad_error_shape(cad):
    out = await cad.generate_part({"base": {"type": "box"}})
    assert out["error_category"] == "validation" and "error_detail" in out


async def test_kernel_gap_points_at_cad_build(cad):
    geometry = {**PLATE, "fillets": [{"radius": 1}], "chamfers": [{"size": 0.5}]}
    out = await cad.generate_part(geometry)
    assert out["error_category"] == "kernel_gap" and "cad_build" in out["error"]


async def test_success_builds_then_finalizes_in_one_session(cad, monkeypatch, tmp_path):
    calls = []

    async def fake_build(code, session, out_dir):
        calls.append(("build", session, "show(part, 'part')" in code))
        return {"ok": True, "validate": {"valid": True}, "measure": {"volume": 1}}

    async def fake_finalize(obj, base, session, out_dir, publish):
        calls.append(("finalize", session, obj))
        return {"ok": True, "stl_path": "/workspace/x.stl", "step_url": "u"}

    monkeypatch.setattr(cad.b123d_bridge, "cad_build", fake_build)
    monkeypatch.setattr(cad.b123d_bridge, "cad_finalize", fake_finalize)
    monkeypatch.setattr(cad, "_out_dir", lambda: tmp_path)
    out = await cad.generate_part(PLATE, "req-1")
    assert out["ok"] and out["stl_path"] == "/workspace/x.stl" and "script" in out
    assert calls[0][1] == calls[1][1] and calls[0][2] is True and calls[1][2] == "part"


async def test_failed_build_returns_script_and_error(cad, monkeypatch, tmp_path):
    async def fake_build(code, session, out_dir):
        return {"ok": False, "stage": "execute", "error": "boom"}

    monkeypatch.setattr(cad.b123d_bridge, "cad_build", fake_build)
    monkeypatch.setattr(cad, "_out_dir", lambda: tmp_path)
    out = await cad.generate_part(PLATE)
    assert out["ok"] is False and out["error"] == "boom" and "script" in out
