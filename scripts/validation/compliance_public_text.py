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
import os
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


def _compliance_row_with_text(data: Any) -> bool:
    """A WFE row from a compliance suite that carries answer text (N-11): the row's head or
    any transcript turn holds content. Matched on content, not on the file name."""
    if not isinstance(data, dict):
        return False
    tag = f"{data.get('suite', '')} {data.get('workspace', '')} {data.get('task_id', '')}".lower()
    if "compliance" not in tag:
        return False
    if data.get("final_text_head"):
        return True
    return any(isinstance(t, dict) and t.get("content") for t in data.get("transcript") or [])


def _structural(root: Path, files: list[str]) -> list[dict]:
    findings: list[dict] = []
    for rel in files:
        parts = rel.split("/")
        name = parts[-1].lower()
        if rel.endswith(".json"):
            try:
                data = json.loads((root / rel).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = None
            if _compliance_row_with_text(data):
                findings.append({"path": rel, "rule": "compliance answer text in a tracked result"})
                continue
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


def _content(root: Path, *, files: list[str] | None = None) -> tuple[bool, str, list[dict]]:
    if importlib.util.find_spec(DETECTOR) is None:
        return False, "detector absent", []
    try:
        detector = importlib.import_module(DETECTOR)
        return True, "", list(detector.head_findings(root, files=files))
    except Exception as exc:  # noqa: BLE001 - no store in CI is the expected case
        return False, f"not run: {type(exc).__name__}: {exc}"[:200], []


def _changed_files(root: Path) -> list[str]:
    """Relative paths of tracked files changed between merge-base and HEAD."""
    base = subprocess.run(
        ["git", "-C", str(root), "merge-base", "HEAD", "origin/main"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if base.returncode != 0:
        # No common ancestor (e.g. first push) — fall back to full scan.
        return _tracked(root)
    merged = base.stdout.strip()
    diff = subprocess.run(
        ["git", "-C", str(root), "diff", "--name-only", merged, "HEAD"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if diff.returncode != 0:
        return _tracked(root)
    return [f for f in diff.stdout.splitlines() if f]


def audit(
    root: Path = REPO_ROOT,
    *,
    content: bool = True,
    _changed_only: bool | None = None,
) -> tuple[str, str, list[dict]]:
    files = _tracked(root)
    findings = _structural(root, files)
    if content:
        if _changed_only is None:
            _changed_only = os.environ.get("PORTAL5_VALIDATE_CHANGED_ONLY") == "1"
        if _changed_only:
            changed = _changed_files(root)
            ran, why, hits = _content(root, files=changed)
            scan = "content scan ran (changed-only)" if ran else f"content scan NOT RUN ({why})"
        else:
            ran, why, hits = _content(root)
            scan = "content scan ran" if ran else f"content scan NOT RUN ({why})"
    else:
        ran, why, hits = False, "disabled", []
        scan = "content scan NOT RUN (disabled)"
    findings.extend({"path": h.get("path", "?"), "rule": "operator-derived content"} for h in hits)
    if findings:
        return (
            "FAIL",
            f"{len(findings)} public file(s) hold local-only material; {scan}",
            findings,
        )
    return (
        "PASS",
        f"{len(files)} tracked files: public reports are outcome summaries only; {scan}",
        [],
    )


@register(
    "compliance_public_tree_carries_no_operator_text",
    "HK. public tree holds outcome summaries only; run data and operator content stay local",
    order=202,
)
def check_compliance_public_text() -> tuple[str, str, list[dict]]:
    return audit()
