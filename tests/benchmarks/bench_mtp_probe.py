#!/usr/bin/env python3
"""MTP/speculative-drafting A/B probe for pending-verdict models flagged
'mtp-speculative' by scripts/pending_verdicts_report.py's capability
categorizer.

Why this exists: raw TPS on the MTP-tagged model alone is meaningless in
isolation for this category (per the category's own dont_measure note) —
the entire point of self-speculative MTP decoding is a wall-time speedup
over the same dense base model on identical prompts. Ollama/llama.cpp
doesn't expose a draft-token-acceptance-rate stat via its API, so this
probe reports wall-time speedup (matching the methodology and reporting
shape of the prior MTP_BENCH_20260528.md A/B result, which also only had
avg-TPS-based speedup available), not draft acceptance rate.

MTP_BASE_PAIRS maps an MTP-tagged pending model to its same-architecture
dense baseline tag already present in the fleet, where one is
identifiable. A model with no known baseline pair still gets its own TPS
measured (useful as a floor check) but is reported with speedup=None and
an explicit "no baseline pair identified" note rather than a fabricated
comparison.

Emits tests/benchmarks/results/mtp_probe_<UTC>.json in the same JSON
shape bench_tps.py uses, so scripts/pending_verdicts_evidence.py picks it
up automatically. quality_score here is 1.0 if the MTP model produced a
coherent, non-empty, non-error response (a floor sanity check, not a
rigorous quality-parity judge — that would need a much larger investment
than a probe script; the report's own analysis marks quality parity as
still-open even when this probe finds a real speedup).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OLLAMA_URL = "http://localhost:11434"
RESULTS_DIR = REPO_ROOT / "tests" / "benchmarks" / "results"
TIMEOUT = 180
FIXED_PROMPT = "Write a Python function that finds the longest increasing subsequence in a list of integers, with a brief docstring."

# Same-architecture dense baselines already present in the fleet, for the
# models where a baseline is actually identifiable from the tag/arch.
MTP_BASE_PAIRS: dict[str, str] = {
    "portal5/qwen3.6-27b-mtp:q8_0-drafted": "qwen3.6:27b-q8_0",
    "qwen3.6:27b-mtp-q4_K_M": "qwen3.6:27b-q8_0",
    "hf.co/Jackrong/Qwopus3.6-27B-v2-MTP-GGUF:Qwopus3.6-27B-v2-MTP-Q5_K_M.gguf": "qwen3.6:27b-q8_0",
    "hf.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF:Q4_K_M": "portal5/gemma4-12b:q4_K_M-ctx8k",
}


def unload(model: str) -> None:
    try:
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=json.dumps({"model": model, "keep_alive": 0}).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=15).read()
    except Exception:
        pass


def measure_tps(model: str) -> dict:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": FIXED_PROMPT}],
        "stream": False,
        "think": False,
        "options": {"num_predict": 256, "temperature": 0},
    }
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.load(r)
    except Exception as e:
        return {"ok": False, "error": str(e), "wall_s": time.monotonic() - t0}
    content = (data.get("message") or {}).get("content", "") or ""
    eval_count = data.get("eval_count") or 0
    eval_duration_ns = data.get("eval_duration") or 0
    tps = (eval_count / (eval_duration_ns / 1e9)) if eval_duration_ns else None
    return {
        "ok": True,
        "tps": tps,
        "eval_count": eval_count,
        "coherent": len(content.strip()) > 20 and "def " in content,
        "response_preview": content[:150],
        "wall_s": time.monotonic() - t0,
    }


def probe_model(model: str) -> dict:
    mtp_result = measure_tps(model)
    unload(model)

    base_tag = MTP_BASE_PAIRS.get(model)
    base_result = None
    speedup = None
    if base_tag:
        base_result = measure_tps(base_tag)
        unload(base_tag)
        if mtp_result.get("tps") and base_result.get("tps"):
            speedup = round(mtp_result["tps"] / base_result["tps"], 2)

    coherent = bool(mtp_result.get("coherent"))
    return {
        "model": model,
        "avg_tps": mtp_result.get("tps"),
        "quality_score": 1.0 if coherent else 0.0,
        "runs_success": 1 if coherent else 0,
        "runs_total": 1,
        "prompt_category": "mtp_speculative",
        "base_tag": base_tag,
        "base_avg_tps": base_result.get("tps") if base_result else None,
        "speedup_vs_base": speedup,
        "note": None if base_tag else "no baseline pair identified in fleet — TPS floor check only",
        "mtp_result": mtp_result,
        "base_result": base_result,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="MTP/speculative-drafting A/B probe.")
    ap.add_argument(
        "--model", action="append", required=True, help="Model tag to probe (repeatable)"
    )
    args = ap.parse_args(argv)

    print(f"Probing {len(args.model)} model(s), fixed prompt, temperature=0")

    results = []
    for i, model in enumerate(args.model, 1):
        print(f"  [{i}/{len(args.model)}] {model[:80]} ...", flush=True)
        r = probe_model(model)
        results.append(r)
        if r["speedup_vs_base"] is not None:
            print(
                f"    tps={r['avg_tps']} base_tps={r['base_avg_tps']} speedup={r['speedup_vs_base']}x"
            )
        else:
            print(f"    tps={r['avg_tps']} ({r['note']})")

    stamp = _dt.datetime.now(_dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"mtp_probe_{stamp}.json"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"results": results}, indent=2))
    print(f"\nWrote {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
