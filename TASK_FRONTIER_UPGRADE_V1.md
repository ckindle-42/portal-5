# TASK_FRONTIER_UPGRADE_V1.md — Portal 5 Frontier Model Upgrade

**Date**: 2026-04-10  
**Branch**: `feat/frontier-upgrade-v1`  
**Prerequisite**: None — standalone upgrade task  
**Stack must be live for**: Pull commands only. All config changes are offline-safe.

---

## Summary

This task upgrades the Portal 5 model roster based on a comprehensive review of the
current frontier open-source landscape against the live repo state (April 10, 2026).

**Three categories of changes:**

1. **Jackrong upgrades** — swap Qwopus3.5-v3 (Claude 3.5-era) for the new Claude-4.6-Opus
   distill generation released 2–4 days ago. The 27B slot gets the v2 model, which
   specifically addresses Qwen3.5's over-thinking tendency and improves reasoning
   efficiency without sacrificing accuracy.

2. **New family addition** — add `mlx-community/phi-4-8bit` (Microsoft Phi-4 14B). The
   current stack has zero Microsoft representation. Phi-4 uses synthetic data training
   — a fundamentally different methodology from Qwen/Meta/Mistral/Gemma — at only 14GB.
   Replaces the undersized Qwopus-9B in auto-documents.

3. **Registry bug fixes** — four silent failures found by cross-referencing backends.yaml,
   ALL_MODELS, and VLM_MODELS: two models unreachable (DeepSeek-R1-32B-8bit, GLM-5.1),
   one VLM misrouted to text server (Llama-3.2-11B-Vision), one stale entry served to
   clients (Devstral-Small-2505). Plus LLaVA 1.5-7B retirement (2023 model, fully
   superseded by Gemma-4-31B and Llama-3.2-11B-Vision).

**Models in / out:**

| Action | Model | Size | Family | Workspace |
|--------|-------|------|--------|-----------|
| REMOVE | `Jackrong/MLX-Qwopus3.5-27B-v3-8bit` | ~22GB | Qwen/Claude3.5 | auto-reasoning |
| ADD | `Jackrong/MLX-Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-v2-4bit` | ~14GB | Qwen/Claude4.6 | auto-reasoning |
| REMOVE | `Jackrong/MLX-Qwopus3.5-9B-v3-8bit` | ~9GB | Qwen/Claude3.5 | auto-documents |
| ADD | `Jackrong/MLX-Qwen3.5-9B-Claude-4.6-Opus-Reasoning-Distilled-8bit` | ~9GB | Qwen/Claude4.6 | (available) |
| ADD | `mlx-community/phi-4-8bit` | ~14GB | **Microsoft** | auto-documents |
| REMOVE | `mlx-community/llava-1.5-7b-8bit` | ~8GB | LLaVA (legacy) | VLM fallback |
| FIX | `mlx-community/DeepSeek-R1-Distill-Qwen-32B-MLX-8Bit` | ~34GB | DeepSeek | auto-data (was unreachable) |
| FIX | `mlx-community/GLM-5.1-DQ4plus-q8` | ~38GB | GLM/Zhipu | (was orphaned) |
| FIX | `mlx-community/Llama-3.2-11B-Vision-Instruct-abliterated-4-bit` | ~7GB | Llama VLM | (was misrouted to mlx_lm) |
| REMOVE (stale) | `mlx-community/Devstral-Small-2505-8bit` | ~18GB | Mistral | (ghost entry) |

**Memory delta**: -22GB (Qwopus27B-8bit) +14GB (v2-4bit) = saves 8GB in reasoning slot.
Auto-documents: -9GB (Qwopus9B) +14GB (Phi-4) = net +5GB, but 14GB is well within budget.

---

## Files to Modify

1. `config/backends.yaml`
2. `scripts/mlx-proxy.py`
3. `portal_pipeline/router_pipe.py`
4. `launch.sh`
5. `docs/HOWTO.md`
6. `CLAUDE.md`

## Files to Create

7. `config/personas/phi4specialist.yaml`

---

