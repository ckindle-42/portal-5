# TASK: Add Coding Capability Benchmark Workspaces

**Task ID:** TASK-BENCH-001  
**Version target:** v6.0.4  
**Priority:** Normal  
**Category:** Feature / Architecture  
**Protected files touched:** None  
**Estimated risk:** Low — additive only, zero changes to existing workspaces or routing logic

---

## ⚠️ Amendment: `mlx_only` Field Required in WORKSPACES Entries

**Added by TASK-BENCH-002.** When executing Change 1 (WORKSPACES dict additions), include
`"mlx_only": True` on all 7 MLX bench workspace entries. Do NOT add it to `bench-glm`
or `bench-gptoss` — those are Ollama-only and have no MLX backend to enforce.

The field drives the hard-fail filtering added in TASK-BENCH-002. Without it, bench
workspaces silently fall through to Ollama on MLX failure, contaminating results.

See `TASK_BENCH_MLX_ONLY.md` for the full Change 1 before/after for each entry.
TASK-BENCH-001 and TASK-BENCH-002 should be committed together in a single session.

---

## Problem Statement

The Portal 5 validation guide includes a Section 5 "Coding Capability Benchmark" that requires
running the same prompt (a complete single-file browser game) against multiple coding-capable
models under identical behavioral framing to reveal real capability differences.

This is currently impossible because:

1. `/v1/models` only exposes the 17 workspace IDs — individual model names are never surfaced
   to Open WebUI. There is no "model picker" at the UI level.
2. `mlx_model_hint` and `model_hint` in each `WORKSPACES` entry hardwire model selection.
   The only way to expose a different model is a new workspace entry.
3. The Creative Coder persona (`workspace_model: auto-coding`) is locked to Devstral-Small-2507
   via the `auto-coding` hint. Applying the same behavioral framing across multiple models
   requires one persona per model.

## Solution

Add 9 new "bench-*" workspaces, each pinned to one specific model via `mlx_model_hint` /
`model_hint`. Add 9 corresponding personas that carry the Creative Coder system prompt verbatim,
each pointing to its bench workspace. This makes every benchmark model selectable from the Open
WebUI model dropdown as a named persona with identical system framing.

**Design constraints (do not violate):**
- Bench workspaces are user-selected only — do NOT add to `_VALID_WORKSPACE_IDS` or
  `_ROUTER_JSON_SCHEMA`. They are never auto-routed by the LLM intent classifier.
- Do NOT set `context_limit` on any bench workspace. The 32K cap in `auto-agentic` is a
  deliberate big-model-mode constraint for that workflow only. Benchmarks need full context.
- Additive only — zero changes to any existing WORKSPACES entry, persona, or routing logic.

---

## Safety Gate

```bash
git tag pre-bench-workspaces
git stash  # if needed
```

---

## Files to Change

| # | File | Change type |
|---|------|-------------|
| 1 | `portal_pipeline/router_pipe.py` | Add 9 entries to `WORKSPACES` dict |
| 2 | `config/backends.yaml` | Add 9 keys to `workspace_routing` block |
| 3 | `config/personas/bench_devstral.yaml` | New file |
| 4 | `config/personas/bench_qwen3_coder_next.yaml` | New file |
| 5 | `config/personas/bench_qwen3_coder_30b.yaml` | New file |
| 6 | `config/personas/bench_llama33_70b.yaml` | New file |
| 7 | `config/personas/bench_phi4.yaml` | New file |
| 8 | `config/personas/bench_phi4_reasoning.yaml` | New file |
| 9 | `config/personas/bench_dolphin8b.yaml` | New file |
| 10 | `config/personas/bench_glm.yaml` | New file |
| 11 | `config/personas/bench_gptoss.yaml` | New file |
| 12 | `imports/openwebui/workspaces/workspace_bench_devstral.json` | New file |
| 13 | `imports/openwebui/workspaces/workspace_bench_qwen3_coder_next.json` | New file |
| 14 | `imports/openwebui/workspaces/workspace_bench_qwen3_coder_30b.json` | New file |
| 15 | `imports/openwebui/workspaces/workspace_bench_llama33_70b.json` | New file |
| 16 | `imports/openwebui/workspaces/workspace_bench_phi4.json` | New file |
| 17 | `imports/openwebui/workspaces/workspace_bench_phi4_reasoning.json` | New file |
| 18 | `imports/openwebui/workspaces/workspace_bench_dolphin8b.json` | New file |
| 19 | `imports/openwebui/workspaces/workspace_bench_glm.json` | New file |
| 20 | `imports/openwebui/workspaces/workspace_bench_gptoss.json` | New file |
| 21 | `imports/openwebui/workspaces/workspaces_all.json` | Append 9 entries |

