# P5_ACTION_PROMPT.md — Action Items (v4 agent, R10)

**Date:** March 4, 2026
**Source:** code-quality-agent-v4 delta run (R10)
**Status:** 16/16 checks pass — no blocking action items

**Session bootstrap:**
```bash
cd /Users/chris/projects/portal-5
git checkout main && git pull
.venv/bin/python3 -m pip install -e ".[dev,mcp,channels]" --quiet
.venv/bin/python3 -m pytest tests/ -q --tb=no
# Expected: 72 passed
```

---

## Open Tasks

### TASK-001 — Add skipif markers to MCP endpoint tests (P5-ROAD-107)

**Priority:** P2-HIGH
**What:** 9 tests in `tests/unit/test_mcp_endpoints.py` raise ERROR (not SKIP) when the `mcp` package is not installed in the active Python environment. They should show as SKIPPED.

**Fix:** Add `pytest.importorskip("mcp")` or `@pytest.mark.skipif(...)` guards at the top of `TestTTSOpenAIEndpoints` and `TestWhisperOpenAIEndpoints` fixture setup so tests skip gracefully when `mcp` is absent.

**Evidence:**
```
$ python3 -m pytest tests/unit/test_mcp_endpoints.py -q --tb=line
ERROR tests/unit/test_mcp_endpoints.py::TestTTSOpenAIEndpoints::test_health_endpoint
...ModuleNotFoundError: No module named 'mcp'
9 errors in 0.XX s
```

**Verify:**
```bash
python3 -m pytest tests/unit/test_mcp_endpoints.py -q --tb=no
# Expected: 9 skipped (or passed if mcp installed), 0 errors
```

---

## No Other Tasks

All other previously identified issues are resolved:

| Previously open | Resolved in |
|----------------|-------------|
| Sandbox --security-opt/--cap-drop | R9 |
| Channel dispatcher (bots used httpx directly) | R9 |
| Workspace toolIds auto-activation | R8 |
| TTS HTTP 500→503 | R8 |
| TOOLS_MANIFEST bidirectional alignment | R8 |
| Test mock patches targeting wrong module | R10 |
| README production-grade | R10 |
| Code quality agent v4 checks | R10 |
| Documentation agent v4 checks | R10 |

**COMPLIANCE CHECK**
- Hard constraints met: Yes
- All findings backed by evidence: Yes
- Uncertainty Log: None
