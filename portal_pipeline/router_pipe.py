"""Portal 6.0.4 — Intelligent Router Pipeline.

Exposes OpenAI-compatible /v1/models and /v1/chat/completions.
Open WebUI connects here as its sole model source.
Routes by workspace to the appropriate backend + model.
"""

from __future__ import annotations

import asyncio
import fcntl
import hmac
import importlib.metadata
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from portal_pipeline.notifications import NotificationDispatcher, NotificationScheduler

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

from portal_pipeline.cluster_backends import BackendRegistry

logger = logging.getLogger(__name__)
# Ensure the logger has its own stderr handler — survives uvicorn multi-worker fork().
# Without this, logger.info() output is silently dropped when workers > 1 because
# logging.basicConfig() from __main__.py doesn't propagate to forked child processes.
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    logger.addHandler(_handler)
_log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logger.setLevel(getattr(logging, _log_level, logging.INFO))

# Persistent state file — survives pipeline restarts.
# Mounted as a Docker volume so it persists across container lifecycle.
_STATE_FILE = Path(os.environ.get("METRICS_STATE_FILE", "/app/data/metrics_state.json"))

# Basic Prometheus-compatible metrics counter
_request_count: dict[str, int] = {}
_startup_time = time.time()

# Maximum request body size (default 4MB)
_MAX_REQUEST_BYTES: int = int(os.environ.get("MAX_REQUEST_BYTES", str(4 * 1024 * 1024)))

# Extended stats tracked for daily summary (aggregated from Prometheus metrics)
# These are updated on every request and read by the notification scheduler.
_total_response_time_ms: float = 0.0
_total_tps: float = 0.0
_request_tps_count: int = 0
_total_input_tokens: int = 0
_total_output_tokens: int = 0
_req_count_by_model: dict[str, int] = {}  # model_name -> count (plain dict for summary)
_req_count_by_error: dict[str, int] = {}  # error_type -> count (plain dict for summary)
_peak_concurrent: int = 0
_persona_usage_raw: dict[str, dict[str, int]] = {}  # persona -> {model -> count}

# Background task that periodically persists state to disk
_state_save_task: asyncio.Task | None = None


def _record_error(workspace: str, error_type: str) -> None:
    """Record an error in both the Prometheus Counter and the plain dict for summaries."""
    _errors_total.labels(workspace=workspace, error_type=error_type).inc()
    global _req_count_by_error
    _req_count_by_error[error_type] = _req_count_by_error.get(error_type, 0) + 1


def _record_persona(persona: str, model: str) -> None:
    """Record persona usage in both the Prometheus Counter and the raw dict for persistence."""
    _persona_usage.labels(persona=persona, model=model).inc()
    global _persona_usage_raw
    if persona not in _persona_usage_raw:
        _persona_usage_raw[persona] = {}
    _persona_usage_raw[persona][model] = _persona_usage_raw[persona].get(model, 0) + 1


def _load_state() -> None:
    """Restore persisted metrics state from disk (survives restarts).

    IMPORTANT: In-memory accumulator counters (_request_count, _total_tps, etc.)
    are intentionally NOT pre-loaded from disk.  The _save_state() merge adds
    each worker's in-memory delta on top of the existing file totals; if we also
    pre-loaded the file totals into memory we would double-count on every save
    cycle, compounding exponentially across workers and restarts.

    Only peak_concurrent is restored because it uses max() rather than addition
    in the merge, so loading the historical peak is safe and desirable.
    """
    global _peak_concurrent

    if not _STATE_FILE.exists():
        logger.info("No persisted metrics state found at %s — starting fresh", _STATE_FILE)
        return

    try:
        state = json.loads(_STATE_FILE.read_text())
        _peak_concurrent = int(state.get("peak_concurrent", 0))
        logger.info(
            "Loaded persisted metrics state: %d cumulative requests in file, peak concurrent=%d",
            sum(v for v in state.get("request_count", {}).values() if isinstance(v, int)),
            _peak_concurrent,
        )
    except Exception as e:
        logger.warning("Failed to load persisted metrics state: %s — starting fresh", e)


def _save_state() -> None:
    """Persist current metrics state to disk with delta semantics.

    Cross-worker correctness:
      1. Acquire exclusive flock on a sidecar lockfile (serialises all workers).
      2. Read the file, add this worker's in-memory delta, write atomically.
      3. Reset in-memory accumulators to 0 — the delta has been persisted.
    The reset is critical: without it, every subsequent save re-adds the same
    cumulative totals on top of the file, inflating values by ~saves_per_day.
    Only `peak_concurrent` uses max() rather than addition — it survives the
    reset and accumulates correctly across saves.
    """
    global _total_response_time_ms, _total_tps, _request_tps_count
    global _total_input_tokens, _total_output_tokens
    global _request_count, _req_count_by_model, _req_count_by_error, _persona_usage_raw
    global _peak_concurrent

    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        lock_file = _STATE_FILE.with_suffix(".lock")
        with open(lock_file, "w") as lf:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            try:
                # Read existing state (may have been written by another worker)
                existing: dict = {}
                if _STATE_FILE.exists():
                    with suppress(json.JSONDecodeError, OSError):
                        existing = json.loads(_STATE_FILE.read_text())

                # Merge: sum accumulators, max for peak
                merged = {
                    "request_count": dict(existing.get("request_count", {})),
                    "total_response_time_ms": float(existing.get("total_response_time_ms", 0.0))
                    + _total_response_time_ms,
                    "total_tps": float(existing.get("total_tps", 0.0)) + _total_tps,
                    "request_tps_count": int(existing.get("request_tps_count", 0)) + _request_tps_count,
                    "total_input_tokens": int(existing.get("total_input_tokens", 0)) + _total_input_tokens,
                    "total_output_tokens": int(existing.get("total_output_tokens", 0))
                    + _total_output_tokens,
                    "req_count_by_model": dict(existing.get("req_count_by_model", {})),
                    "req_count_by_error": dict(existing.get("req_count_by_error", {})),
                    "peak_concurrent": max(int(existing.get("peak_concurrent", 0)), _peak_concurrent),
                    "persona_usage_raw": dict(existing.get("persona_usage_raw", {})),
                }

                # Merge nested dicts
                for ws, count in _request_count.items():
                    merged["request_count"][ws] = merged["request_count"].get(ws, 0) + count
                for model, count in _req_count_by_model.items():
                    merged["req_count_by_model"][model] = (
                        merged["req_count_by_model"].get(model, 0) + count
                    )
                for err_type, count in _req_count_by_error.items():
                    merged["req_count_by_error"][err_type] = (
                        merged["req_count_by_error"].get(err_type, 0) + count
                    )
                for persona, models in _persona_usage_raw.items():
                    if persona not in merged["persona_usage_raw"]:
                        merged["persona_usage_raw"][persona] = {}
                    for model, count in models.items():
                        merged["persona_usage_raw"][persona][model] = (
                            merged["persona_usage_raw"][persona].get(model, 0) + count
                        )

                # Atomic write
                tmp = _STATE_FILE.with_suffix(".tmp")
                tmp.write_text(json.dumps(merged))
                tmp.rename(_STATE_FILE)

                # CRITICAL: reset in-memory accumulators after successful persist.
                # The delta is now in the file. Re-summing in-memory on the next
                # save would double-count.
                _total_response_time_ms = 0.0
                _total_tps = 0.0
                _request_tps_count = 0
                _total_input_tokens = 0
                _total_output_tokens = 0
                _request_count.clear()
                _req_count_by_model.clear()
                _req_count_by_error.clear()
                _persona_usage_raw.clear()
                # peak_concurrent is NOT reset — it uses max() and represents
                # an all-time peak that should survive across save cycles.
            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
    except Exception as e:
        logger.debug("Failed to persist metrics state: %s", e)


async def _state_save_loop(interval: int = 60) -> None:
    """Background task: save state to disk every N seconds."""
    while True:
        await asyncio.sleep(interval)
        _save_state()


# Notification subsystem handles operational alerts and daily summaries
_notification_dispatcher: NotificationDispatcher | None = None
_notification_scheduler: NotificationScheduler | None = None

# Cached multiprocess collector registry — rebuilt only when the process
# directory changes, not on every /metrics scrape.
_mp_registry_cache: CollectorRegistry | None = None
_mp_registry_dir_cache: str | None = None

# ── Prometheus metrics (per-model granularity) ────────────────────────────
# Use a separate registry to avoid conflicts with default prometheus_client
# global state when running with multiple uvicorn workers.
_REGISTRY = CollectorRegistry(auto_describe=True)

_tokens_per_second = Histogram(
    "portal_tokens_per_second",
    "Tokens generated per second by model and workspace",
    ["model", "workspace"],
    buckets=[5, 10, 20, 30, 40, 50, 60, 80, 100, 150, 200],
    registry=_REGISTRY,
)

_output_tokens = Counter(
    "portal_output_tokens_total",
    "Total output tokens generated by model and workspace",
    ["model", "workspace"],
    registry=_REGISTRY,
)

_input_tokens = Counter(
    "portal_input_tokens_total",
    "Total input tokens processed by model and workspace",
    ["model", "workspace"],
    registry=_REGISTRY,
)

_requests_by_model = Counter(
    "portal_requests_by_model_total",
    "Total requests routed to each model",
    ["model", "workspace"],
    registry=_REGISTRY,
)

