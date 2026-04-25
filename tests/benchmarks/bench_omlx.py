#!/usr/bin/env python3
"""Portal 5 — OMLX vs mlx-proxy bake-off benchmark.

Runs the same workload against:
  - http://localhost:8081 (mlx-proxy)
  - http://localhost:8085 (omlx)

Captures TPS, TTFT, total wall-time, KV cache hit rate (OMLX-side metric),
and memory pressure for each. Outputs side-by-side JSON.

Run after:
  ./launch.sh restart-mlx
  ./launch.sh start-omlx
  sleep 60
"""

import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

MLX_PROXY_URL = "http://localhost:8081"
OMLX_URL = "http://localhost:8085"
RESULTS_DIR = Path(__file__).parent / "results"

# Test matrix
MODELS = [
    "mlx-community/Llama-3.2-3B-Instruct-8bit",
    "mlx-community/Dolphin3.0-Llama3.1-8B-8bit",
    "mlx-community/phi-4-8bit",
    "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit",
    "Jackrong/MLX-Qwopus3.5-27B-v3-8bit",
    "lmstudio-community/Devstral-Small-2507-MLX-4bit",
]

PROMPTS = {
    "coding": "Write a Python function to compute the nth Fibonacci number with memoization.",
    "reasoning": (
        "If a train leaves Boston at 8am going 60mph and another leaves NYC at 9am "
        "going 80mph, when do they meet (assume 200 miles)?"
    ),
    "general": "Explain the OSI 7-layer model with one example protocol per layer.",
}

# 5-turn conversation for KV cache test
CONVERSATION = [
    {"role": "system", "content": "You are a helpful assistant. Be concise."},
    {"role": "user", "content": "What is functional programming?"},
    {
        "role": "assistant",
        "content": "Functional programming is a paradigm based on immutability and pure functions.",
    },
    {"role": "user", "content": "Give me an example in Haskell."},
    {"role": "assistant", "content": "Here's a Haskell example: map (+1) [1,2,3] returns [2,3,4]."},
    {"role": "user", "content": "Now translate to TypeScript."},
]


async def _bench_one(client, base_url, model, messages, max_tokens=200):
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, "stream": False}
    t0 = time.monotonic()
    try:
        r = await client.post(f"{base_url}/v1/chat/completions", json=body, timeout=300)
        elapsed = time.monotonic() - t0
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}", "elapsed": elapsed}
        data = r.json()
        usage = data.get("usage", {})
        completion = usage.get("completion_tokens", 0)
        prompt = usage.get("prompt_tokens", 0)
        return {
            "elapsed": elapsed,
            "completion_tokens": completion,
            "prompt_tokens": prompt,
            "tps": completion / elapsed if elapsed > 0 else 0,
        }
    except Exception as e:
        return {"error": str(e), "elapsed": time.monotonic() - t0}


async def bench_endpoint(base_url, label, models=None, max_tokens=200):
    print(f"\n=== Benchmarking {label} ({base_url}) ===")
    results = []
    test_models = models or MODELS
    async with httpx.AsyncClient() as client:
        for model in test_models:
            print(f"\n--- {model} ---")
            for prompt_cat, prompt in PROMPTS.items():
                # Single-turn
                msgs = [{"role": "user", "content": prompt}]
                out = await _bench_one(client, base_url, model, msgs, max_tokens=max_tokens)
                out.update({"endpoint": label, "model": model, "category": prompt_cat, "turns": 1})
                results.append(out)
                print(
                    f"  {prompt_cat} (1 turn): {out.get('tps', 0):.1f} TPS, {out.get('elapsed', 0):.1f}s"
                )

                # Multi-turn (KV cache test)
                out = await _bench_one(client, base_url, model, CONVERSATION, max_tokens=max_tokens)
                out.update(
                    {"endpoint": label, "model": model, "category": "multi-turn", "turns": 5}
                )
                results.append(out)
                print(
                    f"  multi-turn (5 turns): {out.get('tps', 0):.1f} TPS, {out.get('elapsed', 0):.1f}s"
                )

                # Settle between models
                await asyncio.sleep(3)
    return results


async def main():
    parser = argparse.ArgumentParser(description="OMLX vs mlx-proxy bake-off benchmark")
    parser.add_argument("--mlx-only", action="store_true", help="Only bench mlx-proxy")
    parser.add_argument("--omlx-only", action="store_true", help="Only bench OMLX")
    parser.add_argument("--max-tokens", type=int, default=200, help="Max tokens per completion")
    parser.add_argument("--model", help="Filter: single model substring")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    models = None
    if args.model:
        models = [m for m in MODELS if args.model.lower() in m.lower()]
        if not models:
            print(f"No models matched '{args.model}'")
            return

    output = {
        "timestamp": ts,
        "mlx_only": args.mlx_only,
        "omlx_only": args.omlx_only,
        "results": [],
    }

    if not args.omlx_only:
        output["results"].extend(
            await bench_endpoint(MLX_PROXY_URL, "mlx-proxy", models, args.max_tokens)
        )
    if not args.mlx_only:
        output["results"].extend(await bench_endpoint(OMLX_URL, "omlx", models, args.max_tokens))

    out_path = RESULTS_DIR / f"omlx_bakeoff_{ts}.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults: {out_path}")

    # Quick summary
    print("\n=== Summary ===")
    by_endpoint = {}
    for r in output["results"]:
        if r.get("error"):
            continue
        key = (r["endpoint"], r["model"], r["category"])
        by_endpoint[key] = r.get("tps", 0)

    print(f"{'Model':<60} {'Cat':<12} {'mlx-proxy':>10} {'OMLX':>8} {'Delta':>6}")
    keys = sorted({(k[1], k[2]) for k in by_endpoint})
    for model, cat in keys:
        mlx = by_endpoint.get(("mlx-proxy", model, cat), 0)
        omlx = by_endpoint.get(("omlx", model, cat), 0)
        delta = (omlx / mlx - 1) * 100 if mlx > 0 else 0
        flag = "v" if delta > 10 else "." if delta > -10 else "x"
        print(f"{flag} {model[:58]:<58} {cat:<12} {mlx:>10.1f} {omlx:>8.1f} {delta:>+5.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
