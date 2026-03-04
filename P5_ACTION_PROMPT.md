# P5_ACTION_PROMPT.md — Action Items

**Session bootstrap:**
```bash
cd /Users/chris/projects/portal-5
source .venv/bin/activate || (uv venv && source .venv/bin/activate && uv pip install -e ".[dev]")
git checkout main && git pull
python3 -m pytest tests/ -q --tb=no && echo "Tests OK" || echo "Tests BROKEN — fix before proceeding"
python3 -m ruff check portal_pipeline/ scripts/ --quiet && echo "Lint OK" || echo "Lint violations present"
```

---

## TASK-001 (RESOLVED)
- **Tier**: 2 (fix soon)
- **File(s)**: portal_pipeline/router_pipe.py:175
- **Category**: CORRECTNESS
- **Finding**: Private attribute access `_request_semaphore._value` is fragile across Python versions
- **Action**: Replace with `asyncio.BoundedSemaphore` wrapper or use try/except around acquire with nowait pattern
- **Status**: DONE - Changed to `.locked()` method
- **Risk**: MEDIUM
- **Acceptance**: Run lint check - should pass with no F841 violations

---

## TASK-002 (RESOLVED)
- **Tier**: 3 (backlog)
- **File(s)**: imports/openwebui/tools/portal_web.json, portal_shell.json
- **Category**: MISSING_FEATURE
- **Finding**: Tool JSON imports existed but no compose services for ports 8091, 8092
- **Action**: Either add mcp-web and mcp-shell services to docker-compose.yml OR remove the unused JSON imports
- **Status**: DONE - Deleted unused JSON files
- **Risk**: LOW
- **Acceptance**: `grep -c "8091\|8092" imports/openwebui/tools/` returns 0

---

## TASK-003 (RESOLVED)
- **Tier**: 3 (backlog)
- **File(s)**: portal_mcp/mcp_server/ (multiple files)
- **Category**: LINT
- **Finding**: 24 lint violations - B904 (raise from), N803 (arg names), SIM102/117 (nested if/with)
- **Action**: Fix lint violations in mcp_server/ files
- **Status**: DONE - All violations resolved
- **Risk**: LOW
- **Acceptance**: `python3 -m ruff check portal_mcp/ --quiet` returns no errors

---

## TASK-004 (PARTIAL)
- **Tier**: 3 (backlog)
- **File(s)**: portal_pipeline/router_pipe.py
- **Category**: TEST_GAP
- **Finding**: Test coverage at 63% - streaming error handling not tested
- **Action**: Add test for SSE error chunk formatting
- **Status**: PARTIAL - Streaming error tests exist in test suite
- **Risk**: LOW
- **Acceptance**: Coverage increases

---

## TASK-005 (OPEN)
- **Tier**: 3 (backlog)
- **File(s)**: portal_pipeline/
- **Category**: PERFORMANCE
- **Roadmap ID**: P5-ROAD-020
- **Finding**: Load test with 25 concurrent users not verified
- **Action**: Run concurrent load test against Pipeline API
- **Status**: OPEN
- **Risk**: MEDIUM
- **Acceptance**: Pipeline handles 25 concurrent requests without failures

---

## TASK-006 (OPEN)
- **Tier**: 3 (backlog)
- **File(s)**: portal_pipeline/router_pipe.py
- **Category**: CORRECTNESS
- **Roadmap ID**: P5-ROAD-021
- **Finding**: Semaphore exhaustion behavior (503 + Retry-After header) not verified
- **Action**: Verify that when semaphore is full, proper 503 response with Retry-After is returned
- **Status**: OPEN
- **Risk**: MEDIUM
- **Acceptance**: Semaphore exhaustion returns 503 with Retry-After header

---

## TASK-007 (OPEN)
- **Tier**: 1 (critical)
- **File(s)**: Multiple
- **Category**: RELEASE
- **Roadmap ID**: P5-ROAD-030
- **Finding**: Release v5.0.0 not completed
- **Action**: Complete all P1 items, run full test suite, tag release
- **Status**: OPEN
- **Risk**: HIGH
- **Acceptance**: All P1 items done, tests pass, version tagged

---

## TASK-008 (OPEN)
- **Tier**: 2 (high)
- **File(s)**: Open WebUI configuration
- **Category**: SECURITY
- **Roadmap ID**: P5-ROAD-031
- **Finding**: Multi-user rate limiting not implemented at Open WebUI layer
- **Action**: Configure rate limiting in Open WebUI or via middleware
- **Status**: OPEN
- **Risk**: MEDIUM
- **Acceptance**: Rate limits enforced for multi-user scenario

---

## TASK-009 (OPEN)
- **Tier**: 2 (high)
- **File(s)**: portal_channels/telegram/bot.py
- **Category**: RESOURCE
- **Roadmap ID**: P5-ROAD-032
- **Finding**: Telegram bot conversation history bounding not implemented
- **Action**: Implement sliding window or token budget for conversation history
- **Status**: OPEN
- **Risk**: MEDIUM
- **Acceptance**: Telegram bot respects conversation history limits

---

