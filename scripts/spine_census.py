#!/usr/bin/env python3
"""Spine census — measures the wiki's *granularity*, not its size.

The spine's stated job is to hold the projection you cannot get by reading code:
decisions, contracts, and constraints. The `BR` coverage gate, however, walks the
filesystem and requires a unit per eligible `.py` file. That imposes file
granularity on knowledge that lives at subsystem granularity, and it makes
documentation mass grow in lockstep with code mass forever.

This tool separates the two populations so the regrain can be argued from data:

  MIRROR    unit citing exactly one code path and nothing else — its scope was
            almost certainly set by the coverage gate, not by a decision
  SURFACE   unit citing several code paths, or a config/doc source alongside
            code — scoped to a subsystem or contract
  ORPHAN    unit whose cited paths no longer resolve
  CLAIMED   unit with bound claims (the only units BS can actually verify)

Report mode is advisory. `--surfaces` proposes a surface manifest by clustering
mirror units on their common directory, which is the input to the operator
decision about what coverage should mean.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CANONICAL = REPO / "portal_wiki" / "canonical"
ARCHIVE = REPO / "portal_wiki" / "archive"


@dataclass
class Unit:
    uid: str
    path: Path
    kind: str = ""
    tags: list[str] = field(default_factory=list)
    code_sources: list[str] = field(default_factory=list)
    other_sources: list[str] = field(default_factory=list)
    claims: list = field(default_factory=list)
    words: int = 0
    has_why: bool = False

    @property
    def is_mirror(self) -> bool:
        return len(self.code_sources) == 1 and not self.other_sources

    @property
    def is_surface(self) -> bool:
        return len(self.code_sources) > 1 or (bool(self.code_sources) and bool(self.other_sources))

    def unresolved(self) -> list[str]:
        """Cited paths that do not resolve on disk.

        Sources carrying a `<scheme>:` prefix (`ATT&CK:T1078`, `bench-run:...`) are
        logical identifiers, not filesystem paths, and are never unresolved.
        """
        cited = self.code_sources + self.other_sources
        return [p for p in cited if ":" not in p.split("/")[0] and not (REPO / p).exists()]


def _split_front_matter(text: str) -> tuple[str, str]:
    if not text.startswith("---"):
        return "", text
    try:
        end = text.index("\n---", 3)
    except ValueError:
        return "", text
    return text[3:end], text[end + 4 :]


def load_units(directory: Path) -> list[Unit]:
    import yaml

    out: list[Unit] = []
    for p in sorted(directory.glob("*.md")):
        raw, body = _split_front_matter(p.read_text(errors="replace"))
        if not raw:
            continue
        try:
            fm = yaml.safe_load(raw) or {}
        except yaml.YAMLError:
            continue
        srcs = fm.get("sources") or []
        code, other = [], []
        for s in srcs:
            if not isinstance(s, dict):
                continue
            path = str(s.get("path", "")).split("#", 1)[0].strip()
            if not path:
                continue
            (code if s.get("type") == "code" else other).append(path)
        out.append(
            Unit(
                uid=str(fm.get("id", p.stem)),
                path=p,
                kind=str(fm.get("kind", "")),
                tags=list(fm.get("tags") or []),
                code_sources=code,
                other_sources=other,
                claims=list(fm.get("claims") or []),
                words=len(body.split()),
                has_why="## Why" in body,
            )
        )
    return out


def eligible_code_surfaces() -> list[str]:
    """Mirror BR's own eligibility walk so coverage numbers are comparable."""
    try:
        r = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "--", "*.py"],
            cwd=REPO,
            capture_output=True,
            check=True,
            timeout=20,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []
    files = [p for p in r.stdout.decode("utf-8", errors="replace").split("\n") if p]
    keep = []
    for f in files:
        parts = Path(f).parts
        if any(x.startswith(".") or x in {"__pycache__", "results", "node_modules"} for x in parts):
            continue
        try:
            if (REPO / f).stat().st_size == 0:
                continue
        except OSError:
            continue
        keep.append(f)
    return sorted(keep)


