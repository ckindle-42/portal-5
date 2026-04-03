# TASK: Migrate Qwen3-Coder-Next from 8-bit to 4-bit MLX Quantization
**Scope:** `scripts/mlx-proxy.py`, `config/backends.yaml`, `portal_pipeline/router_pipe.py`,
`launch.sh`, `CLAUDE.md`, `docs/HOWTO.md`, `tests/unit/test_pipeline.py`
**Safe to skip:** `config/personas/*.yaml` — persona files reference the Ollama tag
`qwen3-coder-next:30b-q5` only, not the MLX model ID. No changes needed there.

---

## Why This Change Is Necessary

Qwen3-Coder-Next is an **80B parameter MoE** model (3B active parameters per forward
pass). Despite the small active-parameter count, the full weight set must fit in unified
memory at load time. Memory requirements are:

| Quantization | Weight size | Fits 64GB M4 Pro? |
|---|---|---|
| 8-bit (`mlx-community/Qwen3-Coder-Next-8bit`) | ~85GB | ❌ No — forces SSD swap |
| 4-bit (`mlx-community/Qwen3-Coder-Next-4bit`) | ~46GB | ✅ Yes — ~18GB headroom |

The project's internal docs (`CLAUDE.md`, `backends.yaml`, `HOWTO.md`) all document
`~32GB` for the 8-bit variant. That figure is wrong — it belongs to the **30B model**
(`Qwen3-Coder-30B-A3B-Instruct-8bit`), not the 80B Coder-Next. The confusion arose
because both models share the `Qwen3-Coder` lineage and the `-Next` suffix was
interpreted as a minor revision rather than a different scale class.

The 4-bit quant (`mlx-community/Qwen3-Coder-Next-4bit`) was produced using mlx-lm
0.30.5 — the same version as the 8-bit, so no compatibility change is introduced.
The mlx-lm version pin at `<0.31` in `launch.sh` remains correct and must not change.

---

## Safety Checkpoint Before Starting

```bash
# 1. Tag the current state
git tag pre-4bit-migration

# 2. Confirm working tree is clean
git status
```

---

## Changes Required

### 1. `scripts/mlx-proxy.py`

**One line change — the model ID in `ALL_MODELS`:**

```python
# BEFORE (line 35):
"mlx-community/Qwen3-Coder-Next-8bit",

# AFTER:
"mlx-community/Qwen3-Coder-Next-4bit",
```

No other changes to this file. Do NOT add `--max-tokens` or `--kv-bits` flags to
`start_server()` — those are separate operational decisions not part of this task.

---

### 2. `config/backends.yaml`

**Line 24 — model ID and comment:**

```yaml
# BEFORE:
- mlx-community/Qwen3-Coder-Next-8bit              # Primary coder: 80B MoE (~32GB, 256k ctx)

# AFTER:
- mlx-community/Qwen3-Coder-Next-4bit              # Primary coder: 80B MoE, 3B active (~46GB, 256k ctx)
```

**Lines 22-23 — header comment block:**

```yaml
# BEFORE:
# 8bit quants used on 64GB M4 Mac — one model at a time, max quality.
# 64GB budget: 8bit model + ComfyUI (~18GB) + Ollama 3B (~3GB) + OS (~8GB) ≈ 55GB

# AFTER:
# 8bit quants used on 64GB M4 Mac — one model at a time, max quality.
# Exception: Qwen3-Coder-Next uses 4bit (~46GB) — 80B total params, 8bit would require ~85GB.
# 64GB budget: Coder-Next-4bit (~46GB) + Ollama 3B (~3GB) + OS (~8GB) ≈ 57GB (no ComfyUI concurrent)
```

---

### 3. `portal_pipeline/router_pipe.py`

**Line 388 — `mlx_model_hint` for `auto-coding` workspace:**

```python
# BEFORE:
"mlx_model_hint": "mlx-community/Qwen3-Coder-Next-8bit",

# AFTER:
"mlx_model_hint": "mlx-community/Qwen3-Coder-Next-4bit",
```

**Line 759 — inline comment (cosmetic):**

