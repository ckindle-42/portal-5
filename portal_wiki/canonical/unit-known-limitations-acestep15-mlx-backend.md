---
id: unit-known-limitations-acestep15-mlx-backend
kind: mixed
title: "Known Limitation — ACE-Step 1.5 XL-Turbo: Apple Silicon only, tight memory envelope"
sources:
- type: code
  path: portal/modules/media/tools/music_mcp.py
claims:
- probe: repo.path.exists
  path: portal/modules/media/tools/music_mcp.py
  equals: true
confidence: high
tags: [known-limitations, music, apple-silicon]

---

### ACE-Step 1.5 XL-Turbo — Apple Silicon only, tight memory envelope

- **ID**: P5-MUSIC-ACESTEP-001
- **Status**: The 2026-08-27 dual-daemon deployment (2B `acestep-v15-sft`, `music_ace_mcp.py` plus `acestep-api`, ports 8933/8934) is retired. Those files and launchd labels are gone. The replacement is one MCP (`music_mcp.py`, port 8912) that spawns ACE-Step 1.5 XL-Turbo (`use_mlx_dit`, LM backend `mlx`) per job. The engine is installed on this host and proven live: the 2026-11-19 media trace (`portal trace --section media`) generated a wav end-to-end, with system free memory falling to ~22% at the peak. Live enablement is `unit-fact-module-states`, not this unit.
- **Description**: Install is `./launch.sh install-music`, which pins `ace-step/ACE-Step-1.5` at `ca1e85fe9430179831e6bc6be790c332190a3866` and refuses non-arm64. Admission uses `music:acestep-xl-turbo` = 16 GB plus headroom. That figure is a research estimate, not a live sample. XL-Turbo download size cited for the installer is about 18.8 GB for `ACE-Step/acestep-v15-xl-turbo`; the LM and core-bundle sizes are not pinned. `mlx-audio==0.6.6` is installed into the same venv for the MiniMax fallback and has not been proven to coexist with the locked torch/mlx pins. No extra int8 quantization is applied.
- **Impact**: A host that is not arm64 cannot run it, and a song job squeezes the box — the 2026-11-19 trace peaked with system free memory at ~22%.
- **Mitigation**: Re-prove after any engine or admission change with `portal trace --section media --timeout 900` (published wav URL, 200 + bytes, idle RSS drops after the child exits), and keep large Ollama residents unloaded around a song job (`unit-HOWTO-media-memory-and-launch-order`).

## Why

The old two-process memory ceiling was specific to the 2B sft deployment and is not a measurement of this subprocess path. Recording both the retirement and the measured envelope keeps an operator from treating the research admission table as a live result — or the dated trace figure as a guarantee.