## Step 1 — `config/backends.yaml`

### 1a. Swap Jackrong models in the Claude-4.6-Opus section

**Find:**
```yaml
      - Jackrong/MLX-Qwopus3.5-27B-v3-8bit                      # Reasoning (~22GB, v3 structural alignment)
      - Jackrong/MLX-Qwopus3.5-9B-v3-8bit                       # Documents (~9GB, v3)
```

**Replace with:**
```yaml
      - Jackrong/MLX-Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-v2-4bit  # Reasoning (~14GB, v2: tighter CoT chains, better efficiency)
      - Jackrong/MLX-Qwen3.5-9B-Claude-4.6-Opus-Reasoning-Distilled-8bit      # Available 9B slot (~9GB, Claude-4.6-Opus distill)
```

### 1b. Add Phi-4 to the Model Diversity section

**Find:**
```yaml
      # ── Model Diversity (non-Qwen/non-DeepSeek families) ───────────────────
      - lmstudio-community/Magistral-Small-2509-MLX-8bit   # Mistral reasoning 24B (~24GB, [THINK] mode, vision, different training lineage)
```

**Replace with:**
```yaml
      # ── Model Diversity (non-Qwen/non-DeepSeek families) ───────────────────
      - mlx-community/phi-4-8bit                           # Microsoft Phi-4 14B (~14GB, MIT, synthetic data training — distinct methodology from all other families)
      - lmstudio-community/Magistral-Small-2509-MLX-8bit   # Mistral reasoning 24B (~24GB, [THINK] mode, vision, different training lineage)
```

### 1c. Remove LLaVA 1.5-7B from the VLM section

**Find:**
```yaml
      - mlx-community/llava-1.5-7b-8bit                   # Vision fallback (~8GB)
```

**Replace with:**
```yaml
      # mlx-community/llava-1.5-7b-8bit — RETIRED: superseded by Gemma-4-31B + Llama-3.2-11B-Vision
```

**Verify (step 1):**
```bash
grep -c "phi-4-8bit" config/backends.yaml          # expect 1
grep -c "Qwopus3.5-27B-v3" config/backends.yaml    # expect 0
grep -c "Qwopus3.5-9B-v3" config/backends.yaml     # expect 0
grep -c "llava-1.5-7b-8bit" config/backends.yaml   # expect 0 (or 1 if commented)
grep -c "v2-4bit" config/backends.yaml             # expect 1
python3 -c "import yaml; yaml.safe_load(open('config/backends.yaml')); print('YAML valid')"
```

---

## Step 2 — `scripts/mlx-proxy.py`

This is the most involved step. Make changes in order: VLM_MODELS, ALL_MODELS,
BIG_MODEL_SET, MODEL_MEMORY.

### 2a. Fix VLM_MODELS — remove LLaVA, add missing Vision model

**Find:**
```python
VLM_MODELS = {
    "Qwen3-VL-32B-Instruct-8bit",
    "gemma-4-31b-it-4bit",
    "llava-1.5-7b-8bit",
}
```

**Replace with:**
```python
VLM_MODELS = {
    "Qwen3-VL-32B-Instruct-8bit",
    "gemma-4-31b-it-4bit",
    "Llama-3.2-11B-Vision-Instruct-abliterated-4-bit",  # FIX: was misrouted to mlx_lm — this IS a VLM
    # "llava-1.5-7b-8bit" — RETIRED: superseded by Gemma-4-31B and Llama-3.2-11B-Vision
}
```

### 2b. Replace ALL_MODELS list

