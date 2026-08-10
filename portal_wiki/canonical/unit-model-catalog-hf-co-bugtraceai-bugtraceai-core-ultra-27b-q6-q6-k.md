---
id: unit-model-catalog-hf-co-bugtraceai-bugtraceai-core-ultra-27b-q6-q6-k
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/BugTraceAI/BugTraceAI-CORE-Ultra-27B-Q6:Q6_K`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: fb9979b75eb4d70f331e849b80fc7326e8e61847
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.621984
updated_at: 1784946220.621984
---

`hf.co/BugTraceAI/BugTraceAI-CORE-Ultra-27B-Q6:Q6_K` (~22.1GB Q6_K, BugTraceAI, Apache 2.0, Qwen3.6 dense 27B, SFT on 2,541 real bug-bounty/CVE writeups) is a TOOLING model — it emits runnable artifacts (Nuclei templates, CVE PoCs, JWT crackers, C exploits) rather than prose. `config/backends.yaml` registers it in both the `general` and `security` groups with `supports_tools: false`; the security entry's comment explains why — per the supergemma4 precedent, offensive models given tool definitions enter reasoning loops, so it is scored on artifact content, not dispatch. `config/portal.yaml` selects it as the `model_hint` for `bench-bugtrace-ultra-27b`, whose description records the self-reported 5/5 tooling bench and 0% refusal. It is V11 candidate intake (2026-06-30), bench-only, PROMOTE_POLICY=confirm.

## Why

The doc body asserted `supports_tools=false` "per supergemma4 reasoning-loop precedent" without a source; `config/backends.yaml`'s security-group comment states exactly that rationale, and `config/portal.yaml`'s bench workspace carries the artifact-scoring framing. Re-grounding makes the tooling-model identity and the false flag traceable to config comments rather than doc prose, keeping the self-reported figures where the bench description records them.
