"""SA4.4 -- analyst-pivot pair identification with independent basis (A6).

Hermetic: pairs come from REAL co-occurrence only -- shared authoritative/
confirmed external labels, shared entity/time-window observations from a real
join, or simultaneous multi-source capture. No pair derives from clustering
output (A2): machine-proposed (T2) labels never ground a pair.
"""

from __future__ import annotations

from portal.modules.security.core.bully.analyst_corpus import (
    PIVOT_BASIS_SHARED_ENTITY_WINDOW,
    PIVOT_BASIS_SHARED_EXTERNAL_LABEL,
    PIVOT_BASIS_SIMULTANEOUS_CAPTURE,
    PIVOT_BASIS_VALUES,
    HypothesisStore,
    PivotPair,
    PivotPairLedger,
    identify_pivot_pairs,
    ingest_events,
)


def _specimen(
    specimen_id: str,
    *,
    sourcetype: str,
    techniques: tuple[str, ...],
    labeling: str = "authoritative",
    provenance: dict | None = None,
) -> dict:
    return ingest_events(
        [{"EventCode": 4688, "Image": "cmd.exe"}],
        specimen_id=specimen_id,
        sourcetype=sourcetype,
        techniques=techniques,
        labeling=labeling,
        provenance=provenance or {"source_id": "external", "origin": "external_corpus"},
    )


def test_pairs_from_shared_external_label_are_cross_class_and_based():
    sysmon = _specimen(
        "sysmon-kerberoast",
        sourcetype="windows:sysmon",
        techniques=("T1558.003",),
        provenance={
            "source_id": "attack_data",
            "origin": "external_corpus",
            "labeling": "authoritative",
        },
    )
    okta = _specimen(
        "okta-kerberoast",
        sourcetype="OktaIM2:log",
        techniques=("T1558.003",),
        provenance={
            "source_id": "okta_export",
            "origin": "external_corpus",
            "labeling": "authoritative",
        },
    )
    unrelated = _specimen(
        "sysmon-unrelated", sourcetype="windows:sysmon", techniques=("T1059.001",)
    )
    pairs = identify_pivot_pairs([sysmon, okta, unrelated])
    assert len(pairs) == 1
    pair = pairs[0]
    assert pair.basis == PIVOT_BASIS_SHARED_EXTERNAL_LABEL
    assert pair.basis_detail == "T1558.003"
    assert pair.cross_class is True
    assert {pair.left_specimen_id, pair.right_specimen_id} == {
        "sysmon-kerberoast",
        "okta-kerberoast",
    }


def test_every_pair_carries_a_basis_and_never_clustering_output():
    co_occurrence = {
        PIVOT_BASIS_SHARED_ENTITY_WINDOW: {
            "detail": "account:svc-alice@corp",
            "specimen_ids": ("sp-a", "sp-b", "sp-c"),
            "window": "2026-08-16T10:00Z/11:00Z",
        }
    }
    pairs = identify_pivot_pairs([], co_occurrence=co_occurrence)
    assert len(pairs) == 3  # C(3,2)
    for pair in pairs:
        assert pair.basis in PIVOT_BASIS_VALUES
        assert pair.basis_detail
    assert all(pair.basis == PIVOT_BASIS_SHARED_ENTITY_WINDOW for pair in pairs)


def test_machine_proposed_t2_labels_never_ground_a_pair():
    """A2: a machine-proposed (T2) label can never be the independent basis of
    a pivot pair. Two specimens sharing a technique through a T2 (proposed)
    label produce no pair; the same technique as T0 (authoritative) does."""
    t2_left = _specimen(
        "t2-left",
        sourcetype="windows:sysmon",
        techniques=("T1558.003",),
        labeling="machine-clustered",
    )
    t2_right = _specimen(
        "t2-right", sourcetype="OktaIM2:log", techniques=("T1558.003",), labeling="proposed"
    )
    assert identify_pivot_pairs([t2_left, t2_right]) == ()

    t0_left = _specimen(
        "t0-left", sourcetype="windows:sysmon", techniques=("T1558.003",), labeling="authoritative"
    )
    t0_right = _specimen(
        "t0-right", sourcetype="OktaIM2:log", techniques=("T1558.003",), labeling="authoritative"
    )
    pairs = identify_pivot_pairs([t0_left, t0_right])
    assert len(pairs) == 1


def test_hypothesis_proposals_are_not_a_pivot_input(tmp_path):
    """A2: the proposed-structure lane (hypotheses) is never a basis for pivot
    pairs. Even a confirmed hypothesis cannot inject a pair -- the pair input
    surface is real co-occurrence only."""
    store = HypothesisStore(tmp_path / "hypotheses.jsonl")
    proposal = store.propose(
        kind="cluster",
        subject="T1558.003",
        detail={"members": ["sp-x", "sp-y"]},
    )
    store.confirm(
        proposal["hypothesis_id"], basis="operator review", basis_evidence={"reviewer": "sec-ops"}
    )
    # Two specimens that only relate through that hypothesis produce nothing.
    a = _specimen(
        "sp-x", sourcetype="windows:sysmon", techniques=("T9999.001",), labeling="unknown"
    )
    b = _specimen("sp-y", sourcetype="OktaIM2:log", techniques=("T9999.001",), labeling="unknown")
    assert identify_pivot_pairs([a, b]) == ()


def test_simultaneous_multi_source_capture_produces_cross_class_pairs():
    endpoint = _specimen(
        "ep-capture-1",
        sourcetype="windows:security",
        techniques=(),
        provenance={
            "source_id": "lab",
            "origin": "simultaneous_capture",
            "capture_id": "cap-0712",
            "labeling": "unknown",
        },
    )
    network = _specimen(
        "net-capture-1",
        sourcetype="netflow",
        techniques=(),
        provenance={
            "source_id": "lab",
            "origin": "simultaneous_capture",
            "capture_id": "cap-0712",
            "labeling": "unknown",
        },
    )
    identity = _specimen(
        "id-capture-1",
        sourcetype="OktaIM2:log",
        techniques=(),
        provenance={
            "source_id": "lab",
            "origin": "simultaneous_capture",
            "capture_id": "cap-0712",
            "labeling": "unknown",
        },
    )
    pairs = identify_pivot_pairs([endpoint, network, identity])
    assert len(pairs) == 3  # C(3,2) from the shared capture
    assert all(pair.basis == PIVOT_BASIS_SIMULTANEOUS_CAPTURE for pair in pairs)
    assert all(pair.cross_class for pair in pairs)


def test_pivot_pair_ledger_seals_pairs_with_basis(tmp_path):
    ledger = PivotPairLedger(tmp_path / "specimens")
    pair = PivotPair(
        pair_id="pair-1",
        left_specimen_id="a",
        right_specimen_id="b",
        basis=PIVOT_BASIS_SHARED_EXTERNAL_LABEL,
        basis_detail="T1558.003",
        cross_class=True,
    )
    ledger.record(pair)
    ledger.record(pair)  # idempotent
    rows = ledger.records()
    assert len(rows) == 1
    assert rows[0]["basis"] == PIVOT_BASIS_SHARED_EXTERNAL_LABEL
    assert rows[0]["basis_detail"] == "T1558.003"
    assert rows[0]["cross_class"] is True


def test_pivot_pair_requires_basis_detail():
    import pytest

    with pytest.raises(ValueError):
        PivotPair(
            pair_id="bad",
            left_specimen_id="a",
            right_specimen_id="b",
            basis=PIVOT_BASIS_SHARED_EXTERNAL_LABEL,
            basis_detail="",
            cross_class=False,
        )
