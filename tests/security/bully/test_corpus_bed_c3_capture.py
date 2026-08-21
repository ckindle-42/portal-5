"""C.3 -- capture reads every corpus lane, streamed.

Seeded against the exact bug this closes: `capture_records` used to read
`portal5_lab` only, so BOTS (`botsv1`/`botsv2`/`botsv3`) was invisible.
"""

from __future__ import annotations

from portal.modules.security.core.bully import corpus_bed
from portal.modules.security.core.bully import inject_plane as ip


def _fake_connector_factory(counts: dict[str, int], rows_per_index: dict[str, list[dict]]):
    from portal.modules.security.core.bully.connectors import (
        QUERY_IN_PLACE_MODE,
        NativeQuery,
        QueryResult,
    )

    def factory(*, source_id="lab-splunk", index=None):
        class _FakeConnector:
            source_id_ = source_id
            mode = QUERY_IN_PLACE_MODE

            def translate(self, intent):
                return NativeQuery(self.source_id_, "SPL", {"search": "search"}, intent)

            def read(self, intent):
                spl = intent.seed.get("spl", "")
                if "stats count" in spl:
                    records = ({"fields": {"count": counts.get(index, 0)}},)
                else:
                    records = tuple(rows_per_index.get(index, []))
                return QueryResult(
                    self.source_id_, self.mode, self.translate(intent), records, 0.0, 0.0
                )

        return _FakeConnector()

    return factory


def test_capture_reads_from_all_four_indexes_when_bots_counts_present(monkeypatch) -> None:
    monkeypatch.setattr(ip, "lab_available", lambda: (True, ""))
    from portal.modules.security.core.bully import live_connect

    counts = {"portal5_lab": 50_000, "botsv1": 3_000_000, "botsv2": 5_000_000, "botsv3": 5_650_000}
    rows = {idx: [{"fields": {"sourcetype": "st"}, "host": "h", "_time": 1.0}] for idx in counts}
    monkeypatch.setattr(live_connect, "lab_splunk_connector", _fake_connector_factory(counts, rows))

    report = ip.capture_records()
    seen_indexes = {r["__index"] for r in report.records}
    assert seen_indexes == set(corpus_bed.resolve_indexes())
    assert report.bed_report is not None
    assert report.bed_report.is_haystack is True


def test_bed_report_says_lane_a_absent_with_only_portal5_lab(monkeypatch) -> None:
    monkeypatch.setattr(ip, "lab_available", lambda: (True, ""))
    from portal.modules.security.core.bully import live_connect

    counts = {"portal5_lab": 2000}
    rows = {"portal5_lab": [{"fields": {"sourcetype": "st"}, "host": "h", "_time": 1.0}]}
    monkeypatch.setattr(live_connect, "lab_splunk_connector", _fake_connector_factory(counts, rows))

    report = ip.capture_records(indexes=("portal5_lab",))
    assert report.bed_report is not None
    assert report.bed_report.is_haystack is False
    assert any("lane_A_absent" in r for r in report.bed_report.reasons)
