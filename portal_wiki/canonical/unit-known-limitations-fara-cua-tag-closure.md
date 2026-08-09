---
id: unit-known-limitations-fara-cua-tag-closure
kind: what
title: "KNOWN_LIMITATIONS \u2014 Fara1.5-27B CUA tag-closure reliability"
sources:
- type: code
  path: tests/benchmarks/bench_fara_cua_probe.py
last_generated_commit: 925f52c4b7e7ec876ea24823d3a221c7f2f8f505
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1786308700.0
updated_at: 1786308700.0
---

- **ID**: P5-FARA-CUA-001
- **Status**: Open — TASK-BATCH-BENCH-001 Part C intake finding. Not blocking; scoped to a
  named follow-on below.
- **Description**: `portal5/fara1.5-27b:q4_k_m` (`microsoft/Fara1.5-27B`, imported via
  `hf_hub_download` + `ollama create` with a second `FROM` line for the
  `mmproj-Fara1.5-27B-f16.gguf` vision projector — `ollama show` confirms the projector loaded:
  `clip`, 460.73M params) correctly perceives a synthetic 1440x900 login-page screenshot fixture
  and correctly reasons about the CUA task (identified the username/password fields, correctly
  triggered a Case-1 "missing user information" critical point per its own trained pause logic)
  in every sample tested. But the tool call itself lands in the `thinking` field rather than
  `content` or Ollama's structured `tool_calls`, in the model's native
  `<tool_call><function=computer_use><parameter=KEY>value</parameter>...</function></tool_call>`
  XML dialect — because this is a from-GGUF custom import with no `TEMPLATE` override, so the
  GGUF's own embedded chat template drives generation and Ollama's built-in tool-call parser
  does not recognize this dialect as structured `tool_calls`. Across 4 raw `temperature=0.0`
  samples: 1 was a complete, well-formed block (action `pause` — not in the model card's
  documented 17-action vocabulary, a possible near-synonym for `pause_and_memorize_fact` or
  `ask_user_question`); 3 omitted the closing `</parameter>` tag on the `action` field, causing
  the value to run on into the next `<parameter=` tag (`bench_fara_cua_probe.py`'s parser
  isolates this correctly as a malformed/unsupported action rather than silently absorbing the
  bleed-through text).
- **Reproduced directly** (bypassing any harness, isolating the model via raw `/api/chat`
  calls): confirmed across both a bare system-prompt-only request (which degenerated into a
  `</think>`-tag repetition loop without the `tools` field present) and a request with the
  `computer_use` tool declared via Ollama's standard OpenAI-style `tools` array (which produced
  the coherent, correctly-reasoned XML-dialect responses described above). The `tools` field is
  necessary for coherent output; it does not by itself make tag closure reliable.
- **Verdict**: Real capability confirmed (screenshot perception, correct CUA reasoning, correct
  critical-point handling), format brittleness noted as the open caveat. This clears the bar the
  task set for scheduling the bounded MagenticLite follow-on (`TASK_FARA_MAGENTIC_BENCH_V1`,
  not built in this task) — MagenticLite ships Fara's actual trained chat template and grammar
  constraints, which this ad-hoc Ollama import deliberately does not attempt to replicate.
- **Not attempted here**: writing a custom Ollama `TEMPLATE` to force well-formed native
  `tool_calls` extraction for this XML dialect. That is exactly the class of harness investment
  MagenticLite already provides and TASK-BATCH-BENCH-001 scoped as intake-only.

## Why

The direct raw-`/api/chat` reproduction (bypassing any pipeline or probe-script logic) is what proves this is a chat-template/extraction gap rather than a Fara capability gap or a probe bug: the same model, same fixture, same question produces coherent, correctly-reasoned CUA output every time, but the *closure* of that output's XML tags is unreliable under the generic GGUF template. Recording the exact XML dialect and the 1-well-formed/3-malformed sample split here — rather than leaving it only in the gitignored `tests/benchmarks/results/fara_cua_probe_*.txt` artifacts — is what lets a future session (or the MagenticLite follow-on) start from "known to work, known brittleness point" instead of re-deriving both facts from scratch.
