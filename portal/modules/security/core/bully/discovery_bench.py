"""SA2 real-vs-real discovery lane (TASK_BULLY_SA2_DISCOVERY_MEASUREMENT_V1).

Grades the 988 real `attack_data`-lane corpus parents against each other with
**no planted relationship** and **no forge involvement** (A2). The engine
(`cousin_engine.grade`) sees only telemetry + trust tier, exactly as it does
in the forge lane; this module's only addition is a truth *join* the engine
never touches -- ``data.yml`` ATT&CK technique ids and the scenario-family
label already carried on each specimen -- used solely by the scorer, after
grading, to judge whether a surfaced relationship is real (A2, A7).

The joint `relationship x response` product metric (A1) is the reported
number; relationship-only accuracy is never reported as the product here.
`ANOMALOUS_UNCLASSIFIED` is always a `DISCOVERY` (A5), valued by distance,
never a miss.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from . import cousin_engine, signatures
from .cousin_calibration_bench import (
    MAX_DEGENERATE_RETRIEVAL_RATE,
    ReadOnlyKnnSnapshot,
    _known_near_far_controls,
    _rate,
    _record_family,
    _record_id,
    load_specimen_corpus,
)

DISCOVERY_BASELINE_V1 = "DISCOVERY_BASELINE_V1"
DISCOVERY_TAXONOMY_VERSION = "DISCOVERY_TAXONOMY_V1"

# A7: how far the mean shuffled-label precision must sit below the real
# (correctly-joined) precision, or how close to the empirical chance level it
# must land, before the lane is trusted as non-circular.
SHUFFLE_COLLAPSE_MARGIN = 0.15
SHUFFLE_REPEATS = 10


# ── real-parent selection (A2: no forge) ─────────────────────────────────────


def real_probe_specimens(corpus: dict[str, Any]) -> list[dict[str, Any]]:
    """The 988 (or however many) real `attack_data`-lane parents only.

    Never draws from `replay_mutation` (forge children) or `live_lab`
    single-row lane -- SA2.1's pairing pool is real-vs-real exclusively.
    """
    return [s for s in corpus["specimens"] if s["source_lane"] == "attack_data"]


def analyst_probe_specimens(corpus: dict[str, Any]) -> list[dict[str, Any]]:
    """Scoreable real specimens from the analyst corpus (SA5.7): attack_data
    parents plus acquired external-corpus specimens that carry T0/T1 labels.

    The analyst snapshot is multi-class -- cloud/identity live beside the
    endpoint backbone -- so the probe pool is real-vs-real across ALL scored
    lanes, never the forge (replay_mutation) or the single live-lab row.
    """
    probes = []
    for specimen in corpus["specimens"]:
        lane = specimen.get("source_lane")
        if lane in ("replay_mutation", "live_lab"):
            continue
        tier = str(specimen.get("label_tier") or "")
        if tier not in ("T0", "T1"):
            continue
        probes.append(specimen)
    return probes


def analyst_snapshot_specimens(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract the distinct specimens from an ANALYST_CORPUS snapshot
    (deduplicated on canonical text) for the discovery lane (SA5.7)."""
    if "distinct_specimens" in snapshot and isinstance(snapshot.get("distinct_specimens"), list):
        return snapshot["distinct_specimens"]
    if isinstance(snapshot.get("specimens"), list):
        return snapshot["specimens"]
    raise ValueError("unsupported analyst snapshot shape: no distinct_specimens/specimens")


def _specimen_technique_ids(specimen: dict[str, Any]) -> frozenset[str]:
    mappings = specimen["engine_view"]["telemetry_view"].get("attack_mappings") or []
    return frozenset(
        str(m.get("technique_id"))
        for m in mappings
        if isinstance(m, dict) and m.get("technique_id")
    )


def _specimen_family(specimen: dict[str, Any]) -> str:
    topology = specimen["engine_view"]["telemetry_view"].get("context_topology") or {}
    return str(topology.get("family") or "")


