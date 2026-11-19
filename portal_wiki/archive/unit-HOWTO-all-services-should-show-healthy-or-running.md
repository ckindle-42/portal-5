---
id: unit-HOWTO-all-services-should-show-healthy-or-running
historical: true
kind: why
title: "HOWTO \u2014 All services should show \"healthy\" or \"running\""
sources:
- type: design
  path: docs/HOWTO.md
  section: All services should show "healthy" or "running"
confidence: high
tags:
- docs
- HOWTO

---

```

**Troubleshoot:**
```bash
docker compose -f deploy/portal-5/docker-compose.yml logs <service-name>
```

---
