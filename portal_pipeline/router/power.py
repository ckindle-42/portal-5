"""Powermetrics polling, energy accounting, and per-request usage recording.

Reads the host powermetrics socket, converts watt-seconds to USD, and records
token/energy usage into the metrics collectors. Depends on
``portal_pipeline.router.metrics`` and ``portal_pipeline.router.state``;
never imports router_pipe.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time

import portal_pipeline.router.state as _state_mod
from portal_pipeline.router.metrics import (
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


def watts_seconds_to_cost_usd(ws: float) -> float:
    """Convert watt-seconds to USD via ``ELECTRICITY_RATE_USD_PER_KWH``.

    **Currently has no callers in the active codebase.** The
    ``_energy_consumed_ws_total`` Prometheus counter is in
    watt-seconds (the integral of ``current_w * elapsed``); this
    helper is the canonical conversion to dollars, but no metric or
    endpoint actually calls it. Likely scaffolded for a future cost
    endpoint or Grafana-side query; tracked in
    ``DOCSTRINGS_V1_NOTES.md``.

    Args:
        ws: Watt-seconds.

    Returns:
        Equivalent cost in USD at the configured kWh rate.
    """
    kwh = ws / 3600 / 1000
    return kwh * ELECTRICITY_RATE_USD_PER_KWH


async def _power_polling_loop():
    """Background task: poll the host powermetrics daemon every 10s; update gauges.

    The pipeline does not shell out to ``powermetrics`` itself (no
    root in the container; macOS-only tool). Instead a separate
    launchd-managed daemon — ``scripts/portal5-powermetrics.py`` —
    runs as root on the host, polls ``powermetrics``, and republishes
    JSON-per-line on a Unix socket at
    ``/tmp/portal5-powermetrics.sock``. This task connects, reads
    one line, decodes, updates the ``_power_*_watts`` gauges and the
    ``_energy_consumed_ws_total`` counter, then closes the connection.

    Degrades silently when the daemon isn't running: ``FileNotFoundError``
    on the socket connect is caught and the loop just retries every
    10s. This is intentional — operators may not install the
    powermetrics service, and the pipeline must still serve.

    Elapsed time for the energy accumulator (``current_w * elapsed``)
    is computed from the daemon's reported timestamp (``state["ts"]``),
    not local ``time.time()``, so jitter in the daemon's cadence
    doesn't bias energy attribution.

    Started as a background task by ``lifespan`` and runs for the
    lifetime of the process. Never cancelled explicitly — relies on
    asyncio task cleanup at shutdown.

    Failure swallowing: ``except Exception: pass`` at the end of the
    try block catches everything silently. Acceptable for a
    telemetry-only loop, but means malformed socket payloads are
    invisible without ``logger.debug`` instrumentation. Tracked in
    ``DOCSTRINGS_V1_NOTES.md``.
    """
    last_poll = time.time()
    while True:
        try:
            reader, writer = await asyncio.open_unix_connection(_POWERMETRICS_SOCKET)
            data = await reader.readline()
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
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
            pass
        await asyncio.sleep(10)


def _record_usage(
    model: str, workspace: str, data: dict, elapsed_seconds: float | None = None
) -> None:
    """Extract token counts and TPS from a backend response dict; record to metrics.

    Shape-tolerant. Safe to call with incomplete dicts — missing
    fields are skipped, never raised. Supports four observed
    response shapes from the three backend types Portal 5 talks to:

    * **Ollama native** (top-level): ``eval_count``,
      ``prompt_eval_count``, ``eval_duration`` (nanoseconds).
    * **Ollama nested**: same fields under ``usage:`` (rare fork
      variant; included defensively).
    * **OpenAI top-level**: ``completion_tokens``, ``prompt_tokens``.
    * **OpenAI nested in ``usage``**: spec-compliant shape (vLLM,
      MLX proxy when streaming).

    TPS preference (most-accurate first):

    1. ``eval_duration_ns`` — Ollama's reported model compute time.
       No network jitter, no SSE chunking; the cleanest TPS we get.
    2. ``elapsed_seconds`` — wall-clock from the streaming caller.
       Used when the backend doesn't return ``eval_duration`` (MLX
       proxy in OpenAI-streaming mode).
    3. Skipped — when neither is available, token counts are still
       recorded but no TPS observation is emitted.

    Updates both the Prometheus histograms/counters (scraped by
    ``/metrics``) and the module-level aggregates used by the daily
    summary scheduler (``_total_tps``, ``_request_tps_count``,
    ``_total_input_tokens``, ``_total_output_tokens``,
    ``_req_count_by_model``).

    Failure handling: bare ``except Exception`` swallows everything
    to ``logger.debug``. A malformed backend payload should not crash
    a successful request's metric path — worst case is a missing
    data point in ``/metrics``.

    Args:
        model: Concrete model id (post-``model_hint`` resolution).
        workspace: Workspace id from the request.
        data: The backend's response dict, in any of the four
            shapes above.
        elapsed_seconds: Wall-clock elapsed time, supplied by the
            streaming caller. ``None`` from non-streaming callers
            (they rely on ``eval_duration`` instead).
    """
    try:
        # Prefer OpenAI format fields (completion_tokens / prompt_tokens)
        # Fall back to Ollama native (eval_count / prompt_eval_count)
        # MLX server nests tokens inside "usage" dict — check both levels.
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
            # Update running totals for daily summary
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
            # Update running totals for daily summary
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
            # OpenAI-format streaming with no usage data (data: [DONE] path).
            # We still know the request completed — record with 0 tokens but
            # track the elapsed time for response time visibility.
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
