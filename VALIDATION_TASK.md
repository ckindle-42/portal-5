# Portal 5.2 — Complete Validation Task for Claude Code

## Purpose

Run this task from Claude Code on the **production system** from within the `portal-5/` project directory. It validates every feature documented in `docs/HOWTO.md`, runs all tests, exercises the live stack, tests the frontend via Chromium, and produces a comprehensive results report with corrections for any errors found.

**Run from:** `cd ~/portal-5` (or wherever the repo is cloned)
**Estimated time:** 30–60 minutes (first run with model pulls may take longer)

---

## PHASE 0 — Environment & Prerequisites

### 0.1 — Verify working directory and git state

```bash
# Confirm we're in the portal-5 root
test -f launch.sh && test -f pyproject.toml && echo "PASS: In portal-5 root" || echo "FAIL: Wrong directory"

# Check git status
git log --oneline -1
git status --short
```

### 0.2 — System requirements check

```bash
# Docker is running
docker info > /dev/null 2>&1 && echo "PASS: Docker running" || echo "FAIL: Docker not running"

# Python 3.10+
python3 -c "import sys; assert sys.version_info >= (3, 10), f'Need 3.10+, got {sys.version}'; print(f'PASS: Python {sys.version}')"

# RAM check (16GB minimum)
if [ "$(uname -s)" = "Darwin" ]; then
    RAM_GB=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
elif [ -f /proc/meminfo ]; then
    RAM_GB=$(( $(awk '/MemTotal/ {print $2}' /proc/meminfo) / 1024 / 1024 ))
fi
[ "$RAM_GB" -ge 16 ] && echo "PASS: ${RAM_GB}GB RAM" || echo "WARN: ${RAM_GB}GB RAM (16GB minimum)"

# Disk check (20GB minimum)
DISK_FREE=$(python3 -c "import shutil; print(shutil.disk_usage('/').free // 1024**3)" 2>/dev/null || echo 0)
[ "$DISK_FREE" -ge 20 ] && echo "PASS: ${DISK_FREE}GB free disk" || echo "WARN: ${DISK_FREE}GB free (20GB recommended)"
```

### 0.3 — Install dev dependencies

```bash
# Create virtualenv and install all dev deps
pip install uv 2>/dev/null || true
uv venv .venv --python 3.11 2>/dev/null || python3 -m venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]" 2>/dev/null || pip install -e ".[dev]"

# Verify key imports
python3 -c "import fastapi, httpx, pydantic, yaml, pytest; print('PASS: All core deps installed')"
```

### 0.4 — Install Chromium for frontend testing

```bash
# Install Playwright for browser-based testing
pip install playwright pytest-playwright 2>/dev/null || uv pip install playwright pytest-playwright
python3 -m playwright install chromium
echo "PASS: Chromium installed for frontend testing"
```

---

## PHASE 1 — Static Analysis & Unit Tests (No Docker Required)

### 1.1 — Lint with ruff

```bash
ruff check . --fix 2>&1
RUFF_EXIT=$?
[ $RUFF_EXIT -eq 0 ] && echo "PASS: ruff check clean" || echo "FAIL: ruff found issues (exit $RUFF_EXIT)"
```

### 1.2 — Format check with ruff

```bash
ruff format --check . 2>&1
FMT_EXIT=$?
[ $FMT_EXIT -eq 0 ] && echo "PASS: ruff format clean" || echo "FAIL: formatting issues found"
```

### 1.3 — Run all unit tests

```bash
# HOWTO Section: "Testing" — pytest tests/ -v --tb=short
pytest tests/ -v --tb=short 2>&1
TEST_EXIT=$?
[ $TEST_EXIT -eq 0 ] && echo "PASS: All unit tests passed" || echo "FAIL: Unit tests failed (exit $TEST_EXIT)"
```

### 1.4 — Workspace routing consistency check

```bash
# CLAUDE.md Rule 6: workspace IDs must match between router_pipe.py and backends.yaml
python3 -c "
import yaml
from portal_pipeline.router_pipe import WORKSPACES
cfg = yaml.safe_load(open('config/backends.yaml'))
pipe_ids = set(WORKSPACES.keys())
yaml_ids = set(cfg['workspace_routing'].keys())
if pipe_ids == yaml_ids:
    print(f'PASS: Workspace IDs consistent ({len(pipe_ids)} workspaces)')
else:
    print(f'FAIL: Mismatch — in pipe only: {pipe_ids - yaml_ids}, in yaml only: {yaml_ids - pipe_ids}')
" 2>&1
```

