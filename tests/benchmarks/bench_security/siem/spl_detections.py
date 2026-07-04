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


def technique_reference() -> dict[str, str]:
    """Return {technique_id: description} for every covered technique.

    Each description already names the evidence signature that identifies the
    technique (event IDs, log field patterns) — written for the SPL author,
    but never surfaced to the blue model doing the same classification job by
    hand. Found live 2026-07-04: sylink/sylink:8b and a tool-fixed
    CyberSecQwen-4B both received correct, live Kerberoasting/DCSync telemetry
    and still reported the wrong MITRE sub-technique ID — with zero mapping
    reference in their prompt, they were guessing from training knowledge
    alone instead of matching the exact evidence in front of them.
    """
    return {tid: entry.get("description", "") for tid, entry in _load().items() if entry}
