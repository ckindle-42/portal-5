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
last_generated_commit: 64c5f5f41652bf67e97863ee1a6285289eaeea00
claims:
- probe: workspaces.functional
  pattern: '**{value} functional workspaces**'
- probe: workspaces.bench
  pattern: plus {value} benchmark workspaces
- probe: workspaces.total
  pattern: '{value} total'
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.679355
updated_at: 1784946220.679355
---

Select a workspace in the Open WebUI model dropdown to activate the right model
and tools automatically. Each workspace carries a `model_hint:` (the served model)
and a `tools:` array (the tool grants), both defined in `config/portal.yaml` and
loaded at import time into `WORKSPACES` by `portal/platform/inference/router/workspaces.py`
via `get_workspace_dict()`.

Portal 5 includes **23 functional workspaces** (plus 46 benchmark workspaces for
performance comparison, gated off by default behind the `eval` module, which is
disabled unless `PORTAL_ENABLE_EVAL=1` is set; 69 total —
`python3 -c "import yaml; d=yaml.safe_load(open('config/portal.yaml')); print(len(d['workspaces']))"`).
Benchmark workspaces are excluded from routing when the eval module is off, so the
daily model dropdown stays limited to the functional set.

## Why

Routing against a config-declared workspace catalog rather than a hardcoded model
list keeps model and tool selection an operator-editable fact: adding a workspace
is one block in `config/portal.yaml`, and `sync-config` propagates it to routing,
the model registry and Open WebUI presets. The eval-module gate exists so
benchmark lanes never leak into normal use unless the operator explicitly opts in.
