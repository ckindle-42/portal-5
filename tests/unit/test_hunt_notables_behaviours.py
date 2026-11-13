from __future__ import annotations

import duckdb

from portal.modules.security.core.hunt.executor import Read
from portal.modules.security.core.hunt.notables.__main__ import _print_behaviours
from portal.modules.security.core.hunt.notables.behaviours import (
    ExampleEvent,
    _extract,
    aggregate_events,
    behaviour_key,
    collect_behaviours,
    create_events,
    field_modes,
    keyed_rows,
    load_behaviours,
    load_source_stats,
    per_window_events,
    value_shape,
    window_bounds,
)
from portal.modules.security.core.hunt.notables.cards import SourceCard
from portal.modules.security.core.hunt.notables.sample import SourceFacts


def _card() -> SourceCard:
    return SourceCard(
        index="ix",
        sourcetype="st",
        kind="activity",
        roles={"actor": ("user",), "action": ("image",), "object": ("path",)},
        understood=True,
        reason=None,
        fmt="json",
        coverage=1.0,
        fields=(),
        sample={},
        facts={},
        model={},
        cache_key="key",
    )


def _facts() -> SourceFacts:
    return SourceFacts("ix", "st", 10, 0.0, 7200.0, ("h1",), 1, ("s1",), 1)


def _event(index: int, user: str, raw: str = "") -> ExampleEvent:
    return ExampleEvent(
        "ix:st",
        "h1",
        float(index),
        raw or raw,
        {"user": user, "image": "cmd.exe", "path": f"/tmp/{index}"},
        0.0,
        3600.0,
    )


def test_value_shape_keeps_classes_and_field_modes_respect_the_effort_budget(monkeypatch):
    assert value_shape("ab12-CD") == "aa99-aa"
    assert value_shape("") == ""
    events = [_event(index, "bob" if index < 2 else "amy") for index in range(4)]
    modes = field_modes(["user"], events)
    assert modes["user"] == "literal"
    monkeypatch.setattr(
        "portal.modules.security.core.hunt.notables.behaviours.BEHAVIOUR_FIELD_VALUES", 1
    )
    assert field_modes(["user"], events)["user"] == "shape"


def test_behaviour_key_uses_the_first_present_role_field_and_shapes_variety():
    fields = {"user": "bob", "image": "cmd.exe", "path": "/tmp/1"}
    literal = behaviour_key(
        _card(), fields, {"user": "literal", "image": "literal", "path": "shape"}
    )
    assert literal == ("user", "bob", "image", "cmd.exe", "path", "/aaa/9")
    shaped = behaviour_key(
        _card(), fields, {"user": "shape", "image": "literal", "path": "literal"}
    )
    assert shaped[0:2] == ("user", "aaa")


def test_keyed_row_reproduces_every_literal_part_of_the_key():
    card = _card()
    rows = keyed_rows(card, _facts(), [_event(7, "bob", "raw line")])
    assert len(rows) == 1
    query = str(rows[0][10])
    assert 'TERM("bob")' in query
    assert 'TERM("cmd.exe")' in query
    assert 'TERM("/tmp/7")' in query
    assert 'index="ix"' in query
    assert rows[0][11] == 0.0 and rows[0][12] == 3600.0


def test_a_generalised_value_is_left_out_of_the_query(monkeypatch):
    monkeypatch.setattr(
        "portal.modules.security.core.hunt.notables.behaviours.BEHAVIOUR_FIELD_VALUES", 1
    )
    card = _card()
    rows = keyed_rows(card, _facts(), [_event(7, "bob"), _event(8, "bob")])
    query = str(rows[0][10])
    assert 'TERM("bob")' in query
    assert "/tmp/7" not in query and "/tmp/8" not in query


def test_a_part_card_keys_only_its_own_events():
    card = SourceCard(
        index="ix",
        sourcetype="st",
        kind="activity",
        roles={"actor": ("user",), "action": ("image",)},
        understood=True,
        reason=None,
        fmt="json",
        coverage=1.0,
        fields=(),
        sample={},
        facts={},
        model={},
        cache_key="key",
        part_field="kind",
        part_value="run",
    )
    rows = [
        {"_raw": '{"kind": "run", "user": "bob", "image": "cmd.exe"}', "_time": 1.0},
        {"_raw": '{"kind": "stats", "user": "bob", "image": "cmd.exe"}', "_time": 2.0},
        {"_raw": '{"kind": "run", "user": "amy", "image": "cmd.exe"}', "_time": 3.0},
    ]
    events = _extract(card, rows, [(0.0, 10.0)])
    assert [event.fields["user"] for event in events] == ["bob", "amy"]


def test_a_template_behaviour_is_program_template_and_slot_values():
    card = SourceCard(
        index="ix",
        sourcetype="st",
        kind="activity",
        roles={"actor": ("program",), "action": ("template",), "object": ("s1", "s2")},
        understood=True,
        reason=None,
        fmt="template",
        coverage=1.0,
        fields=(),
        sample={},
        facts={},
        model={},
        cache_key="key",
    )
    fields = {
        "program": "sshd",
        "template": "Accepted password for *",
        "s1": "bob",
        "s2": "10.0.0.5",
    }
    key = behaviour_key(card, fields, {"s1": "literal", "s2": "literal"})
    assert key == (
        "program",
        "sshd",
        "template",
        "Accepted password for *",
        "slots",
        "bob 10.0.0.5",
    )
    event = ExampleEvent("ix:st", "h1", 1.0, "raw", fields, 0.0, 3600.0)
    query = str(keyed_rows(card, _facts(), [event])[0][10])
    assert 'TERM("sshd")' in query
    assert 'TERM("bob")' in query
    assert 'TERM("10.0.0.5")' in query
    assert "Accepted password" not in query


