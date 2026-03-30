# P5_ROADMAP.md — Portal 5 Future Enhancements

```
Portal 5.2+ Roadmap
==================
Last updated: March 30, 2026
Version: 5.2.0 (production-ready)

LEGEND: P1=Critical, P2=High, P3=Medium
STATUS: DONE, IN_PROGRESS, FUTURE
```

All v5.0–v5.2 items are marked DONE in CHANGELOG.md. This document tracks
genuinely open future work beyond the current stable release.

---

## Future Considerations (Not Yet Implemented)

| ID | Priority | Title | Status | Notes |
|----|----------|-------|--------|-------|
| P5-FUT-001 | P2 | Per-user rate limiting | FUTURE | Open WebUI lacks per-user rate limiting; deploy behind reverse proxy (nginx/Traefik) for now |
| P5-FUT-002 | P3 | Per-user quota enforcement | FUTURE | Admin controls for per-user quotas |
| P5-FUT-003 | P3 | Usage analytics dashboard | IN_PROGRESS | Grafana panels added: workspace request trends, top workspaces, model×workspace breakdown. Per-user usage blocked — Open WebUI does not expose user IDs to the Pipeline. |
| P5-FUT-004 | P3 | Webhook-based event notifications | IN_PROGRESS | Generic WebhookChannel implemented (portal_pipeline/notifications/channels/webhook.py); env vars: WEBHOOK_URL, WEBHOOK_HEADERS. Verbs: POST JSON to arbitrary endpoint on all alert and summary events. |

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

Implemented: `WebhookChannel` sends JSON POST to any user-defined HTTP endpoint on all
alert events (backend_down, backend_recovered, all_backends_down, config_error) and
daily_summary events. Configure via `WEBHOOK_URL` and optional `WEBHOOK_HEADERS` env vars.

Still TODO (out of scope for this item): new user signup, model pull completion, sandbox
security events — those would require additional event types and are tracked separately.

---

## Score History

| Date | Score | Notes |
|------|-------|-------|
| 2026-03-30 | 100/100 | v5.2.0 — all production items complete |

---

*Last updated: 2026-03-30*
*Part of Portal 5.2.0 release documentation*
