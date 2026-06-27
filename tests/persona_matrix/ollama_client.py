"""Direct Ollama HTTP client — pins models in the request body to
bypass the Portal pipeline at :9099. Used by persona-matrix to test
raw model behavior independent of routing logic.

Includes admission helpers (_ollama_unload with cooldown) that mirror
the bench_tps.py pattern for memory discipline.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ._common import (
    AUDIT_PROMPT,
    AUDIT_TOOL_DEFINITION,
    EVICT_BACKOFF_S,
    OLLAMA_URL,
    REQUEST_TIMEOUT,
    RESULTS_DIR,
    SYSTEM_PROMPT_CAP_CHARS,
)
from .loaders import _ollama_size_estimate, chain_models_for_workspace, load_backends_yaml


async def _chat_direct(
    client: httpx.AsyncClient,
    backend_type: str,
    model_id: str,
    system: str,
    user_prompt: str,
    timeout: float = REQUEST_TIMEOUT,
) -> tuple[int, str]:
    """Direct backend call — pipeline bypassed.

    System prompt cap: 8000 chars. The cap is intentionally well above the
    largest current compliance persona (complianceanalyst at 4963 chars) so
    the OUTPUT CONTRACT section is never silently dropped. Personas longer
    than the cap will hit the assertion in run_cell() with a clear error
    rather than being silently truncated.
    """
    if len(system) > SYSTEM_PROMPT_CAP_CHARS:
        return 0, (
            f"persona system prompt {len(system)} chars exceeds cap "
            f"{SYSTEM_PROMPT_CAP_CHARS}; raise SYSTEM_PROMPT_CAP_CHARS or "
            f"shorten the persona before re-running."
        )

    base_url = OLLAMA_URL
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": user_prompt})
    payload = {
        "model": model_id,
        "messages": msgs,
        "max_tokens": 700,
        "stream": False,
    }
    try:
        r = await client.post(f"{base_url}/v1/chat/completions", json=payload, timeout=timeout)
        if r.status_code != 200:
            return r.status_code, r.text[:300]
        data = r.json()
        msg = data.get("choices", [{}])[0].get("message", {})
        content = msg.get("content", "") or ""
        reasoning = msg.get("reasoning", "") or ""
        return 200, (content + " " + reasoning).strip() if reasoning else content
    except httpx.ReadTimeout:
        return 408, "timeout"
    except Exception as e:
        return 0, str(e)[:200]


async def _audit_tool_support(
    client: httpx.AsyncClient,
    backend_type: str,
    model_id: str,
    timeout: float = REQUEST_TIMEOUT,
) -> dict:
    """Send AUDIT_PROMPT with AUDIT_TOOL_DEFINITION attached and classify the response.

    Returns: {outcome, http_status, detail, elapsed_s}
    outcome ∈ {"tool_call", "text_only", "api_error", "exception"}
    """
    base_url = OLLAMA_URL
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": AUDIT_PROMPT}],
        "tools": [AUDIT_TOOL_DEFINITION],
        "tool_choice": "auto",
        "max_tokens": 200,
        "stream": False,
    }
    t0 = time.time()
    try:
        r = await client.post(f"{base_url}/v1/chat/completions", json=payload, timeout=timeout)
        elapsed = round(time.time() - t0, 2)
        if r.status_code != 200:
            return {
                "outcome": "api_error",
                "http_status": r.status_code,
                "detail": r.text[:300],
                "elapsed_s": elapsed,
            }
        data = r.json()
        msg = data.get("choices", [{}])[0].get("message", {})
        tool_calls = msg.get("tool_calls")
        if tool_calls:
            return {
                "outcome": "tool_call",
                "http_status": 200,
                "detail": f"emitted {len(tool_calls)} tool_call(s); first={tool_calls[0].get('function', {}).get('name')}",
                "elapsed_s": elapsed,
            }
        content = msg.get("content", "") or ""
        return {
            "outcome": "text_only",
            "http_status": 200,
            "detail": f"no tool_calls; text response {len(content)} chars",
            "elapsed_s": elapsed,
        }
    except httpx.ReadTimeout:
        return {
            "outcome": "exception",
            "http_status": 408,
            "detail": "timeout",
            "elapsed_s": round(time.time() - t0, 2),
        }
    except Exception as e:
        return {
            "outcome": "exception",
            "http_status": 0,
            "detail": str(e)[:200],
            "elapsed_s": round(time.time() - t0, 2),
        }


async def run_audit_tools(args) -> dict:
    """Audit-tools sweep: per-(model, backend), verify tool-call support empirically."""
    cfg = load_backends_yaml()
    workspace_id = args.workspace
    chain_models = chain_models_for_workspace(cfg, workspace_id)

    if args.backend == "ollama":
        chain_models = [m for m in chain_models if m["backend_type"] == "ollama"]

    if args.model:
        chain_models = [m for m in chain_models if args.model in m["id"]]

    if not args.include_big_models:
        chain_models = [m for m in chain_models if not m.get("big_model")]

    print(f"\n=== Audit-tools sweep: workspace={workspace_id}, models={len(chain_models)} ===\n")

    results = []
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        for i, m in enumerate(chain_models, 1):
            print(
                f"  [{i}/{len(chain_models)}] {m['backend_type']:6} {m['id'][:60]:60} ... ",
                end="",
                flush=True,
            )
            audit = await _audit_tool_support(client, m["backend_type"], m["id"])
            print(f"{audit['outcome']:10} ({audit['elapsed_s']:5.1f}s)")
            results.append(
                {
                    "model": m["id"],
                    "backend": m["backend_type"],
                    "memory_gb": m.get("memory_gb"),
                    **audit,
                }
            )
            if m["backend_type"] == "ollama":
                await _ollama_unload(client, m["id"])
                await asyncio.sleep(EVICT_BACKOFF_S)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace": workspace_id,
        "audit_prompt": AUDIT_PROMPT,
        "audit_tool": AUDIT_TOOL_DEFINITION["function"]["name"],
        "results": results,
    }

    output = (
        Path(args.output)
        if args.output
        else RESULTS_DIR
        / f"audit_tools_{workspace_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2))

    print("\n=== Summary ===")
    by_outcome: dict[str, int] = {}
    for r in results:
        by_outcome[r["outcome"]] = by_outcome.get(r["outcome"], 0) + 1
    for outcome, count in sorted(by_outcome.items()):
        print(f"  {outcome:12} {count}")
    print(f"\nReport: {output}\n")

    print("Models verified tool-capable (flip supports_tools to true):")
    for r in results:
        if r["outcome"] == "tool_call":
            print(f"  - {r['model']} ({r['backend']})")
    print("\nModels that errored (keep supports_tools false):")
    for r in results:
        if r["outcome"] == "api_error":
            print(f"  - {r['model']} ({r['backend']}): {r['detail'][:80]}")

    return report


async def _ollama_unload(client: httpx.AsyncClient, model_id: str) -> None:
    """Send keep_alive=0 AND wait until Ollama confirms model is evicted.

    Without waiting for confirmation, Ollama keeps the model resident and
    subsequent model loads accumulate, exhausting memory on 64GB systems.
    """
    try:
        await client.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": model_id, "keep_alive": 0, "prompt": ""},
            timeout=10.0,
        )
        # Wait for Ollama to actually free the model's memory
        for _ in range(30):  # 30 × 2s = 60s max wait
            await asyncio.sleep(2.0)
            try:
                r = await client.get(f"{OLLAMA_URL}/api/ps", timeout=5.0)
                models = r.json().get("models", [])
                if not any(m["name"] == model_id for m in models):
                    return  # model successfully evicted
            except Exception:
                pass
    except Exception:
        pass


# ── Per-cell runner ───────────────────────────────────────────────────────

