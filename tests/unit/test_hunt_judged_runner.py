from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

from portal.modules.security.core.hunt.executor import DEFAULT_BUDGETS, HuntBudgetExceededError
from portal.modules.security.core.hunt.observations import (
    Observation,
    ObservationRun,
    literal_query,
)
from scripts.hunt_bed import judged_hunt


def _observation(host: str, hour: int, score: float) -> Observation:
    return Observation(
        "shape",
        host,
        "abc",
        hour,
        score,
        {"signal": "burst", "literal": literal_query("shape", "events", host, "abc")},
    )


def _specific_observation(kind: str, entity: str, score: float) -> Observation:
    return Observation(
        kind,
        "node-a",
        entity,
        3600,
        score,
        {"signal": "burst", "literal": literal_query(kind, "events", "node-a", entity)},
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


class _EvidenceExecutor(_Executor):
    def __init__(self, rows, reason=None):
        super().__init__()
        self.rows = rows
        self.reason = reason

    def read(self, query, earliest, latest, *, kind, row_cap):
        return SimpleNamespace(rows=self.rows, reason=self.reason)


def _run_single_cell(tmp_path: Path, monkeypatch, observations, rows, reason=None):
    monkeypatch.setattr(judged_hunt, "JUDGE_CELLS", 1)
    run = ObservationRun(observations, {}, {"shape": {"complete": True}})
    executor = _EvidenceExecutor(rows, reason)
    args = SimpleNamespace(
        index="events",
        out=str(tmp_path),
        start=0,
        end=7200,
        baseline="current",
        from_grids=None,
        judge_url="endpoint",
        judge_model="security-workspace",
        judge_key_env="KEY",
    )
    judged_hunt.run_judged_hunt(
        args,
        prepare=lambda _args: (run, {"index": "events", "start": 0, "end": 7200}, executor),
        client=_Judge(),
    )
    return json.loads((tmp_path / "leads.json").read_text())["leads"][0]


def _events(count: int, *, source: str = "svc", distinct_sources: bool = False):
    return [
        {
            "_time": 3601 + index,
            "host": "node-a",
            "source": f"source-{index // 2}" if distinct_sources else source,
            "sourcetype": "log",
            "punct": f"p{index // 2}" if source == "svc" and not distinct_sources else "abc",
            "_raw": f"event={index}",
        }
        for index in range(count)
    ]


def test_one_selected_punct_across_twenty_sources_is_judged(tmp_path: Path, monkeypatch):
    lead = _run_single_cell(
        tmp_path,
        monkeypatch,
        [_specific_observation("shape", "abc", 4.0)],
        _events(40, distinct_sources=True),
    )

    assert lead["judged"] is True
    assert len(lead["evidence"]) == 2
    assert lead["observations"][0]["entity"] == "abc"


def test_one_selected_source_across_forty_puncts_is_judged(tmp_path: Path, monkeypatch):
    lead = _run_single_cell(
        tmp_path,
        monkeypatch,
        [_specific_observation("source", "svc\tlog", 4.0)],
        _events(80),
    )

    assert lead["judged"] is True
    assert len(lead["evidence"]) == 2
    assert lead["observations"][0]["entity"] == "svc\tlog"


def test_volume_ranked_first_does_not_widen_selected_evidence(tmp_path: Path, monkeypatch):
    volume = _specific_observation("volume", "", 9.0)
    shape = _specific_observation("shape", "abc", 8.0)
    rows = _events(3, distinct_sources=True)
    rows[2]["punct"] = "other"

    lead = _run_single_cell(tmp_path, monkeypatch, [volume, shape], rows)

    assert lead["judged"] is True
    assert [item["kind"] for item in lead["observations"]] == ["shape"]
    assert len(lead["evidence"]) == 2
    assert all(item["query"] == shape.evidence["literal"] for item in lead["evidence"])


def test_truncated_read_with_lines_is_still_judged_and_reason_is_kept(tmp_path: Path, monkeypatch):
    lead = _run_single_cell(
        tmp_path,
        monkeypatch,
        [_specific_observation("shape", "abc", 4.0)],
        _events(1, distinct_sources=True),
        "row_budget",
    )

    assert lead["judged"] is True
    assert lead["reason"] == "row_budget"
    assert len(lead["evidence"]) == 1
    progress = json.loads((tmp_path / "progress.json").read_text())
    assert progress["coverage"]["cells_judged"] == 1
    assert progress["coverage"]["cells_unjudged"] == 0
    assert progress["coverage_complete"] is False


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
        order="judged",
        budget_order="layer1",
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
    assert [lead["budget_rank"] for lead in leads] == [2, 1, 3, 4]


def _args(tmp_path: Path, **overrides: object) -> SimpleNamespace:
    values = {
        "index": "events",
        "out": str(tmp_path),
        "start": 0,
        "end": 18000,
        "baseline": "current",
        "from_grids": None,
        "judge_url": "endpoint",
        "judge_model": "security-workspace",
        "judge_key_env": "KEY",
        "judge_cells": 3,
        "budget_order": "round_robin",
        "order": "fused",
        "event_chars": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _prepare(observations: list[Observation], executor: _Executor):
    run = ObservationRun(
        observations, {"observe": {"requests": 3, "seconds": 1.0}}, {"volume": {"complete": True}}
    )
    return lambda _args: (run, {"index": "events", "start": 0, "end": 18000}, executor)


def test_round_robin_budget_reaches_the_next_host_before_a_second_hour(
    tmp_path: Path,
):
    observations = [
        _observation("node-a", 0, 9),
        _observation("node-a", 3600, 8),
        _observation("node-b", 0, 7),
    ]

    judged_hunt.run_judged_hunt(
        _args(tmp_path, judge_cells=2, order="budget"),
        prepare=_prepare(observations, _Executor()),
        client=_Judge(),
    )

    leads = json.loads((tmp_path / "leads.json").read_text())["leads"]
    assert [(lead["host"], lead["hour"], lead["budget_rank"]) for lead in leads] == [
        ("node-a", 0, 1),
        ("node-b", 0, 2),
        ("node-a", 3600, 3),
    ]
    assert [lead["judged"] for lead in leads] == [True, True, False]
    assert leads[2]["reason"] == "beyond_judge_cell_budget"
    assert leads[2]["evidence"] == []


def test_layer1_budget_keeps_the_layer_one_prefix(tmp_path: Path):
    observations = [
        _observation("node-a", 0, 9),
        _observation("node-a", 3600, 8),
        _observation("node-b", 0, 7),
    ]

    judged_hunt.run_judged_hunt(
        _args(tmp_path, judge_cells=2, budget_order="layer1", order="budget"),
        prepare=_prepare(observations, _Executor()),
        client=_Judge(),
    )

    leads = json.loads((tmp_path / "leads.json").read_text())["leads"]
    assert [(lead["host"], lead["hour"], lead["judged"]) for lead in leads] == [
        ("node-a", 0, True),
        ("node-a", 3600, True),
        ("node-b", 0, False),
    ]


def test_fused_order_and_cases_cover_every_judged_host_day(tmp_path: Path):
    observations = [
        _observation("node-a", 0, 9),
        _observation("node-b", 0, 8),
        _observation("node-a", 3600, 7),
    ]

    judged_hunt.run_judged_hunt(
        _args(tmp_path, judge_cells=3, order="fused"),
        prepare=_prepare(observations, _Executor()),
        client=_Judge(),
    )

    leads = json.loads((tmp_path / "leads.json").read_text())["leads"]
    cases = json.loads((tmp_path / "cases.json").read_text())["cases"]
    progress = json.loads((tmp_path / "progress.json").read_text())
    assert [(lead["host"], lead["hour"]) for lead in leads] == [
        ("node-a", 0),
        ("node-b", 0),
        ("node-a", 3600),
    ]
    assert [case["host"] for case in cases] == ["node-a", "node-b"]
    assert cases[0]["start"] == 0 and cases[0]["end"] == 7200
    assert [member["hour"] for member in cases[0]["members"]] == [0, 3600]
    assert cases[0]["members"][0]["lead_rank"] == 1
    assert cases[0]["evidence"] == leads[0]["evidence"]
    assert cases[1]["start"] == 0 and cases[1]["end"] == 3600
    assert progress["options"]["budget_order"] == "round_robin"
    assert progress["options"]["order"] == "fused"
    assert progress["model_id_as_served"] == ["served-seat"]
    assert "wall_seconds" in progress
    for payload in (leads, cases):
        assert _keys(payload).isdisjoint({"seconds", "wall_seconds", "prompt_tokens"})


def test_judged_order_is_p_yes_then_unjudged_then_beyond(tmp_path: Path):
    observations = [
        _observation("node-a", 0, 9),
        _observation("node-b", 0, 8),
        _observation("node-c", 0, 7),
    ]

    judged_hunt.run_judged_hunt(
        _args(tmp_path, judge_cells=2, budget_order="layer1", order="judged"),
        prepare=_prepare(observations, _Executor()),
        client=_Judge(),
    )

    leads = json.loads((tmp_path / "leads.json").read_text())["leads"]
    assert [(lead["host"], lead["judged"]) for lead in leads] == [
        ("node-b", True),
        ("node-a", True),
        ("node-c", False),
    ]
    assert leads[2]["reason"] == "beyond_judge_cell_budget"


def _keys(payload: object) -> set[str]:
    found: set[str] = set()
    if isinstance(payload, dict):
        found.update(payload)
        for value in payload.values():
            found.update(_keys(value))
    elif isinstance(payload, list):
        for value in payload:
            found.update(_keys(value))
    return found


class _BudgetingExecutor:
    """Splunk stand-in: honor `| head N`, otherwise return the wide host-hour."""

    def __init__(self, wide_rows: int, events_limit: int):
        self.wide_rows = wide_rows
        self.events_limit = events_limit
        self.events = 0
        self.calls: list[str] = []
        self._lock = threading.Lock()
        self.budget = SimpleNamespace(limits={"events": events_limit, "requests": 2000})
        self._evidence = {"requests": 0, "seconds": 0.0, "censored": 0}

    def stats(self):
        return {"evidence": dict(self._evidence)}

    def read(self, query, earliest, latest, *, kind, row_cap):
        head = re.search(r"\| head (\d+)", query)
        count = int(head.group(1)) if head else self.wide_rows
        count = min(count, self.wide_rows)
        with self._lock:
            self.calls.append(query)
            self._evidence["requests"] += 1
            if self.events + count > self.events_limit:
                raise HuntBudgetExceededError("event_budget_exhausted")
            self.events += count
        host = query.split('host="', 1)[1].split('"', 1)[0]
        rows = [
            {
                "_time": earliest + 1,
                "host": host,
                "source": "svc",
                "sourcetype": "log",
                "punct": "abc",
                "_raw": f"event-{index}",
                "_hunt_observation": 0,
            }
            for index in range(min(count, 2))
        ]
        # The budget counts every row the search returns, not only the lines shown.
        rows.extend(rows[:1] * (count - len(rows)))
        return SimpleNamespace(rows=rows[:count], reason=None)


def test_bounded_cell_reads_judge_the_whole_budget_the_wide_read_cannot(tmp_path: Path):
    """160 cells of the old 300-row read exceed 5,000 events; the bounded read must not."""
    cell_count = 20
    wide_rows = 300
    events_limit = int(DEFAULT_BUDGETS["events"])
    assert wide_rows * cell_count > events_limit
    observations = [
        _observation(f"h{index}", 0, float(cell_count - index)) for index in range(cell_count)
    ]
    executor = _BudgetingExecutor(wide_rows, events_limit)

    progress = judged_hunt.run_judged_hunt(
        _args(tmp_path, judge_cells=cell_count, budget_order="layer1", order="judged"),
        prepare=_prepare(observations, executor),
        client=_Judge(),
    )

    head = re.search(r"\| head (\d+)", executor.calls[0])
    assert head is not None
    assert int(head.group(1)) * 160 <= events_limit
    assert "punct source" not in executor.calls[0]
    assert progress["coverage"]["cells_judged"] == cell_count
    assert progress["coverage_complete"] is True
    assert executor.events <= events_limit


def test_event_budget_exhaustion_remains_on_the_receipt(tmp_path: Path):
    observations = [_observation(f"h{index}", 0, float(4 - index)) for index in range(4)]
    executor = _BudgetingExecutor(wide_rows=30, events_limit=10)

    progress = judged_hunt.run_judged_hunt(
        _args(tmp_path, judge_cells=4, budget_order="layer1", order="budget"),
        prepare=_prepare(observations, executor),
        client=_Judge(),
    )

    assert progress["coverage_complete"] is False
    reasons = {row["reason"] for row in progress["coverage"]["unjudged"]}
    assert "event_budget_exhausted" in reasons


def test_help_names_the_pipeline_workspace_and_the_new_options():
    completed = subprocess.run(
        [sys.executable, "scripts/hunt_bed/judged_hunt.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    help_text = completed.stdout
    assert "Portal Pipeline" in help_text
    assert "workspace id" in help_text
    assert "PORTAL_HUNT_JUDGE_URL" in help_text
    assert "PORTAL_HUNT_JUDGE_MODEL" in help_text
    assert "--budget-order" in help_text and "round_robin" in help_text
    assert "accumulated" in help_text and "layer1" in help_text
    assert "--order" in help_text and "{fused,judged,budget}" in help_text
    assert "--evidence" in help_text and "{rarest,strongest}" in help_text
    assert "--judge-cells" in help_text
    assert "--event-chars" in help_text


def test_parse_defaults_accumulated_rarest_and_fifty_cells(monkeypatch):
    monkeypatch.setenv("PORTAL_HUNT_JUDGE_URL", "http://pipeline.example/v1")
    monkeypatch.setenv("PORTAL_HUNT_JUDGE_MODEL", "security-reviewer")
    monkeypatch.setattr(sys, "argv", ["judged_hunt.py", "--index", "events", "--out", "out"])

    args = judged_hunt._parse()

    assert args.judge_cells == 50
    assert args.budget_order == "accumulated"
    assert args.evidence == "rarest"
    assert args.order == "fused"


def test_accumulated_budget_judges_the_sum_before_first_appearance(tmp_path: Path):
    observations = [
        _observation("node-a", 0, 1),
        _observation("node-b", 0, 2),
        _observation("node-b", 0, 2),
    ]

    judged_hunt.run_judged_hunt(
        _args(tmp_path, judge_cells=1, budget_order="accumulated", order="budget"),
        prepare=_prepare(observations, _Executor()),
        client=_Judge(),
    )

    leads = json.loads((tmp_path / "leads.json").read_text())["leads"]
    progress = json.loads((tmp_path / "progress.json").read_text())
    assert [(lead["host"], lead["judged"], lead["risk"], lead["acc_rank"]) for lead in leads] == [
        ("node-b", True, 4.0, 1),
        ("node-a", False, 1.0, 2),
    ]
    assert leads[0]["evidence_selection"] == "rarest"
    assert leads[0]["span"] == 3600
    assert progress["options"]["budget_order"] == "accumulated"
    assert progress["options"]["evidence"] == "rarest"
    assert progress["order_statement"] == "budget sequence"
    assert progress["request_kinds"]["judge"]["requests"] == 1


def test_round_robin_follows_accumulated_order_within_and_across_hosts(tmp_path: Path):
    observations = [
        _observation("node-a", 0, 9),
        _observation("node-a", 3600, 8),
        _observation("node-b", 0, 1),
        _observation("node-b", 0, 1),
        _observation("node-b", 3600, 7),
    ]

    judged_hunt.run_judged_hunt(
        _args(tmp_path, judge_cells=4, budget_order="round_robin", order="budget"),
        prepare=_prepare(observations, _Executor()),
        client=_Judge(),
    )

    leads = json.loads((tmp_path / "leads.json").read_text())["leads"]
    assert [(lead["host"], lead["hour"], lead["budget_rank"]) for lead in leads] == [
        ("node-a", 0, 1),
        ("node-b", 3600, 2),
        ("node-a", 3600, 3),
        ("node-b", 0, 4),
    ]


def test_fused_order_breaks_equal_p_yes_by_accumulated_rank(tmp_path: Path):
    observations = [
        _observation("b", 0, 5),
        _observation("c", 0, 4),
        _observation("a", 0, 9),
    ]

    judged_hunt.run_judged_hunt(
        _args(tmp_path, judge_cells=3, budget_order="layer1", order="fused"),
        prepare=_prepare(observations, _Executor()),
        client=_Judge(),
    )

    leads = json.loads((tmp_path / "leads.json").read_text())["leads"]
    assert [lead["host"] for lead in leads] == ["b", "a", "c"]
    assert [lead["acc_rank"] for lead in leads] == [2, 1, 3]
    assert [lead["budget_rank"] for lead in leads] == [1, 3, 2]
    progress = json.loads((tmp_path / "progress.json").read_text())
    assert "acc_rank" in progress["order_statement"]
    assert progress["order"] == "fused"


def test_unjudged_tail_follows_accumulated_order(tmp_path: Path):
    observations = [
        _observation("node-a", 0, 1),
        _observation("node-b", 0, 5),
        _observation("node-c", 0, 9),
    ]

    judged_hunt.run_judged_hunt(
        _args(tmp_path, judge_cells=1, budget_order="layer1", order="judged"),
        prepare=_prepare(observations, _Executor()),
        client=_Judge(),
    )

    leads = json.loads((tmp_path / "leads.json").read_text())["leads"]
    assert [(lead["host"], lead["reason"]) for lead in leads] == [
        ("node-a", None),
        ("node-c", "beyond_judge_cell_budget"),
        ("node-b", "beyond_judge_cell_budget"),
    ]


class _HourExecutor(_Executor):
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
                    "_raw": f"hour-{int(earliest)}",
                }
            ],
            reason=None,
        )


class _PreferLater:
    def complete(self, **kwargs):
        prompt = kwargs["messages"][0]["content"]
        value = 0.9 if "hour-3600" in prompt else 0.2
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


def test_cases_cover_every_host_day_and_members_follow_lead_order(tmp_path: Path):
    observations = [
        _observation("node-a", 0, 4),
        _observation("node-a", 3600, 3),
        _observation("node-b", 86400, 1),
    ]

    judged_hunt.run_judged_hunt(
        _args(tmp_path, judge_cells=2, budget_order="layer1", order="judged"),
        prepare=_prepare(observations, _HourExecutor()),
        client=_PreferLater(),
    )

    leads = json.loads((tmp_path / "leads.json").read_text())["leads"]
    cases = json.loads((tmp_path / "cases.json").read_text())["cases"]
    assert [(lead["host"], lead["hour"]) for lead in leads] == [
        ("node-a", 3600),
        ("node-a", 0),
        ("node-b", 86400),
    ]
    assert [case["host"] for case in cases] == ["node-a", "node-b"]
    assert cases[0]["risk"] == 7.0
    assert [member["hour"] for member in cases[0]["members"]] == [3600, 0]
    assert cases[0]["members"][0]["p_yes"] > cases[0]["members"][1]["p_yes"]
    assert cases[0]["evidence"] == leads[0]["evidence"]
    assert cases[1]["risk"] == 1.0
    assert cases[1]["evidence"] == []
    member = cases[1]["members"][0]
    assert member["p_yes"] is None
    assert member["hour"] == 86400
    assert {"risk", "acc_rank", "l1_rank", "lead_rank"} <= set(member)
    assert _keys(cases).isdisjoint({"seconds", "wall_seconds", "prompt_tokens"})
