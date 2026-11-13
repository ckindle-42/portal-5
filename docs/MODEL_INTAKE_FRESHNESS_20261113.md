# Model Intake Freshness — 2026-11-13 delta

Research-only delta from [`MODEL_INTAKE_FRESHNESS_20261111.md`](MODEL_INTAKE_FRESHNESS_20261111.md).
The baseline remains authoritative for earlier release history, role fit, and the existing
screen evidence. No weights were downloaded, no local model tags were inspected or changed,
no config was edited, and no Portal service was called.

**Method.** Compared Hugging Face model metadata (`createdAt`, `lastModified`, latest commit
subjects, license field, and file-tree sizes) for the baseline's named vendor and community
repos and newest-first org feeds, then checked dated vendor announcement pages for 2026-11-06
through 2026-11-13. The feeds covered the baseline's vendor/model orgs plus `bartowski`,
`mlx-community`, `lmstudio-community`, and `mradermacher`; commit subjects were inspected
before treating a `lastModified` bump as a checkpoint update. Sizes below are repository file
sizes as returned by HF (decimal GB); they are not claims about runtime memory. No model
weights were fetched. An empty result in an org feed is not treated as proof that a model was
withdrawn. The session had no wiki search/get tool, so this delta uses primary vendor pages
and HF API metadata rather than wiki fact units.

**Status vocabulary.** `unchanged` means no qualifying source, weight, quant, card, or license
change was found after the 11-11 baseline. `superseded` names a newer same-family release;
it does not imply that the successor fits the seat. `newly relevant` means a post-baseline
release/build or a release in the seven-day news window merits a role-specific review. No
withdrawal was found among the baseline candidates.

## Changes and new items