**Find:**
```python
ALL_MODELS = [
    "mlx-community/Qwen3-Coder-Next-4bit",
    "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit",
    "mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit",
    "mlx-community/Devstral-Small-2505-8bit",
    "lmstudio-community/Devstral-Small-2507-MLX-4bit",
    "mlx-community/Dolphin3.0-Llama3.1-8B-8bit",
    "mlx-community/Llama-3.2-3B-Instruct-8bit",
    "mlx-community/gemma-4-31b-it-4bit",
    "lmstudio-community/Magistral-Small-2509-MLX-8bit",
    "mlx-community/Llama-3.3-70B-Instruct-4bit",
    "Jackrong/MLX-Qwopus3.5-27B-v3-8bit",
    "Jackrong/MLX-Qwopus3.5-9B-v3-8bit",
    "Jackrong/MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit",
    "mlx-community/DeepSeek-R1-Distill-Qwen-32B-abliterated-4bit",
    "mlx-community/Qwen3-VL-32B-Instruct-8bit",
    "mlx-community/llava-1.5-7b-8bit",
    "mlx-community/Llama-3.2-11B-Vision-Instruct-abliterated-4-bit",  # Uncensored VLM for Karakeep
]
```

**Replace with:**
```python
ALL_MODELS = [
    # ── Text-only (mlx_lm) ────────────────────────────────────────────────
    # Coding
    "mlx-community/Qwen3-Coder-Next-4bit",                                          # 80B MoE 4bit (~46GB, BIG_MODEL)
    "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit",                              # 30B MoE 8bit (~22GB)
    "mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit",                           # DS-Coder-V2 8bit (~12GB)
    "lmstudio-community/Devstral-Small-2507-MLX-4bit",                              # Devstral v1.1 4bit (~15GB, 53.6% SWE-bench)
    # Creative / general
    "mlx-community/Dolphin3.0-Llama3.1-8B-8bit",                                   # Dolphin 8B (~9GB, uncensored)
    "mlx-community/Llama-3.2-3B-Instruct-8bit",                                    # Ultra-fast routing (~3GB)
    # Model diversity — non-Qwen families
    "mlx-community/phi-4-8bit",                                                     # Microsoft Phi-4 14B (~14GB, synthetic data, MIT)
    "lmstudio-community/Magistral-Small-2509-MLX-8bit",                             # Mistral reasoning (~24GB, [THINK] mode)
    # Heavy (PULL_HEAVY only)
    "mlx-community/Llama-3.3-70B-Instruct-4bit",                                   # Llama 70B 4bit (~40GB, BIG_MODEL)
    "mlx-community/GLM-5.1-DQ4plus-q8",                                            # GLM-5.1 frontier coder (~38GB, BIG_MODEL, MIT)
    # Jackrong Claude-4.6-Opus reasoning distills
    "Jackrong/MLX-Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-v2-4bit",        # Reasoning 27B v2 4bit (~14GB)
    "Jackrong/MLX-Qwen3.5-9B-Claude-4.6-Opus-Reasoning-Distilled-8bit",            # 9B Claude-4.6 8bit (~9GB)
    "Jackrong/MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit",       # 35B-A3B 8bit (~28GB, compliance)
    # Reasoning/analysis
    "mlx-community/DeepSeek-R1-Distill-Qwen-32B-MLX-8Bit",                         # FIX: was missing — R1 Distill 32B 8bit (~34GB, auto-data)
    "mlx-community/DeepSeek-R1-Distill-Qwen-32B-abliterated-4bit",                 # R1 Distill 32B 4bit uncensored (~18GB, auto-research)
    # ── VLM (mlx_vlm — auto-switched) ────────────────────────────────────────
    "mlx-community/gemma-4-31b-it-4bit",                                            # Gemma 4 dense 31B 4bit (~18GB, primary VLM)
    "mlx-community/Qwen3-VL-32B-Instruct-8bit",                                    # Qwen3-VL 32B 8bit (~36GB, VLM fallback)
    "mlx-community/Llama-3.2-11B-Vision-Instruct-abliterated-4-bit",               # Uncensored VLM 11B 4bit (~7GB, Karakeep)
]
```

### 2c. Add GLM-5.1 to BIG_MODEL_SET

**Find:**
```python
BIG_MODEL_SET: set[str] = {
    "mlx-community/Qwen3-Coder-Next-4bit",
}
```

