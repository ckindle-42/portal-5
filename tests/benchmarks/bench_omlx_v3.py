"""Phase-0 oMLX v3 re-evaluation probe (P5-FUT-013 successor, 2026-08-02).

Re-runs the 2026-04-25 / 2026-05-28 bake-off protocol against oMLX 0.5.x with
Ollama GGUF as the production baseline (mlx-proxy is retired). Protocol shapes
are kept identical to the deleted bench_omlx.py (recovered from git history at
10075f1c) so numbers are comparable across all three evaluation rounds.

Gates (from the Phase-0 plan):
  kv        Gate 1 — warm TTFT must beat cold TTFT; cached_tokens must be >0 on
            warm rounds. This was the 2026-04-25 cancel trigger.
  tps       Gate 2 — decode TPS vs same-session Ollama GGUF baseline
            (>= 1.3x on the production-primary model to pass).
  mtp       Gate 2b — Lightning MTP on/off speedup on an -mtp checkpoint
            (>= 1.5x on long outputs, per P5-FUT-SPEC gate).
  tools     Gate 3 — structured tool_calls probe per model family
            (P5-TOOL-001 discipline: live probe, never the model card).
  grammar   Gate 4 — response_format json_schema correctness (router contract).
  concurrent Gate 5a — 4-way parallel throughput vs serial (batching sanity).

The same harness measures both engines: oMLX (:8085) and Ollama (:11434) both
speak /v1/chat/completions. Pass --url accordingly for baseline runs.

Usage:
  python3 tests/benchmarks/bench_omlx_v3.py --gate all --url http://localhost:8085
  python3 tests/benchmarks/bench_omlx_v3.py --gate tps --url http://localhost:11434 --models qwen3-coder:30b-a3b-q4_K_M
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

OMLX_URL = "http://localhost:8085"
OLLAMA_URL = "http://localhost:11434"
RESULTS_DIR = Path(__file__).parent / "results"

# ── Model matrix ─────────────────────────────────────────────────────────────
# oMLX ids are directory names under /Volumes/data01/omlx-models.
# Ollama ids are the production GGUF tags (baselines).

OMLX_MODELS = {
    "3b": "Llama-3.2-3B-Instruct-8bit",  # continuity with 2026-04/05 evals
    "coder": "Qwen3-Coder-30B-A3B-Instruct-4bit",  # auto-coding production primary
    "gemma": "gemma-4-e4b-it-4bit",  # LLM-router family
    "mtp": "Qwen3.6-27B-oQ8-mtp",  # MTP checkpoint (real dir, on disk)
}

OLLAMA_BASELINES = {
    # -ctxNk tags carry a real Modelfile-baked PARAMETER num_ctx — Ollama's
    # /v1/chat/completions endpoint silently ignores a runtime options.num_ctx
    # override (verified live), so the bare untagged ids run at full model
    # context (131k-262k) regardless of any request-level cap.
    "coder": "qwen3-coder:30b-a3b-q4_K_M-ctx16k",  # matches auto-coding's real hint
    "gemma": "gemma4:e4b-it-qat-ctx8k",
    "3b": "llama3.2:3b-ctx8k",
}

# ── Protocol constants (identical to bench_omlx.py @ 10075f1c) ───────────────

SINGLE_PROMPTS = {
    "coding": (
        "Write a Python function called merge_intervals that takes a list of "
        "tuples (each tuple is a pair of integers representing a start and end value) "
        "and returns a new list with overlapping intervals merged. "
        "Include type hints, a docstring, and handle edge cases."
    ),
    "reasoning": (
        "A hospital emergency room has 30 patients arriving per hour. "
        "The ER has 8 beds, 3 doctors, and 12 nurses. Average treatment "
        "time is 45 minutes. Identify the primary bottleneck and show the math."
    ),
    "general": (
        "List the 7 OSI model layers from bottom to top. For each layer, provide: "
        "the layer number, the standard name, and one example protocol."
    ),
}

KV_SYSTEM = (
    "You are a helpful, precise coding assistant. You write clean, well-documented Python. "
    "You explain your reasoning step by step. You cite time and space complexity. "
    "You handle edge cases explicitly. You never skip error handling."
)


def _agentic_system_prompt() -> str:
    """~1.8K-token agentic system prompt: persona + tool schemas + conventions.

    oMLX's paged prefix cache works on 256-token blocks, so a sub-block prefix
    (like the legacy KV_SYSTEM, ~120 tokens) can never produce a cache hit.
    Gate 1's decision signal must use a realistically-sized agentic prefix.
    Deterministic content — only prefill cost matters here.
    """
    header = (
        "You are auto-coding, Portal 5's agentic coding workspace. You generate, review, "
        "and repair code in a single pass. You have access to the following tools and must "
        "use them exactly as specified. Never invent tool names. Never skip verification.\n\n"
    )
    tool_block = (
        "TOOL: execute_python\n"
        "DESCRIPTION: Run Python 3 code in an isolated sandbox (no network, 256MB RAM, "
        "30s timeout, read-only filesystem). Use for verification, data processing, and "
        "quick proofs. Input: {'code': str, 'timeout': int?}. Output: stdout, stderr, "
        "exit_code, timed_out.\n"
        "TOOL: execute_bash\n"
        "DESCRIPTION: Run a bash script in the same sandbox. Use for file pipelines and "
        "shell-native tasks. Input: {'code': str, 'timeout': int?}.\n"
        "TOOL: read_file / write_file / edit_file\n"
        "DESCRIPTION: Workspace file operations. Paths are workspace-relative. Never "
        "write outside /workspace. Always read before editing.\n"
        "CONVENTIONS: Prefer small diffs. Cite file paths. Run tests after every edit. "
        "If a command fails, read the error before retrying. Keep responses under 400 "
        "words unless the task requires code. Never fabricate command output.\n\n"
    )
    return header + tool_block * 14  # ~1.8K tokens


KV_LONG_CONVERSATION = [
    {"role": "system", "content": _agentic_system_prompt()},
    {"role": "user", "content": "What is the difference between a list and a tuple in Python?"},
    {
        "role": "assistant",
        "content": (
            "Lists are mutable sequences; tuples are immutable. "
            "Use tuples for fixed data (coordinates, records), lists for dynamic collections."
        ),
    },
    {"role": "user", "content": "When would you use a named tuple?"},
    {
        "role": "assistant",
        "content": (
            "Use namedtuple (or dataclass) when you want attribute access on tuple fields "
            "without writing a full class. Good for lightweight record types."
        ),
    },
    {
        "role": "user",
        "content": "Write a Python function that takes a list of 2-tuples and returns a dict.",
    },
]
KV_CONVERSATION = [
    {"role": "system", "content": KV_SYSTEM},
    {"role": "user", "content": "What is the difference between a list and a tuple in Python?"},
    {
        "role": "assistant",
        "content": (
            "Lists are mutable sequences; tuples are immutable. "
            "Use tuples for fixed data (coordinates, records), lists for dynamic collections."
        ),
    },
    {"role": "user", "content": "When would you use a named tuple?"},
    {
        "role": "assistant",
        "content": (
            "Use namedtuple (or dataclass) when you want attribute access on tuple fields "
            "without writing a full class. Good for lightweight record types."
        ),
    },
    {
        "role": "user",
        "content": "Write a Python function that takes a list of 2-tuples and returns a dict.",
    },
]

MAX_TOKENS = 200
REQUEST_TIMEOUT = 600.0
KV_ROUNDS = 3
TPS_RUNS = 3
CONCURRENT_N = 4

MTP_SIZES = [
    {"label": "short", "max_tokens": 128},
    {"label": "medium", "max_tokens": 512},
    {"label": "long", "max_tokens": 2048},
]
MTP_PROMPT = (
    "Write a Python function that computes the Fibonacci sequence up to N=100 "
    "using both recursion and memoization. Then explain each line of both "
    "implementations in detail. Cover every variable, every operation, time "
    "complexity, and space complexity. Do not abbreviate the explanation; "
    "fill the response budget."
)
MTP_GATE_SPEEDUP = 1.5

# Gate-3 tool probe: same shape as the fleet --audit-tools probe.
TOOLS_PROBE = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current time in a given city",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "City name"}},
                "required": ["city"],
            },
        },
    }
]
TOOLS_PROMPT = "What time is it in Paris right now? Use the tool."

# Gate-4 grammar probe: minimal router-shaped schema (workspace classification).
GRAMMAR_SCHEMA = {
    "type": "object",
    "properties": {
        "workspace": {
            "type": "string",
            "enum": ["auto-coding", "auto-research", "auto-daily"],
        },
        "confidence": {"type": "number"},
    },
    "required": ["workspace", "confidence"],
    "additionalProperties": False,
}
GRAMMAR_PROMPT = (
    "Classify this user request into the best workspace: "
    "'write a bash script that renames every photo in ~/Pictures by date taken'. "
    "Return JSON only."
)


# ── Core request helper (streaming, TTFT + usage capture) ────────────────────


def one_request(
    url: str, model: str, messages: list, max_tokens: int = MAX_TOKENS, extra: dict | None = None
) -> dict:
    """Single streaming chat request. Returns timing, token, and cache data."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_tokens": max_tokens,
    }
    if extra:
        payload.update(extra)

    t0 = time.perf_counter()
    t_first: float | None = None
    completion_tokens = 0
    cached_tokens: int | None = None
    prompt_tokens: int | None = None
    response_text = ""
    tool_calls: list = []
    finish_reason: str | None = None

    # Pipeline runs (:9099) require Bearer auth; oMLX/Ollama ignore the extra header.
    headers = {}
    _api_key = os.environ.get("PIPELINE_API_KEY", "")
    if _api_key and "9099" in url:
        headers["Authorization"] = f"Bearer {_api_key}"

    try:
        with (
            httpx.Client(timeout=REQUEST_TIMEOUT) as client,
            client.stream(
                "POST", f"{url}/v1/chat/completions", json=payload, headers=headers
            ) as resp,
        ):
            if resp.status_code != 200:
                body = resp.read()[:300].decode(errors="replace")
                return {
                    "error": f"HTTP {resp.status_code}: {body[:200]}",
                    "elapsed_s": round(time.perf_counter() - t0, 3),
                }
            for raw_line in resp.iter_lines():
                line = (
                    raw_line.strip()
                    if isinstance(raw_line, str)
                    else raw_line.decode(errors="replace").strip()
                )
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    obj = json.loads(data_str)
                except Exception:
                    continue
                choices = obj.get("choices") or []
                delta = choices[0].get("delta", {}) if choices else {}
                chunk = delta.get("content") or ""
                if chunk and t_first is None:
                    t_first = time.perf_counter()
                response_text += chunk
                if delta.get("tool_calls"):
                    tool_calls.extend(delta["tool_calls"])
                if choices and choices[0].get("finish_reason"):
                    finish_reason = choices[0]["finish_reason"]
                usage = obj.get("usage") or {}
                if usage.get("completion_tokens"):
                    completion_tokens = usage["completion_tokens"]
                if usage.get("prompt_tokens") is not None:
                    prompt_tokens = usage["prompt_tokens"]
                details = usage.get("prompt_tokens_details") or {}
                if details.get("cached_tokens") is not None:
                    cached_tokens = details["cached_tokens"]
    except httpx.ReadTimeout:
        return {"error": "timeout", "elapsed_s": REQUEST_TIMEOUT}
    except Exception as e:
        return {"error": str(e)[:150], "elapsed_s": round(time.perf_counter() - t0, 3)}

    elapsed = time.perf_counter() - t0
    if completion_tokens == 0 and response_text:
        completion_tokens = max(1, len(response_text.split()))
    ttft = round(t_first - t0, 3) if t_first is not None else None
    decode_s = (elapsed - ttft) if ttft is not None else None
    return {
        "elapsed_s": round(elapsed, 3),
        "ttft_s": ttft,
        "completion_tokens": completion_tokens,
        "prompt_tokens": prompt_tokens,
        "cached_tokens": cached_tokens,
        "tps": round(completion_tokens / elapsed, 1) if elapsed > 0 else 0.0,
        "decode_tps": round(completion_tokens / decode_s, 1) if decode_s and decode_s > 0 else None,
        "tool_calls": tool_calls or None,
        "finish_reason": finish_reason,
        "response_preview": response_text[:200],
        "response_chars": len(response_text),
    }


