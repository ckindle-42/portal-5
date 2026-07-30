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
    """Repo-relative paths cited by at least one non-aggregate unit.

    Glob citations are expanded so a unit that legitimately cites `portal/foo/*.py`
    covers each match — coverage should never be understated by citation style.
    """
    root = repo_root or _REPO_ROOT
    covered: set[str] = set()
    for unit in units:
        if unit.id.startswith(_AGGREGATE_ID_PREFIX):
            continue
        for source in unit.sources:
            path = _normalize_source_path(source.path)
            if not path or path.startswith("/"):
                continue
            if any(ch in path for ch in "*?["):
                try:
                    for match in root.glob(path):
                        if match.is_file():
                            covered.add(str(match.relative_to(root)))
                except (OSError, ValueError):
                    continue
            else:
                covered.add(path)
    return frozenset(covered)


def compute_coverage(repo_root: Path | None = None, units=None) -> CoverageReport:
    """Measure code-surface coverage. Loads all canonical units when not supplied."""
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
