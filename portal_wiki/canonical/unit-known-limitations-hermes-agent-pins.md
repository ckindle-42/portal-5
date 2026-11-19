---
id: unit-known-limitations-hermes-agent-pins
kind: what
title: hermes-agent cannot take the pillow 13 and PyJWT 2.14 advisory floors
sources:
- type: code
  path: scripts/lib/services.sh
claims:
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

- **ID**: P5-HERMES-AGENT-001
- **Status**: OPEN. Not a Portal service. Recorded 2026-11-19 from the host uv tool, not from a live Portal trace.
- **Description**: `hermes-agent` 0.19.0 (`~/.local/share/uv/tools/hermes-agent`) pins `Pillow==12.2.0` and `PyJWT[crypto]==2.13.0`. Those exact pins cannot satisfy pillow 13.0.0 (`GHSA-5x8w-8jj5-q52h` / `CVE-2026-112398`, fixed in 13.0.0) or PyJWT 2.14.0 (`PYSEC-2026-4144` JWKS redirect, `PYSEC-2026-4151` algorithm confusion, both fixed in 2.14.0). The resolver reports the constraints unsatisfiable.
- **Used by Portal**: no. Nothing under `portal/`, `scripts/`, `deploy/`, or `config/` invokes `hermes-agent`. It is an operator uv tool on the host, separate from the `hermes3:8b` model seat and the `hermes` tool-call parser name.
- **Mitigation**: leave the tool pinned until upstream moves those pins, or remove the uv tool. Do not force pillow or PyJWT inside that environment. Portal engine installers do not touch it (`scripts/engine_install_plan.py` holds the media core stack and applies sweep fixes only to music, mflux, and video-mlx).

## Why

A host uv tool that Portal never starts was failing the same advisory floors as the media venvs. Recording the pins and the fact that Portal does not use it keeps a later sweep from treating the tool as a platform dependency, and leaves removal as an operator choice.
