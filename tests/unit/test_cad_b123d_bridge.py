"""Unit tests for the build123d engine bridge (no engine required — httpx MockTransport)."""

from __future__ import annotations

import json

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
