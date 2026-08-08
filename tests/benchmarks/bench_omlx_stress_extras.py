"""Follow-on stress probes for P5-FUT-013 v3 (2026-08-05), closing gaps
flagged after the multi-model bake-off (reports/OMLX_OLLAMA_MULTIMODEL_BAKEOFF_V4):

  tools_load       Gate 3 (tool_calls) repeated under sustained concurrency —
                    does the single-shot PASS/FAIL from gate_tools hold up
                    when the same probe runs back-to-back under load?
  grammar_livelock  Gate 4 (json_schema) alternated unconstrained -> constrained
                    many times in a row on gemma, to try to reproduce the
                    reproducible-but-rare livelock noted in OMLX_DECISION.md.
  vision            VLM correctness + perf probe — 3 quant-matched oMLX/Ollama
                    pairs (Qwen3-VL-32B, supergemma4-26b multimodal, gemma-4-e4b)
                    against 3 synthetic images (shape/color, bar count, OCR text).
                    Not covered anywhere in the Phase-0 gate ladder or the V4
                    bake-off — bench_omlx_v3.py has no image-payload support.

Reuses bench_omlx_v3's one_request/warmup/model matrix so results are
comparable to the existing gate artifacts. Not merged into bench_omlx_v3.py's
GATES dict — these are one-off follow-up probes, not part of the Phase-0 gate
ladder.
"""

from __future__ import annotations

import argparse
import base64
import json
import statistics as st
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import bench_omlx_v3 as base

RESULTS_DIR = Path(__file__).parent / "results"
ASSETS_DIR = Path(__file__).parent / "assets"

UNCONSTRAINED_PROMPT = "Briefly describe, in one or two sentences, what a doubly linked list is."

# ── Vision (VLM) model matrix ────────────────────────────────────────────────
# Quant-matched pairs verified via `du -shL` on the oMLX side vs `ollama show`
# size on the Ollama side (all within the same quant class as the rest of the
# bake-off's parity audits — see bench_omlx_v3.py's OLLAMA_BASELINES comments).
VISION_MODELS = {
    "qwen-vl": {  # 18GB (oMLX 4bit) vs 20.9GB (Ollama ctx8k) — dedicated VLM
        "omlx": "Qwen3-VL-32B-Instruct-4bit",
        "ollama": "qwen3-vl:32b-ctx8k",
    },
    "supergemma-vl": {  # 15GB (oMLX 4bit) vs 16.8GB (Ollama Q4_K_M) — multimodal
        "omlx": "supergemma4-26b-abliterated-multimodal-mlx-4bit",
        "ollama": "supergemma4-26b-uncensored:Q4_K_M-ctx64k",
    },
    "gemma-e4b-vl": {  # 4.8GB (oMLX 4bit) vs 6.1GB (Ollama qat) — same pair used
        "omlx": "gemma-4-e4b-it-4bit",  # for text tasks in V4, gemma4 e4b is vision-capable
        "ollama": "gemma4:e4b-it-qat-ctx8k",
    },
}

VISION_PROBES = [
    {
        "name": "shape_color",
        "image": "vision_probe_shape.png",
        "prompt": "What color and what shape is drawn in this image? Answer in a few words.",
        "expect_any": ["red", "circle"],
    },
    {
        "name": "bar_count",
        "image": "vision_probe_bars.png",
        "prompt": "How many bars are in this bar chart? Answer with just the number.",
        "expect_any": ["5", "five"],
    },
    {
        "name": "ocr_text",
        "image": "vision_probe_text.png",
        "prompt": "What text is written in this image? Answer with just the text.",
        "expect_any": ["portal5", "portal 5"],
    },
]


def _image_data_url(name: str) -> str:
    data = (ASSETS_DIR / name).read_bytes()
    return f"data:image/png;base64,{base64.b64encode(data).decode()}"


