"""Event-driven streaming wait — shared across bench, UAT, and acceptance harnesses.

Design philosophy
-----------------
The wall-clock timeout is a CEILING, not the primary driver. A generation is judged
healthy or stuck by ACTIONABLE EVENTS, not elapsed time:

  * Primary signal — inter-token idle gap. While a stream is flowing, every received
    chunk resets an idle clock. If no chunk arrives within ``idle_gap_s`` the model has
    gone silent and the request is abandoned. This is implemented natively via
    ``httpx.Timeout(read=idle_gap_s)``: httpx raises ``ReadTimeout`` exactly when no
    bytes arrive within the read window, so the idle gap costs nothing to detect.

  * Secondary signal — model-loaded event. Before the first token, the model may be
    cold-loading. ``/api/ps`` is polled; the moment a model appears (or the first token
    arrives) Phase 1 ends. If neither happens within ``phase1_no_stream_s`` the cold
    load is treated as failed.

  * Ceiling — overall deadline. ``overall_ceiling_s`` bounds the absolute runtime as a
    last resort. Under healthy streaming it is never reached.

On a stall (idle gap or cold-load failure) the request is retried ONCE with a fresh
connection. If the retry also stalls, whatever partial text was received is returned
with ``StreamStatus.STALLED`` — callers map that to WARN, never a hard FAIL, because a
silent stream is not a wrong answer.

This is the HTTP/SSE counterpart of the browser-rendered tiered poll in
``tests/uat/browser.py`` (which watches the stop-button + DOM growth as its chunk
events). The two implementations are intentionally parallel; keep them in sync if the
philosophy changes.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum

import httpx

# ── Defaults (seeded from proven UAT/bench values; override per call) ──────────
IDLE_GAP_S: float = 45.0  # max seconds between chunks before "silent"
CONNECT_S: float = 10.0  # TCP connect timeout
PHASE1_NO_STREAM_S: float = 120.0  # max wait for first token / model-loaded (UAT NO_STREAM_TIMEOUT)
OVERALL_CEILING_S: float = 300.0  # absolute runtime ceiling (matches cold-load wait)
POLL_PS_S: float = 3.0  # /api/ps poll cadence during Phase 1
DEFAULT_OLLAMA_URL: str = "http://localhost:11434"


class StreamStatus(str, Enum):
    """Outcome of a streaming wait."""

    OK = "ok"  # stream completed normally ([DONE] or clean EOF)
    HTTP_ERROR = "http_error"  # non-200 status from the endpoint
    STALLED = "stalled"  # idle gap or cold-load failure after one retry → caller WARNs
    CEILING = "ceiling"  # overall wall-clock ceiling hit → caller WARNs
    CONN_ERROR = "conn_error"  # connection refused / protocol error → caller decides


@dataclass
class StreamResult:
    """Structured result of a streaming wait. Transport-only — no PASS/WARN vocabulary."""

    status: StreamStatus
    text: str = ""
    model: str = ""
    route: str = ""
    http_status: int = 0
    first_token_s: float | None = None  # time to first token (seconds)
    elapsed_s: float = 0.0
    chunks: int = 0
    retried: bool = False
    detail: str = ""
    raw_lines: list[str] = field(default_factory=list)  # only populated when capture_raw=True


async def _poll_model_loaded(ollama_url: str, deadline: float, poll_s: float) -> bool:
    """Return True the moment /api/ps reports a loaded model, or False at deadline."""
    while time.monotonic() < deadline:
        try:
            async with httpx.AsyncClient() as c:
                r = await c.get(f"{ollama_url}/api/ps", timeout=5)
            if r.status_code == 200 and r.json().get("models"):
                return True
        except Exception:
            pass
        await asyncio.sleep(poll_s)
    return False


def _parse_sse_delta(line: str) -> tuple[str, str, str]:
    """Parse one SSE 'data: {...}' line → (content_chunk, model, done_marker).

    Returns ("", "", "DONE") for the terminal [DONE] sentinel.
    Accumulates content, reasoning, and tool_call fragments so signal checks see
    everything the model produced.
    """
    if not line.startswith("data: "):
        return "", "", ""
    payload = line[6:]
    if payload == "[DONE]":
        return "", "", "DONE"
    try:
        obj = json.loads(payload)
    except Exception:
        return "", "", ""
    delta = obj.get("choices", [{}])[0].get("delta", {})
    chunk = delta.get("content") or ""
    chunk += delta.get("reasoning") or ""
    for tc in delta.get("tool_calls") or []:
        fn = tc.get("function", {}) if isinstance(tc, dict) else {}
        chunk += (fn.get("name") or "") + (fn.get("arguments") or "")
    return chunk, obj.get("model", ""), ""


async def _stream_once(
    *,
    client: httpx.AsyncClient,
    url: str,
    body: dict[str, object],
    headers: dict[str, str],
    idle_gap_s: float,
    connect_s: float,
    phase1_no_stream_s: float,
    overall_ceiling_s: float,
    poll_ps_s: float,
    ollama_url: str,
    capture_raw: bool,
) -> StreamResult:
    """One streaming attempt. ReadTimeout (idle gap) → STALLED; ceiling → CEILING."""
    start = time.monotonic()
    overall_deadline = start + overall_ceiling_s
    phase1_deadline = start + phase1_no_stream_s
    first_token_at: float | None = None
    text = ""
    model = ""
    chunks = 0
    raw: list[str] = []

    # read=idle_gap_s is the inter-chunk idle signal; httpx raises ReadTimeout
    # if no bytes arrive within that window. connect bounds the handshake.
    timeout = httpx.Timeout(connect=connect_s, read=idle_gap_s, write=connect_s, pool=connect_s)

    # Phase 1 cold-load watch runs concurrently with the request: if the model
    # is loading, /api/ps will flip to loaded; if it never does and no token
    # arrives, we fail Phase 1 rather than waiting the full read window repeatedly.
    ps_task = asyncio.ensure_future(_poll_model_loaded(ollama_url, phase1_deadline, poll_ps_s))

    try:
        async with client.stream("POST", url, json=body, headers=headers, timeout=timeout) as resp:
            route = resp.headers.get("x-portal-route", "")
            if resp.status_code != 200:
                err_body = (await resp.aread())[:200].decode(errors="replace")
                ps_task.cancel()
                return StreamResult(
                    status=StreamStatus.HTTP_ERROR,
                    http_status=resp.status_code,
                    route=route,
                    elapsed_s=round(time.monotonic() - start, 2),
                    detail=err_body[:120],
                )
            async for raw_line in resp.aiter_lines():
                if time.monotonic() > overall_deadline:
                    ps_task.cancel()
                    return StreamResult(
                        status=StreamStatus.CEILING,
                        text=text,
                        model=model,
                        route=route,
                        http_status=200,
                        first_token_s=first_token_at,
                        chunks=chunks,
                        elapsed_s=round(time.monotonic() - start, 2),
                        detail=f"overall ceiling {overall_ceiling_s}s hit",
                        raw_lines=raw,
                    )
                line = (
                    raw_line.strip()
                    if isinstance(raw_line, str)
                    else raw_line.decode(errors="replace").strip()
                )
                if capture_raw and line:
                    raw.append(line)
                chunk, chunk_model, done = _parse_sse_delta(line)
                if done == "DONE":
                    break
                if chunk and first_token_at is None:
                    first_token_at = round(time.monotonic() - start, 3)
                if chunk:
                    chunks += 1
                text += chunk
                if chunk_model and not model:
                    model = chunk_model
        ps_task.cancel()
        return StreamResult(
            status=StreamStatus.OK,
            text=text,
            model=model,
            route=route,
            http_status=200,
            first_token_s=first_token_at,
            chunks=chunks,
            elapsed_s=round(time.monotonic() - start, 2),
            raw_lines=raw,
        )
    except httpx.ReadTimeout:
        ps_task.cancel()
        # No bytes within idle_gap_s. If we never got a first token, this is a
        # Phase-1 cold-load stall; otherwise a Phase-2 mid-stream silence.
        phase = "pre-first-token (cold-load)" if first_token_at is None else "mid-stream"
        return StreamResult(
            status=StreamStatus.STALLED,
            text=text,
            model=model,
            http_status=200,
            first_token_s=first_token_at,
            chunks=chunks,
            elapsed_s=round(time.monotonic() - start, 2),
            detail=f"idle gap >{idle_gap_s}s ({phase})",
            raw_lines=raw,
        )
    except (httpx.ConnectError, httpx.RemoteProtocolError, httpx.ConnectTimeout) as e:
        ps_task.cancel()
        return StreamResult(
            status=StreamStatus.CONN_ERROR,
            text=text,
            model=model,
            elapsed_s=round(time.monotonic() - start, 2),
            detail=str(e)[:120],
            raw_lines=raw,
        )
    except Exception as e:  # noqa: BLE001 — transport boundary; surface as conn_error
        ps_task.cancel()
        return StreamResult(
            status=StreamStatus.CONN_ERROR,
            text=text,
            model=model,
            elapsed_s=round(time.monotonic() - start, 2),
            detail=str(e)[:120],
            raw_lines=raw,
        )


async def stream_chat(
    *,
    url: str,
    body: dict[str, object],
    headers: dict[str, str] | None = None,
    client: httpx.AsyncClient | None = None,
    idle_gap_s: float = IDLE_GAP_S,
    connect_s: float = CONNECT_S,
    phase1_no_stream_s: float = PHASE1_NO_STREAM_S,
    overall_ceiling_s: float = OVERALL_CEILING_S,
    poll_ps_s: float = POLL_PS_S,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    retry_on_stall: bool = True,
    capture_raw: bool = False,
) -> StreamResult:
    """Event-driven streaming chat request against an OpenAI-compatible SSE endpoint.

    The request body MUST set ``"stream": True``; this function does not mutate it
    (callers control model/messages/max_tokens). Returns a StreamResult; the caller maps
    status → its own PASS/WARN/FAIL vocabulary.

    On StreamStatus.STALLED with ``retry_on_stall=True`` the request is retried ONCE with
    a fresh connection before returning. CEILING and HTTP_ERROR are not retried.
    """
    headers = headers or {}
    own_client = client is None
    _actual_client: httpx.AsyncClient = client if client is not None else httpx.AsyncClient()
    try:
        result = await _stream_once(
            client=_actual_client,
            url=url,
            body=body,
            headers=headers,
            idle_gap_s=idle_gap_s,
            connect_s=connect_s,
            phase1_no_stream_s=phase1_no_stream_s,
            overall_ceiling_s=overall_ceiling_s,
            poll_ps_s=poll_ps_s,
            ollama_url=ollama_url,
            capture_raw=capture_raw,
        )
        if result.status is StreamStatus.STALLED and retry_on_stall:
            retry = await _stream_once(
                client=_actual_client,
                url=url,
                body=body,
                headers=headers,
                idle_gap_s=idle_gap_s,
                connect_s=connect_s,
                phase1_no_stream_s=phase1_no_stream_s,
                overall_ceiling_s=overall_ceiling_s,
                poll_ps_s=poll_ps_s,
                ollama_url=ollama_url,
                capture_raw=capture_raw,
            )
            retry.retried = True
            # Prefer the retry's outcome; if it produced more text, keep that.
            if retry.status is StreamStatus.OK or len(retry.text) >= len(result.text):
                return retry
            result.retried = True
            return result
        return result
    finally:
        if own_client:
            await _actual_client.aclose()
