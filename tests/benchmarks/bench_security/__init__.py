"""Portal 5 — Security Model Benchmark (refactored package).

Submodules
----------
_data      Static configuration, prompt library, exec sequences, lab constants
_config    BenchConfig dataclass — per-run context replacing mutable globals
scoring    Pure scoring functions (no I/O, no mutable state)
lab        Lab lifecycle — probing, snapshot/restore, tool dispatch, stealth queries
blue       Blue team defender — detection chain, telemetry, purple scoring
chain      Chain execution — multi-turn tool-call chains, scenarios, synthetic results
cli        CLI entry point — argparse, run_bench, summary printing

This module is a thin facade: it defines the two pipeline I/O functions
(call_pipeline, call_pipeline_exec) used by run_bench, and re-exports
all public symbols from the submodules for backward compatibility.
"""

from __future__ import annotations

import json as _json
import time

import httpx

# ── Config ───────────────────────────────────────────────────────────────────
from ._config import BenchConfig

# ── Data (static constants) ──────────────────────────────────────────────────
from ._data import (
    _LAB_PREFIX,
    CHAIN_INHERITANCE,
    DEFAULT_WORKSPACES,
    DISCLAIMER_PATTERNS,
    EXEC_SEQUENCES,
    EXECUTION_WORKSPACES,
    MITRE_PATTERN,
    PIPELINE_API_KEY,
    PIPELINE_URL,
    PROMPT_MAX_TOKENS,
    PROMPTS,
    REQUEST_TIMEOUT,
    RESULTS_DIR,
)

# ── Blue ─────────────────────────────────────────────────────────────────────
from .blue import (
    BLUE_TOOLS,
    run_blue_chain_tests,
    run_purple_tests,
)

# ── Chain ────────────────────────────────────────────────────────────────────
from .chain import (
    CHAIN_TOOLS_BASE,
    OLLAMA_URL,
    SCENARIOS,
    _run_exec_chain,
    _run_multimodel_chain,
    _run_refusal_test,
    run_audit_tools,
    run_candidate_intake,
    run_chain_tests,
    _pull_model,
    _tps_warmup,
    TPS_FLOOR,
    PULL_TIMEOUT_S,
)

# ── CLI ──────────────────────────────────────────────────────────────────────
from .cli import (
    main,
    run_bench,
)

# ── Lab ──────────────────────────────────────────────────────────────────────
from .lab import (
    dispatch_lab_tool,
    print_lab_probe_report,
    probe_lab_services,
    restore_lab_vms,
    snapshot_lab_vms,
)

# ── Scoring ──────────────────────────────────────────────────────────────────
from .scoring import (
    evaluate_condition,
    score_execution,
    score_handoff_quality,
    score_response,
    scoring_criteria_met,
)

# ── Public API ───────────────────────────────────────────────────────────────
__all__ = [
    # Entry point
    "main",
    "run_bench",
    # Config
    "BenchConfig",
    # Scoring
    "evaluate_condition",
    "score_response",
    "score_execution",
    "score_handoff_quality",
    "scoring_criteria_met",
    # Pipeline I/O (defined below)
    "call_pipeline",
    "call_pipeline_exec",
    # Lab
    "probe_lab_services",
    "print_lab_probe_report",
    "snapshot_lab_vms",
    "restore_lab_vms",
    "dispatch_lab_tool",
    # Blue
    "run_blue_chain_tests",
    "run_purple_tests",
    "BLUE_TOOLS",
    # Chain
    "_run_exec_chain",
    "_run_multimodel_chain",
    "_run_refusal_test",
    "run_chain_tests",
    "run_audit_tools",
    "run_candidate_intake",
    "_pull_model",
    "_tps_warmup",
    "TPS_FLOOR",
    "PULL_TIMEOUT_S",
    "CHAIN_TOOLS_BASE",
    "OLLAMA_URL",
    "SCENARIOS",
    # Data
    "PROMPTS",
    "EXEC_SEQUENCES",
    "CHAIN_INHERITANCE",
    "DEFAULT_WORKSPACES",
    "EXECUTION_WORKSPACES",
    "RESULTS_DIR",
    "PIPELINE_URL",
    "PIPELINE_API_KEY",
    "REQUEST_TIMEOUT",
    "PROMPT_MAX_TOKENS",
    "DISCLAIMER_PATTERNS",
    "MITRE_PATTERN",
]


