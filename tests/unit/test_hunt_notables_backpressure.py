from __future__ import annotations

import json
import math

import httpx
import pytest

from portal.modules.security.core.hunt.judge import (
    BackpressureClient,
    ThrottleBudgetExceededError,
    judge_cell,
)
from portal.modules.security.core.hunt.notables.__main__ import main
from portal.modules.security.core.hunt.notables.cards import (
    CardCache,
    ModelAnswer,
    SourceCard,
    answer_cards,
    ask_model,
    assemble_cards,
    prepare_cards,
)
from portal.modules.security.core.hunt.notables.judge_notables import judge_all
from portal.modules.security.core.hunt.notables.pipeline import (
    BackendPinnedClient,
    PreflightRejected,
    preflight,
)
from portal.modules.security.core.hunt.notables.run import (
    _card_failure_counts,
    _check_http_error_rate,
)
from portal.modules.security.core.hunt.notables.sample import SourceFacts


def _throttled(retry_after: float | None = None) -> httpx.HTTPStatusError:
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else {}
    request = httpx.Request("POST", "http://pipeline.invalid/v1/chat/completions")
    response = httpx.Response(429, headers=headers, request=request)
    return httpx.HTTPStatusError("throttled", request=request, response=response)


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class _Inner:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls = 0
        self.requests: list[dict[str, object]] = []

    def complete(self, **request: object) -> dict[str, object]:
        self.calls += 1
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return dict(outcome)  # type: ignore[arg-type]


def _http_error(status: int, detail: str) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://pipeline.invalid/v1/chat/completions")
    response = httpx.Response(status, text=detail, request=request)
    return httpx.HTTPStatusError("pipeline error", request=request, response=response)


def test_back_pressure_waits_and_retries_instead_of_failing():
    clock = _Clock()
    inner = _Inner([_throttled(2), _throttled(), {"ok": True}])
    client = BackpressureClient(inner, budget_seconds=30, sleep=clock.sleep, clock=clock)
    assert client.complete(model="m") == {"ok": True}
    assert clock.sleeps == [2.0, 2.0]
    assert client.stats()["throttles"] == 2
    assert client.stats()["retries"] == 2
    assert client.stats()["exhausted"] is False


def test_back_pressure_stops_only_when_the_model_work_budget_is_spent():
    clock = _Clock()
    inner = _Inner([_throttled(30)] * 10)
    client = BackpressureClient(inner, budget_seconds=5, sleep=clock.sleep, clock=clock)
    with pytest.raises(ThrottleBudgetExceededError):
        client.complete(model="m")
    assert client.stats()["exhausted"] is True
    assert clock.now == 5.0


def test_a_throttled_request_is_not_a_generic_request_failure():
    class _Throttled:
        def complete(self, **request: object) -> dict[str, object]:
            del request
            raise ThrottleBudgetExceededError("spent")

    answer = ask_model(_Throttled(), "seat", "prompt")
    assert answer.error == "throttled"
    result = judge_cell(_Throttled(), model="seat", prompt="prompt")
    assert result.p_yes is None
    assert result.reason == "throttled"


def test_preflight_rejects_a_bad_backend_model_pair_with_pipeline_error():
    inner = _Inner([_http_error(400, "model is not served by pinned backend")])
    client = BackendPinnedClient(inner, "omlx-general")

    rejected = preflight(client, "security-reviewer")

    assert rejected == PreflightRejected(
        "security-reviewer", "omlx-general", 400, "model is not served by pinned backend"
    )
    assert inner.calls == 1
    assert inner.requests[0]["portal_backend"] == "omlx-general"
    assert inner.requests[0]["model"] == "security-reviewer"


