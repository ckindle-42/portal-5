---
id: unit-model-catalog-laguna-xs-2-4bit
kind: what
title: "MODEL_CATALOG \u2014 `Laguna-XS.2-4bit`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 10c7734f3f87df5a9d525bb5c1f3970c96a73a91
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1785900000.0
updated_at: 1785900000.0
---

`Laguna-XS.2-4bit` is the 4-bit MLX conversion of poolside/Laguna-XS.2 served by the oMLX evaluation backend. `config/backends.yaml` registers it twice: in the no-traffic `omlx-local` holding entry (group `omlx`) and in the live `omlx-coding` entry (group `coding`, `priority: 10`), both with `supports_tools: true`. The `omlx-coding` `aliases` block maps the production GGUF hint `laguna-xs.2:Q4_K_M-ctx64k` onto this oMLX name, so `config/portal.yaml`'s auto-coding laguna variant keeps serving that hint without a workspace change. The conversion ships `modeling_laguna.py`/`configuration_laguna.py` custom code that mlx_lm never upstreamed; oMLX loads it natively. No Phase-0 bench numbers cover it yet — added post-hoc for the B2 shadow-then-shift.

## Why

This unit grounds the oMLX Laguna entry to the two backends.yaml registrations that actually serve it and to the aliases block that ties it to the GGUF hint used by portal.yaml's auto-coding laguna variant. The retired MLX proxy plugin is dropped as a source because oMLX now loads the custom code natively; the alias relationship is the load-bearing fact for production routing.
