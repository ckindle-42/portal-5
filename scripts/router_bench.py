#!/usr/bin/env python3
"""Bench auto-router classifier candidates on the production prompt, offline.

The router model is the pipeline's LLM_ROUTER_MODEL env, not a request parameter, so a WFE
campaign cannot swap it. This calls the production classifier path directly: the real prompt
(`routing._build_router_prompt`) and payload (`routing._router_payload`: temperature 0,
grammar-enforced JSON, 64-token cap, num_ctx 2048), changing only `model`. Each row is
scored against `tests/wfe/suites/routing_production.jsonl` (expected workspace = the
task's routed_workspace checker). Latency is reported against the pipeline's deadline
(LLM_ROUTER_TIMEOUT_MS, default 2000 ms): a reply after the deadline is a fallback to
keyword routing in production, so it counts as a miss here too.

    uv run python scripts/router_bench.py --model MODEL [--model MODEL ...] [--json-out PATH]
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
import urllib.request
from pathlib import Path

from portal.platform.inference.router import routing

REPO = Path(__file__).resolve().parents[1]
SUITE = REPO / "tests/wfe/suites/routing_production.jsonl"
OLLAMA = os.environ.get("OLLAMA_HOST_URL", "http://localhost:11434")
DEADLINE_MS = int(os.environ.get("LLM_ROUTER_TIMEOUT_MS", "2000"))


def _expected(task: dict) -> str:
    for checker in task.get("checkers") or []:
        if checker.get("type") == "routed_workspace":
            return str(checker["workspace"])
    return ""


def _classify(model: str, text: str) -> tuple[dict, float]:
    payload = routing._router_payload(routing._build_router_prompt(text))
    payload["model"] = model
    req = urllib.request.Request(
        f"{OLLAMA}/api/generate", json.dumps(payload).encode(), {"Content-Type": "application/json"}
    )
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.load(resp)
    ms = (time.monotonic() - t0) * 1000
    try:
        return json.loads(body.get("response") or "{}"), ms
    except ValueError:
        return {"_unparsed": body.get("response", "")[:200]}, ms


def bench(model: str, tasks: list[dict]) -> dict:
    _classify(model, "warm up")  # load + cache the prompt prefix, like warm_router_model
    rows = []
    for task in tasks:
        out, ms = _classify(model, task["instruction"])
        want = _expected(task)
        got = str(out.get("workspace") or "")
        conf = out.get("confidence")
        rows.append(
            {
                "id": task["id"],
                "kind": task.get("kind"),
                "expected": want,
                "got": got,
                "confidence": conf,
                "ms": round(ms),
                "ok": got == want,
                "in_deadline": ms <= DEADLINE_MS,
                "parsed": "_unparsed" not in out,
            }
        )
    lat = [r["ms"] for r in rows]
    return {
        "model": model,
        "n": len(rows),
        "correct": sum(r["ok"] for r in rows),
        "correct_in_deadline": sum(r["ok"] and r["in_deadline"] for r in rows),
        "parsed": sum(r["parsed"] for r in rows),
        "median_ms": statistics.median(lat),
        "p90_ms": sorted(lat)[int(len(lat) * 0.9)],
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--model", action="append", required=True)
    ap.add_argument("--json-out", type=Path)
    args = ap.parse_args()
    tasks = [json.loads(line) for line in SUITE.read_text().splitlines() if line.strip()]
    results = []
    for model in args.model:
        r = bench(model, tasks)
        results.append(r)
        print(
            f"{model}: correct {r['correct']}/{r['n']}  within {DEADLINE_MS}ms "
            f"{r['correct_in_deadline']}/{r['n']}  parsed {r['parsed']}/{r['n']}  "
            f"median {r['median_ms']:.0f}ms p90 {r['p90_ms']:.0f}ms",
            flush=True,
        )
    if args.json_out:
        args.json_out.write_text(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
