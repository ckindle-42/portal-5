"""Standalone scorer-side lane for measured, untagged telemetry cousins."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..siem import capture_store
from ..telemetry import IMPORTED_OBSERVED, IMPORTED_OBSERVED_TRUST_TIER
from . import config
from .contracts import MutationOperatorSpec
from .cousin_calibration_bench import construction_distance
from .specimen_ledger import SpecimenLedger, SpecimenRecord

SIGNATURE_FEATURES = (
    "action_sequence",
    "event_graph",
    "parameter_families",
    "context_topology",
    "artifacts",
    "attack_mappings",
    "telemetry_shape",
    "detector_outcomes",
)

ReplayFn = Callable[..., dict[str, Any]]


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _features(telemetry_view: dict[str, Any]) -> dict[str, Any]:
    return {name: copy.deepcopy(telemetry_view.get(name)) for name in SIGNATURE_FEATURES}


def signature_feature_delta(
    before: dict[str, Any], after: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Return only engine-observable feature changes."""
    delta: dict[str, dict[str, Any]] = {}
    for feature in SIGNATURE_FEATURES:
        old = before.get(feature)
        new = after.get(feature)
        if _canonical(old) != _canonical(new):
            delta[feature] = {"before": old, "after": new}
    return delta


def _replace(value: Any, source: str, target: str) -> Any:
    if isinstance(value, str):
        return value.replace(source, target)
    if isinstance(value, list):
        return [_replace(item, source, target) for item in value]
    if isinstance(value, dict):
        return {key: _replace(item, source, target) for key, item in value.items()}
    return value


def _apply_evasion(
    telemetry: dict[str, list[Any]], view: dict[str, Any], params: dict[str, Any]
) -> None:
    directive = str(params.get("directive_text") or "")
    if not directive:
        return
    shape = dict(view.get("telemetry_shape") or {})
    shape["representation"] = hashlib.sha256(directive.encode()).hexdigest()[:12]
    view["telemetry_shape"] = shape
    for token in params.get("discriminator_tokens") or ():
        replacement = f"representation-{hashlib.sha256(str(token).encode()).hexdigest()[:8]}"
        for sourcetype, events in telemetry.items():
            telemetry[sourcetype] = _replace(events, str(token), replacement)


def _reorder(telemetry: dict[str, list[Any]], view: dict[str, Any], params: dict) -> None:
    actions = list(view.get("action_sequence") or [])
    requested = params.get("order")
    reordered = (
        list(requested)
        if requested and sorted(requested) == sorted(actions)
        else list(reversed(actions))
    )
    view["action_sequence"] = reordered
    graph = dict(view.get("event_graph") or {})
    graph["ordered"] = reordered
    view["event_graph"] = graph
    for sourcetype, events in telemetry.items():
        telemetry[sourcetype] = list(reversed(events))


def _substitute(telemetry: dict[str, list[Any]], view: dict[str, Any], params: dict) -> None:
    source, target = str(params.get("from") or ""), str(params.get("to") or "")
    if not source or not target:
        return
    actions = list(view.get("action_sequence") or [])
    view["action_sequence"] = [target if item == source else item for item in actions]
    view["event_graph"] = _replace(view.get("event_graph") or {}, source, target)
    for sourcetype, events in telemetry.items():
        telemetry[sourcetype] = _replace(events, source, target)


def _vary_parameter(telemetry: dict[str, list[Any]], view: dict[str, Any], params: dict) -> None:
    placeholder = str(params.get("placeholder") or "")
    value = params.get("value")
    if not placeholder or value is None:
        return
    families = dict(view.get("parameter_families") or {})
    families[placeholder] = str(value)
    view["parameter_families"] = families
    for sourcetype, events in telemetry.items():
        telemetry[sourcetype] = _replace(events, placeholder, str(value))


def _off_script(_telemetry: dict[str, list[Any]], view: dict[str, Any], params: dict) -> None:
    additions = list(params.get("technique_ids") or [])
    if params.get("technique_id"):
        additions.append(str(params["technique_id"]))
    if additions:
        topology = dict(view.get("context_topology") or {})
        topology["off_script_observable_count"] = len(additions)
        view["context_topology"] = topology


_OPERATORS = {
    "REORDER_STEPS": _reorder,
    "SUBSTITUTE_TECHNIQUE": _substitute,
    "VARY_PARAMETER": _vary_parameter,
    "INJECT_EVASION_DIRECTIVE": _apply_evasion,
    "OFF_SCRIPT_SUPPLY": _off_script,
    "REVERSE_GEN_SEED": _off_script,
}


def _apply_operator(
    telemetry: dict[str, list[Any]], view: dict[str, Any], operator: MutationOperatorSpec
) -> None:
    apply = _OPERATORS.get(operator.operator)
    if apply is not None:
        apply(telemetry, view, operator.params)


