from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb

from portal.modules.security.core.hunt.notables import behaviours
from portal.modules.security.core.hunt.notables.cards import SourceCard
from portal.modules.security.core.hunt.notables.parse import FieldStat
from portal.modules.security.core.hunt.notables.sample import RowSet, SourceFacts
from portal.modules.security.core.hunt.notables.spine import (
    SpineEvent,
    build_spine,
    entities_for,
    event_id,
)


def _card(
    sourcetype: str,
    kind: str,
    roles: dict[str, tuple[str, ...]] | None = None,
) -> SourceCard:
    return SourceCard(
        index="ot",
        sourcetype=sourcetype,
        kind=kind,
        roles=roles or {},
        understood=True,
        reason=None,
        fmt="json",
        coverage=1.0,
        fields=(FieldStat("reading", 4, 4, ("10", "12", "14"), 4),),
        sample={},
        facts={},
        model={},
        cache_key="key",
    )


def _spine_event(
    source: str,
    ts: float,
    fields: dict[str, str],
    *,
    host: str,
) -> SpineEvent:
    raw = json.dumps(fields)
    return SpineEvent(event_id(source, host, ts, raw), source, "", host, ts, raw, fields)


def test_rtu_addresses_datablock_and_nonstandard_host_get_entities(tmp_path: Path) -> None:
    roles = {
        ("ot:serial", "actor_id"): "actor",
        ("ot:serial", "command_address"): "from",
        ("ot:serial", "response_address"): "to",
        ("ot:serial", "object_id"): "object",
    }
    events = [
        _spine_event(
            "ot:serial",
            1000.0 + offset,
            {
                "actor_id": "3",
                "command_address": "4",
                "response_address": "7",
                "object_id": "DB12",
            },
            host="plc-1",
        )
        for offset in (0, 60)
    ]

    receipt = build_spine(events, tmp_path / "entities.duckdb", roles)

    assert receipt["events_without_entity"] == 0
    assert receipt["entities"] > 0
    con = duckdb.connect(str(tmp_path / "entities.duckdb"), read_only=True)
    try:
        entities = set(con.execute("SELECT entity_kind, value FROM entities").fetchall())
    finally:
        con.close()
    assert ("address", "4") in entities
    assert ("address", "7") in entities
    assert ("address", "3") in entities
    assert ("object", "object_id=DB12") in entities
    assert ("device", "plc-1") in entities


def test_generic_entity_fallback_keeps_placeholder_and_multicast_exclusions() -> None:
    roles = {
        ("ot:serial", "command_address"): "from",
        ("ot:serial", "object_id"): "object",
    }
    event = _spine_event(
        "ot:serial",
        1000.0,
        {"command_address": "224.0.0.251", "object_id": "unknown"},
        host="unknown",
    )

    assert entities_for(event, roles=roles) == []


def _run_behaviours(
    cards: list[SourceCard],
    rows_by_source: dict[str, list[dict[str, Any]]],
    out: Path,
    monkeypatch: Any,
) -> tuple[list[behaviours.Behaviour], dict[str, Any], list[str]]:
    facts = {
        card.source_id: SourceFacts(
            card.index,
            card.sourcetype,
            len(rows_by_source.get(card.source_id, [])),
            0.0,
            100.0,
            ("plc-1",),
            1,
            ("telemetry.json",),
            1,
        )
        for card in cards
    }
    read_sources: list[str] = []
    monkeypatch.setattr(behaviours, "_localise_sources", lambda *_args: ({}, {}))
    monkeypatch.setattr(behaviours, "_burst_windows_by_source", lambda *_args: {})

    def read_source(
        _executor: Any, source_facts: SourceFacts, *_args: Any, **_kwargs: Any
    ) -> RowSet:
        source_id = f"{source_facts.index}:{source_facts.sourcetype}"
        read_sources.append(source_id)
        rows = rows_by_source.get(source_id, [])
        return RowSet(rows=rows, windows=1, events_scanned=len(rows), coverage="whole")

    monkeypatch.setattr(behaviours, "read_behaviour_source", read_source)
    result = behaviours.collect_behaviours(object(), cards, facts, out / "behaviours.duckdb")
    return result[0], result[1], read_sources


def test_mixed_index_keeps_skipping_measurement_cards(tmp_path: Path, monkeypatch: Any) -> None:
    activity = _card("events", "activity", {"actor": ("user",), "action": ("action",)})
    measurement = _card("telemetry", "measurement")
    rows = {
        activity.source_id: [
            {"_time": 10.0, "host": "plc-1", "_raw": '{"user":"operator","action":"start"}'},
        ],
        measurement.source_id: [
            {"_time": 10.0, "host": "plc-1", "_raw": '{"reading":10.0}'},
        ],
    }

    _result, receipt, read_sources = _run_behaviours(
        [activity, measurement], rows, tmp_path / "mixed", monkeypatch
    )

    assert read_sources == [activity.source_id]
    assert any(item["card_id"] == measurement.card_id for item in receipt["skipped"])


def test_measurement_only_index_builds_behaviours_and_spine_entities(
    tmp_path: Path, monkeypatch: Any
) -> None:
    measurement = _card("telemetry", "measurement")
    samples = [(10.0, 10.0), (20.0, 12.0), (30.0, 14.0), (40.0, 90.0)]
    rows = {
        measurement.source_id: [
            {
                "_time": ts,
                "host": "plc-1",
                "_raw": json.dumps({"reading": value, "state": "run"}),
            }
            for ts, value in samples
        ]
    }
    out = tmp_path / "measurement-only"
    out.mkdir()

    result, receipt, read_sources = _run_behaviours([measurement], rows, out, monkeypatch)

    assert read_sources == [measurement.source_id]
    assert receipt["events_read"] == len(samples)
    assert receipt["receipts"][0]["events_keyed"] == len(samples)
    assert result
    assert all(item.actor_field == "host" and item.actor == "plc-1" for item in result)
    assert {item.object for item in result} == {"bin_1", "bin_4"}

    from portal.modules.security.core.hunt.notables.spine import spine_from_store

    (out / "sources.json").write_text(json.dumps({"cards": [measurement.as_dict()]}))
    spine = spine_from_store(out, receipts=receipt["receipts"])
    assert spine["events_without_entity"] == 0
    assert spine["entities"] > 0
