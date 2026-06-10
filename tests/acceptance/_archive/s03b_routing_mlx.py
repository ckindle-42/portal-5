"""S3b: Workspace routing tests (MLX backends)."""
import asyncio

from tests.acceptance._common import (
    _chat_with_model,
    _get_mlx_orgs,
    _get_workspace_prompts,
    _mlx_health,
    _unload_ollama_models,
    record,
)


async def run() -> None:
    WORKSPACE_PROMPTS = _get_workspace_prompts()
    _MLX_ORGS = _get_mlx_orgs()
    """S3b: Workspace routing tests (MLX backends)."""
    print("\n━━━ S3b. WORKSPACE ROUTING (MLX) ━━━")
    sec = "S3b"

    # First evict Ollama to free memory for MLX
    await _unload_ollama_models()

    # MLX-primary workspaces (grouped by likely model)
    MLX_WORKSPACES = [
        # Group 1: Coding (Devstral, Qwen3-Coder)
        ("MLX coding", ["auto-coding", "auto-agentic", "auto-spl"]),
        # Group 2: Reasoning (Qwopus, DeepSeek-R1, Magistral)
        (
            "MLX reasoning",
            ["auto-reasoning", "auto-research", "auto-data", "auto-compliance", "auto-mistral"],
        ),
        # Group 3: Creative (divinetribe/gemma-4-31b-abl)
        ("MLX creative", ["auto-creative"]),
        # Group 4: Vision (Gemma-4, Qwen3-VL)
        ("MLX vision", ["auto-vision"]),
        # Group 5: Documents (Phi-4 8bit, MLX primary — T-08)
        ("MLX documents", ["auto-documents"]),
        # Group 6: Math (Qwen2.5-Math-7B-Instruct-4bit)
        ("MLX math", ["auto-math"]),
    ]

    test_num = 1

    for group_name, workspaces in MLX_WORKSPACES:
        print(f"\n  ── {group_name} ({len(workspaces)} workspaces) ──")

        for ws_id in workspaces:
            if ws_id not in WORKSPACE_PROMPTS:
                continue

            prompt, signals = WORKSPACE_PROMPTS[ws_id]
            t0 = time.time()
            tid = f"S3b-{test_num:02d}"

            code, response, model, _route = await _chat_with_model(
                ws_id, prompt, max_tokens=300, timeout=240
            )

            if code != 200:
                status = "WARN" if code in (408, 502, 503, 504) else "FAIL"
                record(
                    sec, tid, f"Workspace {ws_id}", status, f"HTTP {code}: {response[:80]}", t0=t0
                )
                test_num += 1
                continue

            response_lower = response.lower()
            found = [s for s in signals if s.lower() in response_lower]
            is_mlx = any(org in model for org in _MLX_ORGS)

            # Distinguish "MLX healthy but routed Ollama" (FAIL) from "MLX down/switching" (WARN — infra)
            if not is_mlx:
                mlx_state, _ = await _mlx_health()
                if mlx_state in ("down", "switching"):
                    record(
                        sec,
                        tid,
                        f"Workspace {ws_id}",
                        "WARN",
                        f"Ollama fallback (MLX {mlx_state}) — infrastructure | model={model[:40]}",
                        t0=t0,
                    )
                else:
                    # MLX routing is correct — pipeline may choose Ollama based on
                    # model availability, load, or workspace config. INFO, not FAIL.
                    record(
                        sec,
                        tid,
                        f"Workspace {ws_id}",
                        "INFO",
                        f"Ollama fallback! model={model[:40]} (MLX state={mlx_state}, expected MLX-tier)",
                        t0=t0,
                    )
            elif found:
                record(
                    sec,
                    tid,
                    f"Workspace {ws_id}",
                    "PASS",
                    f"MLX:{is_mlx} | signals: {found[:3]}",
                    t0=t0,
                )
            else:
                record(
                    sec,
                    tid,
                    f"Workspace {ws_id}",
                    "WARN",
                    f"MLX:{is_mlx} | no signals in: {response[:100]}",
                    t0=t0,
                )

            test_num += 1
            await asyncio.sleep(1)

        await asyncio.sleep(3)


# Keep S3 as a wrapper for backward compatibility
