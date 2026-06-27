"""Loaders for backends.yaml, persona files, and routing-chain resolution.
Pure I/O — no HTTP, no async."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml

from ._common import WORKSPACE_REGISTRY

ROOT = Path(__file__).parent.parent.resolve()
REPO_ROOT = ROOT.parent


def load_backends_yaml() -> dict[str, Any]:
    with open(REPO_ROOT / "config" / "backends.yaml") as f:
        return yaml.safe_load(f)


def chain_for_workspace(cfg: dict[str, Any], workspace_id: str) -> list[str]:
    """Return the list of backend group names for a workspace, in chain order."""
    return cfg.get("workspace_routing", {}).get(workspace_id, ["general"])


def models_in_group(cfg: dict[str, Any], group: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for be in cfg.get("backends", []):
        if be.get("group") != group:
            continue
        if True:
            for mid in be.get("models", []):
                # Accept dict-form Ollama entries (new) and bare strings (legacy).
                # Dict entries carry per-model metadata; strings imply defaults.
                if isinstance(mid, dict):
                    model_id = mid["id"]
                else:
                    model_id = mid
                out.append(
                    {
                        "id": model_id,
                        "backend_type": "ollama",
                        "big_model": False,
                        "is_vlm": False,
                        "memory_gb": _ollama_size_estimate(model_id),
                    }
                )
    return out


def _ollama_size_estimate(model_id: str) -> float:
    lower = model_id.lower()
    if "70b" in lower or ":70b" in lower:
        return 40.0
    if "33b" in lower or "32b" in lower or "30b" in lower or "35b" in lower:
        return 18.0
    if "24b" in lower or "26b" in lower or "27b" in lower:
        return 16.0
    if "20b" in lower:
        return 12.0
    if "16b" in lower:
        return 10.0
    if ":13b" in lower or "13b" in lower:
        return 8.0
    if "9b" in lower or "8b" in lower or ":7b" in lower or "7b" in lower:
        return 5.5
    if "3b" in lower:
        return 2.5
    if "1b" in lower or "0.5b" in lower:
        return 1.0
    return 6.0


def chain_models_for_workspace(
    cfg: dict[str, Any],
    workspace_id: str,
) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for group in chain_for_workspace(cfg, workspace_id):
        for m in models_in_group(cfg, group):
            key = (m["backend_type"], m["id"])
            if key in seen:
                continue
            seen.add(key)
            out.append({**m, "group": group})
    return out


# ── Persona ↔ workspace lookup ────────────────────────────────────────────


def load_personas_for_workspace(
    workspace_id: str,
    categories: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Return parsed YAML for every persona that:
    (a) has its workspace_model == workspace_id, OR
    (b) has category in `categories` (broader catch for personas not
        explicitly bound to this workspace).
    """
    out = []
    for f in sorted((REPO_ROOT / "config" / "personas").glob("*.yaml")):
        try:
            d = yaml.safe_load(f.read_text()) or {}
            ws = d.get("workspace_model")
            cat = d.get("category")
            if ws == workspace_id or cat in categories:
                out.append(d)
        except Exception:
            continue
    return out


def load_personas_by_slugs(slugs: tuple[str, ...]) -> list[dict[str, Any]]:
    """Return parsed YAML for personas whose slug is in `slugs`, preserving
    the order of the input list.

    Used by workspaces that set persona_slugs_explicit in their registry
    entry. The category filter is bypassed entirely — this lets a single
    workspace (e.g. auto-coding-bench) sample production personas across
    multiple categories without pulling in everything in those categories.

    See TASK_CODING_SHOOTOUT_V2.md §A2 / §A7.
    """
    by_slug: dict[str, dict[str, Any]] = {}
    for f in sorted((REPO_ROOT / "config" / "personas").glob("*.yaml")):
        try:
            d = yaml.safe_load(f.read_text()) or {}
            slug = d.get("slug")
            if slug in slugs:
                by_slug[slug] = d
        except Exception:
            continue
    # Preserve input order; report missing personas immediately
    out: list[dict[str, Any]] = []
    missing: list[str] = []
    for slug in slugs:
        if slug in by_slug:
            out.append(by_slug[slug])
        else:
            missing.append(slug)
    if missing:
        print(
            f"persona_slugs_explicit references unknown personas (not found in "
            f"config/personas/*.yaml): {missing}",
            file=sys.stderr,
        )
        sys.exit(5)
    return out


# ── Direct backend calls ──────────────────────────────────────────────────