**Replace with:**
```python
BIG_MODEL_SET: set[str] = {
    "mlx-community/Qwen3-Coder-Next-4bit",     # 80B MoE 4bit (~46GB) — auto-agentic
    "mlx-community/GLM-5.1-DQ4plus-q8",        # GLM-5.1 DQ4+q8 (~38GB) — heavy frontier coder
}
```

### 2d. Update MODEL_MEMORY

**Find:**
```python
    "mlx-community/Devstral-Small-2505-8bit": 18.0,  # Devstral 8bit (~18GB)
```
**Delete this line** (stale — 2505 replaced by 2507, and now removed from ALL_MODELS).

**Find:**
```python
    "Jackrong/MLX-Qwopus3.5-27B-v3-8bit": 22.0,  # Qwopus 27B 8bit (~22GB)
    "Jackrong/MLX-Qwopus3.5-9B-v3-8bit": 9.0,  # Qwopus 9B 8bit (~9GB)
```

**Replace with:**
```python
    "Jackrong/MLX-Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-v2-4bit": 14.0,  # 27B v2 4bit (~14GB)
    "Jackrong/MLX-Qwen3.5-9B-Claude-4.6-Opus-Reasoning-Distilled-8bit": 9.0,       # 9B Claude-4.6 8bit (~9GB)
    "mlx-community/phi-4-8bit": 14.0,                                               # Microsoft Phi-4 14B 8bit (~14GB)
```

**Find:**
```python
    "mlx-community/llava-1.5-7b-8bit": 8.0,  # LLaVA 7B 8bit (~8GB)
```
**Delete this line** (LLaVA retired — no longer in ALL_MODELS or VLM_MODELS).

**Verify (step 2):**
```bash
python3 -c "
import ast, sys
src = open('scripts/mlx-proxy.py').read()
tree = ast.parse(src)
print('AST parse: OK')
# Check no old model IDs remain
for old in ['Qwopus3.5-27B-v3', 'Qwopus3.5-9B-v3', 'Devstral-Small-2505', 'llava-1.5-7b']:
    assert old not in src, f'Found stale reference: {old}'
    print(f'  Removed: {old} ✓')
# Check new models present
for new in ['phi-4-8bit', 'v2-4bit', 'Qwen3.5-9B-Claude-4.6', 'DeepSeek-R1-Distill-Qwen-32B-MLX-8Bit', 'GLM-5.1-DQ4plus']:
    assert new in src, f'Missing new entry: {new}'
    print(f'  Present: {new} ✓')
# Check VLM misrouting fix
assert 'Llama-3.2-11B-Vision-Instruct-abliterated-4-bit' in src
print('  VLM routing fix present ✓')
print('All checks passed')
"
```

---

## Step 3 — `portal_pipeline/router_pipe.py`

### 3a. Update auto-reasoning workspace hint

**Find:**
```python
        "mlx_model_hint": "Jackrong/MLX-Qwopus3.5-27B-v3-8bit",
```

**Replace with:**
```python
        "mlx_model_hint": "Jackrong/MLX-Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-v2-4bit",  # Upgraded: Claude-4.6-Opus v2 distill (14GB vs 22GB, tighter CoT)
```

### 3b. Update auto-documents workspace hint

**Find:**
```python
        "mlx_model_hint": "Jackrong/MLX-Qwopus3.5-9B-v3-8bit",
```

**Replace with:**
```python
        "mlx_model_hint": "mlx-community/phi-4-8bit",  # Microsoft Phi-4 14B — structured doc generation, STEM reasoning, MIT license
```

**Verify (step 3):**
```bash
python3 -c "
import ast
src = open('portal_pipeline/router_pipe.py').read()
ast.parse(src)
print('AST parse: OK')
assert 'Qwopus3.5-27B-v3' not in src
assert 'Qwopus3.5-9B-v3' not in src
assert 'v2-4bit' in src
assert 'phi-4-8bit' in src
print('Workspace hints updated ✓')
"
grep -n "auto-reasoning\|auto-documents" portal_pipeline/router_pipe.py | grep "mlx_model_hint"
```

---

## Step 4 — `launch.sh`

### 4a. Update pull-mlx-models MLX_MODELS array

