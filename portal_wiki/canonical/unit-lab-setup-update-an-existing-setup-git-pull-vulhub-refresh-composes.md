---
id: unit-lab-setup-update-an-existing-setup-git-pull-vulhub-refresh-composes
kind: what
title: "LAB_SETUP \u2014 Update an existing setup (git pull vulhub, refresh composes):"
sources:
- type: doc
  path: docs/LAB_SETUP.md
  commit: 05e42ec2
  section: 'Update an existing setup (git pull vulhub, refresh composes):'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.519338
updated_at: 1784946220.519338
---

./launch.sh setup --update
```

**What `setup` downloads** (all idempotent — skips if already present/current):
- vulhub (1,234 environments, 154 families) — `git clone --depth 1` into `$LAB_DIR/vulhub`
- Purpose-built challenge composes (JWT, k8s, cloud-metadata, GraphQL — vulhub gaps)
- Base images pre-pull (heavy vulhub images + telemetry stack) for warm first `lab up`
- Security-lane model pulls (reuses `./launch.sh pull-models`)
- Seed data (sprayable accounts, breach pairs via the existing seed path)

**Disk expectation:** ~10–15 GB for vulhub (shallow clone) + models (variable). Use
`--skip-heavy` to defer large downloads.
