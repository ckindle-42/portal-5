---
id: unit-lab-setup-reference
kind: what
title: "LAB_SETUP \u2014 Reference"
sources:
- type: code
  path: Dockerfile.attack
- type: code
  path: scripts/lab_setup.py
- type: code
  path: scripts/lab_ready.py
- type: code
  path: scripts/lab_targets.py
- type: code
  path: config/lab_targets.yaml
- type: code
  path: config/challenge_classes.yaml
- type: code
  path: scripts/lib/lab.sh
- type: code
  path: tests/PORTAL5_BENCH_SEC_EXECUTE_V3.md
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5228422
updated_at: 1784946220.5228422
---

The lab reference table maps each artifact to its role:

| Artifact | What it is |
|---|---|
| Dockerfile.attack | builds portal5-attack and verifies the lab-exercise tool contract at build time |
| scripts/lab_setup.py | Tier-1 provisioner (vulhub, challenges, models) |
| scripts/lab_ready.py | readiness gate |
| scripts/lab_targets.py | on-demand ephemeral target engine |
| config/lab_targets.yaml | live-target catalog |
| config/challenge_classes.yaml | challenge-class to container mapping |
| tests/PORTAL5_BENCH_SEC_EXECUTE_V3.md | security bench execution runbook |
| scripts/lib/lab.sh | launch.sh lab-up, lab-down, lab-status implementations |

The bench execution runbook is version V3, not V2, and the lab container
commands live in `scripts/lib/lab.sh`, which launch.sh sources at startup.

## Why

Each artifact has a single owner file so the operator can trace a claim to its
implementation: the catalog and its classes are declarative config, the three
python scripts are the three lifecycle phases, and lab.sh is the launch.sh
integration point. Recording the current names prevents a stale artifact list
from being trusted by agents that route on unit content.