---

## Change 1: `portal_pipeline/router_pipe.py`

### Location

Line 481 — the closing `},` of the `"auto-mistral"` entry, followed by `}` closing `WORKSPACES`.

### Before (lines 480–484)

```python
        "mlx_model_hint": "lmstudio-community/Magistral-Small-2509-MLX-8bit",
    },
}

# ── Content-aware routing: weighted keyword scoring ──────────────────────────
```

### After

```python
        "mlx_model_hint": "lmstudio-community/Magistral-Small-2509-MLX-8bit",
    },
    # ── Coding Capability Benchmark Workspaces ───────────────────────────────
    # User-selected only — never auto-routed by the LLM intent classifier.
    # Each workspace is pinned to exactly one model via mlx_model_hint / model_hint.
    # No context_limit — benchmarks must run at full context for fair comparison.
    # Companion personas (config/personas/bench_*.yaml) carry the Creative Coder
    # system prompt verbatim so all models are evaluated under identical framing.
    "bench-devstral": {
        "name": "🔬 Bench · Devstral-Small-2507",
        "description": "Benchmark: Devstral-Small-2507 (MLX, Mistral/Codestral lineage, ~15GB, 53.6% SWE-bench)",
        "model_hint": "devstral:24b",
        "mlx_model_hint": "lmstudio-community/Devstral-Small-2507-MLX-4bit",
    },
    "bench-qwen3-coder-next": {
        "name": "🔬 Bench · Qwen3-Coder-Next (80B MoE)",
        "description": "Benchmark: Qwen3-Coder-Next-4bit (MLX, Alibaba, 80B MoE 3B active, ~46GB, 256K ctx — cold load ~60s)",
        "model_hint": "qwen3-coder:30b",
        "mlx_model_hint": "mlx-community/Qwen3-Coder-Next-4bit",
    },
    "bench-qwen3-coder-30b": {
        "name": "🔬 Bench · Qwen3-Coder-30B",
        "description": "Benchmark: Qwen3-Coder-30B-A3B-8bit (MLX, Alibaba, 30B MoE 3B active, ~22GB)",
        "model_hint": "qwen3-coder:30b",
        "mlx_model_hint": "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit",
    },
    "bench-llama33-70b": {
        "name": "🔬 Bench · Llama-3.3-70B",
        "description": "Benchmark: Llama-3.3-70B-Instruct-4bit (MLX, Meta, ~40GB — cold load ~60s, plan for sequential runs)",
        "model_hint": "llama3.3:70b-q4_k_m",
        "mlx_model_hint": "mlx-community/Llama-3.3-70B-Instruct-4bit",
    },
    "bench-phi4": {
        "name": "🔬 Bench · Phi-4",
        "description": "Benchmark: phi-4-8bit (MLX, Microsoft, 14B, synthetic training data — distinct methodology)",
        "model_hint": "qwen3.5:9b",
        "mlx_model_hint": "mlx-community/phi-4-8bit",
    },
    "bench-phi4-reasoning": {
        "name": "🔬 Bench · Phi-4-reasoning-plus",
        "description": "Benchmark: Phi-4-reasoning-plus (MLX, Microsoft, RL-trained, ~7GB — produces reasoning traces before code)",
        "model_hint": "qwen3.5:9b",
        "mlx_model_hint": "lmstudio-community/Phi-4-reasoning-plus-MLX-4bit",
    },
    "bench-dolphin8b": {
        "name": "🔬 Bench · Dolphin-Llama3-8B",
        "description": "Benchmark: Dolphin3.0-Llama3.1-8B-8bit (MLX, Cognitive Computations, ~9GB — fast baseline, uncensored)",
        "model_hint": "dolphin-llama3:8b",
        "mlx_model_hint": "mlx-community/Dolphin3.0-Llama3.1-8B-8bit",
    },
    "bench-glm": {
        "name": "🔬 Bench · GLM-4.7-Flash",
        "description": "Benchmark: glm-4.7-flash:q4_k_m (Ollama, Zhipu AI — distinct Chinese research lineage, ~6GB)",
        "model_hint": "glm-4.7-flash:q4_k_m",
    },
    "bench-gptoss": {
        "name": "🔬 Bench · GPT-OSS-20B",
        "description": "Benchmark: gpt-oss:20b (Ollama, OpenAI open-weight MoE, ~12GB, o3-mini level — configurable thinking depth)",
        "model_hint": "gpt-oss:20b",
    },
}

# ── Content-aware routing: weighted keyword scoring ──────────────────────────
```

