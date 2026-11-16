from __future__ import annotations

from dataclasses import replace

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
    identity_plan,
    identity_stats,
    keyed_rows,
    load_behaviours,
    load_source_stats,
    per_window_events,
    reproduction_query,
    window_bounds,
)
from portal.modules.security.core.hunt.notables.cards import SourceCard
from portal.modules.security.core.hunt.notables.receipt import read_json, write_json
from portal.modules.security.core.hunt.notables.run import _write_role_overrides
from portal.modules.security.core.hunt.notables.sample import SourceFacts


def _card(roles: dict[str, tuple[str, ...]] | None = None, fmt: str = "json") -> SourceCard:
    return SourceCard(
        index="ix",
        sourcetype="st",
        kind="activity",
        roles=roles or {"actor": ("user",), "action": ("image",), "object": ("path",)},
        understood=True,
        reason=None,
        fmt=fmt,
        coverage=1.0,
        fields=(),
        sample={},
        facts={},
        model={},
        cache_key="key",
    )


def _facts() -> SourceFacts:
    return SourceFacts("ix", "st", 10, 0.0, 7200.0, ("h1",), 1, ("s1",), 1)


def test_reproduction_query_drops_star_adjacent_role_values() -> None:
    query = reproduction_query(_facts(), ["alpha*medium*verylongsegment"])

    assert "verylongsegment" not in query
    assert "medium" not in query
    assert "*" not in query


def _event(
    ts: float,
    user: str = "",
    *,
    image: str = "cmd.exe",
    path: str = "",
    pid: str = "",
    program: str = "",
    template: str = "",
    v1: str = "",
    v2: str = "",
) -> ExampleEvent:
    fields = {
        "user": user,
        "image": image,
        "path": path,
        "pid": pid,
        "program": program,
        "template": template,
        "v1": v1,
        "v2": v2,
    }
    return ExampleEvent(
        "ix:st",
        "h1",
        ts,
        "raw",
        {name: value for name, value in fields.items() if value},
        0.0,
        3600.0,
    )


def _identity_events() -> list[ExampleEvent]:
    """bob and amy recur across two hours; pid is new on every event."""
    events = [
        _event(1.0, "bob", pid="7916"),
        _event(2.0, "bob", pid="7917"),
        _event(3.0, "amy", pid="7918"),
        _event(3601.0, "bob", pid="7919"),
        _event(3602.0, "bob", pid="7920"),
        _event(3603.0, "amy", pid="7921"),
    ]
    for index, event in enumerate(events):
        event.fields["path"] = f"/tmp/{index}"  # type: ignore[index]
    return events


def test_identity_needs_recurrence_across_events_and_hours():
    stats = identity_stats(["user", "pid"], _identity_events())
    assert stats["user"].present == 6
    assert stats["user"].distinct == 2
    assert stats["user"].recurrence == 3.0
    assert stats["user"].bucket_share == 1.0
    assert stats["user"].identity is True
    assert stats["pid"].distinct == 6
    assert stats["pid"].identity is False


