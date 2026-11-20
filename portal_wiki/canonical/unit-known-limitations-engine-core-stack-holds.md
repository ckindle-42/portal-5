---
id: unit-known-limitations-engine-core-stack-holds
kind: what
title: Media engine core stacks hold at installed versions; remaining advisories need a deliberate engine bump
sources:
- type: code
  path: scripts/engine_install_plan.py
claims:
- probe: repo.symbol.exists
  path: scripts/engine_install_plan.py
  symbol: build_plan
  equals: true
- probe: repo.symbol.exists
  path: scripts/lib/services.sh
  symbol: _engine_dep_plan
  equals: true
confidence: high
tags:
- known-limitations
- security
- dependencies

---

- **ID**: P5-ENGINE-CORE-001
- **Status**: OPEN. Recorded 2026-11-19 from the round-3 installer run and a resolve reproduction against scratch copies of the three engine venvs.
- **Description**: The music, mflux and video-mlx installers hold each engine's core stack (torch, transformers, diffusers, huggingface-hub, numpy, mlx*) at the versions `uv pip freeze` reports for that venv, and apply sweep fixes only where the flagged version is the one installed there. The advisories the sweep flags against the held core therefore remain open until an operator deliberately bumps the engine: music holds `torch==2.10.0` (`GHSA-rrmf-rvhw-rf47`, fixed 2.13.0) and `transformers==4.57.6` (`GHSA-xrqw-3rrv-vx5w` / `PYSEC-2026-3929`, fixed 5.10.0); video-mlx holds `transformers==5.3.0` (same advisory, fix 5.10.0). mflux holds nothing vulnerable (torch 2.13.0 and transformers 5.16.1 already satisfy the fixes). Music additionally holds `mlx==0.30.6` from the ACE-Step lock, which contradicts the `mlx-audio==0.6.6` MiniMax fallback (requires `mlx>=0.32.4`): the installer refuses it loudly and leaves the fallback uninstalled.
- **Used by Portal**: yes. `scripts/engine_install_plan.py` builds each installer's pip plan; `scripts/lib/services.sh` applies it for `install-music`, `install-mflux` and `install-video-mlx`.
- **Mitigation**: an operator picks a maintenance window, checks the ACE-Step/ltx-2/mflux engine locks, and bumps the core stack as a deliberate engine change (not a sweep remediation), then re-runs the installer. Until then the music MiniMax fallback errors at job time (the worker catches the ImportError) and the torch/transformers advisories stay open in the held versions.

## Why

Round 3 proved the hold discipline works — services stayed loaded and core upgrades were refused — but its refusal list mixed advisories from other environments into each engine. Anchoring the plan in the installed venv makes the refusal list per-engine and truthful; the cost is that the remaining core advisories are now explicitly held rather than silently fixed, which is the deliberate tradeoff of not taking a live service down.
