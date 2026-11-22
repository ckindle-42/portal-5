from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from portal.modules.security.core.hunt.engine import HOUR
from portal.modules.security.core.hunt.evidence import (
    MAX_OBSERVATIONS_PER_CELL,
    _observation_tests,
    accumulated_host_hours,
    evidence_cells,
    read_cell,
    read_cells,
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


def test_value_observation_keeps_whole_minor_phrases_and_drops_unclean_values() -> None:
    observation = Observation("value", "node-a", "alpha=medium=verylongsegment", HOUR, 1.0, {})
    unclean = Observation("value", "node-a", "foo^bar", HOUR, 1.0, {})

    search, evaluate = _observation_tests(observation)  # type: ignore[misc]

    assert search == '"alpha=medium=verylongsegment" "verylongsegment"'
    assert evaluate.count("searchmatch(") == 2
    assert " AND " in evaluate
    assert _observation_tests(unclean) is None


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


class _Recorder:
    """Fake executor: records the issued evidence query, returns a fixed row set."""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []
        self.queries: list[str] = []

    def read(
        self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
    ) -> Any:
        self.queries.append(query)
        return SimpleNamespace(rows=list(self.rows), reason=None)


def _cell(observation: Observation) -> Any:
    return evidence_cells([observation])[0]


def test_observation_tests_use_the_search_time_name_when_a_rename_applies() -> None:
    renames = {"wineventlog:security": "WinEventLog", "fgt_traffic": "fortigate_traffic"}
    source = Observation("source", "node-a", "svc\tWinEventLog:Security", HOUR, 1.0, {})
    stream = Observation("stream", "node-a", "fgt_traffic\tabc", HOUR, 1.0, {})

    search, evaluate = _observation_tests(source, renames)
    stream_search, stream_evaluate = _observation_tests(stream, renames)

    assert search == 'source="svc" sourcetype="WinEventLog"'
    assert evaluate == 'source="svc" AND sourcetype="WinEventLog"'
    assert stream_search == 'sourcetype="fortigate_traffic" punct="abc"'
    assert stream_evaluate == 'sourcetype="fortigate_traffic" AND punct="abc"'


def test_observation_tests_keep_the_indexed_name_without_a_rename() -> None:
    source = Observation("source", "node-a", "svc\tWinEventLog:Security", HOUR, 1.0, {})
    stream = Observation("stream", "node-a", "fgt_traffic\tabc", HOUR, 1.0, {})

    assert _observation_tests(source) == (
        'source="svc" sourcetype="WinEventLog:Security"',
        'source="svc" AND sourcetype="WinEventLog:Security"',
    )
    assert _observation_tests(stream, {}) == (
        'sourcetype="fgt_traffic" punct="abc"',
        'sourcetype="fgt_traffic" AND punct="abc"',
    )


def test_read_cell_searches_the_search_time_name_when_a_rename_applies() -> None:
    recorder = _Recorder()

    read = read_cell(
        recorder,
        INDEX,
        _cell(_observation("stream", "fgt_traffic\tabc", HOUR, 1.0)),
        0.0,
        2 * HOUR,
        renames={"fgt_traffic": "fortigate_traffic"},
    )

    assert 'sourcetype="fortigate_traffic" punct="abc"' in recorder.queries[0]
    assert 'sourcetype="fortigate_traffic" AND punct="abc"' in recorder.queries[0]
    assert "fgt_traffic" not in recorder.queries[0]
    assert read.evidence == []


def test_read_cell_keeps_the_indexed_name_without_a_rename() -> None:
    recorder = _Recorder()

    read_cell(
        recorder, INDEX, _cell(_observation("stream", "fgt_traffic\tabc", HOUR, 1.0)), 0.0, 2 * HOUR
    )

    assert 'sourcetype="fgt_traffic" punct="abc"' in recorder.queries[0]
    assert 'sourcetype="fgt_traffic" AND punct="abc"' in recorder.queries[0]
    assert "fortigate_traffic" not in recorder.queries[0]


def test_read_cells_pass_renames_to_every_cell_read() -> None:
    recorder = _Recorder()

    reads = read_cells(
        recorder,
        INDEX,
        [_cell(_observation("source", "svc\tfgt_traffic", HOUR, 1.0))],
        0.0,
        2 * HOUR,
        renames={"fgt_traffic": "fortigate_traffic"},
    )

    assert len(reads) == 1
    assert 'sourcetype="fortigate_traffic"' in recorder.queries[0]
    assert 'source="svc" AND sourcetype="fortigate_traffic"' in recorder.queries[0]