---

## Change 2: `config/backends.yaml`

### Location

Line 149 — the `auto-mistral` entry, which is the last line of `workspace_routing`.
Insert the 9 bench entries after it, before the blank line preceding `defaults:`.

### Before (lines 149–151)

```yaml
  auto-mistral:    [mlx, reasoning, general]   # Magistral-Small dedicated reasoning — Mistral training lineage

defaults:
```

### After

```yaml
  auto-mistral:    [mlx, reasoning, general]   # Magistral-Small dedicated reasoning — Mistral training lineage
  # ── Coding Capability Benchmark Workspaces ──────────────────────────────
  # User-selected only. Each workspace is pinned to one model.
  # If MLX cannot load the target model, abort the benchmark run — do not
  # compare against a fallback. Fallback groups listed for graceful degradation
  # only; the bench persona description warns users to verify model loaded.
  bench-devstral:          [mlx, coding, general]   # Devstral-Small-2507 (Mistral/Codestral)
  bench-qwen3-coder-next:  [mlx, coding, general]   # Qwen3-Coder-Next-4bit (Alibaba, 80B MoE)
  bench-qwen3-coder-30b:   [mlx, coding, general]   # Qwen3-Coder-30B-A3B-8bit (Alibaba, 30B MoE)
  bench-llama33-70b:       [mlx, coding, general]   # Llama-3.3-70B-4bit (Meta)
  bench-phi4:              [mlx, coding, general]   # Phi-4-8bit (Microsoft)
  bench-phi4-reasoning:    [mlx, coding, general]   # Phi-4-reasoning-plus (Microsoft RL)
  bench-dolphin8b:         [mlx, general]           # Dolphin3.0-Llama3.1-8B (Cognitive Computations)
  bench-glm:               [coding, general]        # glm-4.7-flash (Zhipu AI — Ollama only)
  bench-gptoss:            [reasoning, general]     # gpt-oss:20b (OpenAI open-weight — Ollama only)

defaults:
```

---

## Change 3–11: Persona YAML Files

All 9 personas share the Creative Coder system prompt verbatim. The only differences are
`name`, `slug`, `workspace_model`, and the routing comment. Create each file exactly as shown.

### `config/personas/bench_devstral.yaml`

```yaml
name: 🔬 Bench · Devstral-Small-2507
slug: bench-devstral
category: benchmark
workspace_model: bench-devstral
# Routes to: Devstral-Small-2507 (MLX primary, Mistral/Codestral lineage, ~15GB)
# Fallback: devstral:24b (Ollama GGUF — same model family, lower quality)
# BENCHMARK NOTE: Verify MLX loaded this model before recording results.
# Check: ./launch.sh logs | grep "Switching to model"
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

### `config/personas/bench_qwen3_coder_next.yaml`

```yaml
name: 🔬 Bench · Qwen3-Coder-Next (80B MoE)
slug: bench-qwen3-coder-next
category: benchmark
workspace_model: bench-qwen3-coder-next
# Routes to: Qwen3-Coder-Next-4bit (MLX, Alibaba, 80B MoE 3B active, ~46GB, 256K ctx)
# Fallback: qwen3-coder:30b (Ollama GGUF)
# BENCHMARK NOTE: ~46GB — cold load ~60s. Verify loaded before recording results.
# No context_limit applied (unlike auto-agentic which caps at 32K for big-model mode).
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

