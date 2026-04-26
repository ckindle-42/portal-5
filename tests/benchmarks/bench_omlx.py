#!/usr/bin/env python3
"""Portal 5 — OMLX full bake-off benchmark (P5-FUT-013).

Measures the three dimensions the initial smoke test missed:

  1. TTFT on repeated prefix (KV cache test) — the headline OMLX feature.
     Sends the same 5-turn conversation 3× in sequence. Cold TTFT (first call,
     no cache) vs warm TTFT (subsequent calls, cache populated). A meaningful
     KV cache hit should reduce warm TTFT by 10× or more on large models.

  2. TPS on large models — Qwen3-Coder-30B (22GB) and Llama-3.3-70B (40GB).
     The smoke test only tested 3B and 14B. KV cache savings are proportionally
     larger relative to load time on bigger models.

  3. Concurrent request throughput — 4 simultaneous requests against a loaded
     model. OMLX promises continuous batching; mlx-proxy is serial per request.

Methodology:
  - Strictly isolated: one endpoint tested at a time, full memory available.
  - 30s Metal reclaim wait between endpoint switches.
  - Synchronous HTTP (not async) to avoid shared-memory interference.
  - Warm-up request before each timed series (mirrors bench_tps.py).
  - Models tested: Llama-3.2-3B (3GB, baseline), Qwen3-Coder-30B (22GB, medium),
    Llama-3.3-70B (40GB, large — skip if unavailable on either endpoint).

Run after:
  ./launch.sh restart-mlx
  # start OMLX: /Volumes/data01/omlx-venv/bin/omlx serve --config deploy/omlx/config.yaml
  sleep 60   # wait for both servers to settle

Usage:
  python3 tests/benchmarks/bench_omlx.py                   # full bake-off
  python3 tests/benchmarks/bench_omlx.py --skip-large      # skip 70B (faster)
  python3 tests/benchmarks/bench_omlx.py --mlx-only        # mlx-proxy only
  python3 tests/benchmarks/bench_omlx.py --omlx-only       # OMLX only
  python3 tests/benchmarks/bench_omlx.py --dry-run         # show plan
"""

import argparse
import concurrent.futures
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

MLX_PROXY_URL = "http://localhost:8081"
OMLX_URL = "http://localhost:8085"
RESULTS_DIR = Path(__file__).parent / "results"

# ── Test matrix ───────────────────────────────────────────────────────────────

# Models tested in all three dimensions (size order: small → large).
# Skip 70B if --skip-large or if unavailable on either endpoint.
TEST_MODELS = [
    {
        "id": "mlx-community/Llama-3.2-3B-Instruct-8bit",
        "short": "Llama-3.2-3B",
        "memory_gb": 3,
        "big_model": False,
        "role": "baseline",
    },
    {
        "id": "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit",
        "short": "Qwen3-Coder-30B",
        "memory_gb": 22,
        "big_model": False,
        "role": "medium",
    },
    {
        "id": "mlx-community/Llama-3.3-70B-Instruct-4bit",
        "short": "Llama-3.3-70B",
        "memory_gb": 40,
        "big_model": True,
        "role": "large",
    },
]

# Single-shot prompts for TPS and concurrent tests.
# Using same prompts as bench_tps.py for comparability.
SINGLE_PROMPTS = {
    "coding": (
        "Write a Python function called merge_intervals that takes a list of "
        "tuples (each tuple is a pair of integers representing a start and end value) "
        "and returns a new list with overlapping intervals merged. "
        "Include type hints, a docstring, and handle edge cases."
    ),
    "reasoning": (
        "A hospital emergency room has 30 patients arriving per hour. "
        "The ER has 8 beds, 3 doctors, and 12 nurses. Average treatment "
        "time is 45 minutes. Identify the primary bottleneck and show the math."
    ),
    "general": (
        "List the 7 OSI model layers from bottom to top. For each layer, provide: "
        "the layer number, the standard name, and one example protocol."
    ),
}

