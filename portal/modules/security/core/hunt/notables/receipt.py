"""Receipt helpers shared by the notables stages: wall time, memory and JSON files."""

from __future__ import annotations

import json
import resource
import sys
import time
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
    merged["peak_memory_mb"] = peak_memory_mb()
    write_json(path, merged)
    return merged
