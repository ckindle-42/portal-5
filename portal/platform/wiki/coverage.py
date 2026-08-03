"""Code-surface coverage for the wiki spine — the code→spine authority inversion.

The spine's single-write-point discipline guarantees the forward direction: when a
canonical *unit* changes, its downstream docs regenerate. It does not guarantee the
converse — that a newly added code surface arrives with a unit describing it. This
module measures the converse and is the data source for validate_system.py's
"BR. spine code coverage ratchet".

Denominator honesty (why aggregates do not count):
`unit-code-<subsystem>` units are auto-seeded by `adapters/seed_code.py`, which cites
only the first five files of a subsystem while titling itself with the full file count.
Counting those citations as coverage grades the generator against its own output — the
same circularity diagnosed in the doc-generation arc, where ~940 units cited the docs
they themselves fed. Coverage here therefore counts citations from *non-aggregate*
units only. Measured at the time this module landed: 46 of 605 eligible files (7.6%).

Ratchet, not cliff: a 100% assertion is unreachable today and pretending otherwise
would mean either weakening the denominator or mass-generating stub units. The gate
instead pins the current uncovered set as a baseline and fails only when that set
*grows* — so new code cannot land uncovered, and the debt can only shrink.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]

BASELINE_RELPATH = "config/spine_coverage_baseline.yaml"

_AGGREGATE_ID_PREFIX = "unit-code-"
_EXCLUDED_PATH_PARTS = frozenset({"__pycache__", "results", "node_modules"})

# Assessed once per unit-set so the identifier-universe walk (~3.6 s) is not
# repeated for every unit. Keyed by repo root + unit ids; invalidated when new
# units land or a different unit set is assessed.
_gate_passing_cache: dict[tuple[Path, frozenset[str]], frozenset[str]] = {}


def _gate_passing_ids(units, repo_root: Path) -> frozenset[str]:
    """Unit ids that pass the authored-quality gate, cached per unit-set."""
    key = (repo_root, frozenset(u.id for u in units))
    if key in _gate_passing_cache:
        return _gate_passing_cache[key]
    from portal.platform.wiki.quality import assess

    passing = set(assess(units, repo_root).passing)
    _gate_passing_cache[key] = frozenset(passing)
    return _gate_passing_cache[key]


def reset_gate_cache() -> None:
    """Drop the assessed-unit cache (tests, or after new units are authored)."""
    _gate_passing_cache.clear()


@dataclass(frozen=True)
class CoverageReport:
    """Result of a coverage computation. All path tuples are repo-relative, sorted."""

    eligible: tuple[str, ...]
    covered: tuple[str, ...]
    uncovered: tuple[str, ...]

    @property
    def pct(self) -> float:
        if not self.eligible:
            return 100.0
        return 100.0 * len(self.covered) / len(self.eligible)


def _is_eligible(rel_path: str, repo_root: Path) -> bool:
    """Mirror seed_code's eligibility rules: no dotdirs, no caches, no empty files."""
    parts = Path(rel_path).parts
    if any(p.startswith(".") or p in _EXCLUDED_PATH_PARTS for p in parts):
        return False
    try:
        if os.path.getsize(repo_root / rel_path) == 0:
            return False
    except OSError:
        return False
    return True


def discover_code_surfaces(repo_root: Path | None = None) -> tuple[str, ...]:
    """Enumerate eligible Python code surfaces, git-aware (respects .gitignore)."""
    root = repo_root or _REPO_ROOT
    try:
        result = subprocess.run(
            [
                "git",
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
                "--",
                "*.py",
            ],
            cwd=root,
            capture_output=True,
            check=True,
            timeout=15,
        )
        candidates = [
            p for p in result.stdout.decode("utf-8", errors="surrogateescape").split("\0") if p
        ]
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        candidates = [str(p.relative_to(root)) for p in root.rglob("*.py")]
    return tuple(sorted(p for p in candidates if _is_eligible(p, root)))


def _normalize_source_path(raw: str) -> str:
    """Strip a `#section` fragment and surrounding whitespace/quotes."""
    return raw.split("#", 1)[0].strip().strip('"').strip("'")


def covered_surfaces(units, repo_root: Path | None = None) -> frozenset[str]:
    """Repo-relative paths cited by at least one non-aggregate, gate-passing unit.

    A citation counts as coverage only when the citing unit passes `quality.assess`
    (see `quality.py` for the checks). A unit that fails the gate is not coverage —
    the gate is the definition, not a review step afterwards.

    Glob citations are expanded so a unit that legitimately cites `portal/foo/*.py`
    covers each match — coverage should never be understated by citation style.
    """
    root = repo_root or _REPO_ROOT
    passing = _gate_passing_ids(units, root)
    covered: set[str] = set()
    for unit in units:
        if unit.id.startswith(_AGGREGATE_ID_PREFIX) or unit.id not in passing:
            continue
        covered |= _cited_paths_of(unit, root)
    return frozenset(covered)


