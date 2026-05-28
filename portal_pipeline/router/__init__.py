"""Portal 5 router package.

Sub-modules:
    workspaces  — WORKSPACES dict, persona map, workspace tool helpers

Sub-modules (each owns one concern; router_pipe.py is the facade that
re-exports their public names so external import paths are unchanged):
    workspaces  — WORKSPACES dict, persona map, workspace tool helpers
    metrics     — the single CollectorRegistry and all Prometheus collectors
    state       — metrics-state persistence + per-event recorders
    power       — powermetrics polling, energy/cost, usage recording
    tools       — MCP tool dispatch for the tool loop
    routing     — workspace detection (keywords) + LLM-router fallback

router_pipe.py retains the FastAPI app, all @app routes, request
concurrency/semaphores, option injection, warmups, lifespan, auth, and the
streaming core. Further extraction of those is deferred to a V2.
"""
