---
id: unit-known-limitations-acestep15-mlx-backend
kind: mixed
title: "Known Limitation — ACE-Step-1.5 MLX Backend Constraints (disabled)"
sources:
- type: code
  path: portal/modules/media/tools/music_ace_mcp.py
claims: []
confidence: high
tags: [known-limitations, music, apple-silicon]
created_at: 1787857994
updated_at: 1787872869
---

### ACE-Step-1.5 Disabled After Dual-Engine Comparison — Memory Ceiling, Non-Deterministic Vocal Captioning, Quality

- **ID**: P5-MUSIC-ACESTEP-001
- **Status**: **Disabled 2026-08-27** after `TASK_MUSIC_DUAL_BACKEND`'s `[GATE:
  SELECT ENGINE]` — the operator compared both engines on real 60s/30-step
  generations and kept MiniMax-Music3-MLX. `music_ace_mcp.py`, its install
  function, and its tools manifest are untouched in the repo (module built to
  share zero code with MiniMax's, per the dual-backend task's modularity
  contract); only fleet registration and `auto-music` wiring were removed. The
  downloaded checkpoints (~14GB) and both launchd services were removed from
  this host. See `config/portal.yaml`'s `mcp_fleet` comment for the exact
  removal record.
- **Description**: `music_ace_mcp.py` proxies to a separate ACE-Step-1.5 API
  server. Three real findings from the live comparison:
  1. **Memory ceiling is structural, not transient.** Once ACE-Step's model is
     loaded, its own resident footprint (~23GB) plus its admission
     requirement (~44GB free) exceeds this machine's 64GB total — it cannot
     pass its own admission check for a second job without being unloaded
     first, even with the entire rest of the stack (Docker, ComfyUI, MLX
     services) shut down. The first job in a session succeeds only if enough
     is freed beforehand; a follow-up job (e.g. a repaint) on the same
     resident model cannot.
  2. **The LM "thinking"/captioning stage is non-deterministic per call and
     can contradict the prompt.** Two identical-prompt/lyrics runs, one
     requesting "energetic female vocal," produced captions of "a powerful
     female lead vocal" and "a powerful, clean male vocal performance"
     respectively. ACE-Step's own API supports `seed`/`use_random_seed` for
     reproducibility; `ace_generate` does not yet expose them (unlike
     MiniMax's tool, which does).
  3. **Output quality did not hold up against MiniMax** in the operator's own
     listening comparison, independent of the audio-format issue below.
  Separately (unrelated to the disable decision): upstream issue #995
  documents an MLX DiT bug specific to the XL/4B model size; this deployment
  defaulted to the non-turbo 2B `acestep-v15-sft`, out of scope for that bug.
  The engine and proxy ran as two separate launchd processes.
- **Impact**: None currently — the module is disabled and not reachable from
  any workspace. If re-enabled: XL/4B overrides may fail on MLX until #995 is
  fixed; a second job on an already-loaded model will likely be refused by
  the admission gate on any host with less than ~67GB RAM; vocal
  gender/character will vary between identical-prompt runs unless a seed
  parameter is added to `ace_generate` first.
- **Mitigation to re-enable**: `./launch.sh install-music-ace` (re-clones and
  re-downloads the ~14GB checkpoint set), re-add the `music-ace` fleet entry
  and `ace_*` tools to `auto-music` in `config/portal.yaml` (both were left as
  inline comments/history at removal, not deleted outright), remove
  `portal_music_ace` from `scripts/update_workspace_tools.py`'s
  `DEAD_SERVERS`. Consider adding seed support first, matching MiniMax's tool,
  to make future A/B comparisons reproducible.
- **Note**: ACE-Step-1.5 is MIT-licensed.

## Why

The two-process failure mode, the memory-ceiling math, and the non-deterministic
captioning are specific to this integration and this hardware, not general
ACE-Step documentation — recording them here gives a future operator (or a
future re-enable attempt) the actual reason this was shelved instead of a bare
"disabled" with no rationale, and a concrete list of what to fix before
re-evaluating.
