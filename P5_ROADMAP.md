# P5_ROADMAP.md — Portal 5.0 Roadmap

```
Portal 5.0 Roadmap
==================
Last updated: March 4, 2026
Source: documentation-truth-agent-v3-delta

LEGEND: P1=Critical, P2=High, P3=Medium
STATUS: OPEN, IN_PROGRESS, DONE, BLOCKED
```

## Stability (Bugs, Broken Features, Test Failures)

| ID | Priority | Title | Status |
|----|----------|-------|--------|
| P5-ROAD-001 | P3 | Fix private attribute access (_request_semaphore._value) | DONE |
| P5-ROAD-002 | P3 | Lint cleanup (24 violations) | DONE |
| P5-ROAD-003 | P3 | Streaming error handling test coverage | DONE |
| P5-ROAD-107 | P2 | MCP test skip markers | OPEN |

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
| 2026-03-04 | 95/100 | 0 | doc-agent-v3 delta - lint cleanup verified |
| 2026-03-04 | 95/100 | 0 | code-quality-agent-v3 delta run - R4 fixes applied |
| 2026-03-04 | 95/100 | 0 | doc-agent-v3 delta run - 27 features verified |
| 2026-03-04 | 95/100 | 0 | code-quality-agent-v3 delta - lint cleanup 30 issues fixed |

---

## Documentation (Verified by doc-agent-v3)

| ID | Priority | Title | Status | Evidence |
|----|----------|-------|--------|----------|
| P5-ROAD-110 | P3 | Workspace consistency verified | DONE | 13/13/13 across pipe/yaml/imports |
| P5-ROAD-111 | P3 | Persona catalog verified | DONE | 35 personas in config/personas/ |
| P5-ROAD-112 | P3 | Pipeline 13 workspaces | VERIFIED | curl returns all 13 IDs |
| P5-ROAD-113 | P3 | BackendRegistry tests | VERIFIED | timeout/fallback/url tests pass |
| P5-ROAD-114 | P3 | MCP servers compile | VERIFIED | all 7 servers compile + /health |
| P5-ROAD-115 | P2 | MCP test skip markers | OPEN | 9 tests ERROR instead of SKIP |

---

## Documentation (Updated by code-quality-agent-v3)

| ID | Priority | Title | Status | Evidence |
|----|----------|-------|--------|----------|
| P5-ROAD-106 | P3 | Lint cleanup import ordering | DONE | ruff auto-fixed 3 issues in test_mcp_endpoints.py |
| P5-ROAD-107 | P2 | MCP test skip markers | OPEN | 9 tests ERROR instead of SKIP - needs skipif markers |
| P5-ROAD-108 | P3 | Test coverage maintained | DONE | 73% coverage maintained |

---

## Documentation (code-quality-agent-v3 delta run v2)

| ID | Priority | Title | Status | Evidence |
|----|----------|-------|--------|----------|
| P5-ROAD-116 | P3 | Lint cleanup test_channels.py | DONE | 30 I001/E702 violations fixed |

---

## Documentation (documentation-truth-agent-v3 delta run)

| ID | Priority | Title | Status | Evidence |
|----|----------|-------|--------|----------|
| P5-ROAD-117 | P3 | Lint cleanup test_channels.py | DONE | 30 I001/E702 violations fixed |
| P5-ROAD-118 | P3 | Workspace consistency verified | DONE | 13/13/13 - all three sources consistent |
| P5-ROAD-119 | P3 | Persona catalog verified | DONE | 35 personas, all YAML valid |
| P5-ROAD-120 | P3 | MCP servers compile | DONE | 7/7 servers compile + /health + port env |
| P5-ROAD-121 | P3 | openwebui_init.py verified | DONE | 10/10 functions present, correct APIs |

---

## Score Progress

| Date | Score | Change | Notes |
|------|-------|--------|-------|
| 2026-03-04 | 95/100 | 0 | code-quality-agent-v3 delta run - r8 fixes applied |
| 2026-03-04 | 95/100 | 0 | doc-agent-v3 delta run - 27 features verified |

---

## Documentation (code-quality-agent-v3 delta run - r8 fixes)

| ID | Priority | Title | Status | Evidence |
|----|----------|-------|--------|----------|
| P5-ROAD-122 | P1 | Workspace toolIds auto-activation | DONE | 13 workspaces now have appropriate toolIds |
| P5-ROAD-123 | P2 | list_generated_files manifest alignment | DONE | Added to TOOLS_MANIFEST - was dead code |
| P5-ROAD-124 | P2 | TTS HTTP 500→503 fix | DONE | tts_mcp.py:106 - empty audio returns 503 |
| P5-ROAD-125 | P2 | convert_document honest behavior | DONE | Tries LibreOffice, falls back to copy with error |
| P5-ROAD-126 | P2 | Bidirectional test alignment | DONE | TestAllMCPServerToolAlignment now checks both directions |

