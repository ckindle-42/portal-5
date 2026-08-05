---
id: unit-model-catalog-phi-4-reasoning-plus-mlx-4bit
kind: what
title: "MODEL_CATALOG \u2014 `Phi-4-reasoning-plus-MLX-4bit`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: 86e6f142c0069ca2d4824b4721a545e64bd585b3
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1785716664.2314298
updated_at: 1785716664.2314298
---

`Phi-4-reasoning-plus-MLX-4bit` is the 4-bit MLX conversion of Phi-4-reasoning-plus (lmstudio-community), probed as a candidate refuge for the GGUF crash. `config/backends.yaml` registers it in the `omlx` group's `omlx-local` backend with `supports_tools: false`; the group's header comment marks Phi-4-reasoning-plus a degenerate-output FAIL — registered but do-not-migrate until the template issue resolves. Phase-0 Gate-6 reproduced special-token leakage and incoherent output under the default chat template, so it is not production-viable as probed. The registration keeps the id known without letting any workspace route to it.

## Why

Grounding anchors the model to the single `omlx-local` registration whose supports_tools false flag and degenerate-output comment are the authoritative statement of its status, replacing the doc-only claim. The Phase-0 Gate-6 result is kept as the institutional evidence behind the do-not-migrate note, which is a chat-template defect, not a model-quality judgement.
