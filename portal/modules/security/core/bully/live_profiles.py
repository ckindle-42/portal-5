"""Live re-profiling of all currently registered data-plane sources."""

from __future__ import annotations

from collections.abc import Mapping

from .connectors import QueryIntent
from .data_plane import DataPlane, SourceProfile, profile_source


def derive_live_profiles(
    plane: DataPlane,
    *,
    intents: Mapping[str, QueryIntent] | None = None,
    sample_limit: int = 128,
) -> dict[str, SourceProfile]:
    """Replace catalog profiles with bounded samples observed from each source."""
    profiles: dict[str, SourceProfile] = {}
    intent_map = dict(intents or {})
    for source_id, connector in list(plane.connectors.items()):
        previous = plane.catalog.get(source_id)
        intent = intent_map.get(
            source_id,
            QueryIntent("derive live source profile", limit=sample_limit),
        )
        result = connector.read(intent)
        observed_count = result.metadata.get("record_count")
        if result.truncated and previous is not None:
            observed_count = previous.record_count
        profile = profile_source(
            source_id,
            connector,
            result.records,
            source_meta={
                "freshness_at": result.finished_at,
                "record_count_override": observed_count,
                "sensitivity": previous.access.sensitivity if previous else "internal",
                "credential_ref": previous.access.credential_ref if previous else None,
            },
        )
        plane.records[source_id] = tuple(result.records)
        plane.catalog.register(profile)
        plane.audit.record(result, sensitivity=profile.access.sensitivity)
        old_capabilities = previous.capabilities.as_dict() if previous else {}
        live_capabilities = profile.capabilities.as_dict()
        downgraded = sorted(
            capability
            for capability, was_present in old_capabilities.items()
            if was_present and not live_capabilities.get(capability, False)
        )
        plane.live_profile_evidence[source_id] = {
            "profile_version": profile.profile_version,
            "sample_count": len(result.records),
            "record_count": profile.record_count,
            "schema_confidence": profile.schema.confidence,
            "native_query": result.native_query.expression,
            "mode": result.mode,
            "source_metadata": result.metadata,
            "previous_capabilities": old_capabilities,
            "live_capabilities": live_capabilities,
            "downgraded_capabilities": downgraded,
            "derived_from_live": True,
        }
        profiles[source_id] = profile
    return profiles
