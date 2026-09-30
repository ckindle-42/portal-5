"""HJ - compliance suite receipts say how their verdicts were reached, and what ran.

READING_TRUTH_V1 P9. Every compliance "baseline" quoted before this check was a
MECHANICAL citation score presented as reading quality, compared across runs
whose grader, persona, tool manifest, engine and sampling had moved, with
nothing on the receipt saying either. Two things are therefore required of
every suite receipt written after CUTOFF_UTC:

* ``verdict_basis`` - ``mechanical`` (citation-integrity checks only) or
  ``judged`` (a blind reading against the answer key). A judged receipt also
  names the key it was judged against (``key_manifest_sha256``).
* ``provenance`` - ``scripts/compliance/truth/provenance.py``'s block: git
  head, workspace settings, persona and tool-manifest hashes, grader hashes.

Receipts written before the cutoff are history and are exempt; this check is
about what gets written from now on. Private receipts are audited when present
(the operator's machine) and simply absent in CI.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from scripts.validation.registry import register

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOTS = (
    REPO_ROOT / "reports" / "compliance",
    REPO_ROOT / "portal" / "modules" / "compliance" / "data" / "private",
)
SUITE_RECEIPTS = (
    "conversational_proof.json",
    "product_questions_family.json",
    "judged_report.json",
)
#: set by READING_TRUTH_V1 P9 to the moment its harness changes landed
CUTOFF_UTC = "2026-09-28T00:00:00+00:00"
VERDICT_BASES = ("mechanical", "judged")


def _when(stamp: str) -> datetime | None:
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _problems(data: dict) -> list[str]:
    problems: list[str] = []
    basis = data.get("verdict_basis")
    if basis not in VERDICT_BASES:
        problems.append("verdict_basis missing or not one of mechanical|judged")
    provenance = data.get("provenance")
    if not isinstance(provenance, dict) or not provenance.get("git_head"):
        problems.append("provenance block missing or has no git_head")
    elif not isinstance(provenance.get("workspace_settings"), dict):
        problems.append("provenance block has no workspace_settings")
    if basis == "judged" and not data.get("key_manifest_sha256"):
        problems.append("judged receipt does not name the answer key it was judged against")
    return problems


def audit(roots: tuple[Path, ...] = ROOTS, cutoff: str = CUTOFF_UTC) -> tuple[str, str, list[dict]]:
    limit = _when(cutoff)
    findings: list[dict] = []
    checked = 0
    for root in roots:
        if not root.is_dir():
            continue
        for name in SUITE_RECEIPTS:
            for path in sorted(root.rglob(name)):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    findings.append({"receipt": str(path), "problems": [f"unreadable: {exc}"]})
                    continue
                if not isinstance(data, dict):
                    continue
                when = _when(str(data.get("run_id") or data.get("generated_utc") or ""))
                if when is None or limit is None or when < limit:
                    continue
                checked += 1
                problems = _problems(data)
                if problems:
                    rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
                    findings.append({"receipt": str(rel), "problems": problems})
    if findings:
        return (
            "FAIL",
            f"{len(findings)} compliance suite receipt(s) after {cutoff} do not declare "
            "verdict_basis/provenance",
            findings,
        )
    return (
        "PASS",
        f"{checked} post-cutoff suite receipt(s) declare verdict basis and provenance",
        [],
    )


@register(
    "compliance_receipts_declare_basis_and_provenance",
    "HJ. compliance suite receipts declare how verdicts were reached and what ran",
    order=201,
)
def check_compliance_receipts_declare_basis() -> tuple[str, str, list[dict]]:
    return audit()
