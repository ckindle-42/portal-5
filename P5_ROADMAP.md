# P5_ROADMAP.md — Portal 5 Future Enhancements

```
Portal 5.2.1+ Roadmap
==================
Last updated: April 4, 2026
Version: 5.2.1 (production-ready)

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
| P5-FUT-005 | P2 | Weighted keyword scoring for content-aware routing | DONE | Replaced regex-based `_detect_workspace` with weighted keyword scoring. Each keyword carries weight 1-3 (weak/medium/strong), workspaces have activation thresholds, highest score above threshold wins. Handles overlapping signals naturally (e.g. "exploit in Python" → security wins, not coding). Implemented in v5.2.1. |
| P5-FUT-006 | P3 | Embedding-based semantic routing | FUTURE | Compare message embedding against workspace prototype embeddings using a local embedding model (e.g., nomic-embed-text). More accurate than keyword matching but adds latency and requires embedding infrastructure. Research needed on TTFT impact. |
| P5-FUT-007 | P3 | Lightweight ML text classifier | FUTURE | Train a small scikit-learn or ONNX classifier on workspace-labeled message samples. Adds a dependency and model file but could be very fast at inference. Research needed on accuracy vs maintenance cost. |
| P5-FUT-008 | P3 | Intent classification via small local model | FUTURE | Use a tiny intent classifier model (e.g., distilled BERT or fastText) to route messages. More flexible than keywords, handles novel phrasing. Research needed on model size, accuracy, and whether it fits within the lean pipeline constraint. |

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
| 2026-03-30 | 100/100 | v5.2.1-unreleased — P5-FUT-003 (analytics dashboard) + P5-FUT-004 (webhook channel) implemented, verified live |
| 2026-04-04 | 100/100 | v5.2.1 — P5-FUT-005 (weighted keyword routing), S18-S22 acceptance tests, persona prompt/signal fixes, documentation updates |

---

*Last updated: 2026-04-04*
*Part of Portal 5.2.1 release documentation*
