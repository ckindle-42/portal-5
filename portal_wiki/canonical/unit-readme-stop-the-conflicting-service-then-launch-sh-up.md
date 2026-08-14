---
id: unit-readme-stop-the-conflicting-service-then-launch-sh-up
kind: what
title: "README \u2014 Stop the conflicting service, then ./launch.sh up"
sources:
- type: code
  path: scripts/lib/util.sh
- type: code
  path: launch.sh
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.689433
updated_at: 1784946220.689433
---

"Stop the conflicting service, then `./launch.sh up`" is the resolution for a
port-conflict abort. The `up` case in `launch.sh` runs `_check_ports`
(`scripts/lib/util.sh`) as a pre-flight: it probes each reserved port with `nc`
or a `/dev/tcp` fallback and, for a busy port, prints the owning process (via
`lsof` or `ss`) with a `kill` hint. If any port is taken the stack refuses to
start and exits 1.

The printed options are the actual remediation paths: stop the conflicting
process, run `./launch.sh down` if the owner is a previous Portal 5 stack (it also
stops native Speech and ComfyUI), or override the port in `.env` (for example
`DOCUMENTS_HOST_PORT=9013` for MCP Documents). After freeing the port, re-run
`./launch.sh up`.

## Why

Ports are reserved in this project, so silent collisions would produce confusing
half-started services and cross-talk between Open WebUI, the pipeline and the MCP
fleet. A hard pre-flight that names the offender and offers both stop and override
escapes turns the most common first-run failure into a one-line fix instead of a
log dig.
