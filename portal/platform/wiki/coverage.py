"""Code-surface coverage for the wiki spine — the code→spine authority inversion.

The spine's single-write-point discipline guarantees the forward direction: when a
canonical *unit* changes, its downstream docs regenerate. It does not guarantee the
converse — that a newly added code surface arrives with a unit describing it. This
module measures the converse and is the data source for validate_system.py's
"BR. spine code coverage" check.

Denominator honesty (why aggregates do not count):
`unit-code-<subsystem>` units are auto-seeded by `adapters/seed_code.py`, which cites
only the first five files of a subsystem while titling itself with the full file count.
Counting those citations as coverage grades the generator against its own output — the
same circularity diagnosed in the doc-generation arc, where ~940 units cited the docs
they themselves fed. Coverage here therefore counts citations from *non-aggregate*
units only. Measured at the time this module landed: 46 of 605 eligible files (7.6%).

Absolute, not a ratchet: TASK_WIKI_ZERO_DEBT_V1 drove the uncovered set to zero and
deleted the coverage baseline, so BR is now an unconditional 100% assertion — any
eligible surface not cited by a gate-passing non-aggregate unit fails outright.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]

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
    eligible = set(discover_code_surfaces(root))
    by_unit: dict[str, set[str]] = {}
    for unit in units:
        if unit.id.startswith(_AGGREGATE_ID_PREFIX):
            continue
        # Only a citation to an *eligible code surface* can claim coverage. A unit
        # citing an ATT&CK technique id, a `bench-run:` identifier, or a directory
        # is not claiming a code surface, so it is not an offender no matter how
        # it scores.
        by_unit[unit.id] = _cited_paths_of(unit, root) & eligible
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


# ── R3 manifest-driven coverage ──────────────────────────────────────────────
#
# TASK_PORTAL_SIMPLIFY_V1 Phase R3 replaced the per-file era. Before it, every
# eligible `.py` file needed a hand-authored unit, which set knowledge
# granularity by filesystem walk and made documentation mass grow in lockstep
# with code mass. The regrain collapsed ~570 per-file mirror units into ~30
# subsystem surfaces. Coverage is now asserted against a manifest
# (`config/spine_surfaces.yaml`) that names each surface, the globs that define
# it, and the unit that documents it. The wiki engine stays per-file: check AJ
# treats `portal/platform/wiki/` as the extraction-guarantee boundary, and a new
# file there must be deliberately added to the manifest — which is exactly what
# the R3 adversarial probe verifies.

SURFACE_MANIFEST_PATH = _REPO_ROOT / "config" / "spine_surfaces.yaml"

# Directories whose eligible files are declared one-per-file in the manifest so
# a new file in them fails the gate until deliberately registered. Currently the
# wiki engine only — the extraction-guarantee boundary (check AJ).
_PER_FILE_SURFACE_DIRS = frozenset({"portal/platform/wiki"})


def _expand_manifest_glob(root: Path, pattern: str) -> set[str]:
    """Expand a manifest glob to the eligible files it matches."""
    try:
        return {str(m.relative_to(root)) for m in root.glob(pattern) if m.is_file()}
    except (OSError, ValueError):
        return set()


def _matches_pattern(path: str, pattern: str) -> bool:
    """Does `path` fall under a manifest glob pattern (with fnmatch semantics)?"""
    if any(ch in pattern for ch in "*?["):
        return Path(path).match(pattern)
    return path == pattern


def load_surface_manifest(repo_root: Path | None = None) -> list[dict]:
    """Read `config/spine_surfaces.yaml`: [{name, globs, unit}, ...]."""
    root = repo_root or _REPO_ROOT
    path = root / "config" / "spine_surfaces.yaml"
    if not path.exists():
        return []
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    surfaces = data.get("surfaces") or []
    out = []
    for s in surfaces:
        out.append(
            {
                "name": str(s.get("name", "")),
                "globs": [str(g) for g in (s.get("globs") or [])],
                "unit": str(s.get("unit", "")),
            }
        )
    return out


def surface_manifest_uncovered(
    repo_root: Path | None = None, units=None
) -> tuple[list[str], list[str]]:
    """The R3 two-part gate, read-only.

    Returns (part1_errors, part2_uncovered) where each is a list of messages:

    Part 1 — every declared surface has a covering unit: the unit exists, passes
    the quality gate, and cites at least one path matching the surface's globs.
    Part 2 — every eligible `.py` file falls under some declared surface glob.
    """
    root = repo_root or _REPO_ROOT
    if units is None:
        from portal.platform.wiki.store import load_all

        units = load_all()
    surfaces = load_surface_manifest(root)
    passing = _gate_passing_ids(units, root)
    eligible = set(discover_code_surfaces(root))

    part1: list[str] = []
    for s in surfaces:
        uid, globs = s["unit"], s["globs"]
        if not uid or not globs:
            part1.append(f"surface {s['name']!r}: missing unit or globs")
            continue
        if uid not in {u.id for u in units}:
            part1.append(f"surface {s['name']!r}: covering unit {uid} does not exist")
            continue
        if uid not in passing:
            part1.append(f"surface {s['name']!r}: covering unit {uid} fails the quality gate")
            continue
        unit = next(u for u in units if u.id == uid)
        cited = _cited_paths_of(unit, root) & eligible
        if not any(_matches_pattern(p, g) for p in cited for g in globs):
            part1.append(
                f"surface {s['name']!r}: unit {uid} cites no eligible path matching "
                f"its globs {globs}"
            )

    covered_by_surfaces: set[str] = set()
    for s in surfaces:
        for g in s["globs"]:
            covered_by_surfaces |= _expand_manifest_glob(root, g)

    part2 = sorted(p for p in eligible if p not in covered_by_surfaces)
    return part1, part2


def generate_surface_manifest(repo_root: Path | None = None, units=None) -> list[dict]:
    """Emit the manifest from R2's landed boundaries — never hand-write it.

    The `unit-surface-*` units' globs become the consolidated surface entries.
    Everything else in the eligible tree becomes a per-file entry mapped to the
    best covering unit, EXCEPT the per-file dirs (`portal/platform/wiki/`), whose
    files are declared individually so a new file there forces a manifest entry.
    Idempotent: regenerating over an unchanged tree reproduces the same YAML.
    """
    root = repo_root or _REPO_ROOT
    if units is None:
        from portal.platform.wiki.store import load_all

        units = load_all()
    eligible = sorted(discover_code_surfaces(root))
    passing = _gate_passing_ids(units, root)

    citing: dict[str, list[str]] = {}
    for u in units:
        if u.id.startswith(_AGGREGATE_ID_PREFIX):
            continue
        for p in _cited_paths_of(u, root) & set(eligible):
            citing.setdefault(p, []).append(u.id)

    def best_unit(path: str) -> str:
        for uid in citing.get(path, []):
            if uid in passing:
                return uid
        return citing.get(path, [None])[0] or "unit-code-missing"

    surfaces: list[dict] = []
    covered: set[str] = set()

    # 1. Consolidated surface units carry their own globs.
    for u in sorted(units, key=lambda u: u.id):
        if not u.id.startswith("unit-surface-"):
            continue
        globs = [s.path for s in u.sources if any(c in s.path for c in "*?[")]
        if not globs:
            continue
        surfaces.append({"name": u.id, "globs": sorted(set(globs)), "unit": u.id})
        for g in globs:
            covered |= _expand_manifest_glob(root, g)

    # 2. Per-file dirs: the wiki engine stays per-file so a new file there is a
    #    deliberate manifest addition, not an automatic cover.
    per_file_covered: set[str] = set()
    for p in eligible:
        parent = str(Path(p).parent)
        if parent in _PER_FILE_SURFACE_DIRS and p not in covered:
            name = f"file-{Path(p).with_suffix('').as_posix().replace('/', '-')}"
            surfaces.append({"name": name, "globs": [p], "unit": best_unit(p)})
            per_file_covered.add(p)
    covered |= per_file_covered

    # 3. Any remaining eligible file: per-file entry so new code outside a
    #    documented surface still forces a deliberate manifest addition.
    for p in eligible:
        if p in covered:
            continue
        name = f"file-{Path(p).with_suffix('').as_posix().replace('/', '-')}"
        surfaces.append({"name": name, "globs": [p], "unit": best_unit(p)})
        covered.add(p)

    return sorted(surfaces, key=lambda s: s["name"])


def write_surface_manifest(repo_root: Path | None = None, units=None) -> list[dict]:
    """Regenerate `config/spine_surfaces.yaml` from the live unit set."""
    import yaml

    root = repo_root or _REPO_ROOT
    surfaces = generate_surface_manifest(root, units=units)
    payload = {
        "surfaces": [{"name": s["name"], "globs": s["globs"], "unit": s["unit"]} for s in surfaces]
    }
    path = root / "config" / "spine_surfaces.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Manifest-driven code-surface coverage (BR). Generated by\n"
        "# `python3 -m portal.platform.wiki.coverage` — never hand-edit.\n"
        "# Each surface: a name, the globs that define it, and the unit that\n"
        "# documents it. Every eligible .py file must fall under a declared\n"
        "# surface; new code outside one forces a deliberate manifest entry.\n"
    )
    path.write_text(header + yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return surfaces


if __name__ == "__main__":
    import sys

    args = [a for a in sys.argv[1:] if a == "--write-manifest"]
    if args:
        write_surface_manifest()
        print("wrote config/spine_surfaces.yaml")
    else:
        p1, p2 = surface_manifest_uncovered()
        print(f"part1 errors: {len(p1)}")
        for e in p1[:10]:
            print("  ", e)
        print(f"part2 uncovered: {len(p2)}")
        for p in p2[:10]:
            print("  ", p)
