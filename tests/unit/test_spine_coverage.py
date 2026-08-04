"""Spine code-coverage gate — hermetic tests for the code→spine authority inversion.

These prove the gate's semantics on a synthetic tree, never against the live repo:
a coverage gate that only works on one repository state is not a gate. The baseline
ratchet was retired in TASK_WIKI_ZERO_DEBT_V1 — the gate is now an absolute 100%
assertion, so a unit must pass the quality gate to confer coverage.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from portal.platform.wiki.coverage import (
    compute_coverage,
    covered_surfaces,
    discover_code_surfaces,
)
from portal.platform.wiki.schema import KnowledgeUnit, SourceRef

_BODY_BY_ID: dict[str, str] = {
    "unit-alpha-behavior": (
        "alpha.py is the entry module in this synthetic tree, wiring the "
        "request path and owning the dispatch decision that the coverage gate "
        "attributes to a unit explaining it rather than a bare citation.\n\n"
        "## Why\n\n"
        "alpha.py carries the load-bearing routing decision for the whole "
        "synthetic tree, and a covering unit is what lets the spine prove the "
        "surface is understood instead of merely listed by a citation."
    ),
    "unit-portal-surface": (
        "portal surfaces are enumerated by glob, and the gate expands each "
        "match so a directory-wide citation never understates coverage.\n\n"
        "## Why\n\n"
        "A glob citation legitimately covers every file it matches, so the "
        "gate must count all of them or the reported coverage ratio silently "
        "understates what is actually documented."
    ),
    "unit-alpha-why": (
        "alpha.py is cited with a line fragment, and the gate strips the "
        "fragment so the citation resolves to the file itself.\n\n"
        "## Why\n\n"
        "A section anchor names the file plus a location, and coverage is "
        "about the file itself, never about a specific line inside it, so "
        "the fragment must not break the citation."
    ),
    "unit-alpha": (
        "alpha.py is the only covered surface in this scenario, so the gate "
        "reports the other two files as uncovered and the ratio reflects it.\n\n"
        "## Why\n\n"
        "One covering unit for one file is the minimal green case that the "
        "absolute coverage gate must accept without any baseline allowance "
        "for the remaining surfaces."
    ),
    "unit-beta": (
        "beta.py handles the secondary routing lane, and its placement here "
        "is what the gate needs to prove the surface is understood.\n\n"
        "## Why\n\n"
        "beta.py is a distinct file from alpha.py, so a distinct unit must "
        "cover it or the absolute gate must report it uncovered without "
        "waiting for a baseline re-pin."
    ),
    "unit-gamma": (
        "gamma.py under sub lives on the nested path and carries the "
        "innermost dispatch, so the covering unit records its role for the "
        "spine authority inversion.\n\n"
        "## Why\n\n"
        "gamma.py sits one directory deeper than the others, and nesting must "
        "never exempt a surface from the coverage requirement that the "
        "absolute gate enforces across the whole tree."
    ),
    "unit-junk": (
        "A citation to an absolute path or an empty string names no "
        "repository-local file, so the gate must ignore it entirely rather "
        "than treat it as a surface.\n\n"
        "## Why\n\n"
        "An absolute path and a blank source both resolve to nothing inside "
        "the repository, so neither can be counted as coverage for any file."
    ),
    "unit-delta": (
        "delta.py is added after the first scenario to prove the gate reacts "
        "to a newly landed surface that has no covering unit.\n\n"
        "## Why\n\n"
        "A new file with no unit must be reported uncovered by the absolute "
        "gate, because there is no baseline left to absorb new debt once the "
        "coverage set reaches one hundred percent."
    ),
}


def _unit(unit_id: str, *paths: str) -> KnowledgeUnit:
    """A gate-passing unit: 40+ prose words, a `## Why` section, no figures."""
    return KnowledgeUnit(
        id=unit_id,
        kind="what",
        title=unit_id,
        sources=[SourceRef(type="code", path=p) for p in paths],
        body=_BODY_BY_ID.get(
            unit_id,
            (
                f"{unit_id} is a synthetic unit whose body explains the cited "
                "surface and the rationale behind it, with enough prose to "
                "count as a real explanation of the file it covers.\n\n"
                "## Why\n\n"
                f"{unit_id} exists to give the coverage gate a gate-passing "
                "unit to attribute a surface to, which is the whole point of "
                "the authority inversion under test."
            ),
        ),
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


def test_absolute_gate_reports_every_uncovered_surface(tree: Path) -> None:
    """No baseline to absorb an uncovered surface — it is reported directly."""
    report = compute_coverage(tree, [_unit("unit-alpha", "portal/alpha.py")])
    assert set(report.uncovered) == {"portal/beta.py", "portal/sub/gamma.py"}
    assert report.pct == pytest.approx(100.0 / 3)


def test_gate_passes_when_every_surface_is_covered(tree: Path) -> None:
    units = [
        _unit("unit-alpha", "portal/alpha.py"),
        _unit("unit-beta", "portal/beta.py"),
        _unit("unit-gamma", "portal/sub/gamma.py"),
    ]
    report = compute_coverage(tree, units)
    assert report.uncovered == ()
    assert report.pct == 100.0


def test_gate_failing_unit_confers_no_coverage(tree: Path) -> None:
    """A unit that fails the quality gate cannot carry coverage for a surface."""
    weak = KnowledgeUnit(
        id="unit-weak",
        kind="what",
        title="unit-weak",
        sources=[SourceRef(type="code", path="portal/alpha.py")],
        body="too short",
    )
    report = compute_coverage(tree, [weak])
    assert report.covered == ()
    assert "portal/alpha.py" in report.uncovered


def test_empty_tree_reports_full_coverage_not_division_error(tmp_path: Path) -> None:
    report = compute_coverage(tmp_path, [])
    assert report.eligible == ()
    assert report.pct == 100.0
