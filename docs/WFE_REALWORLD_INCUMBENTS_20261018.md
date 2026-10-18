# Real-world model evidence — incumbent fleet, second pass (2026-10-18)

Read-only web evidence pass over the models named in the dispatch. Complements
`docs/WFE_SEAT_PRIOR_20261018.md` (leaderboard/vendor numbers) with what people *running*
these models publish: Unsloth guides and quant notes, HF model pages and community threads,
llama.cpp/ollama bug trackers. "Ours" = `config/portal.yaml` + `config/backends.yaml` +
`config/model_card_expectations.yaml` (read 2026-10-18).

**Tags:** **measured** = a number with method/hardware · **anecdotal** = user report without a
method · **vendor** = card/blog/leaderboard run by an interested party. "not found" means
searched, nothing located — nothing here is estimated.

**Method caveat:** the session's web-search tool was unavailable (every query cancelled) and
Reddit/DuckDuckGo were unreachable from this network path, so r/LocalLLaMA-style reports are
**absent**; user-report coverage comes from GitHub issue trackers (llama.cpp, ollama), HF
community discussions, and publisher docs. All URLs fetched 2026-10-18 unless dated inline.

---

## 1. gemma4:26b-a4b — Q4_K_M + QAT builds (seats: compliance-reading ctx128k, auto-daily QAT ctx16k)

**Practical verdict.** The strongest evidence-backed all-rounder in the fleet; MoE (25.2B total /
3.8B active, 256K ctx) makes it the fast 26B-class option. One card-adverse number matters for our
128k reading seat: Google's own MRCR v2 8-needle @128k is **44.1%** — long-context recall is the
family's weak lane (31B: 66.4%, E4B: 25.4%).

