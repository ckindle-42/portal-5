# Model Intake Freshness — 2026-11-11

Re-survey of `docs/MODEL_INTAKE_FRESHNESS_20261029.md` (and its base,
`docs/MODEL_LANDSCAPE_REFRESH_20261029.md`) executed **2026-11-11**. Research only: no
downloads, no config edits, no seat changes; proposals are hypotheses for a live screen per
`docs/MODEL_SEAT_PROCESS.md`, never verdicts. Same standing rules: 1 oMLX + 1 GGUF per role,
replace in place, Unsloth authoritative for GGUF where a repo exists, no bf16, and a quant
must fit 64 GiB **beside** the resident router (gemma-4-E4B-OBLITERATED ≈ 5.4 GiB; seat
budget ≈ 50 GiB weights + KV).

**Method.** Hugging Face API `createdAt` / `lastModified` / commit subjects / tree file sizes
pulled 2026-11-11 for every seated checkpoint and every family named in the 10-29 snapshots,
plus org sweeps (newest-first) of: google, Qwen, unsloth, nvidia, zai-org, mistralai,
deepseek-ai, ibm-granite, meta-models, LiquidAI, JetBrains, RecursiveSI, poolside, inclusionAI,
MiniMaxAI, Aleph-Alpha, IFM, Kwaipilot, deepreinforce-ai, coder543, sjakek, fdtn-ai, huihui-ai,
NousResearch, microsoft, Alibaba-NLP, openai, mradermacher (Heretic search), bartowski,
mlx-community, lmstudio-community. A `lastModified` bump was only treated as a checkpoint
change after reading the commit subjects; every bump found in the window resolved to
README/card/quant-file changes (details below). The session's web-search integration was
unavailable; vendor pages cited below were fetched directly, and the new-repo sweeps above
served as the 30-day news scan.

**Status words:** `current` = the 10-29 entry is still the newest that matters for the role.
`superseded` = a newer same-job checkpoint exists (named). `newly relevant` = a model the
10-29 docs did not queue, and it fits this machine. Vendor-run scores are marked.

---

## What changed since 10-29

1. **Arete-27B (Nous Research, 2026-11-06) is the window's main release.** SFT value-alignment
   post-train of Qwen3.8-27B, 27.36B dense, Apache 2.0. Vendor Propaganda Eval: fact score
   2.32 → 2.98 / 5, propaganda-framed answers 22% → 0.9% (vendor-run). GGUF (bartowski,
   2026-11-06, Q4_K_M 17.20 GB), community uncensored/Heretic variants within four days, and
   an mlx-community OptiQ-4bit conversion landed **2026-11-11** (today; contents unverified).
   It is the first candidate that speaks to the CCP-framing half of the Qwen3.8 phone-home
   finding (§0.1 of the landscape) — it does **not** address the egress finding.
2. **The research default's family moved and its GGUF source vanished.** `nex-agi/Nex-N2.5-mini`
   (2026-09-08, 35.11B, Apache 2.0) supersedes the seated Nex-N2-mini; and the fleet's GGUF
   hint `hf.co/sjakek/Nex-N2-mini-GGUF` points at the `sjakek` org, which now returns **zero
   models**. Original (`nex-agi`) and bartowski GGUF exist. Same class of problem:
   `deepreinforce-ai` (Ornith-1.0-35B GGUF hint) is also empty — the family moved to
   `ornith-ai`. Both seats still run from local blobs; **re-pulls would fail**.
3. **NVIDIA Nemotron Labs Dory1.0-4B (2026-10-16)** — new small-model line: looped
   (latent-recurrent) normalized-GPT, 4B total, 256K ctx, OpenMDW-1.1, official GGUF at
   Q5_K_M (3.67 GB). A potential tools-fast challenger, gated on an engine probe (new
   architecture class on Ollama 0.40 / oMLX is unproven).
4. **Bolt E4B's missing-MLX condition cleared:** `mlx-community/NVIDIA-Nemotron-3.5-Bolt-E4B-OptiQ-4bit`
   created 2026-10-24. The 10-29 queue's item 5 is now actionable as written.
5. **Mellum 2.1 gained the pieces the 10-29 doc said it lacked:** official MTP repo
   `JetBrains/Mellum2.1-12B-A2.5B-Thinking-MTP` (2026-10-30) and an mlx-community conversion
   (`...-Thinking-6bit`, 2026-10-11). No Mellum 2.2.
6. **Clover-35B-A3B-Preview (DiffuSpace, 2026-10-24)** — block-diffusion LM on the seated
   Qwen3.6-35B-A3B backbone, 128K, Apache 2.0, GGUF Q4_K_M 23.00 GB, no MLX. Same-family
   descendant but a different decoding architecture: runtime support on Ollama 0.40 / oMLX is
   the open question, so it is a watch, not a queued screen.
