#!/usr/bin/env python3
"""Portal 5 — Comprehensive TPS Benchmark.

Measures tokens/sec across every model, every workspace, and every persona
on every available backend.

Three test paths:
  1. Direct backends  — MLX proxy (:8081) + Ollama (:11434), every model
  2. Pipeline routing  — portal-pipeline (:9099) per workspace
  3. Persona routing    — portal-pipeline (:9099) per persona workspace_model

Model discovery is config-driven (backends.yaml + persona YAMLs), not
runtime-only. Undownloaded Ollama models are tested and reported as unavailable.

Usage:
    python3 tests/benchmarks/bench_tps.py                         # everything, 3 runs
    python3 tests/benchmarks/bench_tps.py --runs 1                # single run (faster)
    python3 tests/benchmarks/bench_tps.py --mode direct           # backends only
    python3 tests/benchmarks/bench_tps.py --mode pipeline         # workspaces only
    python3 tests/benchmarks/bench_tps.py --mode personas         # personas only
    python3 tests/benchmarks/bench_tps.py --mode all              # everything (default)
    python3 tests/benchmarks/bench_tps.py --model dolphin-llama3  # filter by model substring
    python3 tests/benchmarks/bench_tps.py --workspace auto-coding # single workspace
    python3 tests/benchmarks/bench_tps.py --persona cybersecurity # filter personas
    python3 tests/benchmarks/bench_tps.py --output results.json   # custom output
    python3 tests/benchmarks/bench_tps.py --dry-run               # show plan
    python3 tests/benchmarks/bench_tps.py --cooldown 5            # 5s gap between models
    python3 tests/benchmarks/bench_tps.py --order size            # smallest models first

Memory management:
    Models are tested ONE AT A TIME (sequential, blocking). Ollama models are force-unloaded
    via keep_alive=0 after each test to reclaim unified memory. Between MLX model tests a
    cooldown period allows the MLX proxy to fully switch and release GPU memory.

    --order size (default): tests smallest models first, so failures on large models don't
    waste time after small models already passed. MLX sizes come from the proxy's
    MODEL_MEMORY dict; Ollama sizes are parsed from backends.yaml comments.
    --order config: preserves backends.yaml ordering (group-then-model).
    --cooldown N: seconds to wait between model tests for memory reclamation (default: 3).

Output: JSON file with raw TPS data for every model/workspace/persona.
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

MLX_URL = "http://localhost:8081"
OLLAMA_URL = "http://localhost:11434"
PIPELINE_URL = "http://localhost:9099"

MAX_TOKENS = 256
REQUEST_TIMEOUT = 180.0
RESULTS_FILE = "/tmp/bench_tps_results.json"

# ── Prompt library ────────────────────────────────────────────────────────────
# Category-mapped prompts designed to produce ~150-250 tokens of structured
# output. Each prompt targets a specific capability so TPS comparisons are
# apples-to-apples within a category. The "general" prompt is used as fallback.

PROMPTS: dict[str, str] = {
    "general": (
        "You are a helpful assistant. Answer concisely.\n\n"
        "List the 7 OSI model layers from bottom to top. For each layer, provide: "
        "1) the layer number, 2) the standard name, 3) one example protocol or technology. "
        "Format as a numbered list with one line per layer."
    ),
    "coding": (
        "You are a code assistant. Write clean, production-quality code.\n\n"
        "Write a Python function called `merge_intervals` that takes a list of "
        "tuples (each tuple is a pair of integers representing a start and end value) "
        "and returns a new list with overlapping intervals merged. "
        "Example: [(1,3),(2,6),(8,10),(15,18)] → [(1,6),(8,10),(15,18)]. "
        "Include type hints, a docstring with the algorithm explanation, and "
        "handle edge cases (empty list, single interval, fully overlapping). "
        "Return only the function, no explanation outside the docstring."
    ),
    "security": (
        "You are a cybersecurity analyst. Be precise and cite frameworks.\n\n"
        "Analyze the following scenario and provide a structured response:\n"
        "A company's SIEM detected repeated SSH brute-force attempts from 47 "
        "unique IPs over 2 hours targeting port 22 on 3 servers in the DMZ. "
        "Two IPs are on the CrowdSec community blocklist.\n\n"
        "For each item below, provide 2-3 sentences:\n"
        "1. Classification (MITRE ATT&CK tactic + technique ID)\n"
        "2. Immediate containment actions (first 30 minutes)\n"
        "3. Detection rule to write (field names + logic)\n"
        "4. Root cause question to investigate"
    ),
    "reasoning": (
        "You are a structured reasoner. Think step-by-step before concluding.\n\n"
        "A hospital emergency room has 30 patients arriving per hour during peak "
        "hours. The ER has 8 beds, 3 doctors, and 12 nurses. Average treatment "
        "time is 45 minutes per patient. Current wait time is 3.5 hours.\n\n"
        "Identify: 1) the primary bottleneck (beds, doctors, or nurses — show "
        "the math), 2) the minimum number of additional resources of each type "
        "needed to reduce wait time to under 1 hour, 3) one process change that "
        "could help without adding resources. Show your calculations."
    ),
    "creative": (
        "You are a creative writer with strong narrative voice.\n\n"
        "Write the opening scene (exactly 8-10 sentences) of a noir detective "
        "story set in a city where memories can be extracted and traded as "
        "currency. The detective has just been hired to find a stolen memory — "
        "but it belongs to the detective themselves. End the scene on a hook. "
        "Use vivid sensory details and short, punchy sentences."
    ),
    "vision": (
        "You are a multimodal vision analyst. Describe what you see precisely.\n\n"
        "For any image provided, respond with this exact structure:\n"
        "1. OBJECTS: List every distinct object visible (name + color + position)\n"
        "2. TEXT: Transcribe any visible text exactly as written\n"
        "3. SCENE: Describe the setting in 2-3 sentences\n"
        "4. ANOMALIES: Note anything unusual, damaged, or out of place\n"
        "5. CONFIDENCE: Rate your analysis certainty (high/medium/low) per category\n\n"
        "Since no image is provided for this text-only test, describe this prompt "
        "template itself — what it expects, what each section does, and suggest "
        "one improvement to the analysis framework."
    ),
}

# Map workspace IDs → prompt category
WORKSPACE_PROMPT_MAP: dict[str, str] = {
    "auto": "general",
    "auto-coding": "coding",
    "auto-agentic": "coding",
    "auto-spl": "coding",
    "auto-security": "security",
    "auto-redteam": "security",
    "auto-blueteam": "security",
    "auto-creative": "creative",
    "auto-reasoning": "reasoning",
    "auto-documents": "coding",
    "auto-video": "creative",
    "auto-music": "creative",
    "auto-research": "reasoning",
    "auto-vision": "vision",
    "auto-data": "reasoning",
    "auto-compliance": "reasoning",
    "auto-mistral": "reasoning",
}

# Map Ollama backend group → prompt category
GROUP_PROMPT_MAP: dict[str, str] = {
    "general": "general",
    "coding": "coding",
    "security": "security",
    "reasoning": "reasoning",
    "vision": "vision",
    "creative": "creative",
}

# Map persona category (from YAML) → prompt category
PERSONA_CATEGORY_PROMPT_MAP: dict[str, str] = {
    "security": "security",
    "redteam": "security",
    "blueteam": "security",
    "pentesting": "security",
    "coding": "coding",
    "software": "coding",
    "development": "coding",
    "reasoning": "reasoning",
    "research": "reasoning",
    "analysis": "reasoning",
    "creative": "creative",
    "writing": "creative",
    "vision": "vision",
    "multimodal": "vision",
    "data": "reasoning",
    "compliance": "reasoning",
}

# MLX models don't have explicit groups in backends.yaml — infer from name/path
_MLX_MODEL_PROMPT_OVERRIDES: dict[str, str] = {
    "Devstral": "coding",
    "Qwen3-Coder": "coding",
    "DeepSeek-Coder": "coding",
    "Dolphin": "creative",
    "Llama-3.2-3B": "general",
    "phi-4": "reasoning",
    "Magistral": "reasoning",
    "Llama-3.3-70B": "coding",
    "Qwopus": "reasoning",
    "Qwen3.5-27B-Claude": "reasoning",
    "Qwen3.5-9B-Claude": "reasoning",
    "Qwen3.5-35B": "reasoning",
    "DeepSeek-R1-Distill": "reasoning",
    "gemma-4-31b": "vision",
    "Qwen3-VL": "vision",
    "gemma-4-e4b": "vision",
    "gemma-4-26b": "vision",
    "Phi-4-reasoning": "reasoning",
    "Llama-3.2-11B-Vision": "vision",
}


def _get_prompt_for_model(model: str, group: str = "") -> str:
    """Get the right prompt for a model based on its group or name."""
    # Ollama models: group is explicit
    if group and group in GROUP_PROMPT_MAP:
        return PROMPTS[GROUP_PROMPT_MAP[group]]
    # MLX models: match against known model name patterns
    for pattern, category in _MLX_MODEL_PROMPT_OVERRIDES.items():
        if pattern in model:
            return PROMPTS[category]
    return PROMPTS["general"]


def _prompt_category_for_model(model: str, group: str = "") -> str:
    """Return the prompt category name for a model."""
    if group and group in GROUP_PROMPT_MAP:
        return GROUP_PROMPT_MAP[group]
    for pattern, category in _MLX_MODEL_PROMPT_OVERRIDES.items():
        if pattern in model:
            return category
    return "general"


def _get_prompt_for_workspace(workspace_id: str) -> str:
    category = WORKSPACE_PROMPT_MAP.get(workspace_id, "general")
    return PROMPTS[category]


def _get_prompt_for_persona_category(category: str) -> str:
    cat_lower = category.lower() if category else ""
    for key, prompt_cat in PERSONA_CATEGORY_PROMPT_MAP.items():
        if key in cat_lower:
            return PROMPTS[prompt_cat]
    return PROMPTS["general"]


def _prompt_category_for_persona(category: str) -> str:
    """Return the prompt category name for a persona category string."""
    cat_lower = category.lower() if category else ""
    for key, prompt_cat in PERSONA_CATEGORY_PROMPT_MAP.items():
        if key in cat_lower:
            return prompt_cat
    return "general"


PROJECT_ROOT = Path(__file__).parent.parent.parent


# ── Helpers ───────────────────────────────────────────────────────────────────


def _load_env() -> None:
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


_load_env()

PIPELINE_API_KEY = os.environ.get("PIPELINE_API_KEY", "")


def _check_backend(url: str, path: str) -> bool:
    headers: dict[str, str] = {}
    if url == PIPELINE_URL and PIPELINE_API_KEY:
        headers["Authorization"] = f"Bearer {PIPELINE_API_KEY}"
    try:
        r = httpx.get(f"{url}{path}", timeout=3.0, headers=headers)
        if r.status_code == 200:
            return True
        # MLX proxy returns 503 when idle (load-on-demand) — still available
        if url == MLX_URL and r.status_code == 503:
            return True
    except Exception:
        pass
    return False


def _get_hardware_info() -> dict:
    info: dict = {"platform": platform.system(), "machine": platform.machine()}
    if sys.platform == "darwin":
        try:
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)
            info["unified_memory_gb"] = round(int(out.strip()) / 1024**3, 1)
        except Exception:
            pass
        try:
            out = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True)
            info["cpu"] = out.strip()
        except Exception:
            pass
    return info


def _load_backends_config() -> dict:
    cfg_path = PROJECT_ROOT / "config" / "backends.yaml"
    if not cfg_path.exists():
        return {}
    return yaml.safe_load(cfg_path.read_text()) or {}


def _unload_ollama_model(model: str) -> None:
    """Send keep_alive=0 to an Ollama model to force memory reclamation.

    Uses the same pattern as mlx-proxy's _evict_ollama_models_for_big_model().
    Ollama holds loaded models in unified memory indefinitely (keep_alive=-1).
    Sending keep_alive=0 with an empty prompt forces immediate unload.
    """
    try:
        with httpx.Client(timeout=10.0) as client:
            client.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": model, "keep_alive": 0, "prompt": ""},
            )
    except Exception:
        pass


def _unload_all_running_ollama_models() -> None:
    """Evict every model currently loaded in Ollama via keep_alive=0.

    Mirrors mlx-proxy's _evict_ollama_models() — uses /api/ps (running models
    only) rather than /api/tags (all installed) to avoid briefly loading models
    that happen to be installed but idle.
    """
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(f"{OLLAMA_URL}/api/ps")
            if r.status_code != 200:
                return
            models = [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return
    for name in models:
        try:
            with httpx.Client(timeout=15.0) as client:
                client.post(
                    f"{OLLAMA_URL}/api/generate",
                    json={"model": name, "keep_alive": 0, "prompt": ""},
                )
        except Exception:
            pass


def _wait_ollama_idle(timeout_s: float = 60.0) -> bool:
    """Poll /api/ps until no models are running (memory fully reclaimed).

    Returns True if Ollama becomes idle within timeout_s, False otherwise.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = httpx.get(f"{OLLAMA_URL}/api/ps", timeout=5.0)
            if r.status_code == 200 and not r.json().get("models"):
                return True
        except Exception:
            pass
        time.sleep(2.0)
    return False


