"""AnythingLLM adapter — seeds workspaces and agent settings via API."""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

import httpx

from frontend_seeder.source import load_workspaces, production_workspaces

ANYTHINGLLM_URL = os.environ.get("ANYTHINGLLM_URL", "http://anythingllm:3001")
ANYTHINGLLM_ADMIN_PASSWORD = os.environ.get("ANYTHINGLLM_ADMIN_PASSWORD", "")
PIPELINE_API_KEY = os.environ.get("PIPELINE_API_KEY", "")
PIPELINE_URL = os.environ.get("PIPELINE_URL", "http://portal-pipeline:9099/v1")


async def _wait_healthy(client: httpx.AsyncClient, max_wait: int = 120) -> None:
    for _ in range(max_wait // 5):
        try:
            r = await client.get(f"{ANYTHINGLLM_URL}/api/v1/health")
            if r.status_code == 200:
                return
        except Exception:
            pass
        await asyncio.sleep(5)
    raise RuntimeError(f"AnythingLLM not healthy after {max_wait}s")


async def _setup_or_login(client: httpx.AsyncClient) -> str:
    """Run initial setup if needed, then return API token."""
    # Check if setup is already done
    r = await client.get(f"{ANYTHINGLLM_URL}/api/v1/auth")
    data = r.json()

    if not data.get("isMultiUserMode") and data.get("requiresAuth") is False:
        # Fresh install — run setup
        r = await client.post(
            f"{ANYTHINGLLM_URL}/api/v1/system/update-env",
            json={"AuthToken": ANYTHINGLLM_ADMIN_PASSWORD},
        )
        if r.status_code not in (200, 201):
            print(f"  [anythingllm] Setup warning: {r.status_code} {r.text[:120]}")

    # Login with the token directly (AnythingLLM uses a single admin token)
    return ANYTHINGLLM_ADMIN_PASSWORD


async def _get_existing_workspaces(client: httpx.AsyncClient, token: str) -> set[str]:
    headers = {"Authorization": f"Bearer {token}"}
    r = await client.get(f"{ANYTHINGLLM_URL}/api/v1/workspaces", headers=headers)
    if r.status_code == 200:
        return {ws.get("name", "") for ws in r.json().get("workspaces", [])}
    return set()


async def _seed_workspaces(client: httpx.AsyncClient, token: str) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    workspaces = production_workspaces(load_workspaces())
    existing = await _get_existing_workspaces(client, token)

    created = skipped = 0
    for ws_id, ws_cfg in workspaces.items():
        name = ws_cfg["name"]
        if name in existing:
            skipped += 1
            continue

        # Create workspace
        r = await client.post(
            f"{ANYTHINGLLM_URL}/api/v1/workspace/new",
            json={"name": name},
            headers=headers,
        )
        if r.status_code not in (200, 201):
            print(f"  [anythingllm] Workspace create failed ({ws_id}): {r.status_code}")
            continue

        slug = r.json().get("workspace", {}).get("slug", "")
        if not slug:
            created += 1
            continue

        # Configure workspace to use Portal 5 pipeline
        settings: dict[str, Any] = {
            "openAiModel": ws_id,
            "openAiKey": PIPELINE_API_KEY,
            "openAiApiBase": PIPELINE_URL,
            "chatMode": "chat",
        }
        desc = ws_cfg.get("description", "")
        if desc:
            settings["openAiPrompt"] = desc

        r2 = await client.post(
            f"{ANYTHINGLLM_URL}/api/v1/workspace/{slug}/update",
            json=settings,
            headers=headers,
        )
        if r2.status_code in (200, 201):
            created += 1
        else:
            print(f"  [anythingllm] Workspace update failed ({slug}): {r2.status_code}")

    print(f"  [anythingllm] Workspaces: {created} created, {skipped} skipped")


async def _configure_llm(client: httpx.AsyncClient, token: str) -> None:
    """Set the global LLM provider to Portal 5 pipeline."""
    headers = {"Authorization": f"Bearer {token}"}
    r = await client.post(
        f"{ANYTHINGLLM_URL}/api/v1/system/update-env",
        json={
            "LLMProvider": "openai",
            "OpenAiKey": PIPELINE_API_KEY,
            "OpenAiModelPref": "auto",
            "OpenAiBaseUrl": PIPELINE_URL,
        },
        headers=headers,
    )
    if r.status_code in (200, 201):
        print("  [anythingllm] Global LLM configured → Portal 5 pipeline")
    else:
        print(f"  [anythingllm] LLM config warning: {r.status_code} {r.text[:120]}")


async def seed() -> None:
    if not ANYTHINGLLM_ADMIN_PASSWORD:
        print("ERROR: ANYTHINGLLM_ADMIN_PASSWORD not set", file=sys.stderr)
        sys.exit(1)

    async with httpx.AsyncClient(timeout=30) as client:
        print("[anythingllm] Waiting for AnythingLLM to be healthy...")
        await _wait_healthy(client)
        print("[anythingllm] Authenticating...")
        token = await _setup_or_login(client)
        print("[anythingllm] Configuring LLM provider...")
        await _configure_llm(client, token)
        print("[anythingllm] Seeding workspaces...")
        await _seed_workspaces(client, token)
    print("[anythingllm] Seeding complete.")