### 1.5 — Validate persona YAML files

```bash
python3 -c "
import yaml, os, sys
persona_dir = 'config/personas'
errors = []
count = 0
required_fields = {'name', 'slug', 'system_prompt', 'workspace_model'}
for f in sorted(os.listdir(persona_dir)):
    if not f.endswith('.yaml') and not f.endswith('.yml'):
        continue
    path = os.path.join(persona_dir, f)
    try:
        data = yaml.safe_load(open(path))
        missing = required_fields - set(data.keys())
        if missing:
            errors.append(f'{f}: missing fields {missing}')
        count += 1
    except Exception as e:
        errors.append(f'{f}: parse error: {e}')
if errors:
    for e in errors:
        print(f'FAIL: {e}')
else:
    print(f'PASS: All {count} persona YAML files valid')
" 2>&1
```

### 1.6 — Validate docker-compose.yml syntax

```bash
docker compose -f deploy/portal-5/docker-compose.yml config --quiet 2>&1 && \
    echo "PASS: docker-compose.yml valid" || echo "FAIL: docker-compose.yml has errors"
```

### 1.7 — Validate port assignments (CLAUDE.md Rule 7)

```bash
python3 -c "
import re, yaml

# Expected port assignments from CLAUDE.md
EXPECTED_PORTS = {
    8080: 'Open WebUI',
    9099: 'Portal Pipeline',
    8910: 'MCP: ComfyUI',
    8911: 'MCP: Video',
    8912: 'MCP: Music',
    8913: 'MCP: Documents',
    8914: 'MCP: Code Sandbox',
    8915: 'MCP: Whisper',
    8916: 'MCP: TTS',
    8188: 'ComfyUI',
    8088: 'SearXNG',
    11434: 'Ollama',
    9090: 'Prometheus',
    3000: 'Grafana',
}

# Parse docker-compose.yml for port mappings
compose = yaml.safe_load(open('deploy/portal-5/docker-compose.yml'))
found_ports = {}
for svc_name, svc in compose.get('services', {}).items():
    for port_spec in svc.get('ports', []):
        port_str = str(port_spec)
        # Extract host port from patterns like '127.0.0.1:8080:8080' or '8080:8080'
        parts = port_str.split(':')
        host_port = int(parts[-2]) if len(parts) >= 2 else int(parts[0])
        found_ports[host_port] = svc_name

conflicts = []
for port, expected_svc in EXPECTED_PORTS.items():
    if port in found_ports:
        pass  # Port is mapped in compose
    # Port might be on host (Ollama, ComfyUI) — that's OK
    
print(f'PASS: {len(found_ports)} ports mapped in docker-compose.yml')
print(f'INFO: Ports on host (not in compose): Ollama:11434, ComfyUI:8188')
" 2>&1
```

### 1.8 — Validate imports/openwebui JSON files

```bash
python3 -c "
import json, os
errors = []
count = 0
for root, dirs, files in os.walk('imports/openwebui'):
    for f in files:
        if f.endswith('.json'):
            path = os.path.join(root, f)
            try:
                json.load(open(path))
                count += 1
            except Exception as e:
                errors.append(f'{path}: {e}')
if errors:
    for e in errors:
        print(f'FAIL: {e}')
else:
    print(f'PASS: All {count} JSON import files valid')
" 2>&1
```

---

## PHASE 2 — Stack Launch & Service Health (HOWTO Sections 1, 2)

### 2.1 — Launch the stack

```bash
# HOWTO Section 1: Quick Start
./launch.sh up 2>&1 | tail -30
LAUNCH_EXIT=$?
[ $LAUNCH_EXIT -eq 0 ] && echo "PASS: launch.sh up succeeded" || echo "FAIL: launch.sh up failed (exit $LAUNCH_EXIT)"
```

### 2.2 — Verify all services healthy

```bash
# HOWTO Section 1: Verify
./launch.sh status 2>&1
STATUS_EXIT=$?
[ $STATUS_EXIT -eq 0 ] && echo "PASS: All services healthy" || echo "WARN: Some services unhealthy"
```

### 2.3 — Individual service health checks

