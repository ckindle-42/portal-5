"""Expected-model resolution for routing validation across all three test suites.

Single source of truth: portal_pipeline.router.workspaces.WORKSPACES and
the per-persona YAML files. This module never modifies them; it only reads
the canonical config and returns "what model should have served this
request" given a workspace ID, a persona slug, and the current MLX state.

Used by:
  - tests/portal5_acceptance_v6.py (S3a, S6, S10, S21 routing checks)
  - tests/portal5_uat_driver.py (per-test routed_model validation)
  - tests/benchmarks/bench_tps.py (expected_model_match flag in JSON output)

All checks are case-insensitive substring matches against the actual model
name returned by the backend. The matchers are intentionally loose (basename
of HF path, family prefix of Ollama tag) because Ollama may return abbreviated
names and MLX may return either the full HF path or just the basename
depending on proxy version.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from portal_pipeline.router.workspaces import (  # noqa: PLC0415
        WORKSPACES,
        _PERSONA_MAP,
    )
except Exception as exc:  # pragma: no cover
    WORKSPACES = {}
    _PERSONA_MAP = {}
    _IMPORT_ERROR = str(exc)
else:
    _IMPORT_ERROR = ""


_MLX_ORG_PREFIXES = (
    "mlx-community/",
    "lmstudio-community/",
    "Jackrong/",
    "Jiunsong/",
    "unsloth/",
    "dealignai/",
    "huihui-ai/",
    "divinetribe/",
)


def is_mlx_model(actual_model: str) -> bool:
    """True if the model string looks like an MLX-served model (HF path)."""
    if not actual_model:
        return False
    return any(actual_model.startswith(p) for p in _MLX_ORG_PREFIXES)


def _ollama_family(tag: str) -> str:
    """Get the family/basename of an Ollama tag for fuzzy matching.

    'baronllm:q6_k' -> 'baronllm'
    'deepseek-r1:32b-q4_k_m' -> 'deepseek-r1'
    'hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF' -> 'llama-3.2-3b-instruct-abliterated'
    """
    if not tag:
        return ""
    s = tag.split(":")[0]
    if "/" in s:
        s = s.split("/")[-1]
    return s.lower().replace("-gguf", "")


def _mlx_basename(hf_path: str) -> str:
    """Last path component of an MLX HF path, lowercased.

    'mlx-community/Qwen3-Coder-Next-4bit' -> 'qwen3-coder-next-4bit'
    """
    if not hf_path:
        return ""
    return hf_path.split("/")[-1].lower()


def expected_model_keys(
    workspace_id: str,
    *,
    mlx_state: str = "ready",
) -> tuple[list[str], str]:
    """Return (keys, source_label) for what model should serve this workspace.

    `keys` is a list of lowercase substrings; if any appears in the actual
    model name (case-insensitive), the routing is considered correct. The
    list is ordered: most-preferred (MLX hint) first, then fallback (Ollama
    hint). The caller is responsible for case-insensitive comparison.

    `source_label` is a short human-readable description ("MLX preferred",
    "Ollama only", etc.) for inclusion in test output.

    `mlx_state` should be one of "ready", "switching", "none", "down".
    When MLX is "down" or "unreachable", only the Ollama hint is returned.
    """
    cfg = WORKSPACES.get(workspace_id, {})
    if not cfg:
        return [], "unknown workspace"

    mlx_hint = (cfg.get("mlx_model_hint") or "").strip()
    ollama_hint = (cfg.get("model_hint") or "").strip()

    keys: list[str] = []
    parts: list[str] = []

    mlx_available = mlx_state in ("ready", "switching", "none")
    if mlx_hint and mlx_available:
        keys.append(_mlx_basename(mlx_hint))
        parts.append(f"MLX:{_mlx_basename(mlx_hint)}")
    if ollama_hint:
        keys.append(_ollama_family(ollama_hint))
        parts.append(f"Ollama:{_ollama_family(ollama_hint)}")

    if not keys:
        return [], f"{workspace_id}: no hints in WORKSPACES"

    seen: set[str] = set()
    deduped = [k for k in keys if not (k in seen or seen.add(k))]
    return deduped, " | ".join(parts)


def expected_model_keys_for_persona(
    persona_slug: str,
    *,
    mlx_state: str = "ready",
) -> tuple[list[str], str]:
    """Resolve a persona slug to its workspace, then return that workspace's
    expected models. Personas inherit their workspace's routing.

    Returns ([], "<reason>") if the persona is unknown or has no workspace.
    """
    p = _PERSONA_MAP.get(persona_slug)
    if not p:
        return [], f"persona '{persona_slug}' not in _PERSONA_MAP"
    ws = p.get("workspace_model") or p.get("workspace")
    if not ws:
        return [], f"persona '{persona_slug}' has no workspace_model"
    keys, src = expected_model_keys(ws, mlx_state=mlx_state)
    return keys, f"via workspace '{ws}': {src}"


def model_matches_expected(
    actual_model: str,
    expected_keys: Iterable[str],
) -> bool:
    """Case-insensitive substring match: any key in actual_model = match.

    Empty actual_model never matches (no routing info available).
    Empty expected_keys never matches (caller had no expectation; should
    have skipped the check rather than calling this).
    """
    if not actual_model:
        return False
    actual_lower = actual_model.lower()
    return any(k.lower() in actual_lower for k in expected_keys if k)


def resolve_expected(
    *,
    workspace_id: str = "",
    persona_slug: str = "",
    mlx_state: str = "ready",
) -> tuple[list[str], str]:
    """Convenience wrapper. Use persona_slug if provided, else workspace_id.

    For UAT driver tests where model_slug can be either, the caller should
    pass the slug as workspace_id first, fall back to persona_slug if no
    workspace match. Or just call this:

        keys, src = resolve_expected(
            workspace_id=test['model_slug'],
            persona_slug=test['model_slug'],
            mlx_state=current_mlx_state,
        )
    """
    if persona_slug and persona_slug in _PERSONA_MAP:
        return expected_model_keys_for_persona(persona_slug, mlx_state=mlx_state)
    if workspace_id and workspace_id in WORKSPACES:
        return expected_model_keys(workspace_id, mlx_state=mlx_state)
    return [], f"unresolvable: workspace='{workspace_id}', persona='{persona_slug}'"