def warmup(url: str, model: str) -> bool:
    r = one_request(url, model, [{"role": "user", "content": "hi"}], max_tokens=1)
    if "error" in r:
        print(f"      warmup FAILED for {model}: {r['error']}")
        return False
    return True


# ── Gate 1: KV cache warm vs cold (the 2026-04-25 cancel trigger) ────────────


def gate_kv(url: str, model: str, rounds: int = KV_ROUNDS) -> dict:
    """Run both the legacy short-prefix continuity test and the long-prefix
    agentic decision test. The verdict is computed on the long prefix only —
    oMLX 0.5.x caches in 256-token blocks, so the legacy ~120-token prefix
    cannot produce a hit and is kept purely for cross-eval continuity."""
    print(f"    [kv] {model}: short (continuity) + agentic-long (decision)", flush=True)
    if not warmup(url, model):
        return {"test": "kv_cache_ttft", "model": model, "error": "warmup failed"}

    out: dict = {"test": "kv_cache_ttft", "model": model}
    for label, convo in (("short", KV_CONVERSATION), ("agentic_long", KV_LONG_CONVERSATION)):
        results = []
        for i in range(1, rounds + 1):
            r = one_request(url, model, convo, max_tokens=MAX_TOKENS)
            r["round"] = i
            r["round_label"] = "cold" if i == 1 else f"warm-{i - 1}"
            results.append(r)
            print(
                f"      [{label}] round {i} ({r['round_label']}): TTFT={r.get('ttft_s')}s "
                f"prompt_tokens={r.get('prompt_tokens')} cached={r.get('cached_tokens')} "
                f"decode_tps={r.get('decode_tps')}" + (f" [{r['error']}]" if "error" in r else ""),
                flush=True,
            )
            if i < rounds:
                time.sleep(3)

        cold = next((r for r in results if r["round"] == 1 and r.get("ttft_s") is not None), None)
        warm = [r for r in results if r["round"] > 1 and r.get("ttft_s") is not None]
        cold_ttft = cold["ttft_s"] if cold else None
        warm_avg = round(sum(r["ttft_s"] for r in warm) / len(warm), 3) if warm else None
        speedup = (
            round(cold_ttft / warm_avg, 2) if cold_ttft and warm_avg and warm_avg > 0 else None
        )
        warm_hits = [r.get("cached_tokens") for r in warm]
        cell = {
            "cold_ttft_s": cold_ttft,
            "warm_ttft_avg_s": warm_avg,
            "ttft_speedup_x": speedup,
            "warm_cached_tokens": warm_hits,
            "rounds": results,
        }
        if label == "agentic_long":
            cell["verdict"] = (
                "PASS"
                if speedup and speedup > 1.0 and any(c and c > 0 for c in warm_hits)
                else "FAIL"
            )
            out["verdict"] = cell["verdict"]
        out[label] = cell
    return out