def _cited_paths_of(unit, repo_root: Path) -> set[str]:
    """Repo-relative paths a single unit cites (globs expanded)."""
    out: set[str] = set()
    for source in unit.sources:
        path = _normalize_source_path(source.path)
        if not path or path.startswith("/"):
            continue
        if any(ch in path for ch in "*?["):
            try:
                for match in repo_root.glob(path):
                    if match.is_file():
                        out.add(str(match.relative_to(repo_root)))
            except (OSError, ValueError):
                continue
        else:
            out.add(path)
    return out


def gate_failing_coverage_units(repo_root: Path | None = None, units=None) -> tuple[str, ...]:
    """Units that fail the quality gate yet are the only citation for a surface.

    A unit that fails `quality.assess` cannot carry coverage — but a failing unit
    whose citation is redundant (another gate-passing unit covers the same
    surface) is harmless noise. This returns the units that are actually
    *claiming* coverage through a citation nothing else covers: the offender set
    BR names on a hard fail.
    """
    root = repo_root or _REPO_ROOT
    if units is None:
        from portal.platform.wiki.store import load_all

        units = load_all()
    passing = _gate_passing_ids(units, root)
    by_unit: dict[str, set[str]] = {}
    for unit in units:
        if unit.id.startswith(_AGGREGATE_ID_PREFIX):
            continue
        by_unit[unit.id] = _cited_paths_of(unit, root)
    offenders: set[str] = set()
    for uid, paths in by_unit.items():
        if uid in passing:
            continue
        for path in paths:
            others = [
                other
                for other, other_paths in by_unit.items()
                if other != uid and other in passing and path in other_paths
            ]
            if not others:
                offenders.add(uid)
                break
    return tuple(sorted(offenders))


def compute_coverage(repo_root: Path | None = None, units=None) -> CoverageReport:
    """Measure code-surface coverage. Loads all canonical units when not supplied.

    A surface is covered only when a *gate-passing* non-aggregate unit cites it —
    the quality gate is part of the definition of coverage, so a citation from a
    unit that fails `quality.assess` does not count.
    """
    root = repo_root or _REPO_ROOT
    if units is None:
        from portal.platform.wiki.store import load_all

        units = load_all()
    eligible = discover_code_surfaces(root)
    cited = covered_surfaces(units, root)
    covered = tuple(p for p in eligible if p in cited)
    uncovered = tuple(p for p in eligible if p not in cited)
    return CoverageReport(eligible=eligible, covered=covered, uncovered=uncovered)


def load_baseline(repo_root: Path | None = None) -> frozenset[str]:
    """Read the pinned uncovered set. Missing file means an empty baseline."""
    root = repo_root or _REPO_ROOT
    path = root / BASELINE_RELPATH
    if not path.exists():
        return frozenset()
    import yaml

    data = yaml.safe_load(path.read_text()) or {}
    return frozenset(data.get("uncovered", []) or [])


def render_baseline(report: CoverageReport) -> str:
    """Serialize a baseline document. Deterministic — safe to diff and re-run."""
    lines = [
        "# Spine code-coverage baseline — pinned uncovered code surfaces.",
        "#",
        "# Generated by portal.platform.wiki.coverage. Consumed by",
        "# validate_system.py check BR (spine code coverage ratchet).",
        "#",
        "# This list may SHRINK freely (write a covering unit, then re-pin). It may",
        "# never GROW: a new uncovered surface fails CI. Do not hand-edit to silence",
        "# the gate — that defeats the authority inversion it exists to enforce.",
        f"eligible_count: {len(report.eligible)}",
        f"covered_count: {len(report.covered)}",
        f"coverage_pct: {report.pct:.1f}",
        "uncovered:",
    ]
    lines.extend(f"  - {p}" for p in report.uncovered)
    return "\n".join(lines) + "\n"


def ratchet_violations(
    report: CoverageReport, baseline: frozenset[str] | None = None, repo_root: Path | None = None
) -> tuple[str, ...]:
    """Uncovered surfaces absent from the baseline — i.e. new code with no unit."""
    base = load_baseline(repo_root) if baseline is None else baseline
    return tuple(p for p in report.uncovered if p not in base)


def retired_baseline_entries(
    report: CoverageReport, baseline: frozenset[str] | None = None, repo_root: Path | None = None
) -> tuple[str, ...]:
    """Baseline entries now covered or deleted — the debt that can be re-pinned away."""
    base = load_baseline(repo_root) if baseline is None else baseline
    current = set(report.uncovered)
    return tuple(sorted(p for p in base if p not in current))
