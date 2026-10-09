"""SA5.4 -- bulk-ship acquired corpora to lab Splunk, index-verified.

Hermetic: `verify_index_confirmed` polls Splunk for a per-source search
confirmation (the P7.2 `live_indexed` receipt) and returns a reconciled
receipt; the per-source census reconciles to the input file count. No live
Splunk needed -- httpx is mocked at the transport level.
"""

from __future__ import annotations

from scripts import corpus_ingest

_INDEX = corpus_ingest.INDEX


def test_verify_index_confirmed_returns_receipt(monkeypatch):
    """A shipped source whose count search confirms >=1 event returns a
    reconciled receipt with `indexed_confirmed: True` (A5 / P7.2)."""
    monkeypatch.setattr(
        "portal.modules.security.core.siem.index_wait.wait_indexed", lambda **kwargs: True
    )
    monkeypatch.setattr(corpus_ingest, "_confirm_count_search", lambda *a, **k: 2900)
    receipt = corpus_ingest.verify_index_confirmed("invictus_ir_aws_dataset")
    assert receipt["schema"] == "CORPUS_SHIP_RECEIPT_V1"
    assert receipt["indexed_confirmed"] is True
    assert receipt["confirmed_count"] == 2900
    assert receipt["source"] == "invictus_ir_aws_dataset"
    assert receipt["index"] == _INDEX


def test_verify_index_confirmed_false_when_not_confirmed(monkeypatch):
    """A source the index does not confirm returns `indexed_confirmed: False`
    -- an honest receipt, not a silent pass."""
    monkeypatch.setattr(
        "portal.modules.security.core.siem.index_wait.wait_indexed", lambda **kwargs: False
    )
    monkeypatch.setattr(corpus_ingest, "_confirm_count_search", lambda *a, **k: 0)
    receipt = corpus_ingest.verify_index_confirmed("unshipped_source")
    assert receipt["indexed_confirmed"] is False
    assert receipt["confirmed_count"] == 0


def test_dataset_census_reconciles_to_input_files(tmp_path):
    """Every shipped input file is reconciled in the census -- admitted /
    unmapped / no-events / read-error totals equal the observed count (A7)."""
    root = tmp_path / "cloud"
    root.mkdir()
    (root / "a.json").write_text(
        '{"Records": [{"eventName": "ListBuckets"}, {"eventName": "PutObject"}]}\n',
        encoding="utf-8",
    )
    (root / "b.json").write_text('{"Records": [{"eventName": "ConsoleLogin"}]}\n', encoding="utf-8")
    (root / "empty.json").write_text("\n", encoding="utf-8")
    census = corpus_ingest.dataset_census(root)
    assert census["datasets_observed"] == 3
    assert census["reconciled"] is True
    assert len(census["admitted"]) == 2
    assert census["no_events"] == ["empty.json"]
    assert {row["dataset"] for row in census["admitted"]} == {"a.json", "b.json"}
    assert all(row["sourcetype"] == "aws:cloudtrail" for row in census["admitted"])
    assert all(row["source_class"] == "cloud" for row in census["admitted"])
