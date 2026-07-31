---
id: unit-lab-setup-readiness-gate
kind: what
title: "LAB_SETUP \u2014 Readiness Gate"
sources:
- type: doc
  path: docs/LAB_SETUP.md
  commit: 05e42ec2
  section: Readiness Gate
- type: code
  path: scripts/lab_ready.py
- type: code
  path: scripts/verify_attack_image.py
- type: config
  path: config/attack_image_contract.json
- type: code
  path: tests/unit/test_lab_setup.py
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
| attack_manifest | Yes | Manifest is complete and its SHA-256 matches the current lab-exercise contract |
| vulhub_cloned | Yes | `$LAB_DIR/vulhub/.git` exists |
| challenge_dirs | Yes | `$LAB_DIR/challenges/` materialized |
| telemetry | No | Wazuh/WinEvent reachable on 10.10.11.21:55000 |
| snapshots | No | `LAB_DC_VMID` set |
| disk_space | Yes | >10 GB free on `$LAB_DIR` mount |

Returns non-zero if a **required** component is RED. **Do not bench a lab that fails
lab-ready.** Best-effort components (extended arsenal, optional telemetry) warn but don't
block.

The image build runs `scripts/verify_attack_image.py` against
`config/attack_image_contract.json`; any absent required command or support file
fails the image build. At runtime, `lab-ready` reads the manifest from the image
inside DinD, rejects false entries, and rejects an image built from an older
contract hash. Theory-only exercises are intentionally outside this image
contract.
