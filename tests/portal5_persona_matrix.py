#!/usr/bin/env python3
"""Portal 5 — Per-(persona, model) persona coverage matrix.

For each workspace-registered persona × each model in the persona's routing
chain, this driver:

  1. Hits Ollama (:11434) DIRECTLY, pinning the
     model in the request body. The pipeline at :9099 is bypassed entirely.
  2. Runs every applicable scenario from the workspace's fixture against
     that (persona, model) pair, with the persona's system prompt loaded.
  3. Aggregates assertion outcomes into PASS / WARN / FAIL per scenario.
  4. Builds a matrix and writes it to tests/benchmarks/results/
     persona_matrix_<workspace>_<UTC>.json + emits a console summary.

Usage:
    python3 tests/portal5_persona_matrix.py                   # full sweep
    python3 tests/portal5_persona_matrix.py --workspace auto-coding
    python3 tests/portal5_persona_matrix.py --persona complianceanalyst
    python3 tests/portal5_persona_matrix.py --model granite4.1
    python3 tests/portal5_persona_matrix.py --backend ollama  # explicit (sole backend)
    python3 tests/portal5_persona_matrix.py --skip-big-models # default skips big_model: true
    python3 tests/portal5_persona_matrix.py --dry-run         # plan only
    python3 tests/portal5_persona_matrix.py --output FILE.json
    python3 tests/portal5_persona_matrix.py --max-scenarios 8 # limit per persona for quick sweeps

Memory discipline:
    Models are loaded one at a time. After all scenarios for a model finish,
    the model is evicted (keep_alive=0). A 5-second cooldown between models
    lets Metal settle. Mirrors bench_tps.py's pattern.

    Models with big_model: true in backends.yaml are skipped by default.
    Pass --include-big-models to test them; expect ≥3 minutes per model
    cold-load.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml

# Repo-relative imports — the driver runs from the repo root
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

# Workspace registry — maps a workspace_id to its matrix configuration.
# Each entry references its own assertion library and fixture loader.
# Add a new workspace here; no other driver changes required.
WORKSPACE_REGISTRY: dict[str, dict[str, str]] = {
    "auto-compliance": {
        "assertions_module": "tests.lib.compliance_assertions",
        "fixtures_module": "tests.lib.compliance_fixtures",
        "persona_categories": ("compliance",),
        "threshold_doc": "docs/COMPLIANCE_FALLBACK_POLICY.md",
    },
    "auto-coding": {
        "assertions_module": "tests.lib.coding_assertions",
        "fixtures_module": "tests.lib.coding_fixtures",
        "persona_categories": ("coding", "software", "development", "systems"),
        "threshold_doc": "docs/CODING_FALLBACK_POLICY.md",
    },
    # Shootout-only registry entry — same assertions and fixtures as auto-coding,
    # but filters by the benchmark persona category so bench-* personas (each
    # pinned to a single model) participate. The Creative Coder system prompt
    # is identical across all bench personas — only the model varies, which is
    # the controlled-experiment shape the shootout requires.
    #
    # models_explicit overrides the production workspace_routing chain. This
    # entry is NOT registered in backends.yaml's workspace_routing table — the
    # shootout is a test harness, not a production routing target. See
    # TASK_CODING_SHOOTOUT_V1.md §A2 and §T3.
    "auto-coding-bench": {
        "assertions_module": "tests.lib.coding_assertions",
        "fixtures_module": "tests.lib.coding_fixtures",
        # persona_categories is retained as a fallback if persona_slugs_explicit is
        # cleared, but V2 routes through the slug list. See A2/A7.
        "persona_categories": ("benchmark",),
        "threshold_doc": "TASK_CODING_SHOOTOUT_V2.md",
        # V2 enumerates the production personas the workspace actually serves,
        # pruned per A3. Categories-based filtering can't express this set
        # because it spans multiple persona categories AND requires exclusions
        # within those categories. See TASK_CODING_SHOOTOUT_V2.md §A2-A4.
        "persona_slugs_explicit": (
            # REPL shape (UAT 0/3 — Laguna's catastrophic miss; javascriptconsole
            # is regression guard, the only REPL persona that PASSed)
            "sqlterminal",
            "linuxterminal",
            "pythoninterpreter",
            "javascriptconsole",
            # Audit shape (UAT 0/2 FAIL on strict contracts; PASS on relaxed)
            "codereviewer",
            "softwarequalityassurancetester",
            "bugdiscoverycodeassistant",
            "codereviewassistant",
            # Composite shape (UAT 0/3 — multi-element output)
            "e2etestauthor",
            "e2edebugger",
            "fullstacksoftwaredeveloper",
            # Ship-It shape (UAT mostly PASS — regression guard)
            "creativecoder",
            "pythoncodegeneratorcleanoptimizedproduction-ready",
            "devopsautomator",
            "githubexpert",
        ),
        # Persona-shape mapping for the analyzer. The matrix's columns are
        # derived from this dict. Keys must match persona_slugs_explicit exactly.
        "persona_shapes": {
            "sqlterminal": "REPL",
            "linuxterminal": "REPL",
            "pythoninterpreter": "REPL",
            "javascriptconsole": "REPL",
            "codereviewer": "Audit",
            "softwarequalityassurancetester": "Audit",
            "bugdiscoverycodeassistant": "Audit",
            "codereviewassistant": "Audit",
            "e2etestauthor": "Composite",
            "e2edebugger": "Composite",
            "fullstacksoftwaredeveloper": "Composite",
            "creativecoder": "Ship-It",
            "pythoncodegeneratorcleanoptimizedproduction-ready": "Ship-It",
            "devopsautomator": "Ship-It",
            "githubexpert": "Ship-It",
        },
        "models_explicit": (
            # V2 incumbents retained for continuity — per-shape delta directly comparable
            "laguna-xs.2:q4_K_M",
            "glm-4.7-flash:q4_K_M",
            "qwen3-coder:30b-a3b-q4_K_M",
            "devstral-small-2",
            # V9 candidates (TASK_V9_EVAL_EXTENDED)
            "hf.co/yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q4_K_M",
            "hf.co/Jackrong/Qwopus3.6-27B-Coder-MTP-GGUF:Qwopus3.6-27B-Coder-MTP-Q5_K_M.gguf",
            # Reference columns — 80B/3B MoE (~46 GB), different weight class.
            # NOT auto-coding repin candidates. Comparison points for the upper tier.
            "qwen3-coder-next",  # auto-agentic production pin
            "hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M",  # auto-spl production pin (V8)
        ),
        # Models that should be flagged in the matrix as "reference" rather than
        # "candidate" — the analyzer excludes these from the overall-column
        # ranking so a reference column dominating doesn't get misread as a
        # repin signal. See A5.
        "models_reference_only": (
            "qwen3-coder-next",
            "hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M",
        ),
    },
}

# Module-level aliases reassigned by run_sweep() based on --workspace.
# Default to compliance modules so any direct importer of run_cell() (e.g.,
# from a test) gets the prior behavior unchanged.
ca = importlib.import_module("tests.lib.compliance_assertions")
cf = importlib.import_module("tests.lib.compliance_fixtures")


def _load_workspace_modules(workspace_id: str):
    """Resolve (assertions, fixtures) modules for a workspace."""
    cfg = WORKSPACE_REGISTRY.get(workspace_id)
    if not cfg:
        raise SystemExit(
            f"workspace '{workspace_id}' not registered in WORKSPACE_REGISTRY. "
            f"Known: {list(WORKSPACE_REGISTRY.keys())}"
        )
    return (
        importlib.import_module(cfg["assertions_module"]),
        importlib.import_module(cfg["fixtures_module"]),
        cfg["persona_categories"],
    )


OLLAMA_URL = "http://localhost:11434"
RESULTS_DIR = _REPO / "tests" / "benchmarks" / "results"

# System prompt cap for matrix driver direct calls. Sized so the largest
# current compliance persona (complianceanalyst at ~5000 chars) has 60%
# headroom. Raise if a persona legitimately exceeds; do not silently
# truncate. See TASK_MATRIX_DRIVER_REMEDIATION_V1 §RC-1.
SYSTEM_PROMPT_CAP_CHARS = 8000

REQUEST_TIMEOUT = 240.0
EVICT_BACKOFF_S = 5.0

# ── Audit-tools mode fixture ──────────────────────────────────────────────
# Sample tool used by --audit-tools to verify per-model tool-call support.
# A single, simple tool definition is sufficient — we're testing whether the
# Ollama API accepts the request and the model emits a structured tool_calls
# response, not whether the model picks the right arguments.
# See TASK_TOOL_SUPPORT_AUDIT_V1 §A14.

AUDIT_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "get_current_time",
        "description": "Get the current time for a city.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "The name of the city"},
            },
            "required": ["city"],
        },
    },
}

AUDIT_PROMPT = "What time is it in Paris right now?"


# ── Backend enumeration ───────────────────────────────────────────────────


def load_backends_yaml() -> dict[str, Any]:
    with open(_REPO / "config" / "backends.yaml") as f:
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
    for f in sorted((_REPO / "config" / "personas").glob("*.yaml")):
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
    for f in sorted((_REPO / "config" / "personas").glob("*.yaml")):
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


async def _chat_direct(
    client: httpx.AsyncClient,
    backend_type: str,
    model_id: str,
    system: str,
    user_prompt: str,
    timeout: float = REQUEST_TIMEOUT,
) -> tuple[int, str]:
    """Direct backend call — pipeline bypassed.

    System prompt cap: 8000 chars. The cap is intentionally well above the
    largest current compliance persona (complianceanalyst at 4963 chars) so
    the OUTPUT CONTRACT section is never silently dropped. Personas longer
    than the cap will hit the assertion in run_cell() with a clear error
    rather than being silently truncated.
    """
    if len(system) > SYSTEM_PROMPT_CAP_CHARS:
        return 0, (
            f"persona system prompt {len(system)} chars exceeds cap "
            f"{SYSTEM_PROMPT_CAP_CHARS}; raise SYSTEM_PROMPT_CAP_CHARS or "
            f"shorten the persona before re-running."
        )

    base_url = OLLAMA_URL
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": user_prompt})
    payload = {
        "model": model_id,
        "messages": msgs,
        "max_tokens": 700,
        "stream": False,
    }
    try:
        r = await client.post(f"{base_url}/v1/chat/completions", json=payload, timeout=timeout)
        if r.status_code != 200:
            return r.status_code, r.text[:300]
        data = r.json()
        msg = data.get("choices", [{}])[0].get("message", {})
        content = msg.get("content", "") or ""
        reasoning = msg.get("reasoning", "") or ""
        return 200, (content + " " + reasoning).strip() if reasoning else content
    except httpx.ReadTimeout:
        return 408, "timeout"
    except Exception as e:
        return 0, str(e)[:200]


async def _audit_tool_support(
    client: httpx.AsyncClient,
    backend_type: str,
    model_id: str,
    timeout: float = REQUEST_TIMEOUT,
) -> dict:
    """Send AUDIT_PROMPT with AUDIT_TOOL_DEFINITION attached and classify the response.

    Returns: {outcome, http_status, detail, elapsed_s}
    outcome ∈ {"tool_call", "text_only", "api_error", "exception"}
    """
    base_url = OLLAMA_URL
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": AUDIT_PROMPT}],
        "tools": [AUDIT_TOOL_DEFINITION],
        "tool_choice": "auto",
        "max_tokens": 200,
        "stream": False,
    }
    t0 = time.time()
    try:
        r = await client.post(f"{base_url}/v1/chat/completions", json=payload, timeout=timeout)
        elapsed = round(time.time() - t0, 2)
        if r.status_code != 200:
            return {
                "outcome": "api_error",
                "http_status": r.status_code,
                "detail": r.text[:300],
                "elapsed_s": elapsed,
            }
        data = r.json()
        msg = data.get("choices", [{}])[0].get("message", {})
        tool_calls = msg.get("tool_calls")
        if tool_calls:
            return {
                "outcome": "tool_call",
                "http_status": 200,
                "detail": f"emitted {len(tool_calls)} tool_call(s); first={tool_calls[0].get('function', {}).get('name')}",
                "elapsed_s": elapsed,
            }
        content = msg.get("content", "") or ""
        return {
            "outcome": "text_only",
            "http_status": 200,
            "detail": f"no tool_calls; text response {len(content)} chars",
            "elapsed_s": elapsed,
        }
    except httpx.ReadTimeout:
        return {
            "outcome": "exception",
            "http_status": 408,
            "detail": "timeout",
            "elapsed_s": round(time.time() - t0, 2),
        }
    except Exception as e:
        return {
            "outcome": "exception",
            "http_status": 0,
            "detail": str(e)[:200],
            "elapsed_s": round(time.time() - t0, 2),
        }


async def run_audit_tools(args) -> dict:
    """Audit-tools sweep: per-(model, backend), verify tool-call support empirically."""
    cfg = load_backends_yaml()
    workspace_id = args.workspace
    chain_models = chain_models_for_workspace(cfg, workspace_id)

    if args.backend == "ollama":
        chain_models = [m for m in chain_models if m["backend_type"] == "ollama"]

    if args.model:
        chain_models = [m for m in chain_models if args.model in m["id"]]

    if not args.include_big_models:
        chain_models = [m for m in chain_models if not m.get("big_model")]

    print(f"\n=== Audit-tools sweep: workspace={workspace_id}, models={len(chain_models)} ===\n")

    results = []
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        for i, m in enumerate(chain_models, 1):
            print(
                f"  [{i}/{len(chain_models)}] {m['backend_type']:6} {m['id'][:60]:60} ... ",
                end="",
                flush=True,
            )
            audit = await _audit_tool_support(client, m["backend_type"], m["id"])
            print(f"{audit['outcome']:10} ({audit['elapsed_s']:5.1f}s)")
            results.append(
                {
                    "model": m["id"],
                    "backend": m["backend_type"],
                    "memory_gb": m.get("memory_gb"),
                    **audit,
                }
            )
            if m["backend_type"] == "ollama":
                await _ollama_unload(client, m["id"])
                await asyncio.sleep(EVICT_BACKOFF_S)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace": workspace_id,
        "audit_prompt": AUDIT_PROMPT,
        "audit_tool": AUDIT_TOOL_DEFINITION["function"]["name"],
        "results": results,
    }

    output = (
        Path(args.output)
        if args.output
        else RESULTS_DIR
        / f"audit_tools_{workspace_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2))

    print("\n=== Summary ===")
    by_outcome: dict[str, int] = {}
    for r in results:
        by_outcome[r["outcome"]] = by_outcome.get(r["outcome"], 0) + 1
    for outcome, count in sorted(by_outcome.items()):
        print(f"  {outcome:12} {count}")
    print(f"\nReport: {output}\n")

    print("Models verified tool-capable (flip supports_tools to true):")
    for r in results:
        if r["outcome"] == "tool_call":
            print(f"  - {r['model']} ({r['backend']})")
    print("\nModels that errored (keep supports_tools false):")
    for r in results:
        if r["outcome"] == "api_error":
            print(f"  - {r['model']} ({r['backend']}): {r['detail'][:80]}")

    return report


async def _ollama_unload(client: httpx.AsyncClient, model_id: str) -> None:
    """Send keep_alive=0 AND wait until Ollama confirms model is evicted.

    Without waiting for confirmation, Ollama keeps the model resident and
    subsequent model loads accumulate, exhausting memory on 64GB systems.
    """
    try:
        await client.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": model_id, "keep_alive": 0, "prompt": ""},
            timeout=10.0,
        )
        # Wait for Ollama to actually free the model's memory
        for _ in range(30):  # 30 × 2s = 60s max wait
            await asyncio.sleep(2.0)
            try:
                r = await client.get(f"{OLLAMA_URL}/api/ps", timeout=5.0)
                models = r.json().get("models", [])
                if not any(m["name"] == model_id for m in models):
                    return  # model successfully evicted
            except Exception:
                pass
    except Exception:
        pass


# ── Per-cell runner ───────────────────────────────────────────────────────


async def run_cell(
    client: httpx.AsyncClient,
    persona: dict[str, Any],
    model: dict[str, Any],
    scenarios: list,
) -> dict[str, Any]:
    persona_slug = persona["slug"]
    system = persona.get("system_prompt", "")
    cell: dict[str, Any] = {
        "persona": persona_slug,
        "model": model["id"],
        "backend": model["backend_type"],
        "group": model["group"],
        "scenarios": [],
        "summary": {"PASS": 0, "WARN": 0, "FAIL": 0, "ERROR": 0},
    }

    applicable = [s for s in scenarios if s.persona_slug == persona_slug]
    if not applicable:
        return cell

    for scenario in applicable:
        t0 = time.time()
        code, response = await _chat_direct(
            client,
            backend_type=model["backend_type"],
            model_id=model["id"],
            system=system,
            user_prompt=scenario.prompt,
        )
        elapsed = time.time() - t0

        if code != 200:
            cell["scenarios"].append(
                {
                    "id": scenario.scenario_id,
                    "framework": scenario.framework_id,
                    "status": "ERROR",
                    "http_status": code,
                    "detail": f"HTTP {code}: {response[:120]}",
                    "response_preview": response[:800],
                    "elapsed_s": round(elapsed, 2),
                }
            )
            cell["summary"]["ERROR"] += 1
            continue

        outcome = cf.run_assertions(scenario, response)
        results_payload = [
            {
                "name": r.name,
                "passed": r.passed,
                "severity": r.severity,
                "detail": r.detail[:200],
            }
            for r in outcome.results
        ]
        cell["scenarios"].append(
            {
                "id": scenario.scenario_id,
                "framework": scenario.framework_id,
                "status": outcome.status,
                "http_status": 200,
                "results": results_payload,
                "response_chars": len(response),
                "response_preview": response[:800],
                "elapsed_s": round(elapsed, 2),
                "tps": round(len(response) / elapsed, 1) if elapsed > 0 else 0.0,
            }
        )
        cell["summary"][outcome.status] += 1
        await asyncio.sleep(0.2)

    return cell


# ── Sweep orchestrator ────────────────────────────────────────────────────


async def run_sweep(args) -> dict[str, Any]:
    cfg = load_backends_yaml()

    workspace_id = args.workspace
    ca_module, cf_module, persona_categories = _load_workspace_modules(workspace_id)

    # Driver-wide aliases so the rest of run_sweep doesn't change.
    global ca, cf
    ca = ca_module
    cf = cf_module

    # If the registry entry pins specific persona slugs (V2 capability survey),
    # bypass the category-based loader and load exactly those slugs in order.
    # Otherwise fall through to the production category-filtered loader.
    # See TASK_CODING_SHOOTOUT_V2.md §A2 / §A7.
    _ws_cfg = WORKSPACE_REGISTRY.get(workspace_id, {})
    _persona_slugs_explicit = _ws_cfg.get("persona_slugs_explicit")
    if _persona_slugs_explicit:
        personas = load_personas_by_slugs(_persona_slugs_explicit)
    else:
        personas = load_personas_for_workspace(workspace_id, persona_categories)

    if args.persona:
        personas = [p for p in personas if args.persona in p["slug"]]
        if not personas:
            print(f"no persona matched filter '{args.persona}'", file=sys.stderr)
            sys.exit(2)

    # If the registry entry pins specific models, use them (shootout harness).
    # Otherwise fall through to the production workspace_routing chain.
    # See TASK_CODING_SHOOTOUT_V1.md §T3.
    _ws_cfg = WORKSPACE_REGISTRY.get(workspace_id, {})
    _models_explicit = _ws_cfg.get("models_explicit")
    if _models_explicit:
        # Build the chain by looking up each named model in backends.yaml.
        # An explicit model that is not registered is a hard error — fail
        # fast rather than silently producing partial results.
        all_models: dict[str, dict[str, Any]] = {}
        for be in cfg.get("backends", []):
            if True:
                for mid in be.get("models", []):
                    model_id = mid["id"] if isinstance(mid, dict) else mid
                    all_models[model_id] = {
                        "id": model_id,
                        "backend_type": "ollama",
                        "big_model": False,
                        "is_vlm": False,
                        "memory_gb": _ollama_size_estimate(model_id),
                        "group": be.get("group", "general"),
                    }
        chain = []
        missing = []
        for mid in _models_explicit:
            if mid in all_models:
                chain.append(all_models[mid])
            else:
                missing.append(mid)
        if missing:
            print(
                f"workspace '{workspace_id}' models_explicit references unregistered "
                f"models (not found in backends.yaml): {missing}",
                file=sys.stderr,
            )
            sys.exit(4)
    else:
        chain = chain_models_for_workspace(cfg, workspace_id)

    if args.backend:
        chain = [m for m in chain if m["backend_type"] == args.backend]
    if args.model:
        chain = [m for m in chain if args.model in m["id"]]
    if not args.include_big_models:
        chain = [m for m in chain if not m["big_model"]]

    chain.sort(key=lambda m: m["memory_gb"])

    if args.require:
        required = [r.strip() for r in args.require.split(",") if r.strip()]
        chain_ids = [m["id"] for m in chain]
        missing = [r for r in required if not any(r in cid for cid in chain_ids)]
        if missing:
            print(
                f"REQUIRED models missing from resolved chain: {missing}\n"
                f"Available models in chain: {chain_ids}",
                file=sys.stderr,
            )
            sys.exit(3)

    # Thread the workspace's persona_categories down into the fixtures loader so
    # auto-coding (production) and auto-coding-bench (shootout) load different
    # persona sets from the same coding_scenarios.yaml. See
    # TASK_CODING_SHOOTOUT_V1.md §T1.5 for rationale.
    _ws_cfg = WORKSPACE_REGISTRY.get(args.workspace, {})
    _persona_categories = tuple(_ws_cfg.get("persona_categories", ()))
    # Only the coding fixtures module accepts a categories kwarg; the
    # compliance fixtures select personas from the fixture YAML itself.
    # Guard on the signature so workspaces with persona_categories but a
    # non-parameterised fixtures module (auto-compliance) don't TypeError.
    import inspect as _inspect

    _accepts_categories = "categories" in _inspect.signature(cf.expand_scenarios).parameters
    if _persona_categories and _accepts_categories:
        scenarios = list(cf.expand_scenarios(categories=_persona_categories))
    else:
        scenarios = list(cf.expand_scenarios())
    if args.max_scenarios:
        kept: dict[str, int] = {}
        scenarios = [
            s
            for s in scenarios
            if (
                kept.setdefault(s.persona_slug, 0) < args.max_scenarios
                and not kept.update({s.persona_slug: kept[s.persona_slug] + 1})
            )
        ]

    plan = {
        "workspace": workspace_id,
        "personas": [p["slug"] for p in personas],
        "models": [
            {
                "id": m["id"],
                "backend": m["backend_type"],
                "group": m["group"],
                "big_model": m["big_model"],
                "memory_gb": m["memory_gb"],
            }
            for m in chain
        ],
        "scenarios_total": len(scenarios),
        "cells_total": len(personas) * len(chain),
    }

    print(f"\n=== PERSONA MATRIX SWEEP — workspace={workspace_id} ===")
    print(f"  personas:  {len(personas)}  ({', '.join(plan['personas'])})")
    print(f"  models:    {len(chain)}  (smallest-first)")
    print(f"  scenarios: {len(scenarios)}")
    print(f"  cells:     {plan['cells_total']}")
    if args.dry_run:
        print("\nDRY RUN — exiting without execution.")
        for m in chain:
            print(
                f"    {m['backend_type']:6}  {m['id']:60}  {m['memory_gb']:5.1f}GB  group={m['group']}"
            )
        return {"plan": plan, "cells": []}

    results: list[dict[str, Any]] = []
    started = time.time()

    async with httpx.AsyncClient() as client:
        for mi, model in enumerate(chain, start=1):
            print(
                f"\n  [{mi}/{len(chain)}] model: {model['backend_type']}/{model['id']}  ({model['memory_gb']:.1f}GB)"
            )
            # Pre-model cleanup: evict ALL Ollama models to ensure only one
            # model is resident at a time. Without this, Ollama accumulates
            # models and exhausts 64GB unified memory mid-sweep.
            if model["backend_type"] == "ollama" and mi > 1:
                try:
                    r = await client.get(f"{OLLAMA_URL}/api/ps", timeout=5.0)
                    for m in r.json().get("models", []):
                        await _ollama_unload(client, m["name"])
                except Exception:
                    pass
            for pi, persona in enumerate(personas, start=1):
                pre = time.time()
                cell = await run_cell(client, persona, model, scenarios)
                summary = cell["summary"]
                el = time.time() - pre
                print(
                    f"    [{pi}/{len(personas)}] {persona['slug']:35}"
                    f"  PASS={summary['PASS']:3} WARN={summary['WARN']:2}"
                    f" FAIL={summary['FAIL']:2} ERR={summary['ERROR']:2}"
                    f"  ({el:.1f}s)"
                )
                results.append(cell)

            if model["backend_type"] == "ollama":
                await _ollama_unload(client, model["id"])
            await asyncio.sleep(EVICT_BACKOFF_S)

    elapsed = time.time() - started
    print(f"\n=== SWEEP COMPLETE — {elapsed:.0f}s ===")

    return {
        "schema": "portal5.persona_matrix.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": round(elapsed, 1),
        "plan": plan,
        "cells": results,
    }


# ── Console summary table ─────────────────────────────────────────────────


def render_matrix_table(report: dict[str, Any]) -> str:
    cells = report["cells"]
    if not cells:
        return "(no cells — dry run or empty plan)"

    personas = sorted({c["persona"] for c in cells})
    models = []
    seen: set[tuple[str, str]] = set()
    for c in cells:
        key = (c["backend"], c["model"])
        if key not in seen:
            seen.add(key)
            models.append((c["backend"], c["model"]))

    by_pm: dict[tuple[str, str, str], dict[str, int]] = {}
    for c in cells:
        by_pm[(c["persona"], c["backend"], c["model"])] = c["summary"]

    def short(model: str) -> str:
        return model.split("/")[-1][:24]

    persona_w = max(len(p) for p in personas) + 1
    lines = []
    header = " " * persona_w + " | " + " | ".join(short(m) for _, m in models)
    lines.append(header)
    lines.append("-" * len(header))
    for p in personas:
        cells_for_p = []
        for be, m in models:
            s = by_pm.get((p, be, m), {})
            label = f"P{s.get('PASS', 0)}/W{s.get('WARN', 0)}/F{s.get('FAIL', 0)}" if s else "-"
            cells_for_p.append(label.ljust(24))
        lines.append(p.ljust(persona_w) + " | " + " | ".join(cells_for_p))
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument(
        "--workspace",
        default="auto-compliance",
        choices=tuple(WORKSPACE_REGISTRY.keys()),
        help=(
            "Which workspace's chain to sweep. Default: auto-compliance. "
            "Each workspace has its own fixture + assertion library + "
            "threshold doc registered in WORKSPACE_REGISTRY."
        ),
    )
    p.add_argument("--persona", help="filter persona slugs by substring")
    p.add_argument("--model", help="filter model ids by substring")
    p.add_argument(
        "--backend",
        choices=("ollama",),
        help="restrict to one backend type",
    )
    p.add_argument(
        "--include-big-models",
        action="store_true",
        help="include models flagged big_model: true (default: skip)",
    )
    p.add_argument(
        "--require",
        default="",
        help=(
            "comma-separated list of model substrings that MUST appear in "
            "the resolved chain (after filters). Driver exits non-zero "
            "before running if any required model is absent. Example: "
            "--require granite4.1:8b,granite4.1:30b"
        ),
    )
    p.add_argument(
        "--max-scenarios",
        type=int,
        default=0,
        help="cap scenarios per persona (0 = no cap, default)",
    )
    p.add_argument("--dry-run", action="store_true", help="print plan and exit")
    p.add_argument(
        "--audit-tools",
        action="store_true",
        help="Per-model tool-call verification mode. Skips persona/scenario "
        "fixtures; sends AUDIT_PROMPT with AUDIT_TOOL_DEFINITION attached "
        "and classifies the response. See TASK_TOOL_SUPPORT_AUDIT_V1 §A14.",
    )
    p.add_argument(
        "--output",
        help="JSON output path (default: results dir UTC-stamped)",
    )
    p.add_argument(
        "--baseline-compare",
        default="",
        help=(
            "Path to an existing matrix-result JSON to diff this run against. "
            "After the sweep completes, the driver runs the diff equivalent "
            "of `tests/persona_matrix_diff.py baseline.json this_run.json` "
            "and prints regressions to stderr. Exits non-zero if any "
            "regression exceeds --regression-threshold."
        ),
    )
    p.add_argument(
        "--regression-threshold",
        type=float,
        default=10.0,
        help=(
            "Per-(persona, model) PASS-rate drop in percentage points that "
            "counts as a regression. Default: 10.0. Used only with "
            "--baseline-compare."
        ),
    )
    return p.parse_args(argv)


async def amain(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.audit_tools:
        await run_audit_tools(args)
        return 0
    report = await run_sweep(args)

    if args.dry_run:
        return 0

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = (
        Path(args.output)
        if args.output
        else RESULTS_DIR / f"persona_matrix_{args.workspace}_{ts}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))
    print(f"\nwrote {out_path}")
    print("\n--- MATRIX (PASS/WARN/FAIL per cell) ---")
    print(render_matrix_table(report))

    # Inline diff-vs-baseline (TASK 007 §2.4).
    regressions: list[str] = []
    if args.baseline_compare:
        try:
            from tests.persona_matrix_diff import compute_regressions  # noqa: E402

            regressions = compute_regressions(
                Path(args.baseline_compare),
                report,
                threshold_pp=args.regression_threshold,
            )
        except Exception as e:
            print(f"baseline-compare failed: {e}", file=sys.stderr)

    if regressions:
        print(
            f"\n--- REGRESSIONS vs baseline (threshold {args.regression_threshold:.1f}pp) ---",
            file=sys.stderr,
        )
        for line in regressions:
            print(f"  {line}", file=sys.stderr)

    any_fail = any(c["summary"].get("FAIL", 0) > 0 for c in report["cells"])
    if regressions:
        return 2 if any_fail else 1
    return 1 if any_fail else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(amain()))
