"""Stdio MCP bridge (:8949) — relay, health, and the fleet entry. No network."""

from __future__ import annotations

import asyncio
import json
import sys
import textwrap
from pathlib import Path

import httpx
import pytest

from portal.modules.orchestration.mcp import stdio_bridge_mcp as bridge

STUB = textwrap.dedent(
    """
    import json, sys
    def send(obj):
        sys.stdout.write(json.dumps(obj) + "\\n")
        sys.stdout.flush()
    for line in sys.stdin:
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if "id" not in msg:
            continue
        method = msg.get("method")
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": msg["id"], "result": {
                "protocolVersion": "2025-11-25", "capabilities": {},
                "serverInfo": {"name": "stub"}}})
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": msg["id"], "result": {
                "tools": [{"name": "stub_read", "description": "stub", "inputSchema": {}}]}})
        elif method == "tools/call":
            send({"jsonrpc": "2.0", "id": msg["id"], "result": {
                "content": [{"type": "text", "text": json.dumps({"echo": msg["params"]["name"]})}]}})
        else:
            send({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": "no"}})
    """
)


def _app(tmp_path: Path) -> bridge.Starlette:
    return bridge.build_app("unifi", [sys.executable, str(tmp_path / "stub.py")])


def _client(app: bridge.Starlette) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _request(method: str, params: dict[str, object], request_id: object = 1) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})


@pytest.fixture(name="stub_app")
def _stub_app(tmp_path: Path) -> bridge.Starlette:
    (tmp_path / "stub.py").write_text(STUB, encoding="utf-8")
    return _app(tmp_path)


def test_health_is_down_until_the_child_is_up(stub_app: bridge.Starlette) -> None:
    async def run() -> None:
        async with _client(stub_app) as client:
            response = await client.get("/health")
            assert response.status_code == 503
            listed = await client.post("/mcp", content=_request("tools/list", {}))
            assert listed.status_code == 200
            assert listed.json()["result"]["tools"][0]["name"] == "stub_read"
            healthy = await client.get("/health")
            assert healthy.status_code == 200
            assert healthy.json()["status"] == "ok"

    asyncio.run(run())


def test_tools_call_relay_returns_the_child_result(stub_app: bridge.Starlette) -> None:
    async def run() -> None:
        async with _client(stub_app) as client:
            response = await client.post(
                "/mcp",
                content=_request("tools/call", {"name": "stub_read", "arguments": {}}),
            )
            assert response.status_code == 200
            result = response.json()["result"]
            assert result["content"][0]["text"] == '{"echo": "stub_read"}'

    asyncio.run(run())


def test_legacy_initialize_is_answered_locally(stub_app: bridge.Starlette) -> None:
    async def run() -> None:
        async with _client(stub_app) as client:
            initialized = await client.post(
                "/mcp",
                content=_request(
                    "initialize",
                    {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {}},
                ),
            )
            assert initialized.status_code == 200
            assert initialized.json()["result"]["protocolVersion"] == "2025-11-25"
            assert initialized.json()["result"]["serverInfo"]["name"] == (
                "portal-stdio-bridge-unifi"
            )
            notification = await client.post(
                "/mcp",
                content=json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            )
            assert notification.status_code == 202

    asyncio.run(run())


def test_an_unknown_method_is_a_jsonrpc_error(stub_app: bridge.Starlette) -> None:
    async def run() -> None:
        async with _client(stub_app) as client:
            response = await client.post("/mcp", content=_request("resources/list", {}))
            assert response.status_code == 200
            assert response.json()["error"]["code"] == -32601

    asyncio.run(run())


def test_a_dead_child_is_respawned_on_the_next_call(stub_app: bridge.Starlette) -> None:
    async def run() -> None:
        async with _client(stub_app) as client:
            first = await client.post("/mcp", content=_request("tools/list", {}))
            assert first.status_code == 200
            child: bridge.StdioChild = stub_app.state.child
            proc = child.proc
            assert proc is not None and proc.returncode is None
            proc.kill()
            await proc.wait()
            child.proc = None
            second = await client.post("/mcp", content=_request("tools/list", {}))
            assert second.status_code == 200
            assert second.json()["result"]["tools"][0]["name"] == "stub_read"

    asyncio.run(run())


def test_fleet_entry_serves_the_operator_unifi_launcher() -> None:
    argv, port = bridge.fleet_entry("unifi")
    assert port == 8949
    assert argv == [f"{Path.home()}/mcp/unifi-network/run.sh"]


def test_fleet_entry_errors_are_named(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="no mcp_fleet entry"):
        bridge.fleet_entry("no-such-fleet-id")
    config = tmp_path / "portal.yaml"
    config.write_text(
        "mcp_fleet:\n"
        "  - id: bare\n"
        "    module: orchestration\n"
        "    name: bare\n"
        "    port: 8999\n"
        "    command:\n"
        "      type: local\n"
        "      command: []\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="no local command"):
        bridge.fleet_entry("bare", config)
