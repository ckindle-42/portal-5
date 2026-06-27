"""Shared helpers for the portal CLI sub-modules."""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from portal_pipeline.config import PortalConfig

def _detect_ollama_cmd() -> str | None:
    """Return the ollama command to use (native or docker exec), or None."""
    # Check native Ollama
    import urllib.request as _ur

    try:
        r = _ur.urlopen("http://localhost:11434/api/tags", timeout=3)
        r.close()
        if subprocess.run(["which", "ollama"], capture_output=True).returncode == 0:
            return "ollama"
    except Exception:
        pass
    # Check Docker Ollama
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=5,
        )
        if "portal5-ollama" in result.stdout:
            return "docker exec portal5-ollama ollama"
    except Exception:
        pass
    return None


def _model_exists_in_ollama(model_name: str, ollama_cmd: str) -> bool:
    """Check if a model is already loaded in Ollama."""
    parts = ollama_cmd.split() + ["list"]
    try:
        result = subprocess.run(parts, capture_output=True, text=True, timeout=10)
        for line in result.stdout.lower().splitlines():
            if model_name.lower() in line:
                return True
    except Exception:
        pass
    return False


def _fmt_size(size: int) -> str:
    """Format bytes into human-readable size."""
    for unit in ("B", "K", "M", "G", "T"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}P"


def _resolve_model_name(raw: str) -> str:
    """Resolve ${VAR:-default} env var references in model names."""
    import re as _re

    def _repl(m):
        var, default = m.group(1), m.group(2)
        return os.environ.get(var, default)

    return _re.sub(r"\$\{(\w+):-([^}]+)\}", _repl, raw)


# ── Cross-reference workspace ↔ model registry ────────────────────────────────


@dataclass(frozen=True)
class CrossRefReport:
    """Result of cross-referencing portal.yaml workspaces ↔ models.

    Classifications:
      orphan_hints   — bare-tag workspace model_hint values that match
                       a registered ollama_name with mismatched value
                       (currently always empty pending near-miss detection)
      unused_models  — non-retired registry ollama_names referenced by
                       zero workspaces (soft warning)

    Hints prefixed with ``hf.co/`` are Ollama-native and outside this
    cross-reference's scope.
    """

    orphan_hints: list[str]  # model_hint values with no matching ollama_name
    unused_models: list[str]  # non-retired ollama_names referenced by zero workspaces

    @property
    def ok(self) -> bool:
        return not self.orphan_hints


def cross_reference_workspaces_and_models(cfg: PortalConfig) -> CrossRefReport:
    """Cross-check workspace model_hint values against the models registry.

    Returns a CrossRefReport that callers can format as they choose.
    Pure function — no I/O, no side effects.
    """
    # Build the set of pullable ollama_names from the registry
    {m.ollama_name for m in cfg.models}
    non_retired_names = {m.ollama_name for m in cfg.models if not m.retired}

    # Walk workspaces, collect their model_hint values
    hint_to_workspaces: dict[str, list[str]] = {}
    for ws_id, ws in cfg.workspaces.items():
        hint = getattr(ws, "model_hint", None)
        if hint:
            hint_to_workspaces.setdefault(hint, []).append(ws_id)

    # hf.co/ hints are Ollama-native HF pulls — no registry entry needed.
    # Bare-tag hints use Ollama library models; registry coverage is opt-in.
    # Future enhancement: near-miss detection for bare-tag typos of registered
    # ollama_name values (Levenshtein distance ≤ 2).
    orphan_hints: list[str] = []
    for hint in hint_to_workspaces:
        if hint.startswith("hf.co/"):
            continue  # Ollama-native HF pull, no registry needed

    # An unused model is a non-retired entry no workspace references
    referenced = set(hint_to_workspaces)
    unused_models = sorted(non_retired_names - referenced)

    return CrossRefReport(
        orphan_hints=sorted(orphan_hints),
        unused_models=unused_models,
    )

