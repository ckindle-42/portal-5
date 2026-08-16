"""Standing ONBOARD -> CHARACTERIZE -> ADMIT acceptance instruments (SA1)."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ..siem.spl_detections import spl_for_source
from . import cousin_engine, signatures, source_adapters
from .cousin_calibration_bench import (
    BaselineCalibrationReport,
    corpus_parent_reference_record,
)
from .handoff import check_quiet_on_benign, gather_quiet_on_benign, validate_spl_syntax

SA1_CLASS_ONBOARDING_V1 = "SA1_CLASS_ONBOARDING_V1"
SA1_CROSS_CLASS_V1 = "SA1_CROSS_CLASS_V1"
V3_SCOPE = frozenset({"windows:security", "linux:auditd", "web:access", "docker:daemon"})


def run_detection_qa(
    corpus: dict[str, Any],
    *,
    source_techniques: dict[str, str],
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Prove each class detection on live positives and the benign corpus."""
    classes: dict[str, Any] = {}
    for source_class, technique_id in source_techniques.items():
        spl = spl_for_source(technique_id, source_class) or ""
        syntax_ok, syntax_errors = validate_spl_syntax(spl)
        quiet = check_quiet_on_benign(gather_quiet_on_benign(spl))
        rows = [
            specimen
            for specimen in corpus["specimens"]
            if specimen.get("source_class") == source_class
        ]
        parents = [item for item in rows if item["source_lane"] == "attack_data"]

        def outcomes(specimens: list[dict[str, Any]]) -> Counter[str]:
            return Counter(
                value
                for specimen in specimens
                for value in specimen["engine_view"]["telemetry_view"]["detector_outcomes"].values()
            )

        parent_outcomes = outcomes(parents)
        class_outcomes = outcomes(rows)
        classes[source_class] = {
            "technique_id": technique_id,
            "syntax_ok": syntax_ok,
            "syntax_errors": syntax_errors,
            "known_positive_live_fires": parent_outcomes["fired"],
            "parent_detector_outcomes": dict(sorted(parent_outcomes.items())),
            "class_detector_outcomes": dict(sorted(class_outcomes.items())),
            "quiet_on_benign": quiet,
            "passed": syntax_ok and parent_outcomes["fired"] > 0 and quiet["outcome"] == "pass",
        }
    report = {
        "schema": "SA1_DETECTION_QA_V1",
        "passed": bool(classes) and all(item["passed"] for item in classes.values()),
        "classes": classes,
        "live_indexed_evidence": True,
    }
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return report


def _metric(report: BaselineCalibrationReport, *path: str) -> float | None:
    value: Any = report.characterization
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return float(value) if isinstance(value, int | float) else None


def class_verdict(
    source_class: str,
    report: BaselineCalibrationReport,
    *,
    v3_profile: dict[str, float],
) -> dict[str, Any]:
    """Issue the explicit ADMIT/FLAG/REJECT decision for one class."""
    if report.status != "VALID" or not report.controls.get("passed"):
        return {
            "source_class": source_class,
            "verdict": "REJECT",
            "reason": "measurement_controls_failed",
            "diagnosis": list(report.diagnosis),
        }
    observed = {
        "band_accuracy": _metric(report, "band_crossing", "accuracy"),
        "monotonic_accuracy": _metric(report, "monotonicity", "accuracy"),
        "correct_family_accuracy": _metric(report, "family_parent", "accuracy"),
        "real_same_overclaim_rate": _metric(report, "overclaims", "rate"),
        "response_independent_rows": report.oracle_independence_contract.get(
            "rows_with_independent_signal", 0
        ),
    }
    weaknesses = []
    for name in ("band_accuracy", "monotonic_accuracy", "correct_family_accuracy"):
        if observed[name] is None or observed[name] < v3_profile[name]:
            weaknesses.append(f"{name}_below_v3_shape")
    if (
        observed["real_same_overclaim_rate"] is None
        or observed["real_same_overclaim_rate"] > v3_profile["real_same_overclaim_rate"]
    ):
        weaknesses.append("real_same_overclaim_above_v3")
    if not observed["response_independent_rows"]:
        weaknesses.append("response_axis_indeterminate")
    return {
        "source_class": source_class,
        "verdict": "FLAG" if weaknesses else "ADMIT",
        "reason": ",".join(weaknesses) if weaknesses else "controls_and_profile_shape_passed",
        "weaknesses": weaknesses,
        "observed": observed,
    }


def v3_profile_from_artifact(path: Path) -> dict[str, float]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    characterization = payload["characterization"]
    return {
        "band_accuracy": float(characterization["band_crossing"]["accuracy"]),
        "monotonic_accuracy": float(characterization["monotonicity"]["accuracy"]),
        "correct_family_accuracy": float(characterization["family_parent"]["accuracy"]),
        "real_same_overclaim_rate": float(characterization["overclaims"]["rate"]),
    }


