# MEDIA MLX Acceptance — TASK_IMAGE_VIDEO_OVERHAUL_V1

**Date:** 2026-08-28
**Host:** Apple Silicon M4 Pro, 64 GB unified memory (host-native MLX layer)
**Nature:** functional acceptance, not a comparison — the ComfyUI incumbent is
broken on Metal (FP8 unsupported, Wan2.2 ~82 min / 2 s, LTX-2 NaN on MPS), so
there is nothing to bench against. Each arm records wall-clock, peak MLX memory,
and a usable / not-usable verdict.

All image runs: `--quantize 8 --low-ram`, 1024×1024, seed 1. Same
`mflux-generate` / `mflux-generate-flux2` CLI path the `mflux_mcp.py` server
shells out to.

## Track A — Image (MFLUX) — GO (schnell + klein)

| Arm | CLI model | steps | wall | peak MLX | verdict |
|---|---|---|---|---|---|
| `schnell` | `mflux-generate` | 4 | 67 s cached (344 s incl. one-time pull) | 14.5 GB | ✅ **usable** — clean photoreal mug-on-desk |
| `klein` | `mflux-generate-flux2` | 28 | ~30 s gen | 18.0 GB | ✅ **usable** — sharp studio-lit mug, strong material rendering |
| `qwen-image` | `mflux-generate-qwen` | 8 | ~135 s denoise | **36.8 GB** | ✅ **usable** — bookshop storefront with crisp, legible "GRAND OPENING" text; the text-rendering arm |
| `z-image` | `mflux-generate-z-image-turbo` | 8 | ~2 min | **26.8 GB** | ✅ **usable** — sharp red mug on wood, softbox visible, strong studio lighting |

**All four image arms produce usable output within the 64 GB envelope.**
qwen-image (36.8 GB) and z-image (26.8 GB) are heavier — the admission table
reflects the measured peaks so an oversized co-resident job is refused.

Without `--low-ram`, `schnell` peaks ~25 GB MLX vs 14.5 GB with it.

**Root cause of the earlier qwen/z-image failures (fixed):** mflux 0.19 ships a
separate entry-point binary per model family (`mflux-generate-qwen`,
`mflux-generate-qwen-edit`, `mflux-generate-z-image-turbo`, `mflux-generate-flux2`);
routing a non-FLUX.1 model through the base `mflux-generate` silently falls back to
the FLUX weight loader, which then dies looking for a `text_encoder_2/`.
`mflux_mcp.py` now dispatches to the right family binary per model.

## Track B — Video (ltx-2-mlx / LTX-2.3) — GO (proven, off by default)

Package: `dgrauet/ltx-2-mlx` v0.15.1 (pure MLX, no torch runtime). Server:
`video_mlx_mcp.py` with `@mcp.tool()` `generate_video` / `animate_image`, `video`
M7 module **off by default**, fleet id `video_mlx` :8935 (`default_enabled:
false`), `install-video-mlx` / `pull-video-mlx-models` commands.

`ltx-2-mlx info` estimated ~72 GB RAM for the q4 pack, but that is the
all-transformers-resident figure — with `--low-ram` block-streaming the real
peak is far lower:

| Arm | mode | res / frames | wall | peak footprint | verdict |
|---|---|---|---|---|---|
| `ltx-2.3-q4` | `--distilled --low-ram` | 512×320 / 97 (~4.04 s, +audio) | ~95 s gen (237 s incl. 141 s one-time Gemma text-encoder pull) | **16.0 GB** (max RSS 13.0 GB) | ✅ **usable** — recognizable storm-cloud city skyline, cinematic lighting, matches prompt; preview-grade (foreground detail is loose). Ran concurrently with an MFLUX job and still fit. |

Well inside the 64 GB envelope. Distilled two-stage: stage-1 denoise 8 steps
(~38 s), stage-2 upscale+refine 3 steps (~42 s), VAE+audio decode ~5 s.

## Disposition — both media proven; ComfyUI removed entirely

1. **Image — GO, live.** MFLUX MCP running on :8933 (launchd), `/health` green.
   `auto-image` (`expose_to_owui: true`) + `auto-vision` repointed to
   `generate_image` / `edit_image`. schnell + klein produce usable output at
   14.5 / 18.0 GB peak.
2. **Video — GO, proven, off by default.** LTX-2.3 q4 `--distilled --low-ram`
   produces a usable 4 s clip (with audio) at **16 GB peak** — comfortably
   inside the envelope; the `info` tool's 72 GB figure was pessimistic.
   `video_mlx` is a real M7 module kept **off by default** for footprint (heavy,
   thermally punishing, ~95 s/clip, preview-grade). `auto-video` is repointed to
   `generate_video` / `animate_image`, `expose_to_owui: false` until an operator
   runs `./launch.sh install-video-mlx` + `portal module enable video`.
3. **ComfyUI removal — done.** The whole subsystem — `comfyui_mcp.py`,
   `video_mcp.py`, `gen-image/video.py`, the compose `comfyui` profile +
   model-init, `install-comfyui` / `pull-wan22` / `pull-qwen-image` /
   `download-comfyui-models`, `comfyui:*` / `video:*` admission keys,
   `tests/comfyui/`, the OWUI comfyui/video tools, ~30 `unit-comfyui-*` wiki
   units, `docs/COMFYUI_SETUP.md` — is removed. Model weights on disk left for a
   separate operator reclaim decision.
4. **qwen-image / z-image — fixed.** Root cause was mflux 0.19's per-family
   entry-point binaries (`mflux-generate-qwen` etc.); `mflux_mcp.py` now
   dispatches correctly. All four image models verified usable.

`validate_system.py`: 195 pass / 1 fail / 1 warn. The fail is `H. unit test
suite` — pre-existing: `validate_system.py` shells out to Homebrew `python3`
(3.14) whose numpy is compiled for 3.13. Unrelated to this task; the unit suite
passes clean under `uv run` (1093 passed).

Pre-existing bug noted in passing (not fixed, out of scope): `tests/acceptance/
s02_services.py` line 87 uses `MCP["music"]` where the dict key is
`music_minimax`.
