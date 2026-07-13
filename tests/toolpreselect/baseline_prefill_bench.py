"""Baseline prefill bench — measures primary-model prefill cost of full tool schemas.

Compares three conditions per workspace/model:
  FULL:     all tools the workspace sends (8-15 tools)
  TRIMMED:  first 3 tools from that list (simulating preselector K=3 output)
  ZERO:     no tools at all (floor reference)

Measures prompt_eval_duration (prefill-isolated) not end-to-end latency.

Output: tests/results/baseline_prefill_bench_<UTC-timestamp>.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
REPS = 5
NUM_PREDICT = 20
TIMEOUT_S = 60.0

# Workspace configurations: model + fixed user turn. This bench hits Ollama
# directly (OLLAMA_URL) with an explicit model tag per entry — the dict key
# is a display/grouping label only, never a pipeline model_slug. "auto-agentic"/
# "auto-agentic-lite" keys renamed to "auto-coding+heavy"/"auto-coding+lite"
# (BUILD_PROGRAM_ALIAS_RETIRE_V1.md Phase 3) to match the workspace+variant
# those aliases fold into, for legibility.
WORKSPACE_CONFIGS: dict[str, dict] = {
    "auto-coding": {
        "model": "qwen3-coder:30b-a3b-q4_K_M-ctx16k",
        "user_turn": "Run this Python snippet and tell me the output: print(sum(range(100)))",
    },
    "auto-coding+heavy": {
        "model": "qwen3-coder-next:latest-ctx64k",
        "user_turn": "Search the web for today's date and tell me what day of the week it is.",
    },
    "auto-daily": {
        "model": "gemma4:26b-a4b-it-qat-ctx8k",
        "user_turn": "Read my calendar summary document and tell me what meetings I have today.",
    },
    "auto-coding+lite": {
        "model": "hf.co/unsloth/Qwen-AgentWorld-35B-A3B-GGUF:UD-Q4_K_XL-ctx64k",
        "user_turn": "Search the web for today's date and tell me what day of the week it is.",
    },
}

# Tool name lists per workspace (from portal.yaml)
WORKSPACE_TOOL_NAMES: dict[str, list[str]] = {
    "auto-coding": [
        "execute_python",
        "execute_nodejs",
        "execute_bash",
        "sandbox_status",
        "read_word_document",
        "read_pdf",
        "remember",
        "recall",
    ],
    "auto-coding+heavy": [
        "execute_python",
        "execute_bash",
        "execute_nodejs",
        "sandbox_status",
        "read_word_document",
        "read_excel",
        "read_powerpoint",
        "read_pdf",
        "classify_vulnerability",
        "web_search",
        "web_fetch",
        "remember",
        "recall",
        "kb_search",
        "kb_list",
    ],
    "auto-daily": [
        "web_search",
        "web_fetch",
        "kb_search",
        "kb_list",
        "read_pdf",
        "read_word_document",
        "read_excel",
        "create_word_document",
        "create_excel",
        "create_powerpoint",
        "execute_python",
        "remember",
        "recall",
        "generate_music",
        "transcribe_audio",
    ],
    "auto-coding+lite": [
        "execute_python",
        "execute_bash",
        "execute_nodejs",
        "sandbox_status",
        "read_word_document",
        "read_excel",
        "read_powerpoint",
        "read_pdf",
        "classify_vulnerability",
        "web_search",
        "web_fetch",
        "remember",
        "recall",
        "kb_search",
        "kb_list",
    ],
}


def _load_tool_schemas(schemas_path: Path) -> dict[str, list[dict]]:
    """Load pre-extracted OpenAI-format tool schemas."""
    with open(schemas_path) as f:
        return json.load(f)


async def _warmup(model: str) -> dict:
    """Throwaway call to warm the model."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Say ok."}],
        "stream": False,
        "think": False,
        "keep_alive": "10m",
        "options": {"temperature": 0.0, "top_k": 1, "num_predict": 5},
    }
    t0 = time.monotonic()
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        resp = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
    latency_ms = int((time.monotonic() - t0) * 1000)
    resp.raise_for_status()
    data = resp.json()
    return {"latency_ms": latency_ms, "model": data.get("model", model)}


async def _run_single(
    model: str,
    user_turn: str,
    tools: list[dict] | None,
) -> dict:
    """Run one inference call and extract prefill metrics."""
    messages = [{"role": "user", "content": user_turn}]
    payload: dict = {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": False,
        "keep_alive": "10m",
        "options": {
            "temperature": 0.0,
            "top_k": 1,
            "num_predict": NUM_PREDICT,
        },
    }
    if tools is not None:
        payload["tools"] = tools

    t0 = time.monotonic()
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        resp = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
    wall_ms = int((time.monotonic() - t0) * 1000)
    if resp.status_code == 500:
        # Ollama transient error — return partial result
        return {
            "wall_ms": wall_ms,
            "prompt_eval_count": None,
            "prompt_eval_duration_ms": None,
            "prompt_tps": None,
            "eval_count": None,
            "eval_duration_ms": None,
            "tool_count": len(tools) if tools else 0,
            "error": "500",
        }
    resp.raise_for_status()
    data = resp.json()

    # Extract prefill-isolated metrics
    prompt_eval_count = data.get("prompt_eval_count")
    prompt_eval_duration_ns = data.get("prompt_eval_duration")
    prompt_eval_duration_ms = (
        round(prompt_eval_duration_ns / 1_000_000, 1) if prompt_eval_duration_ns else None
    )

    # Extract generation metrics (sanity check — should be roughly flat)
    eval_count = data.get("eval_count")
    eval_duration_ns = data.get("eval_duration")
    eval_duration_ms = round(eval_duration_ns / 1_000_000, 1) if eval_duration_ns else None

    # Tokens per second for prefill
    prompt_tps = (
        round(prompt_eval_count / (prompt_eval_duration_ns / 1_000_000_000), 1)
        if prompt_eval_count and prompt_eval_duration_ns
        else None
    )

    return {
        "wall_ms": wall_ms,
        "prompt_eval_count": prompt_eval_count,
        "prompt_eval_duration_ms": prompt_eval_duration_ms,
        "prompt_tps": prompt_tps,
        "eval_count": eval_count,
        "eval_duration_ms": eval_duration_ms,
        "tool_count": len(tools) if tools else 0,
    }


