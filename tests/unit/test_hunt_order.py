"""Host-hour order is shared by the bench script and the hunt job."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from portal.modules.security.core.hunt import jobs
from portal.modules.security.core.hunt.engine import HOUR, hunt
from portal.modules.security.core.hunt.judge import JudgeResult
from portal.modules.security.core.hunt.observations import (
    Observation,
    ObservationRun,
    literal_query,
)
from portal.modules.security.core.hunt.order import (
    best_host_hour,
    judge_selected,
    order_group_indexes,
    positive_seeds,
    rank_from_observations,
)
from scripts.hunt_bed import judged_hunt
from tests.unit.test_hunt_judged_runner import _Executor, _Judge
from tests.unit.test_hunt_observations import END, INDEX, START, GridSearch
from tests.unit.test_hunt_wire import JobSearch, _plant


def _shape(host: str, hour: int, entity: str, score: float) -> Observation:
    return Observation(
        "shape",
        host,
        entity,
        hour,
        score,
        {"signal": "burst", "literal": literal_query("shape", "events", host, entity)},
    )


def test_positive_seeds_follow_the_host_hour_sum() -> None:
    busy = [_shape("busy", 0, f"e{i}", 2) for i in range(3)]
    idle = _shape("idle", 0, "zero", 0)
    rows = [_shape("solo", 0, "once", 5), *busy, idle]
    from portal.modules.security.core.hunt.order import accumulated_rows

    ordered = accumulated_rows(rows, "judge_not_configured")

    assert [row["host"] for row in ordered[:2]] == ["busy", "solo"]
    assert ordered[-1]["host"] == "idle"
    assert all(row["p_yes"] is None for row in ordered)
    assert all(row["reason"] == "judge_not_configured" for row in ordered)
    assert {item.host for item in positive_seeds(rows, ordered, 1, 12)} == {"busy"}
    assert idle not in positive_seeds(rows, ordered, 3, 12)


def test_group_order_uses_best_host_hour_and_keeps_ties() -> None:
    rows = [{"host": "a", "hour": 1}, {"host": "b", "hour": 2}]

    assert order_group_indexes([[("b", 2)], [("a", 1), ("b", 2)]], rows) == [1, 0]
    assert order_group_indexes([[("a", 1)], [("a", 1)]], rows) == [0, 1]
    assert best_host_hour([("b", 2), ("a", 1)], rows) == ("a", 1)


def test_script_receipts_match_the_core(tmp_path: Path, monkeypatch: Any) -> None:
    fixed = JudgeResult(0.25, 4, 0.2, "served-seat", None)
    monkeypatch.setattr(
        "portal.modules.security.core.hunt.order.judge_cell", lambda *_a, **_k: fixed
    )
    observations = [_shape("node-a", 0, "abc", 1), _shape("node-b", 3600, "abc", 3)]
    run = ObservationRun(observations, {"shape": {"requests": 1, "seconds": 0.1}}, {})
    executor = _Executor()
    meta = {"index": "events", "start": 0.0, "end": 7200.0}
    args = type("Args", (), {})()
    args.index = "events"
    args.out = str(tmp_path)
    args.baseline = "current"
    args.from_grids = None
    args.judge_url = "http://pipeline.example/v1"
    args.judge_model = "workspace"
    args.judge_key_env = "KEY"
    args.judge_cells = 2
    args.budget_order = "accumulated"
    args.order = "fused"
    args.evidence = "rarest"
    args.event_chars = 300
    judged_hunt.run_judged_hunt(args, prepare=lambda _args: (run, meta, executor), client=_Judge())
    ranked = rank_from_observations(
        observations,
        executor,
        "events",
        0.0,
        7200.0,
        _Judge(),
        "workspace",
        budget_order="accumulated",
        judge_cells=2,
        order_mode="fused",
        evidence_mode="rarest",
        event_chars=300,
    )

    assert (tmp_path / "leads.json").read_text() == json.dumps(
        {"leads": ranked["leads"]}, indent=1
    ) + "\n"
    assert (tmp_path / "cases.json").read_text() == json.dumps(
        {"cases": ranked["cases"]}, indent=1
    ) + "\n"
    assert (tmp_path / "cells.jsonl").read_text() == "".join(
        json.dumps(row, sort_keys=True) + "\n" for row in ranked["judged_rows"]
    )
    progress = json.loads((tmp_path / "progress.json").read_text())
    assert progress["coverage"] == ranked["coverage"]
    assert progress["request_kinds"]["judge"] == ranked["judge_cost"]
    assert progress["order"] == "fused"


class _Clock:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, **_kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        yes, no = (-0.2, -1.0) if self.calls == 1 else (-1.0, -0.2)
        return {
            "model": "served-seat",
            "usage": {"prompt_tokens": 3},
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


def test_a_stop_keeps_only_the_cells_already_judged() -> None:
    from portal.modules.security.core.hunt.evidence import EvidenceCell

    cells = [
        EvidenceCell("h", 0, 1, ()),
        EvidenceCell("h", HOUR, 2, ()),
    ]
    read = type("Read", (), {"evidence": [{"line": "svc | row"}], "reason": None})()
    reads = {(cell.host, cell.hour): read for cell in cells}
    clock = _Clock()

    judged, cost, _served, stopped = judge_selected(
        clock, "workspace", cells, reads, stop=lambda: clock.calls > 0
    )

    assert stopped is True
    assert cost["requests"] == 1
    assert list(judged) == [("h", 0)]
    assert judged[("h", 0)][1].p_yes is not None


class _EvidenceSearch(JobSearch):
    def iter_post(self, query: str, start: float, end: float) -> list[dict[str, Any]]:
        if "_hunt_observation" in query:
            host = query.split('host="', 1)[1].split('"', 1)[0]
            return [
                {
                    "_time": float(start) + 1,
                    "host": host,
                    "source": "svc",
                    "sourcetype": "a",
                    "punct": ".",
                    "_raw": f"marker {host}",
                    "_hunt_observation": 0,
                }
            ]
        return super().iter_post(query, start, end)


class _Timeout:
    def complete(self, **_kwargs: Any) -> dict[str, Any]:
        raise httpx.TimeoutException("slow")


def _fused(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    judged = [row for row in rows if row["p_yes"] is not None]
    ordered = sorted(judged, key=lambda row: (-float(row["p_yes"]), int(row["acc_rank"])))
    place = {(row["host"], row["hour"]): rank for rank, row in enumerate(ordered, 1)}
    return sorted(
        judged,
        key=lambda row: (place[(row["host"], row["hour"])] + int(row["acc_rank"]), row["acc_rank"]),
    )


def test_the_job_orders_leads_by_the_fused_host_hour(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(jobs, "_ROOT", tmp_path)
    jobs._run(
        "hunt-order",
        _EvidenceSearch(_plant()),
        INDEX,
        float(START),
        float(END),
        5,
        budgets={
            "query_seconds": 30,
            "job_seconds": 60,
            "requests": 200,
            "cells": 1000,
            "events": 1000,
        },
        judge=_Clock(),
        judge_model="workspace",
    )
    job = jobs.load("hunt-order")

    assert job is not None
    assert job["judge"]["configured"] is True
    assert job["judge"]["order"] == "fused"
    assert job["progress"]["judge_requests"] > 0
    hours = job["host_hours"]
    judged = [row for row in hours if row["p_yes"] is not None]
    assert judged
    assert hours[: len(judged)] == _fused(hours)
    assert all(row["p_yes"] is not None for row in judged)
    position = {(row["host"], row["hour"]): index for index, row in enumerate(hours)}

    def best(lead: dict[str, Any]) -> int:
        return min(position[(row["host"], int(row["hour"]))] for row in lead["observations"])

    assert [best(lead) for lead in job["leads"]] == sorted(best(lead) for lead in job["leads"])
    assert all(best(lead) < 5 for lead in job["leads"])
    for lead in job["leads"]:
        key = min(
            ((row["host"], int(row["hour"])) for row in lead["observations"]),
            key=lambda item: position[item],
        )
        row = next(item for item in hours if (item["host"], item["hour"]) == key)
        assert lead["risk"] == row["risk"]
        assert lead["acc_rank"] == row["acc_rank"]
        assert lead["p_yes"] == row["p_yes"]
    view = jobs.leads_view(job_id="hunt-order")
    assert {"risk", "acc_rank", "p_yes"} <= set(view["leads"][0])
    status = jobs.status(job_id="hunt-order")
    assert status["judge"]["configured"] is True
    assert status["host_hours"]
    assert len(json.dumps(status)) < 6000
    assert len(json.dumps(view)) < 6000
    case = jobs.case_view(job_id="hunt-order", case_no=1)
    assert {"risk", "acc_rank", "p_yes"} <= set(case)
    assert len(json.dumps(case)) < 6000


def test_an_unconfigured_judge_is_recorded_and_keeps_accumulated_order(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(jobs, "_ROOT", tmp_path)
    jobs._run(
        "hunt-plain",
        JobSearch(_plant()),
        INDEX,
        float(START),
        float(END),
        5,
        budgets={
            "query_seconds": 30,
            "job_seconds": 60,
            "requests": 200,
            "cells": 1000,
            "events": 1000,
        },
    )
    job = jobs.load("hunt-plain")

    assert job is not None
    assert job["judge"] == {"configured": False}
    assert job["host_hours"]
    assert all(row["reason"] == "judge_not_configured" for row in job["host_hours"])
    assert all(row["p_yes"] is None for row in job["host_hours"])
    assert [row["acc_rank"] for row in job["host_hours"]] == sorted(
        row["acc_rank"] for row in job["host_hours"]
    )
    assert any(row["risk"] == 0 for row in job["host_hours"])
    assert job["progress"]["judge_requests"] == 0
    assert all(lead["p_yes"] is None for lead in job["leads"])


def test_a_timeout_does_not_fail_the_job_or_invent_a_score(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(jobs, "_ROOT", tmp_path)
    jobs._run(
        "hunt-slow",
        _EvidenceSearch(_plant()),
        INDEX,
        float(START),
        float(END),
        5,
        budgets={
            "query_seconds": 30,
            "job_seconds": 60,
            "requests": 200,
            "cells": 1000,
            "events": 1000,
        },
        judge=_Timeout(),
        judge_model="workspace",
    )
    job = jobs.load("hunt-slow")

    assert job is not None
    assert job["status"] != "FAILED"
    assert job["judge"]["configured"] is True
    assert job["progress"]["judge_requests"] > 0
    assert all(row["p_yes"] is None for row in job["host_hours"])
    assert any(row["reason"] == "timeout" for row in job["host_hours"])


def test_a_judge_without_an_executor_does_not_call_out() -> None:
    called: list[str] = []

    class _Client:
        def complete(self, **_kwargs: Any) -> dict[str, Any]:
            called.append("called")
            return {}

    leads = hunt(
        GridSearch(_plant()),
        INDEX,
        float(START),
        float(END),
        candidates=5,
        judge=_Client(),
        judge_model="workspace",
    )

    assert called == []
    assert leads
    assert all(lead.p_yes is None for lead in leads)
    assert all(lead.acc_rank >= 1 for lead in leads)
