# Splash Inference Engine — Bench Note V1

**Date:** 2026-09-19
**Status:** Exploratory bench only. Nothing in this doc changes `config/backends.yaml` or any workspace routing. Portal 5's inference tier remains Ollama per CLAUDE.md rule 8; splash was tested standalone, outside the portal stack.
**Repo tested:** https://github.com/incoai/splash (Apache-2.0)

## Summary

Splash is a purpose-built local inference engine for Apple silicon that ships two optimized Qwen packages. On this machine (M4 Pro, 64GB, macOS 27.0) it beat Ollama on every measured axis for both models — 1.3–2.1× depending on model and concurrency — using the *exact* `Qwen3.8-27B` weights already running as `auto-compliance`'s model. The compliance module's documented speed problem (`reports/compliance/PROVE_THEN_SCALE_V1.md`, P7 sweep: 72 min/CIP standard, ~4.9hr full sweep) is decode-throughput-bound and sequential-by-design, which is exactly the shape of win splash's single-request decode speedup addresses — projected roughly 72min → ~45–48min per standard, ~4.9hr → ~3–3.3hr full sweep, all else equal. Not yet verified against the real sweep; see Next Steps.

## What Splash Is

- Custom inference engine (not MLX, not llama.cpp/GGUF) built by Inco AI, Apache-2.0, Homebrew-installed.
- Ships two packages: `incoai/Qwen3.8-27B-Splash` (17.4GB) and `incoai/Qwen3.6-35B-A3B-Splash` (20.9GB) — both **4-bit**, each bundled with a **DFlash 2** speculative-decoding draft model trained specifically for it.
- Fused Metal kernels are hand-tuned per model's exact tensor shapes and ship precompiled (no local compilation).
- Speaks OpenAI Chat Completions/Responses and Anthropic Messages APIs; supports streaming, tool calls, JSON Schema output, images/PDFs.
- **One server at a time**, hardcoded to `127.0.0.1:8000`, no `--port` flag. Swapping models requires stopping (Ctrl+C / SIGINT) and restarting.
- Requirements: Apple M3+, macOS 26.4+, 36GB+ unified memory (48GB recommended). This machine: macOS 27.0, 64GB — comfortably above the bar.
- Context: native 256K window (matches Qwen3.8/3.6), usable capacity bounded by available memory.
- Reasoning is on by default; `"reasoning_effort": "none"` disables it (27B also takes `low`/`medium`/`xhigh`) — the equivalent of Ollama's `think: false`.
- Install/run:
  ```
  brew install incoai/tap/splash
  splash serve --model incoai/Qwen3.8-27B-Splash
  ```

## Bench Methodology

- Hardware: this machine, M4 Pro, 64GB unified memory, macOS 27.0 (26A428).
- Prompt: single fixed prompt ("Write a detailed 400-word explanation of how TCP congestion control works…"), `max_tokens`/`num_predict` = 400, reasoning off on both sides (`reasoning_effort: none` / `think: false`) for apples-to-apples output.
- Both servers warmed with a throwaway request before timing.
- Two test shapes:
  - **Single-request**: 3 sequential rounds per engine, per model — decode tok/s and TTFT.
  - **4-concurrent**: 4 requests fired via `ThreadPoolExecutor`, aggregate tok/s = total completion tokens / wall time. Splash and Ollama run sequentially relative to each other (never both concurrency tests at once), per the "sequential bench runs only" rule.
- Models compared (same fleet Q4 quant family on both sides):
  - `Qwen3.8-27B`: splash `incoai/Qwen3.8-27B-Splash` vs Ollama `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M` — **this is the exact tag `auto-compliance` runs (as `...-ctx32k`)**.
  - `Qwen3.6-35B-A3B` (MoE, ~3B active): splash `incoai/Qwen3.6-35B-A3B-Splash` vs Ollama `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-ctx32k`.
- Bench script: `/private/tmp/claude-501/.../scratchpad/splash_bench/bench.py` (session scratchpad, not committed — re-derive from this doc if repeating).

## Results

| Model | Test | Splash | Ollama | Ratio |
|---|---|---|---|---|
| Qwen3.8-27B | single decode | 17.8–21.1 tok/s | 12.4–12.7 tok/s | ~1.5–1.6× |
| Qwen3.8-27B | 4-concurrent aggregate | 26.2 tok/s | 12.7 tok/s (flat vs single) | ~2.1× |
| Qwen3.6-35B-A3B | single decode | 61.6–62.8 tok/s | 47.1–47.4 tok/s | ~1.3× |
| Qwen3.6-35B-A3B | 4-concurrent aggregate | 63.2 tok/s | 46.5 tok/s | ~1.4× |

TTFT was comparable to slightly worse on splash in this bench (splash ~0.4–1.0s vs Ollama ~0.05–0.9s, both cold-cache) — not the axis splash is optimized for at short-prompt scale; its published TTFT win shows up on long cached-prefix replay (see below), which we haven't tested.

Notable: Ollama's aggregate throughput at 4 concurrent requests was flat versus a single request on both models — no continuous batching in this configuration. Splash roughly doubled its 27B throughput under load and gained more modestly on the MoE model.

## Comparison to Inco.ai's Published Numbers

Their launch post (M5 Pro, 16-core GPU, 48GB, SPEED-Bench coding prompts, 1024-token output limit, **reasoning ON — medium for the 27B**):