```python
# BEFORE:
4. Coding keywords → auto-coding (Qwen3-Coder-Next via MLX)

# AFTER:
4. Coding keywords → auto-coding (Qwen3-Coder-Next-4bit via MLX)
```

---

### 4. `launch.sh`

Four locations need updating. Use exact string matching — do not reformat surrounding
lines.

**Location A — line 1963, `mlx-status` model listing:**

```bash
# BEFORE:
echo "    mlx-community/Qwen3-Coder-Next-8bit              (~32GB — primary coder)"

# AFTER:
echo "    mlx-community/Qwen3-Coder-Next-4bit              (~46GB — primary coder, 80B MoE)"
```

**Location B — line 2130, `MLX_MODELS` array:**

```bash
# BEFORE:
"mlx-community/Qwen3-Coder-Next-8bit"              # ~32GB active

# AFTER:
"mlx-community/Qwen3-Coder-Next-4bit"              # ~46GB — 80B MoE, 4bit required (8bit ~85GB exceeds 64GB)
```

**Location C — line 2207, end-of-section usage hint:**

```bash
# BEFORE:
echo "  MLX_MODEL=mlx-community/Qwen3-Coder-Next-8bit ~/.portal5/mlx/start.sh"

# AFTER:
echo "  MLX_MODEL=mlx-community/Qwen3-Coder-Next-4bit ~/.portal5/mlx/start.sh"
```

**Location D — line 1856-1857, mlx-lm pin comment and echo (leave the pin itself
untouched — `mlx-lm<0.31` is correct):**

No change needed here. The pin comment already explains itself. Do not touch the
`pip3 install "mlx-lm<0.31"` line.

---

### 5. `CLAUDE.md`

Three locations:

**Memory table (line 258):**

```markdown
# BEFORE:
| `mlx-community/Qwen3-Coder-Next-8bit` | ~32GB | mlx_lm | ComfyUI (CPU) + Ollama general (3B) |

# AFTER:
| `mlx-community/Qwen3-Coder-Next-4bit` | ~46GB | mlx_lm | No concurrent ComfyUI — 46GB + 8GB OS = 54GB |
```

**Memory budget example (line 272):**

```markdown
# BEFORE:
**64GB systems**: Qwen3-Coder-Next (~32GB) + Wan2.2 (~18GB) + Ollama (~5GB) = 55GB total — feasible but tight.

# AFTER:
**64GB systems**: Qwen3-Coder-Next-4bit (~46GB) + Ollama (~5GB) + OS (~8GB) = 59GB — no concurrent ComfyUI/Wan2.2.
```

**Memory table by tier (line 287):**

```markdown
# BEFORE:
| 64GB | Qwen3-Coder-Next (~32GB) | ComfyUI Wan2.2 + Ollama general |

# AFTER:
| 64GB | Qwen3-Coder-Next-4bit (~46GB) | Ollama general only — unload before ComfyUI |
```

**Workspace routing table (line 372):**

```markdown
# BEFORE:
| `auto-coding` | mlx → coding → general | mlx-community/Qwen3-Coder-Next-8bit |

# AFTER:
| `auto-coding` | mlx → coding → general | mlx-community/Qwen3-Coder-Next-4bit |
```

---

### 6. `docs/HOWTO.md`

**Model reference table (line 885):**

```markdown
# BEFORE:
| `mlx-community/Qwen3-Coder-Next-8bit` | ~32GB | mlx_lm | Code generation |

# AFTER:
| `mlx-community/Qwen3-Coder-Next-4bit` | ~46GB | mlx_lm | Code generation (80B MoE, 4bit required on 64GB) |
```

**Memory budget example (line 904):**

```markdown
# BEFORE:
Qwen3-Coder-Next (~18GB) + Wan2.2 video (~18GB) + Ollama general (~5GB) = 41GB ✓

# AFTER:
Qwen3-Coder-Next-4bit (~46GB) + Ollama general (~5GB) + OS (~8GB) = 59GB — run without ComfyUI/Wan2.2 ✓
```

**Inline reference (line 86):**

