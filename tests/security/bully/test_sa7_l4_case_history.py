from __future__ import annotations

from portal.modules.security.core.bully.case_history import register_case_history_source
from portal.modules.security.core.bully.connectors import QueryIntent
from portal.modules.security.core.bully.contracts import (
    DecisionEvent,
    DecisionImpact,
    RecallReceipt,
)
from portal.modules.security.core.bully.data_plane import DataPlane
from portal.modules.security.core.bully.store import Store


def _event(event_id: str, kind: str, rationale: str) -> DecisionEvent:
    return DecisionEvent(
        event_id=event_id,
        hunt_id="hunt-1",
        iteration_id="iteration-1",
        actor="operator:alice",
        kind=kind,
        subject_id="candidate-1",
        rationale=rationale,
        data={"technique_id": "T1059", "asset": "host-1"},
    )


def test_store_case_history_is_queryable_with_chain_and_operator_provenance(tmp_path):
    store = Store(tmp_path / "hunt_state.db")
    first = store.record_decision(_event("event-1", "promote", "promote validated host evidence"))
    second = store.record_decision(_event("event-2", "kill", "demote after operator review"))
    store.promotion_enqueue(
        queue_id="queue-1", item_kind="cousin_detection", item_id="candidate-1", hunt_id="hunt-1"
    )
    store.promotion_resolve(
        "queue-1", actor="operator:alice", state="confirmed", rationale="operator confirmed"
    )
    store.recall_receipt_put(
        RecallReceipt(
            recall_id="recall-1",
            hunt_id="hunt-1",
            query="validated host evidence",
            filters={},
            source_health={},
            projection_version="projection-v1",
            embedding_version="embedding-v1",
            reranker_version=None,
        )
    )
    store.decision_impact_put(
        DecisionImpact(
            impact_id="impact-1",
            recall_id="recall-1",
            consuming_decision_ref="event-1",
            before={"selected": False},
            after={"selected": True},
            cited_record_ids=["event-1"],
            change_kind="SELECTED",
            explanation="case history selected the validated evidence",
        )
    )

    plane = DataPlane()
    profile = register_case_history_source(plane, store)
    result = plane.query(
        "case-history",
        QueryIntent("validated operator promote", seed={"hunt_id": "hunt-1"}, limit=10),
    )
    classes = {record["record_class"] for record in result.records}

    assert profile.mode == "query_in_place"
    event_ids = {
        record["event_id"] for record in result.records if record["record_class"] == "case_decision"
    }
    assert {first.event_id, second.event_id} <= event_ids
    assert "operator_confirmation" in classes
    assert "decision_impact" in classes
    assert result.metadata["chain_valid"] is True
    assert all(record["provenance"]["store_db"] for record in result.records)
    assert len(plane.audit.entries()) == 1
    store.close()


def test_case_history_query_does_not_copy_or_mutate_store(tmp_path):
    store = Store(tmp_path / "hunt_state.db")
    store.record_decision(_event("event-1", "gate", "operator reviewed telemetry"))
    before = len(store.decision_events())
    plane = DataPlane()
    register_case_history_source(plane, store)
    plane.query("case-history", QueryIntent("operator reviewed", limit=4))
    assert len(store.decision_events()) == before
    store.close()
