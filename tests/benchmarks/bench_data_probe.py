#!/usr/bin/env python3
"""Data-analysis capability probe for models serving the auto-data intent
(analysis, statistics, aggregation over structured data).

Why this exists: auto-data's job is answering computable questions over real
datasets — counts, distinct values, frequency, filtering. These have exact right
answers, so a model can be oracle-scored: the ground truth is computed in Python
from the same data the model sees. A generic chat score can't tell a correct
aggregate from a confident wrong one.

Ground truth: the fleet's real benign SIEM corpus
(config/security/benign_corpus_bench_benign_cells.json) — actual Windows/Linux/
web event logs. The probe embeds a subset of events in the prompt, asks a
computable question, and checks the model's final number against the Python-
computed answer. This is real OT/ICS-relevant data-analysis, not a synthetic CSV.

Scored per question: exact-match on the computed answer (numeric or set). A
lucky-looking prose answer that states the wrong number fails.

Emits tests/benchmarks/results/data_probe_<UTC>.json (harness prefix
`data_probe`). quality_score = fraction of questions answered correctly.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import time
import urllib.request
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OLLAMA_URL = "http://localhost:11434"
RESULTS_DIR = REPO_ROOT / "tests" / "benchmarks" / "results"
CORPUS = REPO_ROOT / "config" / "security" / "benign_corpus_bench_benign_cells.json"
TIMEOUT = 240


def load_events() -> list[dict]:
    try:
        return json.loads(CORPUS.read_text())
    except Exception:
        return []


def build_test_cases() -> list[dict]:
    """Compute ground-truth answers in Python, then build prompts around the SAME
    events the oracle used. Each case embeds its event slice so the model has the
    data in-context and the question is deterministic."""
    cells = load_events()
    if not cells:
        return []
    all_events = [e for c in cells for e in c["events"]]

    def fmt(events: list[str]) -> str:
        return "\n".join(f"  {e}" for e in events)

    cases = []

    # Q1 — total event count over a fixed slice
    slice1 = all_events[:20]
    cases.append({
        "id": "count_events",
        "kind": "numeric",
        "answer": float(len(slice1)),
        "prompt": (
            "Here are log events, one per line:\n" + fmt(slice1) +
            "\n\nHow many log events are listed above? Answer with just the number."
        ),
    })

    # Q2 — distinct TargetUserName across a slice
    slice2 = all_events
    users = set(re.findall(r"TargetUserName=(\w+)", " ".join(slice2)))
    cases.append({
        "id": "distinct_users",
        "kind": "numeric",
        "answer": float(len(users)),
        "prompt": (
            "Here are Windows security events:\n" + fmt([e for e in slice2 if "TargetUserName=" in e]) +
            "\n\nHow many DISTINCT values of TargetUserName appear? Answer with just the number."
        ),
    })

    # Q3 — count of a specific EventCode
    ev4624 = [e for e in all_events if "EventCode=4624" in e]
    cases.append({
        "id": "count_eventcode_4624",
        "kind": "numeric",
        "answer": float(len(ev4624)),
        "prompt": (
            "Here are Windows security events:\n" + fmt([e for e in all_events if "EventCode=" in e]) +
            "\n\nHow many events have EventCode=4624? Answer with just the number."
        ),
    })

    # Q4 — most frequent EventCode (value question)
    codes = Counter(re.search(r"EventCode=(\d+)", e).group(1)
                    for e in all_events if "EventCode=" in e)
    top_code = codes.most_common(1)[0][0]
    cases.append({
        "id": "top_eventcode",
        "kind": "token",
        "answer": top_code,
        "prompt": (
            "Here are Windows security events:\n" + fmt([e for e in all_events if "EventCode=" in e]) +
            "\n\nWhich EventCode appears most frequently? Answer with just the numeric code."
        ),
    })

    # Q5 — distinct sourcetypes (from cell metadata, embedded explicitly)
    st = sorted({c["sourcetype"] for c in cells})
    lines = [f'  host={c["host"]} sourcetype={c["sourcetype"]}' for c in cells]
    cases.append({
        "id": "distinct_sourcetypes",
        "kind": "numeric",
        "answer": float(len(st)),
        "prompt": (
            "Here are log cells:\n" + "\n".join(lines) +
            "\n\nHow many DISTINCT sourcetypes appear? Answer with just the number."
        ),
    })
    return cases


def _score(text: str, case: dict) -> bool:
    if case["kind"] == "numeric":
        nums = re.findall(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
        return bool(nums) and abs(float(nums[-1]) - case["answer"]) < 0.01
    # token: the exact expected token appears
    return case["answer"] in text


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
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": case["prompt"]}],
        "stream": False,
        "options": {"num_predict": 512},
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
    # strip reasoning so we score the final answer
    body = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip() or content
    matched = _score(body, case)
    eval_count = data.get("eval_count") or 0
    eval_duration_ns = data.get("eval_duration") or 0
    tps = (eval_count / (eval_duration_ns / 1e9)) if eval_duration_ns else None
    return {
        "id": case["id"], "ok": True, "matched": matched,
        "expected": case["answer"], "response_preview": body[:120],
        "tps": tps, "wall_s": time.monotonic() - t0,
    }


def probe_model(model: str, cases: list[dict]) -> dict:
    case_results = [run_case(model, c) for c in cases]
    unload(model)
    ok = [c for c in case_results if c.get("ok")]
    matched = sum(1 for c in ok if c.get("matched"))
    total = len(cases)
    tps_vals = [c["tps"] for c in ok if c.get("tps")]
    avg_tps = round(sum(tps_vals) / len(tps_vals), 2) if tps_vals else None
    return {
        "model": model, "avg_tps": avg_tps,
        "quality_score": round(matched / total, 2) if total else None,
        "runs_success": matched, "runs_total": total,
        "prompt_category": "data",
        "cases": case_results,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Data-analysis capability probe (real SIEM corpus).")
    ap.add_argument("--model", action="append", required=True, help="Model tag (repeatable)")
    args = ap.parse_args(argv)
    cases = build_test_cases()
    if not cases:
        print("No data corpus found — check benign_corpus_bench_benign_cells.json path.")
        return 1
    print(f"Probing {len(args.model)} model(s) with {len(cases)} data-analysis questions each")
    results = []
    for i, model in enumerate(args.model, 1):
        print(f"  [{i}/{len(args.model)}] {model[:70]} ...", flush=True)
        r = probe_model(model, cases)
        results.append(r)
        print(f"    quality={r['quality_score']} avg_tps={r['avg_tps']}")
    stamp = _dt.datetime.now(_dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"data_probe_{stamp}.json"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"results": results}, indent=2))
    print(f"\nWrote {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