def _specimen_source_class(specimen: dict[str, Any]) -> str:
    return str(specimen.get("source_class") or "")


def _specimen_detector_outcomes(specimen: dict[str, Any]) -> dict[str, str]:
    return specimen["engine_view"]["telemetry_view"].get("detector_outcomes") or {}


def independent_truth_related(
    probe_techniques: frozenset[str],
    reference_techniques: frozenset[str],
    probe_family: str,
    reference_family: str,
) -> bool:
    """Scorer-only truth join (A2): shared `data.yml` ATT&CK technique or
    shared scenario-family lineage. Never consulted by `cousin_engine`."""
    if probe_techniques and reference_techniques and (probe_techniques & reference_techniques):
        return True
    return bool(probe_family and reference_family and probe_family == reference_family)


def _exclude_self(
    candidates: cousin_engine.CandidateSetReceipt, specimen_id: str
) -> cousin_engine.CandidateSetReceipt:
    """Drop the probe's own indexed record so it can never cousin itself."""
    filtered = tuple(
        item for item in candidates.candidates if _record_id(item["record"]) != specimen_id
    )
    return replace(candidates, candidates=filtered)


# ── per-pair grading (engine sees telemetry + trust tier only) ──────────────


def discovery_band(relationship: str, response: str) -> str:
    """SA2.2 taxonomy (A1/A5) -- distinct from `cousin_engine.product_band`,
    which serves the forge/recognition lane. This is the discovery-lane
    product classification: DISCOVERY / REGRESSION / FLOOR / NO-RELATION /
    INDETERMINATE."""
    if response == "INDETERMINATE":
        return "INDETERMINATE"
    if relationship == "SAME" and response in ("MISSED", "NEAR_MISS"):
        return "REGRESSION"
    if response == "COVERED":
        return "FLOOR"
    if relationship in ("SIMILAR", "NEW", "ANOMALOUS_UNCLASSIFIED") and response in (
        "MISSED",
        "NEAR_MISS",
    ):
        return "DISCOVERY"
    if relationship == "DIFFERENT" and response in ("MISSED", "NEAR_MISS"):
        return "NO-RELATION"
    return "INDETERMINATE"


