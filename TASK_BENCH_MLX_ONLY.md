# TASK: Bench Workspace MLX-Only Hard-Fail Enforcement

**Task ID:** TASK-BENCH-002  
**Depends on:** TASK-BENCH-001 (bench workspaces must exist before this runs)  
**Version target:** v6.0.4  
**Priority:** Normal — must execute as part of the same release as TASK-BENCH-001  
**Category:** Bug Fix / Architecture  
**Protected files touched:** None  
**Estimated risk:** Low — changes are isolated to the bench-* workspace dispatch path only

---

## Problem Statement

Without this task, bench workspaces silently fall back to Ollama when the target MLX
model fails to respond. This contaminates benchmark results — a failed MLX load
produces an Ollama response that passes for a successful run, making cross-model
comparison meaningless.

Three failure modes that trigger silent fallback today:

1. **MLX model not yet loaded** — cold load takes 30–60s for large models. During that
   window, if the inference request times out, `_try_non_streaming` returns `None` and
   the loop advances to the Ollama candidates.

2. **`enforce_hint=not is_last` relaxation** — with one MLX candidate (always `is_last=True`),
   `enforce_hint=False` allows the backend to substitute a different model if the hinted
   one isn't matched. This is correct behavior for production workspaces; wrong for
   benchmarking where the whole point is model identity.

3. **Streaming fallback** — `_stream_or_fallback` will attempt non-streaming Ollama
   candidates if the MLX stream fails.

## Why the Existing 300s Timeout Already Handles Cold Loads

The shared `_http_client` uses `httpx.Timeout(300.0, connect=5.0)`. A 40GB model cold
load takes approximately 60s. The pipeline will wait up to 300s for MLX to respond —
no additional polling or retry logic is needed. The "give grace time" requirement is
already satisfied by the existing timeout. What is NOT satisfied is the "fail hard
instead of continuing to Ollama" requirement, which this task addresses.

## Key Architecture Note: Streaming Path Is Self-Healing

After filtering `candidates` to MLX-only (Change 1 below), `len(candidates) == 1`.
The streaming dispatch code already handles this:

```python
if len(candidates) == 1:
    # Single candidate — no fallback possible, return streaming directly
    return StreamingResponse(_stream_with_preamble(...), ...)
```

`remaining = candidates[1:]` is empty, so `_stream_or_fallback` is never invoked and
Ollama fallback is structurally impossible. **No changes are needed to the streaming
path.**

---

## Safety Gate

```bash
git tag pre-bench-mlx-only
```

---

## Files to Change

| # | File | Change type |
|---|------|-------------|
| 1 | `portal_pipeline/router_pipe.py` | Add `mlx_only: True` to 7 bench WORKSPACES entries |
| 2 | `portal_pipeline/router_pipe.py` | Insert MLX-only filtering block in `chat_completions()` |
| 3 | `portal_pipeline/router_pipe.py` | Enforce hint strictly + add bench-specific error in non-streaming loop |

All three changes are in the same file. Apply in order.

---

## Change 1: Add `mlx_only` to WORKSPACES Entries

The 7 MLX bench workspaces (those with `mlx_model_hint`) receive `"mlx_only": True`.
The 2 Ollama-only bench workspaces (`bench-glm`, `bench-gptoss`) do NOT — they have no
MLX backend to enforce, and their Ollama model_hint already pins the target model.

Apply each of the following 7 str_replace edits. Each targets the closing line of one
WORKSPACES entry.

### bench-devstral

**Before:**
```python
    "bench-devstral": {
        "name": "🔬 Bench · Devstral-Small-2507",
        "description": "Benchmark: Devstral-Small-2507 (MLX, Mistral/Codestral lineage, ~15GB, 53.6% SWE-bench)",
        "model_hint": "devstral:24b",
        "mlx_model_hint": "lmstudio-community/Devstral-Small-2507-MLX-4bit",
    },
```

