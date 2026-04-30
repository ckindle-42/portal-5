# TASK_LAGUNA_MLX_UPGRADE_V1.md
# Portal 5 — Add Laguna-XS.2 + MLX Upgrade Track
# Execute via: Claude Code reading this file
# Scope: additive only — no existing entries removed or replaced

## Context

Laguna-XS.2 is a new agentic coding MoE from Poolside AI (released 2026-04-28):
- 33B total / 3B active parameters, Apache 2.0 license
- mlx-community/Laguna-XS.2-4bit: ~18.8 GB MLX footprint
- 68.2% SWE-bench Verified — strongest new coding model this cycle
- Poolside lineage: first model in the stack NOT from Alibaba/Meta/Google/NVIDIA/Mistral/Microsoft
- Native reasoning (interleaved thinking between tool calls), native tool calling
- Converted via mlx-lm 0.31.3 — requires mlx-lm >= 0.31.3 to serve

MLX is actively developed. The install-mlx path currently caps at mlx-audio's mlx-lm pin.
This task also upgrades the install path to pull latest mlx-lm explicitly after mlx-vlm.

## Pre-flight checks (run before any edits)

```bash
# Confirm current mlx-lm version on system (expected: 0.31.x)
python3 -c "import mlx_lm; print(mlx_lm.__version__)" 2>/dev/null || echo "not installed"

# Confirm current mlx-vlm version on system
python3 -c "import mlx_vlm; print(mlx_vlm.__version__)" 2>/dev/null || echo "not installed"

# Verify workspace consistency baseline (must pass before and after)
python3 -c "
import yaml
import sys
sys.path.insert(0, '.')
from portal_pipeline.router.workspaces import WORKSPACES
cfg = yaml.safe_load(open('config/backends.yaml'))
pipe_ids = set(WORKSPACES.keys())
yaml_ids = set(cfg['workspace_routing'].keys())
assert pipe_ids == yaml_ids, f'Mismatch: pipe={pipe_ids - yaml_ids} yaml={yaml_ids - pipe_ids}'
print('PASS: workspace IDs consistent')
"

# Count current persona files
ls config/personas/*.yaml | wc -l
```

---

## Task 1 — Add Laguna-XS.2-4bit to config/backends.yaml

### File: `config/backends.yaml`

#### 1a. Add model entry to mlx_models list

Insert the following block AFTER the `lmstudio-community/Devstral-Small-2507-MLX-4bit` entry and BEFORE the `# ── GLM-4.7` section. The exact insertion anchor is:

```yaml
      - id: lmstudio-community/Devstral-Small-2507-MLX-4bit
        memory_gb: 15
        big_model: false
        is_vlm: false
        supports_tools: true
        notes: "Devstral v1.1 4bit (~15GB, 53.6% SWE-bench) — bench-devstral pin, displaced by GLM-4.7-Flash for auto-coding"
      # ── GLM-4.7 (Z.AI lineage — escapes Qwen+Gemma duopoly) ───────────────────
```

Insert BETWEEN those two blocks:

```yaml
      - id: mlx-community/Laguna-XS.2-4bit
        memory_gb: 19
        big_model: false
        is_vlm: false
        supports_tools: true
        notes: "Laguna XS.2 33B-A3B MoE 4bit (~18.8GB) — Poolside AI lineage (first non-Alibaba/Meta/Google/NVIDIA/Mistral coder in stack). 68.2% SWE-bench Verified. Native interleaved reasoning + tool calling. SWA+FP8 KV cache. Apache 2.0. Converted mlx-lm 0.31.3."
```

#### 1b. Add bench-laguna to workspace_routing

In the `workspace_routing:` block, after the `bench-gptoss` line, add:

```yaml
  bench-laguna:             [mlx, coding, general]   # Laguna-XS.2-4bit (Poolside — new lineage)
```

### Verification
```bash
python3 -c "
import yaml
cfg = yaml.safe_load(open('config/backends.yaml'))
ids = [m['id'] for m in cfg['backends'][0]['mlx_models']]
assert 'mlx-community/Laguna-XS.2-4bit' in ids, 'FAIL: model not found in mlx_models'
assert 'bench-laguna' in cfg['workspace_routing'], 'FAIL: bench-laguna not in workspace_routing'
print('PASS: backends.yaml updated correctly')
"
```

---

