"""Eval-only recall attribution for completed corpus-replay cells.

This module answers a narrower question than the corpus replay scorer:
when a labeled cell did not confirm its expected technique, was that
technique's machine-checkable discriminator present in the telemetry returned
to the model?

The label is used only by :func:`attribute_cell` to select the corresponding
production detection signature.  :func:`evidence_presence`, the actual
presence decision, receives only telemetry and discriminators and performs a
deterministic token search.  Nothing in this module is imported by a
production verdict path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path

from portal.modules.security.core.siem.spl_detections import technique_signature_full

PRESENT = "PRESENT"
ABSENT = "ABSENT"
INDETERMINATE = "INDETERMINATE"

TRUE_POSITIVE = "TRUE_POSITIVE"
MISATTRIBUTION = "MISATTRIBUTION"
EVIDENCE_PRESENT_MISS = "EVIDENCE_PRESENT_MISS"
HONEST_ANOMALY = "HONEST_ANOMALY"
FALSE_NEGATIVE = "FALSE_NEGATIVE"
HONEST_NEGATIVE = "HONEST_NEGATIVE"
UNSCORABLE_BY_ORACLE = "UNSCORABLE_BY_ORACLE"

_FIELD_VALUE_RE = re.compile(
    r"\b(?P<field>[A-Za-z_][A-Za-z0-9_.]*)\s*=\s*"
    r"(?:\"(?P<double>[^\"]+)\"|'(?P<single>[^']+)'|(?P<bare>[^\s|()\]]+))"
)
_SPL_METADATA_FIELDS = frozenset({"index", "sourcetype"})


def _normalize_search_text(value: str) -> str:
    """Normalize harmless representation differences without interpreting."""
    text = str(value or "").lower()
    text = text.replace('"', "").replace("'", "")
    text = re.sub(r"\s*[:=]\s*", "=", text)
    return re.sub(r"\s+", " ", text)


def _search_token(token: str) -> str:
    """Return the literal searched for by the oracle.

    SPL wildcard values such as ``NewProcessName=*wmic*`` cannot occur
    literally in raw telemetry.  Their non-wildcard literal (``wmic``) is the
    machine-checkable part declared by the detection and is what is searched.
    """
    normalized = _normalize_search_text(token).strip()
    if "=" not in normalized or "*" not in normalized:
        return normalized
    _field, value = normalized.split("=", 1)
    literal = value.replace("*", "").strip()
    return literal or normalized


def spl_field_value_discriminators(spl: str) -> list[str]:
    """Extract explicit, non-metadata ``field=value`` clauses from SPL.

    This intentionally does not infer tokens from prose descriptions,
    expected-signal text, bare search words, thresholds, or correlations.
    Those cases remain indeterminate unless the detection library explicitly
    declares ``discriminator_tokens``.
    """
    search_clause = str(spl or "").split("|", 1)[0]
    found: list[str] = []
    for match in _FIELD_VALUE_RE.finditer(search_clause):
        # A quoted free-search term such as "cmd=" or "onerror=" is not an
        # SPL field comparison; the opening quote sits immediately before
        # the regex match.  Bare search words are deliberately out of scope.
        if match.start() and search_clause[match.start() - 1] in {'"', "'"}:
            continue
        field = match.group("field")
        if field.lower() in _SPL_METADATA_FIELDS:
            continue
        value = match.group("double") or match.group("single") or match.group("bare") or ""
        token = f"{field}={value}"
        if token not in found:
            found.append(token)
    return found


def technique_discriminators(technique_id: str) -> dict:
    """Select read-only discriminator data from the production SPL library."""
    signature = technique_signature_full(str(technique_id or "").strip().upper())
    features = signature.get("distinguishing_features") or {}
    declared = [
        str(token) for token in (features.get("discriminator_tokens") or []) if str(token).strip()
    ]
    if declared:
        return {"tokens": declared, "source": "declared_discriminator_tokens"}
    derived = spl_field_value_discriminators(str(signature.get("spl") or ""))
    return {"tokens": derived, "source": "spl_field_value_clauses" if derived else "none"}


def evidence_presence(
    telemetry: str,
    technique_discriminators: Sequence[str],
) -> tuple[str, list[str]]:
    """Search telemetry for already-selected discriminators.

    Deliberately label-blind: this function has no expected-technique, episode,
    ground-truth, verdict, or answer-key parameter.
    """
    tokens = [str(token) for token in technique_discriminators if str(token).strip()]
    if not tokens:
        return INDETERMINATE, []
    haystack = _normalize_search_text(telemetry)
    matched = [token for token in tokens if _search_token(token) in haystack]
    return (PRESENT, matched) if matched else (ABSENT, [])


def model_visible_telemetry(cell: dict) -> tuple[str, bool]:
    """Return only retriever results persisted in the cell trace.

    Queries, model prose, scenario names, expected labels, and any broader
    corpus data are excluded.  A legacy tool trace without ``content`` cannot
    support an honest presence/absence decision and is marked incomplete.
    """
    tool_entries = [entry for entry in (cell.get("trace") or []) if entry.get("section") == "tool"]
    if not tool_entries or any("content" not in entry for entry in tool_entries):
        return "", False
    return "\n".join(str(entry.get("content") or "") for entry in tool_entries), True


def _attribution(verdict: str, exact_hit: bool, oracle: str) -> str:
    if verdict == "CONFIRMED":
        return TRUE_POSITIVE if exact_hit else MISATTRIBUTION
    if oracle == INDETERMINATE:
        return UNSCORABLE_BY_ORACLE
    if verdict == "ANOMALOUS_UNCLASSIFIED":
        return EVIDENCE_PRESENT_MISS if oracle == PRESENT else HONEST_ANOMALY
    if verdict == "RULED_OUT":
        return FALSE_NEGATIVE if oracle == PRESENT else HONEST_NEGATIVE
    return UNSCORABLE_BY_ORACLE


def attribute_cell(cell: dict) -> dict:
    """Attribute one completed, labeled corpus-replay cell."""
    expected = str(cell.get("technique_expected") or "").strip().upper()
    verdict = str(cell.get("verdict") or "").strip().upper()
    reported = [str(t).strip().upper() for t in (cell.get("technique_ids") or []) if t]
    discriminator = technique_discriminators(expected)
    telemetry, capture_complete = model_visible_telemetry(cell)
    if capture_complete:
        oracle, matched = evidence_presence(telemetry, discriminator["tokens"])
        oracle_reason = (
            discriminator["source"] if oracle != INDETERMINATE else "no_declared_discriminator"
        )
    else:
        oracle, matched = INDETERMINATE, []
        oracle_reason = "model_visible_telemetry_not_captured"

    exact_hit = expected in reported
    attribution = _attribution(verdict, exact_hit, oracle)
    return {
        "label": cell.get("label"),
        "technique_expected": expected,
        "mode": cell.get("mode"),
        "model_arm": cell.get("model_arm"),
        "verdict": verdict,
        "technique_ids": reported,
        "promotion_recall": float(cell.get("scoring_recall") or 0.0),
        "oracle_result": oracle,
        "oracle_reason": oracle_reason,
        "discriminator_source": discriminator["source"],
        "discriminators": discriminator["tokens"],
        "matched_discriminators": matched,
        "telemetry_capture_complete": capture_complete,
        "telemetry_chars": len(telemetry),
        "telemetry_sha256": hashlib.sha256(telemetry.encode()).hexdigest(),
        "attribution": attribution,
    }


def attribute_cells(cells: Iterable[dict]) -> list[dict]:
    """Attribute all completed cells in stable input order."""
    return [
        attribute_cell(cell)
        for cell in cells
        if cell.get("status") == "done" and cell.get("technique_expected")
    ]


def _rollup(rows: Iterable[dict]) -> dict[str, int]:
    counts = Counter(row["attribution"] for row in rows)
    return {
        "A_evidence_present_misses": (counts[EVIDENCE_PRESENT_MISS] + counts[FALSE_NEGATIVE]),
        # V5B's branch rule defines B narrowly as RULED_OUT + ABSENT.
        "B_honest_negatives": counts[HONEST_NEGATIVE],
        "defensible_honest_anomalies": counts[HONEST_ANOMALY],
        "I_unscorable": counts[UNSCORABLE_BY_ORACLE],
        "M_misattributions": counts[MISATTRIBUTION],
        "true_positives": counts[TRUE_POSITIVE],
        "cells": sum(counts.values()),
    }


def build_result(cells: list[dict], checkpoint: Path) -> dict:
    rows = attribute_cells(cells)
    by_arm: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_arm[str(row["model_arm"])].append(row)
    return {
        "schema_version": 1,
        "source_checkpoint": str(checkpoint),
        "source_checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
        "semantics": {
            "A": "EVIDENCE_PRESENT_MISS + FALSE_NEGATIVE",
            "B": "HONEST_NEGATIVE (V5B branch-rule definition)",
            "D": "HONEST_ANOMALY (evidence absent but anomaly surfaced; I8-preserving)",
            "I": "UNSCORABLE_BY_ORACLE",
            "M": "MISATTRIBUTION",
        },
        "overall": _rollup(rows),
        "arms": {arm: _rollup(arm_rows) for arm, arm_rows in sorted(by_arm.items())},
        "cells": rows,
    }


def render_markdown(result: dict) -> str:
    lines = [
        "# Blue Orchestration V5A Attribution — 2026-07-25",
        "",
        "## Measurement boundary",
        "",
        "This eval-only instrument selected each cell's labeled technique, loaded "
        "that technique's read-only discriminator data from `spl_detections.yaml`, "
        "and searched only the retriever `content` persisted in the cell trace. "
        "It did not query fresh corpus data and did not inspect model prose when "
        "deciding PRESENT/ABSENT.",
        "",
        f"Checkpoint SHA-256: `{result['source_checkpoint_sha256']}`.",
        "",
        "## World A / World B rollup",
        "",
        "| Arm | A: evidence-present miss | B: honest negative | Honest anomaly | "
        "I: unscorable | M: misattribution | True positive | Cells |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm, rollup in result["arms"].items():
        lines.append(
            f"| `{arm}` | {rollup['A_evidence_present_misses']} | "
            f"{rollup['B_honest_negatives']} | "
            f"{rollup['defensible_honest_anomalies']} | "
            f"{rollup['I_unscorable']} | {rollup['M_misattributions']} | "
            f"{rollup['true_positives']} | {rollup['cells']} |"
        )

    strong = result["arms"].get("strong_full_v3", {})
    lines.extend(
        [
            "",
            "V5B routes on the promotion-relevant `strong_full_v3` arm. Its "
            f"observed branch inputs are **A={strong.get('A_evidence_present_misses', 0)}, "
            f"B={strong.get('B_honest_negatives', 0)}, "
            f"I={strong.get('I_unscorable', 0)}, "
            f"M={strong.get('M_misattributions', 0)}**. "
            "HONEST_ANOMALY is reported separately because discovery is not "
            "punished (I8) and V5B's rule defines B specifically as HONEST_NEGATIVE.",
            "",
            "## Per-technique attribution",
            "",
            "| Arm | Expected | Verdict / reported IDs | Oracle | Attribution | "
            "Matched discriminator |",
            "|---|---|---|---|---|---|",
        ]
    )
    for row in sorted(
        result["cells"], key=lambda item: (str(item["model_arm"]), str(item["technique_expected"]))
    ):
        ids = ", ".join(row["technique_ids"]) or "—"
        matched = ", ".join(row["matched_discriminators"]) or "—"
        lines.append(
            f"| `{row['model_arm']}` | `{row['technique_expected']}` | "
            f"{row['verdict']} / {ids} | {row['oracle_result']} | "
            f"{row['attribution']} | {matched} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation limits",
            "",
            "- PRESENT means a detection-library discriminator was in the exact "
            "retrieval text shown to the model; it does not prove the model noticed it.",
            "- ABSENT means that discriminator was not in model-visible retrieval "
            "text. Evidence may exist elsewhere in the labeled corpus, but fresh "
            "corpus queries are deliberately excluded.",
            "- INDETERMINATE means either the library has no machine-checkable "
            "declared/SPL `field=value` discriminator or a legacy cell did not "
            "capture model-visible retrieval content.",
            "- A CONFIRMED cell is a TRUE_POSITIVE only for the exact expected ID. "
            "Parent/tactic credit retained by the promotion scorer is recorded in "
            "`promotion_recall`, but a different emitted ID remains MISATTRIBUTION "
            "for this precision instrument.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Attribute corpus-replay non-confirms")
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--report-out", type=Path)
    args = parser.parse_args()

    cells = json.loads(args.checkpoint.read_text())
    if not isinstance(cells, list):
        raise SystemExit("checkpoint must contain a JSON list of cell records")
    result = build_result(cells, args.checkpoint)
    rendered_json = json.dumps(result, indent=2, sort_keys=True) + "\n"
    rendered_report = render_markdown(result)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered_json)
    if args.report_out:
        args.report_out.parent.mkdir(parents=True, exist_ok=True)
        args.report_out.write_text(rendered_report)
    if not args.json_out and not args.report_out:
        print(rendered_report)


if __name__ == "__main__":
    main()
