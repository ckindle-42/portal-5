---
id: unit-known-limitations-acestep15-mlx-backend
kind: mixed
title: "Known Limitation — ACE-Step 1.5 XL-Turbo is unproven live"
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

### ACE-Step 1.5 XL-Turbo — Apple Silicon only, not yet proven on this host

- **ID**: P5-MUSIC-ACESTEP-001
- **Status**: The 2026-08-27 dual-daemon deployment (2B `acestep-v15-sft`, `music_ace_mcp.py` plus `acestep-api`, ports 8933/8934) is retired. Those files and launchd labels are gone. The replacement is one MCP (`music_mcp.py`, port 8912) that spawns ACE-Step 1.5 XL-Turbo (`use_mlx_dit`, LM backend `mlx`) per job. `modules.music.enabled` stays false.
- **Description**: Install is `./launch.sh install-music`, which pins `ace-step/ACE-Step-1.5` at `ca1e85fe9430179831e6bc6be790c332190a3866` and refuses non-arm64. Admission uses `music:acestep-xl-turbo` = 16 GB plus headroom. That figure is a research estimate, not a live sample. XL-Turbo download size cited for the installer is about 18.8 GB for `ACE-Step/acestep-v15-xl-turbo`; the LM and core-bundle sizes are not pinned. `mlx-audio==0.6.6` is installed into the same venv for the MiniMax fallback and has not been proven to coexist with the locked torch/mlx pins. No extra int8 quantization is applied.
- **Impact**: Until the orchestrator installs, enables, and generates a wav, this engine produces nothing. A host that is not arm64 cannot run it.
- **Mitigation**: Keep the module disabled until `portal trace --section media --timeout 900` reads back a published wav URL (200 + bytes) and idle RSS drops after the child exits.

## Why

The old two-process memory ceiling was specific to the 2B sft deployment and is not a measurement of this subprocess path. Recording both the retirement and the unproven replacement keeps an operator from treating the research table as a live result.