def _evict_mlx_current_model(smallest_mlx_model: str | None) -> None:
    """Force the MLX proxy to release its current (possibly large) model.

    The MLX proxy has no explicit unload endpoint — eviction is triggered by
    loading a different model. We load the smallest configured MLX model to
    push out whatever large model was last tested, leaving only ~3GB resident
    instead of potentially 40-70GB.

    If no small model is available, we just sleep to give the proxy time to
    settle — the proxy's own admission control will handle the next request.
    """
    if not smallest_mlx_model:
        return
    payload = {
        "model": smallest_mlx_model,
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
        "max_tokens": 1,
    }
    try:
        with httpx.Client(timeout=300.0) as client:
            client.post(f"{MLX_URL}/v1/chat/completions", json=payload)
    except Exception:
        pass


def _parse_ollama_sizes_from_config() -> dict[str, float]:
    """Parse model→GB size estimates from backends.yaml.

    Priority:
    1. Inline comments like '# ~46GB' (MLX models have these).
    2. Parameter count inferred from model name (e.g., ':70b' → ~40GB for Q4).
    3. Fallback: 20.0 GB (conservative).
    """
    import re

    cfg_path = PROJECT_ROOT / "config" / "backends.yaml"
    if not cfg_path.exists():
        return {}
    sizes: dict[str, float] = {}
    model_re = re.compile(r"^\s+-\s+(\S+)")
    size_re = re.compile(r"~(\d+(?:\.\d+)?)\s*GB")
    # Parse inline size comments first
    for line in cfg_path.read_text().splitlines():
        m = model_re.match(line)
        if m:
            s = size_re.search(line)
            if s:
                sizes[m.group(1)] = float(s.group(1))
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