def test_identities_in_a_short_sample_are_judged_on_its_own_span():
    events = [_event(float(ts), "bob" if (ts // 60) % 2 else "amy") for ts in range(0, 600, 60)]
    stats = identity_stats(["user"], events)
    assert stats["user"].identity is True


def test_the_actor_is_the_first_identity_field_and_the_override_is_recorded():
    card = _card(
        {
            "actor": ("pid", "user"),
            "action": ("image",),
            "object": ("path",),
        }
    )
    plan = identity_plan(card, _identity_events())
    assert plan.actor_field == "user"
    assert plan.actor_mode == "literal"
    assert plan.overrides[0]["role"] == "actor"
    assert plan.overrides[0]["chosen"] == "user"
    assert plan.overrides[0]["first_present"] == "pid"


def test_a_field_with_no_identity_is_generalised_and_a_constant_stays_literal():
    card = _card({"actor": ("pid",), "action": ("image",), "object": ("path",)})
    plan = identity_plan(card, _identity_events())
    assert plan.actor_field == "pid"
    assert plan.actor_mode == "shape"
    assert plan.action_mode == "literal"  # constant image
    assert plan.overrides[0]["mode"] == "shape"


def test_behaviour_key_uses_the_plan_modes():
    card = _card({"actor": ("pid", "user"), "action": ("image",), "object": ("path",)})
    plan = identity_plan(card, _identity_events())
    fields = {"pid": "7916", "user": "bob", "image": "cmd.exe", "path": "/tmp/1"}
    assert behaviour_key(card, fields, plan) == (
        "user",
        "bob",
        "image",
        "cmd.exe",
        "path",
        "*",
    )


def test_keyed_row_reproduces_every_literal_part_of_the_key():
    card = _card()
    rows = keyed_rows(card, _facts(), _identity_events())
    assert len(rows) == 6
    query = str(rows[0][13])
    assert '"bob"' not in query
    assert '"cmd.exe"' in query
    assert "TERM(" not in query
    assert "/tmp/0" not in query
    assert 'index="ix"' in query
    assert rows[0][14] == 0.0 and rows[0][15] == 3600.0


def test_an_identity_over_the_value_budget_is_generalised(monkeypatch):
    monkeypatch.setattr(
        "portal.modules.security.core.hunt.notables.behaviours.IDENTITY_VALUE_BUDGET", 1
    )
    card = _card()
    plan = identity_plan(card, _identity_events())
    assert plan.actor_mode == "shape"
    rows = keyed_rows(card, _facts(), _identity_events(), plan)
    query = str(rows[0][13])
    assert '"bob"' not in query
    assert '"cmd.exe"' in query
    assert "TERM(" not in query


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
    events, matched, unparsed = _extract(card, rows, [(0.0, 10.0)])
    assert [event.fields["user"] for event in events] == ["bob", "amy"]
    assert matched == {0, 2}
    assert unparsed == 0


def test_a_template_behaviour_is_program_template_and_identity_slots():
    card = _card(
        {"actor": ("program",), "action": ("template",), "object": ("v1", "v2")},
        fmt="template",
    )
    events = [
        _event(1.0, program="sshd", template="Accepted *", v1="bob", v2="10.0.0.5"),
        _event(2.0, program="sshd", template="Accepted *", v1="amy", v2="10.0.0.6"),
        _event(3601.0, program="sshd", template="Accepted *", v1="bob", v2="10.0.0.5"),
        _event(3602.0, program="sshd", template="Accepted *", v1="amy", v2="10.0.0.6"),
    ]
    plan = identity_plan(card, events)
    assert plan.actor_field == "program"
    assert [mode for _name, mode in plan.objects] == ["literal", "literal"]
    key = behaviour_key(card, events[0].fields, plan)
    assert key == ("program", "sshd", "template", "Accepted *", "slots", "bob 10.0.0.5")
    query = str(keyed_rows(card, _facts(), events, plan)[0][13])
    assert '"sshd"' in query
    assert '"bob"' not in query
    assert '"10.0.0.5"' in query
    assert "TERM(" not in query


def test_a_template_without_a_program_takes_its_first_identity_slot_as_actor():
    card = _card(
        {"actor": ("program",), "action": ("template",), "object": ("v1", "v2")}, fmt="template"
    )
    events = [
        _event(1.0, template="* - - *", v1="1.2.3.4", v2="GET"),
        _event(2.0, template="* - - *", v1="1.2.3.5", v2="GET"),
        _event(3601.0, template="* - - *", v1="1.2.3.4", v2="POST"),
        _event(3602.0, template="* - - *", v1="1.2.3.5", v2="POST"),
    ]
    plan = identity_plan(card, events)
    assert plan.actor_field == "v1"
    assert plan.overrides[0]["reason"] == "first_identity_slot"


def test_an_event_with_neither_actor_nor_object_is_not_a_behaviour():
    card = _card({"actor": ("user",), "action": ("image",), "object": ()})
    event = _event(1.0, image="stats")
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


def test_behaviours_use_only_activity_part_of_a_mixed_source(tmp_path):
    activity = replace(
        _card({"actor": ("src",), "action": ("proto",), "object": ("dst",)}),
        part_field="event_type",
        part_value="flow",
    )
    alert = replace(
        activity,
        kind="alert",
        roles={"actor": ("src",), "action": ("sig",)},
        part_value="alert",
    )
    measurement = replace(activity, kind="measurement", roles={}, part_value="stats")
    rows = [
        {
            "_raw": '{"event_type":"flow","src":"a","proto":"TCP","dst":"b"}',
            "_time": 1.0,
            "host": "h1",
        },
        {
            "_raw": '{"event_type":"flow","src":"a","proto":"TCP","dst":"b"}',
            "_time": 3601.0,
            "host": "h1",
        },
        {"_raw": '{"event_type":"alert","src":"a","sig":"scan"}', "_time": 2.0, "host": "h1"},
        {"_raw": '{"event_type":"stats","cpu":"0.4"}', "_time": 3.0, "host": "h1"},
    ]

    behaviours, receipt = collect_behaviours(
        _RowsExecutor(rows),  # type: ignore[arg-type]
        [activity, alert, measurement],
        {"ix:st": SourceFacts("ix", "st", 4, 0.0, 7200.0, ("h1",), 1, ("s1",), 1)},
        tmp_path / "mixed.duckdb",
    )

    assert [(item.action, item.object) for item in behaviours] == [("TCP", "b")]
    assert [item["card_id"] for item in receipt["receipts"]] == [activity.card_id]


def test_each_source_reports_behaviours_and_singletons(tmp_path):
    card = _card({"actor": ("user",), "action": ("image",), "object": ()})
    rows = [
        {"_raw": '{"user": "bob", "image": "cmd.exe"}', "_time": 1.0, "host": "h1"},
        {"_raw": '{"user": "bob", "image": "cmd.exe"}', "_time": 3601.0, "host": "h1"},
        {"_raw": '{"user": "bob", "image": "cmd.exe"}', "_time": 3602.0, "host": "h2"},
        {"_raw": '{"user": "amy", "image": "cmd.exe"}', "_time": 2.0, "host": "h1"},
        {"_raw": '{"user": "amy", "image": "cmd.exe"}', "_time": 3603.0, "host": "h1"},
    ]
    behaviours, receipt = collect_behaviours(
        _RowsExecutor(rows),  # type: ignore[arg-type]
        [card],
        {"ix:st": SourceFacts("ix", "st", 5, 0.0, 7200.0, ("h1",), 1, ("s1",), 1)},
        tmp_path / "b.duckdb",
    )
    assert len(behaviours) == 2
    entry = receipt["receipts"][0]
    assert entry["behaviours"] == 2
    assert entry["singletons"] == 0
    assert entry["singleton_share"] == 0.0
    assert entry["identity"]["actor"]["field"] == "user"


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


def test_role_overrides_are_written_back_onto_the_cards(tmp_path):
    write_json(
        tmp_path / "sources.json",
        {"cards": [{"card_id": "ix:st", "source_id": "ix:st"}, {"card_id": "ix:other"}]},
    )
    _write_role_overrides(tmp_path, {"ix:st": {"actor": {"field": "user", "mode": "literal"}}})
    payload = read_json(tmp_path / "sources.json")
    assert payload["cards"][0]["role_overrides"]["actor"]["field"] == "user"
    assert "role_overrides" not in payload["cards"][1]


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
        "INSERT INTO events VALUES (" + ",".join("?" for _ in range(16)) + ")",
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
            "literal",
            "literal",
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
            "literal",
            "literal",
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
            "literal",
            "literal",
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
    assert (top.actor_mode, top.action_mode, top.object_mode) == ("literal", "literal", "shape")
    assert [item.actor for item in behaviours] == ["bob", "amy"]
    loaded = load_behaviours(path)
    assert len(loaded) == 2
    stats = load_source_stats(path)
    assert stats["ix:st"] == {"hosts_possible": 2, "actors_possible": 2}
