"""Tool registry — discovers model-facing tools from MCP servers and dispatches calls.

Maps ``tool_name → MCP server URL + JSON schema`` for every model-callable tool:
discovery (poll each MCP's ``/tools`` endpoint), advertisement (serialize to the
OpenAI ``tools:`` array), and dispatch (POST a tool call and return its result).

A module-level singleton ``tool_registry = ToolRegistry()`` is used by
``router_pipe.py``; discovery runs lazily on the first ``refresh()`` and on
demand via ``POST /admin/refresh-tools``.

``MCP_SERVERS`` is not the full fleet — internal infrastructure (reranker :8925,
browser :8923) is excluded. Failure isolation is by design: one MCP's discovery
failure doesn't affect others, and ``dispatch`` returns error dicts rather than
raising so a tool failure can't break the SSE stream.

Knobs (env-overridable): ``TOOL_REGISTRY_REFRESH_S`` (3600s refresh interval),
``TOOL_DISPATCH_TIMEOUT_S`` (60s per-call POST timeout, overridable per-tool via
``ToolDefinition.custom_timeout_s``), and per-server ``MCP_<NAME>_URL``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from portal.platform.inference.config import get_pipeline_mcp_servers, load_portal_config

logger = logging.getLogger(__name__)

# MCP server base URLs — derived from the portal.yaml fleet table; env vars
# MCP_<ID_UPPER>_URL override individual entries.
MCP_SERVERS: dict[str, str] = get_pipeline_mcp_servers(load_portal_config())

TOOL_REGISTRY_REFRESH_S = float(os.environ.get("TOOL_REGISTRY_REFRESH_S", "3600"))
TOOL_DISCOVERY_TIMEOUT_S = 5.0
TOOL_DISPATCH_TIMEOUT_S = float(os.environ.get("TOOL_DISPATCH_TIMEOUT_S", "60"))


def _backoff_seconds(failures: int) -> float:
    """Backoff window in seconds for ``failures`` consecutive errors.

    Schedule: ``30, 120, 300, 900, 3600`` — capped at 1h.

    Args:
        failures: Consecutive-failure count, 1-indexed. Values < 1 return
            the first slot; values beyond the schedule clamp to 1h.

    Returns:
        Backoff window in seconds.
    """
    schedule = [30, 120, 300, 900, 3600]
    return float(schedule[min(failures - 1, len(schedule) - 1)])


@dataclass
class ToolDefinition:
    """One discovered tool, with attached circuit-breaker state.

    Constructed by ``ToolRegistry.refresh`` from an MCP's ``/tools`` response.
    The first five fields describe the tool; the rest track dispatch history so
    the registry can apply backoff. State lives on this object so ``refresh``
    can preserve it with a field copy when a tool re-appears — without that, a
    flapping MCP would escape its penalty box every refresh.

    Attributes:
        name: Unique tool name; matches the key in ``ToolRegistry._tools``.
        description: Human-readable description fed verbatim to models via
            ``to_openai_tool``.
        parameters: OpenAI/JSON-Schema-shaped parameters object.
        server_id: Stable id of the source MCP (a key in ``MCP_SERVERS``).
        server_url: Base URL the tool is dispatched against.
        last_seen: Monotonic time of the last successful discovery.
        healthy: ``False`` after any failed dispatch. Re-set to ``True``
            on the next successful dispatch.
        custom_timeout_s: Per-tool dispatch timeout override. Currently
            unpopulated by any MCP's ``/tools`` response — reserved for
            tools that need longer than ``TOOL_DISPATCH_TIMEOUT_S`` (60s
            default; insufficient for video / music generation).
        next_retry_at: Epoch seconds. While ``healthy`` is False and
            ``time.time() < next_retry_at``, the tool is filtered out of
            ``get_openai_tools`` and ``dispatch`` returns an error
            without contacting the MCP.
        consecutive_failures: Drives the ``_backoff_seconds`` lookup.
    """

    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema
    server_id: str
    server_url: str
    last_seen: float = 0.0
    healthy: bool = True
    custom_timeout_s: float | None = None  # override TOOL_DISPATCH_TIMEOUT_S
    next_retry_at: float = 0.0  # epoch seconds; 0 = retry allowed immediately
    consecutive_failures: int = 0  # for exponential backoff calc

    def to_openai_tool(self) -> dict[str, Any]:
        """Render as one entry of an OpenAI-format ``tools`` array.

        Returns ``{"type": "function", "function": {...}}`` with only the
        model-facing fields (``name``, ``description``, ``parameters``);
        circuit-breaker state is dropped.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Discovers tools from MCP servers and dispatches calls to them.

    Singleton by convention — the module-level ``tool_registry`` instance is the
    only one used by ``router_pipe.py``.

    Concurrency: ``_refresh_lock`` serializes ``refresh()`` so a manual refresh
    racing a lazy refresh can't lose circuit-breaker state. One shared
    ``httpx.AsyncClient`` (lazily created in ``_client``) serves discovery and
    dispatch; close it via ``close()`` on shutdown.

    Failure isolation: one MCP's discovery failure doesn't affect others
    (``asyncio.gather(..., return_exceptions=True)``); dispatch never raises —
    every failure path returns an error dict so the SSE stream feeding the model
    survives.
    """

    def __init__(self) -> None:
        """Initialize an empty registry; no network calls.

        Side-effect-free construction — the first ``refresh()`` discovers
        tools — makes the import-time ``tool_registry = ToolRegistry()`` safe in
        tests and CI where MCP servers may not be reachable.
        """
        self._tools: dict[str, ToolDefinition] = {}
        self._last_refresh: float = 0.0
        self._refresh_lock = asyncio.Lock()
        self._http: httpx.AsyncClient | None = None

    async def _client(self) -> httpx.AsyncClient:
        """Return the shared HTTP client, creating it if missing or closed.

        Recovers transparently if ``close()`` was called and the registry is
        reused (test teardown). Client timeout defaults to
        ``TOOL_DISCOVERY_TIMEOUT_S``; ``dispatch`` overrides per-call.
        """
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=TOOL_DISCOVERY_TIMEOUT_S)
        return self._http

    async def refresh(self, force: bool = False) -> int:
        """Rediscover tools from every MCP in ``MCP_SERVERS``.

        Rate-limited: refreshes are no-ops within ``TOOL_REGISTRY_REFRESH_S`` of
        the last one (checked lockless, re-checked under ``_refresh_lock``);
        ``force=True`` bypasses the TTL. Discovery is parallel via
        ``asyncio.gather(..., return_exceptions=True)``. Circuit-breaker state is
        preserved across refreshes for tools that re-appear; new tools start
        healthy; tools that disappear from a server's ``/tools`` response are
        dropped (next dispatch returns ``"Tool '...' not in registry"``).

        Args:
            force: When ``True``, run discovery regardless of the TTL.

        Returns:
            Number of tools currently registered after the refresh.
        """
        # Lockless fast path — TTL check without acquiring _refresh_lock.
        # Under CPython the GIL guarantees a coherent read of _last_refresh
        # and _tools; both are only mutated together at successful-refresh
        # finish under the lock, so a stale-but-consistent read is safe.
        if not force and time.time() - self._last_refresh < TOOL_REGISTRY_REFRESH_S:
            return len(self._tools)

        async with self._refresh_lock:
            # Re-check under the lock: concurrent callers can both pass the
            # lockless check; only the first should do the work.
            now = time.time()
            if not force and now - self._last_refresh < TOOL_REGISTRY_REFRESH_S:
                return len(self._tools)

            client = await self._client()
            new_tools: dict[str, ToolDefinition] = {}
            succeeded_servers: set[str] = set()

            async def _discover_one(server_id: str, base_url: str) -> None:
                """Fetch and parse one MCP server's ``/tools`` endpoint."""
                try:
                    r = await client.get(f"{base_url.rstrip('/')}/tools")
                    if r.status_code != 200:
                        logger.warning("Tool discovery: %s returned %d", server_id, r.status_code)
                        return
                    succeeded_servers.add(server_id)
                    payload = r.json()
                    tools = payload if isinstance(payload, list) else payload.get("tools", [])
                    for raw in tools:
                        # Most `/tools` manifests are flat
                        # ({"name", "description", "parameters"}); at least
                        # one server's (compliance) uses the OpenAI-wrapped
                        # shape ({"type": "function", "function": {...}}).
                        # Unwrap so this one server's convention doesn't
                        # silently drop every one of its tools from
                        # discovery (found live, P8-L: get_openai_tools(
                        # ["nerc_cip_requirement"]) returned [] even though
                        # the server's /tools endpoint listed it).
                        tdef = raw["function"] if isinstance(raw.get("function"), dict) else raw
                        name = tdef.get("name")
                        if not name:
                            continue
                        new_tools[name] = ToolDefinition(
                            name=name,
                            description=tdef.get("description", ""),
                            parameters=tdef.get("parameters", {}),
                            server_id=server_id,
                            server_url=base_url,
                            last_seen=now,
                            custom_timeout_s=float(tdef["timeout_s"])
                            if tdef.get("timeout_s")
                            else None,
                        )
                except Exception as e:
                    logger.warning("Tool discovery for %s failed: %s", server_id, e)

            await asyncio.gather(
                *[_discover_one(sid, url) for sid, url in MCP_SERVERS.items()],
                return_exceptions=True,
            )

            # Preserve tools from servers that failed discovery
            for sid in MCP_SERVERS:
                if sid not in succeeded_servers:
                    carried = 0
                    for name, tool in self._tools.items():
                        if tool.server_id == sid:
                            new_tools[name] = ToolDefinition(
                                name=tool.name,
                                description=tool.description,
                                parameters=tool.parameters,
                                server_id=tool.server_id,
                                server_url=tool.server_url,
                                last_seen=tool.last_seen,
                                healthy=tool.healthy,
                                custom_timeout_s=tool.custom_timeout_s,
                                next_retry_at=tool.next_retry_at,
                                consecutive_failures=tool.consecutive_failures,
                            )
                            carried += 1
                    if carried:
                        logger.warning(
                            "discovery failed for %s — retaining %d previously-known tools",
                            sid,
                            carried,
                        )

            # Preserve backoff state from previous tools that re-appeared
            for name, tool in new_tools.items():
                if name in self._tools:
                    prev = self._tools[name]
                    tool.healthy = prev.healthy
                    tool.consecutive_failures = prev.consecutive_failures
                    tool.next_retry_at = prev.next_retry_at

            self._tools = new_tools
            self._last_refresh = now
            logger.info(
                "Tool registry refreshed: %d tools across %d servers",
                len(self._tools),
                len(MCP_SERVERS),
            )
            return len(self._tools)

    def get(self, name: str) -> ToolDefinition | None:
        """Look up a tool by name; ``None`` if not in the registry."""
        return self._tools.get(name)

    def list_tool_names(self) -> list[str]:
        """Return every registered tool name, sorted alphabetically."""
        return sorted(self._tools.keys())

    def get_openai_tools(self, names: list[str]) -> list[dict[str, Any]]:
        """Build the OpenAI ``tools:[]`` array from ``names``, skipping cool-down tools.

        Include a tool only if healthy or its backoff window has elapsed.
        Re-admission while ``healthy == False`` is intentional: the next
        ``dispatch`` flips it back to healthy on success. Unknown names are
        silently skipped — the persona is still advertised, just without those
        tools.

        Args:
            names: Tool names to advertise. Order is preserved in the output.

        Returns:
            List of OpenAI-format tool dicts. May be shorter than ``names``.
        """
        now = time.time()
        result = []
        for n in names:
            t = self._tools.get(n)
            if t is None:
                continue
            if t.healthy or now >= t.next_retry_at:
                result.append(t.to_openai_tool())
        return result

    async def dispatch(
        self, tool_name: str, arguments: dict[str, Any], request_id: str = ""
    ) -> dict[str, Any]:
        """Dispatch a tool call to its source MCP; return the result or an error dict.

        Never raises — every failure path (unknown tool, cool-down, HTTP
        non-200, timeout, network error, JSON decode failure) returns
        ``{"error": "..."}``. The caller JSON-encodes the result into a
        ``tool`` role message streamed back to the model, so a raised
        exception would break the SSE stream.

        Circuit-breaker behaviour: tools in cool-down (``healthy=False`` AND
        ``time.time() < next_retry_at``) return an error without a network
        call; a 200 resets ``healthy=True``, ``consecutive_failures=0``,
        ``next_retry_at=0``; any non-success increments
        ``consecutive_failures`` and recomputes ``next_retry_at`` via
        ``_backoff_seconds``. Timeout: ``tool.custom_timeout_s`` if set, else
        ``TOOL_DISPATCH_TIMEOUT_S``.

        Args:
            tool_name: Must match a key in ``self._tools``. Unknown names
                return an error dict.
            arguments: JSON-serialisable kwargs forwarded as the ``arguments``
                field of the POST body; the MCP validates the schema.
            request_id: Opaque request correlator forwarded as ``request_id``
                so MCP logs can be cross-referenced with pipeline logs. May be
                empty.

        Returns:
            The MCP's parsed JSON response (success) or an error dict.
        """
        tool = self.get(tool_name)
        if tool is None:
            return {"error": f"Tool '{tool_name}' not in registry — call ignored"}

        now = time.time()
        if not tool.healthy and now < tool.next_retry_at:
            remaining = int(tool.next_retry_at - now)
            return {
                "error": f"Tool '{tool_name}' in backoff (retry in {remaining}s after "
                f"{tool.consecutive_failures} consecutive failures)"
            }

        timeout_s = tool.custom_timeout_s or TOOL_DISPATCH_TIMEOUT_S
        url = f"{tool.server_url.rstrip('/')}/tools/{tool_name}"

        try:
            client = await self._client()
            r = await client.post(
                url,
                json={"arguments": arguments, "request_id": request_id},
                timeout=timeout_s,
            )
            if r.status_code == 200:
                tool.healthy = True
                tool.consecutive_failures = 0
                tool.next_retry_at = 0.0
                return r.json()
            else:
                tool.consecutive_failures += 1
                tool.healthy = False
                tool.next_retry_at = now + _backoff_seconds(tool.consecutive_failures)
                return {
                    "error": f"Tool '{tool_name}' returned HTTP {r.status_code}",
                    "detail": r.text[:200],
                }
        except (TimeoutError, httpx.TimeoutException):
            tool.consecutive_failures += 1
            tool.healthy = False
            tool.next_retry_at = now + _backoff_seconds(tool.consecutive_failures)
            return {"error": f"Tool '{tool_name}' timed out after {timeout_s}s"}
        except Exception as e:
            tool.consecutive_failures += 1
            tool.healthy = False
            tool.next_retry_at = now + _backoff_seconds(tool.consecutive_failures)
            return {"error": f"Tool '{tool_name}' dispatch failed: {e}"}

    async def close(self) -> None:
        """Close the shared HTTP client; safe to call multiple times.

        Idempotent via the ``is_closed`` guard so multiple shutdown hooks can
        call it. After close, ``_client`` lazily creates a fresh client if the
        registry is reused (test pattern; in production close happens at exit).
        """
        if self._http is not None and not self._http.is_closed:
            await self._http.aclose()
            self._http = None


# Module-level singleton — pipeline imports this and uses it
tool_registry = ToolRegistry()
