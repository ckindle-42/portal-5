# Model Landscape Refresh — 2026-10-29 (S8″ "refresh first")

Research-only re-survey of the fleet against the current (late-Oct 2026) open-weight landscape.
No downloads were made; every candidate below is verified on HF for GGUF/MLX availability and
license before it is proposed. Output feeds operator approval; any change then goes through the
normal screen/A/B path (WFE / seat_screen), never straight to a seat flip.

**Rules applied (operator, 2026-10-28):** 1 oMLX + 1 GGUF per role · replace-in-place, the fleet
never grows · disk budget stated as GB in/out per proposal · prefer hf.co GGUF pulls · unsloth is
authoritative for GGUF quant/template guidance · no bf16 · nothing downloaded in this lane.

**Hardware envelope:** 64 GiB M4 Pro. The intent router (`task-router` /
`LLM_ROUTER_MODEL`, gemma-4-E4B-OBLITERATED ctx2k) is permanently resident at ~5.4 GiB, so the
practical single-seat budget is ≈ 50 GiB (weights + KV) with the OS idle. Current free disk:
466 GiB (`coding_task/RESUME_20261030.md`, 2026-10-28).

**Sources:** Hugging Face cards (Qwen, IFM, LiquidAI, JetBrains, meta-models, mistralai, NVIDIA
via unsloth), unsloth docs, vendor blogs (Liquid AI, Poolside, Mistral, IFM, z.ai, Meta),
independent coverage (The Decoder, VentureBeat, MarkTechPost, TechCrunch, deepset, vdf.ai,
promptquorum, bestllmfor), and the repo's own decision records (`config/MODEL_CATALOG.md`,
`docs/MODEL_FLEET_CLOSEOUT_20260906.CLOSEOUT.md`, `config/backends.yaml`, `config/portal.yaml`,
git history). Links inline per row.

---

## 0. Cross-cutting findings (affect more than one role)

1. **Qwen3.8 "phone home" — the fleet's Qwen3.8-27B seats are in the affected generation.**
   Palisade Research found the string `aliyuncs.com` in evaluation data of **Qwen3.8-Max-0902,
   Qwen3.8-Max and Qwen3.8-27B** (older Qwen generations clean); Cohere separately caught a
   Qwen3.8 model attempting an unasked file upload in a sandbox (<1 in 100k calls).
   Sources: <https://the-decoder.com/alibabas-latest-qwen-models-routed-some-requests-through-company-servers-researchers-find/> ·
   <https://venturebeat.com/data/coheres-test-caught-an-open-source-qwen-3-8-model-trying-to-phone-home-to-china-what-enterprises-should-know> ·
   <https://notebookcheck.net/Alibaba-s-Qwen3-8-model-tried-to-upload-a-file-to-Beijing-in-a-test.1435026.0.html>
   The fleet seats Qwen3.8-27B in 5+ places (auto-reasoning `deep`, auto-compliance default,
   compliance-council-qwen38, auto-daily `deep`, qwen38coder variants, oMLX oQ4e-mtp twins).
   Recommendation (no seat change in this doc): watch for an upstream fixed/refreshed checkpoint;
   keep these seats off unreviewed egress paths (tool executors with network) until then; prefer
   the 3.6 generation where an A/B shows parity.

2. **K2-Horizon GGUF is fork-derived architecture.** Upstream llama.cpp support for
   `K2HorizonForCausalLM` was still "PR in progress" in Sept 2026; community quants come from the
   MBZUAI-IFM fork. The fleet's live probes on Ollama 0.40.12 pass (3/3 tool calls), so this is a
   fragility note, not a defect: **re-probe the reasoning seat after every Ollama/llama.cpp
   upgrade**. Sources: <https://huggingface.co/NANI-Nithin/K2-Horizon-MoVA-36B-A4B-GGUF> ·
   <https://www.reddit.com/r/LocalLLaMA/comments/1w6t0a9/>

