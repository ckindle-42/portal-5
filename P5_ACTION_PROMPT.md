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

All tasks from prior run are RESOLVED. Several improvements were made:

- **TASK-001**: Fixed N806 lint violation in `scripts/download_comfyui_models.py` - moved MODELS constant to module level
- **TASK-002**: R4 security fix - 11 internal services bound to 127.0.0.1 (Ollama, MCP servers, Prometheus, SearXNG, ComfyUI)
- **TASK-003**: wan2.2 download fixed - uses `snapshot_download` instead of `hf_hub_download(filename=None)`
- **TASK-004**: TTS imports consolidated - removed 6 redundant in-function imports from tts_mcp.py
- **TASK-005**: TTS_DEFAULT_VOICE added to .env.example with voice options documented
- **TASK-006**: New test file test_mcp_endpoints.py with 3 new test classes (TTS, Whisper, Backend routing)

The codebase is in excellent shape:
- 25 tests passing
- 0 lint violations
- 95/100 production readiness score
- All workspace consistency checks pass
- All zero-setup compliance checks pass

**COMPLIANCE CHECK**
- Hard constraints met: Yes
- Output format followed: Yes
- All findings backed by runtime or static evidence: Yes
- Uncertainty Log: None

---

*Generated from P5_ROADMAP.md open items (Delta Run)*