def propose_surfaces(units: list[Unit], min_members: int = 3) -> dict[str, list[str]]:
    """Cluster mirror units by the directory of their single cited path.

    A directory holding several mirror units is a candidate consolidation target:
    one surface unit describing the subsystem, replacing N file-scoped units.
    """
    by_dir: dict[str, list[str]] = defaultdict(list)
    for u in units:
        if u.is_mirror:
            by_dir[str(Path(u.code_sources[0]).parent)].append(u.uid)
    return {d: sorted(v) for d, v in sorted(by_dir.items()) if len(v) >= min_members}


def render(units: list[Unit], archived: list[Unit], top: int) -> str:
    eligible = eligible_code_surfaces()
    cited = {p for u in units for p in u.code_sources}
    mirrors = [u for u in units if u.is_mirror]
    surfaces = [u for u in units if u.is_surface]
    neither = [u for u in units if not u.is_mirror and not u.is_surface]
    orphans = [u for u in units if u.unresolved()]
    claimed = [u for u in units if u.claims]
    words = sum(u.words for u in units)

    out: list[str] = []
    out.append("=" * 78)
    out.append("SPINE CENSUS")
    out.append("=" * 78)
    out.append(
        f"  canonical {len(units)}   archived {len(archived)}   "
        f"prose ~{words:,} words (median {sorted(u.words for u in units)[len(units) // 2]})"
    )
    out.append(
        f"  eligible .py surfaces {len(eligible)}   cited by some unit {len(cited & set(eligible))}"
    )
    out.append("")
    out.append(
        f"MIRROR   {len(mirrors)} units scoped to exactly one code file "
        f"({100 * len(mirrors) // max(len(units), 1)}%), ~{sum(u.words for u in mirrors):,} words"
    )
    out.append(
        f"SURFACE  {len(surfaces)} units citing >1 path or code+config "
        f"({100 * len(surfaces) // max(len(units), 1)}%), ~{sum(u.words for u in surfaces):,} words"
    )
    out.append(f"NEITHER  {len(neither)} units with no code source")
    out.append(f"ORPHAN   {len(orphans)} units citing a path that no longer resolves")
    out.append(f"CLAIMED  {len(claimed)} units with bound claims — the only ones BS can verify")
    out.append("")
    kinds = Counter(u.kind for u in units)
    tags = Counter(t for u in units for t in u.tags)
    out.append(f"  kinds: {dict(kinds)}")
    out.append(f"  authored-v1 {tags['authored-v1']}   verified-v1 {tags['verified-v1']}")
    out.append("")
    proposed = propose_surfaces(units)
    collapsible = sum(len(v) for v in proposed.values())
    out.append(f"CONSOLIDATION CANDIDATES — {len(proposed)} directories hold >=3 mirror units,")
    out.append(
        f"  covering {collapsible} units that could regrain to {len(proposed)} surface units"
    )
    for d, members in sorted(proposed.items(), key=lambda kv: -len(kv[1]))[:top]:
        out.append(f"     {len(members):>3} mirrors  {d}")
    if orphans:
        out.append("")
        out.append("ORPHANS (fix or archive — these already fail BS):")
        for u in orphans[:top]:
            out.append(f"     {u.uid:<54} -> {u.unresolved()}")
    out.append("=" * 78)
    return "\n".join(out)


def totals(units: list[Unit]) -> dict:
    eligible = eligible_code_surfaces()
    return {
        "canonical_units": len(units),
        "mirror_units": sum(1 for u in units if u.is_mirror),
        "surface_units": sum(1 for u in units if u.is_surface),
        "orphan_units": sum(1 for u in units if u.unresolved()),
        "claimed_units": sum(1 for u in units if u.claims),
        "prose_words": sum(u.words for u in units),
        "eligible_py_surfaces": len(eligible),
        "consolidation_directories": len(propose_surfaces(units)),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Portal wiki spine census")
    ap.add_argument("--json", action="store_true", help="machine-readable totals")
    ap.add_argument("--surfaces", action="store_true", help="emit the proposed surface manifest")
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()

    units = load_units(CANONICAL)
    if not units:
        print(f"[spine] no units found under {CANONICAL}", file=sys.stderr)
        return 1
    archived = load_units(ARCHIVE) if ARCHIVE.exists() else []

    if args.surfaces:
        print(json.dumps(propose_surfaces(units), indent=2, sort_keys=True))
        return 0
    if args.json:
        print(json.dumps(totals(units), indent=2, sort_keys=True))
        return 0
    print(render(units, archived, args.top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
