"""SA4.6 -- ANALYST_CORPUS_SNAPSHOT_V1 + coverage/known_state integration (A4/A5/A8).

Hermetic: immutable hash-verified snapshots deduplicated on canonical embed
text; the corpus stays appendable after a snapshot; ingested classes populate
``coverage_cells``/``known_state`` and are rankable by ``targeting.select``.
"""

from __future__ import annotations

from types import SimpleNamespace

from portal.modules.security.core.bully import costing, targeting
from portal.modules.security.core.bully.analyst_corpus import (
    SNAPSHOT_SCHEMA,
    T0_AUTHORITATIVE,
    T3_UNKNOWN,
    canonical_embed_text,
    ingest_benign,
    ingest_events,
    load_snapshot,
    populate_coverage_cells,
    populate_known_state,
    save_snapshot,
    take_snapshot,
    verify_snapshot,
)
from portal.modules.security.core.bully.store import Store


def _specimen(
    specimen_id: str,
    *,
    sourcetype: str,
    event: dict | None = None,
    techniques: tuple[str, ...] = (),
    labeling: str = "authoritative",
    provenance: dict | None = None,
) -> dict:
    return ingest_events(
        [event or {"EventCode": 4688, "Image": "cmd.exe", "CommandLine": "/c whoami"}],
        specimen_id=specimen_id,
        sourcetype=sourcetype,
        techniques=techniques,
        labeling=labeling,
        provenance=provenance or {"source_id": "external", "origin": "external_corpus"},
    )


def test_snapshot_dedupes_on_canonical_embed_text():
    a = _specimen("dup-a", sourcetype="windows:security")
    b = _specimen("dup-b", sourcetype="windows:security")  # identical telemetry
    c = _specimen(
        "distinct-c",
        sourcetype="windows:security",
        event={"EventCode": 4688, "Image": "msbuild.exe"},
    )
    assert canonical_embed_text(a) == canonical_embed_text(b)
    snapshot = take_snapshot([a, b, c])
    composition = snapshot["composition"]
    assert composition["distinct_text_collapse"]["specimen_count"] == 3
    assert composition["distinct_text_collapse"]["distinct_texts"] == 2
    assert composition["distinct_text_collapse"]["duplicate_texts"] == 1
    assert len(snapshot["distinct_specimens"]) == 2


def test_snapshot_is_immutable_and_hash_verified(tmp_path):
    specimens = [_specimen(f"sp-{i}", sourcetype="windows:security") for i in range(3)]
    snapshot = take_snapshot(specimens)
    assert snapshot["schema"] == SNAPSHOT_SCHEMA
    assert verify_snapshot(snapshot)["valid"] is True
    path = save_snapshot(snapshot, tmp_path)
    reloaded = load_snapshot(path)
    assert reloaded["snapshot_hash"] == snapshot["snapshot_hash"]
    # Tampering breaks the hash: the snapshot is immutable.
    tampered = dict(snapshot)
    tampered["distinct_specimens"] = tampered["distinct_specimens"][1:]
    assert verify_snapshot(tampered)["valid"] is False


def test_corpus_remains_appendable_after_snapshot():
    first = take_snapshot([_specimen("sp-a", sourcetype="windows:security")])
    assert verify_snapshot(first)["valid"] is True
    # The corpus is not frozen: add a specimen, take a second snapshot.
    second = take_snapshot(
        [
            _specimen("sp-a", sourcetype="windows:security"),
            _specimen("sp-b", sourcetype="OktaIM2:log"),
        ]
    )
    assert second["composition"]["specimen_count"] == 2
    # The first snapshot is unaffected and still verifies (immutable view).
    assert first["snapshot_hash"] != second["snapshot_hash"]
    assert verify_snapshot(first)["valid"] is True


def test_snapshot_reports_composition():
    specimens = [
        _specimen("win-a", sourcetype="windows:security"),
        _specimen(
            "cloud-b",
            sourcetype="aws:cloudtrail",
            event={"eventSource": "s3.amazonaws.com", "eventName": "PutObject"},
        ),
        ingest_benign(
            [{"EventCode": 4688, "Image": "explorer.exe"}],
            specimen_id="benign-c",
            sourcetype="windows:security",
        ),
    ]
    snapshot = take_snapshot(specimens)
    composition = snapshot["composition"]
    assert composition["per_class_counts"] == {"aws:cloudtrail": 1, "windows:security": 2}
    assert composition["tier_distribution"] == {T0_AUTHORITATIVE: 2, T3_UNKNOWN: 1}
    assert composition["benign_ratio"] == round(1 / 3, 6)
    assert composition["pivot_pair_counts"] == {"total": 0, "cross_class": 0}


def test_targeting_ranks_a_cell_sourced_from_a_new_class(tmp_path):
    """A8: ingested classes populate coverage_cells; a cell sourced from a new
    cloud class is rankable by targeting.select."""
    specimens = [
        _specimen("win-a", sourcetype="windows:security"),
        _specimen(
            "cloud-b",
            sourcetype="aws:cloudtrail",
            event={"eventSource": "s3.amazonaws.com", "eventName": "PutObject"},
        ),
        _specimen(
            "okta-c",
            sourcetype="OktaIM2:log",
            event={"eventType": "user.authentication.auth_via_mfa"},
        ),
    ]
    store = Store(tmp_path / "hunt_state.db")
    try:
        written = populate_coverage_cells(store, specimens, cost_ref="hunt-1")
        assert written == 3
        cells = store.coverage_cells()
        ids = {cell["cell_id"] for cell in cells}
        assert "cell-corpus-aws:cloudtrail" in ids  # the new cloud class

        ledger = costing.CostView(
            [
                costing.build_record(
                    "hunt-1",
                    None,
                    [costing.observation("lab_minutes", "hunt-1:sk", 1.0)],
                ).to_dict()
            ]
        )
        context = SimpleNamespace(
            hunt_id="hunt-1",
            open_cells=cells,
            known_state_view=[],
            config_version="cfg-1",
        )
        recall = SimpleNamespace(recall_id="rr-1", selected_context=[])
        decision = targeting.select(context, recall, ledger)
        assert decision.status == "selected"
        assert decision.selected_cell_id in {
            "cell-corpus-aws:cloudtrail",
            "cell-corpus-OktaIM2:log",
            "cell-corpus-windows:security",
        }
    finally:
        store.close()


def test_populate_known_state_records_corpus_coverage(tmp_path):
    specimens = [
        _specimen("win-a", sourcetype="windows:security"),
        _specimen(
            "cloud-b",
            sourcetype="aws:cloudtrail",
            event={"eventSource": "s3.amazonaws.com", "eventName": "PutObject"},
        ),
        ingest_benign(
            [{"EventCode": 4688, "Image": "explorer.exe"}],
            specimen_id="benign-c",
            sourcetype="windows:security",
        ),
    ]
    store = Store(tmp_path / "hunt_state.db")
    try:
        entries = populate_known_state(store, specimens, hunt_id="hunt-1", snapshot_ref="SNAP-1")
        assert entries == 2  # one per class, benign folded into its class
        rows = store._conn.execute(
            "SELECT subject, kind, trust_tier FROM known_state ORDER BY subject"
        ).fetchall()
        assert {row["subject"] for row in rows} == {"aws:cloudtrail", "windows:security"}
        assert all(row["kind"] == "corpus_coverage" for row in rows)
        assert all(row["trust_tier"] == "IMPORTED_OBSERVED" for row in rows)
    finally:
        store.close()