## Task 2 — Add bench-laguna workspace to portal_pipeline/router/workspaces.py

### File: `portal_pipeline/router/workspaces.py`

In the `WORKSPACES` dict, after the `"bench-gptoss"` entry (just before the closing `}`), add:

```python
    "bench-laguna": {
        "name": "🔬 Bench · Laguna-XS.2 (Poolside)",
        "description": "Benchmark: Laguna-XS.2-4bit (MLX, Poolside AI, 33B-A3B MoE, ~18.8GB, 68.2% SWE-bench Verified, interleaved reasoning)",
        "model_hint": "glm-4.7-flash:q4_k_m",
        "mlx_model_hint": "mlx-community/Laguna-XS.2-4bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "tools": [],
    },
```

Note: `model_hint` is the Ollama fallback. `mlx_only: True` means no results are recorded if MLX cannot load the target model.

### Verification
```bash
python3 -c "
import sys; sys.path.insert(0, '.')
from portal_pipeline.router.workspaces import WORKSPACES
assert 'bench-laguna' in WORKSPACES, 'FAIL: bench-laguna not in WORKSPACES'
ws = WORKSPACES['bench-laguna']
assert ws['mlx_model_hint'] == 'mlx-community/Laguna-XS.2-4bit'
assert ws['mlx_only'] == True
print('PASS: WORKSPACES updated correctly')
"
```

---

## Task 3 — Create config/personas/bench_laguna.yaml

### File: `config/personas/bench_laguna.yaml` (NEW FILE)

```yaml
name: 🔬 Bench · Laguna-XS.2 (Poolside)
slug: bench-laguna
category: benchmark
workspace_model: bench-laguna
# Routes to: mlx-community/Laguna-XS.2-4bit (MLX primary, Poolside AI lineage, ~18.8GB)
# Fallback: glm-4.7-flash:q4_k_m (Ollama GGUF — different model family, for graceful degradation only)
# BENCHMARK NOTE: Verify MLX loaded Laguna-XS.2-4bit before recording results.
# Check: ./launch.sh logs | grep "Switching to model"
# Laguna has native interleaved reasoning — <think> blocks appear between tool calls.
# enable_thinking is on by default; set enable_thinking: false in request to suppress.
system_prompt: |
  You are a creative coder who builds playable, visual, and interactive things
  in the browser. Your default output is a complete, working, single-file HTML
  deliverable. You ship first and explain after.

  HARD CONSTRAINTS (never violate):
  - Never ask for a framework, toolchain, or dependency preference — vanilla JS
    and Canvas are your default. Use a CDN-loaded library only if it meaningfully
    reduces complexity (e.g. Three.js for 3D, Tone.js for audio).
  - Never produce incomplete code. If the scope is large, build a smaller but
    fully-working version and say so — do not leave stubs, TODOs, or placeholders.
  - Do not lecture about accessibility, bundle size, or production architecture
    unless the user asks. These are toys and experiments, not enterprise apps.
  - Never start with clarifying questions for requests that are self-evident
    (e.g. "make a snake game", "visualize a sorting algorithm"). Build it.

  EXPERTISE:
  - Browser games: Canvas 2D, game loops, collision detection, particle systems,
    sprite animation, level progression, score/lives systems
  - Generative art: noise fields, L-systems, cellular automata, reaction-diffusion,
    Lissajous curves, recursive geometry
  - Simulations: physics (Verlet, simple gravity/bounce), flocking (boids), fluid
    approximations, cellular automata (Conway, Brian's Brain)
  - Audio/visual: Web Audio API for synth/SFX, CSS animations, SVG drawing,
    requestAnimationFrame loops
  - Data visualization: SVG charts, Canvas plots, animated transitions without a
    framework dependency
  - Interactive demos: sliders/controls that update in real-time, drag-and-drop,
    touch support for mobile

  DELIVERY APPROACH:
  - Default: one self-contained HTML file, no build step, opens in browser
  - For larger projects: one HTML file per major component, clearly named
  - Always include keyboard controls where relevant, and list them in the UI
  - Make it look good: dark background, clean typography, subtle glow/shadow effects
    give the retro-arcade aesthetic that matches the medium
  - After delivering: one short paragraph of craft notes — what made it interesting,
    what could be extended, any non-obvious technique used

  WHEN TO ASK:
  - Ask only when the request is genuinely ambiguous about *what to build*
    (e.g. "make something cool" with no other context).
  - Never ask about tech stack, deployment, or code style.

  Build the most interesting version of the idea, not the safest one.
tags:
  - benchmark
  - creative
  - games
  - canvas
  - javascript
```

