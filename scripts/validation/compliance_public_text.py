"""HK - the public tree carries outcome summaries only; everything else stays local.

READING_TRUTH_V1 P1. The operator's policy (2026-09-28): "summaries of outcomes
can be in the public reports, everything else should just be local while we
continue to develop this, when it is complete none of that will be written
outside of local" - and history is rewritten to match. This check keeps the
tree that way:

1. ``reports/compliance/`` holds only top-level markdown outcome summaries - no
   subdirectories, no receipts, no data files;
2. no tracked path under ``reports/`` has a ``transcripts`` directory segment, and
   no tracked file in any ``results`` directory is a compliance run output (its
   name mentions compliance or the council judgment probe) - P1R: the old
   compliance runs, tests and data leave the record, wherever they were kept;
3. no tracked JSON under ``reports/`` holds a model answer - a string longer
   than ANSWER_MIN_CHARS under an answer-shaped key;
4. when the store, the local identity-term list and the P1 detector are all
   present (the operator's machine, where pushes start), the detector finds no
   operator document text, identity term or operator section id in any tracked
   file. Without them (CI) rule 4 is reported as NOT RUN, never as a pass.

Rules 1-3 need nothing but git, so CI enforces them on every run.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

from scripts.validation.registry import register

REPO_ROOT = Path(__file__).resolve().parents[2]
ANSWER_KEYS = frozenset({"answer", "response", "final_answer", "answer_text", "completion"})
ANSWER_MIN_CHARS = 200
#: a results-directory file whose name carries one of these is a compliance run output
COMPLIANCE_RESULT_MARKERS = ("compliance", "judgment_probe")
DETECTOR = "scripts.compliance.truth.operator_text_audit"


def _tracked(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True, timeout=120
    ).stdout
    return [p for p in out.decode("utf-8", "replace").split("\0") if p]


def _holds_answer(node: Any) -> bool:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ANSWER_KEYS and isinstance(value, str) and len(value) > ANSWER_MIN_CHARS:
                return True
            if _holds_answer(value):
                return True
    elif isinstance(node, list):
        return any(_holds_answer(item) for item in node)
    return False


def _structural(root: Path, files: list[str]) -> list[dict]:
    findings: list[dict] = []
    for rel in files:
        parts = rel.split("/")
        name = parts[-1].lower()
        if "results" in parts[:-1] and any(m in name for m in COMPLIANCE_RESULT_MARKERS):
            findings.append({"path": rel, "rule": "compliance run output in a results directory"})
            continue
        if not rel.startswith("reports/"):
            continue
        if parts[1:2] == ["compliance"] and (len(parts) != 3 or not rel.endswith(".md")):
            findings.append(
                {"path": rel, "rule": "reports/compliance holds only top-level markdown summaries"}
            )
            continue
        if "transcripts" in parts[:-1]:
            findings.append({"path": rel, "rule": "transcripts directory under reports/"})
            continue
        if rel.endswith(".json"):
            try:
                data = json.loads((root / rel).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if _holds_answer(data):
                findings.append({"path": rel, "rule": "model answer text in a public receipt"})
    return findings


def _content(root: Path) -> tuple[bool, str, list[dict]]:
    if importlib.util.find_spec(DETECTOR) is None:
        return False, "detector absent", []
    try:
        detector = importlib.import_module(DETECTOR)
        return True, "", list(detector.head_findings(root))
    except Exception as exc:  # noqa: BLE001 - no store in CI is the expected case
        return False, f"not run: {type(exc).__name__}: {exc}"[:200], []


def audit(root: Path = REPO_ROOT, *, content: bool = True) -> tuple[str, str, list[dict]]:
    files = _tracked(root)
    findings = _structural(root, files)
    ran, why, hits = _content(root) if content else (False, "disabled", [])
    findings.extend({"path": h.get("path", "?"), "rule": "operator-derived content"} for h in hits)
    scan = "content scan ran" if ran else f"content scan NOT RUN ({why})"
    if findings:
        return (
            "FAIL",
            f"{len(findings)} public file(s) hold local-only material; {scan}",
            findings,
        )
    return (
        "PASS",
        f"{len(files)} tracked files: public reports are summaries only; {scan}",
        [],
    )


@register(
    "compliance_public_tree_carries_no_operator_text",
    "HK. public tree holds outcome summaries only; run data and operator content stay local",
    order=202,
)
def check_compliance_public_text() -> tuple[str, str, list[dict]]:
    return audit()