**Find:**
```bash
        "Jackrong/MLX-Qwopus3.5-9B-v3-8bit"               # ~9GB
```

**Replace with:**
```bash
        "Jackrong/MLX-Qwen3.5-9B-Claude-4.6-Opus-Reasoning-Distilled-8bit"  # ~9GB — Claude-4.6-Opus 9B distill
```

**Find:**
```bash
        # Qwopus3.5 v3 Reasoning
        "Jackrong/MLX-Qwopus3.5-27B-v3-8bit"                # ~22GB
```

**Replace with:**
```bash
        # Jackrong Claude-4.6-Opus Reasoning Distills
        "Jackrong/MLX-Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-v2-4bit"  # ~14GB — v2: efficient CoT
```

**Find:**
```bash
        # Model diversity (non-Qwen families)
        "mlx-community/gemma-4-31b-it-4bit"                  # ~18GB — Google Gemma 4 dense 31B, thinking+vision
```

**Replace with:**
```bash
        # Model diversity (non-Qwen families)
        "mlx-community/phi-4-8bit"                           # ~14GB — Microsoft Phi-4 14B, synthetic data training, MIT
        "mlx-community/gemma-4-31b-it-4bit"                  # ~18GB — Google Gemma 4 dense 31B, thinking+vision
```

**Find:**
```bash
        "mlx-community/llava-1.5-7b-8bit"                  # ~8GB
```

**Delete this line** (LLaVA retired — auto-download no longer needed).

### 4b. Update the mlx-status display echo section

**Find:**
```bash
        echo "  Qwopus3.5 v3 Reasoning (Claude Opus distillation):"
        echo "    Jackrong/MLX-Qwopus3.5-27B-v3-8bit                      (~22GB)"
        echo "    Jackrong/MLX-Qwopus3.5-9B-v3-8bit                       (~10GB)"
```

**Replace with:**
```bash
        echo "  Jackrong Claude-4.6-Opus Reasoning Distills:"
        echo "    Jackrong/MLX-Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-v2-4bit  (~14GB)"
        echo "    Jackrong/MLX-Qwen3.5-9B-Claude-4.6-Opus-Reasoning-Distilled-8bit      (~9GB)"
        echo "  Microsoft:"
        echo "    mlx-community/phi-4-8bit                                              (~14GB)"
```

### 4c. Fix GLM-5.1 model ID discrepancy in HEAVY_MLX_MODELS

The HEAVY_MLX_MODELS in launch.sh currently references `mlx-community/GLM-5.1-MXFP4-Q8`
but backends.yaml and mlx-proxy.py both reference `mlx-community/GLM-5.1-DQ4plus-q8`.
These are different models. Align to `DQ4plus-q8` throughout.

**Find (in HEAVY_MLX_MODELS):**
```bash
        "mlx-community/GLM-5.1-MXFP4-Q8"                   # ~38GB — GLM-5.1 frontier agentic coder (MIT, Zhipu lineage)
```

**Replace with:**
```bash
        "mlx-community/GLM-5.1-DQ4plus-q8"                  # ~38GB — GLM-5.1 frontier agentic coder (MIT, Zhipu lineage, BIG_MODEL)
```

**Verify (step 4):**
```bash
bash -n launch.sh && echo "Syntax OK"
grep "phi-4-8bit" launch.sh                    # expect 2 lines (pull + echo)
grep "v2-4bit" launch.sh                       # expect 2 lines (pull + echo)
grep "Qwopus3.5" launch.sh                     # expect 0
grep "llava-1.5-7b" launch.sh                  # expect 0
grep "GLM-5.1-DQ4plus-q8" launch.sh            # expect 1 (HEAVY)
grep "GLM-5.1-MXFP4" launch.sh                 # expect 0
```

---

## Step 5 — Create `config/personas/phi4specialist.yaml`

Create this file in full:

