from __future__ import annotations

from portal.modules.security.core.bully.connectors import (
    IterableIngestConnector,
    QueryInPlaceConnector,
)
from portal.modules.security.core.bully.data_plane import DataPlane
from portal.modules.security.core.bully.planner_proof import planner_proof


def test_planner_proof_selects_different_sets_and_explains_exclusions():
    plane = DataPlane()
    plane.connect(
        "live-telemetry",
        QueryInPlaceConnector("live-telemetry", lambda _: [{"host": "srv01", "actor": "alice"}]),
        [{"host": "srv01", "actor": "alice"}],
        source_meta={
            "capabilities": {
                "queryable_in_place": True,
                "entity_identity": True,
                "semantic_text": True,
            }
        },
    )
    plane.connect(
        "coverage",
        IterableIngestConnector("coverage", [{"technique_id": "T1059", "description": "shell"}]),
        [{"technique_id": "T1059", "description": "shell"}],
        source_meta={"capabilities": {"label_basis": True, "semantic_text": True}},
    )
    plane.connect(
        "insufficient",
        IterableIngestConnector("insufficient", [{"value": "other"}]),
        [{"value": "other"}],
    )

    proof = planner_proof(plane)
    telemetry = set(proof["telemetry"]["source_order"])
    coverage = set(proof["coverage"]["source_order"])
    insufficient = next(
        item for item in proof["telemetry"]["decisions"] if item["source_id"] == "insufficient"
    )

    assert proof["materially_different"] is True
    assert telemetry == {"live-telemetry"}
    assert coverage == {"coverage"}
    assert insufficient["selected"] is False
    assert any("missing-capabilities" in reason for reason in insufficient["reasons"])
    assert len(proof["proof_hash"]) == 16
    assert proof == planner_proof(plane)