**After:**
```python
    "bench-devstral": {
        "name": "🔬 Bench · Devstral-Small-2507",
        "description": "Benchmark: Devstral-Small-2507 (MLX, Mistral/Codestral lineage, ~15GB, 53.6% SWE-bench)",
        "model_hint": "devstral:24b",
        "mlx_model_hint": "lmstudio-community/Devstral-Small-2507-MLX-4bit",
        "mlx_only": True,  # Hard-fail if MLX unavailable — no Ollama fallback during benchmark
    },
```

### bench-qwen3-coder-next

**Before:**
```python
    "bench-qwen3-coder-next": {
        "name": "🔬 Bench · Qwen3-Coder-Next (80B MoE)",
        "description": "Benchmark: Qwen3-Coder-Next-4bit (MLX, Alibaba, 80B MoE 3B active, ~46GB, 256K ctx — cold load ~60s)",
        "model_hint": "qwen3-coder:30b",
        "mlx_model_hint": "mlx-community/Qwen3-Coder-Next-4bit",
    },
```

**After:**
```python
    "bench-qwen3-coder-next": {
        "name": "🔬 Bench · Qwen3-Coder-Next (80B MoE)",
        "description": "Benchmark: Qwen3-Coder-Next-4bit (MLX, Alibaba, 80B MoE 3B active, ~46GB, 256K ctx — cold load ~60s)",
        "model_hint": "qwen3-coder:30b",
        "mlx_model_hint": "mlx-community/Qwen3-Coder-Next-4bit",
        "mlx_only": True,  # Hard-fail if MLX unavailable — no Ollama fallback during benchmark
    },
```

### bench-qwen3-coder-30b

**Before:**
```python
    "bench-qwen3-coder-30b": {
        "name": "🔬 Bench · Qwen3-Coder-30B",
        "description": "Benchmark: Qwen3-Coder-30B-A3B-8bit (MLX, Alibaba, 30B MoE 3B active, ~22GB)",
        "model_hint": "qwen3-coder:30b",
        "mlx_model_hint": "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit",
    },
```

**After:**
```python
    "bench-qwen3-coder-30b": {
        "name": "🔬 Bench · Qwen3-Coder-30B",
        "description": "Benchmark: Qwen3-Coder-30B-A3B-8bit (MLX, Alibaba, 30B MoE 3B active, ~22GB)",
        "model_hint": "qwen3-coder:30b",
        "mlx_model_hint": "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit",
        "mlx_only": True,  # Hard-fail if MLX unavailable — no Ollama fallback during benchmark
    },
```

### bench-llama33-70b

**Before:**
```python
    "bench-llama33-70b": {
        "name": "🔬 Bench · Llama-3.3-70B",
        "description": "Benchmark: Llama-3.3-70B-Instruct-4bit (MLX, Meta, ~40GB — cold load ~60s, plan for sequential runs)",
        "model_hint": "llama3.3:70b-q4_k_m",
        "mlx_model_hint": "mlx-community/Llama-3.3-70B-Instruct-4bit",
    },
```

**After:**
```python
    "bench-llama33-70b": {
        "name": "🔬 Bench · Llama-3.3-70B",
        "description": "Benchmark: Llama-3.3-70B-Instruct-4bit (MLX, Meta, ~40GB — cold load ~60s, plan for sequential runs)",
        "model_hint": "llama3.3:70b-q4_k_m",
        "mlx_model_hint": "mlx-community/Llama-3.3-70B-Instruct-4bit",
        "mlx_only": True,  # Hard-fail if MLX unavailable — no Ollama fallback during benchmark
    },
```

### bench-phi4

**Before:**
```python
    "bench-phi4": {
        "name": "🔬 Bench · Phi-4",
        "description": "Benchmark: phi-4-8bit (MLX, Microsoft, 14B, synthetic training data — distinct methodology)",
        "model_hint": "qwen3.5:9b",
        "mlx_model_hint": "mlx-community/phi-4-8bit",
    },
```

**After:**
```python
    "bench-phi4": {
        "name": "🔬 Bench · Phi-4",
        "description": "Benchmark: phi-4-8bit (MLX, Microsoft, 14B, synthetic training data — distinct methodology)",
        "model_hint": "qwen3.5:9b",
        "mlx_model_hint": "mlx-community/phi-4-8bit",
        "mlx_only": True,  # Hard-fail if MLX unavailable — no Ollama fallback during benchmark
    },
```

