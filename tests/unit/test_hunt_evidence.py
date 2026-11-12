from __future__ import annotations

from portal.modules.security.core.hunt.engine import HOUR
from portal.modules.security.core.hunt.evidence import (
    EVENTS_PER_OBSERVATION,
    MAX_EVENT_CHARACTERS,
    MAX_OBSERVATIONS_PER_CELL,
    evidence_cells,
    read_cell,
)
from portal.modules.security.core.hunt.observations import Observation, literal_query

INDEX = "events"


def _observation(kind: str, entity: str, hour: int, score: float) -> Observation:
    return Observation(
        kind,
        "node-a",
        entity,
        hour,
        score,
        {"signal": "burst", "literal": literal_query(kind, INDEX, "node-a", entity)},
    )


def test_evidence_cells_keep_layer_one_order():
    rows = [
        _observation("shape", f"p{index}", 2 * HOUR, float(30 - index))
        for index in range(MAX_OBSERVATIONS_PER_CELL + 1)
    ] + [_observation("source", "svc\tlog", HOUR, 1.0)]

    cells = evidence_cells(rows)

    assert [(cell.host, cell.hour, cell.l1_rank) for cell in cells] == [
        ("node-a", 2 * HOUR, 1),
        ("node-a", HOUR, 2),
    ]
    assert len(cells[0].observations) == MAX_OBSERVATIONS_PER_CELL + 1
    assert [obs.entity for obs in cells[0].observations] == [
        f"p{index}" for index in range(MAX_OBSERVATIONS_PER_CELL + 1)
    ]


class _Executor:
    def __init__(self, rows, reason=None):
        self.rows = rows
        self.reason = reason
        self.calls = []

    def read(self, query, earliest, latest, *, kind, row_cap):
        self.calls.append((query, earliest, latest, kind, row_cap))
        return type("Read", (), {"rows": self.rows, "reason": self.reason})()


def test_one_bounded_read_returns_only_matching_events_with_reproducible_bounds():
    shape = _observation("shape", "abc", HOUR, 4.0)
    source = _observation("source", "svc\tlog", HOUR, 3.0)
    cell = evidence_cells([shape, source])[0]
    rows = [
        {
            "_time": HOUR + 1,
            "host": "node-a",
            "source": "svc",
            "sourcetype": "log",
            "punct": "abc",
            "_raw": "x" * 350,
        },
        {
            "_time": HOUR + 2,
            "host": "node-a",
            "source": "svc",
            "sourcetype": "log",
            "punct": "abc",
            "_raw": "y=2\nz=3",
        },
        {
            "_time": HOUR + 3,
            "host": "node-a",
            "source": "other",
            "sourcetype": "log",
            "punct": "zzz",
            "_raw": "z=3",
        },
    ]
    executor = _Executor(rows)

    result = read_cell(executor, INDEX, cell, HOUR, 3 * HOUR)

    assert len(executor.calls) == 1
    query, earliest, latest, kind, row_cap = executor.calls[0]
    assert "append" not in query
    assert f"dedup {EVENTS_PER_OBSERVATION} punct source" in query
    assert "sort 0 _time _raw source punct sourcetype" in query
    assert (earliest, latest, kind) == (HOUR, 2 * HOUR, "evidence")
    assert row_cap is None
    assert result.reason is None
    assert result.evidence
    assert all(item["earliest"] == HOUR and item["latest"] == 2 * HOUR for item in result.evidence)
    assert all(
        len(item["line"].split(" | ", 1)[1]) <= MAX_EVENT_CHARACTERS for item in result.evidence
    )
    assert all("\n" not in item["line"] for item in result.evidence)
    assert all(
        item["query"] in {shape.evidence["literal"], source.evidence["literal"]}
        for item in result.evidence
    )
    assert result == read_cell(_Executor(rows), INDEX, cell, HOUR, 3 * HOUR)


