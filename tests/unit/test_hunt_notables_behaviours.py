from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from portal.modules.security.core.hunt.executor import Read
from portal.modules.security.core.hunt.notables.behaviours import (
    _INSERT,
    ExampleEvent,
    _extract,
    aggregate_events,
    anchor_windows,
    behaviour_identity,
    behaviour_key,
    create_events,
    identity_plan,
    identity_stats,
    keyed_rows,
    load_behaviour_peaks,
    load_behaviours,
    per_window_events,
    read_mode_of,
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


def test_per_window_events_allocates_each_source_its_share_of_the_stage_budget() -> None:
    from portal.modules.security.core.hunt.notables.behaviours import (
        BEHAVIOUR_TOTAL_EVENTS,
        BEHAVIOUR_WINDOWS,
    )

    # a lone source may spend its whole share: the old 2500 slice ceiling starved it
    assert per_window_events(1) == BEHAVIOUR_TOTAL_EVENTS // BEHAVIOUR_WINDOWS
    assert per_window_events(1) > 2500
    for sources in (1, 2, 8, 16, 10_000):
        assert per_window_events(sources) >= 1
        assert sources * BEHAVIOUR_WINDOWS * per_window_events(sources) <= BEHAVIOUR_TOTAL_EVENTS


class _SplunkCapExec:
    """Models Splunk: one query returns only its time window's events, capped at maxresultrows."""

    def __init__(self, events: int) -> None:
        self.events = events
        self.calls: list[tuple[float, float, int | None]] = []

    def read(
        self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
    ) -> Read:
        del query, kind
        self.calls.append((start, end, row_cap))
        in_window = [t for t in range(self.events) if start <= t < end]
        count = min(len(in_window), row_cap or 0, 10_000)
        rows = [{"_time": float(t), "host": "h1", "_raw": f"event-{t}"} for t in in_window[:count]]
        return Read(rows, False, None)


def test_a_hundred_thousand_event_lone_source_is_read_whole_not_sampled() -> None:
    from portal.modules.security.core.hunt.notables.behaviours import read_behaviour_source

    facts = SourceFacts("ix", "st", 95_871, 0.0, 95_871.0, ("h1",), 1, ("s1",), 1)
    executor = _SplunkCapExec(95_871)
    read = read_behaviour_source(executor, facts, per_window_events(1))

    assert read.read_mode == "whole"
    assert len(read.rows) == 95_871  # every event, so a 23-row rare burst cannot be sampled away
    assert read.selection == "full source range within allocated row budget"
    # one capped query would stop at 10000; time-bounded sub-windows read the whole source
    assert len(executor.calls) > 1
    assert all(
        len([t for t in range(95_871) if s <= t < e]) <= 10_000 for s, e, _ in executor.calls
    )


def test_a_whole_source_under_the_splunk_ceiling_stays_one_window() -> None:
    from portal.modules.security.core.hunt.notables.behaviours import read_behaviour_source

    facts = SourceFacts("ix", "st", 9_000, 0.0, 9_000.0, ("h1",), 1, ("s1",), 1)
    executor = _SplunkCapExec(9_000)
    read = read_behaviour_source(executor, facts, per_window_events(1))

    assert read.read_mode == "whole"
    assert len(read.rows) == 9_000
    assert len(executor.calls) == 1  # no needless splitting below the ceiling


def test_sampled_slices_keep_the_per_read_ceiling_when_the_share_is_larger() -> None:
    from portal.modules.security.core.hunt.notables.behaviours import (
        BEHAVIOUR_EVENTS_PER_WINDOW,
        read_behaviour_source,
    )

    class _Exec:
        def __init__(self) -> None:
            self.caps: list[int | None] = []

        def read(
            self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
        ) -> Read:
            del query, start, end, kind
            self.caps.append(row_cap)
            return Read([], False, None)

    # too big for its share, so it stays sampled; no slice may read above the old ceiling
    facts = SourceFacts("ix", "st", 5_000_000, 0.0, 2_000_000.0, ("h1",), 1, ("s1",), 1)
    executor = _Exec()
    read = read_behaviour_source(executor, facts, per_window_events(1))

    assert read.read_mode == "sampled"
    assert executor.caps
    assert all((cap or 0) <= BEHAVIOUR_EVENTS_PER_WINDOW for cap in executor.caps)


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


def test_wide_source_read_narrows_to_the_localised_host_window():
    from portal.modules.security.core.hunt.executor import Read
    from portal.modules.security.core.hunt.notables.behaviours import (
        BEHAVIOUR_WINDOWS,
        read_behaviour_source,
    )
    from portal.modules.security.core.hunt.notables.sample import LocalWindow

    class _Exec:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def read(
            self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
        ) -> Read:
            del kind, row_cap
            self.queries.append(query)
            label = "anchored" if 'host="h1"' in query else "base"
            return Read([{"_time": start + 1.0, "host": "h1", "_raw": label}], False, None)

    facts = SourceFacts("ix", "st", 55_000_000, 0.0, 2_000_000.0, ("h1",), 1, ("s1",), 1)
    executor = _Exec()
    read = read_behaviour_source(
        executor,
        facts,
        per_window=100,
        anchors=[LocalWindow("h1", 1000.0, 4600.0, 5000)],
    )
    assert read.read_mode == "anchored"
    assert read.rung == "narrowed_scan"
    assert read.events_scanned >= 5000
    assert read.windows == BEHAVIOUR_WINDOWS
    assert any('host="h1"' in query for query in executor.queries)


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


def test_burst_guided_merge_preserves_duplicate_timestamp_events_and_hourly_burst_slices():
    from portal.modules.security.core.hunt.executor import Read
    from portal.modules.security.core.hunt.notables.behaviours import (
        BEHAVIOUR_SUB_WINDOWS,
        BEHAVIOUR_WINDOWS,
        read_behaviour_source,
    )

    class _DupExec:
        def __init__(self) -> None:
            self.calls: list[tuple[float, float]] = []

        def read(
            self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
        ) -> Read:
            del query, kind, row_cap
            self.calls.append((start, end))
            if start >= 100_000.0 and end <= 114_400.0:
                # 1-hour slices: hit mid-bucket event at +8347s (in 3rd hour 107200..110800)
                if start <= 108_347.0 < end:
                    return Read(
                        [{"_time": 108_347.0, "host": "h1", "_raw": "mid-bucket-burst"}],
                        False,
                        None,
                    )
                return Read([], False, None)
            # Duplicate identical (ts, host, raw) lines like Samba permission-denied floods
            if start <= 500_000.0 < end:
                return Read(
                    [{"_time": 500_000.0, "host": "h1", "_raw": "repeated-line"}] * 10,
                    False,
                    None,
                )
            # An overlapping uniform row inside the burst window must not double-count
            if start <= 108_347.0 < end:
                return Read(
                    [{"_time": 108_347.0, "host": "h1", "_raw": "mid-bucket-burst"}],
                    False,
                    None,
                )
            return Read([], False, None)

    facts = SourceFacts("ix", "st", 100_000, 0.0, 2_000_000.0, ("h1",), 1, ("s1",), 1)
    executor = _DupExec()
    bursts = [(100_000.0 + i * 200_000.0, 114_400.0 + i * 200_000.0) for i in range(4)]
    read = read_behaviour_source(executor, facts, per_window=100, burst_windows=bursts)
    assert sum(1 for row in read.rows if row["_raw"] == "repeated-line") == 10
    assert sum(1 for row in read.rows if row["_raw"] == "mid-bucket-burst") == 1
    assert len(executor.calls) <= BEHAVIOUR_WINDOWS * BEHAVIOUR_SUB_WINDOWS


def test_select_source_bursts_prioritizes_residual_then_fills_with_raw_peaks():
    from portal.modules.security.core.hunt.notables.behaviours import _select_source_bursts

    # Top-2 raw == top-2 residual; bucket 300 is a genuine raw peak during moderate shift,
    # while buckets 400/500 are flat low-z baseline buckets with zero shift.
    per_source_z = {
        "smtp": [
            (7.4, 100.0),
            (3.3, 200.0),
            (0.9, 300.0),
            (0.2, 400.0),
            (0.2, 500.0),
        ]
    }
    shifts = {100.0: 1.3, 200.0: 1.7, 300.0: 0.8, 400.0: 0.0, 500.0: 0.0}
    selected = _select_source_bursts(per_source_z, shifts, limit=4)
    starts = [lo for lo, _hi in selected["smtp"]]
    assert 300.0 in starts
    assert {100.0, 200.0}.issubset(starts)


def test_the_read_receipt_reports_whole_anchored_and_sampled():
    small = SourceFacts("ix", "st", 600, 0.0, 7200.0, ("h1",), 1, ("s1",), 1)
    large = SourceFacts("ix", "big", 40_000_000, 0.0, 7200.0, ("h1",), 1, ("s1",), 1)
    per_window = 100
    anchors = [(1_000.0, 1_200.0), (3_000.0, 3_100.0)]
    assert read_mode_of(small, per_window, ()) == "whole"
    assert read_mode_of(large, per_window, anchors) == "anchored"
    assert read_mode_of(large, per_window, ()) == "sampled"

    inventory = {
        "fields": [
            {
                "source_id": "ix:big",
                "status": "complete",
                "values": [
                    {"value": "a", "events": 9, "first_seen": 1_000.0, "last_seen": 1_100.0},
                    {"value": "b", "events": 3, "first_seen": 1_200.0, "last_seen": 1_200.0},
                    {"value": "c", "events": 1, "first_seen": 9_000.0, "last_seen": 9_000.0},
                ],
            },
            {
                "source_id": "ix:other",
                "status": "complete",
                "values": [
                    {"value": "z", "events": 50, "first_seen": 1_500.0, "last_seen": 1_500.0}
                ],
            },
        ]
    }
    # the two spans on the same source merge; the other source's list is not an anchor here
    assert anchor_windows(inventory, "ix:big") == [(1_000.0, 1_201.0), (9_000.0, 9_001.0)]


def test_the_localisation_receipt_carries_the_window_a_range_outside_it_is_a_scan():
    from portal.modules.security.core.hunt.executor import Read
    from portal.modules.security.core.hunt.notables.behaviours import _localise_sources

    class _Exec:
        def read(
            self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
        ) -> Read:
            del start, end, kind, row_cap
            if "summariesonly=true count min(_time)" in query:
                if "datamodel=Authentication" in query:
                    return Read([{"count": "9", "first": 0.0, "last": 500.0}], False, None)
                return Read([], False, None)
            rows = [{"_time": index * 300.0, "host": "h1", "count": "21"} for index in range(24)]
            return Read(rows, False, None)

    facts = SourceFacts("ix", "st", 55_000_000, 600.0, 7200.0, ("h1",), 1, ("s1",), 1)
    anchors, block = _localise_sources(_Exec(), [("ix:st", [_card()], facts, 0.0)], 100)

    entry = block["indexes"][0]
    assert entry["mechanism"] == "indexed"
    assert entry["coverage"] == "scan"
    assert entry["accel_window"] == [0.0, 501.0]
    assert anchors == {}


class _ModelWindowExecutor:
    """One model's summary holds `window`; every bucket read answers inside its own bounds."""

    def __init__(self, window: tuple[float, float]) -> None:
        self.window = window
        self.calls: list[tuple[str, float, float]] = []

    def read(
        self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
    ) -> Read:
        del kind, row_cap
        self.calls.append((query, start, end))
        if "summariesonly=true count min(_time)" in query:
            if "datamodel=Authentication" in query:
                return Read(
                    [{"count": "9", "first": self.window[0], "last": self.window[1]}], False, None
                )
            return Read([], False, None)
        rows = [
            {"_time": stamp, "host": "h1", "count": "1"}
            for stamp in (start + 300.0 * step for step in range(int((end - start) // 300.0) + 1))
            if start <= stamp < end
        ]
        if rows:
            rows[-1]["count"] = "50"
        return Read(rows, False, None)


def test_a_source_inside_one_models_window_localises_accelerated():
    from portal.modules.security.core.hunt.notables.behaviours import _localise_sources

    inside = SourceFacts("ix", "linux_secure", 55_000_000, 0.0, 7000.0, ("h1",), 1, ("s1",), 1)
    beyond = SourceFacts("ix", "syslog", 55_000_000, 0.0, 9000.0, ("h1",), 1, ("s2",), 1)
    anchors, block = _localise_sources(
        _ModelWindowExecutor((0.0, 7000.0)),
        [("ix:linux_secure", [_card()], inside, 0.0), ("ix:syslog", [_card()], beyond, 0.0)],
        100,
    )

    entries = {entry["source"]: entry for entry in block["indexes"]}
    assert entries["ix:linux_secure"]["mechanism"] == "accelerated"
    assert entries["ix:linux_secure"]["coverage"] == "accelerated"
    assert entries["ix:syslog"]["mechanism"] == "accelerated_partial"
    assert set(anchors) == {"ix:linux_secure", "ix:syslog"}


def test_a_sources_span_is_never_compared_to_the_index_union():
    from portal.modules.security.core.hunt.notables.behaviours import _localise_sources

    early = SourceFacts("ix", "linux_secure", 55_000_000, 1000.0, 2000.0, ("h1",), 1, ("s1",), 1)
    late = SourceFacts("ix", "syslog", 55_000_000, 5000.0, 9000.0, ("h2",), 1, ("s2",), 1)
    executor = _ModelWindowExecutor((0.0, 10_000.0))
    _localise_sources(
        executor,
        [("ix:linux_secure", [_card()], early, 0.0), ("ix:syslog", [_card()], late, 0.0)],
        100,
    )

    bounds = {
        (start, end)
        for query, start, end in executor.calls
        if "summariesonly=true count min(_time)" not in query
    }
    assert (1000.0, 2001.0) in bounds
    assert (5000.0, 9001.0) in bounds
    assert (1000.0, 9000.000001) not in bounds


class _UntunedExecutor:
    """No model holds a summary: every localisation falls to the index aggregate."""

    def __init__(self) -> None:
        self.scans: list[str] = []

    def read(
        self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
    ) -> Read:
        del start, end, kind, row_cap
        if "summariesonly=true count min(_time)" in query:
            return Read([], False, None)
        self.scans.append(query)
        rows = [{"_time": step * 300.0, "host": "h1", "count": "21"} for step in range(24)]
        return Read(rows, False, None)


def test_ten_untuned_sources_share_one_indexed_localise_query():
    """Same width: one index aggregate is fetched and sliced per source, one entry each."""
    from portal.modules.security.core.hunt.notables.behaviours import _localise_sources

    scheduled = [
        (
            f"ix:st{number}",
            [_card()],
            SourceFacts("ix", f"st{number}", 55_000_000, 0.0, 7200.0, ("h1",), 1, ("s1",), 1),
            0.0,
        )
        for number in range(10)
    ]
    executor = _UntunedExecutor()
    anchors, block = _localise_sources(executor, scheduled, 100)

    assert len(executor.scans) == 1  # one indexed scan for the estate, not one per source
    assert len(block["indexes"]) == 10  # E3's invariant: one receipt row per wide source
    assert {entry["mechanism"] for entry in block["indexes"]} == {"indexed"}
    assert anchors == {}  # uniform buckets peak nowhere, as before


def test_collect_behaviours_keeps_s2_value_spans_when_localisation_finds_nothing(tmp_path):
    from portal.modules.security.core.hunt.executor import Read
    from portal.modules.security.core.hunt.notables.behaviours import collect_behaviours

    class _EmptyLocaliser:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def read(
            self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
        ) -> Read:
            del kind, row_cap
            self.queries.append(query)
            if query.startswith("| tstats"):
                return Read([], False, None)
            raw = '{"user": "bob", "image": "cmd.exe", "path": "/tmp/x"}'
            return Read([{"_time": start + 1.0, "host": "h1", "_raw": raw}], False, None)

    facts = SourceFacts("ix", "st", 40_000_000, 0.0, 7200.0, ("h1",), 1, ("s1",), 1)
    inventory = {
        "fields": [
            {
                "source_id": "ix:st",
                "status": "complete",
                "values": [
                    {"value": "a", "events": 9, "first_seen": 4_000.0, "last_seen": 4_600.0},
                ],
            }
        ]
    }
    executor = _EmptyLocaliser()
    _behaviours, receipt = collect_behaviours(
        executor, [_card()], {"ix:st": facts}, tmp_path / "behaviours.duckdb", inventory
    )

    assert receipt["localisation"]["windows"] == 0
    assert any(query.startswith("| tstats") for query in executor.queries)
    source = receipt["receipts"][0]
    assert source["read_mode"] == "anchored"
    assert source["rung"] == "value_spans"
    assert not any('host="h1"' in query for query in executor.queries)


class _BudgetExecutor:
    """A read path with a real request budget: records what it issued and what it declared."""

    def __init__(self, remaining: int) -> None:
        from portal.modules.security.core.hunt.executor import DEFAULT_BUDGETS, HuntBudget

        self.budget = HuntBudget(dict(DEFAULT_BUDGETS) | {"requests": 1_000})
        self.budget.queries = 1_000 - remaining
        self.reads: list[str] = []
        self.skipped: list[tuple[str, str]] = []

    def read(
        self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
    ) -> Any:
        from portal.modules.security.core.hunt.executor import Read

        del kind, row_cap
        self.reads.append(query)
        return Read([{"_time": start + 1.0, "host": "h1", "_raw": "x"}], False, None)

    def record_skipped_read(
        self,
        query: str,
        start: float,
        end: float,
        *,
        source_id: str | None = None,
        part: str | None = None,
        reason: str,
    ) -> None:
        del start, end, source_id, part
        self.skipped.append((query, reason))


def _budget_facts(count: int = 20) -> SourceFacts:
    """Twenty indexed files, largest first, from one wide (peaked) source."""
    from portal.modules.security.core.hunt.notables.sample import IndexFile

    files = tuple(
        sorted(
            (
                IndexFile(f"/var/log/a{index:02d}.log", 1_000 + index * 10, ("h1",))
                for index in range(count)
            ),
            key=lambda item: (-item.events, item.path),
        )
    )
    return SourceFacts(
        "ix",
        "st",
        sum(item.events for item in files),
        0.0,
        7_200.0,
        ("h1",),
        1,
        tuple(item.path for item in files),
        len(files),
        count_cv=1.5,
        files=files,
    )


def _planned_read(remaining: int) -> tuple[Any, _BudgetExecutor]:
    from portal.modules.security.core.hunt.notables.behaviours import read_behaviour_source

    executor = _BudgetExecutor(remaining=remaining)
    return read_behaviour_source(executor, _budget_facts(), per_window=100), executor


def _evidence_reads(executor: _BudgetExecutor) -> list[str]:
    """Evidence reads only; E2's per-window density probes spend from the same request counter."""
    return [query for query in executor.reads if not query.startswith("| tstats")]


def test_the_read_plan_never_exceeds_the_remaining_request_budget():
    issued = {}
    for remaining in (0, 10, 20, 30, 40, 200):
        _read, executor = _planned_read(remaining)
        issued[remaining] = len(_evidence_reads(executor))
        assert issued[remaining] <= remaining, remaining

    read, _executor = _planned_read(40)
    assert 0 < issued[40] < issued[200]
    # 40 requests pay for a19's four probed windows (8) plus 36 evidence-only ones: a19..a11
    assert {item.path for item in read.files if not item.reason} == {
        item.path for item in _budget_facts().files[:9]
    }


def test_a_window_dropped_by_the_planner_is_declared():
    from portal.modules.security.core.hunt.notables.behaviours import read_behaviour_source

    facts = _budget_facts()
    executor = _BudgetExecutor(remaining=40)

    read = read_behaviour_source(executor, facts, per_window=100)

    dropped = [item for item in read.files if item.reason]
    assert {item.path for item in dropped} == {item.path for item in facts.files[9:]}
    assert {item.reason for item in dropped} == {"request_budget_exhausted"}
    assert len(executor.skipped) == len(dropped)
    assert all(reason == "request_budget_exhausted" for _query, reason in executor.skipped)
