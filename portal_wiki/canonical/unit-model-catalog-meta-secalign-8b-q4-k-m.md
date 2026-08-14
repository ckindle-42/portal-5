---
id: unit-model-catalog-meta-secalign-8b-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `meta-secalign-8b-q4_k_m`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 41df61e0a6102275a700700e9765972f1508c4c5
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.629568
updated_at: 1784946220.629568
---

`meta-secalign-8b-q4_k_m` is Meta-SecAlign-8B (arxiv 2507.02735, Llama-3.1-8B base, Meta/Facebook, Llama 3.1 license, ~4.7GB Q4_K_M), a V13-D blue-defender intake. `config/backends.yaml` registers it in `group: security` with `supports_tools: true`; its inline comment documents the self-quantization pipeline and the clean tool_calls preflight probe. The bench workspace in `config/portal.yaml` pins the `:latest` sibling as `model_hint`, but this unsuffixed id is the security-group entry. Self-quantization was an operator-directed override: no GGUF existed, so the gated LoRA adapter was merged onto the gated base and quantized locally. The adversarial probe COMPLIED, not resisted — the backends comment notes this reflects Ollama's lack of a non-standard `"role": "input"` delimiter, a harness gap, not a refutation. `bench-meta-secalign-8b` target; `PROMOTE_POLICY=confirm`.

## Why

Grounding anchors the model to the security-group registration whose comment carries both the supports_tools true flag and the preflight/self-quantization provenance, plus the bench workspace that consumes the tag family. The COMPLIED adversarial result is kept because it is the institutional reason the model stays a candidate rather than a promotion — a harness/role gap, not a confirmed capability.
