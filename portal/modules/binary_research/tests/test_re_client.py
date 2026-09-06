"""RE client — URL shape + payload construction, no live server (monkeypatched)."""

from __future__ import annotations

from typing import Any, Literal

import httpx
import pytest

from portal.modules.binary_research.harness.re_client import REClient, REClientError


def test_exec_posts_correct_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class _Resp:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return {"exit_code": 0, "stdout": "ok", "stderr": ""}

    class _Client:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        def __enter__(self) -> _Client:
            return self

        def __exit__(self, *a: object) -> Literal[False]:
            return False

        def post(self, url: str, json: dict[str, Any]) -> _Resp:
            captured["url"] = url
            captured["json"] = json
            return _Resp()

    monkeypatch.setattr(httpx, "Client", _Client)

    client = REClient(base_url="http://127.0.0.1:8930")
    result = client.exec(command="readelf -h x", project="j1", timeout=60)
    assert result["stdout"] == "ok"
    assert captured["url"] == "http://127.0.0.1:8930/tools/re_exec"
    assert captured["json"]["arguments"]["command"] == "readelf -h x"
    assert captured["json"]["arguments"]["project"] == "j1"


def test_exec_wraps_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Client:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        def __enter__(self) -> _Client:
            return self

        def __exit__(self, *a: object) -> Literal[False]:
            return False

        def post(self, url: str, json: dict[str, Any]) -> dict[str, Any]:
            raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "Client", _Client)

    try:
        REClient().exec(command="x")
        raise AssertionError("should have raised")
    except REClientError as exc:
        assert "re_exec failed" in str(exc)
