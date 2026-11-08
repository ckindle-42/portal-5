#!/usr/bin/env python3
"""Load attack_data episode corpus into the review service's anchor index.

Seeds the review store with one ``attack_episode`` anchor per labelled episode
(episode = the parent directory of a ``data.yml`` manifest). Enforces a
held-out half-split so eval episodes never contaminate the anchor library
(T.2, TASK_BULLY_REAL_TELEMETRY_V1). Reports shape achieved and label
provenance.

Usage::

    python3 scripts/load_attack_data_anchors.py --root /Volumes/data01/portal5_hunt/sources/attack_data/datasets --store /tmp/anchors.sqlite3 --dry-run
    python3 scripts/load_attack_data_anchors.py --root /Volumes/data01/portal5_hunt/sources/attack_data/datasets --store /tmp/anchors.sqlite3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from portal.modules.security.core.bully import telemetry_behavior
from portal.modules.security.core.bully.anchors import AnchorLibrary
from portal.modules.security.core.bully.unit_measurement import (
    HeldOutSplit,
    assert_no_contamination,
    split_datasets,
)
from portal.modules.security.core.review.contracts import TruthClass
from portal.modules.security.core.review.store import ReviewStore
from scripts.corpus_ingest import load_manifest_catalog

COMMIT_PROVENANCE = "4145e8b60fd8a3d44bc2170d1eb343fe7247387b"
LABEL_PROVENANCE = f"attack_data:data_yml::{COMMIT_PROVENANCE}"


def p5_item_id(publisher: str, test_id: str) -> str:
    """Stable short item id for a corpus file, from the reingest contract."""
    return hashlib.sha256(f"{publisher}|{test_id}".encode()).hexdigest()[:16]


def check_split_and_assert_no_contamination(
    evaluation_dataset_keys: list[str], split: HeldOutSplit
) -> None:
    """Thin wrapper around ``assert_no_contamination``; surface the guard as
    the loader's explicit split check so tests can patch/replace it without
    reaching into ``unit_measurement`` internals."""
    assert_no_contamination(evaluation_dataset_keys, split)


def _read_episode_records(episode_path: Path) -> list[dict[str, Any]]:
    """Read every data file in an episode directory, yielding one dict per
    record. Silently skips archives/files that fail to parse -- a malformed
    episode must not kill the whole load."""
    from scripts.corpus_ingest import iter_events_text

    records: list[dict[str, Any]] = []
    for path in sorted(episode_path.iterdir()):
        if not path.is_file():
            continue
        if path.name.lower().endswith((".yml", ".yaml")):
            continue
        try:
            for line in iter_events_text(path):
                if not line:
                    continue
                stripped = line.strip()
                if stripped.startswith("{"):
                    try:
                        records.append(json.loads(stripped))
                        continue
                    except (json.JSONDecodeError, TypeError):
                        pass
                records.append({"_raw": stripped})
        except Exception:  # noqa: BLE001 -- malformed file, never kill the run
            pass
    return records


def _episode_key(episode_path: Path, root: Path) -> str:
    """Deterministic key for an episode, used for splitting and idempotency.
    Relative to the attack_data root so the same episode always hashes the
    same way regardless of how the root itself is mounted."""
    relative = episode_path.relative_to(root)
    return f"attack_data:{relative.as_posix()}"


def _load_single_episode(
    ep_path: Path,
    manifest_items: list[Any],
    episode_techniques: tuple[str, ...],
    store: ReviewStore,
    library: AnchorLibrary,
    root: Path,
) -> tuple[int, set[str]]:
    """Load one episode into library + store. Returns (anchors_added, new_techniques)."""
    from portal.modules.security.core.bully import series_cousin as sc

    records = _read_episode_records(ep_path)
    if not records:
        return 0, set()

    data_file_key = manifest_items[0].path.relative_to(root).as_posix()

    anchor_id = f"an-{p5_item_id('attack_data', data_file_key)}"
    classified: list[dict[str, Any]] = []
    for rec in records:
        rec_copy = dict(rec) if isinstance(rec, dict) else {"_raw": str(rec)}
        cls = telemetry_behavior.classify_record(
            rec_copy, manifest_items[0].sourcetype or "corpus:raw"
        )
        rec_copy["_class"] = cls
        classified.append(rec_copy)

    payload = {
        "record_id": anchor_id,
        "source_id": "attack_data",
        "technique_ids": episode_techniques,
        "attack_mappings": [{"technique_id": t} for t in episode_techniques],
        "n_records": len(records),
        "file": data_file_key,
        "sourcetype": manifest_items[0].sourcetype,
        "dataset_epoch": manifest_items[0].dataset_epoch,
        "card": f"attack_data:{data_file_key} techniques={','.join(episode_techniques)}",
    }

    logs = classified

    def action_of(r: dict[str, Any]) -> Any:
        return r.get("_class", "")

    dominant_st = manifest_items[0].sourcetype or "corpus:raw"
    series = None
    if logs and action_of is not None:
        series = sc.series_from_logs(
            anchor_id,
            logs,
            action_of=action_of,
            sourcetype_of=lambda _r, _st=dominant_st: _st,
            technique=episode_techniques[0] if episode_techniques else None,
            source_ids=("attack_data",),
        )

    anchor = library.load_attack_episode(
        source_id="attack_data",
        record=payload,
        techniques=episode_techniques,
        label_basis="data_yml",
        logs=logs,
        action_of=action_of,
        behavior_classifier=None,
    )

    store.put_anchor(
        anchor_id=anchor.anchor_id,
        kind="attack_episode",
        malice="malicious",
        label=anchor.label_basis or "data_yml",
        record=asdict(anchor),
        derived_from="attack_data_manifest",
        truth_class=TruthClass.MACHINE_DERIVED,
    )
    return 1, set(episode_techniques)


def load_episodes(
    root: Path,
    store: ReviewStore,
    *,
    dataset_key_fn: Any = _episode_key,
    check_fn: Any = check_split_and_assert_no_contamination,
    split_seed: int = 0,
    type_fraction: float = 0.5,
) -> dict[str, Any]:
    """Load every labelled episode under ``root`` into ``store``, enforcing a
    held-out split. Returns a report with shape, techniques, skip reasons, and
    wall time.

    ``dataset_key_fn`` maps an episode Path -> a string key used for the
    split. ``check_fn`` is the contamination guard; swapping it lets tests
    verify failure behaviour without touching the real path.
    """
    started_at = time.time()

    catalog = load_manifest_catalog(root)

    # Group manifests by episode (parent directory). An episode may have
    # multiple data files (powershell + security + sysmon) -- the union of
    # their techniques is the episode's labelled technique set.
    episodes: dict[Path, list[Any]] = {}
    for item in catalog:
        ep = item.path.parent
        episodes.setdefault(ep, []).append(item)

    # Filter to episodes with at least one declared technique (labelled).
    labelled_episodes = {
        ep: items for ep, items in episodes.items() if any(item.techniques for item in items)
    }

    # Build deterministic keys and split.
    episode_keys = sorted(labelled_episodes.keys(), key=lambda p: str(p))
    ep_keys_list: list[str] = [dataset_key_fn(ep, root) for ep in episode_keys]
    split = split_datasets(ep_keys_list, type_fraction=type_fraction, seed=split_seed)

    # Guard: eval datasets must not also have contributed a type.
    check_fn(list(split.eval_dataset_keys), split)

    report: dict[str, Any] = {
        "schema": "ATTACK_DATA_LOADER_REPORT_V1",
        "label_provenance": LABEL_PROVENANCE,
        "commit": COMMIT_PROVENANCE,
        "label_basis": "data_yml",
        "total_episodes_observed": len(episodes),
        "labelled_episodes": len(labelled_episodes),
        "train_episodes": len(split.type_dataset_keys),
        "eval_episodes": len(split.eval_dataset_keys),
        "anchors_stored": 0,
        "techniques_covered": [],
        "episodes_skipped": [],
        "skipped_reasons": Counter(),
        "wall_time_s": 0.0,
        "store_health": {},
    }

    library = AnchorLibrary()
    technique_set: set[str] = set()

    for ep_path in episode_keys:
        ep_key = dataset_key_fn(ep_path, root)
        if ep_key not in split.type_dataset_keys:
            continue

        manifest_items = labelled_episodes[ep_path]
        episode_techniques = tuple(sorted({t for item in manifest_items for t in item.techniques}))
        if not episode_techniques:
            report["skipped_reasons"]["no_technique"] += 1
            report["episodes_skipped"].append(str(ep_path))
            continue

        # Load records from the episode's data files.
        records = _read_episode_records(ep_path)
        if not records:
            report["skipped_reasons"]["empty_episode"] += 1
            report["episodes_skipped"].append(str(ep_path))
            continue

        anchors_added, new_techs = _load_single_episode(
            ep_path, manifest_items, episode_techniques, store, library, root
        )
        report["anchors_stored"] += anchors_added
        technique_set.update(new_techs)

    report["techniques_covered"] = sorted(technique_set)
    report["wall_time_s"] = round(time.time() - started_at, 3)
    report["store_health"] = dict(store.health())
    return report


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--root", required=True, type=Path, help="attack_data datasets root")
    ap.add_argument(
        "--store",
        required=True,
        type=Path,
        help="path to the SQLite review store (must not be the live store)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="plan the load without writing to the store",
    )
    ap.add_argument(
        "--type-fraction",
        type=float,
        default=0.5,
        help="fraction of episodes to use as type-library (default 0.5)",
    )
    ap.add_argument(
        "--seed",
        type=int,
        default=0,
        help="split seed for reproducibility",
    )
    ap.add_argument(
        "--resume",
        type=Path,
        help="path to a previous report JSON: skip episodes already present",
    )
    args = ap.parse_args()

    if not args.root.is_dir():
        print(f"[FAIL] --root {args.root} is not a directory", file=sys.stderr)
        return 2

    args.store.parent.mkdir(parents=True, exist_ok=True)
    store = ReviewStore(path=args.store)

    if args.dry_run:
        report: dict[str, Any] = {
            "schema": "ATTACK_DATA_LOADER_REPORT_V1",
            "label_provenance": LABEL_PROVENANCE,
            "commit": COMMIT_PROVENANCE,
            "mode": "DRY-RUN",
            "anchors_stored": 0,
            "store_health": store.health(),
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        store.close()
        return 0

    report = load_episodes(
        args.root,
        store,
        split_seed=args.seed,
        type_fraction=args.type_fraction,
    )
    store.close()

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["anchors_stored"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
