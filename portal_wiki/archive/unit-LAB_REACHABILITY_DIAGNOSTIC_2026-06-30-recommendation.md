---
id: unit-LAB_REACHABILITY_DIAGNOSTIC_2026-06-30-recommendation
kind: why
title: "LAB_REACHABILITY_DIAGNOSTIC_2026-06-30 \u2014 Recommendation"
sources:
- type: design
  path: docs/LAB_REACHABILITY_DIAGNOSTIC_2026-06-30.md
  section: Recommendation
last_generated_commit: ''
confidence: high
tags:
- docs
- LAB_REACHABILITY_DIAGNOSTIC_2026-06-30
created_at: 1783195000.8677142
updated_at: 1783195000.8677142
---


**Do NOT re-run the full 24-test chain sweep yet.** Before re-running:

1. Set lab env vars (`.env`): `LAB_TARGET_DC`, `LAB_TARGET_SRV`, `LAB_TARGET_WEB`, `LAB_DC_VMID`, `LAB_SRV_VMID`, `SANDBOX_LAB_EXEC=true`
2. Verify Proxmox VM power state — ensure DC (vmid 101) and SRV (vmid 102) are running and on the correct network
3. Verify `portal5-dind` / `portal5-attack` can reach `10.10.11.21` on ports 53, 88, 389, 445:
   ```bash
   docker exec portal5-dind docker run --rm --net bridge portal5-attack:latest sh -c "timeout 3 bash -c 'echo > /dev/tcp/10.10.11.21/445' 2>&1 && echo REACHABLE || echo UNREACHABLE"
   ```
4. Create or ensure the `baseline-ad` snapshot exists on VMs 101 and 103 (the `revert_lab_target` tool uses this name)
5. Re-run step 4b (without `--force-unreachable-lab`) — the gate should pass
6. Only then proceed with the full sweep
