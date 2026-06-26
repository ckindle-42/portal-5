"""Portal 5 router package.

Each sub-module owns one concern; ``router_pipe.py`` is the facade that
re-exports their public names so external import paths are unchanged.

Sub-modules
-----------
anthropic_compat
    /v1/messages ↔ OpenAI format bridge (Claude Code local mode).
app
    ``FastAPI(...)`` instance and ``@app.<method>`` route wiring.
auth
    Bearer-token verification for /v1/* and /admin/* endpoints.
concurrency
    Global request semaphore, per-workspace/API-key semaphores,
    :class:`RequestSlot` — single-owner lifecycle for all three semaphores
    and the concurrent-requests gauge within one request.
handlers
    Route handler function bodies — one async function per endpoint.
lifespan
    ``lifespan`` async context manager — startup/shutdown wiring,
    notification init, model warmups.
metrics
    Single ``CollectorRegistry`` and all Prometheus collectors.
monitor
    Metal GPU memory + Ollama model state primitives.
non_streaming
    Non-streaming request dispatch (mirrors streaming.py for
    ``stream=False`` completion requests).
power
    ``powermetrics`` polling, energy/cost accounting, usage recording.
preinject
    Pre-dispatch request transforms — persona resolution, auto routing,
    vision fallback, temporal context, system prompt append, file
    attachment normalization.
routing
    Workspace detection — keyword scoring (Layer 2) and LLM-router fallback
    (Layer 1).
state
    Metrics-state persistence (``_save_state`` / ``_load_state``) and
    per-event recorders (``_record_error``, ``_record_persona``, …).
streaming
    Streaming transport — ``_stream_from_backend_guarded``,
    ``_stream_with_preamble``, ``_stream_with_tool_loop`` (+impl),
    ``_json_completion_to_sse``, ``_SHOW_ROUTING_STATUS``,
    ``_http_client`` (lifespan-injected).
thinking
    Shared ``<think>…</think>`` strip + reasoning passthrough.
tools
    MCP tool dispatch for the multi-hop tool loop.
validation
    Pre-flight workspace hint validation and per-backend option injection.
workspaces
    ``WORKSPACES`` dict, persona map, workspace tool helpers,
    ``MAX_TOOL_HOPS``.
"""

