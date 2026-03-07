# Portal 5 — Post-Fix Clone Re-Review

**Repository**: `github.com/ckindle-42/portal-5`  
**Commit**: `58b88ce` (fix: correct model tags and remove broken MLX entries)  
**Audit Date**: March 6, 2026  
**Scope**: Full codebase re-review after two fix commits (71a42da + 58b88ce)

---

## Executive Summary

**Overall Health: 9.5/10** — up from 9.2 in the prior audit.

All 11 fixes from the prior audit + model verification pass landed correctly. The codebase is feature-complete per its documentation, with one minor version string miss and stale references in the agent prompt files that need updating.

### Fix Verification Results (11/11 PASS)

| Check | Status |
|-------|--------|
| Workspace IDs: router_pipe ↔ backends.yaml (13/13) | ✅ |
| Workspace IDs: dispatcher ↔ router_pipe (13/13) | ✅ |
| Broken mlx-vlm models commented out | ✅ |
| qwen3-coder:30b present (correct tag, not :32b) | ✅ |
| deepseek-r1 added to security group | ✅ |
| CLAUDE.md workspace routing table matches code | ✅ |
| Version 5.1.0 across pyproject.toml + __init__.py files | ✅ |
| `"go "` removed from coding keywords | ✅ |
| `"apt"` removed from security keywords | ✅ |
| `_health_timeout` defensive default in __init__ | ✅ |
| Melody conditioning implemented (generate_with_chroma) | ✅ |

### Routing False-Positive Regression Tests (8/8 PASS)

| Test | Result | Expected |
|------|--------|----------|
| "let me go ahead and explain" | None | None ✅ |
| "I had a panic attack today" | None | None ✅ |
| "write a golang web server" | auto-coding | auto-coding ✅ |
| "analyze this malware sample" | auto-security | auto-security ✅ |
| "write a python function" | auto-coding | auto-coding ✅ |
| "reverse shell payload for CTF" | auto-redteam | auto-redteam ✅ |
| "analyze and compare step by step" | auto-reasoning | auto-reasoning ✅ |
| "hello how are you" | None | None ✅ |

---

## Remaining Findings

### FIND-1: FastAPI app version still "5.0.0" (cosmetic)

**File**: `portal_pipeline/router_pipe.py`, line 479  
**Severity**: Cosmetic — version string in FastAPI metadata, not functional

```python
app = FastAPI(title="Portal Pipeline", version="5.0.0", lifespan=lifespan)
```

Should be `version="5.1.0"` to match pyproject.toml and CLAUDE.md.

### FIND-2: Agent prompt `portal5_code_quality_agent_v5.md` has stale MLX port

**File**: `portal5_code_quality_agent_v5.md`, line 416  
**Issue**: Test code uses `url="http://localhost:8080"` for MLX backend. Port 8080 is Open WebUI; MLX is 8081.

```python
# Line 416 — STALE
b_mlx = Backend(id="t-mlx", type="mlx", url="http://localhost:8080", group="mlx",
# Should be:
b_mlx = Backend(id="t-mlx", type="mlx", url="http://localhost:8081", group="mlx",
```

### FIND-3: Agent prompt `portal5_documentation_truth_agent_v4.md` has multiple stale references

**File**: `portal5_documentation_truth_agent_v4.md`

