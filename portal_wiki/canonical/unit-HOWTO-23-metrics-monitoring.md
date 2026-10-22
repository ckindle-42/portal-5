---
id: unit-HOWTO-23-metrics-monitoring
kind: why
title: "HOWTO \u2014 23. Metrics & Monitoring"
sources:
- type: code
  path: portal/platform/inference/router/handlers.py
- type: code
  path: portal/platform/inference/router/metrics.py
- type: code
  path: portal/platform/inference/router/power.py
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1783195000.8631291
updated_at: 1792281600
---

**What:** Prometheus metrics collection and Grafana dashboards for the pipeline.

**How:** The pipeline exposes Prometheus-compatible metrics at `GET /metrics` (`metrics` in `portal/platform/inference/router/handlers.py` — intentionally unauthenticated so Prometheus can scrape it). The `prometheus` service scrapes on port 9090 using `config/prometheus/prometheus.yml`, and the `grafana` service serves on port 3000 with dashboards and datasources provisioned from `config/grafana/dashboards` and `config/grafana/datasources` (both defined in `deploy/portal-5/docker-compose.yml`). Grafana login is `admin` / `GRAFANA_PASSWORD` from `.env`. Both are part of the default `./launch.sh up` stack.

Exporting a dashboard or panel as PNG/PDF (Share → Export as image / PDF) renders through the `grafana-image-renderer` sidecar defined next to `grafana` in `deploy/portal-5/docker-compose.yml` — a compose-internal service with no host port that shares the `GRAFANA_RENDERER_TOKEN` secret with Grafana (override it in `.env`; Grafana 13 requires a non-default renderer token).

**Inspect:**
```bash
./launch.sh status
curl http://localhost:9090/-/healthy
curl http://localhost:9099/metrics
```

The speed panels read token-weighted counters. `portal_decode_tokens_total` and `portal_decode_seconds_total` count every generated token over model decode time: Ollama `eval_count` / `eval_duration` when the engine reports them (`source="engine"`), otherwise a caller-supplied `decode_seconds` (`source="measured"`). They do not fall back to wall clock; a request with tokens but no decode time increments `portal_tps_unmeasured_total` and is left out of the ratio. `portal_answer_tokens_total` and `portal_answer_seconds_total` count only visible-answer rows with at least 32 answer tokens and a supplied answer split. The shared `MIN_ANSWER_TOKENS_FOR_RATE = 32` threshold avoids answer-rate noise from short, bursty generations; shorter answers remain in decode and TTFT metrics but not the answer-rate counters or daily answer-rate totals. `portal_ttft_seconds` is the time from request to the first generated token. Grafana divides five-minute rates, `sum by(model) (rate(portal_decode_tokens_total[5m])) / sum by(model) (rate(portal_decode_seconds_total[5m]))`, and the same shape for the answer counters and for workspace. TTFT panels use `histogram_quantile` on `portal_ttft_seconds_bucket`. `portal_tokens_per_second` is deprecated for one release: it is a per-request rate and can still fall back to wall clock.

## Why

Observability is kept out of Open WebUI and out of the pipeline's code: the router only emits Prometheus text, and dashboards live as provisioned files under `config/grafana/`. That makes metrics reproducible from git — there are no click-configured panels to lose — and lets an operator point any Prometheus-compatible stack at the pipeline without changing Portal itself.