# ── Gate 2: steady-state TPS (same prompts as bench_tps.py) ──────────────────


def gate_tps(url: str, model: str, runs: int = TPS_RUNS) -> dict:
    print(f"    [tps] {model}: {runs} runs x {len(SINGLE_PROMPTS)} prompts", flush=True)
    if not warmup(url, model):
        return {"test": "tps", "model": model, "error": "warmup failed"}
    all_runs = []
    for cat, prompt in SINGLE_PROMPTS.items():
        for run_n in range(1, runs + 1):
            r = one_request(url, model, [{"role": "user", "content": prompt}])
            r["prompt_category"] = cat
            r["run"] = run_n
            all_runs.append(r)
            print(
                f"      {cat} run {run_n}: {r.get('tps')} t/s "
                f"(decode {r.get('decode_tps')} t/s)"
                + (f" [{r['error']}]" if "error" in r else ""),
                flush=True,
            )
            time.sleep(1)

    ok = [r for r in all_runs if "error" not in r]
    avg = round(sum(r["tps"] for r in ok) / len(ok), 1) if ok else 0.0
    decodes = [r["decode_tps"] for r in ok if r.get("decode_tps")]
    avg_decode = round(sum(decodes) / len(decodes), 1) if decodes else None
    return {
        "test": "tps",
        "model": model,
        "avg_tps": avg,
        "avg_decode_tps": avg_decode,
        "runs_success": len(ok),
        "runs_total": len(all_runs),
        "runs": all_runs,
    }


