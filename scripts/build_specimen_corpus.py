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
from typing import Any, Protocol

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

# ruff: noqa: E402

from portal.modules.security.core.bully import config
from portal.modules.security.core.bully.contracts import MutationOperatorSpec
from portal.modules.security.core.bully.cousin_calibration_bench import (
    FROZEN_SWEEP,
    construction_distance,
)
from portal.modules.security.core.bully.cousin_forge import forge
from portal.modules.security.core.bully.specimen_ledger import (
    SpecimenLedger,
    SpecimenRecord,
)
from portal.modules.security.core.recall_attribution import (
    evidence_presence,
    technique_discriminators,
)
from portal.modules.security.core.siem import capture_store
from portal.modules.security.core.siem.spl_backend import SplunkBackend
from portal.modules.security.core.siem.spl_detections import spl_for
from portal.modules.security.core.telemetry import (
    IMPORTED_OBSERVED,
    IMPORTED_OBSERVED_TRUST_TIER,
    LIVE_SENSOR_TRUST_TIER,
)
from scripts import corpus_ingest

SPECIMEN_CORPUS_V1 = "SPECIMEN_CORPUS_V1"
SPECIMEN_CORPUS_V2 = "SPECIMEN_CORPUS_V2"
DETECTOR_OUTCOME_POLICY_V1 = "DETECTOR_OUTCOME_POLICY_V1"
_EVENT_CODE = re.compile(r"(?:EventCode|EventID)\s*[=:]\s*([A-Za-z0-9_.-]+)")
_OBSERVED_FIELD = re.compile(r"(?:Name=['\"]|\b)([A-Za-z][A-Za-z0-9_.-]+)(?:['\"]|)\s*[=>]")


class EpisodeDetectionBackend(Protocol):
    def query_episode(
        self,
        window: dict[str, str],
        *,
        episode_id: str,
        host: str | None = None,
        limit: int = 500,
    ) -> dict[str, Any]: ...

    def query_freeform(
        self,
        spl: str,
        window: dict[str, str],
        *,
        episode_id: str,
        host: str | None = None,
    ) -> dict[str, Any]: ...


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _event_actions(event: dict | str, index: int) -> list[str]:
    if isinstance(event, dict):
        value = event.get("EventCode") or event.get("EventID") or event.get("type")
        fields = [str(key) for key in event if not str(key).startswith("@")]
        return [f"event-{index}:{value or 'record'}", *(f"field:{key}" for key in fields[:4])]
    match = _EVENT_CODE.search(str(event))
    fields = list(dict.fromkeys(_OBSERVED_FIELD.findall(str(event))))
    return [
        f"event-{index}:{match.group(1) if match else 'record'}",
        *(f"field:{key}" for key in fields[:4]),
    ]