def test_an_event_with_neither_actor_nor_object_is_not_a_behaviour():
    card = _card()
    event = ExampleEvent("ix:st", "h1", 1.0, "raw", {"image": "stats"}, 0.0, 3600.0)
    assert keyed_rows(card, _facts(), [event]) == []


def test_a_skipped_source_receipt_carries_its_source_id(tmp_path):
    card = SourceCard(
        index="ix",
        sourcetype="st",
        kind="other",
        roles={},
        understood=False,
        reason="unparsed_sample:coverage=0.00",
        fmt="text",
        coverage=0.0,
        fields=(),
        sample={},
        facts={},
        model={},
        cache_key="key",
    )
    _behaviours, receipt = collect_behaviours(None, [card], {}, tmp_path / "b.duckdb")  # type: ignore[arg-type]
    assert receipt["skipped"] == [
        {
            "card_id": "ix:st",
            "source_id": "ix:st",
            "reason": "unparsed_sample:coverage=0.00",
            "behaviours": 0,
        }
    ]


class _RowsExecutor:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def read(
        self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
    ) -> Read:
        del query, start, end, kind, row_cap
        return Read([dict(row) for row in self.rows], False, None)


def test_each_source_reports_its_own_distinct_behaviour_count(tmp_path):
    card = SourceCard(
        index="ix",
        sourcetype="st",
        kind="activity",
        roles={"actor": ("user",), "action": ("image",)},
        understood=True,
        reason=None,
        fmt="json",
        coverage=1.0,
        fields=(),
        sample={},
        facts={},
        model={},
        cache_key="key",
    )
    rows = [
        {"_raw": '{"user": "bob", "image": "cmd.exe"}', "_time": 1.0, "host": "h1"},
        {"_raw": '{"user": "bob", "image": "cmd.exe"}', "_time": 2.0, "host": "h2"},
        {"_raw": '{"user": "amy", "image": "cmd.exe"}', "_time": 3.0, "host": "h1"},
    ]
    behaviours, receipt = collect_behaviours(
        _RowsExecutor(rows),  # type: ignore[arg-type]
        [card],
        {"ix:st": SourceFacts("ix", "st", 3, 0.0, 3600.0, ("h1",), 1, ("s1",), 1)},
        tmp_path / "b.duckdb",
    )
    assert len(behaviours) == 2
    assert receipt["receipts"][0]["behaviours"] == 2


def test_the_behaviour_printer_survives_a_partial_receipt(capsys):
    _print_behaviours(
        [],
        {
            "receipts": [{"source_id": "ix:st"}],
            "skipped": [{"card_id": "ix:other", "reason": "no_roles"}],
        },
    )
    output = capsys.readouterr().out
    assert "skipped ix:other: no_roles" in output
    assert "behaviours: events_read=0" in output


def test_window_bounds_slices_a_range_deterministically():
    bounds = window_bounds(0.0, 120.0, 3)
    assert bounds == [(0.0, 40.0), (40.0, 80.0), (80.0, 120.0)]
    assert window_bounds(5.0, 5.0, 2) == [(5.0, 3605.0)]


def test_per_window_events_never_exceeds_the_slice_budget():
    assert per_window_events(1) > 0
    assert per_window_events(1) <= 2500
    assert per_window_events(10_000) >= 1


def _insert(con: duckdb.DuckDBPyConnection, row: tuple[object, ...]) -> None:
    con.execute(
        "INSERT INTO events VALUES (" + ",".join("?" for _ in range(13)) + ")",
        list(row),
    )


def test_aggregate_counts_behaviours_and_source_possible_sharers(tmp_path):
    path = tmp_path / "store.duckdb"
    con = duckdb.connect(str(path))
    try:
        create_events(con)
        base = (
            "ix:st",
            "h1",
            10.0,
            "user",
            "bob",
            "image",
            "cmd.exe",
            "path",
            "shape",
            "raw",
            "q",
            0.0,
            60.0,
        )
        second = (
            "ix:st",
            "h2",
            20.0,
            "user",
            "bob",
            "image",
            "cmd.exe",
            "path",
            "shape",
            "raw",
            "q",
            0.0,
            60.0,
        )
        other = (
            "ix:st",
            "h1",
            30.0,
            "user",
            "amy",
            "image",
            "cmd.exe",
            "path",
            "shape",
            "raw",
            "q",
            0.0,
            60.0,
        )
        for row in (base, second, other):
            _insert(con, row)
        behaviours, existed = aggregate_events(con)
    finally:
        con.close()
    assert existed == 2
    top = behaviours[0]
    assert (top.actor, top.action, top.events, top.hosts) == ("bob", "cmd.exe", 2, 2)
    assert (top.example_earliest, top.example_latest) == (10.0, 20.0)
    assert [item.actor for item in behaviours] == ["bob", "amy"]
    loaded = load_behaviours(path)
    assert len(loaded) == 2
    stats = load_source_stats(path)
    assert stats["ix:st"] == {"hosts_possible": 2, "actors_possible": 2}
