#!/usr/bin/env python3
"""CAD gauntlet v2 — tool-agnostic, spec-graded (TASK_CAD_ARM_REDEVELOP_V1).

What changed from v1 (bench_cad_gauntlet.py, kept as the historical record):
  * Prompts describe the PART, never the tool. Each arm uses whatever tools its
    workspace config (config/portal.yaml) gives it, so a toolset change is
    measured, not presupposed.
  * Grading is sealed and spec-derived: tests/benchmarks/cad_grader.py reads the
    artifact the arm actually produced (latest stl_path from any CAD tool result)
    and checks validity, bbox, volume and genus against oracle truth. Tool
    self-reports are never scored.
  * Repeats (--reps, default 3) — single runs hid a 4/8 convergence rate before.
  * Every tool call carries a unique request_id per task run, which the CAD MCP
    uses as its build123d session handle (one run = one isolated CAD session).

Usage:
  uv run python tests/benchmarks/bench_cad_gauntlet_v2.py \\
      --arm b0=auto-cad --arm prior=bench-cad-prior --reps 3 --label B0
Results: tests/benchmarks/results/cad_gauntlet_v2_<label>_<ts>.{json,md}
Resumable: --resume <json> skips (arm, task, rep) cells already recorded.
Set CAD_GAUNTLET_TRACE_DIR=<dir> to write one full transcript per cell. Each cell also
records `ended` (final_text | turn_cap | error) and the model's last text.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tests.benchmarks.cad_grader import grade_mesh  # noqa: E402

RESULTS_DIR = REPO_ROOT / "tests" / "benchmarks" / "results"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
# Container paths in tool results are under /workspace; on the host that is AI_OUTPUT_DIR.
CONTAINER_WS = "/workspace"
HOST_WS = Path(os.environ.get("AI_OUTPUT_DIR", str(Path.home() / "AI_Output")))
MAX_TURNS = int(os.environ.get("CAD_GAUNTLET_MAX_TURNS", "14"))
INACTIVITY_S = int(os.environ.get("CAD_GAUNTLET_INACTIVITY_S", "180"))
TOOL_TIMEOUT_S = 600

DELIVER = (
    " Units are millimetres. Deliver the finished part as a printable solid "
    "(STEP and/or STL) using your CAD tools, then state its overall dimensions."
)

TASKS: list[dict[str, str]] = [
    {
        "id": "plate_4holes",
        "prompt": "Design a flat mounting plate 80 x 50 x 5 mm with four 5 mm diameter through-holes, each hole centre 8 mm in from both adjacent edges."
        + DELIVER,
    },
    {
        "id": "grommet_plate",
        "prompt": "Design a cable grommet plate 80 x 30 x 4 mm with three 10 mm diameter through-holes along the long centreline, 25 mm apart centre-to-centre with the middle hole at the plate centre, each with a 1 mm chamfer on the top edge."
        + DELIVER,
    },
    {
        "id": "enclosure",
        "prompt": "Design an open-top electronics enclosure: outer 60 x 40 x 25 mm, 2 mm walls and 2 mm floor, open top. Inside, on the floor, four cylindrical PCB standoffs 6 mm diameter and 6 mm tall, centred 7 mm in from the inner wall corners in X and Y (i.e. at +/-23, +/-13 from centre), each with a 2.5 mm pilot hole 5 mm deep from its top."
        + DELIVER,
    },
    {
        "id": "l_bracket",
        "prompt": "Design a 90 degree L-bracket from 3 mm plate, 40 mm wide: a horizontal leg 30 mm long and a vertical leg 25 mm tall (outer dimensions), with a 3 mm radius fillet on the inside corner. Two 4.5 mm through-holes in each leg, 24 mm apart, centred across the width; horizontal-leg holes 18 mm from the outer back face, vertical-leg holes 15 mm above the bottom."
        + DELIVER,
    },
    {
        "id": "flanged_bushing",
        "prompt": "Design a flanged bushing: flange 30 mm outer diameter and 3 mm thick, body 16 mm outer diameter, overall length 20 mm including the flange, with a 10 mm through-bore."
        + DELIVER,
    },
    {
        "id": "countersunk_plate",
        "prompt": "Design a 60 x 30 x 6 mm plate with two holes for M4 countersunk screws on the long centreline, 40 mm apart and symmetric about the centre: 4.5 mm through-hole with a 90 degree countersink to 9 mm diameter at the top face."
        + DELIVER,
    },
    {
        "id": "hex_standoff",
        "prompt": "Design a hexagonal standoff 8 mm across flats and 15 mm long with a 3.3 mm through-bore along its axis."
        + DELIVER,
    },
    {
        "id": "spur_gear",
        "prompt": "Design a spur gear: 12 teeth, module 2 (24 mm pitch diameter), 20 degree pressure angle involute teeth, 8 mm face width, 5 mm centre bore."
        + DELIVER,
    },
]


def _fleet_ports() -> dict[str, int]:
    cfg = yaml.safe_load((REPO_ROOT / "config" / "portal.yaml").read_text())
    return {s["id"]: s["port"] for s in cfg.get("mcp_fleet", []) if s.get("port")}


# manifest file stem -> fleet id that serves it
_MANIFEST_SERVER = {"cad_render_mcp": "cad_render", "code_sandbox_mcp": "execution"}


def load_tool_routes() -> tuple[dict[str, dict], dict[str, str]]:
    ports = _fleet_ports()
    schemas: dict[str, dict] = {}
    routes: dict[str, str] = {}
    for stem, server in _MANIFEST_SERVER.items():
        p = REPO_ROOT / "config" / "inference" / f"tools_manifest_{stem}.json"
        if not p.exists() or server not in ports:
            continue
        for entry in json.loads(p.read_text()):
            e = entry["function"] if isinstance(entry.get("function"), dict) else entry
            schemas[e["name"]] = {
                "type": "function",
                "function": {
                    "name": e["name"],
                    "description": e.get("description", ""),
                    "parameters": e.get("parameters", {}),
                },
            }
            routes[e["name"]] = f"http://localhost:{ports[server]}/tools/{e['name']}"
    return schemas, routes


def load_workspace(ws_id: str) -> dict:
    cfg = yaml.safe_load((REPO_ROOT / "config" / "portal.yaml").read_text())
    return cfg["workspaces"][ws_id]


def unload(model: str) -> None:
    try:
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=json.dumps({"model": model, "keep_alive": 0}).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=15).read()  # noqa: S310 — fixed localhost URL
    except Exception:  # noqa: BLE001
        pass


async def _stream_chat_async(payload: dict) -> dict:
    """Chat through the SAME transport production uses for Ollama.

    Raw POST /v1/chat/completions silently drops `think`, top_k, min_p and
    repeat_penalty (KNOWN_LIMITATIONS P5-OLLAMA-V1-SAMPLING-001), so a thinking model
    ran with thinking on and every arm ran off its configured sampling. The pipeline
    fixes this with OllamaNativeTransport (answers /v1 from native /api/chat); using it
    here keeps the gauntlet production-like. Per-read inactivity timeout as before.
    """
    from portal.platform.inference.ollama_native import OllamaNativeTransport

    parts: list[str] = []
    acc: dict[int, dict] = {}
    transport = OllamaNativeTransport(httpx.AsyncHTTPTransport(), lambda _base: True)
    timeout = httpx.Timeout(30.0, read=INACTIVITY_S)
    async with (
        httpx.AsyncClient(transport=transport, timeout=timeout) as c,
        c.stream(
            "POST", f"{OLLAMA_URL}/v1/chat/completions", json={**payload, "stream": True}
        ) as resp,
    ):
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            delta = ((chunk.get("choices") or [{}])[0]).get("delta") or {}
            if delta.get("content"):
                parts.append(delta["content"])
            for tc in delta.get("tool_calls") or []:
                e = acc.setdefault(
                    tc.get("index", 0),
                    {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
                )
                e["id"] = tc.get("id") or e["id"]
                fn = tc.get("function") or {}
                e["function"]["name"] = fn.get("name") or e["function"]["name"]
                e["function"]["arguments"] += fn.get("arguments") or ""
    msg: dict[str, Any] = {"role": "assistant", "content": "".join(parts) or None}
    if acc:
        msg["tool_calls"] = [acc[i] for i in sorted(acc)]
    return msg


def stream_chat(payload: dict) -> dict:
    return asyncio.run(_stream_chat_async(payload))


def host_path(p: str | None) -> Path | None:
    if not p:
        return None
    if p.startswith(CONTAINER_WS + "/"):
        return HOST_WS / p[len(CONTAINER_WS) + 1 :]
    return Path(p)


def _write_trace(task_id: str, rid: str, ended: str, messages: list[dict[str, Any]]) -> None:
    """Full transcript (tool results clipped) so a failure can be read, not guessed at."""
    trace_dir = os.environ.get("CAD_GAUNTLET_TRACE_DIR")
    if not trace_dir:
        return
    clipped = [
        {**m, "content": (m.get("content") or "")[:3000]} if m.get("role") == "tool" else m
        for m in messages
    ]
    Path(trace_dir).mkdir(parents=True, exist_ok=True)
    (Path(trace_dir) / f"{task_id}_{rid}.json").write_text(
        json.dumps({"task": task_id, "ended": ended, "messages": clipped}, indent=1)
    )


def _build_payload(
    ws_cfg: dict, messages: list[dict[str, Any]], tools: list[dict], tc: str, have_artifact: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": ws_cfg["model_hint"],
        "messages": messages,
        "tools": tools,
        # tool_choice=required is only meaningful until a deliverable exists;
        # after that the model must be allowed to answer in prose.
        "tool_choice": "auto" if (have_artifact or tc not in ("auto", "required")) else tc,
        "temperature": ws_cfg.get("temperature", 0.2),
        "top_p": ws_cfg.get("top_p", 0.9),
        "max_tokens": ws_cfg.get("predict_limit", 8192),
    }
    if "think" in ws_cfg:
        payload["think"] = ws_cfg["think"]
    for key in ("top_k", "min_p", "repeat_penalty", "presence_penalty"):
        if ws_cfg.get(key) is not None:
            payload[key] = ws_cfg[key]
    return payload


def run_one(ws_cfg: dict, task: dict, schemas: dict, routes: dict) -> dict:
    tools = [schemas[t] for t in ws_cfg.get("tools", []) if t in schemas]
    tc = ws_cfg.get("tool_choice", "auto")
    messages: list[dict[str, Any]] = []
    if ws_cfg.get("system_prompt_append"):
        messages.append({"role": "system", "content": ws_cfg["system_prompt_append"]})
    messages.append({"role": "user", "content": task["prompt"]})
    rid = f"gauntlet-{uuid.uuid4().hex[:12]}"
    calls: list[dict] = []
    artifact: str | None = None
    t0 = time.monotonic()
    error = None
    ended = "turn_cap"
    last_text = ""
    for turn in range(MAX_TURNS):
        payload = _build_payload(ws_cfg, messages, tools, tc, bool(artifact))
        try:
            msg = stream_chat(payload)
        except Exception as e:  # noqa: BLE001
            error = f"chat failed on turn {turn}: {type(e).__name__}: {e}"
            ended = "error"
            break
        tcs = msg.get("tool_calls") or []
        if not tcs:
            ended = "final_text"
            last_text = (msg.get("content") or "")[:400]
            messages.append(msg)
            break
        messages.append(msg)
        for call in tcs:
            fn = call.get("function", {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            route = routes.get(name)
            if not route:
                result: dict[str, Any] = {"error": f"tool {name!r} not available"}
            else:
                try:
                    r = httpx.post(
                        route, json={"arguments": args, "request_id": rid}, timeout=TOOL_TIMEOUT_S
                    )
                    result = (
                        r.json()
                        if r.status_code == 200
                        else {"error": f"HTTP {r.status_code}", "detail": r.text[:300]}
                    )
                except Exception as e:  # noqa: BLE001
                    result = {"error": f"{type(e).__name__}: {e}"}
            if isinstance(result, dict) and result.get("stl_path"):
                artifact = result["stl_path"]
            calls.append(
                {
                    "tool": name,
                    "ok": isinstance(result, dict) and not result.get("error"),
                    "arg_chars": len(json.dumps(args)),
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "content": json.dumps(result)[:6000],
                }
            )
    grade = grade_mesh(task["id"], host_path(artifact))
    _write_trace(task["id"], rid, ended, messages)
    return {
        "task": task["id"],
        "request_id": rid,
        "elapsed_s": round(time.monotonic() - t0, 1),
        "turns": len([m for m in messages if m["role"] == "assistant"]),
        "tool_calls": calls,
        "error": error,
        "ended": ended,
        "last_text": last_text,
        **grade,
    }


def summarize(cells: list[dict]) -> dict:
    scores = [c["score"] for c in cells]
    return {
        "n": len(cells),
        "mean_score": round(statistics.mean(scores), 3) if scores else 0.0,
        "pass_rate": round(sum(c["verdict"] == "PASS" for c in cells) / len(cells), 3)
        if cells
        else 0.0,
        "validity_rate": round(
            sum(c["verdict"] in ("PASS", "WRONGSIZE") for c in cells) / len(cells), 3
        )
        if cells
        else 0.0,
        "median_s": round(statistics.median([c["elapsed_s"] for c in cells]), 1) if cells else None,
    }


def render_md(run: dict) -> str:
    lines = [
        f"# CAD gauntlet v2 — {run['label']}",
        "",
        f"Generated: {run['generated']}  ",
        f"Reps: {run['reps']}  Tasks: {len(TASKS)}",
        "",
        "| arm | workspace | model | mean score | PASS rate | validity | median s |",
        "|---|---|---|---|---|---|---|",
    ]
    for a in run["arms"]:
        s = a["summary"]
        lines.append(
            f"| {a['key']} | {a['workspace']} | `{a['model']}` | {s['mean_score']} | "
            f"{s['pass_rate']} | {s['validity_rate']} | {s['median_s']} |"
        )
    lines += [
        "",
        "## Per task (PASS count / reps)",
        "",
        "| task | " + " | ".join(a["key"] for a in run["arms"]) + " |",
        "|---|" + "---|" * len(run["arms"]),
    ]
    for t in TASKS:
        row = [t["id"]]
        for a in run["arms"]:
            cs = [c for c in a["cells"] if c["task"] == t["id"]]
            row.append(f"{sum(c['verdict'] == 'PASS' for c in cs)}/{len(cs)}")
        lines.append("| " + " | ".join(row) + " |")
    lines += [
        "",
        "Grader: tests/benchmarks/cad_grader.py (sealed, spec-derived; tool self-reports are not scored).",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", action="append", required=True, help="key=workspace_id (repeatable)")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--task", action="append", help="limit to task id(s)")
    ap.add_argument("--label", default="run")
    ap.add_argument("--resume", type=Path)
    ap.add_argument(
        "--override",
        action="append",
        default=[],
        metavar="KEY=JSON",
        help="merge JSON into an arm's workspace config (repeatable), "
        'e.g. moe={"model_hint": "tag", "think": false}',
    )
    args = ap.parse_args()

    schemas, routes = load_tool_routes()
    overrides = {k: json.loads(v) for k, v in (o.split("=", 1) for o in args.override)}
    tasks = [t for t in TASKS if not args.task or t["id"] in args.task]
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_json = args.resume or RESULTS_DIR / f"cad_gauntlet_v2_{args.label}_{ts}.json"
    run = (
        json.loads(out_json.read_text())
        if args.resume
        else {"label": args.label, "generated": ts, "reps": args.reps, "arms": []}
    )

    for spec in args.arm:
        key, ws_id = spec.split("=", 1)
        ws = {**load_workspace(ws_id), **overrides.get(key, {})}
        arm = next((a for a in run["arms"] if a["key"] == key), None)
        if arm is None:
            arm = {
                "key": key,
                "workspace": ws_id,
                "model": ws["model_hint"],
                "tool_choice": ws.get("tool_choice", "auto"),
                "think": ws.get("think"),
                "context_limit": ws.get("context_limit"),
                "tools": ws.get("tools", []),
                "cells": [],
            }
            run["arms"].append(arm)
        print(f"\n=== {key}: {ws_id} / {ws['model_hint']} ===", flush=True)
        for t in tasks:
            for rep in range(args.reps):
                if any(c["task"] == t["id"] and c.get("rep") == rep for c in arm["cells"]):
                    continue
                cell = run_one(ws, t, schemas, routes)
                cell["rep"] = rep
                arm["cells"].append(cell)
                print(
                    f"  {t['id']} rep{rep}: {cell['verdict']} score={cell['score']} {cell['elapsed_s']}s",
                    flush=True,
                )
                arm["summary"] = summarize(arm["cells"])
                out_json.write_text(json.dumps(run, indent=1))
        arm["summary"] = summarize(arm["cells"])
        unload(ws["model_hint"])
    out_json.write_text(json.dumps(run, indent=1))
    out_json.with_suffix(".md").write_text(render_md(run))
    print(f"\nwrote {out_json} and .md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
