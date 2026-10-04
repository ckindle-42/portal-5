"""HL — the compliance data path's derived views verify against the store.

TASK_COMPLIANCE_DATA_TRUTH_V1 D1b (L11). The canonical store is the source of
truth; the Lance index, the default revision scope, the declared windows and
the relationship edges are derived views that must be regenerable and
verifiable against it. ``scripts/compliance/truth/data_integrity.py`` computes
that verification; this check runs it so a drift fails the validator instead
of surfacing as wrong answers months later — which is exactly how the
8,753-section index gap and the 32k-vs-262k window fiction stayed invisible.

Pre-service (``IN_SERVICE=False``) a FAIL downgrades to WARN, like its
sibling checks: the module re-cuts its data constantly during DATA_TRUTH, and
intermediate red must not block pushes of unrelated work. The gate that
matters is the task's own D-step gates.
"""

from __future__ import annotations

from pathlib import Path

from scripts.validation import compliance_acceptance
from scripts.validation.registry import register

REPO_ROOT = Path(__file__).resolve().parents[2]


@register(
    "compliance_data_integrity",
    "HL. the compliance data path's derived views (index, revision scope, "
    "windows, edges) verify against the canonical store",
    order=200,
)
def check_compliance_data_integrity() -> tuple[str, str, list[dict]]:
    import sys

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from scripts.compliance.truth.data_integrity import data_integrity_report

    report = data_integrity_report()
    findings: list[dict] = []
    failed: list[str] = []
    warned: list[str] = []
    for result in report["results"]:
        findings.append({result["name"]: result})
        if result["status"] == "fail":
            failed.append(f"{result['name']}: {result['detail']}")
        elif result["status"] == "warn":
            warned.append(f"{result['name']}: {result['detail']}")
    status = "FAIL" if failed else ("WARN" if warned else "PASS")
    detail = "; ".join(failed or warned)
    if status == "FAIL" and not compliance_acceptance.IN_SERVICE:
        return (
            "WARN",
            f"compliance is pre-service (IN_SERVICE=False) — not blocking. Underlying: {detail}",
            findings,
        )
    return status, detail, findings
