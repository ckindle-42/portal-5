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
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from portal.platform.wiki.schema import KnowledgeUnit

_REPO_ROOT = Path(__file__).resolve().parents[3]

_AGGREGATE_ID_PREFIX = "unit-code-"
_EXCLUDED_PATH_PARTS = frozenset({"__pycache__", "results", "node_modules"})

# Assessed once per unit-set so the identifier-universe walk (~3.6 s) is not
# repeated for every unit. Keyed by repo root + unit ids; invalidated when new
# units land or a different unit set is assessed.
_gate_passing_cache: dict[tuple[Path, frozenset[str]], frozenset[str]] = {}


def _gate_passing_ids(units: Sequence[KnowledgeUnit], repo_root: Path) -> frozenset[str]:
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


def covered_surfaces(
    units: Sequence[KnowledgeUnit], repo_root: Path | None = None
) -> frozenset[str]:
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


def _cited_paths_of(unit: KnowledgeUnit, repo_root: Path) -> set[str]:
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


def gate_failing_coverage_units(
    repo_root: Path | None = None,
    units: Sequence[KnowledgeUnit] | None = None,
) -> tuple[str, ...]:
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


def compute_coverage(
    repo_root: Path | None = None,
    units: Sequence[KnowledgeUnit] | None = None,
) -> CoverageReport:
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


# ── B3 directory ownership ───────────────────────────────────────────────────
#
# DESIGN_ROOTS_REFINEMENT_20261020 B3 replaced R3's per-file manifest. R3's
# 419 file → unit bindings churned on routine commits because every new file
# forced a manifest entry. Ownership is now a directory: a module dir
# (`portal/modules/<name>`) is owned by `unit-module-<name>`, a platform
# package (`portal/platform/<pkg>`) by the gate-passing unit citing most of
# its eligible files. Coverage asks whether every module, MCP and platform
# package has a unit — a code edit inside a module demands no unit edit and
# no manifest entry; a contract change (new module, new MCP, new platform
# package) forces the unit.

SURFACE_MANIFEST_PATH = _REPO_ROOT / "config" / "spine_surfaces.yaml"

_MODULES_ROOT = "portal/modules"
_PLATFORM_ROOT = "portal/platform"


def _under(path: str, directory: str) -> bool:
    """Is `path` the directory itself or a file inside it?"""
    return path == directory or path.startswith(directory + "/")


def _code_dirs(root: Path, base: str) -> list[str]:
    """Dirs under `base` holding at least one eligible `.py` file."""
    parent = root / base
    if not parent.is_dir():
        return []
    out = []
    for d in sorted(parent.iterdir()):
        if not d.is_dir() or d.name.startswith((".", "__")):
            continue
        if any(_is_eligible(str(p.relative_to(root)), root) for p in d.rglob("*.py")):
            out.append(f"{base}/{d.name}")
    return out


def discover_module_dirs(repo_root: Path | None = None) -> list[str]:
    """Module directories on disk: `portal/modules/<name>` with eligible code."""
    return _code_dirs(repo_root or _REPO_ROOT, _MODULES_ROOT)


def discover_platform_packages(repo_root: Path | None = None) -> list[str]:
    """Platform packages on disk: `portal/platform/<pkg>` with eligible code."""
    return _code_dirs(repo_root or _REPO_ROOT, _PLATFORM_ROOT)


def load_surface_manifest(repo_root: Path | None = None) -> list[dict[str, str]]:
    """Read `config/spine_surfaces.yaml`: [{name, dir, unit}, ...]."""
    root = repo_root or _REPO_ROOT
    path = root / "config" / "spine_surfaces.yaml"
    if not path.exists():
        return []
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    surfaces = data.get("surfaces") or []
    return [
        {
            "name": str(s.get("name", "")),
            "dir": str(s.get("dir", "")),
            "unit": str(s.get("unit", "")),
        }
        for s in surfaces
    ]


def _citations_by_path(
    units: Sequence[KnowledgeUnit], root: Path, eligible: set[str]
) -> dict[str, list[str]]:
    """Eligible path -> non-aggregate unit ids citing it."""
    citing: dict[str, list[str]] = {}
    for u in units:
        if u.id.startswith(_AGGREGATE_ID_PREFIX):
            continue
        for p in _cited_paths_of(u, root) & eligible:
            citing.setdefault(p, []).append(u.id)
    return citing


def _best_owning_unit(directory: str, citing: dict[str, list[str]], passing: frozenset[str]) -> str:
    """The gate-passing unit citing the most eligible files under `directory`."""
    scores: dict[str, int] = {}
    for path, ids in citing.items():
        if not _under(path, directory):
            continue
        for uid in ids:
            if uid in passing:
                scores[uid] = scores.get(uid, 0) + 1
    if not scores:
        return "unit-code-missing"
    return max(sorted(scores), key=lambda uid: scores[uid])


