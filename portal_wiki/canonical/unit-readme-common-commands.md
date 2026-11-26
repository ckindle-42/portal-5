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
- type: code
  path: portal/platform/inference/cli/smoke.py
- type: code
  path: portal/platform/inference/cli/models.py
- type: code
  path: scripts/openwebui_init.py
- type: code
  path: config/portal.yaml
claims:
- probe: repo.path.exists
  path: launch.sh
  equals: true
confidence: high
tags:
- docs
- verified-v1
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

## Discovering commands, and the worktree guard

```bash
./launch.sh help            # list every subcommand; touches nothing
```

`help` (also `-h`, `--help`) is the only subcommand that is safe to run from a
lane worktree, and the only way to discover the surface without risking the
stack: it prints the usage block and exits. Every other subcommand — including a
bare `./launch.sh`, which resolves to `up` — is refused from a git worktree that
is not the live checkout. The guard lives at the top of `launch.sh`, backed by
`_portal_is_lane_worktree` / `_portal_refuse_lane_worktree` in
`scripts/lib/util.sh`: a linked worktree (`git rev-parse --git-common-dir` ≠
`--absolute-git-dir`), or any checkout whose toplevel is not
`PORTAL_LIVE_CHECKOUT` (default `$HOME/projects/portal-5`), exits non-zero with
an explanatory message. The allowlist is default-deny, so a command added later
is guarded without being listed. `PORTAL_ALLOW_STACK_FROM_WORKTREE=1` lifts the
guard for the orchestrator; lanes have no reason to set it. The refusal exists
because compose's project name is shared: on 2026-11-20 a lane's bare
`./launch.sh` ran `up` from its worktree and destroyed every live container.

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

## Host log rotation

On Apple Silicon, `./launch.sh up` installs the hourly `com.portal5.log-rotate`
user agent. Preview the configured files and threshold with:

```bash
.venv/bin/python scripts/rotate_logs.py --dry-run
```

`LOG_ROTATE_MAX_MB`, `LOG_ROTATE_KEEP`, and the optional
`LOG_ROTATE_FILES` in `.env` configure the threshold, archive count, and paths.

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
./launch.sh seed            # Upsert Portal presets in place (workspaces + personas)
./launch.sh reseed          # Delete and recreate Portal presets (FORCE_RESEED=true)
```

Both run the `openwebui-init` compose service, which executes
`scripts/openwebui_init.py` against the Open WebUI API. `seed` is an in-place
upsert of presets Portal created: system prompt, params, toolIds, model, meta and
access converge to the repo, an unchanged preset is not written, and chat history
and pins stay. `reseed` sets `FORCE_RESEED=true` and deletes then recreates those
presets. A retired Portal persona is reported on seed and deleted only by reseed.
`./launch.sh up` runs the same upsert in the background whenever `open-webui` is
already healthy.

## Why

A single entrypoint keeps every operational action deterministic and scriptable:
each subcommand maps to one small shell library or one typed CLI module, so there
is exactly one way to start, stop, seed, verify or back up the stack, and the
Docker Compose project directory and `.env` are never hand-edited — which keeps
`docker compose up` and `launch.sh up` from diverging. The groups above are kept
separate from the lifecycle core because each is an occasional, operator-initiated
step — pulling the large specialized catalog, provisioning an account, repairing a
drifted preset set — that has no business running on every boot.
