"""Bridge one fleet stdio MCP onto a Pipeline-facing HTTP port.

The operator's user-wide UniFi MCP (sirkirby ``unifi-network-mcp@0.40.0`` via
``~/mcp/unifi-network/run.sh``) stays an independent stdio process — CLAUDE.md
Rule 3 — and this bridge only relays native MCP ``tools/list`` / ``tools/call``
to it over streamable HTTP, plus a ``/health`` route for the up gate. The child
command comes from the fleet entry's ``command:`` (single source of truth);
this module never imports the child's code.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
import yaml
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

logger = logging.getLogger(__name__)

CALL_TIMEOUT_S = float(os.environ.get("STDIO_BRIDGE_CALL_TIMEOUT_S", "60"))
INIT_TIMEOUT_S = float(os.environ.get("STDIO_BRIDGE_INIT_TIMEOUT_S", "20"))
LEGACY_PROTOCOL_VERSION = "2025-11-25"


class BridgeError(RuntimeError):
    """One JSON-RPC error the bridge reports to its HTTP caller."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def _portal_yaml() -> Path:
    """config/portal.yaml of the checkout this server is deployed from."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "config" / "portal.yaml").is_file():
            return parent / "config" / "portal.yaml"
    return Path(__file__).resolve().parents[4] / "config" / "portal.yaml"


def fleet_entry(fleet_id: str, config_path: Path | None = None) -> tuple[list[str], int]:
    """The local command argv and port of one fleet entry, ${VAR}s expanded."""
    path = config_path or _portal_yaml()
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for item in loaded.get("mcp_fleet") or []:
        if not isinstance(item, dict) or item.get("id") != fleet_id:
            continue
        command = item.get("command")
        port = item.get("port")
        argv = command.get("command") if isinstance(command, dict) else None
        if (
            not isinstance(argv, list)
            or not argv
            or not all(isinstance(part, str) for part in argv)
        ):
            raise RuntimeError(f"fleet {fleet_id} has no local command to bridge")
        if not isinstance(port, int):
            raise RuntimeError(f"fleet {fleet_id} has no port")
        return [os.path.expandvars(part) for part in argv], port
    raise RuntimeError(f"no mcp_fleet entry {fleet_id}")


class StdioChild:
    """One stdio MCP child, MCP-initialized once, requests relayed by id."""

    def __init__(self, argv: list[str]) -> None:
        self.argv = argv
        self.proc: asyncio.subprocess.Process | None = None
        self.pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self.lock = asyncio.Lock()

    def alive(self) -> bool:
        return self.proc is not None and self.proc.returncode is None

    async def ensure(self) -> None:
        """Spawn and initialize the child once; respawn after a death."""
        async with self.lock:
            if self.alive():
                return
            self.proc = await asyncio.create_subprocess_exec(
                *self.argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
            )
            reader = self.proc.stdout
            if reader is None:  # pragma: no cover — PIPE always yields a stream
                raise RuntimeError("child has no stdout pipe")
            asyncio.create_task(self._read(reader))
            await self._request(
                "initialize",
                {
                    "protocolVersion": LEGACY_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "portal-stdio-bridge", "version": "1.0.0"},
                },
                INIT_TIMEOUT_S,
            )
            await self._notify("notifications/initialized")

    async def _read(self, reader: asyncio.StreamReader) -> None:
        """Dispatch child responses to their waiting requests until EOF."""
        while True:
            line = await reader.readline()
            if not line:
                break
            try:
                message = json.loads(line)
            except ValueError:
                logger.warning("bridge child emitted a non-JSON line: %r", line[:120])
                continue
            if not isinstance(message, dict):
                continue
            future = self.pending.get(str(message.get("id")))
            if future is None or future.done():
                continue
            if isinstance(message.get("error"), dict):
                error = message["error"]
                future.set_exception(
                    BridgeError(
                        int(error.get("code") or -32603),
                        str(error.get("message") or "MCP JSON-RPC error"),
                    )
                )
            else:
                future.set_result(message.get("result") or {})
        for future in self.pending.values():
            if not future.done():
                future.set_exception(BridgeError(-32603, "bridge child exited"))

    async def _notify(self, method: str) -> None:
        proc = self.proc
        if proc is None or proc.stdin is None:  # pragma: no cover — ensure() ran first
            raise BridgeError(-32603, "bridge child is not running")
        proc.stdin.write((json.dumps({"jsonrpc": "2.0", "method": method}) + "\n").encode())
        await proc.stdin.drain()

    async def _request(
        self, method: str, params: dict[str, Any], timeout_s: float
    ) -> dict[str, Any]:
        proc = self.proc
        if proc is None or proc.stdin is None:
            raise BridgeError(-32603, "bridge child is not running")
        request_id = uuid.uuid4().hex
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        try:
            proc.stdin.write((json.dumps(payload) + "\n").encode())
            await proc.stdin.drain()
            return await asyncio.wait_for(future, timeout_s)
        except TimeoutError:
            raise BridgeError(-32603, f"bridge child timed out after {timeout_s}s") from None
        finally:
            self.pending.pop(request_id, None)

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """One relayed request; a dead child is respawned once and retried."""
        await self.ensure()
        try:
            return await self._request(method, params, CALL_TIMEOUT_S)
        except BridgeError:
            if self.alive():  # a live child answered with an error — not a crash
                raise
            self.proc = None
            await self.ensure()
            return await self._request(method, params, CALL_TIMEOUT_S)


def _server_info(fleet_id: str) -> dict[str, Any]:
    return {"name": f"portal-stdio-bridge-{fleet_id}", "version": "1.0.0"}


async def _handle(
    fleet_id: str, child: StdioChild, method: str, params: dict[str, Any]
) -> dict[str, Any]:
    if method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if isinstance(requested, str) else LEGACY_PROTOCOL_VERSION
        return {
            "protocolVersion": version,
            "capabilities": {"tools": {}},
            "serverInfo": _server_info(fleet_id),
        }
    if method == "ping":
        return {}
    if method in ("tools/list", "tools/call"):
        return await child.request(method, params)
    raise BridgeError(-32601, f"unknown method {method}")


def build_app(fleet_id: str, argv: list[str] | None = None) -> Starlette:
    """The bridge app for one fleet id. ``argv`` overrides the fleet command."""
    child = StdioChild(argv or fleet_entry(fleet_id)[0])

    async def health(request: Request) -> JSONResponse:
        if not child.alive():
            return JSONResponse(
                {"status": "down", "service": f"stdio-bridge-{fleet_id}"}, status_code=503
            )
        proc = child.proc
        return JSONResponse(
            {"status": "ok", "service": f"stdio-bridge-{fleet_id}", "child_pid": proc and proc.pid}
        )

    async def mcp_endpoint(request: Request) -> Response:
        try:
            body: Any = await request.json()
        except ValueError:
            body = None
        if not isinstance(body, dict) or not isinstance(body.get("method"), str):
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32600, "message": "invalid request"},
                },
                status_code=400,
            )
        if "id" not in body:  # a notification needs no answer
            return Response(status_code=202)
        method = str(body["method"])
        raw_params = body.get("params")
        params = raw_params if isinstance(raw_params, dict) else {}
        try:
            result = await _handle(fleet_id, child, method, params)
        except BridgeError as exc:
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "error": {"code": exc.code, "message": str(exc)},
                }
            )
        return JSONResponse({"jsonrpc": "2.0", "id": body["id"], "result": result})

    async def supervisor() -> None:
        while True:
            try:
                await child.ensure()
            except Exception as exc:  # noqa: BLE001 — keep supervising a bad child
                logger.warning("bridge child startup failed: %s", exc)
            await asyncio.sleep(5)

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        task = asyncio.create_task(supervisor())
        try:
            yield
        finally:
            task.cancel()
            if child.proc is not None and child.proc.returncode is None:
                child.proc.kill()

    app = Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/mcp", mcp_endpoint, methods=["POST"]),
        ],
        lifespan=lifespan,
    )
    app.state.child = child
    return app


def main() -> None:
    fleet_id = os.environ.get("STDIO_MCP_BRIDGE_ID", "")
    if not fleet_id:
        raise SystemExit("STDIO_MCP_BRIDGE_ID is required (the fleet id to bridge)")
    argv, port = fleet_entry(fleet_id)
    logging.basicConfig(level=logging.INFO)
    logger.info("stdio bridge %s on :%d spawning %s", fleet_id, port, " ".join(argv))
    uvicorn.run(build_app(fleet_id, argv), host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
