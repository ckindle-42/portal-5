---
id: unit-readme-troubleshooting
kind: what
title: "README \u2014 Troubleshooting"
sources:
- type: code
  path: launch.sh
- type: code
  path: scripts/lib/util.sh
last_generated_commit: a81c5e73569f981ecedb0d95b088563fcce651ed
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
from `docker compose ps --format json` and renders a table covering Open WebUI,
the pipeline, SearXNG, Prometheus, Grafana and the MCP servers, marking each
healthy, running, starting or failed. `logs` in `launch.sh` tails
`docker compose logs -f <service>` (default `portal-pipeline`).

**Out of disk space:**
```bash
docker system df            # See Docker disk usage
./launch.sh clean           # Stop services and remove the Open WebUI data volume
```

`clean` in `launch.sh` stops the stack and removes only the `open-webui-data`
volume, explicitly preserving the Ollama models volume — so a clean wipes chat
history and settings but does not force the model weights to re-download.

## Why

Most boot failures are container health or disk exhaustion, so the troubleshooting
surface is deliberately two commands. `status` resolves the question of which
container is not healthy without parsing compose output, and `clean` is scoped to
remove exactly the data that is safe to lose, because nuking the Ollama volume
would force hours of model re-downloads.