def _parse_model_size_gb(model_name: str, backend_type: str = "ollama") -> float:
    """Estimate model memory footprint in GB.

    Both MLX and Ollama: uses inline '# ~XXGB' comments from backends.yaml
    when available, then falls back to name-pattern inference, then 20GB.
    """
    if model_name in _CONFIG_SIZES:
        return _CONFIG_SIZES[model_name]
    if backend_type == "mlx":
        return 20.0
    return _infer_ollama_model_size(model_name)


# ── Model discovery: config-driven (canonical source of truth) ───────────────


def _config_mlx_models() -> list[str]:
    """All MLX models from backends.yaml."""
    cfg = _load_backends_config()
    for be in cfg.get("backends", []):
        if be.get("type") == "mlx":
            return list(be.get("models", []))
    return []


def _config_ollama_models_by_group() -> dict[str, list[str]]:
    """Ollama models grouped by backend group from backends.yaml."""
    cfg = _load_backends_config()
    groups: dict[str, list[str]] = {}
    for be in cfg.get("backends", []):
        if be.get("type") == "ollama":
            group = be.get("group", be.get("id", "unknown"))
            groups[group] = list(be.get("models", []))
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


def _runtime_mlx_models() -> set[str]:
    """Models available via MLX proxy.

    When the proxy is idle (503), it means no model is loaded yet but the proxy
    IS running and will load models on demand. In that case, fall back to the
    config model list so benchmarks treat all configured MLX models as available.
    """
    try:
        r = httpx.get(f"{MLX_URL}/v1/models", timeout=5.0)
        if r.status_code == 200:
            return {m["id"] for m in r.json().get("data", [])}
        # 503 = proxy idle, models load on demand — use config list
        if r.status_code == 503:
            return set(_config_mlx_models())
    except Exception:
        pass
    return set()