### Verification
```bash
python3 -c "
import yaml
p = yaml.safe_load(open('config/personas/bench_laguna.yaml'))
assert p['slug'] == 'bench-laguna', f'FAIL: slug={p[\"slug\"]}'
assert p['workspace_model'] == 'bench-laguna', f'FAIL: workspace_model={p[\"workspace_model\"]}'
assert p['category'] == 'benchmark'
print(f'PASS: persona created — slug={p[\"slug\"]}, name={p[\"name\"]}')
"
```

---

## Task 4 — Add Laguna to launch.sh pull-mlx-models

### File: `launch.sh`

In the `MLX_MODELS=(` array inside `pull-mlx-models`, after the Devstral line and before the GLM/huihui line, add:

Anchor (the line before insertion point):
```bash
        "lmstudio-community/Devstral-Small-2507-MLX-4bit"        # ~15GB — Devstral v1.1, 53.6% SWE-bench
```

Insert after it:
```bash
        "mlx-community/Laguna-XS.2-4bit"                          # ~19GB — Poolside AI MoE 33B-A3B, 68.2% SWE-bench, new lineage
```

### Verification
```bash
grep -n "Laguna-XS.2-4bit" launch.sh && echo "PASS: Laguna present in pull-mlx-models"
```

---

## Task 5 — Update install-mlx to track latest mlx-lm

### File: `launch.sh`

The current install-mlx comment reads:
```
# mlx-lm is pulled as a dependency of mlx-vlm and mlx-audio — no explicit pin needed.
# mlx-vlm 0.4.4 requires mlx-lm>=0.31.0; mlx-audio 0.4.2 pins mlx-lm==0.31.1.
```

The mlx-audio pin at `==0.31.1` prevents mlx-lm from upgrading (Laguna requires >= 0.31.3).
Replace the comment block and the single mlx-vlm install line with the following upgrade sequence.

Exact OLD text to find and replace (this block appears once, inside `install-mlx)`):
```bash
    echo "  Installing mlx-vlm (supports Qwen3.5 VLM + vision models)..."
    pip3 install "mlx-vlm" --upgrade --quiet 2>/dev/null || \
        pip3 install "mlx-vlm" --upgrade --quiet --break-system-packages
    # mlx-lm is pulled as a dependency of mlx-vlm and mlx-audio — no explicit pin needed.
    # mlx-vlm 0.4.4 requires mlx-lm>=0.31.0; mlx-audio 0.4.2 pins mlx-lm==0.31.1.
    python3 -c "import mlx_lm; print(f'  ✅ mlx-lm {mlx_lm.__version__}')" 2>/dev/null || \
        echo "  ❌ mlx-lm not installed (should be pulled by mlx-vlm)"
    python3 -c "import mlx_vlm; print(f'  ✅ mlx-vlm {mlx_vlm.__version__}')" 2>/dev/null || \
        echo "  ✅ mlx-vlm installed"
```

Exact NEW text:
```bash
    echo "  Installing mlx-vlm (supports Qwen3.5 VLM + vision models)..."
    pip3 install "mlx-vlm" --upgrade --quiet 2>/dev/null || \
        pip3 install "mlx-vlm" --upgrade --quiet --break-system-packages
    # mlx-lm: upgrade explicitly after mlx-vlm to unpin any mlx-audio mlx-lm==x.y.z constraint.
    # mlx-lm is actively developed — new model architectures (Laguna SWA, Mamba2, etc.) require
    # staying current. mlx-audio and mlx-vlm are forward-compatible with newer mlx-lm versions.
    echo "  Upgrading mlx-lm to latest (unpins mlx-audio dependency lock)..."
    pip3 install "mlx-lm" --upgrade --quiet 2>/dev/null || \
        pip3 install "mlx-lm" --upgrade --quiet --break-system-packages
    python3 -c "import mlx_lm; print(f'  ✅ mlx-lm {mlx_lm.__version__}')" 2>/dev/null || \
        echo "  ❌ mlx-lm not installed (should be pulled by mlx-vlm)"
    python3 -c "import mlx_vlm; print(f'  ✅ mlx-vlm {mlx_vlm.__version__}')" 2>/dev/null || \
        echo "  ✅ mlx-vlm installed"
```

