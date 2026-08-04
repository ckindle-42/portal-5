---
id: unit-SECURITY_BENCH_EXEC-adding-a-new-lab-target
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Adding a new lab target"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: Adding a new lab target
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.9133341
updated_at: 1783195000.9133341
---

1. Add env vars to `.env` and `_data.py` fallback block
2. Add service probes to `_LAB_SERVICE_PROBES` in `_data.py`
3. Add prompt mappings to `_svc_to_prompt` dict in `__init__.py` (probe auto-filter)
4. Deploy target (Proxmox VM via API or Docker via compose on lxc 112)
5. Verify reachability from sandbox: `docker exec portal5-dind docker run --rm --net bridge portal5-attack:latest sh -c '<probe cmd>'`
