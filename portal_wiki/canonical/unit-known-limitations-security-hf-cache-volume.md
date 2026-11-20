---
id: unit-known-limitations-security-hf-cache-volume
kind: what
title: Security MCP model cache lives in a Docker volume on the main drive, not on data01
sources:
- type: code
  path: deploy/portal-5/docker-compose.yml
claims:
- probe: repo.path.exists
  path: deploy/portal-5/docker-compose.yml
  equals: true
confidence: high
tags:
- known-limitations
- disk
- security

---

#### security-hf-cache model cache is a Docker volume on the main drive (2026-11-19)

- **ID**: P5-DISK-001
- **Status**: OPEN. Recorded 2026-11-19 after the main drive hit 142 MiB free and `./launch.sh rebuild` failed with ENOSPC.
- **Description**: The security MCP's HuggingFace model cache is a named Docker volume, not a data01 path: `deploy/portal-5/docker-compose.yml` mounts `security-hf-cache:/app/data/hf_cache` with `HF_HOME=/app/data/hf_cache`, so the cache lives inside `Docker.raw` on the main drive. Measured 2026-11-19 (`docker system df -v`): `portal-5_security-hf-cache` held **12.97 GB**. Cache volumes grow with model fetches and are never pruned by anything — `_disk_hygiene` in `scripts/lib/util.sh` deliberately never touches volumes (CLAUDE.md: never delete volumes or models) — so this is the same growth-on-the-main-drive class that filled the disk on 2026-11-19, minus the image-export leak (fixed: the sweep's exports now go to `/Volumes/data01/portal5_sweep_scratch/osv-image-scan`).
- **Used by Portal**: yes — the security MCP (port 8919, CIRCL/VL model downloads). A sibling volume `portal-5_portal5-hf-cache` (0.5 GB, TTS/whisper) is the same pattern at a size that does not yet matter.
- **Mitigation**: Moving the cache to data01 is a compose change (`security-hf-cache:/app/data/hf_cache` → a bind mount such as `/Volumes/data01/portal5_sweep_scratch`-style path under an env var), a data migration of the existing 13 GB, and a security-MCP restart — recorded, not applied here, because a 13 GB volume move is neither small nor safe to do blind. `./launch.sh backup`/`clean-all` semantics must be checked before any volume is moved.

#### Why

The 2026-11-19 ENOSPC came from three main-drive growers at once (build cache, superseded images, and the sweep's `$TMPDIR` exports). The first two are now pruned by `_disk_hygiene` and the third moved to data01, but a volume can never be pruned by an automated path, so anything a container caches into a named volume keeps growing on the main drive until an operator moves it. This record keeps the 13 GB visible next to the mechanisms that did get fixed instead of letting the next disk-full look spontaneous.