### `config/personas/bench_qwen3_coder_30b.yaml`

```yaml
name: 🔬 Bench · Qwen3-Coder-30B
slug: bench-qwen3-coder-30b
category: benchmark
workspace_model: bench-qwen3-coder-30b
# Routes to: Qwen3-Coder-30B-A3B-Instruct-8bit (MLX, Alibaba, 30B MoE 3B active, ~22GB)
# Fallback: qwen3-coder:30b (Ollama GGUF)
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

### `config/personas/bench_llama33_70b.yaml`

```yaml
name: 🔬 Bench · Llama-3.3-70B
slug: bench-llama33-70b
category: benchmark
workspace_model: bench-llama33-70b
# Routes to: Llama-3.3-70B-Instruct-4bit (MLX, Meta, ~40GB)
# Fallback: llama3.3:70b-q4_k_m (Ollama GGUF — same weights, different runtime)
# BENCHMARK NOTE: ~40GB — cold load ~60s. Will displace any other loaded MLX model.
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

### `config/personas/bench_phi4.yaml`

```yaml
name: 🔬 Bench · Phi-4
slug: bench-phi4
category: benchmark
workspace_model: bench-phi4
# Routes to: phi-4-8bit (MLX, Microsoft, 14B, ~14GB, synthetic training data methodology)
# Fallback: qwen3.5:9b (Ollama — different model, closest available size)
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

### `config/personas/bench_phi4_reasoning.yaml`

```yaml
name: 🔬 Bench · Phi-4-reasoning-plus
slug: bench-phi4-reasoning
category: benchmark
workspace_model: bench-phi4-reasoning
# Routes to: Phi-4-reasoning-plus-MLX-4bit (MLX, Microsoft, RL-trained, ~7GB)
# Fallback: qwen3.5:9b (Ollama — different model, closest available size)
# BENCHMARK NOTE: RL-trained model — expect visible reasoning traces before HTML output.
# This is expected behavior, not a failure. Evaluate code quality of the HTML only.
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

### `config/personas/bench_dolphin8b.yaml`

```yaml
name: 🔬 Bench · Dolphin-Llama3-8B
slug: bench-dolphin8b
category: benchmark
workspace_model: bench-dolphin8b
# Routes to: Dolphin3.0-Llama3.1-8B-8bit (MLX, Cognitive Computations, ~9GB)
# Fallback: dolphin-llama3:8b (Ollama GGUF — same model family)
# BENCHMARK NOTE: Fast model (~30+ TPS). Useful as speed/quality baseline.
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

### `config/personas/bench_glm.yaml`

```yaml
name: 🔬 Bench · GLM-4.7-Flash
slug: bench-glm
category: benchmark
workspace_model: bench-glm
# Routes to: glm-4.7-flash:q4_k_m (Ollama, Zhipu AI, ~6GB)
# Ollama only — no MLX variant available. Routing: [coding, general].
# BENCHMARK NOTE: Distinct Chinese research lineage. No MLX — Ollama delivery only.
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

### `config/personas/bench_gptoss.yaml`

