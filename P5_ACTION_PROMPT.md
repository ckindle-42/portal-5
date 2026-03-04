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

## Tasks

### TASK-001
Tier:         2 (fix soon)
File(s):      tests/unit/test_mcp_endpoints.py
Category:     Tests
Finding:      FINDING-001 - 9 MCP tests ERROR instead of SKIP
Action:       Add skip markers for MCP-dependent tests. Add at top of test_mcp_endpoints.py:

```python
import importlib.util
MCP_AVAILABLE = importlib.util.find_spec("mcp") is not None
```

Then add to each test class that imports from portal_mcp:
```python
@pytest.mark.skipif(not MCP_AVAILABLE, reason="MCP SDK not installed")
```

Risk:         Low
Acceptance:   python3 -m pytest tests/unit/test_mcp_endpoints.py -v shows SKIPPED (not ERROR) for MCP tests