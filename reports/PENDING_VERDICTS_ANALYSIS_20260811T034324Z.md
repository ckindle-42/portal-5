# Pending model verdicts — informed-decision analysis (2026-08-11 03:43 UTC)

61 pending entries, 759.7 GB total.

## ⚠ Stack boundary in effect

**Boundary date: 2026-08-07** (`--stack-boundary-days=3`).

The Ollama + oMLX inference stack has changed materially. Evidence
captured before the boundary was measured under a prior stack and
**does not reflect current behavior**. TPS/quality averages here
are post-boundary-only. Numeric-driven decline verdicts require
≥1 post-boundary row — otherwise the hypothesis defaults to
`investigate-refresh` (re-bench required).

- models with NO post-boundary evidence: **59 / 61** (of which 11 have only pre-boundary rows)

**Closeout reports from before the boundary are surfaced but are
NOT treated as authoritative** — the human decided on numbers
that no longer hold. Re-affirm any pre-boundary closeout signal
against a fresh bench before treating it as current guidance.

## Purpose

Every pending model was pulled with intent. The evidence miner
(`pending_verdicts_evidence.py`) gave the numbers; this report gives
the *context*: why the model was pulled, what it does, where it sits
in the fleet, what the model card advertises vs how we actually
slotted it, what disappears on removal, and whether the fleet's
arch/vendor diversity survives.

The hypothesis at the top of each entry is a mechanical score across
the axes below. It is **not authoritative**. Read the sections; write
the verdict as a paragraph across the axes.

## KEEP signals across the backlog (attend to these before declining)

- models where removal ends the fleet's only exploration of that arch: **11**
- models with a net-new signal (arch/vendor/capability not in fleet): **21**
- models whose removal drops their arch family from the fleet entirely: **11**
- models with a distinctive capability (MoE / MTP / vision / abliteration / etc.): **14**
- models where the card advertises capabilities we HAVEN'T tested (probe first): **33**

## Model card cache coverage

- Cards available for analysis: **53 / 61**

## Re-bench work required (grouped by capability)

Total models needing re-bench (no post-boundary evidence): **59 / 61**
Of those, models blocked by workspace slot issues (must fix config before benching): **39**

**Category distribution** — group re-bench work by shared harness/prompt-corpus:

- `vision` (Vision / multimodal (non-CUA)): **25 models, 351.5 GB**
- `general` (General / no specific capability advertised): **13 models, 125.6 GB**
- `reasoning-explicit` (Explicit reasoning / thinking traces): **9 models, 96.2 GB**
- `mtp-speculative` (MTP / speculative drafting): **5 models, 89.2 GB**
- `security-tooling` (Security tooling (exploit / artifact generation)): **2 models, 22.9 GB**
- `agent-toolcall` (Agent / tool-use tuned): **2 models, 24.0 GB**
- `abliterated` (Abliterated / uncensored): **2 models, 9.7 GB**
- `moe` (MoE architecture): **1 models, 17.7 GB**

⚠ **Slot-fix priority list** — models where the workspace config prevents valid benching regardless of prompt corpus:

- `qwen3.6:27b-q8_0` — 2 fix(es): model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-qwen3.6`)
- `qwen3.6:35b-a3b-q4_K_M` — 2 fix(es): `bench-qwen36-35b-a3b`: needs vision projector (`mmproj`) — the bench cannot produce valid multimodal data without it
- `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL` — 3 fix(es): `bench-qwen36-35b-a3b-ud`: needs vision projector (`mmproj`) — the bench cannot produce valid multimodal data without it
- `hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-GGUF:Q4_K_M` — 2 fix(es): `bench-huihui-qwen36-35b-a3b`: needs vision projector (`mmproj`) — the bench cannot produce valid multimodal data withou
- `hf.co/Mia-AiLab/Qwable-3.6-35b:Qwable-3.6-35b_q4_k_m.gguf` — 2 fix(es): model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-Qwable-3.6-35b`)
- `hf.co/Abiray/Agents-A1-Q4_K_M-GGUF:Q4_K_M` — 1 fix(es): `bench-agents-a1`: `predict_limit` needs to accommodate high enough to fit thinking traces (8k+ typical)
- `hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf-ctx64k` — 1 fix(es): **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is unte
- `deepseek-r1:32b-q4_k_m` — 2 fix(es): model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-deepseek-r1`)
- `hf.co/Jackrong/Qwopus3.6-27B-v2-MTP-GGUF:Qwopus3.6-27B-v2-MTP-Q5_K_M.gguf` — 1 fix(es): card advertises reasoning traces but no slot has `emits_reasoning: true` — advertised capability untested
- `gemma4:31b-it-qat-ctx8k` — 2 fix(es): model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-gemma4`)
- `gemma4:31b-it-qat` — 1 fix(es): card advertises reasoning traces but no slot has `emits_reasoning: true` — advertised capability untested
- `gemma4:26b-a4b-it-q4_K_M` — 3 fix(es): `bench-gemma4-26b-optiq`: needs vision projector (`mmproj`) — the bench cannot produce valid multimodal data without it
- `hf.co/bartowski/Qwen_Qwen3.6-27B-GGUF:Q4_K_M` — 2 fix(es): `bench-qwen36-27b-optiq`: MTP benching requires paired draft model config — check `predict_limit` and draft binding
- `qwen3.6:27b-mtp-q4_K_M` — 2 fix(es): model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-qwen3.6`)
- `hf.co/mradermacher/gemma-4-26B-A4B-it-uncensored-heretic-GGUF:gemma-4-26B-A4B-it-uncensored-heretic.Q4_K_M.gguf` — 2 fix(es): model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-gemma-4-26B-A4B-
- `sylink/sylink:8b-ctx8k` — 1 fix(es): **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is unte
- `phi4:14b-q8_0` — 2 fix(es): model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-phi4`)
- `mistral-small3.2:24b` — 2 fix(es): model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-mistral-small3.2
- `devstral-small-2:latest-ctx8k` — 2 fix(es): model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-devstral-small-2
- `devstral:24b` — 2 fix(es): `bench-devstral`: needs vision projector (`mmproj`) — the bench cannot produce valid multimodal data without it
- `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL-ctx64k` — 2 fix(es): model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-GLM-4.7-Flash-RE
- `gpt-oss:20b` — 1 fix(es): `bench-gptoss`: `predict_limit` needs to accommodate high enough to fit thinking traces (8k+ typical)
- `hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0` — 1 fix(es): `bench-foundation-sec-8b-reasoning`: `predict_limit` needs to accommodate high enough to fit thinking traces (8k+ typica
- `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-9B-MTP-GGUF:Q4_K_M` — 2 fix(es): `bench-jackrong-dsv4-9b`: needs vision projector (`mmproj`) — the bench cannot produce valid multimodal data without it
- `hf.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF:Q4_K_M` — 1 fix(es): `bench-gemma4-12b-agentic`: MTP benching requires paired draft model config — check `predict_limit` and draft binding
- `gemma4:e4b-it-qat-ctx8k` — 2 fix(es): model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-gemma4`)
- `gemma4:e4b-it-qat` — 1 fix(es): card advertises reasoning traces but no slot has `emits_reasoning: true` — advertised capability untested
- `dolphin-llama3:8b` — 2 fix(es): model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-dolphin-llama3`)
- `hermes3:8b` — 2 fix(es): model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-hermes3`)
- `huihui_ai/gemma-4-abliterated:E2b-qat-ctx8k` — 2 fix(es): model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-gemma-4-ablitera
- `huihui_ai/gemma-4-abliterated:E2b-qat` — 4 fix(es): `bench-e2b-pentest`: needs vision projector (`mmproj`) — the bench cannot produce valid multimodal data without it
- `hf.co/Andycurrent/Mistral-7B-Uncensored-GGUF:Q4_K_M` — 3 fix(es): `bench-mistral7b-uncensored`: needs `emits_reasoning: true` — otherwise reasoning trace is suppressed
- `gemma4:e2b-it-qat-ctx8k` — 2 fix(es): model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-gemma4`)
- `gemma4:e2b-it-qat` — 1 fix(es): card advertises reasoning traces but no slot has `emits_reasoning: true` — advertised capability untested
- `llama3.2:3b-instruct-q8_0-ctx8k` — 1 fix(es): **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is unte
- `cybersecqwen-4b-toolfix:latest` — 1 fix(es): `bench-cybersecqwen-4b-toolfix`: needs `emits_reasoning: true` — otherwise reasoning trace is suppressed
- `llama3.2:3b` — 1 fix(es): **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is unte
- `hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF:latest` — 1 fix(es): **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is unte
- `hf.co/Nguuma/security-slm-unsloth-1.5b:latest` — 1 fix(es): `bench-security-slm-1p5b`: `predict_limit` needs to accommodate high enough to fit thinking traces (8k+ typical)

## Hypothesis histogram (not authoritative)

- `investigate-refresh`: 59 models, 736.8 GB
- `investigate`: 1 models, 19.7 GB
- `keep-open`: 1 models, 3.2 GB

## How to record a verdict

Open `config/PENDING_MODEL_VERDICTS.md`. For each entry, either
leave `- [ ]` or check `- [x]` and add a verdict paragraph that
reasons across the axes. Example:

```
- [x] `qwen3.6:27b-q8_0` — 27.9 GB
  - verdict: decline (bench-orphaned, no active role; Q8 doesn't earn 2x
    memory over Q4_K_M peer; no coverage gap — Q4_K_M and Q6_K remain;
    no diversity loss — Qwen3.6 family still 3-strong; TPS 12.3 below 20 floor)
```

The executor writes that reason **verbatim** into the DROPPED catalog
stub, so the reasoning is documented permanently in the wiki spine —
not just in this report file, which lives in `reports/` (gitignored).

Sorted biggest-reclaim-first below.

## `portal5/qwen3.6-27b-mtp:q8_0-drafted` — 43.6 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - capability: MTP speculative drafting (draft model bound to base)
- **What we'd gain:** 43.6 GB disk

### Intake rationale

- **Intake age:** 46d ago (first-seen commit `84c15f78`)
- **Mentioned in 4 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `portal5/deepwen-3.6:q4.5-moq-ctx32k` \ - `portal5/gemma4-12b:q4_K_M-ctx8k` \ - `portal5/qwen3.6-27b-mtp:q8_0-drafted` \ - `portal5/xyz-aquila-mini:q4_k_m` \ - `qwen3-coder-next:latest` \ - `qwen3-c…
  - `portal_wiki/canonical/unit-model-catalog-qwen3-6-27b-mtp-q4-k-m.md` — (no nearby heading)
    > --- \  \ `qwen3.6:27b-mtp-q4_K_M` is the Q4 embedded-MTP draft model (~19GB, Alibaba) that feeds `portal5/qwen3.6-27b-mtp:q8_0-drafted`. `config/backends.yaml` registers it in `group: reasoning` with …
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## general (84)
    > - `portal5/deepwen-3.6:q4.5-moq-ctx32k` \ - `portal5/gemma4-12b:q4_K_M-ctx8k` \ - `portal5/qwen3.6-27b-mtp:q8_0-drafted` \ - `portal5/xyz-aquila-mini:q4_k_m` \ - `qwen3-coder-next:latest` \ - `qwen3-c…

### Capability profile

- **Architecture:** Qwen3.6
- **Parameters:** 27B
- **Quantization:** Q8_0
- **Source:** portal5-local-build (`portal5`)
- **Distinguishing features (from tag pattern):**
  - MTP speculative drafting (draft model bound to base)
- **Reversibility:** NOT registry-pullable — local build; reconstruct via original derivation task

### Fleet position

- **Bench workspaces routing here:** `bench-qwen36-27b-mtp`
- **Same-arch (`Qwen3.6`) production workspaces:** 3
  - `huihui_ai/Qwen3.6-abliterated:27b-ctx8k` (via `auto-general-uncensored`)
  - `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k` (via `auto-creative`)
  - `qwen3.6:27b-q4_K_M-ctx16k` (via `auto-council`)
