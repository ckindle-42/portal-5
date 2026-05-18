"""LibreChat adapter — generates librechat.yaml and seeds presets via API."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

import httpx
import yaml as _yaml

from frontend_seeder.source import (
    PORTAL_ROOT,
    load_mcp_servers,
    load_personas,
    load_workspaces,
    production_workspaces,
)

LIBRECHAT_URL = os.environ.get("LIBRECHAT_URL", "http://librechat:3080")
LIBRECHAT_ADMIN_EMAIL = os.environ.get("LIBRECHAT_ADMIN_EMAIL", "admin@portal.local")
LIBRECHAT_ADMIN_PASSWORD = os.environ.get("LIBRECHAT_ADMIN_PASSWORD", "")
PIPELINE_API_KEY = os.environ.get("PIPELINE_API_KEY", "")
PIPELINE_URL = os.environ.get("PIPELINE_URL", "http://portal-pipeline:9099/v1")


# ── Config file generator ────────────────────────────────────────────────────

def generate_librechat_yaml(output_path: Path | None = None) -> str:
    """Generate librechat.yaml with Portal 5 pipeline endpoint + MCP servers."""
    mcp_servers = load_mcp_servers()
    workspaces = production_workspaces(load_workspaces())

    # Build model list for static declaration (also fetched live via fetch:true)
    model_ids = list(workspaces.keys())

    mcp_block: dict[str, Any] = {}
    for srv in mcp_servers:
        key = srv["id"].replace("portal_", "portal-")
        mcp_block[key] = {"url": srv["url"]}

    config: dict[str, Any] = {
        "version": "1.3.11",
        "cache": True,
        "registration": {
            "socialLogins": ["openid"],
            "allowedDomains": [],
        },
        "endpoints": {
            "custom": [
                {
                    "name": "Portal 5",
                    "apiKey": "${PIPELINE_API_KEY}",
                    "baseURL": "${PIPELINE_URL}",
                    "models": {
                        "default": model_ids,
                        "fetch": True,
                    },
                    "titleConvo": True,
                    "titleModel": "auto",
                    "modelDisplayLabel": "Portal 5",
                    "iconURL": "https://raw.githubusercontent.com/ckindle-42/portal-5/main/docs/portal5-icon.png",
                }
            ]
        },
        "mcpServers": mcp_block,
    }

    out = _yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False)
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(out)
        print(f"  [librechat] Wrote {output_path}")
    return out


# ── API seeder ───────────────────────────────────────────────────────────────

async def _wait_healthy(client: httpx.AsyncClient, max_wait: int = 120) -> None:
    for _ in range(max_wait // 5):
        try:
            r = await client.get(f"{LIBRECHAT_URL}/health")
            if r.status_code == 200:
                return
        except Exception:
            pass
        await asyncio.sleep(5)
    raise RuntimeError(f"LibreChat not healthy after {max_wait}s")


async def _get_token(client: httpx.AsyncClient) -> str:
    r = await client.post(
        f"{LIBRECHAT_URL}/api/auth/login",
        json={"email": LIBRECHAT_ADMIN_EMAIL, "password": LIBRECHAT_ADMIN_PASSWORD},
    )
    if r.status_code != 200:
        raise RuntimeError(f"LibreChat login failed: {r.status_code} {r.text[:200]}")
    return r.json()["token"]


async def _register_admin(client: httpx.AsyncClient) -> None:
    """Create admin account if it doesn't exist."""
    r = await client.post(
        f"{LIBRECHAT_URL}/api/auth/register",
        json={
            "name": "Portal Admin",
            "email": LIBRECHAT_ADMIN_EMAIL,
            "password": LIBRECHAT_ADMIN_PASSWORD,
            "confirm_password": LIBRECHAT_ADMIN_PASSWORD,
        },
    )
    if r.status_code in (200, 201):
        print(f"  [librechat] Admin account created: {LIBRECHAT_ADMIN_EMAIL}")
    elif r.status_code == 422 or "already" in r.text.lower():
        print(f"  [librechat] Admin account already exists")
    else:
        print(f"  [librechat] Register returned {r.status_code}: {r.text[:120]}")


async def _seed_presets(client: httpx.AsyncClient, token: str) -> None:
    """Seed workspace + persona presets."""
    headers = {"Authorization": f"Bearer {token}"}
    workspaces = production_workspaces(load_workspaces())
    personas = load_personas()

    # Fetch existing presets to avoid duplicates
    r = await client.get(f"{LIBRECHAT_URL}/api/presets", headers=headers)
    existing_titles: set[str] = set()
    if r.status_code == 200:
        for p in r.json():
            existing_titles.add(p.get("title", ""))

    created = skipped = 0

    # Workspace presets (one per workspace)
    for ws_id, ws_cfg in workspaces.items():
        title = ws_cfg["name"]
        if title in existing_titles:
            skipped += 1
            continue
        preset = {
            "title": title,
            "endpoint": "Portal 5",
            "model": ws_id,
            "chatGptLabel": ws_cfg["name"],
            "promptPrefix": ws_cfg.get("description", ""),
        }
        r = await client.post(f"{LIBRECHAT_URL}/api/presets", json=preset, headers=headers)
        if r.status_code in (200, 201):
            created += 1
        else:
            print(f"  [librechat] Preset create failed ({ws_id}): {r.status_code}")
    print(f"  [librechat] Workspace presets: {created} created, {skipped} skipped")

    # Persona presets
    created = skipped = 0
    for persona in personas:
        slug = persona.get("slug", "")
        name = persona.get("name", slug)
        title = f"🎭 {name}"
        if title in existing_titles:
            skipped += 1
            continue
        ws_model = persona.get("workspace_model", "auto")
        system = persona.get("system_prompt", "")
        preset = {
            "title": title,
            "endpoint": "Portal 5",
            "model": ws_model,
            "chatGptLabel": name,
            "promptPrefix": system,
        }
        r = await client.post(f"{LIBRECHAT_URL}/api/presets", json=preset, headers=headers)
        if r.status_code in (200, 201):
            created += 1
        else:
            print(f"  [librechat] Persona preset failed ({slug}): {r.status_code}")
    print(f"  [librechat] Persona presets: {created} created, {skipped} skipped")


async def seed() -> None:
    if not LIBRECHAT_ADMIN_PASSWORD:
        print("ERROR: LIBRECHAT_ADMIN_PASSWORD not set", file=sys.stderr)
        sys.exit(1)

    async with httpx.AsyncClient(timeout=30) as client:
        print("[librechat] Waiting for LibreChat to be healthy...")
        await _wait_healthy(client)
        print("[librechat] Registering admin account...")
        await _register_admin(client)
        print("[librechat] Logging in...")
        token = await _get_token(client)
        print("[librechat] Seeding presets...")
        await _seed_presets(client, token)
    print("[librechat] Seeding complete.")
