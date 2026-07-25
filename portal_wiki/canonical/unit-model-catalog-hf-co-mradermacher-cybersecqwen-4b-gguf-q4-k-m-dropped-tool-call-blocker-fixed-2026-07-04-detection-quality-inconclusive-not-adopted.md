---
id: unit-model-catalog-hf-co-mradermacher-cybersecqwen-4b-gguf-q4-k-m-dropped-tool-call-blocker-fixed-2026-07-04-detection-quality-inconclusive-not-adopted
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/mradermacher/CyberSecQwen-4B-GGUF:Q4_K_M` \u2014\
  \ DROPPED (tool-call blocker fixed 2026-07-04; detection quality inconclusive, not\
  \ adopted)"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: "`hf.co/mradermacher/CyberSecQwen-4B-GGUF:Q4_K_M` \u2014 DROPPED (tool-call\
    \ blocker fixed 2026-07-04; detection quality inconclusive, not adopted)"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.62912
updated_at: 1784946220.62912
---

Blue-defender candidate (athena129/CyberSecQwen-4B, Qwen3-4B base, Apache-2.0, ~2.5GB; card claims it beats
Cisco Foundation-Sec-8B, the current blue incumbent). The exact `athena129` repo ships no GGUF ("planned"
per its card) — `mradermacher/CyberSecQwen-4B-GGUF` is a community quant of the same base, pulled and
preflighted instead. Coherent, on-topic completion (correctly discusses Kerberoasting on request, though it
cites the wrong technique ID — T1557.004 instead of the real T1558.003). Originally disqualified on
tool-call audit: a direct `/api/chat` call with `report_detection` in the tools list returned a hard 400.

**2026-07-04 UPDATE — root cause was the shipped template, not the model.** Byte-inspected the GGUF's
embedded `tokenizer.chat_template` directly: it exists, but is a bare ChatML loop with no `{% if tools %}`
block and no `<tool_call>` rendering at all — this is what athena129 shipped, not an artifact of the
mradermacher quant conversion. Since the base is Qwen3-4B (a tool-capable family) and `<tool_call>` is a
registered special token in the tokenizer, hand-authored a standard Qwen3 Hermes-style `<tool_call>` XML
Go template into a derived Modelfile (`FROM hf.co/mradermacher/CyberSecQwen-4B-GGUF:Q4_K_M`, local tag
`cybersecqwen-4b-toolfix`) — same fix class as `TASK_TOOLCALL_FIX_LOCKIN_V1` (baronllm-abliterated), except
there no pre-existing working template existed to borrow, so this one was authored from scratch. Verified
directly against `/api/chat`: two independent probes (`run_nmap_scan` with a target arg; `query_windows_events`
matching the actual purple-protocol tool) both returned clean, schema-conformant `tool_calls` — the
fine-tune's underlying tool-calling capability was intact, only the exported template was missing it.
Not yet run through the actual candidate-eval purple gauntlet (`--replay-captured-red`-eligible now, or a
live run) — the 8B-beats-4B card claim, and whether real-scenario `blue_f1` improves over the Cisco
Foundation-Sec-8B incumbent, both remain untested. Template lives only as a local `ollama create` tag today,
not yet checked into the repo as a reusable Modelfile/fix script.
