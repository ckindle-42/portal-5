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


def _invalidate_cache() -> None:
    """Invalidate the YAML cache (for testing after edits)."""
    global _cache
    _cache = None


def spl_for(technique_id: str, source: str = "") -> str | None:
    """Return the SPL search string for a technique, or None if not covered.

    Args:
        technique_id: MITRE ATT&CK technique ID
        source: optional telemetry source (e.g. "windows:security", "linux:auditd").
               If provided and the technique has spl_variants, returns the variant
               matching this source.  Falls back to the default spl field.
    """
    data = _load()
    entry = data.get(technique_id)
    if not entry or not isinstance(entry, dict):
        return None

    # Try variant selection if source is specified
    if source:
        variants = entry.get("spl_variants", [])
        for variant in variants:
            if variant.get("source") == source:
                return variant.get("spl", "")

    return entry.get("spl", "")


def spl_variants_for(technique_id: str) -> list[dict]:
    """Return all SPL variants for a technique.

    Returns list of {source, spl, expected_signal} dicts.
    Empty list if no variants defined.
    """
    data = _load()
    entry = data.get(technique_id)
    if not entry or not isinstance(entry, dict):
        return []
    return entry.get("spl_variants", [])


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
    result = {}
    for tid, entry in _load().items():
        if not entry:
            continue
        desc = entry.get("description", "")
        # M4: append distinguishing features for sub-technique precision
        diff = entry.get("distinguishing_features", {})
        if diff:
            sibling = diff.get("sibling_diff", "")
            key_ind = diff.get("key_indicator", "")
            if sibling:
                desc += f" [DISTINGUISH: {sibling}]"
            if key_ind:
                desc += f" [KEY: {key_ind}]"
        result[tid] = desc
    return result


def technique_signature_full(technique_id: str) -> dict:
    """Return full technique info including distinguishing features.

    Returns dict with: description, expected_signal, spl, distinguishing_features.
    Used by the harness grounding tools for sub-technique precision (M4).
    """
    data = _load()
    entry = data.get(technique_id)
    if not entry or not isinstance(entry, dict):
        return {}
    return {
        "description": entry.get("description", ""),
        "expected_signal": entry.get("expected_signal", ""),
        "spl": entry.get("spl", ""),
        "distinguishing_features": entry.get("distinguishing_features", {}),
    }
