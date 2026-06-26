#!/usr/bin/env python3
"""Router conditions benchmark — 3 router candidates × 4 VRAM load scenarios.

Answers: does VRAM pressure from inference models cause the router to be evicted,
and how badly does that hurt routing quality and latency under real-world conditions?

Router candidates tested:
  hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M  (5.3GB — primary)
  llama3.2:3b                                                  (~2GB  — standby)
  qwen2.5:1.5b                                                 (1GB   — fallback)

Scenarios (run per router, each fully isolated with a clean VRAM state):

  isolated      — router alone; no companions loaded.
                  Establishes warm accuracy + latency baseline.

  one_peer      — router + one inference companion.
                  Tests shared-VRAM accuracy; minimal eviction risk.

  eviction_test — router pre-warmed FIRST, then two companions loaded.
                  Mirrors real operation: pipeline starts → router warms → users
                  load large inference models. With MAX_LOADED=2 the router is
                  evicted by the second companion; with MAX_LOADED=3 it survives.
                  First-request latency after companion load reveals cold-load cost.

  cold_entry    — two companions pre-loaded, router never warmed.
                  Measures: how long does a cold router load take? How many
                  production-timeout failures occur before router is warm?

Key outputs per (router, scenario):
  accuracy / security accuracy / abstain accuracy
  p50 / p95 latency (warm requests)
  first-request latency (cold-load indicator)
  eviction detected (bool)
  cold-load time ms (measured with 60s probe before production-timeout runs)
  timeout count (requests that exceeded LLM_ROUTER_TIMEOUT_MS)

Usage:
    # Full bench — all 3 routers × 4 scenarios (auto-detect companions)
    python3 tests/benchmarks/bench_router_conditions.py

    # Specify companion models explicitly
    python3 tests/benchmarks/bench_router_conditions.py \\
        --companions qwen2.5:7b devstral:latest

    # Skip specific scenarios
    python3 tests/benchmarks/bench_router_conditions.py --skip cold_entry

    # Test a single router
    python3 tests/benchmarks/bench_router_conditions.py --router obliterated

    # Save results
    python3 tests/benchmarks/bench_router_conditions.py \\
        --output tests/benchmarks/results/conditions_$(date +%Y%m%dT%H%M%S).json

    # Dry run — show what would be tested
    python3 tests/benchmarks/bench_router_conditions.py --dry-run

Run twice to compare MAX_LOADED_MODELS=2 vs MAX_LOADED_MODELS=3:
    # First: set OLLAMA_MAX_LOADED_MODELS=2 in .env, ./launch.sh rebuild, run bench
    # Then:  set OLLAMA_MAX_LOADED_MODELS=3 in .env, ./launch.sh rebuild, run bench
    # Compare timeout counts in eviction_test scenario — the key signal.

Requirements:
    Ollama running at OLLAMA_URL (default http://localhost:11434).
    Router candidate models already pulled via ollama pull.
    At least one companion model available (5-25GB preferred).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

# ── Bootstrap: reuse bench_router golden set + routing infrastructure ─────────
_HERE = Path(__file__).resolve().parent
_bench_router_path = _HERE / "bench_router.py"

try:
    _spec = importlib.util.spec_from_file_location("bench_router", _bench_router_path)
    _br = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
    _spec.loader.exec_module(_br)  # type: ignore[union-attr]
    GOLDEN_SET = _br.GOLDEN_SET
    _load_routing_config = _br._load_routing_config
    _build_schema = _br._build_schema
    _build_prompt = _br._build_prompt
    score_results = _br.score_results
except Exception as e:
    print(f"ERROR: could not load bench_router.py: {e}", file=sys.stderr)
    sys.exit(1)

# ── Notification support ──────────────────────────────────────────────────────
try:
    from tests.benchmarks.bench.notify import _send_bench_notification  # type: ignore[import]
except ImportError:
    def _send_bench_notification(message: str, title: str = "Portal 5 Bench") -> None:  # type: ignore[misc]
        pass

# ── Config ────────────────────────────────────────────────────────────────────

OLLAMA_URL: str = os.environ.get("OLLAMA_URL", "http://localhost:11434")
PRODUCTION_TIMEOUT_MS: int = int(os.environ.get("LLM_ROUTER_TIMEOUT_MS", "1000"))
COLD_LOAD_PROBE_TIMEOUT_S: float = 60.0   # extended timeout for cold-load measurement
COMPANION_WAIT_TIMEOUT_S: float = 120.0   # wait for companion to appear in /api/ps
CONFIDENCE_THRESHOLD: float = 0.5

ROUTER_CANDIDATES: list[dict[str, Any]] = [
    {
        "key": "obliterated",
        "model": "hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M",
        "label": "OBLITERATED E4B",
        "vram_gb": 5.3,
        "role": "primary",
        "timeout_ms": 1000,
    },
    {
        "key": "llama3b",
        "model": "llama3.2:3b",
        "label": "llama3.2:3b",
        "vram_gb": 2.0,
        "role": "standby",
        "timeout_ms": 500,
    },
    {
        "key": "qwen15b",
        "model": "qwen2.5:1.5b",
        "label": "qwen2.5:1.5b",
        "vram_gb": 1.0,
        "role": "fallback",
        "timeout_ms": 500,
    },
]

SCENARIO_KEYS: list[str] = ["isolated", "one_peer", "eviction_test", "cold_entry"]


# ── Ollama management ─────────────────────────────────────────────────────────

def get_loaded_models(client: httpx.Client) -> list[dict[str, Any]]:
    try:
        resp = client.get(f"{OLLAMA_URL}/api/ps", timeout=10.0)
        resp.raise_for_status()
        return resp.json().get("models", [])
    except Exception:
        return []


def get_available_models(client: httpx.Client) -> list[dict[str, Any]]:
    try:
        resp = client.get(f"{OLLAMA_URL}/api/tags", timeout=10.0)
        resp.raise_for_status()
        return resp.json().get("models", [])
    except Exception:
        return []


def _model_name_matches(name: str, target: str) -> bool:
    """Fuzzy match: 'llama3.2:3b' matches 'llama3.2:3b', also handles hf.co/ prefix."""
    if name == target:
        return True
    # Strip hf.co/ prefix for comparison
    name_base = name.split("/")[-1]
    target_base = target.split("/")[-1]
    return name_base == target_base or name_base in target or target_base in name


def is_model_loaded(client: httpx.Client, model: str) -> bool:
    for m in get_loaded_models(client):
        if _model_name_matches(m.get("name", ""), model):
            return True
    return False


def is_model_available(client: httpx.Client, model: str) -> bool:
    for m in get_available_models(client):
        if _model_name_matches(m.get("name", ""), model):
            return True
    return False


def load_model(client: httpx.Client, model: str, timeout_s: float = 120.0) -> float:
    """Send a minimal generate request to load model into VRAM. Returns elapsed ms."""
    t0 = time.monotonic()
    try:
        client.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": model,
                "prompt": "ok",
                "stream": False,
                "keep_alive": -1,
                "options": {"num_predict": 1},
            },
            timeout=timeout_s,
        )
    except Exception:
        pass
    return (time.monotonic() - t0) * 1000.0


def unload_model(client: httpx.Client, model: str) -> None:
    """Unload model from VRAM via keep_alive=0."""
    try:
        client.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": model, "prompt": "", "keep_alive": 0},
            timeout=15.0,
        )
    except Exception:
        pass


def unload_all(client: httpx.Client) -> None:
    """Unload all currently loaded models and wait for VRAM to drain."""
    for m in get_loaded_models(client):
        name = m.get("name", "")
        if name:
            unload_model(client, name)
    time.sleep(3.0)


def wait_for_model_loaded(
    client: httpx.Client, model: str, timeout_s: float = 60.0
) -> bool:
    """Poll /api/ps until model appears or timeout. Returns True if found."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if is_model_loaded(client, model):
            return True
        time.sleep(1.0)
    return False


