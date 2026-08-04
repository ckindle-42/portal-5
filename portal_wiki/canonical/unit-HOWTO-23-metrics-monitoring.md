---
id: unit-HOWTO-23-metrics-monitoring
kind: why
title: "HOWTO \u2014 23. Metrics & Monitoring"
sources:
- type: code
  path: portal/platform/inference/router/handlers.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1783195000.8631291
updated_at: 1783195000.8631291
---

**What:** Prometheus metrics collection and Grafana dashboards for the pipeline.

**How:** The pipeline exposes Prometheus-compatible metrics at `GET /metrics` (`metrics` in `portal/platform/inference/router/handlers.py` — intentionally unauthenticated so Prometheus can scrape it). The `prometheus` service scrapes on port 9090 using `config/prometheus/prometheus.yml`, and the `grafana` service serves on port 3000 with dashboards and datasources provisioned from `config/grafana/dashboards` and `config/grafana/datasources` (both defined in `deploy/portal-5/docker-compose.yml`). Grafana login is `admin` / `GRAFANA_PASSWORD` from `.env`. Both are part of the default `./launch.sh up` stack.

**Inspect:**
```bash
./launch.sh status
curl http://localhost:9090/-/healthy
curl http://localhost:9099/metrics
```

## Why

Observability is kept out of Open WebUI and out of the pipeline's code: the router only emits Prometheus text, and dashboards live as provisioned files under `config/grafana/`. That makes metrics reproducible from git — there are no click-configured panels to lose — and lets an operator point any Prometheus-compatible stack at the pipeline without changing Portal itself.
