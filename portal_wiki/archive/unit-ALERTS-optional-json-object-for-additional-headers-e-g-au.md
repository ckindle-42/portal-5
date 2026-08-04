---
id: unit-ALERTS-optional-json-object-for-additional-headers-e-g-au
kind: why
title: "ALERTS \u2014 Optional: JSON object for additional headers (e.g. auth tokens)"
sources:
- type: design
  path: docs/ALERTS.md
  section: 'Optional: JSON object for additional headers (e.g. auth tokens)'
last_generated_commit: ''
confidence: high
tags:
- docs
- ALERTS
created_at: 1783195000.820639
updated_at: 1783195000.820639
---

echo 'WEBHOOK_HEADERS={"Authorization": "Bearer YOUR_TOKEN"}' >> .env
```

**Alert event payload:**
```json
{
  "event": "backend_down",
  "message": "Backend 'ollama-general' has been unhealthy for 3 consecutive checks.",
  "backend_id": "ollama-general",
  "workspace": null,
  "timestamp": "2026-03-30T12:00:00+00:00",
  "metadata": {}
}
```

**Summary event payload:**
```json
{
  "event": "daily_summary",
  "timestamp": "2026-03-30T09:00:00+00:00",
  "total_requests": 1247,
  "requests_by_workspace": {"auto": 800, "auto-coding": 312, "auto-security": 135},
  "healthy_backends": 4,
  "total_backends": 4,
  "uptime_seconds": 86400.0
}
```
