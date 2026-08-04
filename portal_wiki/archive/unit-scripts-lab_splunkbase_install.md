---
id: unit-scripts-lab_splunkbase_install
kind: mixed
title: "Script \u2014 lab_splunkbase_install"
sources:
- type: code
  path: scripts/lab_splunkbase_install.py
  commit: af437ebd
last_generated_commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799528.7184849
updated_at: 1785799528.7184849
---

Installs the Splunkbase add-ons that provide field aliases and CIM normalization for the BOTS datasets.

## Why

BOTS ships raw events; without the add-ons the sourcetype-specific fields do not extract. The install makes the data fully searchable with its field aliases intact, which is the difference between a dataset that answers hunts and a dataset that merely stores events.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