_response_time_seconds = Histogram(
    "portal_response_time_seconds",
    "End-to-end response time (request received to last byte) per model and workspace",
    ["model", "workspace"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
    registry=_REGISTRY,
)

_requests_total = Counter(
    "portal_requests_total",
    "Total requests by workspace (aggregated across workers)",
    ["workspace"],
    registry=_REGISTRY,
)

_errors_total = Counter(
    "portal_errors_total",
    "Total failed requests by workspace and error type",
    ["workspace", "error_type"],
    registry=_REGISTRY,
)

_concurrent_requests = Gauge(
    "portal_concurrent_requests",
    "Number of requests currently being processed",
    registry=_REGISTRY,
)

_persona_usage = Counter(
    "persona_usage_total",
    "Total requests by persona/model preset as selected by user",
    ["persona", "model"],
    registry=_REGISTRY,
)

# ── Tool-call metrics (M2) ─────────────────────────────────────────────────
_tool_calls_total = Counter(
    "portal5_tool_calls_total",
    "Total tool calls dispatched, by tool name and workspace",
    ["tool", "workspace"],
    registry=_REGISTRY,
)
_tool_call_duration = Histogram(
    "portal5_tool_call_duration_seconds",
    "Tool call dispatch latency in seconds, by tool name",
    ["tool"],
    buckets=[0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60],
    registry=_REGISTRY,
)
_tool_call_errors = Counter(
    "portal5_tool_call_errors_total",
    "Tool calls that returned error, by tool and workspace",
    ["tool", "workspace"],
    registry=_REGISTRY,
)
_tool_workspace_strip = Counter(
    "portal5_tool_workspace_strip_total",
    "Tools stripped from request because workspace doesn't authorize them",
    ["workspace"],
    registry=_REGISTRY,
)
_tool_loop_hops = Histogram(
    "portal5_tool_loop_hops",
    "Number of hops in the multi-turn tool loop per request",
    ["workspace"],
    buckets=[1, 2, 3, 5, 8, 10, 15, 20],
    registry=_REGISTRY,
)

# ── Power & cost metrics (M6-T02) ─────────────────────────────────────────
_power_current_watts = Gauge(
    "portal5_power_current_watts",
    "Current total power draw across CPU+GPU+ANE+DRAM",
    registry=_REGISTRY,
)
_power_cpu_watts = Gauge("portal5_power_cpu_watts", "CPU package power", registry=_REGISTRY)
_power_gpu_watts = Gauge("portal5_power_gpu_watts", "GPU power", registry=_REGISTRY)
_power_ane_watts = Gauge("portal5_power_ane_watts", "ANE power", registry=_REGISTRY)
_power_dram_watts = Gauge("portal5_power_dram_watts", "DRAM power", registry=_REGISTRY)
_power_avg_1min_watts = Gauge(
    "portal5_power_avg_1min_watts", "1-minute average power", registry=_REGISTRY
)
_energy_consumed_ws_total = Counter(
    "portal5_energy_consumed_watt_seconds_total",
    "Cumulative energy consumed by the host",
    registry=_REGISTRY,
)
_energy_by_workspace_ws = Counter(
    "portal5_energy_by_workspace_watt_seconds_total",
    "Estimated energy attributed to a workspace",
    ["workspace"],
    registry=_REGISTRY,
)
_request_energy_ws = Histogram(
    "portal5_request_energy_watt_seconds",
    "Estimated energy per request (avg_power * duration)",
    ["workspace", "persona"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600],
    registry=_REGISTRY,
)

# ── Rate-limit metrics (M6-T05) ───────────────────────────────────────────
_workspace_semaphore_busy_total_metric = Counter(
    "portal5_workspace_semaphore_busy_total",
    "Requests rejected because workspace concurrency limit reached",
    ["workspace"],
    registry=_REGISTRY,
)
_workspace_semaphore_busy_total = _workspace_semaphore_busy_total_metric

_POWERMETRICS_SOCKET = "/tmp/portal5-powermetrics.sock"
ELECTRICITY_RATE_USD_PER_KWH = float(os.environ.get("ELECTRICITY_RATE_USD_PER_KWH", "0.15"))


def watts_seconds_to_cost_usd(ws: float) -> float:
    kwh = ws / 3600 / 1000
    return kwh * ELECTRICITY_RATE_USD_PER_KWH


async def _power_polling_loop():
    """Read powermetrics socket every 10s; update gauges and accumulate energy."""
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
    """Extract usage fields from an Ollama or OpenAI-format response dict and record metrics.

    Safe to call with incomplete dicts — missing fields are skipped.
    Supports both Ollama native format (eval_count, eval_duration, prompt_eval_count)
    and OpenAI compatibility format (completion_tokens, prompt_tokens).
    TPS computation (fastest available method):
      1. eval_duration_ns  — Ollama native model compute time (preferred)
      2. elapsed_seconds    — wall-clock time from stream start (streaming fallback)
    Updates both Prometheus histograms/counters and module-level aggregates
    used by the daily summary scheduler.
    """
    try:
        global \
            _total_output_tokens, \
            _total_input_tokens, \
            _total_tps, \
            _request_tps_count, \
            _req_count_by_model
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
            _total_output_tokens += completion_tokens

        if prompt_tokens > 0:
            _input_tokens.labels(model=model, workspace=workspace).inc(prompt_tokens)
            _total_input_tokens += prompt_tokens

        # TPS: prefer Ollama's eval_duration; fall back to wall-clock elapsed time (streaming)
        if completion_tokens > 0 and eval_duration_ns > 0:
            tps = completion_tokens / (eval_duration_ns / 1_000_000_000)
            _tokens_per_second.labels(model=model, workspace=workspace).observe(tps)
            # Update running totals for daily summary
            _total_tps += tps
            _request_tps_count += 1
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
            _total_tps += tps
            _request_tps_count += 1
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
        _req_count_by_model[model] = _req_count_by_model.get(model, 0) + 1

    except Exception as e:
        logger.debug("Failed to record usage metrics: %s", e)


def _record_response_time(model: str, workspace: str, duration_seconds: float) -> None:
    """Record end-to-end response time for a request.

    Updates both Prometheus histogram and module-level aggregate for the daily summary.
    """
    try:
        _response_time_seconds.labels(model=model, workspace=workspace).observe(duration_seconds)
        global _total_response_time_ms
        _total_response_time_ms += duration_seconds * 1000
    except Exception as e:
        logger.debug("Failed to record response time: %s", e)


# ── Persona map (for tool whitelist resolution) ─────────────────────────────
_PERSONA_MAP: dict[str, dict[str, Any]] = {}


def _load_persona_map() -> None:
    """Load persona YAML files into a slug -> data dict for tool resolution."""
    global _PERSONA_MAP
    personas_dir = Path(__file__).resolve().parent.parent / "config" / "personas"
    if not personas_dir.is_dir():
        return
    try:
        import yaml  # noqa: F811 — pyyaml is a pipeline dependency

        for yf in sorted(personas_dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(yf.read_text()) or {}
                slug = data.get("slug", yf.stem)
                _PERSONA_MAP[slug] = data
            except Exception as e:
                logger.debug("Failed to load persona %s: %s", yf, e)
    except Exception as e:
        logger.warning("Failed to load persona map: %s", e)


_load_persona_map()

# Canonical workspace definitions — must match backends.yaml workspace_routing keys
# model_hint: preferred Ollama model tag within the routed backend group
# mlx_model_hint: preferred MLX model tag (HF path) for workspaces that route through MLX
WORKSPACES: dict[str, dict[str, Any]] = {
    "auto": {
        "name": "🤖 Portal Auto Router",
        "description": (
            "Intelligently routes to the best specialist model based on your question. "
            "Security/redteam topics → BaronLLM. Coding → Qwen3-Coder. "
            "Reasoning/research → DeepSeek-R1. Other → general."
        ),
        "model_hint": "dolphin-llama3:8b",
        "tools": [],
    },
    "auto-coding": {
        "name": "💻 Portal Code Expert",
        "description": "Code generation, debugging, architecture review",
        "model_hint": "qwen3-coder:30b",
        "mlx_model_hint": "lmstudio-community/Devstral-Small-2507-MLX-4bit",
        "tools": [
            "execute_python",
            "execute_nodejs",
            "execute_bash",
            "sandbox_status",
            "read_word_document",
            "read_pdf",
        ],
    },
    "auto-agentic": {
        "name": "⚡ Portal Agentic Coder (Heavy)",
        "description": (
            "Full-power agentic coding via Qwen3-Coder-Next-4bit (80B MoE, 3B active, 256K ctx). "
            "Triggers big-model mode: unloads all Ollama + MLX models before loading. "
            "Use for long-horizon multi-file tasks, SWE-agent-style workflows, and complex refactors. "
            "Not for interactive chat — load time ~60s, context capped at 32K."
        ),
        "model_hint": "qwen3-coder:30b",
        "mlx_model_hint": "mlx-community/Qwen3-Coder-Next-4bit",
        "context_limit": 32768,
        "tools": [
            "execute_python",
            "execute_bash",
            "execute_nodejs",
            "sandbox_status",
            "create_word_document",
            "create_excel",
            "create_powerpoint",
            "read_word_document",
            "read_excel",
            "read_powerpoint",
            "read_pdf",
            "classify_vulnerability",
            "transcribe_audio",
            "speak",
            "generate_image",
            "web_search",
            "web_fetch",
            "remember",
            "recall",
            "kb_search",
            "kb_list",
        ],
    },
    "auto-spl": {
        "name": "🔍 Portal SPL Engineer",
        "description": "Splunk SPL queries, pipeline explanation, detection search authoring",
        "model_hint": "deepseek-coder-v2:16b-lite-instruct-q4_K_M",
        "mlx_model_hint": "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit",
        "tools": ["classify_vulnerability", "kb_search", "kb_list"],
    },
    "auto-security": {
        "name": "🔒 Portal Security Analyst",
        "description": "Security analysis, hardening, vulnerability assessment",
        "model_hint": "baronllm:q6_k",
        "tools": [
            "classify_vulnerability",
            "execute_python",
            "execute_bash",
            "web_search",
            "web_fetch",
            "kb_search",
            "kb_list",
        ],
    },
    "auto-redteam": {
        "name": "🔴 Portal Red Team",
        "description": "Offensive security, penetration testing, exploit research",
        "model_hint": "baronllm:q6_k",
        "tools": ["execute_python", "execute_bash", "execute_nodejs", "classify_vulnerability"],
    },
    "auto-blueteam": {
        "name": "🔵 Portal Blue Team",
        "description": "Defensive security, incident response, threat hunting",
        "model_hint": "lily-cybersecurity:7b-q4_k_m",
        "tools": ["execute_python", "classify_vulnerability"],
    },
    "auto-creative": {
        "name": "✍️  Portal Creative Writer",
        "description": "Creative writing, storytelling, content generation",
        "model_hint": "dolphin-llama3:8b",
        "mlx_model_hint": "mlx-community/Dolphin3.0-Llama3.1-8B-8bit",
        "tools": [],
    },
    "auto-reasoning": {
        "name": "🧠 Portal Deep Reasoner",
        "description": "Complex analysis, research synthesis, step-by-step reasoning",
        "model_hint": "deepseek-r1:32b-q4_k_m",
        "mlx_model_hint": "Jackrong/MLX-Qwopus3.5-27B-v3-8bit",
        "predict_limit": 16384,
        "emits_reasoning": True,
        "tools": [],
    },
    "auto-documents": {
        "name": "📄 Portal Document Builder",
        "description": "Create Word, Excel, PowerPoint via MCP tools",
        "model_hint": "qwen3.5:9b",
        "mlx_model_hint": "mlx-community/phi-4-8bit",
        "tools": [
            "create_word_document",
            "create_excel",
            "create_powerpoint",
            "read_word_document",
            "read_excel",
            "read_powerpoint",
            "read_pdf",
        ],
    },
    "auto-video": {
        "name": "🎬 Portal Video Creator",
        "description": "Generate videos via ComfyUI / Wan2.2",
        "model_hint": "dolphin-llama3:8b",
        "tools": [],
    },
    "auto-music": {
        "name": "🎵 Portal Music Producer",
        "description": "Generate music and audio via AudioCraft/MusicGen",
        "model_hint": "dolphin-llama3:8b",
        "tools": [],
    },
    "auto-research": {
        "name": "🔍 Portal Research Assistant",
        "description": "Web research, information synthesis, fact-checking",
        "model_hint": "huihui_ai/tongyi-deepresearch-abliterated",
        "mlx_model_hint": "Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit",
        "predict_limit": 16384,
        "emits_reasoning": True,
        "tools": [
            "web_search",
            "web_fetch",
            "news_search",
            "kb_search",
            "kb_search_all",
            "kb_list",
            "remember",
            "recall",
        ],
    },
    "auto-vision": {
        "name": "👁️  Portal Vision",
        "description": "Image understanding, visual analysis, multimodal tasks",
        "model_hint": "qwen3-vl:32b",
        "mlx_model_hint": "mlx-community/gemma-4-31b-it-4bit",
        "tools": ["transcribe_audio"],
    },
    "auto-data": {
        "name": "📊 Portal Data Analyst",
        "description": "Data analysis, statistics, visualization guidance",
        "model_hint": "deepseek-r1:32b-q4_k_m",
        "mlx_model_hint": "mlx-community/DeepSeek-R1-Distill-Qwen-32B-abliterated-4bit",
        "predict_limit": 16384,
        "emits_reasoning": True,
        "tools": ["execute_python", "create_excel", "kb_search"],
    },
    "auto-compliance": {
        "name": "⚖️  Portal Compliance Analyst",
        "description": "NERC CIP compliance, policy analysis, regulatory guidance",
        "model_hint": "deepseek-r1:32b-q4_k_m",
        "mlx_model_hint": "Jackrong/MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit",
        "predict_limit": 16384,
        "emits_reasoning": True,
        "tools": [
            "create_word_document",
            "read_pdf",
            "kb_search",
            "kb_list",
            "web_search",
        ],
    },
    "auto-mistral": {
        "name": "🧪 Portal Mistral Reasoner",
        "description": (
            "Structured reasoning via Magistral-Small-2509 — Mistral training lineage, "
            "[THINK] mode, distinct failure profile from Qwen/DeepSeek reasoning models."
        ),
        "model_hint": "deepseek-r1:32b-q4_k_m",
        "mlx_model_hint": "lmstudio-community/Magistral-Small-2509-MLX-8bit",
        "predict_limit": 16384,
        "emits_reasoning": True,
        "tools": ["execute_python", "execute_bash"],
    },
    "auto-math": {
        "name": "🧮 Portal Math Reasoner",
        "description": "Mathematical problem solving, proofs, calculus, algebra, statistics",
        "model_hint": "qwen3.5:9b",
        "mlx_model_hint": "mlx-community/Qwen2.5-Math-7B-Instruct-4bit",
        "predict_limit": 8192,
        "tools": ["execute_python"],
    },
    # ── Coding Capability Benchmark Workspaces ───────────────────────────────
    "bench-devstral": {
        "name": "🔬 Bench · Devstral-Small-2507",
        "description": "Benchmark: Devstral-Small-2507 (MLX, Mistral/Codestral lineage, ~15GB, 53.6% SWE-bench)",
        "model_hint": "devstral:24b",
        "mlx_model_hint": "lmstudio-community/Devstral-Small-2507-MLX-4bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "tools": [],
    },
    "bench-qwen3-coder-next": {
        "name": "🔬 Bench · Qwen3-Coder-Next (80B MoE)",
        "description": "Benchmark: Qwen3-Coder-Next-4bit (MLX, Alibaba, 80B MoE 3B active, ~46GB, 256K ctx — cold load ~60s)",
        "model_hint": "qwen3-coder:30b",
        "mlx_model_hint": "mlx-community/Qwen3-Coder-Next-4bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "tools": [],
    },
    "bench-qwen3-coder-30b": {
        "name": "🔬 Bench · Qwen3-Coder-30B",
        "description": "Benchmark: Qwen3-Coder-30B-A3B-8bit (MLX, Alibaba, 30B MoE 3B active, ~22GB)",
        "model_hint": "qwen3-coder:30b",
        "mlx_model_hint": "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "tools": [],
    },
    "bench-llama33-70b": {
        "name": "🔬 Bench · Llama-3.3-70B",
        "description": "Benchmark: Llama-3.3-70B-Instruct-4bit (MLX, Meta, ~40GB — cold load ~60s, plan for sequential runs)",
        "model_hint": "llama3.3:70b-q4_k_m",
        "mlx_model_hint": "mlx-community/Llama-3.3-70B-Instruct-4bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "tools": [],
    },
    "bench-phi4": {
        "name": "🔬 Bench · Phi-4",
        "description": "Benchmark: phi-4-8bit (MLX, Microsoft, 14B, synthetic training data — distinct methodology)",
        "model_hint": "qwen3.5:9b",
        "mlx_model_hint": "mlx-community/phi-4-8bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "tools": [],
    },
    "bench-phi4-reasoning": {
        "name": "🔬 Bench · Phi-4-reasoning-plus",
        "description": "Benchmark: Phi-4-reasoning-plus (MLX, Microsoft, RL-trained, ~7GB — produces reasoning traces before code)",
        "model_hint": "qwen3.5:9b",
        "mlx_model_hint": "lmstudio-community/Phi-4-reasoning-plus-MLX-4bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "tools": [],
    },
    "bench-dolphin8b": {
        "name": "🔬 Bench · Dolphin-Llama3-8B",
        "description": "Benchmark: Dolphin3.0-Llama3.1-8B-8bit (MLX, Cognitive Computations, ~9GB — fast baseline, uncensored)",
        "model_hint": "dolphin-llama3:8b",
        "mlx_model_hint": "mlx-community/Dolphin3.0-Llama3.1-8B-8bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "tools": [],
    },
    "bench-glm": {
        "name": "🔬 Bench · GLM-4.7-Flash",
        "description": "Benchmark: glm-4.7-flash:q4_k_m (Ollama, Zhipu AI — distinct Chinese research lineage, ~6GB)",
        "model_hint": "glm-4.7-flash:q4_k_m",
        "max_concurrent": 1,
        "tools": [],
    },
    "bench-gptoss": {
        "name": "🔬 Bench · GPT-OSS-20B",
        "description": "Benchmark: gpt-oss:20b (Ollama, OpenAI open-weight MoE, ~12GB, o3-mini level — configurable thinking depth)",
        "model_hint": "gpt-oss:20b",
        "max_concurrent": 1,
        "tools": [],
    },
}

# ── Tool-call helpers (M2) ──────────────────────────────────────────────────

MAX_TOOL_HOPS = int(os.environ.get("MAX_TOOL_HOPS", "10"))


def _workspace_tools(workspace_id: str) -> list[str]:
    """Get the tool whitelist for a workspace."""
    return WORKSPACES.get(workspace_id, {}).get("tools", [])


def _resolve_persona_tools(persona: dict, workspace_id: str) -> list[str]:
    """Resolve the effective tool list for a persona within a workspace.

    Order of precedence:
        1. persona.tools_deny — always strips these tools
        2. persona.tools_allow — if present, uses this list (then applies deny)
        3. workspace.tools — default fallback
    """
    workspace_tools = set(_workspace_tools(workspace_id))
    persona_allow = set(persona.get("tools_allow", []) or [])
    persona_deny = set(persona.get("tools_deny", []) or [])

    effective = persona_allow or workspace_tools
    effective = effective - persona_deny
    return sorted(effective)


def _resolve_persona_browser_policy(persona: dict) -> dict:
    """Return the persona's browser policy. Defaults applied for missing fields."""
    bp = persona.get("browser_policy", {}) or {}
    return {
        "allowed_domains": bp.get("allowed_domains") or [],
        "blocked_domains": bp.get("blocked_domains") or [],
        "default_profile": bp.get("default_profile", "_isolated"),
        "force_credential_fill": bp.get("force_credential_fill", False),
        "max_navigations_per_session": bp.get("max_navigations_per_session", 50),
    }


async def _dispatch_tool_call(
    tool_call: dict,
    effective_tools: set[str],
    workspace_id: str,
    persona: str,
    request_id: str,
) -> dict:
    """Dispatch a single tool call. Returns the tool result message.

    Returns a dict shaped like an OpenAI tool message:
        {"role": "tool", "tool_call_id": "...", "name": "...", "content": "..."}
    """
    from portal_pipeline.tool_registry import tool_registry

    fn = tool_call.get("function", {})
    tool_name = fn.get("name", "")
    arguments_str = fn.get("arguments", "{}")
    tool_call_id = tool_call.get("id", "")

    # Parse arguments
    try:
        arguments = json.loads(arguments_str) if arguments_str else {}
    except json.JSONDecodeError:
        _record_error(workspace_id, "tool_arg_parse")
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": json.dumps({"error": f"Invalid JSON arguments: {arguments_str[:200]}"}),
        }

    # Whitelist enforcement
    if tool_name not in effective_tools:
        _record_error(workspace_id, "tool_not_allowed")
        logger.warning(
            "Tool %s called but not in workspace=%s persona=%s whitelist; rejected",
            tool_name,
            workspace_id,
            persona,
        )
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": json.dumps({"error": f"Tool '{tool_name}' not available for {persona}"}),
        }

    # Dispatch via registry
    t0 = time.monotonic()
    result = await tool_registry.dispatch(tool_name, arguments, request_id=request_id)
    elapsed = time.monotonic() - t0

    # Metrics
    _tool_calls_total.labels(tool=tool_name, workspace=workspace_id).inc()
    _tool_call_duration.labels(tool=tool_name).observe(elapsed)
    if "error" in result:
        _tool_call_errors.labels(tool=tool_name, workspace=workspace_id).inc()

    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": tool_name,
        "content": json.dumps(result) if isinstance(result, (dict, list)) else str(result),
    }


