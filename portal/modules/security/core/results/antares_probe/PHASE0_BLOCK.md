# Antares-1B Phase 0.4 — honest-BLOCKED (broken chat-template special tokens, not a gate, not arch)

**Corrected finding (two prior passes were wrong — see below):** `fdtn-ai/antares-1b`'s official
HF repo is gated (`gated: "auto"`), but **ungated community GGUF conversions exist and pull/load
without any access issue** — e.g. `hf.co/HolkViking/antares-1b-Q4_K_M-GGUF` and
`hf.co/DevQuasar/fdtn-ai.antares-1b-GGUF`, both confirmed public.

## What was actually tried

1. `ollama pull hf.co/HolkViking/antares-1b-Q4_K_M-GGUF` — succeeds. `ollama show`: `architecture:
   granite`, capability `completion` only (no `tools`).
2. `ollama pull hf.co/DevQuasar/fdtn-ai.antares-1b-GGUF:Q4_K_M` — succeeds (independent
   uploader). `ollama show`: `architecture: granite`, capabilities `completion` + `tools`.
3. Both quants: `/api/chat` with a trivial plain prompt ("Reply with the single word: ready")
   returns garbage — `@@@@@@@@@@@@@@@@`. The tool-call smoke test correspondingly emits zero
   parseable tool calls.
4. **Isolation test (this is the part that matters):** `ollama generate --raw` (bypasses the
   chat template entirely) on the same prompt-equivalent text ("The capital of France is")
   returns **perfectly coherent output**: "Paris. 2. The largest city in the world by population
   is Tokyo. 3. The". This proves the weights, quantization, and `granite`-mapped architecture
   are all fine.
5. Isolated further: feeding the *exact* literal special-token markup the chat template emits
   (`<|start_of_role|>user<|end_of_role|>The capital of France is<|end_of_text|>\n<|start_of_role|>assistant<|end_of_role|>`)
   through `--raw` reproduces the identical garbage output. The bug is specifically in how
   Granite-4's `<|start_of_role|>`/`<|end_of_role|>`/`<|end_of_text|>` special tokens are
   registered in these GGUF conversions — not the base weights, not llama.cpp's architecture
   support.

## Corrected root cause

Broken/mis-registered special-token handling in the community GGUF conversion's chat template
(or, less likely but not ruled out, a subtly broken special-token embedding row in the base
model that every converter faithfully reproduces — both independently-uploaded quants show the
identical symptom). **This is not** the Cisco access gate the task file's premise assumed (both
quants are ungated and pull fine), **and is not** an unsupported-architecture problem like
Nanbeige4.2-3B/Instella-MoE-16B-A3B in Part A of this same batch-bench task (those fail loudly
and cleanly with "unknown model architecture"; this loads and runs with zero errors and only the
*output* is wrong — a materially harder failure mode to catch, and the reason the first
smoke-test pass here wrongly reported it as an arch mismatch before the raw-vs-chat isolation
test was run).

## Two wrong prior conclusions (kept for the record)

1. **First pass**: "gated, unavailable" — concluded from `ollama list` returning no `antares`
   tag, without ever attempting a pull. Wrong: ungated community conversions exist.
2. **Second pass**: "arch mismatch" (`granitemoehybrid` mapped down to plain `granite`) —
   concluded from `ollama show`'s arch label plus the chat-mode garbage output, without testing
   whether the garbage was template-specific. Wrong: raw completion proves the weights/arch are
   fine; the bug is isolated to the chat template's special-token handling.

## Decision (per Phase 3's §3.1 rule: "If Phase 0 BLOCKED... decision is PASS (for now) with the
captured diagnostic; revisit when a working GGUF exists")

**PASS (for now)** for both Experiment A (Retriever role) and Experiment B (structural-divergence
hunt) — neither can run without coherent chat-formatted tool-calling. Revisit when either a GGUF
conversion with correctly-registered special tokens exists, or a hand-authored Ollama `TEMPLATE`
override is proven against the raw-vs-chat isolation test above (garbage → coherent). That
template-authoring work is real reverse-engineering effort, deferred as a follow-on — the same
call already made for Fara1.5-27B's non-standard tool-call XML dialect elsewhere in this
batch-bench task, not attempted here either.