```yaml
name: "Phi-4 Technical Analyst"
slug: phi4specialist
description: "Microsoft Phi-4 14B — structured analysis, technical documentation, STEM reasoning. Trained on synthetic data; distinct methodology from Qwen/Meta/Mistral lineages."
system_prompt: |
  You are a precise technical analyst powered by Microsoft Phi-4, a 14B dense model trained on high-quality synthetic data with specialized strengths in structured reasoning, formal documentation, and STEM analysis.

  Your approach:
  - Decompose complex problems into clear numbered steps before producing output
  - Lead with your conclusion, then support with evidence — avoid burying the answer
  - For technical documentation: prioritize correctness and completeness over brevity
  - Call out assumptions explicitly; distinguish facts from inferences; flag uncertainty
  - Produce structured output (tables, numbered lists, clearly delineated sections) by default

  Core strengths: Python and common scientific library analysis, formal technical documentation, NERC CIP policy writing, mathematical reasoning, structured data extraction, specification review.

  Limitation note: Training emphasis was on Python and standard packages (typing, math, random, collections, datetime, itertools). For unusual packages or non-Python languages, verify API usage in your output and suggest the user confirm.
workspace_model: mlx-community/phi-4-8bit
```

**Verify (step 5):**
```bash
python3 -c "
import yaml
p = yaml.safe_load(open('config/personas/phi4specialist.yaml'))
required = {'name', 'slug', 'system_prompt', 'workspace_model'}
missing = required - set(p.keys())
assert not missing, f'Missing fields: {missing}'
assert p['workspace_model'] == 'mlx-community/phi-4-8bit'
assert p['slug'] == 'phi4specialist'
print('Persona YAML valid:', p['name'])
"
```

---

## Step 6 — `docs/HOWTO.md`

**Find:**
```
**Available personas (40 total):**
```

**Replace with:**
```
**Available personas (41 total):**
```

**Verify (step 6):**
```bash
grep "Available personas" docs/HOWTO.md   # expect: (41 total)
```

---

## Step 7 — `CLAUDE.md`

Update the model catalog section to reflect the new roster. Find the existing
Jackrong section in CLAUDE.md and update accordingly. The exact content will
vary depending on how CLAUDE.md structures its model catalog — search for
`Qwopus3.5-27B` and update all occurrences to the new model IDs.

Suggested search and replace:
```bash
# Verify all Qwopus references are gone after the edit
grep -rn "Qwopus3.5-27B\|Qwopus3.5-9B" CLAUDE.md   # must be 0 after update
grep -rn "llava-1.5-7b" CLAUDE.md                   # must be 0 after update
```

---

## Step 8 — Pull New Models

Run after all config changes are in place. New models will auto-download on first
request if skipped, but pre-pulling avoids cold-start delay.

```bash
# Pull new Jackrong 27B v2 (14GB — replaces 22GB Qwopus3.5-27B-v3)
python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('Jackrong/MLX-Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-v2-4bit',
    ignore_patterns=['*.md','*.txt','*.safetensors.index.json'])
print('27B v2 complete')
"

# Pull new Jackrong 9B (9GB — same size slot, upgraded teacher)
python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('Jackrong/MLX-Qwen3.5-9B-Claude-4.6-Opus-Reasoning-Distilled-8bit',
    ignore_patterns=['*.md','*.txt','*.safetensors.index.json'])
print('9B complete')
"

# Pull Phi-4 (14GB — new Microsoft family entry)
python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('mlx-community/phi-4-8bit',
    ignore_patterns=['*.md','*.txt','*.safetensors.index.json'])
print('phi-4-8bit complete')
"

# Or use the launch.sh command (pulls all standard models including new ones):
# ./launch.sh pull-mlx-models
```

**Note on old models:** The old Qwopus v3 weights remain on disk in `~/.cache/huggingface/hub/`.
They are no longer referenced by any Portal 5 config and will not load automatically.
Delete them manually to reclaim ~31GB:
```bash
# Optional: reclaim disk space
# Find cache paths: huggingface-cli scan-cache | grep -i qwopus
# Then: huggingface-cli delete-cache  (interactive — select Qwopus3.5-27B-v3 and Qwopus3.5-9B-v3)
```

