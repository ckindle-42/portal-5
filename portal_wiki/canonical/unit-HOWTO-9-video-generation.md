---
id: unit-HOWTO-9-video-generation
kind: why
title: "HOWTO \u2014 9. Video Generation"
sources:
- type: design
  path: docs/HOWTO.md
  section: 9. Video Generation
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.845109
updated_at: 1783195000.845109
---


**Shelved (2026-07-29):** Video generation is not currently in operation.
Wan 2.2's `fp8_scaled` checkpoints (T2V-A14B, S2V-14B) crash on this host's
Apple Silicon MPS stack — see `KNOWN_LIMITATIONS.md`, "Wan 2.2 fp8_scaled
Checkpoints Crash on Apple Silicon MPS." TI2V-5B alone does work, but wasn't
judged worth exposing on its own. The `auto-video` workspace is defined in
`config/portal.yaml` (`expose_to_owui: false`) but hidden from the model
dropdown, and the `mcp-video` container is stopped. Only **image** generation
(`Portal Image Creator`) is in operation — see the Image Generation section.

The code path is left in place, not deleted, in case this becomes viable
later (see the KNOWN_LIMITATIONS entry for what would need to change).