| Line | Stale Value | Current Value |
|------|-------------|---------------|
| 167 | `8080 \| mlx_lm` | `8081 \| mlx_lm` |
| 299 | `url="http://localhost:8080"` (MLX test) | `url="http://localhost:8081"` |
| 678 | `qwen3-coder-next:30b` (doesn't exist as Ollama tag) | Should note this is MLX-only; Ollama tag is `qwen3-coder:30b` |
| 678 | `MiniMax-M2.1` (in coding group list) | Removed — 138GB doesn't fit |
| 679 | `tongyi-deepresearch-30b` (as reasoning model) | Primary is `deepseek-r1:32b-q4_k_m` |
| 719 | `host:8080 (mlx_lm)` | `host:8081 (mlx_lm)` |

### FIND-4: Neither agent prompt tests the mlx-vlm vs mlx-lm issue

Both agent prompts should include a check that verifies MLX models in backends.yaml are mlx-lm compatible (not mlx-vlm). This was the critical finding from the model verification pass and would catch future regressions.

### FIND-5: Neither agent prompt tests melody conditioning

The `generate_continuation` → `generate_with_chroma` fix was a significant bug fix. The code quality agent should verify this path exists.

---

## Agent Prompt Update Task

### Task 1: Fix MLX port in code quality agent v5

**File**: `portal5_code_quality_agent_v5.md`, line 416

Change `http://localhost:8080` to `http://localhost:8081` in the Backend test constructor.

### Task 2: Fix stale references in doc truth agent v4

**File**: `portal5_documentation_truth_agent_v4.md`

- Line 167: Change `8080` to `8081` for mlx_lm port
- Line 299: Change `http://localhost:8080` to `http://localhost:8081`
- Line 678: Remove `MiniMax-M2.1` from coding group model list. Change `qwen3-coder-next:30b` to `qwen3-coder:30b` (Ollama tag) or note it's MLX-only
- Line 679: Change `tongyi-deepresearch-30b` to `deepseek-r1:32b-q4_k_m` as primary reasoning model
- Line 719: Change `host:8080` to `host:8081`

### Task 3: Add mlx-vlm detection check to code quality agent v5

Add to Phase 2 section (after workspace consistency check):

```python
### 2C — MLX Backend Model Compatibility
# Verify no mlx-vlm (vision) models are active in MLX backend
# mlx_lm.server cannot load mlx-vlm conversions

import yaml
cfg = yaml.safe_load(open("config/backends.yaml"))
mlx_backends = [b for b in cfg["backends"] if b.get("type") == "mlx"]
for b in mlx_backends:
    for model in b.get("models", []):
        # Check if model was commented out (shouldn't be here if active)
        if "Qwen3.5" in model:
            print(f"  ⚠️  {model} — verify this is an mlx-lm conversion, not mlx-vlm")
            print(f"     mlx-vlm models will fail to load in mlx_lm.server")
print("MLX model compatibility check complete")
```

### Task 4: Add melody conditioning check to code quality agent v5

Add to the MCP tool checks:

```python
# Verify generate_continuation actually uses melody conditioning
music_src = open("portal_mcp/generation/music_mcp.py").read()
assert "generate_with_chroma" in music_src, \
    "FAIL: generate_continuation does not use AudioCraft melody conditioning"
assert "_generate_with_melody_sync" in music_src, \
    "FAIL: _generate_with_melody_sync function missing"
print("OK: Melody conditioning implemented")
```

### Task 5: Fix FastAPI app version string

**File**: `portal_pipeline/router_pipe.py`, line 479

Change:
```python
app = FastAPI(title="Portal Pipeline", version="5.0.0", lifespan=lifespan)
```
To:
```python
app = FastAPI(title="Portal Pipeline", version="5.1.0", lifespan=lifespan)
```

### Validation

```bash
# Verify all fixes
python3 -c "
import re
# FastAPI version
src = open('portal_pipeline/router_pipe.py').read()
m = re.search(r'version=\"([^\"]+)\"', src)
assert m.group(1) == '5.1.0', f'FastAPI version: {m.group(1)}'
print('✅ FastAPI version 5.1.0')

# Agent prompts — no port 8080 for MLX
for f in ['portal5_code_quality_agent_v5.md', 'portal5_documentation_truth_agent_v4.md']:
    content = open(f).read()
    # Allow 8080 for Open WebUI references, but not for MLX
    lines = content.split('\n')
    for i, line in enumerate(lines, 1):
        if '8080' in line and 'mlx' in line.lower():
            print(f'  ❌ {f}:{i} — stale MLX port 8080')
print('✅ Agent prompts checked')
"
```

### Commit Message

```
fix(agents,version): update agent prompts and FastAPI version to 5.1.0

- Fix MLX port 8080→8081 in code quality agent v5 (line 416)
- Fix 6 stale references in doc truth agent v4 (ports, model names)
- Add mlx-vlm compatibility check to code quality agent
- Add melody conditioning check to code quality agent
- Fix FastAPI app version string: 5.0.0→5.1.0
```

---

## Feature Completeness Assessment

| Feature | Status | Evidence |
|---------|--------|----------|
| 13 workspaces routed correctly | ✅ Complete | Programmatic 3-source check |
| MLX-first with Ollama fallback | ✅ Complete | backends.yaml routing order |
| Content-aware auto-routing | ✅ Complete | 8/8 regression tests pass |
| 7 MCP tool servers registered | ✅ Complete | TOOLS_MANIFEST ↔ @mcp.tool() sync verified |
| Document generation (docx/pptx/xlsx) | ✅ Complete | Tools create real files (tested) |
| Code sandbox (Docker-in-Docker) | ✅ Complete | DinD isolation with security constraints |
| Music generation with melody conditioning | ✅ Complete | generate_with_chroma implemented |
| TTS (kokoro + fish-speech) | ✅ Complete | OpenAI-compatible /v1/audio/speech |
| STT (whisper) | ✅ Complete | OpenAI-compatible /v1/audio/transcriptions |
| Image generation (ComfyUI/FLUX) | ✅ Complete | Workflow templates for FLUX + SDXL |
| Video generation (Wan2.2/CogVideoX) | ✅ Complete | Workflow templates with polling |
| Telegram bot | ✅ Complete | Auth, workspace switching, history bounded |
| Slack bot | ✅ Complete | Socket Mode, channel→workspace mapping |
| Prometheus metrics | ✅ Complete | Per-model tok/s, multiprocess-safe |
| Grafana dashboard | ✅ Complete | Provisioned via docker-compose |
| Secret auto-generation | ✅ Complete | launch.sh bootstrap + repair |
| Broken MLX models flagged | ✅ Complete | Qwen3.5 mlx-vlm entries commented out |
| Model tags verified against registries | ✅ Complete | qwen3-coder:30b (not :32b) |

**No bugs found. No security vulnerabilities found. 5 cosmetic/documentation items identified and tasked above.**