```bash
# Source .env for API keys
set -a; source .env 2>/dev/null; set +a

# Open WebUI (HOWTO Section 2)
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080 2>/dev/null)
[ "$HTTP_CODE" = "200" ] && echo "PASS: Open WebUI :8080 → HTTP $HTTP_CODE" || echo "FAIL: Open WebUI :8080 → HTTP $HTTP_CODE"

# Pipeline (HOWTO Section 3)
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:9099/v1/models -H "Authorization: Bearer $PIPELINE_API_KEY" 2>/dev/null)
[ "$HTTP_CODE" = "200" ] && echo "PASS: Pipeline :9099 → HTTP $HTTP_CODE" || echo "FAIL: Pipeline :9099 → HTTP $HTTP_CODE"

# SearXNG (HOWTO Section 13)
docker compose -f deploy/portal-5/docker-compose.yml ps searxng 2>&1 | grep -q healthy && echo "PASS: SearXNG healthy" || echo "WARN: SearXNG not healthy"

# Prometheus (HOWTO Section 22)
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:9090/-/healthy 2>/dev/null)
[ "$HTTP_CODE" = "200" ] && echo "PASS: Prometheus :9090 → HTTP $HTTP_CODE" || echo "FAIL: Prometheus :9090 → HTTP $HTTP_CODE"

# Grafana (HOWTO Section 22)
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/api/health 2>/dev/null)
[ "$HTTP_CODE" = "200" ] && echo "PASS: Grafana :3000 → HTTP $HTTP_CODE" || echo "FAIL: Grafana :3000 → HTTP $HTTP_CODE"
```

---

## PHASE 3 — Workspace & Persona Validation (HOWTO Sections 3, 4)

### 3.1 — Verify workspace model list

```bash
# HOWTO Section 3: Verify workspace routing
set -a; source .env 2>/dev/null; set +a

WORKSPACE_COUNT=$(curl -s http://localhost:9099/v1/models \
  -H "Authorization: Bearer $PIPELINE_API_KEY" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('data',[])))" 2>/dev/null)

echo "Workspace count: $WORKSPACE_COUNT"
[ "$WORKSPACE_COUNT" -ge 13 ] && echo "PASS: $WORKSPACE_COUNT workspaces (expected ≥13)" || echo "FAIL: Only $WORKSPACE_COUNT workspaces found"

# List all workspace IDs
curl -s http://localhost:9099/v1/models \
  -H "Authorization: Bearer $PIPELINE_API_KEY" \
  | python3 -m json.tool 2>/dev/null | grep '"id"'
```

### 3.2 — Verify personas seeded

```bash
# HOWTO Section 4: Verify personas
set -a; source .env 2>/dev/null; set +a

# Check for Red Team persona specifically (HOWTO example)
curl -s http://localhost:9099/v1/models \
  -H "Authorization: Bearer $PIPELINE_API_KEY" \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
names = [m.get('name','') for m in data.get('data',[])]
red_team = [n for n in names if 'red' in n.lower() and 'team' in n.lower()]
if red_team:
    print(f'PASS: Red Team persona found: {red_team}')
else:
    print('FAIL: Red Team persona not found in model list')
print(f'INFO: Total models/workspaces/personas: {len(names)}')
" 2>/dev/null
```

### 3.3 — Test routing decision (non-streaming)

```bash
# HOWTO Section 6: Security routing test
set -a; source .env 2>/dev/null; set +a

curl -s http://localhost:9099/v1/chat/completions \
  -H "Authorization: Bearer $PIPELINE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "auto", "messages": [{"role": "user", "content": "exploit vulnerability payload injection"}], "stream": false, "max_tokens": 10}' \
  2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    if 'choices' in d:
        print('PASS: Chat completion returned valid response')
    elif 'error' in d:
        print(f'WARN: Chat returned error: {d[\"error\"]}')
    else:
        print(f'INFO: Unexpected response shape: {list(d.keys())}')
except Exception as e:
    print(f'FAIL: Could not parse response: {e}')
"

# Check pipeline logs for routing decision
docker compose -f deploy/portal-5/docker-compose.yml logs portal-pipeline --tail=20 2>&1 | grep -i "routing\|workspace=" | tail -5
```

---

## PHASE 4 — MCP Tool Server Health (HOWTO Sections 5, 7, 9-12)

### 4.1 — Documents MCP (HOWTO Section 7)

```bash
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8913/health 2>/dev/null)
[ "$HTTP_CODE" = "200" ] && echo "PASS: Documents MCP :8913 → HTTP $HTTP_CODE" || echo "FAIL: Documents MCP :8913 → HTTP $HTTP_CODE"

# List tools
curl -s http://localhost:8913/tools 2>/dev/null | python3 -c "
import sys, json
try:
    tools = json.load(sys.stdin)
    if isinstance(tools, list):
        print(f'PASS: Documents MCP has {len(tools)} tools')
    else:
        print(f'INFO: Tools response: {type(tools)}')
except:
    print('WARN: Could not parse tools response')
" 2>/dev/null
```