7. **Mistral Large 4 weights are now on HF** (`mistralai/Mistral-Large-4-1T-A52B`, repo
   created 2026-09-30; Unsloth GGUF 2026-10-29). 1.0T / 52B active: still no fit — the 10-29
   conclusion holds with the weights question now closed.
8. **Gemma 4 E4B/E2B checkpoints were touched 2026-11-03** — commit #50 "fix: Remediate 219
   glitch tokens in tokenizer.json" (E2B same day). Tokenizer/config only; no weights change;
   26B-A4B-it and the QAT repos still show `lastModified` 2026-07-20. The router's
   OBLITERATED build predates the fix (repo modified 2026-10-06) → maintenance question, not
   a seat change.
9. **No checkpoint refresh for the Qwen3.8 phone-home finding.** Qwen3.8-27B's 2026-11-07
   bump is "Add a response template and generation tags (#236)"; the 2026-11-10/11 Unsloth
   GGUF bumps are "New UD3.1 quants" (quant files added; weights blob unchanged). The
   watch-for-a-fixed-checkpoint item from the landscape stays open.
10. **inclusionAI shipped small models:** ZwZ2-4B/9B/27B (2026-10-15/16; ZwZ2-9B is
    image-text-to-text; official GGUFs 2026-10-30), Ling-3.0-tiny-UBTree (2026-10-21, MIT,
    183M safetensors total, on the seated Ling-3.0-tiny base), ZoomGain-4B/9B + GGUFs
    (2026-11-10/11, cards essentially empty), LBS-27B (2026-10-26). None names a fleet role
    yet; all watch.
11. **Community uncensored wave around the seated families:** DavidAU
    Qwen3.8-40B-Ultimate-Heretic-Uncensored (2026-10-22, Build2 11-03, GGUFs 11-10, Q4_K_M
    24.20 GB), ItachiSan LiquidCode-2.5-24B-A2B (LFM2.5 finetune, 2026-11-03, bartowski GGUF
    11-10, Q4_K_M 15.35 GB), Spark-X2.6-4B abliterated variants (2026-10-22 / 10-29), and
    Frost-Cyber-Mini-Uncensored v1.1 (2026-11-07, Q4_K_M 2.62 GB). All screen-shaped, none
    evidence-backed.
12. **Nothing new** for: K2-Horizon (README bump 2026-11-04 only), Qwen3-VL (no official
    successor), Laguna (no 2.2), Flint (unchanged; oQ2e–oQ8e range completed 2026-10-27),
    KAT-Coder (unchanged 2026-07-28), GLM (no release after 2026-08-25), DeepSeek (nothing
    ≤ 64 GiB; no R2), Granite (no 4.3/5; Switch-4.1 GGUFs completed 2026-10-22 incl. 8b),
    Muse (eval results added 2026-10-22, weights unchanged), Kolibri (unchanged), gpt-oss,
    Hermes (4.3-36B remains newest, 2025-11), Devstral (2512 unchanged), Foundation-Sec,
    AgentWorld, phi4-mini-reasoning, Tongyi-DeepResearch. No Unsloth GGUF for LFM3-1.7B yet —
    vendor GGUF remains the route.

---

## Per-role tables

### 1. router-uncensored (task-router + `LLM_ROUTER_MODEL`)

Seat: `hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M-ctx2k` (repo modified
2026-10-06).

