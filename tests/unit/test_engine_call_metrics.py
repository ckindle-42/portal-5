"""Engine calls outside the main dispatchers are counted once and labelled internal."""

from __future__ import annotations

import json
import typing
from types import SimpleNamespace

import pytest

import portal.platform.inference.router.council as council
import portal.platform.inference.router.lifespan as lifespan
import portal.platform.inference.router.non_streaming as ns
import portal.platform.inference.router.routing as routing
import portal.platform.inference.tool_preselect.preselector as preselector
from portal.platform.inference.router.metrics import _REGISTRY
from portal.platform.inference.router.power import (
    INTERNAL_ROUTER_WORKSPACE,
    INTERNAL_WARMUP_WORKSPACE,
)


def _sample(metric: str, **labels: str) -> float:
    return _REGISTRY.get_sample_value(metric, labels) or 0.0


class _Backend:
    id = "test-backend"
    type = "ollama"
    url = "http://test"

    def __init__(self, models: list[str]) -> None:
        self.models = models

    @property
    def chat_url(self) -> str:
        return f"{self.url}/v1/chat/completions"


class _Registry:
    def __init__(self, models: list[str]) -> None:
        self.backend = _Backend(models)

    def get_backend_candidates(self, _workspace_id: str) -> list[_Backend]:
        return [self.backend]

    def list_healthy_backends(self) -> list[_Backend]:
        return [self.backend]


class _JSONResponse:
    status_code = 200

    def __init__(self, data: typing.Any) -> None:
        self._data = data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> typing.Any:
        return self._data


class _PostClient:
    def __init__(self, data: typing.Any) -> None:
        self.data = data
        self.calls: list[dict[str, typing.Any]] = []

    async def post(self, _url: str, *, json: dict[str, typing.Any]) -> _JSONResponse:
        self.calls.append(json)
        return _JSONResponse(self.data)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["reviewer", "synthesizer", "decompose"])