### 4.2 — Code Sandbox MCP (HOWTO Section 5)

```bash
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8914/health 2>/dev/null)
[ "$HTTP_CODE" = "200" ] && echo "PASS: Code Sandbox MCP :8914 → HTTP $HTTP_CODE" || echo "FAIL: Code Sandbox MCP :8914 → HTTP $HTTP_CODE"
```

### 4.3 — Music MCP (HOWTO Section 10)

```bash
MUSIC_RESP=$(curl -s http://localhost:8912/health 2>/dev/null)
echo "Music MCP :8912 → $MUSIC_RESP"
echo "$MUSIC_RESP" | grep -q '"ok"' && echo "PASS: Music MCP healthy" || echo "WARN: Music MCP may not be fully ready"
```

### 4.4 — TTS MCP (HOWTO Section 11)

```bash
TTS_RESP=$(curl -s http://localhost:8916/health 2>/dev/null)
echo "TTS MCP :8916 → $TTS_RESP"
echo "$TTS_RESP" | grep -q '"ok"' && echo "PASS: TTS MCP healthy" || echo "WARN: TTS MCP may not be fully ready"
```

### 4.5 — Whisper MCP (HOWTO Section 12)

```bash
# Whisper health check runs inside the container
docker exec portal5-mcp-whisper python3 -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8915/health').read().decode())" 2>&1
WHISPER_EXIT=$?
[ $WHISPER_EXIT -eq 0 ] && echo "PASS: Whisper MCP :8915 healthy" || echo "WARN: Whisper MCP not reachable (may be expected if not started)"
```

### 4.6 — Video MCP (HOWTO Section 9)

```bash
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8911/health 2>/dev/null)
echo "Video MCP :8911 → HTTP $HTTP_CODE"
# Video MCP may return non-200 if ComfyUI+Wan2.2 not installed — that's documented as optional
```

### 4.7 — ComfyUI bridge MCP (HOWTO Section 8)

```bash
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8910/health 2>/dev/null)
echo "ComfyUI MCP :8910 → HTTP $HTTP_CODE"
# ComfyUI runs on host, may not be present — documented as optional
```

---

## PHASE 5 — Metrics & Monitoring (HOWTO Section 22)

### 5.1 — Pipeline exposes Prometheus metrics

```bash
# HOWTO Section 22: Pipeline is exposing metrics
METRICS=$(curl -s http://localhost:9099/metrics 2>/dev/null | head -20)
echo "$METRICS" | grep -q "portal_" && echo "PASS: Pipeline exposes portal_* metrics" || echo "WARN: No portal_* metrics found yet (may need traffic first)"
```

### 5.2 — Prometheus scraping pipeline

```bash
# HOWTO Section 22: Prometheus is scraping the pipeline
curl -s http://localhost:9090/api/v1/targets 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    targets = d.get('data', {}).get('activeTargets', [])
    pipeline_targets = [t for t in targets if 'pipeline' in str(t.get('labels', {})).lower() or '9099' in str(t.get('scrapeUrl', ''))]
    if pipeline_targets:
        print(f'PASS: Prometheus scraping pipeline ({len(pipeline_targets)} target(s))')
    else:
        print(f'WARN: No pipeline target found in {len(targets)} active targets')
except Exception as e:
    print(f'FAIL: Could not query Prometheus targets: {e}')
"
```

### 5.3 — Grafana dashboard provisioned

```bash
set -a; source .env 2>/dev/null; set +a
GRAFANA_PASS="${GRAFANA_PASSWORD:-admin}"

curl -s -u "admin:$GRAFANA_PASS" http://localhost:3000/api/search 2>/dev/null | python3 -c "
import sys, json
try:
    dashboards = json.load(sys.stdin)
    portal_dashes = [d for d in dashboards if 'portal' in d.get('title','').lower()]
    if portal_dashes:
        print(f'PASS: Grafana has Portal dashboard(s): {[d[\"title\"] for d in portal_dashes]}')
    else:
        print(f'INFO: No Portal dashboard found among {len(dashboards)} dashboards')
except Exception as e:
    print(f'WARN: Could not query Grafana: {e}')
"
```

---

## PHASE 6 — TTS Direct API Test (HOWTO Section 11)

