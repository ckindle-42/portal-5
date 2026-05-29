#!/usr/bin/env python3
"""Positional recall benchmark — LCS line-alignment under long context.

Measures verbatim function-body reproduction accuracy at depth N for
long-context lanes. Reports pass-rate by position bucket (front/middle/tail)
to surface lost-in-the-middle effects.

Method adapted from github.com/alexziskind1/codeneedle (Alex Ziskind).
Talks to MLX-proxy via OpenAI-compatible /v1/chat/completions endpoint.
One model at a time, sequential, with cooldown — isolation rule (A5).

Complements bench_kv_long_context.py (survival) by measuring *usefulness*
at the configured ceiling.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from recall_scorer import score_function_recall  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from recall_extract import (  # noqa: E402
    assemble_corpus,
    bucket,
    extract_functions,
    sample,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKENDS_YAML = REPO_ROOT / "config" / "backends.yaml"
RESULTS_DIR = REPO_ROOT / "tests" / "benchmarks" / "results"

MLX_URL = os.environ.get("MLX_URL", "http://localhost:8081")
DEFAULT_SOURCES: list[str] = [
    "portal_pipeline/cluster_backends.py",
    "scripts/mlx-proxy.py",
    "tests/benchmarks/bench_tps.py",
]


def _load_longctx_models() -> list[dict[str, Any]]:
    """Find all MLX models with max_kv_size set in backends.yaml."""
    import yaml

    cfg = yaml.safe_load(BACKENDS_YAML.read_text())
    models: list[dict[str, Any]] = []
    for be in cfg.get("backends", []):
        if be.get("type") != "mlx":
            continue
        for m in be.get("mlx_models", []):
            if m.get("max_kv_size"):
                models.append(
                    {
                        "model": m["id"],
                        "max_kv_size": m["max_kv_size"],
                        "big_model": m.get("big_model", False),
                    }
                )
    return models


def _token_est(text: str) -> int:
    """Rough token estimate — bytes / 4."""
    return len(text.encode()) // 4


def _hardware_info() -> dict[str, Any]:
    return {
        "platform": platform.system(),
        "machine": platform.machine(),
        "cpu": platform.processor() or "unknown",
    }


def _query_model(
    model: str,
    prompt: str,
    max_tokens: int = 4000,
    timeout: float = 300.0,
) -> dict[str, Any]:
    """Send a chat completion to MLX-proxy, capturing response and timing."""
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": "/nothink\n" + prompt},
        ],
        "stream": True,
        "max_tokens": max_tokens,
    }

    t0 = time.perf_counter()
    t_first_token: float | None = None
    completion_tokens = 0
    response_text = ""

    try:
        with httpx.Client(timeout=timeout) as client:
            with client.stream(
                "POST",
                f"{MLX_URL}/v1/chat/completions",
                json=payload,
            ) as resp:
                if resp.status_code != 200:
                    body = resp.read()[:200].decode(errors="replace")
                    return {
                        "error": f"HTTP {resp.status_code}: {body[:80]}",
                        "elapsed_s": round(time.perf_counter() - t0, 2),
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
                    if chunk and t_first_token is None:
                        t_first_token = time.perf_counter()
                    response_text += chunk
                    completion_tokens += len(chunk.split())
    except Exception as exc:
        return {
            "error": str(exc)[:200],
            "elapsed_s": round(time.perf_counter() - t0, 2),
        }

    elapsed = time.perf_counter() - t0
    tps = completion_tokens / (elapsed - (t_first_token - t0 if t_first_token else 0)) if elapsed > 0 and t_first_token and completion_tokens > 0 else 0

    return {
        "response_text": response_text,
        "completion_tokens": completion_tokens,
        "elapsed_s": round(elapsed, 2),
        "ttft_s": round(t_first_token - t0, 3) if t_first_token else None,
        "tps": round(tps, 1),
    }


def _ensure_health(timeout_s: int = 120) -> bool:
    """Wait for MLX proxy to be healthy."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = httpx.get(f"{MLX_URL}/health", timeout=5.0)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(3)
    return False


def _evict_models() -> None:
    """Ask MLX proxy to evict all loaded models."""
    try:
        httpx.post(f"{MLX_URL}/evict", timeout=10.0)
    except Exception:
        pass


