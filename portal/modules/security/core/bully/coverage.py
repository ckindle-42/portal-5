"""Detection-library records as a queryable SA7 data-plane source."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .connectors import IterableIngestConnector, QueryIntent
from .data_plane import DataPlane, SourceProfile

_SOURCETYPE = re.compile(r'\bsourcetype\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)


def coverage_records(path: Path) -> list[dict[str, Any]]:
    """Read the detection library without converting it into telemetry."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    records = []
    for technique_id, entry in payload.items():
        if not isinstance(entry, dict):
            continue
        spl = str(entry.get("spl") or "")
        variants = entry.get("spl_variants") or ()
        sourcetypes = set(_SOURCETYPE.findall(spl))
        sourcetypes.update(
            str(variant["source"])
            for variant in variants
            if isinstance(variant, dict) and variant.get("source")
        )
        validation = entry.get("validation") or {}
        records.append(
            {
                "record_class": "coverage",
                "technique_id": str(technique_id),
                "description": str(entry.get("description") or ""),
                "sourcetypes": sorted(sourcetypes),
                "spl": spl,
                "expected_signal": str(entry.get("expected_signal") or ""),
                "validation_state": validation.get("status")
                or validation.get("known_positive")
                or "unrecorded",
                "validation": validation,
                "discriminator_tokens": list(
                    (entry.get("distinguishing_features") or {}).get("discriminator_tokens") or ()
                ),
            }
        )
    return records


def register_coverage_source(
    plane: DataPlane,
    *,
    path: Path,
    source_id: str = "detection-coverage",
) -> SourceProfile:
    records = coverage_records(path)
    connector = IterableIngestConnector(source_id, records, language="YAML-records")
    sample = connector.read(QueryIntent("read detection coverage", limit=len(records) or 1))
    return plane.connect(
        source_id,
        connector,
        sample.records,
        source_meta={
            "record_class": "coverage",
            "label_basis": True,
            "benign_present": True,
            "freshness_at": path.stat().st_mtime,
            "record_count_override": len(records),
        },
    )


def coverage_answer(
    plane: DataPlane,
    *,
    technique_id: str,
    source: str | None = None,
) -> dict[str, Any]:
    """Return coverage or a named blind-spot finding."""
    connector = plane.connectors.get("detection-coverage")
    if connector is None:
        return {
            "technique_id": technique_id,
            "covered": False,
            "finding": "coverage source unavailable",
        }
    result = connector.read(QueryIntent("answer detection coverage", limit=None))
    matches = [
        record
        for record in result.records
        if str(record.get("technique_id")) == technique_id
        and (source is None or source in (record.get("sourcetypes") or ()))
    ]
    if matches:
        return {"technique_id": technique_id, "source": source, "covered": True, "records": matches}
    return {
        "technique_id": technique_id,
        "source": source,
        "covered": False,
        "finding": "response-axis coverage blind spot",
    }
