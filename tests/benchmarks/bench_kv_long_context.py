#!/usr/bin/env python3
"""Portal 5 — KV / Long-Context Memory & Throughput Bench.

Finds the largest usable context per MLX model by sweeping prompt length and
recording peak memory + TPS at each step. Companion to bench_tps.py
(short-prompt steady-state) and bench_mlx_vs_ollama.py (matched-pair backend
comparison).

Goal: produce a per-model JSON record that TASK_KV_PROMOTE_V1 consumes to set
optimal `max_kv_size` values in config/backends.yaml.

Usage:
    # Single model, default ctx sweep
    python3 tests/benchmarks/bench_kv_long_context.py \\
        --model mlx-community/GLM-4.7-Flash-4bit

    # Custom ctx sweep + tag for before/after comparison
    python3 tests/benchmarks/bench_kv_long_context.py \\
        --model mlx-community/Qwen3-Coder-Next-4bit \\
        --ctx 8192,32768,65536,131072,200000 \\
        --kv-quant-tag off

    # Sweep all daily-routed MLX primaries (long-running)
    python3 tests/benchmarks/bench_kv_long_context.py --all-daily

Output:
    tests/benchmarks/results/kv_longctx_<UTC_ISO>.json

Method (per model, per ctx point):
    1. Probe /health pre-load; record state.
    2. POST a synthetic prompt of approximately N tokens with max_tokens=128.
    3. Stream the response; record TPS, TTFT, total tokens.
    4. Poll /health mid-decode; record peak Metal mem.
    5. Wait MEMORY_RECLAIM_WAIT seconds; probe /health post; record settled mem.
    6. Mark FAIL if: HTTP error, peak mem > 56 GB, decode TPS < 1, or
       admission control rejected the load.

Termination:
    The sweep stops for a model after the FIRST FAIL — the goal is to find
    the largest usable ctx, not to test failure modes beyond that.
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

import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

MLX_URL = os.environ.get("MLX_URL", "http://localhost:8081")
DEFAULT_CTX_SWEEP = [1024, 8192, 32768, 131072, 200000]
WARMUP_TIMEOUT = 300.0
INFERENCE_TIMEOUT = 600.0
MEMORY_RECLAIM_WAIT = 15.0
PEAK_MEM_SAMPLE_INTERVAL = 0.5
PEAK_MEM_FAIL_GB = 56.0  # hard fail threshold on 64GB M4 Pro


def _load_mlx_models() -> list[dict]:
    """Read mlx_models[] from config/backends.yaml."""
    cfg = yaml.safe_load((ROOT / "config" / "backends.yaml").read_text())
    for be in cfg.get("backends", []):
        if be.get("type") == "mlx":
            return be.get("mlx_models", [])
    return []


def _daily_routed_primaries() -> list[str]:
    """Workspace mlx_model_hint values for auto-* (non-bench) workspaces."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "workspaces", ROOT / "portal_pipeline" / "router" / "workspaces.py"
    )
    if not spec or not spec.loader:
        return []
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    hints = []
    for wsid, cfg in mod.WORKSPACES.items():
        if wsid.startswith("auto-") or wsid == "auto":
            h = cfg.get("mlx_model_hint")
            if h and h not in hints:
                hints.append(h)
    return hints


