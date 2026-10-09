"""The self-test must be able to fail, the report validator must refuse what it cannot back,
and the scorer plane must stay out of the product's import closure."""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from portal.modules.security.core.review_eval import metrics, report, selftest, stamp

ROOT = Path(__file__).parents[3]
CORE = ROOT / "portal" / "modules" / "security" / "core"


def _stamp() -> stamp.Stamp:
    return stamp.build_stamp(
        repo=Path("."),
        embedder_id="emb",
        model_digests={},
        config={"k": 1},
        corpus_snapshot="real:snap",
        policy="p",
        git=lambda _r: ("abc", False),
    )


# ── self-test ────────────────────────────────────────────────────────────────


def test_selftest_passes_for_a_correct_measure() -> None:
    result = selftest.run_selftest(stamp_digest="d")
    assert result.passed, {k: v for k, v in result.checks.items() if not v["passed"]}
    assert set(result.checks) == {
        "oracle",
        "inverted",
        "constant",
        "random",
        "planted",
        "benign_quiet",
    }


def test_selftest_fails_for_a_rigged_measure() -> None:
    def rigged(_s: Sequence[float], _l: Sequence[bool]) -> Mapping[str, float]:
        return {"auroc": 0.97, "recall_at_5pct_fpr": 0.97, "precision_at_npos": 0.97}

    result = selftest.run_selftest(rigged, stamp_digest="d")
    assert not result.passed
    assert not result.checks["oracle"]["passed"] and not result.checks["constant"]["passed"]


def test_selftest_fails_for_a_measure_that_ignores_the_labels() -> None:
    def label_blind(scores: Sequence[float], _l: Sequence[bool]) -> Mapping[str, float]:
        half = len(scores) // 2
        return {
            "auroc": metrics.auroc(list(scores[:half]), list(scores[half:])),
            "recall_at_5pct_fpr": 0.0,
            "precision_at_npos": 0.0,
        }

    assert not selftest.run_selftest(label_blind, stamp_digest="d").passed


# ── report ───────────────────────────────────────────────────────────────────

ROWS: list[dict[str, Any]] = [
    {"label": True, "raised": True},
    {"label": True, "raised": False},
    {"label": False, "raised": False},
    {"label": False, "raised": True},
]


def _recall(rows: Sequence[Mapping[str, Any]]) -> float:
    pos = [r for r in rows if r["label"]]
    return sum(1 for r in pos if r["raised"]) / len(pos)


def _false_raise(rows: Sequence[Mapping[str, Any]]) -> float:
    neg = [r for r in rows if not r["label"]]
    return 1000.0 * sum(1 for r in neg if r["raised"]) / len(neg)


def _metrics() -> list[report.MetricRow]:
    return [
        report.MetricRow(
            "recall", 0.5, 2, 2, "falls to the random-arm recall at the same false-raise"
        ),
        report.MetricRow("false_raise_per_1k", 500.0, 1, 2, "exceeds the analyst budget"),
    ]


RECOMPUTE = {"recall": _recall, "false_raise_per_1k": _false_raise}


def _build(**overrides: Any) -> dict[str, Any]:
    st = overrides.pop("stamp", _stamp())
    args: dict[str, Any] = {
        "stamp": st,
        "selftest": selftest.run_selftest(stamp_digest=st.digest),
        "metrics": _metrics(),
        "rows": ROWS,
        "recompute": RECOMPUTE,
    }
    args.update(overrides)
    return report.build_report(**args)


def test_a_backed_report_builds_and_renders(tmp_path: Path) -> None:
    doc = _build()
    assert doc["stamp_digest"] == _stamp().digest and doc["rows"] == 4
    json_path, md_path = report.write_report(doc, tmp_path, "r1")
    assert json_path.is_file() and md_path.is_file()
    assert "reads as failure when" in md_path.read_text()


def test_report_refuses_a_selftest_bound_to_another_stamp() -> None:
    with pytest.raises(report.ReportInvalid, match="not run against this stamp"):
        _build(selftest=selftest.run_selftest(stamp_digest="some-other-stamp"))