def test_main_stops_before_cards_when_preflight_returns_a_4xx(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    inner = _Inner([_http_error(400, "backend does not serve model")])
    client = BackendPinnedClient(inner, "omlx-general")
    monkeypatch.setattr(
        "portal.modules.security.core.hunt.notables.__main__.model_from_env",
        lambda: (client, "security-reviewer"),
    )
    search = type("Search", (), {"iter_post": lambda *_args: iter([])})()

    code = main(["--index", "idx", "--out", str(tmp_path), "--stage", "cards"], search=search)

    assert code == 1
    assert inner.calls == 1
    error = capsys.readouterr().err
    assert "security-reviewer" in error
    assert "omlx-general" in error


def test_card_http_errors_are_separate_from_unparsed_and_over_threshold_fails():
    cards = [
        SourceCard(
            index="ix",
            sourcetype="st",
            kind="other",
            roles={},
            understood=False,
            reason="model_http_error",
            fmt="json",
            coverage=0.0,
            fields=(),
            sample={},
            facts={},
            model={},
            cache_key="http",
        ),
        SourceCard(
            index="ix",
            sourcetype="st",
            kind="other",
            roles={},
            understood=False,
            reason="unparseable_answer",
            fmt="json",
            coverage=0.0,
            fields=(),
            sample={},
            facts={},
            model={},
            cache_key="parse",
        ),
    ]
    answers = {
        "http": (ModelAnswer("", 0.0, "", None, "http_error"), 1, False),
        "parse": (ModelAnswer("nonsense", 0.0, "seat", None, None), 1, False),
    }

    assert _card_failure_counts(cards, answers) == (1, 1)
    _check_http_error_rate("cards", 1, 5, "seat", unparsed=1)
    with pytest.raises(RuntimeError, match="model_http_errors=2/5.*unparsed=1"):
        _check_http_error_rate("cards", 2, 5, "seat", unparsed=1)


def _facts() -> SourceFacts:
    return SourceFacts("ix", "st", 100, 0.0, 3600.0, ("h1",), 1, ("s1",), 1)


def _rows(tag: str) -> list[dict[str, object]]:
    return [
        {
            "_raw": json.dumps({"user": f"{tag}{index}", "image": "cmd.exe", "n": index}),
            "_time": 1000.0 + index,
            "host": "h1",
        }
        for index in range(4)
    ]


class _Answering:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, **request: object) -> dict[str, object]:
        del request
        self.calls += 1
        content = json.dumps({"kind": "activity", "actor": ["user"], "action": ["image"]})
        return {"model": "seat", "choices": [{"message": {"content": content}}]}


def test_cards_stop_asking_when_the_request_budget_is_spent(tmp_path):
    prepared = [
        item for tag in ("a", "b", "c") for item in prepare_cards(_facts(), _rows(tag), 1, "seat")
    ]
    client = _Answering()
    answers, stats = answer_cards(prepared, client, "seat", CardCache(tmp_path), request_budget=2)
    cards = assemble_cards(prepared, answers)
    assert stats["structures"] == 3
    assert stats["requests"] == 2
    assert stats["unasked"] == 1
    assert stats["request_budget"] == 2
    assert "backpressure" in stats
    assert client.calls == 2
    reasons = [card.reason for card in cards]
    assert reasons.count("model_budget_exhausted") == 1


class _Judge:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, **request: object) -> dict[str, object]:
        del request
        self.calls += 1
        return {
            "model": "seat",
            "choices": [
                {
                    "logprobs": {
                        "content": [
                            {
                                "top_logprobs": [
                                    {"token": " yes", "logprob": math.log(0.9)},
                                    {"token": "no", "logprob": math.log(0.1)},
                                ]
                            }
                        ]
                    }
                }
            ],
        }


def test_judge_stops_asking_when_the_request_budget_is_spent(tmp_path):
    notables = [
        {
            "content_key": f"k{index}",
            "what": f"behaviour {index}",
            "entities": [],
            "evidence": [{"line": "example"}],
        }
        for index in range(3)
    ]
    client = _Judge()
    judged, receipt = judge_all(
        notables, client=client, model="seat", cache_path=tmp_path / "j.json", request_budget=1
    )
    assert client.calls == 1
    assert receipt["requests"] == 1
    assert receipt["request_budget"] == 1
    assert receipt["unasked"] == 2
    assert receipt["unjudged_reasons"] == {"model_budget_exhausted": 2}
    assert [item["p_yes"] is None for item in judged] == [False, True, True]