**Measured / vendor numbers.**
- Vendor card table (26B A4B): MMLU-Pro 82.6, AIME26 88.3, LCB v6 77.1, Codeforces 1718, GPQA-D
  82.3, Tau2 68.2, HLE no-tools 8.7, BBEH 64.8, MMMU-Pro 73.8, MRCR-128k 44.1 —
  [unsloth GGUF card mirror](https://huggingface.co/unsloth/gemma-4-26b-a4b-it-GGUF), vendor, read 2026-10-18.
- **Quant quality (QAT):** naive `Q4_0` conversion of the QAT checkpoint scores **70.2%** top-1 vs
  **85.6%** for Unsloth's UD-Q4_K_XL repack (+15.6, 200 MB smaller) —
  [unsloth Gemma 4 QAT page](https://docs.unsloth.ai/models/gemma-4/qat.md), vendor-measured, Jun 2026. The
  Ollama library build we run (`gemma4:26b-a4b-it-qat`) **is Q4_0** (14 GB + 1.2 GB BF16 projector,
  baked params 1.0/0.95/64 — [ollama.com/library/gemma4:26b-a4b-it-qat](https://ollama.com/library/gemma4:26b-a4b-it-qat)),
  i.e. the conversion Unsloth measured as the *worse* of the two. Our `q4_K_M` tag is non-QAT
  weights, so the two tags are not the same trade.
- **Apple Silicon tok/s (user-measured, with method):** M2 Ultra 192 GB, 1,466-token prompt,
  `num_ctx` 131072 — `gemma4:26b` llama.cpp **76.6 tok/s decode** (2,110 tok/s prefill); Gemma 4
  31B 23.5; 31B-MLX-4bit 23.4 — [ollama#18823](https://github.com/ollama/ollama/issues/18823), measured-anecdotal, 2026-10-06.

**Known problems and fixes.**
- Infinite `<unused49>` loop after long idle, reproducible **across multiple GGUF quant sources**
  (31B report) — [llama.cpp#26088](https://github.com/ggml-org/llama.cpp/issues/26088), open, 2026-07-24, anecdotal.
- Thinking control not working via the OpenAI-API path — [llama.cpp#30759](https://github.com/ggml-org/llama.cpp/issues/30759), open, 2026-10-18, anecdotal.
- `--mmproj` + MTP draft abort at startup — [llama.cpp#30698](https://github.com/ggml-org/llama.cpp/issues/30698), open, 2026-10-17.
- Ollama MLX runner: bf16 Gemma 4 decodes at **~1 tok/s on M2 Ultra** (4-bit and GGUF fine) —
  [ollama#18823](https://github.com/ollama/ollama/issues/18823), open, 2026-10-06; MLX SDPA kernel panic on M2 Max
  (Qwen 3.8 / Gemma 4) — [ollama#18940](https://github.com/ollama/ollama/issues/18940), 2026-10-11.
- Ollama hardcoded Gemma 4 image token budget (280) broke OCR on high-res images; fixed by
  exposing `max_soft_tokens` — [ollama#17152](https://github.com/ollama/ollama/issues/17152) + PR #17154, 2026-07-13.
- Unsloth: re-download for chat-template + llama.cpp fixes (Apr 11); MTP gives 1.4–2.2× decode
  ([guide](https://docs.unsloth.ai/models/gemma-4.md), vendor, Jun 2026).

**Settings vs ours.** Recommended 1.0/0.95/64 everywhere (card + unsloth + Ollama-baked) —
**matches** `model_card_expectations.yaml → gemma4` exactly. Deltas to consider: (a) the QAT seat
runs Q4_0 — if quality complaints appear on auto-daily, an UD-Q4_K_XL QAT repack is the measured
better build; (b) thinking disabled still emits an empty thought block (26B/31B) and thinking
content must be stripped from multi-turn history — template-level, handled by Ollama renderer.

---

## 2. GLM-4.7-Flash Q4_K_M (seats: auto-reasoning challenger, glm-coder persona)

**Practical verdict.** Best measured math/agentic scores in the 30B-A3B class, but the fleet must
be on a **post-Jan-21-2026 GGUF build** — before that fix, looping/garbage was near-universal.
Long-context degradation and Ollama tool-parser bugs remain open.

**Measured / vendor numbers.**
- Vendor table (Z.ai harness): AIME25 **91.6**, GPQA 75.2, LCB v6 64.0, HLE 14.4, SWE-V 59.2,
  τ²-Bench 79.5, BrowseComp 42.8 — [unsloth/GLM-4.7-Flash-GGUF](https://huggingface.co/unsloth/GLM-4.7-Flash-GGUF), vendor, read 2026-10-18.
- Quant loss: **not found** (Unsloth KLD charts are images; no numeric table for this model).
- tok/s: **not found on Apple Silicon.** CUDA anecdotes: 110 tok/s RTX 3090 24 GB
  ([HF discussion #19](https://huggingface.co/unsloth/GLM-4.7-Flash-GGUF/discussions/19)), 90 tok/s RTX 4090D with `kv-unified`
  ([#18](https://huggingface.co/unsloth/GLM-4.7-Flash-GGUF/discussions/18)) — anecdotal, Feb 2026.
- Community eval: HumanEval thread for UD-Q4/Q5 builds — [discussion #22](https://huggingface.co/unsloth/GLM-4.7-Flash-GGUF/discussions/22) (numbers in thread, not re-verified).

**Known problems and fixes.**
- **The big one:** llama.cpp shipped a wrong `scoring_func: "softmax"` (should be `"sigmoid"`) —
  caused looping and poor outputs; all Unsloth quants re-uploaded 2026-01-21, "much better
  outputs"; Jan 22 a CUDA flash-attention fix merged — [GGUF card](https://huggingface.co/unsloth/GLM-4.7-Flash-GGUF) +
  [docs guide](https://docs.unsloth.ai/models/glm-4.7-flash), vendor. Corroborated by pinned discussions
  [#1/#10](https://huggingface.co/unsloth/GLM-4.7-Flash-GGUF/discussions/1) (40+29 comments).
- **Repeat penalty must be 1.0/disabled** — pinned card + [discussion #13](https://huggingface.co/unsloth/GLM-4.7-Flash-GGUF/discussions/13); llama.cpp needs
  `--min-p 0.01` (its default 0.05 misbehaves here). Ollama default `min_p` is 0.0, so only the
  repeat-penalty part applies to us.
- Post-fix stragglers: "still looping and stuck thinking" [#26](https://huggingface.co/unsloth/GLM-4.7-Flash-GGUF/discussions/26) (Feb 2026); "infinite thinking after
  `</thinking>`" [#14](https://huggingface.co/unsloth/GLM-4.7-Flash-GGUF/discussions/14); **"model degrades after ~64,000 tokens"** [#30](https://huggingface.co/unsloth/GLM-4.7-Flash-GGUF/discussions/30) — directly
  relevant to our `-ctx64k` tag; "tool calls destroy good reasoning" [#25](https://huggingface.co/unsloth/GLM-4.7-Flash-GGUF/discussions/25); pinned
  community **Ollama Modelfile to fix tool calling** [#23](https://huggingface.co/unsloth/GLM-4.7-Flash-GGUF/discussions/23). One user preferred bartowski's build
  [#33](https://huggingface.co/unsloth/GLM-4.7-Flash-GGUF/discussions/33) (Mar 2026).
- Ollama tracker: think-loop on q8_0 (closed, [ollama#13886](https://github.com/ollama/ollama/issues/13886), 2026-01-24); tool-call parser
  ends early on `</tool_call>` inside an arg value and strips newlines from string args —
  [ollama#18659](https://github.com/ollama/ollama/issues/18659) / [#18658](https://github.com/ollama/ollama/issues/18658), **open**, 2026-09-26; "GLM crippled today" quality report
  (closed, [#16497](https://github.com/ollama/ollama/issues/16497), 2026-06-04); gibberish-after-a-while (open, [#14273](https://github.com/ollama/ollama/issues/14273), 2026-02-16).
- llama.cpp: much slower than sibling A3B models until fixes (closed, [#19081](https://github.com/ggml-org/llama.cpp/issues/19081), 2026-01-25, 27
  comments); flash-attention eval bug (closed, [#19307](https://github.com/ggml-org/llama.cpp/issues/19307)); grammar-trigger loop + memory leak
  (closed, [#19068](https://github.com/ggml-org/llama.cpp/issues/19068)); IQ4_XS segfault under a coding agent (closed, [#20464](https://github.com/ggml-org/llama.cpp/issues/20464)); MTP
  support landed Jun–Jul 2026 ([#24868](https://github.com/ggml-org/llama.cpp/pull/24868), [#25564](https://github.com/ggml-org/llama.cpp/pull/25564)).

**Settings vs ours.** We already encode card guidance (default 1.0/0.95; agentic 0.7/1.0; 16K max
new tokens for bench modes) — **matches**. **Delta:** our expectations entry pins no
`repeat_penalty`; Unsloth's fix guidance says 1.0/disable. Ollama's default `repeat_penalty` is 1.1
unless the library Modelfile overrides it — the library page shows no baked params, so verify with
`settings_audit --tag glm-4.7-flash:Q4_K_M-ctx64k` and pin 1.0 if it resolves to 1.1. The #30
">64K degradation" report is a reason to keep the 64k tag honest about its ceiling.

---

## 3. granite4.1:8b and granite4.1:30b (seats: tools-specialist, security-reviewer, auto-image/video/documents, compliance council 30b)

**Practical verdict.** The quietest tracker of any model in this pass — essentially **zero**
runtime bug reports on llama.cpp/ollama (only a template-addition PR and an Ollama-Cloud feature
request). Card now public (the first pass hit HTTP 401; that limitation is obsolete). Tool-calling
is the family's selling point and BFCL v3 backs it at both sizes; GPQA is weak (42/46) — a
knowledge/reasoning ceiling, not a bug.

**Measured / vendor numbers** (vendor card table, 8B/30B columns —
[granite-4.1-30b](https://huggingface.co/ibm-granite/granite-4.1-30b), release 2026-04-29, read 2026-10-18; matches the
"IBM chart" figures previously quoted second-hand in-repo):
BFCL v3 **68.27 / 73.68** · IFEval avg **87.06 / 89.65** · GSM8K 92.49 / 94.16 · MMLU 73.84 /
80.16 · MMLU-Pro 55.99 / 64.09 · BBH 80.51 / 83.74 · GPQA 41.96 / 45.76 · HumanEval 85.37 /
88.41 · EvalPlus avg 80.21 / 82.66 · ArenaHard 68.98 / 71.02 · SimpleQA 4.82 / 6.81 · SALAD-Bench
95.80 / 96.41. Context 131,072 at all three sizes. Quant loss: **not found**. Apple Silicon
tok/s: **not found** externally (fleet-internal numbers live in `config/MODEL_CATALOG.md`).

**Known problems and fixes.** No model-specific runtime issues found on either tracker.
Infrastructure-level notes only: llama.cpp Granite 4.1 chat template added
[PR #23518](https://github.com/ggml-org/llama.cpp/pull/23518) (2026-05-22); Unsloth's GGUF build ships **chat-template fixes**
("use `--jinja`" for llama.cpp) — [unsloth/granite-4.1-8b-GGUF](https://huggingface.co/unsloth/granite-4.1-8b-GGUF), vendor, 2026-04-30. A new
*Granite Switch 4.1* 8b/30b pair appeared 2026-10-14 (out of scope here; repo previously rejected
Switch 4.1 — `docs/LANDSCAPE_2026Q3_CLOSEOUT.md`).

**Settings vs ours.** Card ships no sampling config → transformers greedy; ours is `temperature:
0.0` — **matches**. Tools pass through the chat template with `<tool_call>`-wrapped JSON, matching
our prompt contract. Nothing to change.

---

## 4. DeepSeek-R1-0528-Qwen3-8B, unsloth Q4_K_XL (seat: compliance-council-r1, auto-reasoning)

**Practical verdict.** Still the AIME-class per-GB champion the vendor table claims, but it is a
2025 model: 23K-token average thinking per AIME question is the cost driver, and nothing published
since contradicts the card. Template handling is the only recurring trip-point.

**Measured / vendor numbers.**
- Vendor table: AIME24 **86.0**, AIME25 76.3, HMMT-Feb25 61.5, GPQA-D 61.1, LCB(2408-2505) 60.5 —
  [unsloth GGUF card](https://huggingface.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF), vendor (distillation card), 2025-05-29, read 2026-10-18.
- Quant loss for the 8B UD builds: **not found** (Unsloth's Aider 60.9-vs-61.8 dynamic-quant
  figure is for Qwen3-Coder-480B, not this model).
- Apple Silicon tok/s: **not found** externally; fleet-internal ~31 tok/s figure already recorded
  in-repo (first-pass docs).

**Known problems and fixes.**
- Chat template: same as R1; for llama.cpp/GGUF **skip the BOS** (auto-added) — GGUF card usage
  section, vendor. Unsloth guide: [docs.unsloth.ai/basics/deepseek-r1-0528](https://docs.unsloth.ai/basics/deepseek-r1-0528).
- llama.cpp conversion issue (closed, [#15734](https://github.com/ggml-org/llama.cpp/issues/15734), 2025-09-02). Nothing else model-specific
  found on either tracker; the GGUF repo carries 14 community discussions (listing count only, not
  individually reviewed).
- System prompt is supported and `</think>` forcing is unnecessary since 0528 (card, vendor).

**Settings vs ours.** Card: temperature 0.5–0.7 (**0.6 recommended**) "to reduce repetition and
incoherence", top_p 0.95; official system prompt names the model + date; 64K max generation. Ours
is 0.6/0.95 — **matches**. No delta.

---

## 5. mistral-small3.2:24b (seat: compliance council member)

**Practical verdict.** The least-discussed model in the set: no open bug cluster on either
tracker, no community benchmark culture around the GGUF builds. Absence of evidence, not
evidence of quality — nothing here *contradicts* the card either.

**Numbers.** Vendor: IF 84.8 (Mistral's internal set), MMLU-Pro 69.1, GPQA-Diamond 46.1 (card,
2025-06-19, gated on HF — figures via first-pass docs and our config). Quant loss: **not found**.
Apple Silicon tok/s: **not found**.

**Known problems and fixes.**
- Ollama HF-import path: "unknown tokenizer format: Can't Import Mistral-small-3.2" —
  [ollama#13465](https://github.com/ollama/ollama/issues/13465), closed, 2025-12-14 (early-adopter import bug, fixed since).
- llama.cpp chat template added [PR #14349](https://github.com/ggml-org/llama.cpp/pull/14349) (2025-06-23). No open model-specific issues
  found (title- and body-level searches, 2026-10-18).

**Settings vs ours.** Card: low temperature **0.15** + Mistral's own system prompt. Ours is 0.15 —
**matches**. No delta.

---

## 6. LFM2.5-8B-A1B (seats: auto-music, auto-extract-uncensored)

**Practical verdict.** Card is unusually honest about scope: it names itself best for agentic
tool-chaining and **explicitly not** for heavy programming or knowledge-intensive QA without
retrieval — which matches where we seat it. The headline 2.5× DSpark speed-up does not currently
work on the llama.cpp MoE path (crash, open issue).

**Measured / vendor numbers.**
- Vendor tables ([card](https://huggingface.co/LiquidAI/LFM2.5-8B-A1B), read 2026-10-18): IFEval **91.84**, IFBench 56.47, Multi-IF
  79.93, BFCLv3 64.79, BFCLv4 49.73, **Tau²-Telecom 88.07**, Tau²-Retail 39.82, MATH500 88.76,
  AIME25 42.53, AIME26 50.00. Independent cross-check: MathArena AIME-2026 = 50 (HF eval-results
  entry, independent, via first-pass docs).
- Same-card comparisons: Gemma-4-E4B (BFCLv3 57.31, Tau²-Telecom 26.75) and Gemma-4-26B-A4B
  (IFEval 91.40, IFBench 47.25) — Liquid-run, vendor.
- Throughput: "18.5K output tok/s at high concurrency on one H100" — vendor, GPU-side; **Apple
  Silicon tok/s: not found externally** (fleet-internal 78.5 TPS, `config/MODEL_CATALOG.md`,
  2026-06-20). Quant loss: **not found**.
- Architecture: 8.3B total / 1.5B active, 24 layers (18 conv + 6 GQA), ctx 128,000, day-one
  llama.cpp/MLX/vLLM/SGLang; MLX-8bit and GGUF official; **DSpark** 328M drafter claims ~2.5×
  faster decoding with identical outputs (SGLang).

**Known problems and fixes.**
- **Long-context template-path bug:** chat-template path degenerates to repeated `P` at ~44K
  context (raw path fine) — [llama.cpp#27606](https://github.com/ggml-org/llama.cpp/issues/27606), closed, 2026-08-23. Relevant only if a seat
  ever pushes past ~40K (ours are 8K).
- **DSpark + 8B-A1B (MoE) crashes at graph_reserve** — [llama.cpp#28614](https://github.com/ggml-org/llama.cpp/issues/28614), open, 2026-08/09. The 2.5×
  claim is SGLang-only for now; dense LFM2.5 models unaffected.
- Family parser hazard: LFM2.5-24B-A2B emits Qwen3-Coder-style XML tool calls as content, calls
  silently lost — [llama.cpp#30490](https://github.com/ggml-org/llama.cpp/issues/30490), open, 2026-10-14 (different size, same family path).
- Think tags leaking into content on the 1.2B-Thinking build — [llama.cpp#28675](https://github.com/ggml-org/llama.cpp/issues/28675), 2026-09-09.
- Tool calls are **Pythonic by default** (JSON only if asked in the system prompt) — card, vendor;
  already recorded in our config.

**Settings vs ours.** Card: `temperature 0.2, top_k 80, repetition_penalty 1.05` — **matches ours
exactly**. No delta. Opportunity note: the DSpark drafter is the measured 2.5× lever once the
llama.cpp MoE crash is fixed; not actionable today.

---

## 7. qwen3-coder:30b-a3b (seat: auto-coding ctx256k, auto-cad ctx32k, auto-bigfix)

**Practical verdict.** Settings are uncontroversial (card standard), but this is the model with
the **densest open tool-call-corruption cluster** in the pass — every one of them is in the
serving parser, not the weights, and our oMLX quirk recorded in config is part of the same
family. If auto-coding ever drops tool calls, check the parser first.

**Measured / vendor numbers.**
- The 30B card still publishes **no benchmark table** (confirmed again via first-pass S15).
  Closest measured quant figure is the 480B sibling: UD-Q4_K_XL **60.9%** vs bf16 **61.8%** on
  Aider Polyglot (third-party test, per [unsloth guide](https://docs.unsloth.ai/models/tutorials/qwen3-coder-how-to-run-locally.md)) — same family,
  not this model.
- Apple Silicon tok/s: **not found** externally. Community evals for the 30B: **not found**.

**Known problems and fixes.**
- **Tool call silently lost when the model omits the `<tool_call>` opener** (e.g. reasoning first)
  and leaks into content as plain text — [ollama#16686](https://github.com/ollama/ollama/issues/16686) (open, 2026-06-12) and
  [ollama#18530](https://github.com/ollama/ollama/issues/18530) (open, 2026-09-18); recovery PRs [#17742](https://github.com/ollama/ollama/pull/17742),
  [#18538](https://github.com/ollama/ollama/pull/18538) still open; llama.cpp equivalent [#26987](https://github.com/ggml-org/llama.cpp/issues/26987) (closed, 2026-08-12).
- **Parser changes numeric arguments outside int64 range** — [ollama#18421](https://github.com/ollama/ollama/issues/18421), open, 2026-09-13 — silent argument corruption.
- Tool-schema keys render in random order → identical requests miss the prompt cache —
  [ollama#18430](https://github.com/ollama/ollama/issues/18430), open, 2026-09-13.
- "Claude Code shows no response with qwen3-coder" — [ollama#17671](https://github.com/ollama/ollama/issues/17671), closed, 2026-08-11.
- llama.cpp open PRs: accept JSON tool-arg keys in any order [#30193](https://github.com/ggml-org/llama.cpp/pull/30193) (2026-10-08); stop
  reasoning/content before template separators [#30557](https://github.com/ggml-org/llama.cpp/pull/30557) (2026-10-14).
- Unsloth shipped a universal tool-calling fix (template) for all uploads — guide, vendor, 2025.
- Our own recorded oMLX 0.6.4 finding (tool calls as text; prompt-shaped, recovered in pipeline)
  sits in `model_card_expectations.yaml → qwen3-coder` — consistent with the above.

**Settings vs ours.** Card: 0.7 / 0.8 / top_k 20 / repetition_penalty 1.05; recommended **output
context 65,536 tokens**; min_p 0. Ours matches on sampling. **Delta:** none on sampling; note the
65K output guidance vs our 256K *input* tags (no conflict, but keep `num_predict` ≥ 32K for the
coder seats).

---

## 8. Laguna-XS-2.1 (seat: auto-coding::laguna, `portal5/laguna-xs21:q4_K_M-ctx128k`)

**Practical verdict.** Vendor numbers are real but **self-run with thinking enabled**; the Ollama
serving path around this model is young — parser misfires, a degeneration report on Apple Silicon
MLX, and a long-context metadata fix that landed only 2026-10-11. Our recorded Ollama-0.34.2
bare-JSON 500 bug is independently corroborated.

**Measured / vendor numbers.**
- Vendor bench (Harbor framework + poolside harness, temp 1.0, top_k 20, top_p 1.0, **thinking
  on**, 256K ctx, ≤500 steps; SWE-bench Verified mean pass@1 over 4 attempts): SWE-V **70.9%**,
  SWE-Multilingual 63.1%, SWE-Pro 47.6%, Terminal-Bench 2.0 37.5% —
  [poolside/Laguna-XS-2.1](https://huggingface.co/poolside/Laguna-XS-2.1) + [GGUF](https://huggingface.co/poolside/Laguna-XS-2.1-GGUF), vendor, 2026-06-20/29. Same-table
  rows: Qwen3.6-35B-A3B 73.4/67.2/49.5/51.5; North Mini Code 67.6/–/40.2/36.0.
- Architecture: 33B total / 3B active, 256+1 experts, SWA 3:1 over 40 layers, **native FP8 KV
  cache**, 262,144 ctx, interleaved thinking with per-request toggle, OpenMDW-1.1; "runs on a Mac
  with 36 GB RAM"; official Ollama library `laguna-xs-2.1`. Quant loss: **not found** (poolside
  publishes FP8/NVFP4/INT4 but no loss tables; no independent KLD).
- Apple Silicon tok/s: **not found** as a number; behaviour report below instead.

**Known problems and fixes.**
- **Ollama Laguna parser turns JSON in ordinary content into a tool call**, aborting/corrupting
  replies — [ollama#17602](https://github.com/ollama/ollama/issues/17602) + PRs [#17603](https://github.com/ollama/ollama/pull/17603)/[#17616](https://github.com/ollama/ollama/pull/17616), **open**, 2026-08-07 — matches our
  recorded "empty Laguna tool call name" 500 on bare-JSON replies.
- **Laguna-S 2.1 MLX BF16 intermittently fails to terminate and degenerates into
  stream-of-consciousness on Apple Silicon** — [ollama#17632](https://github.com/ollama/ollama/issues/17632), open, 2026-08-09.
- Empty/null 200 responses after ~30–70 min of continuous serving; `ollama stop` recovers —
  [ollama#17524](https://github.com/ollama/ollama/issues/17524), open, 2026-08-02.
- `laguna-xs-2.1:q4_K_M` crash on second run (GGML_ASSERT) — [ollama#17406](https://github.com/ollama/ollama/issues/17406), closed, 2026-07-26.
- llama.cpp: support not upstreamed until [PR #25165](https://github.com/ggml-org/llama.cpp/pull/25165) (merged 2026-06-30, 51 comments);
  **YaRN beta metadata now loaded** ([#30331](https://github.com/ggml-org/llama.cpp/pull/30331), merged 2026-10-11) — long-context configs on older
  builds were silently mis-scaled; chat template aligned to HF ([#26232](https://github.com/ggml-org/llama.cpp/pull/26232)).
- DFlash drafter support requested, not landed — [llama.cpp#26669](https://github.com/ggml-org/llama.cpp/issues/26669).

**Settings vs ours.** Card methodology runs 1.0/1.0/20 **with thinking enabled**; ours runs the
same sampling with `think: false` — a deliberate, recorded local deviation (XS.2 chained invented
calls to the token cap; XS-2.1 stops). Card also suggests bounding local context to ~32K; our tag
declares 128K — the YaRN metadata fix above is the reason to keep the serving build current.

---

## 9. qwen3-vl:32b (seat: auto-vision, Thinking build, ctx8k)

**Practical verdict.** The Thinking build's known failure mode — burning the whole output budget
inside `<think>` and returning empty content — is real, reported, and still open; our seat's
output budget must cover reasoning + answer (our config already says this). A llama.cpp vision
fidelity report claims embeddings sit ~5× above the HF precision floor regardless of quant — a
serving-stack caveat on any GGUF/MLX VL number.

**Measured / vendor numbers.** Vendor card tables are images (first-pass finding, unchanged) —
no extractable MMMU row; **not found**. Quant loss: **not found**. Apple Silicon tok/s: **not
found**.

**Known problems and fixes.**
- **qwen3-vl-thinking exhausts `num_predict` inside a reasoning loop and never emits
  `message.content`** (structured transcription prompts; `done_reason: "length"`, empty content,
  reproduced on Ollama 0.32.15) — [ollama#17978](https://github.com/ollama/ollama/issues/17978), **open**, 2026-08-25, anecdotal.
- mtmd vision embeddings carry **~5× HF precision-floor noise → reproducible accuracy drop vs
  transformers**, reported as quant/backend/version-independent — [llama.cpp#29251](https://github.com/ggml-org/llama.cpp/issues/29251), open, 2026-09-21, measured-by-reporter.
- CUDA flash-attention gives wrong image embeddings on Qwen3.5/Qwen3-VL — [llama.cpp#29629](https://github.com/ggml-org/llama.cpp/issues/29629), open, 2026-09-29 (Metal unaffected per report scope).
- Video input unusable in Ollama — [ollama#18151](https://github.com/ollama/ollama/issues/18151), closed, 2026-08-31.

**Settings vs ours.** Ollama bakes 1.0/0.95/top_k 20 (= Thinking card) and our expectations carry
both modes (thinking 1.0/0.95/20; instruct 0.7/0.8/20 + presence 1.5) — **matches**. Delta: none;
keep the output budget ≥ think+answer and remember `think:false` is ignored on this build.

---

## 10. VulnLLM-R-7B (seat: auto-security, mradermacher Q4_K_M)

**Practical verdict.** A targeted detector that only works inside its trained prompt contract —
our own 18-snippet probe (recorded in config) proved open-ended prompting both loses accuracy and
manufactures false positives. Community usage is thin; nothing contradicts the paper numbers.

**Measured / vendor numbers.**
- Author-run paper F1 (function-level): Python 0.723 / OOD 0.719; C 0.737 / OOD 0.776; Java OOD
  0.870 — [arXiv 2512.07533](https://arxiv.org/abs/2512.07533), author-run (=vendor), 2025-12-08.
- Card claims (vendor): outperforms Claude-3.7-Sonnet, o3-mini, CodeQL, AFL++ on key benchmarks;
  base Qwen2.5-7B-Instruct; C/C++/Python/Java — [UCSB-SURFI/VulnLLM-R-7B](https://huggingface.co/UCSB-SURFI/VulnLLM-R-7B), read 2026-10-18.
- Quant loss: **not found** (mradermacher build, 2025-12-12, no KLD). Apple Silicon tok/s: **not
  found**.

**Known problems and fixes.** No runtime bug reports found (GitHub search: 4 hits, all
third-party integrations; the upstream repo's issue #1 is a weights-availability request,
2025-12-14). **Config nit found:** `model_card_expectations.yaml → vulnllm` cites
`UCSB-SURFI/VulnLLM-R` as its generation_config source, but that repo name does not resolve
(auth wall); the public repo is `UCSB-SURFI/VulnLLM-R-7B`. Worth a one-line fix next time the
file is touched (not fixed here — outside brief).

**Settings vs ours.** Trained contract (reasoning_user_prompt + CWE_INFO + `#judge:` final answer)
at generation_config 0.7/0.8/20/rep 1.05 — ours **matches**, and our recorded probe (17/18 with
trained prompt vs 15/18 + 3/3 FPs open-ended) is local corroboration.

---

## 11. Foundation-Sec-8B-Reasoning (challenger to auto-security; Q8 registered, Q4 published)

**Practical verdict.** Vendor numbers are credible for a domain-tuned 8B, and an independent
fresh-CVE eval exists (ThreatClaw, below). The card's own safety table is the notable adverse
fact: the security specialization came with a large jump in harmful-request compliance.

**Measured / vendor numbers.**
- Vendor benchmarks (0-shot, temp 0.3): CTI-MCQA **0.691**, CTI-RCM (CVE→CWE root-cause mapping)
  **0.753**, CTI-VSP (CVSS prediction) **0.856**, CTI-Reasoning 0.411 — vs Llama-3.1-8B
  (0.607/0.531/0.811/0.335) and GPT-5-Nano (0.688/0.672/0.822/0.431) —
  [fdtn-ai card](https://huggingface.co/fdtn-ai/Foundation-Sec-8B-Reasoning), vendor, release 2026-01-28, read 2026-10-18.
- **Card-adverse:** HarmBench row 93.00% vs Llama-3.1-8B-Instruct 62.75%; vendor recommends
  LlamaGuard (+ human oversight) in front of it — same card. For a fleet seat this is a
  prompt/policy consideration, not a disqualifier (our use is read-only analysis).
- Independent: fresh-CVE accuracy 38.0% (95% CI 36–40), fresh CVE→CWE 55.1% (52–59) — ThreatClaw,
  2026-10-05 (via first-pass docs; not re-fetched).
- Quant loss: **not found**. Apple Silicon tok/s: **not found**.

**Known problems and fixes.** No model-specific runtime bugs found; third-party integrations only
(e.g. a downstream project needed an "Ollama num_ctx fix" for the 1.1-8B-Instruct sibling —
[ixion36-svg/ion#5](https://github.com/ixion36-svg/ion/pull/5), closed, 2026-06-25). fdtn-ai's own GGUF repo ships
`generation_config.json` (the tier-1 source our config already uses).

**Settings vs ours.** Build-provider generation_config: 0.6/0.95/rep 1.1 — ours **matches** it.
Note the spread of published values: card example 0.1, card benchmarks 0.3, generation_config 0.6
(ours). If the auto-security probe underperforms, the first knob is temperature *down*, not model
swap.

---

## 12. huihui_ai/qwen3.5-abliterated:9b (seat: auto intent router)

**Practical verdict.** The uncensoring cost of this exact build is now **measured by a third
party**, and it is real: TruthfulQA −12.65 and GSM8K −5.68 vs base, plus +22% Lambada perplexity.
Refusal removal is total (100%), so the seat's uncensored property holds. For a pure classifier
the tax is mostly harmless; for anything judgment-adjacent it is not free.

**Measured numbers (independent, lm-evaluation-harness via vLLM, bf16** —
[abliterlitics.dev/models/qwen3.5-9b](https://abliterlitics.dev/models/qwen3.5-9b/), read 2026-10-18; eval snapshot 2026-10-18 per first pass):

| task | base Qwen3.5-9B | Heretic | HauhauCS | **Huihui (ours)** |
|---|---|---|---|---|
| MMLU | 78.64 | 78.34 | 78.34 | **77.10** |
| GSM8K strict | 87.64 | 85.97 | 84.99 | **81.96** |
| HellaSwag | 58.30 | 58.41 | 58.69 | **57.42** |
| ARC-Challenge | 54.52 | 53.07 | 53.75 | **49.15** |
| WinoGrande | 72.77 | 71.90 | 71.35 | **71.19** |
| TruthfulQA MC2 | 53.76 | 45.03 | 45.77 | **41.11** |
| PiQA | 79.38 | 79.16 | 79.43 | **78.89** |
| Lambada PPL (lower better) | 3.8805 | 4.2895 | 4.0497 | **4.7392** |

Same source: all three methods remove **100%** of refusals; Huihui's edit direction is 99.7%
aligned with Heretic's but causes more capability damage ("worst single-task loss in the
project"); HauhauCS applies ~4× the output-distribution shift. GSM8K had 3–4% truncated
responses across variants (scores may be slightly understated).

**Vendor / card.** [huihui-ai/Huihui-Qwen3.5-9B-abliterated](https://huggingface.co/huihui-ai/Huihui-Qwen3.5-9B-abliterated) (2026-03-09): plain
abliteration via `remove-refusals-with-transformers`; **no refusal count or KL on the card**; the
Ollama build requires **v0.17.7+**. Apple Silicon tok/s: **not found** externally.

**Known problems and fixes.** Model-specific: none found beyond the tax above. Family-level
(Unsloth [Qwen3.5 guide](https://docs.unsloth.ai/models/qwen3.5.md), vendor, Mar 2026): universal chat-template/tool-calling fixes (Mar 5
re-download), **MXFP4 layers retired** from Q2/Q3/Q4_K_XL after an investigation found some
tensors are very sensitive to quantization, small sizes default thinking OFF, gibberish usually
means context set too low (or try bf16 KV cache).

**Settings vs ours.** Ours: 0.7/0.8/20 (+ presence 1.5 instruct modes) per card — **matches**.
Unsloth adds: presence_penalty 0–2.0 is the recommended loop guard (higher values may slightly
cost performance) and ≥32K output for most queries. No change needed; note the seat itself is the
tax — the base model is the measured-cleaner instrument for the `task-router` titles/tags job.

---

## 13. gemma-4-E4B-it-OBLITERATED (seat: task-router, ctx2k)

**Practical verdict.** The publisher's own card quantifies the uncensoring cost honestly: refusal
is gone (98.8% → 0% hard) but **~20% of outputs are degenerate repetition loops** and ~28% soft
deflection remain. v2 of this build shipped with **54 K/V tensors deleted** (Gemma 4's shared-KV
architecture) — anyone running v2-era GGUFs should re-download v3. No KL divergence is published.

**Card numbers (OBLITERATUS, vendor, repo created 2026-04-15, v3 read 2026-10-18** —
[gemma-4-E4B-it-OBLITERATED](https://huggingface.co/OBLITERATUS/gemma-4-E4B-it-OBLITERATED)):
method = whitened SVD + attention-head surgery + winsorized activations ("aggressive"), 842
contrastive pairs, 21 of 42 layers modified; hard refusal 98.8% → **0%**; soft deflection ~28%;
coherent + on-topic ~51%; degenerate outputs ~20% (mitigation: `repeat_penalty 1.1`); wrong
language ~4% (Thai/Japanese; mitigation: English system prompt); v2→v3 tensor fix 666 → 720
(v2's corrupted shared-K/V projections were dropped by `save_pretrained`; Claude-judged quality
"3.1/10 → improved"). Fleet build: [mradermacher GGUF](https://huggingface.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF) (2026-04-16). Quant
loss: **not found** (no KLD anywhere). Apple Silicon tok/s: **not found** for E4B specifically.

**Known problems and fixes.**
- v2 missing-tensor incident above — vendor-disclosed, fixed in v3; the compatibility table
  requires Ollama 0.20+ / llama.cpp b8665+ for the gemma4 arch.
- Family runtime bugs are tracked under the Gemma 4 entry (#1) — the E4B-specific ones: Vulkan
  E4B segfault [llama.cpp#28997](https://github.com/ggml-org/llama.cpp/issues/28997) (open, 2026-09-16); audio benchmarks exist on card
  (CoVoST 35.54, FLEURS 0.08) but Ollama's audio path for the small builds is where the
  hardcoded-budget class of bugs lived.

**Settings vs ours.** Publisher mitigation: `repeat_penalty 1.1` + English system prompt. Ours:
gemma4 sampling 1.0/0.95/64 at ctx 2K; Ollama's default `repeat_penalty` is 1.1 (not overridden in
expectations), and the task-router persona supplies a system prompt — **effectively aligned**;
the ~20% degenerate-output figure is the number to keep in mind when the router misbehaves.

---

## Cross-model table

| model | quant loss | Apple Silicon tok/s | tool-call reliability | known issues | settings delta vs ours | sources |
|---|---|---|---|---|---|---|
| gemma4:26b-a4b (Q4_K_M/QAT) | QAT naive Q4_0 70.2% vs UD 85.6% top-1 (vendor-measured); KLD chart-only; **we run Q4_0 QAT** | **76.6 tok/s decode, M2 Ultra, llama.cpp, ctx131k** (user-measured); bf16-MLX ~1 tok/s bug | native function calling; OpenAI-API thinking-control bug; ollama image-budget bug (fixed) | `<unused49>` idle loop (multi-quant); mmproj+MTP abort; MLX bf16 decode bug; MRCR-128k 44.1 (vendor, weak lane) | none (1.0/0.95/64 matches card+Ollama-baked); QAT build quality is the watch item | unsloth card+QAT page (V), ollama#18823/#18824/#17152 (A), llama.cpp#26088/#30759/#30698 (A) |
| GLM-4.7-Flash Q4_K_M | not found (chart-only) | not found (CUDA: 110 t/s 3090, 90 t/s 4090D — anecdotal) | ollama parser bugs open (`</tool_call>` in arg, newline strip); community Modelfile fix pinned | pre-2026-01-21 GGUFs loop (sigmoid scoring bug — fixed); post-fix stragglers; **degrades ~64K tokens** (report) | repeat_penalty: unsloth says 1.0/disable; ours unpinned (Ollama default 1.1?) — verify & pin | unsloth card+guide (V), HF disc #26/#30/#25/#23 (A), ollama#18658/#18659/#14273 (A), llama.cpp#19081/#19307 (A), zai table (V) |
| granite4.1:8b / 30b | not found | not found | BFCL v3 68.27/73.68 (vendor); zero runtime bug reports found | none found (quietest tracker in set); unsloth template fixes note; GPQA 42/46 is the ceiling | none (greedy matches card) | ibm-granite cards (V, now public), unsloth GGUF (V), llama.cpp#23518 (V) |
| DeepSeek-R1-0528-Qwen3-8B Q4_K_XL | not found for 8B | not found (fleet-internal ~31 t/s) | function calling improved per card; BFCL_v3_MT 37.0 / Tau2 53.5/63.9 (vendor, 671B parent — not the 8B) | BOS-skip template note; conversion issue (closed, 2025) | none (0.6/0.95 matches card) | unsloth card (V), llama.cpp#15734 (A) |
| mistral-small3.2:24b | not found | not found | no reports found either way | early ollama import bug (closed 2025-12); otherwise silent | none (0.15 matches card) | mistral card via prior (V), ollama#13465 (A) |
| LFM2.5-8B-A1B | not found | not found externally (fleet-internal 78.5 TPS) | Pythonic calls by default (card); family XML-as-content parser bug open at 24B | chat-template path repeats `P` ≥~44K ctx (closed); DSpark+MoE crash (open) | none (0.2/80/1.05 matches card) | Liquid card (V), llama.cpp#27606/#28614/#30490 (A) |
| qwen3-coder:30b-a3b | not found for 30B (480B sibling: Aider 60.9 UD vs 61.8 bf16, 3rd-party) | not found | **worst open parser cluster**: lost calls w/o opener (#16686/#18530), int64 arg corruption (#18421), cache-miss key order (#18430); PRs open | card still publishes no bench table; 65K output guidance | none (0.7/0.8/20/1.05 matches); keep num_predict ≥32K | unsloth guide (V), ollama#16686/#18421/#18430/#18530 (A), llama.cpp#26987/#30193/#30557 (A) |
| Laguna-XS-2.1 q4_K_M | not found (no loss tables; official INT4/NVFP4/FP8) | not found as number; **MLX BF16 degeneration on Apple Silicon (open report)** | ollama parser JSON→tool-call misfire open (corroborates our recorded 500); empty-200s after 30–70 min; q4_K_M second-run crash (closed) | llama.cpp support young; **YaRN metadata fix 2026-10-11** (long-ctx builds must be current); card ran benches with thinking ON (ours: off, deliberate) | sampling matches; think:false + 128K tag vs card's "bound ~32K locally" is our recorded deviation | poolside card+GGUF (V), ollama#17602/#17632/#17524/#17406 (A), llama.cpp#25165/#30331 (V) |
| qwen3-vl:32b | serving-stack vision fidelity: ~5× HF precision-floor embedding noise (llama.cpp, reporter-measured) | not found | n/a (no tools on seat) | **thinking loop exhausts num_predict, empty content (open)**; CUDA FA wrong embeddings (open); video unsupported (closed) | none (1.0/0.95/20 matches baked+card); output budget must cover think+answer | ollama#17978 (A), llama.cpp#29251/#29629 (A), card tables are images (V) |
| VulnLLM-R-7B Q4_K_M | not found | not found | detector prompt contract only; open-ended prompting → FPs (our measured probe 15/18 vs 17/18) | thin community; config source URL names a non-resolving repo (actual: `-7B`) | none (matches generation_config + trained contract) | arXiv 2512.07533 (V), card (V), config-internal probe (measured, in-repo) |
| Foundation-Sec-8B-Reasoning | not found | not found | n/a (analysis seat) | **card's own HarmBench row 93.00%** (vs 62.75 base) — vendor recommends LlamaGuard; downstream num_ctx fix needed for sibling | 0.6/0.95/1.1 matches fdtn GGUF generation_config; card example is 0.1, evals 0.3 — we run the hottest published value | fdtn card+GGUF genconfig (V), ThreatClaw 2026-10-05 (I, via prior) |
| huihui qwen3.5-abliterated:9b | **measured tax vs base:** MMLU −1.54, GSM8K −5.68, ARC −5.37, TruthfulQA −12.65, Lambada PPL +22% (independent) | not found | ollama build needs v0.17.7+; family template fixes universal (Mar 2026) | card publishes no refusal/KL numbers; MXFP4 sensitivity in family Q4_K_XL builds | none (0.7/0.8/20 presence 1.5 matches); base model is the measured-cleaner router instrument | abliterlitics (I, measured), huihui card (V), unsloth qwen3.5 guide (V) |
| gemma-4-E4B-it-OBLITERATED | no KL published; v2 shipped 54 missing shared-KV tensors (vendor-disclosed, fixed v3) | not found (E4B) | n/a (no tools on seat) | **~20% degenerate repetition, ~28% soft deflection, ~4% wrong-language (card's own numbers)**; arch needs Ollama 0.20+/llama.cpp b8665+ | repeat_penalty 1.1 mitigation = Ollama default (aligned); English system prompt = satisfied | OBLITERATUS card (V), mradermacher GGUF (V), llama.cpp#28997 (A) |

Tag key for the last column: (V) vendor · (A) anecdotal/user report · (I) independent.

---

## Sources

**Measured (number with method/hardware):**
- M2 Ultra decode/prefill table for Gemma 4 builds — https://github.com/ollama/ollama/issues/18823 (2026-10-06)
- Unsloth Gemma 4 QAT analysis (Q4_0 70.2% vs UD 85.6% top-1; sizes) — https://docs.unsloth.ai/models/gemma-4/qat.md (Jun 2026)
- Abliterlitics Qwen3.5-9B forensics (8-task table, vLLM bf16; refusal 100%; KL/method analysis) — https://abliterlitics.dev/models/qwen3.5-9b/ (read 2026-10-18)
- OBLITERATUS E4B v3 quality table (0% hard / 28% soft / 51% coherent / 20% degenerate; tensor fix) — https://huggingface.co/OBLITERATUS/gemma-4-E4B-it-OBLITERATED (read 2026-10-18)
- Foundation-Sec-8B-Reasoning CTI table + HarmBench row (0-shot, temp 0.3) — https://huggingface.co/fdtn-ai/Foundation-Sec-8B-Reasoning (read 2026-10-18)
- Granite 4.1 3B/8B/30B vendor eval table — https://huggingface.co/ibm-granite/granite-4.1-30b (2026-04-29)
- Laguna XS 2.1 bench table + methodology (Harbor, temp 1.0/20/1.0, thinking on) — https://huggingface.co/poolside/Laguna-XS-2.1 (2026-06-20)
- VulnLLM-R paper F1 tables — https://arxiv.org/abs/2512.07533 (2025-12-08); card https://huggingface.co/UCSB-SURFI/VulnLLM-R-7B
- DeepSeek-R1-0528-Qwen3-8B distillation table — https://huggingface.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF (2025-05-29)
- LFM2.5-8B-A1B card tables (IFEval/BFCL/Tau²; H100 throughput) — https://huggingface.co/LiquidAI/LFM2.5-8B-A1B (read 2026-10-18)
- GLM-4.7-Flash vendor bench table — https://huggingface.co/unsloth/GLM-4.7-Flash-GGUF (read 2026-10-18)

**Anecdotal (user reports; dates are issue/discussion dates):**
- llama.cpp: #26088, #30759, #30698, #28997 (Gemma 4); #19081, #19307, #19068, #20464 (GLM);
  #16686, #26987, #29251, #29629, #27606, #28614, #30490, #28675 (Qwen3-Coder / Qwen3-VL / LFM2.5)
- ollama: #17978 (qwen3-vl loop), #17602/#17632/#17524/#17406 (Laguna), #16686/#18530/#18421/#18430
  (qwen3-coder), #18658/#18659/#13886/#14273/#16497 (GLM), #18823/#18824/#18940/#17152 (Gemma 4),
  #13465 (Mistral import), #15734 (R1 convert, llama.cpp)
- HF discussions (unsloth/GLM-4.7-Flash-GGUF): #1/#10 (Jan-21 reupload), #13 (repeat penalty),
  #14/#26 (thinking loops), #25 (tool calls vs reasoning), #30 (64K degradation), #23 (Ollama
  Modelfile fix), #19/#18 (CUDA tok/s), #22 (HumanEval), #33 (bartowski preference)

**Vendor (cards, guides, build-provider docs):**
- https://docs.unsloth.ai/models/gemma-4.md (+ /qat.md) · https://docs.unsloth.ai/models/glm-4.7-flash ·
  https://docs.unsloth.ai/models/qwen3.5.md · https://docs.unsloth.ai/models/tutorials/qwen3-coder-how-to-run-locally.md ·
  https://docs.unsloth.ai/basics/deepseek-r1-0528 · https://docs.unsloth.ai/basics/dynamic-3.0-ggufs.md
- https://huggingface.co/unsloth/gemma-4-26b-a4b-it-GGUF · https://ollama.com/library/gemma4:26b-a4b-it-qat (Q4_0, baked 1.0/0.95/64) ·
  https://huggingface.co/unsloth/granite-4.1-8b-GGUF · https://huggingface.co/poolside/Laguna-XS-2.1-GGUF ·
  https://huggingface.co/huihui-ai/Huihui-Qwen3.5-9B-abliterated · https://huggingface.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF ·
  https://huggingface.co/mradermacher/VulnLLM-R-7B-GGUF · https://github.com/ucsb-mlsec/VulnLLM-R
- Independent via first-pass docs (not re-fetched): ThreatClaw Foundation-Sec fresh-CVE numbers
  (2026-10-05); MathArena AIME-2026 = 50 for LFM2.5 (HF eval-results).

**Not found anywhere (searched 2026-10-18):** Apple Silicon tok/s for GLM-4.7-Flash, granite4.1,
R1-0528-8B (external), mistral-small3.2, LFM2.5 (external), qwen3-coder-30B, Laguna, qwen3-vl,
VulnLLM-R, Foundation-Sec, huihui-9B, E4B-OBLITERATED; quantization loss (KLD/PPL) for GLM,
granite, R1-8B, mistral, LFM2.5, qwen3-coder-30B, Laguna, qwen3-vl, VulnLLM-R, Foundation-Sec,
E4B-OBLITERATED; MMMU text for qwen3-vl-32B (card tables are images).
