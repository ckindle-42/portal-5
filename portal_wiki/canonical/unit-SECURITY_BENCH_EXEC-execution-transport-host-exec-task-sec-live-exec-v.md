---
id: unit-SECURITY_BENCH_EXEC-execution-transport-host-exec-task-sec-live-exec-v
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Execution Transport \u2014 `_host_exec` (TASK-SEC-LIVE-EXEC-V1)"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: "Execution Transport \u2014 `_host_exec` (TASK-SEC-LIVE-EXEC-V1)"
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.897208
updated_at: 1783195000.897208
---


**One transport for everything that touches LXC 112:** `scripts/lab_host.py::_host_exec(cmd)` —
`ssh -i ~/.ssh/portal-lab_id_ed25519 root@10.0.0.203 "pct exec 112 -- <cmd>"`. This replaced an
execution layer that was scaffolded but never wired up: `matrix.py::_run_against_target()` used
to `return ""` unconditionally, `scripts/lab_targets.py::cmd_up`/`cmd_down` returned
`{"status": "placeholder"}` and checked a **local** `~/AI_Output/lab/vulhub/...` path, and vulhub
glob resolution ran against that same local (nonexistent) path — while the real vulhub clone
lives on the Proxmox host. Every prior 0%-verified run was that stub/wrong-machine bug, not a
model-capability finding.

**Discovery first:** `python3 -m scripts.lab_discover` probes the host read-only (LXC status,
Docker daemon, vulhub root + env count, running containers, used ports) before anything acts on
assumed state. `LAB_VULHUB_HOST_ROOT` (default `/opt/vulhub`) is the vulhub root every resolution
and spin-up call resolves against.

**Dispatch tiers** (`_run_against_target` in `matrix.py`, keyed on `unit.scenario_key`):
tier-1 = proven `_phase_*` functions in `bench_lab_exec.py` (`kerberoasting, asrep_roasting,
log4shell_rce, redis_to_rce, tomcat_manager, htb_lfi_log_poison`); tier-2 = generic dispatch of
the real `EXEC_SEQUENCES` steps via `_mcp_call`, halting on the first required-step failure;
tier-3 = `DISPATCH_NOT_RUN` sentinel when neither exists for a scenario_key. The governing rule —
enforced in `tests/unit/test_live_exec.py` and validator check `AA. live exec integrity` — is
that DISPATCH_NOT_RUN and any dry-run/halted evidence always score `indeterminate`, never
`verified`.

See `tests/PORTAL5_BENCH_SEC_EXECUTE_V2.md` § "Live-Lab Execution Foundation" for the full
writeup, including the discovery baseline (328/328 vulhub envs present as of 2026-07-01).

**Tier-1 phase content was also live-corrected 2026-07-01:** 3 of the 6 tier-1 phases
(`htb_lfi_log_poison`, `tomcat_manager`, `log4shell_rce`