```yaml
name: 🔬 Bench · GPT-OSS-20B
slug: bench-gptoss
category: benchmark
workspace_model: bench-gptoss
# Routes to: gpt-oss:20b (Ollama, OpenAI open-weight MoE, ~12GB, o3-mini level)
# Ollama only — no MLX variant available. Routing: [reasoning, general].
# BENCHMARK NOTE: OpenAI open-weight lineage. Configurable thinking depth via Ollama options.
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

---

## Changes 12–20: Workspace JSON Files

Create each file in `imports/openwebui/workspaces/`. All bench workspaces include
`portal_code` toolId so the code sandbox is available during benchmark runs.

### `imports/openwebui/workspaces/workspace_bench_devstral.json`
```json
{
  "id": "bench-devstral",
  "name": "🔬 Bench · Devstral-Small-2507",
  "meta": {
    "description": "Benchmark: Devstral-Small-2507 — Mistral/Codestral lineage, ~15GB",
    "profile_image_url": "",
    "toolIds": ["portal_code"]
  },
  "params": {
    "system": "You are a creative coder. Ship complete, working, single-file HTML. No TODOs. No framework questions. Build the most interesting version.",
    "model": "bench-devstral"
  }
}
```

### `imports/openwebui/workspaces/workspace_bench_qwen3_coder_next.json`
```json
{
  "id": "bench-qwen3-coder-next",
  "name": "🔬 Bench · Qwen3-Coder-Next (80B MoE)",
  "meta": {
    "description": "Benchmark: Qwen3-Coder-Next-4bit — Alibaba, 80B MoE, ~46GB, cold load ~60s",
    "profile_image_url": "",
    "toolIds": ["portal_code"]
  },
  "params": {
    "system": "You are a creative coder. Ship complete, working, single-file HTML. No TODOs. No framework questions. Build the most interesting version.",
    "model": "bench-qwen3-coder-next"
  }
}
```

### `imports/openwebui/workspaces/workspace_bench_qwen3_coder_30b.json`
```json
{
  "id": "bench-qwen3-coder-30b",
  "name": "🔬 Bench · Qwen3-Coder-30B",
  "meta": {
    "description": "Benchmark: Qwen3-Coder-30B-A3B-8bit — Alibaba, 30B MoE, ~22GB",
    "profile_image_url": "",
    "toolIds": ["portal_code"]
  },
  "params": {
    "system": "You are a creative coder. Ship complete, working, single-file HTML. No TODOs. No framework questions. Build the most interesting version.",
    "model": "bench-qwen3-coder-30b"
  }
}
```

### `imports/openwebui/workspaces/workspace_bench_llama33_70b.json`
```json
{
  "id": "bench-llama33-70b",
  "name": "🔬 Bench · Llama-3.3-70B",
  "meta": {
    "description": "Benchmark: Llama-3.3-70B-Instruct-4bit — Meta, ~40GB, cold load ~60s",
    "profile_image_url": "",
    "toolIds": ["portal_code"]
  },
  "params": {
    "system": "You are a creative coder. Ship complete, working, single-file HTML. No TODOs. No framework questions. Build the most interesting version.",
    "model": "bench-llama33-70b"
  }
}
```

### `imports/openwebui/workspaces/workspace_bench_phi4.json`
```json
{
  "id": "bench-phi4",
  "name": "🔬 Bench · Phi-4",
  "meta": {
    "description": "Benchmark: phi-4-8bit — Microsoft, 14B, synthetic training data, ~14GB",
    "profile_image_url": "",
    "toolIds": ["portal_code"]
  },
  "params": {
    "system": "You are a creative coder. Ship complete, working, single-file HTML. No TODOs. No framework questions. Build the most interesting version.",
    "model": "bench-phi4"
  }
}
```

### `imports/openwebui/workspaces/workspace_bench_phi4_reasoning.json`
```json
{
  "id": "bench-phi4-reasoning",
  "name": "🔬 Bench · Phi-4-reasoning-plus",
  "meta": {
    "description": "Benchmark: Phi-4-reasoning-plus — Microsoft RL-trained, ~7GB, produces reasoning traces",
    "profile_image_url": "",
    "toolIds": ["portal_code"]
  },
  "params": {
    "system": "You are a creative coder. Ship complete, working, single-file HTML. No TODOs. No framework questions. Build the most interesting version.",
    "model": "bench-phi4-reasoning"
  }
}
```

### `imports/openwebui/workspaces/workspace_bench_dolphin8b.json`
```json
{
  "id": "bench-dolphin8b",
  "name": "🔬 Bench · Dolphin-Llama3-8B",
  "meta": {
    "description": "Benchmark: Dolphin3.0-Llama3.1-8B-8bit — Cognitive Computations, ~9GB, fast baseline",
    "profile_image_url": "",
    "toolIds": ["portal_code"]
  },
  "params": {
    "system": "You are a creative coder. Ship complete, working, single-file HTML. No TODOs. No framework questions. Build the most interesting version.",
    "model": "bench-dolphin8b"
  }
}
```

### `imports/openwebui/workspaces/workspace_bench_glm.json`
```json
{
  "id": "bench-glm",
  "name": "🔬 Bench · GLM-4.7-Flash",
  "meta": {
    "description": "Benchmark: glm-4.7-flash:q4_k_m — Zhipu AI, Ollama only, ~6GB",
    "profile_image_url": "",
    "toolIds": ["portal_code"]
  },
  "params": {
    "system": "You are a creative coder. Ship complete, working, single-file HTML. No TODOs. No framework questions. Build the most interesting version.",
    "model": "bench-glm"
  }
}
```

### `imports/openwebui/workspaces/workspace_bench_gptoss.json`
```json
{
  "id": "bench-gptoss",
  "name": "🔬 Bench · GPT-OSS-20B",
  "meta": {
    "description": "Benchmark: gpt-oss:20b — OpenAI open-weight MoE, Ollama only, ~12GB",
    "profile_image_url": "",
    "toolIds": ["portal_code"]
  },
  "params": {
    "system": "You are a creative coder. Ship complete, working, single-file HTML. No TODOs. No framework questions. Build the most interesting version.",
    "model": "bench-gptoss"
  }
}
```

---

## Change 21: `imports/openwebui/workspaces/workspaces_all.json`

Append the 9 bench workspace objects before the closing `]` of the JSON array.

### Before (last two lines of file)

```json
    }
  }
]
```

### After

```json
    }
  },
  {
    "id": "bench-devstral",
    "name": "🔬 Bench · Devstral-Small-2507",
    "meta": {
      "description": "Benchmark: Devstral-Small-2507 — Mistral/Codestral lineage, ~15GB",
      "profile_image_url": "",
      "toolIds": ["portal_code"]
    },
    "params": {
      "system": "You are a creative coder. Ship complete, working, single-file HTML. No TODOs. No framework questions. Build the most interesting version.",
      "model": "bench-devstral"
    }
  },
  {
    "id": "bench-qwen3-coder-next",
    "name": "🔬 Bench · Qwen3-Coder-Next (80B MoE)",
    "meta": {
      "description": "Benchmark: Qwen3-Coder-Next-4bit — Alibaba, 80B MoE, ~46GB, cold load ~60s",
      "profile_image_url": "",
      "toolIds": ["portal_code"]
    },
    "params": {
      "system": "You are a creative coder. Ship complete, working, single-file HTML. No TODOs. No framework questions. Build the most interesting version.",
      "model": "bench-qwen3-coder-next"
    }
  },
  {
    "id": "bench-qwen3-coder-30b",
    "name": "🔬 Bench · Qwen3-Coder-30B",
    "meta": {
      "description": "Benchmark: Qwen3-Coder-30B-A3B-8bit — Alibaba, 30B MoE, ~22GB",
      "profile_image_url": "",
      "toolIds": ["portal_code"]
    },
    "params": {
      "system": "You are a creative coder. Ship complete, working, single-file HTML. No TODOs. No framework questions. Build the most interesting version.",
      "model": "bench-qwen3-coder-30b"
    }
  },
  {
    "id": "bench-llama33-70b",
    "name": "🔬 Bench · Llama-3.3-70B",
    "meta": {
      "description": "Benchmark: Llama-3.3-70B-Instruct-4bit — Meta, ~40GB, cold load ~60s",
      "profile_image_url": "",
      "toolIds": ["portal_code"]
    },
    "params": {
      "system": "You are a creative coder. Ship complete, working, single-file HTML. No TODOs. No framework questions. Build the most interesting version.",
      "model": "bench-llama33-70b"
    }
  },
  {
    "id": "bench-phi4",
    "name": "🔬 Bench · Phi-4",
    "meta": {
      "description": "Benchmark: phi-4-8bit — Microsoft, 14B, synthetic training, ~14GB",
      "profile_image_url": "",
      "toolIds": ["portal_code"]
    },
    "params": {
      "system": "You are a creative coder. Ship complete, working, single-file HTML. No TODOs. No framework questions. Build the most interesting version.",
      "model": "bench-phi4"
    }
  },
  {
    "id": "bench-phi4-reasoning",
    "name": "🔬 Bench · Phi-4-reasoning-plus",
    "meta": {
      "description": "Benchmark: Phi-4-reasoning-plus — Microsoft RL-trained, ~7GB",
      "profile_image_url": "",
      "toolIds": ["portal_code"]
    },
    "params": {
      "system": "You are a creative coder. Ship complete, working, single-file HTML. No TODOs. No framework questions. Build the most interesting version.",
      "model": "bench-phi4-reasoning"
    }
  },
  {
    "id": "bench-dolphin8b",
    "name": "🔬 Bench · Dolphin-Llama3-8B",
    "meta": {
      "description": "Benchmark: Dolphin3.0-Llama3.1-8B-8bit — Cognitive Computations, ~9GB",
      "profile_image_url": "",
      "toolIds": ["portal_code"]
    },
    "params": {
      "system": "You are a creative coder. Ship complete, working, single-file HTML. No TODOs. No framework questions. Build the most interesting version.",
      "model": "bench-dolphin8b"
    }
  },
  {
    "id": "bench-glm",
    "name": "🔬 Bench · GLM-4.7-Flash",
    "meta": {
      "description": "Benchmark: glm-4.7-flash:q4_k_m — Zhipu AI, Ollama only, ~6GB",
      "profile_image_url": "",
      "toolIds": ["portal_code"]
    },
    "params": {
      "system": "You are a creative coder. Ship complete, working, single-file HTML. No TODOs. No framework questions. Build the most interesting version.",
      "model": "bench-glm"
    }
  },
  {
    "id": "bench-gptoss",
    "name": "🔬 Bench · GPT-OSS-20B",
    "meta": {
      "description": "Benchmark: gpt-oss:20b — OpenAI open-weight MoE, Ollama only, ~12GB",
      "profile_image_url": "",
      "toolIds": ["portal_code"]
    },
    "params": {
      "system": "You are a creative coder. Ship complete, working, single-file HTML. No TODOs. No framework questions. Build the most interesting version.",
      "model": "bench-gptoss"
    }
  }
]
```

---

## Acceptance Criteria

- [ ] `portal_pipeline/router_pipe.py` contains exactly 9 new `bench-*` keys in `WORKSPACES`
- [ ] None of the 9 bench workspace IDs appear in `_VALID_WORKSPACE_IDS` or `_ROUTER_JSON_SCHEMA`
- [ ] None of the 9 bench workspace entries contain a `context_limit` field
- [ ] `config/backends.yaml` contains exactly 9 new `bench-*` keys under `workspace_routing`
- [ ] Workspace consistency check passes (see Verification section)
- [ ] Exactly 9 new `bench_*.yaml` files exist in `config/personas/`
- [ ] All 9 persona YAMLs have `category: benchmark`
- [ ] All 9 persona YAMLs carry the Creative Coder system prompt verbatim (not abbreviated)
- [ ] Exactly 9 new `workspace_bench_*.json` files exist in `imports/openwebui/workspaces/`
- [ ] `workspaces_all.json` is valid JSON after edit (`python3 -m json.tool` passes)
- [ ] All existing tests pass: `pytest tests/ -q --tb=short`
- [ ] Ruff clean: `ruff check portal_pipeline/ && ruff format --check portal_pipeline/`

---

## Verification Commands

```bash
# 1. Workspace consistency check (from CLAUDE.md Rule 6)
python3 -c "
import yaml
from portal_pipeline.router_pipe import WORKSPACES
cfg = yaml.safe_load(open('config/backends.yaml'))
pipe_ids = set(WORKSPACES.keys())
yaml_ids = set(cfg['workspace_routing'].keys())
assert pipe_ids == yaml_ids, f'Mismatch: pipe={pipe_ids-yaml_ids} yaml={yaml_ids-pipe_ids}'
print('Workspace IDs consistent:', len(pipe_ids), 'total')
"

