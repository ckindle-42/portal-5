"""N-1: the research probe's scoring. Errors are unscored (not FAIL), rates use scored items,
text tool calls are not answers, and a verdict needs enough scored items."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parents[2] / "tests" / "benchmarks"
QSET = BENCH / "fixtures" / "research_eval_qset.jsonl"


@pytest.fixture
def probe(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(BENCH))
    sys.modules.pop("bench_research_probe", None)
    return importlib.import_module("bench_research_probe")


def _r(probe, factuality: str, error: str | None = None, source: str = "content", synth: int = 3):
    return probe.QuestionResult(
        qid="x",
        question="q",
        checkable="c",
        final_answer="a",
        hops_used=1,
        factuality=factuality,
        error=error,
        answer_source=source,
        synthesis_1_5=synth,
    )


def test_errors_are_not_counted_as_fail(probe) -> None:
    s = probe.summarize([_r(probe, "PASS"), _r(probe, "ERROR"), _r(probe, "FAIL")])
    assert s["factuality_fail"] == 1
    assert s["scored"] == 2
    assert s["factuality_pass_rate"] == 0.5
    assert s["errors"] == 1


def test_reasoning_fallback_is_counted(probe) -> None:
    s = probe.summarize([_r(probe, "PASS", source="reasoning"), _r(probe, "PASS")])
    assert s["reasoning_fallback"] == 1


def test_a_small_n_is_insufficient_not_a_win(probe) -> None:
    c = probe.summarize([_r(probe, "PASS") for _ in range(10)])
    i = probe.summarize([_r(probe, "FAIL") for _ in range(10)])
    assert probe.verdict(c, i) == "INSUFFICIENT_N"


def test_enough_scored_items_give_a_verdict(probe) -> None:
    n = probe.MIN_SCORED_FOR_VERDICT
    c = probe.summarize([_r(probe, "PASS") for _ in range(n)])
    i = probe.summarize([_r(probe, "FAIL") for _ in range(n)])
    assert probe.verdict(c, i) == "CANDIDATE_WINS"


def test_a_text_tool_call_is_not_an_answer(probe, monkeypatch) -> None:
    class _Resp:
        def __init__(self, body):
            self._b = body

        def raise_for_status(self):
            return None

        def json(self):
            return self._b

    class _Client:
        def post(self, url, json=None, timeout=None):
            return _Resp(
                {
                    "choices": [
                        {
                            "message": {
                                "content": '<tool_call>{"name":"web_search","arguments":{"query":"x"}}</tool_call>',
                            }
                        }
                    ]
                }
            )

    res = probe.run_agent("m", "question", _Client(), max_hops=1)
    assert res.error and res.error.startswith("TEXT_TOOL_CALL")
    assert res.final_answer == ""


def test_rq03_is_date_anchored() -> None:
    rows = [json.loads(line) for line in QSET.read_text().splitlines() if line.strip()]
    q = next(r for r in rows if r["id"] == "rq03")["question"]
    assert "As of" in q and "most recent" not in q.lower()
