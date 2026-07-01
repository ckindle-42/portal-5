"""SPL detection library — technique_id -> SPL search + expected-signal criteria.

Loaded by SplunkBackend.query().  Covers web, command-exec, webshell, container,
cloud-metadata, and AD techniques.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_YAML_PATH = Path(__file__).parent / "spl_detections.yaml"
_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is None:
        _cache = yaml.safe_load(_YAML_PATH.read_text()) or {} if _YAML_PATH.exists() else {}
    return _cache


def spl_for(technique_id: str) -> str | None:
    """Return the SPL search string for a technique, or None if not covered."""
    data = _load()
    entry = data.get(technique_id)
    if entry and isinstance(entry, dict):
        return entry.get("spl", "")
    return None


def techniques_covered() -> list[str]:
    """Return all technique IDs with SPL entries."""
    return list(_load().keys())
