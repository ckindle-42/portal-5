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
    return {
        "record_id": parent.parent_id,
        "signature_id": parent.parent_id,
        "kind": "calibration_parent",
        "family": parent.family,
        "tactic": parent.family,
        "technique_ids": list(parent.technique_ids),
        "action_sequence": list(scenario["red_order"]),
        "behavior_sequence": " ".join(scenario["red_order"]),
        "telemetry_shape": {
            "source": "calibration-scenario",
            "target_host": scenario["target_host"],
        },
        "context_topology": {"family": parent.family, "target_host": scenario["target_host"]},
        "covering_detection_id": parent.covering_detection_id,
        "relationship": "SAME",
        "detection_response": "COVERED",
    }


def grade_blind(child: CalibrationVariant, snapshot: ReadOnlyKnnSnapshot) -> BlindGrade:
    """Real signature→snapshot.knn→candidate_set→grade path, without parent id."""
    before = snapshot.stats().get("row_count")
    signature = signatures.build_signature(child.episode_view, child.telemetry_view)
    semantic_candidates = snapshot.knn(signature.canonical_fingerprint, k=8)
    candidates = cousin_engine.candidate_set(
        signature,
        semantic_candidates=semantic_candidates,
        health={"snapshot": "read-only"},
    )
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
    return BlindGrade(
        variant=child,
        relationship=assessment.relationship,
        response=assessment.defense_response,
        distance=assessment.composite,
        decomposition=asdict(assessment.decomposition),
        confidence=assessment.confidence,
        reference_signature_id=assessment.reference_signature_id,
    )


def _curve_row(result: BlindGrade) -> dict[str, Any]:
    discriminator = technique_discriminators(result.variant.covering_detection_id)
    oracle, matched = evidence_presence(
        result.variant.model_visible_telemetry, discriminator["tokens"]
    )
    if result.variant.discriminator_evasion and oracle == ABSENT:
        oracle_response = "NEAR_MISS"
    elif oracle == INDETERMINATE:
        oracle_response = "INDETERMINATE"
    else:
        oracle_response = "COVERED"
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
        "discriminator_evasion": result.variant.discriminator_evasion,
        "negative_control": result.variant.negative_control,
        "confidence": round(result.confidence, 6),
        "reference_signature_id": result.reference_signature_id,
        **{f"distance_{key}": value for key, value in result.decomposition.items()},
    }


def _proposal(rows: list[dict[str, Any]]) -> dict[str, Any]:
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
    results: tuple[BlindGrade, ...], *, monotonic_tolerance: float = 0.05
) -> CalibrationReport:
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
        calibration_proposal=None if passed else _proposal(rows),
    )


