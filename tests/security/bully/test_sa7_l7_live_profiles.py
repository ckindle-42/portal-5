from __future__ import annotations

from portal.modules.security.core.bully.connectors import IterableIngestConnector, QueryIntent
from portal.modules.security.core.bully.data_plane import DataPlane
from portal.modules.security.core.bully.live_profiles import derive_live_profiles


def test_profiles_are_rederived_from_live_samples_and_downgrades_are_recorded():
    plane = DataPlane()
    connector = IterableIngestConnector(
        "live-records",
        [{"timestamp": "2026-08-17T12:00:00Z", "host": "srv01", "actor": "alice"}],
    )
    plane.connect(
        "live-records",
        connector,
        connector.read(QueryIntent("hermetic profile", limit=1)).records,
        source_meta={
            "label_basis": True,
            "benign_present": True,
            "capabilities": {"label_basis": True, "benign_present": True},
        },
    )

    profiles = derive_live_profiles(
        plane, intents={"live-records": QueryIntent("live refresh", limit=1)}
    )
    evidence = plane.live_profile_evidence["live-records"]

    assert profiles["live-records"].schema.confidence > 0
    assert evidence["derived_from_live"] is True
    assert evidence["mode"] == "ingest"
    assert "label_basis" in evidence["downgraded_capabilities"]
    assert "benign_present" in evidence["downgraded_capabilities"]
    assert len(plane.audit.entries()) == 1
    assert plane.census()["live_profile_evidence"]["live-records"]["sample_count"] == 1