def vision_probe(url: str, model: str, think: bool | None = None) -> list[dict]:
    print(f"    [vision] {model} @ {url}", flush=True)
    if not base.warmup(url, model, think=think):
        return [{"test": "vision", "model": model, "error": "warmup failed"}]

    results = []
    for probe in VISION_PROBES:
        data_url = _image_data_url(probe["image"])
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": probe["prompt"]},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ]
        # 500, not 100: thinking-capable checkpoints (e.g. Ollama's gemma4 e4b,
        # which defaults thinking ON unlike oMLX's same checkpoint) burn their
        # budget on reasoning before answering — verified live: max_tokens=100
        # produced finish_reason=length with 0 visible chars; 600 answered correctly.
        r = base.one_request(url, model, messages, max_tokens=500, think=think)
        if "error" in r:
            verdict, detail = "FAIL", r["error"]
        else:
            preview = (r.get("response_preview") or "").lower()
            hit = any(kw in preview for kw in probe["expect_any"])
            verdict = "PASS" if hit else "FAIL"
            detail = r.get("response_preview") or ""
        print(f"      {probe['name']}: {verdict} ({detail[:80]!r})", flush=True)
        results.append(
            {
                "test": "vision",
                "probe": probe["name"],
                "model": model,
                "verdict": verdict,
                "detail": detail,
                "ttft_s": r.get("ttft_s"),
                "elapsed_s": r.get("elapsed_s"),
                "tps": r.get("tps"),
                "error": r.get("error"),
            }
        )
    return results


