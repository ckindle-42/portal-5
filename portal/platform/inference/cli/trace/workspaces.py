"""Section 3 — every production seat, end to end, through the running Pipeline."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from portal.platform.inference.router.thinking import ThinkTagFilter

from . import engines
from .context import TraceContext
from .model import Hop, Status, short

PROMPT = "Reply with the single word OK."
#: Reasoning channels an engine streams beside answer content.
_REASONING_FIELDS = ("reasoning", "reasoning_content", "thinking")


@dataclass(frozen=True)
class Seat:
    """One routable production seat: a workspace or one of its declared variants.

    ``budget`` is the seat's declared output budget — the same cap the router
    applies to any request for it (``_output_cap`` on its merged config)."""

    seat_id: str
    hint: str
    budget: int


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
    reasoning_deltas: int = 0
    tool_deltas: int = 0
    usage_source: str = ""


@dataclass
class StreamedTurn:
    """A finished stream: stats plus the route the router chose."""

    status_code: int
    route: list[str] = field(default_factory=list)
    stats: TurnStats = field(default_factory=TurnStats)
    body: str = ""
    error: str = ""


def _seat_budget(ws: dict[str, Any], variant: dict[str, Any]) -> int:
    """The seat's declared output budget: the same cap the router applies to a request."""
    from portal.platform.inference.config import merge_workspace_variant
    from portal.platform.inference.router.validation import _output_cap

    return _output_cap(merge_workspace_variant(ws, variant))


def production_seats(portal: dict[str, Any]) -> list[Seat]:
    """Every non-bench workspace and declared variant, base before its variants."""
    seats: list[Seat] = []
    for workspace_id, cfg in (portal.get("workspaces") or {}).items():
        if str(workspace_id).startswith("bench"):
            continue
        base = cfg or {}
        hint = str(base.get("model_hint") or "")
        if hint:
            seats.append(Seat(str(workspace_id), hint, _seat_budget(base, {})))
        for variant_id, variant in (base.get("variants") or {}).items():
            variant_hint = str((variant or {}).get("model_hint") or hint)
            if variant_hint:
                seats.append(
                    Seat(
                        f"{workspace_id}::{variant_id}",
                        variant_hint,
                        _seat_budget(base, variant or {}),
                    )
                )
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
    think = ThinkTagFilter()
    for at, chunk in events:
        frame = chunk.get("usage")
        if isinstance(frame, dict) and frame:
            usage = frame
        for choice in chunk.get("choices") or []:
            delta = (choice or {}).get("delta") or {}
            if any(delta.get(name) for name in _REASONING_FIELDS):
                stats.reasoning_deltas += 1
            if delta.get("tool_calls"):
                stats.tool_deltas += 1
            text = delta.get("content")
            if not text:
                continue
            content = think.feed(str(text))
            if think.take_reasoning():
                # Inline ``<think>`` text is reasoning even when it reaches content.
                stats.reasoning_deltas += 1
            if not content:
                continue
            if first is None:
                first = at
            last = at
            pieces.append(content)
    stats.text = "".join(pieces)
    stats.content_chunks = len(pieces)
    stats.ttft_s = first
    stats.completion_tokens = _int(usage.get("completion_tokens"))
    stats.prompt_tokens = _int(usage.get("prompt_tokens"))
    stats.usage_source = str(usage.get("source") or "")
    if first is not None and last is not None and stats.completion_tokens and last > first:
        stats.decode_tps = stats.completion_tokens / (last - first)
    return stats


