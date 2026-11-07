"""Sampling follows the model that serves, not the seat it replaced.

The seat block applies to the seat tag and to an engine alias of that tag.
A same-family persona/?model= fallback and a cross-family cascade substitute
use the served model's card (build-provider guidance, else the vendor card).
"""

from types import SimpleNamespace

import httpx
import pytest

from portal.platform.inference.router import non_streaming as ns
from portal.platform.inference.router import validation
from portal.platform.inference.router.preinject import _resolve_model_override

_SEAT = "qwen3-vl:32b-ctx8k"
_SAME_FAMILY = "qwen3-vl:32b"
_CROSS_FAMILY = "gemma4:26b-a4b-it-q4_K_M"
_ALIAS = "qwen3-vl-mlx-alias"
_WS = "test-fallback-sampling"
_KEYS = ("temperature", "top_p", "top_k", "min_p", "presence_penalty", "repeat_penalty")

_SEAT_SAMPLING = {
    "temperature": 0.2,
    "top_p": 0.5,
    "top_k": 20,
    "min_p": 0.05,
    "presence_penalty": 0.0,
    "repeat_penalty": 1.2,
}


class _Client:
    def __init__(self) -> None:
        self.bodies: list[dict] = []

    async def post(self, url: str, json: dict, timeout: object) -> httpx.Response:  # noqa: A002
        self.bodies.append(json)
        response = httpx.Response(
            200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
        )
        response.request = httpx.Request("POST", url)
        return response


def _backend(models: list[str], resolve) -> SimpleNamespace:
    return SimpleNamespace(
        id="engine",
        type="ollama",
        chat_url="http://engine/v1/chat/completions",
        models=models,
        resolve_model=resolve,
    )


def _serves(*models: str) -> SimpleNamespace:
    known = set(models)
    return _backend(list(models), lambda hint: hint if hint in known else None)


def _sampling(body: dict) -> dict:
    options = body["options"]
    return {key: options[key] for key in _KEYS if key in options}


@pytest.mark.anyio
async def test_served_model_keeps_its_own_sampling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(ns.WORKSPACES, _WS, {"model_hint": _SEAT, **_SEAT_SAMPLING})
    monkeypatch.setattr(ns, "registry", SimpleNamespace(request_timeout=5.0))
    monkeypatch.setattr(ns, "_model_supports_tools", lambda _model: False)
    alias_backend = _backend(
        [_ALIAS],
        lambda hint: _ALIAS if hint in {_SEAT, _ALIAS} else None,
    )
    monkeypatch.setattr(
        validation, "registry", SimpleNamespace(list_backends=lambda: [alias_backend])
    )
    client = _Client()
    monkeypatch.setattr(ns, "_http_client", client)
    created: list[str] = []
    try:
        seat = await ns._try_non_streaming(_serves(_SEAT), {"messages": []}, _WS, 0.0)
        same_ws = _resolve_model_override(_WS, _SAME_FAMILY)
        created.append(same_ws)
        same = await ns._try_non_streaming(_serves(_SAME_FAMILY), {"messages": []}, same_ws, 0.0)
        cross = await ns._try_non_streaming(
            _serves(_CROSS_FAMILY),
            {"messages": []},
            _WS,
            0.0,
            enforce_hint=False,
        )
        alias = await ns._try_non_streaming(alias_backend, {"messages": []}, _WS, 0.0)
    finally:
        for key in created:
            ns.WORKSPACES.pop(key, None)

    assert seat is not None and same is not None and cross is not None and alias is not None
    assert client.bodies[0]["model"] == _SEAT
    assert _sampling(client.bodies[0]) == _SEAT_SAMPLING
    assert client.bodies[1]["model"] == _SAME_FAMILY
    assert _sampling(client.bodies[1]) == {
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 20,
        "presence_penalty": 0.0,
        "repeat_penalty": 1.0,
    }
    assert client.bodies[2]["model"] == _CROSS_FAMILY
    assert _sampling(client.bodies[2]) == {"temperature": 1.0, "top_p": 0.95, "top_k": 64}
    assert client.bodies[3]["model"] == _ALIAS
    assert _sampling(client.bodies[3]) == _SEAT_SAMPLING
