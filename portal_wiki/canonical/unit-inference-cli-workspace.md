---
id: unit-inference-cli-workspace
kind: mixed
title: "Inference CLI workspace \u2014 init/status for the shared root"
sources:
- type: code
  path: portal/platform/inference/cli/workspace.py
  commit: 5fbf51f8
last_generated_commit: 5fbf51f8
claims: []
confidence: high
tags:
- authored-v1
- platform
- cli
created_at: 1785797886.614827
updated_at: 1785797886.614827
---

`portal workspace` is the workspace operations surface:
`workspace_init` creates the `${AI_OUTPUT_DIR}` structure (uploads and
generated categories) and `workspace_status` reports the workspace state —
paths, sizes, and file counts.

## Why

The shared workspace is the only path for user files (Rule 11), and its
directory structure must exist before the MCP fleet writes into it.
`workspace_init` is the operator command that materialises that structure,
deriving the categories from the workspace helper's whitelist so the CLI and
the fleet agree on what exists. `workspace_status` is the inventory view —
how much is where — which an operator needs before a cleanup or a disk
investigation.

## Interfaces

`workspace_init` creates the uploads and generated structure;
`workspace_status` prints the paths, sizes, and counts; both register on
`workspace_app`.

## Gotchas

`workspace_init` is idempotent by design (creating an existing directory is
a no-op), so it is safe to run before every launch.