def stream_turn(
    base_url: str,
    api_key: str,
    model: str,
    timeout_s: float,
    path: str = "/v1/chat/completions",
    max_tokens: int | None = None,
    prompt: str = PROMPT,
    cid: str = "",
) -> StreamedTurn:
    """One small streaming chat request; the router's own route header names what served it.

    No ``max_tokens`` is sent: the router applies each seat's own declared output
    budget from config, so a verbose-but-healthy seat is graded, not starved."""
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if max_tokens is not None:
        body["max_tokens"] = max_tokens
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    if cid:
        headers["X-Correlation-ID"] = cid
    timeout = httpx.Timeout(timeout_s, connect=min(10.0, timeout_s))
    try:
        with (
            httpx.Client(timeout=timeout) as client,
            client.stream("POST", f"{base_url}{path}", headers=headers, json=body) as response,
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
    if stats.reasoning_deltas:
        parts.append(f"reasoning={stats.reasoning_deltas}")
    if stats.usage_source:
        parts.append(f"usage={stats.usage_source}")
    return " ".join(parts)


def _no_answer(stats: TurnStats) -> bool:
    """The turn reached the client without model answer content of its own."""
    from portal.platform.inference.router.thinking import NO_ANSWER_MESSAGE

    if stats.tool_deltas:
        return False
    text = stats.text.strip()
    return not text or text == NO_ANSWER_MESSAGE


def _no_answer_kind(stats: TurnStats) -> str:
    """Which silence this was: a turn spent on reasoning, or an engine that sent nothing."""
    if stats.reasoning_deltas:
        return f"reasoning-only ({stats.reasoning_deltas} reasoning deltas, no answer content)"
    return "no answer content (engine sent no content and no reasoning)"


def seat_hop(
    seat: Seat,
    turn: StreamedTurn,
    hints: dict[str, str] | None = None,
    budgets: dict[str, int] | None = None,
) -> Hop:
    """One seat's verdict: refused, empty, reasoning-only, usage-less or served with numbers."""
    name = seat.seat_id
    if turn.error:
        return Hop(name, Status.FAIL, short(turn.error, 70), "streamed turn")
    if turn.status_code == 507:
        return Hop(name, Status.FAIL, "refused 507", "loaded", short(turn.body, 70))
    if turn.status_code != 200:
        return Hop(name, Status.FAIL, f"http {turn.status_code}", "200", short(turn.body, 70))
    stats = turn.stats
    if stats.ttft_s is None and not stats.reasoning_deltas:
        return Hop(name, Status.FAIL, "empty stream", "content or reasoning + usage")
    # The router resolves lane seats before serving: `auto` routes by intent and
    # text-only `auto-vision` reroutes to auto-reasoning. The route header's first
    # field names the resolved workspace, whose own hint is then the expectation.
    resolved = turn.route[0].strip() if turn.route else ""
    rerouted = bool(resolved) and resolved != name
    expected = seat.hint
    if rerouted and hints:
        expected = hints.get(resolved, expected)
    observed = _observed(turn) + (f" via={resolved}" if rerouted else "")
    if _no_answer(stats):
        # The turn ran under the serving seat's own declared output budget (no client
        # cap): a turn that still ends inside reasoning is a seat that never answers.
        budget = (budgets or {}).get(resolved, seat.budget)
        detail = (
            f"no answer within its declared {budget}-token output budget; "
            "check the seat's think flag/template"
            if stats.reasoning_deltas
            else short(stats.text, 70) or "turn ended without answer content"
        )
        return Hop(
            name,
            Status.FAIL,
            f"{observed} {_no_answer_kind(stats)}",
            "answer content",
            detail,
        )
    if not stats.completion_tokens:
        missing = " usage=missing" if stats.completion_tokens is None else ""
        return Hop(name, Status.FAIL, observed + missing, "usage tokens", short(stats.text, 70))
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
    budgets = {seat.seat_id: seat.budget for seat in seats}
    confirmed: set[str] = set()
    for seat in seats:
        skipped = disabled_seat(seat.seat_id, served)
        if skipped is not None:
            hops.append(skipped)
            continue
        remaining = deadline - time.monotonic()
        # A budget sliver gave gemma4jangvision a ~1s ReadTimeout (2026-11-19): full timeout or skip.
        if remaining < ctx.timeout_s:
            hops.append(
                Hop(
                    seat.seat_id,
                    Status.WARN,
                    "not run (budget)",
                    "streamed turn",
                    f"{remaining:.0f}s left < {ctx.timeout_s:.0f}s per-turn timeout",
                )
            )
            continue
        turn = stream_turn(ctx.pipeline_url, ctx.api_key, seat.seat_id, ctx.timeout_s)
        hops.append(seat_hop(seat, turn, hints, budgets))
        served_model = turn.route[2] if len(turn.route) > 2 else ""
        if served_model and turn.stats.completion_tokens and turn.route[1] not in confirmed:
            confirmed.add(turn.route[1])
            hops.append(engines.residency_hop(ctx, turn.route[1], served_model))
    if not hops:
        hops.append(Hop("workspaces", Status.FAIL, "no production seats", "config/portal.yaml"))
    return hops
