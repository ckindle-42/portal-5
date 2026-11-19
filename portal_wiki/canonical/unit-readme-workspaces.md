---
id: unit-readme-workspaces
kind: what
title: "README \u2014 Workspaces"
sources:
- type: code
  path: config/portal.yaml
- type: code
  path: portal/platform/inference/router/workspaces.py
- type: code
  path: config/backends.yaml
claims:
- probe: repo.path.exists
  path: config/portal.yaml
  equals: true
confidence: high
tags:
- docs
- verified-v1
---

Select a workspace in the Open WebUI model dropdown to activate the right model
and tools automatically. Each workspace carries a `model_hint:` (the served model)
and a `tools:` array (the tool grants), both defined in `config/portal.yaml` and
loaded at import time into `WORKSPACES` by `portal/platform/inference/router/workspaces.py`
via `get_workspace_dict()`.

Portal 5 includes functional workspaces plus benchmark workspaces for
performance comparison, gated behind the `eval` module (`unit-fact-module-states`,
opt-in via `portal module enable eval` or `PORTAL_ENABLE_EVAL=1`) (count them with
`python3 -c "import yaml; d=yaml.safe_load(open('config/portal.yaml')); print(len(d['workspaces']))"`).
Benchmark workspaces are excluded from routing when the `eval` module is disabled, so the
daily model dropdown stays limited to the functional set.

## Why

Routing against a config-declared workspace catalog rather than a hardcoded model
list keeps model and tool selection an operator-editable fact: adding a workspace
is one block in `config/portal.yaml`, and `sync-config` propagates it to routing,
the model registry and Open WebUI presets. The eval-module gate exists so
benchmark lanes never leak into normal use unless the operator explicitly opts in.
