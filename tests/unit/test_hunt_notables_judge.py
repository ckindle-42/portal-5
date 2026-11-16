from __future__ import annotations

import json
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


def test_opt_in_annotation_prompt_asks_for_a_short_reason_and_room_for_it(tmp_path):
    cache_path = tmp_path / "judge.json"
    judge_all(
        [_notable()],
        client=_Client(_response()),
        model="seat",
        cache_path=cache_path,
    )
    client = _Client(_response())
    judge_all(
        [_notable()],
        client=client,
        model="seat",
        cache_path=cache_path,
        explain=True,
    )

    request = client.calls[0]
    assert len(client.calls) == 1
    assert "short reason" in request["messages"][0]["content"]
    assert request["max_tokens"] == 40


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


def _wrapped_response() -> dict[str, object]:
    return {
        "model": "gemma-seat",
        "usage": {"prompt_tokens": 300},
        "choices": [
            {
                "message": {"content": "**yes**"},
                "logprobs": {
                    "content": [
                        {
                            "token": "**",
                            "top_logprobs": [
                                {"token": "**", "logprob": math.log(0.98)},
                                {"token": "yes", "logprob": math.log(0.01)},
                                {"token": "no", "logprob": math.log(0.01)},
                            ],
                        },
                        {
                            "token": "yes",
                            "top_logprobs": [
                                {"token": "yes", "logprob": math.log(0.8)},
                                {"token": "no", "logprob": math.log(0.2)},
                            ],
                        },
                    ]
                },
            }
        ],
    }


def test_budget_comes_from_the_measured_call_rate_and_the_deadline(tmp_path, monkeypatch):
    from portal.modules.security.core.hunt.notables import judge_notables as module

    clock = [0.0]

    class _TimedClient:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, **request: object) -> dict[str, object]:
            self.calls += 1
            clock[0] += 1.0
            return _wrapped_response()

    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    client = _TimedClient()
    notables = [_notable(f"k{index}") for index in range(12)]
    judged, receipt = judge_all(
        notables,
        client=client,
        model="seat",
        cache_path=tmp_path / "j.json",
        deadline_seconds=10.0,
        probe_calls=2,
    )
    basis = receipt["budget_basis"]
    assert basis["source"] == "measured_rate"
    assert basis["probe_calls"] == 2
    assert basis["seconds_per_call"] == pytest.approx(1.0)
    assert basis["derived_budget"] == 10
    assert receipt["request_budget"] == 10
    assert receipt["requests"] == 10
    assert receipt["unasked"] == 2
    assert sum(1 for item in judged if item["p_yes"] is not None) == 10


def test_explicit_request_budget_is_still_honored(tmp_path):
    client = _Client(_wrapped_response())
    _judged, receipt = judge_all(
        [_notable(f"k{index}") for index in range(5)],
        client=client,
        model="seat",
        cache_path=tmp_path / "j.json",
        request_budget=1,
    )
    assert receipt["request_budget"] == 1
    assert receipt["budget_basis"]["source"] == "explicit"
    assert receipt["requests"] == 1


def test_cache_entries_from_the_old_parse_are_rejudged(tmp_path):
    cache_path = tmp_path / "j.json"
    cache_path.write_text(
        json.dumps({"k1": {"p_yes": 0.99, "served_model": "old", "seconds": 1.0}})
    )
    client = _Client(_wrapped_response())
    judged, receipt = judge_all([_notable()], client=client, model="seat", cache_path=cache_path)
    assert receipt["requests"] == 1
    assert receipt["cached"] == 0
    assert judged[0]["p_yes"] == pytest.approx(0.8, abs=0.01)


def test_cache_and_judge_block_record_the_raw_answer_and_position(tmp_path):
    cache_path = tmp_path / "j.json"
    client = _Client(_wrapped_response())
    judged, _receipt = judge_all([_notable()], client=client, model="seat", cache_path=cache_path)
    assert judged[0]["judge"]["answer"] == "**yes**"
    assert judged[0]["judge"]["decision_index"] == 1
    stored = json.loads(cache_path.read_text())["k1"]
    assert stored["v"] == 2
    assert stored["answer"] == "**yes**"
    assert stored["decision_index"] == 1
    again, receipt = judge_all([_notable()], client=client, model="seat", cache_path=cache_path)
    assert receipt["cached"] == 1
    assert again[0]["judge"]["answer"] == "**yes**"
