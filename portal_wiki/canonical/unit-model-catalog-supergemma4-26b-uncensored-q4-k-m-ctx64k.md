---
id: unit-model-catalog-supergemma4-26b-uncensored-q4-k-m-ctx64k
kind: what
title: "MODEL_CATALOG \u2014 `supergemma4-26b-uncensored:Q4_K_M-ctx64k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 0fec84d46a8898b1b5baf0508af1e25634b099af
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6583612
updated_at: 1784946220.6583612
---

`supergemma4-26b-uncensored:Q4_K_M-ctx64k` is the context-capped derivation of the base `supergemma4-26b-uncensored:Q4_K_M`, baked with `PARAMETER num_ctx 65536`. `config/backends.yaml` lists it under `group: security` (`ollama-security`) and `group: reasoning` (`ollama-reasoning`), both `supports_tools: false`; the shared comment explains that offensive models given tool definitions enter reasoning loops, so the driver parses text output and dispatches via the lab MCP call directly. `config/portal.yaml` pins the tag as the `model_hint` of the auto-security `redteam-deep` and `purpleteam-exec` variants, each with `context_limit: 65536`. The 64K window is therefore the standard context for the security chain, not the base tag.

## Why

The security chain runs on the capped tag, and the `supports_tools: false` posture carries over from the base model's driver-dispatched design. Grounding the tag to its two group entries and to the two workspace pins that consume it ties the context cap and the no-native-tools posture to the exact config lines that enforce them, so a reader can verify both at once.
