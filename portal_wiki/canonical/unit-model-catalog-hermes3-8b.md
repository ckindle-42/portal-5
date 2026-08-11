---
id: unit-model-catalog-hermes3-8b
kind: what
title: "MODEL_CATALOG \u2014 `hermes3:8b`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: ed366c7a6eb34d822a5d4aa04f8072edca8acd5d
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.641385
updated_at: 1784946220.641385
---

`hermes3:8b` is the NousResearch Hermes 3 8B, declared in `config/backends.yaml` under the `creative` group with `supports_tools: true` — the flag matches Hermes' function-calling format, which is why it is tool-tagged. Unlike most catalog entries it is absent from `config/portal.yaml`: no workspace `model_hint` selects it, so it is a registered creative-pool candidate rather than a pinned lane. Its profile is long-form narrative coherence within the `creative` group's candidate set. The `supports_tools: true` value is the config's only assertion about tooling; everything else in the catalog entry is model-card knowledge from the doc.

## Why

The prior body was three sentences of doc-derived prose. Re-grounding binds it to `config/backends.yaml`, which is the sole source since the mapping flags this model as not in portal: the group (`creative`), the exact id, and the `supports_tools: true` flag all come from that file. Its absence from `config/portal.yaml` is a positive, verifiable fact about routing, so the body states it rather than implying a workspace assignment that does not exist.
