"""The review queue (TASK_COMPLIANCE_ENGINE_LANDING_V1 P1). LanceDB-backed;
tmp_path isolates the store per test (no network, no shared state)."""

from __future__ import annotations

import pytest

pytest.importorskip("lancedb")

from portal.modules.compliance.core import review_queue as rq  # noqa: E402


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    from portal.platform.retrieval import store as _store

    monkeypatch.setattr(_store, "LANCE_DIR", str(tmp_path / "lance"))
    monkeypatch.setattr(_store, "RAG_DIR", str(tmp_path / "lance" / "rag"))
    _store._db = None
    yield
    _store._db = None


def test_propose_files_an_open_item_with_evidence():
    item = rq.propose(
        "document_tier",
        "OT-POL-014.pdf",
        {"layer": "policy", "tier": 2},
        evidence=[{"document": "OT-POL-014.pdf", "section": "title", "page": 1, "span": "Policy"}],
        confidence=0.9,
    )
    assert item.status == "OPEN"
    got = rq.get(item.id)
    assert got.proposed_value == {"layer": "policy", "tier": 2}
    assert got.evidence[0]["document"] == "OT-POL-014.pdf"


def test_unknown_kind_rejected():
    with pytest.raises(ValueError):
        rq.propose("not_a_kind", "x", {})


def test_open_item_never_blocks_and_decide_supersedes_not_overwrites():
    item = rq.propose("applicability_scope", "entity", {"impact_present": ["high"]}, confidence=0.5)
    assert item in rq.open_items("applicability_scope")

    decided = rq.decide(item.id, "CONFIRMED", "operator")
    assert decided.status == "CONFIRMED"
    assert decided.prior_item_id == item.id
    # the prior row is closed, not deleted or rewritten — its value is untouched
    prior = rq.get(item.id)
    assert prior.status == "SUPERSEDED"
    assert prior.proposed_value == item.proposed_value
    assert rq.open_items("applicability_scope") == []


def test_decision_is_reversible_via_a_new_superseding_row():
    item = rq.propose("document_tier", "doc.pdf", {"layer": "procedure"}, confidence=0.3)
    first = rq.decide(item.id, "CONFIRMED", "sme_a")
    # a later correction: reverse the earlier CONFIRMED decision
    second = rq.decide(first.id, "REJECTED", "sme_b", corrected_value={"layer": "evidence"})
    assert second.prior_item_id == first.id
    assert rq.get(first.id).status == "SUPERSEDED"
    assert second.status == "REJECTED"
    assert second.proposed_value == {"layer": "evidence"}


def test_list_items_filters_by_kind_and_status():
    rq.propose("document_tier", "a.pdf", {"layer": "policy"})
    rq.propose("mapping_proposal", "m1", {"requirement_id": "CIP-007-6 R2 Part 2.2"})
    assert len(rq.list_items(kind="document_tier")) == 1
    assert len(rq.list_items(status="OPEN")) == 2
    assert len(rq.list_items(kind="mapping_proposal", status="OPEN")) == 1


def test_sync_proposed_mappings_wires_the_mapping_store_not_a_parallel_path(tmp_path):
    from portal.modules.compliance.core.mapping_store import MappingStore

    store = MappingStore(path=tmp_path / "mappings.json")
    m = store.propose("CIP-007-6 R2 Part 2.2", "OT-POL-014.pdf", "4.2", "FULL", confidence=0.8)
    n = rq.sync_proposed_mappings(store)
    assert n == 1
    items = rq.list_items(kind="mapping_proposal")
    assert len(items) == 1
    assert items[0].subject_id == m.id
    # idempotent — a second sync files nothing new
    assert rq.sync_proposed_mappings(store) == 0
