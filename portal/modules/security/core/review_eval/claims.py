"""Derive the four review-program claims from validated, aggregate-only proof rows.

This module is scorer-plane code. Inputs are rows whose source reports already passed their
stamp, self-test, and report checks; it refuses proxy corpora and rows containing event text.
The output keeps sample sizes and uncertainty visible so a small or incomplete sample cannot
turn into a positive claim by omission.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from .metrics import bootstrap_ci

CLAIM_STATUSES = ("PROVEN", "PARTIAL", "UNPROVEN")
_FORBIDDEN_ROW_KEYS = {"_raw", "raw", "raw_text", "event_text", "telemetry", "transcript"}
_CLASSES = ("known", "cousin", "novel", "evidence_twin", "benign")


class ClaimEvidenceError(ValueError):  # noqa: N818 -- public validation contract
    """Proof rows do not meet the aggregate-only, real-corpus input contract."""


def _rows_for(rows: Sequence[Mapping[str, Any]], claim: str) -> list[Mapping[str, Any]]:
    return [row for row in rows if row.get("claim") == claim]


def _required_bool(row: Mapping[str, Any], name: str) -> bool:
    value = row.get(name)
    if not isinstance(value, bool):
        raise ClaimEvidenceError(f"{name} must be a boolean on {row.get('row_id', '<row>')}")
    return value


def _interval(values: Sequence[bool], *, seed: int) -> dict[str, Any]:
    n = len(values)
    if not n:
        return {"n": 0, "estimate": None, "ci95": None}
    estimate = sum(values) / n
    if n < 2:
        return {"n": n, "estimate": estimate, "ci95": None}
    low, high = bootstrap_ci([float(value) for value in values], seed=seed)
    return {"n": n, "estimate": estimate, "ci95": [low, high]}


def _status_vs_control(candidate: Mapping[str, Any], control: Mapping[str, Any]) -> str:
    candidate_ci = candidate.get("ci95")
    control_ci = control.get("ci95")
    if not candidate_ci or not control_ci:
        return "UNPROVEN"
    lower = float(candidate_ci[0])
    control_upper = float(control_ci[1])
    estimate = float(candidate["estimate"])
    control_estimate = float(control["estimate"])
    if lower > control_upper:
        return "PROVEN"
    if estimate > control_estimate:
        return "PARTIAL"
    return "UNPROVEN"


def _not_below_control(
    rows: Sequence[Mapping[str, Any]], *, klasses: Sequence[str], seed: int
) -> tuple[str, dict[str, Any]]:
    selected = [row for row in rows if row.get("class") in klasses]
    workload_b = {row.get("workload_B") for row in selected}
    if len(workload_b) > 1:
        raise ClaimEvidenceError("candidate and control rows must use the same workload B")
    candidate = _interval([_required_bool(row, "review_hit") for row in selected], seed=seed)
    control = _interval([_required_bool(row, "control_hit") for row in selected], seed=seed + 1)
    return _status_vs_control(candidate, control), {
        "workload_B": next(iter(workload_b), None),
        "review": candidate,
        "control": control,
    }


def _c1(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    sources = _rows_for(rows, "C1")
    if len({row.get("source") for row in sources}) != len(sources):
        raise ClaimEvidenceError("C1 needs exactly one row per stratified source")
    review_hits = [
        _required_bool(row, "review_valid_extraction") and _required_bool(row, "review_has_unit")
        for row in sources
    ]
    control_hits = [
        _required_bool(row, "control_valid_extraction") and _required_bool(row, "control_has_unit")
        for row in sources
    ]
    review = _interval(review_hits, seed=6101)
    control = _interval(control_hits, seed=6102)
    status = _status_vs_control(review, control)
    return {
        "claim": "C1",
        "name": "any source",
        "status": status,
        "sampled_sources": len(sources),
        "review_fraction": review,
        "legacy_funnel_fraction": control,
        "blind_sources": sorted(
            str(row["source"]) for row, hit in zip(sources, review_hits, strict=True) if not hit
        ),
    }


def _false_raise(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    benign = [row for row in rows if row.get("class") == "benign"]
    raised = sum(_required_bool(row, "review_raised") for row in benign)
    denominator = len(benign)
    rate = 1000.0 * raised / denominator if denominator else None
    alpha_values = {row.get("alpha") for row in benign}
    if len(alpha_values) > 1:
        raise ClaimEvidenceError("benign rows must share the preregistered alpha")
    alpha = next(iter(alpha_values), None)
    if alpha is not None and not 0.0 <= float(alpha) <= 1.0:
        raise ClaimEvidenceError("alpha must be between zero and one")
    se = (
        1000.0 * math.sqrt((raised / denominator) * (1.0 - raised / denominator) / denominator)
        if denominator
        else None
    )
    within = (
        bool(denominator)
        and alpha is not None
        and rate is not None
        and se is not None
        and rate <= 1000.0 * float(alpha) + 3.0 * se
    )
    return {
        "raised": raised,
        "benign_units": denominator,
        "per_1000": rate,
        "standard_error_per_1000": se,
        "alpha": alpha,
        "within_alpha_plus_3se": within,
    }


def _grounding(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    applicable = [row for row in rows if row.get("class") in _CLASSES]
    resolved = sum(_required_bool(row, "grounding_resolved") for row in applicable)
    fraction = resolved / len(applicable) if applicable else None
    return {"resolved": resolved, "n": len(applicable), "fraction": fraction}


def _novel_absence(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    novel = [row for row in rows if row.get("class") == "novel"]
    surfaced = [row for row in novel if _required_bool(row, "review_hit")]
    verified = [row for row in surfaced if _required_bool(row, "absence_receipt_verified")]
    return {"novel_items": len(novel), "surfaced": len(surfaced), "verified_absence": len(verified)}


def _c2(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    proof_rows = _rows_for(rows, "C2")
    by_class = {
        klass: _not_below_control(
            proof_rows,
            klasses=(klass,),
            seed=6200 + index,
        )[1]
        for index, klass in enumerate(("known", "cousin", "novel"))
    }
    cousin_status, cousin = _not_below_control(proof_rows, klasses=("cousin",), seed=6202)
    false_raise = _false_raise(proof_rows)
    grounding = _grounding(proof_rows)
    all_gates = (
        cousin_status == "PROVEN"
        and false_raise["within_alpha_plus_3se"] is True
        and grounding["fraction"] == 1.0
    )
    status = "PROVEN" if all_gates else "PARTIAL" if cousin_status == "PARTIAL" else "UNPROVEN"
    return {
        "claim": "C2",
        "name": "same or similar",
        "status": status,
        "by_class": by_class,
        "cousin_comparison": cousin,
        "false_raise": false_raise,
        "novel_absence_receipts": _novel_absence(proof_rows),
        "grounding": grounding,
    }


def _c3(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    windows = _rows_for(rows, "C3_WINDOW")
    stages = _rows_for(rows, "C3_STAGE")
    if len({row.get("window_id") for row in windows}) != len(windows):
        raise ClaimEvidenceError("C3 needs exactly one completeness row per window")
    window_details: list[dict[str, Any]] = []
    for row in windows:
        expected = int(row["expected"])
        fetched = int(row["fetched"])
        if expected < 0 or fetched < 0:
            raise ClaimEvidenceError("C3 event counts must be non-negative")
        window_details.append(
            {
                "window_id": str(row["window_id"]),
                "index": str(row["index"]),
                "sourcetype": str(row["sourcetype"]),
                "expected": expected,
                "fetched": fetched,
                "complete": fetched == expected,
            }
        )
    stage_details: list[dict[str, Any]] = []
    stage_times: list[float] = []
    for row in stages:
        examined = int(row["examined"])
        resolved = int(row["resolved"])
        duration = float(row["duration_seconds"])
        cause = str(row.get("cause") or "")
        if min(examined, resolved) < 0 or duration <= 0:
            raise ClaimEvidenceError("C3 stage counts and duration must be valid")
        unexplained = examined != resolved and not cause.strip()
        throughput = resolved / duration
        stage_times.append(duration)
        stage_details.append(
            {
                "stage": str(row["stage"]),
                "examined": examined,
                "resolved": resolved,
                "duration_seconds": duration,
                "throughput_per_second": throughput,
                "cause": cause,
                "unexplained_difference": unexplained,
            }
        )
    expected_total = sum(row["expected"] for row in window_details)
    fetched_total = sum(row["fetched"] for row in window_details)
    full_corpus_events = sum(
        max(
            int(row.get("corpus_size", row["expected"]))
            for row in windows
            if str(row.get("index")) == index
        )
        for index in {str(row.get("index")) for row in windows}
    )
    bottleneck = (
        min(stage_details, key=lambda row: row["throughput_per_second"]) if stage_details else None
    )
    projected = (
        full_corpus_events / float(bottleneck["throughput_per_second"])
        if bottleneck is not None and bottleneck["throughput_per_second"] > 0
        else None
    )
    passed = (
        bool(windows)
        and all(row["complete"] for row in window_details)
        and not any(row["unexplained_difference"] for row in stage_details)
    )
    return {
        "claim": "C3",
        "name": "the corpus is the ground",
        "status": "PROVEN" if passed else "UNPROVEN",
        "windows": window_details,
        "events_fetched": fetched_total,
        "events_expected": expected_total,
        "full_corpus_events": full_corpus_events,
        "stages": stage_details,
        "bottleneck_stage": bottleneck["stage"] if bottleneck else None,
        "projected_full_corpus_seconds": projected,
    }


def _capture_summary(captures: Mapping[str, Any]) -> dict[str, Any]:
    admitted = int(captures.get("admitted_count", 0))
    total = int(captures.get("total_count", 0))
    rejected = max(0, total - admitted)
    histogram = captures.get("rejection_reason_histogram") or {}
    rule_histogram = captures.get("validator_rule_histogram") or {}
    missing_histogram = captures.get("missing_data_histogram") or {}
    return {
        "admitted": admitted,
        "total": total,
        "rejected": rejected,
        "rejection_reason_histogram": dict(sorted(histogram.items())),
        "validator_rule_histogram": dict(sorted(rule_histogram.items())),
        "missing_data_histogram": dict(sorted(missing_histogram.items())),
    }


def _c4(rows: Sequence[Mapping[str, Any]], captures: Mapping[str, Any]) -> dict[str, Any]:
    proof_rows = _rows_for(rows, "C4")
    allowed_classes = ("cousin", "novel", "evidence_twin")
    for row in proof_rows:
        if row.get("class") == "evidence_twin" and row.get("evidence_twin_source") != "corpus":
            raise ClaimEvidenceError("evidence_twin rows must be corpus-derived")
    by_class: dict[str, Any] = {}
    class_statuses: list[str] = []
    for index, klass in enumerate(allowed_classes):
        status, comparison = _not_below_control(
            proof_rows,
            klasses=(klass,),
            seed=6400 + index,
        )
        by_class[klass] = {"status": status, **comparison}
        if klass in {"cousin", "evidence_twin"}:
            class_statuses.append(status)
    false_raise = _false_raise(proof_rows)
    grounding = _grounding(proof_rows)
    capture = _capture_summary(captures)
    sufficient = all(
        by_class[klass]["review"]["ci95"] is not None
        and by_class[klass]["control"]["ci95"] is not None
        for klass in allowed_classes
    )
    comparison_status = (
        "PROVEN"
        if class_statuses and all(status == "PROVEN" for status in class_statuses)
        else "PARTIAL"
        if class_statuses and any(status == "PARTIAL" for status in class_statuses)
        else "UNPROVEN"
    )
    status = (
        "PROVEN"
        if sufficient
        and comparison_status == "PROVEN"
        and false_raise["within_alpha_plus_3se"] is True
        and grounding["fraction"] == 1.0
        else "PARTIAL"
        if comparison_status == "PARTIAL"
        else "UNPROVEN"
    )
    return {
        "claim": "C4",
        "name": "recorded exercise truth recovered",
        "status": status,
        "sample_sufficient_for_all_classes": sufficient,
        "by_class": by_class,
        "false_raise": false_raise,
        "grounding": grounding,
        "capture_admission": capture,
        "admitted_capture_count": capture["admitted"],
        "rejected_capture_count": capture["rejected"],
        "rejection_reason_histogram": capture["rejection_reason_histogram"],
        "validator_rule_rejections": capture["validator_rule_histogram"],
        "missing_data_rejections": capture["missing_data_histogram"],
        "remaining_validator_rule_defect": bool(capture["validator_rule_histogram"]),
    }


def evaluate_claims(
    rows: Sequence[Mapping[str, Any]],
    *,
    corpus_snapshots: Sequence[str],
    selftests_passed: bool,
    captures: Mapping[str, Any],
    processed_fraction: float,
    stop_rule: str,
) -> dict[str, Any]:
    """Evaluate claims from report rows after their originating reports were validated.

    ``rows`` contain identifiers, classifications, booleans, and stage counts only. Raw event
    text is forbidden. All source corpus stamps must be real, and every originating self-test
    must have passed.
    """
    if not rows:
        raise ClaimEvidenceError("claim evaluation needs validated report rows")
    if not corpus_snapshots or any(not value.startswith("real:") for value in corpus_snapshots):
        raise ClaimEvidenceError("claim inputs must come only from real: corpus stamps")
    if not selftests_passed:
        raise ClaimEvidenceError("every source report must have a passing known-answer self-test")
    if not 0.0 <= processed_fraction <= 1.0:
        raise ClaimEvidenceError("processed_fraction must be between zero and one")
    if not stop_rule.strip():
        raise ClaimEvidenceError("the proof must name the stop rule")
    for row in rows:
        keys = {str(key).lower() for key in row}
        forbidden = keys & _FORBIDDEN_ROW_KEYS
        if forbidden:
            raise ClaimEvidenceError(f"raw telemetry field(s) are forbidden: {sorted(forbidden)}")
    claims = [_c1(rows), _c2(rows), _c3(rows), _c4(rows, captures)]
    return {
        "schema": "review.claims.v1",
        "status": "PROVEN" if all(c["status"] == "PROVEN" for c in claims) else "INCOMPLETE",
        "processed_fraction": processed_fraction,
        "stop_rule": stop_rule,
        "corpus_snapshots": list(corpus_snapshots),
        "claims": claims,
    }


def validate_claims_document(document: Mapping[str, Any]) -> list[str]:
    """Validate persisted claim aggregates before the state renderer accepts them."""
    problems: list[str] = []
    if document.get("schema") != "review.claims.v1":
        problems.append("claims schema is not review.claims.v1")
    claims = document.get("claims")
    if not isinstance(claims, list) or [row.get("claim") for row in claims] != [
        "C1",
        "C2",
        "C3",
        "C4",
    ]:
        problems.append("claim rows must appear exactly once in C1-C4 order")
    elif any(row.get("status") not in CLAIM_STATUSES for row in claims):
        problems.append("claim row has an invalid status")
    if not isinstance(document.get("corpus_snapshots"), list) or not all(
        str(value).startswith("real:") for value in document.get("corpus_snapshots", [])
    ):
        problems.append("claim document must list real: corpus stamps")
    fraction = document.get("processed_fraction")
    if not isinstance(fraction, (int, float)) or not 0.0 <= float(fraction) <= 1.0:
        problems.append("processed_fraction must be between zero and one")
    if not str(document.get("stop_rule") or "").strip():
        problems.append("claim document is missing its stop rule")
    return problems


def rejection_histograms(
    reason_counts: Mapping[str, int], *, rule_reasons: set[str]
) -> tuple[dict[str, int], dict[str, int]]:
    """Separate validator-rule defects from missing-data rejections without dropping reasons."""
    all_reasons = Counter({str(reason): int(count) for reason, count in reason_counts.items()})
    rules = {reason: all_reasons[reason] for reason in sorted(rule_reasons) if all_reasons[reason]}
    missing = {
        reason: count for reason, count in sorted(all_reasons.items()) if reason not in rules
    }
    return rules, missing
