---
id: unit-lab-setup-tier-1-first-time-setup-run-once-re-run-to-update
kind: what
title: "LAB_SETUP \u2014 Tier 1 \u2014 First-Time Setup (run once, re-run to update)"
sources:
- type: code
  path: scripts/lab_setup.py
- type: code
  path: config/challenge_classes.yaml
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.518086
updated_at: 1784946220.518086
---

The first-time setup is `python3 scripts/lab_setup.py`. It is idempotent and
safe to re-run: the vulhub step short-circuits with already cloned when the repo
exists, the challenges step recreates directories idempotently from
`config/challenge_classes.yaml`, and the models step reuses `./launch.sh
pull-models`. The --update flag is accepted by the CLI but the current
implementation gives it no distinct behavior: `setup_vulhub` never issues a git
pull, so re-running does not refresh an existing clone.

## Why

Re-running must be harmless because the provisioner is the one command an
operator re-executes after a failed or partial setup, and a non-idempotent clone
would waste the cached downloads. The inert --update flag is called out
explicitly so nobody reads the CLI help and assumes a refresh that the code does
not perform.