def measure_cold_load(
    client: httpx.Client,
    model: str,
    schema: dict[str, Any],
    prompt: str,
) -> float:
    """Fire one routing request with extended timeout to measure cold-load time.

    Returns elapsed ms including the full model load. Used when a model is known
    to be cold (not in /api/ps) before the production-timeout test run begins.
    """
    t0 = time.monotonic()
    try:
        client.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "keep_alive": -1,
                "options": {"temperature": 0, "num_predict": 40, "num_ctx": 2048},
                "format": schema,
            },
            timeout=COLD_LOAD_PROBE_TIMEOUT_S,
        )
    except Exception:
        pass
    return (time.monotonic() - t0) * 1000.0


# ── Companion selection ───────────────────────────────────────────────────────

def select_companions(
    client: httpx.Client,
    router_models: list[str],
    override: list[str] | None = None,
    count: int = 2,
) -> list[dict[str, Any]]:
    """Select companion models for load scenarios.

    Companions simulate inference models already loaded in the fleet. Prefers
    models in the 2-25GB range. Excludes router candidates.

    Args:
        override: If provided, use these model names (must already be pulled).
        count: Number of companions to select (2 = full fleet pressure test).
    """
    if override:
        result = []
        for m in override[:count]:
            if not is_model_available(client, m):
                print(f"  WARNING: companion '{m}' not available in Ollama — skipping", file=sys.stderr)
            else:
                result.append({"name": m, "size_gb": 0.0})
        return result

    router_bases = set()
    for r in router_models:
        router_bases.add(r)
        router_bases.add(r.split("/")[-1])

    available = get_available_models(client)
    candidates: list[dict[str, Any]] = []
    for m in available:
        name = m.get("name", "")
        size_bytes = m.get("size", 0)
        size_gb = size_bytes / 1e9
        # Exclude router candidates
        if any(_model_name_matches(name, r) for r in router_bases):
            continue
        # Prefer realistic inference model sizes
        if 2.0 <= size_gb <= 25.0:
            candidates.append({"name": name, "size_gb": round(size_gb, 1), "size": size_bytes})

    candidates.sort(key=lambda x: x["size"], reverse=True)
    selected = candidates[:count]

    if not selected:
        # Fallback: take any model that isn't a router candidate
        for m in available:
            name = m.get("name", "")
            if any(_model_name_matches(name, r) for r in router_bases):
                continue
            selected.append({"name": name, "size_gb": round(m.get("size", 0) / 1e9, 1)})
            if len(selected) >= count:
                break

    return selected


