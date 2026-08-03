---
id: unit-inference-cli-update
kind: mixed
title: "Inference CLI update \u2014 full upgrade flow"
sources:
- type: code
  path: portal/platform/inference/cli/update.py
  commit: 5fbf51f8
last_generated_commit: 5fbf51f8
claims: []
confidence: high
tags:
- authored-v1
- platform
- cli
created_at: 1785797880.694311
updated_at: 1785797880.694311
---

`portal update` is the full Portal 5 upgrade flow: git pull, rebuild the
containers, pull the models, re-seed the wiki, and restart — one command for
the whole upgrade.

## Why

An upgrade is a sequence of steps with dependencies (rebuild before restart,
pull models before seeding), and doing it by hand is where operators make
mistakes. The single command encodes the correct order, so the platform can
be upgraded the same way every time. It is the zero-setup promise applied to
maintenance.

## Interfaces

`cmd_update` orchestrates the pull → build → models → seed → restart
sequence; `register` attaches it as the top-level `update` command.

## Gotchas

The update touches the running stack — it is a maintenance command with real
consequences, and it should be run deliberately, not by a cron.
