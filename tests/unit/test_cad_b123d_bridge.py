"""Unit tests for the build123d engine bridge (no engine required — httpx MockTransport)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from portal.modules.cad.tools import b123d_bridge as b


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


_BRACKET = """
from build123d import *

base_plate = Box(60, 40, 5, align=(Align.MIN, Align.MIN, Align.MIN))
vertical_wall = Pos(0, 35, 5) * Box(60, 5, 25)
l_bracket = base_plate + vertical_wall
show(l_bracket)
"""

_CUBE = """
from build123d import *

cube = Box(20, 20, 20)
show(cube)
"""

_ALIGNED = """
from build123d import *

part = Box(60, 40, 5, align=(Align.MIN, Align.MIN, Align.MIN))
wall = Pos(0, 35, 5) * Box(60, 5, 25, align=(Align.MIN, Align.MIN, Align.MIN))
show(part + wall, "part")
"""


def test_align_contract_rejects_center_default_and_accepts_explicit_align() -> None:
    bracket = b.align_contract_error(_BRACKET)
    cube = b.align_contract_error(_CUBE)
    assert bracket is not None and "Box() line 5" in bracket
    assert cube is not None and "Box() line 4" in cube
    assert b.align_contract_error(_ALIGNED) is None
    assert b.align_contract_error("this is not python (") is None


async def test_cad_build_resets_and_refuses_unaligned_solid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def fake_engine(name: str, arguments: dict, session: str, client: object = None) -> dict:
        del arguments, session, client
        calls.append(name)
        return {"is_error": False, "texts": ["ok"], "images": []}

    monkeypatch.setattr(b, "engine_call", fake_engine)
    result = await b.cad_build(_BRACKET, "sess", Path("/tmp"))
    assert result["ok"] is False and result["stage"] == "align"
    assert calls == ["reset"]


async def test_cad_execute_refuses_unaligned_solid_without_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def fake_engine(name: str, arguments: dict, session: str, client: object = None) -> dict:
        del arguments, session, client
        calls.append(name)
        return {"is_error": False, "texts": ["ok"], "images": []}

    monkeypatch.setattr(b, "engine_call", fake_engine)
    result = await b.cad_execute(_CUBE, "sess", Path("/tmp"))
    assert result["ok"] is False and result["stage"] == "align"
    assert calls == []
