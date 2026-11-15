"""The graph runner reads bounded cells in one order and reports its own coverage."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from portal.modules.security.core.hunt.engine import HOUR
from portal.modules.security.core.hunt.observations import Observation
from scripts.hunt_bed import graph_hunt

START = 1_700_000_000 // HOUR * HOUR
END = START + 4 * HOUR
INDEX = "idx"


def _obs(
    kind: str,
    host: str,
    entity: str,
    hour: int,
    score: float,
    prior: tuple[int, ...] = (),
) -> Observation:
    return Observation(
        kind,
        host,
        entity,
        hour,
        score,
        {
            "signal": "burst",
            "now": 1,
            "prior": [{"hour": stamp, "count": 1} for stamp in prior],
            "scores": {"current": score, "seasonal": None, "peer": None, "left": None},
        },
    )


class FakeNotable:
    def __init__(self, lead: dict[str, Any], evidence: dict[str, Any]) -> None:
        self.lead = lead
        self.evidence = evidence
        self.entity = str(lead.get("entity", ""))

    def as_lead(self) -> dict[str, Any]:
        return dict(self.lead)

    def as_dict(self) -> dict[str, Any]:
        return {**self.lead, "evidence": self.evidence}


class FakeExecutor:
    __name__ = "fake.executor"

    def __init__(self, censored_hosts: frozenset[str] = frozenset()) -> None:
        self.censored_hosts = censored_hosts
        self.calls: list[dict[str, Any]] = []

    def read(
        self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
    ) -> SimpleNamespace:
        self.calls.append({"query": query, "start": start, "end": end, "kind": kind})
        if query.startswith("| tstats"):
            term = query.split('TERM("', 1)[1].split('")', 1)[0]
            censored = term == "pid=censored"
            return SimpleNamespace(
                rows=[{"_time": start + HOUR * step, "count": 3} for step in range(4)],
                censored=censored,
                reason="query_bound" if censored else None,
            )
        host = query.split('host="', 1)[1].split('"', 1)[0]
        rows = [
            {"_time": start + 60, "host": host, "source": "svc", "_raw": "uid=alpha pid=4242"},
            {"_time": start + 120, "host": host, "source": "svc", "_raw": "uid=alpha pid=9999"},
        ][:row_cap]
        censored = host in self.censored_hosts
        return SimpleNamespace(
            rows=rows, censored=censored, reason="query_bound" if censored else None
        )


def _fake_graph() -> tuple[SimpleNamespace, dict[str, Any]]:
    seen: dict[str, Any] = {}

    def build(
        samples: Any,
        history: Any = None,
        missing: Any = None,
    ) -> dict[str, Any]:
        seen["samples"] = samples
        seen["history"] = history
        seen["missing"] = missing
        return {"built": True}

    def notables(graph: Any, observations: Any) -> list[FakeNotable]:
        seen["observations"] = observations
        return [
            FakeNotable(
                {"entity": "uid=alpha", "host": "h1", "hour": START + 2 * HOUR, "span": 2 * HOUR},
                {"why": 1},
            ),
            FakeNotable(
                {"entity": "pid=4242", "host": "h2", "hour": START, "span": HOUR}, {"why": 2}
            ),
        ]

    return SimpleNamespace(__name__="fake.graph", build=build, notables=notables), seen


def _saved(tmp_path: Path, observations: list[Observation]) -> Path:
    out = tmp_path / "saved"
    out.mkdir()
    lines = [json.dumps(obs.as_dict(), sort_keys=True) for obs in observations]
    (out / "observations.jsonl").write_text("\n".join(lines) + "\n")
    (out / "progress.json").write_text(
        json.dumps(
            {
                "index": INDEX,
                "start": START,
                "end": float(END),
                "coverage": {"volume": {"complete": True, "reasons": []}},
                "request_kinds": {"volume": {"requests": 3, "seconds": 1.0}},
            }
        )
    )
    return out


def _run(tmp_path: Path, monkeypatch: Any, executor: FakeExecutor | None = None) -> Path:
    saved = _saved(
        tmp_path,
        [
            _obs(
                "value",
                "h1",
                "uid=alpha",
                START + 2 * HOUR,
                9.0,
                prior=(START + HOUR, START),
            ),
            _obs("volume", "h2", "", START + 3 * HOUR, 5.0, prior=(START + HOUR,)),
        ],
    )
    graph, _seen = _fake_graph()
    monkeypatch.setattr(graph_hunt, "_graph", graph)
    monkeypatch.setattr(graph_hunt, "_executor", executor or FakeExecutor())
    out = tmp_path / "out"
    monkeypatch.setattr(
        "sys.argv",
        [
            "graph_hunt.py",
            "--index",
            INDEX,
            "--out",
            str(out),
            "--from-grids",
            str(saved),
        ],
    )
    assert graph_hunt.main() == 0
    return out


def test_one_cell_is_read_once_with_the_first_observations_literal() -> None:
    plan = graph_hunt.cell_plan(
        INDEX,
        [_obs("volume", "h0", "", START, 2.0), _obs("value", "h0", "uid=a", START, 9.0)],
    )

    assert [(cell.host, cell.hour, cell.baseline) for cell in plan] == [("h0", START, False)]
    assert plan[0].literal == 'search index="idx" host="h0"'


def test_cells_follow_the_observation_order_then_prior_hours() -> None:
    plan = graph_hunt.cell_plan(
        INDEX,
        [
            _obs("value", "h1", "uid=alpha", START + 2 * HOUR, 9.0, prior=(START + HOUR, START)),
            _obs("volume", "h2", "", START + 3 * HOUR, 5.0, prior=(START + HOUR,)),
        ],
    )

    assert [(cell.host, cell.hour, cell.baseline) for cell in plan] == [
        ("h1", START + 2 * HOUR, False),
        ("h1", START + HOUR, True),
        ("h1", START, True),
        ("h2", START + 3 * HOUR, False),
        ("h2", START + HOUR, True),
    ]
    assert plan[0].literal == 'search index="idx" host="h1" "uid=alpha" "alpha"'


def test_cell_plan_stops_at_the_budget() -> None:
    observations = [
        _obs("volume", f"h{index}", "", START + index * HOUR, 1.0)
        for index in range(graph_hunt.CELL_BUDGET + 10)
    ]

    plan = graph_hunt.cell_plan(INDEX, observations)

    assert len(plan) == graph_hunt.CELL_BUDGET
    assert len({(cell.host, cell.hour) for cell in plan}) == len(plan)


def test_runner_writes_leads_cells_and_progress(tmp_path: Path, monkeypatch: Any) -> None:
    _run(tmp_path, monkeypatch)
    out = tmp_path / "out"
    leads = json.loads((out / "leads.json").read_text())["leads"]
    cells = [json.loads(line) for line in (out / "cells.jsonl").read_text().splitlines()]
    notables = [json.loads(line) for line in (out / "notables.jsonl").read_text().splitlines()]
    progress = json.loads((out / "progress.json").read_text())

    assert [lead["host"] for lead in leads] == ["h1", "h2"]
    assert [lead["hour"] for lead in leads] == [START + 2 * HOUR, START]
    assert [row["evidence"] for row in notables] == [{"why": 1}, {"why": 2}]
    assert [(cell["host"], cell["hour"], cell["baseline"]) for cell in cells] == [
        ("h1", START + 2 * HOUR, False),
        ("h1", START + HOUR, True),
        ("h1", START, True),
        ("h2", START + 3 * HOUR, False),
        ("h2", START + HOUR, True),
    ]
    assert cells[0]["events"] == 2
    assert cells[0]["query"].endswith(
        f"| eval _k=md5(_raw) | sort {graph_hunt.EVENTS_PER_CELL} _k _time _raw "
        f"| head {graph_hunt.EVENTS_PER_CELL} | table _time host source _raw"
    )
    assert progress["lead_count"] == 2
    assert progress["cell_count"] == 5
    assert progress["event_count"] == 10
    assert progress["request_kinds"]["events"]["requests"] == 5
    assert progress["request_kinds"]["events"]["censored"] == 0
    assert progress["request_kinds"]["history"]["requests"] == 2
    assert progress["request_kinds"]["history"]["censored"] == 0
    assert progress["history"] == {
        "budget": graph_hunt.HISTORY_TERMS,
        "trigger_terms": graph_hunt.HISTORY_TRIGGER_TERMS,
        "concurrency": graph_hunt.HISTORY_CONCURRENCY,
        "requested": 2,
        "read": 2,
        "wall_seconds": progress["history"]["wall_seconds"],
        "skipped_count": 0,
        "skipped": [],
    }
    assert progress["budgets"]["history_terms"] == graph_hunt.HISTORY_TERMS
    assert progress["budgets"]["history_concurrency"] == graph_hunt.HISTORY_CONCURRENCY
    assert progress["observation_request_kinds"] == {"volume": {"requests": 3, "seconds": 1.0}}
    assert progress["coverage"] == {
        "observation_complete": True,
        "cells_planned": 5,
        "cells_read": 5,
        "cells_censored": 0,
        "history_planned": 2,
        "history_read": 2,
        "history_censored": 0,
        "reasons": [],
    }
    assert progress["coverage_complete"] is True
    assert progress["modules"] == {"graph": "fake.graph", "executor": "FakeExecutor"}
    assert progress["from_grids"] == str(tmp_path / "saved")


def test_runner_hands_the_graph_cell_samples_keyed_by_host_source_hour(
    tmp_path: Path, monkeypatch: Any
) -> None:
    saved = _saved(
        tmp_path,
        [_obs("value", "h1", "uid=alpha", START + 2 * HOUR, 9.0, prior=(START + HOUR,))],
    )
    graph, seen = _fake_graph()
    monkeypatch.setattr(graph_hunt, "_graph", graph)
    monkeypatch.setattr(graph_hunt, "_executor", FakeExecutor())
    monkeypatch.setattr(
        "sys.argv",
        [
            "graph_hunt.py",
            "--index",
            INDEX,
            "--out",
            str(tmp_path / "out"),
            "--from-grids",
            str(saved),
        ],
    )

    assert graph_hunt.main() == 0

    assert set(seen["samples"]) == {
        ("h1", "svc", START + 2 * HOUR),
        ("h1", "svc", START + HOUR),
    }
    events = [event for cell in seen["samples"].values() for event in cell]
    assert all(set(event) == {"_time", "host", "source", "_raw"} for event in events)
    assert [obs.host for obs in seen["observations"]] == ["h1"]
    assert set(seen["history"]) == {"uid=alpha", "pid=4242"}
    assert seen["missing"] == {}


def test_history_query_is_the_indexed_term_over_the_whole_retention() -> None:
    assert (
        graph_hunt.history_query(INDEX, "op=pam:accounting")
        == '| tstats count where index="idx" TERM("op=pam:accounting") by _time span=1h'
    )


def test_history_reads_are_budgeted_and_skips_say_why(monkeypatch: Any) -> None:
    monkeypatch.setattr(graph_hunt, "HISTORY_TERMS", 1)
    observation = _obs("value", "h1", "uid=alpha", START, 9.0)
    targets, skipped = graph_hunt.history_plan(
        {"uid=alpha", "pid=4242"}, [observation], [_obs("volume", "h1", "pid=4242", START, 2.0)]
    )

    assert targets == ["uid=alpha"]
    assert skipped == [("pid=4242", "budget")]


def test_the_graph_keeps_a_share_of_the_history_budget(monkeypatch: Any) -> None:
    monkeypatch.setattr(graph_hunt, "HISTORY_TERMS", 3)
    monkeypatch.setattr(graph_hunt, "HISTORY_TRIGGER_TERMS", 1)
    observations = [_obs("value", "h1", "t1", START, 9.0), _obs("value", "h1", "t2", START, 8.0)]
    provisional = [_obs("volume", "h1", name, START, 1.0) for name in ("g1", "g2", "g3")]

    targets, skipped = graph_hunt.history_plan(
        {"t1", "t2", "g1", "g2", "g3"}, observations, provisional
    )

    assert targets == ["t1", "g1", "g2"]
    assert skipped == [("g3", "budget"), ("t2", "budget")]


def test_a_value_that_is_not_a_term_is_recorded_not_dropped() -> None:
    observation = _obs("value", "h1", "msg=a,b", START, 9.0)

    targets, skipped = graph_hunt.history_plan({"msg=a,b"}, [observation], [])

    assert targets == []
    assert skipped == [("msg=a,b", "not_a_term")]


def test_a_censored_history_read_makes_coverage_incomplete(
    tmp_path: Path, monkeypatch: Any
) -> None:
    class CensoredExecutor(FakeExecutor):
        def read(
            self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
        ) -> SimpleNamespace:
            if query.startswith("| tstats") and 'TERM("pid=4242")' in query:
                self.calls.append({"query": query, "start": start, "end": end, "kind": kind})
                return SimpleNamespace(rows=[], censored=True, reason="query_bound")
            return super().read(query, start, end, kind=kind, row_cap=row_cap)

    out = _run(tmp_path, monkeypatch, CensoredExecutor())
    progress = json.loads((out / "progress.json").read_text())
    history = progress["history"]

    assert history["requested"] == 2
    assert history["read"] == 1
    assert {"entity": "pid=4242", "reason": "query_bound"} in history["skipped"]
    assert progress["coverage"]["history_censored"] == 1
    assert progress["coverage"]["reasons"] == ["query_bound"]
    assert progress["request_kinds"]["history"]["censored"] == 1
    assert progress["coverage_complete"] is False


def test_censored_cell_makes_coverage_incomplete(tmp_path: Path, monkeypatch: Any) -> None:
    out = _run(tmp_path, monkeypatch, FakeExecutor(censored_hosts=frozenset({"h2"})))
    cells = [json.loads(line) for line in (out / "cells.jsonl").read_text().splitlines()]
    progress = json.loads((out / "progress.json").read_text())

    assert [cell["censored"] for cell in cells] == [False, False, False, True, True]
    assert progress["coverage"]["cells_censored"] == 2
    assert progress["coverage"]["reasons"] == ["query_bound"]
    assert progress["coverage_complete"] is False


def test_saved_grids_for_another_index_are_refused(tmp_path: Path, monkeypatch: Any) -> None:
    saved = _saved(tmp_path, [_obs("volume", "h2", "", START, 5.0)])
    monkeypatch.setattr(graph_hunt, "_graph", _fake_graph()[0])
    monkeypatch.setattr(graph_hunt, "_executor", FakeExecutor())
    monkeypatch.setattr(
        "sys.argv",
        [
            "graph_hunt.py",
            "--index",
            "other",
            "--out",
            str(tmp_path / "out"),
            "--from-grids",
            str(saved),
        ],
    )

    with pytest.raises(SystemExit, match="does not match"):
        graph_hunt.main()


@pytest.mark.parametrize("name", ["leads.json", "notables.jsonl", "cells.jsonl", "progress.json"])
def test_runner_writes_every_documented_file(tmp_path: Path, monkeypatch: Any, name: str) -> None:
    assert (_run(tmp_path, monkeypatch) / name).exists()
