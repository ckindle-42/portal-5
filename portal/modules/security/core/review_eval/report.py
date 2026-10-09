"""review_eval.report -- a report that cannot be backed is never written.

``build_report`` refuses (``ReportInvalid``) unless:

1. the stamp is complete (commit, embedder identity, config hash, corpus snapshot);
2. a self-test passed AND was run against this very stamp (``SelfTestResult.stamp_digest``);
3. every metric states ``n`` and ``denominator`` (both positive) and ``can_fail`` -- the plain
   condition under which the number reads as failure; a metric that cannot say how it fails is
   a headline that was "structurally incapable of showing failure";
4. a precision-like or false-raise-like metric is backed by rows that actually contain negatives
   (``precision 1.0`` over a population with none was a real headline once);
5. every value is finite and equals a recomputation from the raw rows (the lab once reported a
   paired test computed over rows from another configuration, and a "max" over 100 of the
   full population's samples).

Raw rows are fingerprinted (``rows_digest``) so a report is tied to the exact rows it came from.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .selftest import SelfTestResult
from .stamp import Stamp

Recompute = Callable[[Sequence[Mapping[str, Any]]], float]

_NEEDS_NEGATIVES = ("precision", "false_raise", "fpr", "specificity")


class ReportInvalid(ValueError):  # noqa: N818 -- the name is the contract
    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = list(problems)


@dataclass(frozen=True)
class MetricRow:
    name: str
    value: float
    n: int
    denominator: int
    can_fail: str


def rows_digest(rows: Sequence[Mapping[str, Any]]) -> str:
    text = json.dumps(list(rows), sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def validate_report(
    *,
    stamp: Stamp,
    selftest: SelfTestResult,
    metrics: Sequence[MetricRow],
    rows: Sequence[Mapping[str, Any]],
    recompute: Mapping[str, Recompute],
) -> list[str]:
    problems = list(stamp.problems())
    if not selftest.passed:
        failed = sorted(k for k, v in selftest.checks.items() if not v["passed"])
        problems.append(f"known-answer self-test failed: {failed}")
    if selftest.stamp_digest != stamp.digest:
        problems.append("self-test was not run against this stamp")
    if not metrics:
        problems.append("no metrics")
    has_neg = any(r.get("label") is False for r in rows)
    has_pos = any(r.get("label") is True for r in rows)
    for metric in metrics:
        where = f"metric {metric.name!r}"
        if metric.n <= 0 or metric.denominator <= 0:
            problems.append(f"{where}: n and denominator must be positive")
        if not metric.can_fail.strip():
            problems.append(f"{where}: does not state how it can fail")
        if not math.isfinite(metric.value):
            problems.append(f"{where}: value is not finite")
        if any(hint in metric.name for hint in _NEEDS_NEGATIVES) and not (has_neg and has_pos):
            problems.append(f"{where}: needs rows with both positives and negatives")
        fn = recompute.get(metric.name)
        if fn is None:
            problems.append(f"{where}: no recomputation from raw rows")
            continue
        again = fn(rows)
        if not math.isclose(again, metric.value, rel_tol=1e-9, abs_tol=1e-9):
            problems.append(f"{where}: reported {metric.value} but rows recompute to {again}")
    return problems


def build_report(
    *,
    stamp: Stamp,
    selftest: SelfTestResult,
    metrics: Sequence[MetricRow],
    rows: Sequence[Mapping[str, Any]],
    recompute: Mapping[str, Recompute],
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    problems = validate_report(
        stamp=stamp, selftest=selftest, metrics=metrics, rows=rows, recompute=recompute
    )
    if problems:
        raise ReportInvalid(problems)
    return {
        "stamp": stamp.to_dict(),
        "stamp_digest": stamp.digest,
        "selftest": {"passed": selftest.passed, "checks": selftest.checks},
        "metrics": [
            {
                "name": m.name,
                "value": m.value,
                "n": m.n,
                "denominator": m.denominator,
                "can_fail": m.can_fail,
            }
            for m in metrics
        ],
        "rows": len(rows),
        "rows_digest": rows_digest(rows),
        "extra": dict(extra or {}),
        "created_at": time.time(),
    }


def render_markdown(doc: Mapping[str, Any]) -> str:
    stamp = doc["stamp"]
    lines = [
        f"# Review evaluation report `{doc['stamp_digest']}`",
        "",
        f"- commit `{stamp['commit']}`{' (DIRTY tree)' if stamp['dirty'] else ''}",
        f"- embedder `{stamp['embedder_id']}`; corpus `{stamp['corpus_snapshot']}`",
        f"- config `{stamp['config_hash']}`; policy `{stamp['policy']}`",
        f"- models: {', '.join(f'{m}@{d[:12]}' for m, d in stamp['model_digests']) or 'none'}",
        f"- rows `{doc['rows']}` digest `{doc['rows_digest']}`",
        "",
        "## Known-answer self-test",
        "",
    ]
    for name, check in doc["selftest"]["checks"].items():
        lines.append(f"- {name}: {'PASS' if check['passed'] else 'FAIL'}")
    lines += [
        "",
        "## Metrics",
        "",
        "| metric | value | n | denominator | reads as failure when |",
        "|---|---|---|---|---|",
    ]
    for m in doc["metrics"]:
        lines.append(
            f"| {m['name']} | {m['value']:.6g} | {m['n']} | {m['denominator']} | {m['can_fail']} |"
        )
    return "\n".join(lines) + "\n"


def write_report(doc: Mapping[str, Any], directory: Path, name: str) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / f"{name}.json"
    md_path = directory / f"{name}.md"
    json_path.write_text(json.dumps(doc, indent=2, sort_keys=True, default=str), encoding="utf-8")
    md_path.write_text(render_markdown(doc), encoding="utf-8")
    return json_path, md_path
