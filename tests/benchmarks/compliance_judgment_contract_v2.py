"""Strict final-answer and citation scoring for compliance judgment probes.

V1 is retained unchanged for historical reproducibility. V2 consumes the
model's final content only: it never searches a thought trace or surrounding
prose for a JSON object, maps the product's ``INSUFFICIENT`` label to the
benchmark's ``ABSTAIN`` class, and separates literal false support from
conservative scoring penalties for missing/invalid outputs.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

VIOLATION_LABELS = {"PARTIAL", "CONTRADICTED", "ABSENT"}
LABELS = {"SUPPORTED", "PARTIAL", "CONTRADICTED", "ABSENT", "ABSTAIN", "INSUFFICIENT"}
FINDING_TYPES = {"GAP", "CONTRADICTION", "OUTDATED_LANGUAGE", "WEAK_MAPPING"}

_CIP_REF = re.compile(
    r"\bCIP-\d{3}-\d+(?:\.[A-Za-z0-9.]+)?"
    r"(?:\s+R\d+(?:\.\d+)?(?:\s+Part\s+\d+(?:\.\d+)?)?)?",
    re.IGNORECASE,
)


def parse_final_json(text: str) -> dict[str, Any] | None:
    """Parse exactly one JSON object; reject prose, fences, and extracted snippets."""
    try:
        value = json.loads(text.strip())
    except (json.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def packet_ref_ids(case: dict[str, Any]) -> list[str]:
    """List exact CIP references present in the model-visible packet fields."""
    fields = [case.get("governing_ref", ""), case.get("governing_text", "")]
    fields.extend(case.get("premises", []))
    fields.append(case.get("candidate_text", "") or "")
    refs: set[str] = set()
    for value in fields:
        refs.update(re.sub(r"\s+", " ", match).strip() for match in _CIP_REF.findall(str(value)))
    for ref in case.get("source_ref_ids", []):
        if isinstance(ref, str) and ref.strip():
            refs.add(re.sub(r"\s+", " ", ref).strip())
    return sorted(refs, key=str.casefold)


def packet_v2(case: dict[str, Any]) -> dict[str, Any]:
    """Versioned packet with explicit citation IDs, derived only from visible data."""
    return {
        "governing_unit": {"ref": case["governing_ref"], "text": case["governing_text"]},
        "premises": case.get("premises", []),
        "candidate_implementation": case.get("candidate_text"),
        "packet_complete": bool(case.get("packet_complete")),
        "source_refs": packet_ref_ids(case),
    }


def parse_contract_object(raw: str) -> tuple[dict[str, Any] | None, bool, str]:
    """Validate the declared final JSON contract and return a normalized error."""
    obj = parse_final_json(raw)
    if obj is None:
        return None, False, "not_one_json_object"
    allowed_keys = {"determination", "finding_type", "cited_refs", "rationale", "confidence"}
    required_keys = {"determination", "finding_type", "cited_refs", "rationale"}
    if not required_keys.issubset(obj) or not set(obj).issubset(allowed_keys):
        return obj, False, "object_keys_do_not_match_contract"
    determination_value = obj.get("determination")
    if not isinstance(determination_value, str):
        return obj, False, "invalid_determination"
    determination = determination_value.upper()
    if determination not in LABELS:
        return obj, False, "invalid_determination"
    finding_type = obj.get("finding_type")
    if finding_type is not None and (
        not isinstance(finding_type, str) or finding_type.upper() not in FINDING_TYPES
    ):
        return obj, False, "invalid_finding_type"
    cited_refs = obj.get("cited_refs")
    if not isinstance(cited_refs, list) or any(
        not isinstance(ref, str) or not ref.strip() for ref in cited_refs
    ):
        return obj, False, "cited_refs_not_a_string_array"
    rationale = obj.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        return obj, False, "missing_rationale"
    if "confidence" in obj:
        confidence = obj["confidence"]
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            return obj, False, "invalid_confidence"
        if not math.isfinite(float(confidence)) or not 0.0 <= float(confidence) <= 1.0:
            return obj, False, "invalid_confidence"
    return obj, True, ""


def _label_class(label: str) -> str:
    normalized = "ABSTAIN" if label == "INSUFFICIENT" else label
    if normalized == "ABSTAIN":
        return "ABSTAIN"
    return "UNMET" if normalized in VIOLATION_LABELS else "SATISFIED"


def score_case_v2(case: dict[str, Any], raw: str) -> dict[str, Any]:
    obj, schema_ok, schema_error = parse_contract_object(raw)
    gold = str(case["gold_label"]).upper()
    if gold == "INSUFFICIENT":
        gold = "ABSTAIN"
    raw_obj = parse_final_json(raw)
    raw_determination = str(raw_obj.get("determination", "")).upper() if raw_obj is not None else ""
    literal_false_supported = gold in VIOLATION_LABELS and raw_determination == "SUPPORTED"
    if not schema_ok or obj is None:
        return {
            "schema_ok": False,
            "schema_error": schema_error,
            "pred": None,
            "correct": False,
            "literal_false_supported": literal_false_supported,
            "conservative_unresolved_penalty": gold in VIOLATION_LABELS
            and not literal_false_supported,
            "missed_abstain": gold == "ABSTAIN",
            "spurious_abstain": False,
            "citation_ok": False,
            "off_packet_citations": [],
        }

    pred = str(obj["determination"]).upper()
    if pred == "INSUFFICIENT":
        pred = "ABSTAIN"
    cited = {re.sub(r"\s+", " ", ref).strip().casefold() for ref in obj["cited_refs"]}
    gold_cites = {
        re.sub(r"\s+", " ", str(ref)).strip().casefold() for ref in case.get("gold_citation", [])
    }
    packet_cites = {ref.casefold() for ref in packet_ref_ids(case)}
    off_packet = sorted(cited - packet_cites)
    citation_ok = bool(cited) and gold_cites.issubset(cited) and not off_packet
    return {
        "schema_ok": True,
        "schema_error": "",
        "pred": pred,
        "correct": pred == gold,
        "literal_false_supported": literal_false_supported,
        "conservative_unresolved_penalty": False,
        "missed_abstain": gold == "ABSTAIN" and pred != "ABSTAIN",
        "spurious_abstain": gold != "ABSTAIN" and pred == "ABSTAIN",
        "citation_ok": citation_ok,
        "off_packet_citations": off_packet,
    }


def aggregate_v2(cases: list[dict[str, Any]], rows: list[dict[str, Any]]) -> dict[str, Any]:
    if len(cases) != len(rows):
        raise ValueError("case/score row count mismatch")
    tp = fp = fn = tn = 0
    for case, row in zip(cases, rows, strict=True):
        gold = str(case["gold_label"]).upper()
        if gold == "INSUFFICIENT":
            gold = "ABSTAIN"
        gold_pos = gold in VIOLATION_LABELS
        pred = row.get("pred") if row.get("schema_ok") else None
        pred_pos = pred in VIOLATION_LABELS
        if gold_pos and pred_pos:
            tp += 1
        elif gold_pos:
            fn += 1
        elif pred_pos:
            fp += 1
        else:
            tn += 1
    beta2 = 4.0
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f2 = (
        (1 + beta2) * precision * recall / (beta2 * precision + recall)
        if precision + recall
        else 0.0
    )
    abstain_rows = [
        row
        for case, row in zip(cases, rows, strict=True)
        if str(case["gold_label"]).upper() in {"ABSTAIN", "INSUFFICIENT"}
    ]
    return {
        "n": len(cases),
        "violation_class_accuracy": round(
            sum(
                1
                for case, row in zip(cases, rows, strict=True)
                if row.get("schema_ok")
                and _label_class(str(case["gold_label"]).upper()) == _label_class(row["pred"])
            )
            / len(cases),
            4,
        )
        if cases
        else 0.0,
        "exact_accuracy": round(sum(bool(row.get("correct")) for row in rows) / len(cases), 4)
        if cases
        else 0.0,
        "F2_violation": round(f2, 4),
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "literal_false_supported_count": sum(
            bool(row.get("literal_false_supported")) for row in rows
        ),
        "conservative_unresolved_penalty_count": sum(
            bool(row.get("conservative_unresolved_penalty")) for row in rows
        ),
        "schema_valid_rate": round(sum(bool(row.get("schema_ok")) for row in rows) / len(cases), 4)
        if cases
        else 0.0,
        "citation_ok_rate": round(sum(bool(row.get("citation_ok")) for row in rows) / len(cases), 4)
        if cases
        else 0.0,
        "abstain_recall": round(
            sum(row.get("pred") == "ABSTAIN" and row.get("schema_ok") for row in abstain_rows)
            / len(abstain_rows),
            4,
        )
        if abstain_rows
        else None,
    }