@dataclass(frozen=True)
class RealPairVerdict:
    specimen_id: str
    source_class: str
    probe_technique_ids: tuple[str, ...]
    relationship: str
    response: str
    distance: float
    confidence: float
    reference_signature_id: str | None
    reference_family: str
    reference_source_class: str
    reference_technique_ids: tuple[str, ...]
    candidate_set_size: int
    measurement_valid: bool
    truth_related: bool
    cross_class: bool
    discovery_band: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def grade_real_pair(
    probe: dict[str, Any],
    snapshot: ReadOnlyKnnSnapshot,
    *,
    index_by_id: dict[str, dict[str, Any]],
) -> RealPairVerdict:
    """Real signature -> snapshot.knn -> candidate_set -> grade, self-excluded.

    The engine (`cousin_engine.grade`) receives only the probe's own
    telemetry-derived signature, the (self-excluded) candidate set, and a
    `CoverageView` built from the probe's own real detector outcomes (live
    SIEM query results captured at corpus-build time, per SA1) -- never a
    label describing whether the pair is "really" related.
    """
    engine_view = probe["engine_view"]
    signature = signatures.build_signature(
        engine_view["episode_view"], engine_view["telemetry_view"]
    )
    candidates = _exclude_self(
        cousin_engine.retrieve_candidate_axes(signature, snapshot), probe["specimen_id"]
    )
    outcomes = _specimen_detector_outcomes(probe)
    coverage = cousin_engine.CoverageView(
        applicable_detection_ids=tuple(sorted(outcomes)),
        fired_detection_ids=tuple(
            sorted(key for key, value in outcomes.items() if value == "fired")
        ),
        partial_detection_ids=tuple(
            sorted(key for key, value in outcomes.items() if value == "partial")
        ),
        telemetry_healthy=True,
    )
    assessment = cousin_engine.grade(signature, candidates, coverage)

    candidate_records = [item["record"] for item in candidates.candidates]
    selected = next(
        (r for r in candidate_records if _record_id(r) == assessment.reference_signature_id), {}
    )
    reference_specimen = index_by_id.get(assessment.reference_signature_id or "")
    reference_techniques = (
        _specimen_technique_ids(reference_specimen)
        if reference_specimen is not None
        else frozenset(str(t) for t in str(selected.get("attack_ids_text") or "").split())
    )
    reference_family = _record_family(selected)
    reference_source_class = str(selected.get("source_class") or "")

    probe_techniques = _specimen_technique_ids(probe)
    probe_family = _specimen_family(probe)
    is_anomalous = assessment.relationship == "ANOMALOUS_UNCLASSIFIED"
    truth_related = (
        False
        if is_anomalous
        else independent_truth_related(
            probe_techniques, reference_techniques, probe_family, reference_family
        )
    )
    probe_source_class = _specimen_source_class(probe)
    cross_class = bool(
        probe_source_class
        and reference_source_class
        and probe_source_class != reference_source_class
    )
    return RealPairVerdict(
        specimen_id=probe["specimen_id"],
        source_class=probe_source_class,
        probe_technique_ids=tuple(sorted(probe_techniques)),
        relationship=assessment.relationship,
        response=assessment.defense_response,
        distance=assessment.composite,
        confidence=assessment.confidence,
        reference_signature_id=assessment.reference_signature_id,
        reference_family=reference_family,
        reference_source_class=reference_source_class,
        reference_technique_ids=tuple(sorted(reference_techniques)),
        candidate_set_size=len(candidate_records),
        measurement_valid=len(candidate_records) > 0 or is_anomalous,
        truth_related=truth_related,
        cross_class=cross_class,
        discovery_band=discovery_band(assessment.relationship, assessment.defense_response),
    )


def run_real_pairs(
    probes: list[dict[str, Any]],
    snapshot: ReadOnlyKnnSnapshot,
    *,
    corpus: dict[str, Any],
    knn_batch_size: int = 32,
) -> tuple[RealPairVerdict, ...]:
    """Grade every real probe against the un-filtered real snapshot."""
    specimens = corpus.get("specimens") or analyst_snapshot_specimens(corpus)
    index_by_id = {s["specimen_id"]: s for s in specimens}
    prepare_knn = getattr(snapshot, "prepare_knn", None)
    if callable(prepare_knn):
        probe_signatures = [
            signatures.build_signature(
                p["engine_view"]["episode_view"], p["engine_view"]["telemetry_view"]
            )
            for p in probes
        ]
        prepare_knn(
            [q for sig in probe_signatures for q in cousin_engine.candidate_axis_queries(sig)],
            k=8,
            batch_size=knn_batch_size,
        )
    return tuple(grade_real_pair(p, snapshot, index_by_id=index_by_id) for p in probes)


# ── controls (A6/A7) ─────────────────────────────────────────────────────────