| Status | Item and dated evidence | Size / license / evidence limit |
|---|---|---|
| **superseded (family generation)** | [Nex-N2.6](https://huggingface.co/nex-agi/Nex-N2.6), created 2026-11-10, is newer than Nex-N2.5-mini. | Official model is 321B, Apache-2.0, FP8; [bartowski/Nex-N2.6-GGUF](https://huggingface.co/bartowski/Nex-N2.6-GGUF) Q4_K_M files total **200.83 GB** (six shards). It cannot fit the ≤40 GB Q4 intake envelope. It does not replace the reopened N2.5-mini screen. Vendor agentic results are vendor-run; no independent result checked. |
| **newly relevant (format update)** | [Dory1.0-4B MLX 8-bit](https://huggingface.co/mlx-community/NVIDIA-Nemotron-Labs-Dory1.0-4B-MLX-8bit), created 2026-11-12; new format option since baseline. | `model.safetensors` **4.22 GB**. [Official NVFP4](https://huggingface.co/nvidia/NVIDIA-Nemotron-Labs-Dory1.0-4B-NVFP4) (**3.20 GB**) and [MXFP8](https://huggingface.co/nvidia/NVIDIA-Nemotron-Labs-Dory1.0-4B-MXFP8) (**4.75 GB**) repos were modified 2026-11-13; latest commits update response-template/generation-tag metadata, not weights. NVIDIA card states Open Model License; HF API license field is `other`. No engine or tool-call proof; vendor material only. |
| **newly relevant (quant update)** | [Unsloth Qwen3.8-27B GGUF](https://huggingface.co/unsloth/Qwen3.8-27B-GGUF) updated 2026-11-12; commit adds UD3.1 `UD-Q3_K_XL`. | New file **13,146,393,504 bytes (13.15 GB)**. Existing Q4_K_M remains **16.56 GB**. This is a quant addition, not a refreshed base checkpoint or a fix for the phone-home finding. |
| **newly relevant (format update)** | [IBM Granite 4.1 LLMON announcement](https://huggingface.co/blog/ibm-granite/llmon-an-llm-native-markup-language-now-in-granite), dated 2026-11-12; preview repos [granite-4.1-3b-llmon-preview](https://huggingface.co/ibm-granite/granite-4.1-3b-llmon-preview) and [granite-4.1-8b-llmon-preview](https://huggingface.co/ibm-granite/granite-4.1-8b-llmon-preview). | BF16 weights **7.33 GB** and **17.59 GB**, respectively; Apache-2.0. Both fit even before quantization. LLMON is an experimental instruction-serialization format; any learned privilege rule is not an enforcement guarantee. No standalone quant, live-stack support, or independent benchmark was verified. Watch only. |
| **newly relevant (decision model)** | [InclusionAI SingVL-S1-4B](https://huggingface.co/inclusionAI/SingVL_S1_4B), released 2026-11-11; official [GGUF repo](https://huggingface.co/inclusionAI/SingVL_S1_4B_GGUF) created 2026-11-12. | Base BF16 files total **9.08 GB**; official GGUF Q4_K_M **2,708,804,128 bytes (2.71 GB)**. HF license field is empty. This is a vision-language decision model, not a general vision chat replacement. No independent benchmark or runtime support verified; watch only. |
| **newly relevant (tool-action model)** | [Tether/QVAC BotPsy announcement](https://tether.io/news/tethers-800m-ai-agent-beats-models-2-5x-its-size-on-everyday-phone-tasks/) and [technical post](https://qvac.tether.io/blog/on-device-ai-agent-botpsy), released 2026-11-11; repos [qvac/BotPsy-0.8B](https://huggingface.co/qvac/BotPsy-0.8B) and [qvac/BotPsy-0.8B-GGUFs](https://huggingface.co/qvac/BotPsy-0.8B-GGUFs). | 0.853B parameters; Apache-2.0; official GGUF Q4_K_M imatrix file **529,296,960 bytes (0.53 GB)**. Vendor reports six tool-action benchmarks; results are vendor-run, with no independent result found. Candidate for tools-specialist-fast only; no Portal compatibility proven. |
| **newly relevant (regional instruct model)** | Bielik's [2026-11-10 release schedule](https://www.bielik.ai/en/blog/launching-bielik-11b-v31-dflash-and-the-bielik-one-family) announced Bielik-11B-v3.1 on Nov 10 and Bielik-One decision models Nov 12. | [speakleash/Bielik-11B-v3.1-Instruct](https://huggingface.co/speakleash/Bielik-11B-v3.1-Instruct) is Apache-2.0, 11B; official [GGUF Q4_K_M](https://huggingface.co/speakleash/Bielik-11B-v3.1-Instruct-GGUF) **6.72 GB**, [MLX 4-bit](https://huggingface.co/speakleash/Bielik-11B-v3.1-Instruct-MLX-4bit) **about 6.98 GB**. Polish/EU language emphasis makes it watch-only absent a matching role. Bielik-One's [4B](https://huggingface.co/speakleash/Bielik-One-4B-r1) and [11B-v3.1](https://huggingface.co/speakleash/Bielik-One-11B-v3.1-r1) are specialized decision models, not drop-in chat assistants. Bench claims are vendor-run. |
| **newly relevant (specialized decision model)** | [Perplexity Decider v1.3 announcement](https://www.perplexity.ai/en-GB/hub/blog/perplexity-decider), dated 2026-11-12; HF cards [pplx-decider-v1.3](https://huggingface.co/perplexity-ai/pplx-decider-v1.3) and [pplx-decider-flash-v1.3](https://huggingface.co/perplexity-ai/pplx-decider-flash-v1.3). | Apache-2.0; 26B and 4.54B. BF16 repository weights total **54.07 GB** and **9.63 GB**, respectively. Flash fits; these return typed decisions/classifications rather than general assistant text. Vendor blog reports 91.6% on 63 classifications for full and 72.77% for Flash; vendor-run only. Watch; no current decision-model role is wired. |
| **newly relevant (excluded: no measured fit)** | [MetaEncoder v1](https://huggingface.co/facebook/meta-encoder-v1) created 2026-11-12. | 28.4B feature-extraction encoder; BF16 files **56.98 GB**, no HF license field, no official quant found. A 4-bit size estimate is not a measured artifact. Encoder/retrieval use does not fit an assistant screen; no queue slot. |
| **newly relevant (excluded: no fit)** | [Thinking Machines Inkling-2-Small](https://huggingface.co/thinkingmachines/Inkling-2-Small) weights made public 2026-11-12. | 276B total / 12B active; Apache-2.0. NVFP4 files total **390.06 GB**. Active parameter count does not change the weight-fit result. |
| **newly relevant (API-only / no fit)** | [Gemini Decisions API](https://blog.google/innovation-and-ai/technology/developers-tools/gemini-decisions-api/) and [Qwen4-Max Preview](https://docs.qwencloud.com/developer-guides/getting-started/latest-model) announced 2026-11-11; [ERNIE Light Deep Thinking](https://www.prnewswire.com/news-releases/baidu-unveils-latest-ernie-models-amid-broader-full-stack-ai-lineup-and-debuts-token-exchange-to-power-intelligent-organizations-302937959.html) announced 2026-11-12. | Gemini Decisions, Qwen4-Max Preview, and ERNIE Light Deep Thinking are API/application models with no available local checkpoint identified in this scan; Baidu says ERNIE Light weights are expected by 2026-11-25. [ERNIE 5.5 Flash Base](https://ernie.baidu.com/) is open-weight but 280B / 14B active; no fit-sized official quant found (Q4 estimate is over 40 GB). |

### Baseline-family / candidate status

| Baseline entry | Status at 2026-11-13 |
|---|---|
| Gemma 4 E4B/E2B, 26B-A4B-it and QAT; Gemma 4 OBLITERATED router variant | **unchanged** since baseline: the 2026-11-03 E4B/E2B tokenizer remediation predates it; no new weight update found. OBLITERATED rebuild remains a maintenance question. |
| Small uncensored challengers: `mradermacher/Qwen3.5-4B-heretic-v1-GGUF`, Nemotron Bolt E4B Heretic, `SC117/Spark-X2.6-4B-abliterated-FIT-GGUF`, `FrostWolfAI/Spark-X2.6-4B-abliterated-GGUF`, `mradermacher/ZwZ2-4B-Surgical-Abliterated-GGUF`, Frost-Cyber-Mini-Uncensored v1.1 | **unchanged** from their baseline entries; no new weight/quant or evidence warrants a seat change. |
| Qwen3.6-35B-A3B, Qwen3.6 variants, Qwen3.8-27B base/oMLX, Huihui Qwen3.6/Qwen3.8 derivatives | **unchanged** in base weights; Qwen3.8 UD3.1 quant addition above is not a checkpoint successor. The Qwen3.8 phone-home concern remains open. |
| K2-Horizon MoVA; Jais 3; Qwen3-VL; Laguna XS-2.1 / Laguna-S-2.1; KAT-Coder V2.5-Dev | **unchanged**; no successor or withdrawal found in the checked source window. |
| VulnLLM-R-7B; `Cyber-Ornith-1.5-9B-OBLITERATED`; BaronLLM; HauhauCS; GLM-5.3 / V4.1-Flash-1017 derivatives | **unchanged** from baseline; no new fit-sized checkpoint or license/withdrawal change found. |
| GLM-Z1, GLM-4.7-Flash, Magistral-Small-2509; DeepSeek families; Mistral Small 3.2 | **unchanged**; no qualifying ≤40 GB local successor found. |
| Granite 4.1 base and Switch-4.1 (including GGUFs) | Base/Switch weights **unchanged**; Switch-4.1 8B GGUF's 2026-11-12 bump was signature files only. LLMON previews are a separate experimental addition above. |
| Muse; Kolibri-1; gpt-oss; Hermes 4.3-36B; Devstral-Small-2; Foundation-Sec-8B-Reasoning; AgentWorld; phi4-mini-reasoning; Tongyi-DeepResearch | **unchanged**; no qualifying release, quant, license change, or withdrawal found in the scanned feeds. |
| LFM3-1.7B (vendor GGUF and MLX); OrcaCyber-Nano-1.0; North-Mini-Code; Omnicoder2; Nemotron 3.5 Lightning | **unchanged**; no new Unsloth LFM3 GGUF or in-window successor found. |
| XHToken Spark-X2.6-4B / 1.7B; Spark-X2.6 abliterated variants; EmbeddingGemma 2 | **unchanged**; no new weight fit or role-changing update found. EmbeddingGemma remains an embedder rather than a chat-seat candidate. |
| Gemma 4 12B audio seat; Granite 4.1 8B media seats; LFM2.5-8B-A1B and Gaston uncensored derivative | **unchanged**; no qualifying weight, quant, license, or availability change found. |
| Ornith-1.0/1.5; Mistral Large 4; Kimi-K3.1-Pro; MiniMax-M3.1-Flash / H3-Image; Nemotron 74B-A9B / Super-VL | **unchanged** or **no fit** as in baseline; no new fit-sized local quant changes. Existing empty-org provenance risks remain; no local tags were touched. |
| Clover-35B-A3B-Preview; Spectre-37B-v1; LiquidCode-2.5-24B-A2B; Qwen3.8-40B-Ultimate-Heretic; Coder390; Spark-X2.6 abliterated; ZwZ2; ZoomGain; LBS-27B; Ling-3.0-tiny-UBTree | **unchanged** as previously known watch entries unless listed below; no evidence promotes an existing watch item into the queue. |
| Arete-27B; Mellum 2.1; Flint; LiquidAI LFM2.5-24B-A2B; Nemotron 3.5 Bolt E4B | **unchanged** since the 11-11 baseline. No new weight/checkpoint, quant, card, or license change found. All five existing queue decisions stand. |

## Newly observed community builds (watch, not promotion)

| Repo / date | Exact artifact size | Status and limit |
|---|---:|---|
| [mradermacher/gemma-4-26B-A4B-agentic-GGUF](https://huggingface.co/mradermacher/gemma-4-26B-A4B-agentic-GGUF), created 2026-11-13 | Q4_K_M **16.80 GB** | **newly relevant watch**: community agentic fine-tune; Apache-2.0 as listed/inherited by the repo; no independent benchmark or live conformance evidence. |
| [xtools-at/Qwensploit-V2-27B-CyberSecurity-Qwen3.8-GGUF](https://huggingface.co/xtools-at/Qwensploit-V2-27B-CyberSecurity-Qwen3.8-GGUF), created 2026-11-11; source [fine-tune card](https://huggingface.co/xtools-at/Qwensploit-V2-27B-CyberSecurity-Qwen3.8) | Q4_K_M **16.81 GB** | **newly relevant watch**: community cybersecurity derivative, source license field `other`; no independent results or pipeline evidence. |
| [mradermacher/diffusion-lfm2.5-24b-a2b-blocktune-GGUF](https://huggingface.co/mradermacher/diffusion-lfm2.5-24b-a2b-blocktune-GGUF), created 2026-11-11; source [summerAIO/diffusion-lfm2.5-24b-a2b-blocktune](https://huggingface.co/summerAIO/diffusion-lfm2.5-24b-a2b-blocktune) | Q4_K_M **14.53 GB** | **newly relevant watch**: experimental block-masked diffusion fine-tune; source says it is not official LiquidAI and lists license `other`. Separate from the queued native LFM2.5 candidate; runtime path unproven. |
| [bartowski/Danielbrdz_Barcenas-LFM3-1.7B-GGUF](https://huggingface.co/bartowski/Danielbrdz_Barcenas-LFM3-1.7B-GGUF), created 2026-11-12 | Q4_K_M **1.12 GB** | **newly relevant watch**: community fine-tune quant; no evidence to replace or promote over the existing LFM3-1.7B queue item. |

## Seven-day scan exclusions

These were found, but do not justify a seat screen: MetaEncoder has no measured official quant
and is an encoder; Inkling-2-Small exceeds the fit limit despite 12B active weights; Gemini
Decisions is API-only; Bielik/Bielik-One is language- or typed-decision-specific; SingVL and
Perplexity Decider are specialized decision models without an installed decision role. The
named community derivatives above lack independent or live evidence. New model cards and
vendor benchmark reports are not independent benchmark results.

## Source coverage notes

The no-change review included baseline entries from the official/org feeds named in the
11-11 report plus `bartowski`, `mlx-community`, `lmstudio-community`, and `mradermacher`.
The main dated new sources are linked in the tables above. In particular, no new official
Arete, Mellum, Flint, LFM2.5, Bolt E4B, Laguna, KAT-Coder, Jais, Qwen3-VL, or Dory GGUF weight
checkpoint was found; Dory's new MLX and metadata-only official format updates are listed
separately. No baseline candidate was observed as withdrawn, and no new license change was
identified in the HF metadata/commit checks. These are source-scan findings, not guarantees
that an upstream repository cannot change after this report.

## Updated proposed screen queue

One bench at a time; keep the previous replacement-in-place and loser-deletion rules. Queue
order reflects the 11-11 proposed screen order, not the separate `intake_s8/queue.yaml` order.

1. **Nex-N2.5-mini — still stands; operator reopened 2026-11-13.** The 2026-10-22 retirement
   in `config/MODEL_CATALOG.md` predates the current harness/verification and is superseded by
   the operator's explicit reopen. Check the newer family member first: `nex-agi/Nex-N2.6`
   (2026-11-10), but its Q4_K_M community build is **200.83 GB**, so it cannot fill this seat.
   Keep the proposed candidate `nex-agi/Nex-N2.5-mini`; GGUF
   `bartowski/nex-agi_Nex-N2.5-mini-GGUF:Q4_K_M` (**22.32 GB**) and MLX
   `mlx-community/Nex-N2.5-mini-OptiQ-4bit` remain the role-fit pair. The local tag
   `hf.co/bartowski/nex-agi_Nex-N2.5-mini-GGUF:Q4_K_M` stays on disk. Vendor-run agentic
   evidence only; rescreen must use current harness and live tasks.
2. **Arete-27B — still stands.** `NousResearch/Arete-27B`; GGUF
   `bartowski/NousResearch_Arete-27B-GGUF:Q4_K_M` (**17.20 GB**); MLX
   `mlx-community/Arete-27B-OptiQ-4bit`. No delta to the baseline's vendor-run Propaganda
   Eval claims; refusal behavior and tool-call JSON remain live unknowns.
3. **Mellum 2.1 — still stands.** GGUF
   `JetBrains/Mellum2.1-12B-A2.5B-Thinking-GGUF:Q4_K_M` (**8.07 GB**); MLX
   `mlx-community/Mellum2.1-12B-A2.5B-Thinking-6bit`; MTP
   `JetBrains/Mellum2.1-12B-A2.5B-Thinking-MTP`. No successor or new variant found.
4. **Flint — still stands.** `RecursiveSI/flint`; GGUF
   `unsloth/flint-GGUF:UD-Q4_K_XL` (**25.05 GB**); MLX `mlx-community/flint-oQ4e`
   (**23.35 GB**). No new checkpoint or quant found; vendor-run benchmarks only.
5. **LFM2.5-24B-A2B — still stands.** `LiquidAI/LFM2.5-24B-A2B`; GGUF
   `unsloth/LFM2.5-24B-A2B-GGUF:UD-Q4_K_XL` (**14.88 GB**); MLX
   `LiquidAI/LFM2.5-24B-A2B-MLX-4bit` (**13.56 GB**). The new BlockTune diffusion derivative
   is a separate watch item, not a replacement for this screen.
6. **Nemotron 3.5 Bolt E4B — still stands as fallback only.** Run if item 5 does not win,
   matching the original condition. GGUF
   `unsloth/NVIDIA-Nemotron-3.5-Bolt-E4B-GGUF:UD-Q4_K_XL` (**5.06 GB**); MLX
   `mlx-community/NVIDIA-Nemotron-3.5-Bolt-E4B-OptiQ-4bit`. No new checkpoint found.
7. **Dory1.0-4B — still stands, probe-gated.** Existing GGUF
   `nvidia/NVIDIA-Nemotron-Labs-Dory1.0-4B-GGUF:Q5_K_M` (**3.67 GB**). New MLX 8-bit
   **4.22 GB** is an additional format option, but neither that repo nor the official NVFP4 /
   MXFP8 update proves this stack can load the architecture or make nested tool calls. Keep
   the live engine/tool-call probe as a prerequisite to any bench.
8. **BotPsy-0.8B — newly relevant optional tools-specialist-fast challenger, after items 1–7.**
   `qvac/BotPsy-0.8B`; GGUF `qvac/BotPsy-0.8B-GGUFs` Q4_K_M (**0.53 GB**), Apache-2.0.
   Promote to an actual bench only if the operator names that seat decision and a live
   compatibility preflight passes. Evidence is vendor-run; tool-action quality is unproven
   on Portal.

No new candidate is promoted based on model-card benchmark claims alone. All queue outcomes
remain hypotheses until the orchestrator's authorized live screen and seat decision.