```markdown
# BEFORE:
3. The pipeline routes to `mlx-community/Qwen3-Coder-Next-8bit` via MLX (or Ollama fallback)

# AFTER:
3. The pipeline routes to `mlx-community/Qwen3-Coder-Next-4bit` via MLX (or Ollama fallback)
```

---

### 7. `tests/unit/test_pipeline.py`

Four locations — all are string assertions that will fail if the model ID is not
updated to match.

**Line 430 — string in `assertIn` check:**

```python
# BEFORE:
"Qwen3-Coder-Next-8bit",

# AFTER:
"Qwen3-Coder-Next-4bit",
```

**Line 656 — `models` list in mock:**

```python
# BEFORE:
models=["mlx-community/Qwen3-Coder-Next-8bit"],

# AFTER:
models=["mlx-community/Qwen3-Coder-Next-4bit"],
```

**Line 671 — assertion error message:**

```python
# BEFORE:
"MLX primary model (Qwen3-Coder-Next-8bit) not in mlx backend"

# AFTER:
"MLX primary model (Qwen3-Coder-Next-4bit) not in mlx backend"
```

**Line 718 — content assertion:**

```python
# BEFORE:
assert "Qwen3-Coder-Next-8bit" in content

# AFTER:
assert "Qwen3-Coder-Next-4bit" in content
```

---

## Verification Steps

After all changes are applied:

```bash
# 1. Confirm no stale 8bit references remain for Coder-Next specifically
grep -r "Qwen3-Coder-Next-8bit" . \
  --include="*.py" --include="*.yaml" --include="*.yml" \
  --include="*.sh" --include="*.md" --include="*.json" \
  | grep -v ".git"
# Expected output: empty — zero matches

# 2. Confirm 4bit references landed in all the right places
grep -r "Qwen3-Coder-Next-4bit" . \
  --include="*.py" --include="*.yaml" --include="*.sh" --include="*.md" \
  | grep -v ".git"
# Expected: hits in mlx-proxy.py, backends.yaml, router_pipe.py,
#           launch.sh, CLAUDE.md, HOWTO.md, test_pipeline.py

# 3. Run the unit tests
python3 -m pytest tests/unit/test_pipeline.py -v -k "mlx or coding or Coder"

# 4. Syntax-check the proxy script
python3 -m py_compile scripts/mlx-proxy.py && echo "syntax OK"

# 5. Validate backends.yaml is still valid YAML
python3 -c "import yaml; yaml.safe_load(open('config/backends.yaml'))" && echo "YAML OK"
```

---

## What This Does NOT Change

- `launch.sh` mlx-lm version pin (`mlx-lm<0.31`) — correct, leave as-is
- `scripts/mlx-watchdog.py` — no model IDs referenced, no change needed
- `config/personas/*.yaml` — reference `qwen3-coder-next:30b-q5` (Ollama tag), not the MLX ID
- `VLM_MODELS` set in `mlx-proxy.py` — Coder-Next is text-only, already correctly absent
- The mlx-lm / mlx-vlm server routing logic — no architecture changes
- Any Ollama model tags — Ollama and MLX are separate backends

---

## Model Swap on Disk

The code changes above are necessary but not sufficient. The actual weights on disk
must be swapped before the proxy can serve the 4-bit model. This section covers the
correct order of operations.

The HuggingFace cache stores MLX models at:
```
~/.cache/huggingface/hub/models--mlx-community--Qwen3-Coder-Next-8bit/
~/.cache/huggingface/hub/models--mlx-community--Qwen3-Coder-Next-4bit/   ← does not exist yet
```

**Do not delete before pulling.** Delete after the pull is confirmed complete so
there is always a working model available if the pull fails partway through.

### Step 1 — Stop the MLX proxy

The proxy must not be running while the model weights are being manipulated. The
launchd service will attempt to restart the proxy on crash — stop it cleanly first.

