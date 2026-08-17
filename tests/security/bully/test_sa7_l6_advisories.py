from __future__ import annotations

from portal.modules.security.core.bully.advisories import register_live_advisory_source
from portal.modules.security.core.bully.connectors import QueryIntent
from portal.modules.security.core.bully.data_plane import DataPlane


def test_fetched_advisory_is_sparse_and_provenance_preserving():
    plane = DataPlane()
    profile, metadata = register_live_advisory_source(
        plane,
        fetcher=lambda: {
            "vulnerabilities": [
                {
                    "cveID": "CVE-2026-0001",
                    "vendorProject": "Example",
                    "product": "Example App",
                    "vulnerabilityName": "Example flaw",
                    "shortDescription": "A test advisory.",
                    "dateAdded": "2026-08-17",
                    "requiredAction": "Patch it.",
                }
            ]
        },
        source_url="https://example.test/kev.json",
    )
    result = plane.query("live-advisories", QueryIntent("read advisory", limit=1))
    record = result.records[0]

    assert profile.mode == "query_in_place"
    assert metadata["finding"] is None
    assert record["attack_mappings"]
    assert record["artifacts"] == [{"type": "cve", "value": "CVE-2026-0001"}]
    assert record["context_topology"]["vendor"] == "Example"
    assert "action_sequence" not in record
    assert record["source"] == "https://example.test/kev.json"
    assert record["licence"]


def test_fetch_failure_is_a_recorded_finding():
    def fail():
        raise TimeoutError("feed unavailable")

    plane = DataPlane()
    _, metadata = register_live_advisory_source(plane, fetcher=fail)
    assert metadata["finding"]["status"] == "unavailable"
    assert "feed unavailable" in metadata["finding"]["reason"]
    result = plane.query("live-advisories", QueryIntent("retry advisory fetch", limit=1))
    assert result.metadata["finding"]["kind"] == "advisory_fetch"
