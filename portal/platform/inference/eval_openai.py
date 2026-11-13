"""Eval-only OpenAI-compatible backends. Loaded beside production, never in its place.

Production routing stays on the ``ollama`` and ``omlx`` groups. Bench workspaces
listed in ``config/bench_engines.yaml`` are exclusive: a miss returns no
candidate instead of falling through to a production engine. Each candidate
engine has a fixed port backend so switching needs no environment change.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

EVAL_OPENAI = "eval_openai"
# oMLX and the eval engines take the same OpenAI seat body (sampling, thinking).
OPENAI_SEAT_TYPES = frozenset({"omlx", EVAL_OPENAI})

_TRUTHY = frozenset({"1", "true", "yes"})


def uses_openai_seat_injection(backend_type: str) -> bool:
    """True when the request body is the production MLX/OpenAI seat dialect."""
    return backend_type in OPENAI_SEAT_TYPES


def bench_engines_path(config_path: str) -> Path:
    """``config/bench_engines.yaml`` next to the backends file the registry loaded."""
    return Path(config_path).resolve().parent / "bench_engines.yaml"


def load_bench_engines(config_path: str) -> dict[str, Any]:
    """Return the bench-engines mapping, or ``{}`` when the file is absent."""
    path = bench_engines_path(config_path)
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise TypeError(f"{path} must be a mapping")
    return data


def exclusive_workspace_ids(config_path: str) -> frozenset[str]:
    """Workspace ids that must not fall through to a production group."""
    raw = load_bench_engines(config_path).get("exclusive_workspaces") or []
    return frozenset(str(item) for item in raw)


def eval_backends_enabled(config_path: str) -> bool:
    """True when the eval module or a bench harness asked for the eval engines."""
    if os.environ.get("PORTAL_ENABLE_EVAL", "").lower() in _TRUTHY:
        return True
    if os.environ.get("PORTAL_BENCH_WORKSPACES", "").lower() in _TRUTHY:
        return True
    portal = Path(config_path).resolve().parent / "portal.yaml"
    if not portal.is_file():
        return False
    raw = yaml.safe_load(portal.read_text(encoding="utf-8")) or {}
    return bool(((raw.get("modules") or {}).get("eval") or {}).get("enabled"))
