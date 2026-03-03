#!/usr/bin/env python3
"""
Open WebUI First-Run Initialization Script

Runs inside the openwebui-init Docker container after Open WebUI is healthy.
Handles:
  1. Admin account creation (first run only - idempotent)
  2. API key acquisition
  3. MCP Tool Server registration (via correct /api/v1/tools/server/ endpoint)
  4. Workspace creation

Environment variables (all have defaults for local dev):
  OPENWEBUI_URL              - default: http://open-webui:8080
  OPENWEBUI_ADMIN_EMAIL      - default: admin@portal.local
  OPENWEBUI_ADMIN_PASSWORD   - default: portal-admin-change-me
  OPENWEBUI_ADMIN_NAME       - default: Portal Admin
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx

OPENWEBUI_URL = os.environ.get("OPENWEBUI_URL", "http://open-webui:8080").rstrip("/")
ADMIN_EMAIL = os.environ.get("OPENWEBUI_ADMIN_EMAIL", "admin@portal.local")
ADMIN_PASSWORD = os.environ.get("OPENWEBUI_ADMIN_PASSWORD", "portal-admin-change-me")
ADMIN_NAME = os.environ.get("OPENWEBUI_ADMIN_NAME", "Portal Admin")

IMPORTS_DIR = Path("/imports/openwebui")
MCP_FILE = IMPORTS_DIR / "mcp-servers.json"
WORKSPACES_DIR = IMPORTS_DIR / "workspaces"

MAX_WAIT_SECONDS = 120
POLL_INTERVAL = 5


# --- Utilities ---------------------------------------------------------------

def wait_for_openwebui(client: httpx.Client) -> bool:
    """Poll until Open WebUI health endpoint responds."""
    print(f"Waiting for Open WebUI at {OPENWEBUI_URL}...")
    deadline = time.time() + MAX_WAIT_SECONDS
    while time.time() < deadline:
        try:
            resp = client.get(f"{OPENWEBUI_URL}/health", timeout=5.0)
            if resp.status_code == 200:
                print("  Open WebUI is healthy")
                return True
        except Exception:
            pass
        print(f"  Not ready yet - retrying in {POLL_INTERVAL}s...")
        time.sleep(POLL_INTERVAL)
    print("ERROR: Open WebUI did not become ready in time")
    return False


def create_admin_account(client: httpx.Client) -> str | None:
    """Create the admin account. Returns API token or None if already exists."""
    print(f"Creating admin account: {ADMIN_EMAIL}")
    try:
        resp = client.post(
            f"{OPENWEBUI_URL}/api/v1/auths/signup",
            json={
                "name": ADMIN_NAME,
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD,
            },
            timeout=15.0,
        )
        if resp.status_code in (200, 201):
            token = resp.json().get("token")
            print("  Admin account created")
            return token
        elif resp.status_code == 400:
            # User already exists - this is expected on non-first runs
            detail = resp.json().get("detail", "")
            if "already" in detail.lower() or "exist" in detail.lower():
                print("  Admin account already exists (not first run)")
                return None
            print(f"  Signup failed: {detail}")
            return None
        else:
            print(f"  Signup failed: HTTP {resp.status_code} - {resp.text[:150]}")
            return None
    except Exception as e:
        print(f"  Signup error: {e}")
        return None


def login(client: httpx.Client) -> str | None:
    """Login and return API token."""
    print(f"Logging in as: {ADMIN_EMAIL}")
    try:
        resp = client.post(
            f"{OPENWEBUI_URL}/api/v1/auths/signin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=15.0,
        )
        if resp.status_code == 200:
            token = resp.json().get("token")
            print("  Login successful")
            return token
        else:
            print(f"  Login failed: HTTP {resp.status_code} - {resp.text[:150]}")
            return None
    except Exception as e:
        print(f"  Login error: {e}")
        return None


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# --- Tool Server Registration -------------------------------------------------

def register_tool_servers(client: httpx.Client, token: str) -> None:
    """Register all Portal MCP servers as Tool Servers in Open WebUI."""
    print("\nRegistering MCP Tool Servers...")

    if not MCP_FILE.exists():
        print(f"  Skipping - {MCP_FILE} not found")
        return

    servers = json.loads(MCP_FILE.read_text()).get("tool_servers", [])
    if not servers:
        print("  Skipping - no tool_servers in mcp-servers.json")
        return

    # Get existing registrations
    existing_urls: set[str] = set()
    try:
        resp = client.get(
            f"{OPENWEBUI_URL}/api/v1/tools/server/",
            headers=auth_headers(token),
        )
        if resp.status_code == 200:
            data = resp.json()
            for s in (data if isinstance(data, list) else data.get("data", [])):
                existing_urls.add(s.get("url", ""))
    except Exception as e:
        print(f"  Warning: could not check existing tool servers: {e}")

    registered = skipped = failed = 0
    for server in servers:
        url = server["url"]
        name = server["name"]
        key = server.get("api_key", "")

        if url in existing_urls:
            print(f"  Skip (exists): {name}")
            skipped += 1
            continue

        try:
            resp = client.post(
                f"{OPENWEBUI_URL}/api/v1/tools/server/",
                json={
                    "url": url,
                    "config": {
                        "name": name,
                        "auth_type": "none" if not key else "bearer",
                        "key": key,
                    },
                },
                headers=auth_headers(token),
                timeout=10.0,
            )
            if resp.status_code in (200, 201):
                print(f"  Registered: {name}")
                registered += 1
            else:
                print(f"  Failed {name}: HTTP {resp.status_code} - {resp.text[:100]}")
                failed += 1
        except Exception as e:
            print(f"  Error {name}: {e}")
            failed += 1

    print(f"  Done: {registered} registered, {skipped} skipped, {failed} failed")


# --- Workspace Creation -------------------------------------------------------

def create_workspaces(client: httpx.Client, token: str) -> None:
    """Create Portal workspace presets in Open WebUI."""
    print("\nCreating Workspaces...")

    if not WORKSPACES_DIR.exists():
        print(f"  Skipping - {WORKSPACES_DIR} not found")
        return

    ws_files = sorted(WORKSPACES_DIR.glob("workspace_*.json"))
    if not ws_files:
        print("  Skipping - no workspace files found")
        return

    # Get existing workspaces
    existing_names: set[str] = set()
    try:
        resp = client.get(
            f"{OPENWEBUI_URL}/api/v1/models/",
            headers=auth_headers(token),
        )
        if resp.status_code == 200:
            data = resp.json()
            models = data if isinstance(data, list) else data.get("data", [])
            for m in models:
                existing_names.add(m.get("id", ""))
    except Exception as e:
        print(f"  Warning: could not check existing models: {e}")

    created = skipped = failed = 0
    for ws_file in ws_files:
        ws = json.loads(ws_file.read_text())
        ws_id = ws.get("id", "")

        if ws_id in existing_names:
            print(f"  Skip (exists): {ws['name']}")
            skipped += 1
            continue

        payload = {
            "id": ws_id,
            "name": ws["name"],
            "meta": ws.get("meta", {}),
            "params": ws.get("params", {}),
        }

        try:
            resp = client.post(
                f"{OPENWEBUI_URL}/api/v1/models/",
                json=payload,
                headers=auth_headers(token),
                timeout=10.0,
            )
            if resp.status_code in (200, 201):
                print(f"  Created: {ws['name']}")
                created += 1
            else:
                print(f"  Failed {ws['name']}: HTTP {resp.status_code} - {resp.text[:100]}")
                failed += 1
        except Exception as e:
            print(f"  Error {ws['name']}: {e}")
            failed += 1

    print(f"  Done: {created} created, {skipped} skipped, {failed} failed")


# --- Main ---------------------------------------------------------------------

def main() -> int:
    client = httpx.Client(timeout=30.0)

    # Wait for Open WebUI to be ready
    if not wait_for_openwebui(client):
        return 1

    # Create admin account (first run) or skip if exists
    token = create_admin_account(client)

    # If signup failed (account exists), login instead
    if token is None:
        token = login(client)

    if not token:
        print("ERROR: Could not obtain API token - check admin credentials in .env")
        print(f"  OPENWEBUI_ADMIN_EMAIL: {ADMIN_EMAIL}")
        print("  Set OPENWEBUI_ADMIN_EMAIL and OPENWEBUI_ADMIN_PASSWORD in .env")
        return 1

    # Seed the instance
    register_tool_servers(client, token)
    create_workspaces(client, token)

    print("\nPortal Open WebUI initialization complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