async def _run_workspace(
    workspace: str,
    config: dict,
    all_schemas: dict[str, list[dict]],
    jsonl_path: Path,
) -> list[dict]:
    """Run all conditions for one workspace."""
    model = config["model"]
    user_turn = config["user_turn"]
    all_tools = all_schemas.get(workspace, [])

    # Build condition tool lists
    full_tools = all_tools  # all tools from live registry
    trimmed_tools = all_tools[:3] if len(all_tools) >= 3 else all_tools
    zero_tools = None

    conditions = {
        "FULL": full_tools,
        "TRIMMED": trimmed_tools,
        "ZERO": zero_tools,
    }

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"Workspace: {workspace}", file=sys.stderr)
    print(f"Model: {model}", file=sys.stderr)
    print(f"Tool count FULL={len(full_tools)} TRIMMED={len(trimmed_tools)}", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)

    # Warmup
    print("  Warmup...", end="", flush=True, file=sys.stderr)
    warmup = await _warmup(model)
    print(f" {warmup['latency_ms']}ms", file=sys.stderr)

    results: list[dict] = []
    for condition, tools in conditions.items():
        print(
            f"  {condition} ({len(tools) if tools else 0} tools)...",
            end="",
            flush=True,
            file=sys.stderr,
        )
        rep_results = []
        for rep in range(REPS):
            r = await _run_single(model, user_turn, tools)
            # Retry once on Ollama 500
            if r.get("error") == "500":
                print(" [retry]", end="", flush=True, file=sys.stderr)
                await asyncio.sleep(2)
                r = await _run_single(model, user_turn, tools)
            r["workspace"] = workspace
            r["model"] = model
            r["condition"] = condition
            r["rep"] = rep
            r["user_turn"] = user_turn
            r["timestamp"] = datetime.now(UTC).isoformat()
            rep_results.append(r)
            results.append(r)

            with open(jsonl_path, "a") as f:
                f.write(json.dumps(r, ensure_ascii=True) + "\n")

        lats = [r["prompt_eval_duration_ms"] for r in rep_results if r["prompt_eval_duration_ms"]]
        if lats:
            lats_sorted = sorted(lats)
            p50 = lats_sorted[len(lats_sorted) // 2]
            print(f" prompt_eval p50={p50}ms", file=sys.stderr)
        else:
            print(" no prompt_eval data", file=sys.stderr)

    return results


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Baseline prefill bench for tool schema cost")
    p.add_argument(
        "--schemas",
        default="/tmp/workspace_tool_schemas.json",
        help="Path to workspace_tool_schemas.json from Phase 1",
    )
    p.add_argument(
        "--output-dir",
        default=str(Path(__file__).parent.parent / "results"),
        help="Directory for JSONL output",
    )
    args = p.parse_args(argv)

    schemas_path = Path(args.schemas)
    if not schemas_path.exists():
        print(f"ERROR: {schemas_path} not found. Run Phase 1 first.", file=sys.stderr)
        return 1

    all_schemas = _load_tool_schemas(schemas_path)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    jsonl_path = output_dir / f"baseline_prefill_bench_{ts}.jsonl"
    jsonl_path.write_text("")

    all_results: dict[str, list[dict]] = {}
    for workspace, config in WORKSPACE_CONFIGS.items():
        results = asyncio.run(_run_workspace(workspace, config, all_schemas, jsonl_path))
        all_results[workspace] = results

    print(f"\nRaw results written to: {jsonl_path}", file=sys.stderr)

    # Summary
    print(f"\n{'=' * 72}", file=sys.stderr)
    print(
        f"{'Workspace':<20} {'Condition':<10} {'prompt_eval p50':>16} {'prompt_eval p95':>16} {'wall p50':>10}",
        file=sys.stderr,
    )
    print(f"{'=' * 72}", file=sys.stderr)
    for workspace, results in all_results.items():
        by_cond: dict[str, list[dict]] = {}
        for r in results:
            by_cond.setdefault(r["condition"], []).append(r)
        for cond in ["ZERO", "TRIMMED", "FULL"]:
            cond_results = by_cond.get(cond, [])
            prompt_lats = sorted(
                [r["prompt_eval_duration_ms"] for r in cond_results if r["prompt_eval_duration_ms"]]
            )
            wall_lats = sorted([r["wall_ms"] for r in cond_results])
            if prompt_lats:
                p50 = prompt_lats[len(prompt_lats) // 2]
                p95 = prompt_lats[int(len(prompt_lats) * 0.95)]
                wall_p50 = wall_lats[len(wall_lats) // 2] if wall_lats else 0
                print(
                    f"  {workspace:<18} {cond:<10} {p50:>13.1f}ms {p95:>13.1f}ms {wall_p50:>8}ms",
                    file=sys.stderr,
                )
            else:
                print(
                    f"  {workspace:<18} {cond:<10} {'N/A':>16} {'N/A':>16} {'N/A':>10}",
                    file=sys.stderr,
                )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