def compare_v3_regression(report: BaselineCalibrationReport, baseline_path: Path) -> dict[str, Any]:
    """Apply the four-class match-or-beat contract without cohort dilution."""
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    expected = baseline["characterization"]

    def observed(path: tuple[str, ...], default: float) -> float:
        value = _metric(report, *path)
        return default if value is None else value

    checks = {
        "controls": report.status == "VALID" and bool(report.controls.get("passed")),
        "band_accuracy": observed(("band_crossing", "accuracy"), 0.0)
        >= float(expected["band_crossing"]["accuracy"]),
        "monotonic_accuracy": observed(("monotonicity", "accuracy"), 0.0)
        >= float(expected["monotonicity"]["accuracy"]),
        "correct_family_accuracy": observed(("family_parent", "accuracy"), 0.0)
        >= float(expected["family_parent"]["accuracy"]),
        "exact_wrong_parent_rate": observed(("wrong_parent", "rate"), 1.0)
        <= float(expected["wrong_parent"]["rate"]),
        "real_same_overclaim_rate": observed(("overclaims", "rate"), 1.0)
        <= float(expected["overclaims"]["rate"]),
    }
    return {
        "scope": sorted(V3_SCOPE),
        "baseline_schema": baseline["schema"],
        "checks": checks,
        "passed": all(checks.values()),
        "exact_parent_and_family_reported_separately": True,
    }


def _source(record: dict[str, Any]) -> str:
    value = record.get("source_class")
    if value:
        return str(value)
    shape = record.get("telemetry_shape") or {}
    value = shape.get("source_class")
    if value:
        return str(value)
    sources = shape.get("sourcetypes") or ()
    return str(sources[0]) if len(sources) == 1 else ""


def _ids(results: list[tuple[dict[str, Any], float]]) -> list[str]:
    return [str(record.get("record_id") or record.get("signature_id")) for record, _ in results]


