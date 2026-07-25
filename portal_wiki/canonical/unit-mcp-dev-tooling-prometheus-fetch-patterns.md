---
id: unit-mcp-dev-tooling-prometheus-fetch-patterns
kind: what
title: "MCP_DEV_TOOLING \u2014 Prometheus Fetch Patterns"
sources:
- type: doc
  path: docs/MCP_DEV_TOOLING.md
  commit: 05e42ec2
  section: Prometheus Fetch Patterns
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.579963
updated_at: 1784946220.579963
---

```
http://localhost:9090/api/v1/query?query=portal5_requests_total
http://localhost:9090/api/v1/query?query=portal5_tool_calls_total
http://localhost:9090/api/v1/query?query=portal5_tps
http://localhost:9090/api/v1/query?query=up
http://localhost:3000/api/dashboards/home   (Grafana read-only API)
```

---