# ── Gate 2b: MTP on/off speedup ──────────────────────────────────────────────

MTP_SETTINGS = Path.home() / ".omlx" / "model_settings.json"


def _set_mtp(model: str, enabled: bool) -> None:
    state = {}
    if MTP_SETTINGS.exists():
        try:
            state = json.loads(MTP_SETTINGS.read_text())
        except Exception:
            state = {}
    state.setdefault("models", {})[model] = {"mtp_enabled": enabled}
    MTP_SETTINGS.write_text(json.dumps(state, indent=2))
    print(f"    [mtp] mtp_enabled={enabled} written for {model}")


def _restart_omlx() -> bool:
    """Restart by port, not argv pattern — the server process is `omlx-server`,
    so `pkill -f "omlx serve"` silently matches nothing (v3 MTP-gate bug)."""
    import contextlib
    import os
    import signal
    import subprocess

    out = subprocess.run(
        ["lsof", "-tnP", "-iTCP:8085", "-sTCP:LISTEN"], capture_output=True, text=True
    ).stdout.split()
    for pid in out:
        with contextlib.suppress(ValueError, ProcessLookupError):
            os.kill(int(pid), signal.SIGTERM)
    time.sleep(6)
    subprocess.Popen(
        ["omlx", "serve", "--model-dir", "/Volumes/data01/omlx-models", "--port", "8085"],
        stdout=open("/tmp/omlx-phase0-server.log", "a"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    for _ in range(30):
        time.sleep(2)
        try:
            r = httpx.get(f"{OMLX_URL}/v1/models", timeout=3)
            if r.status_code == 200:
                return True
        except Exception:
            pass
    return False


def _mtp_state_lines(model: str) -> list[str]:
    log = Path.home() / ".omlx" / "logs" / "server.log"
    try:
        return [
            line
            for line in log.read_text(errors="replace").splitlines()
            if "Speculative backend selected" in line and model in line
        ]
    except Exception:
        return []


def gate_mtp(url: str, model: str) -> dict:
    print(f"    [mtp] {model}: on/off speedup at 3 output sizes", flush=True)
    cells = []
    for enabled in (False, True):
        _set_mtp(model, enabled)
        if not _restart_omlx():
            return {"test": "mtp", "model": model, "error": "server restart failed"}
        # Engine loads lazily on first request — count state lines before the
        # warmup, then verify the NEW line written by this process's engine load.
        prior = len(_mtp_state_lines(model))
        warmup(url, model)
        new_lines = _mtp_state_lines(model)[prior:]
        mtp_active = any(line.rstrip().endswith("active)") for line in new_lines)
        # The 'Speculative backend selected ... (active)' line is only emitted
        # when MTP engages; disabled state is signalled by its ABSENCE.
        ok = mtp_active if enabled else not mtp_active
        print(f"    [mtp] speculative backend active={mtp_active} (expected {enabled})")
        if not ok:
            return {
                "test": "mtp",
                "model": model,
                "error": f"mtp toggle not honored: active={mtp_active}, expected {enabled}",
            }
        for size in MTP_SIZES:
            r = one_request(
                url, model, [{"role": "user", "content": MTP_PROMPT}], max_tokens=size["max_tokens"]
            )
            r["mtp_enabled"] = enabled
            r["size"] = size["label"]
            cells.append(r)
            print(
                f"      mtp={'on' if enabled else 'off'} {size['label']}: {r.get('tps')} t/s"
                + (f" [{r['error']}]" if "error" in r else ""),
                flush=True,
            )

    verdicts = {}
    for size in MTP_SIZES:
        off = next(
            (
                c
                for c in cells
                if c["size"] == size["label"] and not c["mtp_enabled"] and "error" not in c
            ),
            None,
        )
        on = next(
            (
                c
                for c in cells
                if c["size"] == size["label"] and c["mtp_enabled"] and "error" not in c
            ),
            None,
        )
        # Elapsed-based tps only: MTP emits tokens in burst cycles, so TTFT-based
        # decode rates are meaningless here. Matches omlx server-log tok/s.
        if off and on and off.get("tps") and on.get("tps"):
            sp = round(on["tps"] / off["tps"], 2)
            verdicts[size["label"]] = {"speedup": sp, "pass": sp >= MTP_GATE_SPEEDUP}
        else:
            verdicts[size["label"]] = {"speedup": None, "pass": False}
    return {"test": "mtp", "model": model, "verdicts": verdicts, "cells": cells}


# ── Gate 3: structured tool_calls probe ──────────────────────────────────────


def gate_tools(url: str, model: str) -> dict:
    print(f"    [tools] {model}", flush=True)
    if not warmup(url, model):
        return {"test": "tools", "model": model, "error": "warmup failed"}
    r = one_request(
        url,
        model,
        [{"role": "user", "content": TOOLS_PROMPT}],
        max_tokens=150,
        extra={"tools": TOOLS_PROBE},
    )
    if "error" in r:
        outcome, detail = "error", r["error"]
    elif r.get("tool_calls"):
        names = [tc.get("function", {}).get("name") for tc in r["tool_calls"]]
        outcome, detail = "tool_call", f"structured tool_calls: {names}"
    elif '"name"' in (r.get("response_preview") or "") or "<tool_call>" in (
        r.get("response_preview") or ""
    ):
        outcome, detail = "text_only", f"tool JSON in content: {r['response_preview'][:100]}"
    else:
        outcome, detail = "no_tool", f"plain prose: {(r.get('response_preview') or '')[:100]}"
    print(f"      outcome={outcome} ({detail[:90]})", flush=True)
    return {
        "test": "tools",
        "model": model,
        "outcome": outcome,
        "detail": detail,
        "verdict": "PASS" if outcome == "tool_call" else "FAIL",
        "raw": r,
    }


# ── Gate 4: JSON-schema (grammar) probe ──────────────────────────────────────


def gate_grammar(url: str, model: str) -> dict:
    print(f"    [grammar] {model}", flush=True)
    if not warmup(url, model):
        return {"test": "grammar", "model": model, "error": "warmup failed"}
    r = one_request(
        url,
        model,
        [{"role": "user", "content": GRAMMAR_PROMPT}],
        max_tokens=256,
        extra={
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "route", "schema": GRAMMAR_SCHEMA, "strict": True},
            }
        },
    )
    if "error" in r:
        return {"test": "grammar", "model": model, "verdict": "FAIL", "error": r["error"]}
    text = (r.get("response_preview") or "").strip()
    try:
        obj = json.loads(text)
        valid = obj.get("workspace") in GRAMMAR_SCHEMA["properties"]["workspace"][
            "enum"
        ] and isinstance(obj.get("confidence"), (int, float))
        verdict = "PASS" if valid else "FAIL"
        detail = f"parsed JSON: {obj}"
    except Exception:
        verdict, detail = "FAIL", f"unparseable: {text[:120]}"
    print(f"      verdict={verdict} ({detail[:90]})", flush=True)
    return {"test": "grammar", "model": model, "verdict": verdict, "detail": detail, "raw": r}