def _config_workspaces() -> list[str]:
    """All workspace IDs from backends.yaml, sorted by primary backend group.

    Sorting by the first group in each workspace's routing list keeps the same
    backend active across consecutive tests, minimising model swaps.
    """
    cfg = _load_backends_config()
    routing: dict[str, list[str]] = cfg.get("workspace_routing", {})
    return sorted(routing.keys(), key=lambda ws: (routing[ws][0] if routing[ws] else "", ws))


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


# ── Core benchmark ───────────────────────────────────────────────────────────


def _warmup_mlx_model(model: str) -> bool:
    """Send a minimal warm-up request to force the MLX proxy to load the model.

    When switching between mlx_lm (text) and mlx_vlm (VLM) models, the proxy
    must stop one server and start the other. This warm-up triggers that
    transition before benchmark timing begins.
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
        "max_tokens": 1,
    }
    for attempt in range(3):
        try:
            with httpx.Client(timeout=300.0) as client:
                resp = client.post(f"{MLX_URL}/v1/chat/completions", json=payload)
                if resp.status_code in (200, 503):
                    return True
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError):
            if attempt < 2:
                time.sleep(10)
            continue
        except Exception:
            if attempt < 2:
                time.sleep(10)
            continue
    return False


# P7-PERF: Module-level reusable httpx client for benchmarks
_bench_client: httpx.Client | None = None


def _get_bench_client() -> httpx.Client:
    """Get or create the shared benchmark httpx client."""
    global _bench_client
    if _bench_client is None:
        _bench_client = httpx.Client(
            timeout=REQUEST_TIMEOUT,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    return _bench_client


def bench_tps(
    base_url: str,
    model: str,
    prompt: str,
    runs: int = 3,
    label: str = "",
) -> dict:
    """Benchmark TPS for a single model/endpoint. Returns summary dict.

    P7-PERF: Reuses a shared httpx client to avoid TCP connection overhead
    between runs. This gives a more accurate measurement of actual inference
    time vs connection setup time.
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "max_tokens": MAX_TOKENS,
    }

    headers: dict[str, str] = {}
    if base_url == PIPELINE_URL and PIPELINE_API_KEY:
        headers["Authorization"] = f"Bearer {PIPELINE_API_KEY}"

    client = _get_bench_client()
    run_results = []
    for run_num in range(1, runs + 1):
        t0 = time.perf_counter()
        try:
            resp = client.post(f"{base_url}/v1/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
        except (httpx.ConnectError, httpx.RemoteProtocolError) as e:
            # MLX proxy may be mid-server-switch (mlx_lm ↔ mlx_vlm). Retry once.
            if base_url == MLX_URL:
                time.sleep(10)
                try:
                    t0 = time.perf_counter()
                    resp = client.post(
                        f"{base_url}/v1/chat/completions", json=payload, headers=headers
                    )
                    resp.raise_for_status()
                except Exception as e2:
                    run_results.append(
                        {
                            "run": run_num,
                            "error": str(e2)[:100],
                            "elapsed_s": round(time.perf_counter() - t0, 2),
                        }
                    )
                    continue
            else:
                run_results.append(
                    {
                        "run": run_num,
                        "error": str(e)[:100],
                        "elapsed_s": round(time.perf_counter() - t0, 2),
                    }
                )
                continue
        except httpx.ReadTimeout:
            run_results.append({"run": run_num, "error": "timeout", "elapsed_s": REQUEST_TIMEOUT})
            continue
        except httpx.HTTPStatusError as e:
            body = ""
            try:
                body = e.response.json().get("detail", "")[:80]
            except Exception:
                body = e.response.text[:80]
            run_results.append(
                {
                    "run": run_num,
                    "error": f"HTTP {e.response.status_code}: {body}",
                    "elapsed_s": round(time.perf_counter() - t0, 2),
                }
            )
            continue
        except Exception as e:
            run_results.append(
                {
                    "run": run_num,
                    "error": str(e)[:100],
                    "elapsed_s": round(time.perf_counter() - t0, 2),
                }
            )
            continue

        elapsed = time.perf_counter() - t0
        data = resp.json()
        usage = data.get("usage", {})
        # Handle both OpenAI (completion_tokens) and MLX VLM (output_tokens) formats
        completion_tokens = usage.get("completion_tokens", usage.get("output_tokens", 0))
        prompt_tokens = usage.get("prompt_tokens", usage.get("input_tokens", 0))
        tps = completion_tokens / elapsed if elapsed > 0 else 0.0

        run_results.append(
            {
                "run": run_num,
                "elapsed_s": round(elapsed, 2),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "tps": round(tps, 1),
            }
        )

    successful = [r for r in run_results if "tps" in r]
    if successful:
        avg_tps = round(sum(r["tps"] for r in successful) / len(successful), 1)
        min_tps = min(r["tps"] for r in successful)
        max_tps = max(r["tps"] for r in successful)
        avg_tokens = round(sum(r["completion_tokens"] for r in successful) / len(successful))
        avg_elapsed = round(sum(r["elapsed_s"] for r in successful) / len(successful), 2)
    else:
        avg_tps = min_tps = max_tps = 0.0
        avg_tokens = 0
        avg_elapsed = 0.0

    return {
        "model": model,
        "label": label,
        "runs_total": runs,
        "runs_success": len(successful),
        "avg_tps": avg_tps,
        "min_tps": min_tps,
        "max_tps": max_tps,
        "avg_completion_tokens": avg_tokens,
        "avg_elapsed_s": avg_elapsed,
        "runs": run_results,
    }


# ── Direct backend tests ─────────────────────────────────────────────────────


def bench_direct(
    mlx_available: bool,
    ollama_available: bool,
    models_filter: str | None,
    runs: int,
    dry_run: bool,
    cooldown: float = 3.0,
    order: str = "size",
) -> list[dict]:
    results = []

    if mlx_available:
        mlx_models = _config_mlx_models()
        if models_filter:
            mlx_models = [m for m in mlx_models if models_filter in m]
        if order == "size":
            mlx_models = sorted(mlx_models, key=lambda m: _parse_model_size_gb(m, "mlx"))
        runtime = _runtime_mlx_models()
        print(f"\n  MLX models configured: {len(mlx_models)} (order={order})")
        if runtime:
            print(f"  MLX proxy registered: {len(runtime)}")
        for i, model in enumerate(mlx_models, 1):
            short = model.split("/")[-1]
            size_gb = _parse_model_size_gb(model, "mlx")
            available = model in runtime if runtime else True
            marker = "" if available else " [not registered]"
            print(
                f"    [{i}/{len(mlx_models)}] {short} ({size_gb:.0f}GB){marker} ...",
                end=" ",
                flush=True,
            )
            if dry_run:
                print("(dry run)")
                continue
            if not available:
                print("SKIP")
                r = {
                    "model": model,
                    "label": "mlx-direct",
                    "backend": "mlx",
                    "path": "direct",
                    "available": False,
                    "error": "not registered in proxy",
                    "est_memory_gb": size_gb,
                    "runs_total": runs,
                    "runs_success": 0,
                    "avg_tps": 0,
                    "min_tps": 0,
                    "max_tps": 0,
                    "avg_completion_tokens": 0,
                    "avg_elapsed_s": 0,
                    "runs": [],
                }
                results.append(r)
                continue
            prompt = _get_prompt_for_model(model)
            # Warm-up: force MLX proxy to load model (switches mlx_lm ↔ mlx_vlm if needed)
            print("(warm-up) ", end="", flush=True)
            _warmup_mlx_model(model)
            r = bench_tps(MLX_URL, model, prompt=prompt, runs=runs, label="mlx-direct")
            r["backend"] = "mlx"
            r["path"] = "direct"
            r["available"] = True
            r["est_memory_gb"] = size_gb
            r["prompt_category"] = _prompt_category_for_model(model)
            results.append(r)
            if r["avg_tps"] > 0:
                print(f"{r['avg_tps']} t/s  ({r['runs_success']}/{r['runs_total']} ok)")
            else:
                errors = [run.get("error", "?") for run in r["runs"] if "error" in run]
                print(f"FAIL ({', '.join(set(errors))})")
            # MLX proxy handles memory (admission control, single-model-at-a-time).
            # Cooldown lets proxy settle after model switch.
            if i < len(mlx_models) and cooldown > 0:
                print(f"    cooldown {cooldown:.0f}s ...", end=" ", flush=True)
                time.sleep(cooldown)
                print("ok")

        # ── MLX→Ollama transition eviction ────────────────────────────────
        # The last MLX model is still resident when the Ollama section starts.
        # Force-evict it by loading the smallest configured MLX model (~3GB),
        # then wait for a long transition cooldown so unified memory is clear.
        if ollama_available and mlx_models and not dry_run:
            smallest = sorted(mlx_models, key=lambda m: _parse_model_size_gb(m, "mlx"))[0]
            transition = max(cooldown * 5, 30.0)
            print(
                f"\n  MLX→Ollama: evicting large model via {smallest.split('/')[-1]} "
                f"then {transition:.0f}s transition cooldown ...",
                end=" ",
                flush=True,
            )
            _evict_mlx_current_model(smallest)
            time.sleep(transition)
            print("ok")

    if ollama_available:
        ollama_groups = _config_ollama_models_by_group()
        ollama_unique = _config_ollama_models_unique()
        if models_filter:
            ollama_unique = [m for m in ollama_unique if models_filter in m]
        if order == "size":
            ollama_unique = sorted(ollama_unique, key=lambda m: _parse_model_size_gb(m, "ollama"))
        runtime = _runtime_ollama_models()
        print(
            f"\n  Ollama models configured: {len(ollama_unique)} (across {len(ollama_groups)} groups, order={order})"
        )
        if runtime:
            installed = [m for m in ollama_unique if m in runtime]
            missing = [m for m in ollama_unique if m not in runtime]
            print(f"  Ollama installed: {len(installed)}/{len(ollama_unique)}")
            if missing:
                print(f"  Ollama not installed: {', '.join(missing)}")
        for i, model in enumerate(ollama_unique, 1):
            available = model in runtime if runtime else True
            size_gb = _parse_model_size_gb(model, "ollama")
            marker = "" if available else " [not installed]"
            print(
                f"    [{i}/{len(ollama_unique)}] {model} ({size_gb:.0f}GB){marker} ...",
                end=" ",
                flush=True,
            )
            if dry_run:
                print("(dry run)")
                continue
            if not available:
                print("SKIP")
                r = {
                    "model": model,
                    "label": "ollama-direct",
                    "backend": "ollama",
                    "path": "direct",
                    "available": False,
                    "error": "not installed in Ollama",
                    "est_memory_gb": size_gb,
                    "groups": [g for g, ms in ollama_groups.items() if model in ms],
                    "runs_total": runs,
                    "runs_success": 0,
                    "avg_tps": 0,
                    "min_tps": 0,
                    "max_tps": 0,
                    "avg_completion_tokens": 0,
                    "avg_elapsed_s": 0,
                    "runs": [],
                }
                results.append(r)
                continue
            model_groups = [g for g, ms in ollama_groups.items() if model in ms]
            group = model_groups[0] if model_groups else ""
            prompt = _get_prompt_for_model(model, group=group)
            r = bench_tps(OLLAMA_URL, model, prompt=prompt, runs=runs, label="ollama-direct")
            r["backend"] = "ollama"
            r["path"] = "direct"
            r["available"] = True
            r["est_memory_gb"] = size_gb
            r["groups"] = model_groups
            r["prompt_category"] = _prompt_category_for_model(model, group=group)
            results.append(r)
            if r["avg_tps"] > 0:
                print(f"{r['avg_tps']} t/s  ({r['runs_success']}/{r['runs_total']} ok)")
            else:
                errors = [run.get("error", "?") for run in r["runs"] if "error" in run]
                print(f"FAIL ({', '.join(set(errors))})")
            # Force Ollama to release this model from unified memory before next test.
            # Uses keep_alive=0 then polls /api/ps until Ollama reports no running
            # models — prevents the next model from loading into an already-full
            # unified memory space (the crash vector for large model sequences).
            if i < len(ollama_unique):
                _unload_all_running_ollama_models()
                idle = _wait_ollama_idle(timeout_s=max(cooldown * 10, 60.0))
                if not idle:
                    # Didn't go fully idle — still do the fixed cooldown as fallback
                    if cooldown > 0:
                        print(f"    cooldown {cooldown:.0f}s (idle timeout) ...", end=" ", flush=True)
                        time.sleep(cooldown)
                        print("ok")
                else:
                    print(f"    ollama idle (memory clear)", end="", flush=True)
                    if cooldown > 0:
                        print(f" + {cooldown:.0f}s cooldown ...", end=" ", flush=True)
                        time.sleep(cooldown)
                    print("ok")

    return results


# ── Pipeline workspace tests ─────────────────────────────────────────────────


def bench_pipeline(
    pipeline_available: bool, workspace_filter: str | None, runs: int, dry_run: bool
) -> list[dict]:
    if not pipeline_available:
        return []

    workspaces = _config_workspaces()
    if workspace_filter:
        workspaces = [w for w in workspaces if w == workspace_filter]

    results = []
    print(f"\n  Pipeline workspaces to test: {len(workspaces)}")
    for i, ws in enumerate(workspaces, 1):
        print(f"    [{i}/{len(workspaces)}] {ws} ...", end=" ", flush=True)
        if dry_run:
            print("(dry run)")
            continue
        prompt = _get_prompt_for_workspace(ws)
        r = bench_tps(PIPELINE_URL, ws, prompt=prompt, runs=runs, label="pipeline")
        r["backend"] = "pipeline"
        r["path"] = "pipeline"
        r["workspace"] = ws
        r["prompt_category"] = WORKSPACE_PROMPT_MAP.get(ws, "general")
        results.append(r)
        if r["avg_tps"] > 0:
            print(f"{r['avg_tps']} t/s  ({r['runs_success']}/{r['runs_total']} ok)")
        else:
            errors = [run.get("error", "?") for run in r["runs"] if "error" in run]
            print(f"FAIL ({', '.join(set(errors))})")

    return results


# ── Persona tests ────────────────────────────────────────────────────────────


def bench_personas(
    pipeline_available: bool,
    persona_filter: str | None,
    runs: int,
    dry_run: bool,
) -> list[dict]:
    """Test TPS for each persona's workspace_model through the pipeline."""
    if not pipeline_available:
        return []

    personas = _discover_personas()
    if persona_filter:
        personas = [
            p
            for p in personas
            if persona_filter in p["slug"] or persona_filter in p["name"].lower()
        ]
    # Sort by workspace_model so personas that share a model run consecutively,
    # minimising Ollama model swaps and MLX proxy switches.
    personas = sorted(personas, key=lambda p: (p["workspace_model"], p["slug"]))

    results = []
    print(f"\n  Personas to test: {len(personas)}")
    for i, p in enumerate(personas, 1):
        slug = p["slug"]
        wm = p["workspace_model"]
        cat = p["category"]
        print(f"    [{i}/{len(personas)}] {slug} ({cat}) → {wm} ...", end=" ", flush=True)
        if dry_run:
            print("(dry run)")
            continue
        prompt = _get_prompt_for_persona_category(cat)
        r = bench_tps(PIPELINE_URL, wm, prompt=prompt, runs=runs, label="persona")
        r["backend"] = "pipeline"
        r["path"] = "persona"
        r["persona_slug"] = slug
        r["persona_name"] = p["name"]
        r["persona_category"] = cat
        r["workspace_model"] = wm
        r["prompt_category"] = _prompt_category_for_persona(cat)
        results.append(r)
        if r["avg_tps"] > 0:
            print(f"{r['avg_tps']} t/s  ({r['runs_success']}/{r['runs_total']} ok)")
        else:
            errors = [run.get("error", "?") for run in r["runs"] if "error" in run]
            print(f"FAIL ({', '.join(set(errors))})")

    return results


# ── Output ────────────────────────────────────────────────────────────────────


def _print_availability_report(
    mlx_available: bool,
    ollama_available: bool,
    pipeline_available: bool,
    results: list[dict],
) -> None:
    """Print configured vs available vs tested vs failed counts."""
    print("\n" + "=" * 70)
    print("AVAILABILITY REPORT")
    print("=" * 70)

    mlx = [r for r in results if r.get("backend") == "mlx"]
    if mlx:
        configured = len(mlx)
        available = sum(1 for r in mlx if r.get("available", True))
        tested = sum(1 for r in mlx if r["runs_success"] > 0)
        failed = available - tested
        print(
            f"  MLX:     {configured} configured | {available} registered | {tested} passed | {failed} failed"
        )

    ollama = [r for r in results if r.get("backend") == "ollama"]
    if ollama:
        configured = len(ollama)
        available = sum(1 for r in ollama if r.get("available", True))
        tested = sum(1 for r in ollama if r["runs_success"] > 0)
        failed = available - tested
        missing = configured - available
        print(
            f"  Ollama:  {configured} configured | {available} installed | {tested} passed | {failed} failed | {missing} not installed"
        )

    pipeline = [r for r in results if r.get("path") == "pipeline"]
    if pipeline:
        configured = len(pipeline)
        tested = sum(1 for r in pipeline if r["runs_success"] > 0)
        failed = configured - tested
        print(
            f"  Pipeline (workspaces): {configured} configured | {tested} passed | {failed} failed"
        )

    personas = [r for r in results if r.get("path") == "persona"]
    if personas:
        configured = len(personas)
        tested = sum(1 for r in personas if r["runs_success"] > 0)
        failed = configured - tested
        print(
            f"  Pipeline (personas):   {configured} configured | {tested} passed | {failed} failed"
        )

    print("=" * 70)


def _print_direct_table(results: list[dict]) -> None:
    direct = [r for r in results if r["path"] == "direct"]
    if not direct:
        return

    print("\n" + "=" * 110)
    print(
        f"{'Model':<50} {'Backend':<10} {'Size':<8} {'Status':<10} {'Avg TPS':<10} {'Min':<8} {'Max':<8} {'Tokens':<8}"
    )
    print("=" * 110)
    # Sort: successful first by TPS desc, then unavailable
    for r in sorted(direct, key=lambda x: (x["runs_success"] > 0, x["avg_tps"]), reverse=True):
        model_short = r["model"].split("/")[-1]
        size_gb = r.get("est_memory_gb", 0)
        size_str = f"{size_gb:.0f}GB" if size_gb else "-"
        if r["runs_success"] > 0:
            status = "OK"
            print(
                f"{model_short:<50} {r['backend']:<10} {size_str:<8} {status:<10} {r['avg_tps']:<10.1f} "
                f"{r['min_tps']:<8.1f} {r['max_tps']:<8.1f} {r['avg_completion_tokens']:<8}"
            )
        elif not r.get("available", True):
            print(
                f"{model_short:<50} {r['backend']:<10} {size_str:<8} {'MISSING':<10} {'-':<10} {'-':<8} {'-':<8} {'-':<8}"
            )
        else:
            errors = {run.get("error", "?") for run in r.get("runs", []) if "error" in run}
            err_short = ", ".join(errors)[:20] if errors else "error"
            print(
                f"{model_short:<50} {r['backend']:<10} {size_str:<8} {err_short:<10} {'-':<10} {'-':<8} {'-':<8} {'-':<8}"
            )
    print("=" * 110)

    mlx = [r for r in direct if r["backend"] == "mlx" and r["runs_success"] > 0]
    ollama = [r for r in direct if r["backend"] == "ollama" and r["runs_success"] > 0]
    if mlx and ollama:
        mlx_avg = sum(r["avg_tps"] for r in mlx) / len(mlx)
        ol_avg = sum(r["avg_tps"] for r in ollama) / len(ollama)
        if ol_avg > 0:
            pct = (mlx_avg - ol_avg) / ol_avg * 100
            direction = "faster" if pct >= 0 else "slower"
            print(
                f"\nMLX avg: {mlx_avg:.1f} t/s  |  Ollama avg: {ol_avg:.1f} t/s"
                f"  |  MLX is {abs(pct):.0f}% {direction}"
            )


def _print_pipeline_table(results: list[dict]) -> None:
    pipeline = [r for r in results if r["path"] == "pipeline"]
    if not pipeline:
        return

    print("\n" + "=" * 90)
    print(f"{'Workspace':<30} {'Avg TPS':<10} {'Min':<8} {'Max':<8} {'Tokens':<8} {'Runs':<8}")
    print("=" * 90)
    for r in sorted(pipeline, key=lambda x: x["avg_tps"], reverse=True):
        ws = r.get("workspace", "?")
        if r["runs_success"] > 0:
            print(
                f"{ws:<30} {r['avg_tps']:<10.1f} {r['min_tps']:<8.1f} "
                f"{r['max_tps']:<8.1f} {r['avg_completion_tokens']:<8} "
                f"{r['runs_success']}/{r['runs_total']}"
            )
        else:
            print(
                f"{ws:<30} {'FAIL':<10} {'-':<8} {'-':<8} {'-':<8} {r['runs_success']}/{r['runs_total']}"
            )
    print("=" * 90)


def _print_persona_table(results: list[dict]) -> None:
    personas = [r for r in results if r["path"] == "persona"]
    if not personas:
        return

    print("\n" + "=" * 110)
    print(f"{'Persona':<30} {'Category':<12} {'Workspace Model':<40} {'Avg TPS':<10} {'Runs':<8}")
    print("=" * 110)
    for r in sorted(personas, key=lambda x: x["avg_tps"], reverse=True):
        slug = r.get("persona_slug", "?")
        cat = r.get("persona_category", "?")
        wm = r.get("workspace_model", "?")
        wm_short = wm.split("/")[-1] if "/" in wm else wm
        if r["runs_success"] > 0:
            print(
                f"{slug:<30} {cat:<12} {wm_short:<40} {r['avg_tps']:<10.1f} {r['runs_success']}/{r['runs_total']}"
            )
        else:
            print(
                f"{slug:<30} {cat:<12} {wm_short:<40} {'FAIL':<10} {r['runs_success']}/{r['runs_total']}"
            )
    print("=" * 110)


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Portal 5 TPS Benchmark")
    parser.add_argument(
        "--mode",
        choices=["direct", "pipeline", "personas", "all"],
        default="all",
        help="Test direct backends, pipeline workspaces, persona routing, or all (default: all)",
    )
    parser.add_argument("--runs", type=int, default=3, help="Runs per model/workspace (default: 3)")
    parser.add_argument("--model", help="Filter: substring match on model name (direct only)")
    parser.add_argument("--workspace", help="Filter: exact workspace ID (pipeline only)")
    parser.add_argument("--persona", help="Filter: substring match on persona slug/name")
    parser.add_argument("--prompt", help="Override all prompts with this single prompt string")
    parser.add_argument("--output", default=RESULTS_FILE, help="Output JSON path")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    parser.add_argument(
        "--cooldown",
        type=float,
        default=3.0,
        help="Seconds to wait between model tests for memory reclamation (default: 3)",
    )
    parser.add_argument(
        "--order",
        choices=["size", "config"],
        default="size",
        help="Model test order: 'size' = smallest first (default), 'config' = backends.yaml order",
    )
    args = parser.parse_args()

    # If user provides a single prompt override, replace the entire library
    if args.prompt:
        for key in PROMPTS:
            PROMPTS[key] = args.prompt

    print("=" * 70)
    print("Portal 5 — Comprehensive TPS Benchmark")
    print("=" * 70)

    hw = _get_hardware_info()
    print(f"Hardware: {json.dumps(hw)}")
    if args.prompt:
        print(f"Prompt override: {args.prompt[:60]}...")
    else:
        print(f"Prompts: {len(PROMPTS)} categories ({', '.join(PROMPTS.keys())})")
    print(f"Max tokens: {MAX_TOKENS}  |  Runs per model: {args.runs}")
    print(f"Mode: {args.mode}  |  Order: {args.order}  |  Cooldown: {args.cooldown:.0f}s")

    # Config summary
    mlx_cfg = _config_mlx_models()
    ollama_cfg = _config_ollama_models_unique()
    workspaces_cfg = _config_workspaces()
    personas_cfg = _discover_personas()

    print("\nConfigured (from backends.yaml + persona YAMLs):")
    print(f"  MLX models:    {len(mlx_cfg)}")
    print(f"  Ollama models: {len(ollama_cfg)}")
    print(f"  Workspaces:    {len(workspaces_cfg)}")
    print(f"  Personas:      {len(personas_cfg)}")
    total_configured = len(mlx_cfg) + len(ollama_cfg)
    if args.mode in ("pipeline", "all"):
        total_configured += len(workspaces_cfg)
    if args.mode in ("personas", "all"):
        total_configured += len(personas_cfg)
    print(f"  Total to test: ~{total_configured} (mode={args.mode})")

    mlx_available = _check_backend(MLX_URL, "/v1/models")
    ollama_available = _check_backend(OLLAMA_URL, "/api/tags")
    pipeline_available = _check_backend(PIPELINE_URL, "/v1/models")

    print("\nBackends:")
    print(f"  MLX proxy  ({MLX_URL}):      {'available' if mlx_available else 'not running'}")
    print(f"  Ollama     ({OLLAMA_URL}):    {'available' if ollama_available else 'not running'}")
    print(f"  Pipeline   ({PIPELINE_URL}):  {'available' if pipeline_available else 'not running'}")

    if not any([mlx_available, ollama_available, pipeline_available]):
        print("\nNo backends running. Start at least one and retry.")
        return

    do_direct = args.mode in ("direct", "all")
    do_pipeline = args.mode in ("pipeline", "all")
    do_personas = args.mode in ("personas", "all")

    t0 = time.time()
    all_results: list[dict] = []

    if do_direct:
        print("\n── Direct Backend Tests ──")
        all_results.extend(
            bench_direct(
                mlx_available,
                ollama_available,
                args.model,
                args.runs,
                args.dry_run,
                cooldown=args.cooldown,
                order=args.order,
            )
        )

    if do_pipeline:
        print("\n── Pipeline Workspace Tests ──")
        all_results.extend(
            bench_pipeline(pipeline_available, args.workspace, args.runs, args.dry_run)
        )

    if do_personas:
        print("\n── Persona Routing Tests ──")
        all_results.extend(
            bench_personas(pipeline_available, args.persona, args.runs, args.dry_run)
        )

    total_time = time.time() - t0

    if not args.dry_run:
        _print_availability_report(mlx_available, ollama_available, pipeline_available, all_results)
        _print_direct_table(all_results)
        _print_pipeline_table(all_results)
        _print_persona_table(all_results)

    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "order": args.order,
        "cooldown_s": args.cooldown,
        "runs_per_model": args.runs,
        "total_wall_time_s": round(total_time, 1),
        "hardware": hw,
        "config_summary": {
            "mlx_models_configured": len(mlx_cfg),
            "ollama_models_configured": len(ollama_cfg),
            "workspaces_configured": len(workspaces_cfg),
            "personas_configured": len(personas_cfg),
        },
        "backends": {
            "mlx": {"url": MLX_URL, "available": mlx_available},
            "ollama": {"url": OLLAMA_URL, "available": ollama_available},
            "pipeline": {"url": PIPELINE_URL, "available": pipeline_available},
        },
        "prompts": {
            "override": args.prompt if args.prompt else None,
            "library": {k: v[:80] + "..." if len(v) > 80 else v for k, v in PROMPTS.items()},
            "workspace_map": WORKSPACE_PROMPT_MAP,
            "group_map": GROUP_PROMPT_MAP,
            "persona_category_map": PERSONA_CATEGORY_PROMPT_MAP,
        },
        "results": all_results,
    }

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    tested = sum(1 for r in all_results if r["runs_success"] > 0)
    available = sum(1 for r in all_results if r.get("available", True))
    print(f"\nTotal: {tested}/{available} passed ({len(all_results)} total) in {total_time:.0f}s")
    print(f"Results: {args.output}")


if __name__ == "__main__":
    main()
