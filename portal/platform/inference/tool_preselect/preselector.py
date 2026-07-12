"""Tool preselector — public interface (§3.3) and real logic (§4.2).

Public contract: ``preselect()`` never raises. Every error path falls
back to the full ``effective_tools`` set with an outcome reason —
this is the invariant that guarantees the feature can never regress
worse than "off": in the worst case it's a no-op plus a few ms.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import httpx

from portal.platform.inference.tool_preselect.config import (
    default_k,
    preselect_model,
    resolve_workspace_config,
)
from portal.platform.inference.tool_preselect.parser import (
    indices_to_tool_names,
    parse_ranked_indices,
)
from portal.platform.inference.tool_preselect.prompts import build_prompt

logger = logging.getLogger(__name__)

_TIMEOUT_S = 2.0
_KEEP_ALIVE = "5m"
_MAX_TOKENS = 200

_http_client: httpx.AsyncClient | None = None


def _client() -> httpx.AsyncClient:
    """Lazily-created shared client — connection reuse across calls.

    Self-contained (no lifespan wiring dependency) so preselect() is
    callable in isolation for the CLI probe and unit tests, per §4's
    "no pipeline integration yet" Phase 2 scope.
    """
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=httpx.Timeout(_TIMEOUT_S + 1.0))
    return _http_client


@dataclass
class PreselectOutcome:
    """Result metadata from one preselect() call.

    ``reason`` is one of the Prometheus outcome labels from §1.8:
    ok, fallback_timeout, fallback_lowconf, fallback_parse,
    fallback_empty, bypass_low_tools, bypass_disabled.
    """

    reason: str
    latency_ms: int


async def preselect(
    effective_tools: set[str],
    user_turn_content: str,
    workspace_id: str,
    workspace_config: dict,
    ollama_url: str = "http://localhost:11434",
) -> tuple[set[str], PreselectOutcome]:
    """Narrow ``effective_tools`` to the query-relevant subset.

    Returns (subset, outcome). ``subset`` is always a subset of
    ``effective_tools``. On any fallback path, ``subset ==
    effective_tools`` and ``outcome`` carries the fallback reason.

    Never raises. All errors caught -> fallback with outcome.
    """
    start = time.monotonic()

    def _elapsed_ms() -> int:
        return int((time.monotonic() - start) * 1000)

    # Step 1: opted-in?
    resolved = resolve_workspace_config(workspace_config, len(effective_tools))
    if resolved is None:
        return effective_tools, PreselectOutcome(reason="bypass_disabled", latency_ms=_elapsed_ms())

    # Step 2: too few tools for preselection to help.
    if len(effective_tools) <= 5:
        return effective_tools, PreselectOutcome(
            reason="bypass_low_tools", latency_ms=_elapsed_ms()
        )

    try:
        from portal.platform.inference.tool_registry import tool_registry

        tool_names_ordered = sorted(effective_tools)
        descriptions: dict[str, str] = {}
        for name in tool_names_ordered:
            tdef = tool_registry.get(name)
            descriptions[name] = tdef.description if tdef else ""

        k = resolved.k or default_k(len(effective_tools))
        slack = 3
        prompt = build_prompt(user_turn_content, tool_names_ordered, descriptions, k, slack)

        payload = {
            "model": preselect_model(),
            "prompt": prompt,
            "stream": False,
            "keep_alive": _KEEP_ALIVE,
            "options": {
                "temperature": 0.0,
                "top_p": 1.0,
                "top_k": 1,
                "num_predict": _MAX_TOKENS,
            },
        }

        resp = await asyncio.wait_for(
            _client().post(f"{ollama_url}/api/generate", json=payload),
            timeout=_TIMEOUT_S,
        )
        resp.raise_for_status()
        raw_response = resp.json().get("response", "")

        # Step 5: parse
        indices = parse_ranked_indices(raw_response, valid_max=len(tool_names_ordered))
        ranked_names = indices_to_tool_names(indices, tool_names_ordered)

        # Step 6: nothing parseable
        if len(ranked_names) < 1:
            return effective_tools, PreselectOutcome(
                reason="fallback_parse", latency_ms=_elapsed_ms()
            )

        # Step 7: confidence — too few valid results relative to K
        if len(ranked_names) < max(1, k // 2):
            return effective_tools, PreselectOutcome(
                reason="fallback_lowconf", latency_ms=_elapsed_ms()
            )

        # Step 8: success — top-K by rank
        subset = set(ranked_names[:k])
        return subset, PreselectOutcome(reason="ok", latency_ms=_elapsed_ms())

    except (TimeoutError, httpx.TimeoutException):
        logger.debug("preselect timeout ws=%s", workspace_id)
        return effective_tools, PreselectOutcome(
            reason="fallback_timeout", latency_ms=_elapsed_ms()
        )
    except httpx.HTTPError as e:
        logger.debug("preselect backend unavailable ws=%s: %s", workspace_id, e)
        return effective_tools, PreselectOutcome(
            reason="fallback_timeout", latency_ms=_elapsed_ms()
        )
    except Exception as e:
        # Never raises — any unexpected error is a full-set fallback.
        logger.debug("preselect unexpected error ws=%s: %s", workspace_id, e)
        return effective_tools, PreselectOutcome(reason="fallback_parse", latency_ms=_elapsed_ms())
