"""S3a: Workspace routing tests — all production workspaces (Ollama-only).

Covers the 21 production workspaces: 20 auto-* + tools-specialist. bench-*
workspaces are intentionally excluded — full-catalog routing and TPS coverage
is the job of tests/benchmarks/bench_tps.py (--mode pipeline), not the
acceptance suite. Acceptance asserts functional routing + a content-signal
sanity check per production lane.
"""

import asyncio
import time

from tests.acceptance._common import (
    _assert_routing,
    _chat_with_model,
    _get_workspace_prompts,
    record,
)


async def run() -> None:
    """S3a: Workspace routing tests — production workspaces (Ollama-only)."""
    WORKSPACE_PROMPTS = _get_workspace_prompts()
    print("\n━━━ S3a. WORKSPACE ROUTING (PRODUCTION, OLLAMA) ━━━")
    sec = "S3a"

    # All production workspaces route through Ollama (MLX inference retired
    # in 3a0c58e). Groups are for readability/ordering only.
    PRODUCTION_WORKSPACES = [
        ("General / daily", ["auto", "auto-daily", "auto-mistral", "auto-music", "auto-video"]),
        ("Coding / agentic", ["auto-coding", "auto-agentic", "auto-spl", "auto-documents"]),
        ("Security", ["auto-security", "auto-redteam", "auto-blueteam"]),
        (
            "Reasoning / analysis",
            ["auto-reasoning", "auto-research", "auto-data", "auto-compliance", "auto-math"],
        ),
        ("Creative / vision / audio", ["auto-creative", "auto-vision", "auto-audio"]),
        ("Tool calling", ["tools-specialist"]),
    ]

    test_num = 1

    for group_name, workspaces in PRODUCTION_WORKSPACES:
        print(f"\n  ── {group_name} ({len(workspaces)} workspaces) ──")

        for ws_id in workspaces:
            if ws_id not in WORKSPACE_PROMPTS:
                record(
                    sec,
                    f"S3a-{test_num:02d}",
                    f"Workspace {ws_id}",
                    "FAIL",
                    "no WORKSPACE_PROMPTS entry — add one to portal5_acceptance_v6.py",
                )
                test_num += 1
                continue

            prompt, signals = WORKSPACE_PROMPTS[ws_id]
            t0 = time.time()
            tid = f"S3a-{test_num:02d}"

            code, response, model, _route = await _chat_with_model(
                ws_id, prompt, max_tokens=300, timeout=180
            )

            if code != 200:
                record(
                    sec, tid, f"Workspace {ws_id}", "FAIL", f"HTTP {code}: {response[:80]}", t0=t0
                )
                test_num += 1
                continue

            response_lower = response.lower()
            found = [s for s in signals if s.lower() in response_lower]

            route_status, route_detail = await _assert_routing(sec, tid, ws_id, model)
            if found and route_status == "match":
                record(
                    sec,
                    tid,
                    f"Workspace {ws_id}",
                    "PASS",
                    f"signals: {found[:3]} | {route_detail}",
                    t0=t0,
                )
            elif found and route_status == "mismatch":
                record(
                    sec,
                    tid,
                    f"Workspace {ws_id}",
                    "WARN",
                    f"signals OK but {route_detail}",
                    t0=t0,
                )
            elif found:
                record(
                    sec,
                    tid,
                    f"Workspace {ws_id}",
                    "PASS",
                    f"signals: {found[:3]} | {route_detail}",
                    t0=t0,
                )
            else:
                record(
                    sec,
                    tid,
                    f"Workspace {ws_id}",
                    "WARN",
                    f"no signals in: {response[:80]} | {route_detail}",
                    t0=t0,
                )

            test_num += 1
            await asyncio.sleep(0.5)

        await asyncio.sleep(2)
