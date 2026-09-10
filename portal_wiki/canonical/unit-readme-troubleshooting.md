---
id: unit-readme-troubleshooting
kind: what
title: "README — Troubleshooting"
sources:
- type: code
  path: launch.sh
- type: code
  path: scripts/lib/util.sh
- type: code
  path: scripts/lib/services.sh
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.688112
updated_at: 1784946220.688112
---

**Services not starting:**
```bash
./launch.sh status          # See which services failed
docker compose -f deploy/portal-5/docker-compose.yml logs <service-name>
```

`status` runs `_cmd_status` (`scripts/lib/util.sh`), which reads container health
from `docker compose ps --format json` and renders a table over Open WebUI, the
pipeline, SearXNG, Prometheus, Grafana and the MCP servers, marking each healthy,
running, starting or failed. `logs` tails `docker compose logs -f <service>`
(default `portal-pipeline`).

**Out of disk space:**
```bash
docker system df            # See Docker disk usage
./launch.sh clean           # Stop services and remove the Open WebUI data volume
```

`clean` stops the stack and removes only the `open-webui-data` volume, explicitly
keeping the Ollama models volume — a clean wipes chat history and settings but
does not force the weights to re-download. The disk check in `_check_hardware`
warns below 20 GB free and suggests `docker system prune -a`; below 50 GB it
notes more is needed for the full catalog. Because the core models plus the FLUX
checkpoint (~12 GB) dominate a first download, a tight disk makes `up` or the
pulls fail mid-transfer — free space, then re-run `./launch.sh up`.

**Ollama still loading:**
```bash
./launch.sh pull-models     # Ensure at least one model is pulled
```

On a cold start `_ensure_native_services` restarts Ollama — `launchctl kickstart
-k system/com.portal5.ollama` on Apple Silicon (the pinned `com.portal5.ollama`
install, not Homebrew), `nohup ollama serve` on Linux — then polls
`http://localhost:11434/api/tags` for up to 10 seconds. The router only sees a
backend once its models finish loading, so a request fired immediately after boot
can hit an empty list; wait for Ollama to answer and retry.

**Port already in use:** `_check_ports` probes every reserved port before `up`
and, for a busy one, prints the owning process and a `kill` hint before exiting
1. Stop the conflicting process, run `./launch.sh down` if the owner is an old
Portal 5 stack, or override the port in `.env` (for example
`DOCUMENTS_HOST_PORT=9013`), then re-run `./launch.sh up`.

## Why

Nearly every first-run failure is one of four things — an unhealthy container, an
exhausted disk, a backend that has not finished loading, or a reserved port
already taken — so the troubleshooting surface is deliberately small and each
entry pairs the diagnostic command with the one safe remediation. `status` and
`_check_ports` name the specific offender rather than making the operator read
compose output, and `clean` is scoped to the data that is safe to lose because
nuking the Ollama volume would cost hours of re-downloads.
