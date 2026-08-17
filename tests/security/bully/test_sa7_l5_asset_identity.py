from __future__ import annotations

from portal.modules.security.core.bully.asset_identity import (
    context_answer,
    register_asset_identity_source,
)
from portal.modules.security.core.bully.connectors import IterableIngestConnector
from portal.modules.security.core.bully.data_plane import DataPlane


def test_asset_identity_context_joins_indexed_activity_inventory_and_peer_baseline():
    indexed = IterableIngestConnector(
        "lab-splunk",
        [
            {"_time": 1, "host": "srv01", "fields": {"user": "alice", "action": "login"}},
            {"_time": 2, "host": "srv01", "fields": {"user": "alice", "action": "exec"}},
            {"_time": 3, "host": "srv02", "fields": {"user": "bob", "action": "login"}},
        ],
    )
    plane = DataPlane()
    profile = register_asset_identity_source(
        plane,
        indexed,
        inventory_provider=lambda: [
            {"source": "proxmox", "vmid": 101, "name": "srv01", "node": "pve01"}
        ],
    )

    answer = context_answer(plane, entity_id="alice")
    classes = {record["record_class"] for record in answer["records"]}

    assert profile.source_id == "asset-identity-context"
    assert answer["available"] is True
    assert {"indexed_entity_context", "peer_baseline"} <= classes
    assert all(record["provenance"]["source_id"] for record in answer["records"])
    assert context_answer(plane, entity_id="not-present")["available"] is False


def test_asset_identity_can_operate_with_no_inventory_and_reports_provenance():
    indexed = IterableIngestConnector("lab-splunk", [{"host": "srv01", "user": "alice"}])
    plane = DataPlane()
    register_asset_identity_source(plane, indexed)
    answer = context_answer(plane, entity_id="srv01")
    assert answer["available"] is True
    assert answer["records"][0]["provenance"]["source_id"] == "lab-splunk"
