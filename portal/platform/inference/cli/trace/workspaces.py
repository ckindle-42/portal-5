"""Section 3 — every production seat, end to end, through the running Pipeline."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from .context import TraceContext
from .model import Hop, Status, short

PROMPT = "Reply with the single word OK."
MAX_TOKENS = 24


@dataclass(frozen=True)
class Seat:
    """One routable production seat: a workspace or one of its declared variants."""

    seat_id: str
    hint: str


@dataclass
class TurnStats:
    """What one streamed turn actually did."""

    ttft_s: float | None = None
    decode_tps: float | None = None
    completion_tokens: int | None = None
    prompt_tokens: int | None = None
    text: str = ""
    content_chunks: int = 0
    events: int = 0


@dataclass
class StreamedTurn:
    """A finished stream: stats plus the route the router chose."""

    status_code: int
    route: list[str] = field(default_factory=list)
    stats: TurnStats = field(default_factory=TurnStats)
    body: str = ""
    error: str = ""


def production_seats(portal: dict[str, Any]) -> list[Seat]:
    """Every non-bench workspace and declared variant, base before its variants."""
    seats: list[Seat] = []
    for workspace_id, cfg in (portal.get("workspaces") or {}).items():
        if str(workspace_id).startswith("bench"):
            continue
        hint = str((cfg or {}).get("model_hint") or "")
        if hint:
            seats.append(Seat(str(workspace_id), hint))
        for variant_id, variant in ((cfg or {}).get("variants") or {}).items():
            variant_hint = str((variant or {}).get("model_hint") or hint)
            if variant_hint:
                seats.append(Seat(f"{workspace_id}::{variant_id}", variant_hint))
    return seats


def parse_sse(line: str) -> dict[str, Any] | None:
    """One SSE ``data:`` payload as a dict; ``[DONE]``, comments and noise yield None."""
    text = line.strip()
    if not text.startswith("data:"):
        return None
    payload = text[5:].strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        parsed = json.loads(payload)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def summarize_turn(events: list[tuple[float, dict[str, Any]]]) -> TurnStats:
    """TTFT, decode rate and usage from timestamped stream chunks (times are seconds)."""
    stats = TurnStats(events=len(events))
    pieces: list[str] = []
    first: float | None = None
    last: float | None = None
    usage: dict[str, Any] = {}
    for at, chunk in events:
        frame = chunk.get("usage")
        if isinstance(frame, dict) and frame:
            usage = frame
        for choice in chunk.get("choices") or []:
            delta = (choice or {}).get("delta") or {}
            text = delta.get("content")
            if not text:
                continue
            if first is None:
                first = at
            last = at
            pieces.append(str(text))
    stats.text = "".join(pieces)
    stats.content_chunks = len(pieces)
    stats.ttft_s = first
    stats.completion_tokens = _int(usage.get("completion_tokens"))
    stats.prompt_tokens = _int(usage.get("prompt_tokens"))
    if first is not None and last is not None and stats.completion_tokens and last > first:
        stats.decode_tps = stats.completion_tokens / (last - first)
    return stats


def stream_turn(base_url: str, api_key: str, model: str, timeout_s: float) -> StreamedTurn:
    """One small streaming chat request; the router's own route header names what served it."""
    body = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "stream": True,
        "max_tokens": MAX_TOKENS,
        "stream_options": {"include_usage": True},
    }
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    timeout = httpx.Timeout(timeout_s, connect=min(10.0, timeout_s))
    try:
        with (
            httpx.Client(timeout=timeout) as client,
            client.stream(
                "POST", f"{base_url}/v1/chat/completions", headers=headers, json=body
            ) as response,
        ):
            route = str(response.headers.get("x-portal-route") or "").split(";")
            if response.status_code != 200:
                return StreamedTurn(
                    response.status_code, route, body=response.read().decode("utf-8", "replace")
                )
            start = time.monotonic()
            events = [
                (time.monotonic() - start, chunk)
                for chunk in (parse_sse(line) for line in response.iter_lines())
                if chunk is not None
            ]
    except httpx.HTTPError as exc:
        return StreamedTurn(0, error=f"{type(exc).__name__}: {exc}")
    return StreamedTurn(200, route, summarize_turn(events))


def _route_model(route: list[str]) -> str:
    return route[2] if len(route) > 2 else ""


def _served_hint(hint: str) -> set[str]:
    from portal.platform.inference.model_addressing import alias_targets_for_model

    return {hint, *alias_targets_for_model(hint)}


