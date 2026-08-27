---
id: unit-known-limitations-acestep15-mlx-backend
kind: mixed
title: "Known Limitation — ACE-Step-1.5 MLX Backend Constraints"
sources:
- type: code
  path: portal/modules/media/tools/music_ace_mcp.py
claims: []
confidence: high
tags: [known-limitations, music, apple-silicon]
created_at: 1787857994
updated_at: 1787857994
---

### ACE-Step-1.5 XL/4B MLX Bug Out of Scope; Two-Process Architecture

- **ID**: P5-MUSIC-ACESTEP-001
- **Description**: `music_ace_mcp.py` proxies to a separate ACE-Step-1.5 API server. Upstream issue #995 documents an MLX DiT bug specific to XL/4B. This deployment defaults to non-turbo 2B `acestep-v15-sft`. Engine and proxy are separate launchd processes.
- **Impact**: XL/4B overrides may fail on MLX until the issue is fixed. If the engine dies, proxy tools report connection errors until launchd restarts it.
- **Mitigation**: Do not select XL/4B until #995 is confirmed fixed. `./launch.sh status` reports both processes; inspect `~/.portal5/logs/acestep-server.log` for engine failures.
- **Note**: ACE-Step-1.5 is MIT-licensed.

## Why

The two-process failure mode is specific to this integration and belongs in this repository's limitations register. Recording it separately from upstream model constraints gives operators a direct way to distinguish a proxy connection problem from a generation failure and avoids escalating routine launchd recovery into model debugging.
