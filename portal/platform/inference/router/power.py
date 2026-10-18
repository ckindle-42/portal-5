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
from typing import Any

import portal.platform.inference.router.state as _state_mod
from portal.platform.inference.router import truncation as _truncation
from portal.platform.inference.router.metrics import (
    _answer_seconds,
    _answer_tokens,
    _decode_seconds,
    _decode_tokens,
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
    _tps_unmeasured,
    _ttft_seconds,
)

logger = logging.getLogger(__name__)

_POWERMETRICS_SOCKET = "/tmp/portal5-powermetrics.sock"
ELECTRICITY_RATE_USD_PER_KWH = float(os.environ.get("ELECTRICITY_RATE_USD_PER_KWH", "0.15"))


async def _power_polling_loop() -> None:
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


def _positive_float(value: object) -> float | None:
    """Return ``value`` as a finite float > 0, or ``None`` when it cannot be one."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if number <= 0.0 or number != number or number == float("inf"):
        return None
    return number


def _nonneg_int(value: object) -> int | None:
    """Return ``value`` as an int >= 0, or ``None`` when it cannot be one."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return number


def _decode_observation(
    completion_tokens: int,
    eval_duration_ns: int,
    engine_decode_seconds: float | None,
    decode_seconds: float | None,
) -> tuple[str, float] | None:
    """Engine duration, else caller-measured decode. None if neither applies."""
    if completion_tokens <= 0:
        return None
    if eval_duration_ns > 0:
        return ("engine", eval_duration_ns / 1_000_000_000)
    engine_duration = _positive_float(engine_decode_seconds)
    if engine_duration is not None:
        return ("engine", engine_duration)
    measured = _positive_float(decode_seconds)
    if measured is None:
        return None
    return ("measured", measured)


def _resolve_answer_tokens(
    completion_tokens: int,
    reasoning_tokens: int | None,
    answer_tokens: int | None,
) -> int | None:
    """Visible-answer tokens from an explicit count, else completion minus reasoning."""
    if answer_tokens is not None:
        return _nonneg_int(answer_tokens)
    if reasoning_tokens is None:
        return None
    reasoning = _nonneg_int(reasoning_tokens)
    if reasoning is None:
        return None
    return max(0, completion_tokens - reasoning)


def _record_timing_series(
    *,
    model: str,
    workspace: str,
    completion_tokens: int,
    eval_duration_ns: int,
    engine_decode_seconds: float | None,
    engine_ttft_seconds: float | None,
    decode_seconds: float | None,
    ttft_seconds: float | None,
    reasoning_tokens: int | None,
    answer_seconds: float | None,
    answer_tokens: int | None,
) -> None:
    """Record decode, answer, and TTFT series. Never substitutes wall clock.

    Decode time is Ollama ``eval_duration`` or an engine usage
    ``generation_duration`` (``source="engine"``) when present, otherwise the
    caller ``decode_seconds`` (``source="measured"``). TTFT uses engine
    ``time_to_first_token`` when present and caller ``ttft_seconds`` otherwise.
    When neither is available and the response has completion tokens, the
    request is counted on ``portal_tps_unmeasured_total`` and left out of the
    new series. Answer counters move only when the caller passes the split.
    ``bench-*`` workspaces still update Prometheus and are left out of the
    daily-digest accumulators.
    """
    bench = workspace.startswith("bench-")
    observed = _decode_observation(
        completion_tokens, eval_duration_ns, engine_decode_seconds, decode_seconds
    )
    if completion_tokens > 0 and observed is None:
        _tps_unmeasured.labels(model=model, workspace=workspace).inc()
    if observed is not None:
        source, decode_s = observed
        _decode_tokens.labels(model=model, workspace=workspace, source=source).inc(
            completion_tokens
        )
        _decode_seconds.labels(model=model, workspace=workspace, source=source).inc(decode_s)
        if not bench:
            _state_mod._decode_tokens += completion_tokens
            _state_mod._decode_seconds += decode_s

    ttft = _positive_float(engine_ttft_seconds)
    ttft_source = "engine"
    if ttft is None:
        ttft = _positive_float(ttft_seconds)
        ttft_source = "measured"
    if ttft is not None:
        _ttft_seconds.labels(model=model, workspace=workspace, source=ttft_source).observe(ttft)
        if not bench:
            _state_mod._ttft_samples.append(ttft)

    resolved_answer = _resolve_answer_tokens(completion_tokens, reasoning_tokens, answer_tokens)
    answer_s = _positive_float(answer_seconds)
    if resolved_answer is not None and resolved_answer > 0 and answer_s is not None:
        answer_source = (
            "engine"
            if eval_duration_ns > 0 or _positive_float(engine_decode_seconds) is not None
            else "measured"
        )
        _answer_tokens.labels(model=model, workspace=workspace, source=answer_source).inc(
            resolved_answer
        )
        _answer_seconds.labels(model=model, workspace=workspace, source=answer_source).inc(answer_s)
        if not bench:
            _state_mod._answer_tokens += resolved_answer
            _state_mod._answer_seconds += answer_s
            _state_mod._answer_tokens_by_model[model] = (
                _state_mod._answer_tokens_by_model.get(model, 0) + resolved_answer
            )
            _state_mod._answer_seconds_by_model[model] = (
                _state_mod._answer_seconds_by_model.get(model, 0.0) + answer_s
            )