# ── Router (mirrors production routing.py) ───────────────────────────────────

def route_one(
    client: httpx.Client,
    model: str,
    prompt: str,
    schema: dict[str, Any],
    valid_ids: frozenset[str],
    timeout_s: float,
) -> tuple[str | None, float, float, str]:
    """Send one routing request. Returns (workspace, confidence, elapsed_ms, error)."""
    t0 = time.monotonic()
    try:
        resp = client.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "keep_alive": -1,
                "options": {"temperature": 0, "num_predict": 40, "num_ctx": 2048},
                "format": schema,
            },
            timeout=httpx.Timeout(timeout_s + 2.0, connect=5.0),
        )
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        resp.raise_for_status()
        parsed = json.loads(resp.json().get("response", "").strip())
        workspace = str(parsed.get("workspace", "")).strip()
        confidence = float(parsed.get("confidence", 0.0))
        if workspace not in valid_ids:
            return None, 0.0, elapsed_ms, f"unknown workspace '{workspace}'"
        if confidence < CONFIDENCE_THRESHOLD:
            return None, confidence, elapsed_ms, f"low confidence {confidence:.2f}"
        return workspace, confidence, elapsed_ms, ""
    except httpx.TimeoutException:
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        return None, 0.0, elapsed_ms, "TIMEOUT"
    except Exception as exc:
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        return None, 0.0, elapsed_ms, str(exc)[:80]