# 2. Bench workspaces not in LLM router allowlist
python3 -c "
from portal_pipeline.router_pipe import _VALID_WORKSPACE_IDS, WORKSPACES
bench = [k for k in WORKSPACES if k.startswith('bench-')]
leaked = [k for k in bench if k in _VALID_WORKSPACE_IDS]
assert not leaked, f'Bench workspaces leaked into router allowlist: {leaked}'
print('Bench workspaces correctly excluded from LLM router:', bench)
"

# 3. No context_limit on bench workspaces
python3 -c "
from portal_pipeline.router_pipe import WORKSPACES
for ws_id, cfg in WORKSPACES.items():
    if ws_id.startswith('bench-'):
        assert 'context_limit' not in cfg, f'{ws_id} has context_limit — remove it'
print('No context_limit on bench workspaces: OK')
"

# 4. Persona count
ls config/personas/bench_*.yaml | wc -l
# Expected: 9

# 5. Workspace JSON count
ls imports/openwebui/workspaces/workspace_bench_*.json | wc -l
# Expected: 9

# 6. workspaces_all.json valid JSON
python3 -m json.tool imports/openwebui/workspaces/workspaces_all.json > /dev/null && echo "JSON valid"

# 7. All personas have correct category
grep "category:" config/personas/bench_*.yaml
# All lines should show: category: benchmark

