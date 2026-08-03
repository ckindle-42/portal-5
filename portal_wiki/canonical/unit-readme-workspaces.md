---
id: unit-readme-workspaces
kind: what
title: "README \u2014 Workspaces"
sources:
- type: doc
  path: README.md
  commit: 05e42ec2
  section: Workspaces
last_generated_commit: 05e42ec2
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
created_at: 1784946220.679355
updated_at: 1784946220.679355
---

Select a workspace in the Open WebUI model dropdown to activate the right model
and tools automatically.

Portal 5 includes **23 functional workspaces** (plus 65 benchmark workspaces for performance comparison, gated off by default behind the `eval` module; 88 total — `python3 -c "import yaml; d=yaml.safe_load(open('config/portal.yaml')); print(len(d['workspaces']))"`).