# ── Content-aware routing: weighted keyword scoring ──────────────────────────
# Applied only when the user selects the 'auto' workspace.
# Each workspace defines weighted keywords and an activation threshold.
# Weights: 3 = strong/clear intent, 2 = medium signal, 1 = weak/broad term.
# The workspace with the highest score above its threshold wins.
# This replaces the old regex-based approach — same O(n) complexity but
# handles overlapping signals naturally (highest score wins, not arbitrary order).

# Redteam keywords — clearly offensive intent
_REDTEAM_KEYWORDS: dict[str, int] = {
    # Strong (3) — unambiguous offensive intent
    "exploit": 3,
    "payload": 3,
    "shellcode": 3,
    "reverse shell": 3,
    "bind shell": 3,
    "privilege escalation": 3,
    "privesc": 3,
    "metasploit": 3,
    "msfvenom": 3,
    "cobalt strike": 3,
    "mimikatz": 3,
    "golden ticket": 3,
    "dcsync": 3,
    "pass the hash": 3,
    "antivirus bypass": 3,
    "edr bypass": 3,
    "av evasion": 3,
    # Medium (2) — offensive context
    "bypass": 2,
    "evasion": 2,
    "obfuscate": 2,
    "c2": 2,
    "c2 server": 2,
    "command and control": 2,
    "offensive": 2,
    "red team": 2,
    "redteam": 2,
    "pentest": 2,
    "penetration test": 2,
    "hack": 2,
    "hacking": 2,
    "ctf": 2,
    "lolbas": 2,
    "living off": 2,
    "lateral movement": 2,
    "bloodhound": 2,
    "kerberoast": 2,
}

# Security keywords — broader (defensive + offensive analysis)
_SECURITY_KEYWORDS: dict[str, int] = {
    # Strong (3) — unambiguous security intent
    "exploit": 3,
    "payload": 3,
    "shellcode": 3,
    "privilege escalation": 3,
    "privesc": 3,
    "reverse shell": 3,
    "bind shell": 3,
    "command injection": 3,
    "sql injection": 3,
    "sqli": 3,
    "xss": 3,
    "csrf": 3,
    "buffer overflow": 3,
    "rop chain": 3,
    "heap spray": 3,
    "use after free": 3,
    "uaf": 3,
    "zero day": 3,
    "0day": 3,
    "cve-": 3,
    "metasploit": 3,
    "msfvenom": 3,
    "meterpreter": 3,
    "cobalt strike": 3,
    "c2 server": 3,
    "c&c": 3,
    "lateral movement": 3,
    "persistence mechanism": 3,
    "antivirus bypass": 3,
    "edr bypass": 3,
    "av evasion": 3,
    "defense evasion": 3,
    "exfiltration": 3,
    "data exfiltration": 3,
    "pentesting": 3,
    "pentest": 3,
    "penetration test": 3,
    "red team": 3,
    "redteam": 3,
    "offensive security": 3,
    "mimikatz": 3,
    "crackmapexec": 3,
    "pass the hash": 3,
    "pass the ticket": 3,
    "kerberoasting": 3,
    "asreproasting": 3,
    "golden ticket": 3,
    "silver ticket": 3,
    "dcsync": 3,
    "ransomware": 3,
    "rootkit": 3,
    "backdoor": 3,
    "botnet": 3,
    "incident response": 3,
    "threat hunting": 3,
    "malware analysis": 3,
    "network forensics": 3,
    "memory forensics": 3,
    "mitre att&ck": 3,
    # Medium (2) — clear security context
    "evasion": 2,
    "obfuscation": 2,
    "lolbas": 2,
    "living off the land": 2,
    "bug bounty": 2,
    "ctf": 2,
    "capture the flag": 2,
    "nmap": 3,
    "masscan": 2,
    "gobuster": 2,
    "nikto": 2,
    "burp suite": 2,
    "sqlmap": 2,
    "hydra": 2,
    "hashcat": 2,
    "bloodhound": 2,
    "threat intelligence": 2,
    "ioc": 2,
    "indicator of compromise": 2,
    "reverse engineering": 2,
    "yara rule": 2,
    "sigma rule": 2,
    "siem alert": 2,
    "splunk detection": 2,
    "ids rule": 2,
    "snort rule": 2,
    "suricata": 2,
    "volatility": 2,
    "malware": 3,
    "trojan": 2,
    "threat actor": 2,
    "vulnerability assessment": 2,
    "vulnerability scan": 2,
    "nessus": 2,
    "openvas": 2,
    "hardening": 2,
    "cis benchmark": 2,
    "attack framework": 2,
    "kill chain": 2,
    "diamond model": 2,
    # Weak (1) — broad terms that need corroboration
    "security audit": 1,
    "vulnerability": 1,
    "security": 1,
    "implications": 1,
}

# SPL keywords — Splunk-specific vocabulary (low false positive rate)
_SPL_KEYWORDS: dict[str, int] = {
    # Strong (3) — unambiguous SPL intent
    "splunk": 3,
    "spl query": 3,
    "search processing language": 3,
    "tstats": 3,
    "inputlookup": 3,
    "outputlookup": 3,
    "makeresults": 3,
    "mvexpand": 3,
    "streamstats": 3,
    "eventstats": 3,
    "correlation search": 3,
    "notable event": 3,
    "splunk es": 3,
    "splunk enterprise security": 3,
    "data model acceleration": 3,
    "summary index": 3,
    "detection search": 3,
    "splunk query": 3,
    "write me a splunk": 3,
    "write a splunk": 3,
    "build a splunk": 3,
    # Medium (2) — SPL commands in natural language
    "eval field": 2,
    "rex field": 2,
    "lookup command": 2,
    "transaction command": 2,
    "| stats": 2,
    "| timechart": 2,
    "| eval": 2,
    "| rex": 2,
    "datamodel": 2,
    "saved search": 2,
    "dashboard panel spl": 2,
    # Weak (1) — short terms that need corroboration
    "spl": 1,
    "| table": 1,
    "| dedup": 1,
    "| sort": 1,
    "| rename": 1,
}

# Coding keywords — software development intent
_CODING_KEYWORDS: dict[str, int] = {
    # Strong (3) — clear coding intent
    "write a function": 3,
    "write a script": 3,
    "write a program": 3,
    "write code": 3,
    "debug this": 3,
    "fix this code": 3,
    "fix the bug": 3,
    "code review": 3,
    "run this code": 3,
    # Medium (2) — development activities
    "refactor": 2,
    "implement": 2,
    "class definition": 2,
    "api endpoint": 2,
    "unit test": 2,
    "pytest": 2,
    "unittest": 2,
    "sql query": 2,
    "algorithm": 2,
    "data structure": 2,
    "bash script": 2,
    "powershell": 2,
    "ansible": 2,
    "terraform": 2,
    "bigfix": 2,
    "bes xml": 2,
    "relevance": 2,
    "interpreter": 2,
    "simulator": 2,
    "execute": 2,
    # Weak (1) — broad terms that need corroboration
    "docker": 1,
    "kubernetes": 1,
    "ci/cd": 1,
    "regex": 1,
    "python": 1,
    "javascript": 1,
    "typescript": 1,
    "rust": 1,
    "golang": 1,
    "sql": 1,
    "function": 1,
    "script": 1,
    "review": 2,
    "bug": 2,
    "bash": 2,
    "networking": 2,
    "write function": 2,
    "write script": 2,
    "write a python": 2,
    "write a javascript": 2,
    "write a typescript": 2,
    "write a rust": 2,
    "write a golang": 2,
    "write a sql": 2,
    "write a bash": 2,
    "write a docker": 2,
    "write a kubernetes": 2,
    "docker compose": 2,
    "dockerfile": 2,
    "pipeline": 1,
}

# Reasoning keywords — analytical/deep thinking intent
_REASONING_KEYWORDS: dict[str, int] = {
    # Strong (3) — clear analytical intent
    "pros and cons": 3,
    "trade-off": 3,
    "explain in depth": 3,
    "step by step": 3,
    "break down": 3,
    "what is the difference": 3,
    "deep dive": 3,
    "detailed analysis": 3,
    # Medium (2) — analytical activities
    "analyze": 2,
    "compare": 2,
    "evaluate": 2,
    "research": 2,
    # Weak (1) — broad terms that need corroboration
    "summarize": 1,
    "how does": 1,
    "why does": 1,
    "comprehensive": 1,
    "thorough": 1,
}

# Compliance keywords — NERC CIP and regulatory intent
_COMPLIANCE_KEYWORDS: dict[str, int] = {
    # Strong (3) — unambiguous compliance intent
    "nerc cip": 3,
    "cip-002": 3,
    "cip-003": 3,
    "cip-004": 3,
    "cip-005": 3,
    "cip-006": 3,
    "cip-007": 3,
    "cip-008": 3,
    "cip-009": 3,
    "cip-010": 3,
    "cip-011": 3,
    "cip-013": 3,
    "cip-014": 3,
    "compliance gap": 3,
    "gap analysis": 3,
    "regulatory compliance": 3,
    "audit preparation": 3,
    "policy mapping": 3,
    "policy-to-standard": 3,
    "control evidence": 3,
    "compliance status": 3,
    # Medium (2) — regulatory context
    "nerc": 2,
    "bulk electric": 2,
    "bes cyber": 2,
    "critical asset": 2,
    "low impact": 2,
    "medium impact": 2,
    "high impact": 2,
    "electronic security": 2,
    "physical security": 2,
    "access management": 2,
    "security management": 2,
    "incident response plan": 2,
    "recovery plan": 2,
    "configuration change": 2,
    "patch management": 2,
    # Weak (1) — broad regulatory terms
    "compliance": 1,
    "regulation": 1,
    "audit": 1,
    "standard": 1,
    "policy review": 1,
}

# Mistral/Magistral keywords — structured reasoning with Mistral lineage
_MISTRAL_KEYWORDS: dict[str, int] = {
    # Strong (3) — explicit Mistral/Magistral requests
    "magistral": 3,
    "mistral reasoning": 3,
    "mistral model": 3,
    "think mode": 3,
    "[think]": 3,
    "strategic reasoning": 3,
    "structured reasoning": 3,
    # Medium (2) — strategic/planning context
    "strategic analysis": 2,
    "strategic planning": 2,
    "business reasoning": 2,
    "decision framework": 2,
    "decision analysis": 2,
    "trade-off analysis": 2,
    "risk assessment": 2,
    # Weak (1) — broad planning terms
    "strategy": 1,
    "planning": 1,
}

# Workspace routing configuration: keywords + activation threshold
# Thresholds tuned so a single strong signal (weight 3) triggers routing,
# or a combination of medium signals (2+2=4) reaches the bar.
_WORKSPACE_ROUTING: dict[str, dict[str, Any]] = {
    "auto-redteam": {
        "keywords": _REDTEAM_KEYWORDS,
        "threshold": 4,
    },
    "auto-security": {
        "keywords": _SECURITY_KEYWORDS,
        "threshold": 3,
    },
    "auto-spl": {
        "keywords": _SPL_KEYWORDS,
        "threshold": 3,
    },
    "auto-coding": {
        "keywords": _CODING_KEYWORDS,
        "threshold": 3,
    },
    "auto-agentic": {
        "keywords": {
            "agentic": 3,
            "swe-agent": 3,
            "openhands": 3,
            "multi-file": 3,
            "long-horizon": 3,
            "codebase refactor": 3,
            "full codebase": 3,
            "repository-wide": 3,
            "heavy coder": 2,
            "big model": 2,
            "qwen3 coder next": 2,
        },
        "threshold": 3,
    },
    "auto-reasoning": {
        "keywords": _REASONING_KEYWORDS,
        "threshold": 3,
    },
    "auto-compliance": {
        "keywords": _COMPLIANCE_KEYWORDS,
        "threshold": 3,
    },
    "auto-mistral": {
        "keywords": _MISTRAL_KEYWORDS,
        "threshold": 3,
    },
}

# P7-PERF: Pre-compute keyword data structures for O(1) lookup in _detect_workspace().
# Instead of iterating all keywords per request, we:
# 1. Pre-lowercase all keywords (avoid .lower() per request)
# 2. Group by length for efficient substring matching
# 3. Cache the workspace→keywords mapping
_KEYWORD_CACHE: dict[str, dict[str, int]] = {}
for _ws_id, _ws_cfg in _WORKSPACE_ROUTING.items():
    _KEYWORD_CACHE[_ws_id] = {kw.lower(): weight for kw, weight in _ws_cfg["keywords"].items()}


