"""Ad-hoc TPS/quality probe for models NOT registered in config/backends.yaml.

bench_tps's --model filter matches against the configured backends.yaml
model list — it cannot test a freshly-`ollama pull`ed candidate tag until
that tag is wired into config. That's the right default (bench_tps's job
is regression-tracking the production fleet), but it means there was no
lightweight way to sanity-check an unregistered candidate's raw TPS before
deciding whether it's worth wiring in at all — every one-off eval
(TASK_EVAL_GEMMA4_MLX_TAGS_V1 and future candidate probes) was reinventing
this loop from scratch in a /tmp script.

This reuses bench's own PROMPTS library and TPS formula (streaming
OpenAI-compat endpoint, tps = completion_tokens / elapsed wall time) so
numbers measured here are directly comparable to bench_tps's own output,
without touching backends.yaml or any other config.

Usage:
    python3 -m tests.benchmarks.bench.adhoc_probe --model gemma4:e2b-mlx --model gemma4:e2b-it-qat
    python3 -m tests.benchmarks.bench.adhoc_probe --model some:candidate --runs 3 --prompt-category coding
    python3 -m tests.benchmarks.bench.adhoc_probe --model some:candidate --output /tmp/probe.json

This is scoped to direct-Ollama probing only (no pipeline/workspace mode —
an unregistered model has no workspace). Once a candidate looks promising,
register it in backends.yaml and use bench_tps proper for the real,
regression-tracked measurement.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import httpx

from .config import MAX_TOKENS, OLLAMA_URL, REQUEST_TIMEOUT
from .prompts import PROMPTS


def _warmup(client: httpx.Client, model: str) -> bool:
    try:
        r = client.post(
            f"{OLLAMA_URL}/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
                "max_tokens": 1,
            },
            timeout=300.0,
        )
        return r.status_code == 200
    except Exception as e:
        print(f"  warmup failed: {e}")
        return False


def _run_one(client: httpx.Client, model: str, prompt: str, run_num: int) -> dict:
    """Run one streaming trial.

    Reasoning-model note (mirrors bench/measure.py): a "thinking" model
    (gemma4's Capabilities list includes ``thinking``) emits most or all
    of a response through ``delta.reasoning``, not ``delta.content`` —
    counting only content silently reports "empty response" for models
    that are actually generating plenty of tokens, and undercounts TPS
    for any model that reasons before answering. Reasoning tokens are
    real generation work and count toward TPS here, same as bench_tps.
    """
    t0 = time.perf_counter()
    completion_tokens = 0
    response_text = ""
    reasoning_text = ""
    try:
        with client.stream(
            "POST",
            f"{OLLAMA_URL}/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": True,
                "max_tokens": MAX_TOKENS,
            },
            timeout=REQUEST_TIMEOUT,
        ) as resp:
            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    continue
                try:
                    obj = json.loads(data_str)
                except Exception:
                    continue
                choices = obj.get("choices") or []
                delta = choices[0].get("delta", {}) if choices else {}
                response_text += delta.get("content") or ""
                reasoning_text += delta.get("reasoning") or ""
                usage = obj.get("usage") or {}
                if usage.get("completion_tokens"):
                    completion_tokens = usage["completion_tokens"]
    except Exception as e:
        return {"run": run_num, "error": str(e)[:150]}

    elapsed = time.perf_counter() - t0
    combined_text = response_text + (" " + reasoning_text if reasoning_text else "")
    if completion_tokens == 0 and combined_text.strip():
        completion_tokens = max(1, len(combined_text.split()))
    if completion_tokens == 0:
        return {"run": run_num, "error": "empty response"}
    tps = completion_tokens / elapsed if elapsed > 0 else 0.0
    return {
        "run": run_num,
        "elapsed_s": round(elapsed, 2),
        "completion_tokens": completion_tokens,
        "tps": round(tps, 1),
    }


def probe_models(models: list[str], runs: int, prompt_category: str) -> dict:
    prompt = PROMPTS.get(prompt_category, PROMPTS["general"])
    results: dict[str, dict] = {}
    with httpx.Client() as client:
        for model in models:
            print(f"=== {model} ===")
            if not _warmup(client, model):
                print("  WARMUP FAILED, skipping")
                results[model] = {"error": "warmup_failed"}
                continue
            trials = [_run_one(client, model, prompt, i) for i in range(runs)]
            for t in trials:
                if "error" in t:
                    print(f"  run {t['run']}: ERROR {t['error']}")
                else:
                    print(
                        f"  run {t['run']}: tps={t['tps']} tokens={t['completion_tokens']} "
                        f"elapsed={t['elapsed_s']}s"
                    )
            tps_vals = [t["tps"] for t in trials if "tps" in t]
            if tps_vals:
                results[model] = {
                    "median_tps": round(statistics.median(tps_vals), 1),
                    "mean_tps": round(statistics.mean(tps_vals), 1),
                    "stdev_tps": round(statistics.stdev(tps_vals), 2) if len(tps_vals) > 1 else 0.0,
                    "n_trials": len(tps_vals),
                    "trials": trials,
                }
            else:
                results[model] = {"error": "all_trials_failed", "trials": trials}
            print()
    return results


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Ad-hoc TPS probe for unregistered model tags")
    p.add_argument("--model", action="append", required=True, help="Ollama model tag (repeatable)")
    p.add_argument("--runs", type=int, default=5, help="Trials per model (default: 5)")
    p.add_argument(
        "--prompt-category",
        default="general",
        choices=list(PROMPTS.keys()),
        help="Which prompt from bench's PROMPTS library to use (default: general)",
    )
    p.add_argument("--output", type=Path, default=None, help="Write JSON results here")
    args = p.parse_args(argv)

    results = probe_models(args.model, args.runs, args.prompt_category)

    if args.output:
        args.output.write_text(json.dumps(results, indent=2))
        print(f"Saved to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