### bench-phi4-reasoning

**Before:**
```python
    "bench-phi4-reasoning": {
        "name": "🔬 Bench · Phi-4-reasoning-plus",
        "description": "Benchmark: Phi-4-reasoning-plus (MLX, Microsoft, RL-trained, ~7GB — produces reasoning traces before code)",
        "model_hint": "qwen3.5:9b",
        "mlx_model_hint": "lmstudio-community/Phi-4-reasoning-plus-MLX-4bit",
    },
```

**After:**
```python
    "bench-phi4-reasoning": {
        "name": "🔬 Bench · Phi-4-reasoning-plus",
        "description": "Benchmark: Phi-4-reasoning-plus (MLX, Microsoft, RL-trained, ~7GB — produces reasoning traces before code)",
        "model_hint": "qwen3.5:9b",
        "mlx_model_hint": "lmstudio-community/Phi-4-reasoning-plus-MLX-4bit",
        "mlx_only": True,  # Hard-fail if MLX unavailable — no Ollama fallback during benchmark
    },
```

### bench-dolphin8b

**Before:**
```python
    "bench-dolphin8b": {
        "name": "🔬 Bench · Dolphin-Llama3-8B",
        "description": "Benchmark: Dolphin3.0-Llama3.1-8B-8bit (MLX, Cognitive Computations, ~9GB — fast baseline, uncensored)",
        "model_hint": "dolphin-llama3:8b",
        "mlx_model_hint": "mlx-community/Dolphin3.0-Llama3.1-8B-8bit",
    },
```

**After:**
```python
    "bench-dolphin8b": {
        "name": "🔬 Bench · Dolphin-Llama3-8B",
        "description": "Benchmark: Dolphin3.0-Llama3.1-8B-8bit (MLX, Cognitive Computations, ~9GB — fast baseline, uncensored)",
        "model_hint": "dolphin-llama3:8b",
        "mlx_model_hint": "mlx-community/Dolphin3.0-Llama3.1-8B-8bit",
        "mlx_only": True,  # Hard-fail if MLX unavailable — no Ollama fallback during benchmark
    },
```

---

## Change 2: MLX-Only Filtering in `chat_completions()`

**Location:** `portal_pipeline/router_pipe.py`  
The block immediately after the "No healthy backends" HTTPException and immediately
before `if not stream:`. Find this exact anchor:

**Before:**
```python
        if not candidates:
            raise HTTPException(
                status_code=503,
                detail=(
                    "No healthy backends available. "
                    "Ensure Ollama is running and a model is pulled. "
                    "Check config/backends.yaml."
                ),
            )

        if not stream:
```

**After:**
```python
        if not candidates:
            raise HTTPException(
                status_code=503,
                detail=(
                    "No healthy backends available. "
                    "Ensure Ollama is running and a model is pulled. "
                    "Check config/backends.yaml."
                ),
            )

        # mlx_only workspaces (bench-*): restrict candidates to MLX backends only.
        # A benchmark with a silent Ollama fallback is worse than a hard failure —
        # the result would be attributed to the wrong model entirely.
        # The existing 300s _http_client timeout already covers cold model loads
        # (~60s for 40GB models), so no additional polling or retry logic is needed.
        # Streaming path: after filtering to one MLX backend, len(candidates)==1 takes
        # the single-candidate direct-stream path — _stream_or_fallback never runs.
        _ws_cfg_local = WORKSPACES.get(workspace_id, {})
        _mlx_only = _ws_cfg_local.get("mlx_only", False)
        if _mlx_only:
            candidates = [b for b in candidates if b.type == "mlx"]
            if not candidates:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        f"Workspace '{workspace_id}' requires an MLX backend — "
                        "none are currently healthy. "
                        "Ensure mlx-proxy is running: ./launch.sh status"
                    ),
                )

        if not stream:
```

---

## Change 3: Strict Hint Enforcement + Bench-Specific Failure Message

**Location:** `portal_pipeline/router_pipe.py`  
The non-streaming dispatch loop and its "All backends failed" block below it.