def classify_identity_failure(
    probe: dict[str, Any],
    assessment: cousin_engine.CousinAssessment,
    *,
    same_max_distance: float,
    canonical_text_by_id: dict[str, str],
) -> str:
    """Classify one identity-control failure into a separated cause (P0.3).

    - ``corpus-duplicate``: the probe's canonical text is shared with another
      indexed record, so no embedder can name the exact row as SAME (two
      identical rows are both distance 0).  Not an embedder defect.
    - ``scale-mismatch``: the engine recovered the probe's OWN record as its
      nearest candidate, but the composite exceeds ``same_max_distance`` --
      the space's self-distance (e.g. query-vs-doc form) outruns the frozen
      threshold (Arm B 25/25).  A per-space threshold fix rescues it.
    - ``genuine-discrimination-loss``: a different record outranks the probe's
      own row -- the model maps near-identical records to the same vector
      (Arm A 4/25).  Not rescued by thresholds.
    """
    probe_id = str(probe["specimen_id"])
    reference_id = str(assessment.reference_signature_id or "")
    if reference_id == probe_id and assessment.composite > same_max_distance:
        return "scale-mismatch"
    probe_text = canonical_text_by_id.get(probe_id, "")
    if reference_id != probe_id:
        duplicates = [
            other
            for other, text in canonical_text_by_id.items()
            if other != probe_id and text and text == probe_text
        ]
        if duplicates:
            return "corpus-duplicate"
    return "genuine-discrimination-loss"


