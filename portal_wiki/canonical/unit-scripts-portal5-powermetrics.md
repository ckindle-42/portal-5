---
id: unit-scripts-portal5-powermetrics
kind: mixed
title: "Script \u2014 portal5-powermetrics"
sources:
- type: code
  path: scripts/portal5-powermetrics.py
  commit: 94ecf393
claims: []
confidence: high
tags:
- authored-v1
- scripts

---

Runs powermetrics continuously, parses the output, and exposes current power plus 1-min/10-min averages on a Unix domain socket.

## Why

The energy accounting needs a continuous power signal, and a Unix socket is the lightweight transport that lets the pipeline poll current watts without a heavier service. The averages are what make the instantaneous reading stable enough to charge per-request energy.

## Interfaces

The script runs as the root LaunchDaemon `com.portal5.powermetrics` and publishes JSON per line on `/tmp/portal5-powermetrics.sock`; the pipeline's energy accounting reads it there. Install it through the passwordless root dispatcher — `sudo -n /usr/local/sbin/portal5-root install-powermetrics`, source `deploy/root/portal5-root` — and read `/var/log/portal5-powermetrics.err` when the socket stops answering.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
