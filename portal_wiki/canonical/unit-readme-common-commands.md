---
id: unit-readme-common-commands
kind: what
title: "README \u2014 Common Commands"
sources:
- type: code
  path: launch.sh
- type: code
  path: scripts/lib/util.sh
- type: code
  path: scripts/lib/services.sh
- type: code
  path: scripts/lib/backup.sh
- type: code
  path: scripts/lib/users.sh
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.680423
updated_at: 1784946220.680423
---

The operator surface is one dispatcher: `./launch.sh <command>`. The `case`
statement in `launch.sh` routes every subcommand, and most delegate either to a
sourced library under `scripts/lib/` or to `portal.platform.inference.cli`. The
core lifecycle commands are `./launch.sh up` (build the stack, auto-generate
secrets, run port pre-flight), `./launch.sh down` (stop Docker services plus
native macOS services while preserving data) and `./launch.sh status` (health
table via `_cmd_status` in `scripts/lib/util.sh`).

Around that core sit the operational groups: `seed` / `reseed` for Open WebUI
presets (`scripts/openwebui_init.py`), `pull-models` / `refresh-models` /
`import-gguf` for Ollama models, `add-user` / `list-users` for accounts
(`scripts/lib/users.sh`), `backup` / `restore` for data (`scripts/lib/backup.sh`),
and `up-telegram` / `up-slack` / `up-channels` for messaging bots. Native Apple
Silicon services are managed with `start-speech` / `stop-speech`,
`start-transcribe` / `stop-transcribe` and the embedding service installers in
`scripts/lib/services.sh`. `sync-config` regenerates derived artifacts from
`config/portal.yaml`, and `./launch.sh test` runs live smoke tests.

## Why

A single entrypoint keeps every operational action deterministic and scriptable:
each subcommand either maps to a small shell library or to one typed CLI module,
so there is exactly one way to start, stop, seed or back up the stack. It also
means the Docker Compose project directory and the `.env` file are never touched
by hand, which keeps `docker compose up` and `launch.sh up` from diverging.
