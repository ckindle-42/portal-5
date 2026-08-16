"""BR-COUSIN pure-compute, independent relationship and response grading."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..telemetry import IMPORTED_OBSERVED_TRUST_TIER
from . import signatures as sig_mod
from .contracts import CousinAssessment, Decomposition

ALGORITHM_VERSION = "cousin-v1"

# Missing dimensions contribute no distance or confidence weight; weights are
# never renormalized (I-6 failure semantics).
_WEIGHTS = {
    "behavior": 0.30,
    "telemetry": 0.20,
    "semantic": 0.25,
    "attack": 0.15,
    "context": 0.10,
}

MIN_CONFIDENCE_FOR_CLASSIFICATION = 0.6
DEFAULT_THRESHOLDS = {
    "same_max_distance": 0.05,
    "similar_max_distance": 0.40,
    "new_max_distance": 0.85,
}
THRESHOLDS_VERSION = "bully-cousin-thresholds-v1"


def build_signature(episode_view: dict, telemetry_view: dict | None = None, **kwargs):
    """Thin re-export -- I-6 lists `build_signature` on the cousin engine;
    the actual construction lives in signatures.py (P1.5 build order)."""
    return sig_mod.build_signature(episode_view, telemetry_view, **kwargs)


# ── candidate set (union of semantic k-NN + ATT&CK neighborhood + ...) ──────


@dataclass(frozen=True)
class CandidateSetReceipt:
    receipt_id: str
    sources: dict[str, int]
    candidates: tuple[dict[str, Any], ...]
    health: dict[str, Any] = field(default_factory=dict)
    exclusions: tuple[str, ...] = ()
    created_at: float = field(default_factory=time.time)


def candidate_set(
    signature,
    *,
    semantic_candidates: list[tuple[dict, float]] | None = None,
    attack_neighbors: list[dict] | None = None,
    family_members: list[dict] | None = None,
    event_graph_motifs: list[dict] | None = None,
    health: dict | None = None,
) -> CandidateSetReceipt:
    """Union the injected candidate sources into one receipt.

    Every source is optional and independently injected (organ.knn results,
    an ATT&CK-neighborhood lookup, a scenario-family index, event-graph
    motif matches) -- this function only merges + dedupes + records
    provenance; it never fetches anything itself.
    """
    semantic_candidates = semantic_candidates or []
    attack_neighbors = attack_neighbors or []
    family_members = family_members or []
    event_graph_motifs = event_graph_motifs or []

    merged: dict[str, dict[str, Any]] = {}
    for record, distance in semantic_candidates:
        rid = record.get("record_id") or record.get("signature_id") or str(id(record))
        merged.setdefault(rid, {"record": record})["semantic_distance"] = distance
    for group_name, group in (
        ("attack_neighborhood", attack_neighbors),
        ("scenario_family", family_members),
        ("event_graph_motifs", event_graph_motifs),
    ):
        for record in group:
            rid = record.get("record_id") or record.get("signature_id") or str(id(record))
            merged.setdefault(rid, {"record": record})[f"from_{group_name}"] = True

    return CandidateSetReceipt(
        receipt_id=f"cs-{uuid.uuid4().hex[:12]}",
        sources={
            "semantic_knn": len(semantic_candidates),
            "attack_neighborhood": len(attack_neighbors),
            "scenario_family": len(family_members),
            "event_graph_motifs": len(event_graph_motifs),
        },
        candidates=tuple(merged.values()),
        health=health or {},
    )


def _records_only(results: list[tuple[dict, float]]) -> list[dict]:
    return [record for record, _distance in results]


def _dedupe_records(records: list[dict]) -> list[dict]:
    deduped: dict[str, dict] = {}
    for record in records:
        key = str(record.get("record_id") or record.get("signature_id") or id(record))
        deduped.setdefault(key, record)
    return list(deduped.values())


def candidate_axis_queries(signature) -> tuple[str, ...]:
    queries = [sig_mod.semantic_query(signature)]
    family = sig_mod.signature_family(signature)
    if family:
        queries.append(f"scenario family: {family}")
    queries.extend(f"ATT&CK technique: {value}" for value in sig_mod.attack_ids(signature))
    motif = sig_mod.event_graph_motif(signature)
    if motif:
        queries.append(f"event graph motif: {motif}")
    return tuple(queries)


def retrieve_candidate_axes(signature, snapshot, *, k: int = 8) -> CandidateSetReceipt:
    """Query and wire all four retrieval axes into a candidate receipt.

    Family uses indexed metadata. ATT&CK and event-graph axes use focused
    semantic queries followed by an exact shared-feature check, which works
    with both Organ and small read-only calibration fixtures.
    """
    query = sig_mod.semantic_query(signature)
    semantic = snapshot.knn(query, k=k)

    family = sig_mod.signature_family(signature)
    family_results = []
    if family:
        family_query = f"scenario family: {family}"
        try:
            family_results = snapshot.knn(family_query, k=k, filters={"family": family})
        except (KeyError, RuntimeError, ValueError):
            # Older projections may predate scalar family metadata. Keep those
            # snapshots readable while requiring exact family agreement.
            family_results = [
                (record, distance)
                for record, distance in snapshot.knn(family_query, k=k)
                if sig_mod.signature_family_from_record(record) == family
            ]

    subject_attack = set(sig_mod.attack_ids(signature))
    attack_pool: list[dict] = []
    for technique_id in sorted(subject_attack):
        for record, _distance in snapshot.knn(f"ATT&CK technique: {technique_id}", k=k):
            record_attack = {
                str(item.get("technique_id")) if isinstance(item, dict) else str(item)
                for item in (record.get("attack_mappings") or record.get("technique_ids") or ())
            }
            record_attack.update(str(record.get("attack_ids_text") or "").split())
            if technique_id in record_attack:
                attack_pool.append(record)

    motif = sig_mod.event_graph_motif(signature)
    motif_pool = snapshot.knn(f"event graph motif: {motif}", k=k) if motif else []
    motif_records = [
        record
        for record, _distance in motif_pool
        if str(record.get("event_graph_motif") or "") == motif
        or record.get("event_graph") == signature.event_graph
    ]
    return candidate_set(
        signature,
        semantic_candidates=semantic,
        attack_neighbors=_dedupe_records(attack_pool),
        family_members=_dedupe_records(_records_only(family_results)),
        event_graph_motifs=_dedupe_records(motif_records),
        health={"snapshot": "read-only", "semantic_query": query},
    )


# ── coverage view (defense-response axis input) ─────────────────────────────


@dataclass(frozen=True)
class CoverageView:
    applicable_detection_ids: tuple[str, ...] = ()
    fired_detection_ids: tuple[str, ...] = ()
    partial_detection_ids: tuple[str, ...] = ()
    telemetry_healthy: bool = True


def _response_axis(coverage: CoverageView) -> str:
    """Pure function of CoverageView only -- never reads D/relationship
    (C5 CLAIM 5, axis independence)."""
    if not coverage.telemetry_healthy:
        return "INDETERMINATE"
    if not coverage.applicable_detection_ids:
        return "INDETERMINATE"
    if set(coverage.fired_detection_ids) & set(coverage.applicable_detection_ids):
        return "COVERED"
    if set(coverage.partial_detection_ids) & set(coverage.applicable_detection_ids):
        return "NEAR_MISS"
    return "MISSED"


# ── structural distance decomposition ────────────────────────────────────────


def _jaccard_distance(a: set, b: set) -> float | None:
    if not a and not b:
        return None
    union = a | b
    if not union:
        return None
    return 1.0 - (len(a & b) / len(union))


def _flatten(d: dict) -> set[str]:
    """Flatten a shallow dict to a comparable set of `key=value` tokens,
    exploding list-valued fields element-wise so overlap is measured per
    element (e.g. `{"sourcetype": ["wmi", "smb"]}` -> `{"sourcetype=wmi",
    "sourcetype=smb"}`), not as one atomic blob that never matches a
    same-purpose list differing only by one extra element."""
    out: set[str] = set()
    for k, v in d.items():
        if v is None:
            continue
        if isinstance(v, (list, tuple, set)):
            for item in v:
                out.add(f"{k}={item}")
        else:
            out.add(f"{k}={v}")
    return out


def _decompose(
    subject: Any, reference: dict, *, semantic_distance: float | None
) -> dict[str, float | None]:
    ref_action = set(
        reference.get("action_sequence") or reference.get("behavior_sequence", "").split()
    )
    subj_action = set(getattr(subject, "action_sequence", None) or [])
    behavior = _jaccard_distance(subj_action, ref_action)

    ref_telemetry = _flatten(reference.get("telemetry_shape") or {})
    subj_telemetry = _flatten(getattr(subject, "telemetry_shape", None) or {})
    telemetry = _jaccard_distance(subj_telemetry, ref_telemetry)

    ref_attack = {
        t.get("technique_id") if isinstance(t, dict) else t
        for t in (reference.get("attack_mappings") or reference.get("technique_ids") or [])
    }
    subj_attack = {
        m.get("technique_id")
        for m in (getattr(subject, "attack_mappings", None) or [])
        if m.get("technique_id")
    }
    attack = _jaccard_distance(subj_attack, ref_attack)

    ref_context = _flatten(reference.get("context_topology") or {})
    subj_context = _flatten(getattr(subject, "context_topology", None) or {})
    context = _jaccard_distance(subj_context, ref_context)

    return {
        "behavior": behavior,
        "telemetry": telemetry,
        "semantic": semantic_distance,
        "attack": attack,
        "context": context,
    }


def _weighted_composite(decomposition: dict[str, float | None]) -> tuple[float, float, int]:
    """Returns (composite_distance, confidence, nonsemantic_channels).

    confidence = sum of weights whose dimension was actually present (never
    renormalized so the *distance* itself stays honest about what fraction
    of the weight-mass it represents).
    """
    total = 0.0
    mass = 0.0
    nonsemantic = 0
    for dim, weight in _WEIGHTS.items():
        value = decomposition.get(dim)
        if value is None:
            continue
        total += weight * value
        mass += weight
        if dim != "semantic":
            nonsemantic += 1
    confidence = mass  # in [0, 1]
    composite = total  # never rescaled by 1/mass -- "never renormalized"
    return composite, confidence, nonsemantic


def evaluate_vetoes(
    subject: Any, reference: dict, discriminators: list[str] | None = None
) -> list[dict[str, Any]]:
    """A discriminator contradiction downgrades SAME regardless of embedding
    proximity (C5 CLAIM 4). `discriminators` are field names looked up in
    both signature.context_topology/artifacts and the reference record's
    same-named fields; disagreement on any of them is a veto."""
    if not discriminators:
        return []
    subj_ctx = {
        **(getattr(subject, "context_topology", None) or {}),
        **(getattr(subject, "artifacts", None) or {}),
    }
    ref_ctx = {**(reference.get("context_topology") or {}), **(reference.get("artifacts") or {})}
    vetoes = []
    for field_name in discriminators:
        subj_val = subj_ctx.get(field_name)
        ref_val = ref_ctx.get(field_name)
        if subj_val is not None and ref_val is not None and subj_val != ref_val:
            vetoes.append({"discriminator": field_name, "subject": subj_val, "reference": ref_val})
    return vetoes


def _classify_relationship(
    composite: float, confidence: float, nonsemantic_channels: int, vetoed: bool, thresholds: dict
) -> str:
    if confidence < MIN_CONFIDENCE_FOR_CLASSIFICATION:
        return "ANOMALOUS_UNCLASSIFIED"

    if composite <= thresholds["same_max_distance"]:
        relationship = "SAME"
    elif composite <= thresholds["similar_max_distance"]:
        relationship = "SIMILAR"
    elif composite <= thresholds["new_max_distance"]:
        relationship = "NEW"
    else:
        relationship = "DIFFERENT"

    if relationship in ("SIMILAR", "NEW") and nonsemantic_channels < 2:
        # Can't claim SIMILAR/NEW without >=2 non-semantic corroborating
        # channels (C5 CLAIM 4) -- fall back to the honest DIFFERENT rather
        # than a relationship the evidence can't support.
        relationship = "DIFFERENT"

    if vetoed and relationship == "SAME":
        # A discriminator contradiction downgrades SAME regardless of
        # embedding proximity (C5 CLAIM 4) -- one tier down, never silently
        # kept at SAME.
        relationship = "SIMILAR" if nonsemantic_channels >= 2 else "DIFFERENT"

    return relationship


PRODUCT_BAND_TABLE = {
    ("SAME", "MISSED"): "REGRESSION",
    ("SAME", "NEAR_MISS"): "REGRESSION_RISK",
    ("SIMILAR", "MISSED"): "DISCOVERY",
    ("SIMILAR", "NEAR_MISS"): "DISCOVERY",
    ("NEW", "NEAR_MISS"): "DISCOVERY",
    ("NEW", "MISSED"): "DISCOVERY",
    ("ANOMALOUS_UNCLASSIFIED", "INDETERMINATE"): "BLIND_SPOT",
    ("ANOMALOUS_UNCLASSIFIED", "MISSED"): "BLIND_SPOT",
}


def product_band(relationship: str, response: str) -> str:
    """DATA_MODEL SS1.4 `product_band`: SAME×MISSED is a regression, not a
    discovery (C5 CLAIM 5) -- distinguished by name from the SIMILAR/NEW
    discovery bands, never conflated even though both start from a "not
    COVERED" response."""
    return PRODUCT_BAND_TABLE.get(
        (relationship, response), "NOMINAL" if response == "COVERED" else "OTHER"
    )


