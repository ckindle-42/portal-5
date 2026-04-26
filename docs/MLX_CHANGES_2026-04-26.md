# MLX Changes — 2026-04-26

## Upgrades Applied

| Package | Old | New | Notes |
|---------|-----|-----|-------|
| mlx (core) | 0.31.1 | 0.31.2 | Homebrew upgrade; Python bindings required manual copy of `core.cpython-314-darwin.so` and `nn/` modules from Cellar |
| mlx-lm | 0.31.1 | 0.31.2 | Adds gemma4 architecture support, Gemma4 KV-shared layer fixes, tool parser fixes |
| mlx-vlm | 0.4.4 | 0.4.4 | Latest; compatible with mlx 0.31.2 after core fix |

## Known Issues

### 1. mlx-lm 0.31.2 Server Puts Content in `reasoning` Field
- **Severity**: High — breaks content display in Open WebUI for all models
- **Symptom**: `mlx_lm.generate` CLI returns content correctly, but `mlx_lm.server` HTTP endpoint returns content in `message.reasoning` instead of `message.content`. Also affects SSE streaming: `delta.reasoning` instead of `delta.content`.
- **Root cause**: mlx_lm 0.31.2 server treats all models as reasoning models when emitting responses.
- **Fix applied**: Pipeline now promotes `reasoning` → `content` in both:
  - Non-streaming path: `router_pipe.py:2042` (already existed, verified working)
  - Streaming path: `router_pipe.py:3127` (newly added for MLX SSE pass-through)
- **Status**: Fixed in pipeline. Upstream mlx_lm server bug — report to ml-explore/mlx-lm.

### 2. Speculative Decoding Broken — `ArraysCache` Not Trimmable
- **Severity**: Medium — spec-decoding disabled, loses ~10-20% TPS on supported models
- **Symptom**: `ValueError: Speculative decoding requires a trimmable prompt cache (got {'ArraysCache'}).`
- **Root cause**: mlx_lm 0.31.2 changed default prompt cache from trimmable type to `ArraysCache`. Speculative decoding requires cache trimming to work.
- **Fix applied**: `config/backends.yaml` `speculative_decoding.draft_models` set to `{}` (disabled).
- **Affected models** (were using draft models): Qwen3-Coder-30B, DeepSeek-R1-Distill-Qwen-32B (both 4bit and 8bit), Jackrong/Qwopus3.5-27B, Jackrong/Qwen3.5-27B, Jackrong/Qwen3.5-35B, Llama-3.3-70B
- **Status**: Disabled. Re-enable when mlx_lm fixes cache compatibility.

### 3. Homebrew mlx 0.31.2 Python Bindings Incomplete
- **Severity**: High — `import mlx.core` fails after `brew upgrade mlx`
- **Symptom**: `ModuleNotFoundError: No module named 'mlx.core'` after upgrading mlx via Homebrew.
- **Root cause**: Homebrew formula links `.so` files via symlinks that break on Python 3.14. The Cellar has `core.cpython-314-darwin.so` and full `nn/` package, but site-packages only gets partial copies.
- **Fix applied**: Manual copy of missing files:
  ```
  cp /opt/homebrew/Cellar/mlx/0.31.2/lib/python3.14/site-packages/mlx/core.cpython-314-darwin.so /opt/homebrew/lib/python3.14/site-packages/mlx/
  cp -r /opt/homebrew/Cellar/mlx/0.31.2/lib/python3.14/site-packages/mlx/nn/ /opt/homebrew/lib/python3.14/site-packages/mlx/nn/
  cp -r /opt/homebrew/Cellar/mlx/0.31.2/lib/python3.14/site-packages/mlx/optimizers/ /opt/homebrew/lib/python3.14/site-packages/mlx/optimizers/
  cp -r /opt/homebrew/Cellar/mlx/0.31.2/lib/python3.14/site-packages/mlx/_distributed_utils/ /opt/homebrew/lib/python3.14/site-packages/mlx/_distributed_utils/
  ```
- **Status**: Fixed manually. Will break again on next `brew upgrade mlx`. Need a post-install script or use `pip install mlx` instead of Homebrew.

### 4. gemma4 Architecture Requires mlx-lm >= 0.31.2
- **Severity**: Low — only affects `divinetribe/gemma-4-31b-it-abliterated-4bit-mlx`
- **Symptom**: `ModuleNotFoundError: No module named 'mlx_lm.models.gemma4'` on mlx-lm 0.31.1
- **Status**: Resolved by upgrading to mlx-lm 0.31.2. Model loads and generates via `mlx_lm.generate`. Server path works with content-reasoning fix (#1 above).

## What Needs Fixing Upstream

1. **mlx_lm server**: Content should go in `message.content`, not `message.reasoning`, for non-reasoning models. File issue at ml-explore/mlx-lm.
2. **mlx_lm server**: `ArraysCache` needs to be trimmable or spec-decoding needs to work with non-trimmable caches. File issue at ml-explore/mlx-lm.
3. **Homebrew mlx formula**: Python bindings should be properly linked, not partially symlinked. File issue at Homebrew/homebrew-core.

## What Needs Fixing in Portal 5

1. **Post-brew-upgrade script**: Add a script to `/scripts/` that copies missing mlx Python bindings after Homebrew upgrades.
2. **Spec-decoding re-enable**: Monitor mlx_lm releases; re-enable `draft_models` when ArraysCache fix lands.
3. **Streaming reasoning→content**: The new code at `router_pipe.py:3127` is a hotfix. Clean up when mlx_lm server is fixed upstream.
