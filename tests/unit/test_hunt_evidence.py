from __future__ import annotations

from portal.modules.security.core.hunt.engine import HOUR, _search_literal
from portal.modules.security.core.hunt.evidence import (
    CANDIDATE_OBSERVATIONS,
    EVENTS_PER_OBSERVATION,
    MAX_EVENT_CHARACTERS,
    MAX_OBSERVATIONS_PER_CELL,
    ROW_BUDGET,
    _observation_tests,
    accumulated_host_hours,
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

    result = read_cell(executor, INDEX, cell, HOUR, 3 * HOUR, evidence_mode="strongest")

    assert len(executor.calls) == 1
    query, earliest, latest, kind, row_cap = executor.calls[0]
    assert "append" not in query
    assert f"dedup {EVENTS_PER_OBSERVATION} _hunt_observation" in query
    assert f"| head {ROW_BUDGET}" in query
    assert 'punct="abc"' in query
    assert "searchmatch" not in query
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
    assert result == read_cell(
        _Executor(rows), INDEX, cell, HOUR, 3 * HOUR, evidence_mode="strongest"
    )


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

    result = read_cell(
        _Executor([extra, shared]), INDEX, cell, HOUR, 2 * HOUR, evidence_mode="strongest"
    )
    again = read_cell(
        _Executor([shared, extra]), INDEX, cell, HOUR, 2 * HOUR, evidence_mode="strongest"
    )

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


def test_marker_keeps_the_row_on_the_observation_the_read_named():
    shape = _observation("shape", "abc", HOUR, 4.0)
    source = _observation("source", "svc\tlog", HOUR, 3.0)
    cell = evidence_cells([shape, source])[0]
    row = {
        "_time": HOUR + 1,
        "host": "node-a",
        "source": "svc",
        "sourcetype": "log",
        "punct": "abc",
        "_raw": "once",
        "_hunt_observation": 1,
    }

    result = read_cell(_Executor([row]), INDEX, cell, HOUR, 2 * HOUR, evidence_mode="strongest")

    assert len(result.evidence) == 1
    assert result.evidence[0]["query"] == source.evidence["literal"]


def test_query_names_candidates_with_equality_and_bounds_the_rows():
    assert CANDIDATE_OBSERVATIONS > MAX_OBSERVATIONS_PER_CELL
    assert ROW_BUDGET == MAX_OBSERVATIONS_PER_CELL * EVENTS_PER_OBSERVATION
    observations = [_observation("value", 'alpha"beta', HOUR, 1000.0)]
    observations.extend(
        _observation("shape", f"p{index}", HOUR, float(500 - index))
        for index in range(CANDIDATE_OBSERVATIONS)
    )
    cell = evidence_cells(observations)[0]
    executor = _Executor([])

    read_cell(executor, INDEX, cell, HOUR, 2 * HOUR, evidence_mode="strongest")

    query = executor.calls[0][0]
    assert '"alpha" "beta"' in query
    assert "TERM(" not in query
    assert "searchmatch(" in query
    assert f"punct={_search_literal('p0')}" in query
    assert f"punct={_search_literal(f'p{CANDIDATE_OBSERVATIONS - 1}')}" not in query
    assert f"| head {ROW_BUDGET}" in query


def test_value_observation_keeps_whole_minor_phrases_and_drops_unclean_values() -> None:
    observation = Observation("value", "node-a", "alpha=medium=verylongsegment", HOUR, 1.0, {})
    unclean = Observation("value", "node-a", "foo^bar", HOUR, 1.0, {})

    search, evaluate = _observation_tests(observation)  # type: ignore[misc]

    assert search == '"alpha=medium=verylongsegment" "verylongsegment"'
    assert evaluate.count("searchmatch(") == 2
    assert " AND " in evaluate
    assert _observation_tests(unclean) is None


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


def _scored(
    host: str, hour: int, kind: str, score: float | None, entity: str = "abc"
) -> Observation:
    return Observation(
        kind,
        host,
        entity,
        hour,
        score,
        {"signal": "burst", "literal": literal_query(kind, INDEX, host, entity)},
    )


def test_accumulated_host_hours_sum_positive_scores_and_tie_by_layer1_rank():
    rows = [
        _scored("h1", 0, "shape", 5),
        _scored("h2", 0, "shape", 9),
        _scored("h1", 0, "volume", 6, ""),
        _scored("h3", 0, "value", 11, "k=v"),
        _scored("h1", 0, "source", None, "svc\tlog"),
        _scored("h1", 0, "stream", -3, "log\tabc"),
        _scored("h4", 0, "shape", 11, "later"),
        _scored("h5", HOUR, "shape", 0),
    ]

    cells = accumulated_host_hours(rows)

    assert [(cell.host, cell.risk, cell.acc_rank, cell.l1_rank) for cell in cells] == [
        ("h1", 11.0, 1, 1),
        ("h3", 11.0, 2, 3),
        ("h4", 11.0, 3, 4),
        ("h2", 9.0, 4, 2),
        ("h5", 0.0, 5, 5),
    ]
    assert [item.kind for item in cells[0].observations] == ["shape", "source", "stream"]


def _shape(
    entity: str,
    score: float,
    signal: str,
    active: int | None,
    prior_len: int,
) -> Observation:
    return Observation(
        "shape",
        "node-a",
        entity,
        HOUR,
        score,
        {
            "signal": signal,
            "prior_hours_active": active,
            "prior": [{"hour": index, "count": 1} for index in range(prior_len)],
            "literal": literal_query("shape", INDEX, "node-a", entity),
        },
    )


def _event(punct: str, raw: str, stamp: int) -> dict[str, object]:
    return {
        "_time": stamp,
        "host": "node-a",
        "source": "svc",
        "sourcetype": "log",
        "punct": punct,
        "_raw": raw,
    }


def test_rarest_shapes_are_read_one_event_at_a_time_before_a_second():
    fresh = _shape("fresh", 1, "novelty", None, 0)
    unseen = _shape("unseen", 50, "burst", 0, 5)
    rare = _shape("rare", 2, "burst", 1, 10)
    common = _shape("common", 100, "burst", 8, 10)
    same = _shape("same", 3, "burst", 1, 10)
    cell = evidence_cells([common, unseen, rare, same, fresh])[0]
    rows = []
    for entity in ("fresh", "unseen", "rare", "same", "common"):
        rows.append(_event(entity, f"{entity}-1", HOUR + 1))
        rows.append(_event(entity, f"{entity}-2", HOUR + 2))
    executor = _Executor(rows)

    result = read_cell(executor, INDEX, cell, HOUR, 2 * HOUR)

    assert result.evidence_selection == "rarest"
    assert len(executor.calls) == 1
    query = executor.calls[0][0]
    assert "streamstats count as _hunt_nth by _hunt_observation" in query
    assert f"| where _hunt_nth<={EVENTS_PER_OBSERVATION}" in query
    assert f"| head {ROW_BUDGET}" in query
    assert f"dedup {EVENTS_PER_OBSERVATION} _hunt_observation" not in query
    assert [item["line"].split(" | ", 1)[1] for item in result.evidence] == [
        "fresh-1",
        "unseen-1",
        "rare-1",
        "same-1",
        "common-1",
        "fresh-2",
        "unseen-2",
        "rare-2",
        "same-2",
        "common-2",
    ]


def test_rarest_falls_back_to_strongest_when_no_shape_event_matches():
    shape = _observation("shape", "missing", HOUR, 9)
    source = _observation("source", "svc\tlog", HOUR, 1)
    cell = evidence_cells([shape, source])[0]
    row = {
        "_time": HOUR + 1,
        "host": "node-a",
        "source": "svc",
        "sourcetype": "log",
        "punct": "other",
        "_raw": "kept",
    }
    executor = _Executor([row])

    result = read_cell(executor, INDEX, cell, HOUR, 2 * HOUR)

    assert len(executor.calls) == 1
    assert result.evidence_selection == "strongest"
    assert [item["query"] for item in result.evidence] == [source.evidence["literal"]]


def test_rarest_names_shapes_before_other_kinds_inside_the_candidate_budget():
    observations = [_observation("value", 'a"b', HOUR, 1000.0)]
    observations.extend(
        _observation("shape", f"p{index}", HOUR, float(500 - index))
        for index in range(CANDIDATE_OBSERVATIONS)
    )
    cell = evidence_cells(observations)[0]
    executor = _Executor([])

    read_cell(executor, INDEX, cell, HOUR, 2 * HOUR)

    query = executor.calls[0][0]
    assert f"punct={_search_literal('p0')}" in query
    assert f"punct={_search_literal(f'p{CANDIDATE_OBSERVATIONS - 1}')}" in query
    assert "searchmatch" not in query
    assert f"| head {ROW_BUDGET}" in query


def test_aliased_evidence_cell_reads_both_spellings_in_one_query():
    aliases = ("NODE_core", "node-core")
    observation = Observation(
        "shape",
        "NODE_core",
        "abc",
        HOUR,
        4.0,
        {
            "signal": "burst",
            "host_aliases": list(aliases),
            "literal": literal_query("shape", INDEX, "NODE_core", "abc", host_aliases=aliases),
        },
    )
    cell = evidence_cells([observation])[0]
    rows = [
        _event("abc", "first", HOUR + 1) | {"host": "NODE_core"},
        _event("abc", "second", HOUR + 2) | {"host": "node-core"},
    ]
    executor = _Executor(rows)

    result = read_cell(executor, INDEX, cell, HOUR, 2 * HOUR)

    assert cell.host_aliases == aliases
    assert len(executor.calls) == 1
    assert '(host="NODE_core" OR host="node-core")' in executor.calls[0][0]
    assert {item["line"] for item in result.evidence} == {"svc | first", "svc | second"}
    assert all(item["query"] == observation.evidence["literal"] for item in result.evidence)
