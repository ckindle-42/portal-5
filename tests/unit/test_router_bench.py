"""scripts/router_bench.py scores a classifier reply against the suite's routed_workspace."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _module():
    path = Path(__file__).resolve().parents[2] / "scripts/router_bench.py"
    spec = importlib.util.spec_from_file_location("router_bench", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_expected_workspace_comes_from_the_routed_workspace_checker():
    rb = _module()
    task = {
        "checkers": [
            {"type": "answer_contains"},
            {"type": "routed_workspace", "workspace": "auto-spl"},
        ]
    }
    assert rb._expected(task) == "auto-spl"
    assert rb._expected({"checkers": []}) == ""


def test_bench_scores_ok_and_deadline(monkeypatch):
    rb = _module()
    replies = iter(
        [
            ({}, 5.0),
            ({"workspace": "auto-coding", "confidence": 0.9}, 100.0),
            ({"workspace": "auto-daily"}, 5000.0),
        ]
    )
    monkeypatch.setattr(rb, "_classify", lambda _m, _t: next(replies))
    tasks = [
        {
            "id": "a",
            "instruction": "x",
            "checkers": [{"type": "routed_workspace", "workspace": "auto-coding"}],
        },
        {
            "id": "b",
            "instruction": "y",
            "checkers": [{"type": "routed_workspace", "workspace": "auto-daily"}],
        },
    ]
    r = rb.bench("m", tasks)
    assert (r["correct"], r["correct_in_deadline"]) == (2, 1)