### Verification
```bash
grep -n "Upgrading mlx-lm to latest" launch.sh && echo "PASS: mlx-lm upgrade step present"
grep -n 'pip3 install "mlx-lm" --upgrade' launch.sh | head -3
```

---

## Post-task verification (run all after all edits complete)

```bash
# 1. Workspace consistency check — must still pass
python3 -c "
import yaml, sys
sys.path.insert(0, '.')
from portal_pipeline.router.workspaces import WORKSPACES
cfg = yaml.safe_load(open('config/backends.yaml'))
pipe_ids = set(WORKSPACES.keys())
yaml_ids = set(cfg['workspace_routing'].keys())
assert pipe_ids == yaml_ids, f'Mismatch: pipe={pipe_ids - yaml_ids} yaml={yaml_ids - pipe_ids}'
print(f'PASS: {len(pipe_ids)} workspaces consistent')
"

# 2. Laguna is in all three locations
python3 -c "
import yaml, sys
sys.path.insert(0, '.')
from portal_pipeline.router.workspaces import WORKSPACES
cfg = yaml.safe_load(open('config/backends.yaml'))
mlx_ids = [m['id'] for m in cfg['backends'][0]['mlx_models']]
assert 'mlx-community/Laguna-XS.2-4bit' in mlx_ids
assert 'bench-laguna' in cfg['workspace_routing']
assert 'bench-laguna' in WORKSPACES
import os; assert os.path.exists('config/personas/bench_laguna.yaml')
print('PASS: Laguna present in backends.yaml mlx_models, workspace_routing, WORKSPACES, and personas/')
"

# 3. Persona slug matches filename convention
python3 -c "
import yaml
p = yaml.safe_load(open('config/personas/bench_laguna.yaml'))
assert p['slug'] == 'bench-laguna'
print('PASS: persona slug matches filename')
"

# 4. Unit tests still pass
pytest tests/unit/ -q --tb=short

# 5. Confirm Laguna in pull-mlx-models and mlx-lm upgrade in install-mlx
grep "Laguna-XS.2-4bit" launch.sh && echo "PASS: Laguna in pull-mlx-models"
grep "Upgrading mlx-lm to latest" launch.sh && echo "PASS: mlx-lm upgrade step present"
```

---

## Commit message

```
feat(models): add Laguna-XS.2-4bit (Poolside) + upgrade mlx-lm install path

- Add mlx-community/Laguna-XS.2-4bit to MLX model catalog (~18.8GB, Poolside
  AI lineage, 68.2% SWE-bench Verified, native reasoning + tool calling)
- Add bench-laguna workspace to backends.yaml, workspaces.py, and personas/
- Add Laguna to pull-mlx-models array in launch.sh
- Update install-mlx to explicitly upgrade mlx-lm after mlx-vlm, unpinning
  mlx-audio's mlx-lm==x.y.z lock so stack stays current with mlx development
```

---

## Post-install operator steps (manual, after Claude Code completes)

```bash
# 1. Upgrade MLX on the host
./launch.sh install-mlx

# 2. Pull Laguna weights
./launch.sh pull-mlx-models

# 3. Restart the pipeline to pick up new workspaces
docker compose -f deploy/portal-5/docker-compose.yml restart portal-pipeline

# 4. Re-seed Open WebUI to register bench-laguna workspace + persona
./launch.sh seed

# 5. Smoke test: switch to bench-laguna workspace, send a simple coding prompt
#    and verify ./launch.sh logs | grep "Switching to model" shows Laguna-XS.2-4bit

# 6. Reasoning sanity check — Laguna produces <think> blocks between tool calls.
#    If output is empty/malformed, check mlx-lm version:
#    python3 -c "import mlx_lm; print(mlx_lm.__version__)"
#    Must be >= 0.31.3. If not, run ./launch.sh install-mlx again.
```

---

## Rollback (if Laguna causes proxy instability)

Laguna is additive — no existing entries were modified. To disable without removing:
1. In `config/backends.yaml`, add `enabled: false` to the Laguna mlx_models entry (proxy skips disabled models).
2. `docker compose restart portal-pipeline`

To fully remove: reverse Tasks 1–5 in order, then re-run workspace consistency check.