- **Same-arch bench workspaces:** 10
  - `qwen3.6:27b-q4_K_M` (via `bench-qwen36-27b`)
  - `qwen3.6:35b-a3b-q4_K_M` (via `bench-qwen36-35b-a3b`)
  - `qwen3.6:27b-q4_K_M` (via `bench-qwen36-27b-ud`)
  - `huihui_ai/Qwen3.6-abliterated:27b` (via `bench-huihui-qwen36-27b`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `Qwen3.6` workspaces in fleet:** 13
- **Other workspaces from `portal5`:** 3

### Card claims vs our slotting

- **Card status:** local portal5/* build — no external card
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-qwen36-27b-mtp` (🔬 Bench · Qwen3.6-27B MTP (Ollama speculative))
    > Benchmark: portal5/qwen3.6-27b-mtp:q8_0-drafted — Qwen3.6-27B q8_0 base with mtp-q4_K_M draft (speculative decoding via DRAFT directive). Phase-5 MTP A/B vs bench-qwen36-27b (plain q8_0). Run: ./launch.sh apply-mtp-drafts to create the tag before use.

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `mtp-speculative` — MTP / speculative drafting
- **Recommended harness:** MTP-aware bench — draft acceptance rate + wall-time speedup vs base
- **Prompt corpus:** IDENTICAL to base model's bench for direct comparison
- **Metrics to capture (beyond raw TPS):**
  - draft token acceptance rate (headline signal)
  - wall-time speedup vs base model on identical prompts
  - quality parity vs base (any regression kills the value proposition)
- **Do NOT measure (would produce invalid signal for this capability):**
  - raw TPS without comparing to base — meaningless in isolation
- **Workspace slot requirements for valid bench data:**
  - `paired_draft`: draft model config must be present, correct, and pinned to matching base


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest evidence:** 2026-06-28 (43d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `qwen3.6:27b-q8_0` — 27.9 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - nothing distinctive — arch/vendor/capability all remain represented after removal
- **What we'd gain:** 27.9 GB disk

### Intake rationale

- **Intake age:** 46d ago (first-seen commit `84c15f78`)
- **Mentioned in 5 doc file(s):**
  - `docs/HOWTO.md` — ## 6. Security Analysis
    > | `redteam-deep` | Simulation | `supergemma4-26b-uncensored:Q4_K_M-ctx64k` | none | \ | `blueteam` | Research | `granite4.1:8b-ctx8k` | web_search, web_fetch, classify_vulnerability, kb_search, kb_lis…
  - `docs/MTP_BENCH_20260528.md` — # MTP A/B Bench Results — 2026-05-28
    > Hardware: Apple M4 Pro, 64 GB unified memory \ Model: Qwen3.6-27B dense (4-bit trunk) \  \ ## Results
  - `docs/QWEN_TEMPLATE_PROBE.md` — ## Per-model template state
    > | `Jackrong/MLX-Qwopus3.5-27B-v3-8bit` | qwen3.5 | **GREEN** | clean | hf-cache | chat_template.jinja | \ | `Jackrong/MLX-Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-v2-4bit` | qwen3.5 | **GREEN**…

### Capability profile

- **Architecture:** Qwen3.6
- **Parameters:** 27B
- **Quantization:** Q8_0
- **Source:** ollama-library (`ollama-library`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'qwen3.6:27b-q8_0'

### Fleet position

- **Bench workspaces routing here:** none (bench-orphaned)
- **Same-arch (`Qwen3.6`) production workspaces:** 3
  - `huihui_ai/Qwen3.6-abliterated:27b-ctx8k` (via `auto-general-uncensored`)
  - `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k` (via `auto-creative`)
  - `qwen3.6:27b-q4_K_M-ctx16k` (via `auto-council`)
- **Same-arch bench workspaces:** 11
  - `qwen3.6:27b-q4_K_M` (via `bench-qwen36-27b`)
  - `portal5/qwen3.6-27b-mtp:q8_0-drafted` (via `bench-qwen36-27b-mtp`)
  - `qwen3.6:35b-a3b-q4_K_M` (via `bench-qwen36-35b-a3b`)
  - `qwen3.6:27b-q4_K_M` (via `bench-qwen36-27b-ud`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `Qwen3.6` workspaces in fleet:** 14
- **Other workspaces from `ollama-library`:** 41

### Card claims vs our slotting

- **Card source:** `https://ollama.com/library/qwen3.6` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!doctype html> <html class="h-full overflow-y-scroll"> <head> <title>qwen3.6</title>
- **Deployment signals extracted:** vision / multimodal capability advertised, reasoning-trace capability
- **Slotting:** bench-orphaned — nothing routes to this tag
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `vision` — Vision / multimodal (non-CUA)
- **Recommended harness:** vision probe (image → text tasks)
- **Prompt corpus:** image + question pairs across VQA, captioning, OCR
- **Metrics to capture (beyond raw TPS):**
  - VQA accuracy
  - caption quality
  - OCR fidelity if advertised
- **Do NOT measure (would produce invalid signal for this capability):**
  - text-only quality alone — misses the modality that justifies the model
- **Workspace slot requirements for valid bench data:**
  - `mmproj`: vision projector REQUIRED
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-qwen3.6`)
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 1 invalid (pre-boundary)
- **Avg TPS (pre-boundary — INVALID for decisions):** 5.0 — captured under prior stack
- **Newest evidence:** 2026-06-28 (43d) ⚠ **all pre-boundary**
- **Pre-boundary closeout signals (NOT authoritative — re-affirm on current stack):** pass
  - `tests/benchmarks/results/bench_fleet_refresh_v2_report.md`
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `qwen3.6:35b-a3b-q4_K_M` — 22.3 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - capability: MoE architecture (routes tokens to expert subsets)
- **What we'd gain:** 22.3 GB disk

### Intake rationale

- **Intake age:** 46d ago (first-seen commit `84c15f78`)
- **Mentioned in 5 doc file(s):**
  - `docs/HOWTO.md` — ## 6. Security Analysis
    > | `redteam-deep` | Simulation | `supergemma4-26b-uncensored:Q4_K_M-ctx64k` | none | \ | `blueteam` | Research | `granite4.1:8b-ctx8k` | web_search, web_fetch, classify_vulnerability, kb_search, kb_lis…
  - `docs/MTP_BENCH_20260528.md` — # MTP A/B Bench Results — 2026-05-28
    > Hardware: Apple M4 Pro, 64 GB unified memory \ Model: Qwen3.6-27B dense (4-bit trunk) \  \ ## Results
  - `docs/QWEN_TEMPLATE_PROBE.md` — ## Per-model template state
    > | `Jackrong/MLX-Qwopus3.5-27B-v3-8bit` | qwen3.5 | **GREEN** | clean | hf-cache | chat_template.jinja | \ | `Jackrong/MLX-Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-v2-4bit` | qwen3.5 | **GREEN**…

### Capability profile

- **Architecture:** Qwen3.6
- **Parameters:** 35B
- **Quantization:** Q4_K_M (mixed)
- **Source:** ollama-library (`ollama-library`)
- **Distinguishing features (from tag pattern):**
  - MoE architecture (routes tokens to expert subsets)
- **Reversibility:** ollama pull 'qwen3.6:35b-a3b-q4_K_M'

### Fleet position

- **Bench workspaces routing here:** `bench-qwen36-35b-a3b`
- **Same-arch (`Qwen3.6`) production workspaces:** 3
  - `huihui_ai/Qwen3.6-abliterated:27b-ctx8k` (via `auto-general-uncensored`)
  - `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k` (via `auto-creative`)
  - `qwen3.6:27b-q4_K_M-ctx16k` (via `auto-council`)
- **Same-arch bench workspaces:** 10
  - `qwen3.6:27b-q4_K_M` (via `bench-qwen36-27b`)
  - `portal5/qwen3.6-27b-mtp:q8_0-drafted` (via `bench-qwen36-27b-mtp`)
  - `qwen3.6:27b-q4_K_M` (via `bench-qwen36-27b-ud`)
  - `huihui_ai/Qwen3.6-abliterated:27b` (via `bench-huihui-qwen36-27b`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `Qwen3.6` workspaces in fleet:** 13
- **Other workspaces from `ollama-library`:** 40

### Card claims vs our slotting

- **Card source:** `https://ollama.com/library/qwen3.6` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!doctype html> <html class="h-full overflow-y-scroll"> <head> <title>qwen3.6</title>
- **Deployment signals extracted:** vision / multimodal capability advertised, reasoning-trace capability
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-qwen36-35b-a3b` | tools: none | emits_reasoning
    > Benchmark: Qwen3.6-35B-A3B (GGUF, Ollama, Alibaba Apr 2026, 35B total / 3B active MoE, 262K ctx). SWE-bench Verified 73.4%, AIME26 92.7%.
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - card advertises vision/multimodal but no slot text mentions vision, mmproj, or image tasks — advertised capability likely untested
- **Card vs slotting alignment ✓:**
  - card advertises reasoning; slot has `emits_reasoning: true`

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `vision` — Vision / multimodal (non-CUA)
- **Recommended harness:** vision probe (image → text tasks)
- **Prompt corpus:** image + question pairs across VQA, captioning, OCR
- **Metrics to capture (beyond raw TPS):**
  - VQA accuracy
  - caption quality
  - OCR fidelity if advertised
- **Do NOT measure (would produce invalid signal for this capability):**
  - text-only quality alone — misses the modality that justifies the model
- **Workspace slot requirements for valid bench data:**
  - `mmproj`: vision projector REQUIRED
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - `bench-qwen36-35b-a3b`: needs vision projector (`mmproj`) — the bench cannot produce valid multimodal data without it
  - card advertises vision/multimodal but no slot text mentions vision, mmproj, or image tasks — advertised capability likely untested


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest evidence:** 2026-06-21 (50d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL` — 21.7 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - capability: MoE architecture (routes tokens to expert subsets)
  - capability: Unsloth Dynamic quantization
- **What we'd gain:** 21.7 GB disk

### Intake rationale

- **Intake age:** 46d ago (first-seen commit `84c15f78`)
- **Mentioned in 4 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## coding (41)
    > - `hf.co/unsloth/Qwen-AgentWorld-35B-A3B-GGUF:UD-Q4_K_XL` \ - `hf.co/unsloth/Qwen-AgentWorld-35B-A3B-GGUF:UD-Q4_K_XL-ctx64k` \ - `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL` \ - `hf.co/yuxinlu1/gem…
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## coding (41)
    > - `hf.co/unsloth/Qwen-AgentWorld-35B-A3B-GGUF:UD-Q4_K_XL` \ - `hf.co/unsloth/Qwen-AgentWorld-35B-A3B-GGUF:UD-Q4_K_XL-ctx64k` \ - `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL` \ - `hf.co/yuxinlu1/gem…
  - `portal_wiki/canonical/unit-model-catalog-hf-co-unsloth-qwen3-6-35b-a3b-gguf-ud-q4-k-xl.md` — (no nearby heading)
    > id: unit-model-catalog-hf-co-unsloth-qwen3-6-35b-a3b-gguf-ud-q4-k-xl \ kind: what \ title: "MODEL_CATALOG \u2014 `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL`" \ sources: \ - type: code \   path: co…

### Capability profile

- **Architecture:** Qwen3.6
- **Parameters:** 35B
- **Quantization:** Unsloth Dynamic Q4 XL
- **Source:** huggingface (`unsloth`)
- **Distinguishing features (from tag pattern):**
  - MoE architecture (routes tokens to expert subsets)
  - Unsloth Dynamic quantization
- **Reversibility:** ollama pull 'hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL'

### Fleet position

- **Bench workspaces routing here:** `bench-qwen36-35b-a3b-ud`
- **Same-arch (`Qwen3.6`) production workspaces:** 3
  - `huihui_ai/Qwen3.6-abliterated:27b-ctx8k` (via `auto-general-uncensored`)
  - `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k` (via `auto-creative`)
  - `qwen3.6:27b-q4_K_M-ctx16k` (via `auto-council`)
- **Same-arch bench workspaces:** 10
  - `qwen3.6:27b-q4_K_M` (via `bench-qwen36-27b`)
  - `portal5/qwen3.6-27b-mtp:q8_0-drafted` (via `bench-qwen36-27b-mtp`)
  - `qwen3.6:35b-a3b-q4_K_M` (via `bench-qwen36-35b-a3b`)
  - `qwen3.6:27b-q4_K_M` (via `bench-qwen36-27b-ud`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `Qwen3.6` workspaces in fleet:** 13
- **Other workspaces from `unsloth`:** 3

### Card claims vs our slotting

- **Card source:** `https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF/raw/main/README.md` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <div> <p style="margin: 0 0 0px 0; margin-top: 0px;"> <em>See <a href="https://unsloth.ai/docs/basics/unsloth-dynamic-v2.0-gguf">Unsloth Dynamic 2.0 GGUFs</a> for our quantization benchmarks.</em> </p> <div style="display: flex; gap: 5px; align-items: center; margin-bottom: 0px;"> <a href="https://github.com/unslothai/unsloth/"> <img src="https://github.com/unslothai/unsloth/raw/main/images/unsloth%20new%20logo.png" width="133"> </a> <a href="https://discord.gg/unsloth"> <img src="https://github.com/unslothai/unsloth/raw/main/images/Discord%20button.png" width="173">
- **Deployment signals extracted:** advertises tool-use / function-calling, vision / multimodal capability advertised, explicit context-length claim, reasoning-trace capability, MoE architecture confirmed, speculative / MTP drafting
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-qwen36-35b-a3b-ud` | tools: none | emits_reasoning
    > Benchmark: hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL (Alibaba MoE, 35B total / 3B active, ~22GB). Unsloth Dynamic 2.0 sensitivity-aware quant vs stock Q4_K_M — agentic lane candidate C1, TASK_MODEL_FLEET_REFRESH_V2.
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - card advertises tool-use / function-calling but `bench-qwen36-35b-a3b-ud` has no tools — advertised capability untested
  - card advertises vision/multimodal but no slot text mentions vision, mmproj, or image tasks — advertised capability likely untested
- **Card vs slotting alignment ✓:**
  - card advertises reasoning; slot has `emits_reasoning: true`

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `vision` — Vision / multimodal (non-CUA)
- **Recommended harness:** vision probe (image → text tasks)
- **Prompt corpus:** image + question pairs across VQA, captioning, OCR
- **Metrics to capture (beyond raw TPS):**
  - VQA accuracy
  - caption quality
  - OCR fidelity if advertised
- **Do NOT measure (would produce invalid signal for this capability):**
  - text-only quality alone — misses the modality that justifies the model
- **Workspace slot requirements for valid bench data:**
  - `mmproj`: vision projector REQUIRED
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - `bench-qwen36-35b-a3b-ud`: needs vision projector (`mmproj`) — the bench cannot produce valid multimodal data without it
  - card advertises tool-use / function-calling but `bench-qwen36-35b-a3b-ud` has no tools — advertised capability untested
  - card advertises vision/multimodal but no slot text mentions vision, mmproj, or image tasks — advertised capability likely untested


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest evidence:** 2026-06-28 (43d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M` — 21.4 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - **Nex-N2 disappears from the fleet entirely** — no other workspace uses this arch family
  - **last model from `sjakek`** — vendor exits the fleet
  - NET-NEW arch family: `Nex-N2` (not in fleet elsewhere)
  - NET-NEW vendor: `sjakek` (not in fleet elsewhere)
  - only exploration of `Nex-N2` arch — no other workspace tests it
- **What we'd gain:** 21.4 GB disk

### Intake rationale

- **Intake age:** 46d ago (first-seen commit `84c15f78`)
- **Mentioned in 4 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## coding (41)
    > - `hf.co/deepreinforce-ai/Ornith-1.0-35B-GGUF:Q4_K_M-ctx64k` \ - `hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M` \ - `hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M` \ - `hf.co/unsloth/GLM-4.7-Flash…
  - `docs/generated/ARCHITECTURE_MAP.md` — ## Knowledge Layer
    > | `unit-model-catalog-hf-co-redteamlab-qwen3-6-27b-blueteam-v1-q3-k-s-dropped-evaluated-not-adopted` | what | 2 | \ | `unit-model-catalog-hf-co-redteamlab-qwen3-6-27b-redteam-v5-qwen3-6-27b-redteam-v5…
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## coding (41)
    > - `hf.co/deepreinforce-ai/Ornith-1.0-35B-GGUF:Q4_K_M-ctx64k` \ - `hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M` \ - `hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M` \ - `hf.co/unsloth/GLM-4.7-Flash…

### Capability profile

- **Architecture:** Nex-N2
- **Quantization:** Q4_K_M (mixed)
- **Source:** huggingface (`sjakek`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M'

### Fleet position

- **Bench workspaces routing here:** `bench-nex-n2-mini`
- **Same-arch (`Nex-N2`) production workspaces:** 0
- **Same-arch bench workspaces:** 0
- **Net-new signals (fleet has no other with these):**
  - arch family: `Nex-N2` (not in fleet elsewhere)
  - vendor: `sjakek` (not in fleet elsewhere)
- ⚠ **Removal ends all fleet exploration of `Nex-N2`**

### Diversity impact

- ⚠ **ARCH LOSS**: `Nex-N2` disappears from fleet entirely if removed
- ⚠ **VENDOR LOSS**: `sjakek` exits the fleet

### Card claims vs our slotting

- **Card source:** `https://huggingface.co/sjakek/Nex-N2-mini-GGUF/raw/main/README.md` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > GGUF quantizations of [nex-agi/Nex-N2-mini](https://huggingface.co/nex-agi/Nex-N2-mini) for use with [llama.cpp](https://github.com/ggml-org/llama.cpp).
- **Deployment signals extracted:** vision / multimodal capability advertised, MoE architecture confirmed, speculative / MTP drafting
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-nex-n2-mini` | tools: none | emits_reasoning
    > Benchmark: hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M (June 2026, Apache 2.0, 35B total / 3B active MoE, ~22GB UD-Q4_K_M). Post-trained on Qwen3.5-35B-A3B-Base for agentic coding, tool use, reasoning. Multimodal (image+text). imatrix community GGUF by sjakek. Terminal-Bench 2.1 score: 60.7. PROMOTE_POLICY=confirm.
- **Alignment:** no distinctive claim/slot mismatch detected — slot config appears consistent with card

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `vision` — Vision / multimodal (non-CUA)
- **Recommended harness:** vision probe (image → text tasks)
- **Prompt corpus:** image + question pairs across VQA, captioning, OCR
- **Metrics to capture (beyond raw TPS):**
  - VQA accuracy
  - caption quality
  - OCR fidelity if advertised
- **Do NOT measure (would produce invalid signal for this capability):**
  - text-only quality alone — misses the modality that justifies the model
- **Workspace slot requirements for valid bench data:**
  - `mmproj`: vision projector REQUIRED


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest evidence:** 2026-06-21 (50d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `hf.co/BugTraceAI/BugTraceAI-CORE-Ultra-27B-Q6:Q6_K` — 20.6 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - **BugTraceAI disappears from the fleet entirely** — no other workspace uses this arch family
  - **last model from `BugTraceAI`** — vendor exits the fleet
  - NET-NEW arch family: `BugTraceAI` (not in fleet elsewhere)
  - NET-NEW vendor: `BugTraceAI` (not in fleet elsewhere)
  - capability: Cyber / security domain training
  - only exploration of `BugTraceAI` arch — no other workspace tests it
- **What we'd gain:** 20.6 GB disk

### Intake rationale

- **Intake age:** 41d ago (first-seen commit `ddcf7dff`)
- **Mentioned in 5 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `hf.co/Abiray/Agents-A1-Q4_K_M-GGUF:Q4_K_M` \ - `hf.co/Andycurrent/Mistral-7B-Uncensored-GGUF:Q4_K_M` \ - `hf.co/BugTraceAI/BugTraceAI-CORE-Ultra-27B-Q6:Q6_K` \ - `hf.co/Jackrong/DeepSeek-V4-Pro-Qwe…
  - `docs/generated/ARCHITECTURE_MAP.md` — ## Knowledge Layer
    > | `unit-model-catalog-hf-co-bartowski-thudm-glm-z1-rumination-32b-0414-gguf-thudm-glm-z1-rumination-32b-0414-q4-k-m-gguf` | what | 2 | \ | `unit-model-catalog-hf-co-bartowski-thudm-glm-z1-rumination-3…
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## general (84)
    > - `hf.co/Abiray/Agents-A1-Q4_K_M-GGUF:Q4_K_M` \ - `hf.co/Andycurrent/Mistral-7B-Uncensored-GGUF:Q4_K_M` \ - `hf.co/BugTraceAI/BugTraceAI-CORE-Ultra-27B-Q6:Q6_K` \ - `hf.co/Jackrong/DeepSeek-V4-Pro-Qwe…

### Capability profile

- **Architecture:** BugTraceAI
- **Parameters:** 27B
- **Quantization:** Q6_K
- **Source:** huggingface (`BugTraceAI`)
- **Distinguishing features (from tag pattern):**
  - Cyber / security domain training
- **Reversibility:** ollama pull 'hf.co/BugTraceAI/BugTraceAI-CORE-Ultra-27B-Q6:Q6_K'

### Fleet position

- **Bench workspaces routing here:** `bench-bugtrace-ultra-27b`
- **Same-arch (`BugTraceAI`) production workspaces:** 0
- **Same-arch bench workspaces:** 0
- **Net-new signals (fleet has no other with these):**
  - arch family: `BugTraceAI` (not in fleet elsewhere)
  - vendor: `BugTraceAI` (not in fleet elsewhere)
- ⚠ **Removal ends all fleet exploration of `BugTraceAI`**

### Diversity impact

- ⚠ **ARCH LOSS**: `BugTraceAI` disappears from fleet entirely if removed
- ⚠ **VENDOR LOSS**: `BugTraceAI` exits the fleet

### Card claims vs our slotting

- **Card source:** `https://huggingface.co/BugTraceAI/BugTraceAI-CORE-Ultra-27B-Q6/raw/main/README.md` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > > **The tooling answer the community asked for.** > > *"Seems good for chat, but it's completely unusable with tools."* — Community feedback on Apex > > CORE-Ultra is the fix. Built on Qwen3.6-27B — the architecture the community specifically requested — and fine-tuned via SFT on 2,541 real-world bug bounty reports, CVE writeups, and offensive security research. It generates complete, functional, self-contained artifacts. Every time.
- **Deployment signals extracted:** explicit context-length claim, reasoning-trace capability, abliterated / uncensored, MoE architecture confirmed
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-bugtrace-ultra-27b` | tools: none | emits_reasoning
    > BugTraceAI-CORE-Ultra-27B-Q6 (~22.1GB Q6_K, BugTraceAI, Apache 2.0, Qwen3.6 dense 27B, SFT on 2,541 real bug-bounty/CVE writeups). A TOOLING model — emits runnable artifacts (Nuclei templates, CVE PoCs, JWT crackers, C exploits), not prose. Self-reported 5/5 tooling bench, 0% refusal. Complements Portal's analysis-focused security lanes with exploit-GENERATION capability — a genuinely new ability.…
- **Card vs slotting alignment ✓:**
  - card advertises reasoning; slot has `emits_reasoning: true`

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `security-tooling` — Security tooling (exploit / artifact generation)
- **Recommended harness:** security exec-chain scorer — measures artifact runnability, not chat quality
- **Prompt corpus:** CVE writeup → PoC; vulnerability description → Nuclei template; exploit-target descriptions
- **Metrics to capture (beyond raw TPS):**
  - artifact runnability (compiles / executes as-emitted)
  - refusal rate on offensive prompts (should be near-zero for these models)
  - attack-chain success on synthetic targets
- **Do NOT measure (would produce invalid signal for this capability):**
  - MMLU / general chat quality — model was not trained for chat
  - refusal on benign prompts — irrelevant to the capability
- **Workspace slot requirements for valid bench data:**
  - `tools`: empty ([]) — tool exposure causes reasoning-loop failures per BugTraceAI card guidance
  - `emits_reasoning`: true — capture the reasoning trace, don't suppress it
  - `temperature`: 0.1–0.3 for reproducibility


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest post-boundary evidence:** 2026-08-11
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-GGUF:Q4_K_M` — 20.3 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - capability: MoE architecture (routes tokens to expert subsets)
  - capability: Abliterated (safety-vector ablation)
- **What we'd gain:** 20.3 GB disk

### Intake rationale

- **Intake age:** 46d ago (first-seen commit `84c15f78`)
- **Mentioned in 3 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:Q4_K_M` \ - `hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M` \ - `hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-GGUF:Q4…
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## general (84)
    > - `hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:Q4_K_M` \ - `hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M` \ - `hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-GGUF:Q4…
  - `portal_wiki/canonical/unit-model-catalog-hf-co-mradermacher-huihui-qwen3-6-35b-a3b-abliterated-gguf-q4-k-m.md` — (no nearby heading)
    > id: unit-model-catalog-hf-co-mradermacher-huihui-qwen3-6-35b-a3b-abliterated-gguf-q4-k-m \ kind: what \ title: "MODEL_CATALOG \u2014 `hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-GGUF:Q4_K_M`…

### Capability profile

- **Architecture:** Qwen3.6
- **Parameters:** 35B
- **Quantization:** Q4_K_M (mixed)
- **Source:** huggingface (`mradermacher`)
- **Distinguishing features (from tag pattern):**
  - MoE architecture (routes tokens to expert subsets)
  - Abliterated (safety-vector ablation)
- **Reversibility:** ollama pull 'hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-GGUF:Q4_K_M'

### Fleet position

- **Bench workspaces routing here:** `bench-huihui-qwen36-35b-a3b`
- **Same-arch (`Qwen3.6`) production workspaces:** 3
  - `huihui_ai/Qwen3.6-abliterated:27b-ctx8k` (via `auto-general-uncensored`)
  - `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k` (via `auto-creative`)
  - `qwen3.6:27b-q4_K_M-ctx16k` (via `auto-council`)
- **Same-arch bench workspaces:** 10
  - `qwen3.6:27b-q4_K_M` (via `bench-qwen36-27b`)
  - `portal5/qwen3.6-27b-mtp:q8_0-drafted` (via `bench-qwen36-27b-mtp`)
  - `qwen3.6:35b-a3b-q4_K_M` (via `bench-qwen36-35b-a3b`)
  - `qwen3.6:27b-q4_K_M` (via `bench-qwen36-27b-ud`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `Qwen3.6` workspaces in fleet:** 13
- **Other workspaces from `mradermacher`:** 6

### Card claims vs our slotting

- **Card source:** `https://huggingface.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-GGUF/raw/main/README.md` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!-- ### quantize_version: 2 --> <!-- ### output_tensor_quantised: 1 --> <!-- ### convert_type: hf --> <!-- ### vocab_type:  --> <!-- ### tags:  --> <!-- ### quants:  x-f16 Q4_K_S Q2_K Q8_0 Q6_K Q3_K_M Q3_K_S Q3_K_L Q4_K_M Q5_K_S Q5_K_M IQ4_XS --> <!-- ### quants_skip:  --> <!-- ### skip_mmproj:  --> static quants of https://huggingface.co/huihui-ai/Huihui-Qwen3.6-35B-A3B-abliterated
- **Deployment signals extracted:** vision / multimodal capability advertised, abliterated / uncensored
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-huihui-qwen36-35b-a3b` | tools: none
    > Benchmark: vanch007/Huihui-Qwen3.6-35B-A3B-abliterated (MoE 3B active, ~20GB, abliterated). Speed play vs bench-huihui-qwen36-27b — 3B active MoE for fast decode. Pull from HF GGUF before benching.
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - card advertises vision/multimodal but no slot text mentions vision, mmproj, or image tasks — advertised capability likely untested

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `vision` — Vision / multimodal (non-CUA)
- **Recommended harness:** vision probe (image → text tasks)
- **Prompt corpus:** image + question pairs across VQA, captioning, OCR
- **Metrics to capture (beyond raw TPS):**
  - VQA accuracy
  - caption quality
  - OCR fidelity if advertised
- **Do NOT measure (would produce invalid signal for this capability):**
  - text-only quality alone — misses the modality that justifies the model
- **Workspace slot requirements for valid bench data:**
  - `mmproj`: vision projector REQUIRED
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - `bench-huihui-qwen36-35b-a3b`: needs vision projector (`mmproj`) — the bench cannot produce valid multimodal data without it
  - card advertises vision/multimodal but no slot text mentions vision, mmproj, or image tasks — advertised capability likely untested


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest evidence:** 2026-06-28 (43d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `portal5/xyz-aquila-mini:Q4_K_M` — 19.9 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - nothing distinctive — arch/vendor/capability all remain represented after removal
- **What we'd gain:** 19.9 GB disk

### Intake rationale

- **Intake age:** 0d ago (first-seen commit `d6603676`)
- **Mentioned in 3 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `portal5/gemma4-12b:q4_K_M-ctx8k` \ - `portal5/qwen3.6-27b-mtp:q8_0-drafted` \ - `portal5/xyz-aquila-mini:q4_k_m` \ - `qwen3-coder-next:latest` \ - `qwen3-coder:30b-a3b-q4_K_M` \ - `qwen3.6:27b-q4_K…
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## general (84)
    > - `portal5/gemma4-12b:q4_K_M-ctx8k` \ - `portal5/qwen3.6-27b-mtp:q8_0-drafted` \ - `portal5/xyz-aquila-mini:q4_k_m` \ - `qwen3-coder-next:latest` \ - `qwen3-coder:30b-a3b-q4_K_M` \ - `qwen3.6:27b-q4_K…
  - `portal_wiki/canonical/unit-model-catalog-portal5-xyz-aquila-mini-q4-k-m.md` — (no nearby heading)
    > id: unit-model-catalog-portal5-xyz-aquila-mini-q4-k-m \ kind: what \ title: "MODEL_CATALOG \u2014 `portal5/xyz-aquila-mini:q4_k_m`" \ sources: \ - type: code \   path: config/backends.yaml

### Capability profile

- **Architecture:** XYZ-Aquila
- **Quantization:** Q4_K_M (mixed)
- **Source:** portal5-local-build (`portal5`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** NOT registry-pullable — local build; reconstruct via original derivation task

### Fleet position

- **Bench workspaces routing here:** none (bench-orphaned)
- **Same-arch (`XYZ-Aquila`) production workspaces:** 0
- **Same-arch bench workspaces:** 2
  - `portal5/xyz-aquila-mini:q4_k_m` (via `bench-aquila-mini-35b-a3b`)
  - `portal5/xyz-aquila-mini:q4_k_m-ctx16k` (via `bench-aquila-research`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `XYZ-Aquila` workspaces in fleet:** 2
- **Other workspaces from `portal5`:** 4

### Card claims vs our slotting

- **Card status:** local portal5/* build — no external card

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `general` — General / no specific capability advertised
- **Recommended harness:** bench_tps + portal5_persona_matrix (standard fleet path)
- **Prompt corpus:** default persona matrix across the model's target lane
- **Metrics to capture (beyond raw TPS):**
  - avg_tps vs the 20 t/s floor
  - quality_score vs same-lane incumbent


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest post-boundary evidence:** 2026-08-11
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `portal5/xyz-aquila-mini:q4_k_m-ctx16k` — 19.9 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - nothing distinctive — arch/vendor/capability all remain represented after removal
- **What we'd gain:** 19.9 GB disk

### Intake rationale

- **Intake age:** 0d ago (first-seen commit `1896bb7d`)
- **Mentioned in 3 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `portal5/gemma4-12b:q4_K_M-ctx8k` \ - `portal5/qwen3.6-27b-mtp:q8_0-drafted` \ - `portal5/xyz-aquila-mini:q4_k_m` \ - `qwen3-coder-next:latest` \ - `qwen3-coder:30b-a3b-q4_K_M` \ - `qwen3.6:27b-q4_K…
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## general (84)
    > - `portal5/gemma4-12b:q4_K_M-ctx8k` \ - `portal5/qwen3.6-27b-mtp:q8_0-drafted` \ - `portal5/xyz-aquila-mini:q4_k_m` \ - `qwen3-coder-next:latest` \ - `qwen3-coder:30b-a3b-q4_K_M` \ - `qwen3.6:27b-q4_K…
  - `portal_wiki/canonical/unit-model-catalog-portal5-xyz-aquila-mini-q4-k-m.md` — (no nearby heading)
    > `portal5/xyz-aquila-mini:q4_k_m` is the TASK-BATCH-BENCH-001 Part A intake of XYZ-Aquila-mini (XYZAILab, 35B-A3B MoE ~3B active, post-trained from Qwen3.6-35B-A3B via the AxisAgentic bounded-explorati…

### Capability profile

- **Architecture:** XYZ-Aquila
- **Quantization:** Q4_K_M (mixed)
- **Source:** portal5-local-build (`portal5`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** NOT registry-pullable — local build; reconstruct via original derivation task

### Fleet position

- **Bench workspaces routing here:** `bench-aquila-research`
- **Same-arch (`XYZ-Aquila`) production workspaces:** 0
- **Same-arch bench workspaces:** 1
  - `portal5/xyz-aquila-mini:q4_k_m` (via `bench-aquila-mini-35b-a3b`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `XYZ-Aquila` workspaces in fleet:** 1
- **Other workspaces from `portal5`:** 3

### Card claims vs our slotting

- **Card status:** local portal5/* build — no external card
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-aquila-research` (🔬 Bench · XYZ-Aquila-mini (research-task eval, vs auto-research incumbent))
    > TASK-BENCH-FOLLOWUP-001 Part 1B: research-appropriate head-to-head for Aquila, replacing
the V1 C4/SWE-diagnosis proxy (C4 measures nothing about deep research). Clones
auto-research's tool set (web_search/web_fetch/synthesis) so both arms run the identical
research-task rubric. Working-ctx preflight found 8k truncates conversation history after
~2 tool hops (prompt silently dropped from 15,932 to…

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `general` — General / no specific capability advertised
- **Recommended harness:** bench_tps + portal5_persona_matrix (standard fleet path)
- **Prompt corpus:** default persona matrix across the model's target lane
- **Metrics to capture (beyond raw TPS):**
  - avg_tps vs the 20 t/s floor
  - quality_score vs same-lane incumbent


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest post-boundary evidence:** 2026-08-11
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `muse-glimmer:30b-mlx` — 19.8 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - **Muse-Glimmer disappears from the fleet entirely** — no other workspace uses this arch family
  - NET-NEW arch family: `Muse-Glimmer` (not in fleet elsewhere)
  - only exploration of `Muse-Glimmer` arch — no other workspace tests it
- **What we'd gain:** 19.8 GB disk

### Intake rationale

- **Intake age:** 0d ago (first-seen commit `fb9979b7`)
- **Mentioned in 5 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `meta-secalign-8b-q4_k_m:latest` \ - `mistral-small3.2:24b` \ - `muse-glimmer:30b-mlx` \ - `omnicoder2:9b-q4_k_m` \ - `phi4-mini` \ - `phi4:14b-q8_0`
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## general (84)
    > - `meta-secalign-8b-q4_k_m:latest` \ - `mistral-small3.2:24b` \ - `muse-glimmer:30b-mlx` \ - `omnicoder2:9b-q4_k_m` \ - `phi4-mini` \ - `phi4:14b-q8_0`
  - `portal_wiki/canonical/unit-model-catalog-muse-glimmer-30b-mlx.md` — (no nearby heading)
    > id: unit-model-catalog-muse-glimmer-30b-mlx \ kind: what \ title: "MODEL_CATALOG \u2014 `muse-glimmer:30b-mlx`" \ sources: \ - type: code \   path: config/backends.yaml

### Capability profile

- **Architecture:** Muse-Glimmer
- **Parameters:** 30B
- **Source:** ollama-library (`ollama-library`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'muse-glimmer:30b-mlx'

### Fleet position

- **Bench workspaces routing here:** `bench-muse-glimmer-30b`
- **Same-arch (`Muse-Glimmer`) production workspaces:** 0
- **Same-arch bench workspaces:** 0
- **Net-new signals (fleet has no other with these):**
  - arch family: `Muse-Glimmer` (not in fleet elsewhere)
- ⚠ **Removal ends all fleet exploration of `Muse-Glimmer`**

### Diversity impact

- ⚠ **ARCH LOSS**: `Muse-Glimmer` disappears from fleet entirely if removed
- **Other workspaces from `ollama-library`:** 40

### Card claims vs our slotting

- **Card source:** `https://ollama.com/library/muse-glimmer` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!doctype html> <html class="h-full overflow-y-scroll"> <head> <title>muse-glimmer</title>
- **Deployment signals extracted:** vision / multimodal capability advertised, reasoning-trace capability
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-muse-glimmer-30b` | tools: none | emits_reasoning
    > Benchmark: muse-glimmer:30b-mlx (meta-models/Muse-Glimmer-30B, native Ollama MLX engine, 0.32.7, Apache 2.0). 29.6B dense + ViT-G/14 perception encoder; local-first multimodal agentic model; ships DFlash speculative decoding; OpenClaw/Hermes tool-call compatible.
BENCH RESULT 2026-08-10: TPS 25.6 t/s avg (5/5, clears 20 t/s floor). Tool-calling verified via direct /api/chat probe (clean, correctly…
- **Card vs slotting alignment ✓:**
  - card advertises reasoning; slot has `emits_reasoning: true`

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `vision` — Vision / multimodal (non-CUA)
- **Recommended harness:** vision probe (image → text tasks)
- **Prompt corpus:** image + question pairs across VQA, captioning, OCR
- **Metrics to capture (beyond raw TPS):**
  - VQA accuracy
  - caption quality
  - OCR fidelity if advertised
- **Do NOT measure (would produce invalid signal for this capability):**
  - text-only quality alone — misses the modality that justifies the model
- **Workspace slot requirements for valid bench data:**
  - `mmproj`: vision projector REQUIRED


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest post-boundary evidence:** 2026-08-11
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `hf.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated-gguf-4bit:Q4_K_M` — 19.7 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - **last model from `Jiunsong`** — vendor exits the fleet
  - NET-NEW vendor: `Jiunsong` (not in fleet elsewhere)
  - capability: MoE architecture (routes tokens to expert subsets)
  - capability: Abliterated (safety-vector ablation)
  - capability: Agent-tuned
- **What we'd gain:** 19.7 GB disk

### Intake rationale

- **Intake age:** 41d ago (first-seen commit `ddcf7dff`)
- **Mentioned in 4 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## coding (41)
    > - `gpt-oss:20b` \ - `hf.co/Abiray/Agents-A1-Q4_K_M-GGUF:Q4_K_M` \ - `hf.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated-gguf-4bit:Q4_K_M` \ - `hf.co/Mia-AiLab/Qwable-3.6-35b:Qwable-3.6-35b_q4_k_m…
  - `docs/generated/ARCHITECTURE_MAP.md` — ## Knowledge Layer
    > | `unit-model-catalog-hf-co-gaston-parravicini-lfm2-5-8b-a1b-uncensored-gaston-gguf-q4-k-m-ctx8k` | what | 2 | \ | `unit-model-catalog-hf-co-jackrong-qwopus3-6-27b-v2-mtp-gguf-qwopus3-6-27b-v2-mtp-q5-…
  - `portal_wiki/canonical/unit-model-catalog-hf-co-jiunsong-superqwen-agentworld-35b-a3b-abliterated-gguf-4bit-q4-k-m.md` — (no nearby heading)
    > id: unit-model-catalog-hf-co-jiunsong-superqwen-agentworld-35b-a3b-abliterated-gguf-4bit-q4-k-m \ kind: what \ title: "MODEL_CATALOG \u2014 `hf.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated-ggu…

### Capability profile

- **Architecture:** Qwen3.6
- **Parameters:** 35B
- **Quantization:** Q4_K_M (mixed)
- **Source:** huggingface (`Jiunsong`)
- **Distinguishing features (from tag pattern):**
  - MoE architecture (routes tokens to expert subsets)
  - Abliterated (safety-vector ablation)
  - Agent-tuned
- **Reversibility:** ollama pull 'hf.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated-gguf-4bit:Q4_K_M'

### Fleet position

- **Bench workspaces routing here:** `bench-superqwen-agentworld-ablit`
- **Same-arch (`Qwen3.6`) production workspaces:** 3
  - `huihui_ai/Qwen3.6-abliterated:27b-ctx8k` (via `auto-general-uncensored`)
  - `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k` (via `auto-creative`)
  - `qwen3.6:27b-q4_K_M-ctx16k` (via `auto-council`)
- **Same-arch bench workspaces:** 10
  - `qwen3.6:27b-q4_K_M` (via `bench-qwen36-27b`)
  - `portal5/qwen3.6-27b-mtp:q8_0-drafted` (via `bench-qwen36-27b-mtp`)
  - `qwen3.6:35b-a3b-q4_K_M` (via `bench-qwen36-35b-a3b`)
  - `qwen3.6:27b-q4_K_M` (via `bench-qwen36-27b-ud`)
- **Net-new signals (fleet has no other with these):**
  - vendor: `Jiunsong` (not in fleet elsewhere)

### Diversity impact

- **Other `Qwen3.6` workspaces in fleet:** 13
- ⚠ **VENDOR LOSS**: `Jiunsong` exits the fleet

### Card claims vs our slotting

- **Card source:** `https://huggingface.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated-gguf-4bit/raw/main/README.md` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > This repository contains a 4-bit quantized build of [Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated](https://huggingface.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated).
- **Deployment signals extracted:** abliterated / uncensored
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-superqwen-agentworld-ablit` | tools: 6 configured | emits_reasoning
    > SuperQwen-AgentWorld-35B-A3B abliterated GGUF (~21.2GB Q4_K_M, Jiunsong, Apache 2.0, qwen35moe arch, Qwen AgentWorld base). Abliterated variant of the same Qwen AgentWorld 35B-A3B base Portal already runs — uncensored fork of the held AgentWorld. Card is a stub (see BF16 parent model for benchmarks); treat all capability claims as unverified until benched. PROMOTE_POLICY=confirm.
- **Alignment:** no distinctive claim/slot mismatch detected — slot config appears consistent with card

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `agent-toolcall` — Agent / tool-use tuned
- **Recommended harness:** tool-use probe — schema conformance + multi-turn tool chain success
- **Prompt corpus:** tool definitions + tasks requiring their invocation across turns
- **Metrics to capture (beyond raw TPS):**
  - tool-call schema conformance (parses, correct args)
  - argument correctness for supplied schemas
  - multi-turn tool chain success
- **Do NOT measure (would produce invalid signal for this capability):**
  - single-turn text quality alone — misses the agent capability
- **Workspace slot requirements for valid bench data:**
  - `tools`: populated with representative tool definitions


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest post-boundary evidence:** 2026-08-11
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `portal5/deepwen-3.6:q4.5-moq-ctx32k` — 19.7 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate` — introduced 0d ago — still in eval window; arch already 13-strong; this adds no capability
- **What we'd lose if removed:**
  - nothing distinctive — arch/vendor/capability all remain represented after removal
- **What we'd gain:** 19.7 GB disk

### Intake rationale

- **Intake age:** 0d ago (first-seen commit `0fec84d4`)
- **Mentioned in 5 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `phi4:14b-q8_0` \ - `portal5/deepwen-3.6:q4.5-moq` \ - `portal5/deepwen-3.6:q4.5-moq-ctx32k` \ - `portal5/gemma4-12b:q4_K_M-ctx8k` \ - `portal5/qwen3.6-27b-mtp:q8_0-drafted` \ - `portal5/xyz-aquila-…
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## general (84)
    > - `phi4:14b-q8_0` \ - `portal5/deepwen-3.6:q4.5-moq` \ - `portal5/deepwen-3.6:q4.5-moq-ctx32k` \ - `portal5/gemma4-12b:q4_K_M-ctx8k` \ - `portal5/qwen3.6-27b-mtp:q8_0-drafted` \ - `portal5/xyz-aquila-…
  - `portal_wiki/canonical/unit-model-catalog-portal5-deepwen-3-6-q4-5-moq.md` — (no nearby heading)
    > --- \  \ `portal5/deepwen-3.6:q4.5-moq` is the TASK-BATCH-BENCH-002 Part D intake of Deepwen-3.6 (quimmedes/Deepwen-3.6, a Qwen3.6-35B-A3B fine-tune for procedural geometry / hard-surface / 3D-asset w…

### Capability profile

- **Architecture:** Qwen3.6
- **Source:** portal5-local-build (`portal5`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** NOT registry-pullable — local build; reconstruct via original derivation task

### Fleet position

- **Bench workspaces routing here:** `bench-deepwen-cad`
- **Same-arch (`Qwen3.6`) production workspaces:** 3
  - `huihui_ai/Qwen3.6-abliterated:27b-ctx8k` (via `auto-general-uncensored`)
  - `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k` (via `auto-creative`)
  - `qwen3.6:27b-q4_K_M-ctx16k` (via `auto-council`)
- **Same-arch bench workspaces:** 10
  - `qwen3.6:27b-q4_K_M` (via `bench-qwen36-27b`)
  - `portal5/qwen3.6-27b-mtp:q8_0-drafted` (via `bench-qwen36-27b-mtp`)
  - `qwen3.6:35b-a3b-q4_K_M` (via `bench-qwen36-35b-a3b`)
  - `qwen3.6:27b-q4_K_M` (via `bench-qwen36-27b-ud`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `Qwen3.6` workspaces in fleet:** 13
- **Other workspaces from `portal5`:** 3

### Card claims vs our slotting

- **Card status:** local portal5/* build — no external card
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-deepwen-cad` (🔬 Bench · Deepwen-3.6 (CAD lane vs Qwen3-Coder incumbent))
    > Benchmark: Deepwen-3.6 (quimmedes/Deepwen-3.6, Qwen3.6-35B-A3B fine-tune for procedural geometry / hard-surface / 3D asset workflows, MoQ GGUF ~21GB, arch qwen35moe). TASK-BATCH-BENCH-002 Part D — head-to-head vs auto-cad's Qwen3-Coder-30B-A3B incumbent on the real render_openscad/convert_cad tool loop.
BENCH RESULT 2026-08-10 (revised after root-causing an initial wrong verdict — see below): firs…

### Prescribed re-bench (capability-appropriate)

- **Capability category:** `general` — General / no specific capability advertised
- **Recommended harness:** bench_tps + portal5_persona_matrix (standard fleet path)
- **Prompt corpus:** default persona matrix across the model's target lane
- **Metrics to capture (beyond raw TPS):**
  - avg_tps vs the 20 t/s floor
  - quality_score vs same-lane incumbent


### Numeric evidence

- **Evidence rows mined:** 1 valid (post-boundary), 0 invalid (pre-boundary)
- **Avg TPS (post-boundary only):** 40.4 (above floor)
- **Avg quality_score (post-boundary):** 0.0
- **Newest post-boundary evidence:** 2026-08-11


## `portal5/deepwen-3.6:q4.5-moq` — 19.7 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - nothing distinctive — arch/vendor/capability all remain represented after removal
- **What we'd gain:** 19.7 GB disk

### Intake rationale

- **Intake age:** 0d ago (first-seen commit `fb9979b7`)
- **Mentioned in 5 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `phi4-mini` \ - `phi4:14b-q8_0` \ - `portal5/deepwen-3.6:q4.5-moq` \ - `portal5/deepwen-3.6:q4.5-moq-ctx32k` \ - `portal5/gemma4-12b:q4_K_M-ctx8k` \ - `portal5/qwen3.6-27b-mtp:q8_0-drafted`
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## general (84)
    > - `phi4-mini` \ - `phi4:14b-q8_0` \ - `portal5/deepwen-3.6:q4.5-moq` \ - `portal5/deepwen-3.6:q4.5-moq-ctx32k` \ - `portal5/gemma4-12b:q4_K_M-ctx8k` \ - `portal5/qwen3.6-27b-mtp:q8_0-drafted`
  - `portal_wiki/canonical/unit-model-catalog-portal5-deepwen-3-6-q4-5-moq.md` — (no nearby heading)
    > id: unit-model-catalog-portal5-deepwen-3-6-q4-5-moq \ kind: what \ title: "MODEL_CATALOG \u2014 `portal5/deepwen-3.6:q4.5-moq`" \ sources: \ - type: code \   path: config/backends.yaml

### Capability profile

- **Architecture:** Qwen3.6
- **Source:** portal5-local-build (`portal5`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** NOT registry-pullable — local build; reconstruct via original derivation task

### Fleet position

- **Bench workspaces routing here:** none (bench-orphaned)
- **Same-arch (`Qwen3.6`) production workspaces:** 3
  - `huihui_ai/Qwen3.6-abliterated:27b-ctx8k` (via `auto-general-uncensored`)
  - `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k` (via `auto-creative`)
  - `qwen3.6:27b-q4_K_M-ctx16k` (via `auto-council`)
- **Same-arch bench workspaces:** 11
  - `qwen3.6:27b-q4_K_M` (via `bench-qwen36-27b`)
  - `portal5/qwen3.6-27b-mtp:q8_0-drafted` (via `bench-qwen36-27b-mtp`)
  - `qwen3.6:35b-a3b-q4_K_M` (via `bench-qwen36-35b-a3b`)
  - `qwen3.6:27b-q4_K_M` (via `bench-qwen36-27b-ud`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `Qwen3.6` workspaces in fleet:** 14
- **Other workspaces from `portal5`:** 4

### Card claims vs our slotting

- **Card status:** local portal5/* build — no external card

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `general` — General / no specific capability advertised
- **Recommended harness:** bench_tps + portal5_persona_matrix (standard fleet path)
- **Prompt corpus:** default persona matrix across the model's target lane
- **Metrics to capture (beyond raw TPS):**
  - avg_tps vs the 20 t/s floor
  - quality_score vs same-lane incumbent


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest post-boundary evidence:** 2026-08-11
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `hf.co/Mia-AiLab/Qwable-3.6-35b:Qwable-3.6-35b_q4_k_m.gguf` — 19.7 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - **last model from `Mia-AiLab`** — vendor exits the fleet
  - NET-NEW vendor: `Mia-AiLab` (not in fleet elsewhere)
- **What we'd gain:** 19.7 GB disk

### Intake rationale

- **Intake age:** 46d ago (first-seen commit `84c15f78`)
- **Mentioned in 5 doc file(s):**
  - `docs/SECURITY_BENCH_EXEC.md` — ## Security models loaded
    > ``` \ hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M \ hf.co/Mia-AiLab/Qwable-3.6-35b:Qwable-3.6-35b_q4_k_m.gguf \ huihui_ai/baronllm-abliterated:latest \ hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-G…
  - `docs/ADMIN_GUIDE.md` — ## coding (41)
    > - `hf.co/Abiray/Agents-A1-Q4_K_M-GGUF:Q4_K_M` \ - `hf.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated-gguf-4bit:Q4_K_M` \ - `hf.co/Mia-AiLab/Qwable-3.6-35b:Qwable-3.6-35b_q4_k_m.gguf` \ - `hf.co/…
  - `docs/_archive_execdocs/SECURITY_FLEET_REVIEW_2026-06.md` — ### Remove
    > | `baronllm:q6_k` | 0.00 | Tool template bug caused chain failures (TASK_TOOLCALL_FIX_LOCKIN_V1 fixed this in the abliterated variant, not the q6_k). The base model is not the problem — this quantizat…

### Capability profile

- **Architecture:** Qwen3.6
- **Parameters:** 35B
- **Quantization:** Q4_K_M (mixed)
- **Source:** huggingface (`Mia-AiLab`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'hf.co/Mia-AiLab/Qwable-3.6-35b:Qwable-3.6-35b_q4_k_m.gguf'

### Fleet position

- **Bench workspaces routing here:** none (bench-orphaned)
- **Same-arch (`Qwen3.6`) production workspaces:** 3
  - `huihui_ai/Qwen3.6-abliterated:27b-ctx8k` (via `auto-general-uncensored`)
  - `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k` (via `auto-creative`)
  - `qwen3.6:27b-q4_K_M-ctx16k` (via `auto-council`)
- **Same-arch bench workspaces:** 11
  - `qwen3.6:27b-q4_K_M` (via `bench-qwen36-27b`)
  - `portal5/qwen3.6-27b-mtp:q8_0-drafted` (via `bench-qwen36-27b-mtp`)
  - `qwen3.6:35b-a3b-q4_K_M` (via `bench-qwen36-35b-a3b`)
  - `qwen3.6:27b-q4_K_M` (via `bench-qwen36-27b-ud`)
- **Net-new signals (fleet has no other with these):**
  - vendor: `Mia-AiLab` (not in fleet elsewhere)

### Diversity impact

- **Other `Qwen3.6` workspaces in fleet:** 14
- ⚠ **VENDOR LOSS**: `Mia-AiLab` exits the fleet

### Card claims vs our slotting

- **Card source:** `https://huggingface.co/Mia-AiLab/Qwable-3.6-35b/raw/main/README.md` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <p align="center"> <img src="assets/qwable-35b.png" alt="Qwable 35b" width="720"> </p>
- **Card-advertised strengths:**
  - **Highlights:** * **Base:** `unsloth/Qwen3.6-35b` * **Checkpoint type:** full HF model checkpoint * **Training style:** instruction tuning with trace/reasoning-style examples * **Dataset:** cleaned Fable 5 reasoning/instruction dataset * **Primary focus:** coding, structured answers, technical assistance, and local inference * **MTP:** disabled / not present in th…
- **Card says model is NOT for:**
  - **Limitations

Like all fine-tuned language models, Qwable 35b can produce incorrect, incomplete, or misleading outputs:** Known limitations:  - It is **not** an MTP-trained model. - It may inherit limitations from the base model. - It may reflect biases or artifacts from the training dataset. - It may produce confident but incorrect technical answers. - It may differ fr…
- **Deployment signals extracted:** vision / multimodal capability advertised, reasoning-trace capability, speculative / MTP drafting
- **Slotting:** bench-orphaned — nothing routes to this tag
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here
- **Card-advertised capabilities with no keyword overlap in slot config** (may be untested):
  - Highlights

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `vision` — Vision / multimodal (non-CUA)
- **Recommended harness:** vision probe (image → text tasks)
- **Prompt corpus:** image + question pairs across VQA, captioning, OCR
- **Metrics to capture (beyond raw TPS):**
  - VQA accuracy
  - caption quality
  - OCR fidelity if advertised
- **Do NOT measure (would produce invalid signal for this capability):**
  - text-only quality alone — misses the modality that justifies the model
- **Workspace slot requirements for valid bench data:**
  - `mmproj`: vision projector REQUIRED
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-Qwable-3.6-35b`)
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 1 invalid (pre-boundary)
- **Avg TPS (pre-boundary — INVALID for decisions):** 29.7 — captured under prior stack
- **Newest evidence:** 2026-06-23 (48d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `hf.co/Abiray/Agents-A1-Q4_K_M-GGUF:Q4_K_M` — 19.7 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - **Agents-A1 disappears from the fleet entirely** — no other workspace uses this arch family
  - **last model from `Abiray`** — vendor exits the fleet
  - NET-NEW arch family: `Agents-A1` (not in fleet elsewhere)
  - NET-NEW vendor: `Abiray` (not in fleet elsewhere)
  - only exploration of `Agents-A1` arch — no other workspace tests it
- **What we'd gain:** 19.7 GB disk

### Intake rationale

- **Intake age:** 41d ago (first-seen commit `26dc5832`)
- **Mentioned in 3 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## coding (41)
    > - `glm-4.7-flash:Q4_K_M` \ - `gpt-oss:20b` \ - `hf.co/Abiray/Agents-A1-Q4_K_M-GGUF:Q4_K_M` \ - `hf.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated-gguf-4bit:Q4_K_M` \ - `hf.co/Mia-AiLab/Qwable-3.…
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## coding (41)
    > - `glm-4.7-flash:Q4_K_M` \ - `gpt-oss:20b` \ - `hf.co/Abiray/Agents-A1-Q4_K_M-GGUF:Q4_K_M` \ - `hf.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated-gguf-4bit:Q4_K_M` \ - `hf.co/Mia-AiLab/Qwable-3.…
  - `portal_wiki/canonical/unit-model-catalog-hf-co-abiray-agents-a1-q4-k-m-gguf-q4-k-m.md` — (no nearby heading)
    > id: unit-model-catalog-hf-co-abiray-agents-a1-q4-k-m-gguf-q4-k-m \ kind: what \ title: "MODEL_CATALOG \u2014 `hf.co/Abiray/Agents-A1-Q4_K_M-GGUF:Q4_K_M`" \ sources: \ - type: code \   path: config/bac…

### Capability profile

- **Architecture:** Agents-A1
- **Quantization:** Q4_K_M (mixed)
- **Source:** huggingface (`Abiray`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'hf.co/Abiray/Agents-A1-Q4_K_M-GGUF:Q4_K_M'

### Fleet position

- **Bench workspaces routing here:** `bench-agents-a1`
- **Same-arch (`Agents-A1`) production workspaces:** 0
- **Same-arch bench workspaces:** 0
- **Net-new signals (fleet has no other with these):**
  - arch family: `Agents-A1` (not in fleet elsewhere)
  - vendor: `Abiray` (not in fleet elsewhere)
- ⚠ **Removal ends all fleet exploration of `Agents-A1`**

### Diversity impact

- ⚠ **ARCH LOSS**: `Agents-A1` disappears from fleet entirely if removed
- ⚠ **VENDOR LOSS**: `Abiray` exits the fleet

### Card claims vs our slotting

- **Card source:** `https://huggingface.co/Abiray/Agents-A1-Q4_K_M-GGUF/raw/main/README.md` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > This repository contains the GGUF quantized version of **Agents-A1**, a 35B Mixture-of-Experts (MoE) agentic model developed by InternScience. Quantization has been performed using the `Q4_K_M` method to optimize performance and reduce memory consumption while preserving agentic reasoning capabilities.
- **Deployment signals extracted:** advertises tool-use / function-calling, reasoning-trace capability, MoE architecture confirmed
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-agents-a1` | tools: 6 configured | emits_reasoning
    > InternScience Agents-A1 (~21GB Q4_K_M, Apache 2.0, Qwen3.5-MoE 35B-A3B, 262K ctx, purpose-built long-horizon agentic). Strong self-reported agentic benchmarks (τ2-Bench 79.8, IFEval 94.8, GAIA 96.0, SciCode 44.3). Has GitHub repo + technical report + own open eval framework — most serious candidate in this intake batch. Direct competitor to held AgentWorld and promoted Ornith. Community GGUF from …
- **Card vs slotting alignment ✓:**
  - card advertises reasoning; slot has `emits_reasoning: true`

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `reasoning-explicit` — Explicit reasoning / thinking traces
- **Recommended harness:** reasoning-aware persona matrix — capture and score the thinking traces, not just final answers
- **Prompt corpus:** multi-step reasoning tasks: math, logic, planning, code with edge cases
- **Metrics to capture (beyond raw TPS):**
  - task success rate WITH reasoning captured
  - reasoning coherence score
  - TPS separated by reasoning-on vs reasoning-off runs
  - trace length vs task complexity
- **Do NOT measure (would produce invalid signal for this capability):**
  - single-turn factual recall (doesn't exercise reasoning)
- **Workspace slot requirements for valid bench data:**
  - `emits_reasoning`: true — otherwise the harness sees a truncated model
  - `predict_limit`: high enough to fit thinking traces (8k+ typical)
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - `bench-agents-a1`: `predict_limit` needs to accommodate high enough to fit thinking traces (8k+ typical)


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest post-boundary evidence:** 2026-08-11
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf-ctx64k` — 18.7 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - nothing distinctive — arch/vendor/capability all remain represented after removal
- **What we'd gain:** 18.7 GB disk

### Intake rationale

- **Intake age:** 39d ago (first-seen commit `5dd51bb6`)
- **Mentioned in 5 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — # Persona roster (138 personas)
    > | `githubexpert` | coding | `auto-coding` | — | \ | `glm-coder` | coding | `auto-coding` | `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL-ctx64k` | \ | `glm-thinker` | general | `auto-reaso…
  - `portal_wiki/canonical/unit-model-catalog-hf-co-bartowski-thudm-glm-z1-rumination-32b-0414-gguf-thudm-glm-z1-rumination-32b-0414-q4-k-m-gguf.md` — (no nearby heading)
    > id: unit-model-catalog-hf-co-bartowski-thudm-glm-z1-rumination-32b-0414-gguf-thudm-glm-z1-rumination-32b-0414-q4-k-m-gguf \ kind: what \ title: "MODEL_CATALOG \u2014 `hf.co/bartowski/THUDM_GLM-Z1-Rumi…
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## coding (41)
    > - `hf.co/bartowski/Qwen_Qwen3.6-27B-GGUF:Q4_K_M` \ - `hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf` \ - `hf.co/bartowski/THUDM_GLM-Z1-Rumination-3…

### Capability profile

- **Architecture:** GLM
- **Parameters:** 32B
- **Quantization:** Q4_K_M (mixed)
- **Source:** huggingface (`bartowski`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf-ctx64k'

### Fleet position

- **Bench workspaces routing here:** none (bench-orphaned)
- **Same-arch (`GLM`) production workspaces:** 0
- **Same-arch bench workspaces:** 3
  - `glm-4.7-flash:Q4_K_M` (via `bench-glm`)
  - `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL` (via `bench-glm-reap`)
  - `hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf` (via `bench-glm-z1-rumination`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `GLM` workspaces in fleet:** 3
- **Other workspaces from `bartowski`:** 4

### Card claims vs our slotting

- **Card source:** `https://huggingface.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF/raw/main/README.md` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > Using <a href="https://github.com/ggerganov/llama.cpp/">llama.cpp</a> release <a href="https://github.com/ggerganov/llama.cpp/releases/tag/b5228">b5228</a> for quantization.
- **Slotting:** bench-orphaned — nothing routes to this tag
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `general` — General / no specific capability advertised
- **Recommended harness:** bench_tps + portal5_persona_matrix (standard fleet path)
- **Prompt corpus:** default persona matrix across the model's target lane
- **Metrics to capture (beyond raw TPS):**
  - avg_tps vs the 20 t/s floor
  - quality_score vs same-lane incumbent
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest post-boundary evidence:** 2026-08-11
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `deepseek-r1:32b-q4_k_m` — 18.5 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - **DeepSeek disappears from the fleet entirely** — no other workspace uses this arch family
  - NET-NEW arch family: `DeepSeek` (not in fleet elsewhere)
  - only exploration of `DeepSeek` arch — no other workspace tests it
- **What we'd gain:** 18.5 GB disk

### Intake rationale

- **Intake age:** 46d ago (first-seen commit `84c15f78`)
- **Mentioned in 5 doc file(s):**
  - `docs/ROUTING_INTEGRITY_FINDINGS.md` — ### Finding 1 — Keyword layer: 0 regressions, 1 documented intended change
    > `auto-mistral`'s served model changes from \ `hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0-ctx64k` to \ `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k`. This is the \ **documented, inten…
  - `docs/MLX_CHANGES_2026-04-26.md` — ### 2. Speculative Decoding Broken — `ArraysCache` Not Trimmable
    > - **Root cause**: mlx_lm 0.31.2 changed default prompt cache from trimmable type to `ArraysCache`. Speculative decoding requires cache trimming to work. \ - **Fix applied**: `config/backends.yaml` `sp…
  - `docs/ADMIN_GUIDE.md` — ## reasoning (27)
    > - `DeepSeek-R1-0528-Qwen3-8B-4bit` \ - `Tongyi-DeepResearch-30B-A3B-abliterated-4bit` \ - `deepseek-r1:32b-q4_k_m` \ - `gpt-oss:20b` \ - `granite-4.1-30b-4bit` \ - `granite-4.1-8b-mxfp8`

### Capability profile

- **Architecture:** DeepSeek
- **Parameters:** 32B
- **Quantization:** Q4_K_M (mixed)
- **Source:** ollama-library (`ollama-library`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'deepseek-r1:32b-q4_k_m'

### Fleet position

- **Bench workspaces routing here:** none (bench-orphaned)
- **Same-arch (`DeepSeek`) production workspaces:** 0
- **Same-arch bench workspaces:** 0
- **Net-new signals (fleet has no other with these):**
  - arch family: `DeepSeek` (not in fleet elsewhere)
- ⚠ **Removal ends all fleet exploration of `DeepSeek`**

### Diversity impact

- ⚠ **ARCH LOSS**: `DeepSeek` disappears from fleet entirely if removed
- **Other workspaces from `ollama-library`:** 41

### Card claims vs our slotting

- **Card source:** `https://ollama.com/library/deepseek-r1` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!doctype html> <html class="h-full overflow-y-scroll"> <head> <title>deepseek-r1</title>
- **Deployment signals extracted:** reasoning-trace capability
- **Slotting:** bench-orphaned — nothing routes to this tag
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `reasoning-explicit` — Explicit reasoning / thinking traces
- **Recommended harness:** reasoning-aware persona matrix — capture and score the thinking traces, not just final answers
- **Prompt corpus:** multi-step reasoning tasks: math, logic, planning, code with edge cases
- **Metrics to capture (beyond raw TPS):**
  - task success rate WITH reasoning captured
  - reasoning coherence score
  - TPS separated by reasoning-on vs reasoning-off runs
  - trace length vs task complexity
- **Do NOT measure (would produce invalid signal for this capability):**
  - single-turn factual recall (doesn't exercise reasoning)
- **Workspace slot requirements for valid bench data:**
  - `emits_reasoning`: true — otherwise the harness sees a truncated model
  - `predict_limit`: high enough to fit thinking traces (8k+ typical)
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-deepseek-r1`)
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 2 invalid (pre-boundary)
- **Avg TPS (pre-boundary — INVALID for decisions):** 7.3 — captured under prior stack
- **Newest evidence:** 2026-06-28 (43d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `hf.co/Jackrong/Qwopus3.6-27B-v2-MTP-GGUF:Qwopus3.6-27B-v2-MTP-Q5_K_M.gguf` — 18.2 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - capability: MTP speculative drafting (draft model bound to base)
- **What we'd gain:** 18.2 GB disk

### Intake rationale

- **Intake age:** 46d ago (first-seen commit `84c15f78`)
- **Mentioned in 3 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-4B-MTP-GGUF:Q4_K_M` \ - `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-9B-MTP-GGUF:Q4_K_M` \ - `hf.co/Jackrong/Qwopus3.6-27B-v2-MTP-GGUF:Qwopus3.6-27B-v2-MTP-Q5_K_M.…
  - `portal_wiki/canonical/unit-model-catalog-hf-co-jackrong-qwopus3-6-27b-v2-mtp-gguf-qwopus3-6-27b-v2-mtp-q5-k-m-gguf.md` — (no nearby heading)
    > id: unit-model-catalog-hf-co-jackrong-qwopus3-6-27b-v2-mtp-gguf-qwopus3-6-27b-v2-mtp-q5-k-m-gguf \ kind: what \ title: "MODEL_CATALOG \u2014 `hf.co/Jackrong/Qwopus3.6-27B-v2-MTP-GGUF:Qwopus3.6-27B-v2-…
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## general (84)
    > - `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-4B-MTP-GGUF:Q4_K_M` \ - `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-9B-MTP-GGUF:Q4_K_M` \ - `hf.co/Jackrong/Qwopus3.6-27B-v2-MTP-GGUF:Qwopus3.6-27B-v2-MTP-Q5_K_M.…

### Capability profile

- **Architecture:** unknown
- **Parameters:** 27B
- **Quantization:** Q5_K_M
- **Source:** huggingface (`Jackrong`)
- **Distinguishing features (from tag pattern):**
  - MTP speculative drafting (draft model bound to base)
- **Reversibility:** ollama pull 'hf.co/Jackrong/Qwopus3.6-27B-v2-MTP-GGUF:Qwopus3.6-27B-v2-MTP-Q5_K_M.gguf'

### Fleet position

- **Bench workspaces routing here:** `bench-qwopus-coder-mtp-v2`
- **Same-arch (`unknown`) production workspaces:** 0
- **Same-arch bench workspaces:** 0
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `unknown` workspaces in fleet:** 0
- **Other workspaces from `Jackrong`:** 2

### Card claims vs our slotting

- **Card source:** `https://huggingface.co/Jackrong/Qwopus3.6-27B-v2-MTP-GGUF/raw/main/README.md` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; border: 1px solid #cbd5e1; border-radius: 16px; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05), 0 4px 6px -2px rgba(0, 0, 0, 0.05); overflow: hidden; background: #ffffff; margin-bottom: 30px;"> <div style="background: linear-gradient(135deg, #7c3aed 0%, #4c1d95 100%); padding: 24px; color: white;"> <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px;">
- **Deployment signals extracted:** reasoning-trace capability, speculative / MTP drafting
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-qwopus-coder-mtp-v2` | tools: none
    > Benchmark: hf.co/Jackrong/Qwopus3.6-27B-v2-MTP-GGUF:Qwopus3.6-27B-v2-MTP-Q5_K_M.gguf (Jackrong, Apache 2.0, June 2026, 27B dense, ~19GB Q5_K_M). v2 of Qwopus3.6-27B-Coder-MTP (v1 retired 2026-06-21: quality 0.67, 6.5 TPS — both below gate). Updated SFT mix: additional agentic + multi-turn traces. MTP embedded draft heads. PROBE RESULT (2026-06-16): 10/23 — widespread 500 Internal Server Errors on …
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - card advertises reasoning traces but no slot has `emits_reasoning: true` — advertised capability untested

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `mtp-speculative` — MTP / speculative drafting
- **Recommended harness:** MTP-aware bench — draft acceptance rate + wall-time speedup vs base
- **Prompt corpus:** IDENTICAL to base model's bench for direct comparison
- **Metrics to capture (beyond raw TPS):**
  - draft token acceptance rate (headline signal)
  - wall-time speedup vs base model on identical prompts
  - quality parity vs base (any regression kills the value proposition)
- **Do NOT measure (would produce invalid signal for this capability):**
  - raw TPS without comparing to base — meaningless in isolation
- **Workspace slot requirements for valid bench data:**
  - `paired_draft`: draft model config must be present, correct, and pinned to matching base
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - card advertises reasoning traces but no slot has `emits_reasoning: true` — advertised capability untested


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest post-boundary evidence:** 2026-08-11
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `glm-4.7-flash:Q4_K_M` — 17.7 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - nothing distinctive — arch/vendor/capability all remain represented after removal
- **What we'd gain:** 17.7 GB disk

### Intake rationale

- **Intake age:** 46d ago (first-seen commit `84c15f78`)
- **Mentioned in 5 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## coding (41)
    > - `devstral-small-2:latest-ctx8k` \ - `devstral:24b` \ - `glm-4.7-flash:Q4_K_M` \ - `gpt-oss:20b` \ - `hf.co/Abiray/Agents-A1-Q4_K_M-GGUF:Q4_K_M` \ - `hf.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-ablit…
  - `docs/reselection/AUTOSEC_RESELECT_EVIDENCE_20260716T192100Z.md` — ## Gate Table (all 11 candidates, ranked by reliability_gate then redundant_call_rate)
    > | Model | reliability_gate | valid_rate | spiral_rate | redundant_call_rate | unique/8 | Failure mode | \ |---|---|---|---|---|---|---| \ | **glm-4.7-flash:Q4_K_M** | **PASS** | 1.00 | 0.00 | **0.00**…
  - `docs/reports/V10_CANDIDATE_BENCH_REVIEW.md` — ## Pull / smoke-load results
    > | `bench-north-mini-code` | North-Mini-Code-1.0-QAD (Cohere) | PASS | ~19.3 GB | \ | `bench-qwythos-9b` | Qwythos-9B-Claude-Mythos-5-1M (Empero) | PASS | ~5.6 GB | \ | `bench-glm47f-claude-distill` | …

### Capability profile

- **Architecture:** GLM
- **Quantization:** Q4_K_M (mixed)
- **Source:** ollama-library (`ollama-library`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'glm-4.7-flash:Q4_K_M'

### Fleet position

- **Bench workspaces routing here:** `bench-glm`
- **Same-arch (`GLM`) production workspaces:** 0
- **Same-arch bench workspaces:** 2
  - `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL` (via `bench-glm-reap`)
  - `hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf` (via `bench-glm-z1-rumination`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `GLM` workspaces in fleet:** 2
- **Other workspaces from `ollama-library`:** 40

### Card claims vs our slotting

- **Card source:** `https://ollama.com/library/glm-4.7-flash` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!doctype html> <html class="h-full overflow-y-scroll"> <head> <title>glm-4.7-flash</title>
- **Deployment signals extracted:** MoE architecture confirmed
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-glm` | tools: none
    > Benchmark: glm-4.7-flash:Q4_K_M (~13GB, ZhipuAI/Z.AI, MIT). 31B MoE, 4 experts/token (~3B active), 128K context. Non-Meta/Qwen lineage — diverse training and architecture. Coding bench 2026-06-21: quality 0.67 (template mismatch suspected). Head-to-head vs bench-glm-reap (REAP UD-Q4_K_XL quant). PROMOTE_POLICY: re-bench after chat template verification.
- **Alignment:** no distinctive claim/slot mismatch detected — slot config appears consistent with card

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `moe` — MoE architecture
- **Recommended harness:** bench_tps + MoE-aware profile (active-param observation)
- **Prompt corpus:** mixed-domain prompt matrix to exercise routing
- **Metrics to capture (beyond raw TPS):**
  - standard TPS
  - active-param distribution across prompt buckets
  - expert routing stability (does the same prompt route consistently)


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest evidence:** 2026-06-12 (59d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `gemma4:31b-it-qat-ctx8k` — 17.6 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - nothing distinctive — arch/vendor/capability all remain represented after removal
- **What we'd gain:** 17.6 GB disk

### Intake rationale

- **Intake age:** 39d ago (first-seen commit `5dd51bb6`)
- **Mentioned in 5 doc file(s):**
  - `docs/HOWTO.md` — ## 3. Workspaces
    > |---|---|---| \ | `auto` (Portal Auto Router) | `huihui_ai/qwen3.5-abliterated:9b-ctx8k` | LLM intent classifier routes onward | \ | `auto-daily` | `gemma4:26b-a4b-it-qat-ctx8k` | web_search, create_w…
  - `docs/MLX_CHANGES_2026-04-26.md` — ## Upgrades Applied
    > |---------|-----|-----|-------| \ | mlx (core) | 0.31.1 | 0.31.2 | Homebrew upgrade; Python bindings required manual copy of `core.cpython-314-darwin.so` and `nn/` modules from Cellar | \ | mlx-lm | 0…
  - `docs/ADMIN_GUIDE.md` — # Persona roster (138 personas)
    > | `gemma_e4b` | general | `auto-daily` | — | \ | `gemma_fast` | general | `auto-daily` | — | \ | `gemma_vision` | general | `auto-vision` | `gemma4:31b-it-qat-ctx8k` | \ | `gemmaresearchanalyst` | res…

### Capability profile

- **Architecture:** Gemma4
- **Parameters:** 31B
- **Source:** ollama-library (`ollama-library`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'gemma4:31b-it-qat-ctx8k'

### Fleet position

- **Bench workspaces routing here:** none (bench-orphaned)
- **Same-arch (`Gemma4`) production workspaces:** 2
  - `gemma4:26b-a4b-it-qat-ctx8k` (via `auto-daily`)
  - `gemma4:12b-it-qat-ctx8k` (via `auto-audio`)
- **Same-arch bench workspaces:** 12
  - `gemma4:26b-a4b-it-q4_K_M` (via `bench-gemma4-26b-optiq`)
  - `gemma4:12b-it-qat` (via `bench-gemma4-12b`)
  - `gemma4:e4b-it-q4_K_M` (via `bench-gemma4-e4b`)
  - `gemma4:e2b-it-qat` (via `bench-gemma4-e2b`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `Gemma4` workspaces in fleet:** 14
- **Other workspaces from `ollama-library`:** 41

### Card claims vs our slotting

- **Card source:** `https://ollama.com/library/gemma4` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!doctype html> <html class="h-full overflow-y-scroll"> <head> <title>gemma4</title>
- **Deployment signals extracted:** vision / multimodal capability advertised, specific chat template requirement, reasoning-trace capability, MoE architecture confirmed
- **Slotting:** bench-orphaned — nothing routes to this tag
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `vision` — Vision / multimodal (non-CUA)
- **Recommended harness:** vision probe (image → text tasks)
- **Prompt corpus:** image + question pairs across VQA, captioning, OCR
- **Metrics to capture (beyond raw TPS):**
  - VQA accuracy
  - caption quality
  - OCR fidelity if advertised
- **Do NOT measure (would produce invalid signal for this capability):**
  - text-only quality alone — misses the modality that justifies the model
- **Workspace slot requirements for valid bench data:**
  - `mmproj`: vision projector REQUIRED
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-gemma4`)
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest evidence:** 2026-06-21 (50d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `gemma4:31b-it-qat` — 17.6 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - nothing distinctive — arch/vendor/capability all remain represented after removal
- **What we'd gain:** 17.6 GB disk

### Intake rationale

- **Intake age:** 46d ago (first-seen commit `84c15f78`)
- **Mentioned in 5 doc file(s):**
  - `docs/HOWTO.md` — ## 3. Workspaces
    > |---|---|---| \ | `auto` (Portal Auto Router) | `huihui_ai/qwen3.5-abliterated:9b-ctx8k` | LLM intent classifier routes onward | \ | `auto-daily` | `gemma4:26b-a4b-it-qat-ctx8k` | web_search, create_w…
  - `docs/MLX_CHANGES_2026-04-26.md` — ## Upgrades Applied
    > |---------|-----|-----|-------| \ | mlx (core) | 0.31.1 | 0.31.2 | Homebrew upgrade; Python bindings required manual copy of `core.cpython-314-darwin.so` and `nn/` modules from Cellar | \ | mlx-lm | 0…
  - `docs/ADMIN_GUIDE.md` — # Persona roster (138 personas)
    > | `gemma_e4b` | general | `auto-daily` | — | \ | `gemma_fast` | general | `auto-daily` | — | \ | `gemma_vision` | general | `auto-vision` | `gemma4:31b-it-qat-ctx8k` | \ | `gemmaresearchanalyst` | res…

### Capability profile

- **Architecture:** Gemma4
- **Parameters:** 31B
- **Source:** ollama-library (`ollama-library`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'gemma4:31b-it-qat'

### Fleet position

- **Bench workspaces routing here:** `bench-gemma4-31b-qat`
- **Same-arch (`Gemma4`) production workspaces:** 2
  - `gemma4:26b-a4b-it-qat-ctx8k` (via `auto-daily`)
  - `gemma4:12b-it-qat-ctx8k` (via `auto-audio`)
- **Same-arch bench workspaces:** 11
  - `gemma4:26b-a4b-it-q4_K_M` (via `bench-gemma4-26b-optiq`)
  - `gemma4:12b-it-qat` (via `bench-gemma4-12b`)
  - `gemma4:e4b-it-q4_K_M` (via `bench-gemma4-e4b`)
  - `gemma4:e2b-it-qat` (via `bench-gemma4-e2b`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `Gemma4` workspaces in fleet:** 13
- **Other workspaces from `ollama-library`:** 40

### Card claims vs our slotting

- **Card source:** `https://ollama.com/library/gemma4` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!doctype html> <html class="h-full overflow-y-scroll"> <head> <title>gemma4</title>
- **Deployment signals extracted:** vision / multimodal capability advertised, specific chat template requirement, reasoning-trace capability, MoE architecture confirmed
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-gemma4-31b-qat` | tools: none
    > Benchmark: gemma4:31b-it-qat (Ollama, Google DeepMind, June 2026, Apache 2.0). 31B Dense QAT — ~18GB, vision+text, 256K ctx. QAT quality comparison vs production gemma4:31b-it-q4_K_M. PROMOTE_POLICY=confirm.
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - card advertises reasoning traces but no slot has `emits_reasoning: true` — advertised capability untested

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `vision` — Vision / multimodal (non-CUA)
- **Recommended harness:** vision probe (image → text tasks)
- **Prompt corpus:** image + question pairs across VQA, captioning, OCR
- **Metrics to capture (beyond raw TPS):**
  - VQA accuracy
  - caption quality
  - OCR fidelity if advertised
- **Do NOT measure (would produce invalid signal for this capability):**
  - text-only quality alone — misses the modality that justifies the model
- **Workspace slot requirements for valid bench data:**
  - `mmproj`: vision projector REQUIRED
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - card advertises reasoning traces but no slot has `emits_reasoning: true` — advertised capability untested


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest evidence:** 2026-06-21 (50d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:gemma-4-31b-jang-crack-Q4_K_M.gguf` — 17.4 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - **last model from `douyamv`** — vendor exits the fleet
  - NET-NEW vendor: `douyamv` (not in fleet elsewhere)
- **What we'd gain:** 17.4 GB disk

### Intake rationale

- **Intake age:** 46d ago (first-seen commit `84c15f78`)
- **Mentioned in 5 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — # Persona roster (138 personas)
    > | `gdprdpoadvisor` | compliance | `auto-compliance` | — | \ | `gemma4e4bvision` | general | `auto-vision` | — | \ | `gemma4jangvision` | general | `auto-vision` | `hf.co/douyamv/Gemma-4-31B-JANG_4M-CR…
  - `docs/_archive_execdocs/SECURITY_FLEET_REVIEW_2026-06.md` — ## 2. Security Group — Training Purpose Map
    > | `sylink/sylink:8b` | Qwen3-8B | SOC triage, threat intel, MITRE ATT&CK mapping, incident response | **Blue team** — defensive analysis, not offensive | \ | `supergemma4-26b-uncensored:Q4_K_M` | Gemm…
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## general (84)
    > - `hf.co/coder543/North-Mini-Code-1.0-QAD-GGUF:NVFP4` \ - `hf.co/deepreinforce-ai/Ornith-1.0-35B-GGUF:Q4_K_M` \ - `hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:gemma-4-31b-jang-crack-Q4_K_M.gguf` \ - …

### Capability profile

- **Architecture:** Gemma4
- **Parameters:** 31B
- **Quantization:** Q4_K_M (mixed)
- **Source:** huggingface (`douyamv`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:gemma-4-31b-jang-crack-Q4_K_M.gguf'

### Fleet position

- **Bench workspaces routing here:** `bench-gemma4-31b-crack`
- **Same-arch (`Gemma4`) production workspaces:** 2
  - `gemma4:26b-a4b-it-qat-ctx8k` (via `auto-daily`)
  - `gemma4:12b-it-qat-ctx8k` (via `auto-audio`)
- **Same-arch bench workspaces:** 11
  - `gemma4:26b-a4b-it-q4_K_M` (via `bench-gemma4-26b-optiq`)
  - `gemma4:12b-it-qat` (via `bench-gemma4-12b`)
  - `gemma4:e4b-it-q4_K_M` (via `bench-gemma4-e4b`)
  - `gemma4:e2b-it-qat` (via `bench-gemma4-e2b`)
- **Net-new signals (fleet has no other with these):**
  - vendor: `douyamv` (not in fleet elsewhere)

### Diversity impact

- **Other `Gemma4` workspaces in fleet:** 13
- ⚠ **VENDOR LOSS**: `douyamv` exits the fleet

### Card claims vs our slotting

- **Card source:** `https://huggingface.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF/raw/main/README.md` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > GGUF quantizations of Gemma-4-31B-JANG_4M-CRACK for use with llama.cpp, LM Studio, Ollama, and other GGUF-compatible inference engines.
- **Deployment signals extracted:** vision / multimodal capability advertised
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-gemma4-31b-crack` | tools: none
    > Benchmark: hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:gemma-4-31b-jang-crack-Q4_K_M.gguf (douyamv quant of dealignai/Gemma-4-31B-JANG_4M-CRACK, Gemma license, 31B dense, ~20GB Q4_K_M). JANG_4M-CRACK: abliterated + uncensored Gemma 4 31B fine-tune with 4M context. Vision+text. Head-to-head vs bench-gemma4-31b-qat (refusals baseline) and bench-huihui-qwen36-27b (abliterated comparison). PROBE RESU…
- **Alignment:** no distinctive claim/slot mismatch detected — slot config appears consistent with card

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `vision` — Vision / multimodal (non-CUA)
- **Recommended harness:** vision probe (image → text tasks)
- **Prompt corpus:** image + question pairs across VQA, captioning, OCR
- **Metrics to capture (beyond raw TPS):**
  - VQA accuracy
  - caption quality
  - OCR fidelity if advertised
- **Do NOT measure (would produce invalid signal for this capability):**
  - text-only quality alone — misses the modality that justifies the model
- **Workspace slot requirements for valid bench data:**
  - `mmproj`: vision projector REQUIRED


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest post-boundary evidence:** 2026-08-11
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `gemma4:26b-a4b-it-q4_K_M` — 16.8 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - nothing distinctive — arch/vendor/capability all remain represented after removal
- **What we'd gain:** 16.8 GB disk

### Intake rationale

- **Intake age:** 46d ago (first-seen commit `84c15f78`)
- **Mentioned in 5 doc file(s):**
  - `docs/HOWTO.md` — ## 3. Workspaces
    > |---|---|---| \ | `auto` (Portal Auto Router) | `huihui_ai/qwen3.5-abliterated:9b-ctx8k` | LLM intent classifier routes onward | \ | `auto-daily` | `gemma4:26b-a4b-it-qat-ctx8k` | web_search, create_w…
  - `docs/MLX_CHANGES_2026-04-26.md` — ## Upgrades Applied
    > |---------|-----|-----|-------| \ | mlx (core) | 0.31.1 | 0.31.2 | Homebrew upgrade; Python bindings required manual copy of `core.cpython-314-darwin.so` and `nn/` modules from Cellar | \ | mlx-lm | 0…
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `gemma-4-26b-a4b-it-QAT-4bit` \ - `gemma4:12b-it-qat` \ - `gemma4:26b-a4b-it-q4_K_M` \ - `gemma4:26b-a4b-it-qat` \ - `gemma4:26b-a4b-it-qat-ctx8k` \ - `gemma4:31b-it-qat`

### Capability profile

- **Architecture:** Gemma4
- **Parameters:** 26B
- **Quantization:** Q4_K_M (mixed)
- **Source:** ollama-library (`ollama-library`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'gemma4:26b-a4b-it-q4_K_M'

### Fleet position

- **Bench workspaces routing here:** `bench-gemma4-26b-optiq`
- **Same-arch (`Gemma4`) production workspaces:** 2
  - `gemma4:26b-a4b-it-qat-ctx8k` (via `auto-daily`)
  - `gemma4:12b-it-qat-ctx8k` (via `auto-audio`)
- **Same-arch bench workspaces:** 11
  - `gemma4:12b-it-qat` (via `bench-gemma4-12b`)
  - `gemma4:e4b-it-q4_K_M` (via `bench-gemma4-e4b`)
  - `gemma4:e2b-it-qat` (via `bench-gemma4-e2b`)
  - `gemma4:e4b-it-qat` (via `bench-gemma4-e4b-qat`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `Gemma4` workspaces in fleet:** 13
- **Other workspaces from `ollama-library`:** 40

### Card claims vs our slotting

- **Card source:** `https://ollama.com/library/gemma4` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!doctype html> <html class="h-full overflow-y-scroll"> <head> <title>gemma4</title>
- **Deployment signals extracted:** vision / multimodal capability advertised, specific chat template requirement, reasoning-trace capability, MoE architecture confirmed
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-gemma4-26b-optiq` | tools: none
    > Benchmark: gemma4:26b-a4b-it-q4_K_M (GGUF, Ollama, MoE 4B active), pairs against auto-daily.
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - card advertises vision/multimodal but no slot text mentions vision, mmproj, or image tasks — advertised capability likely untested
  - card advertises reasoning traces but no slot has `emits_reasoning: true` — advertised capability untested

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `vision` — Vision / multimodal (non-CUA)
- **Recommended harness:** vision probe (image → text tasks)
- **Prompt corpus:** image + question pairs across VQA, captioning, OCR
- **Metrics to capture (beyond raw TPS):**
  - VQA accuracy
  - caption quality
  - OCR fidelity if advertised
- **Do NOT measure (would produce invalid signal for this capability):**
  - text-only quality alone — misses the modality that justifies the model
- **Workspace slot requirements for valid bench data:**
  - `mmproj`: vision projector REQUIRED
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - `bench-gemma4-26b-optiq`: needs vision projector (`mmproj`) — the bench cannot produce valid multimodal data without it
  - card advertises vision/multimodal but no slot text mentions vision, mmproj, or image tasks — advertised capability likely untested
  - card advertises reasoning traces but no slot has `emits_reasoning: true` — advertised capability untested


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest evidence:** 2026-06-28 (43d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `hf.co/bartowski/Qwen_Qwen3.6-27B-GGUF:Q4_K_M` — 16.7 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - nothing distinctive — arch/vendor/capability all remain represented after removal
- **What we'd gain:** 16.7 GB disk

### Intake rationale

- **Intake age:** 46d ago (first-seen commit `84c15f78`)
- **Mentioned in 3 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## coding (41)
    > - `hf.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated-gguf-4bit:Q4_K_M` \ - `hf.co/Mia-AiLab/Qwable-3.6-35b:Qwable-3.6-35b_q4_k_m.gguf` \ - `hf.co/bartowski/Qwen_Qwen3.6-27B-GGUF:Q4_K_M` \ - `hf.…
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## coding (41)
    > - `hf.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated-gguf-4bit:Q4_K_M` \ - `hf.co/Mia-AiLab/Qwable-3.6-35b:Qwable-3.6-35b_q4_k_m.gguf` \ - `hf.co/bartowski/Qwen_Qwen3.6-27B-GGUF:Q4_K_M` \ - `hf.…
  - `portal_wiki/canonical/unit-model-catalog-hf-co-bartowski-qwen-qwen3-6-27b-gguf-q4-k-m.md` — (no nearby heading)
    > id: unit-model-catalog-hf-co-bartowski-qwen-qwen3-6-27b-gguf-q4-k-m \ kind: what \ title: "MODEL_CATALOG \u2014 `hf.co/bartowski/Qwen_Qwen3.6-27B-GGUF:Q4_K_M`" \ sources: \ - type: code \   path: conf…

### Capability profile

- **Architecture:** Qwen3.6
- **Parameters:** 27B
- **Quantization:** Q4_K_M (mixed)
- **Source:** huggingface (`bartowski`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'hf.co/bartowski/Qwen_Qwen3.6-27B-GGUF:Q4_K_M'

### Fleet position

- **Bench workspaces routing here:** `bench-qwen36-27b-optiq`
- **Same-arch (`Qwen3.6`) production workspaces:** 3
  - `huihui_ai/Qwen3.6-abliterated:27b-ctx8k` (via `auto-general-uncensored`)
  - `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k` (via `auto-creative`)
  - `qwen3.6:27b-q4_K_M-ctx16k` (via `auto-council`)
- **Same-arch bench workspaces:** 10
  - `qwen3.6:27b-q4_K_M` (via `bench-qwen36-27b`)
  - `portal5/qwen3.6-27b-mtp:q8_0-drafted` (via `bench-qwen36-27b-mtp`)
  - `qwen3.6:35b-a3b-q4_K_M` (via `bench-qwen36-35b-a3b`)
  - `qwen3.6:27b-q4_K_M` (via `bench-qwen36-27b-ud`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `Qwen3.6` workspaces in fleet:** 13
- **Other workspaces from `bartowski`:** 3

### Card claims vs our slotting

- **Card source:** `https://huggingface.co/bartowski/Qwen_Qwen3.6-27B-GGUF/raw/main/README.md` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > Using <a href="https://github.com/ggml-org/llama.cpp/">llama.cpp</a> release <a href="https://github.com/ggml-org/llama.cpp/releases/tag/b9222">b9222</a> for quantization.
- **Deployment signals extracted:** reasoning-trace capability, speculative / MTP drafting
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-qwen36-27b-optiq` | tools: none
    > Benchmark: Qwen3.6-27B with OptiQ per-layer quantization (sensitive layers 8-bit, robust layers 4-bit). Head-to-head vs bench-qwen36-27b (plain Q4_K_M) — TASK_QUANT_TRUEUP_V1 Finding A.
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - card advertises reasoning traces but no slot has `emits_reasoning: true` — advertised capability untested

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `mtp-speculative` — MTP / speculative drafting
- **Recommended harness:** MTP-aware bench — draft acceptance rate + wall-time speedup vs base
- **Prompt corpus:** IDENTICAL to base model's bench for direct comparison
- **Metrics to capture (beyond raw TPS):**
  - draft token acceptance rate (headline signal)
  - wall-time speedup vs base model on identical prompts
  - quality parity vs base (any regression kills the value proposition)
- **Do NOT measure (would produce invalid signal for this capability):**
  - raw TPS without comparing to base — meaningless in isolation
- **Workspace slot requirements for valid bench data:**
  - `paired_draft`: draft model config must be present, correct, and pinned to matching base
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - `bench-qwen36-27b-optiq`: MTP benching requires paired draft model config — check `predict_limit` and draft binding
  - card advertises reasoning traces but no slot has `emits_reasoning: true` — advertised capability untested


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 1 invalid (pre-boundary)
- **Avg TPS (pre-boundary — INVALID for decisions):** 14.4 — captured under prior stack
- **Newest evidence:** 2026-06-21 (50d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `qwen3.6:27b-mtp-q4_K_M` — 16.5 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - capability: MTP speculative drafting (draft model bound to base)
- **What we'd gain:** 16.5 GB disk

### Intake rationale

- **Intake age:** 0d ago (first-seen commit `d6603676`)
- **Mentioned in 5 doc file(s):**
  - `docs/HOWTO.md` — ## 6. Security Analysis
    > | `redteam-deep` | Simulation | `supergemma4-26b-uncensored:Q4_K_M-ctx64k` | none | \ | `blueteam` | Research | `granite4.1:8b-ctx8k` | web_search, web_fetch, classify_vulnerability, kb_search, kb_lis…
  - `docs/MTP_BENCH_20260528.md` — # MTP A/B Bench Results — 2026-05-28
    > Hardware: Apple M4 Pro, 64 GB unified memory \ Model: Qwen3.6-27B dense (4-bit trunk) \  \ ## Results
  - `docs/QWEN_TEMPLATE_PROBE.md` — ## Per-model template state
    > | `Jackrong/MLX-Qwopus3.5-27B-v3-8bit` | qwen3.5 | **GREEN** | clean | hf-cache | chat_template.jinja | \ | `Jackrong/MLX-Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-v2-4bit` | qwen3.5 | **GREEN**…

### Capability profile

- **Architecture:** Qwen3.6
- **Parameters:** 27B
- **Quantization:** Q4_K_M (mixed)
- **Source:** ollama-library (`ollama-library`)
- **Distinguishing features (from tag pattern):**
  - MTP speculative drafting (draft model bound to base)
- **Reversibility:** ollama pull 'qwen3.6:27b-mtp-q4_K_M'

### Fleet position

- **Bench workspaces routing here:** none (bench-orphaned)
- **Same-arch (`Qwen3.6`) production workspaces:** 3
  - `huihui_ai/Qwen3.6-abliterated:27b-ctx8k` (via `auto-general-uncensored`)
  - `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k` (via `auto-creative`)
  - `qwen3.6:27b-q4_K_M-ctx16k` (via `auto-council`)
- **Same-arch bench workspaces:** 11
  - `qwen3.6:27b-q4_K_M` (via `bench-qwen36-27b`)
  - `portal5/qwen3.6-27b-mtp:q8_0-drafted` (via `bench-qwen36-27b-mtp`)
  - `qwen3.6:35b-a3b-q4_K_M` (via `bench-qwen36-35b-a3b`)
  - `qwen3.6:27b-q4_K_M` (via `bench-qwen36-27b-ud`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `Qwen3.6` workspaces in fleet:** 14
- **Other workspaces from `ollama-library`:** 41

### Card claims vs our slotting

- **Card source:** `https://ollama.com/library/qwen3.6` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!doctype html> <html class="h-full overflow-y-scroll"> <head> <title>qwen3.6</title>
- **Deployment signals extracted:** vision / multimodal capability advertised, reasoning-trace capability
- **Slotting:** bench-orphaned — nothing routes to this tag
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `vision` — Vision / multimodal (non-CUA)
- **Recommended harness:** vision probe (image → text tasks)
- **Prompt corpus:** image + question pairs across VQA, captioning, OCR
- **Metrics to capture (beyond raw TPS):**
  - VQA accuracy
  - caption quality
  - OCR fidelity if advertised
- **Do NOT measure (would produce invalid signal for this capability):**
  - text-only quality alone — misses the modality that justifies the model
- **Workspace slot requirements for valid bench data:**
  - `mmproj`: vision projector REQUIRED
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-qwen3.6`)
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 2 invalid (pre-boundary)
- **Avg TPS (pre-boundary — INVALID for decisions):** 4.3 — captured under prior stack
- **Newest evidence:** 2026-06-28 (43d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `hf.co/mradermacher/gemma-4-26B-A4B-it-uncensored-heretic-GGUF:gemma-4-26B-A4B-it-uncensored-heretic.Q4_K_M.gguf` — 16.4 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - capability: Heretic-modified (jailbreak retraining)
- **What we'd gain:** 16.4 GB disk

### Intake rationale

- **Intake age:** 0d ago (first-seen commit `d6603676`)
- **Mentioned in 4 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `hf.co/mradermacher/Qwen3.5-9B-Claude-4.6-HighIQ-THINKING-HERETIC-UNCENSORED-GGUF:Q4_K_M` \ - `hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M` \ - `hf.co/mradermacher/gemma-4-26B-A4B-it-uncensored-here…
  - `docs/generated/ARCHITECTURE_MAP.md` — ## Knowledge Layer
    > | `unit-model-catalog-hf-co-mitkox-fastcontext-1-0-4b-sft-q4-k-m-gguf-q4-k-m` | what | 2 | \ | `unit-model-catalog-hf-co-mradermacher-cybersecqwen-4b-gguf-q4-k-m-dropped-tool-call-blocker-fixed-2026-0…
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## general (84)
    > - `hf.co/mradermacher/Qwen3.5-9B-Claude-4.6-HighIQ-THINKING-HERETIC-UNCENSORED-GGUF:Q4_K_M` \ - `hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M` \ - `hf.co/mradermacher/gemma-4-26B-A4B-it-uncensored-here…

### Capability profile

- **Architecture:** Gemma4
- **Parameters:** 26B
- **Quantization:** Q4_K_M (mixed)
- **Source:** huggingface (`mradermacher`)
- **Distinguishing features (from tag pattern):**
  - Heretic-modified (jailbreak retraining)
- **Reversibility:** ollama pull 'hf.co/mradermacher/gemma-4-26B-A4B-it-uncensored-heretic-GGUF:gemma-4-26B-A4B-it-uncensored-heretic.Q4_K_M.gguf'

### Fleet position

- **Bench workspaces routing here:** none (bench-orphaned)
- **Same-arch (`Gemma4`) production workspaces:** 2
  - `gemma4:26b-a4b-it-qat-ctx8k` (via `auto-daily`)
  - `gemma4:12b-it-qat-ctx8k` (via `auto-audio`)
- **Same-arch bench workspaces:** 12
  - `gemma4:26b-a4b-it-q4_K_M` (via `bench-gemma4-26b-optiq`)
  - `gemma4:12b-it-qat` (via `bench-gemma4-12b`)
  - `gemma4:e4b-it-q4_K_M` (via `bench-gemma4-e4b`)
  - `gemma4:e2b-it-qat` (via `bench-gemma4-e2b`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `Gemma4` workspaces in fleet:** 14
- **Other workspaces from `mradermacher`:** 7

### Card claims vs our slotting

- **Card source:** `https://huggingface.co/mradermacher/gemma-4-26B-A4B-it-uncensored-heretic-GGUF/raw/main/README.md` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!-- ### quantize_version: 2 --> <!-- ### output_tensor_quantised: 1 --> <!-- ### convert_type: hf --> <!-- ### vocab_type:  --> <!-- ### tags:  --> <!-- ### quants:  x-f16 Q4_K_S Q2_K Q8_0 Q6_K Q3_K_M Q3_K_S Q3_K_L Q4_K_M Q5_K_S Q5_K_M IQ4_XS --> <!-- ### quants_skip:  --> <!-- ### skip_mmproj:  --> static quants of https://huggingface.co/llmfan46/gemma-4-26B-A4B-it-uncensored-heretic
- **Deployment signals extracted:** vision / multimodal capability advertised, abliterated / uncensored
- **Slotting:** bench-orphaned — nothing routes to this tag
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `vision` — Vision / multimodal (non-CUA)
- **Recommended harness:** vision probe (image → text tasks)
- **Prompt corpus:** image + question pairs across VQA, captioning, OCR
- **Metrics to capture (beyond raw TPS):**
  - VQA accuracy
  - caption quality
  - OCR fidelity if advertised
- **Do NOT measure (would produce invalid signal for this capability):**
  - text-only quality alone — misses the modality that justifies the model
- **Workspace slot requirements for valid bench data:**
  - `mmproj`: vision projector REQUIRED
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-gemma-4-26B-A4B-it-u`)
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 2 invalid (pre-boundary)
- **Avg TPS (pre-boundary — INVALID for decisions):** 22.8 — captured under prior stack
- **Newest evidence:** 2026-06-28 (43d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `sylink/sylink:8b` — 15.3 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - **last model from `sylink`** — vendor exits the fleet
  - NET-NEW vendor: `sylink` (not in fleet elsewhere)
- **What we'd gain:** 15.3 GB disk

### Intake rationale

- **Intake age:** 46d ago (first-seen commit `84c15f78`)
- **Mentioned in 5 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `qwen3.6:35b-a3b-q4_K_M` \ - `supergemma4-26b-uncensored:Q4_K_M` \ - `sylink/sylink:8b` \  \ ## omlx (2)
  - `docs/generated/ARCHITECTURE_MAP.md` — ## Knowledge Layer
    > | `unit-model-catalog-supergemma4-26b-uncensored-q4-k-m` | what | 2 | \ | `unit-model-catalog-supergemma4-26b-uncensored-q4-k-m-ctx64k` | what | 2 | \ | `unit-model-catalog-sylink-sylink-8b` | what | …
  - `docs/_archive_execdocs/SECURITY_FLEET_REVIEW_2026-06.md` — ## 2. Security Group — Training Purpose Map
    > | `huihui_ai/baronllm-abliterated` | Llama-3.1-8B | 53K cybersec examples, 200+ cybersec domains (AlicanKiraz0/Cybersecurity-BaronLLM) | Broad security domain knowledge — offensive and defensive | \ |…

### Capability profile

- **Architecture:** unknown
- **Parameters:** 8B
- **Source:** ollama-library-namespaced (`sylink`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'sylink/sylink:8b'

### Fleet position

- **Bench workspaces routing here:** `bench-sylink-8b`, `bench-sylink`
- **Same-arch (`unknown`) production workspaces:** 0
- **Same-arch bench workspaces:** 0
- **Net-new signals (fleet has no other with these):**
  - vendor: `sylink` (not in fleet elsewhere)

### Diversity impact

- **Other `unknown` workspaces in fleet:** 0
- ⚠ **VENDOR LOSS**: `sylink` exits the fleet

### Card claims vs our slotting

- **Card source:** `https://ollama.com/sylink/sylink` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!doctype html> <html class="h-full overflow-y-scroll"> <head> <title>sylink/sylink</title>
- **What portal.yaml says we slotted it for** (2 bench workspace(s)):
  - `bench-sylink-8b` | tools: none | emits_reasoning
    > Expert-role candidate comparison (GATE-D ablation): sylink/sylink:8b, security-domain 8B model.
  - `bench-sylink` | tools: none
    > BENCH RESULT 2026-06-16: avg=0.311 on red-team structured output — correctly RETIRED from offensive workspaces. Training purpose is SOC/DFIR/ATT&CK (blue team), not red team prose. PROMOTED to auto-blueteam primary 2026-06-21 (SECURITY_FLEET_REVIEW_2026-06): fleet bench chain 1.00/1.00, depth 12 (deepest 8B), purpose-aligned with its training. Model: sylink/sylink:8b
- **Alignment:** no distinctive claim/slot mismatch detected — slot config appears consistent with card

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `general` — General / no specific capability advertised
- **Recommended harness:** bench_tps + portal5_persona_matrix (standard fleet path)
- **Prompt corpus:** default persona matrix across the model's target lane
- **Metrics to capture (beyond raw TPS):**
  - avg_tps vs the 20 t/s floor
  - quality_score vs same-lane incumbent


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest post-boundary evidence:** 2026-08-11
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `sylink/sylink:8b-ctx8k` — 15.3 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - nothing distinctive — arch/vendor/capability all remain represented after removal
- **What we'd gain:** 15.3 GB disk

### Intake rationale

- **Intake age:** 39d ago (first-seen commit `5dd51bb6`)
- **Mentioned in 5 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## security (32)
    > - `supergemma4-26b-uncensored:Q4_K_M-ctx64k` \ - `sylink/sylink:8b` \ - `sylink/sylink:8b-ctx8k` \  \ ## vision (16)
  - `docs/generated/ARCHITECTURE_MAP.md` — ## Knowledge Layer
    > | `unit-model-catalog-supergemma4-26b-uncensored-q4-k-m` | what | 2 | \ | `unit-model-catalog-supergemma4-26b-uncensored-q4-k-m-ctx64k` | what | 2 | \ | `unit-model-catalog-sylink-sylink-8b` | what | …
  - `docs/_archive_execdocs/SECURITY_FLEET_REVIEW_2026-06.md` — # Security Fleet Review — June 2026
    > **TPS data**: `bench_tps_20260621T030634Z.json` (286 results)   \ **Completion bench A**: `sec_bench_20260621T132602Z.json` (Run A — baronllm-abl, Foundation-Sec, devstral-small-2)   \ **Completion be…

### Capability profile

- **Architecture:** unknown
- **Parameters:** 8B
- **Source:** ollama-library-namespaced (`sylink`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'sylink/sylink:8b-ctx8k'

### Fleet position

- **Bench workspaces routing here:** none (bench-orphaned)
- **Same-arch (`unknown`) production workspaces:** 0
- **Same-arch bench workspaces:** 0
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `unknown` workspaces in fleet:** 0
- **Other workspaces from `sylink`:** 2

### Card claims vs our slotting

- **Card source:** `https://ollama.com/sylink/sylink` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!doctype html> <html class="h-full overflow-y-scroll"> <head> <title>sylink/sylink</title>
- **Slotting:** bench-orphaned — nothing routes to this tag
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `general` — General / no specific capability advertised
- **Recommended harness:** bench_tps + portal5_persona_matrix (standard fleet path)
- **Prompt corpus:** default persona matrix across the model's target lane
- **Metrics to capture (beyond raw TPS):**
  - avg_tps vs the 20 t/s floor
  - quality_score vs same-lane incumbent
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest post-boundary evidence:** 2026-08-11
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `phi4:14b-q8_0` — 14.5 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - nothing distinctive — arch/vendor/capability all remain represented after removal
- **What we'd gain:** 14.5 GB disk

### Intake rationale

- **Intake age:** 0d ago (first-seen commit `d6603676`)
- **Mentioned in 3 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `omnicoder2:9b-q4_k_m` \ - `phi4-mini` \ - `phi4:14b-q8_0` \ - `portal5/deepwen-3.6:q4.5-moq` \ - `portal5/deepwen-3.6:q4.5-moq-ctx32k` \ - `portal5/gemma4-12b:q4_K_M-ctx8k`
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## general (84)
    > - `omnicoder2:9b-q4_k_m` \ - `phi4-mini` \ - `phi4:14b-q8_0` \ - `portal5/deepwen-3.6:q4.5-moq` \ - `portal5/deepwen-3.6:q4.5-moq-ctx32k` \ - `portal5/gemma4-12b:q4_K_M-ctx8k`
  - `portal_wiki/canonical/unit-model-catalog-phi4-14b-q8-0.md` — (no nearby heading)
    > id: unit-model-catalog-phi4-14b-q8-0 \ kind: what \ title: "MODEL_CATALOG \u2014 `phi4:14b-q8_0`" \ sources: \ - type: code \   path: config/backends.yaml

### Capability profile

- **Architecture:** unknown
- **Parameters:** 14B
- **Quantization:** Q8_0
- **Source:** ollama-library (`ollama-library`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'phi4:14b-q8_0'

### Fleet position

- **Bench workspaces routing here:** none (bench-orphaned)
- **Same-arch (`unknown`) production workspaces:** 0
- **Same-arch bench workspaces:** 0
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `unknown` workspaces in fleet:** 0
- **Other workspaces from `ollama-library`:** 41

### Card claims vs our slotting

- **Card source:** `https://ollama.com/library/phi4` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!doctype html> <html class="h-full overflow-y-scroll"> <head> <title>phi4</title>
- **Deployment signals extracted:** reasoning-trace capability
- **Slotting:** bench-orphaned — nothing routes to this tag
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `reasoning-explicit` — Explicit reasoning / thinking traces
- **Recommended harness:** reasoning-aware persona matrix — capture and score the thinking traces, not just final answers
- **Prompt corpus:** multi-step reasoning tasks: math, logic, planning, code with edge cases
- **Metrics to capture (beyond raw TPS):**
  - task success rate WITH reasoning captured
  - reasoning coherence score
  - TPS separated by reasoning-on vs reasoning-off runs
  - trace length vs task complexity
- **Do NOT measure (would produce invalid signal for this capability):**
  - single-turn factual recall (doesn't exercise reasoning)
- **Workspace slot requirements for valid bench data:**
  - `emits_reasoning`: true — otherwise the harness sees a truncated model
  - `predict_limit`: high enough to fit thinking traces (8k+ typical)
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-phi4`)
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 2 invalid (pre-boundary)
- **Avg TPS (pre-boundary — INVALID for decisions):** 8.3 — captured under prior stack
- **Newest evidence:** 2026-06-28 (43d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `mistral-small3.2:24b` — 14.1 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - nothing distinctive — arch/vendor/capability all remain represented after removal
- **What we'd gain:** 14.1 GB disk

### Intake rationale

- **Intake age:** 19d ago (first-seen commit `d52d54c8`)
- **Mentioned in 3 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `llama3.2:3b-instruct-q8_0-ctx8k` \ - `meta-secalign-8b-q4_k_m:latest` \ - `mistral-small3.2:24b` \ - `muse-glimmer:30b-mlx` \ - `omnicoder2:9b-q4_k_m` \ - `phi4-mini`
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## general (84)
    > - `llama3.2:3b-instruct-q8_0-ctx8k` \ - `meta-secalign-8b-q4_k_m:latest` \ - `mistral-small3.2:24b` \ - `muse-glimmer:30b-mlx` \ - `omnicoder2:9b-q4_k_m` \ - `phi4-mini`
  - `portal_wiki/canonical/unit-model-catalog-mistral-small3-2-24b.md` — (no nearby heading)
    > id: unit-model-catalog-mistral-small3-2-24b \ kind: what \ title: "MODEL_CATALOG \u2014 `mistral-small3.2:24b`" \ sources: \ - type: code \   path: config/backends.yaml

### Capability profile

- **Architecture:** Mistral
- **Parameters:** 24B
- **Source:** ollama-library (`ollama-library`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'mistral-small3.2:24b'

### Fleet position

- **Bench workspaces routing here:** none (bench-orphaned)
- **Same-arch (`Mistral`) production workspaces:** 0
- **Same-arch bench workspaces:** 1
  - `hf.co/Andycurrent/Mistral-7B-Uncensored-GGUF:Q4_K_M` (via `bench-mistral7b-uncensored`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `Mistral` workspaces in fleet:** 1
- **Other workspaces from `ollama-library`:** 41

### Card claims vs our slotting

- **Card source:** `https://ollama.com/library/mistral-small3.2` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!doctype html> <html class="h-full overflow-y-scroll"> <head> <title>mistral-small3.2</title>
- **Deployment signals extracted:** vision / multimodal capability advertised
- **Slotting:** bench-orphaned — nothing routes to this tag
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `vision` — Vision / multimodal (non-CUA)
- **Recommended harness:** vision probe (image → text tasks)
- **Prompt corpus:** image + question pairs across VQA, captioning, OCR
- **Metrics to capture (beyond raw TPS):**
  - VQA accuracy
  - caption quality
  - OCR fidelity if advertised
- **Do NOT measure (would produce invalid signal for this capability):**
  - text-only quality alone — misses the modality that justifies the model
- **Workspace slot requirements for valid bench data:**
  - `mmproj`: vision projector REQUIRED
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-mistral-small3.2`)
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 2 invalid (pre-boundary)
- **Avg TPS (pre-boundary — INVALID for decisions):** 8.45 — captured under prior stack
- **Newest evidence:** 2026-06-28 (43d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `devstral-small-2:latest-ctx8k` — 14.1 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - nothing distinctive — arch/vendor/capability all remain represented after removal
- **What we'd gain:** 14.1 GB disk

### Intake rationale

- **Intake age:** 39d ago (first-seen commit `5dd51bb6`)
- **Mentioned in 5 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — # Persona roster (138 personas)
    > | `devopsautomator` | coding | `auto-coding` | — | \ | `devopsengineer` | general | `auto-reasoning` | — | \ | `devstral_coder` | coding | `auto-coding` | `devstral-small-2:latest-ctx8k` | \ | `diagra…
  - `docs/generated/ARCHITECTURE_MAP.md` — ## Knowledge Layer
    > | `unit-model-catalog-deepseek-r1-32b-q4-k-m` | what | 2 | \ | `unit-model-catalog-devstral-24b` | what | 2 | \ | `unit-model-catalog-devstral-small-2` | what | 2 | \ | `unit-model-catalog-devstral-sm…
  - `docs/reselection/AUTOSEC_RESELECT_EVIDENCE_20260716T192100Z.md` — ## Gate Table (all 11 candidates, ranked by reliability_gate then redundant_call_rate)
    > | Qwen3.6-abliterated:27b | PASS (gate 1 only, n=1) | 1.00 | 0.00 | 0.00 | 1 | **DISQUALIFIED by coverage floor** — only 1 tool call ever emitted (trivial valid_rate on n=1), then stuck narrating for …

### Capability profile

- **Architecture:** unknown
- **Source:** ollama-library (`ollama-library`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'devstral-small-2:latest-ctx8k'

### Fleet position

- **Bench workspaces routing here:** none (bench-orphaned)
- **Same-arch (`unknown`) production workspaces:** 0
- **Same-arch bench workspaces:** 0
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `unknown` workspaces in fleet:** 0
- **Other workspaces from `ollama-library`:** 41

### Card claims vs our slotting

- **Card source:** `https://ollama.com/library/devstral-small-2` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!doctype html> <html class="h-full overflow-y-scroll"> <head> <title>devstral-small-2</title>
- **Card-advertised strengths:**
  - **Use Cases:** AI Code Assistants, Agentic Coding, and Software Engineering Tasks. Leveraging advanced AI capabilities for complex tool integration and deep codebase understanding in coding environments.
- **Deployment signals extracted:** vision / multimodal capability advertised
- **Slotting:** bench-orphaned — nothing routes to this tag
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here
- **Card-advertised capabilities with no keyword overlap in slot config** (may be untested):
  - Use Cases

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `vision` — Vision / multimodal (non-CUA)
- **Recommended harness:** vision probe (image → text tasks)
- **Prompt corpus:** image + question pairs across VQA, captioning, OCR
- **Metrics to capture (beyond raw TPS):**
  - VQA accuracy
  - caption quality
  - OCR fidelity if advertised
- **Do NOT measure (would produce invalid signal for this capability):**
  - text-only quality alone — misses the modality that justifies the model
- **Workspace slot requirements for valid bench data:**
  - `mmproj`: vision projector REQUIRED
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-devstral-small-2`)
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest evidence:** 2026-06-21 (50d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `devstral-small-2:latest` — 14.1 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - nothing distinctive — arch/vendor/capability all remain represented after removal
- **What we'd gain:** 14.1 GB disk

### Intake rationale

- **Intake age:** 39d ago (first-seen commit `5dd51bb6`)
- **Mentioned in 5 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — # Persona roster (138 personas)
    > | `devopsautomator` | coding | `auto-coding` | — | \ | `devopsengineer` | general | `auto-reasoning` | — | \ | `devstral_coder` | coding | `auto-coding` | `devstral-small-2:latest-ctx8k` | \ | `diagra…
  - `docs/generated/ARCHITECTURE_MAP.md` — ## Knowledge Layer
    > | `unit-model-catalog-deepseek-r1-32b-q4-k-m` | what | 2 | \ | `unit-model-catalog-devstral-24b` | what | 2 | \ | `unit-model-catalog-devstral-small-2` | what | 2 | \ | `unit-model-catalog-devstral-sm…
  - `docs/reselection/AUTOSEC_RESELECT_EVIDENCE_20260716T192100Z.md` — ## Gate Table (all 11 candidates, ranked by reliability_gate then redundant_call_rate)
    > | Qwen3.6-abliterated:27b | PASS (gate 1 only, n=1) | 1.00 | 0.00 | 0.00 | 1 | **DISQUALIFIED by coverage floor** — only 1 tool call ever emitted (trivial valid_rate on n=1), then stuck narrating for …

### Capability profile

- **Architecture:** unknown
- **Source:** ollama-library (`ollama-library`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'devstral-small-2:latest'

### Fleet position

- **Bench workspaces routing here:** `bench-devstral-small-2`
- **Same-arch (`unknown`) production workspaces:** 0
- **Same-arch bench workspaces:** 0
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `unknown` workspaces in fleet:** 0
- **Other workspaces from `ollama-library`:** 40

### Card claims vs our slotting

- **Card source:** `https://ollama.com/library/devstral-small-2` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!doctype html> <html class="h-full overflow-y-scroll"> <head> <title>devstral-small-2</title>
- **Card-advertised strengths:**
  - **Use Cases:** AI Code Assistants, Agentic Coding, and Software Engineering Tasks. Leveraging advanced AI capabilities for complex tool integration and deep codebase understanding in coding environments.
- **Deployment signals extracted:** vision / multimodal capability advertised
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-devstral-small-2` | tools: none
    > Benchmark: devstral-small-2 (Ollama, Mistral AI + All Hands AI, Dec 2025, Apache 2.0, 24B, ~14GB Q4). Devstral V2: 256K ctx, vision added, improved SWE-bench vs devstral:24b (V1). PROMOTE_POLICY=confirm.
- **Card-advertised capabilities with no keyword overlap in slot config** (may be untested):
  - `Use Cases` — no keyword overlap with any slot description

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `vision` — Vision / multimodal (non-CUA)
- **Recommended harness:** vision probe (image → text tasks)
- **Prompt corpus:** image + question pairs across VQA, captioning, OCR
- **Metrics to capture (beyond raw TPS):**
  - VQA accuracy
  - caption quality
  - OCR fidelity if advertised
- **Do NOT measure (would produce invalid signal for this capability):**
  - text-only quality alone — misses the modality that justifies the model
- **Workspace slot requirements for valid bench data:**
  - `mmproj`: vision projector REQUIRED


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest evidence:** 2026-06-21 (50d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `devstral:24b` — 13.3 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - nothing distinctive — arch/vendor/capability all remain represented after removal
- **What we'd gain:** 13.3 GB disk

### Intake rationale

- **Intake age:** 46d ago (first-seen commit `84c15f78`)
- **Mentioned in 5 doc file(s):**
  - `docs/RESULTS_COLLAPSE_V1_20260712.md` — ## What moved where
    > workspaces) folded into `auto-security`'s `variants:` block. \ - **Deleted outright** (Phase 7, model-tied, no longer needed once `?model=` \   override + persona `preferred_models` chains exist): `au…
  - `docs/ROUTING_INTEGRITY_FINDINGS.md` — ### Finding 4 — Model-tied lanes: zero Stage-R risk by construction (informational, not a regression)
    > **Verdict: not applicable to Stage R — tracked under Stage P.** \  \ `auto-devstral`, `auto-glm`, `auto-glm-thinking`, `auto-gemma-e4b`, \ `auto-gemma-fast`, `auto-gemma-vision` were confirmed **absen…
  - `docs/RESULTS_ALIAS_RETIRE_V1_20260713.md` — ## 2. What changed — the four canonical addressing forms
    > | Coding variants | `auto-coding` + `?variant=<v>` | `auto-coding?variant=heavy` (was `auto-agentic`) | \ | Security roles | `auto-security` + `?variant=<v>` | `auto-security?variant=redteam` (was `au…

### Capability profile

- **Architecture:** unknown
- **Parameters:** 24B
- **Source:** ollama-library (`ollama-library`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'devstral:24b'

### Fleet position

- **Bench workspaces routing here:** `bench-devstral`
- **Same-arch (`unknown`) production workspaces:** 0
- **Same-arch bench workspaces:** 0
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `unknown` workspaces in fleet:** 0
- **Other workspaces from `ollama-library`:** 40

### Card claims vs our slotting

- **Card source:** `https://ollama.com/library/devstral` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!doctype html> <html class="h-full overflow-y-scroll"> <head> <title>devstral</title>
- **Deployment signals extracted:** vision / multimodal capability advertised
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-devstral` | tools: none
    > Benchmark: devstral:24b (Ollama, Mistral, Apache 2.0, 24B MoE 22B active, ~14GB). State-of-the-art open-source agent model for software engineering tasks. 46.8% SWE-bench Verified, #1 open-source at release (May 2025). Designed for agentic coding: multi-step tool use, file editing, repo navigation. Head-to-head vs bench-devstral-small-2 (7B MoE). Candidate for auto-agentic primary if TPS competiti…
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - card advertises vision/multimodal but no slot text mentions vision, mmproj, or image tasks — advertised capability likely untested

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `vision` — Vision / multimodal (non-CUA)
- **Recommended harness:** vision probe (image → text tasks)
- **Prompt corpus:** image + question pairs across VQA, captioning, OCR
- **Metrics to capture (beyond raw TPS):**
  - VQA accuracy
  - caption quality
  - OCR fidelity if advertised
- **Do NOT measure (would produce invalid signal for this capability):**
  - text-only quality alone — misses the modality that justifies the model
- **Workspace slot requirements for valid bench data:**
  - `mmproj`: vision projector REQUIRED
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - `bench-devstral`: needs vision projector (`mmproj`) — the bench cannot produce valid multimodal data without it
  - card advertises vision/multimodal but no slot text mentions vision, mmproj, or image tasks — advertised capability likely untested


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest evidence:** 2026-06-11 (60d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL-ctx64k` — 13.3 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - capability: MoE architecture (routes tokens to expert subsets)
  - capability: Unsloth Dynamic quantization
- **What we'd gain:** 13.3 GB disk

### Intake rationale

- **Intake age:** 39d ago (first-seen commit `5dd51bb6`)
- **Mentioned in 5 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — # Persona roster (138 personas)
    > | `gemmaresearchanalyst` | research | `auto-research` | — | \ | `githubexpert` | coding | `auto-coding` | — | \ | `glm-coder` | coding | `auto-coding` | `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:…
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## coding (41)
    > - `hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M` \ - `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL` \ - `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL-ctx64k` \ - `hf.co/unsloth/Qwen…
  - `portal_wiki/canonical/unit-model-catalog-hf-co-unsloth-glm-4-7-flash-reap-23b-a3b-gguf-ud-q4-k-xl-ctx64k.md` — (no nearby heading)
    > id: unit-model-catalog-hf-co-unsloth-glm-4-7-flash-reap-23b-a3b-gguf-ud-q4-k-xl-ctx64k \ kind: what \ title: "MODEL_CATALOG \u2014 `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL-ctx64k`" \ …

### Capability profile

- **Architecture:** GLM
- **Parameters:** 23B
- **Quantization:** Unsloth Dynamic Q4 XL
- **Source:** huggingface (`unsloth`)
- **Distinguishing features (from tag pattern):**
  - MoE architecture (routes tokens to expert subsets)
  - Unsloth Dynamic quantization
- **Reversibility:** ollama pull 'hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL-ctx64k'

### Fleet position

- **Bench workspaces routing here:** none (bench-orphaned)
- **Same-arch (`GLM`) production workspaces:** 0
- **Same-arch bench workspaces:** 3
  - `glm-4.7-flash:Q4_K_M` (via `bench-glm`)
  - `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL` (via `bench-glm-reap`)
  - `hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf` (via `bench-glm-z1-rumination`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `GLM` workspaces in fleet:** 3
- **Other workspaces from `unsloth`:** 4

### Card claims vs our slotting

- **Card source:** `https://huggingface.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF/raw/main/README.md` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > > [!NOTE] >  Includes Unsloth **chat template fixes**! <br> For `llama.cpp`, use `--jinja` >
- **Deployment signals extracted:** specific chat template requirement, reasoning-trace capability, MoE architecture confirmed
- **Slotting:** bench-orphaned — nothing routes to this tag
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `reasoning-explicit` — Explicit reasoning / thinking traces
- **Recommended harness:** reasoning-aware persona matrix — capture and score the thinking traces, not just final answers
- **Prompt corpus:** multi-step reasoning tasks: math, logic, planning, code with edge cases
- **Metrics to capture (beyond raw TPS):**
  - task success rate WITH reasoning captured
  - reasoning coherence score
  - TPS separated by reasoning-on vs reasoning-off runs
  - trace length vs task complexity
- **Do NOT measure (would produce invalid signal for this capability):**
  - single-turn factual recall (doesn't exercise reasoning)
- **Workspace slot requirements for valid bench data:**
  - `emits_reasoning`: true — otherwise the harness sees a truncated model
  - `predict_limit`: high enough to fit thinking traces (8k+ typical)
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-GLM-4.7-Flash-REAP-2`)
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest post-boundary evidence:** 2026-08-11
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `gpt-oss:20b` — 12.8 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - **GPT-OSS disappears from the fleet entirely** — no other workspace uses this arch family
  - NET-NEW arch family: `GPT-OSS` (not in fleet elsewhere)
  - only exploration of `GPT-OSS` arch — no other workspace tests it
- **What we'd gain:** 12.8 GB disk

### Intake rationale

- **Intake age:** 46d ago (first-seen commit `84c15f78`)
- **Mentioned in 5 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## coding (41)
    > - `devstral:24b` \ - `glm-4.7-flash:Q4_K_M` \ - `gpt-oss:20b` \ - `hf.co/Abiray/Agents-A1-Q4_K_M-GGUF:Q4_K_M` \ - `hf.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated-gguf-4bit:Q4_K_M` \ - `hf.co/…
  - `docs/generated/ARCHITECTURE_MAP.md` — ## Knowledge Layer
    > | `unit-model-catalog-gemma4-e4b-it-qat-ctx8k` | what | 2 | \ | `unit-model-catalog-glm-4-7-flash-q4-k-m` | what | 2 | \ | `unit-model-catalog-gpt-oss-20b` | what | 2 | \ | `unit-model-catalog-granite…
  - `docs/reselection/AUTOSEC_RESELECT_EVIDENCE_20260716T192100Z.md` — ## Method
    > ## Method \  \ Phase 3.0 canary (`gpt-oss:20b`, `granite4.1:8b`) confirmed the harness/tool-schema/parser plumbing is \ sound before trusting the reliability instrument's verdicts (see prior-turn reco…

### Capability profile

- **Architecture:** GPT-OSS
- **Parameters:** 20B
- **Source:** ollama-library (`ollama-library`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'gpt-oss:20b'

### Fleet position

- **Bench workspaces routing here:** `bench-gptoss`
- **Same-arch (`GPT-OSS`) production workspaces:** 0
- **Same-arch bench workspaces:** 0
- **Net-new signals (fleet has no other with these):**
  - arch family: `GPT-OSS` (not in fleet elsewhere)
- ⚠ **Removal ends all fleet exploration of `GPT-OSS`**

### Diversity impact

- ⚠ **ARCH LOSS**: `GPT-OSS` disappears from fleet entirely if removed
- **Other workspaces from `ollama-library`:** 40

### Card claims vs our slotting

- **Card source:** `https://ollama.com/library/gpt-oss` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!doctype html> <html class="h-full overflow-y-scroll"> <head> <title>gpt-oss</title>
- **Deployment signals extracted:** reasoning-trace capability, MoE architecture confirmed
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-gptoss` | tools: 7 configured | emits_reasoning
    > Benchmark: gpt-oss:20b (Ollama, OpenAI open-weight MoE, ~12GB, o3-mini level, configurable thinking depth). PROMOTED 2026-06-20 to auto-agentic fallback + coding pool. 2/2 security chain at 45s. Coding arena: full tool suite.
- **Card vs slotting alignment ✓:**
  - card advertises reasoning; slot has `emits_reasoning: true`

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `reasoning-explicit` — Explicit reasoning / thinking traces
- **Recommended harness:** reasoning-aware persona matrix — capture and score the thinking traces, not just final answers
- **Prompt corpus:** multi-step reasoning tasks: math, logic, planning, code with edge cases
- **Metrics to capture (beyond raw TPS):**
  - task success rate WITH reasoning captured
  - reasoning coherence score
  - TPS separated by reasoning-on vs reasoning-off runs
  - trace length vs task complexity
- **Do NOT measure (would produce invalid signal for this capability):**
  - single-turn factual recall (doesn't exercise reasoning)
- **Workspace slot requirements for valid bench data:**
  - `emits_reasoning`: true — otherwise the harness sees a truncated model
  - `predict_limit`: high enough to fit thinking traces (8k+ typical)
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - `bench-gptoss`: `predict_limit` needs to accommodate high enough to fit thinking traces (8k+ typical)


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest evidence:** 2026-06-28 (43d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `huihui_ai/qwen3-abliterated:14b-v2` — 8.4 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - capability: Abliterated (safety-vector ablation)
- **What we'd gain:** 8.4 GB disk

### Intake rationale

- **Intake age:** 31d ago (first-seen commit `b43d0819`)
- **Mentioned in 4 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## coding (41)
    > - `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL` \ - `hf.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF:Q4_K_M` \ - `huihui_ai/qwen3-abliterated:14b-v2` \ - `laguna-xs.2:Q4_K_M`…
  - `docs/generated/ARCHITECTURE_MAP.md` — ## Knowledge Layer
    > | `unit-model-catalog-huihui-ai-qwen3-6-abliterated-27b` | what | 2 | \ | `unit-model-catalog-huihui-ai-qwen3-6-abliterated-27b-ctx8k` | what | 2 | \ | `unit-model-catalog-huihui-ai-qwen3-abliterated-…
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## coding (41)
    > - `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL` \ - `hf.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF:Q4_K_M` \ - `huihui_ai/qwen3-abliterated:14b-v2` \ - `laguna-xs.2:Q4_K_M`…

### Capability profile

- **Architecture:** Qwen3
- **Parameters:** 14B
- **Source:** ollama-library-namespaced (`huihui_ai`)
- **Distinguishing features (from tag pattern):**
  - Abliterated (safety-vector ablation)
- **Reversibility:** ollama pull 'huihui_ai/qwen3-abliterated:14b-v2'

### Fleet position

- **Bench workspaces routing here:** `bench-qwen3-14b-abliterated`
- **Same-arch (`Qwen3`) production workspaces:** 3
  - `huihui_ai/qwen3.5-abliterated:9b-ctx8k` (via `auto`)
  - `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k` (via `auto-reasoning`)
  - `qwen3-vl:32b-ctx8k` (via `auto-vision`)
- **Same-arch bench workspaces:** 4
  - `huihui_ai/qwen3.5-abliterated:9b` (via `bench-qwen35-abliterated`)
  - `hf.co/mradermacher/Qwen3.5-9B-Claude-4.6-HighIQ-THINKING-HERETIC-UNCENSORED-GGUF:Q4_K_M` (via `bench-qwen35-9b-heretic-vision`)
  - `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-9B-MTP-GGUF:Q4_K_M` (via `bench-jackrong-dsv4-9b`)
  - `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-4B-MTP-GGUF:Q4_K_M` (via `bench-jackrong-dsv4-4b`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `Qwen3` workspaces in fleet:** 7
- **Other workspaces from `huihui_ai`:** 9

### Card claims vs our slotting

- **Card source:** `https://ollama.com/huihui_ai/qwen3-abliterated` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!doctype html> <html class="h-full overflow-y-scroll"> <head> <title>huihui_ai/qwen3-abliterated</title>
- **Deployment signals extracted:** abliterated / uncensored, MoE architecture confirmed
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-qwen3-14b-abliterated` | tools: 4 configured | emits_reasoning
    > huihui-ai Qwen3-14B-abliterated v2 (Qwen3-14B base, huihui-ai native Ollama tag, uncensored). Fills the 9B (qwen35-9b-heretic-vision) to 27B/35B (Ornith/AgentWorld/qwen36) tier gap — no 14B model exists in Portal's fleet today. Same trusted lineage as E2b-qat (huihui_ai native tag). v2 is the current author-supported version — v1 explicitly retired by huihui-ai for garbled-output bugs; do not fall…
- **Alignment:** no distinctive claim/slot mismatch detected — slot config appears consistent with card

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `abliterated` — Abliterated / uncensored
- **Recommended harness:** refusal-rate probe + capability-preservation vs base
- **Prompt corpus:** safety-elicitation set + standard capability set matched to base
- **Metrics to capture (beyond raw TPS):**
  - refusal rate on safety prompts (should be low — the point of the model)
  - capability preservation vs base (chat quality, task success) — did ablation break the model?


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest post-boundary evidence:** 2026-08-11
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0` — 8.0 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - **last model from `fdtn-ai`** — vendor exits the fleet
  - NET-NEW vendor: `fdtn-ai` (not in fleet elsewhere)
- **What we'd gain:** 8.0 GB disk

### Intake rationale

- **Intake age:** 46d ago (first-seen commit `84c15f78`)
- **Mentioned in 5 doc file(s):**
  - `docs/SECURITY_BENCH_EXEC.md` — ## Security models loaded
    > hf.co/Mia-AiLab/Qwable-3.6-35b:Qwable-3.6-35b_q4_k_m.gguf \ huihui_ai/baronllm-abliterated:latest \ hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0 \ ``` \  \ ## Why
  - `docs/ADMIN_GUIDE.md` — ## reasoning (27)
    > - `hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf` \ - `hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_…
  - `docs/_archive_execdocs/PORTAL5_ACCEPTANCE_EXECUTE_V8.md` — ### Workspaces (S3 / S3a)
    > | Workspace | Primary (model_hint) | \ |---|---| \ | auto-blueteam | `hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0` | \ | auto-compliance | `granite4.1:8b` | \ | tools-specialist | `granit…

### Capability profile

- **Architecture:** unknown
- **Parameters:** 8B
- **Quantization:** Q8_0
- **Source:** huggingface (`fdtn-ai`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0'

### Fleet position

- **Bench workspaces routing here:** `bench-foundation-sec-8b-reasoning`
- **Same-arch (`unknown`) production workspaces:** 0
- **Same-arch bench workspaces:** 0
- **Net-new signals (fleet has no other with these):**
  - vendor: `fdtn-ai` (not in fleet elsewhere)

### Diversity impact

- **Other `unknown` workspaces in fleet:** 0
- ⚠ **VENDOR LOSS**: `fdtn-ai` exits the fleet

### Card claims vs our slotting

- **Card source:** `https://huggingface.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF/raw/main/README.md` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > **This model was quantized from fdtn-ai/Foundation-Sec-8B-Reasoning to a 8-bit (Q8_0) GGUF checkpoint using llama.cpp. It retains the cybersecurity specialization of the original 8-billion-parameter model while reducing the memory footprint from approximately 16GB (BF16) to around 8.54GB (Q8_0) for inference.**
- **Deployment signals extracted:** reasoning-trace capability
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-foundation-sec-8b-reasoning` | tools: none | emits_reasoning
    > Benchmark: hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0 (Ollama, Cisco Foundation AI, 8B cybersecurity reasoning model, native Ollama "thinking" capability). GATE-D ablation's locked V2 trio Expert model — added so resolve_pipeline_model() has a real workspace to route to instead of silently falling back to the general group's first model (found 2026-07-20/21: every Expert-role call in…
- **Card vs slotting alignment ✓:**
  - card advertises reasoning; slot has `emits_reasoning: true`

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `reasoning-explicit` — Explicit reasoning / thinking traces
- **Recommended harness:** reasoning-aware persona matrix — capture and score the thinking traces, not just final answers
- **Prompt corpus:** multi-step reasoning tasks: math, logic, planning, code with edge cases
- **Metrics to capture (beyond raw TPS):**
  - task success rate WITH reasoning captured
  - reasoning coherence score
  - TPS separated by reasoning-on vs reasoning-off runs
  - trace length vs task complexity
- **Do NOT measure (would produce invalid signal for this capability):**
  - single-turn factual recall (doesn't exercise reasoning)
- **Workspace slot requirements for valid bench data:**
  - `emits_reasoning`: true — otherwise the harness sees a truncated model
  - `predict_limit`: high enough to fit thinking traces (8k+ typical)
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - `bench-foundation-sec-8b-reasoning`: `predict_limit` needs to accommodate high enough to fit thinking traces (8k+ typical)


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest evidence:** 2026-06-28 (43d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-9B-MTP-GGUF:Q4_K_M` — 7.1 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - capability: MTP speculative drafting (draft model bound to base)
- **What we'd gain:** 7.1 GB disk

### Intake rationale

- **Intake age:** 0d ago (first-seen commit `fb9979b7`)
- **Mentioned in 3 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `hf.co/BugTraceAI/BugTraceAI-CORE-Ultra-27B-Q6:Q6_K` \ - `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-4B-MTP-GGUF:Q4_K_M` \ - `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-9B-MTP-GGUF:Q4_K_M` \ - `hf.co/Jackro…
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## general (84)
    > - `hf.co/BugTraceAI/BugTraceAI-CORE-Ultra-27B-Q6:Q6_K` \ - `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-4B-MTP-GGUF:Q4_K_M` \ - `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-9B-MTP-GGUF:Q4_K_M` \ - `hf.co/Jackro…
  - `portal_wiki/canonical/unit-model-catalog-jackrong-deepseek-v4-pro-qwen3-5-9b-mtp.md` — (no nearby heading)
    > id: unit-model-catalog-jackrong-deepseek-v4-pro-qwen3-5-9b-mtp \ kind: what \ title: "MODEL_CATALOG \u2014 `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-9B-MTP-GGUF:Q4_K_M`" \ sources: \ - type: code \   pa…

### Capability profile

- **Architecture:** Qwen3
- **Parameters:** 9B
- **Quantization:** Q4_K_M (mixed)
- **Source:** huggingface (`Jackrong`)
- **Distinguishing features (from tag pattern):**
  - MTP speculative drafting (draft model bound to base)
- **Reversibility:** ollama pull 'hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-9B-MTP-GGUF:Q4_K_M'

### Fleet position

- **Bench workspaces routing here:** `bench-jackrong-dsv4-9b`
- **Same-arch (`Qwen3`) production workspaces:** 3
  - `huihui_ai/qwen3.5-abliterated:9b-ctx8k` (via `auto`)
  - `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k` (via `auto-reasoning`)
  - `qwen3-vl:32b-ctx8k` (via `auto-vision`)
- **Same-arch bench workspaces:** 4
  - `huihui_ai/qwen3.5-abliterated:9b` (via `bench-qwen35-abliterated`)
  - `hf.co/mradermacher/Qwen3.5-9B-Claude-4.6-HighIQ-THINKING-HERETIC-UNCENSORED-GGUF:Q4_K_M` (via `bench-qwen35-9b-heretic-vision`)
  - `huihui_ai/qwen3-abliterated:14b-v2` (via `bench-qwen3-14b-abliterated`)
  - `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-4B-MTP-GGUF:Q4_K_M` (via `bench-jackrong-dsv4-4b`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `Qwen3` workspaces in fleet:** 7
- **Other workspaces from `Jackrong`:** 2

### Card claims vs our slotting

- **Card source:** `https://huggingface.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-9B-MTP-GGUF/raw/main/README.md` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; border: 1px solid #cbd5e1; border-radius: 16px; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.05), 0 4px 6px -2px rgba(0,0,0,0.05); overflow: hidden; background: #ffffff; margin-bottom: 30px;"> <div style="background: linear-gradient(135deg, #7c3aed 0%, #4c1d95 100%); padding: 24px; color: white;"> <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px;"> <h1 style="margin: 0; font-size: 26px; font-weight: 800; color: white; border: none;">🧠 DeepSeek-V4-Pr
- **Deployment signals extracted:** vision / multimodal capability advertised, reasoning-trace capability, speculative / MTP drafting
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-jackrong-dsv4-9b` | tools: none | emits_reasoning
    > Benchmark: hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-9B-MTP-GGUF:Q4_K_M (~5.8GB, arch qwen35). DeepSeek-V4-Pro→Qwen3.5-9B reasoning distill with embedded MTP draft heads; card claims 97.2% format-compliance.
BENCH RESULT 2026-08-10: TPS 35.6 t/s avg (5/5, clears 20 t/s floor; Q-score 0.67, not perfect — some run-quality variance). Capability C4 vs auto-compliance baseline: format 1.00/1.00 tied (cons…
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - card advertises vision/multimodal but no slot text mentions vision, mmproj, or image tasks — advertised capability likely untested
- **Card vs slotting alignment ✓:**
  - card advertises reasoning; slot has `emits_reasoning: true`

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `vision` — Vision / multimodal (non-CUA)
- **Recommended harness:** vision probe (image → text tasks)
- **Prompt corpus:** image + question pairs across VQA, captioning, OCR
- **Metrics to capture (beyond raw TPS):**
  - VQA accuracy
  - caption quality
  - OCR fidelity if advertised
- **Do NOT measure (would produce invalid signal for this capability):**
  - text-only quality alone — misses the modality that justifies the model
- **Workspace slot requirements for valid bench data:**
  - `mmproj`: vision projector REQUIRED
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - `bench-jackrong-dsv4-9b`: needs vision projector (`mmproj`) — the bench cannot produce valid multimodal data without it
  - card advertises vision/multimodal but no slot text mentions vision, mmproj, or image tasks — advertised capability likely untested


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest post-boundary evidence:** 2026-08-11
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `portal5/gemma4-12b:q4_K_M-ctx8k` — 7.0 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - nothing distinctive — arch/vendor/capability all remain represented after removal
- **What we'd gain:** 7.0 GB disk

### Intake rationale

- **Intake age:** 0d ago (first-seen commit `d6603676`)
- **Mentioned in 5 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `portal5/deepwen-3.6:q4.5-moq` \ - `portal5/deepwen-3.6:q4.5-moq-ctx32k` \ - `portal5/gemma4-12b:q4_K_M-ctx8k` \ - `portal5/qwen3.6-27b-mtp:q8_0-drafted` \ - `portal5/xyz-aquila-mini:q4_k_m` \ - `qw…
  - `docs/generated/ARCHITECTURE_MAP.md` — ## Knowledge Layer
    > | `unit-model-catalog-fredrezones55-qwen3-6-35b-a3b-uncensored-hauhaucs-aggressive-q4-ctx8k` | what | 2 | \ | `unit-model-catalog-gemma-4-e4b-it-4bit` | what | 1 | \ | `unit-model-catalog-gemma4-12b-i…
  - `docs/reports/V9_CANDIDATE_BENCH_REVIEW.md` — ### Comparable fleet models (for context)
    > | Model | Avg TPS (V8) | SWE-bench | Size | \ |---|---|---|---| \ | portal5/gemma4-12b:q4_K_M-ctx8k | — | — | ~7.6GB | \ | qwen3.6:27b-q4_K_M | — | 77.2% | ~16GB | \ | laguna-xs.2:Q4_K_M | — | 68.2% |…

### Capability profile

- **Architecture:** Gemma4
- **Parameters:** 12B
- **Quantization:** Q4_K_M (mixed)
- **Source:** portal5-local-build (`portal5`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** NOT registry-pullable — local build; reconstruct via original derivation task

### Fleet position

- **Bench workspaces routing here:** none (bench-orphaned)
- **Same-arch (`Gemma4`) production workspaces:** 2
  - `gemma4:26b-a4b-it-qat-ctx8k` (via `auto-daily`)
  - `gemma4:12b-it-qat-ctx8k` (via `auto-audio`)
- **Same-arch bench workspaces:** 12
  - `gemma4:26b-a4b-it-q4_K_M` (via `bench-gemma4-26b-optiq`)
  - `gemma4:12b-it-qat` (via `bench-gemma4-12b`)
  - `gemma4:e4b-it-q4_K_M` (via `bench-gemma4-e4b`)
  - `gemma4:e2b-it-qat` (via `bench-gemma4-e2b`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `Gemma4` workspaces in fleet:** 14
- **Other workspaces from `portal5`:** 4

### Card claims vs our slotting

- **Card status:** local portal5/* build — no external card

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `general` — General / no specific capability advertised
- **Recommended harness:** bench_tps + portal5_persona_matrix (standard fleet path)
- **Prompt corpus:** default persona matrix across the model's target lane
- **Metrics to capture (beyond raw TPS):**
  - avg_tps vs the 20 t/s floor
  - quality_score vs same-lane incumbent


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 2 invalid (pre-boundary)
- **Avg TPS (pre-boundary — INVALID for decisions):** 11.35 — captured under prior stack
- **Newest evidence:** 2026-06-28 (43d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `hf.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF:Q4_K_M` — 6.9 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - **last model from `yuxinlu1`** — vendor exits the fleet
  - NET-NEW vendor: `yuxinlu1` (not in fleet elsewhere)
- **What we'd gain:** 6.9 GB disk

### Intake rationale

- **Intake age:** 41d ago (first-seen commit `ddcf7dff`)
- **Mentioned in 3 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## coding (41)
    > - `hf.co/unsloth/Qwen-AgentWorld-35B-A3B-GGUF:UD-Q4_K_XL-ctx64k` \ - `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL` \ - `hf.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF:Q4_K_M…
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## coding (41)
    > - `hf.co/unsloth/Qwen-AgentWorld-35B-A3B-GGUF:UD-Q4_K_XL-ctx64k` \ - `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL` \ - `hf.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF:Q4_K_M…
  - `portal_wiki/canonical/unit-model-catalog-hf-co-yuxinlu1-gemma-4-12b-agentic-fable5-composer2-5-v2-3-5x-tau2-gguf-q4-k-m.md` — (no nearby heading)
    > id: unit-model-catalog-hf-co-yuxinlu1-gemma-4-12b-agentic-fable5-composer2-5-v2-3-5x-tau2-gguf-q4-k-m \ kind: what \ title: "MODEL_CATALOG \u2014 `hf.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5…

### Capability profile

- **Architecture:** Gemma4
- **Parameters:** 12B
- **Quantization:** Q4_K_M (mixed)
- **Source:** huggingface (`yuxinlu1`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'hf.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF:Q4_K_M'

### Fleet position

- **Bench workspaces routing here:** `bench-gemma4-12b-agentic`
- **Same-arch (`Gemma4`) production workspaces:** 2
  - `gemma4:26b-a4b-it-qat-ctx8k` (via `auto-daily`)
  - `gemma4:12b-it-qat-ctx8k` (via `auto-audio`)
- **Same-arch bench workspaces:** 11
  - `gemma4:26b-a4b-it-q4_K_M` (via `bench-gemma4-26b-optiq`)
  - `gemma4:12b-it-qat` (via `bench-gemma4-12b`)
  - `gemma4:e4b-it-q4_K_M` (via `bench-gemma4-e4b`)
  - `gemma4:e2b-it-qat` (via `bench-gemma4-e2b`)
- **Net-new signals (fleet has no other with these):**
  - vendor: `yuxinlu1` (not in fleet elsewhere)

### Diversity impact

- **Other `Gemma4` workspaces in fleet:** 13
- ⚠ **VENDOR LOSS**: `yuxinlu1` exits the fleet

### Card claims vs our slotting

- **Card source:** `https://huggingface.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF/raw/main/README.md` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > > **No matter your GPU. No matter your RAM.** With **~4.5 GB** of VRAM *or* unified memory free, you can run your own > private, offline coding **agent** right now. 🚀 v2 is the big **agentic** upgrade — it reads, reasons, *uses tools*, > and works through multi-step technical tasks before it acts. 🧠🛠️ All local, all yours, no API, no cloud.
- **Deployment signals extracted:** specific chat template requirement, reasoning-trace capability, speculative / MTP drafting
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-gemma4-12b-agentic` | tools: 6 configured | emits_reasoning
    > Gemma-4-12B agentic/fable5/composer2.5 (~6.87GB Q4_K_M, yuxinlu1, Apache 2.0, Gemma-4-12B-it finetune, agentic/coding/terminal, native Gemma-4 tool protocol via <|tool_call|> tokens, thinking mode). Reports HONESTLY: tau2-bench telecom 55% vs base 15% under a stated LOCAL self-eval harness (explicitly not leaderboard-comparable) + 0% fabrication probe. Small enough to fit with room to spare — a fa…
- **Card vs slotting alignment ✓:**
  - card advertises reasoning; slot has `emits_reasoning: true`

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `mtp-speculative` — MTP / speculative drafting
- **Recommended harness:** MTP-aware bench — draft acceptance rate + wall-time speedup vs base
- **Prompt corpus:** IDENTICAL to base model's bench for direct comparison
- **Metrics to capture (beyond raw TPS):**
  - draft token acceptance rate (headline signal)
  - wall-time speedup vs base model on identical prompts
  - quality parity vs base (any regression kills the value proposition)
- **Do NOT measure (would produce invalid signal for this capability):**
  - raw TPS without comparing to base — meaningless in isolation
- **Workspace slot requirements for valid bench data:**
  - `paired_draft`: draft model config must be present, correct, and pinned to matching base
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - `bench-gemma4-12b-agentic`: MTP benching requires paired draft model config — check `predict_limit` and draft binding


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest post-boundary evidence:** 2026-08-11
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `hf.co/mradermacher/Qwen3.5-9B-Claude-4.6-HighIQ-THINKING-HERETIC-UNCENSORED-GGUF:Q4_K_M` — 5.8 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - NET-NEW capability: Explicit thinking / reasoning traces
  - NET-NEW capability: Heretic-modified (jailbreak retraining)
- **What we'd gain:** 5.8 GB disk

### Intake rationale

- **Intake age:** 41d ago (first-seen commit `26dc5832`)
- **Mentioned in 3 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M` \ - `hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-GGUF:Q4_K_M` \ - `hf.co/mradermacher/Qwen3.5-9B-Claude-4.6-HighIQ-THINKING-HERETIC…
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## general (84)
    > - `hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M` \ - `hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-GGUF:Q4_K_M` \ - `hf.co/mradermacher/Qwen3.5-9B-Claude-4.6-HighIQ-THINKING-HERETIC…
  - `portal_wiki/canonical/unit-model-catalog-hf-co-mradermacher-qwen3-5-9b-claude-4-6-highiq-thinking-heretic-uncensored-gguf-q4-k-m.md` — (no nearby heading)
    > id: unit-model-catalog-hf-co-mradermacher-qwen3-5-9b-claude-4-6-highiq-thinking-heretic-uncensored-gguf-q4-k-m \ kind: what \ title: "MODEL_CATALOG \u2014 `hf.co/mradermacher/Qwen3.5-9B-Claude-4.6-Hig…

### Capability profile

- **Architecture:** Qwen3
- **Parameters:** 9B
- **Quantization:** Q4_K_M (mixed)
- **Source:** huggingface (`mradermacher`)
- **Distinguishing features (from tag pattern):**
  - Heretic-modified (jailbreak retraining)
  - Explicit thinking / reasoning traces
- **Reversibility:** ollama pull 'hf.co/mradermacher/Qwen3.5-9B-Claude-4.6-HighIQ-THINKING-HERETIC-UNCENSORED-GGUF:Q4_K_M'

### Fleet position

- **Bench workspaces routing here:** `bench-qwen35-9b-heretic-vision`
- **Same-arch (`Qwen3`) production workspaces:** 3
  - `huihui_ai/qwen3.5-abliterated:9b-ctx8k` (via `auto`)
  - `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k` (via `auto-reasoning`)
  - `qwen3-vl:32b-ctx8k` (via `auto-vision`)
- **Same-arch bench workspaces:** 4
  - `huihui_ai/qwen3.5-abliterated:9b` (via `bench-qwen35-abliterated`)
  - `huihui_ai/qwen3-abliterated:14b-v2` (via `bench-qwen3-14b-abliterated`)
  - `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-9B-MTP-GGUF:Q4_K_M` (via `bench-jackrong-dsv4-9b`)
  - `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-4B-MTP-GGUF:Q4_K_M` (via `bench-jackrong-dsv4-4b`)
- **Net-new signals (fleet has no other with these):**
  - capability: Explicit thinking / reasoning traces
  - capability: Heretic-modified (jailbreak retraining)

### Diversity impact

- **Other `Qwen3` workspaces in fleet:** 7
- **Other workspaces from `mradermacher`:** 6

### Card claims vs our slotting

- **Card source:** `https://huggingface.co/mradermacher/Qwen3.5-9B-Claude-4.6-HighIQ-THINKING-HERETIC-UNCENSORED-GGUF/raw/main/README.md` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!-- ### quantize_version: 2 --> <!-- ### output_tensor_quantised: 1 --> <!-- ### convert_type: hf --> <!-- ### vocab_type:  --> <!-- ### tags:  --> <!-- ### quants:  x-f16 Q4_K_S Q2_K Q8_0 Q6_K Q3_K_M Q3_K_S Q3_K_L Q4_K_M Q5_K_S Q5_K_M IQ4_XS --> <!-- ### quants_skip:  --> <!-- ### skip_mmproj:  --> static quants of https://huggingface.co/DavidAU/Qwen3.5-9B-Claude-4.6-HighIQ-THINKING-HERETIC-UNCENSORED
- **Deployment signals extracted:** vision / multimodal capability advertised, abliterated / uncensored
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-qwen35-9b-heretic-vision` | tools: none | emits_reasoning
    > Qwen3.5-9B Claude-4.6 HighIQ THINKING HERETIC UNCENSORED (~5.6GB Q4_K_M, DavidAU, Apache 2.0, dense, vision image-text-to-text, 262K→1M ctx via YaRN, thinking model). trohrbaugh heretic-v2 abliteration (KLD 0.079, 6/100 refusals). First uncensored vision entry in the fleet — Portal's vision lane has no uncensored option. Claude-4.6 distill claim is unverifiable-provenance marketing (same class as …
- **Alignment:** no distinctive claim/slot mismatch detected — slot config appears consistent with card

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `vision` — Vision / multimodal (non-CUA)
- **Recommended harness:** vision probe (image → text tasks)
- **Prompt corpus:** image + question pairs across VQA, captioning, OCR
- **Metrics to capture (beyond raw TPS):**
  - VQA accuracy
  - caption quality
  - OCR fidelity if advertised
- **Do NOT measure (would produce invalid signal for this capability):**
  - text-only quality alone — misses the modality that justifies the model
- **Workspace slot requirements for valid bench data:**
  - `mmproj`: vision projector REQUIRED


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest post-boundary evidence:** 2026-08-11
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `gemma4:e4b-it-qat-ctx8k` — 5.7 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - nothing distinctive — arch/vendor/capability all remain represented after removal
- **What we'd gain:** 5.7 GB disk

### Intake rationale

- **Intake age:** 39d ago (first-seen commit `5dd51bb6`)
- **Mentioned in 5 doc file(s):**
  - `docs/HOWTO.md` — ## 3. Workspaces
    > |---|---|---| \ | `auto` (Portal Auto Router) | `huihui_ai/qwen3.5-abliterated:9b-ctx8k` | LLM intent classifier routes onward | \ | `auto-daily` | `gemma4:26b-a4b-it-qat-ctx8k` | web_search, create_w…
  - `docs/MLX_CHANGES_2026-04-26.md` — ## Upgrades Applied
    > |---------|-----|-----|-------| \ | mlx (core) | 0.31.1 | 0.31.2 | Homebrew upgrade; Python bindings required manual copy of `core.cpython-314-darwin.so` and `nn/` modules from Cellar | \ | mlx-lm | 0…
  - `docs/ADMIN_GUIDE.md` — ## vision (16)
    > - `gemma4:e4b-it-q4_K_M` \ - `gemma4:e4b-it-qat` \ - `gemma4:e4b-it-qat-ctx8k` \ - `hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:gemma-4-31b-jang-crack-Q4_K_M.gguf` \ - `hf.co/mradermacher/Qwen3.5-9B-…

### Capability profile

- **Architecture:** Gemma4
- **Parameters:** 4B
- **Source:** ollama-library (`ollama-library`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'gemma4:e4b-it-qat-ctx8k'

### Fleet position

- **Bench workspaces routing here:** none (bench-orphaned)
- **Same-arch (`Gemma4`) production workspaces:** 2
  - `gemma4:26b-a4b-it-qat-ctx8k` (via `auto-daily`)
  - `gemma4:12b-it-qat-ctx8k` (via `auto-audio`)
- **Same-arch bench workspaces:** 12
  - `gemma4:26b-a4b-it-q4_K_M` (via `bench-gemma4-26b-optiq`)
  - `gemma4:12b-it-qat` (via `bench-gemma4-12b`)
  - `gemma4:e4b-it-q4_K_M` (via `bench-gemma4-e4b`)
  - `gemma4:e2b-it-qat` (via `bench-gemma4-e2b`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `Gemma4` workspaces in fleet:** 14
- **Other workspaces from `ollama-library`:** 41

### Card claims vs our slotting

- **Card source:** `https://ollama.com/library/gemma4` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!doctype html> <html class="h-full overflow-y-scroll"> <head> <title>gemma4</title>
- **Deployment signals extracted:** vision / multimodal capability advertised, specific chat template requirement, reasoning-trace capability, MoE architecture confirmed
- **Slotting:** bench-orphaned — nothing routes to this tag
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `vision` — Vision / multimodal (non-CUA)
- **Recommended harness:** vision probe (image → text tasks)
- **Prompt corpus:** image + question pairs across VQA, captioning, OCR
- **Metrics to capture (beyond raw TPS):**
  - VQA accuracy
  - caption quality
  - OCR fidelity if advertised
- **Do NOT measure (would produce invalid signal for this capability):**
  - text-only quality alone — misses the modality that justifies the model
- **Workspace slot requirements for valid bench data:**
  - `mmproj`: vision projector REQUIRED
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-gemma4`)
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest evidence:** 2026-06-21 (50d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `gemma4:e4b-it-qat` — 5.7 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - nothing distinctive — arch/vendor/capability all remain represented after removal
- **What we'd gain:** 5.7 GB disk

### Intake rationale

- **Intake age:** 46d ago (first-seen commit `84c15f78`)
- **Mentioned in 5 doc file(s):**
  - `docs/HOWTO.md` — ## 3. Workspaces
    > |---|---|---| \ | `auto` (Portal Auto Router) | `huihui_ai/qwen3.5-abliterated:9b-ctx8k` | LLM intent classifier routes onward | \ | `auto-daily` | `gemma4:26b-a4b-it-qat-ctx8k` | web_search, create_w…
  - `docs/MLX_CHANGES_2026-04-26.md` — ## Upgrades Applied
    > |---------|-----|-----|-------| \ | mlx (core) | 0.31.1 | 0.31.2 | Homebrew upgrade; Python bindings required manual copy of `core.cpython-314-darwin.so` and `nn/` modules from Cellar | \ | mlx-lm | 0…
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `gemma4:e2b-it-qat` \ - `gemma4:e4b-it-q4_K_M` \ - `gemma4:e4b-it-qat` \ - `glm-4.7-flash:Q4_K_M` \ - `gpt-oss:20b` \ - `granite4.1:30b`

### Capability profile

- **Architecture:** Gemma4
- **Parameters:** 4B
- **Source:** ollama-library (`ollama-library`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'gemma4:e4b-it-qat'

### Fleet position

- **Bench workspaces routing here:** `bench-gemma4-e4b-qat`
- **Same-arch (`Gemma4`) production workspaces:** 2
  - `gemma4:26b-a4b-it-qat-ctx8k` (via `auto-daily`)
  - `gemma4:12b-it-qat-ctx8k` (via `auto-audio`)
- **Same-arch bench workspaces:** 11
  - `gemma4:26b-a4b-it-q4_K_M` (via `bench-gemma4-26b-optiq`)
  - `gemma4:12b-it-qat` (via `bench-gemma4-12b`)
  - `gemma4:e4b-it-q4_K_M` (via `bench-gemma4-e4b`)
  - `gemma4:e2b-it-qat` (via `bench-gemma4-e2b`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `Gemma4` workspaces in fleet:** 13
- **Other workspaces from `ollama-library`:** 40

### Card claims vs our slotting

- **Card source:** `https://ollama.com/library/gemma4` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!doctype html> <html class="h-full overflow-y-scroll"> <head> <title>gemma4</title>
- **Deployment signals extracted:** vision / multimodal capability advertised, specific chat template requirement, reasoning-trace capability, MoE architecture confirmed
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-gemma4-e4b-qat` | tools: none
    > Benchmark: gemma4:e4b-it-qat (Ollama, Google DeepMind, Apache 2.0). Effective 4B QAT — ~5GB, audio+image+video+text, thinking, 128K ctx. QAT quality upgrade vs production gemma4:e4b-it-q4_K_M. PROMOTE_POLICY=confirm.
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - card advertises reasoning traces but no slot has `emits_reasoning: true` — advertised capability untested

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `vision` — Vision / multimodal (non-CUA)
- **Recommended harness:** vision probe (image → text tasks)
- **Prompt corpus:** image + question pairs across VQA, captioning, OCR
- **Metrics to capture (beyond raw TPS):**
  - VQA accuracy
  - caption quality
  - OCR fidelity if advertised
- **Do NOT measure (would produce invalid signal for this capability):**
  - text-only quality alone — misses the modality that justifies the model
- **Workspace slot requirements for valid bench data:**
  - `mmproj`: vision projector REQUIRED
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - card advertises reasoning traces but no slot has `emits_reasoning: true` — advertised capability untested


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest evidence:** 2026-06-21 (50d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `meta-secalign-8b-q4_k_m:latest` — 4.6 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - nothing distinctive — arch/vendor/capability all remain represented after removal
- **What we'd gain:** 4.6 GB disk

### Intake rationale

- **Intake age:** 23d ago (first-seen commit `fd9f4493`)
- **Mentioned in 4 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `llama3.2:3b` \ - `llama3.2:3b-instruct-q8_0-ctx8k` \ - `meta-secalign-8b-q4_k_m:latest` \ - `mistral-small3.2:24b` \ - `muse-glimmer:30b-mlx` \ - `omnicoder2:9b-q4_k_m`
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## general (84)
    > - `llama3.2:3b` \ - `llama3.2:3b-instruct-q8_0-ctx8k` \ - `meta-secalign-8b-q4_k_m:latest` \ - `mistral-small3.2:24b` \ - `muse-glimmer:30b-mlx` \ - `omnicoder2:9b-q4_k_m`
  - `portal_wiki/canonical/unit-model-catalog-meta-secalign-8b-q4-k-m.md` — (no nearby heading)
    > id: unit-model-catalog-meta-secalign-8b-q4-k-m \ kind: what \ title: "MODEL_CATALOG \u2014 `meta-secalign-8b-q4_k_m`" \ sources: \ - type: code \   path: config/backends.yaml

### Capability profile

- **Architecture:** unknown
- **Parameters:** 8B
- **Quantization:** Q4_K_M (mixed)
- **Source:** ollama-library (`ollama-library`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'meta-secalign-8b-q4_k_m:latest'

### Fleet position

- **Bench workspaces routing here:** `bench-meta-secalign-8b`
- **Same-arch (`unknown`) production workspaces:** 0
- **Same-arch bench workspaces:** 0
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `unknown` workspaces in fleet:** 0
- **Other workspaces from `ollama-library`:** 40

### Card claims vs our slotting

- **Card status:** card fetch returned 404 — repo may have been renamed or removed
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-meta-secalign-8b` (🧪 Bench · Meta-SecAlign 8B (Blue Defender))
    > Meta-SecAlign-8B — prompt-injection-resistant blue-defender candidate (arxiv 2507.02735). Llama-3.1-8B lineage (same base as production BaronLLM auto-security primary — template compatibility more predictable than a random cybersec finetune). Meta/Facebook-published, specifically trained for prompt-injection resistance in agentic pentesting workflows. Self-quantized locally (operator-directed over…

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `general` — General / no specific capability advertised
- **Recommended harness:** bench_tps + portal5_persona_matrix (standard fleet path)
- **Prompt corpus:** default persona matrix across the model's target lane
- **Metrics to capture (beyond raw TPS):**
  - avg_tps vs the 20 t/s floor
  - quality_score vs same-lane incumbent


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest post-boundary evidence:** 2026-08-11
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `dolphin-llama3:8b` — 4.3 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - **Llama3 disappears from the fleet entirely** — no other workspace uses this arch family
  - NET-NEW arch family: `Llama3` (not in fleet elsewhere)
  - only exploration of `Llama3` arch — no other workspace tests it
- **What we'd gain:** 4.3 GB disk

### Intake rationale

- **Intake age:** 0d ago (first-seen commit `d6603676`)
- **Mentioned in 5 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## creative (11)
    > - `Qwen3.6-35B-A3B-HauhauCS-Aggressive-4bit` \ - `dolphin-llama3:8b` \ - `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4` \ - `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggres…
  - `docs/generated/ARCHITECTURE_MAP.md` — ## Knowledge Layer
    > | `unit-model-catalog-devstral-small-2-latest` | what | 2 | \ | `unit-model-catalog-devstral-small-2-latest-ctx8k` | what | 2 | \ | `unit-model-catalog-dolphin-llama3-8b` | what | 1 | \ | `unit-model-…
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## creative (11)
    > - `Qwen3.6-35B-A3B-HauhauCS-Aggressive-4bit` \ - `dolphin-llama3:8b` \ - `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4` \ - `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggres…

### Capability profile

- **Architecture:** Llama3
- **Parameters:** 8B
- **Source:** ollama-library (`ollama-library`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'dolphin-llama3:8b'

### Fleet position

- **Bench workspaces routing here:** none (bench-orphaned)
- **Same-arch (`Llama3`) production workspaces:** 0
- **Same-arch bench workspaces:** 0
- **Net-new signals (fleet has no other with these):**
  - arch family: `Llama3` (not in fleet elsewhere)
- ⚠ **Removal ends all fleet exploration of `Llama3`**

### Diversity impact

- ⚠ **ARCH LOSS**: `Llama3` disappears from fleet entirely if removed
- **Other workspaces from `ollama-library`:** 41

### Card claims vs our slotting

- **Card source:** `https://ollama.com/library/dolphin-llama3` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!doctype html> <html class="h-full overflow-y-scroll"> <head> <title>dolphin-llama3</title>
- **Deployment signals extracted:** advertises tool-use / function-calling, abliterated / uncensored
- **Slotting:** bench-orphaned — nothing routes to this tag
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `agent-toolcall` — Agent / tool-use tuned
- **Recommended harness:** tool-use probe — schema conformance + multi-turn tool chain success
- **Prompt corpus:** tool definitions + tasks requiring their invocation across turns
- **Metrics to capture (beyond raw TPS):**
  - tool-call schema conformance (parses, correct args)
  - argument correctness for supplied schemas
  - multi-turn tool chain success
- **Do NOT measure (would produce invalid signal for this capability):**
  - single-turn text quality alone — misses the agent capability
- **Workspace slot requirements for valid bench data:**
  - `tools`: populated with representative tool definitions
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-dolphin-llama3`)
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 1 invalid (pre-boundary)
- **Newest evidence:** 2026-08-02 (8d) ⚠ **all pre-boundary**
- **Pre-boundary closeout signals (NOT authoritative — re-affirm on current stack):** pass
  - `tests/benchmarks/results/omlx_v3_reeval_20260802T221435Z.md`
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `hermes3:8b` — 4.3 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - nothing distinctive — arch/vendor/capability all remain represented after removal
- **What we'd gain:** 4.3 GB disk

### Intake rationale

- **Intake age:** 0d ago (first-seen commit `d6603676`)
- **Mentioned in 5 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## creative (11)
    > - `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4` \ - `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k` \ - `hermes3:8b` \ - `hf.co/gaston-parravicini/LFM2.5-8B…
  - `docs/generated/ARCHITECTURE_MAP.md` — ## Knowledge Layer
    > | `unit-model-catalog-granite4-1-8b-ctx16k` | what | 2 | \ | `unit-model-catalog-granite4-1-8b-ctx8k` | what | 2 | \ | `unit-model-catalog-hermes3-8b` | what | 1 | \ | `unit-model-catalog-hf-co-abiray…
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## creative (11)
    > - `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4` \ - `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k` \ - `hermes3:8b` \ - `hf.co/gaston-parravicini/LFM2.5-8B…

### Capability profile

- **Architecture:** unknown
- **Parameters:** 8B
- **Source:** ollama-library (`ollama-library`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'hermes3:8b'

### Fleet position

- **Bench workspaces routing here:** none (bench-orphaned)
- **Same-arch (`unknown`) production workspaces:** 0
- **Same-arch bench workspaces:** 0
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `unknown` workspaces in fleet:** 0
- **Other workspaces from `ollama-library`:** 41

### Card claims vs our slotting

- **Card source:** `https://ollama.com/library/hermes3` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!doctype html> <html class="h-full overflow-y-scroll"> <head> <title>hermes3</title>
- **Deployment signals extracted:** reasoning-trace capability
- **Slotting:** bench-orphaned — nothing routes to this tag
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `reasoning-explicit` — Explicit reasoning / thinking traces
- **Recommended harness:** reasoning-aware persona matrix — capture and score the thinking traces, not just final answers
- **Prompt corpus:** multi-step reasoning tasks: math, logic, planning, code with edge cases
- **Metrics to capture (beyond raw TPS):**
  - task success rate WITH reasoning captured
  - reasoning coherence score
  - TPS separated by reasoning-on vs reasoning-off runs
  - trace length vs task complexity
- **Do NOT measure (would produce invalid signal for this capability):**
  - single-turn factual recall (doesn't exercise reasoning)
- **Workspace slot requirements for valid bench data:**
  - `emits_reasoning`: true — otherwise the harness sees a truncated model
  - `predict_limit`: high enough to fit thinking traces (8k+ typical)
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-hermes3`)
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 3 invalid (pre-boundary)
- **Avg TPS (pre-boundary — INVALID for decisions):** 35.33 — captured under prior stack
- **Newest evidence:** 2026-06-10 (61d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `huihui_ai/gemma-4-abliterated:E2b-qat-ctx8k` — 4.1 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - capability: Abliterated (safety-vector ablation)
- **What we'd gain:** 4.1 GB disk

### Intake rationale

- **Intake age:** 39d ago (first-seen commit `5dd51bb6`)
- **Mentioned in 5 doc file(s):**
  - `docs/HOWTO.md` — ## 6. Security Analysis
    > | `purpleteam-exec` | Execution, 4-hop | `supergemma4-26b-uncensored:Q4_K_M-ctx64k` → same chain | execute_bash, execute_python, web_search | \  \ The `pentest` variant runs inside the `portal5-attack…
  - `docs/ADMIN_GUIDE.md` — ## security (32)
    > - `huihui_ai/baronllm-abliterated:latest-ctx8k` \ - `huihui_ai/gemma-4-abliterated:E2b-qat` \ - `huihui_ai/gemma-4-abliterated:E2b-qat-ctx8k` \ - `huihui_ai/qwen3.5-abliterated:9b` \ - `huihui_ai/qwen…
  - `docs/generated/ARCHITECTURE_MAP.md` — ## Knowledge Layer
    > | `unit-model-catalog-huihui-ai-baronllm-abliterated-latest-ctx8k` | what | 2 | \ | `unit-model-catalog-huihui-ai-baronllm-abliterated-latest-dropped-evaluated-not-adopted-supersedes-the-gated-alicank…

### Capability profile

- **Architecture:** Gemma4
- **Parameters:** 2B
- **Source:** ollama-library-namespaced (`huihui_ai`)
- **Distinguishing features (from tag pattern):**
  - Abliterated (safety-vector ablation)
- **Reversibility:** ollama pull 'huihui_ai/gemma-4-abliterated:E2b-qat-ctx8k'

### Fleet position

- **Bench workspaces routing here:** none (bench-orphaned)
- **Same-arch (`Gemma4`) production workspaces:** 2
  - `gemma4:26b-a4b-it-qat-ctx8k` (via `auto-daily`)
  - `gemma4:12b-it-qat-ctx8k` (via `auto-audio`)
- **Same-arch bench workspaces:** 12
  - `gemma4:26b-a4b-it-q4_K_M` (via `bench-gemma4-26b-optiq`)
  - `gemma4:12b-it-qat` (via `bench-gemma4-12b`)
  - `gemma4:e4b-it-q4_K_M` (via `bench-gemma4-e4b`)
  - `gemma4:e2b-it-qat` (via `bench-gemma4-e2b`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `Gemma4` workspaces in fleet:** 14
- **Other workspaces from `huihui_ai`:** 10

### Card claims vs our slotting

- **Card source:** `https://ollama.com/huihui_ai/gemma-4-abliterated` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!doctype html> <html class="h-full overflow-y-scroll"> <head> <title>huihui_ai/gemma-4-abliterated</title>
- **Deployment signals extracted:** vision / multimodal capability advertised, reasoning-trace capability, abliterated / uncensored
- **Slotting:** bench-orphaned — nothing routes to this tag
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `vision` — Vision / multimodal (non-CUA)
- **Recommended harness:** vision probe (image → text tasks)
- **Prompt corpus:** image + question pairs across VQA, captioning, OCR
- **Metrics to capture (beyond raw TPS):**
  - VQA accuracy
  - caption quality
  - OCR fidelity if advertised
- **Do NOT measure (would produce invalid signal for this capability):**
  - text-only quality alone — misses the modality that justifies the model
- **Workspace slot requirements for valid bench data:**
  - `mmproj`: vision projector REQUIRED
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-gemma-4-abliterated`)
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest post-boundary evidence:** 2026-08-11
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `huihui_ai/gemma-4-abliterated:E2b-qat` — 4.1 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - capability: Abliterated (safety-vector ablation)
- **What we'd gain:** 4.1 GB disk

### Intake rationale

- **Intake age:** 46d ago (first-seen commit `84c15f78`)
- **Mentioned in 5 doc file(s):**
  - `docs/HOWTO.md` — ## 6. Security Analysis
    > | `purpleteam-exec` | Execution, 4-hop | `supergemma4-26b-uncensored:Q4_K_M-ctx64k` → same chain | execute_bash, execute_python, web_search | \  \ The `pentest` variant runs inside the `portal5-attack…
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `huihui_ai/Qwen3.6-abliterated:27b-ctx8k` \ - `huihui_ai/baronllm-abliterated:latest` \ - `huihui_ai/gemma-4-abliterated:E2b-qat` \ - `huihui_ai/qwen3-abliterated:14b-v2` \ - `huihui_ai/qwen3.5-abli…
  - `docs/generated/ARCHITECTURE_MAP.md` — ## Knowledge Layer
    > | `unit-model-catalog-huihui-ai-baronllm-abliterated-latest-ctx8k` | what | 2 | \ | `unit-model-catalog-huihui-ai-baronllm-abliterated-latest-dropped-evaluated-not-adopted-supersedes-the-gated-alicank…

### Capability profile

- **Architecture:** Gemma4
- **Parameters:** 2B
- **Source:** ollama-library-namespaced (`huihui_ai`)
- **Distinguishing features (from tag pattern):**
  - Abliterated (safety-vector ablation)
- **Reversibility:** ollama pull 'huihui_ai/gemma-4-abliterated:E2b-qat'

### Fleet position

- **Bench workspaces routing here:** `bench-e2b-pentest`, `bench-exec-reasoning`
- **Same-arch (`Gemma4`) production workspaces:** 2
  - `gemma4:26b-a4b-it-qat-ctx8k` (via `auto-daily`)
  - `gemma4:12b-it-qat-ctx8k` (via `auto-audio`)
- **Same-arch bench workspaces:** 10
  - `gemma4:26b-a4b-it-q4_K_M` (via `bench-gemma4-26b-optiq`)
  - `gemma4:12b-it-qat` (via `bench-gemma4-12b`)
  - `gemma4:e4b-it-q4_K_M` (via `bench-gemma4-e4b`)
  - `gemma4:e2b-it-qat` (via `bench-gemma4-e2b`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `Gemma4` workspaces in fleet:** 12
- **Other workspaces from `huihui_ai`:** 8

### Card claims vs our slotting

- **Card source:** `https://ollama.com/huihui_ai/gemma-4-abliterated` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!doctype html> <html class="h-full overflow-y-scroll"> <head> <title>huihui_ai/gemma-4-abliterated</title>
- **Deployment signals extracted:** vision / multimodal capability advertised, reasoning-trace capability, abliterated / uncensored
- **What portal.yaml says we slotted it for** (2 bench workspace(s)):
  - `bench-e2b-pentest` | tools: 3 configured
    > HEAD-TO-HEAD EVAL 2026-06-24: Gemma4-E2B-QAT abliterated (3GB, 71.6 t/s) vs baronllm (auto-pentest primary, 8B). Mirrors auto-pentest system prompt exactly — same tools, same lab environment, same hard constraints. Scoring: theory quality, refusal rate, MITRE ATT&CK coverage. If E2b-qat matches baronllm: promotes to auto-pentest primary, 18GB memory savings per concurrent request.
  - `bench-exec-reasoning` | tools: 3 configured
    > Security bench exec-chain role: EXPLOITATION / REASONING. Routes to Gemma4-E2B-QAT abliterated (3GB, 71.6 t/s), bench winner 2026-06-24 at 80.0% (108/135 steps, best of 8 candidates). Replaced Qwable-35B (+7.6pp, 18GB freed). Used by bench --exec-chain-models ... bench-exec-reasoning ... for the exploitation phase of multi-model attack chains through the pipeline.
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - card advertises vision/multimodal but no slot text mentions vision, mmproj, or image tasks — advertised capability likely untested
  - card advertises reasoning traces but no slot has `emits_reasoning: true` — advertised capability untested

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `vision` — Vision / multimodal (non-CUA)
- **Recommended harness:** vision probe (image → text tasks)
- **Prompt corpus:** image + question pairs across VQA, captioning, OCR
- **Metrics to capture (beyond raw TPS):**
  - VQA accuracy
  - caption quality
  - OCR fidelity if advertised
- **Do NOT measure (would produce invalid signal for this capability):**
  - text-only quality alone — misses the modality that justifies the model
- **Workspace slot requirements for valid bench data:**
  - `mmproj`: vision projector REQUIRED
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - `bench-e2b-pentest`: needs vision projector (`mmproj`) — the bench cannot produce valid multimodal data without it
  - `bench-exec-reasoning`: needs vision projector (`mmproj`) — the bench cannot produce valid multimodal data without it
  - card advertises vision/multimodal but no slot text mentions vision, mmproj, or image tasks — advertised capability likely untested
  - card advertises reasoning traces but no slot has `emits_reasoning: true` — advertised capability untested


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest post-boundary evidence:** 2026-08-11
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `hf.co/Andycurrent/Mistral-7B-Uncensored-GGUF:Q4_K_M` — 4.1 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - **Mistral disappears from the fleet entirely** — no other workspace uses this arch family
  - **last model from `Andycurrent`** — vendor exits the fleet
  - NET-NEW arch family: `Mistral` (not in fleet elsewhere)
  - NET-NEW vendor: `Andycurrent` (not in fleet elsewhere)
  - only exploration of `Mistral` arch — no other workspace tests it
- **What we'd gain:** 4.1 GB disk

### Intake rationale

- **Intake age:** 31d ago (first-seen commit `8face6b5`)
- **Mentioned in 4 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `granite4.1:8b-ctx8k` \ - `hf.co/Abiray/Agents-A1-Q4_K_M-GGUF:Q4_K_M` \ - `hf.co/Andycurrent/Mistral-7B-Uncensored-GGUF:Q4_K_M` \ - `hf.co/BugTraceAI/BugTraceAI-CORE-Ultra-27B-Q6:Q6_K` \ - `hf.co/Ja…
  - `docs/generated/ARCHITECTURE_MAP.md` — ## Knowledge Layer
    > | `unit-model-catalog-hermes3-8b` | what | 1 | \ | `unit-model-catalog-hf-co-abiray-agents-a1-q4-k-m-gguf-q4-k-m` | what | 2 | \ | `unit-model-catalog-hf-co-andycurrent-mistral-7b-uncensored-gguf-q4-k…
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## general (84)
    > - `granite4.1:8b-ctx8k` \ - `hf.co/Abiray/Agents-A1-Q4_K_M-GGUF:Q4_K_M` \ - `hf.co/Andycurrent/Mistral-7B-Uncensored-GGUF:Q4_K_M` \ - `hf.co/BugTraceAI/BugTraceAI-CORE-Ultra-27B-Q6:Q6_K` \ - `hf.co/Ja…

### Capability profile

- **Architecture:** Mistral
- **Parameters:** 7B
- **Quantization:** Q4_K_M (mixed)
- **Source:** huggingface (`Andycurrent`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'hf.co/Andycurrent/Mistral-7B-Uncensored-GGUF:Q4_K_M'

### Fleet position

- **Bench workspaces routing here:** `bench-mistral7b-uncensored`
- **Same-arch (`Mistral`) production workspaces:** 0
- **Same-arch bench workspaces:** 0
- **Net-new signals (fleet has no other with these):**
  - arch family: `Mistral` (not in fleet elsewhere)
  - vendor: `Andycurrent` (not in fleet elsewhere)
- ⚠ **Removal ends all fleet exploration of `Mistral`**

### Diversity impact

- ⚠ **ARCH LOSS**: `Mistral` disappears from fleet entirely if removed
- ⚠ **VENDOR LOSS**: `Andycurrent` exits the fleet

### Card claims vs our slotting

- **Card source:** `https://huggingface.co/Andycurrent/Mistral-7B-Uncensored-GGUF/raw/main/README.md` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > This repository provides the Mistral-7B-Uncensored model — a 7-billion-parameter conversational system designed for users who need responsive behavior with minimal automated filtering. Ideal for experimentation, offline usage, and custom alignment work.
- **Card-advertised strengths:**
  - **Capabilities:** - Tuned for instruction-following and productive dialogue - Reduced filtering to support research and customization - Handles contextual reasoning and multi-step tasks - Strong performance on creative writing, utility prompts, and open-ended discussion - Designed for local inference, CPU-friendly runtimes, and quantized deployment - Stable behavior…
- **Deployment signals extracted:** reasoning-trace capability, abliterated / uncensored
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-mistral7b-uncensored` | tools: none
    > Mistral-7B Uncensored (~4.4GB Q4_K_M, Andycurrent GGUF of luvGPT base, Mistral-7B lineage). LINEAGE-DIVERSITY candidate for the Nano/Micro tier, currently Qwen/Gemma-dominant. Mistral is a distinct base architecture not otherwise represented in the fleet — same diversity rationale class as lfm2.5:8b's non-transformer slot. NOT a capability upgrade over existing Nano/Micro models; scored on lineage…
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - card advertises reasoning traces but no slot has `emits_reasoning: true` — advertised capability untested

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `reasoning-explicit` — Explicit reasoning / thinking traces
- **Recommended harness:** reasoning-aware persona matrix — capture and score the thinking traces, not just final answers
- **Prompt corpus:** multi-step reasoning tasks: math, logic, planning, code with edge cases
- **Metrics to capture (beyond raw TPS):**
  - task success rate WITH reasoning captured
  - reasoning coherence score
  - TPS separated by reasoning-on vs reasoning-off runs
  - trace length vs task complexity
- **Do NOT measure (would produce invalid signal for this capability):**
  - single-turn factual recall (doesn't exercise reasoning)
- **Workspace slot requirements for valid bench data:**
  - `emits_reasoning`: true — otherwise the harness sees a truncated model
  - `predict_limit`: high enough to fit thinking traces (8k+ typical)
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - `bench-mistral7b-uncensored`: needs `emits_reasoning: true` — otherwise reasoning trace is suppressed
  - `bench-mistral7b-uncensored`: `predict_limit` needs to accommodate high enough to fit thinking traces (8k+ typical)
  - card advertises reasoning traces but no slot has `emits_reasoning: true` — advertised capability untested


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest post-boundary evidence:** 2026-08-11
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `gemma4:e2b-it-qat-ctx8k` — 4.0 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - nothing distinctive — arch/vendor/capability all remain represented after removal
- **What we'd gain:** 4.0 GB disk

### Intake rationale

- **Intake age:** 39d ago (first-seen commit `5dd51bb6`)
- **Mentioned in 5 doc file(s):**
  - `docs/HOWTO.md` — ## 3. Workspaces
    > |---|---|---| \ | `auto` (Portal Auto Router) | `huihui_ai/qwen3.5-abliterated:9b-ctx8k` | LLM intent classifier routes onward | \ | `auto-daily` | `gemma4:26b-a4b-it-qat-ctx8k` | web_search, create_w…
  - `docs/MLX_CHANGES_2026-04-26.md` — ## Upgrades Applied
    > |---------|-----|-----|-------| \ | mlx (core) | 0.31.1 | 0.31.2 | Homebrew upgrade; Python bindings required manual copy of `core.cpython-314-darwin.so` and `nn/` modules from Cellar | \ | mlx-lm | 0…
  - `docs/ADMIN_GUIDE.md` — ## vision (16)
    > - `gemma4:31b-it-qat-ctx8k` \ - `gemma4:e2b-it-qat` \ - `gemma4:e2b-it-qat-ctx8k` \ - `gemma4:e4b-it-q4_K_M` \ - `gemma4:e4b-it-qat` \ - `gemma4:e4b-it-qat-ctx8k`

### Capability profile

- **Architecture:** Gemma4
- **Parameters:** 2B
- **Source:** ollama-library (`ollama-library`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'gemma4:e2b-it-qat-ctx8k'

### Fleet position

- **Bench workspaces routing here:** none (bench-orphaned)
- **Same-arch (`Gemma4`) production workspaces:** 2
  - `gemma4:26b-a4b-it-qat-ctx8k` (via `auto-daily`)
  - `gemma4:12b-it-qat-ctx8k` (via `auto-audio`)
- **Same-arch bench workspaces:** 12
  - `gemma4:26b-a4b-it-q4_K_M` (via `bench-gemma4-26b-optiq`)
  - `gemma4:12b-it-qat` (via `bench-gemma4-12b`)
  - `gemma4:e4b-it-q4_K_M` (via `bench-gemma4-e4b`)
  - `gemma4:e2b-it-qat` (via `bench-gemma4-e2b`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `Gemma4` workspaces in fleet:** 14
- **Other workspaces from `ollama-library`:** 41

### Card claims vs our slotting

- **Card source:** `https://ollama.com/library/gemma4` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!doctype html> <html class="h-full overflow-y-scroll"> <head> <title>gemma4</title>
- **Deployment signals extracted:** vision / multimodal capability advertised, specific chat template requirement, reasoning-trace capability, MoE architecture confirmed
- **Slotting:** bench-orphaned — nothing routes to this tag
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `vision` — Vision / multimodal (non-CUA)
- **Recommended harness:** vision probe (image → text tasks)
- **Prompt corpus:** image + question pairs across VQA, captioning, OCR
- **Metrics to capture (beyond raw TPS):**
  - VQA accuracy
  - caption quality
  - OCR fidelity if advertised
- **Do NOT measure (would produce invalid signal for this capability):**
  - text-only quality alone — misses the modality that justifies the model
- **Workspace slot requirements for valid bench data:**
  - `mmproj`: vision projector REQUIRED
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - model is bench-orphaned — a workspace must be added to portal.yaml before benching (recommended: `bench-gemma4`)
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest evidence:** 2026-06-21 (50d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `gemma4:e2b-it-qat` — 4.0 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - nothing distinctive — arch/vendor/capability all remain represented after removal
- **What we'd gain:** 4.0 GB disk

### Intake rationale

- **Intake age:** 46d ago (first-seen commit `84c15f78`)
- **Mentioned in 5 doc file(s):**
  - `docs/HOWTO.md` — ## 3. Workspaces
    > |---|---|---| \ | `auto` (Portal Auto Router) | `huihui_ai/qwen3.5-abliterated:9b-ctx8k` | LLM intent classifier routes onward | \ | `auto-daily` | `gemma4:26b-a4b-it-qat-ctx8k` | web_search, create_w…
  - `docs/MLX_CHANGES_2026-04-26.md` — ## Upgrades Applied
    > |---------|-----|-----|-------| \ | mlx (core) | 0.31.1 | 0.31.2 | Homebrew upgrade; Python bindings required manual copy of `core.cpython-314-darwin.so` and `nn/` modules from Cellar | \ | mlx-lm | 0…
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `gemma4:26b-a4b-it-qat-ctx8k` \ - `gemma4:31b-it-qat` \ - `gemma4:e2b-it-qat` \ - `gemma4:e4b-it-q4_K_M` \ - `gemma4:e4b-it-qat` \ - `glm-4.7-flash:Q4_K_M`

### Capability profile

- **Architecture:** Gemma4
- **Parameters:** 2B
- **Source:** ollama-library (`ollama-library`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'gemma4:e2b-it-qat'

### Fleet position

- **Bench workspaces routing here:** `bench-gemma4-e2b`
- **Same-arch (`Gemma4`) production workspaces:** 2
  - `gemma4:26b-a4b-it-qat-ctx8k` (via `auto-daily`)
  - `gemma4:12b-it-qat-ctx8k` (via `auto-audio`)
- **Same-arch bench workspaces:** 11
  - `gemma4:26b-a4b-it-q4_K_M` (via `bench-gemma4-26b-optiq`)
  - `gemma4:12b-it-qat` (via `bench-gemma4-12b`)
  - `gemma4:e4b-it-q4_K_M` (via `bench-gemma4-e4b`)
  - `gemma4:e4b-it-qat` (via `bench-gemma4-e4b-qat`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `Gemma4` workspaces in fleet:** 13
- **Other workspaces from `ollama-library`:** 40

### Card claims vs our slotting

- **Card source:** `https://ollama.com/library/gemma4` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!doctype html> <html class="h-full overflow-y-scroll"> <head> <title>gemma4</title>
- **Deployment signals extracted:** vision / multimodal capability advertised, specific chat template requirement, reasoning-trace capability, MoE architecture confirmed
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-gemma4-e2b` | tools: none
    > Benchmark: gemma4:e2b-it-qat (Ollama, Google DeepMind, Apache 2.0). Effective 2B QAT — ~3GB, audio+image+video+text, thinking, 128K ctx. Fastest TPS candidate in fleet. QAT: near-BF16 at 4-bit. PROMOTE_POLICY=confirm.
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - card advertises reasoning traces but no slot has `emits_reasoning: true` — advertised capability untested

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `vision` — Vision / multimodal (non-CUA)
- **Recommended harness:** vision probe (image → text tasks)
- **Prompt corpus:** image + question pairs across VQA, captioning, OCR
- **Metrics to capture (beyond raw TPS):**
  - VQA accuracy
  - caption quality
  - OCR fidelity if advertised
- **Do NOT measure (would produce invalid signal for this capability):**
  - text-only quality alone — misses the modality that justifies the model
- **Workspace slot requirements for valid bench data:**
  - `mmproj`: vision projector REQUIRED
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - card advertises reasoning traces but no slot has `emits_reasoning: true` — advertised capability untested


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest evidence:** 2026-06-21 (50d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-4B-MTP-GGUF:Q4_K_M` — 3.8 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - capability: MTP speculative drafting (draft model bound to base)
- **What we'd gain:** 3.8 GB disk

### Intake rationale

- **Intake age:** 0d ago (first-seen commit `de01e9b1`)
- **Mentioned in 3 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `hf.co/Andycurrent/Mistral-7B-Uncensored-GGUF:Q4_K_M` \ - `hf.co/BugTraceAI/BugTraceAI-CORE-Ultra-27B-Q6:Q6_K` \ - `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-4B-MTP-GGUF:Q4_K_M` \ - `hf.co/Jackrong/Dee…
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## general (84)
    > - `hf.co/Andycurrent/Mistral-7B-Uncensored-GGUF:Q4_K_M` \ - `hf.co/BugTraceAI/BugTraceAI-CORE-Ultra-27B-Q6:Q6_K` \ - `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-4B-MTP-GGUF:Q4_K_M` \ - `hf.co/Jackrong/Dee…
  - `portal_wiki/canonical/unit-model-catalog-jackrong-deepseek-v4-pro-qwen3-5-4b-mtp.md` — (no nearby heading)
    > id: unit-model-catalog-jackrong-deepseek-v4-pro-qwen3-5-4b-mtp \ kind: what \ title: "MODEL_CATALOG \u2014 `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-4B-MTP-GGUF:Q4_K_M`" \ sources: \ - type: code \   pa…

### Capability profile

- **Architecture:** Qwen3
- **Parameters:** 4B
- **Quantization:** Q4_K_M (mixed)
- **Source:** huggingface (`Jackrong`)
- **Distinguishing features (from tag pattern):**
  - MTP speculative drafting (draft model bound to base)
- **Reversibility:** ollama pull 'hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-4B-MTP-GGUF:Q4_K_M'

### Fleet position

- **Bench workspaces routing here:** `bench-jackrong-dsv4-4b`
- **Same-arch (`Qwen3`) production workspaces:** 3
  - `huihui_ai/qwen3.5-abliterated:9b-ctx8k` (via `auto`)
  - `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k` (via `auto-reasoning`)
  - `qwen3-vl:32b-ctx8k` (via `auto-vision`)
- **Same-arch bench workspaces:** 4
  - `huihui_ai/qwen3.5-abliterated:9b` (via `bench-qwen35-abliterated`)
  - `hf.co/mradermacher/Qwen3.5-9B-Claude-4.6-HighIQ-THINKING-HERETIC-UNCENSORED-GGUF:Q4_K_M` (via `bench-qwen35-9b-heretic-vision`)
  - `huihui_ai/qwen3-abliterated:14b-v2` (via `bench-qwen3-14b-abliterated`)
  - `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-9B-MTP-GGUF:Q4_K_M` (via `bench-jackrong-dsv4-9b`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `Qwen3` workspaces in fleet:** 7
- **Other workspaces from `Jackrong`:** 2

### Card claims vs our slotting

- **Card source:** `https://huggingface.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-4B-MTP-GGUF/raw/main/README.md` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; border: 1px solid #cbd5e1; border-radius: 16px; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.05), 0 4px 6px -2px rgba(0,0,0,0.05); overflow: hidden; background: #ffffff; margin-bottom: 30px;"> <div style="background: linear-gradient(135deg, #7c3aed 0%, #4c1d95 100%); padding: 24px; color: white;"> <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px;"> <h1 style="margin: 0; font-size: 26px; font-weight: 800; color: white; border: none;">🧠 DeepSeek-V4-Pr
- **Deployment signals extracted:** reasoning-trace capability, speculative / MTP drafting
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-jackrong-dsv4-4b` | tools: none | emits_reasoning
    > Benchmark: hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-4B-MTP-GGUF:Q4_K_M (arch qwen35). 4B sibling of bench-jackrong-dsv4-9b — cheap small-reasoner tier. The bare `Jackrong/DeepSeek-V4-Pro-Qwen3.5-4B` repo is safetensors-only (no GGUF); found the official `Jackrong/DeepSeek-V4-Pro-Qwen3.5-4B-MTP-GGUF` mirror instead, pulled clean, no arch/tag issues.
BENCH RESULT 2026-08-10: TPS 52.4 t/s avg (5/5, Q-s…
- **Card vs slotting alignment ✓:**
  - card advertises reasoning; slot has `emits_reasoning: true`

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `mtp-speculative` — MTP / speculative drafting
- **Recommended harness:** MTP-aware bench — draft acceptance rate + wall-time speedup vs base
- **Prompt corpus:** IDENTICAL to base model's bench for direct comparison
- **Metrics to capture (beyond raw TPS):**
  - draft token acceptance rate (headline signal)
  - wall-time speedup vs base model on identical prompts
  - quality parity vs base (any regression kills the value proposition)
- **Do NOT measure (would produce invalid signal for this capability):**
  - raw TPS without comparing to base — meaningless in isolation
- **Workspace slot requirements for valid bench data:**
  - `paired_draft`: draft model config must be present, correct, and pinned to matching base


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest post-boundary evidence:** 2026-08-11
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `llama3.2:3b-instruct-q8_0-ctx8k` — 3.2 GB

### At a glance

- **Hypothesis (non-authoritative):** `keep-open` — card/slot mismatch: 1 advertised capabilities untested; removes Llama3 arch from fleet entirely; net-new: arch family: `Llama3` (not in fleet elsewhere); only exploration of this arch in the fleet; introduced 0d ago — still in eval window
- **What we'd lose if removed:**
  - **Llama3 disappears from the fleet entirely** — no other workspace uses this arch family
  - NET-NEW arch family: `Llama3` (not in fleet elsewhere)
  - only exploration of `Llama3` arch — no other workspace tests it
- **What we'd gain:** 3.2 GB disk

### Intake rationale

- **Intake age:** 0d ago (first-seen commit `d6603676`)
- **Mentioned in 5 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `lfm2.5:8b-ctx8k` \ - `llama3.2:3b` \ - `llama3.2:3b-instruct-q8_0-ctx8k` \ - `meta-secalign-8b-q4_k_m:latest` \ - `mistral-small3.2:24b` \ - `muse-glimmer:30b-mlx`
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## general (84)
    > - `lfm2.5:8b-ctx8k` \ - `llama3.2:3b` \ - `llama3.2:3b-instruct-q8_0-ctx8k` \ - `meta-secalign-8b-q4_k_m:latest` \ - `mistral-small3.2:24b` \ - `muse-glimmer:30b-mlx`
  - `portal_wiki/canonical/unit-model-catalog-llama3-2-3b-instruct-q8-0-ctx8k.md` — (no nearby heading)
    > id: unit-model-catalog-llama3-2-3b-instruct-q8-0-ctx8k \ kind: what \ title: "MODEL_CATALOG \u2014 `llama3.2:3b-instruct-q8_0-ctx8k`" \ sources: \ - type: code \   path: config/backends.yaml

### Capability profile

- **Architecture:** Llama3
- **Parameters:** 3B
- **Quantization:** Q8_0
- **Source:** ollama-library (`ollama-library`)
- **Distinguishing features (from tag pattern):**
  - Instruction-tuned
- **Reversibility:** ollama pull 'llama3.2:3b-instruct-q8_0-ctx8k'

### Fleet position

- **Bench workspaces routing here:** none (bench-orphaned)
- **Same-arch (`Llama3`) production workspaces:** 0
- **Same-arch bench workspaces:** 0
- **Net-new signals (fleet has no other with these):**
  - arch family: `Llama3` (not in fleet elsewhere)
- ⚠ **Removal ends all fleet exploration of `Llama3`**

### Diversity impact

- ⚠ **ARCH LOSS**: `Llama3` disappears from fleet entirely if removed
- **Other workspaces from `ollama-library`:** 41

### Card claims vs our slotting

- **Card source:** `https://ollama.com/library/llama3.2` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!doctype html> <html class="h-full overflow-y-scroll"> <head> <title>llama3.2</title>
- **Slotting:** bench-orphaned — nothing routes to this tag
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here

### Prescribed re-bench (capability-appropriate)

- **Capability category:** `general` — General / no specific capability advertised
- **Recommended harness:** bench_tps + portal5_persona_matrix (standard fleet path)
- **Prompt corpus:** default persona matrix across the model's target lane
- **Metrics to capture (beyond raw TPS):**
  - avg_tps vs the 20 t/s floor
  - quality_score vs same-lane incumbent
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here


### Numeric evidence

- **Evidence rows mined:** 1 valid (post-boundary), 0 invalid (pre-boundary)
- **Avg TPS (post-boundary only):** 31.7 (above floor)
- **Avg quality_score (post-boundary):** 1.0
- **Newest post-boundary evidence:** 2026-08-09


## `hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M` — 2.3 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - **last model from `mitkox`** — vendor exits the fleet
  - NET-NEW vendor: `mitkox` (not in fleet elsewhere)
- **What we'd gain:** 2.3 GB disk

### Intake rationale

- **Intake age:** 46d ago (first-seen commit `84c15f78`)
- **Mentioned in 5 doc file(s):**
  - `docs/MCP_DEV_TOOLING.md` — ### FastContext Repository Explorer
    > <!-- WIKI:GENERATED unit=unit-mcp-dev-tooling-fastcontext-repository-explorer --> \ `explore_repository` in `portal/platform/mcp_host/pipeline_mcp.py` runs the \ FastContext model (`hf.co/mitkox/FastC…
  - `docs/ADMIN_GUIDE.md` — ## coding (41)
    > - `hf.co/deepreinforce-ai/Ornith-1.0-35B-GGUF:Q4_K_M` \ - `hf.co/deepreinforce-ai/Ornith-1.0-35B-GGUF:Q4_K_M-ctx64k` \ - `hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M` \ - `hf.co/sjakek/Nex-…
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## coding (41)
    > - `hf.co/deepreinforce-ai/Ornith-1.0-35B-GGUF:Q4_K_M` \ - `hf.co/deepreinforce-ai/Ornith-1.0-35B-GGUF:Q4_K_M-ctx64k` \ - `hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M` \ - `hf.co/sjakek/Nex-…

### Capability profile

- **Architecture:** unknown
- **Parameters:** 4B
- **Quantization:** Q4_K_M (mixed)
- **Source:** huggingface (`mitkox`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M'

### Fleet position

- **Bench workspaces routing here:** `bench-fastcontext`
- **Same-arch (`unknown`) production workspaces:** 0
- **Same-arch bench workspaces:** 0
- **Net-new signals (fleet has no other with these):**
  - vendor: `mitkox` (not in fleet elsewhere)

### Diversity impact

- **Other `unknown` workspaces in fleet:** 0
- ⚠ **VENDOR LOSS**: `mitkox` exits the fleet

### Card claims vs our slotting

- **Card source:** `https://huggingface.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF/raw/main/README.md` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > This model was converted to GGUF format from [`microsoft/FastContext-1.0-4B-SFT`](https://huggingface.co/microsoft/FastContext-1.0-4B-SFT) using llama.cpp via the ggml.ai's [GGUF-my-repo](https://huggingface.co/spaces/ggml-org/gguf-my-repo) space. Refer to the [original model card](https://huggingface.co/microsoft/FastContext-1.0-4B-SFT) for more details on the model.
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-fastcontext` | tools: none
    > Benchmark: hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M (Microsoft github.com/microsoft/fastcontext, mitkox GGUF quant). 4B SFT model purpose-trained for long-context retrieval and reasoning: needle-in-haystack, multi-hop QA, instruction following at 32K–128K ctx. NOT a coding or tool-use model. NOT suitable as router (standard model; refusals). PROBE RESULT (2026-06-15): returns empty c…
- **Alignment:** no distinctive claim/slot mismatch detected — slot config appears consistent with card

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `general` — General / no specific capability advertised
- **Recommended harness:** bench_tps + portal5_persona_matrix (standard fleet path)
- **Prompt corpus:** default persona matrix across the model's target lane
- **Metrics to capture (beyond raw TPS):**
  - avg_tps vs the 20 t/s floor
  - quality_score vs same-lane incumbent


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest post-boundary evidence:** 2026-08-11
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `cybersecqwen-4b-toolfix:latest` — 2.3 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - capability: Cyber / security domain training
- **What we'd gain:** 2.3 GB disk

### Intake rationale

- **Intake age:** 36d ago (first-seen commit `d15d4a64`)
- **Mentioned in 5 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > ## general (84) \  \ - `cybersecqwen-4b-toolfix:latest` \ - `devstral-small-2:latest` \ - `devstral:24b` \ - `dolphin-llama3:8b`
  - `docs/generated/ARCHITECTURE_MAP.md` — ## Knowledge Layer
    > | `unit-model-catalog-baronllm-q6-k` | what | 2 | \ | `unit-model-catalog-blue-red-candidate-batch-evaluated-2026-07-03-none-promoted` | what | 2 | \ | `unit-model-catalog-cybersecqwen-4b-toolfix-late…
  - `portal_wiki/canonical/unit-model-catalog-cybersecqwen-4b-toolfix-latest.md` — (no nearby heading)
    > id: unit-model-catalog-cybersecqwen-4b-toolfix-latest \ kind: what \ title: "MODEL_CATALOG \u2014 `cybersecqwen-4b-toolfix:latest`" \ sources: \ - type: code \   path: config/backends.yaml

### Capability profile

- **Architecture:** unknown
- **Parameters:** 4B
- **Source:** ollama-library (`ollama-library`)
- **Distinguishing features (from tag pattern):**
  - Cyber / security domain training
- **Reversibility:** ollama pull 'cybersecqwen-4b-toolfix:latest'

### Fleet position

- **Bench workspaces routing here:** `bench-cybersecqwen-4b-toolfix`
- **Same-arch (`unknown`) production workspaces:** 0
- **Same-arch bench workspaces:** 0
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `unknown` workspaces in fleet:** 0
- **Other workspaces from `ollama-library`:** 40

### Card claims vs our slotting

- **Card status:** card fetch returned 404 — repo may have been renamed or removed
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-cybersecqwen-4b-toolfix` (🧪 Bench · CyberSecQwen-4B (toolfix))
    > cybersecqwen-4b-toolfix (~2.5GB, retemplated from mradermacher/CyberSecQwen-4B-GGUF Q4_K_M to add Qwen-style <tool_call> tag support — the base tag hard-errors "does not support tools" in Ollama). Multi-seat V2 bench candidate (2026-07-05) — blue seat. tools: [] deliberately: this workspace exists only so the pipeline resolves the exact model instead of falling back to the general group's first mo…

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `security-tooling` — Security tooling (exploit / artifact generation)
- **Recommended harness:** security exec-chain scorer — measures artifact runnability, not chat quality
- **Prompt corpus:** CVE writeup → PoC; vulnerability description → Nuclei template; exploit-target descriptions
- **Metrics to capture (beyond raw TPS):**
  - artifact runnability (compiles / executes as-emitted)
  - refusal rate on offensive prompts (should be near-zero for these models)
  - attack-chain success on synthetic targets
- **Do NOT measure (would produce invalid signal for this capability):**
  - MMLU / general chat quality — model was not trained for chat
  - refusal on benign prompts — irrelevant to the capability
- **Workspace slot requirements for valid bench data:**
  - `tools`: empty ([]) — tool exposure causes reasoning-loop failures per BugTraceAI card guidance
  - `emits_reasoning`: true — capture the reasoning trace, don't suppress it
  - `temperature`: 0.1–0.3 for reproducibility
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - `bench-cybersecqwen-4b-toolfix`: needs `emits_reasoning: true` — otherwise reasoning trace is suppressed


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest post-boundary evidence:** 2026-08-11
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `llama3.2:3b` — 1.9 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - **Llama3 disappears from the fleet entirely** — no other workspace uses this arch family
  - NET-NEW arch family: `Llama3` (not in fleet elsewhere)
  - only exploration of `Llama3` arch — no other workspace tests it
- **What we'd gain:** 1.9 GB disk

### Intake rationale

- **Intake age:** 0d ago (first-seen commit `d6603676`)
- **Mentioned in 5 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ### Three-Tier Router Models
    > <!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-three-tier-router-models --> \ Three router tiers are documented in `.env.example` and the header of routing.py. PRIMARY is `hf.co/mradermacher/gemma-4-E4B-it…
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## general (84)
    > - `lfm2.5:8b` \ - `lfm2.5:8b-ctx8k` \ - `llama3.2:3b` \ - `llama3.2:3b-instruct-q8_0-ctx8k` \ - `meta-secalign-8b-q4_k_m:latest` \ - `mistral-small3.2:24b`
  - `portal_wiki/canonical/unit-model-catalog-llama3-2-3b-instruct-q8-0-ctx8k.md` — (no nearby heading)
    > id: unit-model-catalog-llama3-2-3b-instruct-q8-0-ctx8k \ kind: what \ title: "MODEL_CATALOG \u2014 `llama3.2:3b-instruct-q8_0-ctx8k`" \ sources: \ - type: code \   path: config/backends.yaml

### Capability profile

- **Architecture:** Llama3
- **Parameters:** 3B
- **Source:** ollama-library (`ollama-library`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'llama3.2:3b'

### Fleet position

- **Bench workspaces routing here:** none (bench-orphaned)
- **Same-arch (`Llama3`) production workspaces:** 0
- **Same-arch bench workspaces:** 0
- **Net-new signals (fleet has no other with these):**
  - arch family: `Llama3` (not in fleet elsewhere)
- ⚠ **Removal ends all fleet exploration of `Llama3`**

### Diversity impact

- ⚠ **ARCH LOSS**: `Llama3` disappears from fleet entirely if removed
- **Other workspaces from `ollama-library`:** 41

### Card claims vs our slotting

- **Card source:** `https://ollama.com/library/llama3.2` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <!doctype html> <html class="h-full overflow-y-scroll"> <head> <title>llama3.2</title>
- **Slotting:** bench-orphaned — nothing routes to this tag
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `general` — General / no specific capability advertised
- **Recommended harness:** bench_tps + portal5_persona_matrix (standard fleet path)
- **Prompt corpus:** default persona matrix across the model's target lane
- **Metrics to capture (beyond raw TPS):**
  - avg_tps vs the 20 t/s floor
  - quality_score vs same-lane incumbent
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest evidence:** 2026-08-05 (5d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF:latest` — 1.3 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - **Llama3 disappears from the fleet entirely** — no other workspace uses this arch family
  - **last model from `QuantFactory`** — vendor exits the fleet
  - NET-NEW arch family: `Llama3` (not in fleet elsewhere)
  - NET-NEW vendor: `QuantFactory` (not in fleet elsewhere)
  - capability: Abliterated (safety-vector ablation)
  - only exploration of `Llama3` arch — no other workspace tests it
- **What we'd gain:** 1.3 GB disk

### Intake rationale

- **Intake age:** 0d ago (first-seen commit `d6603676`)
- **Mentioned in 5 doc file(s):**
  - `docs/RESULTS_ALIAS_RETIRE_V1_20260713.md` — ## 3. The routing-regression proof (§9 safety gate)
    > reassignment above, not a regression. \ - **Layer 1 (LLM router), accuracy check against the real live router \   model** (`hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF`, the \   actual p…
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `hf.co/LiquidAI/LFM2.5-350M-GGUF:Q4_K_M` \ - `hf.co/Nguuma/security-slm-unsloth-1.5b:latest` \ - `hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF` \ - `hf.co/bartowski/Qwen_Qwen3.6-27B-GGU…
  - `portal_wiki/canonical/unit-model-catalog-hf-co-quantfactory-llama-3-2-3b-instruct-abliterated-gguf.md` — (no nearby heading)
    > id: unit-model-catalog-hf-co-quantfactory-llama-3-2-3b-instruct-abliterated-gguf \ kind: what \ title: "MODEL_CATALOG \u2014 `hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF`" \ sources: \ -…

### Capability profile

- **Architecture:** Llama3
- **Parameters:** 3B
- **Source:** huggingface (`QuantFactory`)
- **Distinguishing features (from tag pattern):**
  - Abliterated (safety-vector ablation)
  - Instruction-tuned
- **Reversibility:** ollama pull 'hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF:latest'

### Fleet position

- **Bench workspaces routing here:** none (bench-orphaned)
- **Same-arch (`Llama3`) production workspaces:** 0
- **Same-arch bench workspaces:** 0
- **Net-new signals (fleet has no other with these):**
  - arch family: `Llama3` (not in fleet elsewhere)
  - vendor: `QuantFactory` (not in fleet elsewhere)
- ⚠ **Removal ends all fleet exploration of `Llama3`**

### Diversity impact

- ⚠ **ARCH LOSS**: `Llama3` disappears from fleet entirely if removed
- ⚠ **VENDOR LOSS**: `QuantFactory` exits the fleet

### Card claims vs our slotting

- **Card source:** `https://huggingface.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF/raw/main/README.md` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > ---
- **Deployment signals extracted:** abliterated / uncensored
- **Slotting:** bench-orphaned — nothing routes to this tag
- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `abliterated` — Abliterated / uncensored
- **Recommended harness:** refusal-rate probe + capability-preservation vs base
- **Prompt corpus:** safety-elicitation set + standard capability set matched to base
- **Metrics to capture (beyond raw TPS):**
  - refusal rate on safety prompts (should be low — the point of the model)
  - capability preservation vs base (chat quality, task success) — did ablation break the model?
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - **bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest evidence:** 2026-06-20 (51d) ⚠ **all pre-boundary**
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `hf.co/Nguuma/security-slm-unsloth-1.5b:latest` — 1.0 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - **last model from `Nguuma`** — vendor exits the fleet
  - NET-NEW vendor: `Nguuma` (not in fleet elsewhere)
- **What we'd gain:** 1.0 GB disk

### Intake rationale

- **Intake age:** 36d ago (first-seen commit `d15d4a64`)
- **Mentioned in 4 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `hf.co/LiquidAI/LFM2.5-230M-GGUF:Q4_K_M` \ - `hf.co/LiquidAI/LFM2.5-350M-GGUF:Q4_K_M` \ - `hf.co/Nguuma/security-slm-unsloth-1.5b:latest` \ - `hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GG…
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## general (84)
    > - `hf.co/LiquidAI/LFM2.5-230M-GGUF:Q4_K_M` \ - `hf.co/LiquidAI/LFM2.5-350M-GGUF:Q4_K_M` \ - `hf.co/Nguuma/security-slm-unsloth-1.5b:latest` \ - `hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GG…
  - `portal_wiki/canonical/unit-model-catalog-hf-co-nguuma-security-slm-unsloth-1-5b-latest.md` — (no nearby heading)
    > id: unit-model-catalog-hf-co-nguuma-security-slm-unsloth-1-5b-latest \ kind: what \ title: "MODEL_CATALOG \u2014 `hf.co/Nguuma/security-slm-unsloth-1.5b:latest`" \ sources: \ - type: code \   path: co…

### Capability profile

- **Architecture:** unknown
- **Parameters:** 1.5B
- **Source:** huggingface (`Nguuma`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'hf.co/Nguuma/security-slm-unsloth-1.5b:latest'

### Fleet position

- **Bench workspaces routing here:** `bench-security-slm-1p5b`
- **Same-arch (`unknown`) production workspaces:** 0
- **Same-arch bench workspaces:** 0
- **Net-new signals (fleet has no other with these):**
  - vendor: `Nguuma` (not in fleet elsewhere)

### Diversity impact

- **Other `unknown` workspaces in fleet:** 0
- ⚠ **VENDOR LOSS**: `Nguuma` exits the fleet

### Card claims vs our slotting

- **Card source:** `https://huggingface.co/Nguuma/security-slm-unsloth-1.5b/raw/main/README.md` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > **Developed by:** Nguuma **License:** Apache-2.0 **Base model:** unsloth/deepseek-r1-distill-qwen-1.5b-unsloth-bnb-4bit **Quantized format:** GGUF Q4_K_M (~1.2 GB RAM at inference)
- **Card says model is NOT for:**
  - **Limitations

- Trained on domain-specific samples — a focused specialist, not a general security encyclopedia:** - CVE/CWE and MITRE ATT&CK coverage is curated, not exhaustive — verify against NVD and ATT&CK Navigator for production use - Ransomware IR playbooks are generalist starting points; adjust containment steps to your specific infrastructure - Regulator…
- **Deployment signals extracted:** reasoning-trace capability
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-security-slm-1p5b` | tools: none | emits_reasoning
    > security-slm-unsloth-1.5b (~1.1GB, Nguuma, DeepSeek-R1-distill base finetuned on security corpora). Multi-seat V2 bench candidate (2026-07-05) — red+blue+CoT+mcp-security seats. tools: [] deliberately: audited directly against Ollama, Modelfile TEMPLATE has zero {{ .Tools }} handling, so tool defs never reach the model regardless of what's attached here — it can only be scored on prose/CoT, not to…
- **Card vs slotting alignment ✓:**
  - card advertises reasoning; slot has `emits_reasoning: true`

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `reasoning-explicit` — Explicit reasoning / thinking traces
- **Recommended harness:** reasoning-aware persona matrix — capture and score the thinking traces, not just final answers
- **Prompt corpus:** multi-step reasoning tasks: math, logic, planning, code with edge cases
- **Metrics to capture (beyond raw TPS):**
  - task success rate WITH reasoning captured
  - reasoning coherence score
  - TPS separated by reasoning-on vs reasoning-off runs
  - trace length vs task complexity
- **Do NOT measure (would produce invalid signal for this capability):**
  - single-turn factual recall (doesn't exercise reasoning)
- **Workspace slot requirements for valid bench data:**
  - `emits_reasoning`: true — otherwise the harness sees a truncated model
  - `predict_limit`: high enough to fit thinking traces (8k+ typical)
- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):
  - `bench-security-slm-1p5b`: `predict_limit` needs to accommodate high enough to fit thinking traces (8k+ typical)


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest post-boundary evidence:** 2026-08-11
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:Q4_K_M` — 0.7 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - NET-NEW capability: Instruction-tuned
- **What we'd gain:** 0.7 GB disk

### Intake rationale

- **Intake age:** 46d ago (first-seen commit `84c15f78`)
- **Mentioned in 3 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `hf.co/Jackrong/Qwopus3.6-27B-v2-MTP-GGUF:Qwopus3.6-27B-v2-MTP-Q5_K_M.gguf` \ - `hf.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated-gguf-4bit:Q4_K_M` \ - `hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GG…
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## general (84)
    > - `hf.co/Jackrong/Qwopus3.6-27B-v2-MTP-GGUF:Qwopus3.6-27B-v2-MTP-Q5_K_M.gguf` \ - `hf.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated-gguf-4bit:Q4_K_M` \ - `hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GG…
  - `portal_wiki/canonical/unit-model-catalog-hf-co-liquidai-lfm2-5-1-2b-instruct-gguf-q4-k-m.md` — (no nearby heading)
    > id: unit-model-catalog-hf-co-liquidai-lfm2-5-1-2b-instruct-gguf-q4-k-m \ kind: what \ title: "MODEL_CATALOG \u2014 `hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:Q4_K_M`" \ sources: \ - type: code \   path…

### Capability profile

- **Architecture:** LFM2.5
- **Parameters:** 1.2B
- **Quantization:** Q4_K_M (mixed)
- **Source:** huggingface (`LiquidAI`)
- **Distinguishing features (from tag pattern):**
  - Instruction-tuned
- **Reversibility:** ollama pull 'hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:Q4_K_M'

### Fleet position

- **Bench workspaces routing here:** `bench-lfm-micro-1p2b`
- **Same-arch (`LFM2.5`) production workspaces:** 2
  - `hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:Q4_K_M-ctx8k` (via `auto-extract-uncensored`)
  - `lfm2.5:8b-ctx8k` (via `auto-music`)
- **Same-arch bench workspaces:** 4
  - `lfm2.5:8b` (via `bench-lfm25-8b`)
  - `hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:Q4_K_M` (via `bench-lfm25-8b-uncensored`)
  - `hf.co/LiquidAI/LFM2.5-230M-GGUF:Q4_K_M` (via `bench-lfm-micro-230m`)
  - `hf.co/LiquidAI/LFM2.5-350M-GGUF:Q4_K_M` (via `bench-lfm-micro-350m`)
- **Net-new signals (fleet has no other with these):**
  - capability: Instruction-tuned

### Diversity impact

- **Other `LFM2.5` workspaces in fleet:** 6
- **Other workspaces from `LiquidAI`:** 2

### Card claims vs our slotting

- **Card source:** `https://huggingface.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF/raw/main/README.md` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <div align="center"> <img src="https://cdn-uploads.huggingface.co/production/uploads/61b8e2ba285851687028d395/2b08LKpev0DNEk6DlnWkY.png" alt="Liquid AI" style="width: 100%; max-width: 100%; height: auto; display: inline-block; margin-bottom: 0.5em; margin-top: 0.5em;" /> <div style="display: flex; justify-content: center; gap: 0.5em;"> <a href="https://playground.liquid.ai/"><strong>Try LFM</strong></a> • <a href="https://docs.liquid.ai/lfm/getting-started/welcome"><strong>Docs</strong></a> • <a href="https://leap.liquid.ai/"><strong>LEAP</strong></a> • <a href="https://discord.com/invite/liqu
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-lfm-micro-1p2b` | tools: none
    > LFM2.5-1.2B-Instruct (Liquid AI, ~700MB Q4, reasoning-capable, 32K ctx). Micro model bench: evaluates as router + auto-extract / structured-output offload candidate. Bench-only. Run bench_router.py Round 4 and TPS probe.
- **Alignment:** no distinctive claim/slot mismatch detected — slot config appears consistent with card

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `general` — General / no specific capability advertised
- **Recommended harness:** bench_tps + portal5_persona_matrix (standard fleet path)
- **Prompt corpus:** default persona matrix across the model's target lane
- **Metrics to capture (beyond raw TPS):**
  - avg_tps vs the 20 t/s floor
  - quality_score vs same-lane incumbent


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest post-boundary evidence:** 2026-08-11
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `hf.co/LiquidAI/LFM2.5-350M-GGUF:Q4_K_M` — 0.2 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - nothing distinctive — arch/vendor/capability all remain represented after removal
- **What we'd gain:** 0.2 GB disk

### Intake rationale

- **Intake age:** 46d ago (first-seen commit `84c15f78`)
- **Mentioned in 3 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:Q4_K_M` \ - `hf.co/LiquidAI/LFM2.5-230M-GGUF:Q4_K_M` \ - `hf.co/LiquidAI/LFM2.5-350M-GGUF:Q4_K_M` \ - `hf.co/Nguuma/security-slm-unsloth-1.5b:latest` \ - `h…
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## general (84)
    > - `hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:Q4_K_M` \ - `hf.co/LiquidAI/LFM2.5-230M-GGUF:Q4_K_M` \ - `hf.co/LiquidAI/LFM2.5-350M-GGUF:Q4_K_M` \ - `hf.co/Nguuma/security-slm-unsloth-1.5b:latest` \ - `h…
  - `portal_wiki/canonical/unit-model-catalog-hf-co-liquidai-lfm2-5-350m-gguf-q4-k-m.md` — (no nearby heading)
    > id: unit-model-catalog-hf-co-liquidai-lfm2-5-350m-gguf-q4-k-m \ kind: what \ title: "MODEL_CATALOG \u2014 `hf.co/LiquidAI/LFM2.5-350M-GGUF:Q4_K_M`" \ sources: \ - type: code \   path: config/backends.…

### Capability profile

- **Architecture:** LFM2.5
- **Quantization:** Q4_K_M (mixed)
- **Source:** huggingface (`LiquidAI`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'hf.co/LiquidAI/LFM2.5-350M-GGUF:Q4_K_M'

### Fleet position

- **Bench workspaces routing here:** `bench-lfm-micro-350m`
- **Same-arch (`LFM2.5`) production workspaces:** 2
  - `hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:Q4_K_M-ctx8k` (via `auto-extract-uncensored`)
  - `lfm2.5:8b-ctx8k` (via `auto-music`)
- **Same-arch bench workspaces:** 4
  - `lfm2.5:8b` (via `bench-lfm25-8b`)
  - `hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:Q4_K_M` (via `bench-lfm25-8b-uncensored`)
  - `hf.co/LiquidAI/LFM2.5-230M-GGUF:Q4_K_M` (via `bench-lfm-micro-230m`)
  - `hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:Q4_K_M` (via `bench-lfm-micro-1p2b`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `LFM2.5` workspaces in fleet:** 6
- **Other workspaces from `LiquidAI`:** 2

### Card claims vs our slotting

- **Card source:** `https://huggingface.co/LiquidAI/LFM2.5-350M-GGUF/raw/main/README.md` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <div align="center"> <img src="https://cdn-uploads.huggingface.co/production/uploads/61b8e2ba285851687028d395/2b08LKpev0DNEk6DlnWkY.png" alt="Liquid AI" style="width: 100%; max-width: 100%; height: auto; display: inline-block; margin-bottom: 0.5em; margin-top: 0.5em;" /> <div style="display: flex; justify-content: center; gap: 0.5em; margin-bottom: 1em;"> <a href="https://playground.liquid.ai/"><strong>Try LFM</strong></a> • <a href="https://docs.liquid.ai/lfm/getting-started/welcome"><strong>Docs</strong></a> •
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-lfm-micro-350m` | tools: none
    > LFM2.5-350M (Liquid AI, ~200MB Q4, 313 t/s CPU decode, 128K ctx). Micro model bench: evaluates as router and daily-summarizer candidate. Bench-only — not a primary chat workspace. Run bench_router.py Round 4.
- **Alignment:** no distinctive claim/slot mismatch detected — slot config appears consistent with card

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `general` — General / no specific capability advertised
- **Recommended harness:** bench_tps + portal5_persona_matrix (standard fleet path)
- **Prompt corpus:** default persona matrix across the model's target lane
- **Metrics to capture (beyond raw TPS):**
  - avg_tps vs the 20 t/s floor
  - quality_score vs same-lane incumbent


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest post-boundary evidence:** 2026-08-11
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**


## `hf.co/LiquidAI/LFM2.5-230M-GGUF:Q4_K_M` — 0.1 GB

### At a glance

- **Hypothesis (non-authoritative):** `investigate-refresh` — no post-boundary evidence — stack changed, must re-bench before any decision
- **What we'd lose if removed:**
  - nothing distinctive — arch/vendor/capability all remain represented after removal
- **What we'd gain:** 0.1 GB disk

### Intake rationale

- **Intake age:** 46d ago (first-seen commit `84c15f78`)
- **Mentioned in 3 doc file(s):**
  - `docs/ADMIN_GUIDE.md` — ## general (84)
    > - `hf.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated-gguf-4bit:Q4_K_M` \ - `hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:Q4_K_M` \ - `hf.co/LiquidAI/LFM2.5-230M-GGUF:Q4_K_M` \ - `hf.co/LiquidAI/LFM2…
  - `portal_wiki/canonical/unit-fact-model-catalog.md` — ## general (84)
    > - `hf.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated-gguf-4bit:Q4_K_M` \ - `hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:Q4_K_M` \ - `hf.co/LiquidAI/LFM2.5-230M-GGUF:Q4_K_M` \ - `hf.co/LiquidAI/LFM2…
  - `portal_wiki/canonical/unit-model-catalog-hf-co-liquidai-lfm2-5-230m-gguf-q4-k-m.md` — (no nearby heading)
    > id: unit-model-catalog-hf-co-liquidai-lfm2-5-230m-gguf-q4-k-m \ kind: what \ title: "MODEL_CATALOG \u2014 `hf.co/LiquidAI/LFM2.5-230M-GGUF:Q4_K_M`" \ sources: \ - type: code \   path: config/backends.…

### Capability profile

- **Architecture:** LFM2.5
- **Quantization:** Q4_K_M (mixed)
- **Source:** huggingface (`LiquidAI`)
- **Distinguishing features:** none extractable from tag alone
- **Reversibility:** ollama pull 'hf.co/LiquidAI/LFM2.5-230M-GGUF:Q4_K_M'

### Fleet position

- **Bench workspaces routing here:** `bench-lfm-micro-230m`
- **Same-arch (`LFM2.5`) production workspaces:** 2
  - `hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:Q4_K_M-ctx8k` (via `auto-extract-uncensored`)
  - `lfm2.5:8b-ctx8k` (via `auto-music`)
- **Same-arch bench workspaces:** 4
  - `lfm2.5:8b` (via `bench-lfm25-8b`)
  - `hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:Q4_K_M` (via `bench-lfm25-8b-uncensored`)
  - `hf.co/LiquidAI/LFM2.5-350M-GGUF:Q4_K_M` (via `bench-lfm-micro-350m`)
  - `hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:Q4_K_M` (via `bench-lfm-micro-1p2b`)
- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet

### Diversity impact

- **Other `LFM2.5` workspaces in fleet:** 6
- **Other workspaces from `LiquidAI`:** 2

### Card claims vs our slotting

- **Card source:** `https://huggingface.co/LiquidAI/LFM2.5-230M-GGUF/raw/main/README.md` (fetched 2026-08-11)
- **Card description (first paragraph):**
  > <div align="center"> <img src="https://cdn-uploads.huggingface.co/production/uploads/61b8e2ba285851687028d395/2b08LKpev0DNEk6DlnWkY.png" alt="Liquid AI" style="width: 100%; max-width: 100%; height: auto; display: inline-block; margin-bottom: 0.5em; margin-top: 0.5em;" /> <div style="display: flex; justify-content: center; gap: 0.5em; margin-bottom: 1em;"> <a href="https://playground.liquid.ai/"><strong>Try LFM</strong></a> • <a href="https://docs.liquid.ai/lfm/getting-started/welcome"><strong>Docs</strong></a> •
- **What portal.yaml says we slotted it for** (1 bench workspace(s)):
  - `bench-lfm-micro-230m` | tools: none
    > LFM2.5-230M (Liquid AI, Apache 2.0, ~140MB Q4, hybrid LIV conv + GQA). Micro model bench: evaluates as pipeline-internal workspace classifier. NOT a primary chat model — bench target only. Use bench_router.py Round 4 to evaluate routing accuracy and security-refusal behaviour.
- **Alignment:** no distinctive claim/slot mismatch detected — slot config appears consistent with card

### Prescribed re-bench (capability-appropriate)

- **Re-bench REQUIRED** (no post-boundary evidence)
- **Capability category:** `general` — General / no specific capability advertised
- **Recommended harness:** bench_tps + portal5_persona_matrix (standard fleet path)
- **Prompt corpus:** default persona matrix across the model's target lane
- **Metrics to capture (beyond raw TPS):**
  - avg_tps vs the 20 t/s floor
  - quality_score vs same-lane incumbent


### Numeric evidence

- **Evidence rows mined:** 0 valid (post-boundary), 0 invalid (pre-boundary)
- **Newest post-boundary evidence:** 2026-08-11
- ⚠ **No post-boundary evidence — decision cannot rest on numbers. Re-bench required.**