def test_report_refuses_a_failed_selftest() -> None:
    def rigged(_s: Sequence[float], _l: Sequence[bool]) -> Mapping[str, float]:
        return {"auroc": 0.9, "recall_at_5pct_fpr": 0.9, "precision_at_npos": 0.9}

    st = _stamp()
    with pytest.raises(report.ReportInvalid, match="self-test failed"):
        _build(stamp=st, selftest=selftest.run_selftest(rigged, stamp_digest=st.digest))


def test_report_refuses_a_metric_that_cannot_say_how_it_fails() -> None:
    bad = [report.MetricRow("recall", 0.5, 2, 2, "   ")]
    with pytest.raises(report.ReportInvalid, match="does not state how it can fail"):
        _build(metrics=bad)


def test_report_refuses_a_value_that_the_rows_do_not_recompute() -> None:
    bad = [report.MetricRow("recall", 0.75, 2, 2, "falls to chance")]
    with pytest.raises(report.ReportInvalid, match="recompute"):
        _build(metrics=bad)


def test_report_refuses_precision_like_metrics_without_negatives() -> None:
    rows = [{"label": True, "raised": True}, {"label": True, "raised": True}]
    only = [report.MetricRow("precision", 1.0, 2, 2, "drops under the base rate")]
    with pytest.raises(report.ReportInvalid, match="both positives and negatives"):
        _build(metrics=only, rows=rows, recompute={"precision": lambda r: 1.0})


def test_report_refuses_an_incomplete_stamp() -> None:
    incomplete = stamp.build_stamp(
        repo=Path("."),
        embedder_id="",
        model_digests={},
        config={},
        corpus_snapshot="real:s",
        policy="p",
        git=lambda _r: ("abc", False),
    )
    with pytest.raises(report.ReportInvalid, match="embedder_id is empty"):
        _build(stamp=incomplete)


# ── scorer wall: the product's import closure ────────────────────────────────

FORBIDDEN = {
    "portal.modules.security.core.review_eval",
    "portal.modules.security.core.bully.bots_answer_key",
    "portal.modules.security.core.bully.specimen_ledger",
    "portal.modules.security.core.bully.truth_acceptance",
    "portal.modules.security.core.bully.corpus_bed",
    "portal.modules.security.core.bully.inject_plane",
    "portal.modules.security.core.bully.universe",
    "portal.modules.security.core.bully.blend",
}


def _module_file(name: str) -> Path | None:
    base = ROOT / Path(*name.split("."))
    if base.with_suffix(".py").is_file():
        return base.with_suffix(".py")
    init = base / "__init__.py"
    return init if init.is_file() else None


def _imports(path: Path, module: str) -> set[str]:
    package = module if path.name == "__init__.py" else module.rsplit(".", 1)[0]
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".")
                base = ".".join(parts[: len(parts) - (node.level - 1)])
                target = f"{base}.{node.module}" if node.module else base
            else:
                target = node.module or ""
            found.add(target)
            found.update(f"{target}.{alias.name}" for alias in node.names)
    return {n for n in found if n.startswith("portal.")}


def import_closure(roots: list[str]) -> set[str]:
    seen: set[str] = set()
    stack = list(roots)
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        path = _module_file(name)
        if path is None:
            continue
        seen.add(name)
        stack.extend(_imports(path, name) - seen)
    return seen


def _review_modules() -> list[str]:
    return [
        f"portal.modules.security.core.review.{p.stem}"
        for p in sorted((CORE / "review").glob("*.py"))
        if p.stem != "__init__"
    ] + ["portal.modules.security.core.review"]


def test_the_product_import_closure_excludes_the_scorer_plane() -> None:
    closure = import_closure(_review_modules())
    assert (
        "portal.modules.security.core.bully.artifact_graph" in closure
    )  # the walk reaches the engine
    leaked = sorted(m for m in closure if m in FORBIDDEN or m.startswith(tuple(FORBIDDEN)))
    assert leaked == [], f"scorer-plane modules reachable from the product: {leaked}"


def test_the_walk_can_fail() -> None:
    """Seeded violation: a closure rooted at the scorer plane must contain it."""
    closure = import_closure(["portal.modules.security.core.review_eval.report"])
    assert "portal.modules.security.core.review_eval" in closure
    assert "portal.modules.security.core.review.calibration" in closure  # scorer may import product
