"""SA5.4 -- per-event-timestamp HEC batching (bulk corpus ship).

Hermetic: `ship_batch` with a parallel `event_times` list emits one POST whose
events each carry their own original timestamp -- required for bulk corpus
ingest where events span years and per-second batching would otherwise spawn
one HTTP call per second.
"""

from __future__ import annotations

import json

import pytest

from portal.modules.security.core.siem import hec_ship


class _FakePost:
    """Stands in for ``httpx.post`` -- records bodies, returns 200."""

    def __init__(self) -> None:
        self.bodies: list[str] = []

    def __call__(self, url, **kwargs):
        self.bodies.append(kwargs["content"])
        return _FakeResponse()


class _FakeResponse:
    status_code = 200


class _FakeHttpx:
    def __init__(self) -> None:
        self.post = _FakePost()


@pytest.fixture
def recorder(monkeypatch) -> _FakePost:
    fake = _FakeHttpx()
    monkeypatch.setattr(hec_ship, "HEC_TOKEN", "token")
    monkeypatch.setattr(hec_ship, "HEC_URL", "https://splunk:8088")
    monkeypatch.setattr(hec_ship, "httpx", fake)
    return fake.post


def test_ship_batch_event_times_carries_per_event_timestamp(recorder):
    """Each event in one POST carries its own `time` -- the timeline is
    preserved without a per-second HTTP call (SA5.4)."""
    events = [{"eventName": "ListBuckets"}, {"eventName": "ConsoleLogin"}]
    epochs = [1500000000.0, 1550000000.0]
    result = hec_ship.ship_batch(
        events,
        sourcetype="aws:cloudtrail",
        host="corpus-flaws_cloud",
        event_times=epochs,
        evidence_origin="imported_observed",
        evidence_provenance="external_corpus",
    )
    assert result["ok"] is True
    assert len(recorder.bodies) == 1
    lines = recorder.bodies[0].splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["time"] == 1500000000.0
    assert second["time"] == 1550000000.0
    assert first["sourcetype"] == "aws:cloudtrail"
    assert first["fields"]["evidence_origin"] == "imported_observed"


def test_ship_batch_event_times_must_match_event_count(recorder):
    with pytest.raises(ValueError):
        hec_ship.ship_batch(
            [{"a": 1}],
            sourcetype="aws:cloudtrail",
            host="corpus-x",
            event_times=[1.0, 2.0],
        )


def test_ship_batch_legacy_event_time_still_stamps_all(recorder):
    """The legacy single `event_time` path still stamps every event in the
    batch identically -- existing callers are unchanged."""
    hec_ship.ship_batch(
        [{"a": 1}, {"b": 2}],
        sourcetype="windows:security",
        host="corpus-win",
        event_time=123.0,
    )
    lines = recorder.bodies[0].splitlines()
    assert json.loads(lines[0])["time"] == 123.0
    assert json.loads(lines[1])["time"] == 123.0


def test_shipper_batches_by_count_across_timeline(tmp_path, monkeypatch):
    """The corpus Shipper batches by count, not per-second, so a multi-year
    CloudTrail set ships in a bounded number of HTTP calls."""
    from scripts import corpus_ingest

    shipped: list[dict] = []

    def _fake_ship(events, **kwargs):
        shipped.append({"n": len(events), "times": kwargs.get("event_times")})
        return {"ok": True, "count": len(events)}

    monkeypatch.setattr(corpus_ingest, "ship_batch", _fake_ship)
    monkeypatch.setattr(corpus_ingest, "BATCH", 3)

    shipper = corpus_ingest.Shipper("flaws_cloud", "portal5_lab", ship=True)
    # 10 events across 10 distinct seconds -> 4 batches of <=3, never 10.
    for i in range(10):
        shipper.add("aws:cloudtrail", {"eventName": f"E{i}"}, float(1000 + i))
    shipper.flush()
    assert sum(call["n"] for call in shipped) == 10
    assert len(shipped) == 4
    # every batch preserves its events' original timestamps
    for call in shipped:
        assert len(call["times"]) == call["n"]
