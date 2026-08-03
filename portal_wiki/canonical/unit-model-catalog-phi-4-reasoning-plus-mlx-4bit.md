---
id: unit-model-catalog-phi-4-reasoning-plus-mlx-4bit
kind: what
title: "MODEL_CATALOG — `Phi-4-reasoning-plus-MLX-4bit`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 29bdbca4
  section: '`Phi-4-reasoning-plus-MLX-4bit`'
last_generated_commit: 29bdbca4
confidence: high
tags:
- docs
created_at: 1785716664.2314298
updated_at: 1785716664.2314298
---

MLX conversion (lmstudio-community, 4-bit) of Phi-4-reasoning-plus, probed as a candidate for the GGUF crash refugee (P5-MODEL-PHI4REASONING-001). Phase-0 Gate-6: loads on oMLX but output is degenerate (special-token leakage, incoherent) with the default chat template — NOT production-viable as-probed. Registered in backends.yaml with a do-not-migrate note pending template investigation.
