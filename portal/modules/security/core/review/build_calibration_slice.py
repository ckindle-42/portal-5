"""Build and persist a held-out benign calibration slice from read-only Splunk windows."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from shutil import copy2
from typing import Any

from .intake import IntakeResult, build_window_units
from .pipeline import build_reference
from .service import disjoint_calibration_slice
from .window import SourceSpec, SplunkWindowSource, WindowSource

DEFAULT_SOURCES = (
    SourceSpec("portal5_lab", "linux:auditd"),
    SourceSpec("portal5_lab", "web:access"),
    SourceSpec("portal5_lab", "windows:security"),
)
MAX_WINDOW_EXPANSIONS = 8


class TargetUnitsUnavailableError(RuntimeError):
    """The bounded fetch did not produce the requested calibration-half size."""


def _default_output_dir() -> Path:
    configured = os.environ.get("PORTAL5_REVIEW_DIR")
    return Path(configured).expanduser() if configured else Path.home() / "AI_Output" / "review"


def _source_spec(value: str) -> SourceSpec:
    index, separator, sourcetype = value.partition(":")
    if not separator or not index or not sourcetype:
        raise ValueError(f"source must be INDEX:SOURCETYPE, got {value!r}")
    return SourceSpec(index, sourcetype)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="build-calibration-slice")
    parser.add_argument("--start", type=float, required=True, help="inclusive epoch time")
    parser.add_argument("--end", type=float, required=True, help="exclusive epoch time")
    parser.add_argument("--rule", required=True, help="operator-stated rule for this benign window")
    parser.add_argument("--sources", nargs="+", default=None, metavar="INDEX:SOURCETYPE")
    parser.add_argument(
        "--target-units",
        type=int,
        default=600,
        help="minimum calibration-half units; 600 gives p_step=1/601 and 120 steps at alpha=0.2",
    )
    parser.add_argument("--output-dir", default=None)
    return parser.parse_args(argv)


def _fetch_raw(
    source: WindowSource, sources: Sequence[SourceSpec], start: float, end: float
) -> dict[str, list[dict[str, Any]]]:
    batch = source.fetch(sources, start, end)
    return {source_id: list(rows) for source_id, rows in batch.records_by_source.items()}


def _merge_records(
    target: dict[str, list[dict[str, Any]]], page: dict[str, list[dict[str, Any]]]
) -> None:
    for source_id, records in page.items():
        target.setdefault(source_id, []).extend(records)


def _expand_window(
    source: WindowSource,
    sources: Sequence[SourceSpec],
    records: dict[str, list[dict[str, Any]]],
    start: float,
    end: float,
    page_width: float,
) -> tuple[float, float]:
    lower, upper = start, end
    left = max(0.0, lower - page_width)
    if left < lower:
        _merge_records(records, _fetch_raw(source, sources, left, lower))
        lower = left
    _merge_records(records, _fetch_raw(source, sources, upper, upper + page_width))
    return lower, upper + page_width


def _prepare_units(
    records: dict[str, list[dict[str, Any]]], excluded_event_ids: set[str] | frozenset[str]
) -> tuple[IntakeResult, int]:
    units = build_window_units(records)
    if not excluded_event_ids:
        return units, 0
    disjoint = disjoint_calibration_slice(units, excluded_event_ids)
    return disjoint, len(units.events) - len(disjoint.events)


def _calibration_half(units: IntakeResult, environment_id: str) -> list[Any]:
    from .funnel import split_units

    _, cal_half = split_units([item.unit for item in units.units], salt=environment_id)
    return cal_half


def _p_step(calibration_half_units: int) -> float:
    return 1.0 / (calibration_half_units + 1)


def _provenance(
    *,
    records: dict[str, list[dict[str, Any]]],
    units: IntakeResult,
    start: float,
    end: float,
    rule: str,
    environment_id: str,
    calibration_half_units: int,
    target_units: int,
    p_step: float,
    excluded_events: int,
    expansions: int,
) -> dict[str, Any]:
    return {
        "built_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),  # noqa: UP017
        "rule": rule,
        "window_start": start,
        "window_end": end,
        "records": sum(len(rows) for rows in records.values()),
        "units": len(units.units),
        "calibration_half_units": calibration_half_units,
        "target_units": target_units,
        "target_reached": True,
        "split_method": "salted_equi_split",
        "environment_id": environment_id,
        "p_step": p_step,
        "disjoint_excluded": excluded_events,
        "expansions": expansions,
        "sources": sorted(records),
    }


def _backup_existing(slice_path: Path) -> Path | None:
    if not slice_path.is_file():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")  # noqa: UP017
    backup = slice_path.with_name(f"calibration_slice.{stamp}.json")
    copy2(slice_path, backup)
    return backup


def _write_slice(
    output: Path, records: dict[str, list[dict[str, Any]]], provenance: dict[str, Any]
) -> tuple[Path, Path, Path | None]:
    slice_path = output / "calibration_slice.json"
    provenance_path = output / "calibration_slice_provenance.json"
    slice_tmp = slice_path.with_suffix(".json.tmp")
    provenance_tmp = provenance_path.with_suffix(".json.tmp")
    payload = {**records, "_provenance": provenance}
    slice_tmp.write_text(json.dumps(payload, sort_keys=True, default=str), encoding="utf-8")
    provenance_tmp.write_text(json.dumps(provenance, sort_keys=True, default=str), encoding="utf-8")
    backup = _backup_existing(slice_path)
    slice_tmp.replace(slice_path)
    provenance_tmp.replace(provenance_path)
    return slice_path, provenance_path, backup


def _fit_reference(units: IntakeResult, environment_id: str) -> None:
    from .funnel import FunnelPolicy

    policy = FunnelPolicy(alpha_unusual=0.2, alpha_similar=0.2, levels=("L2_ENTITY", "L3_CHAIN"))
    build_reference(
        units,
        policy=policy,
        index=None,
        embedder=None,
        environment_id=environment_id,
        basis="benign_slice",
    )


def build(
    *,
    start: float,
    end: float,
    rule: str,
    sources: Sequence[SourceSpec] | None = None,
    target_units: int = 600,
    output_dir: Path | None = None,
    splunk_source: WindowSource | None = None,
    excluded_event_ids: set[str] | frozenset[str] | None = None,
    environment_id: str = "portal5_lab",
) -> dict[str, Any]:
    if end <= start or target_units <= 0 or not rule.strip():
        raise ValueError("start, end, target_units, and rule must define a valid build")
    selected_sources = tuple(sources) if sources is not None else DEFAULT_SOURCES
    if not selected_sources:
        raise ValueError("at least one source is required")
    source = splunk_source or SplunkWindowSource()
    page_width = end - start
    records = _fetch_raw(source, selected_sources, start, end)
    lower, upper = start, end
    units, excluded_count = _prepare_units(records, excluded_event_ids or set())
    cal_half = _calibration_half(units, environment_id)
    expansions = 0
    while len(cal_half) < target_units and expansions < MAX_WINDOW_EXPANSIONS:
        lower, upper = _expand_window(source, selected_sources, records, lower, upper, page_width)
        expansions += 1
        units, excluded_count = _prepare_units(records, excluded_event_ids or set())
        cal_half = _calibration_half(units, environment_id)
    achieved = len(cal_half)
    p_step = _p_step(achieved)
    if achieved < target_units:
        raise TargetUnitsUnavailableError(
            f"target {target_units} unavailable: calibration half reached {achieved}, "
            f"short by {target_units - achieved}; p_step={p_step:.6f}; "
            f"expanded window={lower:.6f}:{upper:.6f} after {expansions} pages"
        )
    _fit_reference(units, environment_id)
    provenance = _provenance(
        records=records,
        units=units,
        start=lower,
        end=upper,
        rule=rule,
        environment_id=environment_id,
        calibration_half_units=achieved,
        target_units=target_units,
        p_step=p_step,
        excluded_events=excluded_count,
        expansions=expansions,
    )
    output = output_dir or _default_output_dir()
    output.mkdir(parents=True, exist_ok=True)
    slice_path, provenance_path, backup = _write_slice(output, records, provenance)
    return {
        "written_slice": str(slice_path),
        "written_provenance": str(provenance_path),
        "backup_slice": str(backup) if backup else None,
        "records": sum(len(rows) for rows in records.values()),
        "units": len(units.units),
        "calibration_half_units": achieved,
        "target_units": target_units,
        "target_reached": True,
        "p_step": p_step,
        "disjoint_excluded": excluded_count,
        "rule": rule,
        "sources": [source.source_id for source in selected_sources],
        "window": f"{lower:.6f}:{upper:.6f}",
        "expansions": expansions,
    }


def _redact_credentials(message: str) -> str:
    for key in ("LAB_SPLUNK_USER", "LAB_SPLUNK_PASSWORD", "SPLUNK_USER", "SPLUNK_PASSWORD"):
        secret = os.environ.get(key)
        if secret:
            message = message.replace(secret, "[redacted]")
    return re.sub(r"(https?://)[^/@\s]+@", r"\1[redacted]@", message)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = build(
            start=args.start,
            end=args.end,
            rule=args.rule,
            sources=[_source_spec(value) for value in args.sources] if args.sources else None,
            target_units=args.target_units,
            output_dir=Path(args.output_dir) if args.output_dir else None,
        )
    except Exception as exc:  # noqa: BLE001 -- the CLI must retain the real build diagnostic
        print(
            json.dumps({"error": f"{type(exc).__name__}: {_redact_credentials(str(exc))}"}),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0