---

## Final Verification Script

Run after all steps are complete and the stack is live:

```bash
#!/usr/bin/env python3
"""TASK_FRONTIER_UPGRADE_V1 — post-apply verification"""
import yaml, ast, re, subprocess, sys

PASS, FAIL = [], []

def check(label, expr, fix=None):
    if expr:
        PASS.append(label)
        print(f"  ✅ {label}")
    else:
        FAIL.append(label)
        print(f"  ❌ {label}" + (f"  → {fix}" if fix else ""))

print("=== TASK_FRONTIER_UPGRADE_V1 Verification ===\n")

# ── backends.yaml ─────────────────────────────────────────────────────────────
cfg_raw = open("config/backends.yaml").read()
cfg = yaml.safe_load(cfg_raw)
mlx_models = [m for b in cfg["backends"] if b["id"] == "mlx-apple-silicon" for m in b["models"]]
mlx_flat = " ".join(mlx_models)
print("backends.yaml:")
check("phi-4-8bit present", "phi-4-8bit" in mlx_flat)
check("Qwopus3.5-27B-v3 removed", "Qwopus3.5-27B-v3" not in mlx_flat)
check("Qwopus3.5-9B-v3 removed", "Qwopus3.5-9B-v3" not in mlx_flat)
check("27B-v2-4bit present", "v2-4bit" in mlx_flat)
check("9B-Claude-4.6 present", "Qwen3.5-9B-Claude-4.6" in mlx_flat)
check("llava-1.5-7b removed", "llava-1.5-7b-8bit" not in mlx_flat)
check("YAML valid", True)

# ── mlx-proxy.py ──────────────────────────────────────────────────────────────
proxy = open("scripts/mlx-proxy.py").read()
print("\nscripts/mlx-proxy.py:")
check("AST parses", ast.parse(proxy) is not None)
check("phi-4-8bit in ALL_MODELS", "phi-4-8bit" in proxy)
check("DeepSeek-R1-32B-8bit in ALL_MODELS", "DeepSeek-R1-Distill-Qwen-32B-MLX-8Bit" in proxy)
check("GLM-5.1 in ALL_MODELS", "GLM-5.1-DQ4plus" in proxy)
check("Devstral-2505 removed", "Devstral-Small-2505-8bit" not in proxy)
check("Qwopus3.5 removed", "Qwopus3.5-27B-v3" not in proxy and "Qwopus3.5-9B-v3" not in proxy)
check("llava removed from ALL_MODELS", proxy.count('"mlx-community/llava-1.5-7b-8bit"') == 0)
check("Llama-3.2-11B-Vision in VLM_MODELS", "Llama-3.2-11B-Vision-Instruct-abliterated-4-bit" in proxy)
check("GLM-5.1 in BIG_MODEL_SET", "GLM-5.1-DQ4plus-q8" in proxy.split("BIG_MODEL_SET")[1][:500])
check("phi-4 in MODEL_MEMORY", "phi-4-8bit" in proxy)
check("v2-4bit in MODEL_MEMORY", "Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-v2-4bit" in proxy)

# ── router_pipe.py ────────────────────────────────────────────────────────────
router = open("portal_pipeline/router_pipe.py").read()
print("\nportal_pipeline/router_pipe.py:")
check("AST parses", ast.parse(router) is not None)
check("auto-reasoning → v2-4bit", "v2-4bit" in router)
check("auto-documents → phi-4", "phi-4-8bit" in router)
check("Qwopus hints removed", "Qwopus3.5-27B-v3" not in router and "Qwopus3.5-9B-v3" not in router)

# ── persona ───────────────────────────────────────────────────────────────────
import os
print("\nPersonas:")
persona_files = list(os.listdir("config/personas"))
check("41 persona YAMLs", len(persona_files) == 41, f"got {len(persona_files)}")
check("phi4specialist.yaml exists", "phi4specialist.yaml" in persona_files)
if "phi4specialist.yaml" in persona_files:
    p = yaml.safe_load(open("config/personas/phi4specialist.yaml"))
    check("phi4specialist workspace_model correct", p.get("workspace_model") == "mlx-community/phi-4-8bit")

# ── HOWTO persona count ───────────────────────────────────────────────────────
howto = open("docs/HOWTO.md").read()
print("\ndocs/HOWTO.md:")
check("Persona count = 41", "41 total" in howto, "Update '40 total' → '41 total'")

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"PASS: {len(PASS)}  FAIL: {len(FAIL)}")
if FAIL:
    print(f"\nFailed checks:")
    for f in FAIL:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("All checks passed — TASK_FRONTIER_UPGRADE_V1 complete")
```