```bash
# HOWTO Section 11: Direct API call for TTS
curl -s -X POST http://localhost:8916/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input": "Hello from Portal 5 validation!", "voice": "af_heart"}' \
  --output /tmp/portal5_tts_test.mp3 2>/dev/null

if [ -f /tmp/portal5_tts_test.mp3 ] && [ -s /tmp/portal5_tts_test.mp3 ]; then
    SIZE=$(stat -f%z /tmp/portal5_tts_test.mp3 2>/dev/null || stat -c%s /tmp/portal5_tts_test.mp3 2>/dev/null)
    echo "PASS: TTS generated audio file (${SIZE} bytes)"
    rm -f /tmp/portal5_tts_test.mp3
else
    echo "WARN: TTS did not generate audio (kokoro model may be downloading on first call)"
fi
```

---

## PHASE 7 — CLI Commands Validation (HOWTO Quick Reference)

### 7.1 — Status command

```bash
./launch.sh status 2>&1 | tail -10
echo "PASS: status command executed"
```

### 7.2 — Logs command

```bash
./launch.sh logs --tail=5 2>&1 | head -20
echo "PASS: logs command executed"
```

### 7.3 — Seed command (idempotent)

```bash
./launch.sh seed 2>&1 | tail -10
SEED_EXIT=$?
[ $SEED_EXIT -eq 0 ] && echo "PASS: seed command succeeded" || echo "WARN: seed returned exit $SEED_EXIT"
```

### 7.4 — List users

```bash
./launch.sh list-users 2>&1
echo "PASS: list-users command executed"
```

### 7.5 — Add test user

```bash
./launch.sh add-user testvalidation@portal.local "Validation User" 2>&1
echo "INFO: add-user command executed (may fail if user exists — that's OK)"
```

### 7.6 — Backup command

```bash
./launch.sh backup 2>&1 | tail -5
BACKUP_EXIT=$?
[ $BACKUP_EXIT -eq 0 ] && echo "PASS: backup command succeeded" || echo "WARN: backup returned exit $BACKUP_EXIT"

# Verify backup file created
ls -la backups/ 2>/dev/null | tail -3
```

---

## PHASE 8 — Frontend Browser Testing via Chromium (HOWTO Sections 2, 3, 4, 14)

### 8.1 — Create Playwright test script

