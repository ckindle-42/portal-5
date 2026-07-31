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
| attack_image | Yes | `portal5-attack` exists in the nested DinD runtime |
| attack_manifest | Yes | Manifest is complete, its SHA-256 matches the current lab-exercise contract, and required runtime probes pass |
| vulhub_cloned | Yes | Vulhub exists on the remote lab target host |
| challenge_dirs | Yes | `$LAB_DIR/challenges/` materialized |
| static targets | Yes | DC/SRV SMB and Web HTTP are reachable from the sandbox |
| snapshots | No | Clean-baseline snapshots exist on the configured Proxmox node |
| disk_space | Yes | >10 GB free on `$LAB_DIR` mount |

Returns non-zero if a **required** component is RED. **Do not bench a lab that fails
lab-ready.** Best-effort components (extended arsenal, optional telemetry) warn but don't
block.

The image build runs `scripts/verify_attack_image.py` against
`config/attack_image_contract.json`; any absent required command or support file
fails the image build. At runtime, `lab-ready` reads the manifest from the image
inside DinD, rejects false entries, rejects an image built from an older
contract hash, and executes the contract's runtime checks. This catches tools
that are installed but unusable under the container's default capabilities.
Theory-only exercises are intentionally outside this image contract.

Static target connectivity is probed with `nc -z -w 3` inside a fresh nested
attack container. Do not replace this with a direct PID-1 invocation of GNU
`timeout`: that returns 125 in the current image even when the same TCP
connection succeeds, producing a false-red readiness board.
