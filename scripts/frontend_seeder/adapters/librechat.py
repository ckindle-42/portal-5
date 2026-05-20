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

    # portal_browser uses a custom REST API, not the MCP protocol — skip it.
    _LIBRECHAT_SKIP = {"portal_browser"}
    # mlx-transcribe requires trailing slash to avoid redirect that LibreChat blocks.
    _TRAILING_SLASH = {"portal_mlx_transcribe"}

    mcp_block: dict[str, Any] = {}
    for srv in mcp_servers:
        srv_id = srv["id"]
        if srv_id in _LIBRECHAT_SKIP:
            continue
        key = srv_id.replace("portal_", "portal-")
        url = srv["url"]
        if srv_id in _TRAILING_SLASH and not url.endswith("/"):
            url = url + "/"
        mcp_block[key] = {"url": url, "type": "streamable-http"}

    config: dict[str, Any] = {
        "version": "1.3.11",
        "cache": True,
        "registration": {
            "socialLogins": ["openid"],
            "allowedDomains": [],
        },
        "fileConfig": {
            "serverFileSizeLimit": 500,
            "endpoints": {
                "default": {
                    "fileLimit": 5,
                    "fileSizeLimit": 500,
                    "totalSizeLimit": 500,
                    "supportedMimeTypes": [
                        "audio/mpeg", "audio/mp4", "audio/wav", "audio/ogg",
                        "audio/webm", "audio/x-m4a", "audio/flac",
                        "video/mp4", "video/quicktime",
                        "application/pdf", "text/plain",
                        "image/jpeg", "image/png", "image/gif", "image/webp",
                    ],
                }
            },
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
                }
            ]
        },
        "mcpSettings": {
            "allowedDomains": ["host.docker.internal"],
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


def _reset_password_via_mongo() -> bool:
    """Reset admin password directly in MongoDB when .env password has changed."""
    try:
        import bcrypt
        import pymongo
    except ImportError:
        return False
    try:
        client = pymongo.MongoClient("mongodb://librechat-mongodb:27017/LibreChat", serverSelectionTimeoutMS=5000)
        db = client["LibreChat"]
        hashed = bcrypt.hashpw(LIBRECHAT_ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode()
        result = db.users.update_one(
            {"email": LIBRECHAT_ADMIN_EMAIL},
            {"$set": {"password": hashed}},
        )
        client.close()
        if result.modified_count > 0:
            print(f"  [librechat] Password updated in MongoDB for {LIBRECHAT_ADMIN_EMAIL}")
            return True
        print(f"  [librechat] No user found in MongoDB for {LIBRECHAT_ADMIN_EMAIL}")
        return False
    except Exception as e:
        print(f"  [librechat] MongoDB password reset failed: {e}")
        return False


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
        print("  [librechat] Admin account already exists")
    else:
        print(f"  [librechat] Register returned {r.status_code}: {r.text[:120]}")


async def _upsert_preset(
    client: httpx.AsyncClient,
    headers: dict,
    preset: dict,
    existing: dict[str, str],
) -> str:
    """Create or update a preset. Returns 'created', 'updated', or 'failed'."""
    title = preset["title"]
    if title in existing:
        preset_id = existing[title]
        r = await client.post(
            f"{LIBRECHAT_URL}/api/presets",
            json={**preset, "presetId": preset_id},
            headers=headers,
        )
        return "updated" if r.status_code in (200, 201) else "failed"
    else:
        r = await client.post(f"{LIBRECHAT_URL}/api/presets", json=preset, headers=headers)
        return "created" if r.status_code in (200, 201) else "failed"


async def _seed_presets(client: httpx.AsyncClient, token: str) -> None:
    """Seed workspace + persona presets (upsert — always syncs latest content)."""
    headers = {"Authorization": f"Bearer {token}"}
    workspaces = production_workspaces(load_workspaces())
    personas = load_personas()

    # Fetch existing presets: title → presetId
    r = await client.get(f"{LIBRECHAT_URL}/api/presets", headers=headers)
    existing: dict[str, str] = {}
    if r.status_code == 200:
        for p in r.json():
            existing[p.get("title", "")] = p.get("presetId", p.get("_id", ""))

    created = updated = failed = 0

    # Workspace presets
    for ws_id, ws_cfg in workspaces.items():
        preset = {
            "title": ws_cfg["name"],
            "endpoint": "Portal 5",
            "model": ws_id,
            "chatGptLabel": ws_cfg["name"],
            "promptPrefix": ws_cfg.get("description", ""),
        }
        result = await _upsert_preset(client, headers, preset, existing)
        if result == "created": created += 1
        elif result == "updated": updated += 1
        else:
            failed += 1
            print(f"  [librechat] Workspace preset failed ({ws_id})")
    print(f"  [librechat] Workspace presets: {created} created, {updated} updated, {failed} failed")

    # Persona presets
    created = updated = failed = 0
    for persona in personas:
        slug = persona.get("slug", "")
        name = persona.get("name", slug)
        preset = {
            "title": f"🎭 {name}",
            "endpoint": "Portal 5",
            "model": persona.get("workspace_model", "auto"),
            "chatGptLabel": name,
            "promptPrefix": persona.get("system_prompt", ""),
        }
        result = await _upsert_preset(client, headers, preset, existing)
        if result == "created": created += 1
        elif result == "updated": updated += 1
        else:
            failed += 1
            print(f"  [librechat] Persona preset failed ({slug})")
    print(f"  [librechat] Persona presets: {created} created, {updated} updated, {failed} failed")


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
        try:
            token = await _get_token(client)
        except RuntimeError as e:
            if "login failed" in str(e).lower():
                print("  [librechat] Login failed — .env password may have changed. Attempting MongoDB reset...")
                if _reset_password_via_mongo():
                    token = await _get_token(client)
                else:
                    print("  [librechat] ERROR: Could not reset password. To recover, run:", file=sys.stderr)
                    print("    ./launch.sh librechat-reset", file=sys.stderr)
                    raise
            else:
                raise
        print("[librechat] Seeding presets...")
        await _seed_presets(client, token)
    print("[librechat] Seeding complete.")
