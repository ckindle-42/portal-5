"""Config-driven model/workspace/persona discovery and size estimation.

Extracted byte-for-byte from tests/benchmarks/bench_tps.py.
"""

import httpx
import yaml

from .config import OLLAMA_URL, PROJECT_ROOT


def _load_backends_config() -> dict:
    cfg_path = PROJECT_ROOT / "config" / "backends.yaml"
    if not cfg_path.exists():
        return {}
    return yaml.safe_load(cfg_path.read_text()) or {}


def _parse_ollama_sizes_from_config() -> dict[str, float]:
    """Parse model→GB size estimates from backends.yaml inline comments.

    Priority:
    1. Inline comments like '# ~46GB' (Ollama models).
    2. Parameter count inferred from model name (e.g., ':70b' → ~40GB for Q4).
    3. Fallback: 20.0 GB (conservative).
    """
    import re

    sizes: dict[str, float] = {}
    cfg_path = PROJECT_ROOT / "config" / "backends.yaml"
    if cfg_path.exists():
        model_re = re.compile(r"^\s+-\s+(\S+)")
        size_re = re.compile(r"~(\d+(?:\.\d+)?)\s*GB")
        for line in cfg_path.read_text().splitlines():
            m = model_re.match(line)
            if m:
                name = m.group(1)
                s = size_re.search(line)
                if s:
                    sizes[name] = float(s.group(1))
    return sizes


def _infer_ollama_model_size(model_name: str) -> float:
    """Estimate Ollama model memory from name patterns.

    GGUF models: Q4 ≈ 0.6 bytes/param, Q5 ≈ 0.7, Q6 ≈ 0.8, Q8 ≈ 1.0.
    MoE models: size based on active parameters, not total.
    """
    import re

    name = model_name.lower()

    # MoE models: extract active param count (e.g., "30b-a3b" → 3B active)
    moe_match = re.search(r"(\d+)b-(\d+)b", name)
    if moe_match:
        active_b = int(moe_match.group(2))
        return _gb_per_param(active_b, name)

    # Standard models: extract param count from :Nb or -Nb pattern
    param_match = re.search(r"[:/-](\d+(?:\.\d+)?)b", name)
    if param_match:
        params_b = float(param_match.group(1))
        return _gb_per_param(params_b, name)

    return 20.0


def _gb_per_param(params_b: float, name: str) -> float:
    """Estimate GB from parameter count and quant level in name."""
    if "q8" in name or "8bit" in name:
        return round(params_b * 1.0, 1)
    if "q6" in name:
        return round(params_b * 0.8, 1)
    if "q5" in name:
        return round(params_b * 0.7, 1)
    if "q4" in name or "4bit" in name:
        return round(params_b * 0.6, 1)
    # Unknown quant: assume Q4 (most common GGUF default)
    return round(params_b * 0.6, 1)


_CONFIG_SIZES = _parse_ollama_sizes_from_config()


def _parse_model_size_gb(model_name: str) -> float:
    """Estimate model memory footprint in GB.

    Uses inline '# ~XXGB' comments from backends.yaml when available,
    then falls back to name-pattern inference, then 20GB.
    """
    if model_name in _CONFIG_SIZES:
        return _CONFIG_SIZES[model_name]
    return _infer_ollama_model_size(model_name)


# ── Model discovery: config-driven (canonical source of truth) ───────────────


def _config_ollama_models_by_group() -> dict[str, list[str]]:
    """Ollama models grouped by backend group from backends.yaml.

    Handles both legacy flat-string entries and the current dict form
    (`{id, supports_tools, notes, …}`) introduced in commit 1af5b3c.
    """
    cfg = _load_backends_config()
    groups: dict[str, list[str]] = {}
    for be in cfg.get("backends", []):
        if be.get("type") == "ollama":
            group = be.get("group", be.get("id", "unknown"))
            entries = be.get("models", []) or []
            ids: list[str] = []
            for m in entries:
                if isinstance(m, dict):
                    mid = m.get("id")
                    if mid:
                        ids.append(mid)
                elif isinstance(m, str):
                    ids.append(m)
            groups[group] = ids
    return groups


def _config_ollama_models_unique() -> list[str]:
    """All unique Ollama models from backends.yaml, deduplicated."""
    seen: set[str] = set()
    unique: list[str] = []
    for models in _config_ollama_models_by_group().values():
        for m in models:
            if m not in seen:
                seen.add(m)
                unique.append(m)
    return unique


def _runtime_ollama_models() -> set[str]:
    """Models actually installed in Ollama (from /api/tags).

    Adds lowercase + :latest-stripped variants so backends.yaml entries
    (e.g. 'deepseek-coder-v2-lite:q4_k_m') match Ollama's actual name
    ('deepseek-coder-v2-lite:Q4_K_M:latest').
    """
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5.0)
        if r.status_code == 200:
            names: set[str] = set()
            for m in r.json().get("models", []):
                name = m["name"]
                names.add(name)
                # lowercase variant (handles Q4_K_M vs q4_k_m)
                names.add(name.lower())
                # strip :latest suffix variants
                for variant in (name, name.lower()):
                    if variant.endswith(":latest"):
                        names.add(variant[: -len(":latest")])
            return names
    except Exception:
        pass
    return set()


def _config_workspaces() -> list[str]:
    """All workspace IDs from backends.yaml, sorted by primary backend group.

    Sorting by the first group in each workspace's routing list keeps the same
    backend active across consecutive tests, minimising model swaps.

    Workspaces listed in the top-level ``pipeline_bench_skip:`` list are
    excluded — see backends.yaml for rationale. The exclusion does NOT
    apply when bench_pipeline() is called with an explicit workspace
    filter (operator-driven probe overrides config-level skip).
    """
    cfg = _load_backends_config()
    routing: dict[str, list[str]] = cfg.get("workspace_routing", {})
    skip = set(cfg.get("pipeline_bench_skip", []))
    return sorted(
        (ws for ws in routing if ws not in skip),
        key=lambda ws: (routing[ws][0] if routing[ws] else "", ws),
    )


def _discover_personas() -> list[dict]:
    """Read all persona YAMLs, return [{slug, name, workspace_model, category}]."""
    personas_dir = PROJECT_ROOT / "config" / "personas"
    if not personas_dir.exists():
        return []
    personas = []
    for f in sorted(personas_dir.glob("*.yaml")):
        try:
            p = yaml.safe_load(f.read_text())
        except Exception:
            continue
        personas.append(
            {
                "slug": p.get("slug", f.stem),
                "name": p.get("name", f.stem),
                "workspace_model": p.get("workspace_model", "dolphin-llama3:8b"),
                "category": p.get("category", "general"),
            }
        )
    return personas