# ── Gate 5a: concurrent throughput ───────────────────────────────────────────


def gate_concurrent(url: str, model: str, n: int = CONCURRENT_N) -> dict:
    print(f"    [concurrent] {model}: {n} parallel vs serial", flush=True)
    if not warmup(url, model):
        return {"test": "concurrent", "model": model, "error": "warmup failed"}
    msgs = [{"role": "user", "content": SINGLE_PROMPTS["reasoning"]}]

    t0 = time.perf_counter()
    for _ in range(n):
        one_request(url, model, msgs)
    serial_s = time.perf_counter() - t0

    t0 = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as ex:
        par = list(ex.map(lambda _: one_request(url, model, msgs), range(n)))
    par_s = time.perf_counter() - t0

    speedup = round(serial_s / par_s, 2) if par_s > 0 else None
    fails = sum(1 for r in par if "error" in r)
    print(
        f"      serial {serial_s:.1f}s vs parallel {par_s:.1f}s "
        f"-> {speedup}x, {fails}/{n} failures",
        flush=True,
    )
    return {
        "test": "concurrent",
        "model": model,
        "serial_s": round(serial_s, 2),
        "parallel_s": round(par_s, 2),
        "speedup_x": speedup,
        "failures": fails,
        "verdict": "PASS" if speedup and speedup > 1.2 and fails == 0 else "FAIL",
    }


