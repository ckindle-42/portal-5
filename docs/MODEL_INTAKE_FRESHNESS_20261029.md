# Model Intake Freshness — 2026-10-29

Re-check of `docs/MODEL_LANDSCAPE_REFRESH_20261029.md` (survey executed 2026-10-28 evening)
against vendor orgs, Unsloth, mlx-community, and lmstudio-community as of **2026-10-28**.
Research only: no downloads, no config edits, no seat changes. Same rules as the landscape:
1 oMLX + 1 GGUF per role, replace in place, Unsloth authoritative for GGUF where a repo
exists, no bf16, and a quant has to fit a 64 GiB M4 Pro **beside** the resident router
(`gemma-4-E4B-it-OBLITERATED` ≈ 5.4 GiB; practical seat budget ≈ 50 GiB weights + KV).

**Status words:** `current` = the landscape's named checkpoint is still the newest that
matters for that role. `superseded` = a newer same-job checkpoint exists (named).
`newly relevant` = a model the landscape did not queue, and it can fit this machine.
Vendor-run scores are marked. Two sources were required for the claims that change the queue
(LFM3 does not replace LFM2.5-24B; Flint fits at Q4; Mistral Large 4 weights are not up).

---

## What changed since the landscape

1. **LFM3 shipped 2026-10-27 and is a different size class from LFM2.5-24B-A2B.** Six ~2B
   models on one backbone, 256K on the text model. It does not supersede the 24B screen.
   Liquid's own card says the 1.7B text model is not for agentic coding or complex multi-step
   reasoning. It is a cheap challenger to the Gemma 4 E4B **fast** variant only.
2. **Recursive Flint (2026-10-21) is the coding-seat miss.** 39.8B / ~2.5B active, Apache 2.0,
   Unsloth UD-Q4_K_XL at 25.05 GB and `mlx-community/flint-oQ4e` at 23.35 GB. Both fit beside
   the router. The landscape's coding section does not name it.
3. **NVIDIA Nemotron 3.5 Bolt** added two local sizes the landscape's Nemotron row does not
   name: Bolt 74B-A9B (2026-10-15, vision) and Bolt E4B (2026-10-23, text, Gemma 4 E4B
   post-train, 64K). Super VL 120B-A12B does not fit.
4. **Aleph Alpha Kolibri-1 (2026-10-03)** fits only below Q4. Q4_K_M is 49.76 GB before the
   router. No Unsloth GGUF and no mlx-community build.
5. **Mistral Large 4 weights are not on Hugging Face.** Mistral's 2026-10-06 post still says
   end of the month; a 2026-10-27 fetch of the HF placeholder still showed an upcoming release
   (countdown toward 2026-10-31). At 1.05T it would not fit anyway.
6. **No new Qwen text generation, no Gemma release after the 2026-07-20 checkpoint touch,
   no Mellum 2.2, no Laguna 2.2, no K2-Horizon successor, no Qwen3-VL successor.**

---

## Per-family table

Dates are Hugging Face `createdAt` (UTC) unless a vendor post is the release clock. "Newest"
is the newest **same-family** checkpoint that could matter, not every community quant.