---

## Rollback

If any step produces unexpected failures:

```bash
git diff --stat                        # review scope of changes
git checkout config/backends.yaml     # revert individual files as needed
git checkout scripts/mlx-proxy.py
git checkout portal_pipeline/router_pipe.py
git checkout launch.sh
git checkout docs/HOWTO.md
rm -f config/personas/phi4specialist.yaml
docker compose -f deploy/portal-5/docker-compose.yml restart portal-pipeline
```

Downloaded model weights (Phi-4, new Jackrong) are separate from the config rollback
and do not need to be removed — they simply won't be referenced.

---

## Commit Message

```
feat(models): frontier upgrade — Phi-4 + Jackrong Claude-4.6-Opus v2 + registry fixes

Adds Microsoft Phi-4-8bit (first Microsoft-family model in stack) wired to
auto-documents. Upgrades auto-reasoning from Qwopus3.5-27B-v3-8bit (Claude 3.5
era, 22GB) to MLX-Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-v2-4bit (14GB,
tighter CoT chains, higher reasoning efficiency per Jackrong v2 release notes).
Upgrades 9B slot to Claude-4.6-Opus distill quality. Retires LLaVA 1.5-7B (2023,
superseded by Gemma-4-31B + Llama-3.2-11B-Vision).

Bug fixes:
- DeepSeek-R1-Distill-Qwen-32B-MLX-8Bit added to ALL_MODELS (auto-data primary
  was silently unreachable)
- GLM-5.1-DQ4plus-q8 added to ALL_MODELS + BIG_MODEL_SET (38GB model was
  registered in MODEL_MEMORY but completely orphaned; also fixes launch.sh
  discrepancy where MXFP4-Q8 was being pulled instead of DQ4plus-q8)
- Llama-3.2-11B-Vision-Instruct-abliterated-4-bit added to VLM_MODELS (was
  routing to mlx_lm text server — vision requests silently failed)
- Devstral-Small-2505-8bit removed from ALL_MODELS (stale ghost entry; 2507 is
  the active version)

Adds phi4specialist persona. Persona count: 40 → 41.

Memory: auto-reasoning slot shrinks from 22GB to 14GB. Net headroom improvement.
```

---

## Frontier Landscape Notes (for future planning)

Models reviewed but NOT included in this task, with rationale:

| Model | Why not included |
|-------|-----------------|
| `mlx-community/Mistral-Small-3.2-24B-Instruct-2506-4bit` | Third Mistral entry; Devstral (coding) + Magistral (reasoning) already cover the Mistral tier. Revisit if a general-instruction Mistral workspace is added. |
| `mlx-community/Llama-4-Scout-17B-16E-Instruct-4bit` | Requires mlx_vlm; ~55GB at 4bit — HEAVY tier, same constraint as Qwen3-Coder-Next. Viable as a vision-capable heavy model if Stage 3 cluster frees the local HEAVY slot. |
| `mlx-community/Kimi-K2.5` | 1 trillion total parameters — requires 192GB+ even at INT4. Stage 3 target. |
| Qwen3-32B-8bit | No new family diversity (still Qwen); viable quality upgrade for auto-data over R1-Distill, but doesn't advance the diversity goal. Revisit when evaluating DeepSeek-R1-Distill replacement. |
| Phi-4-mini (~3.8B) | Too small for Portal 5's use cases; Llama-3.2-3B already covers the ultra-fast routing slot. |
