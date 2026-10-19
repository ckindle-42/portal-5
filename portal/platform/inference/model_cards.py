"""Shared model-card lookup and sampling selection."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_EXPECTATIONS_PATH = Path(__file__).resolve().parents[3] / "config" / "model_card_expectations.yaml"
_VERSION_DOT = re.compile(r"(?<=\d)\.(?=\d)")
_SAMPLING_KEYS = frozenset(
    {
        "temperature",
        "top_p",
        "top_k",
        "min_p",
        "repeat_penalty",
        "presence_penalty",
        "seed",
    }
)


def card_registry() -> dict:
    """Load the model-card expectations registry from the repository config."""
    if not _EXPECTATIONS_PATH.exists():
        return {}
    return (yaml.safe_load(_EXPECTATIONS_PATH.read_text()) or {}).get("models", {}) or {}


def _norm_key(value: str) -> str:
    return re.sub(r"[-_.\s]", "", value.lower())


def _key_in_tag(key: str, tag: str) -> bool:
    """Match card families without letting a version dot match another size."""
    if _VERSION_DOT.search(key):

        def bounded(value: str) -> str:
            value = re.sub(r"(?<=\d)[-_.\s](?=\d)", "~", _VERSION_DOT.sub("", value.lower()))
            return re.sub(r"[-_.\s]", "", value)

        return bounded(key) in bounded(tag)
    return _norm_key(key) in _norm_key(tag)


def card_entry(tag: str, registry: dict | None = None) -> tuple[str, dict] | None:
    """Return the longest matching model-card key and its entry."""
    registry = card_registry() if registry is None else registry
    best = None
    for key, entry in registry.items():
        normalized = _norm_key(key)
        if (
            normalized
            and _key_in_tag(key, tag)
            and (best is None or len(normalized) > len(_norm_key(best[0])))
        ):
            best = (key, entry or {})
    return best


def card_sampling(tag: str, think: bool | str | None, registry: dict | None = None) -> dict:
    """Return a card's recommended sampling for the requested thinking state."""
    hit = card_entry(tag, registry)
    if not hit:
        return {}
    entry = hit[1]
    chosen = entry.get("recommended_sampling") or {}
    modes = entry.get("recommended_sampling_modes") or {}
    think_off = think is False or (isinstance(think, str) and think.lower() == "false")
    prefixes = ("instruct", "non_thinking", "nothink") if think_off else ("thinking",)
    chosen = next(
        (
            values
            for mode, values in modes.items()
            if mode.lower().replace("-", "_").startswith(prefixes)
        ),
        chosen,
    )
    out = {}
    for key, value in (chosen or {}).items():
        key = "repeat_penalty" if key == "repetition_penalty" else key
        if key in _SAMPLING_KEYS and value is not None:
            out[key] = value
    return out
