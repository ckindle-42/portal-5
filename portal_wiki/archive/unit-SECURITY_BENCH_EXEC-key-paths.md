---
id: unit-SECURITY_BENCH_EXEC-key-paths
historical: true
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Key paths"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: Key paths
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC

---

- `_run_exec_chain()` in `__init__.py` — multi-model chain orchestrator
- `_dispatch_lab_tool()` → `_lab_mcp_call(cmd)` → MCP sandbox :8914 → portal5-attack container
- Proxmox lifecycle: `_snapshot_lab_vms()` / `_restore_lab_vms()` via `_proxmox_mcp_call()` → MCP :8927
- Blue active response: `_dispatch_blue_response()` dispatches countermeasures to sandbox
