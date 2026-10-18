# Real-world model evidence — second pass (rw_qwen)

Collected 2026-10-18. Companion to `docs/WFE_SEAT_PRIOR_20261018.md` / `docs/WFE_LANDSCAPE_FLEET_20261018.md`
(first pass = vendor cards + a few leaderboards). This pass collects the measured and anecdotal layer:
Unsloth quant-quality numbers, independent replications, Apple Silicon speed reports, agent/tool-calling
field reports, and the abliteration forensics the uncensored builds were missing.

Tag legend (per brief): **measured** = number with method/hardware · **anecdotal** = user report without method ·
**vendor** = model card / vendor docs. Every item has URL + date. "Not found" is written where nothing exists.
Reddit was fetch-blocked from this host; threads cited via `reddit.com/...` links are as linked from the
primary sources I could read, marked "via".

Sources that could not be read directly (repo gated/401): `huihui-ai/Qwen3.6-abliterated` (HF),
`orcarouter/Qwen3.8-27B-Uncensored` (HF), `txgsync/Qwen3.8-27B-oQ4e-mtp` (HF),
`orcarouter/Nex-N2.5-mini-Uncensored-MLX` (HF). Their public Ollama mirrors were used where they exist.

---

## 1. Qwen3.8-27B — unsloth GGUF Q4_K_M + oMLX Qwen3.8-27B-oQ4e-mtp

**Practical verdict.** The strongest 27B dense the community has run, with one loud caveat: the vendor's
`reasoning_effort: xhigh` default over-thinks badly on local hardware, and uniform GGUF quants have an
open deep-thinking failure mode. Community consensus (measured + anecdotal, several independent sources):
run it non-thinking (or low effort) for chat/tools; treat long xhigh CoT on GGUF quants as suspect. Our
fleet already runs `think: false` with the vendor instruct profile — that matches what users converged on.

**Quant quality (independent, measured).**
- Quesma (Piotr Migdał) ran the full Unsloth ladder on rented GPUs (~$3k Modal, llama.cpp Aug-16 build):
  **Q4_K_M is indistinguishable from BF16** on GPQA Diamond, IFBench *and* Terminal-Bench 2.1 (89-task
  agentic coding benchmark) — they also replicated Qwen's published BF16 scores on all three, which no
  prior independent run had done. `UD-Q2_K_XL` drops slightly on TB2.1 but still lands at "Opus 4.7 /
  Gemini 3.1 Pro level" and writes ~25% more tokens on the same solved tasks. 1-bit (`UD-IQ1_S/M`)
  collapses to random-chance GPQA and gets *worse* at xhigh because it reasons itself into empty answers.
  Reasoning-effort choice moves scores more than the quant does. **measured** —
  https://quesma.com/blog/qwen38-27b-quantizations-benchmarked/ (2026-08-26)
- Unsloth's own Dynamic 3.0 numbers (vendor): ">10% top-1 better accuracy at the same size compared to
  every other provider"; Divergence-300@32 held-out set; they warn 1-bit breaks tool calling and loops,
  and state Q2_K_XL (9.8 GB) is the floor for agentic use. **vendor** —
  https://unsloth.ai/docs/basics/dynamic-3.0-ggufs (Aug 2026)
- **Contradiction found (measured, cross-runtime).** HF discussion #135 (Jerryccccc, Oct 2026): uniform
  integer GGUF quants *silently break deep thinking* on this hybrid (Gated DeltaNet) architecture.
  On a 2× RTX 5060 Ti 16 GB: `UD-Q4_K_XL` never converges on a long-horizon canary (0 chars of output,
  budget burned in `<think>`), `UD-Q6_K_XL` tail-loops (~97% repeated 8-grams); reproduced on vLLM +
  gguf-plugin (different codebase) and on an AMD/Vulkan build by another user (reddit r/LocalLLM
  1wyui4o, via). The mixed-precision NVFP4 checkpoint (FP8 on the recurrent/attention path, FP4 on MLP)
  converges the same prompt in ~17K thinking tokens every time. Hypothesis (author's, unproven): GDN
  recurrent-state error accumulation over thousands of autoregressive steps — invisible to perplexity
  and KLD. Our fleet's Q4_K_M sits between Q4_K_S and Q4_K_XL; short-task chat is unaffected.
  **measured (with explicit n=1-per-config caveats)** —
  https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/discussions/135 (2026-10-05 … 10-17)
- The same #135 thread also carries the "Master Quantization Reference Table" pointer (reddit 1vrchn9,
  via) ranking NVFP4 KLD *worse* than UD-Q4_K_XL — the author's point being that KLD does not capture
  the long-horizon damage class.

