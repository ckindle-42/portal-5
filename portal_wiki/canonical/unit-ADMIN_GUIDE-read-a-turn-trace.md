---
id: unit-ADMIN_GUIDE-read-a-turn-trace
kind: mixed
title: "ADMIN_GUIDE — Read a turn trace"
sources:
- type: code
  path: portal/platform/inference/router/handlers.py
- type: code
  path: portal/platform/inference/router/trace.py
claims: []
confidence: high
tags:
- docs
- operator
---

Every chat response carries an `X-Correlation-ID` header. Hand that value to
`GET /v1/trace/{correlation_id}` on the pipeline and the reply is the whole
turn: which workspace the request resolved to from whatever the client asked
for, how many backend candidates were available, and each tool the model
reached for with the verdict on whether its persona was allowed to. `GET
/v1/trace` lists recent turns newest first when the header was not kept.

Both need the pipeline key:

```
curl -s -H "Authorization: Bearer $PIPELINE_API_KEY" \
  http://localhost:9099/v1/trace | jq .
curl -s -H "Authorization: Bearer $PIPELINE_API_KEY" \
  "http://localhost:9099/v1/trace/p5-abc123def456" | jq .
```

A `404` means the turn aged out of the bounded store, predates the container
restart, or capture is off. Nothing is persisted across a restart by design.

## Why

The header was already being minted and stamped on log lines, so the shortest
path from a turn that misbehaved to the reason was a container log grep
against an id. Serving the record over the same port the client already talks
to removes that step, and keeping it key-authenticated matters because a
summary names the workspace, persona and model a turn resolved to.
