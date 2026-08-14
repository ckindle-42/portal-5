---
id: unit-lab-setup-teardown
kind: what
title: "LAB_SETUP \u2014 Teardown"
sources:
- type: code
  path: scripts/lib/lab.sh
- type: code
  path: scripts/lab_targets.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.521163
updated_at: 1784946220.521163
---

Teardown is lighter than the doc advertised: launch.sh implements only lab-down,
which runs docker compose down across the lab, lab-wazuh, and lab-wazuh-ui
profiles in `scripts/lib/lab.sh`, stopping the Incalmo C2, Talon SOC, and Wazuh
containers. There is no lab-teardown command and no --purge-downloads flag, so
the deep-reclaim options in the doc are not implemented. On-demand vulhub
targets are stopped individually with `python3 scripts/lab_targets.py down`,
which resolves the compose file and runs docker compose down for that single
environment on LXC 112.

## Why

The doc promised a teardown command that was never wired into launch.sh, so
recording only what lab-down actually does keeps the unit honest. The download
caches under `$LAB_DIR/vulhub` are intentionally untouched by every stop path,
which is why a later lab-up and the on-demand target engine can come back
instantly.
