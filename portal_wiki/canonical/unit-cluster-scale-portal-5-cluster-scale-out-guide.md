---
id: unit-cluster-scale-portal-5-cluster-scale-out-guide
kind: what
title: "CLUSTER_SCALE \u2014 Portal 5 \u2014 Cluster Scale-Out Guide"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: portal/platform/inference/cluster_backends.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.511627
updated_at: 1784946220.511627
---

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
