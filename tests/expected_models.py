"""Expected-model resolution for routing validation across all three test suites.

Single source of truth: portal_pipeline.router.workspaces.WORKSPACES and
the per-persona YAML files. This module never modifies them; it only reads
the canonical config and returns "what model should have served this
request" given a workspace ID or a persona slug.

Used by:
  - tests/portal5_acceptance_v6.py (S3a, S6, S10, S21 routing checks)
  - tests/uat/routing.py (per-test routed_model validation; entry tests/portal5_uat_driver.py)
  - tests/benchmarks/bench_tps.py (expected_model_match flag in JSON output)

All checks are case-insensitive substring matches against the actual model
name returned by the backend. The matchers are intentionally loose (family
prefix of Ollama tag) because Ollama may return abbreviated names.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from portal_pipeline.router.workspaces import (  # noqa: PLC0415
        _PERSONA_MAP,
        WORKSPACES,
    )
except Exception as exc:  # pragma: no cover
    WORKSPACES = {}
    _PERSONA_MAP = {}
    _IMPORT_ERROR = str(exc)
else:
    _IMPORT_ERROR = ""


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


def expected_model_keys(
    workspace_id: str,
) -> tuple[list[str], str]:
    """Return (keys, source_label) for what Ollama model should serve this workspace.

    `keys` is a list of lowercase substrings; if any appears in the actual
    model name (case-insensitive), the routing is considered correct.

    `source_label` is a short human-readable description for inclusion in
    test output.
    """
    cfg = WORKSPACES.get(workspace_id, {})
    if not cfg:
        return [], "unknown workspace"

    ollama_hint = (cfg.get("model_hint") or "").strip()

    keys: list[str] = []
    parts: list[str] = []

    if ollama_hint:
        keys.append(_ollama_family(ollama_hint))
        parts.append(f"Ollama:{_ollama_family(ollama_hint)}")

    if not keys:
        return [], f"{workspace_id}: no hints in WORKSPACES"

    # auto-vision text-only fallback: pipeline reroutes to auto-reasoning when no
    # image_url is present. Include auto-reasoning model keys so text-only persona
    # tests (chartanalyst, ocrspecialist, etc.) accept the fallback model.
    if workspace_id == "auto-vision":
        ar_cfg = WORKSPACES.get("auto-reasoning", {})
        ar_ollama = (ar_cfg.get("model_hint") or "").strip()
        if ar_ollama:
            keys.append(_ollama_family(ar_ollama))
        parts.append("auto-reasoning fallback (text-only)")

    seen: set[str] = set()
    deduped = [k for k in keys if not (k in seen or seen.add(k))]
    return deduped, " | ".join(parts)


def expected_model_keys_for_persona(
    persona_slug: str,
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
    keys, src = expected_model_keys(ws)
    return keys, f"via workspace '{ws}': {src}"


_WORKSPACE_AND_PERSONA_NAMES: frozenset[str] | None = None
_WORKSPACE_KEYS: dict[str, dict[str, str]] = {}


def _init_routing_names() -> frozenset[str]:
    """Lazy-init the set of valid workspace names and persona slugs."""
    global _WORKSPACE_AND_PERSONA_NAMES, _WORKSPACE_KEYS  # noqa: PLW0603
    if _WORKSPACE_AND_PERSONA_NAMES is not None:
        return _WORKSPACE_AND_PERSONA_NAMES
    names: set[str] = set()
    # workspaces: the auto-router, persona workspaces, etc.
    for ws_id, cfg in WORKSPACES.items():
        names.add(ws_id.lower())
        _WORKSPACE_KEYS[ws_id.lower()] = cfg
    # persona slugs from _PERSONA_MAP
    for slug, info in _PERSONA_MAP.items():
        names.add(slug.lower())
        ws = info.get("workspace_model") or info.get("workspace") or ""
        if ws and ws.lower() not in _WORKSPACE_KEYS:
            _WORKSPACE_KEYS[slug.lower()] = {"ws": ws}
    _WORKSPACE_AND_PERSONA_NAMES = frozenset(names)
    return _WORKSPACE_AND_PERSONA_NAMES


def _is_routing_identifier(actual: str) -> bool:
    """True if `actual` is a workspace name or persona slug — i.e. the
    pipeline resolved it, and OWUI stored the routing identifier rather
    than the backend model name."""
    names = _init_routing_names()
    return actual.lower() in names


def model_matches_expected(
    actual_model: str,
    expected_keys: Iterable[str],
) -> bool:
    """Case-insensitive substring match: any key in actual_model = match.

    Empty actual_model never matches (no routing info available).
    Empty expected_keys never matches (caller had no expectation; should
    have skipped the check rather than calling this).

    If actual_model is a workspace name or persona slug (OWUI stores the
    routing identifier, not the resolved backend model), treat it as a
    match — the pipeline's routing layer resolved it correctly.
    """
    if not actual_model:
        return False
    actual_lower = actual_model.lower()
    keys_list = [k.lower() for k in expected_keys if k]
    if not keys_list:
        return False
    if any(k in actual_lower for k in keys_list):
        return True
    if _is_routing_identifier(actual_model):
        return True
    return False


def resolve_expected(
    *,
    workspace_id: str = "",
    persona_slug: str = "",
) -> tuple[list[str], str]:
    """Convenience wrapper. Use persona_slug if provided, else workspace_id.

    For UAT driver tests where model_slug can be either, the caller should
    pass the slug as workspace_id first, fall back to persona_slug if no
    workspace match. Or just call this:

        keys, src = resolve_expected(
            workspace_id=test['model_slug'],
            persona_slug=test['model_slug'],
        )
    """
    if persona_slug and persona_slug in _PERSONA_MAP:
        return expected_model_keys_for_persona(persona_slug)
    if workspace_id and workspace_id in WORKSPACES:
        return expected_model_keys(workspace_id)
    return [], f"unresolvable: workspace='{workspace_id}', persona='{persona_slug}'"