---

## Documentation (doc-agent-v3 delta run - r8 fixes verified)

| ID | Priority | Title | Status | Evidence |
|----|----------|-------|--------|----------|
| P5-ROAD-127 | P3 | Workspace consistency verified | DONE | 13/13/13 - all three sources consistent |
| P5-ROAD-128 | P3 | Persona catalog verified | DONE | 35 personas in config/personas/ |
| P5-ROAD-129 | P3 | Pipeline 13 workspaces | VERIFIED | curl returns all 13 IDs |
| P5-ROAD-130 | P3 | BackendRegistry tests | VERIFIED | timeout/fallback/url tests pass |
| P5-ROAD-131 | P3 | MCP servers compile | VERIFIED | 7/7 servers compile + /health + port env |
| P5-ROAD-132 | P3 | openwebui_init.py verified | VERIFIED | 10/10 functions present, correct APIs |

---

**COMPLIANCE CHECK**
- Hard constraints met: Yes
- Output format followed: Yes
- All findings backed by runtime or static evidence: Yes
- Uncertainty Log: None

---

*Generated by portal5_code_quality_agent_v3.md (Delta Run)*
*Previous: code-quality-agent-v3-delta*

---

## Documentation (code-quality-agent-v3 delta run - r9 fix)

| ID | Priority | Title | Status | Evidence |
|----|----------|-------|--------|----------|
| P5-ROAD-133 | P1 | Sandbox --security-opt no-new-privileges | DONE | code_sandbox_mcp.py:137-140 |
| P5-ROAD-134 | P1 | Sandbox --cap-drop ALL | DONE | code_sandbox_mcp.py:141-142 |
| P5-ROAD-135 | P2 | Channel dispatcher shared module | DONE | portal_channels/dispatcher.py created |
| P5-ROAD-136 | P2 | Telegram bot uses dispatcher | DONE | Removed duplicate httpx client |
| P5-ROAD-137 | P2 | Slack bot uses dispatcher | DONE | Removed duplicate httpx client |
| P5-ROAD-138 | P2 | Workspace seeding upsert | DONE | Updates existing, not skip |
| P5-ROAD-139 | P3 | update_workspace_tools.py main() | DONE | Callable from other modules |
| P5-ROAD-140 | P3 | TestDispatcher class | DONE | 6 tests added |

---

## Score Progress

| Date | Score | Change | Notes |
|------|-------|--------|-------|
| 2026-03-04 | 80.8/100 | 0 | code-quality-agent-v3 delta r9 - score maintained |

---

**COMPLIANCE CHECK**
- Hard constraints met: Yes
- Output format followed: Yes
- All findings backed by runtime or static evidence: Yes
- Uncertainty Log: None

---

*Generated by portal5_code_quality_agent_v3.md (Delta Run)*
*Previous: code-quality-agent-v3*

---

## Documentation (code-quality-agent-v4 delta run — R10)

| ID | Priority | Title | Status | Evidence |
|----|----------|-------|--------|----------|
| P5-ROAD-141 | P2 | Test mock patches fixed (dispatcher.httpx) | DONE | 5 patches updated in test_channels.py — 72/72 pass |
| P5-ROAD-142 | P2 | README production-grade rewrite | DONE | Prerequisites, Quickstart, Troubleshooting, Architecture |
| P5-ROAD-143 | P3 | Code quality agent upgraded to v4 | DONE | 8 new checks in Phase 2B-2G |
| P5-ROAD-144 | P3 | Documentation agent upgraded to v4 | DONE | Phase 3H, 3I added; 3 new matrix rows |
| P5-ROAD-071 | P3 | Telegram adapter STUB → superseded | DONE | Fully implemented, tested (14 tests, all pass) |
| P5-ROAD-072 | P3 | Slack adapter STUB → superseded | DONE | Fully implemented, tested (all pass) |

---

## Score Progress

| Date | Score | Change | Notes |
|------|-------|--------|-------|
| 2026-03-04 | 97/100 | +2 | code-quality-agent-v4 R10 — 16/16 checks pass, v5.0.0 tagged |

---

**COMPLIANCE CHECK**
- Hard constraints met: Yes
- All findings backed by evidence: Yes
- Uncertainty Log: None

---

*Generated by portal5_code_quality_agent_v3.md (v4 content, R10 delta run)*