"""review.reference -- durable fitted state, with embedder-bound recalibration."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .calibration import CalibrationInsufficient, CalibrationSet
from .funnel import CHANNEL_SIMILAR, FunnelPolicy, calibrate, split_units
from .intake import IntakeResult, IntakeUnit
from .knowledge import AnchorIndex, Embedder, embed_texts
from .pipeline import Reference

SCHEMA = "review-reference-v1"


def _review_root(review_dir: Path | None = None) -> Path:
    if review_dir is not None:
        return review_dir.expanduser()
    configured = os.environ.get("PORTAL5_REVIEW_DIR")
    return Path(configured).expanduser() if configured else Path.home() / "AI_Output" / "review"


def reference_path(name: str = "default", *, review_dir: Path | None = None) -> Path:
    if not name or Path(name).name != name or name in {".", ".."}:
        raise ValueError("reference name must be a simple filename stem")
    return _review_root(review_dir) / "reference" / f"{name}.json"


def to_dict(reference: Reference) -> dict[str, Any]:
    from .funnel import baseline_to_dict

    return {
        "schema": SCHEMA,
        "baseline": baseline_to_dict(reference.baseline),
        "calibrations": json.loads(reference.calibrations.to_json()),
        "basis": reference.basis,
        "degraded": list(reference.degraded),
    }


def from_dict(payload: dict[str, Any]) -> Reference:
    from .funnel import baseline_from_dict

    if payload.get("schema") != SCHEMA:
        raise ValueError(f"unknown reference schema {payload.get('schema')!r}")
    baseline = payload.get("baseline")
    calibrations = payload.get("calibrations")
    if not isinstance(baseline, dict) or not isinstance(calibrations, dict):
        raise ValueError("reference is missing its baseline or calibration set")
    return Reference(
        baseline=baseline_from_dict(baseline),
        calibrations=CalibrationSet.from_json(json.dumps(calibrations)),
        basis=str(payload.get("basis") or ""),
        degraded=[str(value) for value in payload.get("degraded") or []],
    )


def save_reference(
    reference: Reference,
    *,
    name: str = "default",
    review_dir: Path | None = None,
) -> Path:
    path = reference_path(name, review_dir=review_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(to_dict(reference), sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)
    return path


def load_reference(*, name: str = "default", review_dir: Path | None = None) -> Reference:
    path = reference_path(name, review_dir=review_dir)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("reference document must be a JSON object")
    return from_dict(payload)


def stale(reference: Reference, embedder_id: str) -> list[str]:
    """Calibration keys fitted under another embedder identity."""
    return reference.calibrations.stale_for(embedder_id)


def recalibrate(
    reference: Reference,
    *,
    benign: IntakeResult,
    policy: FunnelPolicy,
    index: AnchorIndex,
    embedder: Embedder,
    environment_id: str,
) -> Reference:
    """Rebuild only embedder-dependent nulls from the caller's recorded benign slice.

    The unusual-score calibrations and fitted baseline are copied without change. Similarity
    nulls are recomputed from the held-out half of the supplied recorded slice.
    """
    if not index.population:
        raise ValueError("cannot recalibrate similarity without a non-empty anchor index")
    if index.embedder_id != embedder.identity:
        raise ValueError("anchor index and embedder identities disagree")

    _fit_half, calibration_half = split_units(
        [unit.unit for unit in benign.units], salt=environment_id
    )
    selected_ids = {unit.unit_id for unit in calibration_half}
    replacement = CalibrationSet()
    for calibration in reference.calibrations.items.values():
        if calibration.channel != CHANNEL_SIMILAR:
            replacement.put(calibration)

    degraded = [item for item in reference.degraded if not item.startswith(f"{CHANNEL_SIMILAR}/")]
    for level in policy.levels:
        units: list[IntakeUnit] = [
            item
            for item in benign.units
            if item.unit.unit_id in selected_ids and item.unit.level == level
        ]
        if not units:
            degraded.append(f"{CHANNEL_SIMILAR}/{level}: no units in recorded calibration half")
            continue
        vectors = embed_texts(embedder, [item.card for item in units])
        excludes = [frozenset({item.unit.unit_id}) for item in units]
        hits = index.search(vectors, k=1, exclude=excludes)
        scores = [result[0][1] if result else -1.0 for result in hits]
        try:
            calibrate(
                CHANNEL_SIMILAR,
                level,
                scores,
                policy.alpha_similar,
                basis=reference.basis,
                embedder_id=embedder.identity,
                into=replacement,
            )
        except CalibrationInsufficient as exc:
            degraded.append(f"{CHANNEL_SIMILAR}/{level}: {exc}")
    return Reference(reference.baseline, replacement, reference.basis, degraded)
