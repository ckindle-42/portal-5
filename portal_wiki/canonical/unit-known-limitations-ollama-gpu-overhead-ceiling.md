---
id: unit-known-limitations-ollama-gpu-overhead-ceiling
kind: what
title: "KNOWN_LIMITATIONS — Ollama GPU overhead reservation (resolved)"
sources:
- type: code
  path: scripts/lib/util.sh
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1786393800.0
updated_at: 1786393800.0
---

- **ID**: P5-OLLAMA-GPU-OVERHEAD-001
- **Status**: Resolved 2026-08-10 (TASK-BATCH-BENCH-002 Part A). Not a bug in Ollama or the fleet — a misconfigured safety margin, corrected in place.
- **Description**: `com.portal5.ollama.plist`'s `OLLAMA_GPU_OVERHEAD` was set to `42949672960` (40GiB), intended as coexistence headroom so Ollama and oMLX never collide and crash the box on this 64GB M4 Pro. In practice this overhead is subtracted from a largely fixed Metal working-set ceiling (~56GiB on this hardware), not from live free memory — freeing oMLX's loaded models and even a full daemon restart left Ollama's reported "available" figure completely unchanged (`model requires 19.7 GiB but only 15.5 GiB are available (after 40.5 GiB overhead)`). At 40GiB, the reservation capped **any single Ollama model at ~15.5GiB regardless of oMLX's actual state** — a real problem, since the fleet already runs 20-30GB-class models (Muse-Glimmer-30B, Deepwen-3.6, Qwen3-Coder-30B-A3B) routinely.
- **Fix**: lowered to `21474836480` (20GiB) in the plist, reloaded via `sudo launchctl bootout system/com.portal5.ollama && sudo launchctl bootstrap system /Library/LaunchDaemons/com.portal5.ollama.plist` (note: `launchctl kickstart -k` restarts the process but does **not** re-read the plist's `EnvironmentVariables` — a full bootout/bootstrap is required to pick up an env change). 20GiB still reserves real coexistence headroom (sized off oMLX's own observed footprint, ~22-29GB for its largest single models) without starving Ollama's own budget down to a sliver. Verified: Muse-Glimmer-30B (19.7GiB) loads cleanly post-fix.
- **If this recurs**: check `ps eww -p <ollama-serve-pid> | grep OLLAMA_GPU_OVERHEAD` against the current plist value first — a mismatch means the daemon needs a full bootout/bootstrap, not just a kickstart.

## Why

This is a permanent, box-level constraint that silently caps every future large-model bench on this host, not something scoped to the Muse-Glimmer bench that surfaced it. The kickstart-vs-bootstrap distinction is the actual gotcha (identical-looking "restart" commands, only one re-reads env vars) — a future session hitting the same static "N GiB available" error after changing an Ollama plist env var should find this before re-diagnosing it as a stale-cache or live-memory problem again.
