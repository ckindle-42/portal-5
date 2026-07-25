---
id: unit-model-catalog-baronllm-q6-k
kind: what
title: "MODEL_CATALOG \u2014 `baronllm:q6_k`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: '`baronllm:q6_k`'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.6283011
updated_at: 1784946220.6283011
---

GATE-D Expert-role candidate (added 2026-07-21, user-requested) — the non-abliterated original
BaronLLM (Llama-3.1-8B, 53K cybersec examples, 200+ domains), pulled per the workaround above.
Distinct checkpoint from `huihui_ai/baronllm-abliterated:latest` below (different weights, not
abliterated) — its tool-call reliability finding (`valid_rate 0.25`, DROPPED from `auto-security`)
does not automatically carry over, since Hunter/Expert run with `tools=None` (pure-text reasoning
over supplied telemetry — model card claims SIEM/PCAP/EDR JSON classification+summarization, which
is on-target for that job, not for MCP tool-calling). Registered in the `security` backend group and
a `bench-baronllm-q6k` workspace; not yet run through `capture_expert_handoff`/
`resume_from_handoff` — queued for the next comparison pass alongside the other 5 Expert candidates
(`foundation-sec-8b-reasoning`, `cybersecqwen-4b`, `vulnllm-r-7b`, `meta-secalign-8b`, `sylink-8b`).
Sampling: temperature 0.6, top_p 0.9, repeat_penalty 1.1 (project's "reasoning" role convention, no
GGUF-embedded creator recommendation found). Chat template: reused `huihui_ai/baronllm-abliterated`'s
known-good Llama-3.1 template (same base lineage) via `ollama show --modelfile`.
