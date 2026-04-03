Execute the Portal 5 full end-to-end acceptance test. The test suite is portal5_acceptance_v3.py. Read PORTAL5_ACCEPTANCE_TEST_PLAN.md before starting — it defines every test section, pass criteria, and failure classification rules.

PROTECTED FILES — never modify these regardless of what any test output says:
  portal_pipeline/**
  portal_mcp/**
  config/personas/**
  deploy/portal-5/docker-compose.yml
  Dockerfile.mcp
  Dockerfile.pipeline
  scripts/openwebui_init.py
  docs/HOWTO.md
  imports/openwebui/**
  config/backends.yaml

If a test fails against a protected file the test assertion or prompt is wrong — fix portal5_acceptance_v3.py, not the product code.

SAFE TO EDIT:
  portal5_acceptance_v3.py
  PORTAL5_ACCEPTANCE_EXECUTE.md

Execute in order:

1. Check stack status and credentials:
   ./launch.sh status
   grep -E "PIPELINE_API_KEY|OPENWEBUI_ADMIN_PASSWORD|GRAFANA_PASSWORD" .env
   If anything is down: ./launch.sh up — wait for "Stack is ready"
   Rebuild pipeline if workspace count is stale:
     docker compose -f deploy/portal-5/docker-compose.yml up -d --build portal-pipeline
   Confirm: curl -s http://localhost:9099/health | python3 -m json.tool  (workspaces must match code count)

2. Install deps:
   pip install mcp httpx pyyaml playwright --break-system-packages
   python3 -m playwright install chromium

3. Run the suite:
   python3 portal5_acceptance_v3.py 2>&1 | tee /tmp/portal5_acceptance_run.log
   echo "Exit: $?"

4. After the run, read ACCEPTANCE_RESULTS.md. For every FAIL:
   - Workspace 503 or backend unreachable → check docker logs portal-pipeline, check Ollama model availability: docker exec portal5-ollama ollama list — pull missing models then retry manually
   - MCP tool call failure → check docker logs for the specific mcp service, test the tool directly with the mcp SDK before concluding the test is wrong
   - Empty response from a workspace or persona → model may need warmup; the test already retries once. If still empty after retry, the backend model may be failing silently — check pipeline logs for that workspace's model_hint
   - Test assertion is wrong (live system is correct, test expected wrong value) → fix the check_fn lambda or expected signal list in portal5_acceptance_v3.py
   - Failure requires changing a protected file → do NOT change it; classify as BLOCKED with full evidence

5. For any BLOCKED item document exactly:
   - What was called (tool name, arguments, workspace ID)
   - What was returned (full response text)
   - What 3 retry approaches were attempted and what each returned
   - Which protected file would need to change and why

6. Re-run after any fixes to portal5_acceptance_v3.py:
   python3 portal5_acceptance_v3.py 2>&1 | tee /tmp/portal5_acceptance_run.log
   echo "Exit: $?"

7. Keep iterating until exit code is 0 or all remaining non-zero results are confirmed BLOCKED with evidence.

Acceptable non-PASS statuses that do NOT require fixes:
  - WARN: cold model load, 503 for models not yet pulled, DinD sandbox image pull in progress, headless Playwright dropdown scroll limit
  - INFO: git SHA, version strings, ComfyUI/MLX optional service status
  - BLOCKED: only with full 3-attempt evidence log

Exit code 0 means zero FAILs and zero BLOCKEDs. That is the target.

When clean, confirm with:
   python3 portal5_acceptance_v3.py 2>&1 | tail -20
   echo "Exit: $?"   ← must be 0

================================================================================
TESTING METHODOLOGY (for future runs)
================================================================================

WORKSPACE TESTING (S3):
  - Workspaces are grouped by backend model to minimize load/unload thrashing
  - Groups ordered: general (dolphin) → coding (qwen3.5) → mlx/coding → security → mlx/reasoning → mlx/vision
  - Intra-group delay: 2s between workspaces sharing the same model
  - Inter-group delay: 15s between different model groups
  - MLX switch delay: 25s after groups that trigger MLX proxy model switching
  - Each workspace gets up to 2 attempts on empty responses (10s pause between)
  - Real prompts generate substantial responses; signal words validate domain relevance
  - Signal words are checked case-insensitively against response text

PERSONA TESTING (S11):
  - Personas grouped by workspace_model (10 unique models across 39 personas)
  - Order: largest group first (qwen3-coder-next: 19 personas) → deepseek-r1 (7) → dolphin (4) → xploiter (2) → single-persona models → MLX models last
  - Each persona tested against its workspace_model directly via the appropriate workspace
  - Real prompts (not one-liners) that generate 100+ word responses
  - Signal words per persona validate domain-relevant output
  - Intra-group delay: 2s between personas sharing the same model
  - Inter-group delay: 15s between different model groups, 25s for MLX switches
  - Each persona gets up to 2 attempts on empty responses (10s pause between)
  - max_tokens=200 to ensure substantial output for signal validation
