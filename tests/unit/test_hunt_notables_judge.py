from __future__ import annotations

import math

import httpx
import pytest

from portal.modules.security.core.hunt.notables.judge_notables import (
    JUDGE_PROMPT_CHARS,
    judge_all,
    notable_prompt,
)


class _Client:
    def __init__(self, response=None, error=None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, object]] = []

    def complete(self, **request: object) -> dict[str, object]:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return dict(self.response or {})


def _response() -> dict[str, object]:
    return {
        "model": "seat",
        "usage": {"prompt_tokens": 91},
        "choices": [
            {
                "logprobs": {
                    "content": [
                        {
                            "top_logprobs": [
                                {"token": " yes", "logprob": math.log(0.8)},
                                {"token": "no", "logprob": math.log(0.2)},
                            ]
                        }
                    ]
                }
            }
        ],
    }


def _notable(key: str = "k1") -> dict[str, object]:
    return {
        "notable_id": key,
        "generator": "peer_rare",
        "basis": "behaviour_share",
        "what": "actor bob did cmd.exe to a shape",
        "entities": [{"role": "actor", "value": "bob"}],
        "source_id": "ix:st",
        "why": "on 1/20 hosts",
        "content_key": key,
        "evidence": [{"line": f"example {index}"} for index in range(5)],
    }


def test_notable_prompt_is_compact_and_carries_the_statement_and_examples():
    prompt = notable_prompt(_notable())
    assert "actor bob did cmd.exe" in prompt
    assert "actor=bob" in prompt
    assert "example 0" in prompt
    assert "example 2" in prompt
    assert "example 3" not in prompt
    assert len(prompt) <= JUDGE_PROMPT_CHARS


def test_judge_scores_first_token_mass_once_and_caches_by_content_key(tmp_path):
    cache_path = tmp_path / "judge.json"
    client = _Client(_response())
    judged, receipt = judge_all([_notable()], client=client, model="seat", cache_path=cache_path)
    assert judged[0]["p_yes"] == pytest.approx(0.8, abs=0.01)
    assert judged[0]["judge"]["served_model"] == "seat"
    assert receipt["requests"] == 1
    assert receipt["judged"] == 1
    second, receipt = judge_all([_notable()], client=client, model="seat", cache_path=cache_path)
    assert second[0]["p_yes"] == pytest.approx(0.8, abs=0.01)
    assert receipt["requests"] == 0
    assert receipt["cached"] == 1
    assert len(client.calls) == 1


def test_transport_failure_is_unjudged_with_a_reason_not_a_default(tmp_path):
    client = _Client(error=httpx.ConnectError("down"))
    judged, receipt = judge_all(
        [_notable()], client=client, model="seat", cache_path=tmp_path / "j.json"
    )
    assert judged[0]["p_yes"] is None
    assert judged[0]["judge"]["reason"] == "request_failed"
    assert receipt["unjudged"] == 1
    assert receipt["unjudged_reasons"] == {"request_failed": 1}


def test_a_failed_judgement_is_not_cached_and_is_retried(tmp_path):
    cache_path = tmp_path / "j.json"
    failed = _Client(error=httpx.ConnectError("down"))
    judge_all([_notable()], client=failed, model="seat", cache_path=cache_path)
    healthy = _Client(_response())
    judged, receipt = judge_all([_notable()], client=healthy, model="seat", cache_path=cache_path)
    assert judged[0]["p_yes"] == pytest.approx(0.8, abs=0.01)
    assert receipt["requests"] == 1
    assert receipt["cached"] == 0
    assert len(healthy.calls) == 1
