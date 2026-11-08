"""Join behavior tests: time chaining, entity binding, stopword df, group graph."""

from __future__ import annotations

from portal.modules.security.core.mawa.events import ParsedEvent
from portal.modules.security.core.mawa.join import (
    DEFAULT_GRAPH_PARAMS,
    DEFAULT_JOIN_PARAMS,
    JoinParams,
    build_groups,
    group_graph,
)

BASE_TS = 1_787_380_200.0


def _event(event_id: int, ts: float, entities: set[str], file: str = "log/a.log") -> ParsedEvent:
    return ParsedEvent(
        event_id=event_id,
        ts=ts,
        source_file=file,
        kind="syslog",
        tag="t",
        pid="",
        message="m",
        fields={},
        entities=frozenset(entities),
        raw="raw",
    )


def test_time_window_chains_consecutive_events() -> None:
    events = [_event(1, BASE_TS, {"path:/x"}), _event(2, BASE_TS + 2, {"path:/y"})]
    groups = build_groups(events)
    assert len(groups) == 1 and groups[0].member_ids == (1, 2)


def test_gap_beyond_time_window_and_no_shared_entity_stays_split() -> None:
    events = [_event(1, BASE_TS, {"path:/x"}), _event(2, BASE_TS + 60, {"path:/y"})]
    groups = build_groups(events)
    assert len(groups) == 2


def test_rare_shared_entity_binds_within_entity_window() -> None:
    events = [
        _event(1, BASE_TS, {"path:/shell.php"}),
        _event(2, BASE_TS + 20, {"path:/shell.php"}),
    ]
    groups = build_groups(
        events, JoinParams(time_window_s=3.0, entity_window_s=30.0, max_entity_df=10)
    )
    assert len(groups) == 1
    assert groups[0].binding_entities == {"path:/shell.php"}


def test_shared_entity_beyond_entity_window_does_not_bind() -> None:
    events = [
        _event(1, BASE_TS, {"path:/shell.php"}),
        _event(2, BASE_TS + 31, {"path:/shell.php"}),
    ]
    groups = build_groups(
        events, JoinParams(time_window_s=3.0, entity_window_s=30.0, max_entity_df=10)
    )
    assert len(groups) == 2


def test_high_df_entity_is_suppressed_as_stopword() -> None:
    busy = "path:/busy"
    events = [_event(1, BASE_TS, {busy}), _event(2, BASE_TS + 20, {busy})]
    events += [_event(100 + i, BASE_TS + 1000.0 + i, {busy, f"path:/p{i}"}) for i in range(10)]
    params = JoinParams(time_window_s=3.0, entity_window_s=30.0, max_entity_df=10)
    groups = build_groups(events, params)
    glued = [g for g in groups if 1 in g.member_ids and 2 in g.member_ids]
    assert not glued


def test_time_edge_crosses_files() -> None:
    events = [
        _event(1, BASE_TS, {"path:/x"}, file="log/auth.log"),
        _event(2, BASE_TS + 1, {"path:/y"}, file="log/syslog"),
    ]
    groups = build_groups(events)
    assert len(groups) == 1 and groups[0].files == {"log/auth.log", "log/syslog"}


def test_group_graph_links_groups_on_mid_frequency_entity() -> None:
    ents = {"path:/shell.php"}
    events = [_event(1, BASE_TS, ents), _event(2, BASE_TS + 300, ents)]
    events += [_event(i, BASE_TS + 20.0 + i, {f"path:/p{i}"}) for i in range(3, 60)]
    groups = build_groups(events)
    by_id = {g.group_id: g for g in groups}
    edges = group_graph(events, groups, DEFAULT_GRAPH_PARAMS)
    g1, g2 = by_id[1], by_id[2]
    pair = [e for e in edges if {e.group_a, e.group_b} == {g1.group_id, g2.group_id}]
    assert pair and pair[0].shared_entities == {"path:/shell.php"}
    assert pair[0].delta_s == 300.0


def test_default_params_are_the_frozen_values() -> None:
    assert (
        JoinParams(time_window_s=3.0, entity_window_s=30.0, max_entity_df=10) == DEFAULT_JOIN_PARAMS
    )
    assert DEFAULT_GRAPH_PARAMS.max_entity_df == 50