SHOOTOUT_DURATION_S = 120
SHOOTOUT_CONCURRENCY = 5  # matches PORTAL5_DEFAULT_WORKSPACE_CONCURRENCY (concurrency.py)
# auto-coding (qwen3-coder's real production workspace) uses context_limit=16384,
# predict_limit=16384 (config/portal.yaml). max_tokens is capped below that ceiling
# for practical sweep duration — 16384 tokens at ~15 tok/s is 15-20 min/request.
SHOOTOUT_MAX_TOKENS = 4096

# Multi-step tasks (not single-fact recall) so decode-TPS/tps_cv reflect sustained compute.
SHOOTOUT_PROMPTS = {
    "coding_hard": (
        "Implement an LRU (least-recently-used) cache in Python with get and put "
        "in true O(1) time. Use a dict plus a doubly linked list — do not use "
        "OrderedDict or functools.lru_cache. Explain why a plain dict alone cannot "
        "achieve O(1) eviction order, walk through what happens on a put that "
        "evicts an existing key, and note one thread-safety concern if this cache "
        "were shared across requests."
    ),
    "debugging": (
        "This Python function is supposed to return the second-largest unique "
        "value in a list, or None if fewer than two unique values exist:\n\n"
        "def second_largest(nums):\n"
        "    largest = second = float('-inf')\n"
        "    for n in nums:\n"
        "        if n > largest:\n"
        "            second = largest\n"
        "            largest = n\n"
        "        elif n > second:\n"
        "            second = n\n"
        "    return second if second != float('-inf') else None\n\n"
        "Find the bug (give a concrete input where it returns the wrong answer), "
        "explain why it happens, and provide a corrected version."
    ),
    "scheduling_reasoning": (
        "Four technicians (A, B, C, D) must each complete a distinct one-hour "
        "task (1, 2, 3, 4) between 9am and 1pm. Constraints: A cannot work "
        "before 10am. Task 2 must immediately precede task 4 (same technician "
        "or handoff, back-to-back with no gap). C must do task 3. D's task must "
        "start after B's task ends. Task 1 cannot be the last task of the day. "
        "Find a valid full schedule (technician + task + start time for each "
        "slot) satisfying every constraint, and show your reasoning step by "
        "step — don't just assert an answer."
    ),
    "tradeoff_analysis": (
        "A team is choosing between write-through and write-back caching for a "
        "service that caches database rows in front of a relational database "
        "with strict consistency requirements for financial balances, but also "
        "has a high-write-volume audit-log table where occasional data loss on "
        "crash is acceptable. Recommend a caching strategy for EACH of the two "
        "tables separately, justify each choice against the other option, and "
        "identify the specific failure mode each choice avoids."
    ),
}


