#!/usr/bin/env python3
"""Portal 5 — MLX vs Ollama throughput benchmark.

Usage:
    python3 tests/benchmarks/bench_mlx_vs_ollama.py
    python3 tests/benchmarks/bench_mlx_vs_ollama.py --runs 5

Requires both backends running. Skips gracefully if either is unavailable.
Matched model pair: mlx-community/Llama-3.2-3B-Instruct-4bit vs llama3.2:3b-instruct-q4_K_M
"""

import argparse
import time

import httpx

MLX_URL = "http://localhost:8081"
OLLAMA_URL = "http://localhost:11434"

# Matched pair — same architecture, different backend
MLX_MODEL = "mlx-community/Llama-3.2-3B-Instruct-4bit"
OLLAMA_MODEL = "llama3.2:3b-instruct-q4_K_M"

TEST_PROMPT = (
    "Explain the difference between TCP and UDP in exactly three sentences. "
    "Be precise and technical."
)


def _check_backend(url: str, path: str) -> bool:
    try:
        r = httpx.get(f"{url}{path}", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


def _bench_openai_endpoint(base_url: str, model: str, prompt: str, label: str) -> dict | None:
    """Benchmark an OpenAI-compatible /v1/chat/completions endpoint."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "max_tokens": 256,
    }
    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(f"{base_url}/v1/chat/completions", json=payload)
            resp.raise_for_status()
    except Exception as e:
        print(f"  [{label}] ERROR: {e}")
        return None
    elapsed = time.perf_counter() - t0

    data = resp.json()
    usage = data.get("usage", {})
    completion_tokens = usage.get("completion_tokens", 0)
    tps = completion_tokens / elapsed if elapsed > 0 else 0.0

    return {
        "label": label,
        "model": model,
        "elapsed_s": round(elapsed, 2),
        "completion_tokens": completion_tokens,
        "tokens_per_sec": round(tps, 1),
    }


def _get_unified_memory_gb() -> float | None:
    """Return unified memory size on Apple Silicon, or None on other platforms."""
    import subprocess
    import sys

    if sys.platform != "darwin":
        return None
    try:
        out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)
        return round(int(out.strip()) / 1024**3, 1)
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="MLX vs Ollama benchmark")
    parser.add_argument("--runs", type=int, default=3, help="Number of timed runs")
    args = parser.parse_args()

    print("=" * 60)
    print("Portal 5 — MLX vs Ollama Benchmark")
    print("=" * 60)

    mem = _get_unified_memory_gb()
    if mem:
        print(f"Unified Memory: {mem}GB")

    mlx_available = _check_backend(MLX_URL, "/v1/models")
    ollama_available = _check_backend(OLLAMA_URL, "/api/tags")

    print(
        f"MLX    ({MLX_URL}):    {'✅ available' if mlx_available else '⚠️  not running — skipping'}"
    )
    print(
        f"Ollama ({OLLAMA_URL}): "
        f"{'✅ available' if ollama_available else '⚠️  not running — skipping'}"
    )
    print(f"Prompt: {TEST_PROMPT[:60]}...")
    print(f"Runs: {args.runs}\n")

    if not mlx_available and not ollama_available:
        print("Neither backend is running. Start at least one and retry.")
        return

    results = []
    for run in range(1, args.runs + 1):
        print(f"--- Run {run}/{args.runs} ---")
        if mlx_available:
            r = _bench_openai_endpoint(MLX_URL, MLX_MODEL, TEST_PROMPT, "MLX")
            if r:
                results.append(r)
                print(
                    f"  MLX:    {r['tokens_per_sec']} t/s  "
                    f"({r['completion_tokens']} tokens, {r['elapsed_s']}s)"
                )
        if ollama_available:
            r = _bench_openai_endpoint(OLLAMA_URL, OLLAMA_MODEL, TEST_PROMPT, "Ollama")
            if r:
                results.append(r)
                print(
                    f"  Ollama: {r['tokens_per_sec']} t/s  "
                    f"({r['completion_tokens']} tokens, {r['elapsed_s']}s)"
                )

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for label in ["MLX", "Ollama"]:
        runs = [r for r in results if r["label"] == label]
        if runs:
            avg_tps = sum(r["tokens_per_sec"] for r in runs) / len(runs)
            avg_elapsed = sum(r["elapsed_s"] for r in runs) / len(runs)
            print(
                f"{label:8s}: avg {avg_tps:.1f} t/s  "
                f"avg {avg_elapsed:.2f}s/request  ({len(runs)} runs)"
            )

    mlx_runs = [r for r in results if r["label"] == "MLX"]
    ollama_runs = [r for r in results if r["label"] == "Ollama"]
    if mlx_runs and ollama_runs:
        mlx_avg = sum(r["tokens_per_sec"] for r in mlx_runs) / len(mlx_runs)
        ol_avg = sum(r["tokens_per_sec"] for r in ollama_runs) / len(ollama_runs)
        pct = ((mlx_avg - ol_avg) / ol_avg * 100) if ol_avg > 0 else 0
        direction = "faster" if pct >= 0 else "slower"
        print(f"\nMLX is {abs(pct):.0f}% {direction} than Ollama on this hardware")
        print("(Expected: 20-40% faster on M4 per CLAUDE.md)")

    print()


if __name__ == "__main__":
    main()
