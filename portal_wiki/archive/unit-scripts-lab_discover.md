---
id: unit-scripts-lab_discover
kind: mixed
title: "Script \u2014 lab_discover"
sources:
- type: code
  path: scripts/lab_discover.py
  commit: af437ebd
last_generated_commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799521.465935
updated_at: 1785799521.465935
---

Probes the Proxmox host via the proven transport and reports actual state, writing nothing and changing no bench code — every later lab phase builds on what this reports.

## Why

A lab phase that assumes a state instead of discovering it fails on the first mismatch; the discover script is the ground truth the later phases build on. Writing nothing is the contract — the discovery is observation, and the resolution phases apply their own changes.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
