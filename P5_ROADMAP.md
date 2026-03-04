# P5_ROADMAP.md — Portal 5.0 Roadmap

```
Portal 5.0 Roadmap
==================
Last updated: March 4, 2026
Source: code-quality-agent-v3-delta

LEGEND: P1=Critical, P2=High, P3=Medium
STATUS: OPEN, IN_PROGRESS, DONE, BLOCKED
```

## Stability (Bugs, Broken Features, Test Failures)

| ID | Priority | Title | Status |
|----|----------|-------|--------|
| P5-ROAD-001 | P3 | Fix private attribute access (_request_semaphore._value) | DONE |
| P5-ROAD-002 | P3 | Lint cleanup (24 violations) | DONE |
| P5-ROAD-003 | P3 | Streaming error handling test coverage | DONE |

## Security (Hardening, Audit Items)

| ID | Priority | Title | Status |
|----|----------|-------|--------|
| P5-ROAD-010 | P2 | Verify portal_web/portal_shell MCP services or remove | DONE |

## Capacity (Multi-User, Concurrent Request Handling)

| ID | Priority | Title | Status |
|----|----------|-------|--------|
| P5-ROAD-020 | P3 | Load test with 25 concurrent users | DONE |
| P5-ROAD-021 | P3 | Verify semaphore exhaustion (503 + Retry-After) | DONE |

## Features (Planned Capabilities Not Yet Implemented)

| ID | Priority | Title | Status |
|----|----------|-------|--------|
| P5-ROAD-030 | P1 | Release v5.0.0 | DONE |
| P5-ROAD-031 | P2 | Multi-user rate limiting at Open WebUI layer | DONE (known limitation) |
| P5-ROAD-032 | P2 | Telegram bot conversation history bounding | DONE |

## Documentation (Gaps, Drift, Missing Guides)

| ID | Priority | Title | Status |
|----|----------|-------|--------|
| P5-ROAD-040 | P3 | CLAUDE.md verified current | DONE |
| P5-ROAD-041 | P2 | P5_HOW_IT_WORKS.md comprehensive documentation | DONE |

## Operations (Tooling, Monitoring, Backup)

| ID | Priority | Title | Status |
|----|----------|-------|--------|
| P5-ROAD-050 | P2 | launch.sh verified | DONE |
| P5-ROAD-051 | P2 | Backup/restore documentation | DONE |

## MCP Dependencies (From Phase 3 Verification)

| ID | Priority | Title | Status | Evidence |
|----|----------|-------|--------|----------|
| P5-ROAD-060 | P2 | Document MCP: Add python-docx/pptx/openpyxl to Dockerfile.mcp | DONE | Dependencies present in Dockerfile.mcp |
| P5-ROAD-061 | P2 | Music MCP: Bundle audiocraft in Dockerfile.mcp | DONE | Dependencies present in Dockerfile.mcp |
| P5-ROAD-062 | P2 | TTS MCP: fish-speech host-side setup documented | DONE | docs/FISH_SPEECH_SETUP.md created |
| P5-ROAD-063 | P2 | Whisper MCP: Bundle faster-whisper in Dockerfile.mcp | DONE | Dependencies present in Dockerfile.mcp |
| P5-ROAD-064 | P1 | ComfyUI integration: Document host-side setup required | DONE | docs/COMFYUI_SETUP.md verified and updated |
| P5-ROAD-065 | P1 | Video MCP: Document ComfyUI video model requirements | DONE | docs/COMFYUI_SETUP.md updated with Wan2.2 workflow |

---

## Phase 3 Verification Findings (doc-agent-v3)

| ID | Priority | Title | Status | Evidence |
|----|----------|-------|--------|----------|
| P5-ROAD-070 | P2 | Voice cloning fish-speech optional | DEGRADED | tts_mcp.py has graceful degradation |
| P5-ROAD-071 | P3 | Telegram adapter STUB | STUB | TELEGRAM_ENABLED=false in .env.example |
| P5-ROAD-072 | P3 | Slack adapter STUB | STUB | SLACK_ENABLED=false in .env.example |

## Documentation (Updated by doc-agent-v3)

| ID | Priority | Title | Status | Evidence |
|----|----------|-------|--------|----------|
| P5-ROAD-080 | P2 | P5_HOW_IT_WORKS.md comprehensive documentation | DONE | Full 17-section document created |
| P5-ROAD-081 | P2 | P5_VERIFICATION_LOG.md evidence log | DONE | Raw evidence for all Phase 3 tests |
| P5-ROAD-082 | P3 | Workspace consistency verified | DONE | 13/13/13 workspace IDs consistent |
| P5-ROAD-083 | P3 | Persona catalog verified | DONE | 35 personas, all YAML valid |

---

## Documentation (doc-agent-v3 delta run)