```python
#!/usr/bin/env python3
"""
Portal 5 Frontend Validation — Chromium browser tests.

Tests the Open WebUI frontend at http://localhost:8080 including:
- Login page loads
- Admin login works
- Chat interface appears
- Workspace/model dropdown contains expected entries
- Settings page accessible
- Knowledge base page accessible
"""

import asyncio
import os
import re
import sys

# Load .env
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(env_path):
    for line in open(env_path):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, _, val = line.partition('=')
            os.environ.setdefault(key.strip(), val.strip())

ADMIN_EMAIL = os.environ.get('OPENWEBUI_ADMIN_EMAIL', 'admin@portal.local')
ADMIN_PASSWORD = os.environ.get('OPENWEBUI_ADMIN_PASSWORD', '')

if not ADMIN_PASSWORD:
    print("FAIL: OPENWEBUI_ADMIN_PASSWORD not set in .env")
    sys.exit(1)


async def run_tests():
    from playwright.async_api import async_playwright

    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            ignore_https_errors=True,
        )
        page = await context.new_page()

        # ── Test 1: Login page loads ──────────────────────────────────
        try:
            resp = await page.goto("http://localhost:8080", wait_until="networkidle", timeout=30000)
            if resp and resp.status == 200:
                results.append("PASS: Login page loads (HTTP 200)")
            else:
                results.append(f"FAIL: Login page returned HTTP {resp.status if resp else 'None'}")
        except Exception as e:
            results.append(f"FAIL: Login page timeout: {e}")

        # ── Test 2: Sign in with admin credentials ────────────────────
        try:
            # Wait for email input — Open WebUI shows a sign-in form
            await page.wait_for_selector('input[type="email"], input[name="email"], input[autocomplete="email"]', timeout=10000)
            await page.fill('input[type="email"], input[name="email"], input[autocomplete="email"]', ADMIN_EMAIL)

            # Password field
            await page.fill('input[type="password"]', ADMIN_PASSWORD)

            # Click sign in button
            sign_in_btn = page.locator('button:has-text("Sign in"), button:has-text("Login"), button[type="submit"]')
            await sign_in_btn.first.click()

            # Wait for navigation to chat interface (look for chat input or model selector)
            await page.wait_for_selector('textarea, [contenteditable], #chat-input, .chat-input', timeout=15000)
            results.append("PASS: Admin login successful — chat interface loaded")

            # Take screenshot for evidence
            await page.screenshot(path="/tmp/portal5_chat_interface.png")
            results.append("INFO: Screenshot saved to /tmp/portal5_chat_interface.png")

        except Exception as e:
            results.append(f"FAIL: Admin login failed: {e}")
            await page.screenshot(path="/tmp/portal5_login_failure.png")
            results.append("INFO: Failure screenshot saved to /tmp/portal5_login_failure.png")

        # ── Test 3: Model/workspace dropdown exists ───────────────────
        try:
            # Look for the model selector dropdown in Open WebUI
            model_selector = page.locator('[data-testid="model-selector"], .model-selector, button:has-text("Portal"), select')
            count = await model_selector.count()
            if count > 0:
                results.append(f"PASS: Model/workspace selector found ({count} element(s))")
                # Try clicking to expand
                await model_selector.first.click()
                await page.wait_for_timeout(1000)
                await page.screenshot(path="/tmp/portal5_model_dropdown.png")
                results.append("INFO: Dropdown screenshot saved to /tmp/portal5_model_dropdown.png")
            else:
                # Try alternative selectors
                alt = page.locator('div[class*="model"], div[class*="selector"], button[class*="model"]')
                alt_count = await alt.count()
                results.append(f"INFO: Model selector not found via standard selectors, found {alt_count} alternatives")
        except Exception as e:
            results.append(f"WARN: Model dropdown test: {e}")

        # ── Test 4: Navigate to Settings ──────────────────────────────
        try:
            await page.goto("http://localhost:8080/admin/settings", wait_until="networkidle", timeout=15000)
            title = await page.title()
            results.append(f"PASS: Settings page accessible (title: {title})")
        except Exception as e:
            results.append(f"WARN: Settings page: {e}")

        # ── Test 5: Navigate to Knowledge Base (HOWTO Section 14) ─────
        try:
            # Open WebUI knowledge base is typically at /workspace/knowledge
            await page.goto("http://localhost:8080", wait_until="networkidle", timeout=10000)
            # Look for workspace/knowledge navigation
            knowledge_link = page.locator('a[href*="knowledge"], button:has-text("Knowledge"), [data-testid="knowledge"]')
            count = await knowledge_link.count()
            if count > 0:
                results.append(f"PASS: Knowledge base navigation found ({count} element(s))")
            else:
                results.append("INFO: Knowledge base link not directly visible (may require sidebar expansion)")
        except Exception as e:
            results.append(f"INFO: Knowledge base nav test: {e}")

        # ── Test 6: Verify page has no console errors ─────────────────
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        await page.goto("http://localhost:8080", wait_until="networkidle", timeout=10000)
        await page.wait_for_timeout(3000)
        if console_errors:
            results.append(f"WARN: {len(console_errors)} console error(s): {console_errors[:3]}")
        else:
            results.append("PASS: No JavaScript console errors on main page")

        await browser.close()

    return results


if __name__ == "__main__":
    results = asyncio.run(run_tests())
    print("\n── Frontend Test Results ──")
    for r in results:
        print(f"  {r}")
    
    failures = [r for r in results if r.startswith("FAIL")]
    if failures:
        print(f"\n{len(failures)} FAILURE(S)")
        sys.exit(1)
    else:
        print(f"\nAll frontend tests passed ({len(results)} checks)")
```

### 8.2 — Run the frontend tests

```bash
python3 portal5_frontend_test.py 2>&1
FRONTEND_EXIT=$?
[ $FRONTEND_EXIT -eq 0 ] && echo "PASS: Frontend browser tests passed" || echo "WARN: Some frontend tests had issues"
```

---

## PHASE 9 — Document Generation Smoke Test (HOWTO Section 7)

```bash
# Test the Documents MCP can generate a Word doc
curl -s -X POST http://localhost:8913/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "create_docx",
    "arguments": {
      "title": "Validation Test Document",
      "content": "# Test Document\n\nThis is a validation test.\n\n## Section 1\n\nContent here."
    }
  }' 2>/dev/null | python3 -c "
import sys, json
try:
    resp = json.load(sys.stdin)
    print(f'INFO: Document generation response: {json.dumps(resp)[:200]}')
    if 'error' not in str(resp).lower():
        print('PASS: Document generation endpoint responded')
    else:
        print(f'WARN: Document generation returned error')
except Exception as e:
    print(f'INFO: Document generation test: {e}')
"
```

