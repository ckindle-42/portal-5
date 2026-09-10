---
id: unit-readme-common-commands
kind: what
title: "README — Common Commands"
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
- type: code
  path: portal/platform/inference/cli/smoke.py
- type: code
  path: portal/platform/inference/cli/models.py
- type: code
  path: scripts/openwebui_init.py
- type: code
  path: config/portal.yaml
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
table via `_cmd_status` in `scripts/lib/util.sh`). Around that core sit the
operational groups below; `sync-config` regenerates derived artifacts from
`config/portal.yaml`, and the native Apple Silicon services are handled with the
`start-speech` / `start-transcribe` pairs and the embedding installers in
`scripts/lib/services.sh`.

## Test everything is working

```bash
# Test everything is working
./launch.sh test            # Run live smoke tests against running stack
```

The `test` subcommand executes `portal.platform.inference.cli test`, implemented
in `portal/platform/inference/cli/smoke.py`. `cmd_test` runs end-to-end checks
against the live stack: it probes the pipeline health endpoint (`PIPELINE_URL`,
default `http://localhost:9099`) with the configured `PIPELINE_API_KEY`, then the
Open WebUI URL (`OPENWEBUI_URL`), and prints a per-check pass/fail summary that
exits nonzero on any failure. It is the quick post-`up` check, separate from the
heavier acceptance suite.

## Pull specialized models (security, coding, reasoning — 30–90 min)

```bash
# Pull specialized models (security, coding, reasoning — 30–90 min)
./launch.sh pull-models
```

`pull-models` delegates to `portal.platform.inference.cli models pull`, which
reads the model registry from `config/portal.yaml` (`models:` block), resolves
targets with `_select_pull_targets` (skipping `retired: true` entries and entries
with no `ollama_name`), and fetches each into Ollama — HuggingFace repos through
`hf download`, native registry tags through `ollama pull`. Anything already
present is skipped, and gated repos need `HF_TOKEN` set in `.env`.

## User management

```bash
# User management
./launch.sh add-user alice@example.com "Alice Smith"
./launch.sh list-users
```

Both wrap the Open WebUI admin API from `scripts/lib/users.sh`. `add-user` posts
to `/api/v1/auths/add` with an admin token from `get_admin_token`, mints a
temporary password, and prints the new account's credentials; the role defaults
to `user` and also accepts `admin` or `pending`. `list-users` reads
`/api/v1/users/`. Both need the stack running and an admin token resolvable.

## Seeding

```bash
# Seeding
./launch.sh seed            # Re-seed Open WebUI (workspaces + personas)
./launch.sh reseed          # Force-refresh all presets (delete + recreate)
```

Both run the `openwebui-init` compose service, which executes
`scripts/openwebui_init.py` against the Open WebUI API. `seed` is idempotent —
`FORCE_RESEED` is false, so existing presets are left alone — while `reseed` sets
`FORCE_RESEED=true` and deletes then recreates every workspace, persona and tool
preset. `./launch.sh up` also runs an incremental seed in the background whenever
`open-webui` is already healthy.

## Why

A single entrypoint keeps every operational action deterministic and scriptable:
each subcommand maps to one small shell library or one typed CLI module, so there
is exactly one way to start, stop, seed, verify or back up the stack, and the
Docker Compose project directory and `.env` are never hand-edited — which keeps
`docker compose up` and `launch.sh up` from diverging. The groups above are kept
separate from the lifecycle core because each is an occasional, operator-initiated
step — pulling the large specialized catalog, provisioning an account, repairing a
drifted preset set — that has no business running on every boot.
