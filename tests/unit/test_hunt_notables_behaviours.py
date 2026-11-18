from __future__ import annotations

from portal.modules.security.core.hunt.notables.behaviours import (
    ExampleEvent,
    _extract,
    behaviour_key,
    identity_plan,
    identity_stats,
    keyed_rows,
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
