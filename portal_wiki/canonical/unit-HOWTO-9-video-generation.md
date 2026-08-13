---
id: unit-HOWTO-9-video-generation
kind: why
title: "HOWTO \u2014 9. Video Generation"
sources:
- type: code
  path: config/portal.yaml
last_generated_commit: 75c5054f791636f367b62a1776bcc9f631794766
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1783195000.845109
updated_at: 1783195000.845109
---

**Shelved (2026-07-29):** Video generation is not currently in operation.

Wan 2.2's `fp8_scaled` checkpoints (T2V-A14B, S2V-14B) crash on this host's Apple Silicon MPS stack — see `KNOWN_LIMITATIONS.md`, "Wan 2.2 fp8_scaled Checkpoints Crash on Apple Silicon MPS." TI2V-5B alone does work but was not judged worth exposing on its own. The `auto-video` workspace remains defined in `config/portal.yaml` with `expose_to_owui: false` so it stays hidden from the model dropdown, and the `mcp-video` container is profile-gated out of the default `./launch.sh up` set. Only image generation (`auto-image`, the ComfyUI MCP) is in operation.

The code path is left in place, not deleted, in case this becomes viable later — the `KNOWN_LIMITATIONS.md` entry lists what would need to change. `./launch.sh pull-wan22` still exists as an archival download command but must not be treated as enabling video operation.

## Why

Shelving rather than deleting preserves an operational option at near-zero cost: the workspace, the ComfyUI workflows, and the pull commands are tested code that only lacks a viable MPS checkpoint. Keeping `expose_to_owui: false` and the compose profile gate means the shelf stays literal — nothing video-facing is advertised to users, so the documented posture cannot silently rot into a half-working feature.
