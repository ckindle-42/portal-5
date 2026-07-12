"""Exhaustive acceptance bench runner for tool preselection.

Runs every scenario from scenarios.json against gemma4:e2b-mlx and
gemma4:e4b-mlx with 3 reps each, warmup call isolated, sequential
execution if OLLAMA_NUM_PARALLEL is unset/1.

Output: tests/results/toolpreselect_acceptance_<UTC-timestamp>.jsonl
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

# ---------------------------------------------------------------------------
# Reuse the existing parser and prompt builder from cli_probe
# ---------------------------------------------------------------------------
from portal.platform.inference.tool_preselect.parser import (
    indices_to_tool_names,
    parse_ranked_indices,
)
from portal.platform.inference.tool_preselect.prompts import build_prompt

OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
REPS_PER_SCENARIO = 3
THINK = False  # explicitly suppress thinking mode
K = 3  # top-K to report
TEMPERATURE = 0.0
TOP_K_PARAM = 1
NUM_PREDICT = 200
TIMEOUT_S = 15.0  # per-call httpx timeout


def _get_parallelism() -> str:
    val = os.environ.get("OLLAMA_NUM_PARALLEL", "1")
    try:
        n = int(val)
    except ValueError:
        n = 1
    return "sequential" if n <= 1 else f"parallel(n={n})"


async def _warmup(model: str) -> dict:
    """Issue one throwaway warmup call to isolate model-load latency."""
    payload = {
        "model": model,
        "prompt": "Return the number 1.",
        "stream": False,
        "think": False,
        "keep_alive": "10m",
        "options": {"temperature": 0.0, "top_k": 1, "num_predict": 10},
    }
    t0 = time.monotonic()
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        resp = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
    latency_ms = int((time.monotonic() - t0) * 1000)
    resp.raise_for_status()
    data = resp.json()
    return {
        "latency_ms": latency_ms,
        "eval_count": data.get("eval_count"),
        "eval_duration_ns": data.get("eval_duration"),
    }


async def _run_scenario(
    model: str,
    scenario: dict,
    tool_names: list[str],
    descriptions: dict[str, str],
    k: int,
) -> dict:
    """Run a single scenario once and return the raw result."""
    user_turn = scenario["user_turn"]

    # For reversed scenarios, reverse the tool list
    if scenario.get("tool_list_order") == "reversed":
        ordered_names = list(reversed(tool_names))
    else:
        ordered_names = tool_names

    prompt = build_prompt(user_turn, ordered_names, descriptions, k, slack=3)

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": THINK,
        "keep_alive": "10m",
        "options": {
            "temperature": TEMPERATURE,
            "top_p": 1.0,
            "top_k": TOP_K_PARAM,
            "num_predict": NUM_PREDICT,
        },
    }

    t0 = time.monotonic()
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        resp = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
    latency_ms = int((time.monotonic() - t0) * 1000)
    resp.raise_for_status()
    data = resp.json()
    raw = data.get("response", "")
    thinking_raw = data.get("thinking", "") or data.get("reasoning", "")

    # Parse ranked tools from the model's response
    indices = parse_ranked_indices(raw, valid_max=len(ordered_names))
    ranked = indices_to_tool_names(indices, ordered_names)

    # Score: check if any acceptable tool is in top-K
    acceptable = set(scenario.get("acceptable_tools", []))
    top_k = ranked[:k]
    hit = bool(acceptable & set(top_k)) if acceptable else None  # None for no_good_fit
    top1_hit = bool(acceptable & {top_k[0]}) if top_k and acceptable else None

    return {
        "model": model,
        "scenario_id": scenario["id"],
        "category": scenario["category"],
        "user_turn": user_turn,
        "tool_list_order": scenario.get("tool_list_order", "normal"),
        "acceptable_tools": scenario.get("acceptable_tools", []),
        "k": k,
        "ranked_tools": top_k,
        "raw_ranked_all": ranked,
        "hit_top_k": hit,
        "hit_top_1": top1_hit,
        "latency_ms": latency_ms,
        "eval_count": data.get("eval_count"),
        "eval_duration_ns": data.get("eval_duration"),
        "thinking_leaked": bool(thinking_raw),
        "thinking_raw": thinking_raw[:500] if thinking_raw else "",
        "raw_response": raw[:1000],
        "timestamp": datetime.now(UTC).isoformat(),
    }


async def _run_model(
    model: str,
    scenarios: list[dict],
    tool_names: list[str],
    descriptions: dict[str, str],
    jsonl_path: Path,
) -> list[dict]:
    """Run all scenarios for one model with warmup isolation."""
    parallelism = _get_parallelism()
    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"Model: {model}", file=sys.stderr)
    print(f"Scenarios: {len(scenarios)}", file=sys.stderr)
    print(f"Reps per scenario: {REPS_PER_SCENARIO}", file=sys.stderr)
    print(f"Concurrency: {parallelism}", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)

    # Warmup call (discarded from stats)
    print("  Warmup call...", end="", flush=True, file=sys.stderr)
    warmup = await _warmup(model)
    print(f" {warmup['latency_ms']}ms", file=sys.stderr)

    results: list[dict] = []
    sequential = "sequential" in parallelism

    for i, sc in enumerate(scenarios):
        scenario_results = []
        for rep in range(REPS_PER_SCENARIO):
            if sequential:
                result = await _run_scenario(model, sc, tool_names, descriptions, K)
            else:
                result = await _run_scenario(model, sc, tool_names, descriptions, K)

            result["rep"] = rep
            scenario_results.append(result)
            results.append(result)

            # Write one valid JSON line per rep
            with open(jsonl_path, "a") as f:
                f.write(json.dumps(result, ensure_ascii=True) + "\n")

        # Progress indicator
        sc_id = sc["id"]
        hits = sum(1 for r in scenario_results if r["hit_top_k"])
        lats = [r["latency_ms"] for r in scenario_results]
        avg_lat = sum(lats) // len(lats) if lats else 0
        print(
            f"  [{i + 1:3d}/{len(scenarios)}] {sc_id:12s} "
            f"hits={hits}/{REPS_PER_SCENARIO} avg_lat={avg_lat}ms",
            file=sys.stderr,
        )

    return results


def _load_scenarios(scenarios_path: Path) -> tuple[list[dict], list[dict], dict[str, str]]:
    """Load scenarios and build tool metadata."""
    with open(scenarios_path) as f:
        data = json.load(f)

    tools = data["tools"]
    tool_names = [t["name"] for t in tools]
    descriptions = {t["name"]: t["description"] for t in tools}
    scenarios = data["scenarios"]

    return scenarios, tool_names, descriptions


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Tool preselect exhaustive acceptance bench")
    p.add_argument(
        "--scenarios",
        default=str(Path(__file__).parent / "scenarios.json"),
        help="Path to scenarios.json",
    )
    p.add_argument(
        "--models",
        nargs="+",
        default=["gemma4:e2b-mlx", "gemma4:e4b-mlx"],
        help="Ollama model tags to evaluate",
    )
    p.add_argument(
        "--output-dir",
        default=str(Path(__file__).parent.parent / "results"),
        help="Directory for JSONL output",
    )
    args = p.parse_args(argv)

    scenarios_path = Path(args.scenarios)
    if not scenarios_path.exists():
        print(f"ERROR: {scenarios_path} not found. Run scenario_gen.py first.", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    jsonl_path = output_dir / f"toolpreselect_acceptance_{ts}.jsonl"

    scenarios, tool_names, descriptions = _load_scenarios(scenarios_path)
    print(f"Loaded {len(scenarios)} scenarios, {len(tool_names)} tools", file=sys.stderr)

    # Clear the JSONL file
    jsonl_path.write_text("")

    # Run each model
    all_results: dict[str, list[dict]] = {}
    for model in args.models:
        results = asyncio.run(_run_model(model, scenarios, tool_names, descriptions, jsonl_path))
        all_results[model] = results

    print(f"\nRaw results written to: {jsonl_path}", file=sys.stderr)

    # Print summary
    print(f"\n{'=' * 60}", file=sys.stderr)
    print("SUMMARY", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)
    for model, results in all_results.items():
        by_cat: dict[str, list[dict]] = {}
        for r in results:
            by_cat.setdefault(r["category"], []).append(r)
        print(f"\n{model}:", file=sys.stderr)
        for cat, cat_results in sorted(by_cat.items()):
            hits = sum(1 for r in cat_results if r["hit_top_k"])
            total = len(cat_results)
            pct = (hits / total * 100) if total else 0
            print(f"  {cat:15s}: {hits:3d}/{total:3d} ({pct:.1f}%)", file=sys.stderr)
        all_hits = sum(1 for r in results if r["hit_top_k"])
        all_total = len(results)
        all_pct = (all_hits / all_total * 100) if all_total else 0
        print(f"  {'OVERALL':15s}: {all_hits:3d}/{all_total:3d} ({all_pct:.1f}%)", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