def _clean_engine_view(specimen_id: str, parent: dict[str, Any], view: dict[str, Any]) -> dict:
    visible_features = _features(view)
    return {
        "episode_view": {
            "episode_id": specimen_id,
            "target_host": parent.get("target_host") or "external-observed",
            "trust_tier": IMPORTED_OBSERVED_TRUST_TIER,
        },
        "telemetry_view": {**visible_features, "trust_tier": IMPORTED_OBSERVED_TRUST_TIER},
        "evidence_origin": IMPORTED_OBSERVED,
        "trust_tier": IMPORTED_OBSERVED_TRUST_TIER,
        "provenance": "derived_variant",
    }


@dataclass(frozen=True)
class ForgedSpecimen:
    specimen_id: str
    engine_view: dict[str, Any]
    construction_distance: float
    differences: tuple[dict[str, Any], ...]
    capture_path: str
    replay_receipt: dict[str, Any]


def _mutate(parent: dict[str, Any], operators: tuple[MutationOperatorSpec, ...]):
    raw = copy.deepcopy(parent.get("telemetry") or {})
    view = _features(parent.get("telemetry_view") or parent)
    differences: list[dict[str, Any]] = []
    moved_ops: list[MutationOperatorSpec] = []
    for operator in operators:
        before = _features(view)
        _apply_operator(raw, view, operator)
        delta = signature_feature_delta(before, _features(view))
        if delta:
            moved_ops.append(operator)
            differences.append({"operator": operator.operator, "features": delta})
    moved_features = {feature for difference in differences for feature in difference["features"]}
    if not moved_features:
        raise ValueError("relabel-only, not a cousin")
    distance = construction_distance(tuple(moved_ops), moved_features=moved_features)
    return raw, view, differences, distance


def _write_capture(
    specimen_id: str,
    parent: dict[str, Any],
    telemetry: dict[str, list[Any]],
    evidence_dir: Path | None,
    replay_fn: ReplayFn,
    dry_run: bool,
) -> tuple[Path, dict[str, Any]]:
    target_dir = Path(evidence_dir or (config.hunt_dir() / "specimen_evidence"))
    target_dir.mkdir(parents=True, exist_ok=True)
    capture_path = target_dir / f"{specimen_id}.json"
    capture_payload = {
        "schema_version": 2,
        "scenario": "external-observed-specimen",
        "target_host": parent.get("target_host") or "external-observed",
        "episode_id": specimen_id,
        "telemetry": telemetry,
        "telemetry_origins": dict.fromkeys(telemetry, IMPORTED_OBSERVED),
        "telemetry_provenance": dict.fromkeys(telemetry, "derived_variant"),
        "validity": {"checked": True, "valid": True, "coverage": 1.0},
    }
    capture_path.write_text(json.dumps(capture_payload, sort_keys=True), encoding="utf-8")
    receipt = replay_fn(capture_path, dry_run=dry_run)
    if not receipt.get("ok"):
        raise RuntimeError(f"forged specimen replay failed: {receipt}")
    return capture_path, receipt


def forge(
    parent_telemetry: dict[str, Any],
    operators: tuple[MutationOperatorSpec, ...] | list[MutationOperatorSpec],
    *,
    ledger: SpecimenLedger | None = None,
    evidence_dir: Path | None = None,
    replay_fn: ReplayFn = capture_store.replay_capture,
    dry_run: bool = False,
) -> ForgedSpecimen:
    """Mutate observed telemetry, replay it without lineage tags, then seal truth."""
    parent_id = str(parent_telemetry.get("specimen_id") or parent_telemetry.get("parent_id") or "")
    if not parent_id:
        raise ValueError("parent telemetry requires a scorer-side specimen_id")
    typed_ops = tuple(operators)
    if not typed_ops:
        raise ValueError("relabel-only, not a cousin")

    raw, view, differences, distance = _mutate(parent_telemetry, typed_ops)
    digest = hashlib.sha256(
        _canonical(
            {
                "parent": parent_id,
                "operators": [asdict(operator) for operator in typed_ops],
                "features": _features(view),
            }
        ).encode()
    ).hexdigest()[:20]
    specimen_id = f"specimen-{digest}"
    engine_view = _clean_engine_view(specimen_id, parent_telemetry, view)

    capture_path, replay_receipt = _write_capture(
        specimen_id, parent_telemetry, raw, evidence_dir, replay_fn, dry_run
    )

    truth = SpecimenRecord(
        specimen_id=specimen_id,
        parent_id=parent_id,
        source_lane="replay_mutation",
        transform_ops=tuple(asdict(operator) for operator in typed_ops),
        construction_distance=distance,
        data_yml_techniques=tuple(parent_telemetry.get("data_yml_techniques") or ()),
        created_at=float(parent_telemetry.get("created_at", 0.0)),
        provenance={"class": "derived_variant", "differences": differences},
    )
    (ledger or SpecimenLedger()).record(truth)
    return ForgedSpecimen(
        specimen_id=specimen_id,
        engine_view=engine_view,
        construction_distance=distance,
        differences=tuple(differences),
        capture_path=str(capture_path),
        replay_receipt=replay_receipt,
    )
