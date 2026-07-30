"""Spine code-coverage gate — hermetic tests for the code→spine authority inversion.

These prove the gate's semantics on a synthetic tree, never against the live repo:
a coverage gate that only works on one repository state is not a gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from portal.platform.wiki.coverage import (
    compute_coverage,
    covered_surfaces,
    discover_code_surfaces,
    load_baseline,
    ratchet_violations,
    render_baseline,
    retired_baseline_entries,
)
from portal.platform.wiki.schema import KnowledgeUnit, SourceRef


def _unit(unit_id: str, *paths: str) -> KnowledgeUnit:
    return KnowledgeUnit(
        id=unit_id,
        kind="what",
        title=unit_id,
        sources=[SourceRef(type="code", path=p) for p in paths],
    )


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A synthetic repo: three real surfaces, one empty file, one cache file."""
    (tmp_path / "portal" / "sub").mkdir(parents=True)
    (tmp_path / "portal" / "alpha.py").write_text("x = 1\n")
    (tmp_path / "portal" / "beta.py").write_text("y = 2\n")
    (tmp_path / "portal" / "sub" / "gamma.py").write_text("z = 3\n")
    (tmp_path / "portal" / "empty.py").write_text("")
    (tmp_path / "portal" / "__pycache__").mkdir()
    (tmp_path / "portal" / "__pycache__" / "cached.py").write_text("nope = 1\n")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "skipme.py").write_text("nope = 2\n")
    (tmp_path / "config").mkdir()
    return tmp_path


def test_eligibility_excludes_caches_dotdirs_and_empty_files(tree: Path) -> None:
    surfaces = discover_code_surfaces(tree)
    assert set(surfaces) == {
        "portal/alpha.py",
        "portal/beta.py",
        "portal/sub/gamma.py",
    }


def test_aggregate_units_do_not_confer_coverage(tree: Path) -> None:
    """unit-code-* are auto-seeded aggregates — counting them grades the generator
    against its own output, the circularity this gate exists to avoid."""
    units = [_unit("unit-code-portal", "portal/alpha.py", "portal/beta.py")]
    assert covered_surfaces(units, tree) == frozenset()
    report = compute_coverage(tree, units)
    assert report.covered == ()
    assert len(report.uncovered) == 3
    assert report.pct == pytest.approx(0.0)


def test_non_aggregate_unit_confers_coverage(tree: Path) -> None:
    units = [_unit("unit-alpha-behavior", "portal/alpha.py")]
    report = compute_coverage(tree, units)
    assert report.covered == ("portal/alpha.py",)
    assert set(report.uncovered) == {"portal/beta.py", "portal/sub/gamma.py"}
    assert report.pct == pytest.approx(100.0 / 3)


def test_glob_citation_expands_so_coverage_is_not_understated(tree: Path) -> None:
    units = [_unit("unit-portal-surface", "portal/*.py")]
    report = compute_coverage(tree, units)
    assert set(report.covered) == {"portal/alpha.py", "portal/beta.py"}


def test_section_fragment_is_stripped_from_citation(tree: Path) -> None:
    units = [_unit("unit-alpha-why", "portal/alpha.py#L10-L20")]
    report = compute_coverage(tree, units)
    assert report.covered == ("portal/alpha.py",)


def test_absolute_and_empty_citations_are_ignored(tree: Path) -> None:
    units = [_unit("unit-junk", "/tmp/elsewhere.py", "   ")]
    assert covered_surfaces(units, tree) == frozenset()


def test_ratchet_is_green_against_its_own_baseline(tree: Path) -> None:
    report = compute_coverage(tree, [_unit("unit-alpha", "portal/alpha.py")])
    (tree / "config").mkdir(exist_ok=True)
    (tree / "config" / "spine_coverage_baseline.yaml").write_text(render_baseline(report))
    assert load_baseline(tree) == frozenset(report.uncovered)
    assert ratchet_violations(report, repo_root=tree) == ()


def test_ratchet_fires_on_new_uncovered_surface(tree: Path) -> None:
    """Red-to-green proof: pin a baseline, add uncovered code, gate must fire."""
    units = [_unit("unit-alpha", "portal/alpha.py")]
    baseline_report = compute_coverage(tree, units)
    (tree / "config" / "spine_coverage_baseline.yaml").write_text(render_baseline(baseline_report))
    assert ratchet_violations(baseline_report, repo_root=tree) == ()

    (tree / "portal" / "delta.py").write_text("w = 4\n")
    after = compute_coverage(tree, units)
    assert ratchet_violations(after, repo_root=tree) == ("portal/delta.py",)

    covered_now = compute_coverage(tree, [*units, _unit("unit-delta", "portal/delta.py")])
    assert ratchet_violations(covered_now, repo_root=tree) == ()


def test_missing_baseline_means_every_uncovered_surface_violates(tree: Path) -> None:
    report = compute_coverage(tree, [_unit("unit-alpha", "portal/alpha.py")])
    assert load_baseline(tree) == frozenset()
    assert len(ratchet_violations(report, repo_root=tree)) == len(report.uncovered)


def test_retired_entries_are_reported_so_debt_can_be_repinned(tree: Path) -> None:
    report = compute_coverage(tree, [_unit("unit-alpha", "portal/alpha.py")])
    stale = frozenset({*report.uncovered, "portal/deleted.py"})
    assert retired_baseline_entries(report, stale) == ("portal/deleted.py",)


def test_baseline_render_is_deterministic_and_parses(tree: Path) -> None:
    import yaml

    report = compute_coverage(tree, [_unit("unit-alpha", "portal/alpha.py")])
    first = render_baseline(report)
    assert first == render_baseline(report)
    parsed = yaml.safe_load(first)
    assert parsed["eligible_count"] == 3
    assert parsed["covered_count"] == 1
    assert parsed["uncovered"] == list(report.uncovered)


def test_empty_tree_reports_full_coverage_not_division_error(tmp_path: Path) -> None:
    report = compute_coverage(tmp_path, [])
    assert report.eligible == ()
    assert report.pct == 100.0
