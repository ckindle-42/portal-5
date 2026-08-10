---
id: unit-HOWTO-20-cluster-scaling
kind: why
title: "HOWTO \u2014 20. Cluster Scaling"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: portal/platform/inference/cluster_backends.py
last_generated_commit: 5d5f217e3cd2b239cd1a8444769243ea0a3f752e
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1783195000.8597472
updated_at: 1783195000.8597472
---

**What:** Add more machines to increase throughput — no pipeline code changes needed.

**How:** Cluster scaling is a `config/backends.yaml` edit (CLAUDE.md Rule 1). The file's `backends:` block lists backend groups (general, coding, security, reasoning, vision, creative); each backend declares a `type` (ollama) and a `url` — e.g. `http://192.168.1.102:11434` for a second Mac Studio running Ollama. `BackendRegistry` in `portal/platform/inference/cluster_backends.py` loads this file at startup (resolving the path across container `/app/config/backends.yaml`, local dev, and CI), expands `${OLLAMA_URL}`-style env refs, and health-checks each backend. After editing, restart the pipeline container so the registry re-reads the file. Never edit the generated `workspace_routing` block — `sync-config` owns it.

The full scale-out walkthrough is `docs/CLUSTER_SCALE.md` (single Mac through a 12-node cluster).

## Why

Capacity is treated as data, not architecture: because the router only knows backends through the registry, adding a node is a YAML edit plus a restart. Keeping `workspace_routing` generated while `backends:` stays hand-edited preserves the two jobs — routing intent belongs to the workspaces, hardware topology belongs to the operator — so the scaling surface is exactly the file the operator already owns.
