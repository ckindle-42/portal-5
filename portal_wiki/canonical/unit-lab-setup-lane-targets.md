---
id: unit-lab-setup-lane-targets
kind: what
title: "LAB_SETUP \u2014 Lane Targets"
sources:
- type: code
  path: config/lab_targets.yaml
- type: code
  path: scripts/lab_targets.py
- type: code
  path: scripts/lab_ready.py
- type: code
  path: scripts/lib/lab.sh
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.520834
updated_at: 1784946220.520834
---

The web-browser, cloud, and OAST lanes described in the source doc do not
exist: launch.sh has no lab-web-up, lab-cloud-up, or oast-up command. The target
lanes that are implemented are the vulhub ephemeral lane, whose catalog entries
in `config/lab_targets.yaml` are started as docker-compose environments on LXC
112 by `cmd_up` in `scripts/lab_targets.py`; the static-host lane, dc, srv, web,
and meta3 from the `lab_hosts` block, probed by `scripts/lab_ready.py` over the
AD and web ports; and the SOC-analyst lane, `./launch.sh lab-up`, which starts
the Incalmo C2 and Talon SOC analyst containers through the lab profile in
`deploy/portal-5/docker-compose.lab.yml`.

## Why

The doc promised dedicated per-lane launch commands that were never wired into
launch.sh, so this unit records the lanes that actually exist rather than the
advertised ones. The three real lanes are distinguished by lifecycle: vulhub
targets are ephemeral compose sessions, static hosts are Proxmox VMs that stay
up, and the SOC lane is a container stack for the analyst pair.