# ── LLM-Based Intent Router (P5-FUT-006) ─────────────────────────────────────
# Uses an uncensored Llama 3.2 3B abliterated as a fast semantic intent classifier.
# Abliterated (surgical refusal removal) so red-team/security queries aren't refused.
# Falls back to keyword scoring on low confidence or timeout.

_LLM_ROUTER_ENABLED: bool = os.environ.get("LLM_ROUTER_ENABLED", "true").lower() == "true"
_LLM_ROUTER_MODEL: str = os.environ.get(
    "LLM_ROUTER_MODEL", "hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF"
)
_LLM_ROUTER_CONFIDENCE_THRESHOLD: float = float(
    os.environ.get("LLM_ROUTER_CONFIDENCE_THRESHOLD", "0.5")
)
_LLM_ROUTER_TIMEOUT_MS: int = int(os.environ.get("LLM_ROUTER_TIMEOUT_MS", "500"))
_LLM_ROUTER_OLLAMA_URL: str = os.environ.get(
    "LLM_ROUTER_OLLAMA_URL", "http://host.docker.internal:11434"
)

# Valid workspace IDs the LLM router may return
_VALID_WORKSPACE_IDS: frozenset[str] = frozenset(
    [
        "auto",
        "auto-agentic",
        "auto-coding",
        "auto-spl",
        "auto-security",
        "auto-redteam",
        "auto-blueteam",
        "auto-creative",
        "auto-reasoning",
        "auto-documents",
        "auto-video",
        "auto-music",
        "auto-research",
        "auto-vision",
        "auto-data",
        "auto-compliance",
        "auto-mistral",
        "auto-math",
    ]
)

# JSON schema enforced by Ollama grammar decoding — guarantees parseable output
# Enum constrains workspace to valid IDs (no hallucinated values possible)
_ROUTER_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "workspace": {
            "type": "string",
            "enum": [
                "auto",
                "auto-agentic",
                "auto-coding",
                "auto-spl",
                "auto-security",
                "auto-redteam",
                "auto-blueteam",
                "auto-creative",
                "auto-reasoning",
                "auto-documents",
                "auto-video",
                "auto-music",
                "auto-research",
                "auto-vision",
                "auto-data",
                "auto-compliance",
                "auto-mistral",
                "auto-math",
            ],
        },
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "required": ["workspace", "confidence"],
}

_routing_descriptions: dict[str, str] | None = None
_routing_examples: list[dict] | None = None


def _load_routing_config() -> tuple[dict[str, str], list[dict]]:
    """Load workspace descriptions and few-shot examples from config files.

    Returns cached copies after first load. Falls back to empty dicts/lists
    if files are missing so the LLM router degrades gracefully.
    """
    global _routing_descriptions, _routing_examples
    if _routing_descriptions is not None and _routing_examples is not None:
        return _routing_descriptions, _routing_examples

    desc_path = Path("config/routing_descriptions.json")
    ex_path = Path("config/routing_examples.json")

    try:
        raw = json.loads(desc_path.read_text()) if desc_path.exists() else {}
        _routing_descriptions = {k: v for k, v in raw.items() if not k.startswith("_")}
    except Exception as e:
        logger.warning("LLM router: failed to load routing_descriptions.json: %s", e)
        _routing_descriptions = {}

    try:
        raw = json.loads(ex_path.read_text()) if ex_path.exists() else {}
        _routing_examples = raw.get("examples", [])
    except Exception as e:
        logger.warning("LLM router: failed to load routing_examples.json: %s", e)
        _routing_examples = []

    return _routing_descriptions, _routing_examples


def _build_router_prompt(user_message: str) -> str:
    """Build the classification prompt sent to the uncensored LLM router model.

    Includes workspace descriptions and few-shot examples for in-context learning.
    Fits within Llama-3.2-3B 4096-token context window (17 workspaces ≈ 1100 tokens).
    """
    descriptions, examples = _load_routing_config()

    # Workspace descriptions block
    desc_lines = "\n".join(f"- {ws_id}: {desc}" for ws_id, desc in descriptions.items())

    # Few-shot examples block (cap at 9 examples)
    example_lines = "\n".join(
        f'Message: "{ex["message"]}"\nWorkspace: {ex["workspace"]}\nConfidence: {ex["confidence"]}'
        for ex in (examples or [])[:9]
    )

    return f"""You are an intent router for an AI platform. Classify the user message into exactly one workspace.

WORKSPACES:
{desc_lines}

EXAMPLES:
{example_lines}

Now classify this message:
Message: "{user_message}"

Respond ONLY with a JSON object: {{"workspace": "<workspace_id>", "confidence": <0.0-1.0>}}
The workspace must be one of the valid IDs listed above."""


async def _route_with_llm(messages: list[dict]) -> str | None:
    """Use the uncensored LLM router model to classify user intent into a workspace ID.

    Returns a workspace ID string if confidence >= threshold, else None
    (caller falls back to keyword scoring).

    Safety properties:
    - Hard timeout (LLM_ROUTER_TIMEOUT_MS, default 500ms)
    - JSON schema constraint enforced via Ollama grammar (guaranteed parseable)
    - Workspace ID validated against _VALID_WORKSPACE_IDS allowlist
    - Never raises — all exceptions return None (graceful fallback)
    - Returns None for 'auto' workspace (no-op, no point routing to default)
    """
    if not _LLM_ROUTER_ENABLED:
        return None

    # Extract last user message
    last_user_content = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            last_user_content = (str(content) if isinstance(content, str) else str(content))[:500]
            break

    if not last_user_content:
        return None

    prompt = _build_router_prompt(last_user_content)
    timeout_s = _LLM_ROUTER_TIMEOUT_MS / 1000.0

    try:
        # P7-PERF: Reuse shared httpx client instead of per-request client creation.
        # The shared _http_client has connection pooling configured (20 keepalive, 100 max).
        # Use asyncio.wait_for for timeout instead of client-level timeout to avoid
        # creating a new client just for the shorter LLM router timeout.
        if _http_client is None:
            logger.debug("LLM router skipped: HTTP client not ready")
            return None
        payload = {
            "model": _LLM_ROUTER_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0,
                "num_predict": 40,
                "num_ctx": 2048,
                "keep_alive": "-1",  # Keep model warm — no cold-start penalty
            },
            "format": _ROUTER_JSON_SCHEMA,  # Ollama grammar-enforced JSON
        }
        resp = await asyncio.wait_for(
            _http_client.post(
                f"{_LLM_ROUTER_OLLAMA_URL}/api/generate",
                json=payload,
            ),
            timeout=timeout_s,
        )
        resp.raise_for_status()
        data = resp.json()
        raw_response = data.get("response", "").strip()

        # Parse and validate
        parsed = json.loads(raw_response)
        workspace = str(parsed.get("workspace", "")).strip()
        confidence = float(parsed.get("confidence", 0.0))

        # Validate workspace ID against allowlist
        if workspace not in _VALID_WORKSPACE_IDS:
            logger.warning(
                "LLM router returned unknown workspace '%s' — falling back to keywords",
                workspace,
            )
            return None

        # Don't return 'auto' — it's the default, no routing gain
        if workspace == "auto":
            return None

        if confidence < _LLM_ROUTER_CONFIDENCE_THRESHOLD:
            logger.debug(
                "LLM router low confidence %.2f for '%s' — falling back to keywords",
                confidence,
                workspace,
            )
            return None

        logger.info(
            "LLM router: '%s' → workspace='%s' confidence=%.2f",
            last_user_content[:60],
            workspace,
            confidence,
        )
        return workspace

    except httpx.TimeoutException:
        logger.debug(
            "LLM router timed out after %dms — falling back to keywords",
            _LLM_ROUTER_TIMEOUT_MS,
        )
        return None
    except Exception as e:
        logger.debug("LLM router error (non-fatal): %s — falling back to keywords", e)
        return None


def _detect_workspace(messages: list[dict]) -> str | None:
    """Detect the most appropriate workspace from the last user message.

    Uses weighted keyword scoring: each keyword has a weight (1-3) reflecting
    signal strength. The workspace with the highest score above its threshold wins.

    Returns a workspace ID string, or None if no strong signal found
    (caller should use the default 'auto' routing in that case).

    Routing is determined by score, not arbitrary priority order:
    - "write an exploit in Python" → security wins (exploit=3 + python=1=4 vs coding=3)
    - "analyze this malware" → security wins (malware=2 + analyze=2=4 vs reasoning=2)
    - "step by step comparison of frameworks" → reasoning wins (step by step=3 + compare=2=5)

    P7-PERF: Uses pre-compiled _KEYWORD_CACHE with pre-lowercased keywords to avoid
    repeated .lower() calls and dict iteration overhead.
    """
    # Find the last user message — reversed() stops at first hit (O(1) for recent msgs)
    last_user_content = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user_content = str(msg.get("content", ""))[:2000].lower()
            break

    if not last_user_content:
        return None

    # P7-PERF: Use pre-compiled keyword cache for faster scoring
    scores: dict[str, int] = {}
    for workspace_id, keywords in _KEYWORD_CACHE.items():
        score = sum(weight for kw, weight in keywords.items() if kw in last_user_content)
        threshold = _WORKSPACE_ROUTING[workspace_id]["threshold"]
        if score >= threshold:
            scores[workspace_id] = score

    if not scores:
        return None

    # Redteam takes priority over security when both exceed threshold
    # (same model family, but redteam is more permissive)
    if "auto-redteam" in scores and "auto-security" in scores and scores["auto-redteam"] >= 5:
        return "auto-redteam"

    return max(scores, key=lambda k: scores[k])


_raw_api_key = os.environ.get("PIPELINE_API_KEY", "")
if not _raw_api_key:
    import sys

    print(
        "FATAL: PIPELINE_API_KEY is not set. "
        "Set PIPELINE_API_KEY in .env before starting the pipeline. "
        "Example: PIPELINE_API_KEY=$(openssl rand -hex 32)",
        file=sys.stderr,
    )
    sys.exit(1)
PIPELINE_API_KEY: str = _raw_api_key

# Concurrency limiter — prevents Ollama overload when all workers are busy
_MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT_REQUESTS", "20"))

# Semaphore acquisition timeout in milliseconds. Default 50ms survives normal
# scheduling jitter. Set to 0 to restore original 1ms non-blocking behavior.
try:
    _SEMAPHORE_TIMEOUT = float(os.environ.get("SEMAPHORE_TIMEOUT_MS", "50")) / 1000.0
except ValueError:
    _SEMAPHORE_TIMEOUT = 0.050
    logger.warning("Invalid SEMAPHORE_TIMEOUT_MS value — must be a number. Using default: 50ms")
_request_semaphore: asyncio.Semaphore | None = None

# ── Per-workspace + per-API-key semaphores (M6-T05/T06) ───────────────────────
_workspace_semaphores: dict[str, asyncio.Semaphore] = {}
_workspace_sem_lock = asyncio.Lock()
_api_key_semaphores: dict[str, asyncio.Semaphore] = {}
_api_key_sem_lock = asyncio.Lock()


def _get_workspace_concurrency_limit(workspace_id: str) -> int:
    """Return the configured concurrency limit for a workspace.

    Order:
        1. WORKSPACE_CONCURRENCY_<id> env (e.g., WORKSPACE_CONCURRENCY_AUTO_CODING=4)
        2. workspace's `max_concurrent` field in WORKSPACES dict
        3. PORTAL5_DEFAULT_WORKSPACE_CONCURRENCY env (default: 5)
    """
    env_key = f"WORKSPACE_CONCURRENCY_{workspace_id.upper().replace('-', '_')}"
    if env_key in os.environ:
        return int(os.environ[env_key])
    ws = WORKSPACES.get(workspace_id, {})
    if "max_concurrent" in ws:
        return ws["max_concurrent"]
    return int(os.environ.get("PORTAL5_DEFAULT_WORKSPACE_CONCURRENCY", "5"))


async def _acquire_workspace_sem(workspace_id: str) -> asyncio.Semaphore:
    async with _workspace_sem_lock:
        sem = _workspace_semaphores.get(workspace_id)
        if sem is None:
            limit = _get_workspace_concurrency_limit(workspace_id)
            sem = asyncio.Semaphore(limit)
            _workspace_semaphores[workspace_id] = sem
            logger.info("Workspace semaphore created: %s limit=%d", workspace_id, limit)
        return sem


def _api_key_limit(key_hash: str) -> int:
    prefix = key_hash[:8]
    env_key = f"API_KEY_CONCURRENCY_{prefix.upper()}"
    if env_key in os.environ:
        return int(os.environ[env_key])
    return int(os.environ.get("PORTAL5_DEFAULT_API_KEY_CONCURRENCY", "10"))


async def _acquire_api_key_sem(api_key: str) -> asyncio.Semaphore | None:
    if not api_key:
        return None
    import hashlib
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    async with _api_key_sem_lock:
        sem = _api_key_semaphores.get(key_hash)
        if sem is None:
            limit = _api_key_limit(key_hash)
            sem = asyncio.Semaphore(limit)
            _api_key_semaphores[key_hash] = sem
        return sem

# ── Ollama per-request TTFT tuning ────────────────────────────────────────────
# keep_alive: how long Ollama keeps the model loaded after a request completes.
#   "-1" = never unload. Eliminates the 10-30s cold-start on the next request.
#   Native Ollama default is ~5 min; docker-ollama sets OLLAMA_KEEP_ALIVE=24h
#   server-wide, but native installs don't get that. Injecting it per-request
#   covers both cases reliably.
# num_batch: tokens processed per prompt-evaluation pass (Ollama default: 512).
#   2048 = 4× throughput during prefill — cuts TTFT on long conversation histories.
#   Safe upper bound: match your model's training context / 8. 2048 fits all
#   models in the catalog without exceeding their attention window.
_OLLAMA_KEEP_ALIVE: str = os.environ.get("OLLAMA_KEEP_ALIVE_REQUEST", "-1")
try:
    _OLLAMA_NUM_BATCH: int = int(os.environ.get("OLLAMA_NUM_BATCH", "2048"))
except ValueError:
    _OLLAMA_NUM_BATCH = 2048
    logger.warning(
        "Invalid OLLAMA_NUM_BATCH value — must be an integer. Using default: %d", _OLLAMA_NUM_BATCH
    )

# ── Routing visibility ─────────────────────────────────────────────────────────
# When true, the first line of every streaming response shows which workspace and
# model was selected. Set SHOW_ROUTING_STATUS=true in .env to enable.
# Default false — clean output. Useful for debugging auto-routing decisions.
_SHOW_ROUTING_STATUS: bool = os.environ.get("SHOW_ROUTING_STATUS", "false").lower() in (
    "1",
    "true",
    "yes",
)

