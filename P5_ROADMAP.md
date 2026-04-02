# P5_ROADMAP.md — Portal 5 Future Enhancements

```
Portal 5.2.1+ Roadmap
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
| P5-FUT-003 | P3 | Usage analytics dashboard | DONE | Grafana portal5_overview.json v3: 6 new panels — workspace request trends, tokens by workspace, top workspaces, model×workspace breakdown, request rate. All queries use existing Prometheus metrics. Per-user blocked — Open WebUI doesn't expose user IDs to Pipeline. |
| P5-FUT-004 | P3 | Webhook-based event notifications | DONE | WebhookChannel implemented (portal_pipeline/notifications/channels/webhook.py). Env vars: WEBHOOK_URL, WEBHOOK_HEADERS. POSTs JSON to arbitrary HTTP endpoint on all alert and summary events. Live-verified 2026-03-30. |

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

IMPLEMENTED: `portal5_overview.json` v3 adds 6 new Usage Analytics panels (ids 13-18):
workspace request trends, tokens by workspace, top workspaces, model×workspace matrix, and
current request rate. All use existing Prometheus metrics — no new instrumentation needed.

Per-user analytics remain blocked: Open WebUI does not expose user IDs to the Pipeline.

### P5-FUT-004: Webhook-Based Event Notifications

IMPLEMENTED: `WebhookChannel` (`portal_pipeline/notifications/channels/webhook.py`) sends
JSON POST to any user-defined HTTP endpoint on all alert and daily summary events.
Configure via `WEBHOOK_URL` and optional `WEBHOOK_HEADERS` (JSON object) env vars.
Live-verified: a `config_error` test event was confirmed delivered to a listening endpoint.

---

## Score History

| Date | Score | Notes |
|------|-------|-------|
| 2026-03-30 | 100/100 | v5.2.0 — all production items complete |
| 2026-03-30 | 100/100 | v5.3.0-unreleased — P5-FUT-003 (analytics dashboard) + P5-FUT-004 (webhook channel) implemented, verified live |

---

*Last updated: 2026-03-30*
*Part of Portal 5.2.1 release documentation*
