# Image module install — orchestrator runbook (pinned, arm64-native)

Everything here runs on the host (Apple Silicon). Nothing is auto-enabled:
`modules.image.enabled` stays `false` until step 4.

## 1. Install the MCP (pinned)

```bash
./launch.sh install-mflux
```

What it does (all inside `scripts/lib/services.sh:_launch_install_mflux`):

- Fails unless `uname -m` is `arm64` (Rule 14; no CPU/CUDA fallback).
- Picks a Python ≥ 3.11 (`python3.13` → `3.12` → `3.11` → `python3`; override with
  `MFLUX_PYTHON=`), because `mflux 0.24.0` requires ≥ 3.11 and the system `python3`
  may be 3.10.
- Creates `~/.portal5/mflux/.venv` and installs **`mflux==0.24.0`** (exact pin;
  pulls `pillow>=13.0.0` for GHSA-5x8w-8jj5-q52h, `mlx>=0.32.0,<0.33.0` on darwin)
  plus the MCP service deps (fastapi/uvicorn/httpx/pyyaml/starlette/mcp).
- Verifies before starting: `mflux` imports, `Pillow >= 13.0`, `platform.machine() == arm64`.
- Writes `~/.portal5/mflux/start.sh` (exports `MFLUX_BIN=$MX_VENV/bin/mflux-generate`,
  `MFLUX_FLUX2_BIN`, `MFLUX_MCP_PORT=8933`, sources repo `.env`) and registers
  launchd `com.portal5.mflux` (KeepAlive). Family binaries derive from
  `MFLUX_BIN`'s dirname — `mflux-generate-flux3`, `mflux-generate-flux3-edit`,
  `mflux-generate-qwen-2.1`, `mflux-generate-qwen-2.1-edit`,
  `mflux-generate-z-image-turbo`.

Optional env (set in `.env` before install or exported into launchd via start.sh edit):
`MFLUX_COMPUTE_PRECISION` (default `float16`; set empty to keep model precision),
`MFLUX_TIMEOUT` (default 900), `HF_HOME` (weight cache root).

## 2. Pull the model weights (per family binary)

```bash
./launch.sh pull-mflux-models
```

| Roster key | Tag | Binary | Expected upstream pull |
|---|---|---|---|
| `flux2-klein` (default) | `flux2-klein-4b` | `mflux-generate-flux2` | ~15 GB (Apache 2.0) |
| `flux3-klein` | `flux3-image-klein` | `mflux-generate-flux3` | ~20 GB (Kommunity license — accept + `hf auth login` first; gated repo) |
| `qwen-2.1` | `qwen-image-2.1-turbo` | `mflux-generate-qwen-2.1` | ~33 GB (Qwen Research license) |
| `z-image` (fallback) | `z-image-turbo` | `mflux-generate-z-image-turbo` | ~21 GB (Apache 2.0) |

Total ~89 GB one-time upstream bf16; `-q 8` loads the smaller pre-quantized
`mflux-community/*-mflux-q8` repos where they exist. Pull one at a time to keep
the box quiet. Override the list with `MFLUX_PULL_MODELS="tag:binary …"`.

Verify after pulling:

```bash
~/.portal5/mflux/.venv/bin/mflux-generate-flux2 --model flux2-klein-4b --prompt "smoke" \
  --steps 4 --quantize 8 --low-ram --width 512 --height 512 --seed 1 \
  --output /tmp/mflux_smoke.png --no-metadata && file /tmp/mflux_smoke.png
```

Expect: exit 0 and a PNG; `mflux:<tag>` logs show which weights loaded.

## 3. Readiness (no enable yet)

```bash
curl -s localhost:8933/health
```

Expect `{"status":"ok","service":"mflux-generation","models":["flux2-klein","flux3-klein","qwen-2.1","z-image"]}`.

## 4. Enable + expose (operator decision)

```bash
uv run portal module enable image --yes   # writes modules.image.enabled: true
./launch.sh sync-config                   # regenerates workspace presets (writes repo files only)
docker exec portal5-pipeline grep -n "auto-audio" /app/config/portal.yaml >/dev/null  # baked config check
./launch.sh rebuild && ./launch.sh up     # config/portal.yaml is baked into the Pipeline image
./launch.sh seed                          # creates the auto-audio::image OWUI preset
```

## 5. Live proof

```bash
uv run portal trace --section media --timeout 600
```

- `image module` hop WARNs with "modules.image.enabled is false" while disabled (expected now).
- After step 4 it runs a real `auto-audio::image` OWUI turn (512×512 red circle),
  then `image artifact` PASS only if the reply's `/api/v1/files/<id>/content/<name>`
  URL returns HTTP 200 with bytes, and `owui route trace` PASS on `tool_calls>=1`.

Manual: in OWUI, prompt `auto-audio::image` with "Generate a 1024x1024 cyberpunk
workshop sign reading 'PORTAL 5'" — expect `image_start` → job id, one or two
`image_status` long-polls to `done` (~20–60s), and a working download link backed
by a file under `${AI_OUTPUT_DIR}/generated/images/`.