# ── Scenario runner ───────────────────────────────────────────────────────────

def run_scenario(
    client: httpx.Client,
    router: dict[str, Any],
    scenario_key: str,
    companions: list[dict[str, Any]],
    schema: dict[str, Any],
    prompts: list[str],
    valid_ids: frozenset[str],
) -> dict[str, Any]:
    """Run all GOLDEN_SET tests for one (router, scenario) combination.

    Returns a result dict with per-test rows + summary stats + scenario metadata.
    """
    model = router["model"]
    timeout_s = router["timeout_ms"] / 1000.0
    c1 = companions[0]["name"] if len(companions) >= 1 else None
    c2 = companions[1]["name"] if len(companions) >= 2 else None

    print(f"\n  ── {scenario_key.upper()} {'─'*55}")

    # ── Setup: bring VRAM to the required state ────────────────────────────────
    print("     Setup: clearing all models from VRAM...", end=" ", flush=True)
    unload_all(client)
    print("done")

    if scenario_key == "isolated":
        # Router alone
        print(f"     Loading router ({router['label']})...", end=" ", flush=True)
        load_model(client, model)
        router_warm_before = is_model_loaded(client, model)
        print("✓" if router_warm_before else "✗ (not confirmed in /api/ps)")

    elif scenario_key == "one_peer":
        # Companion first, then router
        if c1:
            print(f"     Loading companion: {c1}...", end=" ", flush=True)
            load_model(client, c1)
            print("✓" if is_model_loaded(client, c1) else "✗")
        print(f"     Loading router ({router['label']})...", end=" ", flush=True)
        load_model(client, model)
        router_warm_before = is_model_loaded(client, model)
        print("✓" if router_warm_before else "✗")

    elif scenario_key == "eviction_test":
        # Router warmed FIRST, then companions loaded — the eviction scenario
        print(f"     Loading router ({router['label']}) first...", end=" ", flush=True)
        load_model(client, model)
        confirmed = is_model_loaded(client, model)
        print("✓" if confirmed else "✗")
        if c1:
            print(f"     Loading companion 1: {c1}...", end=" ", flush=True)
            load_model(client, c1)
            print("✓" if is_model_loaded(client, c1) else "✗")
        if c2:
            print(f"     Loading companion 2: {c2}...", end=" ", flush=True)
            load_model(client, c2)
            print("✓" if is_model_loaded(client, c2) else "✗")
        # Now check if router survived
        router_warm_before = is_model_loaded(client, model)
        evicted_msg = "EVICTED ⚠️" if not router_warm_before else "still loaded ✓"
        print(f"     Router status after companion load: {evicted_msg}")

    elif scenario_key == "cold_entry":
        # Companions loaded first, router never warmed — cold-start test
        if c1:
            print(f"     Loading companion 1: {c1}...", end=" ", flush=True)
            load_model(client, c1)
            print("✓" if is_model_loaded(client, c1) else "✗")
        if c2:
            print(f"     Loading companion 2: {c2}...", end=" ", flush=True)
            load_model(client, c2)
            print("✓" if is_model_loaded(client, c2) else "✗")
        router_warm_before = False  # by design

    else:
        router_warm_before = False

    # ── Capture what's loaded ─────────────────────────────────────────────────
    loaded_snapshot = [m.get("name", "") for m in get_loaded_models(client)]
    evicted = not router_warm_before
    print(f"     VRAM state: {loaded_snapshot or ['(empty)']}")

    # ── Cold-load probe ───────────────────────────────────────────────────────
    # If router is NOT in VRAM, measure how long it takes to cold-load before
    # running production-timeout tests. This isolates the cold-load cost from
    # the accuracy measurement.
    cold_load_ms: float = 0.0
    if evicted:
        print(
            f"     Router cold — measuring load time (up to {COLD_LOAD_PROBE_TIMEOUT_S:.0f}s)...",
            end=" ",
            flush=True,
        )
        cold_load_ms = measure_cold_load(client, model, schema, prompts[0])
        warm_now = is_model_loaded(client, model)
        print(f"{cold_load_ms:.0f}ms  {'(warm ✓)' if warm_now else '(still cold ✗)'}")

    # ── Run GOLDEN_SET with production timeout ────────────────────────────────
    n = len(GOLDEN_SET)
    rows: list[dict[str, Any]] = []
    print(f"     Running {n} tests (timeout={router['timeout_ms']}ms)...")

    for i, (msg, expected, cat, note) in enumerate(GOLDEN_SET):
        workspace, confidence, elapsed_ms, error = route_one(
            client, model, prompts[i], schema, valid_ids, timeout_s
        )

        if workspace == expected or workspace is None and expected == "auto":
            result = "correct"
        elif workspace is None:
            result = "abstained"
        else:
            result = "wrong"

        symbol = "✓" if result == "correct" else ("·" if result == "abstained" else "✗")
        latency_flag = "  ⚠SLOW" if elapsed_ms > router["timeout_ms"] else ""
        ws_disp = workspace or ("(timeout)" if error == "TIMEOUT" else "(fallback)")
        print(
            f"     {i+1:2d}/{n} {symbol} [{cat[:3]:3s}] {expected:26s}"
            f"  → {ws_disp:26s}  {elapsed_ms:6.0f}ms{latency_flag}"
        )

        rows.append({
            "message": msg,
            "expected": expected,
            "got": workspace,
            "confidence": confidence,
            "elapsed_ms": round(elapsed_ms, 1),
            "result": result,
            "category": cat,
            "error": error,
            "notes": note,
        })

    stats = score_results(rows)

    # First-request latency (first row, which reveals cold-load if evicted and probe failed)
    first_req_ms = rows[0]["elapsed_ms"] if rows else 0.0

    print(
        f"\n     RESULT  acc={stats['accuracy_pct']} ({stats['accuracy']*100:.1f}%)  "
        f"sec={stats['security_accuracy']*100:.1f}%  "
        f"p50={stats['p50_ms']:.0f}ms  p95={stats['p95_ms']:.0f}ms  "
        f"TO={stats['timeout_count']}"
    )
    if evicted:
        print(f"     ⚠️  EVICTED  cold-load={cold_load_ms:.0f}ms  first-req={first_req_ms:.0f}ms")

    return {
        "scenario": scenario_key,
        "router_model": model,
        "router_label": router["label"],
        "router_role": router["role"],
        "router_vram_gb": router["vram_gb"],
        "timeout_ms": router["timeout_ms"],
        "companions_loaded": loaded_snapshot,
        "router_warm_before_tests": router_warm_before,
        "evicted": evicted,
        "cold_load_ms": round(cold_load_ms, 1),
        "first_request_ms": round(first_req_ms, 1),
        "stats": stats,
        "rows": rows,
    }


