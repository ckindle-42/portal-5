# Video Module Install Recipe — pinned, arm64-native (orchestrator-run)

The video module's engines are host-native MLX installs (Rule 14: arm64 only —
there is no CPU/CUDA fallback and no Docker-to-Metal bridge). Nothing here runs
during development; the orchestrator runs these commands against the live host
and reads the verify lines. Sizes are measured from the HuggingFace API on
2026-11-18.

## Primary engine — `dgrauet/ltx-2-mlx` (LTX-2.5)

Pin: release tag **v0.18.0** (published 2026-10-23). Deps are pinned by the
upstream `uv.lock` that `uv sync --all-extras --frozen` resolves.

```bash
VX_DIR="$HOME/.portal5/video-mlx"; VX_SRC="$VX_DIR/ltx-2-mlx"
command -v uv >/dev/null || { echo "install uv first"; exit 1; }
command -v ffmpeg >/dev/null || echo "WARN: ffmpeg missing (brew install ffmpeg)"
[ "$(uname -m)" = "arm64" ] || { echo "not arm64"; exit 1; }
git clone --depth 1 --branch v0.18.0 https://github.com/dgrauet/ltx-2-mlx.git "$VX_SRC"
cd "$VX_SRC" && uv sync --all-extras --frozen
"$VX_DIR/ltx-2-mlx/.venv/bin/python" -m pip install --quiet \
  "mcp>=2.0.0,<3.0.0" "starlette>=1.3.0" "httpx>=0.26.0" "pyyaml>=6.0.1"
```

Model pack (expected download ≈ **51 GB**, measured 50.7 GB):

```bash
./launch.sh pull-video-mlx-models    # ltx-2-mlx info --model dgrauet/ltx-2.5-mlx-q4
```

Verify (each line must print the stated value):

```bash
uname -m                                   # arm64
file "$VX_SRC/.venv/bin/python" | grep -o arm64   # arm64 (not x86_64/Rosetta)
"$VX_SRC/.venv/bin/python" -c "import ltx_pipelines_mlx; print('ok')"   # ok
"$VX_SRC/.venv/bin/ltx-2-mlx" generate --help | grep -o -- --two-stage   # --two-stage
```

TeaCache is intentionally not exposed: upstream raises on LTX-2.5 packs
(`--enable-teacache` is calibrated for 2.3 only). `quality="hq"` maps to
`--two-stage`; `quality="fast"` maps to `--distilled`.

Optional speed env (upstream opt-in, unset by default; upstream measured a
701s → 563s I2V render on an M1 Max with the 2.5 q8 pack):
`export LTX2_COMPUTE_DTYPE=float16` in the service env before starting.

## Fallback engine — `mlx-video` Wan2.2-TI2V-5B Q8 (opt-in)

Pin: Blaizzy/mlx-video has no tags; pin commit **87db56a5** (main tip,
2026-11-18). Pack `Anes1032/Wan2.2-TI2V-5B-mlx-q8` (Apache-2.0), expected
download ≈ **20 GB** (19.6 GB). One command does install + download + env:

```bash
./launch.sh install-video-mlx wan
```

Verify:

```bash
"$VX_SRC/.venv/bin/mlx_video.wan_2.generate" --help | head -3    # usage text
grep VIDEO_MLX_WAN_MODEL_DIR "$VX_DIR/start.sh"                  # export line present
du -sh "$VX_DIR/wan2.2-ti2v-5b-q8"                               # ≈ 20G
```

`mlx-video`'s `--model-dir` takes a locally converted MLX dir (the installer
materializes it and exports `VIDEO_MLX_WAN_MODEL_DIR`). Its CLI has no fps
flag and the Wan pipeline writes silent MP4s; the MCP omits fps and reports
`audio: false` for this engine in `video_models()`.

## Service + module (after either engine)

```bash
./launch.sh install-video-mlx       # registers com.portal5.video-mlx (launchd)
portal module enable video          # flips modules.video.enabled
./launch.sh sync-config             # regenerates presets/routing (host: writes repo files too)
./launch.sh rebuild && ./launch.sh up
```

## Size summary

| Item | Size | Notes |
|---|---|---|
| ltx-2-mlx v0.18.0 source + venv | < 1 GB | uv.lock-pinned deps |
| `dgrauet/ltx-2.5-mlx-q4` pack | 50.7 GB | dev + distilled transformer + Gemma-4 text tower |
| `mlx-video` @ 87db56a5 | < 200 MB | pip install from git |
| `Anes1032/Wan2.2-TI2V-5B-mlx-q8` | 19.6 GB | transformer 5.4 + T5 11.4 + VAE 2.8 |
| Peak working set while rendering | 18–26 GB (LTX est.), ~23 GB (Wan est.) | admission keys in `_admission.py` |
