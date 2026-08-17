"""Build and serialize the SA7 census from the registered live sources."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .advisories import register_live_advisory_source
from .asset_identity import register_asset_identity_source
from .case_history import register_case_history_source
from .connectors import QueryIntent
from .coverage import register_coverage_source
from .data_plane import DataPlane
from .live_connect import connect_lab_splunk, register_staged_corpora
from .live_profiles import derive_live_profiles
from .planner_proof import planner_proof
from .store import Store


def _safe_census(value: Any, *, key: str = "") -> Any:
    if isinstance(value, dict):
        return {name: _safe_census(child, key=name) for name, child in value.items()}
    if isinstance(value, list):
        return [_safe_census(child, key=key) for child in value]
    if key in {"left_id", "right_id"} and value is not None:
        digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:16]
        return f"entity-redacted-{digest}"
    return value


def build_live_plane(
    *,
    corpora_root: Path,
    attack_data_root: Path,
    coverage_path: Path,
    store_path: Path,
    sample_limit: int = 32,
    corpus_counts: dict[str, int] | None = None,
    inventory_records: list[dict[str, Any]] | None = None,
) -> tuple[DataPlane, dict[str, Any]]:
    plane = DataPlane()
    connect_lab_splunk(plane, sample_limit=sample_limit, count_records=True)
    register_staged_corpora(
        plane,
        corpora_root=corpora_root,
        attack_data_root=attack_data_root,
        sample_limit=sample_limit,
        counts=corpus_counts,
    )
    if coverage_path.is_file():
        register_coverage_source(plane, path=coverage_path)
    if store_path.is_file():
        # The connector is intentionally query-in-place, so retain the
        # read-only Store handle until all live profiling is complete.
        store = Store(store_path)
        register_case_history_source(plane, store, sample_limit=sample_limit)
        plane._live_store = store
    indexed = plane.connectors.get("lab-splunk")
    if indexed is not None:
        register_asset_identity_source(
            plane,
            indexed,
            inventory_provider=(lambda: inventory_records or ())
            if inventory_records is not None
            else None,
            sample_limit=sample_limit,
        )
    register_live_advisory_source(plane, sample_limit=sample_limit)
    intents = {
        "lab-splunk": QueryIntent(
            "derive live telemetry profile",
            seed={"spl": "search index=portal5_lab sourcetype=aws:cloudtrail"},
            limit=sample_limit,
        ),
        "asset-identity-context": QueryIntent(
            "derive live entity profile",
            seed={"spl": "search index=portal5_lab sourcetype=aws:cloudtrail"},
            limit=sample_limit,
        ),
    }
    derive_live_profiles(plane, intents=intents, sample_limit=sample_limit)
    return plane, planner_proof(plane)


def write_live_census(
    path: Path,
    plane: DataPlane,
    planner: dict[str, Any],
    *,
    findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema": "BULLY_SA7_LIVE_CENSUS_V1",
        "generated_at": time.time(),
        "census": _safe_census(plane.census()),
        "planner_proof": planner,
        "findings": list(findings or []),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