def _record_usage(
    model: str,
    workspace: str,
    data: dict[str, Any],
    elapsed_seconds: float | None = None,
    *,
    decode_seconds: float | None = None,
    ttft_seconds: float | None = None,
    reasoning_tokens: int | None = None,
    answer_seconds: float | None = None,
    answer_tokens: int | None = None,
) -> None:
    """Extract token counts and TPS from a backend response dict; record to metrics.

    Shape-tolerant: missing fields are skipped, never raised. Handles four
    response shapes: Ollama top-level (``eval_count``, ``prompt_eval_count``,
    ``eval_duration`` ns), Ollama nested under ``usage:``, and OpenAI top-level
    (``completion_tokens``, ``prompt_tokens``) or nested ``usage`` including
    engine generation duration and TTFT.

    The deprecated ``portal_tokens_per_second`` histogram still prefers
    ``eval_duration`` and then ``elapsed_seconds`` (wall clock). The decode,
    answer, and TTFT series do not use wall clock. ``bench-*`` traffic is
    excluded from the daily-summary accumulators.

    Keyword-only timings, for a later streaming caller. Omit any you do not
    have; do not pass wall clock as ``decode_seconds``.

    * ``decode_seconds`` — model decode time when the payload has no
      ``eval_duration``. Ignored for the decode series when ``eval_duration``
      is present (engine wins, so passing both does not double-count).
    * ``ttft_seconds`` — request start to the first generated token.
    * ``reasoning_tokens`` — thinking tokens. With ``answer_seconds`` and no
      ``answer_tokens``, answer tokens are ``completion_tokens - reasoning_tokens``.
    * ``answer_seconds`` — visible-answer duration. Required to record the
      answer series. Not derived from ``decode_seconds``.
    * ``answer_tokens`` — visible-answer tokens. Overrides the subtraction.

    Bare ``except Exception`` swallows failures — a malformed payload must not
    crash a successful request's metric path.

    Args:
        model: Concrete model id (post-``model_hint`` resolution).
        workspace: Workspace id from the request.
        data: The backend's response dict, in any of the four shapes above.
        elapsed_seconds: Wall-clock elapsed time. Feeds only the deprecated
            histogram. ``None`` when the caller has no clock.
        decode_seconds: Measured model decode seconds. See above.
        ttft_seconds: Measured time to first generated token. See above.
        reasoning_tokens: Thinking-token count. See above.
        answer_seconds: Measured visible-answer seconds. See above.
        answer_tokens: Visible-answer token count. See above.
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
        engine_decode_seconds = _positive_float(
            data.get("generation_duration") or usage.get("generation_duration")
        )
        engine_ttft_seconds = _positive_float(
            data.get("time_to_first_token") or usage.get("time_to_first_token")
        )

        _requests_by_model.labels(model=model, workspace=workspace).inc()
        _truncation.check(model, workspace, prompt_tokens)

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

        _record_timing_series(
            model=model,
            workspace=workspace,
            completion_tokens=completion_tokens,
            eval_duration_ns=eval_duration_ns,
            engine_decode_seconds=engine_decode_seconds,
            engine_ttft_seconds=engine_ttft_seconds,
            decode_seconds=decode_seconds,
            ttft_seconds=ttft_seconds,
            reasoning_tokens=reasoning_tokens,
            answer_seconds=answer_seconds,
            answer_tokens=answer_tokens,
        )

    except Exception as e:
        logger.debug("Failed to record usage metrics: %s", e)
