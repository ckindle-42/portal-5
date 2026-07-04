---
id: unit-claude-project-layout
kind: why
title: "CLAUDE.md \u2014 Project Layout"
sources:
- type: design
  path: CLAUDE.md
  section: Project Layout
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1783195000.805677
updated_at: 1783195000.805677
---


```
portal-5/
├── portal_pipeline/              # FastAPI Pipeline server (:9099)
│   ├── cluster_backends.py       # BackendRegistry — Ollama (+ vLLM-compatible), health-aware
│   ├── router_pipe.py            # FastAPI app, @app routes, lifespan, auth, option injection
│   ├── __main__.py               # Uvicorn entrypoint (multi-worker)
│   ├── router/                   # Decomposed pipeline modules (facade-exported by router_pipe.py)
│   │   ├── anthropic_compat.py  # /v1/messages ↔ OpenAI format bridge (Claude Code local mode)
│   │   ├── concurrency.py        # 3 semaphores + RequestSlot (single-owner lifecycle)
│   │   ├── metrics.py            # CollectorRegistry + all Prometheus collectors
│   │   ├── monitor.py            # Metal GPU memory + Ollama model state primitives
│   │   ├── power.py              # powermetrics polling, energy/cost, usage recording
│   │   ├── routing.py            # LLM router + keyword workspace detection
│   │   ├── state.py              # State persistence + per-event recorders
│   │   ├── streaming.py          # SSE streaming: _stream_from_backend_guarded, tool loop, preamble
│   │   ├── thinking.py           # Shared <think>…</think> strip + reasoning passthrough
│   │   ├── tools.py              # MCP tool dispatch (_dispatch_tool_call)
│   │   └── workspaces.py         # WORKSPACES dict, persona map, workspace tool helpers
│   ├── cli.py                    # Typed operator CLI (portal config show, …) — entry: portal
│   ├── tool_registry.py          # Tool discovery (polls MCP /tools), advertisement, dispatch
│   └── notifications/            # Operational alerts + daily summaries
│       ├── dispatcher.py         # Event bus: fans out to all configured channels
│       ├── events.py             # AlertEvent / SummaryEvent / EventType
│       ├── scheduler.py          # APScheduler daily summary
│       └── channels/             # Slack, Telegram, Email, Pushover, Webhook
├── portal_mcp/                   # MCP Tool Serve
