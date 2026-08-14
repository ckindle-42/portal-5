---
id: unit-model-catalog-phi4-14b-q8-0
kind: what
title: "MODEL_CATALOG \u2014 `phi4:14b-q8_0`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: 41df61e0a6102275a700700e9765972f1508c4c5
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.599901
updated_at: 1784946220.599901
---

`phi4:14b-q8_0` is Microsoft Phi-4 14B at Q8 (~14GB, MIT, synthetic training data, high precision). `config/backends.yaml` registers it in `group: general` with `supports_tools: false`. The false flag is a runtime fact: Ollama 0.30.x rejects tool injection with a 400 on this model because its template has no tool-calling support. It therefore serves as a general-purpose text assistant rather than a tool-capable backend entry, and no `config/portal.yaml` workspace pins it as a `model_hint`.

## Why

Grounding replaces the doc's shorthand with the general-group registration and its supports_tools false value, which the config actually declares. The Ollama template rejection is kept as the institutional explanation for the flag — a platform limitation, not a claim about the model's quality. The absence of any portal.yaml wiring is stated because it is the reason the model never surfaces as a workspace hint.