| Metric | Qwen3.6-35B-A3B | Qwen3.8-27B |
|---|---:|---:|
| Decode, short prompt | 210 tok/s (1.7×) | 74 tok/s (2.0×) |
| Prefill, 32K prompt | 2,011 tok/s (1.3×) | 363 tok/s (1.2×) |
| Cached TTFT, 32K replay | 123ms (6.6×) | 282ms (7.3×) |
| Aggregate decode, 4-concurrent short | 357 tok/s (2.0×) | 170 tok/s (3.9×) |

Our ratios come in lower across the board (1.3–2.1× vs their 1.7–3.9×). Plausible causes, not yet isolated:
- **Reasoning off vs on** — we disabled reasoning for a clean apples-to-apples comparison; they benched with reasoning on (medium), which changes the token mix and possibly the speculative-decode acceptance rate.
- **M5 Pro vs M4 Pro** — different generation, different Metal/GPU core count and memory bandwidth.
- **Different prompt set** (SPEED-Bench coding prompts vs our single TCP-explanation prompt) and different output length (1024 vs 400 tokens).
- We haven't tested long-context prefill or cached-TTFT-replay at all — that's where their biggest claimed wins are (6.6–7.3×) and where it may matter most for compliance (see below).

## Relevance to the Compliance Module

- `auto-compliance` (`config/portal.yaml`) currently runs `model_hint: hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` — the identical weights/quant family benched here. `context_limit: 32768`, `predict_limit: 24576`, `think: false` (required — Qwen3.8's chat template opens `<think>` by default and degenerates on hard compliance questions without this), `temperature: 0.3`, `repeat_penalty: 1.1`.
- Documented speed problem, `reports/compliance/PROVE_THEN_SCALE_V1.md` (current uncommitted work, based on `513ce96d`, 2026-09-17):
  - P7 "family sweep" (one full CIP standard, register nodes + addressable Parts): **72 minutes wall**, 17.0s/register-node, 23.4s/ADDRESSABLE-node, run **cacheless** by design.
  - Full-register sweep (all 14 NERC CIP standards): projected **≈4.9 hours**.
  - `sweep.py` (line ~310) is **deliberately sequential** — "a single operator has no concurrent traffic" — so this is a hard architectural choice, not a missing optimization. **Splash's concurrency win (2–2.1× on 27B) does not apply here**; only the single-request decode win (~1.5–1.6×) is relevant.
  - Reading material per requirement Part is ~13.9k tokens (`reading_material.py`), comfortably inside both the workspace's 32768 context limit and splash's 256K cap — no context-length blocker either way.
- Naive projection using our measured single-request ratio: 72min → **~45–48min** per standard; 4.9hr → **~3–3.3hr** full sweep. This is a back-of-envelope scaling from a generic 400-token prompt, not a measurement against the actual sweep workload (retrieval-grounded, longer per-call context, possibly different token-length distribution) — treat as a hypothesis, not a verified number.

## Risks / Open Questions

- **Architecture**: CLAUDE.md rule 8 states "single inference tier: Ollama." In practice oMLX already runs alongside Ollama in production, so this rule is a preference, not an enforced constraint — but adding splash as a third tier is still a real architectural decision, not a drop-in swap, and needs explicit buy-in before touching `backends.yaml` or any workspace binding.
- **Single-server-at-a-time**: splash binds one model to `127.0.0.1:8000` with no port flag; swapping models requires a stop/restart. Not obviously compatible with a multi-model fleet running concurrently unless splash adds multi-model or port-flag support, or Portal 5 wraps it with per-model process lifecycle management.
- **Custom format lock-in**: the 4-bit weights + DFlash 2 draft + per-shape kernels are a proprietary Inco AI package format (`owner/repo` "Splash package" on HF) — not portable GGUF/MLX. Only the two shipped Qwen packages exist today; no path to running other fleet models on splash unless Inco AI (or Portal 5, per `DEVELOPMENT.md#model-packages`) builds more.
- **Unverified**: tool-calling behavior under Portal 5's MCP tool-call flow, sustained-load stability (recall the `VL server wedges under sustained load` lesson — a similarly speed-optimized engine deadlocked after ~2.5h continuous load), behavior at full 32K/256K context, and real compliance-workload numbers (vs. this generic-prompt bench).
- Splash is v1.0, young project — no track record yet for production stability under Portal 5's actual traffic shape.

## Next Steps / Monitoring Plan

1. Run `sweep.py`'s actual P7 family-sweep workload (or a small slice of it) against a standalone splash `Qwen3.8-27B-Splash` instance and compare directly to the 72min/17.0s-per-node baseline — the number that actually matters, not the generic-prompt proxy above.
2. Verify tool-calling compatibility (splash claims OpenAI/Anthropic tool-call support) against whatever the compliance module's actual call pattern needs.
3. Test long-context prefill/cached-TTFT behavior at compliance-realistic context sizes (~13.9k tokens/node) — this is where splash's biggest published advantage (6.6–7.3× cached TTFT) sits, and we haven't touched it.
4. Soak-test for stability under sustained sequential load matching a multi-hour sweep, not just short bursts — given the VL-server precedent of a fast engine wedging after ~2.5h.
5. If results hold up, scope what a real integration would need: multi-model story (or an accepted single-model-at-a-time constraint for a dedicated compliance box), and an explicit decision on whether this becomes a sanctioned second/third inference tier or stays a standalone side-channel for one workload.
