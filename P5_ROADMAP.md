# P5_ROADMAP.md — Portal 5 Future Enhancements

```
Portal 5.2+ Roadmap
==================
Last updated: March 30, 2026
Version: 5.2.0 (production-ready)

LEGEND: P1=Critical, P2=High, P3=Medium
STATUS: FUTURE, IN_PROGRESS, DONE
```

All v5.0–v5.2 items are marked DONE in CHANGELOG.md. This document tracks
genuinely open future work beyond the current stable release.

---

## Future Considerations (Not Yet Implemented)

| ID | Priority | Title | Status | Notes |
|----|----------|-------|--------|-------|
| P5-FUT-001 | P2 | Per-user rate limiting | FUTURE | Open WebUI lacks per-user rate limiting; deploy behind reverse proxy (nginx/Traefik) for now |
| P5-FUT-002 | P3 | Per-user quota enforcement | FUTURE | Admin controls for per-user quotas |
| P5-FUT-003 | P3 | Usage analytics dashboard | FUTURE | Beyond current Prometheus/Grafana metrics |
| P5-FUT-004 | P3 | Webhook-based event notifications | FUTURE | Event-driven integrations |

---

## Implementation Notes

### P5-FUT-001: Per-User Rate Limiting

Open WebUI does not have built-in per-user rate limiting. Current workaround:
deploy behind a reverse proxy (nginx, Traefik) with rate limiting configured there.

Reference: `docs/ADMIN_GUIDE.md` — Security Notes section.

### P5-FUT-002: Per-User Quota Enforcement

Admin controls for setting per-user quotas (e.g., daily request limits, model access restrictions).
Would require either Open WebUI plugin/extension point or reverse proxy layer.

### P5-FUT-003: Usage Analytics Dashboard

Beyond current Prometheus metrics (request counts, backend health), a usage analytics
dashboard could provide: per-user usage, per-workspace usage trends, cost estimation,
model switch frequency.

Current: Prometheus + Grafana at `:3000` with `portal5_overview.json` dashboard.

### P5-FUT-004: Webhook-Based Event Notifications

Enable external systems (Slack, PagerDuty, custom webhooks) to receive events from Portal 5
such as: new user signup, model pull completion, backend health changes, sandbox security events.

Would require an event dispatcher module in `portal_pipeline/` or a new MCP-style service.

---

## Score History

| Date | Score | Notes |
|------|-------|-------|
| 2026-03-30 | 100/100 | v5.2.0 — all production items complete |

---

*Last updated: 2026-03-30*
*Part of Portal 5.2.0 release documentation*
