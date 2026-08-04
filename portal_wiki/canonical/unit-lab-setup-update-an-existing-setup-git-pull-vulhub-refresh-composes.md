---
id: unit-lab-setup-update-an-existing-setup-git-pull-vulhub-refresh-composes
kind: what
title: "LAB_SETUP \u2014 Update an existing setup (git pull vulhub, refresh composes):"
sources:
- type: code
  path: scripts/lab_setup.py
- type: code
  path: scripts/lab_targets.py
- type: code
  path: scripts/lab_ready.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.519338
updated_at: 1784946220.519338
---

Updating an existing setup is `python3 scripts/lab_setup.py --update`, but the
flag is currently inert: `setup_vulhub` returns already cloned without running
git pull, so neither vulhub nor the other steps are refreshed. The only place a
git pull on an existing clone exists is `provision_vulhub_env` in
`scripts/lab_targets.py`, which pulls when the LXC-112 root is already a repo
and clones it when it is not. The provisioner's other steps stay idempotent:
challenges materialize purpose-built dirs from `config/challenge_classes.yaml`
and models reuse `./launch.sh pull-models`. The readiness gate requires more
than 10 GB free on the `$LAB_DIR` mount before a bench.

## Why

The update claim in the doc does not match the implementation: --update has no
code path, so this unit records where refresh actually happens, in the on-demand
provisioner's git pull. Keeping the provisioner idempotent while making refresh
explicit in `lab_targets.py` is what prevents a partial update from corrupting
a cached clone.
