"""One normalising lookup for model names that cross the config/Ollama boundary."""

from __future__ import annotations

from collections.abc import Mapping


def model_key(name: str) -> str:
    """Ollama's tag identity: tags that differ only by case are one model."""
    return name.strip().lower()


def lookup_model(mapping: Mapping[str, int], model: str) -> int | None:
    """The value stored for ``model``, matching keys with Ollama's case-insensitive tags."""
    if model in mapping:
        return mapping[model]
    key = model_key(model)
    for name, value in mapping.items():
        if model_key(name) == key:
            return value
    return None