def run_bench(
    model: str,
    max_kv_size: int,
    k: int = 12,
    seed: int = 42,
    n_lines: int = 20,
    pass_threshold: int = 8,
    cooldown: int = 15,
    sources: list[str] | None = None,
) -> dict[str, Any]:
    """Run the positional recall bench for one model at its configured ceiling.

    Returns the full result dict (schema from Phase 3).
    """
    src_paths = sources or DEFAULT_SOURCES
    corpus, functions = assemble_corpus(
        [str(REPO_ROOT / s) for s in src_paths],
        target_ctx=max_kv_size,
    )

    corpus_tokens = _token_est(corpus)

    # Tag each function with its position bucket
    total_chars = len(corpus)
    for f in functions:
        f["bucket"] = bucket(f["char_offset"], total_chars)

    sampled = sample(functions, k=k, seed=seed)
    if len(sampled) < k:
        print(f"  WARN: only {len(sampled)} functions sampled (wanted {k})")

    results: list[dict[str, Any]] = []
    print(f"  Corpus: {corpus_tokens:,} tok est (target {max_kv_size:,}), "
          f"{len(functions)} functions, sampled {len(sampled)}, "
          f"sources: {', '.join(Path(s).name for s in src_paths)}")

    for i, fn in enumerate(sampled):
        name = fn["name"]
        fn_bucket = fn.get("bucket", "front")
        expected_body = fn["body"]

        prompt = (
            f"{corpus}\n\n"
            f"Reproduce the first {n_lines} lines of the function named "
            f"`{name}` exactly as it appears above, verbatim, no commentary."
        )

        print(f"    [{i+1}/{len(sampled)}] {name} ({fn_bucket})...", end=" ", flush=True)
        resp = _query_model(model, prompt, max_tokens=n_lines * 40 + 2000)
        if "error" in resp:
            print(f"ERROR: {resp['error'][:60]}")
            results.append(
                {
                    "name": name,
                    "bucket": fn_bucket,
                    "error": resp["error"],
                    "recall": 0.0,
                    "passed": False,
                    "matched": 0,
                    "missing": n_lines,
                    "hallucinated": 0,
                    "bonus": 0,
                    "tps": 0,
                }
            )
            continue

        produced = resp.get("response_text", "")
        score = score_function_recall(expected_body, produced, n_lines, pass_threshold)
        print(
            f"recall={score['recall']:.2f} "
            f"({'PASS' if score['passed'] else 'FAIL'}) "
            f"tps={resp.get('tps', 0):.1f}"
        )
        results.append(
            {
                "name": name,
                "bucket": fn_bucket,
                "recall": score["recall"],
                "passed": score["passed"],
                "matched": score["matched"],
                "missing": score["missing"],
                "hallucinated": score["hallucinated"],
                "bonus": score["bonus"],
                "tps": resp.get("tps", 0),
                "ttft_s": resp.get("ttft_s"),
                "elapsed_s": resp.get("elapsed_s"),
            }
        )

        if cooldown and i < len(sampled) - 1:
            time.sleep(cooldown)

    # Aggregate by bucket
    by_bucket: dict[str, dict[str, Any]] = {}
    for b in ("front", "middle", "tail"):
        bucket_results = [r for r in results if r["bucket"] == b and "error" not in r]
        n = len(bucket_results)
        if n > 0:
            by_bucket[b] = {
                "pass_rate": round(sum(1 for r in bucket_results if r["passed"]) / n, 2),
                "mean_recall": round(sum(r["recall"] for r in bucket_results) / n, 2),
                "n": n,
            }
        else:
            by_bucket[b] = {"pass_rate": 0.0, "mean_recall": 0.0, "n": 0}

    valid = [r for r in results if "error" not in r]
    overall_pass = (
        round(sum(1 for r in valid if r["passed"]) / len(valid), 2) if valid else 0.0
    )
    overall_recall = (
        round(sum(r["recall"] for r in valid) / len(valid), 2) if valid else 0.0
    )

    front_tail_mean = (
        (by_bucket["front"]["pass_rate"] + by_bucket["tail"]["pass_rate"]) / 2
    )
    lost_in_middle_delta = round(front_tail_mean - by_bucket["middle"]["pass_rate"], 2)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "max_kv_size": max_kv_size,
        "target_ctx": max_kv_size,
        "corpus_tokens_est": corpus_tokens,
        "k": k,
        "seed": seed,
        "n_lines": n_lines,
        "pass_threshold": pass_threshold,
        "hardware": _hardware_info(),
        "by_bucket": by_bucket,
        "overall": {"pass_rate": overall_pass, "mean_recall": overall_recall},
        "lost_in_middle_delta": lost_in_middle_delta,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Positional Recall Benchmark — LCS line-alignment under long context"
    )
    parser.add_argument("--model", help="Single MLX model ID to bench")
    parser.add_argument(
        "--all-longctx",
        action="store_true",
        help="Bench all long-context lanes (those with max_kv_size set)",
    )
    parser.add_argument("--source", action="append", dest="sources", help="Source file(s) for corpus")
    parser.add_argument("--k", type=int, default=12, help="Number of functions to sample")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for sampling")
    parser.add_argument("--n-lines", type=int, default=20, help="Lines to compare from each function")
    parser.add_argument("--pass-threshold", type=int, default=8, help="Matched lines needed for pass")
    parser.add_argument("--cooldown", type=int, default=15, help="Seconds between queries")
    parser.add_argument("--target-ctx", type=int, help="Override target context size")
    parser.add_argument("--output", help="Output JSON path")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Assemble corpus and print sampling plan without querying LLM",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("Portal 5 — Positional Recall Benchmark")
    print("=" * 70)
    hw = _hardware_info()
    print(f"Hardware: {json.dumps(hw)}")
    print(f"k={args.k}  seed={args.seed}  n_lines={args.n_lines}  "
          f"pass_threshold={args.pass_threshold}  cooldown={args.cooldown}s")

    if not args.dry_run:
        if not _ensure_health():
            print("ERROR: MLX proxy not healthy at", MLX_URL)
            sys.exit(1)
        print("MLX proxy: healthy")
    else:
        print("MLX proxy: skipped (dry-run)")

    models_to_bench: list[dict[str, Any]] = []
    if args.all_longctx:
        models_to_bench = _load_longctx_models()
        if not models_to_bench:
            print("ERROR: no long-context models found (need max_kv_size in backends.yaml)")
            sys.exit(1)
        print(f"\nLong-context lanes: {len(models_to_bench)}")
        for m in models_to_bench:
            print(f"  {m['model']}  max_kv={m['max_kv_size']:,}")
    elif args.model:
        kv = args.target_ctx or 32768
        # Try to find max_kv_size from catalog
        for m in _load_longctx_models():
            if m["model"] == args.model:
                kv = m["max_kv_size"]
                break
        models_to_bench = [{"model": args.model, "max_kv_size": kv, "big_model": False}]
    else:
        print("ERROR: specify --model or --all-longctx")
        sys.exit(1)

    if args.dry_run:
        print("\n--dry-run: assembling corpus for first model only")
        src_paths = args.sources or DEFAULT_SOURCES
        model = models_to_bench[0]
        corpus, functions = assemble_corpus(
            [str(REPO_ROOT / s) for s in src_paths],
            target_ctx=model["max_kv_size"],
        )
        for f in functions:
            f["bucket"] = bucket(f["char_offset"], len(corpus))
        sampled = sample(functions, k=args.k, seed=args.seed)
        by_b = {"front": 0, "middle": 0, "tail": 0}
        for f in sampled:
            by_b[f["bucket"]] += 1
        print(f"  Corpus: {_token_est(corpus):,} tok est, {len(functions)} functions")
        print(f"  Sampled: {len(sampled)} functions")
        print(f"  By bucket: front={by_b['front']} middle={by_b['middle']} tail={by_b['tail']}")
        return

    all_results: list[dict[str, Any]] = []
    for i, m in enumerate(models_to_bench):
        model_id = m["model"]
        print(f"\n{'─' * 70}")
        print(f"[{i+1}/{len(models_to_bench)}] {model_id}  max_kv={m['max_kv_size']:,}")
        print(f"{'─' * 70}")

        result = run_bench(
            model=model_id,
            max_kv_size=m["max_kv_size"],
            k=args.k,
            seed=args.seed,
            n_lines=args.n_lines,
            pass_threshold=args.pass_threshold,
            cooldown=args.cooldown,
            sources=args.sources,
        )

        all_results.append(result)
        print(f"  Complete — overall pass_rate={result['overall']['pass_rate']:.2f}, "
              f"LIM-delta={result['lost_in_middle_delta']:.2f}")

        _evict_models()
        time.sleep(args.cooldown)

    output_path = args.output
    if not output_path and models_to_bench:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_path = str(RESULTS_DIR / f"recall_all_{ts}.json")

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        if len(all_results) == 1:
            with open(output_path, "w") as f:
                json.dump(all_results[0], f, indent=2)
        else:
            combined = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "hardware": _hardware_info(),
                "config": {
                    "k": args.k, "seed": args.seed,
                    "n_lines": args.n_lines, "pass_threshold": args.pass_threshold,
                },
                "models": all_results,
            }
            with open(output_path, "w") as f:
                json.dump(combined, f, indent=2)
        print(f"\nResults: {output_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
