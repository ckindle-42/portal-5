"""Entity spine: cadence episodes, neighbour links, and singletons that never key a behaviour."""

from __future__ import annotations

from pathlib import Path

import duckdb

from portal.modules.security.core.hunt.notables.behaviours import (
    ExampleEvent,
    behaviour_key,
    identity_plan,
)
from portal.modules.security.core.hunt.notables.cards import SourceCard
from portal.modules.security.core.hunt.notables.spine import (
    USER,
    SpineEvent,
    build_spine,
    classify,
    entities_for,
    event_id,
    is_sentinel_value,
    segments,
)


def _event(
    source: str,
    ts: float,
    raw: str,
    *,
    host: str = "h1",
    fields: dict[str, str] | None = None,
) -> SpineEvent:
    return SpineEvent(event_id(source, host, ts, raw), source, "", host, ts, raw, fields or {})


def _episode_rows(path: Path) -> list[tuple[str, str, str, float, float]]:
    con = duckdb.connect(str(path), read_only=True)
    try:
        return con.execute(
            "SELECT source_id, prev_source, next_source, start_time, delta FROM episodes"
        ).fetchall()
    finally:
        con.close()


def test_an_entity_confined_to_one_burst_keeps_one_episode_and_a_gap_splits_it() -> None:
    burst = [1_000.0, 1_060.0, 1_120.0, 1_180.0, 1_240.0]
    assert segments(burst) == [(0, 5)]
    # median gap 60s -> threshold max(300s, 240s); a 6h gap splits, and 5m alone never does
    assert segments([0.0, 60.0, 120.0, 120.0 + 6 * 3600]) == [(0, 3), (3, 4)]
    assert segments([0.0, 299.0]) == [(0, 2)]
    # the 4h cap splits a regular series whose own median would otherwise stretch it
    annual = [index * 5 * 3600.0 for index in range(4)]
    assert segments(annual) == [(0, 1), (1, 2), (2, 3), (3, 4)]


def test_adjacent_sources_on_one_host_link_inside_four_hours_and_not_outside(
    tmp_path: Path,
) -> None:
    events = [
        _event("ix:first", 1_000.0, "10.1.1.1 login"),
        _event("ix:second", 1_000.0 + 2 * 3600, "10.1.1.1 exec"),
        _event("ix:third", 1_000.0 + 10 * 3600, "10.1.1.1 exit"),
    ]
    build_spine(events, tmp_path / "entities.duckdb")
    rows = {row[0]: row for row in _episode_rows(tmp_path / "entities.duckdb")}
    assert rows["ix:first"][1] == "" and rows["ix:first"][2] == "ix:second"
    assert rows["ix:first"][4] == 7200.0
    assert rows["ix:second"][1] == "ix:first" and rows["ix:second"][2] == ""
    assert rows["ix:third"][1] == "" and rows["ix:third"][2] == ""


