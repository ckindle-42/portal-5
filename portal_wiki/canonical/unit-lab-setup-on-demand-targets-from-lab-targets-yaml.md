---
id: unit-lab-setup-on-demand-targets-from-lab-targets-yaml
kind: what
title: "LAB_SETUP \u2014 On-Demand Targets (from lab_targets.yaml)"
sources:
- type: code
  path: scripts/lab_targets.py
- type: code
  path: scripts/lab_host.py
- type: code
  path: config/lab_targets.yaml
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.520446
updated_at: 1784946220.520446
---

On-demand targets are driven by `python3 scripts/lab_targets.py`, not by a
launch.sh subcommand. The CLI accepts up, down, ephemeral, status, and list.
The catalog is loaded from `config/lab_targets.yaml`. The up action accepts
either a catalog id such as vulhub-log4shell-solr or a raw vulhub path such as
struts2/s2-045, resolves the compose file path on LXC 112 through
`scripts/lab_host.py`, and runs docker compose up. The down action runs docker
compose down for that environment. The ephemeral action does not itself run a
bench command and does not tear the target down: it records the resolved port
mapping and writes `.port_map.json` under the security core results directory so
the bench knows where to connect.

## Why

Accepting both a catalog id and a raw vulhub path lets the operator spin up any
upstream environment without editing the catalog first, while the catalog id
path carries the cve and technique metadata the bench needs. The ephemeral
action is deliberately narrow: it only resolves and records the port mapping,
leaving the up, bench, and down steps to the caller.
