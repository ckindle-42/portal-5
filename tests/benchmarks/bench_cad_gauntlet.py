#!/usr/bin/env python3
"""TASK_CAD_MODULE_OVERHAUL_V1 Phase 8 gauntlet — real tool loop, all arms, same rubric.

Drives each arm's actual model through Ollama's /v1/chat/completions with the
arm's real tool schemas, executing tool calls for real against the live CAD MCP
(:8926) and sandbox MCP (:8914) — not a fake backend. Scores each task per the
task file's rubric: correct tool called, STL compiles, mesh watertight, bbox
roughly matches the request, completes <120s, and for generate_scad tasks
whether the self-correction loop engaged/recovered (attempts).

Sequential, single-slot: one arm fully finishes (and unloads) before the next
starts. Smallest-model-first load order.

Per-turn cutoff is inactivity-based (streaming + httpx read-timeout), not a
blind elapsed-time timer — a slower-but-actively-generating model (e.g. the
dense challenger, which is known to run higher latency per task than the MoE
arms) is never killed just for taking longer; only genuine stream silence is.
`under_120s` in the results is a recorded data point, not a pass/fail gate.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import time
import urllib.request
from pathlib import Path
from typing import Any

import httpx
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "tests" / "benchmarks" / "results"
OLLAMA_URL = "http://localhost:11434"
CAD_MCP = "http://localhost:8926"
SANDBOX_MCP = "http://localhost:8914"
# Event-driven, not a blind elapsed-time timer: httpx's `read` timeout only
# fires on true silence between chunks on the wire. A slower-but-actively-
# generating model (e.g. the dense challenger) never hits this as long as
# tokens keep arriving; only a genuinely stalled stream does. See
# feedback_uat_timer_vs_events (project memory) — event-driven waits over
# blind timers is a standing preference here.
INACTIVITY_TIMEOUT = 90
HARD_CAP_S = 1800  # sanity ceiling against a truly runaway/broken stream
MAX_TURNS = 4

TOOL_ROUTES = {
    "render_mesh": f"{CAD_MCP}/tools/render_mesh",
    "render_openscad": f"{CAD_MCP}/tools/render_openscad",
    "convert_cad": f"{CAD_MCP}/tools/convert_cad",
    "generate_scad": f"{CAD_MCP}/tools/generate_scad",
    "execute_python": f"{SANDBOX_MCP}/tools/execute_python",
}


def _load_manifest_schemas() -> dict[str, dict]:
    schemas: dict[str, dict] = {}
    for name in ("cad_render_mcp", "code_sandbox_mcp"):
        p = REPO_ROOT / "config" / "inference" / f"tools_manifest_{name}.json"
        if not p.exists():
            continue
        for entry in json.loads(p.read_text()):
            schemas[entry["name"]] = {
                "type": "function",
                "function": {
                    "name": entry["name"],
                    "description": entry["description"],
                    "parameters": entry["parameters"],
                },
            }
    return schemas


SCHEMAS = _load_manifest_schemas()


def _load_workspace(ws_id: str) -> dict:
    cfg = yaml.safe_load((REPO_ROOT / "config" / "portal.yaml").read_text())
    return cfg["workspaces"][ws_id]


TASKS = [
    {
        "id": "t1_enclosure",
        "target_tool": "generate_scad",
        "applies_to": {"current", "dense", "moe"},
        "prompt": (
            "Design a parametric sensor enclosure using the generate_scad tool: "
            "60x40x25mm outer box, 2mm wall thickness (hollow), four M3 corner "
            "standoffs inside for mounting a PCB, and a 1.5mm lid lip around the "
            "top opening. Use the generate_scad Tier-A feature JSON — describe "
            "features by face+anchor+offset, do not compute coordinates yourself. "
            "Call the tool and report the result."
        ),
        "expect_bbox": (60, 40, 25),
    },
    {
        "id": "t2_grommet_plate",
        "target_tool": "generate_scad",
        "applies_to": {"current", "dense", "moe"},
        "prompt": (
            "Design a cable grommet plate using the generate_scad tool: "
            "80x30x4mm flat plate with three evenly-spaced 10mm diameter holes "
            "through the face, each with a 1mm chamfer. Use the generate_scad "
            "Tier-A feature JSON (holes positioned by face+anchor+offset, "
            "pattern for the even spacing). Call the tool and report the result."
        ),
        "expect_bbox": (80, 30, 4),
    },
    {
        "id": "t3_bracket",
        "target_tool": "render_openscad",
        "applies_to": {"prior", "current", "dense", "moe"},
        "prompt": (
            "Write complete OpenSCAD source for a 20x10x5mm rectangular bracket "
            "with two M3 (3.2mm) through-holes, each 5mm from an end along the "
            "long axis, centered on the width. Call render_openscad with the code "
            "and report the result."
        ),
        "expect_bbox": (20, 10, 5),
    },
    {
        "id": "t4_spur_gear",
        "target_tool": "render_openscad",
        "applies_to": {"prior", "current", "dense", "moe"},
        "prompt": (
            "Write complete OpenSCAD source for a parametric spur gear: 12 teeth, "
            "module 2 (pitch diameter 24mm), 8mm face width, 5mm center bore. "
            "Call render_openscad with the code and report the result."
        ),
        "expect_bbox": None,
    },
    {
        "id": "t5_gyroid_panel",
        "target_tool": "execute_python",
        "applies_to": {"prior", "current", "dense", "moe"},
        "prompt": (
            "Using Python with trimesh in execute_python, procedurally generate a "
            "40x40x5mm gyroid infill panel with a ~3mm unit cell, suitable for FDM "
            "printing (must be a real watertight solid, not just a surface). "
            "Export it to /tmp/gyroid.stl inside the sandbox and print whether it "
            "loaded as watertight with trimesh, plus its volume and bounding box."
        ),
        "expect_bbox": (40, 40, 5),
    },
]

ARMS = [
    {
        "key": "moe",
        "label": "could-be-MoE",
        "workspace": "bench-moecad",
    },
    {
        "key": "dense",
        "label": "could-be-dense",
        "workspace": "bench-qwen36-cad",
    },
    {
        "key": "prior",
        "label": "what-was (prior harness)",
        "workspace": "bench-cad-prior",
    },
    {
        "key": "current",
        "label": "what-is (current incumbent)",
        "workspace": "auto-cad",
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


def stream_chat_completion(payload: dict) -> dict:
    """POST /v1/chat/completions with stream:true, returning the assembled message.

    Uses httpx's per-read timeout as the cutoff: it only fires when no bytes
    arrive on the wire for INACTIVITY_TIMEOUT seconds. A model that is slower
    overall but keeps emitting tokens never trips it — only genuine silence
    (a hung backend, a dropped connection) does. HARD_CAP_S is just a sanity
    ceiling against a truly runaway stream, not the primary cutoff.
    """
    stream_payload = {**payload, "stream": True}
    content_parts: list[str] = []
    tool_calls_acc: dict[int, dict] = {}
    timeout = httpx.Timeout(30.0, read=INACTIVITY_TIMEOUT)
    t_start = time.monotonic()
    with (
        httpx.Client(timeout=timeout) as client,
        client.stream("POST", f"{OLLAMA_URL}/v1/chat/completions", json=stream_payload) as resp,
    ):
        resp.raise_for_status()
        for line in resp.iter_lines():
            if time.monotonic() - t_start > HARD_CAP_S:
                raise TimeoutError(f"hard cap {HARD_CAP_S}s exceeded (stream still active)")
            if not line or not line.startswith("data:"):
                continue
            data_str = line[len("data:") :].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            choice = (chunk.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            if delta.get("content"):
                content_parts.append(delta["content"])
            for tc in delta.get("tool_calls") or []:
                idx = tc.get("index", 0)
                entry = tool_calls_acc.setdefault(
                    idx,
                    {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
                )
                if tc.get("id"):
                    entry["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    entry["function"]["name"] = fn["name"]
                if fn.get("arguments"):
                    entry["function"]["arguments"] += fn["arguments"]
    message: dict[str, Any] = {"role": "assistant", "content": "".join(content_parts) or None}
    if tool_calls_acc:
        message["tool_calls"] = [tool_calls_acc[i] for i in sorted(tool_calls_acc)]
    return message


def execute_tool(name: str, args: dict) -> dict:
    route = TOOL_ROUTES.get(name)
    if not route:
        return {"error": f"unknown tool {name}"}
    try:
        resp = httpx.post(route, json={"arguments": args}, timeout=180)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def _bbox_of(result: dict) -> tuple[float, float, float] | None:
    bb = result.get("bounding_box") or (result.get("validation") or {}).get("bounding_box")
    if isinstance(bb, dict):
        try:
            return (float(bb["x"]), float(bb["y"]), float(bb["z"]))
        except Exception:
            return None
    if isinstance(bb, list) and len(bb) == 3:
        return tuple(float(v) for v in bb)
    return None


def _bbox_sane(got, want) -> bool | None:
    if not got or not want:
        return None
    g = sorted(got)
    w = sorted(want)
    return all(abs(a - b) <= max(0.3 * b, 3.0) for a, b in zip(g, w, strict=False))


def run_task(workspace_id: str, ws_cfg: dict, task: dict) -> dict:
    tools_available = [t for t in ws_cfg.get("tools", []) if t in SCHEMAS]
    tool_schemas = [SCHEMAS[t] for t in tools_available]
    tool_choice = ws_cfg.get("tool_choice", "auto")

    messages: list[dict[str, Any]] = []
    sys_prompt = ws_cfg.get("system_prompt_append")
    if sys_prompt:
        messages.append({"role": "system", "content": sys_prompt})
    messages.append({"role": "user", "content": task["prompt"]})

    model = ws_cfg["model_hint"]
    t0 = time.monotonic()
    tool_calls_made: list[dict] = []
    called_target = False
    last_result: dict | None = None

    for _turn in range(MAX_TURNS):
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "tools": tool_schemas,
            "tool_choice": tool_choice if tool_choice in ("auto", "required", "none") else "auto",
            "temperature": ws_cfg.get("temperature", 0.2),
            "top_p": ws_cfg.get("top_p", 0.9),
            "max_tokens": ws_cfg.get("predict_limit", 4096),
        }
        # Pass the workspace's think setting through verbatim when declared —
        # otherwise a reasoning-capable model's thinking-block time gets
        # counted as tool-use latency, confounding the comparison (see
        # auto-council's documented think:false precedent for this model).
        if "think" in ws_cfg:
            payload["think"] = ws_cfg["think"]
        try:
            msg = stream_chat_completion(payload)
        except Exception as e:
            return {
                "task": task["id"],
                "error": f"chat call failed: {e}",
                "elapsed_s": round(time.monotonic() - t0, 1),
            }
        tcs = msg.get("tool_calls") or []
        if not tcs:
            break
        messages.append(msg)
        for tc in tcs:
            fn = tc.get("function", {})
            fn_name = fn.get("name", "")
            try:
                fn_args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                fn_args = {}
            result = execute_tool(fn_name, fn_args)
            tool_calls_made.append({"tool": fn_name, "args": fn_args, "result": result})
            if fn_name == task["target_tool"]:
                called_target = True
                last_result = result
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": json.dumps(result)[:6000],
                }
            )

    elapsed = round(time.monotonic() - t0, 1)

    watertight = None
    printable = None
    problems: list[str] = []
    attempts = None
    bbox = None
    if last_result is not None:
        val = last_result.get("validation") or last_result
        watertight = val.get("watertight")
        printable = val.get("printable")
        problems = val.get("problems") or []
        attempts = last_result.get("attempts")
        bbox = _bbox_of(last_result)

    return {
        "task": task["id"],
        "target_tool": task["target_tool"],
        "called_target_tool": called_target,
        "tool_calls": tool_calls_made,
        "watertight": watertight,
        "printable": printable,
        "problems": problems,
        "attempts": attempts,
        "bbox": bbox,
        "bbox_sane": _bbox_sane(bbox, task.get("expect_bbox")),
        "last_result": last_result,
        "elapsed_s": elapsed,
        "under_120s": elapsed < 120,
        "final_content": (
            messages[-1].get("content") if messages and not tool_calls_made else None
        ),
    }


def run_arm(arm: dict) -> dict:
    ws_cfg = _load_workspace(arm["workspace"])
    model = ws_cfg["model_hint"]
    tasks = [t for t in TASKS if arm["key"] in t["applies_to"]]
    print(f"\n=== Arm: {arm['label']} ({arm['workspace']} / {model}) — {len(tasks)} task(s) ===")
    results = []
    for t in tasks:
        print(f"  [{t['id']}] running...", flush=True)
        r = run_task(arm["workspace"], ws_cfg, t)
        results.append(r)
        print(
            f"    called_target={r.get('called_target_tool')} watertight={r.get('watertight')} "
            f"attempts={r.get('attempts')} elapsed={r.get('elapsed_s')}s"
        )
    unload(model)
    return {
        "arm": arm["key"],
        "label": arm["label"],
        "workspace": arm["workspace"],
        "model": model,
        "results": results,
    }


def render_matrix(all_results: list[dict]) -> str:
    lines = ["# CAD Overhaul Phase 8 Gauntlet — what-was / what-is / could-be matrix\n"]
    lines.append(f"Generated: {_dt.datetime.now(_dt.UTC).isoformat()}\n")
    by_task: dict[str, dict[str, dict]] = {}
    for arm_res in all_results:
        for r in arm_res["results"]:
            by_task.setdefault(r["task"], {})[arm_res["arm"]] = r
    header = ["task"] + [a["label"] for a in ARMS]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * len(header))
    for t in TASKS:
        row = [t["id"]]
        for a in ARMS:
            r = by_task.get(t["id"], {}).get(a["key"])
            if r is None:
                row.append("N/A (tool absent)")
            elif r.get("error"):
                row.append(f"ERROR: {r['error'][:40]}")
            else:
                mark = "PASS" if r.get("called_target_tool") and r.get("watertight") else "FAIL"
                extra = f" attempts={r.get('attempts')}" if r.get("attempts") is not None else ""
                row.append(f"{mark} ({r.get('elapsed_s')}s){extra}")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("\n## Per-arm detail\n")
    for arm_res in all_results:
        lines.append(f"### {arm_res['label']} — {arm_res['workspace']} ({arm_res['model']})\n")
        for r in arm_res["results"]:
            lines.append(
                f"- `{r['task']}`: {json.dumps({k: v for k, v in r.items() if k != 'final_content'})}"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="CAD overhaul Phase 8 gauntlet")
    ap.add_argument(
        "--arm", action="append", choices=[a["key"] for a in ARMS], help="Restrict to these arms"
    )
    args = ap.parse_args()

    arms = [a for a in ARMS if not args.arm or a["key"] in args.arm]
    stamp = _dt.datetime.now(_dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"cap_cad-overhaul_{stamp}.txt"
    json_path = RESULTS_DIR / f"cap_cad-overhaul_{stamp}.json"

    all_results: list[dict] = []
    for a in arms:
        all_results.append(run_arm(a))
        # Persist after every arm — a kill/crash mid-run keeps completed arms.
        json_path.write_text(json.dumps(all_results, indent=2, default=str))
        out_path.write_text(render_matrix(all_results))
        print(f"  [checkpoint] wrote {out_path.relative_to(REPO_ROOT)} through arm {a['key']}")

    print(f"\nWrote {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