**Before:**
```python
            for i, backend in enumerate(candidates):
                is_last = i == len(candidates) - 1
                result = await _try_non_streaming(
                    backend, body, workspace_id, start_time, enforce_hint=not is_last
                )
                if result is not None:
                    resolved_model = backend.models[0] if backend.models else "unknown"
                    _record_response_time(
                        resolved_model,
                        workspace_id,
                        time.monotonic() - start_time,
                    )
                    _record_persona(persona, resolved_model)
                    _concurrent_requests.dec()
                    return result
            # All backends failed
            _record_error(workspace_id, "all_backends_failed")
            _concurrent_requests.dec()
            raise HTTPException(
                status_code=502,
                detail="All backends failed — check server logs",
            )
```

**After:**
```python
            for i, backend in enumerate(candidates):
                is_last = i == len(candidates) - 1
                # mlx_only: always enforce model hint — never substitute a different
                # model on the same backend. The benchmark result must be attributable
                # to exactly the model named in the workspace's mlx_model_hint.
                result = await _try_non_streaming(
                    backend, body, workspace_id, start_time,
                    enforce_hint=True if _mlx_only else (not is_last),
                )
                if result is not None:
                    resolved_model = backend.models[0] if backend.models else "unknown"
                    _record_response_time(
                        resolved_model,
                        workspace_id,
                        time.monotonic() - start_time,
                    )
                    _record_persona(persona, resolved_model)
                    _concurrent_requests.dec()
                    return result
            # All backends failed
            _record_error(workspace_id, "all_backends_failed")
            _concurrent_requests.dec()
            if _mlx_only:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        f"Benchmark workspace '{workspace_id}': target MLX model did not respond. "
                        "Large models (>30GB) require up to 60s to load on first use. "
                        "If you just switched models, wait for the load to complete and retry. "
                        "To verify: ./launch.sh logs | grep 'Switching to model'"
                    ),
                )
            raise HTTPException(
                status_code=502,
                detail="All backends failed — check server logs",
            )
```

---

## Acceptance Criteria

- [ ] `_mlx_only = True` is read from WORKSPACES for all 7 MLX bench workspaces
- [ ] `_mlx_only = False` (default) for all non-bench workspaces and `bench-glm` / `bench-gptoss`
- [ ] When `_mlx_only=True`: `candidates` contains only `type == "mlx"` backends
- [ ] When `_mlx_only=True` and no MLX backend is healthy: raises 503 with "requires an MLX backend" message
- [ ] When `_mlx_only=True` and MLX backend fails: raises 503 with "target MLX model did not respond" message, NOT 502 "All backends failed"
- [ ] When `_mlx_only=True`: `enforce_hint=True` is passed regardless of `is_last`
- [ ] Existing non-bench workspaces: behavior unchanged — `enforce_hint=not is_last` as before
- [ ] All unit tests pass: `pytest tests/ -q --tb=short`
- [ ] Ruff clean: `ruff check portal_pipeline/ && ruff format --check portal_pipeline/`

---

## Verification Commands

