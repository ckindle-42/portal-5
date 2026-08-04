---
id: unit-inference-cli-sync
kind: mixed
title: "Inference CLI sync \u2014 operator artifact regeneration"
sources:
- type: code
  path: portal/platform/inference/cli/sync.py
  commit: 5fbf51f8
last_generated_commit: 5fbf51f8
claims: []
confidence: high
tags:
- authored-v1
- platform
- cli
created_at: 1785797874.7389781
updated_at: 1785797874.7389781
---

`portal sync-config` regenerates the derived artifacts from
`config/portal.yaml`, and `sync-readme` regenerates the README's generated
blocks. They are the operator-facing wrappers over `sync_config.py` and the
wiki renderer.

## Why

The generation must be runnable by an operator without invoking the module
directly, and these commands are the typed wrapper over the same idempotent
generator the pre-commit hook uses. Running `sync-config` from the CLI and
from CI must produce identical output — which is guaranteed because they call
the same generator.

## Interfaces

`sync_config` runs the artifact generation; `sync_readme` renders the README
blocks; both register as top-level commands.

## Gotchas

The command is idempotent — running it twice changes nothing — which is the
property the freshness gate relies on.
