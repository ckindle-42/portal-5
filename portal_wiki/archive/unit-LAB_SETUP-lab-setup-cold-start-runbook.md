---
id: unit-LAB_SETUP-lab-setup-cold-start-runbook
historical: true
kind: why
title: "LAB_SETUP \u2014 Lab Setup \u2014 Cold-Start Runbook"
sources:
- type: design
  path: docs/LAB_SETUP.md
  section: "Lab Setup \u2014 Cold-Start Runbook"
confidence: high
tags:
- docs
- LAB_SETUP

---


Two-tier lab: **Tier 1** (expensive, rare, idempotent — downloads everything) and **Tier 2**
(cheap, frequent — start/stop what's provisioned).