def _identity_control(
    probes: list[dict[str, Any]],
    snapshot: ReadOnlyKnnSnapshot,
    *,
    sample_size: int = 25,
    thresholds: dict[str, float] | None = None,
    canonical_text_by_id: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Sanity check: WITHOUT self-exclusion the engine must recognize a
    probe's own indexed record as SAME at near-zero distance. This proves
    self-exclusion in `grade_real_pair` is doing real work, not masking a
    broken retrieval path that would never find anything anyway.

    Identity is a **classified diagnostic**, not a sole disqualifier (P0.3):
    each failure is separated into corpus-duplicate / scale-mismatch /
    genuine-discrimination-loss, and the per-space thresholds are honored.
    """
    thresholds = thresholds or cousin_engine.DEFAULT_THRESHOLDS
    sample = probes[:sample_size]
    failures = []
    for probe in sample:
        engine_view = probe["engine_view"]
        signature = signatures.build_signature(
            engine_view["episode_view"], engine_view["telemetry_view"]
        )
        candidates = cousin_engine.retrieve_candidate_axes(signature, snapshot)
        outcomes = _specimen_detector_outcomes(probe)
        coverage = cousin_engine.CoverageView(
            applicable_detection_ids=tuple(sorted(outcomes)), telemetry_healthy=True
        )
        assessment = cousin_engine.grade(signature, candidates, coverage, thresholds=thresholds)
        if (
            assessment.reference_signature_id != probe["specimen_id"]
            or assessment.relationship != "SAME"
            or assessment.composite > thresholds["same_max_distance"]
        ):
            cause = classify_identity_failure(
                probe,
                assessment,
                same_max_distance=float(thresholds["same_max_distance"]),
                canonical_text_by_id=canonical_text_by_id or {},
            )
            failures.append(
                {
                    "specimen_id": probe["specimen_id"],
                    "relationship": assessment.relationship,
                    "reference_signature_id": assessment.reference_signature_id,
                    "distance": assessment.composite,
                    "cause": cause,
                }
            )
    by_cause: dict[str, int] = {}
    for failure in failures:
        by_cause[failure["cause"]] = by_cause.get(failure["cause"], 0) + 1
    return {
        "passed": not failures,
        "checked": len(sample),
        "failures": failures,
        "by_cause": dict(sorted(by_cause.items())),
        "thresholds_applied": dict(thresholds),
    }


def _retrieval_health(verdicts: tuple[RealPairVerdict, ...]) -> dict[str, Any]:
    degenerate = sum(v.candidate_set_size == 0 for v in verdicts)
    rate = _rate(degenerate, len(verdicts)) or 0.0
    return {
        "passed": rate <= MAX_DEGENERATE_RETRIEVAL_RATE,
        "rows": len(verdicts),
        "degenerate_candidate_sets": degenerate,
        "degenerate_retrieval_rate": rate,
        "maximum_degenerate_rate": MAX_DEGENERATE_RETRIEVAL_RATE,
    }


def _discovery_precision(verdicts: tuple[RealPairVerdict, ...]) -> float | None:
    eligible = [
        v
        for v in verdicts
        if v.discovery_band == "DISCOVERY" and v.relationship != "ANOMALOUS_UNCLASSIFIED"
    ]
    if not eligible:
        return None
    return _rate(sum(v.truth_related for v in eligible), len(eligible))


def shuffled_label_control(
    verdicts: tuple[RealPairVerdict, ...],
    probes_by_id: dict[str, dict[str, Any]],
    *,
    seed: int = 20260816,
    repeats: int = SHUFFLE_REPEATS,
    margin: float = SHUFFLE_COLLAPSE_MARGIN,
) -> dict[str, Any]:
    """A7 -- randomize the scorer's independent labels (probe<->technique/
    family correspondence) and confirm discovery precision collapses.

    Only the truth *join* is shuffled; the engine's own relationship/response
    verdicts (already produced label-blind) are untouched. If precision does
    not collapse, the truth join is not doing independent work -> circular.
    """
    real_precision = _discovery_precision(verdicts)
    eligible = [
        v
        for v in verdicts
        if v.discovery_band == "DISCOVERY" and v.relationship != "ANOMALOUS_UNCLASSIFIED"
    ]
    if not eligible:
        return {
            "passed": True,
            "real_precision": real_precision,
            "mean_shuffled_precision": None,
            "note": "no comparable DISCOVERY rows (relationship-with-reference) to shuffle",
        }
    probe_ids = list(probes_by_id)
    shuffled_precisions: list[float] = []
    for trial in range(repeats):
        rng = random.Random(seed + trial)
        donors = probe_ids[:]
        rng.shuffle(donors)
        remap = dict(zip(probe_ids, donors, strict=True))
        hits = 0
        for verdict in eligible:
            donor = probes_by_id.get(remap.get(verdict.specimen_id, verdict.specimen_id))
            if donor is None:
                continue
            donor_techniques = _specimen_technique_ids(donor)
            donor_family = _specimen_family(donor)
            reference_techniques = frozenset(verdict.reference_technique_ids)
            if independent_truth_related(
                donor_techniques, reference_techniques, donor_family, verdict.reference_family
            ):
                hits += 1
        shuffled_precisions.append(_rate(hits, len(eligible)) or 0.0)
    mean_shuffled = round(sum(shuffled_precisions) / len(shuffled_precisions), 6)
    collapsed = (
        real_precision is None
        or (real_precision - mean_shuffled) >= margin
        or real_precision == 0.0
    )
    return {
        "passed": collapsed,
        "real_precision": real_precision,
        "mean_shuffled_precision": mean_shuffled,
        "shuffled_precisions": shuffled_precisions,
        "repeats": repeats,
        "margin": margin,
        "eligible_rows": len(eligible),
    }


def circularity_probe(
    verdicts: tuple[RealPairVerdict, ...],
    circular_truth_by_specimen: dict[str, bool],
    probes_by_id: dict[str, dict[str, Any]],
    *,
    seed: int = 20260816,
    repeats: int = SHUFFLE_REPEATS,
    margin: float = SHUFFLE_COLLAPSE_MARGIN,
) -> dict[str, Any]:
    """Test-only helper (SA2.3): re-run the shuffle check against a
    deliberately circular truth source (one that is itself a function of the
    engine's own verdict, keyed by specimen id) and confirm the control
    reports `passed: False` -- proving it distinguishes a real independent
    join from a circular one, not just "some numbers moved."
    """
    eligible = [
        v
        for v in verdicts
        if v.discovery_band == "DISCOVERY" and v.relationship != "ANOMALOUS_UNCLASSIFIED"
    ]
    if not eligible:
        return {"passed": True, "note": "no eligible rows"}
    real_precision = _rate(
        sum(circular_truth_by_specimen.get(v.specimen_id, False) for v in eligible), len(eligible)
    )
    probe_ids = list(probes_by_id)
    shuffled_precisions: list[float] = []
    for trial in range(repeats):
        rng = random.Random(seed + trial)
        donors = probe_ids[:]
        rng.shuffle(donors)
        remap = dict(zip(probe_ids, donors, strict=True))
        hits = sum(
            circular_truth_by_specimen.get(remap.get(v.specimen_id, v.specimen_id), False)
            for v in eligible
        )
        shuffled_precisions.append(_rate(hits, len(eligible)) or 0.0)
    mean_shuffled = round(sum(shuffled_precisions) / len(shuffled_precisions), 6)
    collapsed = (
        real_precision is None
        or (real_precision - mean_shuffled) >= margin
        or real_precision == 0.0
    )
    return {
        "passed": collapsed,
        "real_precision": real_precision,
        "mean_shuffled_precision": mean_shuffled,
    }


def run_controls(
    probes: list[dict[str, Any]],
    verdicts: tuple[RealPairVerdict, ...],
    snapshot: ReadOnlyKnnSnapshot,
    *,
    thresholds: dict[str, float] | None = None,
    canonical_text_by_id: dict[str, str] | None = None,
    identity_gate: str = "hard",
) -> dict[str, Any]:
    identity = _identity_control(
        probes,
        snapshot,
        thresholds=thresholds,
        canonical_text_by_id=canonical_text_by_id,
    )
    retrieval = _retrieval_health(verdicts)
    near_far = _known_near_far_controls()
    probes_by_id = {p["specimen_id"]: p for p in probes}
    shuffle = shuffled_label_control(verdicts, probes_by_id)
    # P0.3: identity is a CLASSIFIED diagnostic. Under the "diagnostic" gate,
    # identity never sole-disqualifies an arm -- its by-cause classification
    # (corpus-duplicate / scale-mismatch / genuine-discrimination-loss) is
    # reported and discovery precision decides adoption. The anti-circularity
    # controls (retrieval health, known near/far, shuffled-label collapse)
    # still gate hard. The "hard" gate is the default and preserves the
    # frozen V1 behavior.
    identity_in_gate = identity["passed"] if identity_gate == "hard" else True
    return {
        "passed": identity_in_gate
        and retrieval["passed"]
        and near_far["passed"]
        and shuffle["passed"],
        "identity": identity,
        "identity_gate": identity_gate,
        "retrieval_health": retrieval,
        "known_near_far": near_far,
        "shuffled_label_control": shuffle,
    }


# ── SA2.4: cross-class breakout + coverage asymmetry ─────────────────────────


def _coverage_asymmetry(probes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """For every technique with >=1 real detector outcome in >=2 classes,
    report classes where it is covered vs uncovered (A4)."""
    by_technique: dict[str, dict[str, list[str]]] = {}
    for probe in probes:
        outcomes = _specimen_detector_outcomes(probe)
        if not outcomes:
            continue
        source_class = _specimen_source_class(probe)
        response = (
            "COVERED"
            if "fired" in outcomes.values()
            else "NEAR_MISS"
            if "partial" in outcomes.values()
            else "MISSED"
        )
        for technique_id in _specimen_technique_ids(probe):
            by_technique.setdefault(technique_id, {}).setdefault(source_class, []).append(response)

    findings = []
    for technique_id, by_class in sorted(by_technique.items()):
        if len(by_class) < 2:
            continue
        covered_classes = sorted(c for c, rs in by_class.items() if "COVERED" in rs)
        uncovered_classes = sorted(c for c, rs in by_class.items() if "COVERED" not in rs)
        if covered_classes and uncovered_classes:
            findings.append(
                {
                    "technique_id": technique_id,
                    "covered_in": covered_classes,
                    "uncovered_in": uncovered_classes,
                }
            )
    return findings


def _cohort_summary(verdicts: list[RealPairVerdict]) -> dict[str, Any]:
    return {
        "rows": len(verdicts),
        "joint_outcome_distribution": dict(
            sorted(Counter(f"{v.relationship}x{v.response}" for v in verdicts).items())
        ),
        "discovery_band_distribution": dict(
            sorted(Counter(v.discovery_band for v in verdicts).items())
        ),
        "discovery_precision": _discovery_precision(tuple(verdicts)),
    }


def characterize_cross_class(
    verdicts: tuple[RealPairVerdict, ...], probes: list[dict[str, Any]]
) -> dict[str, Any]:
    same_class = [v for v in verdicts if not v.cross_class]
    cross_class = [v for v in verdicts if v.cross_class]
    cross_discoveries = [v for v in cross_class if v.discovery_band == "DISCOVERY"]
    asymmetry = _coverage_asymmetry(probes)
    asymmetry_by_technique = {row["technique_id"]: row for row in asymmetry}
    characterized = []
    for verdict in cross_discoveries:
        shared = set(verdict.probe_technique_ids) & set(verdict.reference_technique_ids)
        matches = [asymmetry_by_technique[t] for t in shared if t in asymmetry_by_technique]
        characterized.append(
            {
                "specimen_id": verdict.specimen_id,
                "source_class": verdict.source_class,
                "reference_signature_id": verdict.reference_signature_id,
                "reference_source_class": verdict.reference_source_class,
                "relationship": verdict.relationship,
                "response": verdict.response,
                "distance": verdict.distance,
                "truth_related": verdict.truth_related,
                "shared_technique_ids": sorted(shared),
                "coverage_asymmetry": matches,
            }
        )
    return {
        "same_class": _cohort_summary(same_class),
        "cross_class": _cohort_summary(cross_class),
        "cross_class_discoveries": tuple(characterized),
        "coverage_asymmetry_findings": tuple(asymmetry),
    }


# ── report + freeze ───────────────────────────────────────────────────────────


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True)
class DiscoveryReport:
    schema: str
    status: str
    corpus_snapshot_hash: str
    real_parent_count: int
    joint_outcome_distribution: dict[str, int]
    discovery_band_distribution: dict[str, int]
    discovery_precision: float | None
    discovery_recall_proxy: float | None
    same_class: dict[str, Any]
    cross_class: dict[str, Any]
    cross_class_discoveries: tuple[dict[str, Any], ...]
    coverage_asymmetry_findings: tuple[dict[str, Any], ...]
    regressions: tuple[dict[str, Any], ...]
    controls: dict[str, Any]
    diagnosis: tuple[str, ...] = ()
    open_gaps: tuple[str, ...] = field(
        default_factory=lambda: (
            "compounding (six-feed DecisionImpact on hunt N+1) not measured here",
            "promotion-through-the-bin end-to-end not measured here",
            "response-axis coverage lift from further onboarding not measured here",
        )
    )
    self_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _discovery_recall_proxy(verdicts: tuple[RealPairVerdict, ...]) -> float | None:
    """Of pairs with independently-related truth AND an uncovered probe
    response, how many did the engine surface as DISCOVERY?"""
    related_uncovered = [
        v
        for v in verdicts
        if v.truth_related
        and v.response in ("MISSED", "NEAR_MISS")
        and v.relationship != "ANOMALOUS_UNCLASSIFIED"
    ]
    if not related_uncovered:
        return None
    surfaced = sum(v.discovery_band == "DISCOVERY" for v in related_uncovered)
    return _rate(surfaced, len(related_uncovered))


def score_discovery(
    verdicts: tuple[RealPairVerdict, ...],
    probes: list[dict[str, Any]],
    *,
    corpus: dict[str, Any],
    controls: dict[str, Any],
) -> DiscoveryReport:
    controls_passed = bool(controls.get("passed"))
    if not controls_passed:
        diagnosis = tuple(
            name
            for name, result in controls.items()
            if isinstance(result, dict) and name != "identity" and not result.get("passed", True)
        )
        if controls.get("identity_gate") == "hard" and not controls.get("identity", {}).get(
            "passed", True
        ):
            diagnosis = ("identity",) + diagnosis
        return DiscoveryReport(
            schema=DISCOVERY_BASELINE_V1,
            status="INVALID",
            corpus_snapshot_hash=corpus.get("snapshot_hash", ""),
            real_parent_count=len(probes),
            joint_outcome_distribution={},
            discovery_band_distribution={},
            discovery_precision=None,
            discovery_recall_proxy=None,
            same_class={},
            cross_class={},
            cross_class_discoveries=(),
            coverage_asymmetry_findings=(),
            regressions=(),
            controls=controls,
            diagnosis=diagnosis,
        )

    breakout = characterize_cross_class(verdicts, probes)
    regressions = tuple(v.to_dict() for v in verdicts if v.discovery_band == "REGRESSION")
    report = DiscoveryReport(
        schema=DISCOVERY_BASELINE_V1,
        status="VALID",
        corpus_snapshot_hash=corpus.get("snapshot_hash", ""),
        real_parent_count=len(probes),
        joint_outcome_distribution=dict(
            sorted(Counter(f"{v.relationship}x{v.response}" for v in verdicts).items())
        ),
        discovery_band_distribution=dict(
            sorted(Counter(v.discovery_band for v in verdicts).items())
        ),
        discovery_precision=_discovery_precision(verdicts),
        discovery_recall_proxy=_discovery_recall_proxy(verdicts),
        same_class=breakout["same_class"],
        cross_class=breakout["cross_class"],
        cross_class_discoveries=breakout["cross_class_discoveries"],
        coverage_asymmetry_findings=breakout["coverage_asymmetry_findings"],
        regressions=regressions,
        controls=controls,
    )
    hash_payload = report.to_dict()
    hash_payload["self_hash"] = None
    return replace(report, self_hash=hashlib.sha256(_canonical(hash_payload).encode()).hexdigest())


def write_discovery_artifacts(report: DiscoveryReport, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "discovery_baseline_v1.json"
    path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"report": str(path)}


def run_discovery_bench(
    snapshot: ReadOnlyKnnSnapshot,
    *,
    corpus_path: Path | None = None,
    corpus: dict[str, Any] | None = None,
    output_dir: Path | None = None,
    thresholds: dict[str, float] | None = None,
    canonical_text_by_id: dict[str, str] | None = None,
    probe_selector=real_probe_specimens,
    identity_gate: str = "hard",
    knn_batch_size: int = 32,
) -> DiscoveryReport:
    """SA2.1-SA2.4 end to end: real-vs-real pairing, joint scoring, controls
    (incl. A7 shuffled-label), cross-class breakout. Never touches the forge.

    ``corpus`` may be given directly (e.g. an analyst snapshot dict) instead
    of ``corpus_path``; ``probe_selector`` picks the real probe pool (the
    default filters attack_data parents; SA5.7 uses the multi-class analyst
    selector). ``thresholds`` optionally carries the per-embedding-space
    thresholds (P0.2); identity is then a classified diagnostic against those
    (P0.3) rather than the frozen constants.
    """
    if corpus is None:
        if corpus_path is None:
            raise ValueError("run_discovery_bench requires corpus or corpus_path")
        corpus = load_specimen_corpus(corpus_path)
    probes = probe_selector(corpus)
    verdicts = run_real_pairs(probes, snapshot, corpus=corpus, knn_batch_size=knn_batch_size)
    controls = run_controls(
        probes,
        verdicts,
        snapshot,
        thresholds=thresholds,
        canonical_text_by_id=canonical_text_by_id,
        identity_gate=identity_gate,
    )
    report = score_discovery(verdicts, probes, corpus=corpus, controls=controls)
    if output_dir is not None:
        write_discovery_artifacts(report, output_dir)
    return report
