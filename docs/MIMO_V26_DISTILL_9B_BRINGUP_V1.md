# MiMo-V2.6-Distill-Qwen-9B — Bring-up & Bench (2026-09-21)

**Status: candidate only.** Not wired into `config/portal.yaml`, `config/backends.yaml`, or any persona YAML. Promotion to a live `model_hint` is a separate operator task.

## What it is

`XiaomiMiMo/MiMo-V2.6-Distill-Qwen-9B` — Qwen3.5-9B base, SFT'd on 77.4B tokens across Code (23.2B) / Cyber (11.0B) / General (22.0B) / Visual (21.2B). Architecture: `Qwen3_5ForConditionalGeneration`, hybrid linear/full attention, 262144 native `max_position_embeddings`, no rope_scaling needed.

Model-card claims: SWE Verified 60.0→61.1, SWE Pro 32.0→44.6, AutomationBench 5.0→30.3, Terminal Bench 27.0→37.1, MiMo Cyber 5.7→31.3 (base→this SFT).

## Pull & tag

`ollama pull hf.co/bartowski/...` hit a known Ollama xet-CDN redirect bug (`blocked redirect to a different host` on HF's `us.aws.cdn.hf.co` xet-bridge URL). Worked around by downloading the GGUF directly via `hf download bartowski/MiMo-V2.6-Distill-Qwen-9B-GGUF MiMo-V2.6-Distill-Qwen-9B-Q4_K_M.gguf` (5.84GB) and importing via local `ollama create` with a Modelfile — not an Ollama-library fallback, still the bartowski Q4_K_M GGUF, just fetched by a different client.

Final tag: **`portal5/mimo-v26-distill-9b:q4_K_M-ctx256k`**

Baked `PARAMETER num_ctx 262144` (full native context) — precedent already exists in this fleet for a same-size model (`portal5/omnicoder2-9b:q4_K_M-ctx256k`), and hybrid linear/full attention keeps KV-cache growth far cheaper than a dense-attention model at this context. Confirmed empirically: resident footprint at full 262144 ctx is **11GB, 100% GPU** — cheap.

## Template/config verification (source vs. harness — not just trusted)

Per this fleet's standing rule (thinking models silently opening `<think>` by default, and the command-r tool-envelope bug, are both prior production incidents that trace back to trusting a harness's guessed default over the model's real source config), the bartowski GGUF's baked-in template was diffed against XiaomiMiMo's own source repo, not assumed:

- **Tool-call wrapper**: source `chat_template.jinja` renders `<tool_call><function=NAME><parameter=K>V</parameter></function></tool_call>` — byte-identical to what `ollama show <tag> --template` baked in. No mismatch.
- **Thinking control**: source template gates on `{%- if enable_thinking is false -%}` (README confirms `chat_template_kwargs: {"enable_thinking": true/false}`), matching the baked template exactly. Ollama's own `think:false` request param maps onto this correctly — verified live (see probes below).
- **EOS/stop**: source `tokenizer_config.json` sets `eos_token: "<|im_end|>"`, matching the baked template's turn-closing token. No mismatch.
- **Verdict: bartowski's GGUF embeds the real source template, not a generic/fallback one.** No Modelfile fix was needed.

## Live probes

**Tool-call probe** (direct `/api/chat` with a `get_weather` tool definition):
```json
{"tool_calls":[{"function":{"name":"get_weather","arguments":{"city":"Boston"}}}]}
```
Clean, correctly-typed arguments, reasoning routed to `thinking` field (not leaked into `content`). **`supports_tools:true` confirmed by probe**, not inferred from arch.

**Thinking-suppression probe** (`think:false`, `"2+2=?"`): returned bare `"4"`, no `<think>` leakage. Confirmed.

**Cold load**: 1.36s (first smoke request, clean system state).

## Bench — clean, isolated numbers only

A head-to-head coding-lane comparison against the auto-coding incumbent (Laguna-XS.2) was attempted and **invalidated by a system-level confound, not a model problem**: the box was under heavy swap pressure (~22GB swap in use, physical free memory near zero) during the Laguna run, likely compounded by an operator error mid-session (a second request was fired at a different model before the first Laguna request had actually completed, deadlocking Ollama's model-swap logic in a `Stopping...` state for ~10+ minutes until the stale client was killed). **The Laguna timing/correctness data from that run is discarded — not reported as real.** A valid Laguna (or other incumbent) comparison needs its own separately-isolated pass, stack quiesced, nothing else loaded — not attempted again in this session.

What follows are clean, isolated, single-model numbers for MiMo alone (no other model resident, no swap pressure):

| Probe | Result | eval tok/s | eval tokens | prompt eval | notes |
|---|---|---|---|---|---|
| Coding: batch-processing off-by-one bug | **Correct fix** (`items[i:i+batch_size]`) | 36.0 tok/s | 51 | 0.46s / 141 tok | clean, isolated |
| Security: open-redirect classification | **Correct** — CWE-601, High/7.1-8.0 CVSS w/ sound justification, working allowlist mitigation | 35.8 tok/s | 529 | 0.35s / 80 tok | clean, isolated |

Both correctness results are qualitatively strong for a 9B model — the CWE identification, CVSS band reasoning, and mitigation code in the security probe would not look out of place from a much larger model. Decode speed (~36 tok/s) is consistent across both tasks regardless of output length, as expected for a dense-attention decode workload at this size on this hardware.

**Coding-lane and security-lane head-to-head comparisons against the seated incumbents (Laguna-XS.2 for coding; VulnLLM-R-7B for security) are NOT validly measured yet** — only MiMo's own standalone numbers are trustworthy from this session. Don't cite this doc as "MiMo beats/loses to X" on speed or quality; it only supports "MiMo works correctly and performs reasonably in isolation."

## Footprint

- Disk: 5.84GB (Q4_K_M GGUF)
- Resident: 11GB at full 262144 ctx, 100% GPU
- Cheap enough to coexist with most of this fleet's other seated models on 64GB unified memory (compare: auto-coding's Laguna-XS.2 alone is ~25GB resident at its 131072 ctx tag)

## Recommendation

**PROMOTE_POLICY=confirm** for candidate-pool inclusion (matching the existing BENCH-GATED PROVISIONAL pattern used for kat-coder-v2.5-dev / orcarouter Qwen3.8-27B-Uncensored) — the correctness signal (clean tool-calls, correct bug fix, correct CWE/CVSS reasoning) and the cheap footprint (11GB vs 17-25GB for the current small-candidate pool) justify a place in the pool alongside the other unpromoted coding/security candidates. **Do not promote to a live model_hint or claim a win over Laguna-XS.2 / VulnLLM-R-7B** — that requires a properly isolated head-to-head that this session did not get a valid run of. Next step: a dedicated single-purpose isolated bench session (stack quiesced, one model at a time, verified fully unloaded between models) against both incumbents.
