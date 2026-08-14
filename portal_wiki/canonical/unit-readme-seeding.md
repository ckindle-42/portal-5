---
id: unit-readme-seeding
kind: what
title: "README \u2014 Seeding"
sources:
- type: code
  path: launch.sh
- type: code
  path: scripts/openwebui_init.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6836202
updated_at: 1784946220.6836202
---

```bash
./launch.sh seed            # Re-seed Open WebUI (workspaces + personas)
./launch.sh reseed          # Force-refresh all presets (delete + recreate)
```

Both commands run the `openwebui-init` compose service, which executes
`scripts/openwebui_init.py` against the Open WebUI API. `seed` runs it idempotently:
`FORCE_RESEED` is false, so existing presets are skipped and only new ones are
created. `reseed` sets `FORCE_RESEED=true`, and the script deletes and re-creates
all workspaces, personas and tool presets, so updated persona prompts, workspace
tool ids and model presets are pushed into Open WebUI.

`./launch.sh up` also performs an incremental seed: if `open-webui` is already
healthy, it runs `openwebui-init` in the background to pick up any personas or
workspaces added since the last boot.

## Why

Seeding exists because the workspace and persona catalog is generated from
`config/portal.yaml` and `config/personas/`, not entered by hand in Open WebUI.
The idempotent default makes `up` converge safely on every boot, while `reseed`
is the explicit escape hatch to repair a drifted or partially edited preset set
without touching Open WebUI's database by hand.