# 8. All personas have correct workspace_model prefix
grep "workspace_model:" config/personas/bench_*.yaml
# All values should start with bench-

# 9. Existing test suite
pytest tests/ -q --tb=short

# 10. Ruff
ruff check portal_pipeline/ && ruff format --check portal_pipeline/
```

---

## Post-Implementation: Reseed Open WebUI

```bash
# Restart pipeline to pick up new WORKSPACES entries
./launch.sh restart portal-pipeline

# Reseed Open WebUI to register bench workspaces and personas
./launch.sh reseed

# Verify bench workspaces appear in /v1/models
curl -s -H "Authorization: Bearer ${PIPELINE_API_KEY}" \
  http://localhost:9099/v1/models | python3 -m json.tool | grep "bench-"
# Expected: 9 bench-* IDs in output
```

---

## Rollback Procedure

```bash
git checkout pre-bench-workspaces -- \
  portal_pipeline/router_pipe.py \
  config/backends.yaml \
  imports/openwebui/workspaces/workspaces_all.json

rm -f config/personas/bench_*.yaml
rm -f imports/openwebui/workspaces/workspace_bench_*.json

./launch.sh restart portal-pipeline
./launch.sh reseed
```

---

## Commit Message

```
feat(bench): add 9 coding capability benchmark workspaces

Adds bench-* workspace IDs to WORKSPACES (router_pipe.py) and
workspace_routing (backends.yaml), each pinned to one specific model
via mlx_model_hint / model_hint. Adds 9 companion personas carrying
the Creative Coder system prompt verbatim — identical behavioral
framing across all models for fair comparison.

Models covered (9):
  MLX: Devstral-Small-2507, Qwen3-Coder-Next (80B MoE),
       Qwen3-Coder-30B, Llama-3.3-70B, Phi-4, Phi-4-reasoning-plus,
       Dolphin-Llama3-8B
  Ollama: GLM-4.7-Flash (Zhipu AI), GPT-OSS-20B (OpenAI open-weight)

Design: bench-* workspaces are user-selected only — excluded from
_VALID_WORKSPACE_IDS and _ROUTER_JSON_SCHEMA so the LLM intent
classifier never auto-routes to them. No context_limit applied.
Additive only — zero changes to existing workspaces or routing logic.

Closes: TASK-BENCH-001
```
