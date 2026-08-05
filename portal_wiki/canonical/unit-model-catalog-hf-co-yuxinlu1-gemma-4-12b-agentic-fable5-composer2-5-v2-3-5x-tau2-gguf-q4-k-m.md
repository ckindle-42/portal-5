---
id: unit-model-catalog-hf-co-yuxinlu1-gemma-4-12b-agentic-fable5-composer2-5-v2-3-5x-tau2-gguf-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF:Q4_K_M`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 778def71961fd1bb2f1088be9754388706facf7a
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.611209
updated_at: 1784946220.611209
---

`hf.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF:Q4_K_M` is a ~6.87GB Gemma-4-12B-it fine-tune for agentic, coding, and terminal work using the `gemma4_unified` architecture with a native Gemma-4 tool protocol and thinking mode. `config/backends.yaml` registers it under both the `general` and `coding` groups with `supports_tools: true`. `config/portal.yaml` binds it as the `bench-gemma4-12b-agentic` `model_hint`, noting its honest self-reported tau2-bench telecom score of 55 percent versus a 15 percent base under a local harness, and marking the fable5 label as marketing provenance. The intake is bench-only with PROMOTE_POLICY=confirm.

## Why

The dual `general`/`coding` registration with `supports_tools: true` is asserted directly by `config/backends.yaml`, and `config/portal.yaml` provides the `bench-gemma4-12b-agentic` binding plus the honest-eval and provenance caveats. The institutional notes about the local self-eval and the needs-recent-Ollama requirement for `gemma4_unified` are preserved because the bench description records them, which is the source the body now cites.