# KV cache test: 5-turn conversation with a long shared prefix.
# The system prompt + first 4 turns are the "prefix" that should be cached.
# Turn 5 is sent cold (first call) then warm (subsequent calls).
KV_SYSTEM = (
    "You are a helpful, precise coding assistant. You write clean, well-documented Python. "
    "You explain your reasoning step by step. You cite time and space complexity. "
    "You handle edge cases explicitly. You never skip error handling."
)
KV_CONVERSATION = [
    {"role": "system", "content": KV_SYSTEM},
    {"role": "user", "content": "What is the difference between a list and a tuple in Python?"},
    {
        "role": "assistant",
        "content": (
            "Lists are mutable sequences; tuples are immutable. "
            "Use tuples for fixed data (coordinates, records), lists for dynamic collections."
        ),
    },
    {"role": "user", "content": "When would you use a named tuple?"},
    {
        "role": "assistant",
        "content": (
            "Use namedtuple (or dataclass) when you want attribute access on tuple fields "
            "without writing a full class. Good for lightweight record types."
        ),
    },
    {
        "role": "user",
        "content": "Write a Python function that takes a list of 2-tuples and returns a dict.",
    },
]

MAX_TOKENS = 200
WARMUP_TOKENS = 1
REQUEST_TIMEOUT = 300.0
KV_ROUNDS = 3   # cold + 2 warm rounds per model per endpoint
TPS_RUNS = 3    # single-shot TPS runs per prompt per model per endpoint
CONCURRENT_N = 4  # parallel workers for concurrency test


# ── HTTP helpers ──────────────────────────────────────────────────────────────


def _check_endpoint(url: str) -> bool:
    try:
        r = httpx.get(f"{url}/v1/models", timeout=5.0)
        if r.status_code == 200:
            return True
        # mlx-proxy returns 503 when idle but functional
        if url == MLX_PROXY_URL and r.status_code == 503:
            h = httpx.get(f"{url}/health", timeout=3.0).json()
            return h.get("state") in ("none", "switching", "ready")
    except Exception:
        pass
    return False


def _warmup(url: str, model: str) -> bool:
    """Force model load before timed runs (same pattern as bench_tps.py)."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
        "max_tokens": WARMUP_TOKENS,
    }
    for attempt in range(3):
        try:
            r = httpx.post(f"{url}/v1/chat/completions", json=payload, timeout=300.0)
            if r.status_code in (200, 503):
                return True
        except Exception:
            if attempt < 2:
                time.sleep(10)
    return False


def _one_request(url: str, model: str, messages: list, max_tokens: int = MAX_TOKENS) -> dict:
    """Single synchronous streaming request. Returns timing + token data."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "max_tokens": max_tokens,
    }
    t0 = time.perf_counter()
    t_first: float | None = None
    completion_tokens = 0
    response_text = ""

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            with client.stream("POST", f"{url}/v1/chat/completions", json=payload) as resp:
                if resp.status_code != 200:
                    body = resp.read()[:200].decode(errors="replace")
                    return {
                        "error": f"HTTP {resp.status_code}: {body[:80]}",
                        "elapsed_s": round(time.perf_counter() - t0, 3),
                    }
                for raw_line in resp.iter_lines():
                    line = (
                        raw_line.strip()
                        if isinstance(raw_line, str)
                        else raw_line.decode(errors="replace").strip()
                    )
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        obj = json.loads(data_str)
                    except Exception:
                        continue
                    delta = obj.get("choices", [{}])[0].get("delta", {})
                    chunk = delta.get("content") or ""
                    if chunk and t_first is None:
                        t_first = time.perf_counter()
                    response_text += chunk
                    usage = obj.get("usage") or {}
                    if usage.get("completion_tokens"):
                        completion_tokens = usage["completion_tokens"]

    except httpx.ReadTimeout:
        return {"error": "timeout", "elapsed_s": REQUEST_TIMEOUT}
    except Exception as e:
        return {"error": str(e)[:100], "elapsed_s": round(time.perf_counter() - t0, 3)}

    elapsed = time.perf_counter() - t0
    if completion_tokens == 0 and response_text:
        completion_tokens = max(1, len(response_text.split()))
    ttft = round(t_first - t0, 3) if t_first is not None else None
    tps = round(completion_tokens / elapsed, 1) if elapsed > 0 else 0.0

    return {
        "elapsed_s": round(elapsed, 3),
        "ttft_s": ttft,
        "completion_tokens": completion_tokens,
        "tps": tps,
        "response_preview": response_text[:120],
    }