async def test_council_engine_call_records_usage_once(
    monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    model, workspace = f"council-{role}-model", "auto-council"
    data = {
        "model": model,
        "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7},
    }
    monkeypatch.setattr(council, "_http_client", _PostClient(data))
    before_requests = _sample("portal_requests_by_model_total", model=model, workspace=workspace)
    before_input = _sample("portal_input_tokens_total", model=model, workspace=workspace)
    before_output = _sample("portal_output_tokens_total", model=model, workspace=workspace)

    call = await council._post_model(
        model=model,
        system="system",
        user="user",
        max_tokens=16,
        sampling={},
        think=False,
        workspace_id=workspace,
        registry=_Registry([model]),
        role=role,
    )

    assert call.called
    assert (
        _sample("portal_requests_by_model_total", model=model, workspace=workspace)
        - (before_requests)
        == 1
    )
    assert (
        _sample("portal_input_tokens_total", model=model, workspace=workspace) - (before_input)
        == 11
    )
    assert (
        _sample("portal_output_tokens_total", model=model, workspace=workspace) - (before_output)
        == 7
    )


@pytest.mark.asyncio
async def test_council_engine_call_without_usage_counts_the_call_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model, workspace = "council-no-usage-model", "auto-council"
    data = {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
    monkeypatch.setattr(council, "_http_client", _PostClient(data))
    before_requests = _sample("portal_requests_by_model_total", model=model, workspace=workspace)
    before_output = _sample("portal_output_tokens_total", model=model, workspace=workspace)

    call = await council._post_model(
        model=model,
        system="system",
        user="user",
        max_tokens=16,
        sampling={},
        think=False,
        workspace_id=workspace,
        registry=_Registry([model]),
        role="reviewer",
    )

    assert call.called
    assert (
        _sample("portal_requests_by_model_total", model=model, workspace=workspace)
        - (before_requests)
        == 1
    )
    assert _sample("portal_output_tokens_total", model=model, workspace=workspace) == before_output


class _HopResponse:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def raise_for_status(self) -> None:
        return None

    async def aiter_lines(self) -> typing.AsyncIterator[str]:
        for line in self._lines:
            yield line


class _HopCtx:
    def __init__(self, response: _HopResponse) -> None:
        self._response = response

    async def __aenter__(self) -> _HopResponse:
        return self._response

    async def __aexit__(self, *_: typing.Any) -> None:
        return None


class _HopClient:
    def __init__(self, responses: list[_HopResponse]) -> None:
        self._responses = list(responses)

    def stream(self, *_args: typing.Any, **_kwargs: typing.Any) -> _HopCtx:
        return _HopCtx(self._responses.pop(0))


def _hop_lines(text: str, prompt_tokens: int, completion_tokens: int) -> list[str]:
    content = json.dumps(
        {"choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]}
    )
    usage = json.dumps(
        {
            "choices": [],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
        }
    )
    return [f"data: {content}", f"data: {usage}", "data: [DONE]"]


@pytest.mark.asyncio
async def test_non_streaming_chain_counts_each_hop_once(monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = "auto-purpleteam"
    hop_a, hop_b = "chain-hop-a", "chain-hop-b"
    client = _HopClient(
        [
            _HopResponse(_hop_lines("blue", 3, 4)),
            _HopResponse(_hop_lines("detect", 5, 6)),
        ]
    )
    monkeypatch.setattr(ns, "_http_client", client)
    monkeypatch.setattr(ns, "registry", None)
    primary = {
        "model": "chain-primary",
        "choices": [{"message": {"role": "assistant", "content": "red"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 2},
    }
    # The primary was already recorded by _apply_non_stream_response.
    from portal.platform.inference.router.power import _record_engine_call

    _record_engine_call("chain-primary", workspace, primary)
    before_primary = _sample(
        "portal_requests_by_model_total", model="chain-primary", workspace=workspace
    )
    before_a = _sample("portal_requests_by_model_total", model=hop_a, workspace=workspace)
    before_b = _sample("portal_requests_by_model_total", model=hop_b, workspace=workspace)

    await ns._run_non_streaming_chain(
        primary_text="red",
        chain=[
            {"model": hop_a, "label": "BLUE", "system": "s", "user_template": "{hop_0}"},
            {"model": hop_b, "label": "DETECT", "system": "s", "user_template": "{hop_0}"},
        ],
        backend=SimpleNamespace(id="test-backend", chat_url="http://test/v1/chat/completions"),
        body={},
        workspace_id=workspace,
        primary_data=primary,
        primary_model="chain-primary",
    )

    assert (
        _sample("portal_requests_by_model_total", model="chain-primary", workspace=workspace)
        == before_primary
    ), "the primary must not be recorded a second time by the chain"
    assert (
        _sample("portal_requests_by_model_total", model=hop_a, workspace=workspace) - (before_a)
        == 1
    )
    assert (
        _sample("portal_requests_by_model_total", model=hop_b, workspace=workspace) - (before_b)
        == 1
    )


class _RouterResponse:
    status_code = 200

    def __init__(self, data: dict[str, typing.Any]) -> None:
        self._data = data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, typing.Any]:
        return self._data


class _RouterClient:
    def __init__(self, data: dict[str, typing.Any]) -> None:
        self.data = data

    async def post(self, _url: str, *, json: dict[str, typing.Any]) -> _RouterResponse:
        return _RouterResponse(self.data)


@pytest.mark.asyncio
async def test_intent_router_call_is_labelled_internal(monkeypatch: pytest.MonkeyPatch) -> None:
    model = routing._LLM_ROUTER_MODEL
    decision = json.dumps({"workspace": "auto-coding", "confidence": 0.9})
    monkeypatch.setattr(
        routing,
        "_http_client",
        _RouterClient({"model": model, "response": decision, "eval_count": 5}),
    )
    monkeypatch.setattr(routing, "_LLM_ROUTER_ENABLED", True)
    monkeypatch.setattr(routing._load_guard, "GUARD", None)
    before = _sample(
        "portal_requests_by_model_total", model=model, workspace=INTERNAL_ROUTER_WORKSPACE
    )
    before_tokens = _sample(
        "portal_output_tokens_total", model=model, workspace=INTERNAL_ROUTER_WORKSPACE
    )

    workspace = await routing._route_with_llm([{"role": "user", "content": "hello there"}])

    assert workspace is not None
    assert (
        _sample("portal_requests_by_model_total", model=model, workspace=INTERNAL_ROUTER_WORKSPACE)
        - (before)
        == 1
    )
    assert (
        _sample("portal_output_tokens_total", model=model, workspace=INTERNAL_ROUTER_WORKSPACE)
        - (before_tokens)
        == 5
    )


@pytest.mark.asyncio
async def test_router_warmup_is_labelled_internal(monkeypatch: pytest.MonkeyPatch) -> None:
    model = routing._LLM_ROUTER_MODEL
    monkeypatch.setattr(routing, "_http_client", _RouterClient({"model": model, "eval_count": 1}))
    monkeypatch.setattr(routing._load_guard, "GUARD", None)
    before = _sample(
        "portal_requests_by_model_total", model=model, workspace=INTERNAL_WARMUP_WORKSPACE
    )

    assert await routing.warm_router_model() == 200

    assert (
        _sample("portal_requests_by_model_total", model=model, workspace=INTERNAL_WARMUP_WORKSPACE)
        - (before)
        == 1
    )


@pytest.mark.asyncio
async def test_auto_model_warmup_is_labelled_internal(monkeypatch: pytest.MonkeyPatch) -> None:
    model = "warmup-model"
    client = _RouterClient(
        {"model": model, "prompt_eval_count": 2, "eval_count": 1, "eval_duration": 1_000_000}
    )
    monkeypatch.setattr(lifespan, "_http_client", client)
    monkeypatch.setattr(lifespan._load_guard_mod, "GUARD", None)
    registry = SimpleNamespace(
        get_backend_for_workspace=lambda _workspace: SimpleNamespace(
            id="warm", type="ollama", url="http://warm", models=[model]
        )
    )
    before = _sample(
        "portal_requests_by_model_total", model=model, workspace=INTERNAL_WARMUP_WORKSPACE
    )

    await lifespan._warmup_auto_model(registry)

    assert (
        _sample("portal_requests_by_model_total", model=model, workspace=INTERNAL_WARMUP_WORKSPACE)
        - (before)
        == 1
    )


@pytest.mark.asyncio
async def test_internal_traffic_stays_out_of_daily_digest() -> None:
    from portal.platform.inference.router import state
    from portal.platform.inference.router.power import _record_engine_call

    model = "digest-internal-model"
    before_in = state._total_input_tokens
    before_out = state._total_output_tokens
    before_requests = _sample(
        "portal_requests_by_model_total", model=model, workspace=INTERNAL_ROUTER_WORKSPACE
    )

    _record_engine_call(
        model,
        INTERNAL_ROUTER_WORKSPACE,
        {"usage": {"prompt_tokens": 3, "completion_tokens": 4}},
    )

    assert (
        _sample("portal_requests_by_model_total", model=model, workspace=INTERNAL_ROUTER_WORKSPACE)
        - (before_requests)
        == 1
    )
    assert state._total_input_tokens == before_in
    assert state._total_output_tokens == before_out
    assert model not in state._req_count_by_model


@pytest.mark.asyncio
async def test_tool_preselect_is_labelled_internal(monkeypatch: pytest.MonkeyPatch) -> None:
    model = "preselect-model"
    monkeypatch.setenv("PORTAL5_TOOL_PRESELECT_MODEL", model)
    monkeypatch.setattr(preselector, "_http_client", _PostClient({"response": "1, 2, 3"}))
    monkeypatch.setattr(preselector, "resolve_workspace_config", lambda *_a: SimpleNamespace(k=3))
    import portal.platform.inference.load_guard as load_guard

    monkeypatch.setattr(load_guard, "GUARD", None)
    before = _sample("portal_requests_by_model_total", model=model, workspace="internal-preselect")

    subset, outcome = await preselector.preselect(
        {"tool_a", "tool_b", "tool_c", "tool_d", "tool_e", "tool_f"},
        "find the right tool",
        "auto",
        {"tool_preselect": {"enabled": True, "k": 3}},
    )

    assert outcome.reason == "ok"
    assert subset
    assert (
        _sample("portal_requests_by_model_total", model=model, workspace="internal-preselect")
        - (before)
        == 1
    )