## TASK-010 (RESOLVED)
- **Tier**: 2 (high)
- **File(s)**: docs/
- **Category**: DOCUMENTATION
- **Roadmap ID**: P5-ROAD-051
- **Finding**: Backup/restore documentation missing
- **Action**: Create backup/restore documentation for Portal 5
- **Status**: DONE - docs/BACKUP_RESTORE.md created with comprehensive backup/restore procedures
- **Risk**: LOW
- **Acceptance**: docs/BACKUP_RESTORE.md exists and is complete

---

## TASK-011 (RESOLVED)
- **Tier**: 2 (high)
- **File(s)**: Dockerfile.mcp
- **Category**: DEPENDENCY
- **Roadmap ID**: P5-ROAD-060
- **Finding**: Document MCP dependencies - verification agent reported STUB but deps ARE in Dockerfile
- **Action**: Verify python-docx, python-pptx, openpyxl in Dockerfile.mcp
- **Status**: RESOLVED - Dependencies already present in Dockerfile.mcp lines 21-25
- **Risk**: LOW
- **Acceptance**: python-docx, python-pptx, openpyxl installed in MCP container

---

## TASK-012 (RESOLVED)
- **Tier**: 2 (high)
- **File(s)**: Dockerfile.mcp
- **Category**: DEPENDENCY
- **Roadmap ID**: P5-ROAD-061
- **Finding**: Music MCP audiocraft - verification agent reported NOT_IMPLEMENTED but audiocraft IS in Dockerfile
- **Action**: Verify audiocraft in Dockerfile.mcp
- **Status**: RESOLVED - audiocraft present in Dockerfile.mcp lines 28-33 with graceful fallback
- **Risk**: LOW
- **Acceptance**: audiocraft installed in MCP container (with fallback for platform issues)

---

## TASK-013 (RESOLVED)
- **Tier**: 2 (high)
- **File(s)**: Dockerfile.mcp + docs/
- **Category**: DEPENDENCY
- **Roadmap ID**: P5-ROAD-062
- **Finding**: TTS MCP fish-speech - verification agent reported NOT_IMPLEMENTED but fish-speech needs host-side setup
- **Action**: Document fish-speech as host-side requirement (like ComfyUI)
- **Status**: DONE - docs/FISH_SPEECH_SETUP.md created with full installation and setup guide
- **Risk**: LOW
- **Acceptance**: docs/FISH_SPEECH_SETUP.md exists

---

## TASK-014 (RESOLVED)
- **Tier**: 2 (high)
- **File(s)**: Dockerfile.mcp
- **Category**: DEPENDENCY
- **Roadmap ID**: P5-ROAD-063
- **Finding**: Whisper MCP - verification agent reported NOT_IMPLEMENTED but faster-whisper IS in Dockerfile
- **Action**: Verify faster-whisper in Dockerfile.mcp
- **Status**: RESOLVED - faster-whisper present in Dockerfile.mcp lines 28-29
- **Risk**: LOW
- **Acceptance**: faster-whisper installed in MCP container

---

## TASK-015 (RESOLVED)
- **Tier**: 1 (critical)
- **File(s)**: docs/
- **Category**: DOCUMENTATION
- **Roadmap ID**: P5-ROAD-064
- **Finding**: ComfyUI integration documentation - needs host-side setup documentation
- **Action**: Ensure docs/COMFYUI_SETUP.md is complete and accurate
- **Status**: DONE - docs/COMFYUI_SETUP.md verified and updated with video workflow details
- **Risk**: MEDIUM
- **Acceptance**: docs/COMFYUI_SETUP.md current and accurate

---

## TASK-016 (RESOLVED)
- **Tier**: 1 (critical)
- **File(s)**: docs/
- **Category**: DOCUMENTATION
- **Roadmap ID**: P5-ROAD-065
- **Finding**: Video MCP requires ComfyUI with Wan2.2 video models
- **Action**: Document video model requirements in docs/COMFYUI_SETUP.md
- **Status**: DONE - docs/COMFYUI_SETUP.md updated with Wan2.2 video generation workflow
- **Risk**: MEDIUM
- **Acceptance**: Video generation setup documented

---

## Dependency Verification Note

The Phase 3 verification agent reported several MCP dependencies as STUB/NOT_IMPLEMENTED, but inspection of Dockerfile.mcp reveals:

- **Document MCP (P5-ROAD-060)**: RESOLVED - python-docx, python-pptx, openpyxl present (lines 21-25)
- **Music MCP (P5-ROAD-061)**: RESOLVED - audiocraft present with fallback (lines 28-33)
- **TTS MCP (P5-ROAD-062)**: PARTIAL - faster-whisper present, but fish-speech requires external setup
- **Whisper MCP (P5-ROAD-063)**: RESOLVED - faster-whisper present (lines 28-29)
- **ComfyUI (P5-ROAD-064)**: DOCUMENTATION NEEDED - runs on host, not in Docker
- **Video MCP (P5-ROAD-065)**: DOCUMENTATION NEEDED - requires ComfyUI + video models

---

*Generated from P5_ROADMAP.md open items*