registry: BackendRegistry | None = None
_health_task: asyncio.Task | None = None

# Shared httpx client for backend inference — P1: connection pool reused across
# all streaming and completion requests, avoiding TCP/TLS handshake overhead.
_http_client: httpx.AsyncClient | None = None


def _validate_workspace_hints(registry: BackendRegistry) -> list[str]:
    """Verify every WORKSPACES hint resolves to an actual backend model.

    Returns a list of error strings. Empty list = all hints reachable.

    Hints check against the union of `backend.models` for all backends
    whose `group` appears in `workspace_routing[ws_id]`.
    """
    group_models: dict[str, set[str]] = {}
    for be in registry.list_backends():
        group_models.setdefault(be.group, set()).update(be.models)

    errors: list[str] = []
    for ws_id, ws_cfg in WORKSPACES.items():
        groups = registry._workspace_routes.get(ws_id, [])
        available: set[str] = set()
        for g in groups:
            available |= group_models.get(g, set())

        for hint_key in ("model_hint", "mlx_model_hint"):
            hint = ws_cfg.get(hint_key)
            if hint and hint not in available:
                errors.append(
                    f"workspace={ws_id!r} {hint_key}={hint!r} "
                    f"not in any backend's models for groups={groups}. "
                    f"Add it to config/backends.yaml or correct the WORKSPACES hint."
                )
    return errors


def _inject_ollama_options(body: dict, workspace_id: str = "") -> dict:
    """Inject Ollama-specific TTFT performance defaults not already in the request.

    Only called for backends with type='ollama'. Skipped for MLX and vLLM which
    do not recognise these fields.

    - keep_alive: top-level Ollama field. Prevents model unloading between
      requests, eliminating the 10-30s cold-start on the next request.
    - num_batch: inside 'options'. Larger batch = faster prompt evaluation = lower
      TTFT on multi-turn conversations with long histories.
    - num_predict: output token cap for research/reasoning workspaces. Prevents
      DeepSeek-R1 CoT exhaustion (where thinking chain consumes all tokens and
      message.content is empty). 16384 tokens ≈ 50 pages — enough for any
      research response but cuts off runaway thinking chains.

    Uses setdefault() throughout — never overrides an explicit value from the
    caller (e.g. Open WebUI passing its own keep_alive).
    """
    body = dict(body)
    ws_cfg_local = WORKSPACES.get(workspace_id, {}) if workspace_id else {}
    # Big-model context cap (P5-BIG-001): if workspace defines context_limit, enforce it.
    ctx_limit = ws_cfg_local.get("context_limit")
    if ctx_limit:
        body.setdefault("options", {})
        body["options"].setdefault("num_ctx", ctx_limit)
    # Research/reasoning workspaces: cap output tokens to prevent CoT exhaustion.
    # DeepSeek-R1 (Ollama fallback) can exhaust all tokens in its thinking block,
    # leaving message.content empty. predict_limit is set per-workspace in WORKSPACES.
    predict_limit = ws_cfg_local.get("predict_limit")
    if predict_limit:
        body.setdefault("options", {})
        body["options"].setdefault("num_predict", predict_limit)
    body.setdefault("keep_alive", _OLLAMA_KEEP_ALIVE)
    opts: dict = dict(body.get("options") or {})
    opts.setdefault("num_batch", _OLLAMA_NUM_BATCH)
    body["options"] = opts
    return body


def _init_notifications(registry: BackendRegistry) -> None:
    """Initialize the notification dispatcher and scheduler."""
    global _notification_dispatcher, _notification_scheduler
    # Late import to avoid circular dependency — notifications imports cluster_backends
    from portal_pipeline.notifications import NotificationDispatcher, NotificationScheduler
    from portal_pipeline.notifications.channels import (
        EmailChannel,
        PushoverChannel,
        SlackChannel,
        TelegramChannel,
        WebhookChannel,
    )

    _notification_dispatcher = NotificationDispatcher()

    # Register configured channels — share the pipeline's HTTP connection pool
    _notification_dispatcher.add_channel(SlackChannel(_http_client))
    _notification_dispatcher.add_channel(TelegramChannel(_http_client))
    _notification_dispatcher.add_channel(EmailChannel(_http_client))
    _notification_dispatcher.add_channel(PushoverChannel(_http_client))
    _notification_dispatcher.add_channel(WebhookChannel(_http_client))

    # Run threshold check on first health cycle to catch any immediate issues
    _notification_dispatcher.check_thresholds_and_alert(registry)

    # Schedule daily summary
    _notification_scheduler = NotificationScheduler(_notification_dispatcher)

    # Attach scheduler to pipeline metrics BEFORE starting — _init_baseline_snapshot()
    # reads _request_count during start(), so the reference must be set first.
    from portal_pipeline.notifications import scheduler as notif_scheduler

    notif_scheduler._attach_to_pipeline(
        _notification_dispatcher,
        _request_count,
        _startup_time,
        registry,
    )

    _notification_scheduler.start()


async def _warmup_auto_model(registry: BackendRegistry) -> None:
    """Pre-load the auto workspace's default inference model on startup.

    Ollama lazily loads models on first request. A cold load of an 8B model
    takes 10-30s on HDD, 1-5s on SSD/NFS. By making a minimal generation call
    during startup, subsequent user requests skip this penalty entirely.

    Runs inside _run_startup_warmups — errors are logged but swallowed.
    """
    if _http_client is None:
        logger.debug("Warmup skipped: HTTP client not ready")
        return
    try:
        backend = registry.get_backend_for_workspace("auto")
        if backend is None:
            logger.debug("Warmup skipped: no healthy auto backend")
            return

        # Minimal prompt: one token of output, fastest model already in memory
        warmup_payload = {
            "model": backend.models[0] if backend.models else "dolphin-llama3:8b",
            "prompt": "ok",
            "stream": False,
            "options": {"num_predict": 1},
        }

        resp = await _http_client.post(backend.chat_url, json=warmup_payload)
        if resp.status_code == 200:
            logger.info(
                "Warmup complete: %s model '%s' pre-loaded",
                backend.type,
                warmup_payload["model"],
            )
        else:
            logger.debug(
                "Warmup backend %s returned HTTP %d — will load on first use",
                backend.id,
                resp.status_code,
            )
    except Exception as e:
        logger.debug("Model warmup failed (non-fatal): %s", e)


async def _warmup_llm_router() -> None:
    """Pre-load the LLM intent-router model on startup.

    Every request routed through the 'auto' workspace calls _route_with_llm(),
    which sends a generation request to the router model before any inference
    happens. On a cold Ollama instance this adds 30-60s of model-loading time
    to the first auto request even when the inference model is already warm.

    This warmup fires a single minimal generate call at startup so the router
    model is resident in memory when the first user request arrives.

    Skipped when LLM routing is disabled (LLM_ROUTER_ENABLED=false).
    """
    if not _LLM_ROUTER_ENABLED:
        return
    if _http_client is None:
        logger.debug("LLM router warmup skipped: HTTP client not ready")
        return
    try:
        resp = await _http_client.post(
            f"{_LLM_ROUTER_OLLAMA_URL}/api/generate",
            json={
                "model": _LLM_ROUTER_MODEL,
                "prompt": "ok",
                "stream": False,
                "options": {"num_predict": 1, "keep_alive": "-1"},
            },
        )
        if resp.status_code == 200:
            logger.info("Warmup complete: LLM router model '%s' pre-loaded", _LLM_ROUTER_MODEL)
        else:
            logger.debug(
                "LLM router warmup returned HTTP %d — router will cold-load on first use",
                resp.status_code,
            )
    except Exception as e:
        logger.debug("LLM router warmup failed (non-fatal): %s", e)


async def _run_startup_warmups(registry: BackendRegistry) -> None:
    """Fire all startup warmups in parallel.

    Runs as a background task so pipeline startup is not blocked.
    Both sub-tasks swallow exceptions — a failed warmup never crashes the pipeline.

    Order matters: both fire simultaneously so neither has to wait for the other.
    The LLM router warmup and the inference warmup are fully independent.
    """
    await asyncio.gather(
        _warmup_auto_model(registry),
        _warmup_llm_router(),
        return_exceptions=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global registry, _health_task, _request_semaphore, _http_client
    global _notification_dispatcher, _notification_scheduler, _state_save_task
    _request_semaphore = asyncio.Semaphore(_MAX_CONCURRENT)
    # P5-FIX: pre-create Prometheus multiproc dir at startup so workers don't race.
    if (mp_dir := os.environ.get("PROMETHEUS_MULTIPROC_DIR")):
        os.makedirs(mp_dir, exist_ok=True)
    # P1: create shared client with a connection pool sized for concurrent inference
    # Timeout raised to 300s: cold-loading 32B models under memory pressure takes
    # 2-4 min before the first token. 120s was causing S3-18 streaming timeouts.
    # connect stays 5s — local backends should bind immediately.
    _http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(300.0, connect=5.0),
        limits=httpx.Limits(
            max_keepalive_connections=20,
            max_connections=100,
        ),
    )
    registry = BackendRegistry()
    hint_errors = _validate_workspace_hints(registry)
    if hint_errors:
        for e in hint_errors:
            logger.error("HINT VALIDATION: %s", e)
        if os.environ.get("STRICT_HINT_VALIDATION", "false").lower() in ("true", "1", "yes"):
            raise RuntimeError(
                f"STRICT_HINT_VALIDATION=true and {len(hint_errors)} hint(s) failed validation. "
                "See logs above. Set STRICT_HINT_VALIDATION=false to start anyway."
            )
        else:
            logger.warning(
                "HINT VALIDATION: %d hint(s) failed but STRICT_HINT_VALIDATION=false — starting anyway. "
                "Hints will silently fall back at request time. Fix backends.yaml or WORKSPACES.",
                len(hint_errors),
            )
    await registry.health_check_all()
    # Load persisted metrics state from disk (survives restarts)
    _load_state()
    # Pre-warm: load the inference model AND the LLM router model in parallel so
    # the first 'auto' request is not penalized by two sequential cold-loads:
    # (1) router model classification (~30-60s if cold) then
    # (2) inference model generation (~10-30s if cold).
    # Both fire simultaneously as background tasks — startup is not blocked.
    asyncio.create_task(_run_startup_warmups(registry))
    # Power metrics polling (M6-T02) — graceful if daemon not running
    asyncio.create_task(_power_polling_loop())
    healthy = registry.list_healthy_backends()
    logger.info("Portal Pipeline started. Healthy backends: %d", len(healthy))
    if not healthy:
        logger.warning(
            "No healthy backends on startup — check Ollama is running and "
            "config/backends.yaml URLs are reachable from this container"
        )

    # ── Notifications: alerts + daily summaries ──────────────────────────────
    if os.environ.get("NOTIFICATIONS_ENABLED", "false").lower() in ("true", "1", "yes"):
        _init_notifications(registry)

    async def _on_health(r: "BackendRegistry") -> None:
        if _notification_dispatcher:
            await _notification_dispatcher.check_thresholds_and_alert(r)

    _health_task = asyncio.create_task(
        registry.start_health_loop(on_health_check=_on_health)
    )

    # Background task: persist metrics state to disk every 60s
    _state_save_task = asyncio.create_task(_state_save_loop(interval=60))

    yield

    # Final state save on shutdown
    _save_state()
    if _state_save_task:
        _state_save_task.cancel()
    if _health_task:
        _health_task.cancel()
    if _http_client:
        await _http_client.aclose()
    if _notification_scheduler:
        _notification_scheduler.stop()
    await BackendRegistry.close_health_client()


try:
    _PKG_VERSION = importlib.metadata.version("portal-5")
except importlib.metadata.PackageNotFoundError:
    _PKG_VERSION = "dev"
app = FastAPI(title="Portal Pipeline", version=_PKG_VERSION, lifespan=lifespan)


def _verify_key(authorization: str | None) -> None:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(token.encode(), PIPELINE_API_KEY.encode()):
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.get("/health")
async def health() -> dict:
    if registry is None:
        raise HTTPException(status_code=503, detail="Backend registry not initialised")
    healthy = registry.list_healthy_backends()
    return {
        "status": "ok" if healthy else "degraded",
        "version": _PKG_VERSION,
        "backends_healthy": len(healthy),
        "backends_total": len(registry.list_backends()),
        "workspaces": len(WORKSPACES),
    }


