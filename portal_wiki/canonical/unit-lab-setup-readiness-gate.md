---
id: unit-lab-setup-readiness-gate
kind: what
title: "LAB_SETUP \u2014 Readiness Gate"
sources:
- type: code
  path: scripts/lab_ready.py
- type: code
  path: scripts/verify_attack_image.py
- type: code
  path: config/attack_image_contract.json
- type: code
  path: Dockerfile.attack
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.521493
updated_at: 1784946220.521493
---

The readiness gate is `python3 scripts/lab_ready.py`. It prints a board of
GREEN, AMBER, and RED statuses from the `CHECKS` table and exits non-zero when a
required check is RED:

| Check | Required | What it checks |
|---|---|---|
| docker | Yes | local Docker daemon present |
| dind | Yes | portal5-dind nested daemon running |
| attack_image | Yes | portal5-attack image exists inside the DinD runtime |
| attack_manifest | Yes | in-image manifest complete, contract SHA-256 equals `config/attack_image_contract.json`, runtime probes pass |
| vulhub_clone | Yes | vulhub repo exists on the remote lab host or under `$LAB_DIR/vulhub` |
| challenge_dirs | Yes | `$LAB_DIR/challenges/` is materialized |
| disk | Yes | more than 10 GB free on the `$LAB_DIR` mount |
| ollama | No | Ollama present (best-effort) |
| dc_reachable | Yes | DC at 10.10.11.21:445 reachable from a nested attack container |
| srv_reachable | Yes | SRV at 10.10.11.33:445 reachable from a nested attack container |
| web_reachable | Yes | Web at 10.10.11.50:8080 reachable from a nested attack container |
| snapshots | No | clean-baseline snapshots exist for the DC and SRV VMIDs |

Optional checks warn but never block the gate. The attack image build runs
`verify_attack_image.py` against `config/attack_image_contract.json` inside
`Dockerfile.attack`, so an absent command or support file fails the build. At
runtime the gate reads the manifest from inside the image and rejects both false
entries and an image built from an older contract hash. Static-target
connectivity is probed with `nc -z -w 3` launched in a fresh nested attack
container; GNU timeout must not replace it because it exits 125 as PID one in
this image.

## Why

The gate exists to make a bench run against a broken lab impossible: a required
RED check is a hard stop before any scenario starts. The manifest hash check is
the sharpest part, because a rebuilt image that silently dropped a tool still
reports green to a naive existence probe, and the nested runtime probe exists
because tools installed but unusable under the container capabilities are a
failure that an ordinary which check cannot see.
