---
id: unit-router-app
kind: mixed
title: "Router app \u2014 FastAPI wiring and route binding"
sources:
- type: code
  path: portal/platform/inference/router/app.py
  commit: a234187e
last_generated_commit: a234187e
claims: []
confidence: high
tags:
- authored-v1
- platform
- inference
- router
created_at: 1785798046.446672
updated_at: 1785798046.446672
---

`app.py` is the FastAPI app wiring: it instantiates the app, binds the route
handlers, and attaches the middleware. It is the thing `router_pipe.app`
re-exports and uvicorn serves.

## Why

The app object is the pipeline's public face — the connection point Open
WebUI is configured against. Keeping its construction in one small module
means the route handlers (in `handlers`), the middleware, and the metadata
all bind in one place, and a change to the app surface (a new route, a new
middleware) has one obvious home rather than being scattered.

## Interfaces

Exports `app` (the `FastAPI` instance) with the routes bound and metadata
set. Serves the chat-completions, health, models, metrics, and admin
endpoints the handlers define.

## Gotchas

The app references the pipeline API key and auth — anything bound here must
not create import cycles with the handler modules it wires.
