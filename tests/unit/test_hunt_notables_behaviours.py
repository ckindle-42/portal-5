from __future__ import annotations

from pathlib import Path

import duckdb

from portal.modules.security.core.hunt.notables.behaviours import (
    _INSERT,
    ExampleEvent,
    _extract,
    aggregate_events,
    behaviour_identity,
    behaviour_key,
    create_events,
    identity_plan,
    identity_stats,
    keyed_rows,
    load_behaviour_peaks,
    load_behaviours,
    per_window_events,
    reproduction_query,
    window_bounds,
)
from portal.modules.security.core.hunt.notables.cards import SourceCard
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


def test_behaviour_peaks_use_the_full_stored_key_and_four_hour_buckets(tmp_path: Path):
    card = _card()
    fields = {"user": "45.77.65.211", "image": "TRAFFIC", "path": "ssl"}
    events = [
        ExampleEvent("ix:st", "h1", ts, "raw", fields, 0.0, 14400.0)
        for ts in (100.0, 200.0, 14400.0)
    ]
    rows = keyed_rows(card, _facts(), events)
    path = tmp_path / "behaviours.duckdb"
    connection = duckdb.connect(str(path))
    try:
        create_events(connection)
        connection.executemany(_INSERT, rows)
        aggregate_events(connection)
    finally:
        connection.close()

    behaviours = load_behaviours(path)
    peaks = load_behaviour_peaks(path, 14400.0)

    assert peaks == {behaviour_identity(behaviours[0]): 2}


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


def test_window_bounds_slices_a_range_deterministically():
    bounds = window_bounds(0.0, 120.0, 3)
    assert bounds == [(0.0, 40.0), (40.0, 80.0), (80.0, 120.0)]
    assert window_bounds(5.0, 5.0, 2) == [(5.0, 3605.0)]


def test_per_window_events_never_exceeds_the_slice_budget():
    assert per_window_events(1) > 0
    assert per_window_events(1) <= 2500
    assert per_window_events(10_000) >= 1


def test_source_window_reports_distinct_objects_for_one_actor_and_action():
    from portal.modules.security.core.hunt.notables.generators import _source_deviations
    from portal.modules.security.core.hunt.notables.window_activity import window_activity

    _, firsts, _ = _source_deviations({"st": [(0, 4)]}, "ix", 0)
    seed = firsts[0]
    rows = [
        {"_time": t, "_raw": raw}
        for t, raw in [
            (3, '{"user":"a","image":"retrieve","path":"last.txt"}'),
            (1, '{"user":"a","image":"retrieve","path":"first.txt"}'),
            (2, '{"user":"b","image":"retrieve","path":"other.txt"}'),
            (14400, '{"user":"a","image":"retrieve","path":"outside.txt"}'),
        ]
    ]
    result = window_activity(seed, [_card()], rows, "search index=ix | head 10")
    assert result.basis == "source_first_seen_activity"
    assert result.counts["distinct_objects"] == result.counts["group_rows"] == 2
    assert [x["time"] for x in result.evidence[:2]] == [1, 3]
    assert result.entities == (
        ("actor", "a"),
        ("action", "retrieve"),
        ("object", "first.txt"),
        ("object", "last.txt"),
    )
    assert window_activity(seed, [_card()], rows[:1], "query") is seed


def test_bursty_recurring_identity_stays_literal_despite_single_hour_concentration():
    card = _card({"actor": ("c_ip",), "action": ("method",), "object": ("uri",)})
    events = [
        ExampleEvent(
            "ix:http",
            "h1",
            100.0 + index,
            "raw",
            {"c_ip": "45.77.65.211" if index < 8 else "10.0.0.1", "method": "GET", "uri": "/a"},
            0.0,
            3600.0,
        )
        for index in range(10)
    ]
    # Add one baseline event in a later hour so span spans multiple buckets
    events.append(
        ExampleEvent(
            "ix:http",
            "h1",
            40_000.0,
            "raw",
            {"c_ip": "10.0.0.2", "method": "GET", "uri": "/a"},
            36000.0,
            43200.0,
        )
    )
    plan = identity_plan(card, events)
    assert plan.actor_field == "c_ip"
    assert plan.actor_mode == "literal"