@app.get("/health/all")
async def health_all():
    """Aggregate health across pipeline + all MCPs + MLX proxy + Ollama."""
    checks: dict[str, dict] = {}
    checks["pipeline"] = {"status": "ok"}
    for name, url, path in [
        ("mlx_proxy", os.environ.get("MLX_PROXY_URL", "http://host.docker.internal:8081"), "/health"),
        ("ollama", os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434"), "/api/tags"),
        ("mcp_documents", "http://mcp-documents:8913", "/health"),
        ("mcp_sandbox", "http://mcp-sandbox:8914", "/health"),
        ("mcp_comfyui", "http://mcp-comfyui:8910", "/health"),
        ("mcp_video", "http://mcp-video:8911", "/health"),
        ("mcp_whisper", "http://mcp-whisper:8915", "/health"),
        ("mcp_tts", "http://mcp-tts:8916", "/health"),
        ("mcp_security", "http://mcp-security:8919", "/health"),
    ]:
        try:
            async with httpx.AsyncClient(timeout=3) as c:
                r = await c.get(f"{url}{path}")
                checks[name] = r.json() if r.status_code == 200 else {
                    "status": "degraded", "code": r.status_code,
                }
        except Exception as e:
            checks[name] = {"status": "down", "error": str(e)[:100]}
    return checks


PORTAL5_ADMIN_KEY = os.environ.get("PORTAL5_ADMIN_KEY", os.environ.get("PIPELINE_API_KEY", ""))


def _verify_admin_key(authorization: str | None) -> None:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(token.encode(), PORTAL5_ADMIN_KEY.encode()):
        raise HTTPException(status_code=401, detail="Invalid admin key")


@app.post("/admin/refresh-tools")
async def admin_refresh_tools(authorization: str | None = Header(None)):
    _verify_admin_key(authorization)
    from portal_pipeline.tool_registry import tool_registry
    n = await tool_registry.refresh(force=True)
    return {"refreshed": True, "tools_registered": n, "names": tool_registry.list_tool_names()}


@app.post("/notifications/test")
async def test_notifications(authorization: str | None = Header(None)) -> dict:
    """Fire a test alert and summary to verify notification channel configuration.

    Returns the status of each configured channel (sent / skipped / error).
    Requires NOTIFICATIONS_ENABLED=true and at least one channel configured.
    """
    _verify_key(authorization)

    if _notification_dispatcher is None:
        raise HTTPException(
            status_code=503,
            detail="Notification dispatcher not initialized (NOTIFICATIONS_ENABLED=false?)",
        )

    from portal_pipeline.notifications.events import AlertEvent, EventType, SummaryEvent

    results: dict[str, str] = {}

    # Fire a test alert
    alert = AlertEvent(
        type=EventType.BACKEND_DOWN,
        message="This is a test alert — Portal 5 notification test successful!",
        backend_id="test-backend",
    )
    try:
        await _notification_dispatcher.dispatch(alert)
        results["alert"] = "dispatched"
    except Exception as e:
        results["alert"] = f"error: {e}"

    # Fire a test summary (stats will be zeros/minimal for a test)
    summary = SummaryEvent(
        timestamp=datetime.now(timezone.utc),
        report_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        total_requests=sum(_request_count.values()),
        requests_by_workspace=dict(_request_count),
        healthy_backends=len(registry.list_healthy_backends()) if registry else 0,
        total_backends=len(registry.list_backends()) if registry else 0,
        uptime_seconds=time.time() - _startup_time if _startup_time else 0.0,
        requests_by_model=dict(_req_count_by_model),
        avg_tokens_per_second=0.0,
        total_input_tokens=0,
        total_output_tokens=0,
        avg_response_time_ms=0.0,
    )
    try:
        await _notification_dispatcher.dispatch(summary)
        results["summary"] = "dispatched"
    except Exception as e:
        results["summary"] = f"error: {e}"

    # Report per-channel configuration status
    results["channels"] = {
        "slack": "configured" if os.environ.get("SLACK_ALERT_WEBHOOK_URL") else "not configured",
        "telegram": "configured"
        if os.environ.get("TELEGRAM_ALERT_BOT_TOKEN")
        else "not configured",
        "email": "configured" if os.environ.get("SMTP_HOST") else "not configured",
        "pushover": "configured"
        if (os.environ.get("PUSHOVER_API_TOKEN") and os.environ.get("PUSHOVER_USER_KEY"))
        else "not configured",
        "webhook": "configured" if os.environ.get("WEBHOOK_URL") else "not configured",
    }

    # Report scheduler settings
    results["scheduler"] = {
        "enabled": os.environ.get("ALERT_SUMMARY_ENABLED", "true").lower() in ("true", "1", "yes"),
        "hour": int(os.environ.get("ALERT_SUMMARY_HOUR", "9")),
        "timezone": os.environ.get("ALERT_SUMMARY_TIMEZONE", "UTC"),
    }

    return {"status": "ok", "results": results}


@app.get("/metrics")
async def metrics() -> PlainTextResponse:
    """Prometheus-compatible metrics endpoint.

    Intentionally unauthenticated — Prometheus scrapes without credentials.
    """
    uptime = time.time() - _startup_time
    if registry is None:
        raise HTTPException(status_code=503, detail="Backend registry not initialised")
    healthy = len(registry.list_healthy_backends())
    total = len(registry.list_backends())

    lines = [
        "# HELP portal_backends_healthy Number of healthy backends",
        "# TYPE portal_backends_healthy gauge",
        f"portal_backends_healthy {healthy}",
        "# HELP portal_backends_total Total registered backends",
        "# TYPE portal_backends_total gauge",
        f"portal_backends_total {total}",
        "# HELP portal_uptime_seconds Process uptime in seconds",
        "# TYPE portal_uptime_seconds gauge",
        f"portal_uptime_seconds {uptime:.1f}",
        "# HELP portal_workspaces_total Number of configured workspaces",
        "# TYPE portal_workspaces_total gauge",
        f"portal_workspaces_total {len(WORKSPACES)}",
    ]
    # Combine hand-rolled metrics with prometheus_client metrics.
    # Use multiprocess collector when PROMETHEUS_MULTIPROC_DIR is set
    # (aggregates metrics across all uvicorn workers).
    # Cache the registry object — MultiProcessCollector reads from disk files,
    # so there's no need to reconstruct it on every scrape.
    global _mp_registry_cache, _mp_registry_dir_cache
    mp_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if mp_dir:
        # P5-FIX: prometheus_client writes per-pid files but does not create the
        # parent dir. Without this, the first /metrics scrape after worker fork
        # fails with errno-2 (see ACCEPTANCE_RESULTS S70-07, 2026-04-25).
        os.makedirs(mp_dir, exist_ok=True)
        if _mp_registry_cache is None or _mp_registry_dir_cache != mp_dir:
            from prometheus_client import multiprocess

            _mp_registry_cache = CollectorRegistry()
            multiprocess.MultiProcessCollector(_mp_registry_cache)
            _mp_registry_dir_cache = mp_dir
        prometheus_output = generate_latest(_mp_registry_cache).decode("utf-8")
    else:
        prometheus_output = generate_latest(_REGISTRY).decode("utf-8")
    return PlainTextResponse("\n".join(lines) + "\n" + prometheus_output)


@app.get("/v1/models")
async def list_models(authorization: str | None = Header(None)) -> dict:
    _verify_key(authorization)
    ts = int(time.time())
    models = [
        {
            "id": ws_id,
            "object": "model",
            "created": ts,
            "owned_by": "portal-5",
            "name": ws_cfg["name"],
            "description": ws_cfg["description"],
        }
        for ws_id, ws_cfg in WORKSPACES.items()
    ]
    return {"object": "list", "data": models}


async def _try_non_streaming(
    backend: Any,
    body: dict,
    workspace_id: str,
    start_time: float,
    *,
    enforce_hint: bool = True,
) -> JSONResponse | None:
    """Try non-streaming completion from a single backend.

    Returns JSONResponse on success, None on failure (caller tries next backend).
    When enforce_hint=True and the workspace has a model_hint, backends that
    don't carry the hinted model are skipped (returns None) so the loop tries
    the next backend. Set enforce_hint=False on the last candidate to accept
    any model as fallback.
    """
    if _http_client is None:
        return None
    ws_cfg = WORKSPACES.get(workspace_id, {})
    model_hint = ws_cfg.get("model_hint", "")
    mlx_hint = ws_cfg.get("mlx_model_hint", "")

    # Pick the right hint for the backend type
    if backend.type == "mlx" and mlx_hint:
        target_model = mlx_hint if mlx_hint in backend.models else ""
        if not target_model and enforce_hint:
            logger.debug(
                "MLX backend %s lacks hinted model %s for workspace=%s — skipping",
                backend.id,
                mlx_hint,
                workspace_id,
            )
            return None
        if not target_model:
            target_model = backend.models[0] if backend.models else "dolphin-llama3:8b"
    elif model_hint and model_hint in backend.models:
        target_model = model_hint
    elif model_hint and enforce_hint and backend.type != "mlx":
        logger.debug(
            "Backend %s lacks hinted model %s for workspace=%s — skipping",
            backend.id,
            model_hint,
            workspace_id,
        )
        return None
    else:
        target_model = backend.models[0] if backend.models else "dolphin-llama3:8b"
    req_body = {**body, "model": target_model, "stream": False}
    if backend.type == "ollama":
        req_body = _inject_ollama_options(req_body, workspace_id)

    try:
        resp = await _http_client.post(backend.chat_url, json=req_body)
        resp.raise_for_status()
        data = resp.json()

        # Translate Ollama's native non-streaming format to OpenAI format
        # Ollama returns: {"message": {"role": "assistant", "content": "..."}, "eval_count": N, ...}
        # Pipeline expects: {"choices": [{"message": {"content": "..."}, ...}], ...}
        if "message" in data and "choices" not in data:
            _msg = data.get("message", {})
            _content = _msg.get("content", "")
            _reasoning = (
                _msg.get("reasoning_content", "")
                or _msg.get("reasoning", "")
                or _msg.get("thinking", "")
            )
            if not _content and _reasoning:
                _content = _reasoning
                _reasoning = ""
            response_msg: dict = {
                "role": _msg.get("role", "assistant"),
                "content": _content,
            }
            if _reasoning:
                response_msg["reasoning_content"] = _reasoning
            data = {
                "id": f"chatcmpl-p5-{int(time.time())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": target_model,
                "choices": [
                    {
                        "index": 0,
                        "message": response_msg,
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": data.get("prompt_eval_count", 0),
                    "completion_tokens": data.get("eval_count", 0),
                    "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
                },
            }

        # Reasoning model normalisation: DeepSeek-R1, Qwen3 thinking mode, and Magistral
        # populate message.reasoning instead of message.content when the thinking chain
        # exhausts max_tokens. Promote reasoning→content so Open WebUI and all callers
        # always find the response in the standard OpenAI content field.
        try:
            for choice in data.get("choices") or []:
                msg = choice.get("message") or {}
                if not msg.get("content") and msg.get("reasoning"):
                    logger.debug(
                        "Backend %s: reasoning→content promotion for workspace=%s "
                        "(thinking chain consumed all tokens)",
                        backend.id,
                        workspace_id,
                    )
                    msg["content"] = msg["reasoning"]
        except Exception:
            pass  # Never let normalisation break a valid response

        _record_usage(
            model=target_model,
            workspace=workspace_id,
            data=data,
            elapsed_seconds=time.monotonic() - start_time,
        )
        # Inject model field — ensures callers can always identify which backend
        # served the request (Ollama includes it, MLX may not).
        if "model" not in data or not data["model"]:
            data["model"] = target_model
        logger.info(
            "Backend %s succeeded for workspace=%s model=%s",
            backend.id,
            workspace_id,
            target_model,
        )
        return JSONResponse(
            content=data,
            headers={"x-portal-route": f"{workspace_id};{backend.id};{target_model}"},
        )
    except Exception as e:
        logger.warning(
            "Backend %s failed for workspace=%s: %s — trying next candidate",
            backend.id,
            workspace_id,
            e,
        )
        return None


@app.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    authorization: str | None = Header(None),
) -> Any:
    _verify_key(authorization)

    content_length = int(request.headers.get("content-length", 0))
    if content_length > _MAX_REQUEST_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Request body too large (max {_MAX_REQUEST_BYTES // 1024 // 1024}MB)",
        )

    if _request_semaphore is None:
        raise HTTPException(status_code=503, detail="Request semaphore not initialised")
    try:
        await asyncio.wait_for(_request_semaphore.acquire(), timeout=_SEMAPHORE_TIMEOUT)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=503,
            detail="Server busy — too many concurrent requests. Please retry.",
            headers={"Retry-After": "5"},
        ) from None

    # Per-API-key semaphore (M6-T06)
    _api_key_raw = authorization.removeprefix("Bearer ").strip() if authorization else ""
    _api_sem = await _acquire_api_key_sem(_api_key_raw)
    if _api_sem is not None:
        try:
            await asyncio.wait_for(_api_sem.acquire(), timeout=_SEMAPHORE_TIMEOUT)
        except asyncio.TimeoutError:
            _request_semaphore.release()
            raise HTTPException(
                status_code=429,
                detail="API key at concurrency limit. Please retry.",
                headers={"Retry-After": "5"},
            ) from None

    _is_streaming = False
    workspace_id: str = "unknown"
    start_time = time.monotonic()
    try:
        if registry is None:
            raise HTTPException(status_code=503, detail="Backend registry not initialised")

        try:
            body = await request.json()
        except Exception:
            _concurrent_requests.dec()
            raise HTTPException(status_code=400, detail="Invalid JSON body") from None
        workspace_id = body.get("model") or "auto"
        stream = body.get("stream", False)

        # Content-aware routing for 'auto' workspace
        # Primary path: LLM-based intent classification (P5-FUT-006).
        # Fallback: weighted keyword scoring (_detect_workspace).
        # This lets users ask security/coding/reasoning questions through 'auto'
        # and get the right specialist model without manually switching workspaces.
        if workspace_id == "auto":
            messages = body.get("messages", [])
            # LLM router first — semantic intent, ~100ms, falls back on timeout/low confidence
            detected = await _route_with_llm(messages)
            if detected:
                logger.info(
                    "Auto-routing (LLM): detected workspace '%s' from message content", detected
                )
                workspace_id = detected
            else:
                # Keyword fallback — deterministic, zero-latency
                detected = _detect_workspace(messages)
                if detected:
                    logger.info(
                        "Auto-routing (keywords): detected workspace '%s' from message content",
                        detected,
                    )
                    workspace_id = detected

        # auto-vision text-only fallback: vision-language models (qwen3-vl:32b, Gemma 4)
        # return empty content when no image is provided. Detect absence of image_url
        # content parts and reroute to auto-reasoning for text-only queries, so users
        # always receive a meaningful response from the auto-vision workspace.
        if workspace_id == "auto-vision":
            messages = body.get("messages", [])
            has_image = any(
                isinstance(part, dict) and part.get("type") == "image_url"
                for msg in messages
                for part in (msg.get("content", []) if isinstance(msg.get("content"), list) else [])
            )
            if not has_image:
                logger.info(
                    "auto-vision: no image_url in request — rerouting to auto-reasoning "
                    "with vision system context injected"
                )
                workspace_id = "auto-reasoning"
                # Inject a system message so the reasoning model responds with
                # vision-domain vocabulary (image, visual, diagram, detect, etc.)
                # This ensures auto-vision text-only queries return domain-relevant
                # responses describing visual analysis capabilities rather than
                # generic reasoning answers.
                messages = body.get("messages", [])
                has_system = any(m.get("role") == "system" for m in messages)
                if not has_system:
                    vision_system = {
                        "role": "system",
                        "content": (
                            "You are a vision AI assistant. When answering questions about "
                            "your capabilities, focus on visual analysis tasks: image "
                            "understanding, diagram interpretation, visual element detection, "
                            "object recognition, scene description, chart reading, and "
                            "multimodal reasoning from images and diagrams."
                        ),
                    }
                    body = {**body, "messages": [vision_system] + messages}

        # Per-workspace semaphore (M6-T05)
        _ws_sem = await _acquire_workspace_sem(workspace_id)
        try:
            await asyncio.wait_for(_ws_sem.acquire(), timeout=_SEMAPHORE_TIMEOUT)
        except asyncio.TimeoutError:
            if _workspace_semaphore_busy_total is not None:
                _workspace_semaphore_busy_total.labels(workspace=workspace_id).inc()
            _request_semaphore.release()
            if _api_sem is not None:
                _api_sem.release()
            raise HTTPException(
                status_code=429,
                detail=f"Workspace '{workspace_id}' at concurrency limit. Try again shortly.",
                headers={"Retry-After": "5"},
            ) from None

        _request_count[workspace_id] = _request_count.get(workspace_id, 0) + 1
        _requests_total.labels(workspace=workspace_id).inc()
        _concurrent_requests.inc()
        global _peak_concurrent
        _peak_concurrent = max(_peak_concurrent, int(_concurrent_requests._value.get()))

        # Track persona usage — the "model" field in the request is the persona
        # (workspace ID) the user selected in Open WebUI.
        persona = body.get("model") or "auto"
        if persona in WORKSPACES:
            _record_persona(persona, "unknown")

        candidates = registry.get_backend_candidates(workspace_id)
        if not candidates:
            raise HTTPException(
                status_code=503,
                detail=(
                    "No healthy backends available. "
                    "Ensure Ollama is running and a model is pulled. "
                    "Check config/backends.yaml."
                ),
            )

        # mlx_only workspaces (bench-*): restrict candidates to MLX backends only.
        # A benchmark with a silent Ollama fallback is worse than a hard failure —
        # the result would be attributed to the wrong model entirely.
        # The existing 300s _http_client timeout already covers cold model loads
        # (~60s for 40GB models), so no additional polling or retry logic is needed.
        # Streaming path: after filtering to one MLX backend, len(candidates)==1 takes
        # the single-candidate direct-stream path — _stream_or_fallback never runs.
        _ws_cfg_local = WORKSPACES.get(workspace_id, {})
        _mlx_only = _ws_cfg_local.get("mlx_only", False)
        if _mlx_only:
            candidates = [b for b in candidates if b.type == "mlx"]
            if not candidates:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        f"Workspace '{workspace_id}' requires an MLX backend — "
                        "none are currently healthy. "
                        "Ensure mlx-proxy is running: ./launch.sh status"
                    ),
                )

        if not stream:
            # Non-streaming: try each backend in priority order until one succeeds.
            # Model hint is enforced (skip backends without the hinted model) for
            # all but the last candidate, where we accept any model as fallback.
            # Log the routing decision here — mirrors the streaming-path log at line ~1443
            # so that S3-19 log validation and operational log parsing work regardless
            # of whether the client requested streaming or non-streaming mode.
            logger.info(
                "Routing workspace=%s → %d candidate(s) stream=%s",
                workspace_id,
                len(candidates),
                stream,
            )
            for i, backend in enumerate(candidates):
                is_last = i == len(candidates) - 1
                # mlx_only: always enforce model hint — never substitute a different
                # model on the same backend. The benchmark result must be attributable
                # to exactly the model named in the workspace's mlx_model_hint.
                result = await _try_non_streaming(
                    backend,
                    body,
                    workspace_id,
                    start_time,
                    enforce_hint=True if _mlx_only else (not is_last),
                )
                if result is not None:
                    resolved_model = backend.models[0] if backend.models else "unknown"
                    _record_response_time(
                        resolved_model,
                        workspace_id,
                        time.monotonic() - start_time,
                    )
                    _record_persona(persona, resolved_model)
                    _concurrent_requests.dec()
                    return result
            # All backends failed
            _record_error(workspace_id, "all_backends_failed")
            _concurrent_requests.dec()
            if _mlx_only:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        f"Benchmark workspace '{workspace_id}': target MLX model did not respond. "
                        "Large models (>30GB) require up to 60s to load on first use. "
                        "If you just switched models, wait for the load to complete and retry. "
                        "To verify: ./launch.sh logs | grep 'Switching to model'"
                    ),
                )
            raise HTTPException(
                status_code=502,
                detail="All backends failed — check server logs",
            )

        # Streaming: try first backend. If the stream yields an error chunk early,
        # fall back to non-streaming with remaining candidates.
        backend = candidates[0]
        ws_cfg = WORKSPACES.get(workspace_id, {})
        model_hint = ws_cfg.get("model_hint", "")
        mlx_hint = ws_cfg.get("mlx_model_hint", "")

        # Pick the right hint for the backend type
        if backend.type == "mlx" and mlx_hint:
            if mlx_hint in backend.models:
                target_model = mlx_hint
            else:
                target_model = backend.models[0] if backend.models else "dolphin-llama3:8b"
                logger.warning(
                    "mlx_model_hint %r not in backend %s models — falling back to %r. "
                    "Add it to config/backends.yaml MLX list or correct the hint in WORKSPACES.",
                    mlx_hint, backend.id, target_model,
                )
        elif model_hint:
            if model_hint in backend.models:
                target_model = model_hint
            else:
                target_model = backend.models[0] if backend.models else "dolphin-llama3:8b"
                logger.warning(
                    "model_hint %r not in backend %s models — falling back to %r. "
                    "Add it to config/backends.yaml or correct the hint in WORKSPACES.",
                    model_hint, backend.id, target_model,
                )
        else:
            target_model = backend.models[0] if backend.models else "dolphin-llama3:8b"

        backend_body = {**body, "model": target_model}

        # Inject keep_alive + num_batch for Ollama backends.
        # Skipped for MLX (doesn't accept these fields) and vLLM (uses its own config).
        if backend.type == "ollama":
            backend_body = _inject_ollama_options(backend_body, workspace_id)

        # Resolve effective tool list for this request (M2)
        persona_data = _PERSONA_MAP.get(persona, {})
        effective_tools = _resolve_persona_tools(persona_data, workspace_id)
        _has_tools = bool(effective_tools) and backend.type == "ollama"

        if _has_tools:
            from portal_pipeline.tool_registry import tool_registry

            await tool_registry.refresh()
            tools_array = tool_registry.get_openai_tools(effective_tools)
            if tools_array:
                backend_body["tools"] = tools_array
                backend_body["tool_choice"] = backend_body.get("tool_choice", "auto")
                logger.info(
                    "Tool-call: workspace=%s persona=%s exposed %d tools",
                    workspace_id,
                    persona,
                    len(tools_array),
                )
            else:
                _has_tools = False

        logger.info(
            "Routing workspace=%s → backend=%s model=%s stream=%s (1/%d candidates)",
            workspace_id,
            backend.id,
            target_model,
            stream,
            len(candidates),
        )

        if len(candidates) == 1:
            # Single candidate — no fallback possible, return streaming directly
            _record_persona(persona, target_model)
            _stream_fn = (
                _stream_with_tool_loop(
                    backend.chat_url,
                    backend_body,
                    _request_semaphore,
                    workspace_id,
                    target_model,
                    persona,
                    set(effective_tools),
                    start_time,
                    ws_sem=_ws_sem,
                    api_sem=_api_sem,
                )
                if _has_tools
                else _stream_with_preamble(
                    backend.chat_url,
                    backend_body,
                    _request_semaphore,
                    workspace_id=workspace_id,
                    model=target_model,
                    start_time=start_time,
                    ws_sem=_ws_sem,
                    api_sem=_api_sem,
                )
            )
            _streaming_response = StreamingResponse(
                _stream_fn,
                media_type="text/event-stream",
                headers={"x-portal-route": f"{workspace_id};{backend.id};{target_model}"},
            )
            _is_streaming = True
            return _streaming_response

        # Multiple candidates — streaming with non-streaming fallback.
        # Try streaming from first backend; if it fails, fall back to non-streaming
        # from the remaining candidates.
        remaining = candidates[1:]

        async def _stream_or_fallback() -> AsyncIterator[bytes]:
            stream_failed = False
            try:
                _inner_stream = (
                    _stream_with_tool_loop(
                        backend.chat_url,
                        backend_body,
                        _request_semaphore,
                        workspace_id,
                        target_model,
                        persona,
                        set(effective_tools),
                        start_time,
                        ws_sem=_ws_sem,
                        api_sem=_api_sem,
                    )
                    if _has_tools
                    else _stream_with_preamble(
                        backend.chat_url,
                        backend_body,
                        _request_semaphore,
                        workspace_id=workspace_id,
                        model=target_model,
                        start_time=start_time,
                        ws_sem=_ws_sem,
                        api_sem=_api_sem,
                    )
                )
                async for chunk in _inner_stream:
                    if b'"error"' in chunk:
                        stream_failed = True
                    yield chunk
            except Exception:
                stream_failed = True

            if stream_failed and remaining:
                logger.info(
                    "Stream from %s failed, falling back to non-streaming for workspace=%s",
                    backend.id,
                    workspace_id,
                )
                fallback_body = {**body, "stream": False}
                for j, fb in enumerate(remaining):
                    fb_last = j == len(remaining) - 1
                    result = await _try_non_streaming(
                        fb, fallback_body, workspace_id, start_time, enforce_hint=not fb_last
                    )
                    if result is not None:
                        # Wrap non-streaming response as SSE for Open WebUI
                        import json as _json

                        data = _json.loads(result.body)
                        ts = int(time.time())
                        rid = f"chatcmpl-p5-{ts}"
                        # Emit role chunk
                        role_payload = {
                            "id": rid,
                            "object": "chat.completion.chunk",
                            "created": ts,
                            "model": workspace_id,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"role": "assistant", "content": ""},
                                    "finish_reason": None,
                                }
                            ],
                        }
                        yield f"data: {_json.dumps(role_payload)}\n\n".encode()
                        # Emit content chunk
                        content = ""
                        if "choices" in data and data["choices"]:
                            msg = data["choices"][0].get("message", {})
                            # Reasoning model fallback: promote reasoning→content
                            content = msg.get("content", "") or msg.get("reasoning", "")
                        if content:
                            content_payload = {
                                "id": rid,
                                "object": "chat.completion.chunk",
                                "created": ts,
                                "model": workspace_id,
                                "choices": [
                                    {
                                        "index": 0,
                                        "delta": {"content": content},
                                        "finish_reason": None,
                                    }
                                ],
                            }
                            yield f"data: {_json.dumps(content_payload)}\n\n".encode()
                        # Emit done
                        done_payload = {
                            "id": rid,
                            "object": "chat.completion.chunk",
                            "created": ts,
                            "model": workspace_id,
                            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                        }
                        yield f"data: {_json.dumps(done_payload)}\n\n".encode()
                        yield b"data: [DONE]\n\n"
                        return

        _streaming_response = StreamingResponse(
            _stream_or_fallback(),
            media_type="text/event-stream",
            headers={"x-portal-route": f"{workspace_id};{backend.id};{target_model}"},
        )
        _record_persona(persona, target_model)
        _is_streaming = True
        return _streaming_response
    except HTTPException:
        _concurrent_requests.dec()
        raise
    except Exception:
        _record_error(workspace_id, "unexpected_error")
        _concurrent_requests.dec()
        raise
    finally:
        if not _is_streaming:
            # Non-streaming: response fully awaited above, safe to release here
            # Streaming: generator releases after stream completes
            _request_semaphore.release()
            if _ws_sem is not None:
                _ws_sem.release()
            if _api_sem is not None:
                _api_sem.release()


