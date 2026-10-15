"""N-3: the candidates probe does not send its own max_tokens, so the pipeline applies the
seat's predict_limit (setdefault: a request cap would win over it)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parents[2] / "tests" / "benchmarks"


class _Resp:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"choices": [{"message": {"content": "ok"}}], "usage": {"completion_tokens": 1}}


class _Client:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    def post(self, url: str, json: dict, headers: dict) -> _Resp:
        self.sent.append(json)
        return _Resp()


@pytest.fixture
def probe(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(BENCH))
    sys.modules.pop("bench_candidates_v10", None)
    mod = importlib.import_module("bench_candidates_v10")
    client = _Client()
    monkeypatch.setattr(mod, "_get_http_client", lambda: client)
    return mod, client


def test_default_call_sends_no_max_tokens(probe) -> None:
    mod, client = probe
    mod.call_pipeline("auto-coding", [{"role": "user", "content": "hi"}])
    assert "max_tokens" not in client.sent[-1]


def test_an_explicit_cap_is_still_sent_when_a_caller_asks(probe) -> None:
    mod, client = probe
    mod.call_pipeline("auto-coding", [{"role": "user", "content": "hi"}], max_tokens=64)
    assert client.sent[-1]["max_tokens"] == 64