| Family / entry | 10-29 said | Newest as of 2026-11-11 | Date | Status |
|---|---|---|---|---|
| Gemma 4 E4B base | weights last touched 2026-07-20 | `google/gemma-4-E4B-it` lastModified 2026-11-03 — tokenizer glitch-token remediation (commit #50), no weights change | 2026-11-03 | **current**, new maintenance note: OBLITERATED rebuild predates the tokenizer fix |
| Small uncensored challengers | Nemotron Bolt E4B Heretic (10-27), no JSON evidence | Window additions, all without JSON-discipline evidence: `mradermacher/Qwen3.5-4B-heretic-v1-GGUF` (Q4_K_M 2.71 GB), `SC117/Spark-X2.6-4B-abliterated-FIT-GGUF` (10-22), `FrostWolfAI/Spark-X2.6-4B-abliterated-GGUF` (10-29), `mradermacher/ZwZ2-4B-Surgical-Abliterated-GGUF` (10-30) | 2026-10-22 → 11-10 | **current.** Do not re-seat. |

### 2. reasoning (auto-reasoning)

Seat: `hf.co/bartowski/K2-Horizon-MoVA-36B-A4B-GGUF:Q4_K_M-ctx64k` (GGUF repo unchanged
2026-10-07). Deep variant: Qwen3.8-27B (GGUF + oMLX oQ4e-mtp).

| Family / entry | 10-29 said | Newest as of 2026-11-11 | Date | Status |
|---|---|---|---|---|
| K2-Horizon MoVA 36B-A4B | current | Same checkpoint. IFM repo 2026-11-04 bump = "Update README.md" only | 2026-11-04 | **current.** Fork-GGUF note still stands |
| Jais 3 | newly relevant, Arabic only | Official GGUFs now on the IFM org (`IFM/Jais-3-*-GGUF`, 2026-10-12/13) — previously the GGUF was on `IFM` only per snapshot; no Jais 4 | 2026-10-13 | **current** for this role (Arabic-only relevance unchanged) |
| Qwen3.8 (deep variant) | no fixed checkpoint yet | No refreshed checkpoint: 2026-11-07 commits are README/response-template only; Unsloth added UD3.1 quant files 2026-11-10/11 (weights blob unchanged) | 2026-11-11 | **current.** Phone-home finding open; **Arete-27B is the first value-aligned Qwen3.8-27B derivative** (see §New entries) |
| Kolibri-1 | watch, Q4 no fit | Unchanged (`Aleph-Alpha` org sweep). huihui Kolibri-abliterated GGUF (2026-10-06) does not change the fit problem | 2026-10-06 | **current (watch)** |
| GLM-Z1 / Magistral-Small-2509 (council variants) | unchanged | No newer GLM-Z1 or Magistral in window (zai-org / mistralai sweeps) | — | **current** |

### 3. general-fast (auto-daily::fast; tools-specialist default)

Seat: `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-ctx96k` + oMLX `unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit`.
Screen challenger already registered in `config/backends.yaml`: LFM2.5-24B-A2B UD-Q4_K_XL-ctx96k.

| Family / entry | 10-29 said | Newest as of 2026-11-11 | Date | Status |
|---|---|---|---|---|
| Qwen3.6-35B-A3B (seat) | current, no 3.6.5/3.7 | Same checkpoint. Qwen repo 2026-11-07 bump = "Add a response template and generation tags (#81)" (transformers-side; the seat's unsloth GGUF unchanged 2026-04-20) | 2026-11-07 | **current** |
| LFM2.5-24B-A2B (queued screen) | screen head, not superseded by LFM3 | Same checkpoint; card gained IFBench + community HLE/SWE-bench-Verified/GPQA results 2026-11-03 (weights unchanged; unsloth GGUF modified 2026-10-20) | 2026-11-03 | **current — screen stands** |
| Clover-35B-A3B-Preview | not named | `Diffuspace/Clover-35B-A3B-Preview`: 34.66B / ~3B active, base Qwen3.6-35B-A3B, block diffusion, 128K, Apache 2.0; GGUF Q4_K_M 23.00 GB; no MLX; needs its own inference path (HF impl, SGLang/llama.cpp self-speculative) | 2026-10-24 | **newly relevant, runtime-gated** (watch) |
| LiquidCode-2.5-24B-A2B | not named | `ItachiSan/LiquidCode-2.5-24B-A2B`: LFM2.5-24B-A2B finetune, 23.97B; bartowski GGUF 2026-11-10, Q4_K_M 15.35 GB; no MLX | 2026-11-03 | **newly relevant (watch)** — only if the LFM2.5 screen itself passes |
| Gemma 4 (gemma-fast variant) | current | E4B tokenizer remediation 2026-11-03 (weights unchanged); 26B-A4B-it + QAT repos unchanged 2026-07-20 | 2026-11-03 | **current** |
| Nemotron 3.5 Lightning (daily variant) | in fleet | No newer Lightning found in nvidia/unsloth sweeps; nvidia repo API returned 401 for the direct lookup (treated as "no new checkpoint seen", not as absence) | — | **current** |

### 4. tools-specialist

Seat: default shares §3; fast variant `gemma4:e4b-it-qat-ctx8k`. Registered s8 challengers:
LFM3-1.7b QAD-Q4_0 and Nemotron Bolt E4B UD-Q4_K_XL (both in `config/backends.yaml`).

| Family / entry | 10-29 said | Newest as of 2026-11-11 | Date | Status |
|---|---|---|---|---|
| LFM3-1.7B (queued screen) | vendor GGUF only, no Unsloth | Unchanged; mlx-community `LFM3-1.7B-OptiQ-4bit` (2026-10-28) and `LFM3-VL-2B-OptiQ-4bit` (2026-10-30) exist. Still no `unsloth/LFM3-1.7B-GGUF` | 2026-10-28 | **current — screen stands** |
| Nemotron 3.5 Bolt E4B (queued, "only if LFM3 doesn't win"; MLX pending) | lmstudio MLX 4bit | **MLX condition cleared:** `mlx-community/NVIDIA-Nemotron-3.5-Bolt-E4B-OptiQ-4bit` (2026-10-24) | 2026-10-24 | **current — queue item now fully actionable** |
| Dory1.0-4B | not named | `nvidia/NVIDIA-Nemotron-Labs-Dory1.0-4B(-GGUF)`: 4B looped latent-recurrent, 256K, OpenMDW-1.1, official GGUF Q5_K_M 3.67 GB; no mlx-community (community MLX 8bit only, 2026-10-17) | 2026-10-16 | **newly relevant, engine-gated** |
| Mellum 2.1 (queued for coding fast-repair; MLX pending) | official GGUF 8.07 GB Q4_K_M | GGUF unchanged; **MLX gap filled** `mlx-community/Mellum2.1-12B-A2.5B-Thinking-6bit` (2026-10-11); official MTP repo `JetBrains/Mellum2.1-12B-A2.5B-Thinking-MTP` (2026-10-30, 12.15B, Apache 2.0) = oMLX speculative option | 2026-10-30 | **current — queue item upgraded** |

### 5. reading (auto-compliance::reading, compliance-mapping, -overflow, auto-documents)

Seat: `gemma4:26b-a4b-it-q4_K_M-ctx128k` (plain) / `...-qat-ctx64k` (overflow; QAT also selected
for auto-documents + bench 2026-11-06 per `config/backends.yaml` keep_reason — live-config
evolution, not an HF change).

| Family / entry | 10-29 said | Newest as of 2026-11-11 | Date | Status |
|---|---|---|---|---|
| Gemma 4 26B-A4B (seat) | current, no refresh since 2026-07-20 | Unchanged (`lastModified` 2026-07-20). No Gemma 5; the ai.google.dev releases page's newest entry (2026-10-06) is the EmbeddingGemma 2 740M release, not a chat model | 2026-07-20 | **current** |
| LFM2.5-24B-A2B (only challenger) | screen after general-fast answers always-think | unchanged (see §3) | 2026-11-03 | **current — sequencing stands** |

### 6. coding (auto-coding)

Live seat map (HEAD wins): default `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k` (oMLX twins
Qwen3.8-27B-oQ4e-mtp / Huihui-Qwen3.6-27B-abliterated-MLX-4bit / Qwen3.8-27B-4bit DFlash2);
variants laguna-xs21, kat-coder fast-repair, agentworld lite, ornith, devstral, glm-4.7-flash,
hauhaucs, gemma4-heretic, northmini, omnicoder2. Registered s8 challenger: Flint UD-Q4_K_XL-ctx256k.

| Family / entry | 10-29 said | Newest as of 2026-11-11 | Date | Status |
|---|---|---|---|---|
| Flint (queued screen) | coding-seat candidate, vendor benches only | Unchanged (`RecursiveSI/flint` 2026-10-21; unsloth UD-Q4_K_XL 25.05 GB re-verified today; mlx-community oQ2e–oQ8e completed 2026-10-27) | 2026-10-27 | **current — screen stands** |
| Qwen3.8-27B (default + qwen38coder) | phone-home finding; watch for refresh | No refreshed checkpoint (see §2) | 2026-11-11 | **current** |
| KAT-Coder V2.5-Dev (fast-repair seat) | current | Unchanged (repo 2026-07-23 / 07-28) | 2026-07-28 | **current** |
| Mellum 2.1 (queued for fast-repair) | MLX pending | See §4 — MLX + MTP now exist | 2026-10-30 | **current — queue item upgraded** |
| Laguna XS-2.1 (laguna variant) | current, no 2.2 | Unchanged (2026-06-20 / 08-19). Bigger sibling Laguna-S-2.1 exists (2026-07-13, GGUF) — pre-window, no seat asks for it | 2026-08-19 | **current** |
| Huihui-Qwen3.8-27B-Coder390-EfficientThink-abliterated | not named | nerkyor Qwen3.8-27B-Coder390 mega-finetune, huihui-abliterated; 27.78B, Apache 2.0 (inherited); GGUF IQ3_S 12.14 GB + bf16 54.66 GB, mmproj present (no Q4 file) | 2026-10-11 (GGUF 10-14) | **newly relevant (watch)** for the uncensored-coder variants; only a 3-bit GGUF exists |
| Devstral-Small-2 / GLM-4.7-Flash / AgentWorld / North-Mini-Code / omnicoder2 (variants) | — | All unchanged (2512 repo modified 2026-07-15; GLM-4.7-Flash 2026-01-19/29; AgentWorld 2026-06-25; North-Mini-Code 2026-06-18) | — | **current** |

### 7. vision (auto-vision)

Seat: `qwen3-vl:32b-ctx8k` (Thinking); variants gemma_vision (31B QAT) + gemma4jangvision.

| Family / entry | 10-29 said | Newest as of 2026-11-11 | Date | Status |
|---|---|---|---|---|
| Qwen3-VL (seat) | current; 30B-A3B-Thinking pre-registered replacement | No official successor in window (newest official Qwen3-VL items remain 2025-10/2026-01; no Qwen3.5-VL/4-VL). `Qwen/Qwen3-VL-32B-Thinking` unchanged 2025-10-21 | 2025-10-21 | **current** |
| ZwZ2 (inclusionAI) | not named | `inclusionAI/ZwZ2-9B` is image-text-to-text (9.41B, base Qwen3.5-9B, license field empty); official GGUFs 2026-10-30; Surgical-Abliterated GGUF 2026-10-30 | 2026-10-30 | **newly relevant (watch)** — vision projector support in Ollama unverified; not a 32B-seat successor |
| Nemotron Bolt 74B-A9B / Super VL | watch / no fit | Unchanged (no new quants in window) | 2026-10-14 | **current (watch)** |
| MiniMax-H3-Image | — | `MiniMaxAI/MiniMax-H3-Image` (2026-11-03) + PE variant (2026-11-08): image generation, not a VL chat seat | 2026-11-08 | out of seat scope |

### 8. Other roles the live config shows

| Role / seat | Family newest as of 2026-11-11 | Date | Status |
|---|---|---|---|
| auto-general-uncensored (Huihui-Qwen3.6-35B-A3B-abliterated q4_K_M) + creative/throwaway variants (hauhaucs, gemma4-heretic, ornith15) | **Arete-27B (2026-11-06) is the window's genuine candidate here** (see below). HauhauCS line unchanged (Apr–Jun 2026 builds). `ornith-ai/Ornith-1.5-35B-A3B` unchanged 2026-08-23. Qwen3.8-40B-Ultimate-Heretic-Uncensored (DavidAU, Q4_K_M 24.20 GB) newly relevant as a community-merge challenger. huihui GLM-5.3-abliterated (10-29) and V4.1-Flash-1017-abliterated (10-25) exist but do not fit | 2026-11-10 | seat **current**; Arete + DavidAU newly relevant |
| auto-security (VulnLLM-R-7B; councils granite4.1 8b/30b, qwen3.6:27b ctx4k, mistral-small3.2:24b, Foundation-Sec-8B-Reasoning; redteam/purpleteam huihui 9b / supergemma4-26b) | All seat families unchanged (Foundation-Sec GGUF 2026-01-28; granite-4.1 2026-05-04; no Mistral Small 3.3). Window additions: `FrostWolfAI_Frost-Cyber-Mini-Uncensored-v1.1-GGUF` Q4_K_M 2.62 GB (2026-11-07), `mradermacher/Cyber-Ornith-1.5-9B-OBLITERATED` (2026-09-25, pre-window edge), BaronSecurity BaronLLM GGUF re-upload (2026-10-30, dl 336) | 2026-11-07 | seats **current**; Frost-Cyber-Mini newly relevant (watch, tiny) |
| auto-research (Nex-N2-mini UD-Q4_K_M; data = Qwen3.6-35B ctx32k) | **superseded:** `nex-agi/Nex-N2.5-mini` (2026-09-08, 35.11B, Apache 2.0; bartowski GGUF 2026-09-11, Q4_K_M 22.32 GB; mlx OptiQ-4bit 2026-09-12). And the seat's GGUF source org `sjakek` is empty (see risks). ZoomGain-4B/9B + GGUFs (2026-11-10/11, cards empty); LBS-27B (2026-10-26, role unexamined); Ling-3.0-tiny-UBTree (2026-10-21) is an MIT addon on the seated Ling-3.0-tiny base (183M safetensors total) | 2026-11-11 | **superseded — screen + provenance fix** |
| auto-spl (Qwen3.8-27B-oQ4e-mtp; nano = orcacyber-nano-1.0) | No new Qwen3.8 checkpoint; orcacyber-nano-1.0 has no in-window successor found in sweeps | — | **current** |
| auto-audio (gemma4:12b-it-qat; media variants granite4.1:8b / lfm2.5:8b) | Gemma 4 unchanged; no Granite text successor; LFM2.5-8B-A1B line unchanged (gaston uncensored GGUF 2026-08 era) | — | **current** |
| compliance councils (deepseek-r1-0528-qwen3-8b; magistral-2509; GLM-Z1-32B) | No successors in window (mistralai/zai-org/deepseek-ai sweeps) | — | **current** |
| orchestration arm (fast = auto-daily::gemma-fast; deep = auto-daily::deep; shadow = portal5/spark-x2.6) | Gemma 26B QAT unchanged; Qwen3.8 unchanged; **Spark-X2.6 family active in window**: `XHToken/Spark-X2.6-4B` (2026-10-19, 4.11B, Apache 2.0, own base; README updates 2026-11-06), 1.7B same day, bartowski GGUFs (10-20 / 10-31), abliterated variants (10-22 / 10-29), mlx OptiQ-4bit (10-24) | 2026-11-06 | seats **current**; shadow-seat family evolving |
| platform embedder (EmbeddingGemma 2 :8946) | `google/embeddinggemma-2` unchanged (2026-09-14); the Gemma releases page entry 2026-10-06 is the 740M release of the same model family | 2026-10-06 | out of chat-seat scope; current |

---

## New entries (fit + screen shape)

### Arete-27B — newly relevant, uncensored + Qwen3.8 value-aligned line

- Repo `NousResearch/Arete-27B` (created 2026-11-06; blog <https://nousresearch.com/arete>,
  dated 2026-11-06). 27.36B dense on Qwen3.8-27B, SFT only (no RL/DPO), text-only, 64k
  training context, Apache 2.0.
- Quant: **GGUF `bartowski/NousResearch_Arete-27B-GGUF:Q4_K_M` = 17.20 GB** (IQ4_XS 15.24 GB,
  Q5_K_M 20.68 GB) — fits beside the router. MLX `mlx-community/Arete-27B-OptiQ-4bit`
  created **2026-11-11** (same day as this survey; contents not inspected).
- Community derivatives: SargeDev Uncensored GGUF (11-07), mradermacher Heretic-ARA (11-09),
  SolsticeAI Unlocked-Uncensored-Heretic (11-10) — all unproven.
- Benchmarks: vendor-run Propaganda Eval (fact 2.32 → 2.98 / 5; propaganda answers 22% →
  0.9%); "no meaningful regression" on general/agentic benches is the vendor's claim. No
  independent score found. **For the uncensored seat the benchmark that matters is refusal
  behavior + tool-call JSON discipline on this stack — neither is evidenced yet.**
- Caveat: inherits the Qwen3.8 lineage — the egress half of the phone-home finding is **not**
  addressed by a value-alignment SFT. Treat as "needs an A/B", never a verdict.

### Nex-N2.5-mini — supersedes the research default's family

- `nex-agi/Nex-N2.5-mini` (2026-09-08; announcement <https://nex-agi.com/> dated 2026-09-08).
  35.11B, Apache 2.0; agentic family positioning (computer use / browsing / visually grounded
  agents, per the nex-agi card). GGUF `bartowski/nex-agi_Nex-N2.5-mini-GGUF:Q4_K_M` 22.32 GB
  (2026-09-11); MLX `mlx-community/Nex-N2.5-mini-OptiQ-4bit` (2026-09-12) — both fit.
- Benches are vendor-run on the agentic suites; independent evidence not found. The research
  seat's job (long-horizon data/research tasks) maps to agentic/tool benches — exactly where
  vendor-run numbers deserve the most skepticism.
- The incumbent's GGUF hint (`hf.co/sjakek/Nex-N2-mini-GGUF`) points at an empty org — this
  screen doubles as the provenance repair path (operator decision required either way).

### NVIDIA Nemotron Labs Dory1.0-4B — newly relevant, tools-fast, engine-gated

- `nvidia/NVIDIA-Nemotron-Labs-Dory1.0-4B` + `-GGUF` (2026-10-16; card states release date
  October 16, 2026). 4B total, looped latent-recurrent normalized-GPT, SWA+full-attention
  hybrid, 256K ctx, English, OpenMDW-1.1. Official GGUF Q5_K_M **3.67 GB**. No mlx-community
  build; community MLX 8bit (2026-10-17) and a heretic GGUF (2026-10-27) exist.
- Card positioning: "general-purpose reasoning on a small footprint"; no tool-calling claim
  seen in the card summary. **Gate:** a live probe that the looped architecture runs and calls
  tools on Ollama 0.40 / oMLX before any screen is queued — new architecture classes have
  broken parsers here before (Laguna 500 note in `config/backends.yaml`).

### Clover-35B-A3B-Preview — newly relevant, runtime-gated (watch)

`Diffuspace/Clover-35B-A3B-Preview` (2026-10-24; blog <https://diffuspace.ai/blog/clover-35b/>,
undated page). 34.66B / ~3B active on the seated Qwen3.6-35B-A3B backbone, block diffusion +
LowConfidence decoding, 128K, Apache 2.0. GGUF Q4_K_M 23.00 GB (2026-10-28 community quants;
bartowski 2026-11-03); no MLX. Vendor agentic benchmarks (blog) — vendor-run. Whether
Ollama 0.40 or oMLX can serve a diffusion LM at all is unverified; a successful GGUF load on
this stack is the precondition for any screen.

### Window community-watch shelf (fits, unproven, no queue slot)

| Entry | Date | Size (file measured today) | Note |
|---|---|---|---|
| `DavidAU/Qwen3.8-40B-Ultimate-Heretic-Uncensored` (+Build2; mradermacher GGUFs 11-10) | 2026-10-22 / 11-03 | Q4_K_M 24.20 GB | community merge expansion of Qwen3.8-27B; phone-home lineage caveat; unscreened merge quality |
| `ItachiSan/LiquidCode-2.5-24B-A2B` (bartowski GGUF 11-10) | 2026-11-03 | Q4_K_M 15.35 GB | LFM2.5 finetune; relevant only as a variant of the already-queued LFM screen; derivative license listed apache-2.0 over an LFM-Open base — verify before any use |
| `TheDrummer/Spectre-37B-v1` (bartowski GGUF 11-07) | 2026-11-06 | Q4_K_M 23.17 GB | creative/roleplay candidate for the uncensored-creative slot; license field empty on HF API — unknown |
| `huihui-ai/Huihui-Qwen3.8-27B-Coder390-EfficientThink-abliterated(-GGUF)` | 2026-10-11 / 10-14 | IQ3_S 12.14 GB (no Q4) | uncensored-coder watch; 3-bit-only GGUF and mmproj present |
| Spark-X2.6-4B abliterated (`SC117` 10-22, `FrostWolfAI` 10-29) | 2026-10-29 | not measured | shadow-seat family; only if the spark-x2.6 shadow seat itself earns a screen |
| `inclusionAI` ZwZ2 (GGUFs 10-30) / ZoomGain (11-10/11) / LBS-27B (10-26) | 2026-11-11 | not measured | cards essentially empty; roles undefined; ZoomGain GGUFs are day-old |
| `inclusionAI/Ling-3.0-tiny-UBTree` | 2026-10-21 | 183M safetensors total | MIT addon variant on the seated Ling-3.0-tiny base; watch |

### No-fit shelf (window updates that do not change a 64 GiB seat)

`moonshotai/Kimi-K3.1-Pro` (2026-11-02, 2.78T, kimi-k3.1-pro license; unsloth 2026-11-04) ·
`mistralai/Mistral-Large-4-1T-A52B` (weights now up; 1T/52B active; unsloth GGUF 2026-10-29) ·
`ornith-ai/Ornith-1.5-122B` (2026-10-16, MIT, 125B; unsloth GGUF 2026-10-20) ·
`unsloth/MiniMax-M3.1-Flash-GGUF` (2026-10-23) · huihui GLM-5.3 / V4.1-Flash-1017
abliterated (10-29 / 10-25) · `MiniMaxAI/MiniMax-H3-Image` (11-03, image gen) — all confirmed
present, none fit beside the router.

---

## Fleet-provenance risks (findings, not screens)

1. **`hf.co/deepreinforce-ai/Ornith-1.0-35B-GGUF`** (auto-coding::ornith hint) — the
   `deepreinforce-ai` org returns zero models; the family lives at `ornith-ai`
   (`Ornith-1.0-35B-GGUF` there, created 2026-06-25). Verified twice: author API and search
   API. Local tag keeps serving; a re-pull of the hint as written would fail.
2. **`hf.co/sjakek/Nex-N2-mini-GGUF`** (auto-research default hint) — `sjakek` org returns
   zero models; originals at `nex-agi` / `bartowski`. Verified twice, same method. The seat is
   also family-superseded (Nex-N2.5-mini above).
3. **Gemma 4 E4B/E2B tokenizer remediation (2026-11-03)** post-dates the router's OBLITERATED
   build (2026-10-06). Whether the abliterated rebuild should be regenerated on the fixed
   tokenizer is an operator call; JSON-discipline re-probe would be required either way
   (matches the landscape's standing "verify installed blob vs refreshed checkpoint" item).

Both org moves pre-date or straddle the window; they surfaced here because this survey is the
first to sweep the GGUF-source orgs of every seated hint.

---

## Proposed screen queue (hypotheses for live screens; one bench at a time, replace in place, delete the loser)

1. **Nex-N2.5-mini** — research default (superseded family + broken GGUF source).
   `nex-agi/Nex-N2.5-mini` · GGUF `bartowski/nex-agi_Nex-N2.5-mini-GGUF:Q4_K_M` 22.32 GB ·
   MLX `mlx-community/Nex-N2.5-mini-OptiQ-4bit`. Worth a screen because the role has no
   challenger since June and the incumbent's upstream is gone. Vendor-run agentic benches only.
2. **Arete-27B** — uncensored default (vs Huihui-Qwen3.6-35B-A3B-abliterated) and the first
   value-aligned Qwen3.8-27B derivative. `NousResearch/Arete-27B` · GGUF
   `bartowski/NousResearch_Arete-27B-GGUF:Q4_K_M` 17.20 GB · MLX
   `mlx-community/Arete-27B-OptiQ-4bit` (2026-11-11, inspect before any pull). Worth a screen
   because refusal behavior is this role's core metric and the vendor claims a measured
   refusal collapse; JSON discipline is the known unknown. Not a phone-home fix.
3. **Mellum 2.1** (carried) — coding fast-repair; the 10-29 blocker (no MLX) is gone.
   `JetBrains/Mellum2.1-12B-A2.5B-Thinking-GGUF:Q4_K_M` (8.07 GB, measured 2026-10-28) ·
   MLX `mlx-community/Mellum2.1-12B-A2.5B-Thinking-6bit` (2026-10-11) · MTP
   `JetBrains/Mellum2.1-12B-A2.5B-Thinking-MTP` (2026-10-30) as the oMLX acceleration option.
4. **Flint** (carried, unchanged) — coding pair. `RecursiveSI/flint` · GGUF
   `unsloth/flint-GGUF:UD-Q4_K_XL` 25.05 GB · MLX `mlx-community/flint-oQ4e` (23.35 GB,
   measured 2026-10-28). Vendor benches only.
5. **LFM2.5-24B-A2B** (carried, unchanged) — general-fast + tools default. `LiquidAI/LFM2.5-24B-A2B` ·
   GGUF `unsloth/LFM2.5-24B-A2B-GGUF:UD-Q4_K_XL` 14.88 GB · MLX
   `LiquidAI/LFM2.5-24B-A2B-MLX-4bit` 13.56 GB (sizes measured 2026-10-28).
6. **Nemotron 3.5 Bolt E4B** (carried; now dual-engine) — tools-fast fallback if 5 doesn't
   win. GGUF `unsloth/NVIDIA-Nemotron-3.5-Bolt-E4B-GGUF:UD-Q4_K_XL` (5.06 GB, 2026-10-28) ·
   MLX `mlx-community/NVIDIA-Nemotron-3.5-Bolt-E4B-OptiQ-4bit` (2026-10-24).
7. **Dory1.0-4B** — only after a live probe proves the looped architecture loads and calls
   tools on this stack. `nvidia/NVIDIA-Nemotron-Labs-Dory1.0-4B-GGUF:Q5_K_M` 3.67 GB.

Watch (no slot): Clover (runtime-gated), LiquidCode (only if the LFM screen wins), Spectre
(creative slot, license unknown), Qwen3.8-40B-Ultimate (community merge), Spark-X2.6
abliterated variants, Coder390 (3-bit only), ZwZ2 / ZoomGain / LBS-27B (cards undefined),
Ling-3.0-tiny-UBTree, Gemma 4 E4B OBLITERATED tokenizer rebuild (maintenance decision).

---

## Provenance

- Hugging Face API (models, commits, tree) pulls dated 2026-11-11 for every repo named above;
  file sizes from tree listings pulled 2026-11-11 except where marked "measured 2026-10-28"
  (carried from the 10-29 snapshot).
- `nex-agi/Nex-N2.5-mini` card + <https://nex-agi.com/> (2026-09-08).
- Arete: `NousResearch/Arete-27B` card + <https://nousresearch.com/arete> (2026-11-06).
- Clover: `Diffuspace/Clover-35B-A3B-Preview` card + <https://diffuspace.ai/blog/clover-35b/>.
- Dory: `nvidia/NVIDIA-Nemotron-Labs-Dory1.0-4B-GGUF` card (release date 2026-10-16).
- Gemma: <https://ai.google.dev/gemma/docs/releases> (newest entry 2026-10-06) and the
  `google/gemma-4-E4B-it` commit page (commit #50, 2026-11-03, glitch-token remediation).
- Liquid: <https://www.liquid.ai/blog> index (newest post 2026-10-27 — nothing newer in window).
- Org-vanish checks: `https://huggingface.co/api/models?author=deepreinforce-ai` and
  `?author=sjakek` (both empty), cross-checked with model-search API for "Ornith" /
  "Nex-N2-mini" (both families alive under `ornith-ai` / `nex-agi`).
- Live seat map: `config/backends.yaml`, `config/portal.yaml` (workspaces + variants +
  `orchestration_arm`), `config/bench_workspaces.yaml` at HEAD `62563585f`.
- Web-search integration was unavailable during this survey; no secondary-news cross-check
  was performed. Where a vendor page could not be fetched, the claim is marked as HF-metadata
  only.
