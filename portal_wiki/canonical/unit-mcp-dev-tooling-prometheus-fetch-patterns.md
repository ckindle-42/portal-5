---
id: unit-mcp-dev-tooling-prometheus-fetch-patterns
kind: what
title: "MCP_DEV_TOOLING \u2014 Prometheus Fetch Patterns"
sources:
- type: code
  path: portal/platform/inference/router/handlers.py
- type: code
  path: portal/platform/inference/router/metrics.py
- type: code
  path: config/prometheus/prometheus.yml
- type: code
  path: deploy/portal-5/docker-compose.yml
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.579963
updated_at: 1784946220.579963
---

The pipeline exposes Prometheus text on /metrics from `portal/platform/inference/router/handlers.py`.
Hand-rolled gauges report `portal_backends_healthy`, `portal_backends_total`,
`portal_uptime_seconds`, and `portal_workspaces_total`, while the registry adds the
labelled request counter `portal_requests_total`, the error counter
`portal_errors_total`, and the `portal5_*` family such as `portal5_tool_calls_total`.
Prometheus runs on :9090 scraping the pipeline (see the job in
`config/prometheus/prometheus.yml`), and Grafana on :3000 provisions dashboards from
`config/grafana/dashboards`. The pipeline MCP's `get_metrics_summary` reads the same
text endpoint and collapses it into a summary.

## Why

The patterns exist so an operator can verify behaviour end to end — request counts,
tool dispatch, errors — without guessing. Metric names are the contract between the
exposition and any consumer, so they are stated here as they are defined in the
code, and the dashboard and MCP consumers all read from the one /metrics endpoint
rather than maintaining their own instrumentation.
