---
id: unit-portal5-bench-sec-execute-v3-0b-lab-readiness-gate-do-not-bench-a-cold-or-unreachable-lab
kind: what
title: "PORTAL5_BENCH_SEC_EXECUTE_V3 \u2014 0b. Lab readiness gate \u2014 do not bench\
  \ a cold or unreachable lab"
sources:
- type: code
  path: launch.sh
- type: code
  path: scripts/lib/lab.sh
- type: code
  path: scripts/lab_ready.py
- type: code
  path: config/attack_image_contract.json
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.705761
updated_at: 1784946220.705761
---

`./launch.sh lab-up` starts the core lab stack (Incalmo C2 + Talon SOC
analyst) via `_launch_lab_up` in `scripts/lib/lab.sh`; `./launch.sh lab-up-wazuh`
adds the Wazuh/OpenSearch telemetry stack via `_launch_lab_up_wazuh` (requires
`LAB_OPENSEARCH_PASSWORD`), which blue-detection scoring needs. The readiness
gate itself is `python3 scripts/lab_ready.py` — note that `launch.sh` has no
`lab-ready` case, so the bare `./launch.sh lab-ready` form falls through to the
usage message. `scripts/lab_ready.py` runs its `CHECKS` table — attack image
present in DinD, image manifest hash matching `config/attack_image_contract.json`,
vulhub clone, challenge dirs, DC/SRV/WEB reachable from the attack container,
sufficient disk — and exits non-zero whenever a required check is RED. Do not
bench a cold or unreachable lab. See `docs/LAB_SETUP.md` for the cold-start
runbook.

## Why

A green gate is a precondition, not a courtesy: a cold lab produces zero
live-success signals across an entire multi-hour run with nothing telling the
operator why. The gate is a standalone script precisely so it can run from
automation and CI, and its required-versus-best-effort split keeps optional
telemetry from blocking an otherwise ready bench.

---
