#!/usr/bin/env python3
"""CAD tool-call convergence probe (TASK-BENCH-FOLLOWUP-001 Part 2).

Re-benches Deepwen-3.6's CAD reliability on N>=20 trials of the same
production CAD prompt against the auto-cad incumbent (Qwen3-Coder), scoring:
  1. first-attempt tool-call convergence rate (no retry)
  2. STL validity (openscad --render succeeds via render_openscad)
  3. mesh watertightness (render_mesh's trimesh-derived `watertight` field)
and, for trials that didn't converge on the first attempt, an optional bounded
1-retry/nudge policy re-scored the same way. Isolated: writes only to
tests/benchmarks/results/, never touches production workspaces or config.

Usage:
    python3 tests/benchmarks/bench_cad_probe.py --trials 20 \
        --candidate bench-deepwen-cad --incumbent auto-cad
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "tests" / "benchmarks" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

OLLAMA_URL = "http://localhost:11434"
CAD_MCP_URL = "http://localhost:8926"
GEN_TIMEOUT_S = 420.0
TOOL_TIMEOUT_S = 150.0  # openscad --render can be slow on complex geometry

CAD_SYSTEM_PROMPT = (
    "CAD OUTPUT RULE: When asked for a 3D model or printable part, write COMPLETE "
    "OpenSCAD source code in a fenced ```openscad block. State all dimensions as "
    "named variables at the top (units=mm, wall thickness, tolerances) so the part "
    "is parametric. End by calling the render_openscad tool with your code to "
    "produce the STL + preview PNG. Do not leave stubs."
)

# The same production-shaped multi-constraint prompt used across the Deepwen
# CAD closeout passes: a parametric mounting bracket exercising hulls, holes,
# and named-variable dimensioning in one request.
CAD_PROMPT = (
    "Design a parametric wall-mount bracket for a small electronics enclosure: "
    "80mm x 50mm footprint, 4mm wall thickness, rounded corners (5mm radius), "
    "four M3 counterbored mounting holes near the corners (3.2mm through-hole, "
    "6mm x 3mm counterbore), and a center cutout for cable routing. All dimensions "
    "must be named variables at the top of the file."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "render_openscad",
            "description": "Render OpenSCAD source code to an STL + preview PNG.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Complete OpenSCAD source"},
                    "resolution": {"type": "integer", "description": "PNG resolution"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "render_mesh",
            "description": "Render an existing mesh file to PNG and report bounding box + watertightness.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mesh_path": {"type": "string", "description": "Path to the mesh file"},
                },
                "required": ["mesh_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "convert_cad",
            "description": "Convert a mesh between formats (stl/3mf/obj/ply).",
            "parameters": {
                "type": "object",
                "properties": {
                    "input_path": {"type": "string"},
                    "to_format": {"type": "string"},
                },
                "required": ["input_path", "to_format"],
            },
        },
    },
]

_WORKSPACE_CACHE: dict[str, dict] | None = None


def _load_workspaces() -> dict[str, dict]:
    global _WORKSPACE_CACHE
    if _WORKSPACE_CACHE is None:
        cfg = yaml.safe_load((REPO_ROOT / "config" / "portal.yaml").read_text())
        _WORKSPACE_CACHE = {
            k: v for k, v in cfg.get("workspaces", {}).items() if isinstance(v, dict)
        }
    return _WORKSPACE_CACHE


def resolve_workspace(workspace_id: str) -> dict[str, Any]:
    ws = _load_workspaces().get(workspace_id)
    if not ws:
        raise SystemExit(f"Unknown workspace: {workspace_id}")
    return ws


@dataclass
class TrialResult:
    trial: int
    first_attempt_converged: bool
    stl_valid: bool = False
    watertight: bool = False
    used_retry: bool = False
    retry_converged: bool = False
    retry_stl_valid: bool = False
    retry_watertight: bool = False
    error: str | None = None
    latency_s: float = 0.0


def _call_model(
    model: str, tool_choice: str | None, messages: list[dict[str, Any]], client: httpx.Client
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "tools": TOOLS,
        "stream": False,
        "temperature": 0.2,
    }
    if tool_choice:
        body["tool_choice"] = tool_choice
    r = client.post(f"{OLLAMA_URL}/v1/chat/completions", json=body, timeout=GEN_TIMEOUT_S)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]


def _extract_render_openscad_call(msg: dict[str, Any]) -> dict[str, Any] | None:
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function", {})
        if fn.get("name") == "render_openscad":
            raw_args = fn.get("arguments", {})
            return raw_args if isinstance(raw_args, dict) else json.loads(raw_args or "{}")
    return None


def _score_openscad_call(args: dict[str, Any], client: httpx.Client) -> tuple[bool, bool]:
    """Dispatch a render_openscad call for real; return (stl_valid, watertight)."""
    code = args.get("code", "")
    if not isinstance(code, str) or not code:
        return False, False
    r = client.post(
        f"{CAD_MCP_URL}/tools/render_openscad",
        json={"arguments": {"code": code}},
        timeout=TOOL_TIMEOUT_S,
    )
    r.raise_for_status()
    result = r.json()
    stl_path = result.get("stl_path")
    if result.get("error") or not stl_path:
        return False, False
    r2 = client.post(
        f"{CAD_MCP_URL}/tools/render_mesh",
        json={"arguments": {"mesh_path": stl_path}},
        timeout=TOOL_TIMEOUT_S,
    )
    r2.raise_for_status()
    mesh_result = r2.json()
    if mesh_result.get("error"):
        return True, False
    return True, bool(mesh_result.get("watertight", False))


def run_trial(
    trial: int, model: str, tool_choice: str | None, with_retry: bool, client: httpx.Client
) -> TrialResult:
    t0 = time.time()
    messages = [
        {"role": "system", "content": CAD_SYSTEM_PROMPT},
        {"role": "user", "content": CAD_PROMPT},
    ]
    res = TrialResult(trial=trial, first_attempt_converged=False)
    try:
        msg = _call_model(model, tool_choice, messages, client)
        call_args = _extract_render_openscad_call(msg)
        if call_args is not None:
            res.first_attempt_converged = True
            res.stl_valid, res.watertight = _score_openscad_call(call_args, client)
        elif with_retry:
            res.used_retry = True
            messages.append({"role": "assistant", "content": msg.get("content") or ""})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "You did not call render_openscad. Write the complete OpenSCAD "
                        "source now and call render_openscad with it — do not just "
                        "describe the design."
                    ),
                }
            )
            msg2 = _call_model(model, tool_choice, messages, client)
            call_args2 = _extract_render_openscad_call(msg2)
            if call_args2 is not None:
                res.retry_converged = True
                res.retry_stl_valid, res.retry_watertight = _score_openscad_call(call_args2, client)
    except Exception as e:
        res.error = f"{type(e).__name__}: {e}"
    res.latency_s = round(time.time() - t0, 1)
    return res


def unload_model(model: str, client: httpx.Client) -> None:
    import contextlib

    with contextlib.suppress(Exception):
        client.post(
            f"{OLLAMA_URL}/api/generate", json={"model": model, "keep_alive": 0}, timeout=30.0
        )


def run_arm(
    label: str, workspace_id: str, trials: int, with_retry: bool, client: httpx.Client
) -> list[TrialResult]:
    ws = resolve_workspace(workspace_id)
    model = ws["model_hint"]
    tool_choice = ws.get("tool_choice")
    print(f"== {label}: {workspace_id} ({model}, tool_choice={tool_choice}) ==")
    results = []
    for i in range(trials):
        res = run_trial(i + 1, model, tool_choice, with_retry, client)
        results.append(res)
        print(
            f"    [{i + 1}/{trials}] converged={res.first_attempt_converged} "
            f"stl_valid={res.stl_valid} watertight={res.watertight} "
            f"retry_converged={res.retry_converged if res.used_retry else '-'} "
            f"latency={res.latency_s}s{' ERROR:' + res.error if res.error else ''}"
        )
    unload_model(model, client)
    return results


def summarize(results: list[TrialResult]) -> dict[str, Any]:
    n = len(results) or 1
    converged = sum(1 for r in results if r.first_attempt_converged)
    stl_valid = sum(1 for r in results if r.stl_valid)
    watertight = sum(1 for r in results if r.watertight)
    retried = [r for r in results if r.used_retry]
    retry_converged = sum(1 for r in retried if r.retry_converged)
    with_retry_converged = converged + retry_converged
    return {
        "n": len(results),
        "first_attempt_convergence_rate": round(converged / n, 2),
        "stl_valid_of_converged": round(stl_valid / converged, 2) if converged else 0.0,
        "watertight_of_stl_valid": round(watertight / stl_valid, 2) if stl_valid else 0.0,
        "with_1_retry_convergence_rate": round(with_retry_converged / n, 2),
        "errors": sum(1 for r in results if r.error),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="CAD tool-call convergence probe")
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--candidate", required=True, help="Candidate workspace id")
    ap.add_argument("--incumbent", required=True, help="Incumbent workspace id")
    ap.add_argument(
        "--with-retry", action="store_true", help="Also score a bounded 1-retry/nudge policy"
    )
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = Path(args.output) if args.output else RESULTS_DIR / f"cad_probe_{ts}.json"

    with httpx.Client() as client:
        candidate_results = run_arm(
            "Candidate", args.candidate, args.trials, args.with_retry, client
        )
        incumbent_results = run_arm(
            "Incumbent", args.incumbent, args.trials, args.with_retry, client
        )

    candidate_summary = summarize(candidate_results)
    incumbent_summary = summarize(incumbent_results)

    payload = {
        "generated_at": ts,
        "candidate": args.candidate,
        "incumbent": args.incumbent,
        "trials": args.trials,
        "with_retry": args.with_retry,
        "candidate_summary": candidate_summary,
        "incumbent_summary": incumbent_summary,
        "candidate_results": [asdict(r) for r in candidate_results],
        "incumbent_results": [asdict(r) for r in incumbent_results],
    }
    out_path.write_text(json.dumps(payload, indent=2))

    print()
    print("=" * 80)
    print(f"Candidate ({args.candidate}): {candidate_summary}")
    print(f"Incumbent ({args.incumbent}): {incumbent_summary}")
    print(f"Results: {out_path}")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
