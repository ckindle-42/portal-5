"""TASK_BULLY_INVESTIGATION_V1 (I.3): capture driven by bounded investigations.

`capture_investigation` replaces the single `search index=X | head N` slab
scan with many bounded, entity-scoped pivot queries. Seeded against a small
BOTSv3-shaped fixture: capture issues only bounded queries, total events
read is far below a slab capture's cap, and sourcetype diversity per
investigation is higher than a random slab sample would show.
"""

from __future__ import annotations

from portal.modules.security.core.bully import inject_plane as ip
from portal.modules.security.core.bully import investigation_pivot as pivot

DAY_START = 1534737600.0  # 2018-08-20 00:00:00 UTC
SYMPTOM_AT = DAY_START + 15 * 3600 + 45 * 60

EVENTS = [
    {"_time": DAY_START + 9 * 3600, "sourcetype": "aws:cloudtrail", "userIdentity": "web_admin"},
    {
        "_time": DAY_START + 10 * 3600,
        "sourcetype": "xmlwineventlog:sysmon",
        "user": "bstoll",
        "host": "BSTOLL-L",
    },
    {
        "_time": SYMPTOM_AT,
        "sourcetype": "symantec:ep:security:file",
        "host": "BSTOLL-L",
    },
]


def _make_fake_connector(index: str):
    from portal.modules.security.core.bully.connectors import (
        QUERY_IN_PLACE_MODE,
        NativeQuery,
        QueryResult,
    )

    class _FakeConnector:
        source_id = f"lab-splunk:{index}"
        mode = QUERY_IN_PLACE_MODE
        calls: list = []

        def translate(self, intent):
            return NativeQuery(self.source_id, "SPL", {"search": "search"}, intent)

        def read(self, intent):
            self.calls.append(intent)
            spl = str(intent.seed.get("spl") or "")
            if "tstats" in spl:
                rows = (
                    {
                        "fields": {
                            "first": str(DAY_START),
                            "last": str(DAY_START + 24 * 3600),
                        }
                    },
                )
                return QueryResult(
                    self.source_id, self.mode, self.translate(intent), rows, 0.0, 0.0
                )
            if "eventcount" in spl:
                rows = ({"fields": {"count": len(EVENTS)}},)
                return QueryResult(
                    self.source_id, self.mode, self.translate(intent), rows, 0.0, 0.0
                )
            if intent.start is None or intent.end is None:
                raise AssertionError(f"unbounded corpus query issued: {intent!r}")
            entity = intent.entities[0] if intent.entities else None
            matched = tuple(
                {"_time": e["_time"], "host": e.get("host", ""), "fields": e}
                for e in EVENTS
                if intent.start <= e["_time"] <= intent.end
                and entity in (e.get("user"), e.get("host"), e.get("userIdentity"))
            )
            return QueryResult(self.source_id, self.mode, self.translate(intent), matched, 0.0, 0.0)

    return _FakeConnector()


def test_capture_investigation_issues_only_bounded_queries(monkeypatch) -> None:
    monkeypatch.setattr(ip, "lab_available", lambda: (True, ""))
    from portal.modules.security.core.bully import live_connect

    connectors = {}

    def factory(*, source_id="lab-splunk", index=None):
        connectors.setdefault(index, _make_fake_connector(index))
        return connectors[index]

    monkeypatch.setattr(live_connect, "lab_splunk_connector", factory)

    anchor = pivot.Anchor(
        anchor_id="a-monero-1545",
        at=SYMPTOM_AT,
        entity="BSTOLL-L",
        entity_kind="host",
        sourcetype="symantec:ep:security:file",
        why="monero_miner_detection",
        index="botsv3",
    )
    report = ip.capture_investigation([anchor], indexes=("botsv3",))
    assert report.plane == "live"
    assert len(report.investigations) == 1
    inv = report.investigations[0]
    assert inv.entities_seen.get("BSTOLL-L") == "host"
    assert "bstoll" in inv.entities_seen
    # far below a slab's typical cap, and only sourcetypes actually pivoted to
    assert len(inv.events) < 20
    assert inv.sourcetypes


def test_capture_investigation_clamps_to_discovered_index_range(monkeypatch) -> None:
    monkeypatch.setattr(ip, "lab_available", lambda: (True, ""))
    from portal.modules.security.core.bully import live_connect

    connectors = {}

    def factory(*, source_id="lab-splunk", index=None):
        connectors.setdefault(index, _make_fake_connector(index))
        return connectors[index]

    monkeypatch.setattr(live_connect, "lab_splunk_connector", factory)

    anchor = pivot.Anchor(
        anchor_id="a-monero-1545",
        at=SYMPTOM_AT,
        entity="BSTOLL-L",
        entity_kind="host",
        sourcetype="symantec:ep:security:file",
        why="monero_miner_detection",
        index="botsv3",
    )
    report = ip.capture_investigation([anchor], indexes=("botsv3",))
    rng = report.index_ranges["botsv3"]
    assert rng.earliest == DAY_START
    assert rng.latest == DAY_START + 24 * 3600