# ── Eviction / memory management ─────────────────────────────────────────────
# Mirrors bench_tps.py patterns exactly.


def _evict_mlx(smallest_model: str) -> None:
    """Load the smallest model to push out the current model."""
    payload = {
        "model": smallest_model,
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
        "max_tokens": 1,
    }
    try:
        httpx.post(f"{MLX_PROXY_URL}/v1/chat/completions", json=payload, timeout=300.0)
    except Exception:
        pass


def _wait_mlx_memory(needed_gb: float, timeout_s: float = 120.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = httpx.get(f"{MLX_PROXY_URL}/health", timeout=3.0)
            if r.status_code == 200:
                mem = r.json().get("memory", {}).get("current", {})
                avail = (
                    mem.get("free_gb", 0.0)
                    + mem.get("inactive_gb", 0.0)
                    + mem.get("purgeable_gb", 0.0)
                )
                if avail >= needed_gb:
                    return True
        except Exception:
            pass
        time.sleep(5.0)
    return False


SMALLEST_MLX = "mlx-community/Llama-3.2-3B-Instruct-8bit"
METAL_RECLAIM_WAIT = 30  # seconds between endpoint switches


# ── Test 1: KV cache TTFT ─────────────────────────────────────────────────────


def test_kv_cache(url: str, label: str, model: str, rounds: int = KV_ROUNDS) -> dict:
    """
    Send KV_CONVERSATION `rounds` times in sequence against the same loaded model.

    Round 1 is cold (model just loaded, cache empty or prefix not yet cached).
    Rounds 2+ are warm (prefix should be in OMLX's KV cache if the feature works).

    The delta between cold and warm TTFT is the KV cache signal.
    mlx-proxy has no KV cache persistence across requests, so all rounds should
    show similar TTFT (baseline). OMLX warm rounds should be dramatically faster.
    """
    print(f"    KV cache test ({rounds} rounds, same prefix each time) ...", flush=True)
    results = []
    for i in range(1, rounds + 1):
        label_round = "cold" if i == 1 else f"warm-{i-1}"
        r = _one_request(url, model, KV_CONVERSATION, max_tokens=MAX_TOKENS)
        r["round"] = i
        r["round_label"] = label_round
        results.append(r)
        ttft_str = f"{r['ttft_s']:.2f}s" if r.get("ttft_s") is not None else "N/A"
        tps_str = f"{r.get('tps', 0):.1f} t/s" if "tps" in r else "FAIL"
        err = f" [{r['error']}]" if "error" in r else ""
        print(f"      round {i} ({label_round}): TTFT={ttft_str}  TPS={tps_str}{err}")
        # Brief pause between rounds to let the model settle but NOT enough to
        # evict the KV cache (OMLX's TTL is 168h per config)
        if i < rounds:
            time.sleep(3)

    cold = next((r for r in results if r["round"] == 1 and "ttft_s" in r), None)
    warm = [r for r in results if r["round"] > 1 and "ttft_s" in r]

    cold_ttft = cold["ttft_s"] if cold else None
    warm_ttft_avg = (
        round(sum(r["ttft_s"] for r in warm) / len(warm), 3) if warm else None
    )
    speedup = (
        round(cold_ttft / warm_ttft_avg, 1)
        if cold_ttft and warm_ttft_avg and warm_ttft_avg > 0
        else None
    )

    return {
        "test": "kv_cache_ttft",
        "endpoint": label,
        "model": model,
        "cold_ttft_s": cold_ttft,
        "warm_ttft_avg_s": warm_ttft_avg,
        "ttft_speedup_x": speedup,
        "rounds": results,
    }


# ── Test 2: TPS on large models ───────────────────────────────────────────────


def test_tps_large(url: str, label: str, model: str, runs: int = TPS_RUNS) -> dict:
    """TPS measurement using domain-appropriate prompts, N runs, averaged."""
    print(f"    TPS test ({runs} runs × {len(SINGLE_PROMPTS)} prompts) ...", flush=True)
    all_runs = []
    for cat, prompt in SINGLE_PROMPTS.items():
        msgs = [{"role": "user", "content": prompt}]
        for run_n in range(1, runs + 1):
            r = _one_request(url, model, msgs)
            r["prompt_category"] = cat
            r["run"] = run_n
            all_runs.append(r)
            tps_str = f"{r.get('tps', 0):.1f}" if "tps" in r else "FAIL"
            err = f" [{r['error']}]" if "error" in r else ""
            print(f"      {cat} run {run_n}: {tps_str} t/s{err}")
            time.sleep(1)

    successful = [r for r in all_runs if "tps" in r and not r.get("error")]
    avg_tps = round(sum(r["tps"] for r in successful) / len(successful), 1) if successful else 0.0
    avg_ttft = (
        round(
            sum(r["ttft_s"] for r in successful if r.get("ttft_s") is not None)
            / sum(1 for r in successful if r.get("ttft_s") is not None),
            3,
        )
        if any(r.get("ttft_s") is not None for r in successful)
        else None
    )

    return {
        "test": "tps_large",
        "endpoint": label,
        "model": model,
        "avg_tps": avg_tps,
        "avg_ttft_s": avg_ttft,
        "runs_success": len(successful),
        "runs_total": len(all_runs),
        "runs": all_runs,
    }


# ── Test 3: Concurrent throughput ─────────────────────────────────────────────


def test_concurrent(url: str, label: str, model: str, n: int = CONCURRENT_N) -> dict:
    """
    Send N requests simultaneously against the same loaded model.
    Measures wall-clock time for all N to complete and total tokens generated.

    mlx-proxy is serial — requests queue. OMLX uses continuous batching.
    Serial baseline: N × single-request time.
    Batched ideal: ~single-request time (all N processed together).
    """
    print(f"    Concurrent test ({n} parallel requests) ...", flush=True)
    prompt = SINGLE_PROMPTS["coding"]
    msgs = [{"role": "user", "content": prompt}]

    # Serial baseline first (sequential, 1 by 1)
    serial_times = []
    for i in range(n):
        r = _one_request(url, model, msgs)
        if "elapsed_s" in r:
            serial_times.append(r["elapsed_s"])
        time.sleep(1)
    serial_avg = round(sum(serial_times) / len(serial_times), 2) if serial_times else 0.0
    serial_total_est = round(serial_avg * n, 2)

    # Concurrent: N simultaneous requests
    t_wall_start = time.perf_counter()
    concurrent_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as executor:
        futures = [
            executor.submit(_one_request, url, model, msgs) for _ in range(n)
        ]
        for f in concurrent.futures.as_completed(futures):
            concurrent_results.append(f.result())
    wall_elapsed = round(time.perf_counter() - t_wall_start, 2)

    successful = [r for r in concurrent_results if "tps" in r and not r.get("error")]
    total_tokens = sum(r.get("completion_tokens", 0) for r in successful)
    aggregate_tps = round(total_tokens / wall_elapsed, 1) if wall_elapsed > 0 else 0.0
    speedup = round(serial_total_est / wall_elapsed, 2) if wall_elapsed > 0 else None

    print(f"      serial avg: {serial_avg:.2f}s/req  |  concurrent wall: {wall_elapsed:.2f}s  |  speedup: {speedup}×")

    return {
        "test": "concurrent",
        "endpoint": label,
        "model": model,
        "workers": n,
        "serial_avg_s": serial_avg,
        "serial_total_est_s": serial_total_est,
        "concurrent_wall_s": wall_elapsed,
        "aggregate_tps": aggregate_tps,
        "speedup_x": speedup,
        "requests_success": len(successful),
        "requests_total": n,
        "results": concurrent_results,
    }


# ── Endpoint runner ───────────────────────────────────────────────────────────


def run_endpoint(url: str, label: str, models: list[dict], args) -> list[dict]:
    """Run all three tests against `url` for each model in `models`."""
    print(f"\n{'='*60}")
    print(f"ENDPOINT: {label} ({url})")
    print(f"{'='*60}")

    all_results = []
    for model_def in models:
        model_id = model_def["id"]
        short = model_def["short"]
        mem_gb = model_def["memory_gb"]
        print(f"\n  Model: {short} ({mem_gb}GB)")

        # Warm-up (force model load before timed runs)
        print(f"    Warming up {short} ...", end=" ", flush=True)
        if not args.dry_run:
            ok = _warmup(url, model_id)
            print("ok" if ok else "FAILED (continuing)")
        else:
            print("(dry run)")

        if args.dry_run:
            print("    (dry run — skipping all tests)")
            continue

        # Test 1: KV cache TTFT
        r1 = test_kv_cache(url, label, model_id)
        all_results.append(r1)

        # Test 2: TPS (large model single-shot)
        r2 = test_tps_large(url, label, model_id)
        all_results.append(r2)

        # Test 3: Concurrent throughput
        r3 = test_concurrent(url, label, model_id)
        all_results.append(r3)

        # Evict + reclaim between models on mlx-proxy
        # (OMLX handles its own LRU eviction; no eviction call needed)
        if url == MLX_PROXY_URL and model_def != models[-1]:
            next_gb = models[models.index(model_def) + 1]["memory_gb"]
            print(f"    Evicting {short} → reclaim for next model ({next_gb}GB) ...", end=" ", flush=True)
            _evict_mlx(SMALLEST_MLX)
            ok = _wait_mlx_memory(next_gb + 10, timeout_s=120.0)
            time.sleep(10)
            print("ok" if ok else "ok (partial reclaim)")

    return all_results


# ── Summary printer ───────────────────────────────────────────────────────────


def _print_summary(all_results: list[dict]) -> None:
    print(f"\n{'='*70}")
    print("BAKE-OFF SUMMARY")
    print(f"{'='*70}")

    # Group by test type
    kv_results = [r for r in all_results if r["test"] == "kv_cache_ttft"]
    tps_results = [r for r in all_results if r["test"] == "tps_large"]
    conc_results = [r for r in all_results if r["test"] == "concurrent"]

    if kv_results:
        print("\n── KV Cache TTFT (cold vs warm) ──")
        print(f"{'Endpoint':<15} {'Model':<20} {'Cold TTFT':>10} {'Warm TTFT':>10} {'Speedup':>8}")
        print("-" * 68)
        for r in kv_results:
            cold = f"{r['cold_ttft_s']:.2f}s" if r.get("cold_ttft_s") else "N/A"
            warm = f"{r['warm_ttft_avg_s']:.2f}s" if r.get("warm_ttft_avg_s") else "N/A"
            sp = f"{r['ttft_speedup_x']:.1f}×" if r.get("ttft_speedup_x") else "N/A"
            short = r["model"].split("/")[-1][:20]
            print(f"{r['endpoint']:<15} {short:<20} {cold:>10} {warm:>10} {sp:>8}")

    if tps_results:
        print("\n── TPS — Large Models ──")
        print(f"{'Endpoint':<15} {'Model':<20} {'Avg TPS':>10} {'Avg TTFT':>10} {'Runs OK':>8}")
        print("-" * 68)
        for r in tps_results:
            tps = f"{r['avg_tps']:.1f}" if r.get("avg_tps") else "N/A"
            ttft = f"{r['avg_ttft_s']:.2f}s" if r.get("avg_ttft_s") else "N/A"
            runs = f"{r['runs_success']}/{r['runs_total']}"
            short = r["model"].split("/")[-1][:20]
            print(f"{r['endpoint']:<15} {short:<20} {tps:>10} {ttft:>10} {runs:>8}")

    if conc_results:
        print("\n── Concurrent Throughput (4 parallel) ──")
        print(f"{'Endpoint':<15} {'Model':<20} {'Serial est':>11} {'Conc wall':>10} {'Speedup':>8}")
        print("-" * 69)
        for r in conc_results:
            ser = f"{r['serial_total_est_s']:.2f}s"
            wall = f"{r['concurrent_wall_s']:.2f}s"
            sp = f"{r['speedup_x']:.2f}×" if r.get("speedup_x") else "N/A"
            short = r["model"].split("/")[-1][:20]
            print(f"{r['endpoint']:<15} {short:<20} {ser:>11} {wall:>10} {sp:>8}")

    # Head-to-head KV delta
    mlx_kv = {r["model"]: r for r in kv_results if r["endpoint"] == "mlx-proxy"}
    omlx_kv = {r["model"]: r for r in kv_results if r["endpoint"] == "omlx"}
    shared_models = set(mlx_kv) & set(omlx_kv)
    if shared_models:
        print("\n── KV TTFT Head-to-Head (warm round) ──")
        for m in shared_models:
            mx = mlx_kv[m].get("warm_ttft_avg_s")
            ox = omlx_kv[m].get("warm_ttft_avg_s")
            if mx and ox:
                delta = round((mx - ox) / mx * 100, 1)
                winner = "OMLX" if ox < mx else "mlx-proxy"
                print(f"  {m.split('/')[-1]}: mlx={mx:.2f}s  omlx={ox:.2f}s  → {winner} {abs(delta):.1f}% faster")

    print(f"\n{'='*70}")
    print("Update OMLX_DECISION.md with these results, then close P5-FUT-013.")
    print(f"{'='*70}")


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="OMLX full bake-off benchmark")
    parser.add_argument("--mlx-only", action="store_true", help="Test mlx-proxy only")
    parser.add_argument("--omlx-only", action="store_true", help="Test OMLX only")
    parser.add_argument("--skip-large", action="store_true", help="Skip Llama-3.3-70B")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without running")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    models = [m for m in TEST_MODELS if not (args.skip_large and m["role"] == "large")]

    print("Portal 5 — OMLX Full Bake-off")
    print(f"Timestamp: {ts}")
    print(f"Models: {[m['short'] for m in models]}")
    print(f"Tests: KV cache TTFT ({KV_ROUNDS} rounds)  |  TPS ({TPS_RUNS} runs)  |  Concurrent ({CONCURRENT_N} workers)")

    mlx_up = _check_endpoint(MLX_PROXY_URL)
    omlx_up = _check_endpoint(OMLX_URL)
    print(f"\nmlx-proxy ({MLX_PROXY_URL}): {'UP' if mlx_up else 'DOWN'}")
    print(f"OMLX      ({OMLX_URL}):       {'UP' if omlx_up else 'DOWN'}")

    if not args.omlx_only and not mlx_up:
        print("\nERROR: mlx-proxy not running. Start it before benchmarking.")
        return
    if not args.mlx_only and not omlx_up:
        print("\nERROR: OMLX not running. Start it before benchmarking.")
        return

    all_results: list[dict] = []

    # Always test mlx-proxy first (the established baseline)
    if not args.omlx_only:
        mlx_results = run_endpoint(MLX_PROXY_URL, "mlx-proxy", models, args)
        all_results.extend(mlx_results)

    # Wait for Metal to reclaim fully before switching endpoints
    if not args.omlx_only and not args.mlx_only and not args.dry_run:
        print(f"\n  Switching endpoints — waiting {METAL_RECLAIM_WAIT}s for Metal reclaim ...", end=" ", flush=True)
        _evict_mlx(SMALLEST_MLX)
        _wait_mlx_memory(30.0, timeout_s=90.0)
        time.sleep(METAL_RECLAIM_WAIT)
        print("ok")

    if not args.mlx_only:
        omlx_results = run_endpoint(OMLX_URL, "omlx", models, args)
        all_results.extend(omlx_results)

    if not args.dry_run:
        _print_summary(all_results)

    out = {
        "timestamp": ts,
        "models_tested": [m["short"] for m in models],
        "skip_large": args.skip_large,
        "kv_rounds": KV_ROUNDS,
        "tps_runs": TPS_RUNS,
        "concurrent_workers": CONCURRENT_N,
        "results": all_results,
    }
    out_path = RESULTS_DIR / f"omlx_bakeoff_{ts}.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nResults saved: {out_path}")


if __name__ == "__main__":
    main()
