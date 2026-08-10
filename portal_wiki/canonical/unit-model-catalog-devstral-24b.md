---
id: unit-model-catalog-devstral-24b
kind: what
title: "MODEL_CATALOG \u2014 `devstral:24b`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 3cdc95603cf1faa41ddd64aa3eaad1ec45a113ce
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.607148
updated_at: 1784946220.607148
---

`devstral:24b` is registered in `config/backends.yaml` under the `coding` backend group with `supports_tools: true` and appears in the `general` group's intake block with `supports_tools: false`. `config/portal.yaml` gives it the `bench-devstral` workspace `model_hint` and describes it as a 24B MoE (22B active, ~14GB) agentic software-engineering model: 46.8% SWE-bench Verified, the top open-source model at its May 2025 release, built for multi-step tool use, file editing, and repo navigation. This is the V1 entry; the prior `devstral-small-2` label was incorrect, and V2 carries its own id.

## Why

The `coding` group registration with `supports_tools: true` and the `general` group entry with `supports_tools: false` are both asserted by `config/backends.yaml`, while the V1 lineage facts, the 46.8% SWE-bench score, and the May 2025 release note come from the `bench-devstral` description in `config/portal.yaml`. The V1-versus-V2 correction is kept as institutional knowledge because it resolves a real labeling ambiguity across the Devstral family.
