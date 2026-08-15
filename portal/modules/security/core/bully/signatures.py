"""bully.signatures -- BehaviorSignature construction from Episodes (P1.5).

Pure compute over injected data (MASTER SS3): no network, no SQL, no model
calls. `build_signature` is deterministic -- same episode + telemetry_view
+ algorithm version always produces the same canonical_fingerprint and
completeness (C4).
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

SIGNATURE_ALGORITHM_VERSION = "sig-v1"

# The dimensions completeness is measured across (DATA_MODEL SS1.3): missing
# ones lower completeness, never renormalize the ones that ARE present.
_DIMENSIONS = (
    "action_sequence",
    "event_graph",
    "parameter_families",
    "context_topology",
    "artifacts",
    "attack_mappings",
    "telemetry_shape",
    "detector_outcomes",
)


@dataclass(frozen=True)
class BehaviorSignature:
    signature_id: str
    episode_ref: str
    signature_algorithm_version: str
    input_manifest_hash: str
    canonical_fingerprint: str
    action_sequence: list[str] = field(default_factory=list)
    event_graph: dict[str, Any] = field(default_factory=dict)
    parameter_families: dict[str, Any] = field(default_factory=dict)
    context_topology: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    attack_mappings: list[dict[str, Any]] = field(default_factory=list)
    telemetry_shape: dict[str, Any] = field(default_factory=dict)
    detector_outcomes: dict[str, Any] = field(default_factory=dict)
    trust_tier: str = ""
    evidence_manifest_id: str | None = None
    completeness: float = 1.0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _canonical_fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_signature(
    episode_view: dict[str, Any],
    telemetry_view: dict[str, Any] | None = None,
    *,
    evidence_manifest_id: str | None = None,
    evidence_manifest_hash: str = "",
) -> BehaviorSignature:
    """Build a `BehaviorSignature` from an adapted Episode + optional
    telemetry view (`evidence.adapt_episode(episode)`'s output shape, or
    any dict carrying the same keys -- this module never imports
    episode.py directly, keeping it fully injectable/testable).

    Missing telemetry_view fields lower `completeness`; they are never
    fabricated or renormalized away (DATA_MODEL SS1.3 / C5 CLAIM 3-5).
    """
    telemetry_view = telemetry_view or {}

    action_sequence = list(telemetry_view.get("action_sequence") or [])
    event_graph = dict(telemetry_view.get("event_graph") or {})
    parameter_families = dict(telemetry_view.get("parameter_families") or {})
    context_topology = {
        "target_host": episode_view.get("target_host"),
        **dict(telemetry_view.get("context_topology") or {}),
    }
    artifacts = dict(telemetry_view.get("artifacts") or {})
    attack_mappings = list(telemetry_view.get("attack_mappings") or [])
    telemetry_shape = dict(telemetry_view.get("telemetry_shape") or {})
    detector_outcomes = dict(telemetry_view.get("detector_outcomes") or {})
    trust_tier = str(telemetry_view.get("trust_tier") or episode_view.get("trust_tier") or "")

    present = {
        "action_sequence": bool(action_sequence),
        "event_graph": bool(event_graph),
        "parameter_families": bool(parameter_families),
        "context_topology": bool(context_topology.get("target_host") or len(context_topology) > 1),
        "artifacts": bool(artifacts),
        "attack_mappings": bool(attack_mappings),
        "telemetry_shape": bool(telemetry_shape),
        "detector_outcomes": bool(detector_outcomes),
    }
    completeness = sum(present.values()) / len(_DIMENSIONS)

    fingerprint_payload = {
        "action_sequence": action_sequence,
        "event_graph": event_graph,
        "parameter_families": parameter_families,
        "context_topology": context_topology,
        "artifacts": artifacts,
        "attack_mappings": attack_mappings,
    }
    fingerprint = _canonical_fingerprint(fingerprint_payload)

    input_manifest_hash = evidence_manifest_hash or _canonical_fingerprint(
        {"episode": episode_view, "telemetry": telemetry_view}
    )

    return BehaviorSignature(
        signature_id=f"sig-{uuid.uuid4().hex[:12]}",
        episode_ref=str(episode_view.get("episode_id", "")),
        signature_algorithm_version=SIGNATURE_ALGORITHM_VERSION,
        input_manifest_hash=input_manifest_hash,
        canonical_fingerprint=fingerprint,
        action_sequence=action_sequence,
        event_graph=event_graph,
        parameter_families=parameter_families,
        context_topology=context_topology,
        artifacts=artifacts,
        attack_mappings=attack_mappings,
        telemetry_shape=telemetry_shape,
        detector_outcomes=detector_outcomes,
        trust_tier=trust_tier,
        evidence_manifest_id=evidence_manifest_id,
        completeness=completeness,
    )
