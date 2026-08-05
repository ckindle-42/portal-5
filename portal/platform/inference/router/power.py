"""Powermetrics polling, energy accounting, and per-request usage recording.

Reads the host powermetrics socket, converts watt-seconds to USD, and records
token/energy usage into the metrics collectors. Depends on
``portal.platform.inference.router.metrics`` and ``portal.platform.inference.router.state``;
never imports router_pipe.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import time

import portal.platform.inference.router.state as _state_mod
from portal.platform.inference.router.metrics import (
    _energy_consumed_ws_total,
    _input_tokens,
    _output_tokens,
    _power_ane_watts,
    _power_avg_1min_watts,
    _power_cpu_watts,
    _power_current_watts,
    _power_dram_watts,
    _power_gpu_watts,
    _requests_by_model,
    _tokens_per_second,
)

logger = logging.getLogger(__name__)

_POWERMETRICS_SOCKET = "/tmp/portal5-powermetrics.sock"
ELECTRICITY_RATE_USD_PER_KWH = float(os.environ.get("ELECTRICITY_RATE_USD_PER_KWH", "0.15"))


async def _power_polling_loop():
    """Background task: poll the host powermetrics daemon every 10s; update gauges.

    The pipeline doesn't shell out to ``powermetrics`` (no root in the
    container; macOS-only). A launchd daemon (``scripts/portal5-powermetrics.py``)
    runs as root on the host and republishes JSON-per-line on the Unix socket at
    ``/tmp/portal5-powermetrics.sock``. This task connects, reads one line,
    updates the ``_power_*_watts`` gauges and ``_energy_consumed_ws_total``, then
    closes the connection.

    Degrades silently when the daemon isn't running (socket connect raises
    ``FileNotFoundError``, caught, retried next tick). Energy elapsed time uses
    the daemon's reported timestamp (``state["ts"]``), not local ``time.time()``,
    so daemon cadence jitter doesn't bias energy attribution.

    Started by ``lifespan``; runs for the process lifetime. All failures are
    swallowed — acceptable for a telemetry-only loop.
    """
    last_poll = time.time()
    while True:
        try:
            reader, writer = await asyncio.open_unix_connection(_POWERMETRICS_SOCKET)
            data = await reader.readline()
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            state = json.loads(data.decode())
            now = state.get("ts", time.time())
            elapsed = now - last_poll
            last_poll = now
            current_w = state.get("current_w", 0.0)
            _power_current_watts.set(current_w)
            _power_cpu_watts.set(state.get("cpu_w", 0.0))
            _power_gpu_watts.set(state.get("gpu_w", 0.0))
            _power_ane_watts.set(state.get("ane_w", 0.0))
            _power_dram_watts.set(state.get("dram_w", 0.0))
            _power_avg_1min_watts.set(state.get("avg_1min_w", 0.0))
            _energy_consumed_ws_total.inc(current_w * elapsed)
        except FileNotFoundError:
            pass  # powermetrics daemon not running — degrade gracefully
        except Exception:
            logger.debug("Power poller error — skipping this tick", exc_info=True)
        await asyncio.sleep(10)


def _record_usage(
    model: str, workspace: str, data: dict, elapsed_seconds: float | None = None
) -> None:
    """Extract token counts and TPS from a backend response dict; record to metrics.

    Shape-tolerant: missing fields are skipped, never raised. Handles four
    response shapes: Ollama top-level (``eval_count``, ``prompt_eval_count``,
    ``eval_duration`` ns), Ollama nested under ``usage:``, OpenAI top-level
    (``completion_tokens``, ``prompt_tokens``), OpenAI nested in ``usage``.

    TPS preference: ``eval_duration_ns`` (Ollama's model compute time, no
    network jitter), then ``elapsed_seconds`` (wall clock from the streaming
    caller), then skipped (token counts still recorded). Updates the Prometheus
    collectors and the daily-summary aggregates (``_total_tps``,
    ``_total_input_tokens``, etc.); ``bench-*`` traffic is excluded from the
    daily-summary TPS (cold model loads inflate wall-clock TPS).

    Bare ``except Exception`` swallows failures — a malformed payload must not
    crash a successful request's metric path.

    Args:
        model: Concrete model id (post-``model_hint`` resolution).
        workspace: Workspace id from the request.
        data: The backend's response dict, in any of the four shapes above.
        elapsed_seconds: Wall-clock elapsed time from the streaming caller;
            ``None`` from non-streaming callers (they rely on ``eval_duration``).
    """
    try:
        # Tokens may be OpenAI (completion/prompt_tokens) or Ollama
        # (eval/prompt_eval_count), top-level or nested under usage:.
        usage = data.get("usage") or {}
        completion_tokens = int(
            data.get("completion_tokens")
            or usage.get("completion_tokens")
            or data.get("eval_count")
            or usage.get("eval_count")
            or 0
        )
        prompt_tokens = int(
            data.get("prompt_tokens")
            or usage.get("prompt_tokens")
            or data.get("prompt_eval_count")
            or usage.get("prompt_eval_count")
            or 0
        )
        eval_duration_ns = int(data.get("eval_duration") or usage.get("eval_duration") or 0)

        _requests_by_model.labels(model=model, workspace=workspace).inc()

        if completion_tokens > 0:
            _output_tokens.labels(model=model, workspace=workspace).inc(completion_tokens)
            _state_mod._total_output_tokens += completion_tokens

        if prompt_tokens > 0:
            _input_tokens.labels(model=model, workspace=workspace).inc(prompt_tokens)
            _state_mod._total_input_tokens += prompt_tokens

        # TPS: prefer Ollama's eval_duration; fall back to wall-clock elapsed time (streaming)
        if completion_tokens > 0 and eval_duration_ns > 0:
            tps = completion_tokens / (eval_duration_ns / 1_000_000_000)
            _tokens_per_second.labels(model=model, workspace=workspace).observe(tps)
            # Exclude bench-* traffic from daily summary (cold model loads inflate wall-clock TPS)
            if not workspace.startswith("bench-"):
                _state_mod._total_tps += tps
                _state_mod._request_tps_count += 1
            logger.debug(
                "Usage: workspace=%s model=%s tokens=%d tps=%.1f (model time)",
                workspace,
                model,
                completion_tokens,
                tps,
            )
        elif completion_tokens > 0 and elapsed_seconds and elapsed_seconds > 0:
            tps = completion_tokens / elapsed_seconds
            _tokens_per_second.labels(model=model, workspace=workspace).observe(tps)
            # Exclude bench-* traffic from daily summary (cold model loads inflate wall-clock TPS)
            if not workspace.startswith("bench-"):
                _state_mod._total_tps += tps
                _state_mod._request_tps_count += 1
            logger.debug(
                "Usage: workspace=%s model=%s tokens=%d tps=%.1f (wall clock)",
                workspace,
                model,
                completion_tokens,
                tps,
            )
        elif elapsed_seconds and elapsed_seconds > 0:
            # OpenAI-format stream with no usage data (data: [DONE] path) —
            # log elapsed for response-time visibility.
            logger.debug(
                "Usage: workspace=%s model=%s no token data (OpenAI stream), elapsed=%.2fs",
                workspace,
                model,
                elapsed_seconds,
            )

        # Track per-model request count for summary (plain dict, not the Counter)
        _state_mod._req_count_by_model[model] = _state_mod._req_count_by_model.get(model, 0) + 1

    except Exception as e:
        logger.debug("Failed to record usage metrics: %s", e)