def _make_synthetic_prompt(target_tokens: int) -> str:
    """Build a prompt of approximately `target_tokens` tokens.

    Token estimate: ~3.5 chars per token for English text. Uses a repeating
    block of distinct content so the model cannot just echo a short pattern.
    """
    block = (
        "The Apache MXNet ecosystem provides distributed training primitives. "
        "Apple Silicon's unified memory model enables direct GPU access without "
        "host-device transfers. Memory bandwidth on M4 Pro is approximately 273 "
        "GB/s, which constrains decode throughput on large language models. "
    )
    char_budget = int(target_tokens * 3.5)
    text = (block * ((char_budget // len(block)) + 1))[:char_budget]
    return text + "\n\nSummarize the preceding text in two sentences."


def _probe_health() -> dict:
    """Read mlx-proxy /health. Returns dict with at least 'state' and 'memory'.

    Normalises the proxy's nested memory.current structure into a flat
    'used_gb' field so the rest of the bench can read it uniformly.
    """
    try:
        r = httpx.get(f"{MLX_URL}/health", timeout=5.0)
        d = r.json()
        cur = (d.get("memory") or {}).get("current") or {}
        total = cur.get("total_gb", 0.0)
        pct = cur.get("used_pct", 0.0)
        if total and pct:
            (d.setdefault("memory", {}))["used_gb"] = round(total * pct / 100, 1)
        return d
    except Exception as e:
        return {"state": "unreachable", "error": str(e)}


def _bench_one_ctx(model: str, ctx_tokens: int) -> dict:
    """One ctx point. Returns result dict; FAIL fields populated on error."""
    prompt = _make_synthetic_prompt(ctx_tokens)
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 128,
        "stream": True,
        "temperature": 0,
    }
    pre = _probe_health()
    pre_used = (pre.get("memory") or {}).get("used_gb")

    start = time.time()
    ttft = None
    tokens = 0
    err = None
    peak_seen = pre_used or 0.0

    try:
        with (
            httpx.Client(timeout=httpx.Timeout(INFERENCE_TIMEOUT, read=INFERENCE_TIMEOUT)) as c,
            c.stream("POST", f"{MLX_URL}/v1/chat/completions", json=body) as r,
        ):
            if r.status_code != 200:
                return {
                    "ctx_tokens_requested": ctx_tokens,
                    "status": "FAIL",
                    "fail_reason": f"HTTP {r.status_code}",
                    "fail_body": r.read().decode("utf-8", "replace")[:500],
                }
            last_sample = time.time()
            for line in r.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                if line == "data: [DONE]":
                    break
                if ttft is None:
                    ttft = time.time() - start
                try:
                    payload = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                delta = (payload.get("choices") or [{}])[0].get("delta", {})
                if delta.get("content"):
                    tokens += 1
                if time.time() - last_sample > PEAK_MEM_SAMPLE_INTERVAL:
                    h = _probe_health()
                    used = (h.get("memory") or {}).get("used_gb", 0.0)
                    peak_seen = max(peak_seen, used)
                    last_sample = time.time()
    except Exception as e:
        err = type(e).__name__ + ": " + str(e)[:200]

    elapsed = time.time() - start
    if err:
        return {
            "ctx_tokens_requested": ctx_tokens,
            "status": "FAIL",
            "fail_reason": err,
            "ttft_s": ttft,
            "elapsed_s": elapsed,
        }

    time.sleep(MEMORY_RECLAIM_WAIT)
    post = _probe_health()
    post_used = (post.get("memory") or {}).get("used_gb")

    decode_s = (elapsed - ttft) if ttft else None
    tps = (tokens / decode_s) if decode_s and decode_s > 0 else None

    status = "OK"
    fail_reason = None
    if peak_seen > PEAK_MEM_FAIL_GB:
        status = "FAIL"
        fail_reason = f"peak_used_gb={peak_seen:.1f} > {PEAK_MEM_FAIL_GB} (system risk)"
    elif tps is not None and tps < 1.0:
        status = "FAIL"
        fail_reason = f"tps={tps:.2f} < 1.0 (unusable throughput)"

    return {
        "ctx_tokens_requested": ctx_tokens,
        "status": status,
        "fail_reason": fail_reason,
        "ttft_s": round(ttft, 3) if ttft else None,
        "decode_s": round(decode_s, 3) if decode_s else None,
        "tokens_generated": tokens,
        "tps": round(tps, 2) if tps else None,
        "pre_used_gb": round(pre_used, 2) if pre_used else None,
        "peak_used_gb": round(peak_seen, 2),
        "post_used_gb": round(post_used, 2) if post_used else None,
        "delta_gb_to_pre": round(peak_seen - (pre_used or 0.0), 2),
    }


def _bench_model(model: str, ctx_sweep: list[int]) -> dict:
    """Sweep a single model; stop at first FAIL."""
    print(f"\n=== Bench: {model} ===")
    results: list[dict] = []
    largest_ok = 0
    for ctx in ctx_sweep:
        print(f"  ctx={ctx} ...", flush=True)
        r = _bench_one_ctx(model, ctx)
        results.append(r)
        print(f"    {r['status']}  peak={r.get('peak_used_gb')}GB  tps={r.get('tps')}")
        if r["status"] == "FAIL":
            print(f"    halting sweep for {model}: {r.get('fail_reason')}")
            break
        largest_ok = ctx
    return {
        "model": model,
        "ctx_sweep": ctx_sweep,
        "results": results,
        "largest_ok_ctx": largest_ok,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Portal 5 KV / long-context memory and throughput bench."
    )
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--model", help="Single MLX model HF path")
    g.add_argument(
        "--all-daily",
        action="store_true",
        help="Sweep all auto-* workspace primaries",
    )
    ap.add_argument(
        "--ctx",
        default=",".join(str(x) for x in DEFAULT_CTX_SWEEP),
        help="Comma-separated ctx points (default: 1024,8192,32768,131072,200000)",
    )
    ap.add_argument(
        "--kv-quant-tag",
        default="",
        help="Tag for output filename + JSON metadata (e.g. 'off', 'lm-kv4.5')",
    )
    args = ap.parse_args()

    ctx_sweep = [int(x.strip()) for x in args.ctx.split(",") if x.strip()]

    if args.all_daily:
        models = _daily_routed_primaries()
        print(f"Sweeping {len(models)} daily-routed primaries:")
        for m in models:
            print(f"  - {m}")
    else:
        models = [args.model]

    h0 = _probe_health()
    if h0.get("state") == "unreachable":
        print(f"FATAL: mlx-proxy not reachable at {MLX_URL}", file=sys.stderr)
        return 2

    all_results = [_bench_model(m, ctx_sweep) for m in models]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tag_suffix = f"_{args.kv_quant_tag}" if args.kv_quant_tag else ""
    out = RESULTS_DIR / f"kv_longctx_{stamp}{tag_suffix}.json"
    out.write_text(
        json.dumps(
            {
                "schema": "kv_longctx_v1",
                "captured_utc": stamp,
                "host": platform.platform(),
                "mlx_url": MLX_URL,
                "kv_quant_tag": args.kv_quant_tag,
                "models": all_results,
            },
            indent=2,
        )
    )
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
