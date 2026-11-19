"""Section — an Open WebUI turn reaches the Pipeline tool path and renders a closed receipt."""

from __future__ import annotations

import time

import httpx

from .context import TraceContext, env_value
from .model import Hop, Status, short
from .workspaces import StreamedTurn, stream_turn

WORKSPACE = "tools-specialist"
VALUE = "488895"
MARKER = "<details><summary>Tool results</summary>"
PROMPT = (
    "Use the execute_python tool exactly once with this code:\n"
    "print(sum(len(str(i)) for i in range(1, 100001)))\n"
    "Then reply with only the number it printed. Do not compute the number yourself."
)


def receipt_hop(turn: StreamedTurn) -> Hop:
    """The answer states the sandbox value under a closed receipt naming the tool that ran."""
    body, _, receipt = turn.stats.text.partition(MARKER)
    named, closed = "execute_python" in receipt, receipt.rstrip().endswith("</details>")
    ok = VALUE in body and named and closed
    observed = f"{VALUE}={VALUE in body} tool={named} closed={closed}"
    detail = "" if ok else short(turn.error or turn.body or turn.stats.text, 70)
    return Hop("owui tool receipt", Status.PASS if ok else Status.FAIL, observed, VALUE, detail)


def trace_hop(ctx: TraceContext, since: float) -> Hop:
    """The Pipeline's record of that turn: the seat it resolved, its backend and its tool call."""
    headers = {"Authorization": f"Bearer {ctx.api_key}"} if ctx.api_key else {}
    try:
        listing = httpx.get(f"{ctx.pipeline_url}/v1/trace", headers=headers, params={"limit": 10})
        records = listing.json()["data"]
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        return Hop("owui route trace", Status.WARN, "unread", "GET /v1/trace", str(exc)[:70])
    if not records:
        return Hop("owui route trace", Status.WARN, "empty trace store", "a trace record")
    recent = [
        row
        for row in records
        if row.get("workspace") == WORKSPACE and float(row.get("started_at") or 0) >= since - 5
    ]
    row = max(recent, key=lambda item: float(item.get("started_at") or 0)) if recent else {}
    calls = int(row.get("tool_calls") or 0)
    ok = bool(row.get("backend")) and row.get("outcome") == "complete" and calls >= 1
    observed = f"{row.get('backend')}/{row.get('model')} tool_calls={calls}"
    return Hop(
        "owui route trace", Status.PASS if ok else Status.FAIL, observed, f"{WORKSPACE} turn"
    )


def run(ctx: TraceContext, portal: dict[str, object]) -> list[Hop]:
    """One OWUI turn: user ingress must reach the Pipeline's tool loop, not just an engine."""
    key = env_value("OWUI_API_KEY")
    if not key:
        return [Hop("owui turn", Status.WARN, "not run: no OWUI_API_KEY", "an OWUI turn", "set it")]
    started = time.time()
    turn = stream_turn(
        ctx.owui_url,
        key,
        WORKSPACE,
        ctx.timeout_s,
        "/api/chat/completions",
        max_tokens=None,
    )
    return [receipt_hop(turn), trace_hop(ctx, started)]
