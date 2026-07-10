"""Backwards-compat shim — canonical home is portal_pipeline.router.

Open WebUI's pipeline manifest references portal_pipeline.router_pipe.app
as its FastAPI app. This file preserves that contract by re-exporting
``app`` and the symbols downstream consumers historically imported.

New code should import from portal_pipeline.router.* directly.
"""

from __future__ import annotations

# Anthropic compat (router/anthropic_compat.py)
from portal_pipeline.router.anthropic_compat import (  # noqa: F401
    anthropic_to_openai_body,
    openai_response_to_anthropic,
    openai_stream_to_anthropic_sse,
)

# ── FastAPI app (the main thing OWUI imports) ──────────────────────────────────
from portal_pipeline.router.app import app  # noqa: F401

# Auth (router/auth.py)
from portal_pipeline.router.auth import (  # noqa: F401
    PIPELINE_API_KEY,
    _verify_admin_key,
    _verify_key,
)

# Concurrency (router/concurrency.py)
from portal_pipeline.router.concurrency import (  # noqa: F401
    _MAX_CONCURRENT,
    _SEMAPHORE_TIMEOUT,
    RequestSlot,
    _acquire_api_key_sem,
    _acquire_workspace_sem,
    _api_key_limit,
    _get_workspace_concurrency_limit,
)

# Handlers (router/handlers.py)
from portal_pipeline.router.handlers import (  # noqa: F401
    admin_refresh_tools,
    chat_completions,
    health,
    health_all,
    list_backends_endpoint,
    list_models,
    metrics,
    test_notifications,
)

# Lifespan (router/lifespan.py)
from portal_pipeline.router.lifespan import (  # noqa: F401
    _http_client,
    _notification_dispatcher,
    _notification_scheduler,
    _startup_time,
    _state_save_task,
    lifespan,
    registry,
)

# Metrics (router/metrics.py)
from portal_pipeline.router.metrics import (  # noqa: F401
    _REGISTRY,
    _concurrent_requests,
    _energy_by_workspace_ws,
    _energy_consumed_ws_total,
    _errors_total,
    _hint_fallback_total,
    _input_tokens,
    _output_tokens,
    _persona_usage,
    _power_ane_watts,
    _power_avg_1min_watts,
    _power_cpu_watts,
    _power_current_watts,
    _power_dram_watts,
    _power_gpu_watts,
    _reasoning_promotion_total,
    _record_response_time,
    _request_energy_ws,
    _requests_by_model,
    _requests_total,
    _response_time_seconds,
    _router_latency_seconds,
    _router_layer_total,
    _stream_content_yielded_total,
    _tokens_per_second,
    _tool_call_duration,
    _tool_call_errors,
    _tool_calls_total,
    _tool_loop_hops,
    _tool_workspace_strip,
    _total_response_time_ms,
    _workspace_semaphore_busy_total,
    _workspace_semaphore_busy_total_metric,
)

# Non-streaming (router/non_streaming.py)
from portal_pipeline.router.non_streaming import (  # noqa: F401
    _try_non_streaming,
)

# Power (router/power.py)
from portal_pipeline.router.power import (  # noqa: F401
    _POWERMETRICS_SOCKET,
    ELECTRICITY_RATE_USD_PER_KWH,
    _power_polling_loop,
    _record_usage,
)

# Pre-dispatch injection (router/preinject.py)
from portal_pipeline.router.preinject import (  # noqa: F401
    _inject_attached_files,
    _inject_system_prompt_append,
    _inject_temporal_context,
    _resolve_auto_routing,
    _resolve_persona_workspace,
    _resolve_vision_fallback,
)

# Routing (router/routing.py)
from portal_pipeline.router.routing import (  # noqa: F401
    _CODING_KEYWORDS,
    _LLM_ROUTER_ENABLED,
    _LLM_ROUTER_MODEL,
    _LLM_ROUTER_OLLAMA_URL,
    _SPL_KEYWORDS,
    _VALID_WORKSPACE_IDS,
    _build_router_prompt,
    _detect_workspace,
    _load_routing_config,
    _route_with_llm,
)

# ── Re-export historical public symbols ────────────────────────────────────────
# State persistence (router/state.py)
from portal_pipeline.router.state import (  # noqa: F401
    _STATE_FILE,
    _load_state,
    _peak_concurrent,
    _persona_usage_raw,
    _record_error,
    _record_persona,
    _req_count_by_error,
    _req_count_by_model,
    _request_count,
    _request_tps_count,
    _save_state,
    _state_save_loop,
    _total_input_tokens,
    _total_output_tokens,
    _total_tps,
)

# Streaming (router/streaming.py)
from portal_pipeline.router.streaming import (  # noqa: F401
    _json_completion_to_sse,
    _stream_from_backend_guarded,
    _stream_with_chain,
    _stream_with_preamble,
    _stream_with_secondary_chain,
    _stream_with_tool_loop,
    _stream_with_tool_loop_impl,
)

# Tools (router/tools.py)
from portal_pipeline.router.tools import (  # noqa: F401
    _dispatch_tool_call,
)

# Validation (router/validation.py)
from portal_pipeline.router.validation import (  # noqa: F401
    _inject_ollama_options,
    _model_supports_tools,
    _validate_workspace_hints,
)

# Workspaces (router/workspaces.py)
from portal_pipeline.router.workspaces import (  # noqa: F401
    _PERSONA_MAP,
    MAX_TOOL_HOPS,
    WORKSPACES,
    _resolve_persona_tools,
    _workspace_tools,
)
