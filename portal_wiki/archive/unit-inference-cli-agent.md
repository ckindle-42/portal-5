---
id: unit-inference-cli-agent
kind: mixed
title: "Inference CLI agent \u2014 dry decide-turn operator surface"
sources:
- type: code
  path: portal/platform/inference/cli/agent.py
  commit: 5fbf51f8
last_generated_commit: 5fbf51f8
claims: []
confidence: high
tags:
- authored-v1
- platform
- cli
created_at: 1785797845.125549
updated_at: 1785797845.125549
---

`portal agent` is the operator surface for the platform agent loop:
`agent_explain` runs a single dry decide-turn against the platform core with
the deterministic ranker, and `agent_proposed` lists the proposed agent
decisions.

## Why

The agent loop's decisions are normally invisible — they happen inside the
core and only their effects surface. The CLI makes a single decide-turn
inspectable, so an operator can ask "what would the ranker do with this
input" and see the deterministic answer without a live loop. This is the
debugging surface for the platform's decision layer.

## Interfaces

`agent_explain` takes an input and runs the dry decide-turn; `agent_proposed`
lists pending proposals; both register on `agent_app`.

## Gotchas

The decide-turn is explicitly *dry* — it exercises the ranker without
dispatching to models or tools, so its output is the decision, not the
consequence.