def test_censored_read_keeps_its_reason_and_does_not_claim_evidence():
    observation = _observation("shape", "abc", HOUR, 4.0)
    cell = evidence_cells([observation])[0]

    result = read_cell(_Executor([], "row_cap"), INDEX, cell, 0, 3 * HOUR)

    assert result.censored is True
    assert result.reason == "row_cap"
    assert result.evidence == []


def test_volume_only_cell_has_no_narrowing_observations():
    observation = _observation("volume", "", HOUR, 4.0)
    cell = evidence_cells([observation])[0]

    result = read_cell(_Executor([]), INDEX, cell, HOUR, 2 * HOUR)

    assert cell.observations == ()
    assert result.reason == "no_narrowing_observations"
    assert result.evidence == []


def test_executor_censored_read_preserves_available_matching_lines():
    observation = _observation("shape", "abc", HOUR, 4.0)
    cell = evidence_cells([observation])[0]
    row = {
        "_time": HOUR + 1,
        "host": "node-a",
        "source": "svc",
        "sourcetype": "log",
        "punct": "abc",
        "_raw": "x=1",
    }

    result = read_cell(_Executor([row], "row_budget"), INDEX, cell, HOUR, 2 * HOUR)

    assert result.censored is True
    assert result.reason == "row_budget"
    assert len(result.evidence) == 1


def test_each_event_is_kept_once_and_a_repeat_does_not_spend_the_observation_budget():
    shapes = [
        _observation("shape", "abc", HOUR, float(100 - index))
        for index in range(MAX_OBSERVATIONS_PER_CELL)
    ]
    later = _observation("source", "svc\tlog", HOUR, 1.0)
    cell = evidence_cells([*shapes, later])[0]
    shared = {
        "_time": HOUR + 1,
        "host": "node-a",
        "source": "svc",
        "sourcetype": "log",
        "punct": "abc",
        "_raw": "shared",
    }
    extra = {
        "_time": HOUR + 2,
        "host": "node-a",
        "source": "svc",
        "sourcetype": "log",
        "punct": "other",
        "_raw": "only-source",
    }

    result = read_cell(_Executor([extra, shared]), INDEX, cell, HOUR, 2 * HOUR)
    again = read_cell(_Executor([shared, extra]), INDEX, cell, HOUR, 2 * HOUR)

    assert len(cell.observations) == MAX_OBSERVATIONS_PER_CELL + 1
    assert [item["line"].split(" | ", 1)[1] for item in result.evidence] == [
        "shared",
        "only-source",
    ]
    assert result.evidence[0]["query"] == shapes[0].evidence["literal"]
    assert result.evidence[1]["query"] == later.evidence["literal"]
    assert [item["line"] for item in again.evidence] == [item["line"] for item in result.evidence]


def test_observation_budget_stops_after_twelve_contributing_observations():
    observations = [
        _observation("shape", f"p{index}", HOUR, float(100 - index))
        for index in range(MAX_OBSERVATIONS_PER_CELL + 1)
    ]
    cell = evidence_cells(observations)[0]
    rows = [
        {
            "_time": HOUR + index,
            "host": "node-a",
            "source": "svc",
            "sourcetype": "log",
            "punct": f"p{index}",
            "_raw": f"e{index}",
        }
        for index in range(MAX_OBSERVATIONS_PER_CELL + 1)
    ]

    result = read_cell(_Executor(rows), INDEX, cell, HOUR, 2 * HOUR)

    assert len(result.evidence) == MAX_OBSERVATIONS_PER_CELL
    assert all(item["query"] != observations[-1].evidence["literal"] for item in result.evidence)


def test_event_chars_overrides_the_default_line_budget():
    observation = _observation("shape", "abc", HOUR, 4.0)
    cell = evidence_cells([observation])[0]
    row = {
        "_time": HOUR + 1,
        "host": "node-a",
        "source": "svc",
        "sourcetype": "log",
        "punct": "abc",
        "_raw": "abcdefghij",
    }

    result = read_cell(_Executor([row]), INDEX, cell, HOUR, 2 * HOUR, event_chars=4)

    assert result.evidence[0]["line"] == "svc | abcd"