def surface_manifest_uncovered(
    repo_root: Path | None = None,
    units: Sequence[KnowledgeUnit] | None = None,
    module_roster: Sequence[str] | None = None,
    mcp_fleet: Sequence[str] | None = None,
) -> tuple[list[str], list[str]]:
    """The B3 two-part gate, read-only.

    Returns (part1_errors, part2_uncovered) where each is a list of messages:

    Part 1 — every declared owner exists, passes the quality gate, and cites
    at least one eligible path under its directory.
    Part 2 — coverage by entity: every module dir and platform package is
    declared, every roster module has `unit-module-<name>`, and every
    mcp_fleet id has `unit-capability-<id>`.
    """
    root = repo_root or _REPO_ROOT
    if units is None:
        from portal.platform.wiki.store import load_all

        units = load_all()
    surfaces = load_surface_manifest(root)
    passing = _gate_passing_ids(units, root)
    eligible = set(discover_code_surfaces(root))
    by_id = {u.id: u for u in units}

    part1: list[str] = []
    for s in surfaces:
        uid, directory = s["unit"], s["dir"]
        if not uid or not directory:
            part1.append(f"surface {s['name']!r}: missing unit or dir")
            continue
        unit = by_id.get(uid)
        if unit is None:
            part1.append(f"surface {s['name']!r}: owning unit {uid} does not exist")
            continue
        if uid not in passing:
            part1.append(f"surface {s['name']!r}: owning unit {uid} fails the quality gate")
            continue
        if not any(_under(p, directory) for p in _cited_paths_of(unit, root) & eligible):
            part1.append(
                f"surface {s['name']!r}: unit {uid} cites no eligible path under {directory}"
            )

    part2 = _entity_coverage_gaps(root, units, surfaces, module_roster, mcp_fleet)
    return part1, part2


def _load_mcp_fleet_ids(root: Path) -> list[str]:
    """mcp_fleet ids from config/portal.yaml; empty when the file is absent."""
    import yaml

    path = root / "config" / "portal.yaml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [str(e["id"]) for e in data.get("mcp_fleet") or [] if e.get("id")]


def _entity_coverage_gaps(
    root: Path,
    units: Sequence[KnowledgeUnit],
    surfaces: list[dict[str, str]],
    module_roster: Sequence[str] | None,
    mcp_fleet: Sequence[str] | None,
) -> list[str]:
    """Part 2: the modules, MCPs, module dirs and platform packages missing a unit."""
    by_id = {u.id for u in units}
    declared = {s["dir"] for s in surfaces}
    module_dirs = discover_module_dirs(root)
    platform_dirs = discover_platform_packages(root)

    gaps: list[str] = []
    for d in module_dirs + platform_dirs:
        if d not in declared:
            gaps.append(f"{d} is named in no manifest entry")

    roster = (
        list(module_roster)
        if module_roster is not None
        else [d.rsplit("/", 1)[1] for d in module_dirs]
    )
    for name in roster:
        uid = f"unit-module-{name.replace('_', '-')}"
        if uid not in by_id:
            gaps.append(f"module {name} has no {uid}")

    fleet = list(mcp_fleet) if mcp_fleet is not None else _load_mcp_fleet_ids(root)
    for fid in fleet:
        uid = f"unit-capability-{fid.replace('_', '-')}"
        if uid not in by_id:
            gaps.append(f"MCP {fid} has no {uid}")
    return gaps


def generate_surface_manifest(
    repo_root: Path | None = None, units: Sequence[KnowledgeUnit] | None = None
) -> list[dict[str, str]]:
    """Emit the directory-ownership manifest from the live unit set.

    One entry per module dir — owned by `unit-module-<name>` when that unit
    exists, else the best gate-passing unit citing the dir — and one per
    platform package, owned by the gate-passing unit citing most of its
    eligible files. Idempotent: regenerating over an unchanged tree
    reproduces the same YAML.
    """
    root = repo_root or _REPO_ROOT
    if units is None:
        from portal.platform.wiki.store import load_all

        units = load_all()
    passing = _gate_passing_ids(units, root)
    eligible = set(discover_code_surfaces(root))
    citing = _citations_by_path(units, root, eligible)
    unit_ids = {u.id for u in units}

    surfaces: list[dict[str, str]] = []
    for d in discover_module_dirs(root):
        name = d.rsplit("/", 1)[1]
        uid = f"unit-module-{name.replace('_', '-')}"
        if uid not in unit_ids:
            uid = _best_owning_unit(d, citing, passing)
        surfaces.append({"name": f"module-{name}", "dir": d, "unit": uid})
    for d in discover_platform_packages(root):
        surfaces.append(
            {
                "name": f"platform-{d.rsplit('/', 1)[1]}",
                "dir": d,
                "unit": _best_owning_unit(d, citing, passing),
            }
        )
    return sorted(surfaces, key=lambda s: s["name"])


def write_surface_manifest(
    repo_root: Path | None = None, units: Sequence[KnowledgeUnit] | None = None
) -> list[dict[str, str]]:
    """Regenerate `config/spine_surfaces.yaml` from the live unit set."""
    import yaml

    root = repo_root or _REPO_ROOT
    surfaces = generate_surface_manifest(root, units=units)
    payload = {
        "surfaces": [{"name": s["name"], "dir": s["dir"], "unit": s["unit"]} for s in surfaces]
    }
    path = root / "config" / "spine_surfaces.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Directory-ownership code coverage (BR). Generated by\n"
        "# `python3 -m portal.platform.wiki.coverage` — never hand-edit.\n"
        "# Each entry: a module dir or platform package, and the unit that\n"
        "# owns it. Adding a file inside a module needs no entry here; a new\n"
        "# module, MCP or platform package forces its unit (DESIGN B3).\n"
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
