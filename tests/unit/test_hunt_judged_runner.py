from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from portal.modules.security.core.hunt.observations import (
    Observation,
    ObservationRun,
    literal_query,
)
from scripts.hunt_bed import judged_hunt


def _observation(host: str, hour: int, score: float) -> Observation:
    return Observation(
        "volume",
        host,
        "",
        hour,
        score,
        {"signal": "burst", "literal": literal_query("volume", "events", host, "")},
    )


class _Executor:
    def __init__(self):
        self.budget = SimpleNamespace(phase="ranking", limits={"requests": 2000}, kind_stats={})

    def stats(self):
        return {"observe": {"requests": 3, "seconds": 1.0}}

    def read(self, query, earliest, latest, *, kind, row_cap):
        host = query.split('host="', 1)[1].split('"', 1)[0]
        return SimpleNamespace(
            rows=[
                {
                    "_time": earliest + 1,
                    "host": host,
                    "source": "svc",
                    "sourcetype": "log",
                    "punct": "abc",
                    "_raw": f"event={host}",
                }
            ],
            reason=None,
        )


class _Judge:
    def complete(self, **kwargs):
        prompt = kwargs["messages"][0]["content"]
        value = 0.9 if "node-b" in prompt else 0.4
        yes = -0.1 if value == 0.9 else -1.0
        no = -1.0 if value == 0.9 else -0.1
        return {
            "model": "served-seat",
            "usage": {"prompt_tokens": 12},
            "choices": [
                {
                    "logprobs": {
                        "content": [
                            {
                                "top_logprobs": [
                                    {"token": "yes", "logprob": yes},
                                    {"token": "no", "logprob": no},
                                ]
                            }
                        ]
                    }
                }
            ],
        }


def test_runner_writes_one_ordered_lead_per_cell_and_records_budget_coverage(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(judged_hunt, "JUDGE_CELLS", 3)
    observations = [
        _observation("node-a", 3600, 9),
        _observation("node-b", 7200, 8),
        _observation("node-c", 10800, 7),
        _observation("node-a", 14400, 6),
    ]
    run = ObservationRun(
        observations, {"observe": {"requests": 3, "seconds": 1.0}}, {"volume": {"complete": True}}
    )
    executor = _Executor()
    args = SimpleNamespace(
        index="events",
        out=str(tmp_path),
        start=0,
        end=18000,
        baseline="current",
        from_grids=None,
        judge_url="endpoint",
        judge_model="security-workspace",
        judge_key_env="KEY",
    )

    judged_hunt.run_judged_hunt(
        args,
        prepare=lambda _args: (run, {"index": "events", "start": 0, "end": 18000}, executor),
        client=_Judge(),
    )

    leads = json.loads((tmp_path / "leads.json").read_text())["leads"]
    progress = json.loads((tmp_path / "progress.json").read_text())
    cells = [json.loads(line) for line in (tmp_path / "cells.jsonl").read_text().splitlines()]
    assert len(leads) == 4
    assert [lead["host"] for lead in leads] == ["node-b", "node-a", "node-c", "node-a"]
    assert [lead["l1_rank"] for lead in leads] == [2, 1, 3, 4]
    assert leads[0]["judged"] is True, json.dumps(leads)
    assert leads[3]["reason"] == "beyond_judge_cell_budget"
    assert progress["coverage"]["cells_judged"] == 3
    assert len(progress["coverage"]["beyond_budget"]) == 1
    assert progress["coverage_complete"] is False
    assert len(cells) == 3 and cells[0]["prompt_tokens"] == 12