def write_artifacts(report: CalibrationReport, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "calibration_report.json"
    csv_path = output_dir / "calibration_curve.csv"
    plot_path = output_dir / "calibration_curve.svg"
    report_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
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
    report = score(results)
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


def corpus_parent_reference_record(entry: dict[str, Any]) -> dict[str, Any]:
    """Project a parent evidence view into Organ without consulting scorer truth."""
    view = entry["engine_view"]["telemetry_view"]
    return {
        "record_id": entry["specimen_id"],
        "signature_id": entry["specimen_id"],
        "kind": "specimen_parent",
        "action_sequence": list(view.get("action_sequence") or []),
        "behavior_sequence": " ".join(view.get("action_sequence") or []),
        "telemetry_shape": dict(view.get("telemetry_shape") or {}),
        "context_topology": dict(view.get("context_topology") or {}),
        "attack_mappings": list(view.get("attack_mappings") or []),
        "relationship": "SAME",
        "detection_response": "INDETERMINATE",
        "trust_tier": entry["engine_view"].get("trust_tier"),
    }


def grade_corpus_blind(
    specimen: dict[str, Any], snapshot: ReadOnlyKnnSnapshot
) -> BlindCorpusVerdict:
    """Produce an engine verdict from the evidence view, before any truth join."""
    before = snapshot.stats().get("row_count")
    engine_view = specimen["engine_view"]
    signature = signatures.build_signature(
        engine_view["episode_view"], engine_view["telemetry_view"]
    )
    candidates = cousin_engine.candidate_set(
        signature,
        semantic_candidates=snapshot.knn(signature.canonical_fingerprint, k=8),
        health={"snapshot": "read-only"},
    )
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
    if snapshot.stats().get("row_count") != before:
        raise RuntimeError("read-only baseline snapshot changed while grading")
    return BlindCorpusVerdict(
        specimen_id=specimen["specimen_id"],
        source_lane=specimen["source_lane"],
        relationship=assessment.relationship,
        response=assessment.defense_response,
        distance=assessment.composite,
        decomposition=asdict(assessment.decomposition),
        confidence=assessment.confidence,
        reference_signature_id=assessment.reference_signature_id,
    )


def _visible_telemetry(corpus_dir: Path, specimen: dict[str, Any]) -> str:
    payload = json.loads((corpus_dir / "evidence" / specimen["evidence_ref"]).read_text())
    return "\n".join(
        _canonical(event)
        for sourcetype in sorted(payload.get("telemetry") or {})
        for event in payload["telemetry"][sourcetype]
    )


def _oracle_response(telemetry: str, techniques: list[str]) -> tuple[str, dict[str, Any]]:
    observations: dict[str, Any] = {}
    for technique_id in techniques:
        discriminator = technique_discriminators(technique_id)
        result, matched = evidence_presence(telemetry, discriminator["tokens"])
        observations[technique_id] = {"result": result, "matched": matched}
    results = {value["result"] for value in observations.values()}
    if not observations or INDETERMINATE in results:
        return "INDETERMINATE", observations
    if ABSENT in results:
        return "NEAR_MISS", observations
    return "COVERED", observations


def _baseline_row(
    verdict: BlindCorpusVerdict,
    *,
    specimen: dict[str, Any],
    truth: dict[str, Any],
    corpus_dir: Path,
) -> dict[str, Any]:
    response, detail = _oracle_response(
        _visible_telemetry(corpus_dir, specimen), truth["data_yml_techniques"]
    )
    source_classes = (
        specimen["engine_view"]["telemetry_view"]
        .get("context_topology", {})
        .get("source_classes", [])
    )
    expected_relationship = _expected_relationship(float(truth["construction_distance"]))
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
        "scenario_family": source_classes[0] if len(source_classes) == 1 else "mixed_or_unknown",
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


def _characterize_baseline(
    rows: list[dict[str, Any]],
    failures: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    band_hits = [
        row for row in rows if row["relationship"] == _expected_relationship(row["d_applied"])
    ]
    blind_spots = [
        row
        for row in rows
        if 0.05 < row["d_applied"] <= 0.40
        and row["relationship"] in {"NEW", "DIFFERENT", "ANOMALOUS_UNCLASSIFIED"}
    ]
    overclaims = [row for row in rows if row["d_applied"] > 0.05 and row["relationship"] == "SAME"]
    parent_rows = [row for row in rows if row["parent_id"]]
    wrong_parent = failures["wrong_parent"]
    comparable_pairs = 0
    by_parent: dict[str, list[dict[str, Any]]] = {}
    for row in parent_rows:
        by_parent.setdefault(row["parent_id"], []).append(row)
    for grouped in by_parent.values():
        comparable_pairs += max(0, len(grouped) - 1)

    per_lane = _lane_metrics(rows)
    replay = per_lane["replay_mutation"]
    lab = per_lane["live_lab"]
    return {
        "published_thresholds": dict(cousin_engine.DEFAULT_THRESHOLDS),
        "band_crossing": {
            "correct": len(band_hits),
            "rows": len(rows),
            "accuracy": _rate(len(band_hits), len(rows)),
        },
        "monotonicity": {
            "comparable_pairs": comparable_pairs,
            "violations": len(failures["non_monotonic"]),
            "accuracy": _rate(comparable_pairs - len(failures["non_monotonic"]), comparable_pairs),
        },
        "blind_spots": {
            "count": len(blind_spots),
            "rate": _rate(len(blind_spots), len(rows)),
        },
        "overclaims": {
            "count": len(overclaims),
            "rate": _rate(len(overclaims), len(rows)),
        },
        "wrong_parent": {
            "count": len(wrong_parent),
            "eligible_rows": len(parent_rows),
            "rate": _rate(len(wrong_parent), len(parent_rows)),
        },
        "response_axis": {
            "distribution": dict(sorted(Counter(row["grader_response"] for row in rows).items())),
            "oracle_distribution": dict(
                sorted(Counter(row["oracle_response"] for row in rows).items())
            ),
        },
        "per_lane": per_lane,
        "lane_comparison": {
            "replay_mutation_vs_live_lab": {
                "band_accuracy_delta": (
                    round(replay["band_crossing_accuracy"] - lab["band_crossing_accuracy"], 6)
                    if replay["band_crossing_accuracy"] is not None
                    and lab["band_crossing_accuracy"] is not None
                    else None
                ),
                "mean_graded_distance_delta": (
                    round(replay["mean_graded_distance"] - lab["mean_graded_distance"], 6)
                    if replay["mean_graded_distance"] is not None
                    and lab["mean_graded_distance"] is not None
                    else None
                ),
            }
        },
    }


def score_baseline(
    verdicts: tuple[BlindCorpusVerdict, ...],
    *,
    corpus: dict[str, Any],
    corpus_dir: Path,
    ledger: SpecimenLedger,
    monotonic_tolerance: float = 0.05,
) -> BaselineCalibrationReport:
    """Join sealed truth only after every blind verdict, then score the cold reading."""
    specimens = {item["specimen_id"]: item for item in corpus["specimens"]}
    rows: list[dict[str, Any]] = []
    failures: dict[str, list[dict[str, Any]]] = {
        "mid_distance_new_blind_spot": [],
        "real_same_overclaim": [],
        "non_monotonic": [],
        "wrong_parent": [],
        "response_axis": [],
    }
    unresolved: list[dict[str, Any]] = []
    indeterminate: list[dict[str, Any]] = []
    by_parent: dict[str, list[dict[str, Any]]] = {}
    for verdict in verdicts:
        truth = ledger.truth_for(verdict.specimen_id)
        if truth is None:
            raise ValueError(f"sealed truth missing for {verdict.specimen_id}")
        row = _baseline_row(
            verdict,
            specimen=specimens[verdict.specimen_id],
            truth=truth,
            corpus_dir=corpus_dir,
        )
        rows.append(row)
        _classify_baseline_row(row, failures, unresolved, indeterminate)
        if row["parent_id"]:
            by_parent.setdefault(row["parent_id"], []).append(row)

    failures["non_monotonic"] = _find_non_monotonic(by_parent, monotonic_tolerance)
    passed = not any(failures.values()) and not unresolved and not indeterminate
    is_v2 = corpus["schema"] == "SPECIMEN_CORPUS_V2"
    characterization = _characterize_baseline(rows, failures) if is_v2 else {}
    reference_guard = (
        {
            "immutable": True,
            "designation": "source_agnostic_redesign_reference",
            "acceptance": "match_or_beat",
            "scope": [
                "windows:security",
                "linux:auditd",
                "web:access",
                "docker:daemon",
            ],
        }
        if is_v2
        else {}
    )
    report = BaselineCalibrationReport(
        schema=BASELINE_CALIBRATION_V2 if is_v2 else BASELINE_CALIBRATION_V1,
        passed=passed,
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
        reference_guard=reference_guard,
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
    version = "v2" if report.schema == BASELINE_CALIBRATION_V2 else "v1"
    report_path = output_dir / f"baseline_calibration_{version}.json"
    compatibility_path = output_dir / "calibration_report.json"
    curve_path = output_dir / "baseline_calibration_curve.csv"
    payload = json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    report_path.write_text(payload, encoding="utf-8")
    compatibility_path.write_text(payload, encoding="utf-8")
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
    verdicts = tuple(grade_corpus_blind(specimen, snapshot) for specimen in corpus["specimens"])
    if snapshot.stats().get("row_count") != before:
        raise RuntimeError("baseline specimens contaminated the Organ snapshot")
    report = score_baseline(
        verdicts,
        corpus=corpus,
        corpus_dir=corpus_path.parent,
        ledger=ledger,
    )
    write_baseline_artifacts(report, output_dir)
    return report
