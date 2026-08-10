---
id: unit-ADMIN_GUIDE-add-a-cluster-node
kind: why
title: "ADMIN_GUIDE \u2014 Add a Cluster Node"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: scripts/lib/util.sh
last_generated_commit: 3cdc95603cf1faa41ddd64aa3eaad1ec45a113ce
claims: []
confidence: high
tags:
- ADMIN_GUIDE
- docs
- verified-v1
created_at: 1783195000.812903
updated_at: 1783195000.812903
---

Cluster scaling is a config-only operation. Adding a node means appending a backend entry to `config/backends.yaml`: a unique `id`, a `type` (`ollama` or `openai_compatible`), the node's `url`, the routing `group`, and the model list it serves. The pipeline discovers new backends through `BackendRegistry` at startup and the auto-routing layer load-balances across healthy backends. After editing, restart the pipeline container so the registry re-reads the file. `./launch.sh status` confirms the new backend through the pipeline health block (`backends_healthy` / `backends_total`).

## Why

Scaling must never touch routing code, so the registry treats `config/backends.yaml` as the single operator-edited surface — a twelve-node fleet is still a YAML edit plus a restart. Keeping the scale-out path data-only is what lets a single-node install grow to a cluster without a fork, a feature flag, or a new code path.
