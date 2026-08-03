---
id: unit-inference-cli-init
kind: mixed
title: "Inference CLI \u2014 typed operator surface composition root"
sources:
- type: code
  path: portal/platform/inference/cli/__init__.py
  commit: 5fbf51f8
last_generated_commit: 5fbf51f8
claims: []
confidence: high
tags:
- authored-v1
- platform
- cli
created_at: 1785797821.4518359
updated_at: 1785797821.4518359
---

The CLI package is the typed operator surface for the portal: `portal
config`, `portal workspace`, `portal models`, `portal module`, `portal
agent`, plus top-level `sync-config`, `test`, and `update`. Each sub-module
registers commands on shared typer apps, and the `__init__` is the
composition root where they all come together.

## Why

The CLI exists because the operator needs typed, discoverable commands over
the portal config instead of ad-hoc python invocations. The composition-root
pattern matters: modules register their own subcommands onto the shared app
(the security module's CLI registers here), so a module can expose operator
commands without the platform internals depending on the module — the same
plugin-into-host relationship the MCP fleet uses.

## Interfaces

`app` is the root typer app with the five sub-apps mounted; `_apps` holds the
shared app instances; each sub-module registers its commands; `register(app)`
is the plugin hook the sync, smoke, update, and security modules use.

## Gotchas

The `__init__` does real work at import time (mounting sub-apps and
registering modules), so importing the CLI pulls in the security module —
the composition root is intentionally centralised rather than split across
platform internals.