| ID | Priority | Title | Status | Evidence |
|----|----------|-------|--------|----------|
| P5-ROAD-084 | P1 | SearXNG secret_key hardcoded fix | DONE | settings.yml no longer has literal secret |
| P5-ROAD-085 | P1 | Prometheus open-webui scrape removed | DONE | prometheus.yml - only portal-pipeline + ollama |
| P5-ROAD-086 | P1 | Audio TTS/STT via env vars | DONE | compose env vars AUDIO_TTS_ENGINE etc |
| P5-ROAD-087 | P2 | Grafana dashboard provisioned | DONE | config/grafana/dashboards/ created |
| P5-ROAD-088 | P2 | backends.yaml hf.co/ prefix fix | DONE | Models use hf.co/ for GGUF format |
| P5-ROAD-089 | P2 | cluster_backends.py auto-detect config | DONE | Finds config relative to repo root |

---

## Score Progress

| Date | Score | Change | Notes |
|------|-------|--------|-------|
| 2026-03-03 | 90/100 | +2 | Initial review |
| 2026-03-03 | 92/100 | +2 | Test coverage improvement |
| 2026-03-03 | 94/100 | +2 | Documentation agent v3 complete |
| 2026-03-03 | 95/100 | +1 | Code quality agent v3 delta - additional tests |
| 2026-03-04 | 96/100 | +1 | doc-agent-v3 delta run - 11 fixes verified |
| 2026-03-04 | 95/100 | -1 | code-quality-agent-v3 delta - maintained, 1 lint fix |

---

## Documentation (doc-agent-v3 delta run - lint cleanup)

| ID | Priority | Title | Status | Evidence |
|----|----------|-------|--------|----------|
| P5-ROAD-092 | P3 | Lint cleanup N806 | DONE | MODELS constant moved to module level |
| P5-ROAD-093 | P3 | Remove unused json import | DONE | tts_mcp.py cleaned |
| P5-ROAD-094 | P3 | contextlib.suppress in whisper_mcp | DONE | cleaner exception handling |
| P5-ROAD-095 | P3 | Test suite maintained | DONE | 22 tests pass |

---

## Score Progress

| Date | Score | Change | Notes |
|------|-------|--------|-------|
| 2026-03-03 | 90/100 | +2 | Initial review |
| 2026-03-03 | 92/100 | +2 | Test coverage improvement |
| 2026-03-03 | 94/100 | +2 | Documentation agent v3 complete |
| 2026-03-03 | 95/100 | +1 | Code quality agent v3 delta - additional tests |
| 2026-03-04 | 96/100 | +1 | doc-agent-v3 delta run - 11 fixes verified |
| 2026-03-04 | 95/100 | -1 | code-quality-agent-v3 delta - maintained, 1 lint fix |
| 2026-03-04 | 95/100 | 0 | doc-agent-v3 delta - lint cleanup verified |

---

## Score Progress (code-quality-agent-v3 delta run)

| Date | Score | Change | Notes |
|------|-------|--------|-------|
| 2026-03-03 | 90/100 | +2 | Initial review |
| 2026-03-03 | 92/100 | +2 | Test coverage improvement |
| 2026-03-03 | 94/100 | +2 | Documentation agent v3 complete |
| 2026-03-03 | 95/100 | +1 | Code quality agent v3 delta - additional tests |
| 2026-03-04 | 96/100 | +1 | doc-agent-v3 delta run - 11 fixes verified |
| 2026-03-04 | 95/100 | -1 | code-quality-agent-v3 delta - maintained, 1 lint fix |
| 2026-03-04 | 95/100 | 0 | doc-agent-v3 delta - lint cleanup verified |
| 2026-03-04 | 95/100 | 0 | code-quality-agent-v3 delta run - R4 fixes applied |

---

## R4 Fixes (code-quality-agent-v3)

| ID | Priority | Title | Status | Evidence |
|----|----------|-------|--------|----------|
| P5-ROAD-100 | P1 | Port security: 11 services bound to 127.0.0.1 | DONE | docker-compose.yml ports updated |
| P5-ROAD-101 | P1 | wan2.2 download fix | DONE | snapshot_download instead of hf_hub_download |
| P5-ROAD-102 | P3 | TTS import consolidation | DONE | tts_mcp.py imports moved to top-level |
| P5-ROAD-103 | P3 | TTS_DEFAULT_VOICE in .env.example | DONE | Added with voice options |
| P5-ROAD-104 | P2 | Test coverage for MCP endpoints | DONE | test_mcp_endpoints.py created |
| P5-ROAD-105 | P2 | CHANGELOG.md [Unreleased] section | DONE | All R1-R4 fixes documented |

---

*Generated by portal5_code_quality_agent_v3.md*
*Previous: code-quality-agent-v3-delta*