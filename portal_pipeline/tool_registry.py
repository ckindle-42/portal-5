"""Tool registry — discovers model-facing tools from MCP servers and dispatches calls.

This module owns the mapping of ``tool_name → MCP server URL + JSON schema``
for every tool that a model can call from a chat completion. Three concerns
live here: discovery (poll each MCP's ``/tools`` endpoint), advertisement
(serialize to OpenAI ``tools:`` array), and dispatch (POST a tool call to
the right MCP and return its result).

A module-level singleton ``tool_registry = ToolRegistry()`` is created at
import time and is the single instance used by ``router_pipe.py``. Discovery
runs lazily on the first ``refresh()`` (called during chat-completion
handling) and on demand via ``POST /admin/refresh-tools``.

``MCP_SERVERS`` is intentionally not the full MCP fleet. Only servers whose
tools are meant to be model-callable are listed here. The reranker MCP
(:8925) and the browser MCP (:8923) are absent because they are internal
infrastructure — the reranker is invoked directly by the RAG MCP with
graceful fallback, and browser actions are wrapped behind ``research``/web
search tools rather than exposed as raw tools.

Failure isolation is by design throughout: discovery failures for one MCP
do not affect others, and ``dispatch`` returns error dicts rather than
raising so a tool failure cannot break the SSE stream feeding the model.

Knobs (all env-overridable):

* ``TOOL_REGISTRY_REFRESH_S`` (default 3600s) — refresh interval.
* ``TOOL_DISCOVERY_TIMEOUT_S`` (5s, not overridable) — per-server
  ``/tools`` GET timeout.
* ``TOOL_DISPATCH_TIMEOUT_S`` (default 60s) — per-call POST timeout,
  overridable per-tool via ``ToolDefinition.custom_timeout_s``.
* Per-server ``MCP_<NAME>_URL`` — override the default ``localhost:<port>``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from portal_pipeline.config import get_pipeline_mcp_servers, load_portal_config

logger = logging.getLogger(__name__)

# MCP server base URLs — derived from portal.yaml fleet table (M1 migration).
# Env vars MCP_<ID_UPPER>_URL still override individual entries as before.
# The hand-maintained dict below was replaced by the fleet table in portal.yaml;
# this one-liner produces the identical runtime value.
MCP_SERVERS: dict[str, str] = get_pipeline_mcp_servers(load_portal_config())

TOOL_REGISTRY_REFRESH_S = float(os.environ.get("TOOL_REGISTRY_REFRESH_S", "3600"))
TOOL_DISCOVERY_TIMEOUT_S = 5.0
TOOL_DISPATCH_TIMEOUT_S = float(os.environ.get("TOOL_DISPATCH_TIMEOUT_S", "60"))


def _backoff_seconds(failures: int) -> float:
    """Look up the backoff window for a tool with ``failures`` consecutive errors.

    Hand-picked schedule (seconds): ``30, 120, 300, 900, 3600`` — capped at
    1h. Failures beyond the fifth stay at 1h, matching the default registry
    refresh cadence so a permanently-broken tool gets re-probed by discovery
    on roughly the same beat as by post-backoff retry.

    Args:
        failures: Consecutive-failure count, 1-indexed. Values < 1 return
            the first slot (30s); values beyond the schedule clamp to 1h.

    Returns:
        Backoff window in seconds.
    """
    schedule = [30, 120, 300, 900, 3600]
    return float(schedule[min(failures - 1, len(schedule) - 1)])


@dataclass
class ToolDefinition:
    """One discovered tool, with attached circuit-breaker state.

    Constructed exclusively by ``ToolRegistry.refresh`` from the
    ``/tools`` response of an MCP server. The first five fields describe
    the tool itself; the last four track its dispatch history so the
    registry can apply backoff.

    State fields live on this object (rather than a parallel map keyed
    by tool name) so ``refresh`` can preserve circuit-breaker state with
    a straight field copy when a tool re-appears in a later discovery
    cycle. Without that preservation, a flapping MCP would escape its
    penalty box every refresh.

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

        Returns the canonical ``{"type": "function", "function": {...}}`` shape
        that is splatted into the outgoing chat-completions request body in
        ``router_pipe.chat_completions``. Drops all circuit-breaker state —
        only the model-facing fields (``name``, ``description``,
        ``parameters``) are included.
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

    Singleton by convention — the module-level ``tool_registry`` instance
    (line 229) is the only one imported by ``router_pipe.py``. Constructing
    another instance is legal but pointless: it would have its own empty
    ``_tools`` dict and HTTP client.

    Concurrency:

    * ``_refresh_lock`` serializes ``refresh()`` so a manual
      ``POST /admin/refresh-tools`` racing a chat-completion's lazy refresh
      can't lose circuit-breaker state via last-write-wins.
    * One shared ``httpx.AsyncClient`` is used for both discovery (5s
      timeout) and dispatch (60s+ via per-call override). It is created
      lazily in ``_client`` and must be closed via ``close()`` on shutdown.

    Failure isolation:

    * Discovery failures for one MCP do not affect others
      (``asyncio.gather(..., return_exceptions=True)``).
    * Dispatch never raises — every failure path returns an error dict,
      because the caller feeds the result back to the model as a ``tool``
      role message and an uncaught exception would break the SSE stream.
    """

    def __init__(self) -> None:
        """Initialize an empty registry; no network calls.

        Construction is side-effect-free — the first ``refresh()`` call is
        what actually discovers tools. This is what makes the module-level
        ``tool_registry = ToolRegistry()`` at import time safe in tests and
        CI where MCP servers may not be reachable.
        """
        self._tools: dict[str, ToolDefinition] = {}
        self._last_refresh: float = 0.0
        self._refresh_lock = asyncio.Lock()
        self._http: httpx.AsyncClient | None = None

    async def _client(self) -> httpx.AsyncClient:
        """Return the shared HTTP client, creating it if missing or closed.

        The ``is_closed`` check lets the registry recover transparently if
        ``close()`` was called and then a discovery or dispatch happens again
        — a sequence that occurs in test teardown / reuse but not in normal
        production lifecycle. Client timeout defaults to
        ``TOOL_DISCOVERY_TIMEOUT_S`` (5s); ``dispatch`` overrides per-call.
        """
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=TOOL_DISCOVERY_TIMEOUT_S)
        return self._http

    async def refresh(self, force: bool = False) -> int:
        """Rediscover tools from every MCP in ``MCP_SERVERS``.

        Behaviour beyond the bare description:

        * **Rate-limited**: refreshes are no-ops if the last one was less than
          ``TOOL_REGISTRY_REFRESH_S`` ago (default 1h). A lockless fast-path
          checks the TTL before acquiring ``_refresh_lock``; callers inside the
          window return immediately without contending. A second check under the
          lock ensures only the first of any concurrent expiries does work.
          ``force=True`` bypasses the TTL (used by ``POST /admin/refresh-tools``).
        * **Parallel discovery**: all MCPs are probed concurrently via
          ``asyncio.gather(..., return_exceptions=True)``. One MCP being
          down does not block discovery of others.
        * **Circuit-breaker state is preserved across refreshes** for tools
          that re-appear: ``healthy``, ``consecutive_failures``, and
          ``next_retry_at`` are copied forward from the previous
          ``ToolDefinition``. Without this, a tool would escape its backoff
          window every refresh cycle.
        * **New tools** (not present in the previous registry) start with
          default state — healthy, zero failures, no pending retry.
        * **Tools that disappear** from a server's ``/tools`` response are
          silently dropped; the next dispatch attempt returns
          ``"Tool '...' not in registry"``.

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
                    for tdef in tools:
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
        """Return every registered tool name, sorted alphabetically.

        Used by ``POST /admin/refresh-tools`` as part of its JSON response so
        operators can verify which tools came through after a manual refresh.
        """
        return sorted(self._tools.keys())

    def get_openai_tools(self, names: list[str]) -> list[dict[str, Any]]:
        """Build the OpenAI ``tools:[]`` array from ``names``, skipping cool-down tools.

        For each name in ``names`` (typically a persona's effective tool list,
        resolved in ``portal_pipeline/router/workspaces.py``), include the
        tool **only if** it's healthy OR its backoff window has elapsed.
        Re-admission while still ``healthy == False`` is intentional: the
        next ``dispatch`` is what flips the tool back to healthy on success.
        Without this re-admission, a tool would only recover via the next
        ``refresh`` (hourly by default).

        Unknown names (not in the registry) are silently skipped — they're
        typically persona configs referencing tools whose source MCP is
        currently unreachable. The persona itself is still advertised to the
        model, just without those tools.

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

        **Never raises.** Every failure path — unknown tool, in cool-down, HTTP
        non-200, timeout, network error, JSON decode failure — returns an
        ``{"error": "..."}`` dict. This contract is load-bearing: the caller
        in ``router_pipe.py`` JSON-encodes the result directly into a ``tool``
        role message that gets streamed back to the model mid-completion, and
        a raised exception there would break the SSE stream.

        Circuit-breaker behaviour:

        * Tools in cool-down (``healthy=False`` AND ``time.time() <
          next_retry_at``) **do not get a network call** — the error returns
          immediately. This is what keeps a broken MCP from being hammered.
        * A 200 response resets ``healthy=True``, ``consecutive_failures=0``,
          ``next_retry_at=0`` regardless of prior state.
        * Any non-success (HTTP non-200, timeout, exception) increments
          ``consecutive_failures`` and recomputes ``next_retry_at`` via
          ``_backoff_seconds``.

        Timeout: ``tool.custom_timeout_s`` if set, else
        ``TOOL_DISPATCH_TIMEOUT_S`` (60s default; env-overridable).

        Args:
            tool_name: Must match a key in ``self._tools``. Unknown names
                return ``{"error": "Tool '...' not in registry ..."}``.
            arguments: JSON-serialisable kwargs forwarded as the ``arguments``
                field of the POST body. The MCP server is responsible for
                schema validation.
            request_id: Opaque request correlator forwarded as the
                ``request_id`` field so MCP logs can be cross-referenced
                with pipeline logs. May be empty.

        Returns:
            Either the MCP's parsed JSON response (success) or an
            ``{"error": "...", "detail"?: "..."}`` dict (any failure mode).
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

        The ``is_closed`` guard makes this idempotent so multiple shutdown
        hooks can call it. After close, ``_client`` will lazily create a
        fresh client if the registry is reused (test pattern; in production
        close happens at process exit).
        """
        if self._http is not None and not self._http.is_closed:
            await self._http.aclose()
            self._http = None


# Module-level singleton — pipeline imports this and uses it
tool_registry = ToolRegistry()
