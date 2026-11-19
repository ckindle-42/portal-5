---
id: unit-LAB_SETUP-reference
historical: true
kind: why
title: "LAB_SETUP \u2014 Reference"
sources:
- type: design
  path: docs/LAB_SETUP.md
  section: Reference
confidence: high
tags:
- docs
- LAB_SETUP

---


| Artifact | What |
|---|---|
| `Dockerfile.attack` | Builds portal5-attack (AD arsenal required; RE/cloud/web/CTF best-effort) |
| `scripts/lab_setup.py` | Tier-1 provisioner |
| `scripts/lab_ready.py` | Readiness gate |
| `scripts/lab_targets.py` | Tier-2 on-demand container engine |
| `config/lab_targets.yaml` | Live-target catalog |
| `config/challenge_classes.yaml` | Class → container map |
| `tests/PORTAL5_BENCH_SEC_EXECUTE_V2.md` | Security bench execution runbook |
