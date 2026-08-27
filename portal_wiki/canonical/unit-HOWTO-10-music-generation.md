---
id: unit-HOWTO-10-music-generation
kind: why
title: "HOWTO — 10. Music Generation"
sources:
- type: code
  path: portal/modules/media/tools/music_minimax_mcp.py
- type: code
  path: scripts/lib/services.sh
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1783195000.8455648
updated_at: 1787872869
---

**What:** Generate full songs — with lyrics/vocals or instrumental — from text descriptions, using MiniMax-Music3-MLX.

**Activate:** Select `Music Producer` (`auto-music`). MiniMax's tools — `minimax_generate`/`minimax_status`/`minimax_models`, plus speech/transcription tools — are granted by `auto-music`'s `tools` list.

**How:** MiniMax runs in-process in `music_minimax_mcp.py` (port 8912) via the vendor's MLX pipeline. Generation is job-based: call `minimax_generate` for a `job_id`, then poll `minimax_status(job_id)` until done. The complete-quality default is 60 seconds / 30 steps. Lyrics use `[Verse]`/`[Chorus]` tags or `[Instrumental]`. MiniMax has no clip-editing/continuation capability (see `unit-known-limitations-minimax-music3-mlx`).

**What changed:** MusicGen was removed (`TASK_MUSIC_DUAL_BACKEND`) and replaced with two independent engines, MiniMax-Music3-MLX and ACE-Step-1.5, installed side by side for an operator comparison. After real 60s/30-step generations on both — including lyrics/vocals and an ACE repaint — the operator's `[GATE: SELECT ENGINE]` decision (2026-08-27) kept MiniMax and disabled ACE-Step: ACE's own resident footprint plus its admission requirement exceeded this machine's 64GB total once loaded (a structural ceiling, not a fluke), its LM captioning stage was non-deterministic and once contradicted the requested vocal gender, and its output quality did not hold up against MiniMax's in a direct listen. ACE-Step's module code (`music_ace_mcp.py`), install function, and tools manifest remain in the repo, unwired, for a possible future re-enable — see `unit-known-limitations-acestep15-mlx-backend` for the full finding and what re-enabling would take.

## Why

MiniMax runs in-process because its footprint (~27GB measured) comfortably coexists with the rest of the live stack. Job polling exists because complete-quality generation takes minutes. The disabled ACE-Step module was kept rather than deleted specifically so a future re-evaluation (e.g. after upstream fixes the captioning non-determinism, or hardware with more RAM) doesn't require rebuilding it from scratch.
