---
id: unit-model-catalog-hf-co-jiunsong-superqwen-agentworld-35b-a3b-abliterated-gguf-4bit-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated-gguf-4bit:Q4_K_M`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: ba66a30a47f104a137e20da5d5a3e3e9cc0b3360
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.610776
updated_at: 1784946220.610776
---

`hf.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated-gguf-4bit:Q4_K_M` (~21.2GB Q4_K_M, Jiunsong, Apache 2.0, qwen35moe arch) is the abliterated fork of the Qwen AgentWorld 35B-A3B base Portal already runs — the uncensored variant of the held AgentWorld. `config/backends.yaml` registers it in the `general` and `coding` groups, both with `supports_tools: true`. `config/portal.yaml` selects it as the `model_hint` for `bench-superqwen-agentworld-ablit`, whose description notes the card is a stub (see BF16 parent) so capability claims are unverified until benched. It is V11 candidate intake (2026-06-30), bench-only, PROMOTE_POLICY=confirm.

## Why

The doc body asserted the abliterated-fork identity and bench-only status; re-grounding pins both to config: `config/backends.yaml` gives the two groups and their `supports_tools: true` flags, and `config/portal.yaml`'s `bench-superqwen-agentworld-ablit` description carries the uncensored-fork framing, the stub-card caveat, and PROMOTE_POLICY=confirm. The candidate-intake date is recorded in the backends comment. No claim now rests on doc prose alone.
