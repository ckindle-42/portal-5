#!/usr/bin/env python3
"""Reasoning-capability probe for pending-verdict models flagged
'reasoning-explicit' by scripts/pending_verdicts_report.py's capability
categorizer.

Why this exists: a reasoning model's value is arriving at the right answer
THROUGH a correct multi-step process — not chat TPS and not a lucky final
token. bench_tps on a coding/general prompt measures neither; the coding
verifier's exact-match rubric is the wrong instrument for a model whose whole
point is the trace. This probe measures two axes on problems where the PATH
matters (a lucky guess shouldn't score full marks):

  Axis 1 — final-answer correctness (oracle-checked, numeric/exact). The hard
           signal: did it get the right answer?
  Axis 2 — reasoning-trace presence (structural). The softer, SUPPORTING
           signal: did it actually show intermediate work, and does the trace
           contain the required intermediate quantities — or did it pattern-
           match straight to a number? Scored mechanically (trace length ratio
           + presence of expected intermediate values), NOT by LLM-grading and
           NOT by writing style. Deliberately a weaker signal than Axis 1: read
           it as corroboration, not a gate.

Baseline comparison (TASK_MODEL_REASONING_HARNESS_V1 option 1): the same
problems are run against a strong in-fleet reasoning baseline (default the
promoted `auto-reasoning` workspace's model) so each pending model is scored
RELATIVE to what the fleet already runs — answering "better/worse than what we
have?" not just an absolute number. This is a comparison signal only; no model
is promoted or declined. PROMOTE_POLICY=confirm.

Runs at each model's production budget + temperature (resolved from portal.yaml
via bench.config.budget_for_model_tag — same fidelity fix the token-budget and
temperature bugs established), so the trace is never truncated mid-thought.

Emits tests/benchmarks/results/reasoning_probe_<UTC>.json in the same JSON shape
bench_tps.py uses, so scripts/pending_verdicts_evidence.py picks it up
automatically (harness prefix `reasoning_probe`).

quality_score = final-answer correctness fraction (Axis 1) — the headline. Axis
2 (trace) and the baseline delta are reported alongside as separate fields for
operator review, not folded into the headline score.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OLLAMA_URL = "http://localhost:11434"
RESULTS_DIR = REPO_ROOT / "tests" / "benchmarks" / "results"
TIMEOUT = 600  # reasoning traces are long; generous ceiling, idle-gap is the real backstop

sys.path.insert(0, str(REPO_ROOT / "tests" / "benchmarks"))
try:
    from capability_lib import extract_final_answer, numeric_answer_matches
except Exception:  # pragma: no cover - offline/path fallback

    def extract_final_answer(text: str) -> str:
        stripped = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL)
        stripped = re.sub(r"<think>.*\Z", "", stripped, flags=re.DOTALL)
        return stripped.strip()

    def numeric_answer_matches(text: str, expected: float, tol: float = 0.0) -> bool:
        body = extract_final_answer(text)
        nums = re.findall(r"-?\d+(?:\.\d+)?", body.replace(",", ""))
        return bool(nums) and abs(float(nums[-1]) - expected) <= tol


try:
    from bench.config import budget_for_model_tag
except Exception:  # pragma: no cover

    def budget_for_model_tag(model_tag: str) -> dict:
        return {"predict_limit": None, "temperature": None, "workspace": None}


DEFAULT_BASELINE_TAG = "hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k"


def build_test_cases() -> list[dict]:
    """Problems with verifiable answers where the PATH matters. Each carries the
    intermediate quantities a correct derivation must pass through, for Axis 2."""
    return [
        {
            "id": "rate_work",
            # 3 painters paint 3 rooms in 3 hours => rate 1 room/painter/3h.
            # 9 painters, 9 rooms => still 3 hours.
            "prompt": (
                "If 3 painters can paint 3 rooms in 3 hours, how many hours do 9 "
                "painters need to paint 9 rooms? Think step by step, then give the "
                "final answer as a number."
            ),
            "answer": 3.0,
            "tol": 0.01,
            "intermediates": ["1", "3"],  # per-painter rate reasoning surfaces a 1 and a 3
        },
        {
            "id": "multi_hop_age",
            # Anna is 3x Ben. In 5 years Anna is 2x Ben. Ben now = 5, Anna now = 15.
            "prompt": (
                "Anna is three times as old as Ben. In five years, Anna will be twice "
                "as old as Ben. How old is Ben now? Think step by step, then give the "
                "final answer as a number."
            ),
            "answer": 5.0,
            "tol": 0.01,
            "intermediates": ["3", "2", "5"],
        },
        {
            "id": "units_chain",
            # 90 km/h -> m/s : 90 * 1000 / 3600 = 25.
            "prompt": (
                "A car travels at 90 kilometers per hour. What is its speed in meters "
                "per second? Think step by step, then give the final answer as a number."
            ),
            "answer": 25.0,
            "tol": 0.01,
            "intermediates": ["1000", "3600"],
        },
        {
            "id": "constraint_logic",
            # Three boxes, one has prize. Labels all wrong. Only "prize not here" combos...
            # Simpler verifiable: consecutive integers summing to 51 -> 16,17,18 -> middle 17.
            "prompt": (
                "Three consecutive integers sum to 51. What is the largest of the "
                "three? Think step by step, then give the final answer as a number."
            ),
            "answer": 18.0,
            "tol": 0.01,
            "intermediates": ["17", "51"],
        },
    ]


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


def _score_trace(full_response: str, final_answer: str, intermediates: list[str]) -> dict:
    """Axis 2 (structural, supporting). Two mechanical checks over the full
    response text (works whether or not reasoning is <think>-tagged):
      - showed_work: the response is substantially longer than a bare answer
        would be (the model wrote out steps, not just a number).
      - intermediate coverage: fraction of expected intermediate quantities that
        actually appear anywhere in the response — a bare "25" scores 0 here
        even though the final answer is right, so a lucky/pattern-matched answer
        can't earn the trace signal.
    Deliberately lenient on form, strict on substance: it doesn't care about
    style, only that the derivation's quantities are present and the model
    actually generated more than a terminal token."""
    full = (full_response or "").strip()
    full_len = len(full)
    covered = sum(1 for q in intermediates if q in full)
    coverage = round(covered / len(intermediates), 3) if intermediates else None
    # A real trace is substantially longer than a bare answer AND surfaces the
    # derivation's intermediate quantities. Length alone is gameable (a chatty
    # wrong answer); coverage alone is gameable (a lucky answer that happens to
    # restate given numbers). Require both: enough text to be a derivation, and
    # at least half the expected intermediates present in it.
    showed_work = full_len > 60
    trace_ok = bool(showed_work and (coverage is None or coverage >= 0.5))
    return {
        "response_chars": full_len,
        "showed_work": showed_work,
        "intermediate_coverage": coverage,
        "trace_ok": trace_ok,
    }


def run_case(model: str, case: dict, predict_limit: int | None, temperature: float | None) -> dict:
    options: dict = {}
    if predict_limit:
        options["num_predict"] = predict_limit
    if temperature is not None:
        options["temperature"] = temperature
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": case["prompt"]}],
        "stream": False,
    }
    if options:
        payload["options"] = options
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
        return {"id": case["id"], "ok": False, "error": str(e), "wall_s": time.monotonic() - t0}
    msg = data.get("message") or {}
    content = msg.get("content", "") or ""
    reasoning = msg.get("reasoning", "") or ""
    full = (reasoning + "\n" + content).strip() if reasoning else content

    final = extract_final_answer(full)
    correct = numeric_answer_matches(full, case["answer"], case.get("tol", 0.0))
    trace = _score_trace(full, final, case.get("intermediates", []))

    eval_count = data.get("eval_count") or 0
    eval_duration_ns = data.get("eval_duration") or 0
    tps = (eval_count / (eval_duration_ns / 1e9)) if eval_duration_ns else None
    return {
        "id": case["id"],
        "ok": True,
        "correct": correct,
        "trace": trace,
        "response_preview": full[:240],
        "tps": tps,
        "wall_s": time.monotonic() - t0,
    }


def probe_model(
    model: str, cases: list[dict], predict_limit: int | None, temperature: float | None
) -> dict:
    case_results = [run_case(model, c, predict_limit, temperature) for c in cases]
    unload(model)

    ok_cases = [c for c in case_results if c.get("ok")]
    correct = sum(1 for c in ok_cases if c.get("correct"))
    trace_ok = sum(1 for c in ok_cases if (c.get("trace") or {}).get("trace_ok"))
    total = len(cases)
    tps_vals = [c["tps"] for c in ok_cases if c.get("tps")]
    avg_tps = round(sum(tps_vals) / len(tps_vals), 2) if tps_vals else None

    return {
        "model": model,
        "avg_tps": avg_tps,
        "quality_score": round(correct / total, 2) if total else None,  # Axis 1 = headline
        "runs_success": correct,
        "runs_total": total,
        "prompt_category": "reasoning-explicit",
        "trace_quality_rate": round(trace_ok / total, 2) if total else None,  # Axis 2, supporting
        "predict_limit": predict_limit,
        "temperature": temperature,
        "cases": case_results,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Reasoning-capability probe (answer + trace + baseline)."
    )
    ap.add_argument(
        "--model", action="append", required=True, help="Model tag to probe (repeatable)"
    )
    ap.add_argument(
        "--baseline",
        default=DEFAULT_BASELINE_TAG,
        help="In-fleet reasoning baseline tag for comparison (default: auto-reasoning's model)",
    )
    ap.add_argument("--no-baseline", action="store_true", help="Skip the baseline comparison run")
    args = ap.parse_args(argv)

    cases = build_test_cases()
    print(f"Probing {len(args.model)} model(s) with {len(cases)} reasoning cases each")

    # Baseline first, once, so every pending model is compared to the same numbers.
    baseline_result = None
    if not args.no_baseline:
        b = budget_for_model_tag(args.baseline)
        print(f"  [baseline] {args.baseline[:70]} ...", flush=True)
        baseline_result = probe_model(
            args.baseline, cases, b.get("predict_limit"), b.get("temperature")
        )
        print(
            f"    baseline quality={baseline_result['quality_score']} "
            f"trace={baseline_result['trace_quality_rate']} avg_tps={baseline_result['avg_tps']}"
        )

    results = []
    for i, model in enumerate(args.model, 1):
        b = budget_for_model_tag(model)
        print(f"  [{i}/{len(args.model)}] {model[:70]} ...", flush=True)
        r = probe_model(model, cases, b.get("predict_limit"), b.get("temperature"))
        if baseline_result is not None:
            r["baseline_tag"] = args.baseline
            r["baseline_quality_score"] = baseline_result["quality_score"]
            r["baseline_trace_quality_rate"] = baseline_result["trace_quality_rate"]
            # Deltas: positive = this model beats the in-fleet baseline.
            if r["quality_score"] is not None and baseline_result["quality_score"] is not None:
                r["quality_delta_vs_baseline"] = round(
                    r["quality_score"] - baseline_result["quality_score"], 2
                )
            if (
                r["trace_quality_rate"] is not None
                and baseline_result["trace_quality_rate"] is not None
            ):
                r["trace_delta_vs_baseline"] = round(
                    r["trace_quality_rate"] - baseline_result["trace_quality_rate"], 2
                )
        results.append(r)
        delta = r.get("quality_delta_vs_baseline")
        print(
            f"    quality={r['quality_score']} trace={r['trace_quality_rate']} "
            f"avg_tps={r['avg_tps']}" + (f" (Δ vs baseline {delta:+})" if delta is not None else "")
        )

    payload = {"results": results}
    if baseline_result is not None:
        payload["baseline"] = baseline_result
    stamp = _dt.datetime.now(_dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"reasoning_probe_{stamp}.json"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"\nWrote {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
