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

from . import pyramid

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
    present_dimensions: tuple[str, ...] = ()
    created_at: float = field(default_factory=time.time)
    # R.3 (loop reintegration): the signature at pyramid-levelled granularity,
    # not a flat token bag. behavior_spine is the ordered L3 class sequence
    # derived from action_sequence -- the retrieval axis that lets a
    # cross-vocabulary cousin actually land in the candidate set.
    levelled_features: tuple[dict[str, Any], ...] = ()
    behavior_spine: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _canonical_fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _semantic_tokens(value: Any) -> list[str]:
    """Flatten a signature feature into stable, human-meaningful tokens."""
    if isinstance(value, dict):
        return [
            token
            for key in sorted(value)
            for token in (str(key), *_semantic_tokens(value[key]))
            if token
        ]
    if isinstance(value, (list, tuple, set)):
        values = sorted(value, key=str) if isinstance(value, set) else value
        return [token for item in values for token in _semantic_tokens(item)]
    text = str(value or "").strip()
    return [text] if text else []


def _level_signature_features(
    action_sequence: list[str],
    artifacts: dict[str, Any],
    parameter_families: dict[str, Any],
    *,
    classifier: pyramid.BehaviorClassifier | None = None,
) -> tuple[dict[str, Any], ...]:
    """Level every raw feature of a signature onto the pyramid axis (R.3):
    action-sequence verbs are ACTION (promoted to L3 when they classify),
    artifact identifiers are ENTITY (L1), and parameter-family tokens are
    PAYLOAD (L1). This replaces the flat token bag with features a
    pyramid-aware grader can compare by level, not just by string equality.
    """
    features: list[pyramid.LeveledFeature] = [
        pyramid.level_feature(verb, "ACTION", raw_verb=verb, classifier=classifier)
        for verb in action_sequence
        if verb
    ]
    for token in _semantic_tokens(artifacts):
        features.append(pyramid.level_feature(token, "ENTITY"))
    for token in _semantic_tokens(parameter_families):
        features.append(pyramid.level_feature(token, "PAYLOAD"))
    return tuple(f.__dict__.copy() for f in features)


def _behavior_spine(levelled_features: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
    """The ordered L3 class sequence -- the retrieval axis (R.3)."""
    return tuple(
        f["behavior_class"]
        for f in levelled_features
        if f["level"] == pyramid.L3_BEHAVIOR and f["behavior_class"]
    )


def behavior_spine_motif(signature: BehaviorSignature) -> str:
    """Small motif string for the behavioural-spine retrieval axis, parallel
    to `event_graph_motif` -- what candidate_axis_queries/retrieve_candidate_axes
    use to retrieve anchors by shared behaviour first."""
    return " ".join(signature.behavior_spine)


def signature_family(signature: BehaviorSignature) -> str:
    """Return the stable scenario-family label carried by a signature."""
    topology = signature.context_topology or {}
    family = topology.get("family") or topology.get("scenario_family")
    if family:
        return str(family)
    source_classes = topology.get("source_classes") or ()
    if isinstance(source_classes, str):
        return source_classes
    return "+".join(sorted(str(value) for value in source_classes if value))


def signature_family_from_record(record: dict[str, Any]) -> str:
    family = record.get("family") or (record.get("context_topology") or {}).get("family")
    if family:
        return str(family)
    source_classes = (record.get("context_topology") or {}).get("source_classes") or ()
    if isinstance(source_classes, str):
        return source_classes
    return "+".join(sorted(str(value) for value in source_classes if value))


def attack_ids(signature: BehaviorSignature) -> tuple[str, ...]:
    """Return normalized ATT&CK ids without leaking the fingerprint hash."""
    return tuple(
        sorted(
            {
                str(mapping.get("technique_id"))
                for mapping in signature.attack_mappings
                if isinstance(mapping, dict) and mapping.get("technique_id")
            }
        )
    )


def event_graph_motif(signature: BehaviorSignature) -> str:
    """Small semantic motif used by the fourth candidate-retrieval axis."""
    graph = signature.event_graph or {}
    ordered = graph.get("ordered") if isinstance(graph, dict) else None
    tokens = _semantic_tokens(ordered if ordered else graph)
    return " ".join(tokens[:12])


def semantic_query(signature: BehaviorSignature) -> str:
    """Serialize behavior for embedding retrieval.

    The canonical fingerprint is an identity digest and deliberately never
    appears here: cryptographic hashes have no useful embedding locality.
    """
    sections = (
        ("actions", _semantic_tokens(signature.action_sequence)[:64]),
        ("parameters", _semantic_tokens(signature.parameter_families)[:64]),
        ("attack", list(attack_ids(signature))),
        ("family", [signature_family(signature)] if signature_family(signature) else []),
    )
    query = " | ".join(f"{name}: {' '.join(tokens)}" for name, tokens in sections if tokens)
    return query or "behavior: unclassified telemetry"


def reference_record_fields(signature: BehaviorSignature) -> dict[str, Any]:
    """Projection fields shared by index and grade representations."""
    family = signature_family(signature)
    techniques = list(attack_ids(signature))
    motif = event_graph_motif(signature)
    source_classes = signature.telemetry_shape.get("source_class") or signature.telemetry_shape.get(
        "sourcetypes"
    )
    if isinstance(source_classes, (list, tuple)):
        source_class = str(source_classes[0]) if len(source_classes) == 1 else ""
    else:
        source_class = str(source_classes or "")
    return {
        "field_signature": signature.canonical_fingerprint,
        "semantic_query": semantic_query(signature),
        "family": family,
        "attack_primary": techniques[0] if techniques else "",
        "attack_ids_text": " ".join(techniques),
        "event_graph_motif": motif,
        "source_class": source_class,
        "present_dimensions": list(signature.present_dimensions),
        "action_sequence": list(signature.action_sequence),
        "behavior_sequence": " ".join(signature.action_sequence),
        "event_graph": dict(signature.event_graph),
        "parameter_families": dict(signature.parameter_families),
        "telemetry_shape": dict(signature.telemetry_shape),
        "context_topology": dict(signature.context_topology),
        "artifacts": dict(signature.artifacts),
        "attack_mappings": list(signature.attack_mappings),
        "behavior_spine": list(signature.behavior_spine),
        "behavior_spine_motif": behavior_spine_motif(signature),
        "levelled_features": [dict(f) for f in signature.levelled_features],
    }


def build_signature(
    episode_view: dict[str, Any],
    telemetry_view: dict[str, Any] | None = None,
    *,
    evidence_manifest_id: str | None = None,
    evidence_manifest_hash: str = "",
    behavior_classifier: pyramid.BehaviorClassifier | None = None,
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

    levelled_features = _level_signature_features(
        action_sequence, artifacts, parameter_families, classifier=behavior_classifier
    )
    behavior_spine = _behavior_spine(levelled_features)

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
        present_dimensions=tuple(name for name in _DIMENSIONS if present[name]),
        levelled_features=levelled_features,
        behavior_spine=behavior_spine,
    )
