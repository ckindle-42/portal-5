---
id: unit-MCP_DEV_TOOLING-prometheus-fetch-patterns
kind: why
title: "MCP_DEV_TOOLING \u2014 Prometheus Fetch Patterns"
sources:
- type: design
  path: docs/MCP_DEV_TOOLING.md
  section: Prometheus Fetch Patterns
last_generated_commit: ''
confidence: high
tags:
- docs
- MCP_DEV_TOOLING
created_at: 1783195000.8749719
updated_at: 1783195000.8749719
---


```
http://localhost:9090/api/v1/query?query=portal5_requests_total
http://localhost:9090/api/v1/query?query=portal5_tool_calls_total
http://localhost:9090/api/v1/query?query=portal5_tps
http://localhost:9090/api/v1/query?query=up
http://localhost:3000/api/dashboards/home   (Grafana read-only API)
```

---