def _empty_assessment(signature, candidates: CandidateSetReceipt, response: str):
    return CousinAssessment(
        assessment_id=f"ca-{uuid.uuid4().hex[:12]}",
        subject_signature_id=signature.signature_id,
        reference_signature_id=None,
        candidate_set_id=candidates.receipt_id,
        decomposition=Decomposition(None, None, None, None, None),
        composite=1.0,
        relationship="ANOMALOUS_UNCLASSIFIED",
        nonsemantic_channels=0,
        vetoes=[],
        defense_response=response,
        nearest_knowns=[],
        confidence=0.0,
        completeness=signature.completeness,
        algorithm_version=ALGORITHM_VERSION,
        thresholds_version=THRESHOLDS_VERSION,
        explanation={
            "reason": "empty candidate set",
            "product_band": product_band("ANOMALOUS_UNCLASSIFIED", response),
        },
    )


def grade(
    signature,
    candidates: CandidateSetReceipt,
    coverage: CoverageView,
    *,
    discriminators: list[str] | None = None,
    thresholds: dict | None = None,
) -> CousinAssessment:
    thresholds = thresholds or DEFAULT_THRESHOLDS
    response = _response_axis(coverage)

    if not candidates.candidates:
        return _empty_assessment(signature, candidates, response)

    scored = []
    for candidate in candidates.candidates:
        record = candidate["record"]
        decomp = _decompose(signature, record, semantic_distance=candidate.get("semantic_distance"))
        composite, confidence, nonsemantic = _weighted_composite(decomp)
        scored.append((composite, confidence, nonsemantic, decomp, record, candidate))
    scored.sort(key=lambda t: t[0])
    composite, confidence, nonsemantic, decomp, best_record, best_candidate = scored[0]

    vetoes = evaluate_vetoes(signature, best_record, discriminators)
    relationship = _classify_relationship(
        composite, confidence, nonsemantic, bool(vetoes), thresholds
    )
    trust_adjustment = None
    exact_signature_match = best_record.get("field_signature") == getattr(
        signature, "canonical_fingerprint", None
    )
    if (
        relationship == "SAME"
        and getattr(signature, "trust_tier", "") == IMPORTED_OBSERVED_TRUST_TIER
        and not exact_signature_match
    ):
        relationship = "SIMILAR" if nonsemantic >= 2 else "DIFFERENT"
        trust_adjustment = "imported_observed_cannot_solely_support_same"

    nearest_knowns = [
        (c["record"].get("record_id", ""), c.get("semantic_distance", s))
        for s, _, _, _, _, c in scored[:5]
    ]
    band = product_band(relationship, response)

    return CousinAssessment(
        assessment_id=f"ca-{uuid.uuid4().hex[:12]}",
        subject_signature_id=signature.signature_id,
        reference_signature_id=best_record.get("signature_id") or best_record.get("record_id"),
        candidate_set_id=candidates.receipt_id,
        decomposition=Decomposition(**decomp),
        composite=composite,
        relationship=relationship,
        nonsemantic_channels=nonsemantic,
        vetoes=vetoes,
        defense_response=response,
        nearest_knowns=nearest_knowns,
        confidence=confidence,
        completeness=min(signature.completeness, confidence),
        algorithm_version=ALGORITHM_VERSION,
        thresholds_version=THRESHOLDS_VERSION,
        explanation={"product_band": band, "trust_adjustment": trust_adjustment},
    )


