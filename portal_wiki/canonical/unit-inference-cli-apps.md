---
id: unit-inference-cli-apps
kind: mixed
title: "Inference CLI apps \u2014 shared typer app instances"
sources:
- type: code
  path: portal/platform/inference/cli/_apps.py
  commit: 5fbf51f8
last_generated_commit: 5fbf51f8
claims: []
confidence: high
tags:
- authored-v1
- platform
- cli
created_at: 1785797833.282933
updated_at: 1785797833.282933
---

`_apps.py` holds the shared typer app instances — one per command group
(config, workspace, models, module, agent) — created in one place so the
sub-modules can import them without circular-import cycles.

## Why

Each sub-module registers commands onto its group's app, and if the apps
lived inside the sub-modules, importing one would pull in another and create
a cycle. Centralising the app instances breaks that: the sub-modules import
from `_apps`, the `__init__` imports the sub-modules, and nothing imports
backwards.

## Interfaces

Exports `config_app`, `workspace_app`, `models_app`, `module_app`, and
`agent_app` — the five typer app instances with their help strings.