```bash
launchctl stop com.portal5.mlx-proxy 2>/dev/null || true
launchctl unload ~/Library/LaunchAgents/com.portal5.mlx-proxy.plist 2>/dev/null || true
pkill -f "mlx-proxy" 2>/dev/null || true
pkill -f "mlx_lm.server" 2>/dev/null || true

# Confirm ports are clear
lsof -i :8081 -i :18081 -i :18082 2>/dev/null | grep LISTEN || echo "Ports clear"
```

### Step 2 — Check available disk space

The 4-bit weights are ~46GB. The 8-bit weights are ~85GB. You need ~46GB free
before pulling. Do not delete the 8-bit until the 4-bit pull succeeds.

```bash
# Free space on the volume where ~/.cache lives
df -h ~

# Current size of the 8-bit cache entry
du -sh ~/.cache/huggingface/hub/models--mlx-community--Qwen3-Coder-Next-8bit 2>/dev/null \
  || echo "8-bit not cached locally"
```

### Step 3 — Pull the 4-bit model

Uses the same `snapshot_download` pattern the project already uses in `pull-mlx-models`.
Idempotent — safe to re-run if interrupted; resumes from where it left off.

```bash
python3 -c "
import warnings; warnings.filterwarnings('ignore')
from huggingface_hub import snapshot_download
print('Pulling mlx-community/Qwen3-Coder-Next-4bit (~46GB)...')
path = snapshot_download(
    'mlx-community/Qwen3-Coder-Next-4bit',
    ignore_patterns=['*.md', '*.txt', '*.safetensors.index.json']
)
print(f'Downloaded to: {path}')
"
```

Do not proceed to Step 4 until this exits cleanly with a path printed.

### Step 4 — Verify the 4-bit download is complete

```bash
# Weight shards must be present
find ~/.cache/huggingface/hub/models--mlx-community--Qwen3-Coder-Next-4bit \
  -name "*.safetensors" | wc -l
# Expected: > 0

# Quick load test — confirms mlx_lm can open the weights
# Takes ~60s; close other memory-heavy apps first
python3 -c "
from mlx_lm import load
print('Loading 4-bit model for verification...')
model, tokenizer = load('mlx-community/Qwen3-Coder-Next-4bit')
print('Load OK — model is valid')
del model
"
```

### Step 5 — Delete the 8-bit weights

Only run this after Step 4 confirms a clean load.

```bash
python3 -c "
from huggingface_hub import scan_cache_dir
cache = scan_cache_dir()
for repo in cache.repos:
    if 'Qwen3-Coder-Next-8bit' in repo.repo_id:
        print(f'Found: {repo.repo_id}  Size: {repo.size_on_disk_str}')
        revisions = [r.commit_hash for r in repo.revisions]
        strategy = cache.delete_revisions(*revisions)
        print(f'Will free: {strategy.expected_freed_size_str}')
        strategy.execute()
        print('Deleted.')
        break
else:
    print('8-bit not found in cache — nothing to delete')
"
```

Or direct filesystem delete if preferred:

```bash
rm -rf ~/.cache/huggingface/hub/models--mlx-community--Qwen3-Coder-Next-8bit
```

### Step 6 — Restart the proxy

```bash
launchctl load ~/Library/LaunchAgents/com.portal5.mlx-proxy.plist
launchctl start com.portal5.mlx-proxy
sleep 5
curl -s http://localhost:8081/health | python3 -m json.tool
# Expected: {"status": "ok", "active_server": "none"}
```

### Step 7 — Smoke test

```bash
# First request takes ~60-90s while 46GB loads into unified memory
curl -s -X POST http://localhost:8081/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mlx-community/Qwen3-Coder-Next-4bit",
    "messages": [{"role": "user", "content": "Write a one-line Python hello world."}],
    "max_tokens": 50
  }' | python3 -m json.tool | grep -A2 '"content"'
# Expected: a Python print statement in the content field
```

---

## Rollback

```bash
git checkout pre-4bit-migration -- \
  scripts/mlx-proxy.py \
  config/backends.yaml \
  portal_pipeline/router_pipe.py \
  launch.sh \
  CLAUDE.md \
  docs/HOWTO.md \
  tests/unit/test_pipeline.py
```