def test_a_singleton_value_becomes_an_entity_but_never_a_behaviour_key(tmp_path: Path) -> None:
    card = SourceCard(
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
    events = [
        _event("ix:st", 1_000.0, "one", fields={"user": "zoe", "image": "a.exe", "path": "/x"}),
        _event("ix:st", 1_060.0, "two", fields={"user": "abe", "image": "a.exe", "path": "/x"}),
    ]
    build_spine(events, tmp_path / "entities.duckdb")
    con = duckdb.connect(str(tmp_path / "entities.duckdb"), read_only=True)
    try:
        users = {
            row[0]
            for row in con.execute("SELECT value FROM entities WHERE entity_kind='user'").fetchall()
        }
    finally:
        con.close()
    assert {"zoe", "abe"} <= users
    plan = identity_plan(
        card,
        [ExampleEvent("ix:st", "h1", item.ts, item.raw, item.fields, 0.0, 60.0) for item in events],
    )
    actor_field, actor, action_field, action, _object_field, _object = behaviour_key(
        card, events[0].fields, plan
    )
    assert actor_field == "user" and actor != "zoe"
    assert action_field == "image" and action == "a.exe"


def test_an_audit_record_whose_only_identity_is_numeric_carries_an_entity(
    tmp_path: Path,
) -> None:
    raw = (
        "type=LOGIN msg=audit(1642420697.752:2279): pid=20750 uid=0 old-auid=4294967295"
        " auid=1002 tty=(none) old-ses=4294967295 ses=318 res=1"
    )
    named = (
        "type=USER_START msg=audit(1642420697.752:2280): pid=20750 uid=0 auid=1002 ses=318"
        ' msg=\'op=PAM:session_open acct="gmorgan" exe="/lib/systemd/systemd" res=success\''
    )
    build_spine(
        [_event("ix:linux_audit", 1_000.0, raw), _event("ix:linux_audit", 1_060.0, named)],
        tmp_path / "entities.duckdb",
    )
    con = duckdb.connect(str(tmp_path / "entities.duckdb"), read_only=True)
    try:
        entities = set(con.execute("SELECT entity_kind, value FROM entities").fetchall())
        episodes = set(con.execute("SELECT entity_kind, value FROM episodes").fetchall())
    finally:
        con.close()
    assert ("user", "1002") in entities
    assert ("user", "1002") in episodes
    assert ("user", "gmorgan") in entities


def test_the_same_stored_events_rebuild_the_same_episode_boundaries(tmp_path: Path) -> None:
    events = [
        _event("ix:a", 1_000.0, "10.2.2.2 one"),
        _event("ix:a", 1_060.0, "10.2.2.2 two"),
        _event("ix:b", 1_000.0 + 4 * 3600 - 1, "10.2.2.2 three"),
        _event("ix:b", 1_000.0 + 30 * 3600, "10.2.2.2 four"),
    ]
    first = tmp_path / "first.duckdb"
    second = tmp_path / "second.duckdb"
    build_spine(events, first)
    build_spine(events, second)
    assert _episode_rows(first) == _episode_rows(second)
    assert len(_episode_rows(first)) == 3  # both sources split beyond four hours


def test_unset_and_loopback_sentinels_never_anchor_the_spine(tmp_path: Path) -> None:
    sentinels = [
        "4294967295",
        "-1",
        "0.0.0.0",
        "::",
        "127.0.0.1",
        "::1",
        "-",
        "(empty)",
        "(none)",
        "(null)",
        "none",
        "null",
        "n/a",
        "unknown",
        "UNKNOWN",
        "N/A",
    ]
    events = [
        _event("ix:st", 1_000.0 + index, f"user={value}", fields={"user": value})
        for index, value in enumerate(sentinels)
    ]
    events += [
        _event("ix:st", 2_000.0, "root login", fields={"user": "root"}),
        _event("ix:st", 2_060.0, "SYSTEM login", fields={"user": "SYSTEM"}),
        _event("ix:st", 2_120.0, "gmorgan login", fields={"user": "gmorgan"}),
        _event("ix:audit", 2_180.0, "auid=1002", fields={"auid": "1002"}),
        _event("ix:web", 2_300.0, "src=10.1.2.3", fields={"src_ip": "10.1.2.3"}),
    ]
    build_spine(events, tmp_path / "entities.duckdb")
    con = duckdb.connect(str(tmp_path / "entities.duckdb"), read_only=True)
    try:
        entities = set(con.execute("SELECT entity_kind, value FROM entities").fetchall())
        episodes = set(con.execute("SELECT entity_kind, value FROM episodes").fetchall())
    finally:
        con.close()
    values = {value for _kind, value in entities}
    assert not values & {value.casefold() for value in sentinels}
    assert not any(value == "4294967295" for _kind, value in episodes)
    assert {("user", "root"), ("user", "SYSTEM"), ("user", "gmorgan"), ("user", "1002")} <= entities
    assert ("address", "10.1.2.3") in entities


def test_sentinel_predicate_keeps_real_privileged_and_network_identities() -> None:
    for value in ("4294967295", "-1", "0.0.0.0", "::", "127.0.0.1", "::1", "(empty)", "unknown"):
        assert is_sentinel_value(value)
    for value in ("root", "SYSTEM", "gmorgan", "1002", "0", "10.1.2.3", "2001:db8::1", "127.0.0.2"):
        assert not is_sentinel_value(value)
    assert classify("auid", "4294967295") is None
    assert classify("user", "unknown") is None
    assert classify("src_ip", "0.0.0.0") is None
    assert classify("user", "root") is not None
    assert classify("src_ip", "10.1.2.3") is not None


def test_a_typed_field_override_still_drops_sentinel_values() -> None:
    event = _event(
        "ix:st",
        1_000.0,
        "sess=4294967295 actor=gmorgan",
        fields={"sess": "4294967295", "actor": "gmorgan"},
    )
    hits = entities_for(event, {("ix:st", "sess"): USER, ("ix:st", "actor"): USER})
    assert {(hit.kind, hit.value) for hit in hits} == {("user", "gmorgan")}