def _telemetry_view(telemetry: dict[str, list[dict | str]]) -> dict[str, Any]:
    events = [
        (sourcetype, event) for sourcetype in sorted(telemetry) for event in telemetry[sourcetype]
    ]
    actions = [
        action for index, (_, event) in enumerate(events) for action in _event_actions(event, index)
    ]
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
        if dataset.mapped_sourcetype.startswith("windows:"):
            event = (
                corpus_ingest.windows_kv(event)
                if isinstance(event, dict)
                else corpus_ingest.windows_xml_kv(str(event)) or event
            )
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
    discriminator_tokens = sorted(
        {
            token
            for technique_id in parent["data_yml_techniques"]
            for token in technique_discriminators(technique_id)["tokens"]
        }
    )
    params = {
        "REORDER_STEPS": {"order": list(reversed(actions))},
        "VARY_PARAMETER": {"placeholder": "target", "value": "alias.local"},
        "INJECT_EVASION_DIRECTIVE": {
            "directive_text": "vary observable representation",
            "discriminator_tokens": discriminator_tokens,
        },
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


def _opaque_detector_id(detector_id: str) -> str:
    digest = hashlib.sha256(f"bully-specimen-detector:{detector_id}".encode()).hexdigest()
    return f"detector-{digest[:16]}"


def _normalized_outcome(value: Any) -> str | None:
    if isinstance(value, dict):
        if value.get("fired") is True:
            return "fired"
        if value.get("partial") is True:
            return "partial"
        value = value.get("status") or value.get("outcome")
    if value is True:
        return "fired"
    if value is False:
        return "missed"
    normalized = str(value or "").strip().lower().replace("-", "_")
    return {
        "covered": "fired",
        "fired": "fired",
        "true_positive": "fired",
        "near_miss": "partial",
        "partial": "partial",
        "missed": "missed",
        "not_fired": "missed",
        "false_negative": "missed",
    }.get(normalized)


def _reported_detector_outcomes(query: dict[str, Any]) -> dict[str, str]:
    """Read only explicit detector results carried by the live query response."""
    reported: dict[str, str] = {}
    for detector_id, value in (query.get("detector_outcomes") or {}).items():
        status = _normalized_outcome(value)
        if status:
            reported[_opaque_detector_id(str(detector_id))] = status
    for row in query.get("rows") or ():
        fields = row.get("fields") or {}
        detector_id = fields.get("detection_id") or fields.get("detector_id")
        status = _normalized_outcome(
            fields.get("detection_status")
            or fields.get("detector_status")
            or fields.get("outcome")
            or fields.get("fired")
        )
        if detector_id and status:
            reported[_opaque_detector_id(str(detector_id))] = status
    return reported


def _episode_detection_outcomes(
    entry: dict[str, Any],
    truth: dict[str, Any],
    backend: EpisodeDetectionBackend,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Observe real episode-scoped detector results without exposing scorer truth."""
    episode_id = entry["specimen_id"]
    host = entry["engine_view"]["episode_view"].get("target_host")
    window = {"earliest": "-15m", "latest": "now"}
    episode_query = backend.query_episode(
        window,
        episode_id=episode_id,
        host=host,
        limit=500,
    )
    provenance = {
        "backend": episode_query.get("backend"),
        "source": episode_query.get("source"),
        "row_count": len(episode_query.get("rows") or ()),
        "query_error": episode_query.get("error"),
    }
    if episode_query.get("error"):
        return {}, provenance

    outcomes = _reported_detector_outcomes(episode_query)
    telemetry = str(episode_query.get("telemetry") or "")
    sourcetypes = (
        entry["engine_view"]["telemetry_view"].get("telemetry_shape", {}).get("sourcetypes", ())
    )
    source = str(sourcetypes[0]) if len(sourcetypes) == 1 else ""
    query_freeform = getattr(backend, "query_freeform", None)
    for technique_id in truth.get("data_yml_techniques") or ():
        detection_spl = spl_for(str(technique_id), source=source)
        if not detection_spl:
            continue
        detector_id = _opaque_detector_id(str(technique_id))
        if detector_id in outcomes:
            continue
        detection_query = (
            query_freeform(
                detection_spl,
                window,
                episode_id=episode_id,
                host=host,
            )
            if callable(query_freeform)
            else None
        )
        if detection_query and not detection_query.get("error"):
            if detection_query.get("rows"):
                outcomes[detector_id] = "fired"
                continue
            discriminator = technique_discriminators(str(technique_id))
            _presence, matched = evidence_presence(telemetry, discriminator["tokens"])
            outcomes[detector_id] = "partial" if matched else "missed"
            continue
        discriminator = technique_discriminators(str(technique_id))
        presence, matched = evidence_presence(telemetry, discriminator["tokens"])
        if presence == "PRESENT":
            outcomes[detector_id] = "fired"
        elif matched:
            outcomes[detector_id] = "partial"
        elif presence == "ABSENT":
            outcomes[detector_id] = "missed"
    return dict(sorted(outcomes.items())), provenance


def _populate_real_detector_outcomes(
    entries: list[dict[str, Any]],
    *,
    ledger: SpecimenLedger,
    backend: EpisodeDetectionBackend,
) -> dict[str, int]:
    counts = {"fired": 0, "partial": 0, "missed": 0, "indeterminate": 0}
    for entry in entries:
        truth = ledger.truth_for(entry["specimen_id"])
        if truth is None:
            raise ValueError(f"sealed truth missing for {entry['specimen_id']}")
        outcomes, provenance = _episode_detection_outcomes(entry, truth, backend)
        telemetry_view = entry["engine_view"]["telemetry_view"]
        telemetry_view["attack_mappings"] = []
        telemetry_view["detector_outcomes"] = outcomes
        entry["execution_mode"] = "live_indexed"
        entry["detector_observation"] = {
            "policy_version": DETECTOR_OUTCOME_POLICY_V1,
            **provenance,
        }
        response_status = "indeterminate"
        if "fired" in outcomes.values():
            response_status = "fired"
        elif "partial" in outcomes.values():
            response_status = "partial"
        elif outcomes:
            response_status = "missed"
        counts[response_status] += 1
    return counts


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


def _parent_entries(
    datasets: list[corpus_ingest.ManifestDataset],
    *,
    ledger: SpecimenLedger,
    evidence_dir: Path,
    event_limit: int,
    ship: bool,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for dataset in datasets:
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
        entries.extend(_forged_entries(parent, ledger=ledger, evidence_dir=evidence_dir, ship=ship))
    return entries


def _forged_entries(
    parent: dict[str, Any], *, ledger: SpecimenLedger, evidence_dir: Path, ship: bool
) -> list[dict[str, Any]]:
    entries = []
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
                child.specimen_id, "replay_mutation", child.engine_view, Path(child.capture_path)
            )
        )
    return entries


def _exclusions(
    catalog: list[corpus_ingest.ManifestDataset],
    admitted: list[corpus_ingest.ManifestDataset],
    eligible: list[corpus_ingest.ManifestDataset],
    attack_data_root: Path,
) -> list[dict[str, str]]:
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
    return excluded


_CENSUS_REASONS = (
    "admitted",
    "parent_limit",
    "no_technique_truth",
    "no_ingested_sourcetype_technique_coverage",
    "missing_data_file",
    "lfs_pointer",
)


def _admission_census(
    catalog: list[corpus_ingest.ManifestDataset],
    admitted: list[corpus_ingest.ManifestDataset],
    eligible: list[corpus_ingest.ManifestDataset],
    attack_data_root: Path,
    *,
    example_limit: int = 5,
) -> dict[str, Any]:
    """Persist a deterministic, reconcilable account of every catalog row."""
    admitted_set = set(admitted)
    eligible_set = set(eligible)
    buckets: dict[str, list[dict[str, str]]] = {reason: [] for reason in _CENSUS_REASONS}
    for item in catalog:
        relative = str(item.path.relative_to(attack_data_root))
        example = {
            "dataset_ref": hashlib.sha256(relative.encode()).hexdigest()[:16],
            "mapped_sourcetype": item.mapped_sourcetype,
        }
        if item in admitted_set:
            reason = "admitted"
        elif item in eligible_set:
            reason = "parent_limit"
        elif not item.techniques:
            reason = "no_technique_truth"
        elif item.mapped_sourcetype not in corpus_ingest.INGESTED_SOURCETYPES:
            reason = "no_ingested_sourcetype_technique_coverage"
        elif not item.path.is_file():
            reason = "missing_data_file"
        else:
            reason = "lfs_pointer"
        buckets[reason].append(example)

    counts = {reason: len(buckets[reason]) for reason in _CENSUS_REASONS}
    return {
        "catalog_size": len(catalog),
        "counts": counts,
        "examples": {reason: buckets[reason][:example_limit] for reason in _CENSUS_REASONS},
        "reconciled": sum(counts.values()) == len(catalog),
    }


def build_corpus(
    *,
    attack_data_root: Path,
    output_dir: Path,
    ledger_root: Path,
    live_lab_captures: tuple[Path, ...] = (),
    event_limit: int = 32,
    max_parents: int = 0,
    ship: bool = False,
    corpus_schema: str = SPECIMEN_CORPUS_V1,
    detector_backend: EpisodeDetectionBackend | None = None,
) -> dict[str, Any]:
    if max_parents < 0:
        raise ValueError("max_parents must be zero (unlimited) or positive")
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

    entries = _parent_entries(
        admitted,
        ledger=ledger,
        evidence_dir=evidence_dir,
        event_limit=event_limit,
        ship=ship,
    )

    for capture in sorted(live_lab_captures):
        entries.append(
            _live_lab_entry(capture, ledger=ledger, evidence_dir=evidence_dir, ship=ship)
        )
    entries.sort(key=lambda item: (item["source_lane"], item["specimen_id"]))
    response_observation_counts = None
    if corpus_schema == SPECIMEN_CORPUS_V2:
        if detector_backend is None:
            raise ValueError("SPECIMEN_CORPUS_V2 requires a live detector backend")
        response_observation_counts = _populate_real_detector_outcomes(
            entries,
            ledger=ledger,
            backend=detector_backend,
        )
    elif corpus_schema != SPECIMEN_CORPUS_V1:
        raise ValueError(f"unsupported specimen corpus schema: {corpus_schema}")
    snapshot_hash = hashlib.sha256(_canonical(entries).encode()).hexdigest()
    per_lane = {
        lane: sum(entry["source_lane"] == lane for entry in entries)
        for lane in ("attack_data", "replay_mutation", "live_lab")
    }
    corpus = {
        "schema": corpus_schema,
        "snapshot_hash": snapshot_hash,
        "ledger_snapshot_hash": ledger.snapshot_hash(),
        "per_lane_counts": per_lane,
        "complete": all(per_lane.values()),
        "coverage_report": {
            "catalog_datasets": len(catalog),
            "admitted_parents": per_lane["attack_data"],
            "excluded": _exclusions(catalog, admitted, eligible, attack_data_root),
        },
        "admission_census": _admission_census(catalog, admitted, eligible, attack_data_root),
        "specimens": entries,
    }
    if corpus_schema == SPECIMEN_CORPUS_V2:
        corpus.update(
            {
                "execution_mode": "live_indexed",
                "detector_outcome_policy_version": DETECTOR_OUTCOME_POLICY_V1,
                "response_observation_counts": response_observation_counts,
            }
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = (
        "specimen_corpus_v2.json"
        if corpus_schema == SPECIMEN_CORPUS_V2
        else "specimen_corpus_v1.json"
    )
    (output_dir / filename).write_text(
        json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return corpus


def build_corpus_v2(
    *,
    attack_data_root: Path,
    output_dir: Path,
    ledger_root: Path,
    live_lab_captures: tuple[Path, ...] = (),
    event_limit: int = 32,
    max_parents: int = 0,
    ship: bool = True,
    detector_backend: EpisodeDetectionBackend | None = None,
) -> dict[str, Any]:
    """Build the response-axis-live, immutable V2 reference corpus."""
    if not ship and detector_backend is None:
        raise ValueError("V2 requires --ship or an injected real-query fixture")
    return build_corpus(
        attack_data_root=attack_data_root,
        output_dir=output_dir,
        ledger_root=ledger_root,
        live_lab_captures=live_lab_captures,
        event_limit=event_limit,
        max_parents=max_parents,
        ship=ship,
        corpus_schema=SPECIMEN_CORPUS_V2,
        detector_backend=detector_backend or SplunkBackend(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attack-data-root", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--ledger-root", type=Path)
    parser.add_argument("--lab-capture", action="append", default=[], type=Path)
    parser.add_argument("--event-limit", type=int, default=32)
    parser.add_argument("--max-parents", type=int, default=0)
    parser.add_argument("--ship", action="store_true")
    parser.add_argument(
        "--schema-version",
        choices=("1", "2"),
        default="2",
        help="artifact version to build (default: response-axis-live V2)",
    )
    args = parser.parse_args(argv)
    default_corpus_dir = f"specimen_corpus_v{args.schema_version}"
    output_dir = args.output_dir or config.hunt_dir() / "artifacts" / default_corpus_dir
    ledger_root = args.ledger_root or config.hunt_dir() / "specimens"
    build = build_corpus_v2 if args.schema_version == "2" else build_corpus
    corpus = build(
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
