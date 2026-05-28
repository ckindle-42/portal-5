"""S3a: Workspace routing tests (Ollama backends only)."""
import asyncio
from tests.acceptance._common import (
    record,
    _assert_routing,
    _chat_with_model,
    _get_workspace_prompts,
)


async def run() -> None:
    WORKSPACE_PROMPTS = _get_workspace_prompts()
    """S3a: Workspace routing tests (Ollama backends only)."""
    print("\n━━━ S3a. WORKSPACE ROUTING (OLLAMA) ━━━")
    sec = "S3a"

    # Ollama-only workspaces (no MLX in routing chain)
    OLLAMA_WORKSPACES = [
        # Group 1: General — auto-video pins to granite4.1:8b (de96984);
        # auto-music pins to huihui_ai/qwen3.5-abliterated:9b
        # (TASK_TOOL_SUPPORT_AUDIT_V1 §A7). `auto` moved to S3b: its
        # workspace_routing is [mlx, security, coding, general] (MLX-first)
        # with mlx_model_hint=huihui-ai/Huihui-Qwen3.5-9B-abliterated-mlx-4bit.
        ("Ollama general", ["auto-video", "auto-music"]),
        # Group 2: Security (baronllm, lily-cybersecurity, xploiter)
        ("Ollama security", ["auto-security", "auto-redteam", "auto-blueteam"]),
        # auto-documents moved to S3b (now [mlx, coding, general] after T-08)
    ]

    test_num = 1

    for group_name, workspaces in OLLAMA_WORKSPACES:
        print(f"\n  ── {group_name} ({len(workspaces)} workspaces) ──")

        for ws_id in workspaces:
            if ws_id not in WORKSPACE_PROMPTS:
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

            route_status, route_detail = await _assert_routing(
                sec, tid, ws_id, model
            )
            if found and route_status == "match":
                record(
                    sec, tid, f"Workspace {ws_id}", "PASS",
                    f"signals: {found[:3]} | {route_detail}",
                    t0=t0,
                )
            elif found and route_status == "mismatch":
                record(
                    sec, tid, f"Workspace {ws_id}", "WARN",
                    f"signals OK but {route_detail}",
                    t0=t0,
                )
            elif found:
                record(
                    sec, tid, f"Workspace {ws_id}", "PASS",
                    f"signals: {found[:3]} | {route_detail}",
                    t0=t0,
                )
            else:
                record(
                    sec, tid, f"Workspace {ws_id}", "WARN",
                    f"no signals in: {response[:80]} | {route_detail}",
                    t0=t0,
                )

            test_num += 1
            await asyncio.sleep(0.5)

        await asyncio.sleep(2)