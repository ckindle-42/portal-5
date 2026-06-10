"""Portal 5 router package.

Each sub-module owns one concern; ``router_pipe.py`` is the facade that
re-exports their public names so external import paths are unchanged.

Sub-modules
-----------
concurrency
    Global request semaphore, per-workspace/API-key semaphores,
    :class:`RequestSlot` — single-owner lifecycle for all three semaphores
    and the concurrent-requests gauge within one request.
metrics
    Single ``CollectorRegistry`` and all Prometheus collectors.
power
    ``powermetrics`` polling, energy/cost accounting, usage recording.
routing
    Workspace detection — keyword scoring (Layer 2) and LLM-router fallback
    (Layer 1, Llama-3.2-3B-Instruct).
state
    Metrics-state persistence (``_save_state`` / ``_load_state``) and
    per-event recorders (``_record_error``, ``_record_persona``, …).
streaming
    Streaming transport — ``_stream_from_backend_guarded``,
    ``_stream_with_preamble``, ``_stream_with_tool_loop`` (+impl),
    ``_json_completion_to_sse``, ``_SHOW_ROUTING_STATUS``,
    ``_http_client`` (lifespan-injected).
tools
    MCP tool dispatch for the multi-hop tool loop.
workspaces
    ``WORKSPACES`` dict, persona map, workspace tool helpers,
    ``MAX_TOOL_HOPS``.

``router_pipe.py`` retains the FastAPI ``app``, all ``@app`` route handlers,
option injection, warmups, lifespan, and auth.
"""