**Apple Silicon speed (measured).**
- Mac Studio M3 Ultra 256 GB, Ollama Q4_K_M: **14.0 tok/s gen (13.2–15.4), 93.1 tok/s prompt**, vs
  qwen3.6:27b Q4_K_M at 28.6 tok/s / 95.0 tok/s on the same box. But 3.8 answers the same prompts in
  ~1/3 the tokens (890–1,090 vs 1,950–3,340), so wall-clock per answer is a near tie (67 s vs 72 s).
  1-bit quant: 27.2 tok/s but "cannot commit to an answer" (400 tokens of second-guessing).
  **measured** — https://terminalbytes.com/run-qwen-3-8-27b-locally/ (2026-08-27)
- Simon Willison, M5 Max 128 GB MacBook Pro + DGX Spark, LM Studio Q4_K_M: **15–30 tok/s**;
  MTP draft (`--spec-type draft-mtp`, llama.cpp) measured ~**+72%** on the Spark vs LM Studio default.
  **measured (informal comparative bench)** — https://simonwillison.net/2026/Aug/16/qwen-38-27b/
  (2026-08-16)
- Ours (internal, backends.yaml): oMLX side-car MTP (txgsync oQ4e-mtp) 17.5–18.6 tok/s vs 12.25 tok/s
  Ollama GGUF baseline (~1.45x, 60–65% draft accept) on this M4 Pro — consistent with the llama.cpp MTP
  reports. (Repo-internal, not public evidence.)
- Server-class cross-check (A100 80 GB, vLLM, BF16): Qwen3.8-27B ~18 tok/s vs Qwen3.6-27B ~62 tok/s —
  dense vs MoE, ~3.4x slower per token; responders note MTP draft acceptance is lower on 3.8 than 3.6.
  **measured/anecdotal mix** — https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/discussions/66 (2026-08-17)

**Tool-calling / agent reliability.**
- Simon Willison drove it in the Pi coding agent (LM Studio backend, DGX Spark): multi-step file-reading
  tool loop answered a codebase question solidly, then built *and self-tested* a jsonl→markdown converter
  from a single prompt. Bounding-box JSON vision output was near-perfect. **measured (published
  transcripts)** — same URL as above.
- Vendor/Unsloth: nested-object tool-call parsing fix and Developer-role support baked into their GGUFs
  (this is why our tags run the `gguf_chat_template` path cleanly — see `model_card_expectations.yaml`
  qwen3.8 note). **vendor** — https://huggingface.co/unsloth/Qwen3.8-27B-GGUF (card)
