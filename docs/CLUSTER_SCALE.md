# Portal 5 — Cluster Scale-Out Guide

<!-- WIKI:GENERATED unit=unit-cluster-scale-portal-5-cluster-scale-out-guide -->
Portal 5 scale-out is a config-only operation. Every inference node is one
entry in the `backends:` list of `config/backends.yaml`; `BackendRegistry`
reads that file once per pipeline process and health-probes each declared
node. Adding capacity therefore never touches Python — the operator appends a
backend entry, restarts the pipeline so `_load_config` re-reads the YAML, and
the health loop takes over reachability from then on. Routing policy lives in
the same file (`workspace_routing:`, `defaults.fallback_group`), so both node
inventory and traffic priority scale without a code change.

## Why

Scale-out belongs in `config/backends.yaml` because `BackendRegistry` is
deliberately configuration-driven. The module docstring fixes the operator
workflow: adding a cluster node is a YAML edit and a pipeline restart, never a
code change. Because the registry is a process-lifetime singleton loaded from
one file, a single-laptop install and a Mac Studio cluster differ only in how
many backend entries that file holds; the routing, health-check, and
request-selection paths are identical at any scale. Hardware grows; the binary
does not.
<!-- /WIKI:GENERATED -->

---

## Stage 1 → Stage 2: Add a Second Mac Studio

<!-- WIKI:GENERATED unit=unit-cluster-scale-stage-1-stage-2-add-a-second-mac-studio -->
Adding a second Ollama node has three steps. First, install Ollama on the new
machine and bind it to the network by launching it with `OLLAMA_HOST=0.0.0.0`
— the compose stack's own `ollama` service sets the same variable in
`deploy/portal-5/docker-compose.yml`. Second, declare the node in
`config/backends.yaml` with `type: ollama`, the node's base `url`, a routing
`group`, and a `models` list; `_load_config` builds a `Backend` from exactly
those fields, and a bare string model list is still accepted. Third, restart
the pipeline container, because the registry is a process-lifetime singleton
built in `router_pipe.lifespan`. After restart `start_health_loop` drives
`health_check_all`, which probes the node at `health_url` and drops it from
routing when unreachable, and `get_backend_candidates` shuffles healthy
same-group backends so traffic balances across both nodes.

```bash
docker compose restart portal-pipeline
```

## Why

There is no automatic network discovery in Portal 5: the registry never scans
the LAN, so a node must be declared in `config/backends.yaml` and the pipeline
restarted before it can serve. `BackendRegistry` is constructed exactly once in
`router_pipe.lifespan`, so `_load_config` parses YAML only at that instant;
"discovery" is declaration plus the health loop's reachability probing, not
scanning. This keeps scale-out deterministic and unit-testable — the suite
mocks the HTTP client, so a second node is exercised without any real daemon
running.
<!-- /WIKI:GENERATED -->

---

## Stage 3: vLLM for 70B Models

<!-- WIKI:GENERATED unit=unit-cluster-scale-stage-3-vllm-for-70b-models -->
A vLLM node for very large models is registered with `type: openai_compatible`.
`cluster_backends.py` names vLLM as the canonical example of that type and
derives its liveness probe from the type as well: `health_url` falls back to
`/health` for any backend that is neither `ollama` nor `omlx`. After starting
`vllm serve` on the target host, append one entry to the `backends:` list of
`config/backends.yaml` carrying `type: openai_compatible`, the base `url`, a
`group`, and the served `models`. An optional `health_path:` override repoints
the probe at a proxy that fronts the vLLM process. Because the OpenAI-compatible
surface means `chat_url` appends `/v1/chat/completions` for every backend type,
the streaming and routing code is engine-agnostic.

## Why

The `type` field on `Backend` exists precisely so engine differences stay inside
config, not code. vLLM speaks the same OpenAI chat protocol as Ollama —
`chat_url` appends `/v1/chat/completions` for every type — and its only
protocol distinction is the liveness surface: `/health` instead of `/api/tags`,
which `health_url` chooses from the type. That single difference is why a
seventy-billion-parameter model server can join the fleet without touching the
request paths. `health_path:` covers the proxy-fronted deployment, keeping even
the nonstandard topology a YAML-only edit.
<!-- /WIKI:GENERATED -->

---

## Stage 4-5: Specialized Model Groups

<!-- WIKI:GENERATED unit=unit-cluster-scale-stage-4-5-specialized-model-groups -->
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
<!-- /WIKI:GENERATED -->

---
