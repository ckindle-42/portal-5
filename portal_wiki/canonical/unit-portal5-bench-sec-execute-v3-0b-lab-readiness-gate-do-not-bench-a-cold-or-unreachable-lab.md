---
id: unit-portal5-bench-sec-execute-v3-0b-lab-readiness-gate-do-not-bench-a-cold-or-unreachable-lab
kind: what
title: "PORTAL5_BENCH_SEC_EXECUTE_V3 \u2014 0b. Lab readiness gate \u2014 do not bench\
  \ a cold or unreachable lab"
sources:
- type: doc
  path: tests/PORTAL5_BENCH_SEC_EXECUTE_V3.md
  commit: 05e42ec2
  section: "0b. Lab readiness gate \u2014 do not bench a cold or unreachable lab"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.705761
updated_at: 1784946220.705761
---

```bash
./launch.sh lab-up                        # core lab stack
./launch.sh lab-up-wazuh                  # telemetry (needed for blue-detection)
./launch.sh lab-ready                     # RED means STOP (non-zero exit)
```
Green `lab-ready` confirms: attack box built, vulhub cloned, challenge dirs
materialized, DC/SRV/WEB reachable from sandbox, disk sufficient. See
`docs/LAB_SETUP.md` for the cold-start runbook.

---