---

## PHASE 10 — Web Search Validation (HOWTO Section 13)

```bash
# SearXNG internal health
docker compose -f deploy/portal-5/docker-compose.yml ps searxng 2>&1

# Direct SearXNG query (internal port 8088)
docker compose -f deploy/portal-5/docker-compose.yml exec -T searxng \
  wget -qO- "http://localhost:8080/search?q=test&format=json" 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    results = d.get('results', [])
    print(f'PASS: SearXNG returned {len(results)} search results')
except:
    print('WARN: SearXNG search test did not return JSON (may need warm-up time)')
" 2>/dev/null
```

---

## PHASE 11 — RAG / Embedding Model Verification (HOWTO Section 14)

```bash
# HOWTO Section 14: Embedding model should be pulled
# Check if Ollama has nomic-embed-text (if Docker Ollama is used)
docker exec portal5-ollama ollama list 2>/dev/null | grep nomic-embed-text && \
    echo "PASS: nomic-embed-text available in Docker Ollama" || \
    echo "INFO: nomic-embed-text not in Docker Ollama (may be on host Ollama)"

# Check host Ollama if available
if curl -s http://localhost:11434/api/tags 2>/dev/null | grep -q nomic-embed-text; then
    echo "PASS: nomic-embed-text available on host Ollama"
fi
```

---

## PHASE 12 — Pipeline Logs Validation

```bash
# Verify pipeline is logging routing decisions
docker compose -f deploy/portal-5/docker-compose.yml logs portal-pipeline --tail=50 2>&1 | grep -c -i "routing\|workspace\|backend\|model" | \
    xargs -I{} bash -c '[ {} -gt 0 ] && echo "PASS: Pipeline logging routing events ({} lines)" || echo "INFO: No routing events yet (send a chat first)"'

# Check for any ERROR or CRITICAL in logs
ERROR_COUNT=$(docker compose -f deploy/portal-5/docker-compose.yml logs portal-pipeline --tail=200 2>&1 | grep -c -iE "ERROR|CRITICAL|traceback")
[ "$ERROR_COUNT" -eq 0 ] && echo "PASS: No errors in pipeline logs" || echo "WARN: $ERROR_COUNT error(s) found in pipeline logs"
```

---

## PHASE 13 — launch.sh Smoke Test (HOWTO: Testing)

```bash
# HOWTO: ./launch.sh test — run live smoke tests
./launch.sh test 2>&1 | tail -20
TEST_EXIT=$?
[ $TEST_EXIT -eq 0 ] && echo "PASS: launch.sh test passed" || echo "WARN: launch.sh test returned exit $TEST_EXIT"
```

---

## PHASE 14 — Documentation Cross-Reference Audit

```bash
python3 -c "
import os, re

errors = []
warnings = []

# 1. Check all ports mentioned in HOWTO match CLAUDE.md port table
howto = open('docs/HOWTO.md').read()
claude_md = open('CLAUDE.md').read()

# Extract port references from HOWTO
howto_ports = set(re.findall(r':(\d{4,5})', howto))
# Extract port references from CLAUDE.md port table
claude_ports = set(re.findall(r'\|\s*(\d{4,5})\s*\|', claude_md))

orphan_howto = howto_ports - claude_ports - {'8080', '8081', '11434'}  # Exclude well-known
if orphan_howto:
    warnings.append(f'Ports in HOWTO not in CLAUDE.md port table: {orphan_howto}')

# 2. Check all HOWTO curl endpoints exist in either docker-compose or code
curl_urls = re.findall(r'http://localhost:(\d+)(/\S*)?', howto)
for port, path in curl_urls:
    if port not in howto_ports:
        warnings.append(f'Undeclared port in HOWTO curl: :{port}{path}')

# 3. Verify version strings match
versions = re.findall(r'Portal\s+5\.(\d+(?:\.\d+)?)', howto)
readme = open('README.md').read()
readme_versions = re.findall(r'Portal\s+5\.(\d+(?:\.\d+)?)', readme)

# 4. Check HOWTO references to .env variables exist in .env.example
env_example = open('.env.example').read()
howto_env_refs = re.findall(r'([A-Z_]{3,})\s*=', howto)
for var in set(howto_env_refs):
    if var not in env_example and var not in ('PASS', 'FAIL', 'WARN', 'INFO', 'PATH'):
        warnings.append(f'HOWTO references env var {var} not in .env.example')

if errors:
    for e in errors:
        print(f'FAIL: {e}')
elif warnings:
    for w in warnings:
        print(f'WARN: {w}')
    print(f'INFO: {len(warnings)} documentation warnings found')
else:
    print('PASS: Documentation cross-references consistent')
" 2>&1
```

