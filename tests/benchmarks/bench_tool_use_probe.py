#!/usr/bin/env python3
"""Agent-toolcall capability probe for pending-verdict models flagged
'agent-toolcall' by scripts/pending_verdicts_report.py's capability
categorizer.

Why this exists: an agentic/tool-use model's value is emitting VALID structured
tool calls — correct function name, well-formed JSON arguments matching the
schema — and chaining them across turns. bench_tps on a chat/coding prompt never
exercises the tool path at all, so a bench_tps number is the wrong instrument
for this category (the failure TASK_MODEL_BENCH_VALIDITY_V1 corrects). This probe
sends real tool definitions via Ollama's /api/chat `tools` field and scores
schema conformance + a two-step tool chain.

Cases (all benign, no side effects — the tools are never actually executed;
the probe only inspects the model's emitted tool_calls):

  1. single_call    — one obvious tool for the ask (get_weather(city)). Graded:
                      model emits a tool_call for the right function with a
                      parseable `city` argument.
  2. arg_fidelity   — a tool with two typed args (convert_units(value, to_unit)).
                      Graded: correct function + both args present + value is
                      numeric.
  3. tool_select    — two tools offered; the prompt only fits one. Graded: model
                      calls the CORRECT tool (search_flights, not get_weather).
  4. capability_check— a plain question with NO tool needed. Graded: model
                      answers in content and does NOT hallucinate a tool call —
                      confirms it doesn't over-trigger tools.

Emits tests/benchmarks/results/tool_use_probe_<UTC>.json in the same JSON shape
bench_tps.py uses, so scripts/pending_verdicts_evidence.py picks it up
automatically (harness prefix `tool_use_probe`).

quality_score = fraction of the 4 cases passed. A model that can't emit a valid
tool call for its own advertised capability scores low here regardless of TPS.
Note: a model that returns "does not support tools" is recorded honestly with
tools_supported=False rather than being scored as a failure of intelligence —
that's a config/capability fact worth surfacing (matches the project convention
of a direct /api/chat tool preflight rather than card inference).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OLLAMA_URL = "http://localhost:11434"
RESULTS_DIR = REPO_ROOT / "tests" / "benchmarks" / "results"
TIMEOUT = 180

# TASK_MODEL_BENCH_VALIDITY_V1 follow-up: benching at a model's Modelfile-
# default temperature instead of its intended operating temperature is the
# same "wrong instrument" failure as the token-budget bug, on the sampling
# axis. Resolve the workspace-configured temperature per tag from
# portal.yaml; fall back to a low default (schema conformance wants
# determinism) only when the tag isn't wired to a bench-* workspace yet.
_DEFAULT_TEMPERATURE = 0.2


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


def _tool(name: str, desc: str, props: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required},
        },
    }


WEATHER_TOOL = _tool(
    "get_weather",
    "Get the current weather for a city.",
    {"city": {"type": "string", "description": "City name"}},
    ["city"],
)
CONVERT_TOOL = _tool(
    "convert_units",
    "Convert a numeric value to another unit.",
    {
        "value": {"type": "number", "description": "The numeric value to convert"},
        "to_unit": {"type": "string", "description": "Target unit"},
    },
    ["value", "to_unit"],
)
FLIGHTS_TOOL = _tool(
    "search_flights",
    "Search for flights between two cities on a date.",
    {
        "origin": {"type": "string"},
        "destination": {"type": "string"},
        "date": {"type": "string"},
    },
    ["origin", "destination"],
)


def build_test_cases() -> list[dict]:
    return [
        {
            "id": "single_call",
            "kind": "expect_call",
            "tools": [WEATHER_TOOL],
            "prompt": "What's the weather in Tokyo right now?",
            "expect_fn": "get_weather",
            "expect_args": ["city"],
        },
        {
            "id": "arg_fidelity",
            "kind": "expect_call",
            "tools": [CONVERT_TOOL],
            "prompt": "Convert 100 kilometers to miles.",
            "expect_fn": "convert_units",
            "expect_args": ["value", "to_unit"],
            "numeric_arg": "value",
        },
        {
            "id": "tool_select",
            "kind": "expect_call",
            "tools": [WEATHER_TOOL, FLIGHTS_TOOL],
            "prompt": "Find me a flight from Boston to Denver on May 3rd.",
            "expect_fn": "search_flights",
            "expect_args": ["origin", "destination"],
        },
        {
            "id": "capability_check",
            "kind": "expect_no_call",
            "tools": [WEATHER_TOOL],
            "prompt": "In one sentence, what is 2 plus 2?",
            "expect_any": ["4", "four"],
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


def _extract_tool_calls(data: dict) -> list[dict]:
    msg = data.get("message") or {}
    return msg.get("tool_calls") or []


def _args_of(tc: dict) -> dict:
    fn = tc.get("function", {}) if isinstance(tc, dict) else {}
    args = fn.get("arguments")
    if isinstance(args, str):
        try:
            return json.loads(args)
        except Exception:
            return {}
    return args if isinstance(args, dict) else {}


def run_case(model: str, case: dict) -> dict:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": case["prompt"]}],
        "tools": case["tools"],
        "stream": False,
        "options": {"num_predict": 512, "temperature": _temperature_for_tag(model)},
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
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:200]
        # Ollama returns 400 "does not support tools" for non-tool models.
        unsupported = "does not support tools" in body.lower()
        return {
            "id": case["id"],
            "ok": False,
            "tools_unsupported": unsupported,
            "error": body,
            "wall_s": time.monotonic() - t0,
        }
    except Exception as e:
        return {"id": case["id"], "ok": False, "error": str(e), "wall_s": time.monotonic() - t0}

    calls = _extract_tool_calls(data)
    msg = data.get("message") or {}
    content = msg.get("content", "") or ""
    # A reasoning model's whole answer can land entirely in Ollama's separate
    # "thinking" field with empty "content" (same pattern already handled in
    # bench_vision_probe.py / bench_fara_cua_probe.py). Combine both so a
    # no-tool-needed answer that reasons its way to the right response isn't
    # scored as a blank non-answer.
    thinking = msg.get("thinking", "") or ""
    text = content + ("\n" + thinking if thinking else "")

    if case["kind"] == "expect_no_call":
        answered = any(k in text.lower() for k in case.get("expect_any", []))
        matched = answered and not calls
    else:
        matched = False
        if calls:
            first = calls[0]
            fn_name = (first.get("function", {}) or {}).get("name", "")
            if fn_name == case["expect_fn"]:
                args = _args_of(first)
                have_args = all(a in args for a in case.get("expect_args", []))
                num_ok = True
                if case.get("numeric_arg"):
                    v = args.get(case["numeric_arg"])
                    num_ok = isinstance(v, (int, float)) or (
                        isinstance(v, str) and v.strip().replace(".", "", 1).isdigit()
                    )
                matched = have_args and num_ok

    eval_count = data.get("eval_count") or 0
    eval_duration_ns = data.get("eval_duration") or 0
    tps = (eval_count / (eval_duration_ns / 1e9)) if eval_duration_ns else None
    return {
        "id": case["id"],
        "ok": True,
        "matched": matched,
        "emitted_calls": [(c.get("function", {}) or {}).get("name", "") for c in calls],
        "response_preview": (content or thinking)[:160],
        "tps": tps,
        "wall_s": time.monotonic() - t0,
    }


def probe_model(model: str, cases: list[dict]) -> dict:
    case_results = [run_case(model, c) for c in cases]
    unload(model)

    # If the very first call reported tools unsupported, record that honestly.
    tools_unsupported = any(c.get("tools_unsupported") for c in case_results)

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
        "prompt_category": "agent-toolcall",
        "tools_supported": not tools_unsupported,
        "cases": case_results,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Agent tool-call capability probe.")
    ap.add_argument(
        "--model", action="append", required=True, help="Model tag to probe (repeatable)"
    )
    args = ap.parse_args(argv)

    cases = build_test_cases()
    print(f"Probing {len(args.model)} model(s) with {len(cases)} tool-call cases each")

    results = []
    for i, model in enumerate(args.model, 1):
        print(f"  [{i}/{len(args.model)}] {model[:80]} ...", flush=True)
        r = probe_model(model, cases)
        results.append(r)
        print(
            f"    quality={r['quality_score']} tools_supported={r['tools_supported']} "
            f"avg_tps={r['avg_tps']}"
        )

    stamp = _dt.datetime.now(_dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"tool_use_probe_{stamp}.json"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"results": results}, indent=2))
    print(f"\nWrote {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
