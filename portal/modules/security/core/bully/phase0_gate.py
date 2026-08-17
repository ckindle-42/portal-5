"""SA7 Phase 0 gate evaluation over a live-built data plane."""

from __future__ import annotations

from typing import Any

from .data_plane import DataPlane

_REQUIRED_NON_TELEMETRY = {
    "live-advisories",
    "case-history",
    "asset-identity-context",
    "detection-coverage",
}


def evaluate_phase0_gate(
    plane: DataPlane,
    census_payload: dict[str, Any],
    planner_proof: dict[str, Any],
) -> dict[str, Any]:
    profiles = plane.catalog.profiles()
    source_ids = {profile.source_id for profile in profiles}
    audited_ids = {entry.source_id for entry in plane.audit.entries()}
    entity_profiles = [profile for profile in profiles if profile.capabilities.entity_identity]
    entity_links_valid = bool(entity_profiles) and all(
        profile.entity_links
        and all(link.confidence > 0 and bool(link.provenance) for link in profile.entity_links)
        for profile in entity_profiles
    )
    advisory_records = plane.records.get("live-advisories", ())
    advisory_sparse = bool(advisory_records) and all(
        {"attack_mappings", "artifacts", "context_topology", "source", "retrieved_at", "licence"}
        <= set(record)
        and "action_sequence" not in record
        for record in advisory_records
    )
    census = census_payload.get("census") or {}
    census_sources = {source.get("source_id") for source in census.get("sources", ())}
    base_gate = plane.gate()
    checks = {
        "query_in_place": base_gate.checks["query_in_place"],
        "schemas_discovered": bool(profiles)
        and all(profile.schema.confidence > 0 for profile in profiles),
        "semantic_bindings_declared": bool(profiles)
        and all(profile.bindings for profile in profiles),
        "time_comparability_declared": bool(profiles)
        and all(profile.time_binding is not None for profile in profiles),
        "entity_resolution_confidence_provenance": entity_links_valid,
        "catalog_drives_selection": bool(planner_proof.get("materially_different"))
        and all(
            decision["selected"] or decision["reasons"]
            for plan in (planner_proof.get("telemetry"), planner_proof.get("coverage"))
            for decision in (plan or {}).get("decisions", ())
        ),
        "volume_quality_sensitivity": bool(profiles)
        and all(profile.volume and profile.quality and profile.access for profile in profiles),
        "complete_query_audit": source_ids <= audited_ids,
        "non_telemetry_sources_connected": source_ids >= _REQUIRED_NON_TELEMETRY
        and all(
            plane.catalog.get(source_id).record_count > 0 for source_id in _REQUIRED_NON_TELEMETRY
        ),
        "advisories_sparse_signatures": advisory_sparse,
        "census_published": source_ids == census_sources and bool(census.get("blind_spots")),
    }
    blockers = sorted(name for name, passed in checks.items() if not passed)
    return {
        "passed": not blockers,
        "checks": checks,
        "blockers": blockers,
        "evidence": {
            "source_count": len(profiles),
            "audit_entries": len(plane.audit.entries()),
            "blind_spots": len(census.get("blind_spots", ())),
            "planner_proof_hash": planner_proof.get("proof_hash"),
            "non_telemetry_sources": sorted(_REQUIRED_NON_TELEMETRY & source_ids),
        },
    }
