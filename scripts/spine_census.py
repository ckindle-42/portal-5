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
        logical identifiers, not filesystem paths, and are never unresolved. Glob
        citations are expanded so a surface unit citing `portal/foo/*.py` is not
        misread as citing a nonexistent literal path.
        """
        cited = self.code_sources + self.other_sources
        out = []
        for p in cited:
            if ":" in p.split("/")[0]:
                continue
            if any(ch in p for ch in "*?["):
                if not list(REPO.glob(p)):
                    out.append(p)
                continue
            if not (REPO / p).exists():
                out.append(p)
        return out


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


def _corpus_commit(root: Path) -> str:
    """HEAD of the corpus checkout, when the dataset tree is a git work tree."""
    for candidate in (root, root.parent):
        if not (candidate / ".git").exists():
            continue
        try:
            result = subprocess.run(
                ["git", "-C", str(candidate), "rev-parse", "HEAD"],
                capture_output=True,
                check=True,
                timeout=20,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return ""
        return result.stdout.strip()
    return ""


def _record_from_event_line(line: str) -> dict:
    """Same record shape the attack-data anchor loader classifies."""
    stripped = line.strip()
    if stripped.startswith("{"):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
    return {"_raw": stripped}


def _classify_episode(episode: Path, items: list, classify) -> dict:
    """Classify every record in one episode directory."""
    from scripts.corpus_ingest import iter_events_text

    declared = {item.path: (item.sourcetype or "(none)") for item in items}
    techniques = sorted({tech for item in items for tech in item.techniques})
    per_st: dict[str, list] = {}
    spine: list[str] = []
    n_records = 0
    for path in sorted(episode.iterdir()):
        if not path.is_file() or path.suffix.lower() in {".yml", ".yaml"}:
            continue
        sourcetype = declared.get(path, "(unlisted)")
        bucket = per_st.setdefault(sourcetype, [0, 0, Counter()])
        try:
            lines = iter_events_text(path)
        except OSError:
            continue
        try:
            for line in lines:
                if not line:
                    continue
                n_records += 1
                bucket[0] += 1
                cls = classify(_record_from_event_line(line)) or ""
                if cls:
                    bucket[1] += 1
                    bucket[2][cls] += 1
                    spine.append(cls)
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
    return {
        "techniques": techniques,
        "per_st": per_st,
        "spine": spine,
        "n_records": n_records,
        "sourcetypes": sorted(declared.values()),
    }


def _median(values: list[int]) -> float:
    if not values:
        return 0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2


def _spine_shape(lengths: list[int], distinct_counts: list[int]) -> dict:
    single = sum(1 for count in distinct_counts if count == 1)
    multi = sum(1 for count in distinct_counts if count >= 2)
    return {
        "empty": 0,
        "single_class": single,
        "multi_class": multi,
        "median_length": _median(lengths),
        "stored": len(lengths),
    }


def _accumulate_sourcetype(totals: dict, sourcetype: str, bucket: list) -> None:
    row = totals.setdefault(
        sourcetype,
        {"records": 0, "classified": 0, "episodes": 0, "class_distribution": Counter()},
    )
    row["records"] += bucket[0]
    row["classified"] += bucket[1]
    row["episodes"] += 1
    row["class_distribution"].update(bucket[2])


def _sourcetype_rows(totals: dict) -> list[dict]:
    rows = []
    for sourcetype, row in totals.items():
        records = row["records"]
        classified = row["classified"]
        rows.append(
            {
                "sourcetype": sourcetype,
                "records": records,
                "classified": classified,
                "rate": round(classified / records, 4) if records else 0.0,
                "episodes": row["episodes"],
                "class_distribution": dict(row["class_distribution"]),
            }
        )
    return sorted(rows, key=lambda item: (item["rate"], item["sourcetype"]))


def content_census(root: Path, *, seed: int = 0, type_fraction: float = 0.5) -> dict:
    """Classify every record of every labelled episode under ``root``."""
    from portal.modules.security.core.bully import telemetry_behavior
    from portal.modules.security.core.bully.unit_measurement import split_datasets
    from scripts.corpus_ingest import load_manifest_catalog
    from scripts.load_attack_data_anchors import _episode_key

    catalog = load_manifest_catalog(root)
    episodes: dict[Path, list] = {}
    for item in catalog:
        episodes.setdefault(item.path.parent, []).append(item)
    labelled = {
        episode: items
        for episode, items in episodes.items()
        if any(item.techniques for item in items)
    }
    ordered = sorted(labelled, key=lambda path: str(path))
    keys = [_episode_key(episode, root) for episode in ordered]
    split = split_datasets(keys, type_fraction=type_fraction, seed=seed)
    classify = telemetry_behavior.classify_content

    totals: dict = {}
    empty_all: list[dict] = []
    train_empty: list[dict] = []
    train_lengths: list[int] = []
    train_distinct: list[int] = []
    train_techniques: set[str] = set()
    train_episodes = 0
    empty_episode = 0
    for index, episode in enumerate(ordered, start=1):
        measured = _classify_episode(episode, labelled[episode], classify)
        for sourcetype, bucket in measured["per_st"].items():
            if bucket[0]:
                _accumulate_sourcetype(totals, sourcetype, bucket)
        relative = episode.relative_to(root).as_posix()
        entry = {
            "episode": relative,
            "sourcetypes": measured["sourcetypes"],
            "techniques": measured["techniques"],
            "records": measured["n_records"],
        }
        key = _episode_key(episode, root)
        in_train = key in split.type_dataset_keys
        if in_train:
            train_episodes += 1
        if measured["n_records"] == 0:
            empty_episode += 1
            continue
        if not measured["spine"]:
            empty_all.append(entry)
            if in_train:
                train_empty.append(entry)
            continue
        if in_train:
            train_lengths.append(len(measured["spine"]))
            train_distinct.append(len(set(measured["spine"])))
            train_techniques.update(measured["techniques"])
        if index % 100 == 0:
            print(f"[content-census] {index}/{len(ordered)} episodes", file=sys.stderr)
    return _content_report(
        root,
        seed=seed,
        type_fraction=type_fraction,
        labelled=len(labelled),
        empty_episode=empty_episode,
        empty_all=empty_all,
        rows=_sourcetype_rows(totals),
        train_episodes=train_episodes,
        train_empty=train_empty,
        train_lengths=train_lengths,
        train_distinct=train_distinct,
        train_techniques=train_techniques,
    )


def _content_report(
    root: Path,
    *,
    seed: int,
    type_fraction: float,
    labelled: int,
    empty_episode: int,
    empty_all: list[dict],
    rows: list[dict],
    train_episodes: int,
    train_empty: list[dict],
    train_lengths: list[int],
    train_distinct: list[int],
    train_techniques: set[str],
) -> dict:
    """Census document. The train half uses the anchor loader's split."""
    return {
        "schema": "CONTENT_CLASSIFIER_CENSUS_V1",
        "root": str(root),
        "corpus_commit": _corpus_commit(root),
        "labelled_episodes": labelled,
        "episodes_with_no_records": empty_episode,
        "episodes_empty_spine": len(empty_all),
        "empty_spine_episodes": empty_all,
        "sourcetypes_measured": len(rows),
        "sourcetypes_at_0": sum(1 for row in rows if row["records"] and row["rate"] == 0.0),
        "sourcetypes": rows,
        "train_split": {
            "seed": seed,
            "type_fraction": type_fraction,
            "train_episodes": train_episodes,
            "empty_spine": len(train_empty),
            "anchors_stored": len(train_lengths),
            "techniques_covered": len(train_techniques),
            "technique_ids": sorted(train_techniques),
            "spine_shape": _spine_shape(train_lengths, train_distinct),
            "empty_spine_episodes": train_empty,
        },
    }


