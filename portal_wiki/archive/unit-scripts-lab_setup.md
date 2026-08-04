---
id: unit-scripts-lab_setup
kind: mixed
title: "Script \u2014 lab_setup"
sources:
- type: code
  path: scripts/lab_setup.py
  commit: af437ebd
last_generated_commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799525.093858
updated_at: 1785799525.093858
---

Sets up the lab targets with heavy/skip-heavy, update, and dry-run modes.

## Why

The lab setup is a sequence of provisioning steps, and the script is the repeatable wrapper with the safety modes (skip-heavy for CI, dry-run for review) that make it safe to run without destroying a working lab.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