def run_cross_class_acceptance(  # noqa: PLR0915 - explicit X1-X5 evidence sequence
    snapshot: Any,
    *,
    corpus: dict[str, Any],
    output_path: Path | None = None,
    k: int = 32,
) -> dict[str, Any]:
    """Exercise X1-X5 against the mixed read-only parent snapshot."""
    parents = [item for item in corpus["specimens"] if item["source_lane"] == "attack_data"]
    records = [corpus_parent_reference_record(item) for item in parents]
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_family[str(record.get("family") or "")].append(record)
    spanning = {
        family: members
        for family, members in by_family.items()
        if family and len({_source(member) for member in members}) >= 2
    }

    cross_evidence = []
    for family, members in sorted(spanning.items()):
        query_member = members[0]
        query_source = _source(query_member)
        unfiltered = snapshot.knn(str(query_member["semantic_query"]), k=k)
        filtered = snapshot.knn(f"scenario family: {family}", k=k, filters={"family": family})
        cross_evidence.append(
            {
                "family": family,
                "query_source": query_source,
                "unfiltered_cross_class_ids": _ids(
                    [
                        (row, distance)
                        for row, distance in unfiltered
                        if _source(row) != query_source
                    ]
                ),
                "family_member_sources": sorted({_source(row) for row, _ in filtered}),
                "family_member_ids": _ids(filtered),
            }
        )
    x1 = {
        "passed": bool(cross_evidence)
        and any(item["unfiltered_cross_class_ids"] for item in cross_evidence),
        "evidence": cross_evidence,
    }
    x2 = {
        "passed": bool(cross_evidence)
        and all(len(item["family_member_sources"]) >= 2 for item in cross_evidence),
        "evidence": cross_evidence,
    }

    full_parent = parents[0]
    full_signature = signatures.build_signature(
        full_parent["engine_view"]["episode_view"],
        full_parent["engine_view"]["telemetry_view"],
    )
    sparse_view = source_adapters.adapt(
        ["advisory IOC"],
        {
            "sourcetype": "threat-intel:advisory",
            "techniques": list(signatures.attack_ids(full_signature)),
            "origin": "vendor_advisory",
            "trust_tier": "external_asserted",
        },
    )
    sparse_signature = signatures.build_signature({"episode_id": "x3-advisory"}, sparse_view)
    reference = corpus_parent_reference_record(full_parent)
    full_assessment = cousin_engine.grade(
        full_signature,
        cousin_engine.candidate_set(full_signature, semantic_candidates=[(reference, 0.0)]),
        cousin_engine.CoverageView(telemetry_healthy=True),
    )
    sparse_assessment = cousin_engine.grade(
        sparse_signature,
        cousin_engine.candidate_set(sparse_signature, semantic_candidates=[(reference, 0.2)]),
        cousin_engine.CoverageView(telemetry_healthy=True),
    )
    sparse_reference = {
        **signatures.reference_record_fields(sparse_signature),
        "record_id": "x3-advisory",
        "signature_id": "x3-advisory",
    }
    reverse_assessment = cousin_engine.grade(
        full_signature,
        cousin_engine.candidate_set(full_signature, semantic_candidates=[(sparse_reference, 0.2)]),
        cousin_engine.CoverageView(telemetry_healthy=True),
    )
    x3 = {
        "passed": sparse_signature.completeness < full_signature.completeness
        and sparse_assessment.confidence < full_assessment.confidence
        and reverse_assessment.confidence < full_assessment.confidence
        and "action_sequence" not in sparse_view,
        "full_completeness": full_signature.completeness,
        "sparse_completeness": sparse_signature.completeness,
        "full_confidence": full_assessment.confidence,
        "sparse_confidence": sparse_assessment.confidence,
        "reverse_sparse_reference_confidence": reverse_assessment.confidence,
        "sparse_relationship": sparse_assessment.relationship,
        "missing_dimensions_padded": False,
    }

    identity_evidence = []
    for source_class in sorted({_source(record) for record in records if _source(record)}):
        record = next(row for row in records if _source(row) == source_class)
        parent = next(item for item in parents if item["specimen_id"] == record["record_id"])
        signature = signatures.build_signature(
            parent["engine_view"]["episode_view"], parent["engine_view"]["telemetry_view"]
        )
        direct = cousin_engine.grade(
            signature,
            cousin_engine.candidate_set(signature, semantic_candidates=[(record, 0.0)]),
            cousin_engine.CoverageView(telemetry_healthy=True),
        )
        mixed = cousin_engine.retrieve_candidate_axes(signature, snapshot, k=k)
        identity_evidence.append(
            {
                "source_class": source_class,
                "direct_relationship": direct.relationship,
                "direct_distance": direct.composite,
                "present_in_mixed_candidates": record["record_id"]
                in {str(item["record"].get("record_id")) for item in mixed.candidates},
            }
        )
    x4 = {
        "passed": bool(identity_evidence)
        and all(
            item["direct_relationship"] == "SAME" and item["present_in_mixed_candidates"]
            for item in identity_evidence
        ),
        "evidence": identity_evidence,
    }

    negative = None
    for left in records:
        for right in records:
            if _source(left) != _source(right) and left.get("family") != right.get("family"):
                negative = (left, right)
                break
        if negative:
            break
    negative_evidence: dict[str, Any] = {}
    if negative:
        left, right = negative
        right_parent = next(item for item in parents if item["specimen_id"] == right["record_id"])
        subject = signatures.build_signature(
            right_parent["engine_view"]["episode_view"],
            right_parent["engine_view"]["telemetry_view"],
        )
        assessment = cousin_engine.grade(
            subject,
            cousin_engine.candidate_set(subject, semantic_candidates=[(left, 0.0)]),
            cousin_engine.CoverageView(telemetry_healthy=True),
        )
        negative_evidence = {
            "left_source": _source(left),
            "right_source": _source(right),
            "left_family": left.get("family"),
            "right_family": right.get("family"),
            "relationship": assessment.relationship,
            "distance": assessment.composite,
        }
    x5 = {
        "passed": bool(negative_evidence) and negative_evidence["relationship"] != "SAME",
        "evidence": negative_evidence,
    }
    checks = {"X1": x1, "X2": x2, "X3": x3, "X4": x4, "X5": x5}
    report = {
        "schema": SA1_CROSS_CLASS_V1,
        "passed": all(item["passed"] for item in checks.values()),
        "checks": checks,
        "parent_classes": sorted({_source(record) for record in records if _source(record)}),
        "parent_count": len(parents),
        "cold_untuned": True,
        "training_applied": False,
        "threshold_tuning_applied": False,
        "truth_wall_intact": True,
    }
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return report


def write_loop_record(
    output_path: Path,
    *,
    verdicts: list[dict[str, Any]],
    regression: dict[str, Any],
    cross_class: dict[str, Any],
    corpus: dict[str, Any],
    detection_qa: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = {
        "schema": SA1_CLASS_ONBOARDING_V1,
        "verdicts": verdicts,
        "regression": regression,
        "cross_class": cross_class,
        "detection_qa": detection_qa or {},
        "coverage": {
            "catalog_datasets": corpus["coverage_report"]["catalog_datasets"],
            "admitted_parents": corpus["coverage_report"]["admitted_parents"],
            "admission_census": corpus["admission_census"],
            "per_class_counts": corpus.get("per_class_counts", {}),
            "response_observation_counts": corpus.get("response_observation_counts", {}),
        },
        "cold_untuned": True,
        "training_applied": False,
        "threshold_tuning_applied": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record
