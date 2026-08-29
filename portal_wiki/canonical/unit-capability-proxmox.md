---
id: unit-capability-proxmox
kind: mixed
title: "Proxmox MCP \u2014 lab virtualization control plane"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/security/tools/proxmox_mcp.py
- type: code
  path: deploy/portal-5/docker-compose.yml
claims: []
confidence: high
tags:
- capability
- mcp
- security
created_at: 1788030600.446044
updated_at: 1788030600.446044
---

# Proxmox MCP — lab virtualization control plane

## What

The Proxmox MCP (`portal/modules/security/tools/proxmox_mcp.py`, port 8927)
wraps the Proxmox API to drive the security lab's VMs and LXC containers. It is
IDE-exposed (`expose_to_pipeline: false`, `expose_to_ide: true`) — an operator
tool for standing up and tearing down lab hosts, not a persona-triggerable
surface.

## How it's used

Its tools cover the full lifecycle: node and cluster status, VM and container
inventory and find-by-name, power operations (start, shutdown, stop, reset,
reboot, suspend, resume), clone and delete, snapshot create/rollback/delete,
VM exec and guest-agent info, and container exec. Node names are
auto-discovered where an operator omits them, and long-running API tasks are
awaited so a tool call returns after the operation actually settles.

## Why it exists

The lab needs reproducible infrastructure without a human clicking a web UI:
snapshot a baseline, run an engagement, roll back, repeat. Exposing that as
typed tools — rather than raw Proxmox shell — gives an operator agent a safe,
bounded control plane and lets the bench harness treat VM state as scriptable.

## Value

Engagement lifecycles become idempotent and reviewable: the same calls that
deploy a target also tear it down and restore its snapshot. Keeping it
IDE-only preserves the security boundary — a pipeline persona can neither see
nor mutate lab infrastructure.