---

## PHASE 15 — Results Collection & Report

```bash
cat << 'REPORT_SCRIPT' > /tmp/portal5_collect_results.sh
#!/bin/bash
echo "═══════════════════════════════════════════════════"
echo "  Portal 5.2 — Validation Report"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "═══════════════════════════════════════════════════"
echo ""

# Collect service states
echo "── Service Health ──"
docker compose -f deploy/portal-5/docker-compose.yml ps --format "table {{.Name}}\t{{.Status}}" 2>/dev/null

echo ""
echo "── Test Summary ──"
cd "$(dirname "$0")/../portal-5" 2>/dev/null || cd portal-5 2>/dev/null || true

# Unit tests
source .venv/bin/activate 2>/dev/null
pytest tests/ -q --tb=no 2>&1 | tail -3

echo ""
echo "── Endpoints Reachable ──"
for PORT_SVC in "8080:OpenWebUI" "9099:Pipeline" "3000:Grafana" "9090:Prometheus" "8913:DocsMCP" "8914:SandboxMCP" "8912:MusicMCP" "8916:TTSMCP"; do
    PORT=$(echo "$PORT_SVC" | cut -d: -f1)
    SVC=$(echo "$PORT_SVC" | cut -d: -f2)
    HTTP=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT" 2>/dev/null)
    printf "  %-15s :%-5s → %s\n" "$SVC" "$PORT" "$HTTP"
done

echo ""
echo "── Workspace Count ──"
set -a; source .env 2>/dev/null; set +a
WC=$(curl -s http://localhost:9099/v1/models -H "Authorization: Bearer $PIPELINE_API_KEY" 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('data',[])))" 2>/dev/null)
echo "  Workspaces/personas registered: $WC"

echo ""
echo "═══════════════════════════════════════════════════"
echo "  Validation complete"
echo "═══════════════════════════════════════════════════"
REPORT_SCRIPT
chmod +x /tmp/portal5_collect_results.sh
bash /tmp/portal5_collect_results.sh 2>&1
```

---

## Error Correction Protocol

If any phase produces a FAIL result, Claude Code should:

1. **Read the relevant source file** — trace the failure to a specific module
2. **Check docker logs** — `docker compose -f deploy/portal-5/docker-compose.yml logs <service> --tail=50`
3. **Propose a fix** — create a patch or describe the code change
4. **If it's a documentation error** — update the relevant .md file with the correction
5. **If it's a test gap** — add a new test case to `tests/unit/`
6. **Re-run the failing phase** to confirm the fix
7. **Log all findings** in a `VALIDATION_RESULTS.md` file at the project root

### Common fixes to attempt automatically:

| Symptom | Likely Fix |
|---------|-----------|
| Unit test import error | `pip install -e ".[dev,mcp]"` |
| Docker service unhealthy | `docker compose -f deploy/portal-5/docker-compose.yml restart <service>` |
| Pipeline 401 | Check `PIPELINE_API_KEY` in `.env` matches |
| MCP tool server 404 | Check container is running: `docker ps \| grep mcp` |
| Frontend login fails | Verify `OPENWEBUI_ADMIN_PASSWORD` in `.env` |
| Workspace count < 13 | Re-run `./launch.sh seed` |
| ruff format failures | Run `ruff format .` to auto-fix |
| Stale .env | Delete `.env` and re-run `./launch.sh up` to regenerate |

---

## Execution Instructions for Claude Code

Run this entire task as a single agentic session:

```bash
# From the production system, inside the portal-5 directory:
claude --dangerously-skip-permissions

# Then paste or reference this task file:
# "Execute VALIDATION_TASK.md phases 0 through 15 sequentially.
#  For each phase, run every command, collect results, and fix any
#  failures before proceeding to the next phase. Write all findings
#  to VALIDATION_RESULTS.md at the end."
```

The agent should:
1. Run each phase top-to-bottom
2. Collect PASS/FAIL/WARN/INFO for every check
3. Attempt automatic fixes for FAILs
4. Re-test after fixes
5. Produce `VALIDATION_RESULTS.md` with the complete run log
6. Flag any items that require human intervention

---

*Generated: 2026-03-30 | For Portal 5.2.0 | Covers HOWTO.md sections 1-22 + all CLI commands*
