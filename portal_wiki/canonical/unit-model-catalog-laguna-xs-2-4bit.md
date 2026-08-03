---
id: unit-model-catalog-laguna-xs-2-4bit
kind: what
title: "MODEL_CATALOG — `Laguna-XS.2-4bit`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: bcd2259a
  section: '`Laguna-XS.2-4bit`'
last_generated_commit: bcd2259a
confidence: high
tags:
- docs
created_at: 1785900000.0
updated_at: 1785900000.0
---

MLX conversion (mlx-community, 4-bit) of poolside/Laguna-XS.2, served by the oMLX evaluation backend. Ships `modeling_laguna.py`/`configuration_laguna.py` custom-code — the architecture mlx_lm never upstreamed (the retired MLX proxy needed a hand-written plugin for this reason, `scripts/_archive/mlx-retired-3a0c58e/mlx-model-laguna.py`); oMLX serves it natively via HF `trust_remote_code`. Registered in both the no-traffic `omlx-local` holding group and the live `group: coding` `omlx-coding` entry (PUNCHLIST B2, priority 10), aliased from the production hint `laguna-xs.2:Q4_K_M-ctx64k`. No Phase-0 bench numbers yet — not covered by the 2026-08-02 gate run; added post-hoc for the B2 shadow-then-shift.
