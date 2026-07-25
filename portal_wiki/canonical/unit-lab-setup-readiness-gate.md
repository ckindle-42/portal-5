---
id: unit-lab-setup-readiness-gate
kind: what
title: "LAB_SETUP \u2014 Readiness Gate"
sources:
- type: doc
  path: docs/LAB_SETUP.md
  commit: 05e42ec2
  section: Readiness Gate
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.521493
updated_at: 1784946220.521493
---

`./launch.sh lab-ready` checks and prints a green/red board:

| Component | Required | What it checks |
|---|---|---|
| attack_image | Yes | portal5-attack built |
| attack_manifest | No | `/opt/portal5-attack.manifest.json` present |
| vulhub_cloned | Yes | `$LAB_DIR/vulhub/.git` exists |
| challenge_dirs | Yes | `$LAB_DIR/challenges/` materialized |
| telemetry | No | Wazuh/WinEvent reachable on 10.10.11.21:55000 |
| snapshots | No | `LAB_DC_VMID` set |
| disk_space | Yes | >10 GB free on `$LAB_DIR` mount |

Returns non-zero if a **required** component is RED. **Do not bench a lab that fails
lab-ready.** Best-effort components (extended arsenal, optional telemetry) warn but don't
block.
