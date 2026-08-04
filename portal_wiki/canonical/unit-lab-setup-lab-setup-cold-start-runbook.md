---
id: unit-lab-setup-lab-setup-cold-start-runbook
kind: what
title: "LAB_SETUP \u2014 Lab Setup \u2014 Cold-Start Runbook"
sources:
- type: code
  path: scripts/lab_setup.py
- type: code
  path: scripts/lib/lab.sh
- type: code
  path: deploy/portal-5/docker-compose.lab.yml
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.517716
updated_at: 1784946220.517716
---

Cold starts follow a two-tier model. Tier 1 is the expensive, rare, idempotent
bulk-download phase handled by `scripts/lab_setup.py`, which clones vulhub,
materializes the purpose-built challenge directories, and pulls the
security-lane models. Tier 2 is the cheap, frequent operational phase:
`./launch.sh lab-up` and `./launch.sh lab-down` start and stop the provisioned
containers from the lab profile in `deploy/portal-5/docker-compose.lab.yml`
without re-downloading anything. The tiers deliberately split provisioning cost
from daily operation so a cold start is a one-time investment.

## Why

The two-tier split exists because the downloads are the expensive part: a vulhub
clone and the model pulls happen once, while the per-day start and stop cycle
must stay nearly free. Keeping the provisioner and the operational commands
separate is what lets an operator rebuild the runtime cheaply without losing
the cached downloads.
