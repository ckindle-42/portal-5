"""Receipt helpers shared by the notables stages: wall time, memory and JSON files."""

from __future__ import annotations

import json
import resource
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def peak_memory_mb() -> float:
    """Peak resident size of this process, in MiB (ru_maxrss is bytes on macOS, KiB elsewhere)."""
    raw = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    divisor = 1024.0 * 1024.0 if sys.platform == "darwin" else 1024.0
    return round(raw / divisor, 1)


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        stored = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return stored if isinstance(stored, dict) else {}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, sort_keys=False))


def progress_update(out: Path, stage: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Merge one stage's result into progress.json and return the merged receipt."""
    path = out / "progress.json"
    progress = read_json(path)
    stages = progress.get("stages")
    if not isinstance(stages, dict):
        stages = {}
    stages[stage] = payload
    merged = {**progress, "stages": stages, "stage": stage, "updated": utc_now()}
    merged["honesty"] = honesty_record(merged)
    merged["peak_memory_mb"] = peak_memory_mb()
    write_json(path, merged)
    return merged


def _notables_stage(progress: Mapping[str, Any]) -> Mapping[str, Any]:
    stages = progress.get("stages")
    notables = stages.get("notables") if isinstance(stages, Mapping) else None
    return notables if isinstance(notables, Mapping) else {}


def knowledge_facts(progress: Mapping[str, Any]) -> dict[str, Any]:
    """The knowledge facts the similar_to_known receipt records, or why it records none."""
    detail = _notables_stage(progress).get("similar_to_known")
    if not isinstance(detail, Mapping):
        return {"knowledge": "none loaded (similar_to_known did not run in this receipt)"}
    reliability = detail.get("reliability")
    return {
        "knowledge": "loaded",
        "families": [str(name) for name in detail.get("loaded_families") or ()],
        "excluded_family": detail.get("excluded_family"),
        "knowledge_items": detail.get("knowledge_items"),
        "embedding_model": detail.get("embedding_model"),
        "reliability_auc": reliability.get("auc") if isinstance(reliability, Mapping) else None,
        "index_unseen": bool(detail.get("index_unseen")),
        "run_index": str(detail.get("run_index") or ""),
    }


def honesty_record(progress: Mapping[str, Any]) -> dict[str, Any]:
    """What a run declares about its knowledge and its merge weights, for progress.json."""
    merge = _notables_stage(progress).get("merge")
    merge = merge if isinstance(merge, Mapping) else {}
    record = knowledge_facts(progress)
    record.pop("index_unseen", None)
    record.pop("run_index", None)
    record["merge_method"] = merge.get("method")
    record["weights_source"] = merge.get("weights_source")
    record["merge_weights"] = dict(merge.get("weights") or {})
    return record