```bash
# 1. Confirm mlx_only set on all 7 MLX bench workspaces, absent on Ollama-only bench
python3 -c "
from portal_pipeline.router_pipe import WORKSPACES
mlx_bench  = [ws for ws, cfg in WORKSPACES.items()
               if ws.startswith('bench-') and cfg.get('mlx_model_hint')]
ollama_bench = [ws for ws, cfg in WORKSPACES.items()
                if ws.startswith('bench-') and not cfg.get('mlx_model_hint')]

for ws in mlx_bench:
    assert WORKSPACES[ws].get('mlx_only') is True, f'{ws} missing mlx_only=True'
for ws in ollama_bench:
    assert not WORKSPACES[ws].get('mlx_only'), f'{ws} should not have mlx_only'

print(f'MLX bench workspaces with mlx_only=True: {mlx_bench}')
print(f'Ollama bench workspaces (no mlx_only):   {ollama_bench}')
"

# 2. Confirm _mlx_only does not appear on any production workspace
python3 -c "
from portal_pipeline.router_pipe import WORKSPACES
leaks = [ws for ws, cfg in WORKSPACES.items()
         if not ws.startswith('bench-') and cfg.get('mlx_only')]
assert not leaks, f'mlx_only leaked onto production workspaces: {leaks}'
print('Production workspaces unaffected: OK')
"

# 3. Confirm the two Ollama bench workspaces are not in the mlx_only set
python3 -c "
from portal_pipeline.router_pipe import WORKSPACES
for ws in ('bench-glm', 'bench-gptoss'):
    assert ws in WORKSPACES, f'{ws} missing from WORKSPACES'
    assert not WORKSPACES[ws].get('mlx_only'), f'{ws} should not have mlx_only'
print('bench-glm and bench-gptoss correctly excluded from mlx_only: OK')
"

# 4. Workspace consistency check (Rule 6 from CLAUDE.md)
python3 -c "
import yaml
from portal_pipeline.router_pipe import WORKSPACES
cfg = yaml.safe_load(open('config/backends.yaml'))
pipe_ids = set(WORKSPACES.keys())
yaml_ids = set(cfg['workspace_routing'].keys())
assert pipe_ids == yaml_ids, f'Mismatch: pipe_only={pipe_ids-yaml_ids} yaml_only={yaml_ids-pipe_ids}'
print(f'Workspace IDs consistent: {len(pipe_ids)} total')
"

# 5. Unit tests
pytest tests/ -q --tb=short

# 6. Ruff
ruff check portal_pipeline/ && ruff format --check portal_pipeline/

# 7. Manual smoke test (requires running stack)
# In a fresh chat, select any bench MLX persona, then immediately send a message.
# The model will either respond (if already loaded) or wait up to 300s while it loads.
# It should NOT respond with content from an Ollama model.
# Verify the model used via pipeline logs:
./launch.sh logs | grep "Routing workspace=bench-"
# Expected: "Routing workspace=bench-* → 1 candidate(s)"
# (1 candidate confirms MLX-only filtering is active)
```

---

## Post-Implementation

```bash
./launch.sh restart portal-pipeline
# No reseed needed — this is a pipeline code change only, not a workspace/persona change
```

---

## Rollback Procedure

```bash
git checkout pre-bench-mlx-only -- portal_pipeline/router_pipe.py
./launch.sh restart portal-pipeline
```

---

## Execution Order

This task amends `portal_pipeline/router_pipe.py` which TASK-BENCH-001 also modifies.
Execute in this order:

1. **TASK-BENCH-001** — creates bench workspaces, personas, workspace JSONs
2. **TASK-BENCH-002 (this task)** — adds `mlx_only` to the entries created in step 1,
   then inserts the filtering and error-handling logic

If both tasks are run in a single Claude Code session, they can be batched into one
commit with the combined commit message below. If run separately, use individual commits.

---

## Commit Message (combined with TASK-BENCH-001)

```
feat(bench): add coding benchmark workspaces with MLX-only enforcement

Adds 9 bench-* workspace IDs (TASK-BENCH-001) and enforces hard-fail
MLX-only behavior on the 7 MLX variants (TASK-BENCH-002).

Workspaces added:
  MLX (mlx_only=True): bench-devstral, bench-qwen3-coder-next,
    bench-qwen3-coder-30b, bench-llama33-70b, bench-phi4,
    bench-phi4-reasoning, bench-dolphin8b
  Ollama only: bench-glm, bench-gptoss

Pipeline changes (router_pipe.py):
  - After candidate selection, filters to MLX-only backends when
    ws_cfg["mlx_only"] is True
  - Returns 503 immediately if no MLX backend is healthy
  - enforce_hint=True for all mlx_only backends (no is_last relaxation)
  - Returns bench-specific 503 with actionable message on MLX failure
  - Streaming path unaffected: single MLX candidate takes direct-stream
    path, _stream_or_fallback never runs

The existing 300s _http_client timeout covers cold model loads (~60s for
40GB models). No additional polling needed.

Companion personas (config/personas/bench_*.yaml) carry the Creative Coder
system prompt verbatim for identical behavioral framing across all models.

Closes: TASK-BENCH-001, TASK-BENCH-002
```
