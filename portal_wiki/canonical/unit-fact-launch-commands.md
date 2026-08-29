---
id: unit-fact-launch-commands
kind: mixed
title: "Operator commands \u2014 the launch.sh surface"
sources:
- type: code
  path: launch.sh
- type: code
  path: scripts/lib/util.sh
- type: code
  path: scripts/lib/services.sh
claims:
- probe: launch.commands
  pattern: '{value} subcommands'
confidence: high
tags:
- fact
- operator
created_at: 1788030600.446044
updated_at: 1788030600.446044
---

# Operator commands — the launch.sh surface

The operator's command surface is `./launch.sh <subcommand>` — 64 subcommands
as of the current usage string, grouped below by what they act on.

## Lifecycle

- `up`, `down`, `clean`, `clean-all`, `update` — start/stop services, wipe
  data at two granularities, and full update (git pull, images, models,
  re-seed). `clean` preserves Ollama models; `clean-all` does not.
- `status`, `logs` — service health and log tails.
- `test`, `rebuild` — smoke tests against the live stack, and a Docker image
  rebuild plus restart after a pull.

## Config and seeding

- `sync-config` — the idempotent re-derivation of `backends.yaml`
  workspace_routing, `.mcp.json`, and OWUI presets from `config/portal.yaml`.
- `seed`, `reseed` — Open WebUI seeding for workspaces, personas, and tools.
- `workspace-init`, `workspace-status`, `workspace-show` — create and inspect
  the shared workspace directory tree.

## Models

- `pull-models`, `refresh-models`, `import-gguf`, `apply-model-params`,
  `apply-mtp-drafts` — model acquisition, update checks, local GGUF import,
  and ctx-tagged variant creation.
- `promptfoo` — LLM quality evals by area.

## Media installs (image / video / music)

- `install-mflux`, `start-mflux`, `stop-mflux`, `pull-mflux-models` — the
  MFLUX image MCP lifecycle and weight pre-pull.
- `install-video-mlx`, `start-video-mlx`, `stop-video-mlx`,
  `pull-video-mlx-models` — the video-mlx MCP lifecycle and LTX-2.3 packs.
- `install-music-minimax`, `install-music-ace`, `stop-music-ace` — music
  backends.

## Speech / transcription / embedding arms

- `start-speech`, `stop-speech` — the host MLX speech server.
- `start-transcribe`, `stop-transcribe` — the host MLX transcribe server.
- `start-embedding-cpu-arm`, `stop-embedding-cpu-arm`,
  `install-embedding-service`, `uninstall-embedding-service` — the native ARM
  embedding server plus its launchd agent.
- `install-powermetrics`, `uninstall-powermetrics` — the sudo power-telemetry
  daemon.

## Lab and channels

- `lab-up`, `lab-up-wazuh`, `lab-down`, `lab-status` — lab profile control,
  with and without the Wazuh SIEM stack.
- `build-lab-attack`, `build-binresearch` — build and load the attack and RE
  toolchain images into DinD.
- `up-telegram`, `up-slack`, `up-channels` — force-start the messaging
  channels.

## Accounts and backup

- `add-user`, `list-users` — user management.
- `backup`, `restore` — data backup and restore.
- `install-ollama` — native Ollama install (Apple Silicon recommended).

## Why

The single `launch.sh` entry point is what makes the platform launch in one
command: every lifecycle, install, and maintenance action has one canonical
form, and the usage string is the completeness source the operator and the
validation gates both read. Keeping installs as idempotent subcommands means a
tight-footprint box pays for a model only by invoking the matching
`install-*` / `pull-*` pair.