# ── explain (reuses unknown_defense as the explanation layer + dual-run) ────


def explain(
    assessment: CousinAssessment, *, reference_record: dict | None = None
) -> dict[str, Any]:
    """Feature-overlap citations for the assessment's nearest reference,
    reusing `unknown_defense.compute_similarity` as the explanation layer
    (never the production grader -- see `dual_run_shadow` below for the
    documented-baseline/comparator role)."""
    citations: list[str] = []
    if reference_record is not None:
        from ..unknown_defense import compute_similarity

        observed = {
            "tactic": reference_record.get("tactic", ""),
            "behavior": " ".join(str(x) for x in (reference_record.get("action_sequence") or [])),
        }
        wiki_descriptions = {
            "reference": " ".join(str(x) for x in (reference_record.get("action_sequence") or []))
        }
        similarity = compute_similarity(observed, wiki_descriptions)
        citations = list(similarity.overlapping_features)

    return {
        "relationship": assessment.relationship,
        "defense_response": assessment.defense_response,
        "composite": assessment.composite,
        "decomposition": assessment.decomposition.to_dict(),
        "vetoes": assessment.vetoes,
        "feature_citations": citations,
        "algorithm_version": assessment.algorithm_version,
        "thresholds_version": assessment.thresholds_version,
        "product_band": assessment.explanation.get("product_band"),
    }


def dual_run_shadow(
    observed_features: dict, wiki_descriptions: dict, composite_relationship: str
) -> dict[str, Any]:
    """I-22: legacy `unknown_defense` grade and BR-COUSIN grade both run
    during shadow; disagreements are recorded, never silently resolved by
    reusing the old NONE->benign fallback. Returns a comparison record for
    the caller (LOOP, P1.7) to persist as migration evidence -- this
    function itself never persists anything (pure compute)."""
    from ..unknown_defense import MatchGrade, compute_similarity

    legacy = compute_similarity(observed_features, wiki_descriptions)
    agree = (legacy.grade == MatchGrade.EXACT and composite_relationship == "SAME") or (
        legacy.grade == MatchGrade.SIMILAR and composite_relationship in ("SIMILAR", "NEW")
    )
    return {
        "legacy_grade": legacy.grade,
        "legacy_overlapping_features": legacy.overlapping_features,
        "composite_relationship": composite_relationship,
        "agree": agree,
    }
