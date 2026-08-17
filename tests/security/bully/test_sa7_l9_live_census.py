from __future__ import annotations

import json

from portal.modules.security.core.bully.connectors import QueryInPlaceConnector
from portal.modules.security.core.bully.data_plane import DataPlane
from portal.modules.security.core.bully.live_census import write_live_census


def test_census_is_generated_with_sources_blind_spots_and_planner_proof(tmp_path):
    plane = DataPlane()
    plane.connect(
        "live-source",
        QueryInPlaceConnector(
            "live-source", lambda _: [{"timestamp": "2026-08-17", "host": "srv01"}]
        ),
        [{"timestamp": "2026-08-17", "host": "srv01"}],
    )
    proof = {
        "proof_hash": "proof-1234567890",
        "materially_different": True,
        "telemetry": {"source_order": ["live-source"]},
        "coverage": {"source_order": []},
    }
    output = tmp_path / "census.json"
    write_live_census(output, plane, proof)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["schema"] == "BULLY_SA7_LIVE_CENSUS_V1"
    assert {source["source_id"] for source in payload["census"]["sources"]} == {"live-source"}
    assert "live-source:missing:label_basis" in payload["census"]["blind_spots"]
    assert payload["planner_proof"]["materially_different"] is True