# ── Full bench runner ─────────────────────────────────────────────────────────

def run_conditions_bench(
    routers: list[dict[str, Any]],
    companions: list[dict[str, Any]],
    scenarios: list[str],
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    descriptions, examples = _load_routing_config()
    if not descriptions:
        print("ERROR: routing_descriptions.json empty — check ROUTING_CONFIG_DIR", file=sys.stderr)
        sys.exit(1)

    try:
        _repo_root = Path(__file__).resolve().parent.parent.parent
        sys.path.insert(0, str(_repo_root))
        from portal_pipeline.router.workspaces import WORKSPACES  # type: ignore[import]
        valid_ids = frozenset(k for k in WORKSPACES if not k.startswith("bench-"))
    except ImportError:
        valid_ids = frozenset(descriptions.keys())

    schema = _build_schema(valid_ids)

    # Pre-build prompts (same prompt reused across all scenarios for a given test)
    prompts = [_build_prompt(msg, descriptions, examples) for msg, _, _, _ in GOLDEN_SET]

    if dry_run:
        print(f"\nDRY RUN  {len(routers)} routers × {len(scenarios)} scenarios × {len(GOLDEN_SET)} tests")
        print("\nRouter candidates:")
        for r in routers:
            print(f"  [{r['role']:8s}]  {r['label']:35s}  {r['vram_gb']}GB  timeout={r['timeout_ms']}ms")
        print(f"\nScenarios: {scenarios}")
        print("\nCompanion models:")
        for c in companions:
            size_str = f"  ({c['size_gb']:.1f}GB)" if c.get("size_gb") else ""
            print(f"  {c['name']}{size_str}")
        print(f"\nTest cases: {len(GOLDEN_SET)}")
        return []

    all_results: list[dict[str, Any]] = []

    _send_bench_notification(
        f"Router conditions bench — {len(routers)} routers × {len(scenarios)} scenarios\n"
        f"Routers: {', '.join(r['label'] for r in routers)}\n"
        f"Companions: {', '.join(c['name'] for c in companions)}\n"
        f"Scenarios: {', '.join(scenarios)}",
        title="🔀 Router Conditions — START",
    )

    bench_start = time.monotonic()

    with httpx.Client() as client:
        for router in routers:
            print(f"\n{'═'*80}")
            print(f"ROUTER: {router['label']}  ({router['role']}, {router['vram_gb']}GB, timeout={router['timeout_ms']}ms)")
            print(f"MODEL:  {router['model']}")
            print(f"{'═'*80}")

            if not is_model_available(client, router["model"]):
                print(f"  ✗ SKIPPED — model not available in Ollama (run: ollama pull {router['model']})")
                continue

            router_results: list[dict[str, Any]] = []

            for scenario_key in scenarios:
                result = run_scenario(
                    client=client,
                    router=router,
                    scenario_key=scenario_key,
                    companions=companions,
                    schema=schema,
                    prompts=prompts,
                    valid_ids=valid_ids,
                )
                router_results.append(result)
                all_results.append(result)

            # Per-router summary notification
            lines = []
            for r in router_results:
                s = r["stats"]
                evict_str = "  EVICTED" if r["evicted"] else ""
                lines.append(
                    f"  {r['scenario']:15s}  acc={s['accuracy']*100:.0f}%  "
                    f"sec={s['security_accuracy']*100:.0f}%  "
                    f"p50={s['p50_ms']:.0f}ms  TO={s['timeout_count']}{evict_str}"
                )
            _send_bench_notification(
                f"{router['label']} ({router['vram_gb']}GB)\n" + "\n".join(lines),
                title=f"🔀 Conditions — {router['label']} done",
            )

    elapsed_total = time.monotonic() - bench_start
    print(f"\n\nTotal elapsed: {elapsed_total/60:.1f} min")

    _send_bench_notification(
        f"Conditions bench complete  {elapsed_total/60:.1f}min\n"
        f"{len(routers)} routers × {len(scenarios)} scenarios × {len(GOLDEN_SET)} tests",
        title="🔀 Router Conditions — DONE",
    )

    return all_results


# ── Summary printer ───────────────────────────────────────────────────────────

def print_summary(all_results: list[dict[str, Any]]) -> None:
    if not all_results:
        return

    print(f"\n\n{'━'*100}")
    print("SUMMARY TABLE  —  router × scenario")
    print(f"{'━'*100}")

    header = (
        f"{'Router':20s}  {'Role':8s}  {'VRAM':4s}  {'Scenario':15s}  "
        f"{'Acc':>6}  {'Sec':>5}  {'p50ms':>6}  {'p95ms':>6}  {'TO':>4}  "
        f"{'Evicted':8}  {'ColdLoadMs':>10}"
    )
    print(header)
    print("─" * 100)

    # Group by router for visual separation
    current_router = None
    for r in all_results:
        if r["router_label"] != current_router:
            if current_router is not None:
                print()
            current_router = r["router_label"]
        s = r["stats"]
        evict_str = "YES ⚠️" if r["evicted"] else "no"
        cold_str = f"{r['cold_load_ms']:.0f}" if r["evicted"] else "—"
        print(
            f"{r['router_label']:20s}  {r['router_role']:8s}  {r['router_vram_gb']:3.1f}G  "
            f"{r['scenario']:15s}  "
            f"{s['accuracy']*100:>5.1f}%  {s['security_accuracy']*100:>4.0f}%  "
            f"{s['p50_ms']:>6.0f}  {s['p95_ms']:>6.0f}  {s['timeout_count']:>4}  "
            f"{evict_str:8}  {cold_str:>10}"
        )

    print(f"\n{'━'*100}")
    print("EVICTION ANALYSIS  —  eviction_test scenario (router pre-warmed, then both companions loaded)")
    print(f"{'━'*100}")

    eviction_rows = [r for r in all_results if r["scenario"] == "eviction_test"]
    if not eviction_rows:
        print("  No eviction_test results.")
        return

    companions_shown = False
    for r in eviction_rows:
        if not companions_shown:
            print(f"  Companions used: {r['companions_loaded']}")
            companions_shown = True

        s = r["stats"]
        if r["evicted"]:
            print(
                f"\n  {r['router_label']:20s} ({r['router_vram_gb']}GB)  ← EVICTED"
            )
            print(f"    Cold-load time:    {r['cold_load_ms']:.0f}ms")
            print(f"    First-req latency: {r['first_request_ms']:.0f}ms")
            print(f"    Production TOs:    {s['timeout_count']} / {len(r['rows'])} requests ({s['timeout_count']/len(r['rows'])*100:.0f}%)")
            print(f"    Accuracy:          {s['accuracy_pct']} ({s['accuracy']*100:.1f}%)")
            print("    → Verdict: ⚠️  Router eviction IS occurring with current MAX_LOADED_MODELS")
            print("       Increase OLLAMA_MAX_LOADED_MODELS or switch to smaller router (qwen2.5:1.5b)")
        else:
            print(
                f"\n  {r['router_label']:20s} ({r['router_vram_gb']}GB)  ← survived (not evicted)"
            )
            print(f"    Accuracy:  {s['accuracy_pct']} ({s['accuracy']*100:.1f}%)")
            print(f"    p50:       {s['p50_ms']:.0f}ms")
            print("    → Verdict: ✓  Router stays warm under fleet load with current MAX_LOADED_MODELS")

    print(f"\n{'━'*100}")
    print("RECOMMENDATIONS")
    print(f"{'━'*100}")

    # Find accuracy by scenario for each router
    router_data: dict[str, dict[str, Any]] = {}
    for r in all_results:
        key = r["router_label"]
        if key not in router_data:
            router_data[key] = {"router": r, "scenarios": {}}
        router_data[key]["scenarios"][r["scenario"]] = r

    for label, data in router_data.items():
        r_meta = data["router"]
        scenarios = data["scenarios"]
        isolated = scenarios.get("isolated", {}).get("stats", {})
        eviction = scenarios.get("eviction_test", {})
        cold = scenarios.get("cold_entry", {}).get("stats", {})

        print(f"\n  {label} ({r_meta['router_role']}, {r_meta['router_vram_gb']}GB):")
        if isolated:
            print(f"    Warm accuracy:    {isolated.get('accuracy', 0)*100:.1f}%  p50={isolated.get('p50_ms', 0):.0f}ms")
        if eviction:
            ev_s = eviction.get("stats", {})
            evicted = eviction.get("evicted", False)
            print(f"    Under pressure:   {'EVICTED — ' + str(eviction.get('cold_load_ms', 0))+' ms cold-load' if evicted else 'not evicted'}")
            if evicted:
                print(f"    Timeout rate:     {ev_s.get('timeout_count', 0)} / {len(eviction.get('rows', []))} ({ev_s.get('timeout_count', 0)/max(len(eviction.get('rows', [])), 1)*100:.0f}%)")
        if cold:
            print(f"    Cold TOs:         {cold.get('timeout_count', 0)} / {len(scenarios.get('cold_entry', {}).get('rows', []))}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Router conditions benchmark — 3 routers × 4 VRAM load scenarios",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--companions",
        nargs="+",
        metavar="MODEL",
        default=None,
        help="Explicit companion models (auto-detected from largest available if not set)",
    )
    parser.add_argument(
        "--router",
        choices=["obliterated", "llama3b", "qwen15b", "all"],
        default="all",
        help="Which router(s) to test (default: all)",
    )
    parser.add_argument(
        "--skip",
        nargs="+",
        choices=SCENARIO_KEYS,
        default=[],
        metavar="SCENARIO",
        help="Scenarios to skip",
    )
    parser.add_argument(
        "--scenarios",
        nargs="+",
        choices=SCENARIO_KEYS,
        default=None,
        metavar="SCENARIO",
        help="Scenarios to run (default: all 4)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print plan only, don't run")
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="Save full results as JSON",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=None,
        help="Override per-request timeout for all routers (default: per-router value)",
    )
    args = parser.parse_args()

    # Build router list
    if args.router == "all":
        routers = ROUTER_CANDIDATES
    else:
        routers = [r for r in ROUTER_CANDIDATES if r["key"] == args.router]

    if args.timeout_ms:
        for r in routers:
            r = dict(r)
            r["timeout_ms"] = args.timeout_ms

    # Build scenario list
    if args.scenarios:
        scenarios = args.scenarios
    else:
        scenarios = [s for s in SCENARIO_KEYS if s not in args.skip]

    print("Portal 5 — Router Conditions Bench")
    print(f"Ollama URL    : {OLLAMA_URL}")
    print(f"Routers       : {len(routers)} × {[r['label'] for r in routers]}")
    print(f"Scenarios     : {scenarios}")
    print(f"Test cases    : {len(GOLDEN_SET)} per scenario")

    # Detect companions
    with httpx.Client() as client:
        router_models = [r["model"] for r in routers]
        companions = select_companions(
            client,
            router_models=router_models,
            override=args.companions,
            count=2,
        )

    if not companions:
        print(
            "\nWARNING: no companion models found — one_peer / eviction_test / cold_entry scenarios"
            " will run without companions (no VRAM pressure applied).",
            file=sys.stderr,
        )

    companion_strs = [f"{c['name']} ({c.get('size_gb', 0):.1f}GB)" for c in companions]
    print(f"Companions    : {companion_strs}")
    print()

    all_results = run_conditions_bench(
        routers=routers,
        companions=companions,
        scenarios=scenarios,
        dry_run=args.dry_run,
    )

    if all_results:
        print_summary(all_results)

    if args.output and all_results:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "bench": "router_conditions",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ollama_url": OLLAMA_URL,
            "production_timeout_ms": PRODUCTION_TIMEOUT_MS,
            "routers": [{"label": r["label"], "model": r["model"], "vram_gb": r["vram_gb"]} for r in routers],
            "companions": companions,
            "scenarios": scenarios,
            "golden_set_count": len(GOLDEN_SET),
            "results": all_results,
        }
        out_path.write_text(json.dumps(payload, indent=2))
        print(f"\nResults saved: {out_path}")


if __name__ == "__main__":
    main()
