"""Eval-side cousin calibration bench (P6.8).

Ground truth comes from the typed mutation plan used to construct each child,
never from BR-COUSIN. Children are graded blind against a read-only Organ
snapshot and are never indexed. The response axis uses the independent
``recall_attribution`` discriminator oracle; this module is the one explicit
eval-side exception to the production package's Rule-BM import boundary.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Protocol

from ..recall_attribution import ABSENT, INDETERMINATE, evidence_presence, technique_discriminators
from . import cousin_engine, mutation, signatures
from .contracts import MutationOperatorSpec, MutationPlan
from .specimen_ledger import SpecimenLedger

CALIB_DISTANCE_POLICY_VERSION = "CALIB_DISTANCE_POLICY_V1"
CALIB_PARENT_SET_VERSION = "CALIB_PARENTS_V1"
CALIB_SWEEP_VERSION = "CALIB_SWEEP_V1"
BASELINE_CALIBRATION_V1 = "BASELINE_CALIBRATION_V1"
BASELINE_CALIBRATION_V2 = "BASELINE_CALIBRATION_V2"
BASELINE_CALIBRATION_V3 = "BASELINE_CALIBRATION_V3"
RETRIEVAL_MIN_HIT_RATE = 0.60
MAX_DEGENERATE_RETRIEVAL_RATE = 0.10

# Frozen structural weights. This table is intentionally unrelated to
# cousin_engine._WEIGHTS and construction_distance never calls the grader.
OPERATOR_CLASS_WEIGHTS: dict[str, float] = {
    "REORDER_STEPS": 0.04,
    "VARY_PARAMETER": 0.08,
    "INJECT_EVASION_DIRECTIVE": 0.14,
    "SUBSTITUTE_TECHNIQUE": 0.20,
    "OFF_SCRIPT_SUPPLY": 0.26,
    "REVERSE_GEN_SEED": 0.32,
}

FROZEN_SWEEP: tuple[tuple[str, ...], ...] = (
    ("REORDER_STEPS",),
    ("VARY_PARAMETER",),
    ("INJECT_EVASION_DIRECTIVE",),
    ("SUBSTITUTE_TECHNIQUE",),
    ("SUBSTITUTE_TECHNIQUE", "INJECT_EVASION_DIRECTIVE"),
    ("SUBSTITUTE_TECHNIQUE", "OFF_SCRIPT_SUPPLY"),
    ("SUBSTITUTE_TECHNIQUE", "OFF_SCRIPT_SUPPLY", "REVERSE_GEN_SEED"),
    tuple(OPERATOR_CLASS_WEIGHTS),
)


@dataclass(frozen=True)
class CalibrationParent:
    parent_id: str
    scenario: str
    family: str
    covering_detection_id: str
    reference_scenario: dict[str, Any]
    technique_ids: tuple[str, ...]


CALIB_PARENTS_V1: tuple[CalibrationParent, ...] = (
    CalibrationParent(
        parent_id="calib-parent-ad-kerberoast",
        scenario="kerberoast_to_da",
        family="active-directory",
        covering_detection_id="T1558.003",
        reference_scenario={
            "red_order": [
                "start_lab_target",
                "run_nmap_scan",
                "check_cve",
                "exploit_service",
                "establish_persistence",
                "lateral_move",
                "exfiltrate_data",
                "revert_lab_target",
            ],
            "red_prompt": "authorized Kerberoast-to-domain-admin lab chain on $TARGET_HOST",
            "mission_objective": "validate credential-theft and lateral-movement coverage",
            "target_host": "10.10.11.21",
        },
        technique_ids=("T1558.003", "T1003.006", "T1053.005"),
    ),
    CalibrationParent(
        parent_id="calib-parent-web-sqli",
        scenario="web_sqli_dump",
        family="web-injection",
        covering_detection_id="T1190",
        reference_scenario={
            "red_order": ["execute_bash", "execute_bash", "execute_bash", "execute_bash"],
            "red_prompt": "authorized SQL-injection data extraction on $TARGET_HOST",
            "mission_objective": "validate public-facing exploit coverage",
            "target_host": "10.10.11.50",
        },
        technique_ids=("T1190", "T1059.004"),
    ),
    CalibrationParent(
        parent_id="calib-parent-smb-lateral",
        scenario="meta3_smb_exploit",
        family="lateral-movement",
        covering_detection_id="T1210",
        reference_scenario={
            "red_order": ["execute_bash", "execute_bash", "execute_bash"],
            "red_prompt": "authorized SMB enumeration and exploitation on $TARGET_HOST",
            "mission_objective": "validate remote-services exploitation coverage",
            "target_host": "10.10.11.13",
        },
        technique_ids=("T1210", "T1021.002"),
    ),
    CalibrationParent(
        parent_id="calib-parent-web-ssrf",
        scenario="web_ssrf",
        family="cloud-metadata",
        covering_detection_id="T1552",
        reference_scenario={
            "red_order": ["execute_bash", "execute_bash"],
            "red_prompt": "authorized SSRF cloud-metadata probe on $TARGET_HOST",
            "mission_objective": "validate metadata credential exposure coverage",
            "target_host": "10.10.11.50",
        },
        technique_ids=("T1190", "T1552"),
    ),
)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


CALIB_PARENTS_V1_SNAPSHOT_HASH = hashlib.sha256(
    _canonical([asdict(parent) for parent in CALIB_PARENTS_V1]).encode()
).hexdigest()


@dataclass(frozen=True)
class CalibrationVariant:
    variant_id: str
    parent_id: str
    family: str
    covering_detection_id: str
    plan: MutationPlan
    d_applied: float
    episode_view: dict[str, Any]
    telemetry_view: dict[str, Any]
    model_visible_telemetry: str
    discriminator_evasion: bool
    negative_control: bool


@dataclass(frozen=True)
class BlindGrade:
    variant: CalibrationVariant
    relationship: str
    response: str
    distance: float
    decomposition: dict[str, float | None]
    confidence: float
    reference_signature_id: str | None
    semantic_query: str = ""
    candidate_set_size: int = 0
    candidate_ids: tuple[str, ...] = ()
    parent_present_in_candidates: bool = False
    family_parent_present_in_candidates: bool = False
    reference_family: str = ""
    measurement_valid: bool = True


@dataclass(frozen=True)
class CalibrationReport:
    passed: bool
    policy_version: str
    parent_set_version: str
    parent_snapshot_hash: str
    sweep_version: str
    thresholds_version: str
    curve: tuple[dict[str, Any], ...]
    by_family: dict[str, tuple[dict[str, Any], ...]]
    failures: dict[str, tuple[dict[str, Any], ...]]
    indeterminate: tuple[dict[str, Any], ...]
    calibration_proposal: dict[str, Any] | None
    status: str = "VALID"
    controls: dict[str, Any] = field(default_factory=dict)
    instrument_health: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReadOnlyKnnSnapshot(Protocol):
    def knn(self, query: str, k: int, filters: dict[str, Any] | None = None): ...

    def stats(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class BlindCorpusVerdict:
    specimen_id: str
    source_lane: str
    relationship: str
    response: str
    distance: float
    decomposition: dict[str, float | None]
    confidence: float
    reference_signature_id: str | None
    semantic_query: str = ""
    candidate_set_size: int = 0
    candidate_ids: tuple[str, ...] = ()
    candidate_families: tuple[str, ...] = ()
    reference_family: str = ""
    measurement_valid: bool = True


@dataclass(frozen=True)
class BaselineCalibrationReport:
    schema: str
    passed: bool
    corpus_snapshot_hash: str
    ledger_snapshot_hash: str
    thresholds_version: str
    cold_untuned: bool
    training_applied: bool
    threshold_tuning_applied: bool
    per_lane_counts: dict[str, int]
    curve: tuple[dict[str, Any], ...]
    failures: dict[str, tuple[dict[str, Any], ...]]
    unresolved: tuple[dict[str, Any], ...]
    indeterminate: tuple[dict[str, Any], ...]
    calibration_proposal: None = None
    characterization: dict[str, Any] = field(default_factory=dict)
    snapshot_hash: str | None = None
    reference_guard: dict[str, Any] = field(default_factory=dict)
    status: str = "VALID"
    controls: dict[str, Any] = field(default_factory=dict)
    diagnosis: tuple[str, ...] = ()
    instrument_health: dict[str, Any] = field(default_factory=dict)
    oracle_independence_contract: dict[str, Any] = field(default_factory=dict)
    x_axis_validity: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def construction_distance(
    plan_or_operators: MutationPlan | tuple[MutationOperatorSpec, ...] | list[MutationOperatorSpec],
    *,
    moved_features: set[str] | None = None,
) -> float:
    """Independent x-axis from applied operators that moved observable features."""
    if moved_features is not None and not moved_features:
        return 0.0
    operators = (
        plan_or_operators.operators
        if isinstance(plan_or_operators, MutationPlan)
        else tuple(plan_or_operators)
    )
    return round(min(sum(OPERATOR_CLASS_WEIGHTS[op.operator] for op in operators), 1.0), 6)


def _operator(parent: CalibrationParent, name: str) -> MutationOperatorSpec:
    order = list(parent.reference_scenario["red_order"])
    params_by_name = {
        "REORDER_STEPS": {"order": list(reversed(order))},
        "VARY_PARAMETER": {"placeholder": "$TARGET_HOST", "value": "lab-alias.local"},
        "INJECT_EVASION_DIRECTIVE": {
            "directive_text": "preserve objective; vary exact discriminator representation"
        },
        "SUBSTITUTE_TECHNIQUE": {
            "from": order[0],
            "to": f"variant_{order[0]}",
        },
        "OFF_SCRIPT_SUPPLY": {"technique_ids": ["T9999.001"]},
        "REVERSE_GEN_SEED": {"technique_id": "T9999.002"},
    }
    return MutationOperatorSpec(operator=name, params=params_by_name[name])


def _plan(parent: CalibrationParent, operator_names: tuple[str, ...]) -> MutationPlan:
    operators = tuple(_operator(parent, name) for name in operator_names)
    digest = hashlib.sha256(
        _canonical(
            {
                "parent": parent.parent_id,
                "operators": [asdict(operator) for operator in operators],
                "policy": CALIB_DISTANCE_POLICY_VERSION,
            }
        ).encode()
    ).hexdigest()[:16]
    return MutationPlan(
        plan_id=f"calib-plan-{digest}",
        plan_version=1,
        reference_scenario=parent.scenario,
        operators=operators,
        invariants=("preserve_mission_objective",),
        expected_observables={"parent_id": parent.parent_id},
        controls=("unmodified-parent",) if len(operators) > 1 else (),
        replay_policy="held_out_never_index",
        allowed_targets=(parent.reference_scenario["target_host"],),
        allowed_tools=(),
        cleanup=(),
        approval_ref=CALIB_SWEEP_VERSION,
        budget_class="extended",
        idempotency_key=f"calib-idem-{digest}",
        proposer="eval:cousin-calibration",
        created_at=0.0,
    )


def _mutated_attack_ids(parent: CalibrationParent, names: tuple[str, ...]) -> list[str]:
    ids = list(parent.technique_ids)
    if "SUBSTITUTE_TECHNIQUE" in names and ids:
        ids[0] = "T9999.100"
    if "OFF_SCRIPT_SUPPLY" in names:
        ids.append("T9999.001")
    if "REVERSE_GEN_SEED" in names:
        ids.append("T9999.002")
    return ids


def generate_variants(
    parent: CalibrationParent,
    sweep: tuple[tuple[str, ...], ...] = FROZEN_SWEEP,
) -> tuple[CalibrationVariant, ...]:
    """Compile a byte-stable held-out sweep over MUT; no indexing occurs."""
    variants: list[CalibrationVariant] = []
    for operator_names in sweep:
        plan = _plan(parent, operator_names)
        overlay = mutation.validate_and_compile(
            plan,
            reference_scenario=parent.reference_scenario,
            hunt_config={"mutation": {"max_variants_per_iteration": 20}},
        )
        d_applied = construction_distance(plan)
        evasion = bool(set(operator_names) & {"INJECT_EVASION_DIRECTIVE", "SUBSTITUTE_TECHNIQUE"})
        telemetry_shape: dict[str, Any] = {
            "source": "calibration-scenario",
            "target_host": parent.reference_scenario["target_host"],
        }
        context_topology: dict[str, Any] = {
            "family": parent.family,
            "target_host": parent.reference_scenario["target_host"],
        }
        if "VARY_PARAMETER" in operator_names:
            telemetry_shape["parameter_variant"] = "lab-alias"
        if "INJECT_EVASION_DIRECTIVE" in operator_names:
            telemetry_shape["discriminator_representation"] = "varied"
        if "OFF_SCRIPT_SUPPLY" in operator_names:
            context_topology["off_script"] = True
        if "REVERSE_GEN_SEED" in operator_names:
            context_topology["reverse_generated"] = True

        discriminator = technique_discriminators(parent.covering_detection_id)
        visible_tokens = [] if evasion else discriminator["tokens"]
        visible_telemetry = " ".join(visible_tokens)
        variant_id = f"variant-{plan.plan_id.removeprefix('calib-plan-')}"
        variants.append(
            CalibrationVariant(
                variant_id=variant_id,
                parent_id=parent.parent_id,
                family=parent.family,
                covering_detection_id=parent.covering_detection_id,
                plan=plan,
                d_applied=d_applied,
                episode_view={
                    "episode_id": variant_id,
                    "target_host": parent.reference_scenario["target_host"],
                },
                telemetry_view={
                    "action_sequence": list(overlay.red_order),
                    "event_graph": {"ordered": list(overlay.red_order)},
                    "parameter_families": {"mutation_classes": list(operator_names)},
                    "context_topology": context_topology,
                    "artifacts": {"plan_id": plan.plan_id},
                    "attack_mappings": [
                        {"technique_id": technique_id}
                        for technique_id in _mutated_attack_ids(parent, operator_names)
                    ],
                    "telemetry_shape": telemetry_shape,
                    "detector_outcomes": {
                        parent.covering_detection_id: "partial" if evasion else "fired"
                    },
                },
                model_visible_telemetry=visible_telemetry,
                discriminator_evasion=evasion,
                negative_control=d_applied >= cousin_engine.DEFAULT_THRESHOLDS["new_max_distance"],
            )
        )
    return tuple(variants)


def parent_reference_record(parent: CalibrationParent) -> dict[str, Any]:
    scenario = parent.reference_scenario
    episode_view = {"episode_id": parent.parent_id, "target_host": scenario["target_host"]}
    telemetry_view = {
        "action_sequence": list(scenario["red_order"]),
        "event_graph": {"ordered": list(scenario["red_order"])},
        "context_topology": {"family": parent.family, "target_host": scenario["target_host"]},
        "attack_mappings": [
            {"technique_id": technique_id} for technique_id in parent.technique_ids
        ],
        "telemetry_shape": {
            "source": "calibration-scenario",
            "target_host": scenario["target_host"],
        },
    }
    signature = signatures.build_signature(episode_view, telemetry_view)
    return {
        **signatures.reference_record_fields(signature),
        "record_id": parent.parent_id,
        "signature_id": parent.parent_id,
        "kind": "calibration_parent",
        "family": parent.family,
        "tactic": parent.family,
        "technique_ids": list(parent.technique_ids),
        "covering_detection_id": parent.covering_detection_id,
        "relationship": "SAME",
        "detection_response": "COVERED",
    }


def _record_id(record: dict[str, Any]) -> str:
    return str(record.get("record_id") or record.get("signature_id") or "")


def _record_family(record: dict[str, Any]) -> str:
    family = record.get("family") or (record.get("context_topology") or {}).get("family")
    if family:
        return str(family)
    source_classes = (record.get("context_topology") or {}).get("source_classes") or ()
    if isinstance(source_classes, str):
        return source_classes
    return "+".join(sorted(str(value) for value in source_classes if value))


def _candidate_metadata(candidates: cousin_engine.CandidateSetReceipt) -> dict[str, Any]:
    records = [item["record"] for item in candidates.candidates]
    return {
        "semantic_query": str(candidates.health.get("semantic_query") or ""),
        "candidate_set_size": len(records),
        "candidate_ids": tuple(_record_id(record) for record in records if _record_id(record)),
        "candidate_families": tuple(
            sorted({_record_family(record) for record in records if _record_family(record)})
        ),
        "measurement_valid": bool(records),
    }


def grade_blind(child: CalibrationVariant, snapshot: ReadOnlyKnnSnapshot) -> BlindGrade:
    """Real signature→snapshot.knn→candidate_set→grade path, without parent id."""
    before = snapshot.stats().get("row_count")
    signature = signatures.build_signature(child.episode_view, child.telemetry_view)
    candidates = cousin_engine.retrieve_candidate_axes(signature, snapshot)
    coverage = cousin_engine.CoverageView(
        applicable_detection_ids=(child.covering_detection_id,),
        fired_detection_ids=() if child.discriminator_evasion else (child.covering_detection_id,),
        partial_detection_ids=(child.covering_detection_id,) if child.discriminator_evasion else (),
        telemetry_healthy=True,
    )
    assessment = cousin_engine.grade(signature, candidates, coverage)
    after = snapshot.stats().get("row_count")
    if before != after:
        raise RuntimeError("read-only calibration snapshot changed while grading a child")
    metadata = _candidate_metadata(candidates)
    candidate_records = [item["record"] for item in candidates.candidates]
    selected = next(
        (
            record
            for record in candidate_records
            if _record_id(record) == assessment.reference_signature_id
        ),
        {},
    )
    return BlindGrade(
        variant=child,
        relationship=assessment.relationship,
        response=assessment.defense_response,
        distance=assessment.composite,
        decomposition=asdict(assessment.decomposition),
        confidence=assessment.confidence,
        reference_signature_id=assessment.reference_signature_id,
        semantic_query=metadata["semantic_query"],
        candidate_set_size=metadata["candidate_set_size"],
        candidate_ids=metadata["candidate_ids"],
        parent_present_in_candidates=child.parent_id in metadata["candidate_ids"],
        family_parent_present_in_candidates=child.family in metadata["candidate_families"],
        reference_family=_record_family(selected),
        measurement_valid=metadata["measurement_valid"],
    )


def _curve_row(result: BlindGrade) -> dict[str, Any]:
    discriminator = technique_discriminators(result.variant.covering_detection_id)
    oracle, matched = evidence_presence(
        result.variant.model_visible_telemetry, discriminator["tokens"]
    )
    detector_signal = set(result.variant.telemetry_view.get("detector_outcomes", {}).values())
    if "fired" in detector_signal:
        oracle_response = "COVERED"
    elif detector_signal & {"partial", "missed"}:
        oracle_response = "NEAR_MISS"
    elif oracle == INDETERMINATE:
        oracle_response = "INDETERMINATE"
    else:
        oracle_response = "COVERED" if oracle != ABSENT else "NEAR_MISS"
    return {
        "variant_id": result.variant.variant_id,
        "parent_id": result.variant.parent_id,
        "family": result.variant.family,
        "covering_detection_id": result.variant.covering_detection_id,
        "d_applied": result.variant.d_applied,
        "graded_distance": round(result.distance, 6),
        "relationship": result.relationship,
        "grader_response": result.response,
        "oracle_response": oracle_response,
        "oracle_result": oracle,
        "matched_discriminators": matched,
        "oracle_independence_established": bool(detector_signal),
        "oracle_detector_signal": sorted(detector_signal),
        "discriminator_evasion": result.variant.discriminator_evasion,
        "negative_control": result.variant.negative_control,
        "confidence": round(result.confidence, 6),
        "reference_signature_id": result.reference_signature_id,
        "reference_family": result.reference_family,
        "semantic_query": result.semantic_query,
        "candidate_set_size": result.candidate_set_size,
        "parent_present_in_candidates": result.parent_present_in_candidates,
        "family_parent_present_in_candidates": result.family_parent_present_in_candidates,
        "measurement_valid": result.measurement_valid,
        **{f"distance_{key}": value for key, value in result.decomposition.items()},
    }


def _propose_thresholds(
    rows: list[dict[str, Any]], *, controls_passed: bool
) -> dict[str, Any] | None:
    if not controls_passed:
        return None
    thresholds = cousin_engine.DEFAULT_THRESHOLDS
    same_observed = [
        row["graded_distance"]
        for row in rows
        if row["d_applied"] <= thresholds["same_max_distance"]
    ]
    similar_observed = [
        row["graded_distance"]
        for row in rows
        if row["d_applied"] <= thresholds["similar_max_distance"]
    ]
    new_observed = [
        row["graded_distance"] for row in rows if row["d_applied"] <= thresholds["new_max_distance"]
    ]
    proposed_same = min(max(same_observed, default=thresholds["same_max_distance"]) + 0.01, 0.25)
    proposed_similar = min(
        max(
            max(similar_observed, default=thresholds["similar_max_distance"]) + 0.01,
            proposed_same,
        ),
        0.80,
    )
    proposed_new = min(
        max(
            max(new_observed, default=thresholds["new_max_distance"]) + 0.01,
            proposed_similar,
        ),
        0.99,
    )
    return {
        "status": "operator_confirmation_required",
        "proposal_version": "bully-cousin-thresholds-v2-proposal",
        "proposed_thresholds": {
            "same_max_distance": round(proposed_same, 4),
            "similar_max_distance": round(proposed_similar, 4),
            "new_max_distance": round(proposed_new, 4),
        },
        "distance_policy_for_rerun": "CALIB_DISTANCE_POLICY_V2_PROPOSAL",
        "required_action": "apply as a new policy version, freeze a fresh sweep, rerun",
    }


def score(
    results: tuple[BlindGrade, ...],
    *,
    monotonic_tolerance: float = 0.05,
    controls: dict[str, Any] | None = None,
) -> CalibrationReport:
    controls_passed = controls is None or bool(controls.get("passed"))
    if not controls_passed:
        return CalibrationReport(
            passed=False,
            policy_version=CALIB_DISTANCE_POLICY_VERSION,
            parent_set_version=CALIB_PARENT_SET_VERSION,
            parent_snapshot_hash=CALIB_PARENTS_V1_SNAPSHOT_HASH,
            sweep_version=CALIB_SWEEP_VERSION,
            thresholds_version=cousin_engine.THRESHOLDS_VERSION,
            curve=(),
            by_family={},
            failures={},
            indeterminate=(),
            calibration_proposal=None,
            status="INVALID",
            controls=controls or {},
            instrument_health=(controls or {}).get("retrieval_health", {}),
        )
    rows = [_curve_row(result) for result in results]
    failures: dict[str, list[dict[str, Any]]] = {
        "mid_band_graded_new": [],
        "variant_graded_same": [],
        "non_monotonic": [],
        "band_crossing": [],
        "false_cousin": [],
        "wrong_parent": [],
        "response_axis": [],
    }
    indeterminate: list[dict[str, Any]] = []
    by_parent: dict[str, list[dict[str, Any]]] = {}
    by_family: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_parent.setdefault(row["parent_id"], []).append(row)
        by_family.setdefault(row["family"], []).append(row)
        x_value = row["d_applied"]
        relationship = row["relationship"]
        if relationship == "ANOMALOUS_UNCLASSIFIED" or row["oracle_response"] == "INDETERMINATE":
            indeterminate.append(row)
            continue
        if 0.05 < x_value <= 0.40 and relationship == "NEW":
            failures["mid_band_graded_new"].append(row)
        if x_value > 0.05 and relationship == "SAME":
            failures["variant_graded_same"].append(row)
        if row["negative_control"] and relationship in {"SAME", "SIMILAR"}:
            failures["false_cousin"].append(row)
        if row["reference_signature_id"] != row["parent_id"]:
            failures["wrong_parent"].append(row)
        if row["discriminator_evasion"] and row["oracle_response"] != "NEAR_MISS":
            failures["response_axis"].append(row)
        if abs(row["graded_distance"] - x_value) > 0.30:
            failures["band_crossing"].append(row)

    for parent_id, parent_rows in by_parent.items():
        ordered = sorted(parent_rows, key=lambda row: row["d_applied"])
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if current["graded_distance"] + monotonic_tolerance < previous["graded_distance"]:
                failures["non_monotonic"].append(
                    {"parent_id": parent_id, "previous": previous, "current": current}
                )

    passed = not any(failures.values()) and not indeterminate
    return CalibrationReport(
        passed=passed,
        policy_version=CALIB_DISTANCE_POLICY_VERSION,
        parent_set_version=CALIB_PARENT_SET_VERSION,
        parent_snapshot_hash=CALIB_PARENTS_V1_SNAPSHOT_HASH,
        sweep_version=CALIB_SWEEP_VERSION,
        thresholds_version=cousin_engine.THRESHOLDS_VERSION,
        curve=tuple(rows),
        by_family={key: tuple(value) for key, value in sorted(by_family.items())},
        failures={key: tuple(value) for key, value in failures.items()},
        indeterminate=tuple(indeterminate),
        calibration_proposal=(
            None if passed else _propose_thresholds(rows, controls_passed=controls_passed)
        ),
        controls=controls or {},
        instrument_health={
            "degenerate_retrieval_rate": _rate(
                sum(row["candidate_set_size"] == 0 for row in rows), len(rows)
            ),
            "parent_or_family_candidate_rate": _rate(
                sum(
                    row["parent_present_in_candidates"]
                    or row["family_parent_present_in_candidates"]
                    for row in rows
                ),
                len(rows),
            ),
        },
    )


def write_artifacts(report: CalibrationReport, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "calibration_report.json"
    csv_path = output_dir / "calibration_curve.csv"
    plot_path = output_dir / "calibration_curve.svg"
    report_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    if report.status == "INVALID":
        return {"report": str(report_path)}
    rows = list(report.curve)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)

    points = [(50 + row["d_applied"] * 500, 550 - row["graded_distance"] * 500) for row in rows]
    circles = "\n".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#2563eb" />' for x, y in points
    )
    plot_path.write_text(
        "\n".join(
            [
                '<svg xmlns="http://www.w3.org/2000/svg" width="620" height="620" viewBox="0 0 620 620">',
                '<rect width="620" height="620" fill="white"/>',
                '<line x1="50" y1="550" x2="550" y2="550" stroke="black"/>',
                '<line x1="50" y1="550" x2="50" y2="50" stroke="black"/>',
                '<line x1="50" y1="550" x2="550" y2="50" stroke="#94a3b8" stroke-dasharray="6 6"/>',
                '<text x="250" y="590">constructed distance</text>',
                '<text x="15" y="330" transform="rotate(-90 15 330)">graded distance</text>',
                circles,
                "</svg>",
            ]
        ),
        encoding="utf-8",
    )
    return {"report": str(report_path), "csv": str(csv_path), "plot": str(plot_path)}


def run_bench(snapshot: ReadOnlyKnnSnapshot, output_dir: Path) -> CalibrationReport:
    before = snapshot.stats().get("row_count")
    results = tuple(
        grade_blind(variant, snapshot)
        for parent in CALIB_PARENTS_V1
        for variant in generate_variants(parent)
    )
    after = snapshot.stats().get("row_count")
    if before != after:
        raise RuntimeError("calibration children contaminated the Organ snapshot")
    controls = _calibration_controls(results, snapshot)
    report = score(results, controls=controls)
    write_artifacts(report, output_dir)
    return report


def load_specimen_corpus(path: Path) -> dict[str, Any]:
    corpus = json.loads(path.read_text(encoding="utf-8"))
    if corpus.get("schema") not in {"SPECIMEN_CORPUS_V1", "SPECIMEN_CORPUS_V2"}:
        raise ValueError("not a supported SPECIMEN_CORPUS artifact")
    observed_hash = hashlib.sha256(_canonical(corpus.get("specimens") or []).encode()).hexdigest()
    if observed_hash != corpus.get("snapshot_hash"):
        raise ValueError("specimen corpus snapshot hash mismatch")
    return corpus


def specimen_source_class(specimen: dict[str, Any]) -> str:
    """Return the explicit class label, with V2-artifact compatibility."""
    if specimen.get("source_class"):
        return str(specimen["source_class"])
    shape = specimen.get("engine_view", {}).get("telemetry_view", {}).get("telemetry_shape", {})
    sources = shape.get("sourcetypes") or ()
    return str(sources[0]) if len(sources) == 1 else ""


def corpus_parent_reference_record(entry: dict[str, Any]) -> dict[str, Any]:
    """Project a parent evidence view into Organ without consulting scorer truth."""
    engine_view = entry["engine_view"]
    view = entry["engine_view"]["telemetry_view"]
    signature = signatures.build_signature(engine_view["episode_view"], view)
    return {
        **signatures.reference_record_fields(signature),
        "record_id": entry["specimen_id"],
        "signature_id": entry["specimen_id"],
        "kind": "specimen_parent",
        "relationship": "SAME",
        "detection_response": "INDETERMINATE",
        "trust_tier": entry["engine_view"].get("trust_tier"),
    }


def grade_corpus_blind(
    specimen: dict[str, Any], snapshot: ReadOnlyKnnSnapshot
) -> BlindCorpusVerdict:
    """Produce an engine verdict from the evidence view, before any truth join."""
    engine_view = specimen["engine_view"]
    signature = signatures.build_signature(
        engine_view["episode_view"], engine_view["telemetry_view"]
    )
    candidates = cousin_engine.retrieve_candidate_axes(signature, snapshot)
    outcomes = engine_view["telemetry_view"].get("detector_outcomes") or {}
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
    metadata = _candidate_metadata(candidates)
    selected = next(
        (
            item["record"]
            for item in candidates.candidates
            if _record_id(item["record"]) == assessment.reference_signature_id
        ),
        {},
    )
    return BlindCorpusVerdict(
        specimen_id=specimen["specimen_id"],
        source_lane=specimen["source_lane"],
        relationship=assessment.relationship,
        response=assessment.defense_response,
        distance=assessment.composite,
        decomposition=asdict(assessment.decomposition),
        confidence=assessment.confidence,
        reference_signature_id=assessment.reference_signature_id,
        semantic_query=metadata["semantic_query"],
        candidate_set_size=metadata["candidate_set_size"],
        candidate_ids=metadata["candidate_ids"],
        candidate_families=metadata["candidate_families"],
        reference_family=_record_family(selected),
        measurement_valid=metadata["measurement_valid"],
    )


def _visible_telemetry(corpus_dir: Path, specimen: dict[str, Any]) -> str:
    payload = json.loads((corpus_dir / "evidence" / specimen["evidence_ref"]).read_text())
    return "\n".join(
        _canonical(event)
        for sourcetype in sorted(payload.get("telemetry") or {})
        for event in payload["telemetry"][sourcetype]
    )


def _oracle_response(
    telemetry: str,
    techniques: list[str],
    detector_outcomes: dict[str, str] | None = None,
) -> tuple[str, dict[str, Any]]:
    observations: dict[str, Any] = {}
    for technique_id in techniques:
        discriminator = technique_discriminators(technique_id)
        result, matched = evidence_presence(telemetry, discriminator["tokens"])
        observations[technique_id] = {"result": result, "matched": matched}
    detector_values = set((detector_outcomes or {}).values())
    contract = {
        "raw_evidence_source": "shipped evidence payload telemetry",
        "forge_evasion_lever": "raw discriminator-token representation",
        "independent_signal": "live detector outcomes",
        "independence_established": bool(detector_values),
        "detector_values": sorted(detector_values),
    }
    observations["_independence_contract"] = contract
    if "fired" in detector_values:
        return "COVERED", observations
    if detector_values & {"partial", "missed"}:
        return "NEAR_MISS", observations
    # Raw-token observations are retained for diagnosis, but they are not an
    # independent oracle because the forge deliberately mutates those tokens.
    return "INDETERMINATE", observations


_FEATURE_EDIT_FIELDS = (
    "action_sequence",
    "event_graph",
    "parameter_families",
    "context_topology",
    "artifacts",
    "attack_mappings",
    "telemetry_shape",
)


def signature_feature_edit_distance(
    subject_view: dict[str, Any], reference_view: dict[str, Any]
) -> float:
    """Measure changed signature fields independently of forge operator weights."""
    changed = sum(
        _canonical(subject_view.get(field)) != _canonical(reference_view.get(field))
        for field in _FEATURE_EDIT_FIELDS
    )
    return round(changed / len(_FEATURE_EDIT_FIELDS), 6)


def _baseline_row(
    verdict: BlindCorpusVerdict,
    *,
    specimen: dict[str, Any],
    truth: dict[str, Any],
    corpus_dir: Path,
    parent_specimen: dict[str, Any] | None,
) -> dict[str, Any]:
    outcomes = specimen["engine_view"]["telemetry_view"].get("detector_outcomes") or {}
    response, detail = _oracle_response(
        _visible_telemetry(corpus_dir, specimen), truth["data_yml_techniques"], outcomes
    )
    source_classes = (
        specimen["engine_view"]["telemetry_view"]
        .get("context_topology", {})
        .get("source_classes", [])
    )
    expected_relationship = _expected_relationship(float(truth["construction_distance"]))
    expected_id = str(truth.get("parent_id") or specimen["specimen_id"])
    expected_family = (
        signatures.signature_family(
            signatures.build_signature(
                parent_specimen["engine_view"]["episode_view"],
                parent_specimen["engine_view"]["telemetry_view"],
            )
        )
        if parent_specimen
        else ""
    )
    exact_parent_present = expected_id in verdict.candidate_ids
    family_parent_present = bool(expected_family and expected_family in verdict.candidate_families)
    measurement_valid = verdict.measurement_valid and (
        exact_parent_present or family_parent_present
    )
    oracle_contract = detail.get("_independence_contract", {})
    return {
        "specimen_id": verdict.specimen_id,
        "source_lane": verdict.source_lane,
        "parent_id": truth["parent_id"],
        "d_applied": truth["construction_distance"],
        "expected_relationship": expected_relationship,
        "band_crossing_correct": verdict.relationship == expected_relationship,
        "graded_distance": round(verdict.distance, 6),
        "relationship": verdict.relationship,
        "grader_response": verdict.response,
        "oracle_response": response,
        "oracle_detail": detail,
        "confidence": round(verdict.confidence, 6),
        "reference_signature_id": verdict.reference_signature_id,
        "reference_family": verdict.reference_family,
        "scenario_family": source_classes[0] if len(source_classes) == 1 else "mixed_or_unknown",
        "exact_parent_correct": verdict.reference_signature_id == expected_id,
        "family_parent_correct": bool(
            expected_family and verdict.reference_family == expected_family
        ),
        "candidate_set_size": verdict.candidate_set_size,
        "true_parent_present_in_candidates": exact_parent_present,
        "family_parent_present_in_candidates": family_parent_present,
        "semantic_query": verdict.semantic_query,
        "measurement_valid": measurement_valid,
        "engine_verdict_counted": measurement_valid,
        "oracle_independence_established": bool(oracle_contract.get("independence_established")),
        "signature_feature_edit_distance": signature_feature_edit_distance(
            specimen["engine_view"]["telemetry_view"],
            parent_specimen["engine_view"]["telemetry_view"] if parent_specimen else {},
        ),
        **{f"distance_{key}": value for key, value in verdict.decomposition.items()},
    }


def _classify_baseline_row(
    row: dict[str, Any],
    failures: dict[str, list[dict[str, Any]]],
    unresolved: list[dict[str, Any]],
    indeterminate: list[dict[str, Any]],
) -> None:
    relationship, response = row["relationship"], row["grader_response"]
    distance = row["d_applied"]
    if not row["measurement_valid"]:
        failures["instrument_failure"].append(row)
        return
    if relationship == "ANOMALOUS_UNCLASSIFIED":
        unresolved.append(row)
    if response == "INDETERMINATE" or row["oracle_response"] == "INDETERMINATE":
        indeterminate.append(row)
    if 0.05 < distance <= 0.40 and relationship == "NEW":
        failures["mid_distance_new_blind_spot"].append(row)
    if distance > 0.05 and relationship == "SAME":
        failures["real_same_overclaim"].append(row)
    if row["parent_id"] and row["reference_signature_id"] != row["parent_id"]:
        failures["wrong_parent"].append(row)
    if row["oracle_response"] == "NEAR_MISS" and response not in {"NEAR_MISS", "INDETERMINATE"}:
        failures["response_axis"].append(row)


def _find_non_monotonic(
    by_parent: dict[str, list[dict[str, Any]]], tolerance: float
) -> list[dict[str, Any]]:
    failures = []
    for parent_id, parent_rows in by_parent.items():
        ordered = sorted(parent_rows, key=lambda item: (item["d_applied"], item["specimen_id"]))
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if current["graded_distance"] + tolerance < previous["graded_distance"]:
                failures.append({"parent_id": parent_id, "previous": previous, "current": current})
    return failures


def _expected_relationship(distance: float) -> str:
    thresholds = cousin_engine.DEFAULT_THRESHOLDS
    if distance <= thresholds["same_max_distance"]:
        return "SAME"
    if distance <= thresholds["similar_max_distance"]:
        return "SIMILAR"
    if distance <= thresholds["new_max_distance"]:
        return "NEW"
    return "DIFFERENT"


def _known_near_far_controls() -> dict[str, Any]:
    reference_episode = {"episode_id": "control-reference", "target_host": "control-host"}
    reference_view = {
        "action_sequence": ["alpha", "charlie"],
        "event_graph": {"ordered": ["alpha", "charlie"]},
        "context_topology": {"family": "control-family", "target_host": "control-host"},
        "attack_mappings": [{"technique_id": "T1000"}],
        "telemetry_shape": {"source": "control-a"},
    }
    reference_signature = signatures.build_signature(reference_episode, reference_view)
    reference = {
        **signatures.reference_record_fields(reference_signature),
        "record_id": "control-reference",
        "signature_id": "control-reference",
    }

    def classify(name: str, view: dict[str, Any], semantic_distance: float) -> dict[str, Any]:
        subject = signatures.build_signature(
            {"episode_id": f"control-{name}", "target_host": "control-host"}, view
        )
        receipt = cousin_engine.candidate_set(
            subject, semantic_candidates=[(reference, semantic_distance)]
        )
        assessment = cousin_engine.grade(
            subject,
            receipt,
            cousin_engine.CoverageView(
                applicable_detection_ids=("control",), fired_detection_ids=("control",)
            ),
        )
        return {
            "relationship": assessment.relationship,
            "distance": round(assessment.composite, 6),
        }

    near_view = {
        **reference_view,
        "action_sequence": ["alpha", "bravo"],
        "event_graph": {"ordered": ["alpha", "bravo"]},
    }
    far_view = {
        **reference_view,
        "action_sequence": ["delta", "echo"],
        "event_graph": {"ordered": ["delta", "echo"]},
        "telemetry_shape": {"source": "control-b"},
    }
    near = classify("near", near_view, 0.2)
    far = classify("far", far_view, 0.4)
    return {
        "passed": near["relationship"] == "SIMILAR" and far["relationship"] == "NEW",
        "near": {**near, "expected": "SIMILAR"},
        "far": {**far, "expected": "NEW"},
    }


def _retrieval_health(
    rows: list[dict[str, Any]],
    *,
    parent_key: str,
    family_key: str,
) -> dict[str, Any]:
    degenerate = sum(row["candidate_set_size"] == 0 for row in rows)
    hits = sum(bool(row[parent_key] or row[family_key]) for row in rows)
    hit_rate = _rate(hits, len(rows)) or 0.0
    degenerate_rate = _rate(degenerate, len(rows)) or 0.0
    return {
        "passed": (
            hit_rate >= RETRIEVAL_MIN_HIT_RATE and degenerate_rate <= MAX_DEGENERATE_RETRIEVAL_RATE
        ),
        "rows": len(rows),
        "parent_or_family_hits": hits,
        "parent_or_family_hit_rate": hit_rate,
        "degenerate_candidate_sets": degenerate,
        "degenerate_retrieval_rate": degenerate_rate,
        "minimum_hit_rate": RETRIEVAL_MIN_HIT_RATE,
        "maximum_degenerate_rate": MAX_DEGENERATE_RETRIEVAL_RATE,
    }


def _calibration_controls(
    results: tuple[BlindGrade, ...], snapshot: ReadOnlyKnnSnapshot
) -> dict[str, Any]:
    rows = [
        {
            "candidate_set_size": result.candidate_set_size,
            "parent": result.parent_present_in_candidates,
            "family": result.family_parent_present_in_candidates,
        }
        for result in results
    ]
    retrieval = _retrieval_health(rows, parent_key="parent", family_key="family")
    near_far = _known_near_far_controls()
    identity_failures = []
    for parent in CALIB_PARENTS_V1:
        reference = parent_reference_record(parent)
        signature = signatures.build_signature(
            {
                "episode_id": parent.parent_id,
                "target_host": parent.reference_scenario["target_host"],
            },
            {
                key: reference[key]
                for key in (
                    "action_sequence",
                    "event_graph",
                    "parameter_families",
                    "context_topology",
                    "artifacts",
                    "attack_mappings",
                    "telemetry_shape",
                )
            },
        )
        candidates = cousin_engine.candidate_set(signature, semantic_candidates=[(reference, 0.0)])
        assessment = cousin_engine.grade(
            signature,
            candidates,
            cousin_engine.CoverageView(
                applicable_detection_ids=(parent.covering_detection_id,),
                fired_detection_ids=(parent.covering_detection_id,),
            ),
        )
        if (
            assessment.relationship != "SAME"
            or assessment.composite > cousin_engine.DEFAULT_THRESHOLDS["same_max_distance"]
        ):
            identity_failures.append(
                {
                    "parent_id": parent.parent_id,
                    "relationship": assessment.relationship,
                    "reference_signature_id": assessment.reference_signature_id,
                    "distance": assessment.composite,
                }
            )
    identity = {
        "passed": not identity_failures,
        "checked": len(CALIB_PARENTS_V1),
        "failures": identity_failures,
    }
    return {
        "passed": identity["passed"] and retrieval["passed"] and near_far["passed"],
        "identity": identity,
        "retrieval_health": retrieval,
        "known_near_far": near_far,
    }


def _baseline_controls(
    verdicts: tuple[BlindCorpusVerdict, ...],
    *,
    corpus: dict[str, Any],
    ledger: SpecimenLedger,
) -> dict[str, Any]:
    specimens = {item["specimen_id"]: item for item in corpus["specimens"]}
    truth_by_id = {record["specimen_id"]: record for record in ledger.records()}
    rows: list[dict[str, Any]] = []
    identity_failures: list[dict[str, Any]] = []
    for verdict in verdicts:
        truth = truth_by_id[verdict.specimen_id]
        expected_id = str(truth.get("parent_id") or verdict.specimen_id)
        parent = specimens.get(expected_id)
        expected_family = ""
        if parent:
            expected_signature = signatures.build_signature(
                parent["engine_view"]["episode_view"], parent["engine_view"]["telemetry_view"]
            )
            expected_family = signatures.signature_family(expected_signature)
        exact_present = expected_id in verdict.candidate_ids
        family_present = bool(expected_family and expected_family in verdict.candidate_families)
        rows.append(
            {
                "candidate_set_size": verdict.candidate_set_size,
                "parent": exact_present,
                "family": family_present,
            }
        )
        if truth.get("parent_id") is None:
            signature = signatures.build_signature(
                specimens[verdict.specimen_id]["engine_view"]["episode_view"],
                specimens[verdict.specimen_id]["engine_view"]["telemetry_view"],
            )
            reference = corpus_parent_reference_record(specimens[verdict.specimen_id])
            identity_assessment = cousin_engine.grade(
                signature,
                cousin_engine.candidate_set(signature, semantic_candidates=[(reference, 0.0)]),
                cousin_engine.CoverageView(telemetry_healthy=True),
            )
            if (
                identity_assessment.relationship != "SAME"
                or identity_assessment.composite
                > cousin_engine.DEFAULT_THRESHOLDS["same_max_distance"]
            ):
                identity_failures.append(
                    {
                        "specimen_id": verdict.specimen_id,
                        "relationship": identity_assessment.relationship,
                        "reference_signature_id": identity_assessment.reference_signature_id,
                        "distance": identity_assessment.composite,
                        "expected_max_distance": cousin_engine.DEFAULT_THRESHOLDS[
                            "same_max_distance"
                        ],
                    }
                )
    identity = {
        "passed": not identity_failures,
        "checked": sum(
            truth_by_id[verdict.specimen_id].get("parent_id") is None for verdict in verdicts
        ),
        "failures": identity_failures,
    }
    retrieval = _retrieval_health(rows, parent_key="parent", family_key="family")
    near_far = _known_near_far_controls()
    return {
        "passed": identity["passed"] and retrieval["passed"] and near_far["passed"],
        "identity": identity,
        "retrieval_health": retrieval,
        "known_near_far": near_far,
    }


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _lane_metrics(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for lane in ("attack_data", "replay_mutation", "live_lab"):
        lane_rows = [row for row in rows if row["source_lane"] == lane]
        blind_spots = [
            row
            for row in lane_rows
            if 0.05 < row["d_applied"] <= 0.40
            and row["relationship"] in {"NEW", "DIFFERENT", "ANOMALOUS_UNCLASSIFIED"}
        ]
        overclaims = [
            row for row in lane_rows if row["d_applied"] > 0.05 and row["relationship"] == "SAME"
        ]
        band_hits = [
            row
            for row in lane_rows
            if row["relationship"] == _expected_relationship(row["d_applied"])
        ]
        result[lane] = {
            "rows": len(lane_rows),
            "band_crossing_accuracy": _rate(len(band_hits), len(lane_rows)),
            "blind_spot_rate": _rate(len(blind_spots), len(lane_rows)),
            "overclaim_rate": _rate(len(overclaims), len(lane_rows)),
            "response_distribution": dict(
                sorted(Counter(row["grader_response"] for row in lane_rows).items())
            ),
            "mean_graded_distance": (
                round(sum(row["graded_distance"] for row in lane_rows) / len(lane_rows), 6)
                if lane_rows
                else None
            ),
        }
    return result


CONSTRUCTION_CEILING_NOTE = (
    "8 FROZEN_SWEEP rungs + the d=0 parent row -> expected bands 2 SAME / "
    "4 SIMILAR / 2 NEW / 1 DIFFERENT by construction. The aggregate "
    "~5/9 (0.5556) band-crossing accuracy this lane tends to land on is a "
    "construction artifact of the rung/band mix, not a discrimination "
    "score -- never a target to tune toward, and never the reported "
    "product (SA2 A3: this lane is a regression/controls instrument; the "
    "product metric is the real-vs-real discovery lane's joint "
    "relationship x response outcome, see discovery_bench.py)."
)


def per_rung_band_accuracy(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """SA2.5 (A3): band-crossing accuracy broken out **per construction
    rung** (`d_applied`), replacing relationship-only band accuracy as a
    headline number for this (forge/recognition) lane. The forge stays a
    cheap, deterministic regression/controls instrument -- it is not, and
    is never reported as, the discovery-lane product metric."""
    by_rung: dict[float, list[dict[str, Any]]] = {}
    for row in rows:
        by_rung.setdefault(row["d_applied"], []).append(row)
    rungs = [
        {
            "d_applied": d_applied,
            "rows": len(rung_rows),
            "band_accuracy": _rate(
                sum(row["band_crossing_correct"] for row in rung_rows), len(rung_rows)
            ),
        }
        for d_applied, rung_rows in sorted(by_rung.items())
    ]
    return {
        "instrument_role": "regression/controls instrument (A3) -- not the product metric",
        "rungs": rungs,
        "construction_ceiling_note": CONSTRUCTION_CEILING_NOTE,
    }


def _characterize_baseline(
    rows: list[dict[str, Any]],
    failures: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    measured_rows = [row for row in rows if row["measurement_valid"]]
    band_hits = [
        row
        for row in measured_rows
        if row["relationship"] == _expected_relationship(row["d_applied"])
    ]
    blind_spots = [
        row
        for row in measured_rows
        if 0.05 < row["d_applied"] <= 0.40
        and row["relationship"] in {"NEW", "DIFFERENT", "ANOMALOUS_UNCLASSIFIED"}
    ]
    overclaims = [
        row for row in measured_rows if row["d_applied"] > 0.05 and row["relationship"] == "SAME"
    ]
    parent_rows = [row for row in measured_rows if row["parent_id"]]
    wrong_parent = failures["wrong_parent"]
    comparable_pairs = 0
    by_parent: dict[str, list[dict[str, Any]]] = {}
    for row in parent_rows:
        by_parent.setdefault(row["parent_id"], []).append(row)
    for grouped in by_parent.values():
        comparable_pairs += max(0, len(grouped) - 1)

    per_lane = _lane_metrics(measured_rows)
    family_parent_correct = sum(row["family_parent_correct"] for row in parent_rows)
    candidate_hits = sum(
        row["true_parent_present_in_candidates"] or row["family_parent_present_in_candidates"]
        for row in rows
    )
    replay, lab = per_lane["replay_mutation"], per_lane["live_lab"]
    band_delta = (
        round(replay["band_crossing_accuracy"] - lab["band_crossing_accuracy"], 6)
        if replay["band_crossing_accuracy"] is not None
        and lab["band_crossing_accuracy"] is not None
        else None
    )
    distance_delta = (
        round(replay["mean_graded_distance"] - lab["mean_graded_distance"], 6)
        if replay["mean_graded_distance"] is not None and lab["mean_graded_distance"] is not None
        else None
    )
    return {
        "published_thresholds": dict(cousin_engine.DEFAULT_THRESHOLDS),
        "band_crossing": {
            "correct": len(band_hits),
            "rows": len(measured_rows),
            "accuracy": _rate(len(band_hits), len(measured_rows)),
            "headline_note": (
                "demoted (SA2 A3): this aggregate is retained for the existing "
                "class-onboarding admit gate, never reported as the product "
                "metric -- see per_rung for the current headline breakdown."
            ),
        },
        "per_rung": per_rung_band_accuracy(measured_rows),
        "monotonicity": {
            "comparable_pairs": comparable_pairs,
            "violations": len(failures["non_monotonic"]),
            "accuracy": _rate(comparable_pairs - len(failures["non_monotonic"]), comparable_pairs),
        },
        "blind_spots": {
            "count": len(blind_spots),
            "rate": _rate(len(blind_spots), len(measured_rows)),
        },
        "overclaims": {
            "count": len(overclaims),
            "rate": _rate(len(overclaims), len(measured_rows)),
        },
        "wrong_parent": {
            "count": len(wrong_parent),
            "eligible_rows": len(parent_rows),
            "rate": _rate(len(wrong_parent), len(parent_rows)),
        },
        "family_parent": {
            "correct": family_parent_correct,
            "eligible_rows": len(parent_rows),
            "accuracy": _rate(family_parent_correct, len(parent_rows)),
        },
        "instrument_health": {
            "measurement_valid_rows": len(measured_rows),
            "measurement_invalid_rows": len(rows) - len(measured_rows),
            "degenerate_retrieval_rate": _rate(
                sum(row["candidate_set_size"] == 0 for row in rows), len(rows)
            ),
            "parent_or_family_candidate_rate": _rate(candidate_hits, len(rows)),
        },
        "response_axis": {
            "distribution": dict(
                sorted(Counter(row["grader_response"] for row in measured_rows).items())
            ),
            "oracle_distribution": dict(
                sorted(Counter(row["oracle_response"] for row in measured_rows).items())
            ),
        },
        "per_lane": per_lane,
        "lane_comparison": {
            "replay_mutation_vs_live_lab": {
                "band_accuracy_delta": band_delta,
                "mean_graded_distance_delta": distance_delta,
            }
        },
    }


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys, strict=True))
    x_mass = sum((x - x_mean) ** 2 for x in xs)
    y_mass = sum((y - y_mean) ** 2 for y in ys)
    denominator = (x_mass * y_mass) ** 0.5
    return round(numerator / denominator, 6) if denominator else None


def _x_axis_validity(rows: list[dict[str, Any]]) -> dict[str, Any]:
    xs = [float(row["d_applied"]) for row in rows]
    ys = [float(row["signature_feature_edit_distance"]) for row in rows]
    correlation = _pearson(xs, ys)
    return {
        "construction_proxy": "operator-weight construction distance",
        "independent_measure": "unweighted signature-feature edit distance",
        "rows": len(rows),
        "pearson_correlation": correlation,
        "correlated": correlation is not None and correlation > 0.0,
    }


def _baseline_reference_guard(is_v2: bool, controls_passed: bool) -> dict[str, Any]:
    if not is_v2 or not controls_passed:
        return {}
    return {
        "immutable": True,
        "designation": "first_trustworthy_redesign_reference",
        "acceptance": "match_or_beat",
        "supersedes_invalid_reference": BASELINE_CALIBRATION_V2,
        "scope": [
            "windows:security",
            "linux:auditd",
            "web:access",
            "docker:daemon",
        ],
    }


def score_baseline(
    verdicts: tuple[BlindCorpusVerdict, ...],
    *,
    corpus: dict[str, Any],
    corpus_dir: Path,
    ledger: SpecimenLedger,
    monotonic_tolerance: float = 0.05,
    controls: dict[str, Any] | None = None,
) -> BaselineCalibrationReport:
    """Join sealed truth only after every blind verdict, then score the cold reading."""
    specimens = {item["specimen_id"]: item for item in corpus["specimens"]}
    truth_by_id = {record["specimen_id"]: record for record in ledger.records()}
    rows: list[dict[str, Any]] = []
    failures: dict[str, list[dict[str, Any]]] = {
        "mid_distance_new_blind_spot": [],
        "real_same_overclaim": [],
        "non_monotonic": [],
        "wrong_parent": [],
        "response_axis": [],
        "instrument_failure": [],
    }
    unresolved: list[dict[str, Any]] = []
    indeterminate: list[dict[str, Any]] = []
    by_parent: dict[str, list[dict[str, Any]]] = {}
    for verdict in verdicts:
        truth = truth_by_id.get(verdict.specimen_id)
        if truth is None:
            raise ValueError(f"sealed truth missing for {verdict.specimen_id}")
        parent_id = str(truth.get("parent_id") or verdict.specimen_id)
        row = _baseline_row(
            verdict,
            specimen=specimens[verdict.specimen_id],
            truth=truth,
            corpus_dir=corpus_dir,
            parent_specimen=specimens.get(parent_id),
        )
        rows.append(row)
        _classify_baseline_row(row, failures, unresolved, indeterminate)
        if row["parent_id"] and row["measurement_valid"]:
            by_parent.setdefault(row["parent_id"], []).append(row)
    failures["non_monotonic"] = _find_non_monotonic(by_parent, monotonic_tolerance)
    passed = not any(failures.values()) and not unresolved and not indeterminate
    is_v2 = corpus["schema"] == "SPECIMEN_CORPUS_V2"
    characterization = _characterize_baseline(rows, failures) if is_v2 else {}
    controls = controls or {"passed": True}
    controls_passed = bool(controls.get("passed"))
    if not controls_passed:
        rows = []
        failures = {key: [] for key in failures}
        unresolved = []
        indeterminate = []
        characterization = {}
    instrument_health = controls.get("retrieval_health", {})
    diagnosis = tuple(
        name
        for name, result in controls.items()
        if isinstance(result, dict) and not result.get("passed", True)
    )
    report = BaselineCalibrationReport(
        schema=BASELINE_CALIBRATION_V3 if is_v2 else BASELINE_CALIBRATION_V1,
        passed=passed if controls_passed else False,
        corpus_snapshot_hash=corpus["snapshot_hash"],
        ledger_snapshot_hash=ledger.snapshot_hash(),
        thresholds_version=cousin_engine.THRESHOLDS_VERSION,
        cold_untuned=True,
        training_applied=False,
        threshold_tuning_applied=False,
        per_lane_counts=dict(corpus["per_lane_counts"]),
        curve=tuple(rows),
        failures={key: tuple(value) for key, value in failures.items()},
        unresolved=tuple(unresolved),
        indeterminate=tuple(indeterminate),
        characterization=characterization,
        reference_guard=_baseline_reference_guard(is_v2, controls_passed),
        status="VALID" if controls_passed else "INVALID",
        controls=controls,
        diagnosis=diagnosis,
        instrument_health=instrument_health,
        oracle_independence_contract={
            "raw_evidence_source": "_visible_telemetry reads shipped evidence payload bytes",
            "forge_evasion_lever": "discriminator-token representation in forged telemetry",
            "independent_signal": "live detector outcomes from the episode query backend",
            "rows_with_independent_signal": sum(
                row["oracle_independence_established"] for row in rows
            ),
            "rows": len(rows),
        },
        x_axis_validity=_x_axis_validity(rows) if rows else {},
    )
    if not is_v2:
        return report
    hash_payload = report.to_dict()
    hash_payload["snapshot_hash"] = None
    return replace(
        report,
        snapshot_hash=hashlib.sha256(_canonical(hash_payload).encode()).hexdigest(),
    )


def write_baseline_artifacts(report: BaselineCalibrationReport, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    version = {
        BASELINE_CALIBRATION_V3: "v3",
        BASELINE_CALIBRATION_V2: "v2",
    }.get(report.schema, "v1")
    report_path = output_dir / f"baseline_calibration_{version}.json"
    compatibility_path = output_dir / "calibration_report.json"
    curve_path = output_dir / "baseline_calibration_curve.csv"
    payload = json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    report_path.write_text(payload, encoding="utf-8")
    compatibility_path.write_text(payload, encoding="utf-8")
    if report.status == "INVALID":
        return {
            "report": str(report_path),
            "compatibility_report": str(compatibility_path),
        }
    rows = list(report.curve)
    with curve_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)
    return {
        "report": str(report_path),
        "compatibility_report": str(compatibility_path),
        "csv": str(curve_path),
    }


def run_baseline_bench(
    snapshot: ReadOnlyKnnSnapshot,
    *,
    corpus_path: Path,
    ledger: SpecimenLedger,
    output_dir: Path,
) -> BaselineCalibrationReport:
    corpus = load_specimen_corpus(corpus_path)
    if ledger.snapshot_hash() != corpus["ledger_snapshot_hash"]:
        raise ValueError("specimen corpus and sealed ledger snapshot do not match")
    before = snapshot.stats().get("row_count")
    prepare_knn = getattr(snapshot, "prepare_knn", None)
    if callable(prepare_knn):
        specimen_signatures = [
            signatures.build_signature(
                specimen["engine_view"]["episode_view"],
                specimen["engine_view"]["telemetry_view"],
            )
            for specimen in corpus["specimens"]
        ]
        prepare_knn(
            [
                query
                for signature in specimen_signatures
                for query in cousin_engine.candidate_axis_queries(signature)
            ],
            k=8,
            batch_size=16,
        )
    verdicts = tuple(grade_corpus_blind(specimen, snapshot) for specimen in corpus["specimens"])
    if snapshot.stats().get("row_count") != before:
        raise RuntimeError("baseline specimens contaminated the Organ snapshot")
    controls = _baseline_controls(verdicts, corpus=corpus, ledger=ledger)
    report = score_baseline(
        verdicts,
        corpus=corpus,
        corpus_dir=corpus_path.parent,
        ledger=ledger,
        controls=controls,
    )
    write_baseline_artifacts(report, output_dir)
    return report


def _run_filtered_corpus_bench(
    snapshot: ReadOnlyKnnSnapshot,
    *,
    corpus: dict[str, Any],
    selected: list[dict[str, Any]],
    corpus_path: Path,
    ledger: SpecimenLedger,
    output_dir: Path,
    reference_guard: dict[str, Any],
) -> tuple[BaselineCalibrationReport, dict[str, Any]]:
    """Grade an isolated denominator against the standing mixed snapshot."""
    cohort = {
        **corpus,
        "snapshot_hash": hashlib.sha256(_canonical(selected).encode()).hexdigest(),
        "per_lane_counts": {
            lane: sum(item["source_lane"] == lane for item in selected)
            for lane in ("attack_data", "replay_mutation", "live_lab")
        },
        "specimens": selected,
    }
    before = snapshot.stats().get("row_count")
    prepare_knn = getattr(snapshot, "prepare_knn", None)
    if callable(prepare_knn):
        cohort_signatures = [
            signatures.build_signature(
                specimen["engine_view"]["episode_view"],
                specimen["engine_view"]["telemetry_view"],
            )
            for specimen in selected
        ]
        prepare_knn(
            [
                query
                for signature in cohort_signatures
                for query in cousin_engine.candidate_axis_queries(signature)
            ],
            k=8,
            batch_size=16,
        )
    verdicts = tuple(grade_corpus_blind(specimen, snapshot) for specimen in selected)
    if snapshot.stats().get("row_count") != before:
        raise RuntimeError("class cohort contaminated the Organ snapshot")
    controls = _baseline_controls(verdicts, corpus=cohort, ledger=ledger)
    report = score_baseline(
        verdicts,
        corpus=cohort,
        corpus_dir=corpus_path.parent,
        ledger=ledger,
        controls=controls,
    )
    report = replace(
        report,
        reference_guard=reference_guard,
        snapshot_hash=None,
    )
    hash_payload = report.to_dict()
    hash_payload["snapshot_hash"] = None
    report = replace(
        report,
        snapshot_hash=hashlib.sha256(_canonical(hash_payload).encode()).hexdigest(),
    )
    write_baseline_artifacts(report, output_dir)
    return report, cohort


def run_class_cohort_bench(
    snapshot: ReadOnlyKnnSnapshot,
    *,
    source_class: str,
    corpus_path: Path,
    ledger: SpecimenLedger,
    output_dir: Path,
) -> BaselineCalibrationReport:
    """Run the full P7.4 controls and curve for exactly one source class.

    The snapshot may remain mixed-class, which is intentional: the cohort
    denominator is isolated while candidate retrieval still exercises the
    source-agnostic standing corpus.  A class with failed controls emits an
    INVALID report and no curve through the existing artifact writer.
    """
    corpus = load_specimen_corpus(corpus_path)
    selected = [
        specimen
        for specimen in corpus["specimens"]
        if specimen_source_class(specimen) == source_class
    ]
    if not selected:
        raise ValueError(f"source class has no specimens: {source_class}")
    report, cohort = _run_filtered_corpus_bench(
        snapshot,
        corpus=corpus,
        selected=selected,
        corpus_path=corpus_path,
        ledger=ledger,
        output_dir=output_dir,
        reference_guard={
            "immutable": True,
            "designation": "source_class_cohort",
            "acceptance": "admit_flag_or_reject_against_v3_profile",
            "source_class": source_class,
            "standing_corpus_snapshot_hash": corpus["snapshot_hash"],
        },
    )
    summary = {
        "schema": "CLASS_COHORT_CALIBRATION_V1",
        "source_class": source_class,
        "corpus_snapshot_hash": cohort["snapshot_hash"],
        "standing_corpus_snapshot_hash": corpus["snapshot_hash"],
        "status": report.status,
        "controls": report.controls,
        "characterization": report.characterization,
        "cold_untuned": True,
        "training_applied": False,
        "threshold_tuning_applied": False,
    }
    (output_dir / "class_cohort_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def run_source_scope_bench(
    snapshot: ReadOnlyKnnSnapshot,
    *,
    source_classes: frozenset[str],
    corpus_path: Path,
    ledger: SpecimenLedger,
    output_dir: Path,
) -> BaselineCalibrationReport:
    """Run a regression scope while retaining new classes in retrieval."""
    corpus = load_specimen_corpus(corpus_path)
    selected = [
        specimen
        for specimen in corpus["specimens"]
        if specimen_source_class(specimen) in source_classes
        or specimen["source_lane"] == "live_lab"
    ]
    report, cohort = _run_filtered_corpus_bench(
        snapshot,
        corpus=corpus,
        selected=selected,
        corpus_path=corpus_path,
        ledger=ledger,
        output_dir=output_dir,
        reference_guard={
            "immutable": True,
            "designation": "standing_v3_regression_scope",
            "acceptance": "match_or_beat_baseline_calibration_v3",
            "scope": sorted(source_classes),
            "standing_corpus_snapshot_hash": corpus["snapshot_hash"],
            "mixed_snapshot": True,
        },
    )
    summary = {
        "schema": "SOURCE_SCOPE_CALIBRATION_V1",
        "source_classes": sorted(source_classes),
        "corpus_snapshot_hash": cohort["snapshot_hash"],
        "standing_corpus_snapshot_hash": corpus["snapshot_hash"],
        "status": report.status,
        "controls": report.controls,
        "characterization": report.characterization,
        "cold_untuned": True,
        "training_applied": False,
        "threshold_tuning_applied": False,
    }
    (output_dir / "source_scope_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report
