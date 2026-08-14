---
id: unit-lab-setup-tier-2-daily-operations
kind: what
title: "LAB_SETUP \u2014 Tier 2 \u2014 Daily Operations"
sources:
- type: code
  path: scripts/lib/lab.sh
- type: code
  path: scripts/lab_ready.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.51969
updated_at: 1784946220.51969
---

Daily operations start and stop the provisioned lab containers without
re-downloading anything. `./launch.sh lab-up` starts the core lab profile: the
Incalmo C2 and the Talon SOC analyst, from `deploy/portal-5/docker-compose.lab.yml`
via `scripts/lib/lab.sh`. `./launch.sh lab-up-wazuh` adds the full Wazuh SIEM
stack and requires LAB_OPENSEARCH_PASSWORD to be set in .env. The readiness
gate is `python3 scripts/lab_ready.py`, not a launch.sh subcommand; it exits
zero when no required check is RED.

## Why

The operational commands stay thin on purpose because the heavy work happened
during Tier 1: starting containers against an already-provisioned lab is cheap
and repeatable. The separate lab-up-wazuh variant exists because the Wazuh stack
is heavy and optional, so a plain session should not pay its memory cost.