def test_identity_plan_falls_back_to_from_and_to_when_actor_absent_or_object_near_constant():
    card = _card(
        {
            "from": ("source_file",),
            "object": ("blocked_uri",),
            "to": ("document_uri",),
        }
    )
    events = [
        ExampleEvent(
            "ix:csp",
            "h1",
            float(index * 4000),
            "raw",
            {
                "source_file": f"http://site/p{index % 3}",
                "blocked_uri": "inline" if index % 2 == 0 else "self",
                "document_uri": f"http://site/doc{index % 4}",
            },
            0.0,
            36000.0,
        )
        for index in range(12)
    ]
    plan = identity_plan(card, events)
    assert plan.actor_field == "source_file"
    assert plan.actor_mode == "literal"
    assert plan.object_field == "document_uri"
    assert plan.object_mode == "literal"


def test_extract_preserves_structured_raw_beyond_400_chars():
    card = _card({"actor": ("user",), "action": ("action",), "object": ("target",)})
    padding = "x" * 700
    raw = f'{{"pad":"{padding}","user":"alice","action":"create","target":"secret.docx"}}'
    events, matched, unparsed = _extract(card, [{"_time": 10.0, "_raw": raw}], [(0.0, 100.0)])
    assert len(events) == 1 and matched == {0} and unparsed == 0
    assert "secret.docx" in events[0].raw


def test_burst_guided_behaviour_read_combines_uniform_and_peak_windows():
    from portal.modules.security.core.hunt.executor import Read
    from portal.modules.security.core.hunt.notables.behaviours import (
        BEHAVIOUR_SUB_WINDOWS,
        BEHAVIOUR_WINDOWS,
        read_behaviour_source,
    )

    class _Exec:
        def __init__(self) -> None:
            self.calls: list[tuple[float, float]] = []

        def read(
            self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
        ) -> Read:
            del query, kind, row_cap
            self.calls.append((start, end))
            if start <= 100_500.0 < end:
                return Read([{"_time": 100_500.0, "host": "h1", "_raw": "burst-hit"}], False, None)
            return Read(
                [{"_time": start + 1.0, "host": "h1", "_raw": f"base-{start}"}], False, None
            )

    facts = SourceFacts("ix", "st", 100_000, 0.0, 2_000_000.0, ("h1",), 1, ("s1",), 1)
    executor = _Exec()
    read = read_behaviour_source(
        executor, facts, per_window=100, burst_windows=[(100_000.0, 114_400.0)]
    )
    assert any(row["_raw"] == "burst-hit" for row in read.rows)
    assert read.windows == BEHAVIOUR_WINDOWS
    assert len(executor.calls) <= BEHAVIOUR_WINDOWS * BEHAVIOUR_SUB_WINDOWS


def test_window_activity_resolves_from_to_and_preserves_mid_window_burst_slice():
    from portal.modules.security.core.hunt.notables.generators import _source_deviations
    from portal.modules.security.core.hunt.notables.window_activity import window_activity

    # 1. Actorless from/to card with URL-encoded payload past 400 chars
    csp_card = _card(
        {"from": ("source_file",), "object": ("blocked_uri",), "to": ("document_uri",)}
    )
    _, firsts, _ = _source_deviations({"st": [(0.0, 4)]}, "ix", 0.0)
    pad = "p" * 450
    csp_rows = [
        {
            "_time": 10.0,
            "_raw": f'{{"pad":"{pad}","source_file":"http://s/edit?u%3Dmal_user%26p%3D1","blocked_uri":"inline","document_uri":"http://s/a"}}',
        },
        {
            "_time": 20.0,
            "_raw": f'{{"pad":"{pad}","source_file":"http://s/edit?u%3Dmal_user%26p%3D1","blocked_uri":"self","document_uri":"http://s/b"}}',
        },
    ]
    res = window_activity(firsts[0], [csp_card], csp_rows, "search index=ix | head 10")
    assert res.basis == "source_first_seen_activity"
    assert "mal_user" in res.what
    assert "u%3Dmal_user" in str(res.evidence[0]["line"])

    # 2. Mid-window dense burst slice preserved alongside first and last
    rows = [
        {"_time": 10.0, "_raw": '{"user":"a","image":"get","path":"/first"}'},
        {"_time": 5000.0, "_raw": '{"user":"a","image":"get","path":"/burst1"}'},
        {"_time": 5001.0, "_raw": '{"user":"a","image":"get","path":"/burst2"}'},
        {"_time": 5002.0, "_raw": '{"user":"a","image":"get","path":"/burst3"}'},
        {"_time": 10000.0, "_raw": '{"user":"a","image":"get","path":"/last"}'},
    ]
    res2 = window_activity(firsts[0], [_card()], rows, "search index=ix | head 10")
    ev_lines = " ".join(str(item["line"]) for item in res2.evidence)
    assert "/first" in ev_lines and "/last" in ev_lines and "/burst1" in ev_lines