def _observed(turn: StreamedTurn) -> str:
    stats = turn.stats
    parts = [
        f"backend={turn.route[1] if len(turn.route) > 1 else '?'}",
        f"model={_route_model(turn.route) or '?'}",
    ]
    if stats.ttft_s is not None:
        parts.append(f"ttft={stats.ttft_s:.2f}s")
    parts.append(
        f"decode={stats.decode_tps:.1f}t/s" if stats.decode_tps is not None else "decode=?"
    )
    parts.append(f"tokens={stats.completion_tokens}")
    return " ".join(parts)


def seat_hop(seat: Seat, turn: StreamedTurn, hints: dict[str, str] | None = None) -> Hop:
    """One seat's verdict: refused, empty, usage-less or served with numbers attached."""
    name = seat.seat_id
    if turn.error:
        return Hop(name, Status.FAIL, short(turn.error, 70), "streamed turn")
    if turn.status_code == 507:
        return Hop(name, Status.FAIL, "refused 507", "loaded", short(turn.body, 70))
    if turn.status_code != 200:
        return Hop(name, Status.FAIL, f"http {turn.status_code}", "200", short(turn.body, 70))
    stats = turn.stats
    if stats.ttft_s is None:
        return Hop(name, Status.FAIL, "empty stream", "content + usage")
    # The router resolves lane seats before serving: `auto` routes by intent and
    # text-only `auto-vision` reroutes to auto-reasoning. The route header's first
    # field names the resolved workspace, whose own hint is then the expectation.
    resolved = turn.route[0].strip() if turn.route else ""
    rerouted = bool(resolved) and resolved != name
    expected = seat.hint
    if rerouted and hints and resolved in hints:
        expected = hints[resolved]
    observed = _observed(turn) + (f" via={resolved}" if rerouted else "")
    if not stats.completion_tokens:
        return Hop(name, Status.FAIL, observed + " usage=missing", "usage tokens")
    served = _route_model(turn.route)
    substituted = bool(served) and served not in _served_hint(expected)
    return Hop(
        name,
        Status.WARN if substituted else Status.PASS,
        observed,
        expected,
        "served model is not the resolved lane's seat or an alias of it" if substituted else "",
    )


def served_seat_ids(ctx: TraceContext) -> set[str]:
    """Workspace ids the running pipeline advertises; empty when the catalog cannot be read."""
    try:
        response = httpx.get(
            f"{ctx.pipeline_url}/v1/models",
            headers={"Authorization": f"Bearer {ctx.api_key}"} if ctx.api_key else {},
            timeout=15.0,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return set()
    if not isinstance(payload, dict):
        return set()
    return {
        str(entry["id"])
        for entry in payload.get("data") or []
        if isinstance(entry, dict) and entry.get("id")
    }


def disabled_seat(seat_id: str, served: set[str]) -> Hop | None:
    """A seat the stack does not advertise *and* config disables is skipped, not failed."""
    if seat_id in served:
        return None
    from portal.platform.wiki.adapters.modules import is_workspace_disabled

    if not is_workspace_disabled(seat_id):
        return None
    return Hop(
        seat_id,
        Status.PASS,
        "skipped: module disabled",
        "",
        "config/portal.yaml has this seat's module disabled (404 by design)",
    )


def run(ctx: TraceContext, portal: dict[str, Any]) -> list[Hop]:
    """Seats are exercised one at a time so cold loads never contend for host memory."""
    if not ctx.api_key:
        return [Hop("pipeline", Status.FAIL, "PIPELINE_API_KEY unset", "auth key")]
    deadline = time.monotonic() + ctx.budget_s
    served = served_seat_ids(ctx)
    hops: list[Hop] = []
    seats = production_seats(portal)
    hints = {seat.seat_id: seat.hint for seat in seats}
    for seat in seats:
        skipped = disabled_seat(seat.seat_id, served)
        if skipped is not None:
            hops.append(skipped)
            continue
        remaining = deadline - time.monotonic()
        if remaining <= 1:
            hops.append(Hop(seat.seat_id, Status.WARN, "not run (budget)", "streamed turn"))
            continue
        turn = stream_turn(
            ctx.pipeline_url, ctx.api_key, seat.seat_id, min(remaining, ctx.timeout_s)
        )
        hops.append(seat_hop(seat, turn, hints))
    if not hops:
        hops.append(Hop("workspaces", Status.FAIL, "no production seats", "config/portal.yaml"))
    return hops
