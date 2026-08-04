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
    generate_surface_manifest,
    load_surface_manifest,
    surface_manifest_uncovered,
    write_surface_manifest,
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
    "unit-surface-foo": (
        "The foo subsystem owns the request path, and the surface unit "
        "documents the contract of the whole directory rather than one file "
        "inside it, which is the regrained shape the manifest gate expects.\n\n"
        "## Why\n\n"
        "A directory glob names one surface covering many files, so the "
        "surface unit must pass the gate and cite paths matching the glob "
        "for the manifest two-part assertion to accept it as documented."
    ),
    "unit-surface-bar": (
        "The bar subsystem enumerates its surfaces by glob, and the manifest "
        "gate expands each match so a directory-wide citation never understates "
        "coverage across the synthetic tree's backend files.\n\n"
        "## Why\n\n"
        "A glob citation legitimately covers every file it matches, and the "
        "manifest must count all of them or the gate reports false "
        "uncovered surfaces for a directory that is fully documented."
    ),
    "unit-engine-a": (
        "The wiki engine file a.py is declared per-file in the manifest so "
        "that a brand new file in the engine directory is not automatically "
        "covered by a sibling glob and must be deliberately registered.\n\n"
        "## Why\n\n"
        "The engine is the extraction-guarantee boundary, so a new file there "
        "must force an explicit manifest addition instead of riding in under "
        "a directory glob, which is exactly what the R3 probe verifies."
    ),
    "unit-engine-b": (
        "The wiki engine file b.py is the second per-file manifest entry, "
        "paired with a.py, and together they prove that per-file declarations "
        "still satisfy the manifest's coverage requirement for the engine.\n\n"
        "## Why\n\n"
        "Per-file coverage for the engine directory keeps the boundary honest "
        "while still meeting part two's demand that every eligible file fall "
        "under some declared surface entry."
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


# ── R3 manifest-driven gate ───────────────────────────────────────────────────

_WIKI_ENGINE = "portal/platform/wiki"


def _manifest_units() -> list[KnowledgeUnit]:
    """A synthetic tree: two glob-covered dirs + a per-file engine dir."""
    return [
        _unit("unit-surface-foo", "portal/foo/alpha.py", "portal/foo/beta.py"),
        _unit("unit-surface-bar", "portal/bar/*.py"),
        _unit("unit-engine-a", f"{_WIKI_ENGINE}/a.py"),
        _unit("unit-engine-b", f"{_WIKI_ENGINE}/b.py"),
    ]


def _manifest_tree(tmp_path: Path) -> Path:
    for p in (
        "portal/foo/alpha.py",
        "portal/foo/beta.py",
        "portal/bar/x.py",
        "portal/bar/y.py",
        f"{_WIKI_ENGINE}/a.py",
        f"{_WIKI_ENGINE}/b.py",
    ):
        f = tmp_path / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x = 1\n")
    return tmp_path


def test_manifest_generation_covers_every_eligible_file(tmp_path: Path) -> None:
    tree = _manifest_tree(tmp_path)
    units = _manifest_units()
    surfaces = generate_surface_manifest(tree, units)
    eligible = set(discover_code_surfaces(tree))
    covered: set[str] = set()
    for s in surfaces:
        for g in s["globs"]:
            if any(ch in g for ch in "*?["):
                for m in tree.glob(g):
                    if m.is_file():
                        covered.add(str(m.relative_to(tree)))
            else:
                covered.add(g)
    assert eligible <= covered, eligible - covered


def test_manifest_two_part_gate_passes_when_covered(tmp_path: Path) -> None:
    tree = _manifest_tree(tmp_path)
    units = _manifest_units()
    write_surface_manifest(tree, units)
    part1, part2 = surface_manifest_uncovered(tree, units)
    assert part1 == []
    assert part2 == []


def test_manifest_gate_fails_new_file_outside_surfaces(tmp_path: Path) -> None:
    """The R3 adversarial probe: a new file under no declared surface fails."""
    tree = _manifest_tree(tmp_path)
    units = _manifest_units()
    write_surface_manifest(tree, units)
    # new file in the per-file engine dir — not declared → must fail
    probe = tmp_path / _WIKI_ENGINE / "_simplify_probe.py"
    probe.write_text("x = 1\n")
    _part1, part2 = surface_manifest_uncovered(tree, units)
    assert f"{_WIKI_ENGINE}/_simplify_probe.py" in part2


def test_manifest_gate_fails_when_covering_unit_is_gate_failing(tmp_path: Path) -> None:
    """Part 1: a declared surface whose unit fails the quality gate is broken."""
    tree = _manifest_tree(tmp_path)
    weak = KnowledgeUnit(
        id="unit-surface-foo",
        kind="what",
        title="unit-surface-foo",
        sources=[SourceRef(type="code", path="portal/foo/alpha.py")],
        body="too short",
    )
    units = [weak] + [u for u in _manifest_units() if u.id != "unit-surface-foo"]
    write_surface_manifest(tree, units)
    part1, _part2 = surface_manifest_uncovered(tree, units)
    assert any("unit-surface-foo" in e for e in part1)


def test_manifest_is_idempotent(tmp_path: Path) -> None:
    tree = _manifest_tree(tmp_path)
    units = _manifest_units()
    write_surface_manifest(tree, units)
    first = (tmp_path / "config" / "spine_surfaces.yaml").read_text()
    write_surface_manifest(tree, units)
    second = (tmp_path / "config" / "spine_surfaces.yaml").read_text()
    assert first == second


def test_manifest_loader_reads_what_was_written(tmp_path: Path) -> None:
    tree = _manifest_tree(tmp_path)
    units = _manifest_units()
    write_surface_manifest(tree, units)
    surfaces = load_surface_manifest(tree)
    assert surfaces, "manifest must not be empty"
    for s in surfaces:
        assert s["name"] and s["globs"] and s["unit"]
