"""Unit tests for the build123d engine bridge (no engine required — httpx MockTransport)."""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from portal.modules.cad.tools import b123d_bridge as b


class FakeEngine:
    """Minimal stand-in for build123d-mcp's JSON-RPC surface."""

    def __init__(self, tmp: Path, responses: dict[str, Any] | None = None, sse: bool = False):
        self.tmp = tmp
        self.calls: list[tuple[str | None, str, dict[str, Any]]] = []
        self.responses = responses or {}
        self.sse = sse

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        session = request.headers.get("Mcp-Cad-Session")
        params = body.get("params", {})
        name = params.get("name", body["method"])
        args = params.get("arguments", {})
        self.calls.append((session, name, args))
        if name == "export":
            stem = Path(args["filename"])
            for ext in ("step", "stl"):
                Path(f"{stem}.{ext}").write_text("solid x\nendsolid x\n")
        if name == "script" and args.get("save_to"):
            Path(args["save_to"]).write_text("from build123d import *\n")
        content = self.responses.get(name, [{"type": "text", "text": "OK"}])
        msg = {"jsonrpc": "2.0", "id": body["id"], "result": {"content": content, "isError": False}}
        if self.sse:
            return httpx.Response(200, text=f"event: message\ndata: {json.dumps(msg)}\n\n")
        return httpx.Response(200, json=msg)


@pytest.fixture
def engine(monkeypatch, tmp_path):
    def make(**kw: Any) -> FakeEngine:
        fe = FakeEngine(tmp_path, **kw)
        transport = httpx.MockTransport(fe.handler)
        real = httpx.AsyncClient

        def client_factory(*a: Any, **k: Any) -> httpx.AsyncClient:
            k["transport"] = transport
            return real(*a, **k)

        monkeypatch.setattr(b.httpx, "AsyncClient", client_factory)
        b._live.clear()
        return fe

    return make


async def _pub(p: Path) -> str:
    return f"url://{p.name}"


def test_session_handle_sanitises_and_falls_back():
    assert b.session_handle("p5-abc/../x") == "p5-abc..x"
    assert b.session_handle("").startswith("anon-")
    assert b.session_handle(None).startswith("anon-")


def test_parse_rpc_body_accepts_json_and_sse():
    msg = {"jsonrpc": "2.0", "id": 1, "result": {}}
    assert b._parse_rpc_body(json.dumps(msg)) == msg
    assert b._parse_rpc_body(f"event: message\ndata: {json.dumps(msg)}\n\n") == msg


@pytest.mark.parametrize(
    ("texts", "is_error", "expected"),
    [
        (["OK"], False, False),
        (["Error: TypeError: Box() missing height"], False, True),
        (['{"error": "No shape in session."}'], False, True),
        (['{"volume": 1.0, "error_margin": 0}'], False, False),
        (["fine"], True, True),
    ],
)
def test_failed_detects_in_band_errors(texts, is_error, expected):
    assert b.failed({"is_error": is_error, "texts": texts, "images": []}) is expected


def test_cad_build_success_resets_first_and_validates(engine, tmp_path):
    fe = engine(
        responses={
            "validate": [{"type": "text", "text": 'Validity gate: PASS\n{"passes_gate": true}'}],
            "measure": [{"type": "text", "text": '{"volume": 10.0}'}],
        }
    )
    r = asyncio.run(b.cad_build("show(Box(1,1,1))", "s1", tmp_path))
    assert r["ok"] is True
    assert [c[1] for c in fe.calls] == ["reset", "execute", "measure", "validate"]
    assert r["measure"] == {"volume": 10.0}
    assert all(c[0] == "s1" for c in fe.calls)


def test_cad_build_error_returns_diagnosis(engine, tmp_path):
    engine(
        responses={
            "execute": [{"type": "text", "text": "Error: NameError: name 'Bx' is not defined"}],
            "last_error": [{"type": "text", "text": "line 1: Bx(1,1,1)"}],
            "repair_hints": [{"type": "text", "text": '{"hints": ["check spelling"]}'}],
        }
    )
    r = asyncio.run(b.cad_build("Bx(1,1,1)", "s1", tmp_path))
    assert r["ok"] is False and r["stage"] == "execute"
    assert (
        "NameError" in r["error"]
        and "line 1" in r["last_error"]
        and "spelling" in r["repair_hints"]
    )


def test_cad_finalize_exports_bare_stem_and_publishes(engine, tmp_path):
    png = base64.b64encode(b"\x89PNG fake").decode()
    fe = engine(
        responses={
            "validate": [{"type": "text", "text": "Validity gate: PASS\n{}"}],
            "render_view": [
                {"type": "image", "data": png, "mimeType": "image/png"},
                {"type": "text", "text": "[SEND: /tmp/x.png]"},
            ],
        }
    )
    r = asyncio.run(b.cad_finalize("", "My Part!", "s1", tmp_path, _pub))
    export_args = next(a for (_, n, a) in fe.calls if n == "export")
    assert not export_args["filename"].endswith((".step", ".stl"))
    assert export_args["format"] == "step,stl"
    assert r["ok"] is True
    assert Path(r["step_path"]).exists() and Path(r["stl_path"]).exists()
    assert {"step_url", "stl_url", "script_url", "png_url"} <= r.keys()
    assert Path(r["stl_path"]).name.startswith("My_Part_")


def test_cad_finalize_stops_on_failed_gate(engine, tmp_path):
    fe = engine(
        responses={"validate": [{"type": "text", "text": 'Validity gate: FAIL\n{"n_solids": 2}'}]}
    )
    r = asyncio.run(b.cad_finalize("", "p", "s1", tmp_path, _pub))
    assert r["ok"] is False and r["stage"] == "validate"
    assert "export" not in [c[1] for c in fe.calls]


def test_lru_eviction_destroys_oldest_handle(engine, tmp_path, monkeypatch):
    monkeypatch.setattr(b, "ENGINE_MAX_SESSIONS", 2)
    fe = engine()
    for h in ("a", "b", "c"):
        asyncio.run(b.engine_call("measure", {}, h))
    destroys = [s for (s, n, _) in fe.calls if n == "destroy_session"]
    assert destroys == ["a"]
    assert set(b._live) == {"b", "c"}


def test_sse_responses_are_parsed(engine, tmp_path):
    engine(sse=True, responses={"measure": [{"type": "text", "text": '{"volume": 3.0}'}]})
    r = asyncio.run(b.cad_measure("", "s1", tmp_path))
    assert r == {"ok": True, "measure": {"volume": 3.0}}


def test_dispatch_unknown_tool(tmp_path):
    r = asyncio.run(b.dispatch("cad_nope", {}, "rid", tmp_path, _pub))
    assert r["ok"] is False and "unknown" in r["error"]


def test_engine_unreachable_is_an_error_not_a_raise(monkeypatch, tmp_path):
    monkeypatch.setattr(b, "ENGINE_URL", "http://127.0.0.1:1/mcp")
    b._live.clear()
    r = asyncio.run(b.engine_call("measure", {}, "s1"))
    assert r["is_error"] is True and "unreachable" in r["texts"][0]