# ── Pipeline I/O ─────────────────────────────────────────────────────────────
# These two functions do httpx streaming against the Portal Pipeline SSE
# endpoint.  They live here (not in a submodule) because run_bench imports
# them at function level to avoid circular imports with cli.py.


def call_pipeline(
    workspace: str, prompt: str, prompt_meta: dict | None = None
) -> tuple[str, float]:
    """Call pipeline workspace via SSE streaming; stop on the first of:

    1. [DONE] SSE event — model finished naturally
    2. Content-completion event — all scoring criteria satisfied
    3. max_tokens capacity event — model-level token cap
    4. REQUEST_TIMEOUT per-chunk httpx ceiling — fires on absent data
    """
    headers = {"Authorization": f"Bearer {PIPELINE_API_KEY}"}
    parts: list[str] = []
    t0 = time.monotonic()
    with httpx.Client(timeout=httpx.Timeout(REQUEST_TIMEOUT, connect=5.0)) as client:
        with client.stream(
            "POST",
            f"{PIPELINE_URL}/v1/chat/completions",
            json={
                "model": workspace,
                "messages": [{"role": "user", "content": prompt}],
                "stream": True,
                "max_tokens": PROMPT_MAX_TOKENS,
            },
            headers=headers,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line == "data: [DONE]":
                    break
                if line.startswith("data: "):
                    try:
                        d = _json.loads(line[6:])
                        c = d["choices"][0]["delta"].get("content") or ""
                        if c:
                            parts.append(c)
                    except Exception:
                        pass
                if prompt_meta and parts and scoring_criteria_met("".join(parts), prompt_meta):
                    break
    return "".join(parts), time.monotonic() - t0


def call_pipeline_exec(
    workspace: str, prompt: str, prompt_meta: dict | None = None
) -> tuple[str, list[dict], float]:
    """Execution pass: tools ENABLED through pipeline, capture via exec_audit trailer."""
    headers = {"Authorization": f"Bearer {PIPELINE_API_KEY}"}
    parts: list[str] = []
    tool_calls: list[dict] = []
    t0 = time.monotonic()

    exec_prompt = (prompt_meta.get("exec_text") if prompt_meta else None) or (_LAB_PREFIX + prompt)

    with httpx.Client(timeout=httpx.Timeout(REQUEST_TIMEOUT, connect=5.0)) as client:
        with client.stream(
            "POST",
            f"{PIPELINE_URL}/v1/chat/completions",
            json={
                "model": workspace,
                "messages": [{"role": "user", "content": exec_prompt}],
                "stream": True,
                "max_tokens": PROMPT_MAX_TOKENS,
                "exec_audit": True,
            },
            headers=headers,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line == "data: [DONE]":
                    break
                if not line.startswith("data: "):
                    continue
                try:
                    d = _json.loads(line[6:])
                    if d.get("type") == "exec_audit":
                        for tc in d.get("tool_calls", []):
                            args_raw = tc.get("arguments", "")
                            try:
                                args = _json.loads(args_raw) if args_raw else {}
                            except Exception:
                                args = {"_raw": args_raw}
                            tool_calls.append({"tool": tc.get("tool", ""), "arguments": args})
                        continue
                    c = (d.get("choices") or [{}])[0].get("delta", {}).get("content") or ""
                    if c:
                        parts.append(c)
                except Exception:
                    pass

    return "".join(parts), tool_calls, time.monotonic() - t0


if __name__ == "__main__":
    main()