def _shootout_pct(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    k = min(len(xs) - 1, int(round((p / 100.0) * (len(xs) - 1))))
    return round(xs[k], 3)


def _shootout_run_load(
    url: str,
    models: list[str],
    prompts: list[str],
    duration_s: int,
    concurrency: int,
    max_tokens: int = SHOOTOUT_MAX_TOKENS,
) -> tuple[list[dict], float]:
    import threading

    samples: list[dict] = []
    stop_at = time.perf_counter() + duration_s
    rr = {"i": 0}
    lock = threading.Lock()
    # Context sizing: pass real -ctxNk-tagged Ollama model ids in `models` (their
    # num_ctx is Modelfile-baked, the only mechanism that actually works — Ollama's
    # /v1/chat/completions endpoint silently ignores a runtime options.num_ctx
    # override, verified live). Don't pass a bare untagged id expecting a cap.

    def _one() -> dict:
        with lock:
            idx = rr["i"]
            rr["i"] += 1
        model = models[idx % len(models)]
        prompt = prompts[idx % len(prompts)]
        r = one_request(url, model, [{"role": "user", "content": prompt}], max_tokens=max_tokens)
        r["model"] = model
        return r

    def _worker() -> None:
        while time.perf_counter() < stop_at:
            try:
                samples.append(_one())
            except Exception as exc:
                samples.append({"error": str(exc), "ttft_s": None, "tps": 0.0})

    threads = [threading.Thread(target=_worker) for _ in range(concurrency)]
    t0 = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return samples, time.perf_counter() - t0


def _shootout_summarize(
    samples: list[dict], models: list[str], duration_s: int, concurrency: int, wall_s: float
) -> dict:
    import statistics as _st

    ok = [r for r in samples if "error" not in r and r.get("ttft_s") is not None]
    ttfts = sorted(r["ttft_s"] for r in ok)
    tpss = [r["tps"] for r in ok if r.get("tps")]
    fails = len(samples) - len(ok)
    truncated = sum(1 for r in ok if r.get("finish_reason") == "length")
    avg_response_chars = (
        round(_st.mean([r.get("response_chars", 0) for r in ok]), 0) if ok else None
    )

    per_model: dict[str, dict] = {}
    for m in models:
        m_ok = [r for r in ok if r.get("model") == m]
        per_model[m] = {
            "requests": len(m_ok),
            "ttft_p50": _shootout_pct(sorted(r["ttft_s"] for r in m_ok), 50),
            "ttft_p95": _shootout_pct(sorted(r["ttft_s"] for r in m_ok), 95),
            "tps_mean": round(_st.mean([r["tps"] for r in m_ok if r.get("tps")]), 1)
            if any(r.get("tps") for r in m_ok)
            else None,
        }

    tps_cv = (
        round(_st.pstdev(tpss) / _st.mean(tpss), 3) if len(tpss) > 1 and _st.mean(tpss) else None
    )
    return {
        "test": "shootout",
        "models": models,
        "duration_s": duration_s,
        "concurrency": concurrency,
        "wall_s": round(wall_s, 1),
        "total_requests": len(samples),
        "ok": len(ok),
        "failures": fails,
        "throughput_rps": round(len(ok) / wall_s, 2) if wall_s else None,
        "ttft_p50": _shootout_pct(ttfts, 50),
        "ttft_p95": _shootout_pct(ttfts, 95),
        "ttft_p99": _shootout_pct(ttfts, 99),
        "tps_mean": round(_st.mean(tpss), 1) if tpss else None,
        "tps_cv": tps_cv,
        "truncated": truncated,  # finish_reason == "length" — hit max_tokens before finishing
        "avg_response_chars": avg_response_chars,
        "per_model": per_model,
    }


def gate_shootout(
    url: str,
    models: list[str],
    duration_s: int = SHOOTOUT_DURATION_S,
    concurrency: int = SHOOTOUT_CONCURRENCY,
    max_tokens: int = SHOOTOUT_MAX_TOKENS,
) -> dict:
    """Sustained mixed-model concurrent load, using SHOOTOUT_PROMPTS — does it hold steady."""
    for m in models:
        warmup(url, m)
    prompts = list(SHOOTOUT_PROMPTS.values())
    samples, wall_s = _shootout_run_load(url, models, prompts, duration_s, concurrency, max_tokens)
    result = _shootout_summarize(samples, models, duration_s, concurrency, wall_s)
    print(
        f"      {result['ok']}/{result['total_requests']} ok, {result['failures']} fail, "
        f"rps={result['throughput_rps']}, ttft p50/p95/p99="
        f"{result['ttft_p50']}/{result['ttft_p95']}/{result['ttft_p99']}s, "
        f"tps_mean={result['tps_mean']} cv={result['tps_cv']}, "
        f"truncated={result['truncated']}/{result['ok']}, "
        f"avg_chars={result['avg_response_chars']}",
        flush=True,
    )
    return result


# ── Driver ────────────────────────────────────────────────────────────────────

GATES = {
    "kv": gate_kv,
    "tps": gate_tps,
    "tools": gate_tools,
    "grammar": gate_grammar,
    "concurrent": gate_concurrent,
    "shootout": gate_shootout,
}


def main() -> None:
    p = argparse.ArgumentParser(description="oMLX v3 Phase-0 gate probe")
    p.add_argument("--gate", choices=[*GATES, "mtp", "all"], required=True)
    p.add_argument("--url", default=OMLX_URL)
    p.add_argument(
        "--models", default=None, help="Comma list of keys from OMLX_MODELS, or explicit model ids"
    )
    p.add_argument("--tag", default=None, help="Extra tag for the results filename")
    p.add_argument(
        "--duration", type=int, default=SHOOTOUT_DURATION_S, help="shootout gate: seconds"
    )
    p.add_argument(
        "--concurrency",
        type=int,
        default=SHOOTOUT_CONCURRENCY,
        help="shootout gate: parallel workers",
    )
    p.add_argument(
        "--max-tokens",
        type=int,
        default=SHOOTOUT_MAX_TOKENS,
        help="shootout gate: max_tokens per request (room to actually reason)",
    )
    args = p.parse_args()

    if args.models:
        keys = args.models.split(",")
        models = [OMLX_MODELS.get(k, k) for k in keys]
    else:
        models = list(OMLX_MODELS.values())

    gates = list(GATES) if args.gate == "all" else [args.gate]
    engine = "omlx" if "8085" in args.url else "ollama"
    started = datetime.now(UTC)
    all_results = []

    if args.gate == "shootout":
        print(f"\n=== shootout: {models} @ {args.url} ===", flush=True)
        res = gate_shootout(
            args.url,
            models,
            duration_s=args.duration,
            concurrency=args.concurrency,
            max_tokens=args.max_tokens,
        )
        res["gate"] = "shootout"
        res["engine"] = engine
        all_results.append(res)
    else:
        for model in models:
            print(f"\n=== {model} @ {args.url} ===", flush=True)
            for g in gates:
                res = gate_mtp(args.url, model) if g == "mtp" else GATES[g](args.url, model)
                res["gate"] = g
                res["engine"] = engine
                all_results.append(res)

    ts = started.strftime("%Y%m%dT%H%M%SZ")
    tag = f"_{args.tag}" if args.tag else ""
    out = RESULTS_DIR / f"omlx_v3_{args.gate}{tag}_{engine}_{ts}.json"
    out.write_text(
        json.dumps(
            {
                "task": "P5-FUT-013 v3 Phase-0 re-evaluation",
                "omlx_version": "0.5.4",
                "engine": engine,
                "url": args.url,
                "started": started.isoformat(),
                "models": models,
                "gates": gates,
                "results": all_results,
            },
            indent=2,
        )
    )
    print(f"\nResults -> {out}")


if __name__ == "__main__":
    main()
