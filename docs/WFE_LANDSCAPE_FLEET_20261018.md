# Open-weight landscape by lane — 2026-10-18

**Box:** Apple Silicon, 64 GB unified memory, ~56 GB usable by the GPU. Every candidate below is open-weight, has a published GGUF and/or MLX build (or an Ollama-native architecture), and is nominally ≤ ~35 GB at 4-bit **before** KV cache. One request at a time; several seats can be resident, so smaller is better.

**Method.** Eleven lanes. For each: the current seat from `config/portal.yaml`; the three strongest fitting open-weight models with a public number; and the cheapest local instrument that would settle the change. Numbers are tagged **independent** (run by a third party on its own harness) or **vendor-reported** (model card, vendor-run table, or a vendor's same-card multi-model table). Same-card tables are labelled "same-harness, vendor-run" and are the only cross-model vendor comparisons used. Numbers from different harnesses are never subtracted across columns. "not found" means exactly that — no number was located, not that the model is bad.

**Provenance.** `[S#]` refers to the source list at the end. A number quoted from the repo's read-only seat prior (`docs/WFE_SEAT_PRIOR_20261018.md`, itself a 2026-10-18 web read) is marked `prior S#`; I did not re-fetch every vendor card in this pass. Source dates are the page/card date where stated, otherwise the read date (2026-10-18).

---

## 1. Recommendation table

| role | current (config/portal.yaml) | recommended | why (numbers + sources) | in backends.yaml? | size at Q4 | confidence |
|---|---|---|---|---|---|---|
| **deep reasoning** | `auto-reasoning` — DeepSeek-R1-0528-Qwen3-8B `:Q4_K_XL-ctx64k` | **Qwen3.8-27B** (`hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k`; the 96K tag is already on disk and over-provisions the 64K lane) | HLE **33.9** independent, GPQA **90.5**, LiveBench **75.3**, AA Intelligence **34** — the highest fitting model in the AA open-weight table [S1,S5,S6,S9,S10]; the seat's vendor GPQA is 61.1 (cross-harness) and it has no HLE row. K2 Horizon 36B-A4B is next on AA at **25** but has no reasoning-harness row [S5,S22]. | yes (ctx96k + MLX) | ~17 GB | **high** |
| **coding — single-turn** | `auto-coding` — `qwen3-coder:30b-a3b-q4_K_M-ctx256k` | **Qwen3.8-27B** | LiveCodeBench v6 **90.3** vs Qwen3.6-27B **83.9** on the same Qwen card; SWE-bench Pro **61.7** [S1]. The seat has **no public benchmark table**; its only measurement is the repo's 40-task `bench_repair` (90 % one-shot) [S26]. **Tag gap:** the registered Qwen3.8 tags stop at 96K; a 256K tag is required for this seat. | yes, but not at 256K — new tag required | ~17 GB | **high** on quality; **medium** on the 256K tag (KV probe needed) |
| **coding — agentic** | `auto-coding` variant `laguna` — `portal5/laguna-xs21:q4_K_M-ctx128k` (Laguna-XS-2.1, 33B-A3B) | **Qwen3.8-27B** for the main seat; **Ornith-1.5-35B-A3B** as the head-to-head challenger | Qwen3.8 TB 2.1 **73.0** vs Qwen3.6-27B **63.4** and Muse Glimmer **51.7** on one vendor harness; SWE-Pro **61.7** [S1]. Ornith-1.5-35B-A3B **79 %** SWE-bench Verified (compiled, vendor) vs Laguna **70.9 %** [S16]. Independent SWE-rebench: Gemma 4 31B **41.6** and Devstral Small 2 **38.9** are the strongest current-generation entries on the 2026-05-06 snapshot (the older Qwen3.5-27B is 58.9 there); Qwen3.6-27B **31.2 ± 1.68** on the live board [S13,S14]. No SWE-rebench row exists for Qwen3.8-27B. **Tag gap:** a 128K tag (native 262K) is required; the registered GGUF tags stop at 96K. | Qwen3.8 yes; Ornith 1.5 only as uncensored GGUF | 17 / 21 GB | **medium** |
| **tool calling / agents** | `tools-specialist` — `granite4.1:8b-ctx8k` | **Qwen3.6-35B-A3B** | Tau2 **95.3** independent; BFCL v4 **65.0** vendor [S8,S15]. GLM-4.7-Flash has the best Tau2 (**98.8**) but no BFCL v4 row in the loaded sources (IFBench 60.8 thinking / 46.3 non-thinking) [S8,S11,S15]; Qwen3.6-27B is **94.2** Tau2 with no BFCL v4 row [S8]. Seat: BFCL **v3** 68.27 (different version, not comparable) and no Tau2 row. | yes | ~21 GB | **medium** |
| **long-document reading (128k)** | `compliance-reading` — `gemma4:26b-a4b-it-q4_K_M-ctx128k` | **Qwen3.8-27B** | AA-LCR **82.0** independent vs seat **65.7** (+16.3); Qwen3.6-27B **77.3**, Gemma 4 31B **69.7** [S7]. Seat's only lane-specific record is internal (4/6 tie; 6/6 verbatim; 124.7k-token read in 211 s) [S26]. **Tag gap:** Qwen3.8's registered GGUF tags stop at 96K, so this needs a 128K/256K tag (native 262K) or the MLX path; the 96K tag would truncate the seat's 124.7k case. | yes, but not at 128K — new tag required | ~17 GB | **medium-high** (quality) / **medium** (window) |
| **structured extraction** | `auto-extract-uncensored` — LFM2.5-8B-A1B-Uncensored `:q4_K_M-ctx8k` | **Qwen3.8-27B** | ExtractBench mean **89.75** independent vs Qwen3.6-35B **88.11**, Qwen3.5-9B **86.10**; seat **not found** [S18,S25]. If the uncensored property is required, `Qwen3.8-27B-Uncensored` is already registered but has no ExtractBench row [S26]. | yes (both) | ~17 GB | **medium-high** on the number; **medium** on the uncensored variant |
| **vision** | `auto-vision` — `qwen3-vl:32b-ctx8k` | **Qwen3.6-35B-A3B** (challenger — keep the seat until the MMMU slice) | MMMU **75.9** independent / **81.7** same-card vendor; Qwen3.5-27B leads independently at **77.6** but is not in `backends.yaml`; Gemma 4 31B **74.1**, Muse Glimmer **74.1**, Gemma 4 26B **71.8** [S2,S12]. Qwen3.8-27B has the strongest vendor VL table (MathVision **90.0**, CharXiv-RQ **83.7**, OmniDocBench 1.5 **91.1**) but **no MMMU row** [S1]. Seat MMMU: **not found** — so this is a challenge, not a proven upgrade. | yes | ~21 GB | **medium-low** |
| **small fast router / classifier (≤10B)** | `auto` — `huihui_ai/qwen3.5-abliterated:9b-ctx8k`; `task-router` — Gemma 4 E4B OBLITERATED | **Qwen3.5-9B base** for `task-router`; **K2 Horizon 7B** as the quality challenger | Base Qwen3.5-9B: BFCL v4 **66.1**, Tau2 **86.8**, IFBench **66.7**, AA **11** [S5,S8,S11,S15]. The abliterated seat pays a measured tax: MMLU **−1.54**, GSM8K **−5.68**, TruthfulQA **−12.65** [prior: abliterlitics.dev/models/qwen3.5-9b]. K2 Horizon 7B: AA **21**, 524K context, Apache 2.0, released 2026-09-03 [S5,S22]. MiniCPM5-2B reaches BFCL **66.6** at 1.6 GB [S27,S24]. | Qwen3.5-9B base **no**; K2 **no**; MiniCPM5 **no**; abliterated seat yes | 5.8 / 4.5 / 1.6 GB | **medium** |
| **general fast assistant** | `general-fast` — Qwen3.6-35B-A3B `:UD-Q4_K_XL-ctx96k`; `auto-daily` — `gemma4:26b-a4b-it-qat-ctx16k` | **keep Qwen3.6-35B-A3B**; test **K2 Horizon 36B-A4B** | Seat AA **18** at ~139 t/s; Gemma 4 26B **17**\* at ~67 t/s; Nemotron 3.5 Lightning **13** at ~299 t/s [S5]. Same-harness NVIDIA table: Qwen3.6-35B GPQA **83.4**, AA-LCR **61.1**, SWE-V **70.1**, TB 2.1 **44.4** vs Gemma 4 26B 79.6 / 57.6 / 57.4 and Nemotron 75.4 / 52.0 / 51.6 [prior S6]. K2 Horizon 36B-A4B AA **25** — the only untested fitting model clearly above the seat [S5,S22]. | yes; K2 **no** | 21 / 22 GB | **medium** (K2 has no local throughput measurement) |
| **creative writing** | `auto-creative` — Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive `:Q4-ctx8k` | **Muse Glimmer 30B** (`muse-glimmer:30b-mlx`) | EQ-Bench Creative Writing v3 Elo **1798.3** vs Qwen3.8-27B **1671.3**, Gemma 4 31B **1368.2**, Gemma 4 26B **1304.6**, Nemotron 3.5 **1280.3**, GLM-4.7-Flash **1124.7**; seat **not found** [S17]. Muse Glimmer is already registered and measured locally at 19.7 GiB [S26]. | yes | 19.7 GiB measured | **high** on the number; **medium** on replacing an uncensored seat |
| **security analysis** | `auto-security` — `hf.co/mradermacher/VulnLLM-R-7B-GGUF:q4_K_M-ctx8k`; `security-reviewer` — `granite4.1:8b-ctx8k` | **keep VulnLLM-R-7B**; run **Foundation-Sec-8B-Reasoning** as the challenger | VulnLLM-R author-run function-level F1 **0.723–0.870** [S20]; Foundation-Sec independent fresh-CVE accuracy **38.0 %** (95 % 36–40) and fresh CVE→CWE **55.1 %** (52–59) [S21]. RealVuln v3.1: security-specialised **86.4** F3 > best general-purpose LLM **80.0** > best SAST **23.1**; no ≤35 GB general model is named [S19]. No matched head-to-head exists. | VulnLLM yes; Foundation-Sec Q8 only (Q4 not registered) | 4 / 5 GB | **low** — probe, do not swap blind |

**Sizes** are nominal weight bytes at Q4; add KV cache at the lane's window. The 256K lanes (`auto-coding` and its `laguna`/`heavy` variants) and 128K lanes must be load-probed before a seat is declared. `Muse Glimmer` is 19.7 GiB measured on this host, not nominal. `*` after an AA score marks the leaderboard's estimated/partial-coverage flag.

---

## 2. Lane evidence

### 2.1 Deep reasoning

| candidate | release | Q4 | independent | vendor / same-harness | fits |
|---|---|---|---|---|---|
| **Qwen3.8-27B** | 2026-08 | ~17 GB | HLE **33.9**, GPQA **90.5**, LiveBench **75.3**, AA **34** [S5,S6,S9,S10] | HLE 30.8, GPQA 89.2, IFBench 79.5, LCB v6 90.3 [S1] | yes |
| K2 Horizon 36B-A4B | 2026-09-03 | ~22 GB | AA **25** [S5] | no reasoning-harness table found | yes |
| Qwen3.6-27B | 2026-04 | ~17 GB | HLE **24.0**, GPQA **84.2**, LiveBench **64.0** [S5,S6,S9,S10] | HLE 24.0, GPQA 87.8, LCB 83.9 [S3] | yes |
| *seat* DeepSeek-R1-0528-Qwen3-8B | 2025-05 | ~5 GB | no HLE row found | GPQA **61.1**, AIME25 76.3 [prior S5] | yes |

The seat is a 2025 8 B distill. Qwen3.8-27B's independent GPQA is **90.5** against the seat's vendor **61.1** — a large gap, but cross-harness, so directional only, not a 29.4-point delta; the seat has no HLE row to compare. At ~3.4× the weight bytes it is still inside one request's budget. The census's own conclusion — the math suite is at its ceiling and GLM-4.7-Flash/Qwen3.8 are 2–6× faster — points the same way. **The one open question is throughput**: Qwen3.8-27B measures 42 t/s on AA's hosted run, vs 59 t/s for Qwen3.5-9B; a local oMLX MTP build is already in the fleet, so measure decode before committing the 64K seat.

### 2.2 Coding — single-turn

| candidate | Q4 | independent | vendor / same-harness | fits |
|---|---|---|---|---|
| **Qwen3.8-27B** | ~17 GB | no LiveCodeBench independent row located | LCB v6 **90.3**, SWE-Pro **61.7**, IFBench 79.5 [S1] | yes |
| Qwen3.6-27B | ~17 GB | SWE-rebench **31.2 ± 1.68** [S13] | LCB v6 **83.9**, SWE-V 77.2, TB 2.0 59.3 [S3] | yes |
| Granite 4.2 30B | ~18 GB | no independent row located | LCB v6 **75.77**, BFCL v4 61.39, SWE-V 57.0 (same card, 3B/8B/30B) [S4] | yes |
| *seat* qwen3-coder:30b-a3b | ~21 GB | none | card has no benchmark table [S26] | yes |

Single-turn coding has the cleanest evidence in the set: one Qwen card runs Qwen3.8-27B, Qwen3.6-27B and two larger siblings through the same harness, and Qwen3.8 leads Qwen3.6 by 6.4 LCB points. The only real risk is the seat's 256K declaration: Qwen3.8-27B is registered at 96K in `backends.yaml` and its native window is 262K, so a `-ctx256k` tag plus a KV probe is a precondition, not a detail.

### 2.3 Coding — agentic

| candidate | Q4 | independent | vendor / compiled | fits |
|---|---|---|---|---|
| **Qwen3.8-27B** | ~17 GB | no SWE-rebench row | TB 2.1 **73.0**, SWE-Pro **61.7**; same card: Qwen3.6-27B 63.4, Muse Glimmer 51.7 [S1] | yes |
| **Ornith-1.5-35B-A3B** | ~21 GB | not on live SWE-rebench | SWE-V **79.0 %** (compiled from published reports) [S16] | yes |
| Gemma 4 31B | ~19 GB | SWE-rebench **41.6** (2026-05-06 imported snapshot) [S14] | SWE-bench Verified not found in the loaded sources | yes |
| Devstral Small 2 24B | ~14 GB | SWE-rebench **38.9** (same snapshot) [S14] | SWE-V not found in card text | yes |
| *seat* Laguna-XS-2.1 33B-A3B | ~19 GB | not on live SWE-rebench | SWE-V **70.9**, SWE-Pro 47.6, TB 2.0 37.5 [prior S10]; local WFE 29/42 [S26] | yes |

This lane has a genuine evidence conflict, and it should not be papered over. On **vendor** SWE-bench Verified, Ornith-1.5-35B-A3B (79 %) and Qwen3.6-27B (77.2 %) beat Laguna (70.9 %). On **independent** SWE-rebench, the 2026-05-06 imported snapshot puts Qwen3.5-27B (58.9) and Qwen3.5-35B-A3B (53.7) above Gemma 4 31B (41.6) and Devstral Small 2 (38.9), while the live October board has Qwen3.6-27B at 31.2 ± 1.68 and Qwen3.6-35B at 24.7 ± 0.79 — a much lower absolute scale. The two boards are not comparable, and Qwen3.8-27B has no SWE-rebench row at all. The defensible ranking is therefore: **Qwen3.8-27B first on the only same-harness 2026 agentic table (TB 2.1)**, **Ornith-1.5-35B-A3B first on SWE-bench Verified**, **Gemma 4 31B / Devstral Small 2 first among current-generation models on independent fresh issues**. The cheapest resolution is a three-arm run on the existing agentic instrument, not another table.

The lite agentic seat has a notable option: **Ornith-1.5-9B**, SWE-V **70.6 %** at ~4.5 GB [S16]. That is within 0.3 points of the current 33B Laguna seat at a quarter of the memory.

### 2.4 Tool calling / agents

| candidate | Q4 | independent | vendor | fits |
|---|---|---|---|---|
| **Qwen3.6-35B-A3B** | ~21 GB | Tau2 **95.3** [S8] | BFCL v4 **65.0**, τ³ 67.2 [S2,S15] | yes |
| GLM-4.7-Flash | ~19 GB | Tau2 **98.8** [S8] | BFCL v4 not found; IFBench 60.8 thinking / 46.3 non-thinking [S11] | yes |
| Qwen3.6-27B | ~17 GB | Tau2 **94.2** [S8] | BFCL v4 not found | yes |
| *seat* granite4.1:8b | ~5 GB | no Tau2 row | BFCL **v3** 68.27, IFEval 87.06 [prior] | yes |

Tau2 and BFCL do not give a clean cross-harness winner: GLM-4.7-Flash wins multi-turn Tau2 by 3.5 points but has no BFCL v4 row, while Qwen3.6-35B has the only BFCL v4 row among the three (65.0). For a seat whose job is "structured API/function calls, often chained", BFCL is the closer harness, so the balanced pick is Qwen3.6-35B-A3B. The 8 B Granite seat is not disgraced — its BFCL **v3** 68.27 is a different version and cannot be compared to the v4 rows — but it is 16 GB smaller and has no multi-turn agent number. **Do not read the v3/v4 rows as a regression or an improvement.**

Two watch-list models do not fit or are not verified: Ling 3.0 Flash scores BFCL **73.0** but is 124 B total / 5.1 B active, ~70 GB at Q4; BTL-3 (88.5) and Atria Dawn (77.0) are open but have no published parameter count, so fitness cannot be established [S15].

### 2.5 Long-document reading (128k)

| candidate | Q4 | independent (AA-LCR) | other | fits |
|---|---|---|---|---|
| **Qwen3.8-27B** | ~17 GB | **82.0** [S7] | native 262K, vendor 1M extension [S1] | yes |
| Qwen3.6-27B | ~17 GB | **77.3** [S7] | native 262K [S3] | yes |
| Gemma 4 31B | ~19 GB | **69.7** [S7] | native 256K [S1] | yes |
| Granite 4.2 30B | ~18 GB | no AA-LCR row | RULER **128K 81.38** (same card) [S4] | yes |
| *seat* gemma4:26b ctx128k | ~16 GB | **65.7** [S7] | internal 4/6 tie, 6/6 verbatim, 124.7k tokens in 211 s [S26] | yes |

AA-LCR is the closest public harness to the seat's job (find and use facts in a long document), and the seat is 16.3 points behind Qwen3.8-27B. The vendor RULER 128K number for Granite 4.2 30B (81.38) is a useful second opinion, but it is a different harness and a same-card comparison only. The seat's internal record — twice measured, including a 124.7k-token real document — is the only lane-specific evidence; it does not overturn a 16-point independent gap, but it does mean the replacement must pass the same 6-item verbatim test before the 128K route is moved. **Window caveat:** Qwen3.8's registered GGUF tags stop at 96K; a 128K/256K tag (or the MLX path, which serves the native window) is a prerequisite, because the seat's worst case is 124.7k tokens.

### 2.6 Structured extraction

| candidate | Q4 | independent (ExtractBench mean) | other | fits |
|---|---|---|---|---|
| **Qwen3.8-27B** | ~17 GB | **89.75** [S18,S25] | native VLM; OmniDocBench 91.1 vendor [S1] | yes |
| Qwen3.6-35B-A3B | ~21 GB | **88.11** [S18,S25] | FP8/vLLM `json_object` serving caveat in the prior | yes |
| Qwen3.5-9B | ~5.8 GB | **86.10** [S18,S25] | BFCL 66.1, IFBench 66.7 [S15,S11] | yes |
| *seat* LFM2.5-8B-A1B-Uncensored | ~5 GB | **not found** | IFEval 91.84, BFCL v3 64.36 [prior S4] | yes |

The independent leaderboard puts three Qwen models within 3.65 points of each other, with the 9B only 3.65 behind the 27B. That matters: if the lane is latency- or memory-sensitive, **Qwen3.5-9B at 5.8 GB is the value pick**; if accuracy is the only criterion, Qwen3.8-27B. The seat has no ExtractBench number, so this is an evidence gap in the incumbent, not a measured loss. Caveat: the ExtractBench site renders its leaderboard as a client-side image; the three means above are from the repo prior's 2026-10-18 snapshot and were **not re-fetched** in this pass.

### 2.7 Vision

| candidate | Q4 | independent (MMMU) | vendor / same-card | fits |
|---|---|---|---|---|
| Qwen3.5-27B | ~17 GB | **77.6** [S12] | not found | **not in backends** |
| **Qwen3.6-35B-A3B** | ~21 GB | **75.9** [S12] | MMMU **81.7**, MMMU-Pro 75.3, VideoMMMU 83.7 [S2] | yes |
| Gemma 4 31B | ~19 GB | **74.1** [S12] | MMMU not found in loaded card text | yes |
| Muse Glimmer 30B | 19.7 GiB | **74.1** [S12] | native ViT-G/14 vision encoder [S23] | yes |
| Qwen3.8-27B | ~17 GB | no MMMU row | MathVision **90.0**, CharXiv-RQ **83.7**, RealWorldQA **85.9**, OmniDocBench 1.5 **91.1** [S1] | yes |
| *seat* qwen3-vl:32b | ~21 GB | **not found** (no MMMU row in the loaded snapshot) | card tables are images | yes |

The independent MMMU table says Qwen3.5-27B, then Qwen3.6-35B, then a three-way tie at 74.1. Qwen3.5-27B is **not registered** and would need a download. Qwen3.8-27B is the strongest model in the lane on its vendor VL table, but it has no MMMU row, so recommending it would be a vendor-only call. The pragmatic evidence-based **challenger** is **Qwen3.6-35B-A3B**: it is already on disk, it has both an independent and a same-card number, and its 81.7 vendor MMMU is second only to Qwen3.6-27B's 82.9 on the same card. It is not yet an upgrade over the seat, because the seat has no MMMU row to compare; the 100-image slice below is what turns this into a decision. If the seat's actual job is documents/charts rather than natural images, Qwen3.8-27B's OmniDocBench 91.1 is the better signal and should be tested in the same run.

### 2.8 Small fast router / classifier (≤10B)

| candidate | Q4 | independent | vendor | fits |
|---|---|---|---|---|
| **Qwen3.5-9B base** | 5.8 GB | Tau2 **86.8**, IFBench **66.7**, MMMU **74.1**, LCR **70.0**, AA **11** [S5,S7,S8,S11,S12] | BFCL v4 **66.1** [S15] | **not in backends** |
| **K2 Horizon 7B** | ~4.5 GB | AA **21** [S5] | 524K context, Apache 2.0, released 2026-09-03 [S22] | **not in backends** |
| MiniCPM5-2B | ~1.6 GB | AA **12** [S5] | BFCL **66.6** [S15] | **not in backends** |
| Granite 4.2 8B | ~5 GB | AA **11** [S5] | BFCL 52.39, IFBench 79.33 [S4] | **not in backends** |
| *seat* qwen3.5-abliterated 9b | 5.8 GB | abliteration tax: MMLU **−1.54**, GSM8K **−5.68**, TruthfulQA **−12.65** [prior S18] | no routing metric | yes |

The current seat is the same 9B Qwen3.5 weights with an abliteration pass. The tax is measured and non-trivial (TruthfulQA −12.65), so for a pure classifier the base model is the better default. K2 Horizon 7B is the interesting new entrant: AA **21** is nearly double the 9B's **11** at a smaller footprint and a 524K window, but there is no BFCL/IFBench/routing number yet, so it is a **screen**, not a swap. MiniCPM5-2B is the cheap fallback: BFCL **66.6** at 1.6 GB, essentially tied with the 9B on the one tool-schema harness both have. The `auto` seat may need the abliterated behaviour for open-topic routing; if so, keep the seat and use Qwen3.5-9B base only for `task-router`, which is a titles/tags job.

### 2.9 General fast assistant

| candidate | Q4 | independent | vendor / same-harness | speed | fits |
|---|---|---|---|---|---|
| **Qwen3.6-35B-A3B** (general-fast seat) | ~21 GB | AA **18** [S5] | GPQA 83.4/86.0, AA-LCR 61.1, SWE-V 70.1/73.4, TB 2.1 44.4, IFBench 63.7 [prior S6] | ~139 t/s (AA hosted) | yes |
| **K2 Horizon 36B-A4B** | ~22 GB | AA **25** [S5] | no speed/tool table found | not measured | yes |
| Gemma 4 26B A4B (auto-daily seat) | ~16 GB | AA **17**\* [S5] | GPQA 79.6, AA-LCR 57.6, SWE-V 57.4, IFBench 77.3 [prior S6] | ~67 t/s (AA hosted) | yes |
| Muse Glimmer 30B | 19.7 GiB | AA **17**, MMMU 74.1 [S5,S12] | 141 t/s hosted; **25.6 t/s measured locally** on the Ollama MLX path [S26] | 25.6 t/s local | yes |
| Nemotron 3.5 Lightning 30B-A3B (auto-nemotron seat) | ~18 GB | AA **13** [S5] | GPQA 75.4, AA-LCR 52.0, SWE-V 51.6, TB 2.1 24.6, IFBench 71.9 [prior S6] | ~299 t/s hosted | yes |

The fleet already holds the correct fast/quality pair: Qwen3.6-35B at AA 18 and Gemma 4 26B at 17\* are within noise, and the NVIDIA same-harness table shows Qwen3.6 ahead on reasoning/coding/long-context while Gemma leads instruction-following by 13.5. K2 Horizon 36B-A4B is the only fitting model with a clear AA lead (+7 over the seat) and the same 3–4 B active class, so it is the one worthwhile download. **Muse Glimmer is not a speed option on this host** — its 141 t/s is hosted, and the local measured figure is 25.6 t/s, below the seat. Nemotron remains the throughput specialist (299 t/s hosted) but is 5 AA points behind and loses every shared reasoning/coding bench.

### 2.10 Creative writing

| candidate | Q4 | independent (EQ-Bench v3 Elo) | notes | fits |
|---|---|---|---|---|
| **Muse Glimmer 30B** | 19.7 GiB | **1798.3** [S17] | 30B dense, Apache 2.0, 128K, native vision [S23]; already in backends [S26] | yes |
| Qwen3.8-27B | ~17 GB | **1671.3** [S17] | also strong reasoning/coding; `Qwen3.8-27B-Uncensored` is registered [S26] | yes |
| Gemma 4 31B | ~19 GB | **1368.2** [S17] | Gemma 4 26B 1304.6, 12B 1288.9 [S17] | yes |
| GLM-4.7-Flash | ~19 GB | **1124.7** [S17] | — | yes |
| *seat* HauhauCS Qwen3.6-35B | ~21 GB | **not found** | 0/465 refusals claimed [prior S11] | yes |

This is the largest single-lane gap in the sweep: Muse Glimmer is **127 Elo** above Qwen3.8-27B and **430 Elo** above Gemma 4 31B, and it is already on disk. The catch is policy, not quality: the seat exists because it is uncensored, and Muse Glimmer is not. The honest recommendation is therefore conditional — **Muse Glimmer for a quality-first creative seat**, and **`Qwen3.8-27B-Uncensored`** (registered, no public creative number) as the uncensored alternative to test against the incumbent. Do not compare the seat's 0/465 refusal claim to a benchmark Elo; they measure different things.

### 2.11 Security analysis

| candidate | Q4 | evidence | fits |
|---|---|---|---|
| **VulnLLM-R-7B** (seat) | ~4 GB | function-level F1 **0.723–0.870** across Python/C/Java, author-run paper [S20] | yes |
| **Foundation-Sec-8B-Reasoning** | ~5 GB (Q4) | fresh-CVE accuracy **38.0 %** (95 % 36–40), fresh CVE→CWE **55.1 %** (52–59), independent 2026-10-05 [S21]; Q4 GGUF published, Q8 registered | yes |
| Qwen3.8-27B | ~17 GB | no matched security number; GPQA 90.5 general [S10] | yes |
| *security-reviewer* granite4.1:8b | ~5 GB | no security metric; BFCL v3 68.27 [prior] | yes |

There is **no matched head-to-head** between the seat and any challenger on the CVE/CWE analytical workload. What exists is directional: VulnLLM-R has a strong author-run function-level result, Foundation-Sec has independent fresh-CVE numbers and a published Q4 build, and RealVuln v3.1 (33 scanners, identical commits) shows the category ordering is real — security-specialised **86.4** F3, best general-purpose LLM **80.0**, best SAST **23.1** — but it names no ≤35 GB general model [S19]. The correct action is a 20-item CVE→CWE + severity probe with both 7–8 B models, not a reseat on cross-benchmark intuition. The `security-reviewer` seat (read-only telemetry review) remains unmeasured; the closest public harness, ExCyTIn-Bench, publishes no per-model scores.

---

## 3. Released since 2026-06 and never considered

Checked against the 207 unique ids in `config/backends.yaml` (exact substring search, 2026-10-18). "Never considered" below means **zero ids** for the family in the registry. Models that were trialled without registration are called out separately.

| model / family | released | size · context · licence | why it matters | in backends? | verdict |
|---|---|---|---|---|---|
| **IBM Granite 4.2** (3B / 8B / 30B) | **2026-08-25** [S4] | 30B dense · 128K native / 512K ext · Apache 2.0 | Same-card table: RULER 128K **81.38**, BFCL v4 **61.39**, LCB v6 **75.77**, SWE-V **57.0**, IFBench **77.17**, GPQA **66.41**. One family covers router (3B/8B) and main (30B). | **no** — 0 ids | **download the 30B + one 8B**; highest-value untried family |
| **K2 Horizon** (0.9B / 3.7B / 7B / 32B / 36B-A4B / 375B-A23B) | **2026-09-03** [S22] | 7B ~4.5 GB, 32B ~19 GB, 36B-A4B ~22 GB · 512K (all but 0.9B) · Apache 2.0, weights+data | AA **25** for 36B-A4B (above Qwen3.6-35B's 18) and **21** for 7B; fully open, day-zero Ollama support claimed. No local throughput or tool number yet. | **no** — 0 ids | **download 36B-A4B and 7B**; the 36B is the only clear general-fast challenger |
| **MiniCPM5-2B** | **2026-09-07** [S24] | 2.5B dense · 131K · Apache 2.0 | BFCL v4 **66.6** — within 0.5 of Qwen3.5-9B — at 1.6 GB; AA **12** beats the 9B's 11. | **no** — 0 ids | **download**; router/preselect candidate |
| **Muse Glimmer 30B** | 2026-08-10 [S23] | 30B dense · 128K · Apache 2.0, vision | EQ-Bench **1798.3**, MMMU **74.1**, AA **17**, SWE-V 76.0 compiled. | **yes** (`muse-glimmer:30b-mlx`) | already considered; local verdict "no coding/agentic edge", but it was never tested on creative — that is the lane it wins |
| **Ornith-1.5-35B-A3B** | 2026 (date not stated) | 35B-A3B · 262K | SWE-V **79 %** compiled — highest fitting local entry [S16]. | **yes**, but only the uncensored GGUF | already considered; the stock base is not registered |
| **Qwen3.8-Flash-Next** | 2026-08 | ~80B-class MoE (REAP-288 build was the only fitting form) | AA **40** — the base is nominally ~45 GB at Q4, above the ceiling. | **no** — `Qwen3.8-Flash-Next-REAP-288-MLX-4bit` removed 2026-10-21 | removed; do not re-flag |
| **Ling 3.0 Flash** | **2026-07-23** [S15] | 124B total / 5.1B active · 262K · MIT | BFCL v4 **73.0**, LCR **73.0**, GPQA 85.5 — but ~70 GB at Q4. | **no** | **does not fit**; it was also trialled and gated on this box (TurboQuant memory gates) [S26] |
| **Solar Mini 4** | 2026-09-22 | 35B-A3B · 512K | AA **24**, but **proprietary — weights not public** [S5 search]. | no | **exclude** (not open-weight) |
| **Motif 3** | 2026-08-07 | 314B total / 13.2B active · 262K · MIT | AA **34**\* — would be interesting at 1/10 the size. | no | **does not fit** (~170 GB nominal at 4-bit) |
| **Inkling-Small** | 2026-07-30 | 276B total / 12B active · 1M · Apache 2.0 | AA **26**; multimodal. | no | **does not fit** (~150 GB nominal at 4-bit) |
| **EXAONE 4.5 33B** | 2026-04-09 | 33B · 262K · open-weight VLM | AA **13**\*; never in the registry. | no | older than the June cutoff; low priority |
| **Nemotron 3 Nano 30B-A3B / Omni** | 2026 (date not stated) | 30B-A3B · 256K–1M | AA **9–10**\*; below the current Nemotron seat. | no | not worth a download |
| **Step3 VL 10B** | older | 10B · 65K | AA **8**\*; vision. | no | not competitive |

**Already considered, so not flagged:** Qwen3.8-27B (Aug 2026, 7 tags), Qwen3.8-27B-Uncensored, Ornith-1.5-35B-A3B (uncensored GGUF), Muse Glimmer 30B, Qwen3.8-Flash-Next-REAP-288, Ling 3.0 Tiny, Gemma 4 12B, Nemotron 3.5 Lightning (Aug 14, seated). **Trial-but-never-registered:** Ling 3.0 Flash (memory-gated), Granite Switch 4.1 (rejected 2026-09-22, `docs/LANDSCAPE_2026Q3_CLOSEOUT.md`).

---

## 4. Cheapest local check per recommendation

All of these use instruments already in the tree. Command shape is the repo's WFE driver: `uv run python -m tests.wfe.campaign --plan <plan> --smoke` first, then the same plan without `--smoke`; one arm per process, per the driver's contract. Nothing here needs a new harness.

| lane | instrument already built | what to run | cost |
|---|---|---|---|
| deep reasoning | `tests/wfe/plans/reasoning_math_decision_v1.yaml` (suite at ceiling — use as regression, not ranking) | Qwen3.8-27B vs seat, `--tier screen`, plus a 20-item GPQA-Diamond slice through the same runner; record median seconds | ~1 h; no download |
| coding single-turn | `tests/wfe/plans/coding_decision_v1.yaml` (`coding_production`, 36 hidden-test tasks) | add Qwen3.8-27B arm at a 256K tag; `--smoke` first to prove the tag loads at the declared window | ~2–4 h; one tag |
| coding agentic | `tests/wfe/plans/s2_laguna_rerun_omlx.yaml` / `seat_baseline_v3.yaml` (`auto-coding::laguna`); plus `bench_repair` 40-task | Laguna vs Qwen3.8-27B vs Ornith-1.5-35B-A3B on the same agentic loop; `bench_repair` for the one-shot/repair split | ~3–6 h; Ornith base download if used |
| tool calling / agents | `tests/wfe/plans/tools_specialist_decision_v1.yaml` | Granite 4.1 8B vs Qwen3.6-35B vs GLM-4.7-Flash; chained tool tasks, same prompt | ~1–2 h; no download |
| long-document reading | `tests/wfe/plans/reading_decision_v1.yaml` (`reading_production`, 128K) | Gemma 4 26B vs Qwen3.8-27B; include the 6-item verbatim citation set and the 124.7k-token document | ~1–2 h; no download |
| structured extraction | `tests/wfe/plans/extract_decision_v1.yaml` (`extract_production`) | LFM2.5-8B vs Qwen3.8-27B vs Qwen3.5-9B; schema validity, value accuracy, record completeness | ~1–2 h; Qwen3.5-9B GGUF if used |
| vision | **no instrument yet** (census: 18 workspaces without one) | 100-question MMMU-val slice through Ollama, same prompt, `qwen3-vl:32b` vs `qwen3.6-35b-a3b` vs `qwen3.8-27b`; score exact-match | ~1 h after the 100-image fixture; smallest new harness in the set |
| small router / classifier | `tests/wfe/plans/routing_decision_v1.yaml` (`routing_production`) | seat abliterated 9B vs Qwen3.5-9B base vs K2 Horizon 7B vs MiniCPM5-2B; classification accuracy + p50 latency at 2K | ~1 h; 3 small downloads |
| general fast assistant | `tests/wfe/plans/general_decision_v1.yaml` (`general_production`) | Qwen3.6-35B vs K2 Horizon 36B-A4B; `--tier screen`; the runner already records tok/s, so gate on ≥50 t/s | ~2 h; one 22 GB download |
| creative writing | `tests/wfe/suites/creative.jsonl` (9-prompt blinded pairwise; no plan file) | Muse Glimmer vs Qwen3.8-27B-Uncensored vs seat; 3 judges, blind labels; **also count refusals** so the uncensored requirement is priced | ~1 h; no download |
| security analysis | **no instrument yet** (census: no instrument) | 20-item CVE→CWE + severity + hardening set, no tools, identical prompt: VulnLLM-R-7B vs Foundation-Sec-8B-Reasoning-Q4; score exact CWE and severity | ~1 h after the fixture; one 5 GB download |

**Order by expected gain:** (1) long-document reading — 16.3 independent points, no download; (2) creative writing — 430 Elo available, no download; (3) structured extraction — 3.65 points if the 9B is the comparator, seat unmeasured; no download; (4) deep reasoning — large independent gap but a speed trade; (5) coding single-turn — 6.4 vendor points, one tag; (6) tool calling — 3.5 Tau2 points, with no GLM BFCL row to compare; (7) general fast — K2 is the only AA lead, one download; (8) small router — K2 7B screen only; (9) vision — independent leader is not registered, so a new download for 1.7 points; (10) agentic coding — evidence conflict, needs a run not a table; (11) security — no matched number, probe only.

---

## 5. What I could not establish

- **ExtractBench**'s live leaderboard is client-side; the three means (89.75 / 88.11 / 86.10) are from the repo prior's 2026-10-18 snapshot, not re-fetched. Treat them as independent-but-second-hand.
- **Qwen3.8-27B has no MMMU, BFCL, Tau2 or SWE-rebench row** in the sources I could load. Its case rests on HLE/GPQA/LCR/LiveBench (independent) plus the Qwen card's coding/VL table (vendor, same-harness). Do not quote it as "best at everything".
- **SWE-rebench and SWE-bench Verified disagree** on the local agentic order. The live SWE-rebench board has Qwen3.6-27B at 31.2 and Qwen3.6-35B at 24.7; the May snapshot has Gemma 4 31B at 41.6 and Devstral Small 2 at 38.9. Different snapshots, different absolute scales. The report keeps them separate; a reader should not subtract across them.
- **Gemma 4 and Granite 4.1 cards are partly gated** (HTTP 401 in the prior read), so some Gemma 4 numbers come via Qwen-run comparison tables and are marked vendor, not independent.
- **Sizes exclude KV cache.** The 256K and 128K seats need a load-and-prefill probe; a nominal 17 GB model can exceed 35 GB at 256K depending on cache quantisation.
- **`Qwen3.5-27B` is not in `backends.yaml`.** It leads independent MMMU (77.6) and is second among fitting models on LCR (77.7, behind Qwen3.8-27B's 82.0), but it is a larger sibling of the seated Qwen3.5-9B and would be a new download. It is named in the lane tables, not in the recommendation table, because the fleet already owns Qwen3.8-27B.
- **No matched security-analysis number exists** for any ≤35 GB model. The security recommendation is deliberately a probe, not a swap.
- I did not call the local stack, download a model, or run a benchmark. This is a read-only landscape review; every "cheapest check" is a proposal.

---

## Sources

| # | source | type | date |
|---|---|---|---|
| S1 | Qwen3.8-27B model card — https://huggingface.co/Qwen/Qwen3.8-27B | vendor (same-card multi-model table) | Aug 2026; read 2026-10-18 |
| S2 | Qwen3.6-35B-A3B model card — https://huggingface.co/Qwen/Qwen3.6-35B-A3B | vendor (same-card multi-model table) | Apr 2026; read 2026-10-18 |
| S3 | Qwen3.6-27B model card — https://huggingface.co/Qwen/Qwen3.6-27B | vendor (same-card multi-model table) | read 2026-10-18 |
| S4 | IBM Granite 4.2 30B model card — https://huggingface.co/ibm-granite/granite-4.2-30b | vendor (same-card 3B/8B/30B table) | released 2026-08-25 |
| S5 | Artificial Analysis LLM leaderboard — https://artificialanalysis.ai/leaderboards/models | **independent** | read 2026-10-18 |
| S6 | LiveBench 2026-06-25 release, mirrored by BenchLM — https://benchlm.ai/benchmarks/livebench | **independent** (official LiveBench harness) | release 2026-06-25; read 2026-10-17 |
| S7 | AA-LCR via PricePerToken — https://pricepertoken.com/leaderboards/benchmark/lcr | **independent** (AA/LayerLens data) | read 2026-10-18 |
| S8 | Tau2 via PricePerToken — https://pricepertoken.com/leaderboards/benchmark/tau2 | **independent** (AA data) | read 2026-10-18 |
| S9 | HLE via PricePerToken — https://pricepertoken.com/leaderboards/benchmark/hle | **independent** (AA data) | read 2026-10-18 |
| S10 | GPQA via PricePerToken — https://pricepertoken.com/leaderboards/benchmark/gpqa | **independent** (AA data) | read 2026-10-18 |
| S11 | IFBench via PricePerToken — https://pricepertoken.com/leaderboards/benchmark/ifbench | **independent** (AA data) | read 2026-10-18 |
| S12 | MMMU via PricePerToken — https://pricepertoken.com/leaderboards/benchmark/mmmu | **independent** (LayerLens data) | read 2026-10-18 |
| S13 | SWE-rebench live leaderboard — https://swe-rebench.com/ | **independent** | read 2026-10-18 |
| S14 | SWE-rebench snapshot, imported by BenchmarkList — https://benchmarklist.com/benchmarks/swe_rebench/ | **independent** (official CSV import) | snapshot 2026-05-06; read 2026-10-18 |
| S15 | BFCL v4, BenchmarkList — https://benchmarklist.com/benchmarks/bfcl_v4/ | mixed: rows marked "model card"/"self-reported" are **vendor**; "imported" rows are **independent** | results updated 2026-10-13 |
| S16 | SWE-bench Verified, compiled by BenchLM from published reports — https://benchlm.ai/benchmarks/swe-bench-verified | **vendor-reported** (compiled) | read 2026-10-17 |
| S17 | EQ-Bench Creative Writing v3 raw results — https://eqbench.com/creative_writing.js | **independent** (LLM-judged Elo) | read 2026-10-18 |
| S18 | ExtractBench — https://arxiv.org/abs/2607.29677 and https://huggingface.co/datasets/llamaindex/ExtractBench | **independent** benchmark; means via repo prior snapshot | paper 2026-07-31; snapshot 2026-10-18 |
| S19 | RealVuln v3.1 — https://realvuln.com/findings.html | **independent** (Apache 2.0, arXiv 2604.13764) | Sept 2026 |
| S20 | VulnLLM-R paper — https://arxiv.org/abs/2512.07533 | **author-run** (vendor-equivalent) | 2025-12-08 |
| S21 | Foundation-Sec-8B ThreatClaw results — https://www.threatclaw.ai/benchmark/models | **independent** | 2026-10-05 (via prior) |
| S22 | IFM K2 Horizon press release — https://ifm.ai/k2/press-release/ | vendor | 2026-09-03 |
| S23 | Meta Muse Glimmer blog — https://research.meta.ai/blog/introducing-muse-glimmer-open-agentic-model | vendor | 2026-08-10 |
| S24 | OpenBMB MiniCPM5-2B release — https://github.com/OpenBMB/MiniCPM | vendor | 2026-09-07 |
| S25 | `docs/WFE_SEAT_PRIOR_20261018.md` and `docs/WFE_SEAT_EVIDENCE_CENSUS_20261018.md` (read-only repo) | repo prior (web read 2026-10-18) | 2026-10-18 |
| S26 | `config/backends.yaml`, `config/portal.yaml`, `config/MODEL_CATALOG.md`, `docs/KNOWN_LIMITATIONS.md` (read-only repo) | repo config | read 2026-10-18 |
| S27 | BFCL v4, BenchLM mirror — https://benchlm.ai/benchmarks/bfcl-v4 | mixed: table rows, no source column; treated as **vendor-reported** | read 2026-10-17 |

**Source count:** 27. Independent: S5, S6, S7, S8, S9, S10, S11, S12, S13, S14, S17, S18, S19, S21 (14). Vendor/compiled: S1–S4, S15 (subset), S16, S20, S22, S23, S24, S27 (11). Repo: S25–S26 (2).