- Ollama-side tool/template bugs found in the wild (all Qwen3.x family, GitHub issues):
  `reasoning_effort:"xhigh"` was being rewritten to `"max"` and 500-ing chat templates (fixed 2026-10-11,
  #18943); qwen3.5 tool parser needed an empty-final-chunk flush (#18872, PR 2026-10-08); /api/chat
  returning 500 after llama-server completed on qwen3.8:27b (#18840, open 2026-10-07).
  **measured (issue reports)** — https://github.com/ollama/ollama/issues/18943 etc.

**Known problems and fixes.**
- **Overthinking default.** xhigh is the default; SimonW's pelican took 21 min / 22,276 reasoning tokens
  (137 s / 3,715 tokens with reasoning off). Consensus fix: `reasoning_effort: low|none` or `think:false`;
  our seats bake `think:false`. **measured** — https://simonwillison.net/2026/Aug/16/qwen-38-27b/
- **Runtime age.** `qwen35` arch needs a recent llama.cpp (older builds: `unknown model architecture:
  'qwen35'`) and Ollama ≥ 0.32.12. **measured** — https://terminalbytes.com/run-qwen-3-8-27b-locally/
- **MLX/Metal kernel panics on Apple Silicon (open).** "Maximum threads per threadgroup is 896 but
  requested 960" on M2 Max for Qwen 3.8 / Gemma 4 on Ollama's MLX runner (#18940 open 2026-10-11, #18966
  open 2026-10-12). Relevant to our M-series host if Ollama's MLX path serves these tags.
- **Deep-think non-convergence on uniform GGUFs** (discussion #135 above). Mitigation if it bites:
  thinking off / budget-capped, or mixed-precision NVFP4-style quants for long thinking.
- **Loop guard.** Vendor instruct profile uses presence_penalty 1.5 "to curb endless repetition"
  (higher risks language mixing). We bake 1.5. **vendor** — https://unsloth.ai/docs/models/qwen3.8

**Recommended settings vs ours.** Card/Unsloth instruct: temp 0.7 / top_p 0.8 / top_k 20 / min_p 0 /
presence 1.5 / rep 1.0; thinking: 1.0 / 0.95 / 20 / 0 / 0 / 1.0. **Ours (general-deep, auto-council):
identical instruct profile, `think:false`** — matches both the card and the community consensus. Deltas
vs vendor guidance: we cap context at 96k/32k (native 262k, YaRN 1M) and `predict_limit` 4096 (vendor
suggests huge output budgets for agentic long-form; fine for chat seats, would truncate long codegen).

## 2. Qwen3.6-35B-A3B — unsloth UD-Q4_K_XL (MoE, ~3B active)

**Practical verdict.** The fast lane. 3x+ the tok/s of the dense 27B at a real but bounded quality cost;
the cost concentrates in instruction-following/tool-discipline, not knowledge. Community Apple Silicon
numbers agree with our 54.2 tok/s M4 Pro measurement.

**Measured numbers.**
- Quesma benchmark on M5 Max 128 GB (8-bit): MLX 85 tok/s (37 GB), llama.cpp 93 tok/s (44 GB),
  llama.cpp+MTP **105 tok/s** (45 GB) — vs Qwen3.6-27B 8-bit at 17/18/32 tok/s. **measured** —
  https://quesma.com/blog/qwen-36-is-awesome/ (2026-06-29)
- Tool/instruction discipline anecdote, same article: in OpenCode, 35B-A3B built a hexagonal minesweeper
  but *ignored the instruction to create a pnpm package* (single index.html), where 27B did it properly —
  consistent with the vendor's own IFBench gap (63.7 vs 69.1/79.5). **measured (transcript-level)**
- har-ki's air-gapped Claude Code handbook, M3 Pro 36 GiB, Ollama MLX runner, NVFP4 (21 GB): decode only
  ~5–8 tok/s but the session is **prefill-bound** (300–400 tok/s prefill falling to ~270; a 25K-token
  turn = 60–70 s; prefill = 90%+ of request time). A 34-minute investigation→PR loop completed correctly
  with `MAX_THINKING_TOKENS=0` (default thinking burned the whole turn budget before any tool call).
  Hardware floor note: on 36 GiB the window is 32K; a 56K-token session thrashed KV (hit rate ~30%,
  prefill 2–3 min/turn). **measured** — https://har-ki.github.io/claude-code-sre-handbook/handbook/06-air-gapped/ (2026-06-11)
- Ours (internal): 54.2 tok/s M4 Pro (backends.yaml auto-data note).
- Speculative decoding is not free on every platform: "Qwen3.6-35B-A3B speculative decoding is
  net-negative on RTX 3090" (HN 2026-04-21, repo thc1006/qwen3.6-speculative-decoding-rtx3090, since
  deleted). **measured (repo, now 404)** — https://news.ycombinator.com/item?id=47843553
- swe-rebench (independent, CI-verified): 24.7 ± 0.79 (vs Qwen3.6-27B 31.2 ± 1.68). **measured** —
  https://swe-rebench.com/ (read 2026-10-18, prior pass S14)

**Quant quality.** Same Unsloth UD (dynamic) recipe as Qwen3.8; no independent KLD ladder published for
the 35B-A3B specifically — the community reference is the reddit "Qwen3.6 35B A3B quantization benchmark"
thread linked from unsloth/Qwen3.6-35B-A3B-GGUF discussion #10 (reddit, via; not fetchable here).
Vendor card (Unsloth GGUF card): developer-role support, nested-object tool-call fix. **vendor** —
https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF

**Known problems.** MoE VRAM: full residency is hard below ~24 GB (community fix: `-ncmoe N` expert
offload — sjakek card pattern). Thinking budget exhaustion on long CoT (base exhausts budget on 68% of
GSM8K at 7K budget — Abliterlitics, see §5). MoE instruction-following shortfall vs dense sibling.

**Settings vs ours.** Card instruct: 0.7 / 0.8 / 20 / min_p 0 / presence 1.5 / rep 1.0; thinking_general
1.0 / 0.95 / 20 + presence 1.5. **Ours (general-fast, UD-Q4_K_XL-ctx96k): identical instruct profile,
`think:false`.** No delta vs card. (HauhauCS card adds `--jinja` + ≥128K-ctx guidance — see §5.)

## 3. Qwen3.6-27B — dense 27B

**Practical verdict.** The quality pick of the Qwen3.6 generation and the best-documented quant ladder in
the fleet: 4-bit is measurably free. It over-thinks under small budgets (a real harness issue) and is
2x slower per token than the MoE sibling, but users consistently rate it the better coder/instruction-follower.

**Measured numbers.**
- Quesma quant ladder (37 GPU-h on own M5 Max + $1,430 cloud; Jul 2026): full KL / top-1 / collision-ppl
  per quant; **BF16→Q4_K_M indistinguishable** in blind Gemini-judged pelican duels (5 per quant,
  Bradley-Terry); 3-bit on the edge; 2-bit loses ~3 points (~19/20 duels vs the field). Terminal-Bench
  2.1: Q4_K_M ≈ BF16. AIME-120: every quant ≥4-bit ≈ BF16; quality tracks KL < 0.05 (quants >0.08 KL
  drop). **measured** — https://quesma.com/blog/qwen-quantization-quality/ (2026-07-27)
- Apple Silicon: qwen3.6:27b Q4_K_M **28.6 tok/s** gen / 95 tok/s prompt on M3 Ultra 256 GB (Ollama) —
  TerminalBytes, same article as §1. 8-bit on M5 Max: MLX 17, llama.cpp 18, +MTP 32 tok/s (Quesma).
  RTX 5090 user (gfosco, HN): Q6_K + Q4_0 KV, **50 tok/s at 123K context**, ~28/32 GB VRAM.
  **measured** — terminalbytes.com (2026-08-27), quesma.com (2026-06-29), news.ycombinator.com/item?id=47871338
- OpenCode field use: hexagonal minesweeper with a proper pnpm package, first try, single prompt;
  landing page from a friend's short prompt "worked, was responsive" — **measured (artifact-level)** —
  https://quesma.com/blog/qwen-36-is-awesome/ (2026-06-29)
- swe-rebench 31.2 ± 1.68 (independent). AA intelligence index 37 ("≈ mid-2025" class, vendor-adjacent).

**Known problems.** Budget-exhausted thinking: base empties on 68.2% of GSM8K at a 7K-token budget
(Abliterlitics base row, 2026-09-16 — also §5); "stops generating randomly" reports exist on the 3.8
sibling (HF discussion #134, 2026-10) — same hybrid family. Ollama MLX-runner panic with
qwen3.6:35b-mlx on 0.40.x (regression from 0.35.0, closed 2026-10-08, #18856).

**Settings vs ours.** Card: thinking 1.0/0.95/20 (general) & 0.6/0.95/20 (precise coding); instruct
0.7/0.8/20/presence 1.5. **Ours (auto-council legacy synthesizer tags, security council tags): instruct
profile; no delta.** Note auto-council's synthesizer seat has already moved to Qwen3.8-27B (§1).

## 4. Nex-N2.5-mini (bartowski Q4_K_M) vs Nex-N2-mini (sjakek UD-Q4_K_M)

**Practical verdict.** N2.5-mini is the newest model in this brief (card created 2026-09-08) and has
almost **no** community track record yet — no Apple Silicon tok/s reports, no agent-harness field
reports, one anecdotal HF discussion. What exists: strong same-vendor-suite gains over N2-mini
(+9.3 BrowseComp, +21.3 Toolathlon — the numbers that staged it as our auto-research challenger) and
measured KL data on the exact Q4_K_M we run. N2-mini has more history but still thin; its card's
own DeepSWE 8.0 vs SWE-V 74.4 is the widest quality spread of any model here.

**Quant quality.**
- bartowski N2.5-mini GGUF (the exact Q4_K_M we pull): **measured KLD vs unquantized: Q4_K_M
  0.0302 ± 0.0006** (computed per-tensor layout) vs 0.0415 ± 0.0006 standard (0.85x, +4.3% size);
  Q3_K_M 0.0659; IQ2_XXS 0.2401. Imatrix calibrated through the model's own chat template on a corpus
  that is 62.7% tool-calling/reasoning conversations. Q4_K_M = 22.32 GB. **measured** —
  https://huggingface.co/bartowski/nex-agi_Nex-N2.5-mini-GGUF (card, 2026-09)
- sjakek N2-mini GGUF (the incumbent seat): Unsloth-UD recipe quants, **MTP draft head NOT in the
  published checkpoint** (block_count=40, nextn_predict_layers=0) — MTP speedups do not apply to our
  N2-mini seat; imatrix borrowed from unsloth/Qwen3.6-35B-A3B-GGUF. **vendor** —
  https://huggingface.co/sjakek/Nex-N2-mini-GGUF (card)

**Community.**
- Only one discussion on the N2.5-mini GGUF repo: "reasoning-effort set to high = 🚀 very interesting
  speedy model" (vico44, 2026-09-11) — positive but method-less. **anecdotal** —
  https://huggingface.co/bartowski/nex-agi_Nex-N2.5-mini-GGUF/discussions/1
- Apple Silicon tok/s for either Nex build: **not found.**
- Tool-call reliability in real agents (opencode/Cline/Claude-Code): **not found** for either build;
  vendor cards assert robust function calling via `--tool-call-parser qwen3_coder` and our own
  preflight probes (3/3 single-call + clean tool-result turn at card sampling) are internal.
- Attribution controversy (does not touch quality, but touches the vendor card's framing): "Rio de
  Janeiro's 'homegrown' LLM appears to be a merge of an existing model" — a Brazilian project's claimed
  model was identified as merged Nex-N2 lineage; the HN thread's top comment notes "it works because
  Nex N2 is also a derivative of the original base Qwen model" (both are Qwen3.5-35B-A3B post-trains).
  The tracking issue (nex-agi/Nex-N2#4) is now 404. **anecdotal (news)** —
  https://news.ycombinator.com/item?id=48528371 (2026-06-14)

**Card-claimed numbers (vendor, same-suite).** N2-mini: BrowseComp 74.1, GDPval 1402, Toolathlon 33.3,
WideSearch 62.0, TAU3 65.9, SWE-V 74.4, TB2.1 60.7, SWE-Pro 50.2, GPQA-D 82.6, IFEval 89.1, DeepSWE
8.0. N2.5-mini: BrowseComp 83.4, Toolathlon 54.6, AutomationBench 32.3, GDPval-AA 1446, TB2.1 73.4,
SWE-Pro 43.8, DeepSWE 36.1, OSWorld-V 71.2, Job Bench 28.5. Sampling 0.7/0.95/40 for both; N2.5-mini's
reasoning_effort defaults to **medium** (adaptive thinking). **vendor** —
https://huggingface.co/nex-agi/Nex-N2-mini and /Nex-N2.5-mini (cards, 2026-06 / 2026-09-08)
- No independent replication of the N2.5-mini suite found (Toolathlon/OSWorld rows are NexCUA-harness
  numbers; OSWorld-Verified 71.2 is the only one with a public leaderboard twin).

**Settings vs ours.** auto-research runs sjakek UD-Q4_K_M-ctx16k at **0.7/0.95/40 + min_p 0.02** — the
card sampling plus a min_p the card doesn't specify; ctx 16k vs native 262k (research seat budget).
Challenger bartowski Q4_K_M-ctx16k has no baked sampling (pipeline sends card values). Delta to watch:
N2.5-mini's adaptive-thinking default (medium) — if the research seat expects deterministic reasoning,
set `reasoning_effort` explicitly; nothing in our config currently does.

## 5. Uncensored Qwen3.6 builds — HauhauCS Aggressive + huihui abliterated

**Practical verdict.** The first pass flagged "no public numbers" for these. That's now wrong for the
27B family: Abliterlitics ran a full forensic comparison (5 techniques, RTX 5090, ~85 GPU-h, 2026-09-16).
Both our lineages ablate refusal nearly completely and preserve knowledge; the difference is *thinking
efficiency and empty-response rate* — HauhauCS empties 5.5% of the time at a 6K budget (base 0.3%),
Huihui 1.3%. HauhauCS's "lossless / no changes to capabilities" card claim is **contradicted**: its KL
(0.0242) is 3.3x Huihui's (0.0074) and it touches 66% of tensors; but the measured *capability* damage
is still small (MMLU +0.6 vs base). Also: the tool HauhauCS used ("Reaper Abliteration") is publicly
documented as plagiarised from Heretic under AGPL with attribution stripped — the build lineage, not
the model output, is the problem; Abliterlitics dropped HauhauCS from future comparisons over it.

**Measured numbers (all: abliterlitics.dev/models/qwen3.6-27b/, 2026-09-16; note these are the 27B
variants — the 35B-A3B variants we also run have not been measured publicly):**
- **KL vs base (lower = better):** Heretic 0.0037, **Huihui 0.0074** (both "excellent"), Abliterix
  0.0222, AEON 0.0238, **HauhauCS 0.0242** ("very good"). Damage threshold per their other work ≈ 0.1.
- **HarmBench 400 (ASR):** Huihui 98.5% → 99.8% with CoT analysis; HauhauCS 94.5% → 100%.
- **MMLU:** base 83.3 → Huihui 83.4 (+0.1), HauhauCS 83.9 (+0.6).
- **GSM8K raw:** base 34.4 → Huihui 75.1, HauhauCS 51.0 — but this is a **thinking-budget artifact**:
  base exhausts its budget on 68.2% of questions, Huihui on 23.0%, HauhauCS on 49.3%; adjusted
  (answered-only) scores are 96.0–96.6 ≈ base 96.2. Abliteration changes how long the model thinks,
  not how well it reasons. (The "Huihui got better at math" take circulating elsewhere is false.)
- **TruthfulQA MC2:** base 56.7 → Huihui 54.8 (−1.9), HauhauCS 47.2 (−9.5). Truthfulness is the one
  axis where the aggressive build measurably pays.
- **Empty responses:** base 1 (0.3%), Huihui 5 (1.3%), HauhauCS 22 (5.5%).
- **Weight forensics:** Huihui edits 128/850 tensors (15.1%, gentlest of the five); HauhauCS 564/850
  (66.4% — Reaper multi-projection ablation + GGUF Q8_K_P round-trip noise superimposed; the noise is
  diffuse and behaviourally benign per their KL/bench results).
- Category table: harassment and "harmful" are 100% ASR for all five methods; HauhauCS also 100% on
  misinformation; cybercrime 88.1 (HauhauCS) vs 95.5 (Huihui).
- huihui's own HF repo for Qwen3.6-abliterated is gated (401); the Ollama mirror publishes no refusal
  count or KL (just usage warnings + lineage). **vendor (absence of numbers)** —
  https://ollama.com/huihui_ai/Qwen3.6-abliterated (tags: 27b 17 GB / 35b 24 GB, 256K ctx)
- HauhauCS card: "0/465 Refusals", "no changes to datasets or capabilities", K_P quants, `--jinja`
  flag, **"keep at least 128K context to preserve thinking capabilities"**. **vendor** —
  https://huggingface.co/HauhauCS/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive (card)

**Contradiction to flag:** auto-creative and auto-general-uncensored run these at **ctx8k**, and the
HauhauCS card (echoing Qwen's own docs) says ≥128K context is needed to preserve thinking. Combined
with the 5.5% empty rate at 6K output budget, the 8K-window seats are running this family in exactly
the regime where its abliteration side-effects concentrate. The throwaway lane's ctx256k tag is the
only seat honouring the guidance.

**Settings vs ours.** Family sampling = qwen3.6 (instruct 0.7/0.8/20/presence 1.5; HauhauCS card adds a
reasoning-task mode 1.0/1.0/40/presence 2.0 we don't use). Ours matches the instruct profile; deltas are
the 8k context tags and the inherited min_p/repeat defaults — no behavioural bug reports found from the
community to justify changing sampling itself.

## 6. orcarouter Qwen3.8-27B-Uncensored

**Practical verdict.** The standout of the uncensored group — and the only one where an independent
panel said the card is honest. Abliterlitics' 12-variant Qwen3.8 comparison (167 + 166 GPU-h, RTX 5090,
dynamic FP8, LLM-judged over full reasoning traces) crowns it: **judge ASR 82.2% (96.7% harmful-only),
top of the panel**, KL 0.0676 ("very good"), capability deltas within ±0.5 pp of base on MMLU-Pro
(62.78 vs 62.82) and GSM8K (90.8 vs 91.2), IFEval actually +0.4. Its card's refusal tables and
capability-retention table were verified claim-by-claim ("4 of 4 card claims verified"). The one real
cost, shared by every aggressive arm: it thinks *much* harder on adversarial prompts (mean 23,830
reasoning chars vs base 2,900; 38% unterminated-think rate on the 400-item HarmBench run at temp 0 —
worst-case, greedy decoding). **measured** — https://abliterlitics.dev/models/qwen38-27b/ (2026-09)

**Card numbers (vendor, vLLM-served vs base FP8, rule-based refusal classifier).** Harmful refusal
0–6% across 8 suites (base 64–99%); thinking-ON refusal ≤1.7%; over-refusal XSTest 0.4% (base 5.6%);
capability retention vs base: MMLU 84.7 (+0.4), MMLU-Pro 76.8 (−0.8), GSM8K 88.7 (−1.3), CMMLU 80.8
(−0.6), WikiText-2 ppl 6.96. q4_K_M 18 GB "recommended default"; MTP + vision tower + 262K preserved;
requires Ollama ≥ 0.17.1; 16 tags each passed 10/10 per-tag release checks. **vendor** —
https://ollama.com/orcarouter/Qwen3.8-27B-Uncensored (HF source repo gated/401)

**Community field reports:** not found (model is ~1 month old; no r/LocalLLaMA threads fetchable, no
agent-harness reports). Our internal WFE: 9/9 home:coding, 26/29 discovery:compliance_agentic
(config/portal.yaml note) — internal, not public.

**Settings vs ours.** Card: q4_K_M default, context deliberately un-pinned (VRAM-tiered: 4K < 24 GiB,
32K up to 48 GiB, 256K above). Ours: `orcarouter/Qwen3.8-27B-Uncensored:Q4_K_M-ctx32k` derived tags
(auto-coding fast-repair / uncensored-fast hints) — matches their 32K tier on this 64 GB host.
Sampling = qwen3.8 instruct profile (0.7/0.8/20/presence 1.5). No delta.

---

## Cross-model table

| model | quant loss | Apple Silicon tok/s | tool-call reliability | known issues | settings delta vs ours | sources |
|---|---|---|---|---|---|---|
| Qwen3.8-27B (unsloth Q4_K_M + oMLX oQ4e-mtp) | Q4_K_M ≈ BF16 on GPQA-D, IFBench, TB2.1 (independent); 1-bit collapses. Open issue: deep-think non-convergence on uniform GGUFs (KLD-invisible) | 14.0 gen / 93.1 PP (M3 Ultra 256 GB, Ollama); 15–30 (M5 Max, LM Studio); +72% with MTP (Spark); ours: 17.5–18.6 oMLX-MTP vs 12.25 GGUF | Good: real Pi-agent loop + self-tested script; Unsloth nested-object tool fix; Ollama #18943/#18872 template+parser bugs fixed Oct | xhigh overthinking default (21 min pelican); MLX SDPA kernel panic open on M2 Max (#18940); needs fresh llama.cpp/Ollama ≥0.32.12 | none on sampling (0.7/0.8/20/pres1.5, think:false = card instruct + community consensus); ctx capped 96k/32k vs 262k | quesma.com (08-26), terminalbytes.com (08-27), simonwillison.net (08-16), HF disc 135/66, github ollama |
| Qwen3.6-35B-A3B (unsloth UD-Q4_K_XL) | No public KLD ladder found; UD recipe same as family. swe-rebench 24.7±0.8 | 85 MLX / 93 llama.cpp / 105 +MTP (M5 Max, 8-bit); ours 54.2 (M4 Pro); 5–8 decode + 300–400 PP prefill-bound on M3 Pro 36 GiB | Adequate, discipline gaps: ignored package instruction in OpenCode (vs 27B); vendor IFBench 63.7 | MoE VRAM on small cards (use -ncmoe); SD net-negative on RTX 3090; thinking burns turn budget in Claude Code (fix MAX_THINKING_TOKENS=0) | none on sampling; ctx 96k | quesma.com (06-29), har-ki (06-11), HN 47843553 |
| Qwen3.6-27B | Best-documented ladder: 4-bit indistinguishable (blind duels, TB2.1, AIME-120); KL<0.05 tracks BF16 | 28.6 gen / 95 PP Q4_K_M (M3 Ultra); 17/18/32 MLX/llama/+MTP 8-bit (M5 Max); 50 tok/s @123K (5090) | Good: OpenCode package-creation first-try; no filed tool-call bugs found | Budget-exhausted thinking (68% empty GSM8K @7K budget); "stops generating" reports on family | none (instruct profile matches); legacy seats only | quesma.com (07-27, 06-29), terminalbytes (08-27) |
| Nex-N2.5-mini vs N2-mini (bartowski Q4_K_M / sjakek UD-Q4_K_M) | N2.5 Q4_K_M KLD 0.0302 (measured, our exact file); N2-mini UD no numbers | **not found** for either | **not found** (vendor asserts qwen3_coder tool format; ours probed 3/3 internally) | N2.5 too new: no community track record; N2-mini card DeepSWE 8.0 vs SWE-V 74.4 spread; no MTP head in sjakek checkpoint; merge-attribution controversy (HN) | N2-mini: +min_p 0.02, ctx 16k; N2.5: none yet — set reasoning_effort explicitly (default medium) | bartowski card (09-26), sjakek card, nex-agi cards, HF disc 1, HN 48528371 |
| HauhauCS Aggressive (Qwen3.6-35B-A3B) | KL 0.0242 vs base (very good) — card's "lossless" claim contradicted (3.3x Huihui's KL, 66% tensors touched); MMLU +0.6, TruthfulQA −9.5 | **not found** (same arch as §2 MoE) | not separately measured; family tools probed internally | 5.5% empty responses @6K budget; Reaper tool plagiarised-from-Heretic controversy (lineage, not quality) | ctx8k seats contradict card's ≥128K guidance; sampling matches | abliterlitics.dev/qwen3.6-27b (09-16), HauhauCS card, reddit 1sw77p0 (via) |
| huihui Qwen3.6-abliterated (27b/35b) | KL 0.0074 (best-in-class for Qwen3.6); avg non-GSM8K delta 0.5 pp; TruthfulQA −1.9 | **not found** | not separately measured | 1.3% empty @6K; no refusal/KL on card; HF repo gated | ctx8k tags vs ≥128K guidance; sampling matches | abliterlitics.dev/qwen3.6-27b (09-16), ollama.com huihui page |
| orcarouter Qwen3.8-27B-Uncensored | KL 0.0676; MMLU-Pro −0.0, GSM8K −0.5, IFEval +0.4 vs base (independent panel); card verified 4/4 | **not found** (dense 27B: expect ≈ Qwen3.8 §1 numbers) | card claims clean structured tool_calls; internal 9/9 WFE coding | 38% unterminated-think on adversarial prompts (temp 0, worst-case); copyright wall (39%, still panel-best) | none (ctx32k = their 32K tier; instruct sampling) | abliterlitics.dev/qwen38-27b (09-26), ollama.com orcarouter card |

**Notes on the table.** "Quant loss" = measured KL/task deltas where they exist; 35B-A3B UD and both Nex
builds are gaps (written as such). Apple Silicon rows are the quants we run where available, else the
closest published quant with hardware named. For every model in this brief, community consensus on
sampling equals the vendor instruct profile we already bake — the actionable deltas are context-window
sizing (HauhauCS/huihui at 8K), the Qwen3.8 deep-think GGUF issue for any long-CoT use, and the
Nex-N2.5-mini reasoning-effort default.

## Cross-model observations (things that contradict or extend the vendor cards)

1. **The Qwen3.8 vendor default (xhigh) is actively bad on local hardware** — SimonW, Quesma and the
   Abliterlitics budget analyses all converge. Every seat we run with `think:false` is following the
   strongest community consensus in this whole brief.
2. **Uniform GGUF vs mixed-precision quant is an open quality axis for the qwen35 hybrid family**
   (HF #135, cross-runtime, cross-vendor reproductions). Not captured by KLD/perplexity, and Unsloth's
   "Dynamic 3.0 is the best quant" claim is the specific claim under challenge for long-horizon thinking.
3. **Abliteration's measured cost is thinking-efficiency, not knowledge** (Qwen3.6-27B and Qwen3.8-27B
   panels agree): refusal removal is ~complete everywhere; empty/loop rates and TruthfulQA dips separate
   the aggressive builds from the surgical ones. "Huihui is better at math" (raw GSM8K) is an artifact.
4. **Runtime maturity is the common failure surface for the whole family on Apple Silicon**: Ollama MLX
   kernel panics (open), single-slot parallel forcing for hybrid archs (#18938), 0.40.x MLX runner
   regression, plus the "25–30% slower all models" regression report (#18968). Older-llama.cpp
   `unknown model architecture` failures are the most-reported user trap.
5. **Nex-N2.5-mini has vendor numbers and nothing else.** The +21.3 Toolathlon / +9.3 BrowseComp that
   staged it are same-vendor, same-harness; nothing independent or user-reported exists yet. Its seat
   promotion is a bet on a card, exactly the thing this evidence pass exists to guard against.
