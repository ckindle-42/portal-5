#!/usr/bin/env python3
"""
MLX vs Ollama Benchmark — Portal 5

Compares Apple Silicon MLX (mlx_lm) against Ollama GGUF on identical prompts.
Measures time-to-first-token (TTFT) and sustained tokens-per-second (t/s).

Usage:
    python3 tests/benchmarks/bench_mlx_vs_ollama.py
    python3 tests/benchmarks/bench_mlx_vs_ollama.py --model mlx-community/Qwen3-Coder-Next-4bit
    python3 tests/benchmarks/bench_mlx_vs_ollama.py --runs 3 --max-tokens 256

Requirements:
    - MLX server running at http://localhost:8081 (./launch.sh install-mlx)
    - Ollama running at http://localhost:11434 (ollama serve)
    - Matching model pulled in both backends
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

import httpx

MLX_BASE = "http://localhost:8081"
OLLAMA_BASE = "http://localhost:11434"
DEFAULT_RUNS = 3
DEFAULT_MAX_TOKENS = 512

# Benchmark prompts — diverse enough to exercise different model capabilities
BENCHMARK_PROMPTS = [
    "Write a Python function to compute the Fibonacci sequence up to n terms.",
    "Explain the difference between a process and a thread in operating systems.",
    "What are the security implications of storing JWTs in localStorage vs httpOnly cookies?",
]


def check_backend(url: str, name: str) -> tuple[bool, str | None]:
    """Return (healthy, model_id_or_error)."""
    try:
        resp = httpx.get(f"{url}/v1/models", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            models = data.get("data", [])
            if models:
                return True, models[0].get("id", "unknown")
            return True, "no models listed"
        return False, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, str(e)


def stream_completion(
    base_url: str, model: str, prompt: str, max_tokens: int = 512
) -> tuple[float, float, int]:
    """Send a streaming completion request.

    Returns:
        ttft_s: Time to first token in seconds
        total_s: Total streaming time in seconds
        num_tokens: Total tokens received
    """
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "max_tokens": max_tokens,
    }
    start = time.perf_counter()
    ttft: float | None = None
    num_tokens = 0

    try:
        with httpx.stream("POST", f"{base_url}/v1/chat/completions", json=body, timeout=60) as resp:
            if resp.status_code != 200:
                err = resp.read().decode(errors="replace")
                raise RuntimeError(f"HTTP {resp.status_code}: {err[:200]}")

            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                payload = line[6:].strip()
                if payload == "[DONE]" or not payload:
                    continue
                chunk_time = time.perf_counter()
                if ttft is None:
                    ttft = chunk_time - start
                num_tokens += 1

    except httpx.ReadTimeout:
        pass  # Some backends stop mid-stream

    total_s = time.perf_counter() - start
    if ttft is None:
        ttft = total_s
    return ttft, total_s, num_tokens


def nonstream_completion(
    base_url: str, model: str, prompt: str, max_tokens: int = 512
) -> tuple[float, float, int, int]:
    """Send a non-streaming completion request.

    Returns:
        latency_s: End-to-end latency in seconds
        num_tokens: Output tokens generated
        prompt_tokens: Input tokens (if available, else 0)
    """
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "max_tokens": max_tokens,
    }
    start = time.perf_counter()
    try:
        resp = httpx.post(f"{base_url}/v1/chat/completions", json=body, timeout=60)
        latency_s = time.perf_counter() - start
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        num_tokens = data.get("usage", {}).get("completion_tokens", 0)
        prompt_tokens = data.get("usage", {}).get("prompt_tokens", 0)
        return latency_s, latency_s, num_tokens, prompt_tokens
    except Exception as e:
        print(f"    [WARNING] Non-streaming request failed: {e}", file=sys.stderr)
        return -1, -1, 0, 0


def run_benchmark(
    backend_name: str,
    base_url: str,
    model: str,
    prompt: str,
    runs: int,
    max_tokens: int,
    stream: bool = True,
) -> dict[str, Any] | None:
    """Run benchmark and return stats dict."""
    print(f"\n  {backend_name} ({base_url})")
    print(f"  Model: {model}")
    print(f"  Runs: {runs}  |  Stream: {stream}  |  Max tokens: {max_tokens}")

    healthy, model_id = check_backend(base_url, backend_name)
    if not healthy:
        print(f"  [SKIP] {backend_name} unavailable: {model_id}")
        return None
    print(f"  Backend model: {model_id}")

    ttft_list: list[float] = []
    tps_list: list[float] = []
    total_latency_list: list[float] = []

    for i in range(runs):
        print(f"    Run {i + 1}/{runs}...", end=" ", flush=True)
        if stream:
            try:
                ttft_s, total_s, num_tokens = stream_completion(base_url, model, prompt, max_tokens)
                tps = num_tokens / total_s if total_s > 0 and num_tokens > 0 else 0
                ttft_ms = ttft_s * 1000
                print(f"TTFT={ttft_ms:.0f}ms  tokens={num_tokens}  t/s={tps:.1f}")
                ttft_list.append(ttft_ms)
                tps_list.append(tps)
                total_latency_list.append(total_s)
            except Exception as e:
                print(f"[ERROR] {e}")
        else:
            lat_s, _, num_tokens, _ = nonstream_completion(base_url, model, prompt, max_tokens)
            if lat_s > 0:
                tps = num_tokens / lat_s if lat_s > 0 else 0
                print(f"latency={lat_s:.2f}s  tokens={num_tokens}  t/s={tps:.1f}")
                ttft_list.append(lat_s * 1000)  # report e2e as "ttft" for non-stream
                tps_list.append(tps)
                total_latency_list.append(lat_s)
            else:
                print("[ERROR] request failed")

    if not ttft_list:
        return None

    avg_ttft = sum(ttft_list) / len(ttft_list)
    avg_tps = sum(tps_list) / len(tps_list)
    avg_latency = sum(total_latency_list) / len(total_latency_list)

    return {
        "backend": backend_name,
        "url": base_url,
        "model": model,
        "runs": runs,
        "avg_ttft_ms": round(avg_ttft, 1),
        "min_ttft_ms": round(min(ttft_list), 1),
        "max_ttft_ms": round(max(ttft_list), 1),
        "avg_tps": round(avg_tps, 1),
        "avg_latency_s": round(avg_latency, 3),
    }


def print_comparison(mlx_stats: dict, ollama_stats: dict) -> None:
    """Print a side-by-side comparison table."""
    header = f"{'Metric':<22} {'MLX':>12} {'Ollama':>12} {'Speedup':>10}"
    sep = "-" * len(header)
    print(f"\n{'=' * len(header)}")
    print("BENCHMARK RESULTS")
    print(f"{'=' * len(header)}")
    print(header)
    print(sep)

    mlx_tps = mlx_stats["avg_tps"]
    ollama_tps = ollama_stats["avg_tps"]
    speedup = mlx_tps / ollama_tps if ollama_tps > 0 else float("inf")
    speedup_str = f"{speedup:.2f}x" if speedup != float("inf") else "N/A"

    rows: list[tuple[str, str, str, str]] = [
        (
            "Avg TTFT (ms)",
            f"{mlx_stats['avg_ttft_ms']:>12.1f}",
            f"{ollama_stats['avg_ttft_ms']:>12.1f}",
            "",
        ),
        (
            "Min TTFT (ms)",
            f"{mlx_stats['min_ttft_ms']:>12.1f}",
            f"{ollama_stats['min_ttft_ms']:>12.1f}",
            "",
        ),
        (
            "Max TTFT (ms)",
            f"{mlx_stats['max_ttft_ms']:>12.1f}",
            f"{ollama_stats['max_ttft_ms']:>12.1f}",
            "",
        ),
        ("Avg tokens/sec", f"{mlx_tps:>12.1f}", f"{ollama_tps:>12.1f}", speedup_str),
        (
            "Avg latency (s)",
            f"{mlx_stats['avg_latency_s']:>12.3f}",
            f"{ollama_stats['avg_latency_s']:>12.3f}",
            "",
        ),
        ("Runs", f"{mlx_stats['runs']:>12}", f"{ollama_stats['runs']:>12}", ""),
    ]
    for metric, mlx_val, ollama_val, speedup_col in rows:
        print(f"  {metric:<20} {mlx_val:>12} {ollama_val:>12} {speedup_col:>10}")

    print(sep)
    print(f"  MLX model:   {mlx_stats['model']}\n  Ollama model: {ollama_stats['model']}")
    print(f"{'=' * len(header)}\n")

    if speedup > 1.1:
        print(f"  MLX is {speedup:.1f}x faster than Ollama on this hardware.")
    elif speedup < 0.9:
        print(f"  Ollama is {1 / speedup:.1f}x faster than MLX on this hardware.")
    else:
        print("  MLX and Ollama are within 10% of each other on this workload.")


def main() -> int:
    parser = argparse.ArgumentParser(description="MLX vs Ollama benchmark")
    parser.add_argument(
        "--mlx-model",
        default="mlx-community/Qwen3-Coder-Next-4bit",
        help="MLX model tag (default: mlx-community/Qwen3-Coder-Next-4bit)",
    )
    parser.add_argument(
        "--ollama-model",
        default="qwen3.5:9b",
        help="Ollama model tag (default: qwen3.5:9b)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=DEFAULT_RUNS,
        help=f"Number of runs per backend (default: {DEFAULT_RUNS})",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help=f"Max output tokens (default: {DEFAULT_MAX_TOKENS})",
    )
    parser.add_argument(
        "--prompt",
        default="",
        help="Custom prompt (default: built-in multi-prompt suite)",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="Use non-streaming requests (measures e2e latency instead of TTFT)",
    )
    args = parser.parse_args()

    print("Portal 5 — MLX vs Ollama Benchmark")
    print("=" * 50)

    # Check backends
    mlx_ok, mlx_model = check_backend(MLX_BASE, "MLX")
    ollama_ok, ollama_model = check_backend(OLLAMA_BASE, "Ollama")

    print(f"\nMLX:   {'✅ ' + mlx_model if mlx_ok else '❌ unavailable: ' + mlx_model}")
    print(f"Ollama: {'✅ ' + ollama_model if ollama_ok else '❌ unavailable: ' + ollama_model}")

    if not mlx_ok and not ollama_ok:
        print("\n[ERROR] Neither backend is available. Start MLX and/or Ollama first.")
        print("  MLX:    ~/.portal5/mlx/start.sh")
        print("  Ollama: ollama serve")
        return 1

    prompts = [args.prompt] if args.prompt else BENCHMARK_PROMPTS
    stream_mode = not args.no_stream

    all_mlx_stats: list[dict] = []
    all_ollama_stats: list[dict] = []

    for i, prompt in enumerate(prompts):
        label = f"[Prompt {i + 1}/{len(prompts)}]"
        print(f"\n{label} {prompt[:60]}{'...' if len(prompt) > 60 else ''}")

        if mlx_ok:
            stats = run_benchmark(
                "MLX",
                MLX_BASE,
                args.mlx_model,
                prompt,
                args.runs,
                args.max_tokens,
                stream=stream_mode,
            )
            if stats:
                all_mlx_stats.append(stats)

        if ollama_ok:
            stats = run_benchmark(
                "Ollama",
                OLLAMA_BASE,
                args.ollama_model,
                prompt,
                args.runs,
                args.max_tokens,
                stream=stream_mode,
            )
            if stats:
                all_ollama_stats.append(stats)

    if not all_mlx_stats and not all_ollama_stats:
        print("\n[ERROR] No results collected.")
        return 1

    # Aggregate
    def avg_stats(stats_list: list[dict]) -> dict:
        if not stats_list:
            return {}
        keys = ["avg_ttft_ms", "min_ttft_ms", "max_ttft_ms", "avg_tps", "avg_latency_s"]
        result = {"runs": stats_list[0]["runs"], "model": stats_list[0]["model"]}
        for k in keys:
            result[k] = round(sum(s[k] for s in stats_list) / len(stats_list), 3)
        return result

    mlx_agg = avg_stats(all_mlx_stats)
    ollama_agg = avg_stats(all_ollama_stats)

    if mlx_agg and ollama_agg:
        print_comparison(mlx_agg, ollama_agg)
    elif mlx_agg:
        print(
            f"\nMLX only — Avg TTFT: {mlx_agg['avg_ttft_ms']}ms  |  Avg t/s: {mlx_agg['avg_tps']}"
        )
    elif ollama_agg:
        print(
            f"\nOllama only — Avg TTFT: {ollama_agg['avg_ttft_ms']}ms  |  Avg t/s: {ollama_agg['avg_tps']}"
        )

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
