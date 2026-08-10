---
id: unit-cluster-scale-stage-1-stage-2-add-a-second-mac-studio
kind: what
title: "CLUSTER_SCALE \u2014 Stage 1 \u2192 Stage 2: Add a Second Mac Studio"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: portal/platform/inference/cluster_backends.py
- type: code
  path: deploy/portal-5/docker-compose.yml
last_generated_commit: 0fec84d46a8898b1b5baf0508af1e25634b099af
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.512039
updated_at: 1784946220.512039
---

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