| Family / role | Landscape entry | Newest as of 2026-10-28 | Date | Status |
|---|---|---|---|---|
| router-uncensored | Gemma 4 E4B-it OBLITERATED, Q4_K_M-ctx2k (tag 2026-10-06) | Same seat. Newest *small abliteration* is `mradermacher/Nemotron-3.5-Bolt-E4B-Heretic-GGUF` | Heretic repo 2026-10-27; Gemma 4 E4B weights last touched 2026-07-20 | **current.** Heretic is newly available and has no JSON-discipline evidence. Do not re-seat. |
| Gemma 4 | E4B / 26B-A4B / 31B, July refresh | `google/gemma-4-E4B-it`, `google/gemma-4-26B-A4B-it`, `google/gemma-4-12B-it` | created 2026-03 / 2026-05; `lastModified` 2026-07-20 on all three | **current.** No Gemma 5. 12B-it exists (May, refreshed July) and was outside the landscape size list; it is not newer than the seated 26B-A4B. |
| reasoning / K2-Horizon | `IFM/K2-Horizon-MoVA-36B-A4B` (fleet GGUF) | Same checkpoint. Newest IFM *adaptation* is Jais 3 (below), not a new K2 | K2 press 2026-09-03; HF `IFM/K2-Horizon-MoVA-36B-A4B` created 2026-09-01, modified 2026-10-14 | **current.** Fork-GGUF note in the landscape still stands. |
| Jais 3 | not named | `inception42/Jais-3-MoVA-36B-A4B` (HF id returned for the IFM base); GGUF `IFM/Jais-3-MoVA-36B-A4B-GGUF`; MLX `IFM/Jais-3-MoVA-36B-A4B-MLX-4bit` | weights 2026-09-29; GGUF 2026-10-12; announcement 2026-10-15 | **newly relevant for Arabic only.** Built on the K2 Horizon checkpoint. Does not supersede the English reasoning seat. |
| Qwen3.6 | `unsloth/Qwen3.6-35B-A3B` seated | No Qwen3.6/3.7-Coder and no newer 35B-A3B base | seat dates in the landscape stand | **current.** |
| Qwen3.8 | `Qwen/Qwen3.8-27B` (and 2.4T-A95B, Flash-Next) | `Qwen/Qwen3.8-27B` created 2026-08-05; `Qwen/Qwen3.8-Flash-Next` 2026-08-24. No Qwen3.9. `stealth-model/Qwen4` is not an Alibaba release | 2026-08 | **current.** No refreshed checkpoint that would clear the phone-home finding. 2.4T still does not fit. |
| Qwen3-VL | `qwen3-vl:32b` Thinking seat; 30B-A3B-Thinking as the speed alternate | `Qwen/Qwen3-VL-32B-Thinking` (2025-10-19); `Qwen/Qwen3-VL-30B-A3B-Thinking` (2025-09-30); Unsloth 30B GGUF 2025-10-30 | 2025 | **current.** Qwen3.8-27B is the newer multimodal *text* model and is already in fleet. |
| LFM | screen `LiquidAI/LFM2.5-24B-A2B` (2026-10-13 post; HF created 2026-10-12) | **24B class unchanged:** `LiquidAI/LFM2.5-24B-A2B`. **New family:** `LiquidAI/LFM3-1.7B` plus VL/Audio/Omni/d1 (table below) | LFM3 text repo created 2026-10-23, blog 2026-10-27 | **24B entry current. LFM3 newly relevant, not a successor.** No `LFM3-24B` repo. |
| Mellum | `JetBrains/Mellum2.1-12B-A2.5B-Thinking` (base 2026-09-20, GGUF 2026-10-07) | Same. GGUF repo modified 2026-10-22. Community MLX `alvinfn/Mellum2.1-12B-A2.5B-Thinking-MLX` (2026-10-18) | 2026-10-07 official GGUF | **current.** No 2.2. No `mlx-community` 2.1 build. Official Q4_K_M file is **8.07 GB** (MXFP4_MOE is 7.03 GB; the landscape's ~7 GiB matches MXFP4, not Q4_K_M). |
| KAT | kat-coder fast-repair variant (~21.4 GiB out) | Open weights still `Kwaipilot/KAT-Coder-V2.5-Dev` (34.7B, Apache 2.0). GGUF `bartowski/Kwaipilot_KAT-Coder-V2.5-Dev-GGUF` | repo created 2026-07-23, card touched 2026-07-28 | **current.** KAT-Coder-Pro V2.5 is the StreamLake API, not a new open checkpoint. |
| Mistral | Small 4 119B-2603, no fit | Small 4 unchanged (`mistralai/Mistral-Small-4-119B-2603`, 2026-01-23). Large 4 is API preview only | preview post 2026-10-06; weights still absent 2026-10-27 | **current** on fit. Large 4 is not seated material at 1.05T / ~49B active. |
| GLM | 5.x Flash, no fit | `zai-org/GLM-5.3` and `zai-org/GLM-5.3-Flash` | both created 2026-08-25 | **current.** No September/October GLM text release on `zai-org`. |
| DeepSeek | V4-Pro / V4.1-Flash, no fit | `deepseek-ai/DeepSeek-V4.1-Flash-1017` (763B safetensors total) supersedes the Sept V4.1-Flash checkpoint | 2026-10-17 | **checkpoint superseded by 1017; fit conclusion current.** Still no 64 GiB quant. |
| Granite | 4.2 30B, closeout stop | Newer *package*: `ibm-granite/granite-switch-4.1-30b` (30.0B, Apache 2.0) plus `-8b`, GGUF `-30b-GGUF` | Switch 2026-10-14; GGUF 2026-10-22. Base `granite-4.1-30b` is 2026-04-06 | **not a 4.2 successor.** Switch composes the older 4.1 base with decision/Guardian adapters and a speech encoder. Closeout on 4.2 still holds. Do not re-queue. |
| Nemotron | 3.5 Lightning 30B-A3B in fleet; Nano Omni as vision watch | **Bolt E4B** `unsloth/NVIDIA-Nemotron-3.5-Bolt-E4B-GGUF` and **Bolt 74B-A9B** `unsloth/NVIDIA-Nemotron-3.5-Bolt-74B-A9B-GGUF`. Super VL Unsloth GGUF exists and does not fit | E4B release 2026-10-23 (Unsloth repo created that day); 74B Unsloth 2026-10-14; Super VL Unsloth 2026-10-14 | **Lightning row current. Bolt E4B and Bolt 74B newly relevant** (details below). |
| Muse | Glimmer 30B (2026-08-10); Spark Open no fit | `meta-models/Muse-Glimmer-30B` 2026-08-09; `meta-models/Muse-Spark-Open-816B-A42B` 2026-09-15 | unchanged | **current.** |
| Laguna | Laguna-XS-2.1 | `poolside/Laguna-XS-2.1` | created 2026-06-20, modified 2026-08-19 | **current.** No 2.2 repo. |
| Flint | not named | `RecursiveSI/flint` | HF created 2026-10-21 (announcement the same day) | **newly relevant.** Coding screen. |
| Kolibri | not named | `Aleph-Alpha/Kolibri-1` | HF created 2026-10-02; announcement 2026-10-03 | **newly relevant, tight fit.** Reasoning watch, not a K2 replacement. |
| Ling | not named | `inclusionAI/Ling-3.1-flash-1019` (572B) | 2026-10-27 | **no fit.** BenchLM's 2026-10-28 open-weight leader. Does not change a 64 GiB seat. |
| MiniMax | M2.1/M3, no fit | `MiniMaxAI/MiniMax-M3.1-Flash` (220B) | 2026-10-17 | **no fit.** Newer and still too big. |

---

## New entries (fit check)

### LFM3 — newly relevant, does not replace LFM2.5-24B-A2B

Blog 2026-10-27. Six branches from `LiquidAI/LFM3-1.7B-Base`. License **LFM Open License v1.0**
(commercial use free under $10M revenue; same threshold the landscape already accepted for
LFM2.5). No Unsloth GGUF as of this survey (`unsloth/LFM3-1.7B-GGUF` is absent). Use the
vendor GGUF until Unsloth publishes one.

| Repo | Params | Role | Quant that fits | Notes |
|---|---|---|---|---|
| `LiquidAI/LFM3-1.7B` | 1.73B text, 256K | small agent / tools-fast | GGUF `LiquidAI/LFM3-1.7B-GGUF` **QAD-Q4_0 1.05 GB** or Q4_K_M 1.10 GB; MLX `LiquidAI/LFM3-1.7B-MLX-4bit` **0.97 GB** | Also `mlx-community/LFM3-1.7B-OptiQ-4bit` (2026-10-28) and `lmstudio-community/LFM3-1.7B-GGUF` (2026-10-26). |
| `LiquidAI/LFM3-VL-2B` | 1.92B, 128K, image+video | not a vision-seat replacement | GGUF `LiquidAI/LFM3-VL-2B-GGUF`; MLX `LiquidAI/LFM3-VL-2B-MLX-4bit` | 2B vs the 32B Thinking seat. Watch only. |
| `LiquidAI/LFM3-Audio-2B` | ~2.00B | speech, not a fleet text role | vendor GGUF + MLX | Out of seat scope. |
| `LiquidAI/LFM3-Omni-2B` | ~2.17B | omni | vendor MLX/GGUF | Out of seat scope. |
| `LiquidAI/d1-2B` / `d1-Omni-2B` | same backbones | structured decisions | vendor GGUF + MLX | Not a chat seat. |

Template (from the 1.7B card): ChatML, **thinking on by default**; `enable_thinking=False` exists
and the card says it can be inconsistent. Tool calls are XML (`<tool_call><function=…>`), not
the OpenAI JSON shape. Card: tool calling and structured output yes; **not recommended for
agentic coding or complex multi-step reasoning.**

Benchmarks on the model card are **vendor-run**. Against Gemma 4 E4B (the tools-fast seat
family): LiveClaw 45.60 vs 20.36, BFCL V4 71.39 vs 48.25, AutomationBench 41.29 vs 1.92,
WebArena-Verified 38.42 vs 17.06. MCP-Atlas goes the other way (32.57 vs the card's Qwen3.5-9B
at 42.67; Gemma 4 E4B is 6.19 on that row). No independent score found.

**Queue effect:** keep the LFM2.5-24B-A2B screen for general-fast and the tools-specialist
default. Add LFM3-1.7B only as a screen against the Gemma 4 E4B fast variant.

Measured LFM2.5 sizes (landscape said ~13–14 GiB Q4 and ~27 GiB for the pair): Unsloth
`unsloth/LFM2.5-24B-A2B-GGUF` **UD-Q4_K_XL = 14.88 GB**; official MLX 4bit
`LiquidAI/LFM2.5-24B-A2B-MLX-4bit` = **13.56 GB**. Pair ≈ 28.4 GB.

### Flint — newly relevant, coding

| | |
|---|---|
| Repo | `RecursiveSI/flint` (2026-10-21) |
| Params | 39.8B total, ~2.5B active, 256K documented context, text only |
| Quant | **Unsloth `unsloth/flint-GGUF` UD-Q4_K_XL = 25.05 GB** (UD-Q3_K_XL 18.49 GB also fits). MLX **`mlx-community/flint-oQ4e` = 23.35 GB** (2026-10-27). Also `lmstudio-community/flint-GGUF` (2026-10-20). |
| License | Apache 2.0 |
| Template | Unsloth's run guide shows thinking controls. A secondary write-up says it reasons before every answer. Confirm `enable_thinking` on the shipped chat template during the screen. Multi-turn tool use is claimed. |
| Benchmarks | **Vendor / Unsloth table:** Terminal-Bench 2.1 54.9, SWE-bench Verified 74.2, SWE-bench Pro v2 89.7, LiveCodeBench v6 80.3, IFEval 95.1. Same table puts Qwen 3.6 at Terminal-Bench 44.9 and SWE-bench Verified 73.4, and Laguna XS 2.1 at Terminal-Bench 24.7. One independent local run (atomicagent, 2026-10-22, RTX 5090, not this host) reports 12/18 agent runs. Treat the leaderboard rows as vendor-run. |
| Disk if it replaces the coding pair | In ≈ 25.1 + 23.4 GB. Out ≈ 18 + 17 GB (Qwen3-Coder-30B-A3B GGUF + MLX). **Net ≈ +13 GB.** RAM at Q4 beside the router is ≈ 30 GB before KV, inside the seat budget. |

### Nemotron 3.5 Bolt E4B — newly relevant, tools-fast

| | |
|---|---|
| Release | 2026-10-23. NVIDIA research page and the Unsloth card. |
| Params | 8B total / 4B effective, Gemma 4 E4B architecture, **64K** context (half of Gemma 4 E4B's 128K), text in / text out |
| Quant | **Unsloth UD-Q4_K_XL = 5.06 GB** (`unsloth/NVIDIA-Nemotron-3.5-Bolt-E4B-GGUF`, created 2026-10-23). MLX `lmstudio-community/NVIDIA-Nemotron-3.5-Bolt-E4B-MLX-4bit` = **4.20 GB** (2026-10-20). DFlash drafter ships beside the GGUF. |
| License | OpenMDW-1.1 (Gemma 4 base remains Apache 2.0) |
| Template | Card: `enable_thinking` and `conversational_mode` chat-template flags. Multi-turn tool use. |
| Benchmarks | NVIDIA claims ~40% higher average quality vs their previous small agent and up to ~80% fewer output tokens. **Vendor-run.** No independent table found. |
| Why it is not the router | Safety-tuned Gemma derivative. The Heretic GGUF (2026-10-27) is uncensored-shaped and unproven on the router's JSON schema. |

### Nemotron 3.5 Bolt 74B-A9B — watch, vision/agent

Unsloth `unsloth/NVIDIA-Nemotron-3.5-Bolt-74B-A9B-GGUF` (2026-10-14). OpenMDW-1.1. Image/video
in, text out, 256K, 74B / 9B active, native low-bit story is ~24 GB. Measured Unsloth files:
**UD-Q4_K_XL directory = 50.22 GB** (over the ≈50 GiB seat budget once the 5.4 GiB router is
resident), **UD-Q3_K_XL = 39.03 GB** (fits), UD-IQ2_XXS = 22.02 GB. No mlx-community build
found in this pass. Do not queue ahead of the text seats until an MLX checkpoint exists.
Super VL (`unsloth/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-GGUF`, 2026-10-14) stays no-fit.

### Kolibri-1 — reasoning watch, Q4 does not fit beside the router

`Aleph-Alpha/Kolibri-1`, announcement 2026-10-03. 78.1B / 3.46B active, Apache 2.0, 1,048,576
context (vendor recommends ≤262,144), reasoning effort plus tool calling, German+English.
FP8 weights are ~78 GB. **No Unsloth GGUF. No mlx-community repo.** Bartowski
`bartowski/Kolibri-1-GGUF` (2026-10-18): **Q4_K_M = 49.76 GB** (does not fit beside the
router and KV), **Q3_K_M = 37.62 GB** (fits). Community MLX exists
(`velaia/Kolibri-1-MLX-4bit`, 2026-10-03) and is not an mlx-community build. Custom
`kolibri1` tool parser. Card benchmarks (GPQA Diamond 84.3, SWE-bench Verified 66.4,
LiveCodeBench v6 85.9) are **vendor-run**. Leave K2-Horizon seated.

---

## Revised s8-intake screen queue

One bench at a time. Replace in place. Delete the loser. Nothing here is a seat flip.

1. **LFM2.5-24B-A2B** — general-fast and the tools-specialist default. Still the right screen.
   Newest ids: `LiquidAI/LFM2.5-24B-A2B`, GGUF `unsloth/LFM2.5-24B-A2B-GGUF` **UD-Q4_K_XL**,
   MLX `LiquidAI/LFM2.5-24B-A2B-MLX-4bit`. Not superseded by LFM3.
2. **Flint** — coding pair (`Qwen3-Coder-30B-A3B` oMLX + GGUF). Newest ids:
   `RecursiveSI/flint`, GGUF `unsloth/flint-GGUF` **UD-Q4_K_XL**, MLX
   `mlx-community/flint-oQ4e`. Net disk ≈ +13 GB if it wins. Vendor benches only.
3. **Mellum 2.1** — coding fast-repair, unchanged job. Newest id:
   `JetBrains/Mellum2.1-12B-A2.5B-Thinking-GGUF` **Q4_K_M (8.07 GB)**. MLX is still not an
   mlx-community or JetBrains build; screen the official GGUF, and do not block on MLX.
4. **LFM3-1.7B** — tools-specialist **fast** variant only (Gemma 4 E4B QAT), after item 1
   so the always-think question is already answered on this stack. Newest ids:
   `LiquidAI/LFM3-1.7B`, GGUF `LiquidAI/LFM3-1.7B-GGUF` **QAD-Q4_0** (no Unsloth yet),
   MLX `LiquidAI/LFM3-1.7B-MLX-4bit`. XML tool calls and inconsistent think-off are the
   screen risks. Card itself rules it out of the coding seat and of the 35B general seat.
5. **Nemotron 3.5 Bolt E4B** — same fast variant, only if item 4 does not win it.
   Newest ids: Unsloth GGUF `unsloth/NVIDIA-Nemotron-3.5-Bolt-E4B-GGUF` **UD-Q4_K_XL**,
   MLX `lmstudio-community/NVIDIA-Nemotron-3.5-Bolt-E4B-MLX-4bit`. Context drops to 64K.
6. **Gemma 4 26B-A4B sha check** — maintenance, not a bench. No newer Google checkpoint
   since `lastModified` 2026-07-20.

Deferred, not queued: K2-Horizon oMLX twin; Muse Glimmer tools slot; Qwen3-VL-30B-A3B on
fan-out demand; Kolibri-1 until a Q3-or-better quant is acceptable **and** an mlx-community
(or official) MLX exists; Nemotron Bolt 74B-A9B until MLX exists (use UD-Q3_K_XL, not Q4);
Jais-3 unless an Arabic workload appears; Granite Switch 4.1 (closeout still holds);
Mistral Large 4, DeepSeek V4.1-Flash-1017, Ling-3.1-flash-1019, MiniMax-M3.1-Flash,
Nemotron Super VL, GLM-5.3 (none fit).

---

## Provenance

- Seat rules and the prior queue: `docs/MODEL_LANDSCAPE_REFRESH_20261029.md`,
  `coding_task/RESUME_20261030.md` (S8″ refresh-first, 1 oMLX + 1 GGUF, no bf16).
- Hugging Face model API `createdAt` / safetensors `total` / tree file sizes, 2026-10-28,
  for the repos named above. A missing repo returned HTTP 401 from this client; those ids
  are treated as absent, not as private mirrors.
- LFM3 card: <https://huggingface.co/LiquidAI/LFM3-1.7B> and
  <https://www.liquid.ai/blog/lfm3> (2026-10-27). MarkTechPost the same day.
- Flint: <https://huggingface.co/RecursiveSI/flint>, <https://huggingface.co/unsloth/flint-GGUF>,
  <https://unsloth.ai/docs/models/flint>, Richard Socher announcement 2026-10-21.
- Bolt E4B: NVIDIA research page dated 2026-10-23;
  <https://huggingface.co/unsloth/NVIDIA-Nemotron-3.5-Bolt-E4B-GGUF>.
- Kolibri: <https://huggingface.co/Aleph-Alpha/Kolibri-1>, Aleph Alpha post 2026-10-03,
  `bartowski/Kolibri-1-GGUF` file sizes.
- Mistral Large 4: <https://mistral.ai/news/mistral-large-4/> (2026-10-06, "weights drop end
  of this month") and the 2026-10-27 report that the HF placeholder still had no weights
  (<https://tech.yahoo.com/ai/meta-ai/articles/reported-date-arrived-weights-did-152932319.html>).
  Direct API lookup of `mistralai/Mistral-Large-4` on 2026-10-28 did not return a model.
- Jais 3: IFM post 2026-10-15 and <https://docs.ifm.ai> model list (adaptation of K2 Horizon).
- Granite Switch: <https://huggingface.co/blog/ibm-granite/granite-switch-4-1> (2026-10-15).
- DeepSeek 1017 and Ling-3.1-flash-1019 and MiniMax-M3.1-Flash: HF `createdAt` plus safetensors
  parameter totals (763B, 572B, 220B).