def _print_content_summary(report: dict) -> None:
    train = report["train_split"]
    shape = train["spine_shape"]
    print(
        f"labelled_episodes {report['labelled_episodes']}  "
        f"sourcetypes {report['sourcetypes_measured']}  "
        f"at_0 {report['sourcetypes_at_0']}  "
        f"empty_spine {report['episodes_empty_spine']}"
    )
    print(
        f"train_episodes {train['train_episodes']}  "
        f"empty_spine {train['empty_spine']}  "
        f"anchors {train['anchors_stored']}  "
        f"techniques {train['techniques_covered']}  "
        f"shape empty/single/multi/median "
        f"{shape['empty']}/{shape['single_class']}/{shape['multi_class']}/{shape['median_length']}"
    )
    print(f"{'rate':>8} {'records':>10} {'episodes':>8}  sourcetype  classes")
    for row in report["sourcetypes"]:
        print(
            f"{row['rate']:8.1%} {row['records']:10} {row['episodes']:8}  "
            f"{row['sourcetype']}  {row['class_distribution']}"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="Portal wiki spine census")
    ap.add_argument("--json", action="store_true", help="machine-readable totals")
    ap.add_argument("--surfaces", action="store_true", help="emit the proposed surface manifest")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--content-root", type=Path, help="labelled attack_data datasets root")
    ap.add_argument("--output", type=Path, help="write the content census JSON here")
    ap.add_argument("--seed", type=int, default=0, help="train/eval split seed (loader default 0)")
    ap.add_argument("--type-fraction", type=float, default=0.5)
    args = ap.parse_args()

    if args.content_root is not None:
        if args.output is None:
            print("[spine] --output is required with --content-root", file=sys.stderr)
            return 2
        if not args.content_root.is_dir():
            print(f"[spine] --content-root {args.content_root} is not a directory", file=sys.stderr)
            return 2
        report = content_census(args.content_root, seed=args.seed, type_fraction=args.type_fraction)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        _print_content_summary(report)
        print(f"[spine] wrote {args.output}")
        return 0

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
