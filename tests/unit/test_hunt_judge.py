from __future__ import annotations

import json
import math

import httpx
import pytest

from portal.modules.security.core.hunt.judge import (
    QUESTION,
    OpenAICompatibleClient,
    build_prompt,
    judge_cell,
)


class _Client:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def _response(alternatives):
    return {
        "model": "served-seat",
        "usage": {"prompt_tokens": 17},
        "choices": [
            {
                "logprobs": {"content": [{"top_logprobs": alternatives}]},
            }
        ],
    }


def test_judge_uses_fixed_question_and_scores_first_token_yes_no_mass():
    prompt = build_prompt([{"line": "service | x=1"}, {"line": "daemon | y=2"}])
    client = _Client(
        _response(
            [
                {"token": " YES", "logprob": math.log(0.75)},
                {"token": "no", "logprob": math.log(0.25)},
            ]
        )
    )

    result = judge_cell(
        client,
        model="security-workspace",
        evidence=[{"line": "service | x=1"}, {"line": "daemon | y=2"}],
    )

    assert prompt.endswith("EVENTS:\nservice | x=1\ndaemon | y=2")
    assert QUESTION in prompt
    call = client.calls[0]
    assert call["model"] == "security-workspace"
    assert call["temperature"] == 0
    assert call["max_tokens"] == 1
    assert call["logprobs"] is True
    assert call["top_logprobs"] > 1
    assert call["reasoning_effort"] == "none"
    assert result.p_yes == pytest.approx(0.75)
    assert result.prompt_tokens == 17
    assert result.served_model == "served-seat"
    assert result.reason is None


def test_missing_logprobs_and_transport_failures_are_unjudged():
    missing = judge_cell(
        _Client({"choices": [{"message": {"content": "yes"}}]}),
        model="seat",
        evidence=[{"line": "svc | x=1"}],
    )
    failed = judge_cell(
        _Client(error=RuntimeError()), model="seat", evidence=[{"line": "svc | x=1"}]
    )
    timeout = judge_cell(
        _Client(error=TimeoutError()), model="seat", evidence=[{"line": "svc | x=1"}]
    )

    assert missing.p_yes is None and missing.reason == "missing_logprobs"
    assert failed.p_yes is None and failed.reason == "request_failed"
    assert timeout.p_yes is None and timeout.reason == "timeout"


def test_http_error_stays_unjudged_without_a_default_score():
    request = httpx.Request("POST", "https://pipeline.invalid/v1/chat/completions")
    error = httpx.HTTPStatusError(
        "unavailable", request=request, response=httpx.Response(503, request=request)
    )

    result = judge_cell(_Client(error=error), model="workspace", evidence=[{"line": "svc | x=1"}])

    assert result.p_yes is None
    assert result.reason == "http_error"


def test_default_client_uses_supplied_endpoint_and_credentials():
    endpoint = "http://model.test/v1/chat/completions"
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"choices": []})

    client = OpenAICompatibleClient(
        endpoint,
        "configured-key",
        transport=httpx.MockTransport(handler),
    )
    client.complete(
        model="security-workspace",
        messages=[{"role": "user", "content": "question"}],
        temperature=0,
        seed=0,
        max_tokens=1,
        logprobs=True,
        top_logprobs=20,
        stream=False,
    )

    assert str(seen[0].url) == endpoint
    assert seen[0].headers["authorization"] == "Bearer configured-key"
    assert json.loads(seen[0].content)["logprobs"] is True
