---
id: unit-cluster-scale-stage-4-5-specialized-model-groups
kind: what
title: "CLUSTER_SCALE \u2014 Stage 4-5: Specialized Model Groups"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: portal/platform/inference/cluster_backends.py
last_generated_commit: fb9979b75eb4d70f331e849b80fc7326e8e61847
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.512875
updated_at: 1784946220.512875
---

Specialized nodes pin capacity to a routing group. Every backend entry carries
a `group:`, and `workspace_routing:` in the same file maps each workspace id to
an ordered list of groups: `auto-coding` lists `coding` before `general`, and
`auto-creative` lists `creative` first. `get_backend_candidates` walks those
groups in YAML order, so a `group: coding` node is preferred by `auto-coding`
traffic while still serving as fallback for everything else. A vLLM-hosted node
should declare `type: openai_compatible`. Because `config/backends.yaml` is
consumed only by the pipeline registry, Open WebUI, the MCP tool fleet, and the
Telegram and Slack channel bots — which all call the pipeline rather than the
registry — keep working after a routing-group edit.

## Why

Routing groups exist to separate capacity from policy. A backend entry states
which group it serves, and `workspace_routing` states which groups each
workspace prefers, so either side changes independently. `get_backend_candidates`
orders candidates by that group list, letting an operator steer traffic with one
YAML mapping instead of a router rewrite. Everything upstream of the pipeline
observes only the OpenAI surface, so moving which machine serves a workspace is
invisible to the clients — that invisibility is the payoff of a config-driven
registry.