async def _stream_with_tool_loop(
    backend_url: str,
    body: dict,
    sem: asyncio.Semaphore,
    workspace_id: str,
    model: str,
    persona: str,
    effective_tools: set[str],
    start_time: float | None = None,
    ws_sem: asyncio.Semaphore | None = None,
    api_sem: asyncio.Semaphore | None = None,
) -> AsyncIterator[bytes]:
    """Stream from backend, dispatching tool calls and re-injecting results.

    Yields the user-visible SSE stream. Tool-call chunks are passed through
    (OWUI renders them); tool results are emitted as custom SSE events.
    Loop continues until finish_reason=stop or MAX_TOOL_HOPS is reached.
    """
    try:
        async for chunk in _stream_with_tool_loop_impl(
            backend_url, body, workspace_id, model, persona, effective_tools, start_time
        ):
            yield chunk
    finally:
        # Release all semaphores acquired by chat_completions on the streaming path.
        # Mirror _stream_with_preamble's pattern (single-sem release in its own finally).
        sem.release()
        if ws_sem is not None:
            ws_sem.release()
        if api_sem is not None:
            api_sem.release()


async def _stream_with_tool_loop_impl(
    backend_url: str,
    body: dict,
    workspace_id: str,
    model: str,
    persona: str,
    effective_tools: set[str],
    start_time: float | None = None,
) -> AsyncIterator[bytes]:
    """Inner implementation for _stream_with_tool_loop (no semaphore ownership)."""
    request_id = f"chatcmpl-p5-{int(time.time())}"
    hop = 0
    current_body = dict(body)

    while hop < MAX_TOOL_HOPS:
        hop += 1

        # Accumulators for this iteration
        tool_calls_buf: list[dict] = []
        finish_reason: str | None = None
        _ollama_tool_calls: list[dict] | None = None

        # Emit preamble (role chunk) on first hop
        if hop == 1:
            ts = int(time.time())
            role_chunk = {
                "id": request_id,
                "object": "chat.completion.chunk",
                "created": ts,
                "model": workspace_id,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": ""},
                        "finish_reason": None,
                    }
                ],
            }
            yield f"data: {json.dumps(role_chunk)}\n\n".encode()
            if _SHOW_ROUTING_STATUS:
                ws_name = WORKSPACES.get(workspace_id, {}).get("name", workspace_id)
                status_chunk = {
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "created": ts,
                    "model": workspace_id,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": f"`⚡ {ws_name} → {model}`\n\n"},
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(status_chunk)}\n\n".encode()

        # Stream from backend
        try:
            async with _http_client.stream("POST", backend_url, json=current_body) as resp:
                if resp.status_code != 200:
                    err = await resp.aread()
                    logger.error(
                        "Tool-loop backend returned HTTP %d: %s", resp.status_code, err[:200]
                    )
                    yield (
                        f"data: {json.dumps({'error': f'Backend HTTP {resp.status_code}'})}\n\n"
                    ).encode()
                    return

                _is_ollama_native = "/api/chat" in backend_url and "/v1/" not in backend_url
                rid = f"chatcmpl-p5-{int(time.time())}"
                ts = int(time.time())

                async for chunk in resp.aiter_bytes():
                    if not chunk:
                        continue
                    if _is_ollama_native:
                        chunk_text = chunk.decode("utf-8", errors="replace")
                        for line in chunk_text.splitlines():
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                obj = json.loads(line)
                            except Exception:
                                continue
                            msg = obj.get("message") or {}

                            # Capture tool calls from Ollama native format
                            if "tool_calls" in msg and msg["tool_calls"]:
                                _ollama_tool_calls = msg["tool_calls"]
                                # Forward tool_calls as SSE so OWUI can render
                                for tc in msg["tool_calls"]:
                                    tc_sse = {
                                        "id": rid,
                                        "object": "chat.completion.chunk",
                                        "created": ts,
                                        "model": workspace_id,
                                        "choices": [
                                            {
                                                "index": 0,
                                                "delta": {
                                                    "tool_calls": [
                                                        {
                                                            "index": 0,
                                                            "id": tc.get("id", f"call_{rid}"),
                                                            "type": "function",
                                                            "function": {
                                                                "name": tc.get("function", {}).get(
                                                                    "name", ""
                                                                ),
                                                                "arguments": json.dumps(
                                                                    tc.get("function", {}).get(
                                                                        "arguments", {}
                                                                    )
                                                                ),
                                                            },
                                                        }
                                                    ],
                                                },
                                                "finish_reason": None,
                                            }
                                        ],
                                    }
                                    yield f"data: {json.dumps(tc_sse)}\n\n".encode()

                            content_delta = (
                                msg.get("content", "")
                                if isinstance(msg.get("content"), str)
                                else ""
                            )
                            reasoning_delta = (
                                msg.get("reasoning_content", "")
                                or msg.get("reasoning", "")
                                or msg.get("thinking", "")
                            )
                            if isinstance(reasoning_delta, dict):
                                reasoning_delta = reasoning_delta.get("text", "") or ""
                            done = obj.get("done", False)
                            if content_delta or reasoning_delta or done:
                                delta_payload: dict = {}
                                if content_delta:
                                    delta_payload["content"] = content_delta
                                if reasoning_delta:
                                    delta_payload["reasoning_content"] = reasoning_delta
                                sse_chunk = {
                                    "id": rid,
                                    "object": "chat.completion.chunk",
                                    "created": ts,
                                    "model": workspace_id,
                                    "choices": [
                                        {
                                            "index": 0,
                                            "delta": delta_payload,
                                            "finish_reason": "stop" if done else None,
                                        }
                                    ],
                                }
                                yield f"data: {json.dumps(sse_chunk)}\n\n".encode()

                            if done:
                                finish_reason = "tool_calls" if _ollama_tool_calls else "stop"
                                elapsed = (time.monotonic() - start_time) if start_time else None
                                _record_usage(
                                    model=obj.get("model", model),
                                    workspace=workspace_id,
                                    data=obj,
                                    elapsed_seconds=elapsed,
                                )
                    else:
                        # OpenAI SSE path — detect tool_calls in delta
                        chunk_text = chunk.decode("utf-8", errors="replace")
                        for line in chunk_text.splitlines():
                            if not line.startswith("data: "):
                                yield (line + "\n\n").encode() if line else b""
                                continue
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                yield b"data: [DONE]\n\n"
                                continue
                            try:
                                obj = json.loads(data_str)
                            except Exception:
                                yield (line + "\n\n").encode()
                                continue

                            choice = (obj.get("choices") or [{}])[0]
                            delta = choice.get("delta", {})

                            if "tool_calls" in delta:
                                for tc_delta in delta["tool_calls"]:
                                    idx = tc_delta.get("index", 0)
                                    while len(tool_calls_buf) <= idx:
                                        tool_calls_buf.append(
                                            {
                                                "id": "",
                                                "type": "function",
                                                "function": {"name": "", "arguments": ""},
                                            }
                                        )
                                    buf = tool_calls_buf[idx]
                                    if "id" in tc_delta:
                                        buf["id"] = tc_delta["id"]
                                    if "function" in tc_delta:
                                        fn = tc_delta["function"]
                                        if "name" in fn:
                                            buf["function"]["name"] += fn["name"]
                                        if "arguments" in fn:
                                            buf["function"]["arguments"] += fn["arguments"]

                            if choice.get("finish_reason"):
                                finish_reason = choice["finish_reason"]

                            yield (line + "\n\n").encode()
        except Exception as e:
            logger.error("Tool-loop stream error from %s: %s", backend_url, e)
            _record_error(workspace_id, "stream_error")
            yield (f"data: {json.dumps({'error': 'Backend connection error'})}\n\n").encode()
            return

        # After stream completes, check if tool calls were emitted
        if finish_reason == "tool_calls":
            # Collect tool calls (Ollama native vs OpenAI format)
            all_tool_calls = []
            if _ollama_tool_calls:
                for tc in _ollama_tool_calls:
                    fn = tc.get("function", {})
                    all_tool_calls.append(
                        {
                            "id": tc.get("id", f"call_{request_id}"),
                            "type": "function",
                            "function": {
                                "name": fn.get("name", ""),
                                "arguments": json.dumps(fn.get("arguments", {}))
                                if isinstance(fn.get("arguments"), dict)
                                else str(fn.get("arguments", "{}")),
                            },
                        }
                    )
            elif tool_calls_buf:
                all_tool_calls = tool_calls_buf

            if not all_tool_calls:
                return

            _tool_loop_hops.labels(workspace=workspace_id).observe(hop)

            # Hop limit guard
            if hop >= MAX_TOOL_HOPS:
                limit_msg = {
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": workspace_id,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "content": f"\n\n[Tool-use limit ({MAX_TOOL_HOPS} hops) reached. Returning partial result.]"
                            },
                            "finish_reason": "stop",
                        }
                    ],
                }
                yield f"data: {json.dumps(limit_msg)}\n\n".encode()
                yield b"data: [DONE]\n\n"
                return

            # Dispatch all tool calls in parallel
            dispatch_results = await asyncio.gather(
                *[
                    _dispatch_tool_call(tc, effective_tools, workspace_id, persona, request_id)
                    for tc in all_tool_calls
                ],
            )

            # Emit tool_result SSE events
            for _tc, result in zip(all_tool_calls, dispatch_results, strict=False):
                tool_result_event = {
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": workspace_id,
                    "tool_result": result,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": None}],
                }
                yield f"event: tool_result\ndata: {json.dumps(tool_result_event)}\n\n".encode()

            # Append assistant turn and tool results to message list
            assistant_msg = {
                "role": "assistant",
                "content": None,
                "tool_calls": all_tool_calls,
            }
            current_body["messages"] = (
                current_body.get("messages", []) + [assistant_msg] + dispatch_results
            )

            logger.info(
                "Tool loop hop=%d/%d workspace=%s tools_called=%s",
                hop,
                MAX_TOOL_HOPS,
                workspace_id,
                [tc["function"]["name"] for tc in all_tool_calls],
            )
            # Continue loop for next iteration
        else:
            # Model finished without tool calls — done
            if start_time is not None:
                _record_response_time(model, workspace_id, time.monotonic() - start_time)
            return


