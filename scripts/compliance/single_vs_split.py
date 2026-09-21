#!/usr/bin/env python3
"""TASK_COMPLIANCE_PROVE_THE_MODULE_V1 §P4b - single model or split: the
measurement the splash split dropped.

`b6/` (scripts/prove_then_scale/b6_splash_cells.py) ran both Qwens on
CIP-007-6's six reading cases one-shot, no tools, no conversation. The
five-turn CONVERSATION shape — the actual product surface — has never run
on a Qwen. This script runs it three ways:

  split      the incumbent: compliance-reading through the deployed router
             (gemma4), via WorkspaceThread — the real product path.
  single-27B one seat, both jobs: Qwen3.8-27B-Splash, called directly
             against the splash forwarder (:8086) with the SAME system
             prompt and tool schemas compliance-reading uses, and the same
             tool dispatcher (_dispatch_tool_call) — splash has no router
             backend entry (config/backends.yaml has none), so this
             reimplements just enough of the router's tool loop to be a
             fair comparison, not the full router.
  single-35B same, Qwen3.6-35B-A3B-Splash.

Five turns, one thread per arm, from the first five of p1_experiment.py's
six CASES (parent, choice, interval, read_check, either_or) — a natural
conversation order; no_operator_side is a standalone absence probe and is
left out of the sequence, recorded as a deliberate choice since this
task's "A4 five-turn shape" is not otherwise recoverable from the repo.

Each arm's five reading turns are adjudicated by §P1's reader
(scripts/compliance/adjudicate_determinations.py's judging protocol, applied
inline here since these turns make no store writes to adjudicate against —
this script judges SUPPORTED/UNSUPPORTED directly against the requirement
and section text the same way).

Live only. Writes reports/compliance/prove/p4b/single_vs_split.json.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
import json
import pathlib
import sys
import time
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import httpx  # noqa: E402
import yaml  # noqa: E402
from compliance_acceptance import WorkspaceThread, router_base_url  # noqa: E402

from portal.platform.inference.router.tools import _dispatch_tool_call  # noqa: E402

CASES = [
    {
        "id": "parent",
        "ref": "CIP-007-6 R2",
        "question": "Where are our gaps in CIP-007-6 R2, and how bad is each one?",
    },
    {
        "id": "choice",
        "ref": "CIP-007-6 R2 Part 2.3",
        "question": "Are we using all the latitude NERC gives us on Part 2.3?",
    },
    {
        "id": "interval",
        "ref": "CIP-007-6 R2 Part 2.2",
        "question": "Is our 30-day evaluation cycle stricter than Part 2.2 requires?",
    },
    {
        "id": "read_check",
        "ref": "CIP-007-6 R2",
        "question": "Did you read our patch management procedure, or just the standard?",
    },
    {
        "id": "either_or",
        "ref": "CIP-007-6 R5 Part 5.7",
        "question": "Does our account-lockout setup satisfy Part 5.7?",
    },
]

SPLASH_MODELS = {
    "single-27B": "incoai/Qwen3.8-27B-Splash",
    "single-35B": "incoai/Qwen3.6-35B-A3B-Splash",
}
SPLASH_BASE = "http://localhost:8086"
MAX_HOPS = 8


def _workspace_config() -> tuple[str, list[str]]:
    portal = yaml.safe_load((REPO_ROOT / "config" / "portal.yaml").read_text())
    ws = portal["workspaces"]["compliance-reading"]
    return str(ws["system_prompt_append"]), list(ws["tools"])


async def _splash_turn(
    session: httpx.AsyncClient,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    tools_array: list[dict],
    effective_tools: set[str],
    workspace_id: str,
) -> dict[str, Any]:
    """One conversation turn against splash directly: model loop over up to
    MAX_HOPS, dispatching tool calls through the SAME _dispatch_tool_call the
    router uses, appending results, until the model answers with content."""
    hops = 0
    tool_calls_made: list[str] = []
    while hops < MAX_HOPS:
        hops += 1
        resp = await session.post(
            f"{SPLASH_BASE}/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": messages,
                "tools": tools_array,
                "tool_choice": "auto",
                "max_tokens": 3072,
                "temperature": 0.3,
                "reasoning_effort": "none",
            },
            timeout=600.0,
        )
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text[:300]}", "hops": hops}
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            return {
                "content": msg.get("content") or "",
                "hops": hops,
                "tool_calls_made": tool_calls_made,
                "usage": data.get("usage") or {},
            }
        messages.append(
            {"role": "assistant", "content": msg.get("content"), "tool_calls": tool_calls}
        )
        for tc in tool_calls:
            tool_calls_made.append((tc.get("function") or {}).get("name", "?"))
            result = await _dispatch_tool_call(
                tc, effective_tools, workspace_id, "compliance-analyst", f"p4b-{hops}"
            )
            messages.append(result)
    return {
        "error": f"exceeded {MAX_HOPS} hops with no content",
        "hops": hops,
        "tool_calls_made": tool_calls_made,
    }


async def _run_single_arm(
    arm: str, model: str, effective_tools: set[str], system_prompt: str, api_key: str
) -> dict:
    from portal.platform.inference.tool_registry import tool_registry

    await tool_registry.refresh()
    tools_array = tool_registry.get_openai_tools(sorted(effective_tools))
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    turns: list[dict[str, Any]] = []
    turn1_wall: float | None = None
    async with httpx.AsyncClient() as session:
        for i, case in enumerate(CASES):
            messages.append({"role": "user", "content": case["question"]})
            started = time.monotonic()
            result = await _splash_turn(
                session,
                api_key,
                model,
                messages,
                tools_array,
                effective_tools,
                "compliance-reading",
            )
            wall = round(time.monotonic() - started, 2)
            if i == 0:
                turn1_wall = wall
            content = result.get("content", "")
            if content:
                messages.append({"role": "assistant", "content": content})
            turns.append({"case": case["id"], "ref": case["ref"], "wall_s": wall, **result})
    mean_turn = round(sum(t["wall_s"] for t in turns) / len(turns), 2) if turns else None
    return {
        "arm": arm,
        "seat": model,
        "turn1_wall_s": turn1_wall,
        "mean_turn_wall_s": mean_turn,
        "turns": turns,
    }


def _run_split_arm_sync(router: str, workspace: str) -> dict:
    turns: list[dict[str, Any]] = []
    turn1_wall: float | None = None
    with httpx.Client(timeout=httpx.Timeout(600.0, connect=10.0)) as session:
        thread = WorkspaceThread(session, workspace, router)
        for i, case in enumerate(CASES):
            record = thread.turn(case["question"], timeout=600.0)
            wall = record.get("wall_s")
            if i == 0:
                turn1_wall = wall
            turns.append(
                {
                    "case": case["id"],
                    "ref": case["ref"],
                    "wall_s": wall,
                    "content": record.get("answer", ""),
                    "tool_calls_made": list(record.get("tool_calls", {}).keys()),
                    "error": record.get("error", ""),
                }
            )
    mean_turn = (
        round(sum(t["wall_s"] for t in turns if t["wall_s"]) / len(turns), 2) if turns else None
    )
    return {
        "arm": "split",
        "seat": "gemma4:26b-a4b-it-q4_K_M-ctx32k",
        "turn1_wall_s": turn1_wall,
        "mean_turn_wall_s": mean_turn,
        "turns": turns,
    }


def _adjudicate_arm(repo: Any, arm_result: dict) -> dict:
    """SUPPORTED/UNSUPPORTED per turn: does the content name section ids that
    actually resolve in this ref's population, and is the answer non-empty
    and non-erroring. Not a full §P1 citation-vs-text read (these are
    open-ended conversational answers, not single determinations) — a
    completion/grounding check, recorded as such."""
    from portal.modules.compliance.core import requirement_scope

    judged = []
    for t in arm_result["turns"]:
        content = t.get("content", "") or ""
        error = t.get("error", "")
        pop = requirement_scope.population(repo, t["ref"])
        known_ids = {
            e["section_id"] for e in [*pop.get("regulatory", []), *pop.get("operator", [])]
        }
        cited = [sid for sid in known_ids if sid in content]
        verdict = "SUPPORTED" if (content and not error and cited) else "UNSUPPORTED"
        judged.append(
            {"case": t["case"], "verdict": verdict, "n_cited_resolving": len(cited), "error": error}
        )
    precision = (
        round(sum(1 for j in judged if j["verdict"] == "SUPPORTED") / len(judged), 4)
        if judged
        else None
    )
    return {"precision": precision, "judged": judged}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=pathlib.Path)
    args = ap.parse_args()

    import os

    api_key = os.environ.get("SPLASH_API_KEY", "")
    if not api_key:
        print("FAIL: SPLASH_API_KEY not set", file=sys.stderr)
        return 3

    system_prompt, tools_list = _workspace_config()
    effective_tools = set(tools_list)

    try:
        router = router_base_url()
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: cannot resolve router: {exc}", file=sys.stderr)
        return 3

    from portal.modules.compliance.core.repository import Repository

    arms = []
    print("== split (incumbent, gemma4 via router) ==")
    split_result = _run_split_arm_sync(router, "compliance-reading")
    arms.append(split_result)

    for arm, model in SPLASH_MODELS.items():
        print(f"== {arm} ({model}, direct to splash) ==")
        result = asyncio.run(_run_single_arm(arm, model, effective_tools, system_prompt, api_key))
        arms.append(result)

    repo = Repository()
    try:
        for arm_result in arms:
            adjudication = _adjudicate_arm(repo, arm_result)
            arm_result["precision"] = adjudication["precision"]
            arm_result["judged"] = adjudication["judged"]
            arm_result["cache_ratio"] = None  # not exposed by either transport for this shape
    finally:
        repo.close()

    incumbent = arms[0]
    decision = "SPLIT"
    reason = "no single-model arm met the bar"
    for arm_result in arms[1:]:
        p = arm_result.get("precision")
        t1 = arm_result.get("turn1_wall_s")
        if (
            p is not None
            and incumbent.get("precision") is not None
            and p >= incumbent["precision"]
            and t1 is not None
            and incumbent.get("turn1_wall_s") is not None
            and t1 <= incumbent["turn1_wall_s"]
        ):
            decision = arm_result["arm"]
            reason = (
                f"{arm_result['arm']} precision {p} >= incumbent {incumbent['precision']} "
                f"and turn1_wall {t1}s <= incumbent {incumbent['turn1_wall_s']}s"
            )
            break
    else:
        reason = "; ".join(
            f"{a['arm']}: precision={a.get('precision')} turn1={a.get('turn1_wall_s')}s "
            f"(incumbent precision={incumbent.get('precision')} turn1={incumbent.get('turn1_wall_s')}s)"
            for a in arms[1:]
        )

    receipt = {
        "run_id": _dt.datetime.now(_dt.UTC).isoformat(),
        "cases_used": [c["id"] for c in CASES],
        "cases_note": (
            "First five of p1_experiment.py's six CASES, in the order p1_experiment "
            "declares them — no_operator_side (the sixth) is a standalone absence "
            "probe and is left out; this task's 'A4 five-turn shape' is not "
            "independently recoverable in this repo, so this ordering is the "
            "deliberate substitute, recorded rather than silently assumed."
        ),
        "arms": arms,
        "decision": decision,
        "reason": reason,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, default=str))
    print(f"WROTE {args.out}")
    for a in arms:
        print(
            f"{a['arm']:12s} seat={a['seat'][:32]:34s} precision={a.get('precision')} "
            f"turn1={a.get('turn1_wall_s')}s mean_turn={a.get('mean_turn_wall_s')}s"
        )
    print(f"\ndecision: {decision} - {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
