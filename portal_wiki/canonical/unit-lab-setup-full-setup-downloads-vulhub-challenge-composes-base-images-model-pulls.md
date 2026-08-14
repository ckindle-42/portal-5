---
id: unit-lab-setup-full-setup-downloads-vulhub-challenge-composes-base-images-model-pulls
kind: what
title: "LAB_SETUP \u2014 Full setup (downloads vulhub, challenge composes, base images,\
  \ model pulls):"
sources:
- type: code
  path: scripts/lab_setup.py
- type: code
  path: config/challenge_classes.yaml
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.518579
updated_at: 1784946220.518579
---

The full Tier-1 provisioner is invoked as `python3 scripts/lab_setup.py`. It
runs three idempotent steps from the `STEPS` table in order: the vulhub step
shallow-clones the upstream repository into `$LAB_DIR/vulhub` unless it is
already present, the challenges step materializes the purpose-built directories
named by the classes list in `config/challenge_classes.yaml`, and the models
step delegates to the existing `./launch.sh pull-models` path. There is no
separate base-image pre-pull step and no telemetry download inside this
provisioner.

## Why

The three-step split keeps the expensive, rarely-changing downloads separate
from the frequent operational phase: cloning once into `$LAB_DIR/vulhub` and
caching it across runs is what makes re-running the provisioner idempotent, and
delegating the model step to the existing pull-models command keeps a single
source of truth for which security models should be resident.
