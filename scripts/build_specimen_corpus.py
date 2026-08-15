#!/usr/bin/env python3
"""Build the frozen three-lane SPECIMEN_CORPUS_V1 without exposing truth."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from portal.modules.security.core.bully import config  # noqa: E402
from portal.modules.security.core.bully.contracts import MutationOperatorSpec  # noqa: E402
from portal.modules.security.core.bully.cousin_calibration_bench import (  # noqa: E402
    FROZEN_SWEEP,
    construction_distance,
)
from portal.modules.security.core.bully.cousin_forge import forge  # noqa: E402
from portal.modules.security.core.bully.specimen_ledger import (  # noqa: E402
    SpecimenLedger,
    SpecimenRecord,
)
from portal.modules.security.core.siem import capture_store  # noqa: E402
from portal.modules.security.core.telemetry import (  # noqa: E402
    IMPORTED_OBSERVED,
    IMPORTED_OBSERVED_TRUST_TIER,
    LIVE_SENSOR_TRUST_TIER,
)
from scripts import corpus_ingest  # noqa: E402

SPECIMEN_CORPUS_V1 = "SPECIMEN_CORPUS_V1"
_EVENT_CODE = re.compile(r"(?:EventCode|EventID)\s*[=:]\s*([A-Za-z0-9_.-]+)")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _event_name(event: dict | str, index: int) -> str:
    if isinstance(event, dict):
        value = event.get("EventCode") or event.get("EventID") or event.get("type")
        return f"event-{index}:{value or 'record'}"
    match = _EVENT_CODE.search(str(event))
    return f"event-{index}:{match.group(1) if match else 'record'}"


def _telemetry_view(telemetry: dict[str, list[dict | str]]) -> dict[str, Any]:
    events = [
        (sourcetype, event) for sourcetype in sorted(telemetry) for event in telemetry[sourcetype]
    ]
    actions = [_event_name(event, index) for index, (_, event) in enumerate(events)]
    field_names = sorted(
        {
            str(key)
            for _, event in events
            if isinstance(event, dict)
            for key in event
            if not str(key).lower().startswith(("technique", "mitre", "parent"))
        }
    )
    return {
        "action_sequence": actions,
        "event_graph": {"ordered": actions},
        "parameter_families": {"event_volume_band": min(len(events), 10)},
        "context_topology": {"source_classes": sorted(telemetry)},
        "artifacts": {"observed_fields": field_names[:24]},
        "attack_mappings": [],
        "telemetry_shape": {
            "sourcetypes": sorted(telemetry),
            "event_count": len(events),
        },
        "detector_outcomes": {},
    }


def _read_parent(dataset: corpus_ingest.ManifestDataset, *, event_limit: int) -> dict[str, Any]:
    events: list[dict | str] = []
    for line in corpus_ingest.iter_events_text(dataset.path):
        event = corpus_ingest.coerce(line)
        if dataset.mapped_sourcetype.startswith("windows:") and isinstance(event, dict):
            event = corpus_ingest.windows_kv(event) or event
        events.append(event)
        if len(events) >= event_limit:
            break
    telemetry = {dataset.mapped_sourcetype: events}
    content_hash = hashlib.sha256(dataset.path.read_bytes()).hexdigest()
    specimen_id = f"specimen-parent-{content_hash[:20]}"
    return {
        "specimen_id": specimen_id,
        "target_host": "corpus-attack-data",
        "created_at": dataset.dataset_epoch or 0.0,
        "data_yml_techniques": list(dataset.techniques),
        "telemetry": telemetry,
        "telemetry_view": _telemetry_view(telemetry),
        "source_path": str(dataset.path),
    }


def _capture_payload(
    specimen_id: str,
    telemetry: dict[str, list[Any]],
    *,
    origin: str,
    provenance: str,
    target_host: str,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "scenario": "external-observed-specimen",
        "target_host": target_host,
        "episode_id": specimen_id,
        "telemetry": telemetry,
        "telemetry_origins": dict.fromkeys(telemetry, origin),
        "telemetry_provenance": dict.fromkeys(telemetry, provenance),
        "validity": {"checked": True, "valid": True, "coverage": 1.0},
    }


def _write_and_replay(
    evidence_dir: Path,
    specimen_id: str,
    payload: dict[str, Any],
    *,
    ship: bool,
) -> Path:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / f"{specimen_id}.json"
    path.write_text(_canonical(payload), encoding="utf-8")
    receipt = capture_store.replay_capture(path, dry_run=not ship)
    if not receipt.get("ok"):
        raise RuntimeError(f"specimen replay failed for {specimen_id}: {receipt}")
    return path


def _forge_operators(parent: dict[str, Any], names: tuple[str, ...]):
    actions = list(parent["telemetry_view"]["action_sequence"])
    params = {
        "REORDER_STEPS": {"order": list(reversed(actions))},
        "VARY_PARAMETER": {"placeholder": "target", "value": "alias.local"},
        "INJECT_EVASION_DIRECTIVE": {"directive_text": "vary observable representation"},
        "SUBSTITUTE_TECHNIQUE": {
            "from": actions[0] if actions else "",
            "to": f"variant-{actions[0]}" if actions else "",
        },
        "OFF_SCRIPT_SUPPLY": {"technique_ids": ["T9999.001"]},
        "REVERSE_GEN_SEED": {"technique_id": "T9999.002"},
    }
    return tuple(MutationOperatorSpec(name, params[name]) for name in names)


def _entry(
    specimen_id: str,
    source_lane: str,
    engine_view: dict[str, Any],
    evidence_path: Path,
) -> dict[str, Any]:
    return {
        "specimen_id": specimen_id,
        "source_lane": source_lane,
        "engine_view": engine_view,
        "evidence_ref": evidence_path.name,
    }


def _live_lab_entry(
    path: Path,
    *,
    ledger: SpecimenLedger,
    evidence_dir: Path,
    ship: bool,
) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    issues = capture_store.capture_replay_issues(data)
    if issues:
        raise ValueError(f"live-lab specimen is not ground-truth-complete: {issues}")
    parent_id = str(data.get("specimen_parent_id") or "")
    if not parent_id:
        raise ValueError("live-lab specimen requires sealed scorer-side specimen_parent_id")
    operators = tuple(
        MutationOperatorSpec.from_dict(item) for item in data.get("mutation_operators") or []
    )
    if not operators:
        raise ValueError("live-lab cousin requires mutation_operators")
    specimen_id = str(data["episode_id"])
    telemetry = data["telemetry"]
    evidence_path = _write_and_replay(
        evidence_dir,
        specimen_id,
        _capture_payload(
            specimen_id,
            telemetry,
            origin="observed_target_log",
            provenance="live_lab",
            target_host=str(data.get("target_host") or "authorized-lab"),
        ),
        ship=ship,
    )
    distance = construction_distance(operators, moved_features={"telemetry_shape"})
    ledger.record(
        SpecimenRecord(
            specimen_id=specimen_id,
            parent_id=parent_id,
            source_lane="live_lab",
            transform_ops=tuple(asdict(operator) for operator in operators),
            construction_distance=distance,
            data_yml_techniques=tuple(data.get("data_yml_techniques") or ()),
            created_at=float(data.get("captured_at") or 0.0),
            provenance={
                "class": "live_sensor",
                "capture_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            },
        )
    )
    view = _telemetry_view(telemetry)
    return _entry(
        specimen_id,
        "live_lab",
        {
            "episode_view": {
                "episode_id": specimen_id,
                "target_host": data.get("target_host"),
                "trust_tier": LIVE_SENSOR_TRUST_TIER,
            },
            "telemetry_view": {**view, "trust_tier": LIVE_SENSOR_TRUST_TIER},
            "evidence_origin": "observed_target_log",
            "trust_tier": LIVE_SENSOR_TRUST_TIER,
            "provenance": "live_lab",
        },
        evidence_path,
    )


def build_corpus(
    *,
    attack_data_root: Path,
    output_dir: Path,
    ledger_root: Path,
    live_lab_captures: tuple[Path, ...] = (),
    event_limit: int = 32,
    max_parents: int = 0,
    ship: bool = False,
) -> dict[str, Any]:
    ledger = SpecimenLedger(ledger_root)
    evidence_dir = output_dir / "evidence"
    catalog = corpus_ingest.load_manifest_catalog(attack_data_root)
    eligible = [
        item
        for item in catalog
        if item.path.is_file()
        and item.techniques
        and item.mapped_sourcetype in corpus_ingest.INGESTED_SOURCETYPES
        and not corpus_ingest.is_lfs_pointer(item.path)
    ]
    admitted = list(eligible)
    if max_parents:
        admitted = admitted[:max_parents]

    entries: list[dict[str, Any]] = []
    for dataset in admitted:
        parent = _read_parent(dataset, event_limit=event_limit)
        if not any(parent["telemetry"].values()):
            continue
        specimen_id = parent["specimen_id"]
        parent_path = _write_and_replay(
            evidence_dir,
            specimen_id,
            _capture_payload(
                specimen_id,
                parent["telemetry"],
                origin=IMPORTED_OBSERVED,
                provenance="external_corpus",
                target_host=parent["target_host"],
            ),
            ship=ship,
        )
        ledger.record(
            SpecimenRecord(
                specimen_id=specimen_id,
                parent_id=None,
                source_lane="attack_data",
                construction_distance=0.0,
                data_yml_techniques=tuple(parent["data_yml_techniques"]),
                created_at=float(parent["created_at"]),
                provenance={
                    "class": "external_corpus",
                    "source_sha256": hashlib.sha256(dataset.path.read_bytes()).hexdigest(),
                    "mapped_sourcetype": dataset.mapped_sourcetype,
                },
            )
        )
        engine_view = {
            "episode_view": {
                "episode_id": specimen_id,
                "target_host": parent["target_host"],
                "trust_tier": IMPORTED_OBSERVED_TRUST_TIER,
            },
            "telemetry_view": {
                **parent["telemetry_view"],
                "trust_tier": IMPORTED_OBSERVED_TRUST_TIER,
            },
            "evidence_origin": IMPORTED_OBSERVED,
            "trust_tier": IMPORTED_OBSERVED_TRUST_TIER,
            "provenance": "external_corpus",
        }
        entries.append(_entry(specimen_id, "attack_data", engine_view, parent_path))
        for names in FROZEN_SWEEP:
            child = forge(
                parent,
                _forge_operators(parent, names),
                ledger=ledger,
                evidence_dir=evidence_dir,
                dry_run=not ship,
            )
            entries.append(
                _entry(
                    child.specimen_id,
                    "replay_mutation",
                    child.engine_view,
                    Path(child.capture_path),
                )
            )

    for capture in sorted(live_lab_captures):
        entries.append(
            _live_lab_entry(capture, ledger=ledger, evidence_dir=evidence_dir, ship=ship)
        )
    entries.sort(key=lambda item: (item["source_lane"], item["specimen_id"]))
    snapshot_hash = hashlib.sha256(_canonical(entries).encode()).hexdigest()
    per_lane = {
        lane: sum(entry["source_lane"] == lane for entry in entries)
        for lane in ("attack_data", "replay_mutation", "live_lab")
    }
    excluded = []
    for item in catalog:
        if item in admitted:
            continue
        relative = str(item.path.relative_to(attack_data_root))
        if item in eligible:
            reason = "parent_limit"
        elif not item.techniques:
            reason = "no_technique_truth"
        elif item.mapped_sourcetype not in corpus_ingest.INGESTED_SOURCETYPES:
            reason = "no_ingested_sourcetype_technique_coverage"
        elif not item.path.is_file():
            reason = "missing_data_file"
        else:
            reason = "lfs_pointer"
        excluded.append(
            {
                "dataset_ref": hashlib.sha256(relative.encode()).hexdigest()[:16],
                "mapped_sourcetype": item.mapped_sourcetype,
                "reason": reason,
            }
        )
    corpus = {
        "schema": SPECIMEN_CORPUS_V1,
        "snapshot_hash": snapshot_hash,
        "ledger_snapshot_hash": ledger.snapshot_hash(),
        "per_lane_counts": per_lane,
        "complete": all(per_lane.values()),
        "coverage_report": {
            "catalog_datasets": len(catalog),
            "admitted_parents": per_lane["attack_data"],
            "excluded": excluded,
        },
        "specimens": entries,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "specimen_corpus_v1.json").write_text(
        json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return corpus


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attack-data-root", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--ledger-root", type=Path)
    parser.add_argument("--lab-capture", action="append", default=[], type=Path)
    parser.add_argument("--event-limit", type=int, default=32)
    parser.add_argument("--max-parents", type=int, default=0)
    parser.add_argument("--ship", action="store_true")
    args = parser.parse_args(argv)
    output_dir = args.output_dir or config.hunt_dir() / "artifacts" / "specimen_corpus_v1"
    ledger_root = args.ledger_root or config.hunt_dir() / "specimens"
    corpus = build_corpus(
        attack_data_root=args.attack_data_root,
        output_dir=output_dir,
        ledger_root=ledger_root,
        live_lab_captures=tuple(args.lab_capture),
        event_limit=args.event_limit,
        max_parents=args.max_parents,
        ship=args.ship,
    )
    print(
        json.dumps(
            {
                key: corpus[key]
                for key in ("schema", "snapshot_hash", "per_lane_counts", "complete")
            },
            indent=2,
        )
    )
    return 0 if corpus["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