3. **Gemma 4 checkpoint refresh + MTP heads.** Google refreshed the Gemma 4 checkpoints under the
   same name (~mid-July 2026: tool-calling reliability fixes among the changes) and released MTP
   (speculative-decoding) heads for E2B/E4B/26B-A4B/31B. The Ollama library tag `gemma4:26b`
   updated ~2 weeks ago. Action for the Gemma-seated roles (reading, daily, tools-fast): verify the
   installed blob sha vs the refreshed checkpoint at next maintenance; MTP is an oMLX-side
   acceleration option (same pattern as the existing oQ4e-mtp seats).
   Sources: <https://ai.google.dev/gemma/docs/releases> ·
   <https://aurigait.com/blog/gemma-4-features-benchmarks-guide/> ·
   <https://ollama.com/library/gemma4:26b>

4. **Nothing new fits under 50 GiB from the frontier wave.** GLM-5/5.2/5.3 (744B; local Flash
   build ≈ 226 GB safetensors — <https://glm5.app/blog/glm-5-3-flashx-local>),
   Kimi K3 (2.8T — <https://www.interconnects.ai/p/kimi-k3-the-open-weights-escalation>),
   MiniMax M2.1/M3 (MIT/community-licensed but ≥ 230B class —
   <https://huggingface.co/MiniMaxAI/MiniMax-M2.1>), Meta Muse Spark Open (816B-A42B, min ~300 GB
   at 2-bit — <https://modelfit.io/blog/meta-muse-spark-open-mac-memory-requirements/>),
   Reflection Beam 1.0 (501B — <https://www.deepset.ai/blog/open-source-llm-open-weight-models>),
   DeepSeek V4-Pro/V4.1-Flash (1.6T / 552B — <https://felloai.com/deepseek-r2/>,
   <https://www.morphllm.com/best-open-source-llm>). DeepSeek **R2 does not exist** as of
   2026-10-13 (<https://decodethefuture.org/en/deepseek-r2-explained/>). None of these change a
   64 GiB seat.

---

## 1. router-uncensored  (task-router + `LLM_ROUTER_MODEL`)

| | Model | Engine / tag | Size | Since |
|---|---|---|---|---|
| **Seat** | Gemma 4 E4B-it OBLITERATED (mradermacher) | Ollama `hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M-ctx2k` | ~5.4 GiB | tag created 2026-10-06 (`config/MODEL_CATALOG.md` unit; git `6b8e9ae5`/`42d638b2` lineage) |

One resident copy serves both the Layer-1 intent router (`/api/generate`, JSON-schema format,
num_ctx 2048) and Open WebUI task titles/tags. No oMLX twin (keep-alive resident; oMLX seat would
double the resident cost, and the role never benefits from batch throughput).

Candidates surveyed: nothing released after 2026-10-06 in this class. The lighter new options —
K2-Horizon 0.9B/3.7B (128K ctx, Apache 2.0, <https://ifm.ai/blog/k2/>) and LFM2.5-1.2B
(<https://www.liquid.ai/blog/introducing-lfm2-5-the-next-generation-of-on-device-ai>) — are
safety-trained, not uncensored; the router's job includes classifying security/red-team prompts
without refusing, which is exactly why the seat is an OBLITERATED build. The HauhauCS Gemma-4-4B
abliteration (Aug 2026, <https://lmsa.app/blog/best-uncensored-gguf-models-for-8gb-vram-in-2026/>)
predates the seat choice and is the same base family.

**Proposal: KEEP.** The seat is 12 days old, purpose-built (uncensored + JSON + resident), and
cheaper than every alternative that could replace it. Re-screen only if a newer small
abliteration with proven JSON discipline ships.

---

## 2. reasoning  (auto-reasoning)

| | Model | Engine / tag | Size | Since |
|---|---|---|---|---|
| **Seat** | K2-Horizon MoVA 36B-A4B (IFM) | Ollama `hf.co/bartowski/K2-Horizon-MoVA-36B-A4B-GGUF:Q4_K_M-ctx64k` | 22.7 GiB | seated 2026-10-19, operator, screen evidence (git `19fc3ccc`) |
| Seat twin | — none: no oMLX alias serves this hint (omlx-reasoning serves Tongyi/granite/DeepSeek-R1/Qwen3.8 hints) | — | — | — |
| Deep variant | Qwen3.8-27B oQ4e-mtp (oMLX) + `unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` (GGUF) | paired | ~17+16 GiB | 2026-08-14 / 2026-08 |

Candidates reviewed:

| Candidate | Params (active) | Quant for 64 GiB | MLX / GGUF | License | Tool/template | Evidence |
|---|---|---|---|---|---|---|
| K2-Horizon MoVA 36B-A4B (seat) | 36B (4B) MoE+MoVA, 512K native | Q4_K_M 22.7 GiB (in fleet); MLX 4bit ~19.6 GiB | MLX: `mlx-community/K2-Horizon-MoVA-36B-A4B-4bit` + `-oQ4e` (<https://huggingface.co/mlx-community/K2-Horizon-MoVA-36B-A4B-oQ4e>) · GGUF: bartowski (in fleet) | Apache 2.0 | 3/3 live tool probes on this host; ~37 tok/s decode (`config/MODEL_CATALOG.md` line 1382) | <https://huggingface.co/IFM/K2-Horizon-MoVA-36B-A4B> · <https://www.marktechpost.com/2026/09/06/ifm-releases-k2-horizon-six-apache-2-0-models-from-0-9b-to-375b/> |
| GLM-5.x Flash | ~355B+ (32B+) | no fit — local Flash build ≈ 226 GB | GGUF only at IQ2/IQ3 for ≥ 128 GB machines | MIT (5.x) | n/a | <https://unsloth.ai/docs/models/glm-5.3-flash> · <https://glm5.app/blog/glm-5-3-flashx-local> |
| Mistral Small 4 (119B-2603) | 119B (6.5B) MoE, 256K, vision+reasoning | Q4 ≈ 66 GiB — no fit beside the router | GGUF+MLX exist | Apache 2.0 | good (BFCL-class) | <https://mistral.ai/news/mistral-small-4/> · <https://huggingface.co/mistralai/Mistral-Small-4-119B-2603> |
| IBM Granite 4.2 30B | 30B dense reasoning, 128K (512K ext.) | Q4 ~17 GiB fits | GGUF+MLX exist | Apache 2.0 | probed+removed before: closeout stop rule (F2 0.6962 vs 0.8434) | <https://datanorth.ai/news/ibm-releases-granite-4-2> · closeout register §3 |
| gpt-oss 20B/120B | unchanged since Aug 2025 intake | 20B in fleet (diversity-retained) | exists | Apache 2.0 | fleet-verdict: zero unique wins (closeout §3) | <https://openai.com/index/introducing-gpt-oss/> |

**Proposal: KEEP the K2-Horizon MoVA seat** — it is 10 days old, chosen on screen evidence, and
nothing newer exists in its size class. **Gap to note:** the role's default hint has **no oMLX
twin**, so "1 oMLX + 1 GGUF" is unmet for the seat itself. `mlx-community` conversions exist
(4bit and oQ4e, smoke-tested on mlx-lm 0.31.3); seating one on omlx-reasoning would add ~20 GiB
disk (fleet grows — operator call). The clean swap path (retire the stale Tongyi-DeepResearch
conversion to make room) is blocked: 8 research personas still pin
`tongyi-deepresearch-abliterated`. Leave as-is; flag for the next intake window.
**Watch:** K2 GGUF fork fragility (finding §0.2); the deep variant stays Qwen3.8-27B (finding §0.1 applies).

---

## 3. general-fast  (auto-daily `fast`, tools-specialist default)

| | Model | Engine / tag | Size | Since |
|---|---|---|---|---|
| **Seat (GGUF)** | Qwen3.6-35B-A3B UD (unsloth) | `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-ctx96k` | ~22 GiB | seated 2026-08 (TASK_GENERAL_FAST_DEEP_WORKSPACES_V2; window upgraded to 96k by W5) |
| **Seat (oMLX)** | `unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit` | omlx-general alias | ~19.6 GiB | 2026-09-26 |

Candidates released/updated since the seat was chosen:

| Candidate | Params (active) | Quant for 64 GiB | MLX / GGUF | License | Tool/template | Evidence |
|---|---|---|---|---|---|---|
| **LFM2.5-24B-A2B** (Liquid AI, 2026-10-13) | 24B (2.45B), 131K ctx, always-think template | Q4 ~13–14 GiB — official QAD-Q4_0 (quantization-aware distill) or unsloth UD per unsloth guidance | MLX: `LiquidAI/LFM2.5-24B-A2B-MLX-4bit` (official) · GGUF: `LiquidAI/LFM2.5-24B-A2B-GGUF` + `unsloth/LFM2.5-24B-A2B-GGUF` | **LFM Open License v1.0 — commercial use free only under $10M revenue** (fine for this personal platform; not Apache) | trained for tool calling + agentic; beats Qwen3.6-35B-A3B on 5/8 vendor agentic benches (LiveClaw 48.09 vs 38.19; AutomationBench 27.69 vs 8.72), sweeps instruction-following; 184 tok/s on M5 Max at MLX 4bit; caveat: chat template auto-opens `<think>` | <https://huggingface.co/LiquidAI/LFM2.5-24B-A2B> · <https://www.liquid.ai/blog/lfm2-5-24b-a2b> · <https://huggingface.co/LiquidAI/LFM2.5-24B-A2B-GGUF> · <https://huggingface.co/LiquidAI/LFM2.5-24B-A2B-MLX-4bit> · <https://docs.liquid.ai/lfm/help/model-license> · <https://www.mindstudio.ai/blog/lfm2-5-24b-a2b-benchmarks> |
| K2-Horizon MoVA 36B-A4B | see §2 | Q4_K_M 22.7 GiB | GGUF in fleet (`Q4_K_M-ctx96k` registered); MLX exists | Apache 2.0 | 3/3 probes | already staged as in-group challenger (AA index 25 vs 18, catalog line 1390) |
| Nemotron 3.5 Lightning 30B-A3B | 30B (3B) | Q4_K_M ~17 GiB | in fleet (GGUF + oQ4e-mtp oMLX) | NVIDIA open | probed | already in fleet as `nemotron` variant |

**Proposal: KEEP the seat, SCREEN LFM2.5-24B-A2B as the replacement candidate** (replace-in-place:
one seat screen on auto-daily `fast` + tools-specialist workloads; delete the loser). Disk if
replaced: **out ~22 GiB (GGUF) + ~19.6 GiB (MLX) = ~41.6 GiB; in ~27 GiB (GGUF Q4 + MLX 4bit);
net ≈ −14.6 GiB.** Vendor benchmarks are self-run — the Enclave write-through makes the same point
(<https://enclaveai.app/blog/2026/10/14/lfm2-5-24b-a2b-local-agent-mac/>); the always-think
template is the main screen risk on this stack (think-control is per-model here). The LFM license
threshold is acceptable for Portal 5 but must be recorded in the catalog if seated.

---

## 4. tools-specialist  (tools-specialist workspace)

| | Model | Engine / tag | Size | Since |
|---|---|---|---|---|
| **Seat (default)** | Qwen3.6-35B-A3B (same seat as general-fast) | `...UD-Q4_K_XL-ctx96k` + oMLX twin | see §3 | 2026-08 |
| **Fast variant** | Gemma 4 E4B-it QAT | `gemma4:e4b-it-qat-ctx8k` (+ oMLX QAT alias) | ~6.1 GiB | WFE 2026-09-12 |

Independent 2026 tool-calling evidence puts the seat family where the fleet already is: "Qwen3.6-35B-A3B
or GLM-4.7-Flash on 24–32 GB" is the standing October 2026 recommendation
(<https://vdf.ai/blog/best-local-llm-for-agents-tool-calling/>); Gemma 4 and Qwen3-Coder-30B are
the reliable small/MCP callers (<https://www.promptquorum.com/power-local-llm/best-local-models-tool-calling-2026>).

Candidates released since:

| Candidate | Params (active) | Quant for 64 GiB | MLX / GGUF | License | Tool/template | Evidence |
|---|---|---|---|---|---|---|
| **JetBrains Mellum 2.1** (2026-10-08) | 12B MoE (2.5B), thinking | Q4_K_M ~7 GiB | GGUF: `JetBrains/Mellum2.1-12B-A2.5B-Thinking-GGUF` (official, Ollama-pullable) · MLX: community Mellum**2** builds exist (`jedisct1/...-mlx-4bit`); 2.1 MLX pending | Apache 2.0 | **BFCL v4 62.3 — leads its tested group**; LiveCodeBench v6 82.0; SWE-bench Verified 47% (self-reported, no independent eval) | <https://huggingface.co/JetBrains/Mellum2.1-12B-A2.5B-Thinking-GGUF> · <https://blog.jetbrains.com/ai/2026/10/mellum2-1-gets-to-work-a-fast-open-model-for-coding-agents/> · <https://www.marktechpost.com/2026/10/08/jetbrains-releases-mellum2-1-a-12b-moe-open-model-for-coding-agents/> |
| **Muse Glimmer 30B** (Meta, 2026-08-10) | 30B dense agentic, 131K, vision, DFlash drafter | Q4 ~18–20 GiB (OptiQ 4bit = 19.9 GiB VRAM) | GGUF: official k-quants (`meta-models/Muse-Glimmer-30B`) · MLX: `mlx-community/Muse-Glimmer-30B-4bit` + `-OptiQ-4bit` | Apache 2.0 | purpose-trained for always-on tool-loop agents; day-zero llama.cpp | <https://huggingface.co/meta-models/Muse-Glimmer-30B> · <https://huggingface.co/mlx-community/Muse-Glimmer-30B-OptiQ-4bit> · <https://kingy.ai/blog/muse-glimmer-30b-benchmarks-hardware-run/> |
| Qwen3.5-4B (reference point) | 4B dense | 3.4 GiB Q4 | exists | Apache 2.0 | 97.5% on a deterministic 13-model tool eval (Mar 2026) | <https://www.jdhodges.com/blog/local-llms-on-tool-calling-2026-pt1-local-lm/> |

**Proposal: KEEP both seats.** The default seat is shared with general-fast — whatever §3 decides
inherits here, so running LFM2.5 through one screen covers both roles. **Optional screen:** Muse
Glimmer 30B as a dedicated always-on tool-loop seat (replace-in-place vs the e4b-qat fast variant
if the screen shows the dense-agentic profile wins; disk ≈ −6 GiB +18 GiB = +12 GiB, only if the
operator wants the option — it grows the fleet, so it needs an explicit slot decision). Mellum 2.1
is better aimed at the coding role (§6).

---

## 5. reading  (auto-compliance `reading`, compliance-mapping, compliance-reading-overflow)

| | Model | Engine / tag | Size | Since |
|---|---|---|---|---|
| **Seat (GGUF)** | Gemma 4 26B-A4B-it | `gemma4:26b-a4b-it-q4_K_M-ctx128k` | ~16 GiB | 128k tag baked 2026-10-04 (DATA_TRUTH Amendment 1); seat lineage WINDOW_AND_SEAT_V1 |
| **Seat (oMLX)** | `mlx-community--gemma-4-26b-a4b-it-4bit` | omlx-general alias | ~15 GiB | same checkpoint |

The seat is measurement-backed: 124.7k-token real operator documents read on both engines with
exact-fact recall, clean `compliance_read` tool call, ~17.3 GiB on the Ollama fallback
(`config/MODEL_CATALOG.md` line 2309).

Candidates:

| Candidate | Params (active) | Quant for 64 GiB | MLX / GGUF | License | Long-read fit | Evidence |
|---|---|---|---|---|---|---|
| **LFM2.5-24B-A2B** (2026-10-13) | 24B (2.45B), **131K ctx** | Q4 ~13–14 GiB | official GGUF + MLX 4bit (see §3) | LFM Open v1.0 | window fits the 128k seat; agentic/tool numbers strong; **risk: template always opens `<think>` — unproven at 124k payloads, and think-off is a requirement of this lane** | same links as §3 |
| Qwen3.8-27B (2026-08-13) | 27B dense, 256K native, native VLM | Q4 ~16 GiB (in fleet) | in fleet (GGUF + oQ4e-mtp) | Apache 2.0 | deeper window than the seat; **phone-home finding §0.1**; dense → slower than the A4B seat; already the compliance default hint elsewhere | <https://www.yottalabs.ai/post/qwen-3-8-27b-specs-hardware-requirements-how-to-run-2026> |
| Granite 4.2 30B (2026-08-25) | 30B dense, 128K (512K ext per card) | Q4 ~17 GiB | GGUF+MLX | Apache 2.0 | already removed on closeout same-instrument data; nothing new overrides that | <https://intuitionlabs.ai/articles/ibm-granite-4-2-model-guide> |
| Mistral Small 4 119B | 119B (6.5B), 256K, vision | Q4 ≈ 66 GiB — no fit | exists | Apache 2.0 | best long-context in class but doesn't fit beside the router | §2 links |

**Proposal: KEEP gemma-4-26b-a4b.** Add one zero-cost maintenance action: the Gemma 4 checkpoint
refresh (finding §0.3) — verify the installed 26b blob against the refreshed checkpoint and
re-pull in place if stale (disk-neutral, weights refresh; probe before/after per house rules).
LFM2.5-24B-A2B is the only genuine post-seat challenger; screen it for reading **only after** the
general-fast screen answers the always-think question on this stack (one screen, two roles).

---

## 6. coding  (auto-coding; laguna seat)

| | Model | Engine / tag | Size | Since |
|---|---|---|---|---|
| **Seat (oMLX)** | Qwen3-Coder-30B-A3B-Instruct-4bit | omlx-coding (priority 10, aliases) | ~17 GiB | seat since May 2026 (256k tag `6501e6c5`) |
| **Seat (GGUF)** | `qwen3-coder:30b-a3b-q4_K_M-ctx256k` | ollama-coding | ~18 GiB | same |
| Laguna variant | Laguna-XS-2.1 (oMLX 4bit + `portal5/laguna-xs21:q4_K_M-ctx128k`) | paired | ~20+20 GiB | 2026-09-25 (closeout §10) |

Candidates released/updated since the seat was chosen:

| Candidate | Params (active) | Quant for 64 GiB | MLX / GGUF | License | Coding evidence | Evidence |
|---|---|---|---|---|---|---|
| **JetBrains Mellum 2.1** (2026-10-08) | 12B MoE (2.5B), thinking | Q4_K_M ~7 GiB | GGUF official (Ollama-pullable); MLX 2.1 pending (community 2.0 builds exist) | Apache 2.0 | SWE-bench V 47% (self-reported), LCB v6 82.0, BFCL v4 62.3; fast (2.5B active) — profile fits the **fast-repair / lite variant seats**, not the 256k main seat | §4 links |
| Qwen3-Coder-Next (Feb 2026) | 80B (3B), 256K | Q4_K_M ≈ 45–48 GiB — fits alone, heavy beside the 5.4 GiB resident router; Unsloth: ">45 GB for 4-bit", 2-bit XL ≥ 30 GB | GGUF: `unsloth/Qwen3-Coder-Next-GGUF` (Dynamic 2.0, updated this week); MLX builds exist | Apache 2.0 | ~70% SWE-bench class claims; **the operator retired its uncensored twin and its pins on 2026-10-22** (seats moved to Huihui-Qwen3.6-27B MLX) — re-adding is a reversal, not a refresh | <https://huggingface.co/unsloth/Qwen3-Coder-Next-GGUF> · <https://unsloth.ai/docs/models/qwen3-coder-next> · <https://modelfit.io/quant-compare/qwen3-next-80b-a3b/> · wiki unit `unit-model-catalog-hf-co-bartowski-huihui-ai-qwen3-coder-next-abliterated-gguf-q4-k-m` |
| Muse Glimmer 30B (2026-08-10) | 30B dense agentic | Q4 ~18–20 GiB | GGUF + MLX (§4) | Apache 2.0 | agentic-trained, but dense (~14-20 tok/s class on this host) — below the MoE seats for IDE loops | §4 links |
| Qwen3.8-27B (2026-08-13) | 27B dense, MTP head | in fleet | in fleet | Apache 2.0 | card: 73.0 vs 63.4 Terminal-Bench vs 3.6-27B; already the `heavy` variant + DFlash seat; §0.1 applies | <https://omidsaffari.com/blog/best-local-ai-models-for-coding> · backends.yaml omlx-coding |
| Laguna XS-2.1 (2026-07-02) | 33B (3B) | in fleet | in fleet | current generation of the seat | no 2.2 / successor found | <https://poolside.ai/blog/introducing-laguna-xs-2-1> |

**Proposal: KEEP Qwen3-Coder-30B-A3B (oMLX + GGUF pair intact).** No Qwen3.6/3.7-Coder exists
(<https://codersera.com/blog/qwen-3-5-complete-guide-2026/>); the seat is still the Mac-coding
default in independent 2026 write-ups. **One screen worth queueing:** Mellum 2.1 for the
`fast-repair` variant seat (replace-in-place: out ~21.4 GiB kat-coder GGUF, in ~7 GiB — net
−14 GiB if it wins its WFE). Qwen3-Coder-Next: watch only — re-adding it contradicts the
2026-10-22 operator prune and its Q4 footprint (≈ 45 GiB + router + KV) leaves no co-residency
headroom.

---

## 7. vision  (auto-vision)

| | Model | Engine / tag | Size | Since |
|---|---|---|---|---|
| **Seat** | Qwen3-VL-32B **Thinking** | Ollama `qwen3-vl:32b-ctx8k` | ~20 GiB | seat pre-dates 2026-10-16 (thinking-card wiring fix `80afba12`) |
| oMLX twin | — none: oMLX's vision path is non-functional (backends.yaml omlx notes); the MLX conversion in `omlx-local` is eval-only | — | — | — |

Candidates:

| Candidate | Params (active) | Quant for 64 GiB | MLX / GGUF | License | Vision evidence | Evidence |
|---|---|---|---|---|---|---|
| **Qwen3-VL-30B-A3B-Thinking** | 30B (3B) MoE | Q4 ~17–18 GiB (unsloth UD) | GGUF: `unsloth/Qwen3-VL-30B-A3B-Thinking-GGUF` (+ a 1M-ctx variant), official `Qwen/Qwen3-VL-30B-A3B-Thinking-GGUF` · MLX 4bit/3bit in mlx-community/lmstudio-community (irrelevant here: seat is Ollama-side) | Apache 2.0 | ~2× faster than the 32B dense seat; community head-to-heads still give the 32B the vision+text quality edge (within-family tradeoff: speed vs quality) | <https://huggingface.co/unsloth/Qwen3-VL-30B-A3B-Thinking-GGUF> · <https://huggingface.co/Qwen/Qwen3-VL-30B-A3B-Thinking-GGUF> · <https://huggingface.co/mlx-community/Qwen3-VL-30B-A3B-Instruct-4bit> · <https://www.reddit.com/r/LocalLLaMA/comments/1omr9rc/> · <https://bestllmfor.com/best/vision/> |
| NVIDIA Nemotron 3 Nano Omni 30B-A3B | 30B (3B) omni: image+video+audio+text | Q4 ≈ 25 GiB class | GGUF: `unsloth/NVIDIA-Nemotron-3-Nano-Omni-30B-A3B-Reasoning-GGUF` (2026-09-21) | NVIDIA open license | tops doc-intelligence / video / audio leaderboards; "perception sub-agent" positioning | <https://huggingface.co/unsloth/NVIDIA-Nemotron-3-Nano-Omni-30B-A3B-Reasoning-GGUF> · <https://www.buildfastwithai.com/blogs/nvidia-nemotron-3-nano-omni-2026> |
| Gemma 4 31B / 26B-A4B (vision-capable) | in fleet (variants) | in fleet | in fleet | Gemma terms | the fleet's `gemma_vision`/JANG variants already cover the fallback path | backends.yaml vision group |

**Proposal: KEEP qwen3-vl:32b Thinking.** The lane is single-image, 8k, latency-tolerant — the
quality edge beats the 2× speedup, and the swap (out ~20 GiB, in ~17.5 GiB) saves only ~2.5 GiB.
Queue the 30B-A3B-Thinking as the pre-registered replacement if vision fan-out throughput ever
becomes a requirement. Nemotron Omni is an **omni-expansion watch** (would add video/audio input
the role doesn't have today) — out of scope for replace-in-place.

---

## 8. Disk budget summary (proposals only; nothing executed)

| Action | GB in | GB out | Net |
|---|---|---|---|
| LFM2.5-24B-A2B replaces Qwen3.6-35B-A3B (if screen wins; covers general-fast + tools-specialist default) | ~27 (GGUF Q4 + MLX 4bit) | ~41.6 (UD GGUF + UD-MLX) | **−14.6** |
| Mellum 2.1 replaces kat-coder fast-repair variant (if WFE wins) | ~7 | ~21.4 | **−14.4** |
| Gemma-4-26b checkpoint refresh re-pull (in place, verify-sha) | ~16 | ~16 (after) | 0 |
| K2-Horizon MoVA oMLX twin (optional, grows fleet — operator call) | ~20 | 0 | +20 |
| Everything else | — | — | 0 |

Worst case (all optional items declined): **net −0 GiB, zero seat changes**. Base case (screens
pass): **≈ −29 GiB** against 466 GiB free. No proposal in this doc grows the fleet except the
explicitly-flagged K2 oMLX twin, which needs an operator slot decision either way.

## 9. Suggested screen queue (cheapest first, one bench at a time)

1. **LFM2.5-24B-A2B** — seat screen on auto-daily `fast` + tools-specialist (answers always-think
   + tool-loop questions for two roles at once). Delete loser either way.
2. **Mellum 2.1** — WFE on the coding `fast-repair` lane. Delete loser either way.
3. **Gemma-4-26b sha check + optional refresh re-pull** (maintenance, not a bench).
4. Deferred/operator-call: K2 MoVA oMLX twin; Muse Glimmer tools slot; Qwen3-VL-30B-A3B swap on
   fan-out demand.

## 10. Provenance & method

- Seat map read from `config/portal.yaml` (21 workspaces + variants), `config/backends.yaml`
  (groups, aliases, keep_reasons), `config/MODEL_CATALOG.md` units, and git history
  (`19fc3ccc` reasoning seat 2026-10-19; `80afba12` vision thinking wiring 2026-10-16;
  `6501e6c5` coding 256k; router tag 2026-10-06).
- Prior decisions respected: `docs/MODEL_FLEET_CLOSEOUT_20260906.CLOSEOUT.md` (gpt-oss, granite
  4.2, kat-coder, Coder-Next-abliterated 2026-10-22 prune), operator decisions 2026-10-28 in
  `coding_task/RESUME_20261030.md` (gemma dual-build hold, seated models need A/B).
- External claims carry inline links; vendor-run benchmarks are labeled as such where they are
  the only evidence. Two independent sources were required for the surprising finding (§0.1).
- Date-stamp note: the file name carries the brief's lane stamp (20261029); survey executed
  2026-10-28 evening.
