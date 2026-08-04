---
id: unit-HOWTO-all-services-should-show-healthy-or-running
kind: why
title: "HOWTO \u2014 All services should show \"healthy\" or \"running\""
sources:
- type: design
  path: docs/HOWTO.md
  section: All services should show "healthy" or "running"
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.838964
updated_at: 1783195000.838964
---

```

**Troubleshoot:**
```bash
docker compose -f deploy/portal-5/docker-compose.yml logs <service-name>
```

---
