#!/usr/bin/env python3
"""Ad hoc TPS bench for Hugging Face mlx-community models via mlx_lm directly.

Ollama's own hf.co puller only accepts GGUF ("Repository is not GGUF or is
not compatible with llama.cpp") — it cannot pull mlx-community safetensors
repos, even though Ollama has its own separate, much narrower set of
official "-mlx" library tags (see project_gemma_mtp_mlx_only memory). This
script fills that gap for one-off comparison benching: pull a HF mlx-community
repo (snapshot_download, same mechanism launch.sh used pre-retirement) and
run it through mlx_lm.generate directly — no server, no proxy, no admission
control, nothing persistent or wired into the pipeline.

This is NOT a revival of the retired MLX proxy stack (scripts/_archive/
mlx-retired-3a0c58e/). It's a throwaway measurement tool. Do not add
launch.sh hooks, systemd/launchd services, or pipeline integration for this
without a deliberate decision to bring MLX back as a supported tier.

Usage:
    python3 tests/benchmarks/bench_mlx_hf.py mlx-community/Qwen3.6-27B-4bit
    python3 tests/benchmarks/bench_mlx_hf.py --runs 5 --output results/mlx_hf_20260701.json \\
        mlx-community/Qwen3.6-27B-4bit mlx-community/GLM-4.7-Flash-4bit
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

DEFAULT_HF_CACHE = "/Volumes/data01/hf-cache"
# Must be set before any huggingface_hub/mlx_lm import resolves its cache path,
# so the pull (snapshot_download) and the load (mlx_lm.load) agree on location —
# otherwise mlx_lm.load() silently re-downloads to ~/.cache/huggingface/hub.
os.environ.setdefault("HF_HUB_CACHE", DEFAULT_HF_CACHE)

sys.path.insert(0, str(Path(__file__).parent))
from bench.prompts import PROMPTS  # noqa: E402


def pull(repo: str) -> None:
    from huggingface_hub import snapshot_download

    cache_dir = os.environ["HF_HUB_CACHE"]
    print(f"  Pulling {repo} -> {cache_dir} ...")
    snapshot_download(
        repo,
        cache_dir=cache_dir,
        ignore_patterns=["*.md", "*.txt", "*.safetensors.index.json"],
    )


def bench_one(repo: str, prompt: str, max_tokens: int, runs: int) -> dict:
    from mlx_lm import load
    from mlx_lm.generate import stream_generate

    print(f"  Loading {repo} ...")
    t_load0 = time.perf_counter()
    model, tokenizer = load(repo)
    load_s = round(time.perf_counter() - t_load0, 1)

    messages = [{"role": "user", "content": prompt}]
    formatted = tokenizer.apply_chat_template(messages, add_generation_prompt=True)

    tps_vals = []
    for i in range(runs):
        last = None
        for resp in stream_generate(model, tokenizer, prompt=formatted, max_tokens=max_tokens):
            last = resp
        if last is None:
            print(f"    run {i + 1}: no output")
            continue
        tps_vals.append(last.generation_tps)
        print(
            f"    run {i + 1}: {last.generation_tps:.1f} t/s "
            f"({last.generation_tokens} tokens, prompt_tps={last.prompt_tps:.1f})"
        )

    avg_tps = round(sum(tps_vals) / len(tps_vals), 1) if tps_vals else 0.0
    return {
        "repo": repo,
        "load_s": load_s,
        "runs_success": len(tps_vals),
        "runs_total": runs,
        "avg_tps": avg_tps,
        "min_tps": round(min(tps_vals), 1) if tps_vals else 0.0,
        "max_tps": round(max(tps_vals), 1) if tps_vals else 0.0,
        "tps_vals": [round(t, 1) for t in tps_vals],
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("repos", nargs="+", help="HF repo IDs, e.g. mlx-community/Qwen3.6-27B-4bit")
    ap.add_argument("--category", default="general", choices=list(PROMPTS.keys()))
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument(
        "--skip-pull", action="store_true", help="Assume repos are already cached locally"
    )
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    prompt = PROMPTS[args.category]
    results = []
    for repo in args.repos:
        print(f"\n=== {repo} ===")
        if not args.skip_pull:
            pull(repo)
        r = bench_one(repo, prompt, args.max_tokens, args.runs)
        results.append(r)

    print("\n" + "=" * 70)
    print(f"{'Repo':<55} {'Avg TPS':>10}")
    print("=" * 70)
    for r in results:
        print(f"{r['repo']:<55} {r['avg_tps']:>10}")

    if args.output:
        Path(args.output).write_text(
            json.dumps({"category": args.category, "results": results}, indent=2)
        )
        print(f"\nResults: {args.output}")


if __name__ == "__main__":
    main()
