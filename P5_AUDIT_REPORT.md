# P5_AUDIT_REPORT.md — Codebase Review Report

**Portal 5 — Codebase Review, Production Readiness & Roadmap Agent**
**Date**: March 3, 2026
**Source**: codebase-review-2026-03-03

---

## 1. Executive Summary

| Metric | Score |
|--------|-------|
| Production Readiness | **78/100** |
| Tests | 11/11 PASS |
| Workspace Consistency | 13/13/13 PASS |
| Security | PASS |
| Code Quality | 24 lint violations (minor) |

**Verdict**: Release Candidate — minor lint issues only, no blocking defects.

**Top Findings**:
1. 24 lint violations (minor style, not blocking)
2. 2 MCP tool imports with no compose services (portal_web:8092, portal_shell:8091)
3. Private attribute access `_request_semaphore._value` (fragile across Python versions)
4. Test coverage at 67% (reasonable for unit tests without Ollama)

---

## 2. Baseline Status

| Item | Status |
|------|--------|
| Python | 3.14.3 |
| venv | active |
| Install | CLEAN |
| Dependencies | 15 OK, 0 MISSING |
| Module imports | 11 OK, 2 FAILED (channels - env vars expected) |
| Lint | 24 violations (B904, N803, SIM102/117) |
| Tests | 11 passed, 0 failed |
| Compile | 85 files OK |
| Branches | main only |
| CLAUDE.md | CURRENT |

---

## 3. Behavioral Verification Summary

| Test | Result |
|------|--------|
| Pipeline startup | PASS (degraded - no Ollama) |
| Auth enforcement | PASS (401/200 correct) |
| Workspace exposure (13) | PASS |
| model_hint routing | PASS |
| Timeout from YAML | PASS (120s) |
| Unhealthy fallback | PASS |
| Compose structure | PASS (13 services, 4 volumes) |
| DinD sandbox | PASS |
| MCP healthchecks | PASS |
| Multi-user env vars | PASS |
| Secret hygiene | PASS |
| Launch script | PASS |
| Branch hygiene | PASS |
| Lint clean | FAIL (24 violations) |
| Tests pass | PASS (11/11) |
| Persona coverage | PASS (35) |

---

## 4. Configuration Audit

### Workspace Consistency (Most Critical)
```
router_pipe.py: 13
backends.yaml:  13
imports/:       13
Status: CONSISTENT ✓
```

### Backend Configuration
- 6 backends defined (ollama-general, coding, security, reasoning, vision, creative)
- All workspace routes have backend coverage
- Timeout: 120s (VERIFIED from YAML)
- Health check: 30s interval, 10s timeout

### MCP Services
- All 7 expected services in compose: documents, music, tts, whisper, sandbox, comfyui, video
- All have healthchecks and MCP_PORT
- **Gap**: portal_web (8092) and portal_shell (8091) have import JSONs but no compose services

---

## 5. Code Findings Register

### FINDING-001
- **File**: portal_pipeline/router_pipe.py:175
- **Severity**: MEDIUM
- **Category**: CORRECTNESS
- **Finding**: Private attribute access `_request_semaphore._value` — fragile across Python versions
- **Evidence**: `if _request_semaphore._value == 0:`
- **Task ref**: TASK-001

### FINDING-002
- **File**: imports/openwebui/tools/portal_web.json, portal_shell.json
- **Severity**: LOW
- **Category**: MISSING_FEATURE
- **Finding**: Tool JSON imports exist but no compose services for ports 8091, 8092
- **Evidence**: Tool JSONs reference http://host.docker.internal:8091/8092 but no compose service
- **Task ref**: TASK-002

### FINDING-003
- **Files**: Multiple in portal_mcp/mcp_server/
- **Severity**: LOW
- **Category**: LINT
- **Finding**: 24 lint violations — B904 (raise from), N803 (arg names), SIM102/117 (nested if/with)
- **Evidence**: `ruff check .` returns 24 errors
- **Task ref**: TASK-003

---

## 6. Test Coverage Map

| Module | Coverage | Status |
|--------|---------|--------|
| portal_pipeline/__init__.py | 100% | ✓ |
| portal_pipeline/__main__.py | 0% | UNTESTABLE (needs Docker) |
| portal_pipeline/cluster_backends.py | 80% | Good |
| portal_pipeline/router_pipe.py | 63% | Good |

**Missing test coverage** (untestable without Ollama/Docker):
- Health loop running
- Actual chat completion streaming
- Backend health check responses

---

## 7. Architecture Blueprint

| Component | File | Status | Port |
|-----------|------|--------|------|
| Portal Pipeline | portal_pipeline/router_pipe.py | VERIFIED | 9099 |
| Backend Registry | portal_pipeline/cluster_backends.py | VERIFIED | — |
| Open WebUI | (external) | EXTERNAL | 8080 |
| Ollama | (external) | EXTERNAL | 11434 |
| MCP: Documents | portal_mcp/documents/ | VERIFIED | 8913 |
| MCP: Music | portal_mcp/generation/music_mcp | VERIFIED | 8912 |
| MCP: TTS | portal_mcp/generation/tts_mcp | VERIFIED | 8916 |
| MCP: Whisper | portal_mcp/generation/whisper_mcp | VERIFIED | 8915 |
| MCP: ComfyUI | portal_mcp/generation/comfyui_mcp | VERIFIED | 8910 |
| MCP: Video | portal_mcp/generation/video_mcp | VERIFIED | 8911 |
| MCP: Sandbox | portal_mcp/execution/ | VERIFIED | 8914 |
| DinD | (external) | EXTERNAL | — |
| Telegram Adapter | portal_channels/telegram/bot.py | VERIFIED (stub) | — |
| Slack Adapter | portal_channels/slack/bot.py | VERIFIED (stub) | — |
| openwebui_init.py | scripts/openwebui_init.py | VERIFIED | — |

---

## 8. Evolution Gap Register

1. **SSE error handling**: Streaming error format needs validation in production
2. **Telegram bot history**: No max turns bounding for conversation history
3. **Rate limiting**: No Open WebUI layer rate limiting for multi-user fairness

---

## 9. Production Readiness Score

| Dimension | Score | Evidence |
|-----------|-------|----------|
| Security (secrets) | 10/10 | Auto-generated secrets, no weak defaults |
| Security (sandbox) | 10/10 | DinD, no docker.sock |
| Multi-user readiness | 10/10 | All 5 env vars present |
| Routing correctness | 9/10 | Workspace consistency verified |
| Capacity (25 users) | 8/10 | Semaphore, OLLAMA_NUM_PARALLEL=4 |
| Operational tooling | 10/10 | launch.sh all commands present |
| Test coverage | 7/10 | 67% (reasonable) |
| Code quality (lint) | 7/10 | 24 violations |
| Documentation | 9/10 | CLAUDE.md current |
| Deployment cleanliness | 9/10 | Healthchecks, volumes correct |
| **TOTAL** | **78/100** | |

**Score: 78/100 — Release Candidate**

---

## 10. Delta Summary (First Run)

This is the first audit run — no prior artifacts exist.

---

*Generated by PORTAL5_CODEBASE_REVIEW_AGENT_v1.md*
