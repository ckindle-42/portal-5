---
id: unit-SECURITY_BENCH_EXEC-7-proxmox-vm-snapshot-restore
kind: why
title: "SECURITY_BENCH_EXEC \u2014 7. Proxmox VM Snapshot/Restore"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 7. Proxmox VM Snapshot/Restore
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.903046
updated_at: 1783195000.903046
---

`--lab-snapshot` creates a named snapshot of all lab VMs before the chain runs, then restores after. Ensures each chain starts from a clean lab state. Requires `LAB_DC_VMID`, `LAB_SRV_VMID`, `LAB_CLEAN_SNAPSHOT` in `.env`.
