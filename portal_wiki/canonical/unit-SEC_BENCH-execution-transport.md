---
id: unit-SEC_BENCH-execution-transport
kind: what
title: 'Execution transport: _host_exec and dispatch tiers'
sources:
- type: code
  path: scripts/lab_host.py
- type: code
  path: scripts/lab_discover.py
- type: code
  path: portal/modules/security/core/matrix.py
claims: []
confidence: high
tags:
- bench
- dispatch
- security
- transport
- verified-v1
created_at: 1784941806.3787038
updated_at: 1784941806.3787038
---

One transport for everything that touches LXC 112: `scripts/lab_host.py::_host_exec(cmd)` -- `ssh -i ~/.ssh/portal-lab_id_ed25519 root@10.0.0.203 "pct exec 112 -- <cmd>"`.

**Discovery first:** `python3 -m scripts.lab_discover` probes the host read-only (LXC status, Docker daemon, vulhub root + env count, running containers, used ports) before anything acts on assumed state.

**Dispatch tiers** (`_run_against_target` in `matrix.py`, keyed on `unit.scenario_key`):
- tier-1 = proven `_phase_*` functions in `bench_lab_exec.py` (kerberoasting, asrep_roasting, log4shell_rce, redis_to_rce, tomcat_manager, htb_lfi_log_poison)
- tier-2 = generic dispatch of the real `EXEC_SEQUENCES` steps via `_mcp_call`, halting on the first required-step failure
- tier-3 = `DISPATCH_NOT_RUN` sentinel when neither exists for a scenario_key

The governing rule is that DISPATCH_NOT_RUN and any dry-run/halted evidence always score `indeterminate`, never `verified`.

## Why

A single transport exists because LXC 112 access is exactly the kind of duplicated, unverifiable plumbing that drifts — ssh flags, key paths, and host addresses all varied across callers before `_host_exec` became the only entry point. Discovery-first mirrors the same principle for state: the host is probed read-only before any phase assumes a container or port exists. The dispatch tiers exist so that proven exploit phases get deterministic, named handlers while everything else falls back to the generic `EXEC_SEQUENCES` path, and anything unresolvable lands on `DISPATCH_NOT_RUN` rather than a fabricated success.
