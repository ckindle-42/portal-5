# mlx-serve Engine Bench V1

**Status:** Exploratory bench only. Nothing in this doc changes `config/backends.yaml` or any workspace routing. Portal 5's inference tier remains Ollama per CLAUDE.md rule 8; mlx-serve was tested standalone, outside the portal stack — same treatment as `docs/SPLASH_ENGINE_BENCH_V1.md`.
**Repo tested:** https://github.com/ddalcu/mlx-serve (MIT), v26.9.2, installed via `brew tap ddalcu/mlx-serve` + `brew install mlx-serve` (prebuilt bottle).

## Why this bench exists

The user asked whether mlx-serve's published performance claims (a promptquorum.com review citing "+26% decode over LM Studio, +25% over oMLX"; other blog coverage from willitrunai.com and modelfit.io) hold up on this actual hardware, after the coordinator flagged those sources as SEO-blog-quality and caught one factual error in the same search results (a claim that "Ollama 0.19 replaced its Apple Silicon inference path with MLX" — false; this fleet's own history confirms Ollama's MLX proxy was retired and Ollama runs native Ollama-Metal GGUF inference, see [[project_mlx_retirement]]). This bench independently measures mlx-serve rather than trusting any blog's numbers.

## Setup

- Hardware: this machine, M4 Pro, 64GB unified memory, macOS 27.0 (26A428).
- Model: `mlx-community/Qwen3.8-27B-4bit` (14.9GB, 4-bit MLX — no bf16 per this fleet's rule) — chosen to reuse the exact Ollama baseline already on record in `docs/SPLASH_ENGINE_BENCH_V1.md` (`hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M`, the same weights `auto-compliance` runs). No mlx-community MLX build of the MiMo-9B model brought up this session exists yet, so that comparison wasn't possible.
- Prompt/methodology: identical to the splash bench for apples-to-apples — single fixed prompt ("Write a detailed 400-word explanation of how TCP congestion control works…"), `max_tokens=400`, `chat_template_kwargs.enable_thinking=false`, temperature 0.3. Warmed with one throwaway request first. 3 sequential single-request rounds, then one 4-concurrent round via `ThreadPoolExecutor` (never overlapping the sequential rounds, per the sequential-bench-runs-only convention — confirmed `ollama ps` idle before and throughout, no other bench active).
- Template fidelity: diffed `mlx-community/Qwen3.8-27B-4bit/chat_template.jinja` against the source — empty diff, no drift from harness defaults.

## Results

| Test | mlx-serve | Ollama (from splash bench doc) | Ratio |
|---|---|---|---|
| Single-request decode | 14.89–15.34 tok/s | 12.4–12.7 tok/s | ~1.19–1.20× |
| 4-concurrent aggregate | 43.19 tok/s | 12.7 tok/s (flat, no batching) | ~3.4× |
| Prefill (284-token tool-call prompt) | 114.9 tok/s | not measured in splash doc | — |

For reference, splash on the same Qwen3.8-27B weights measured 17.8–21.1 tok/s single-request (~1.5–1.6× Ollama) and 26.2 tok/s 4-concurrent (~2.1× Ollama) — so **mlx-serve's single-request decode is slower than splash's**, but **mlx-serve's concurrent throughput clearly beats splash's** (43.2 vs 26.2 tok/s), and mlx-serve's server log confirms genuine batched decode (`[batched] gdn batched decode engaged (slots=2)`), not request queuing — the exact mechanism that sank splash's KEEP_OLLAMA decision (see [[project_splash_engine_compliance_candidate]]).

## Tool-calling probe

Direct `/v1/chat/completions` request with a `get_weather` function tool, no thinking. Clean result: `finish_reason: "tool_calls"`, correctly typed JSON arguments (`{"location":"Boston, MA"}`), no malformed wrapper. Genuinely works, not just marketing copy.

## Do the blog claims hold up?

**Partially, and not as advertised.** The promptquorum "+26% over LM Studio" / "+25% over oMLX" comparisons use different baselines than what we measured (LM Studio and oMLX, not Ollama), so they aren't directly checkable from this bench — but mlx-serve's own README table (fetched from the live repo, not a third-party blog) states the same "+26% decode (MLX, shipping defaults)" figure against LM Studio specifically, on an M4 Max, "identical weights per engine, every engine on its shipping defaults" — a first-party claim with a stated methodology, more credible than the SEO blogs repeating it. We did not test LM Studio or oMLX directly in this bench (out of scope — the useful comparison here is against Ollama, the fleet's actual production baseline), so the specific blog percentages remain unverified by us either way. What we *did* verify independently: mlx-serve clearly beats Ollama on this hardware (~1.2× single-request, ~3.4× under concurrency), and its continuous-batching claim is real, not marketing.

## Verdict

Genuinely interesting candidate — more so than splash, specifically because it doesn't share splash's concurrency-queuing failure mode. Worth a deeper look if compliance-sweep-style concurrent workloads are ever revisited, since that's exactly where splash lost. Not proposing any integration here — this is a standalone exploratory bench only, same status as the splash doc before its multi-day evaluation. Real promotion consideration would need: long-context prefill/TTFT testing (untested here, same gap as the splash bench), a multi-model lifecycle check (does mlx-serve support serving multiple different models without a full restart, unlike splash's single-model-at-a-time limitation), and a production-realistic workload test rather than a single generic prompt.

**PROMOTE_POLICY:** not applicable — no promotion path exists yet, this is a first look only.
