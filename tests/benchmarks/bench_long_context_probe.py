#!/usr/bin/env python3
"""Long-context needle-in-haystack probe for pending-verdict models flagged
'long-context' by scripts/pending_verdicts_report.py's capability
categorizer.

Why this exists: a model's advertised context-length claim says nothing
about whether it can actually *use* that much context — attention quality
degrades well before the architectural ceiling on many models, and raw
TPS (bench_tps.py) never exercises this at all. Do NOT measure short-
context TPS alone for this category — it misses the whole capability
being tested.

Method: insert a unique, keyword-matchable "needle" sentence at a fixed
depth (~60% through) inside deterministic filler prose, at two haystack
sizes (~2K and ~8K tokens — 8K matches the fleet's baked -ctx8k
convention for this category; num_ctx is set explicitly on the request
so the test window isn't silently truncated by Ollama's low default).
Ask the model to recall the needle's content. Scored by keyword match in
the response — same judge pattern as bench_vision_probe.py.

Emits tests/benchmarks/results/long_context_probe_<UTC>.json in the same
JSON shape bench_tps.py uses, so scripts/pending_verdicts_evidence.py
picks it up automatically as fresh post-boundary evidence.
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

# TASK_MODEL_BENCH_VALIDITY_V1 follow-up: bench at the temperature the model
# is actually configured to run at (portal.yaml), not its Modelfile default —
# the same "wrong instrument" failure as the token-budget bug, on the
# sampling axis. Fall back to a low default (needle recall wants
# determinism) only when the tag isn't wired to a bench-* workspace yet.
_DEFAULT_TEMPERATURE = 0.1


def _temperature_for_tag(model_tag: str) -> float:
    try:
        import yaml as _yaml

        data = _yaml.safe_load((REPO_ROOT / "config" / "portal.yaml").read_text()) or {}
        for slug, spec in (data.get("workspaces") or {}).items():
            if not slug.startswith("bench-") or not isinstance(spec, dict):
                continue
            if spec.get("model_hint") == model_tag and spec.get("temperature") is not None:
                return float(spec["temperature"])
    except Exception:
        pass
    return _DEFAULT_TEMPERATURE


NEEDLE_CODE = "QZ-7734-PORTAL"
NEEDLE_SENTENCE = (
    f"The secret verification code for this document is {NEEDLE_CODE}. "
    "Remember this code, it will be asked about later."
)

_FILLER_SENTENCE = (
    "The history of distributed systems is a long chain of incremental "
    "improvements in consistency models, failure detection, and "
    "consensus protocols, each building on lessons learned from earlier "
    "production outages. "
)


def build_haystack(target_tokens: int, needle_depth_frac: float = 0.6) -> str:
    # ~4 chars/token is a reasonable rough estimate for English prose;
    # good enough for a probe (not a tokenizer-exact target).
    target_chars = target_tokens * 4
    filler_block = _FILLER_SENTENCE * (target_chars // len(_FILLER_SENTENCE) + 1)
    insert_at = int(len(filler_block) * needle_depth_frac)
    return (
        filler_block[:insert_at]
        + " "
        + NEEDLE_SENTENCE
        + " "
        + filler_block[insert_at:target_chars]
    )


def build_test_cases() -> list[dict]:
    return [
        {"id": "needle_2k", "target_tokens": 2000, "num_ctx": 4096},
        {"id": "needle_8k", "target_tokens": 8000, "num_ctx": 8192},
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


def run_case(model: str, case: dict) -> dict:
    haystack = build_haystack(case["target_tokens"])
    prompt = (
        f"{haystack}\n\nWhat is the secret verification code mentioned in the "
        "document above? Reply with just the code."
    )
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "options": {
            "num_predict": 64,
            "num_ctx": case["num_ctx"],
            "temperature": _temperature_for_tag(model),
        },
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
        return {"id": case["id"], "ok": False, "error": str(e), "wall_s": time.monotonic() - t0}
    content = (data.get("message") or {}).get("content", "") or ""
    matched = NEEDLE_CODE.lower() in content.lower()
    eval_count = data.get("eval_count") or 0
    eval_duration_ns = data.get("eval_duration") or 0
    tps = (eval_count / (eval_duration_ns / 1e9)) if eval_duration_ns else None
    return {
        "id": case["id"],
        "ok": True,
        "matched": matched,
        "response_preview": content[:150],
        "target_tokens": case["target_tokens"],
        "tps": tps,
        "wall_s": time.monotonic() - t0,
    }


def probe_model(model: str, cases: list[dict]) -> dict:
    case_results = [run_case(model, c) for c in cases]
    unload(model)

    matched = sum(1 for c in case_results if c.get("matched"))
    total = len(case_results)
    tps_vals = [c["tps"] for c in case_results if c.get("tps")]
    avg_tps = round(sum(tps_vals) / len(tps_vals), 2) if tps_vals else None

    return {
        "model": model,
        "avg_tps": avg_tps,
        "quality_score": round(matched / total, 2) if total else None,
        "runs_success": matched,
        "runs_total": total,
        "prompt_category": "long_context",
        "cases": case_results,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Long-context needle-in-haystack probe.")
    ap.add_argument(
        "--model", action="append", required=True, help="Model tag to probe (repeatable)"
    )
    args = ap.parse_args(argv)

    cases = build_test_cases()
    print(f"Probing {len(args.model)} model(s) at needle depths: {[c['id'] for c in cases]}")

    results = []
    for i, model in enumerate(args.model, 1):
        print(f"  [{i}/{len(args.model)}] {model[:80]} ...", flush=True)
        r = probe_model(model, cases)
        results.append(r)
        print(
            f"    quality={r['quality_score']} ({r['runs_success']}/{r['runs_total']}) avg_tps={r['avg_tps']}"
        )

    stamp = _dt.datetime.now(_dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"long_context_probe_{stamp}.json"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"results": results}, indent=2))
    print(f"\nWrote {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
