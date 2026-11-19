---
id: unit-backup-restore-restart-services
kind: what
title: "BACKUP_RESTORE \u2014 Restart services"
sources:
- type: code
  path: launch.sh
claims:
- probe: repo.path.exists
  path: launch.sh
  equals: true
confidence: high
tags:
- verified-v1
---

The final step of any restore or migration is `./launch.sh up`, which copies `.env.example` when `.env` is missing, bootstraps any unset secrets, initializes the shared workspace directories, tears down a stale stack, pulls images, starts native services, and runs the container suite. Named volumes survive this cycle, so the restored Open WebUI and Grafana data persists across the restart. The command also re-runs `openwebui-init` in the background to pick up new personas.

## Why

`up` is the single reconciliation point that makes a restore usable again: it creates the workspace structure the MCPs expect, regenerates secrets that were never stored, and brings the database-driven presets in line with config. Starting with `up` rather than raw compose commands guarantees all the launch-time preparation the stack depends on actually runs.
