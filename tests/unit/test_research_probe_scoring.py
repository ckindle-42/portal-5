"""N-1: the research probe's scoring. Errors are unscored (not FAIL), rates use scored items,
text tool calls are not answers, and a verdict needs enough scored items."""

from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parents[2] / "tests" / "benchmarks"
QSET = BENCH / "fixtures" / "research_eval_qset.jsonl"
LARGE_QSET = BENCH / "fixtures" / "research_eval_qset_large.jsonl"

TIME_SENSITIVE = re.compile(
    r"\b(as of|at present|current|currently|latest|most recent|nowadays|recent|recently|today)\b",
    re.IGNORECASE,
)
QSET_KEYS = ("id", "question", "checkable", "category", "source")


def _load(path: Path) -> list[dict]:
    """Same one-line loader the probe's main() uses."""
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


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


def test_large_qset_every_item_loads() -> None:
    rows = _load(LARGE_QSET)
    assert len(rows) >= 30
    assert len({r["id"] for r in rows}) == len(rows)
    for row in rows:
        missing = [key for key in QSET_KEYS if not isinstance(row.get(key), str)]
        assert not missing, (row.get("id"), missing)
        assert row["question"].strip().endswith("?"), row["id"]
        assert row["source"].startswith(("https://", "http://")), row["id"]
        assert isinstance(row.get("multi_hop"), bool), row["id"]


def test_large_qset_every_item_has_a_scorable_answer_key() -> None:
    for row in _load(LARGE_QSET):
        key = row["checkable"].strip()
        assert len(key) >= 40, row["id"]
        assert key != row["question"].strip(), row["id"]
        assert "{" not in key and "}" not in key, row["id"]
        assert len(set(key.split())) >= 5, row["id"]
        assert not TIME_SENSITIVE.search(f"{row['question']} {key}"), row["id"]


def test_large_qset_is_non_security_and_mixes_multi_hop() -> None:
    rows = _load(LARGE_QSET)
    assert all(row["category"].lower() != "security" for row in rows)
    assert sum(1 for row in rows if row["multi_hop"]) >= 10
