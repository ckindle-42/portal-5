"""AnythingLLM adapter — seeds workspaces via API.

Auth flow (single-user mode):
  1. Ensure an API key exists in the SQLite DB (ANYTHINGLLM_DB_PATH mounted from data volume)
  2. Use that API key Bearer token for all /api/v1 workspace calls

Why direct DB access: AnythingLLM's single-user mode blocks admin API endpoints
(/admin/generate-api-key) with 401 since they require multi-user mode. The only
reliable seeding path is inserting the key directly into the SQLite database,
which is safe to do once at startup before any user traffic.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
from typing import Any

import httpx

from frontend_seeder.source import load_workspaces, production_workspaces

ANYTHINGLLM_URL = os.environ.get("ANYTHINGLLM_URL", "http://anythingllm:3001")
ANYTHINGLLM_ADMIN_PASSWORD = os.environ.get("ANYTHINGLLM_ADMIN_PASSWORD", "")
ANYTHINGLLM_DB_PATH = os.environ.get("ANYTHINGLLM_DB_PATH", "/storage/anythingllm.db")
PIPELINE_API_KEY = os.environ.get("PIPELINE_API_KEY", "")
PIPELINE_URL = os.environ.get("PIPELINE_URL", "http://portal-pipeline:9099/v1")

_SEEDER_API_KEY_NAME = "portal5-seeder"


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


def _ensure_api_key(known_secret: str) -> str:
    """Insert a known API key into the SQLite DB if not already present."""
    if not os.path.exists(ANYTHINGLLM_DB_PATH):
        raise RuntimeError(f"AnythingLLM DB not found at {ANYTHINGLLM_DB_PATH}")

    conn = sqlite3.connect(ANYTHINGLLM_DB_PATH, timeout=10)
    try:
        cur = conn.cursor()
        cur.execute("SELECT secret FROM api_keys WHERE secret = ?", (known_secret,))
        if cur.fetchone():
            return known_secret  # already exists

        cur.execute(
            "INSERT INTO api_keys (name, secret) VALUES (?, ?)",
            (_SEEDER_API_KEY_NAME, known_secret),
        )
        conn.commit()
        print("  [anythingllm] Seeder API key inserted into database")
        return known_secret
    finally:
        conn.close()


async def _get_existing_workspaces(client: httpx.AsyncClient, api_key: str) -> set[str]:
    headers = {"Authorization": f"Bearer {api_key}"}
    r = await client.get(f"{ANYTHINGLLM_URL}/api/v1/workspaces", headers=headers)
    if r.status_code == 200:
        return {ws.get("name", "") for ws in r.json().get("workspaces", [])}
    return set()


async def _seed_workspaces(client: httpx.AsyncClient, api_key: str) -> None:
    headers = {"Authorization": f"Bearer {api_key}"}
    workspaces = production_workspaces(load_workspaces())
    existing = await _get_existing_workspaces(client, api_key)

    created = skipped = 0
    for ws_id, ws_cfg in workspaces.items():
        name = ws_cfg["name"]
        if name in existing:
            skipped += 1
            continue

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

        # Bind workspace to Portal 5 pipeline model
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



async def seed() -> None:
    if not ANYTHINGLLM_ADMIN_PASSWORD:
        print("ERROR: ANYTHINGLLM_ADMIN_PASSWORD not set", file=sys.stderr)
        sys.exit(1)

    async with httpx.AsyncClient(timeout=30) as client:
        print("[anythingllm] Waiting for AnythingLLM to be healthy...")
        await _wait_healthy(client)
        print("[anythingllm] Ensuring API key exists in database...")
        api_key = _ensure_api_key(ANYTHINGLLM_ADMIN_PASSWORD)
        print("[anythingllm] Seeding workspaces...")
        await _seed_workspaces(client, api_key)
    print("[anythingllm] Seeding complete.")