async def _stream_with_preamble(
    url: str,
    body: dict,
    sem: asyncio.Semaphore,
    workspace_id: str = "unknown",
    model: str = "unknown",
    start_time: float | None = None,
    ws_sem: asyncio.Semaphore | None = None,
    api_sem: asyncio.Semaphore | None = None,
) -> AsyncIterator[bytes]:
    """Emit an immediate OpenAI role chunk before connecting to the backend.

    Problem: without this, Open WebUI shows nothing (frozen input, no typing
    indicator) until Ollama returns its first token. That wait includes model
    load time (10-30s cold start) plus prompt prefill — entirely silent from
    the user's perspective.

    Fix: yield a valid OpenAI streaming chunk immediately. FastAPI flushes this
    to the client before the backend connection is even opened, causing Open WebUI
    to show the typing indicator and mark the response as started. The actual
    backend response follows as normal.

    The preamble chunk carries an empty delta content — it adds no visible text to
    the chat. If SHOW_ROUTING_STATUS=true, a second chunk annotates the response
    with the selected workspace and model name.
    """
    ts = int(time.time())
    request_id = f"chatcmpl-p5-{ts}"

    def _make_chunk(delta: dict) -> bytes:
        """Serialise a single OpenAI-compatible SSE chunk."""
        payload = {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": ts,
            "model": workspace_id,
            "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
        }
        return f"data: {json.dumps(payload)}\n\n".encode()

    # Empty role chunk — starts Open WebUI typing indicator with zero latency.
    yield _make_chunk({"role": "assistant", "content": ""})

    # Optional routing annotation — shows workspace + model at top of response.
    if _SHOW_ROUTING_STATUS:
        ws_name = WORKSPACES.get(workspace_id, {}).get("name", workspace_id)
        yield _make_chunk({"content": f"`⚡ {ws_name} → {model}`\n\n"})

    # Stream from backend.
    # Semaphore ownership: _stream_with_preamble owns sem and releases it in its
    # own finally block (below). _stream_from_backend_guarded is called with
    # sem=None so its finally does NOT also release — preventing double-release.
    # This closes the window where a client disconnect after the preamble yield but
    # before the backend stream starts would leave sem permanently acquired.
    try:
        async for chunk in _stream_from_backend_guarded(
            url, body, sem=None, workspace_id=workspace_id, model=model, start_time=start_time
        ):
            yield chunk
    finally:
        sem.release()
        if ws_sem is not None:
            ws_sem.release()
        if api_sem is not None:
            api_sem.release()


async def _stream_from_backend_guarded(
    url: str,
    body: dict,
    sem: asyncio.Semaphore | None,
    workspace_id: str = "unknown",
    model: str = "unknown",
    start_time: float | None = None,
) -> AsyncIterator[bytes]:
    """Stream from backend and optionally release semaphore when stream is complete.

    sem=None: caller (e.g. _stream_with_preamble) owns semaphore release.
    sem=Semaphore: this function releases it in its finally block.

    The sem=None path exists so _stream_with_preamble can own the full semaphore
    lifecycle via its own try/finally, closing the early-disconnect leak window.
    """
    if _http_client is None:
        logger.error("HTTP client not initialised — yielding error chunk")
        yield ("data: " + json.dumps({"error": "Pipeline not ready"}) + "\n\n").encode()
        if sem is not None:
            sem.release()
        return
    try:
        async with _http_client.stream("POST", url, json=body) as resp:
            if resp.status_code != 200:
                err = await resp.aread()
                logger.error(
                    "Backend %s returned HTTP %d: %s",
                    url,
                    resp.status_code,
                    err[:200].decode(errors="replace"),
                )
                _record_error(
                    workspace_id,
                    f"backend_http_{resp.status_code}",
                )
                yield (
                    "data: "
                    + json.dumps({"error": f"Backend returned HTTP {resp.status_code}"})
                    + "\n\n"
                ).encode()
                return
            # Detect Ollama native NDJSON format (bare JSON lines, no "data:" prefix)
            _is_ollama_native = "/api/chat" in url and "/v1/" not in url
            rid = f"chatcmpl-p5-{int(time.time())}"
            ts = int(time.time())
            async for chunk in resp.aiter_bytes():
                if chunk:
                    if _is_ollama_native:
                        # Ollama native NDJSON: translate to SSE for Open WebUI
                        chunk_text = chunk.decode("utf-8", errors="replace")
                        for line in chunk_text.splitlines():
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                obj = json.loads(line)
                            except Exception:
                                continue
                            msg = obj.get("message") or {}
                            content_delta = (
                                msg.get("content", "")
                                if isinstance(msg.get("content"), str)
                                else ""
                            )
                            reasoning_delta = (
                                msg.get("reasoning_content", "")
                                or msg.get("reasoning", "")
                                or msg.get("thinking", "")
                            )
                            if isinstance(reasoning_delta, dict):
                                reasoning_delta = reasoning_delta.get("text", "") or ""
                            done = obj.get("done", False)
                            if content_delta or reasoning_delta or done:
                                delta_payload: dict = {}
                                if content_delta:
                                    delta_payload["content"] = content_delta
                                if reasoning_delta:
                                    delta_payload["reasoning_content"] = reasoning_delta
                                sse_chunk = {
                                    "id": rid,
                                    "object": "chat.completion.chunk",
                                    "created": ts,
                                    "model": workspace_id,
                                    "choices": [
                                        {
                                            "index": 0,
                                            "delta": delta_payload,
                                            "finish_reason": "stop" if done else None,
                                        }
                                    ],
                                }
                                yield f"data: {json.dumps(sse_chunk)}\n\n".encode()
                            if obj.get("done") is True:
                                elapsed = (
                                    (time.monotonic() - start_time)
                                    if start_time is not None
                                    else None
                                )
                                _record_usage(
                                    model=obj.get("model", model),
                                    workspace=workspace_id,
                                    data=obj,
                                    elapsed_seconds=elapsed,
                                )
                                done_chunk = {
                                    "id": rid,
                                    "object": "chat.completion.chunk",
                                    "created": ts,
                                    "model": workspace_id,
                                    "choices": [
                                        {
                                            "index": 0,
                                            "delta": {},
                                            "finish_reason": "stop",
                                        }
                                    ],
                                }
                                yield f"data: {json.dumps(done_chunk)}\n\n".encode()
                                yield b"data: [DONE]\n\n"
                    else:
                        # Non-native path (MLX, vLLM, /v1/ Ollama compat): keep existing logic
                        # P6: Check raw bytes for '"done"' before decode — skip 99% of chunks.
                        if b'"done"' in chunk:
                            chunk_text = chunk.decode("utf-8", errors="replace")
                            for line in chunk_text.splitlines():
                                line = line.strip()
                                if line.startswith("data:") and "done" in line:
                                    payload = line[5:].strip()
                                    if payload and payload != "[DONE]":
                                        try:
                                            usage_data = json.loads(payload)
                                            elapsed = (
                                                (time.monotonic() - start_time)
                                                if start_time is not None
                                                else None
                                            )
                                            _record_usage(
                                                model=usage_data.get("model", model),
                                                workspace=workspace_id,
                                                data=usage_data,
                                                elapsed_seconds=elapsed,
                                            )
                                        except Exception:
                                            logger.debug(
                                                "Could not parse usage payload from stream"
                                            )
                                        break
                        # OpenAI SSE: "data: [DONE]" terminator — no usage data, but record with elapsed time.
                        if b"data: [DONE]" in chunk:
                            elapsed = (
                                (time.monotonic() - start_time) if start_time is not None else None
                            )
                            _record_usage(
                                model=model,
                                workspace=workspace_id,
                                data={},
                                elapsed_seconds=elapsed,
                            )
                        yield chunk
    except Exception as e:
        logger.error("Stream error from %s: %s", url, e)
        _record_error(workspace_id, "stream_error")
        yield (
            "data: "
            + json.dumps({"error": "Backend connection error — check server logs"})
            + "\n\n"
        ).encode()
    finally:
        if start_time is not None:
            _record_response_time(model, workspace_id, time.monotonic() - start_time)
        if sem is not None:
            sem.release()  # Release AFTER generator is fully exhausted