def tools_load(
    url: str, model: str, duration_s: int, concurrency: int, think: bool | None = None
) -> dict:
    print(f"    [tools_load] {model} @ {url} ({concurrency}x for {duration_s}s)", flush=True)
    if not base.warmup(url, model, think=think):
        return {"test": "tools_load", "model": model, "error": "warmup failed"}

    samples: list[dict] = []
    stop_at = time.perf_counter() + duration_s
    lock = threading.Lock()

    def _classify(r: dict) -> str:
        if "error" in r:
            return "timeout" if r["error"] == "timeout" else "error"
        if r.get("tool_calls"):
            return "tool_call"
        preview = r.get("response_preview") or ""
        if '"name"' in preview or "<tool_call>" in preview:
            return "text_only"
        return "no_tool"

    def _worker() -> None:
        while time.perf_counter() < stop_at:
            r = base.one_request(
                url,
                model,
                [{"role": "user", "content": base.TOOLS_PROMPT}],
                max_tokens=150,
                extra={"tools": base.TOOLS_PROBE},
                think=think,
            )
            r["outcome"] = _classify(r)
            with lock:
                samples.append(r)

    t0 = time.perf_counter()
    threads = [threading.Thread(target=_worker) for _ in range(concurrency)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall_s = time.perf_counter() - t0

    counts: dict[str, int] = {}
    for r in samples:
        counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
    ok = [
        r
        for r in samples
        if r["outcome"] != "error" and r["outcome"] != "timeout" and r.get("ttft_s") is not None
    ]
    ttfts = sorted(r["ttft_s"] for r in ok)

    result = {
        "test": "tools_load",
        "model": model,
        "duration_s": duration_s,
        "concurrency": concurrency,
        "wall_s": round(wall_s, 1),
        "total_requests": len(samples),
        "counts": counts,
        "tool_call_rate": round(counts.get("tool_call", 0) / len(samples), 3) if samples else None,
        "ttft_p50": round(ttfts[len(ttfts) // 2], 3) if ttfts else None,
        "ttft_p99": round(ttfts[min(len(ttfts) - 1, int(0.99 * (len(ttfts) - 1)))], 3)
        if ttfts
        else None,
        "verdict": "PASS" if counts.get("tool_call", 0) == len(samples) and samples else "DEGRADED",
    }
    print(
        f"      {len(samples)} reqs, counts={counts}, "
        f"ttft p50/p99={result['ttft_p50']}/{result['ttft_p99']}s -> {result['verdict']}",
        flush=True,
    )
    return result


def grammar_livelock(
    url: str, model: str, iterations: int, timeout_s: float, think: bool | None = None
) -> dict:
    print(
        f"    [grammar_livelock] {model} @ {url} ({iterations} unconstrained<->constrained cycles)",
        flush=True,
    )
    if not base.warmup(url, model, think=think):
        return {"test": "grammar_livelock", "model": model, "error": "warmup failed"}

    orig_timeout = base.REQUEST_TIMEOUT
    base.REQUEST_TIMEOUT = timeout_s
    cycles: list[dict] = []
    try:
        for i in range(iterations):
            r_u = base.one_request(
                url,
                model,
                [{"role": "user", "content": UNCONSTRAINED_PROMPT}],
                max_tokens=100,
                think=think,
            )
            r_c = base.one_request(
                url,
                model,
                [{"role": "user", "content": base.GRAMMAR_PROMPT}],
                max_tokens=256,
                extra={
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "route",
                            "schema": base.GRAMMAR_SCHEMA,
                            "strict": True,
                        },
                    }
                },
                think=think,
            )
            u_ok = "error" not in r_u
            c_ok = "error" not in r_c
            cycles.append(
                {
                    "i": i,
                    "unconstrained_ok": u_ok,
                    "unconstrained_elapsed_s": r_u.get("elapsed_s"),
                    "unconstrained_error": r_u.get("error"),
                    "constrained_ok": c_ok,
                    "constrained_elapsed_s": r_c.get("elapsed_s"),
                    "constrained_error": r_c.get("error"),
                }
            )
            status = "ok" if (u_ok and c_ok) else "LIVELOCK/FAIL"
            print(
                f"      cycle {i}: unconstrained={r_u.get('elapsed_s')}s "
                f"constrained={r_c.get('elapsed_s')}s -> {status}",
                flush=True,
            )
    finally:
        base.REQUEST_TIMEOUT = orig_timeout

    livelocks = [c for c in cycles if not (c["unconstrained_ok"] and c["constrained_ok"])]
    elapsed_c = [
        c["constrained_elapsed_s"] for c in cycles if c["constrained_elapsed_s"] is not None
    ]
    result = {
        "test": "grammar_livelock",
        "model": model,
        "iterations": iterations,
        "timeout_s": timeout_s,
        "livelock_count": len(livelocks),
        "livelock_rate": round(len(livelocks) / iterations, 3) if iterations else None,
        "constrained_elapsed_p50": round(st.median(elapsed_c), 3) if elapsed_c else None,
        "constrained_elapsed_max": round(max(elapsed_c), 3) if elapsed_c else None,
        "cycles": cycles,
        "verdict": "PASS" if not livelocks else "LIVELOCK_REPRODUCED",
    }
    print(f"      livelocks: {len(livelocks)}/{iterations} -> {result['verdict']}", flush=True)
    return result


PROBES = {"tools_load": tools_load, "grammar_livelock": grammar_livelock, "vision": vision_probe}


def main() -> None:
    p = argparse.ArgumentParser(description="oMLX v3 follow-up stress probes")
    p.add_argument("--probe", choices=list(PROBES), required=True)
    p.add_argument("--url", required=True)
    p.add_argument(
        "--models",
        required=True,
        help="Comma list of keys from OMLX_MODELS/VISION_MODELS, or explicit ids",
    )
    p.add_argument("--duration", type=int, default=90)
    p.add_argument("--concurrency", type=int, default=5)
    p.add_argument("--iterations", type=int, default=20)
    p.add_argument("--timeout", type=float, default=45.0)
    p.add_argument("--think", choices=["on", "off"], default=None)
    p.add_argument("--tag", default=None)
    args = p.parse_args()
    think = {"on": True, "off": False, None: None}[args.think]

    engine = "omlx" if "8085" in args.url else ("ollama" if "11434" in args.url else "pipeline")

    keys = args.models.split(",")
    if args.probe == "vision":
        engine_side = "omlx" if engine == "omlx" else "ollama"
        models = [VISION_MODELS[k][engine_side] if k in VISION_MODELS else k for k in keys]
    else:
        models = [base.OMLX_MODELS.get(k, k) for k in keys]

    started = datetime.now(UTC)
    results = []
    for model in models:
        print(f"\n=== {model} @ {args.url} ===", flush=True)
        if args.probe == "tools_load":
            r = tools_load(args.url, model, args.duration, args.concurrency, think=think)
            r["engine"] = engine
            results.append(r)
        elif args.probe == "vision":
            rs = vision_probe(args.url, model, think=think)
            for r in rs:
                r["engine"] = engine
            results.extend(rs)
        else:
            r = grammar_livelock(args.url, model, args.iterations, args.timeout, think=think)
            r["engine"] = engine
            results.append(r)

    ts = started.strftime("%Y%m%dT%H%M%SZ")
    tag = f"_{args.tag}" if args.tag else ""
    out = RESULTS_DIR / f"omlx_v3_{args.probe}{tag}_{engine}_{ts}.json"
    out.write_text(
        json.dumps(
            {
                "probe": args.probe,
                "engine": engine,
                "url": args.url,
                "started": started.isoformat(),
                "results": results,
            },
            indent=2,
        )
    )
    print(f"\nResults -> {out}")


if __name__ == "__main__":
    main()
