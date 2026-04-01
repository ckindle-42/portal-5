# Portal 6.0 Release Acceptance — Claude Code Agent Task

**This document IS the test suite.** Execute every section top to bottom. For each test: run the command, compare output to expected, fix failures, correct docs, re-test until green. Write results to `ACCEPTANCE_RESULTS.md`.

**Run from:** `cd ~/portal-5` with stack running (`./launch.sh up`)

---

## ⛔ CRITICAL RULES — READ BEFORE DOING ANYTHING

1. **NEVER modify these files to make tests pass:**
   - `scripts/openwebui_init.py`
   - `Dockerfile.mcp`
   - `deploy/portal-5/docker-compose.yml`
   - Any file under `portal_mcp/`
   - Any file under `portal_pipeline/`

   If a test fails against these files, **the test is wrong** — fix the test, not the production code. These files are already working in production.

2. **Files you CAN edit to fix failures:**
   - `docs/HOWTO.md` — fix counts, add missing rows, correct examples
   - `scripts/update_workspace_tools.py` — add missing workspace IDs
   - `imports/openwebui/` JSON files — fix workspace configs
   - `portal5_acceptance.py` — if a test is wrong, fix the test
   - `ACCEPTANCE_TASK.md` — if a task instruction is wrong, fix the instruction

3. **Model loading takes time.** When switching between workspaces, models load and unload. A 30-second wait is normal. A 60-second wait means a cold load. Timeouts should be 120-180 seconds for chat completions.

4. **First-time downloads are expected.** AudioCraft downloads ~300MB on first music generation. DinD pulls `python:3.11-slim` on first sandbox execution. Wan2.2 is ~18GB. These are not failures — wait for them.

5. **Personas route through the `auto` workspace.** Personas inject a system prompt and use Open WebUI's model routing. When testing personas through the pipeline directly, send `model=auto` with the persona's system prompt in the messages array. Do NOT send `model=dolphin-llama3:8b` — the pipeline only recognizes workspace IDs.

---

## SETUP — Install test dependencies

```bash
pip install mcp httpx pyyaml playwright
python3 -m playwright install chromium
pip install -e ".[dev]"
```

---

## §1 Quick Start — HOWTO claims `./launch.sh status` shows all healthy

**Test:**
```bash
./launch.sh status
```
**Expected:** Every service shows "healthy" or "running". Zero services "unhealthy" or "exited".

**Fix if fails:** `./launch.sh up` — if still failing, check `docker compose -f deploy/portal-5/docker-compose.yml logs <service> --tail=30`

---

## §2 Chat with AI — Pipeline routes and returns responses

**Test:** Send a chat through the pipeline and verify a response comes back.
```bash
source .env
curl -s http://localhost:9099/v1/chat/completions \
  -H "Authorization: Bearer $PIPELINE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "auto", "messages": [{"role": "user", "content": "Explain how Docker networking works in one sentence."}], "stream": false, "max_tokens": 50}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); c=d.get('choices',[{}])[0].get('message',{}).get('content',''); print(f'PASS: {c[:80]}' if c else f'FAIL: {d}')"
```
**Expected:** A coherent response about Docker networking.

**Test:** Verify routing appears in pipeline logs.
```bash
docker compose -f deploy/portal-5/docker-compose.yml logs portal-pipeline --tail=5 | grep "Routing workspace="
```
**Expected:** Line containing `Routing workspace=auto`
**HOWTO claims:** "Should show: Routing workspace=auto → backend=ollama-local model=dolphin-llama3:8b stream=True"
**Doc fix needed if:** The backend ID or model name in the HOWTO doesn't match actual log output. Update the HOWTO example to match.

---

## §3 Workspaces — All workspace IDs present in /v1/models

**Test:** Count workspace IDs from code, then verify pipeline serves them all.
```bash
# Count from code (source of truth)
python3 -c "
import re
src = open('portal_pipeline/router_pipe.py').read()
block = src[src.index('WORKSPACES:'):src.index('# ── Content-aware')]
ids = sorted(set(re.findall(r'\"(auto[^\"]*)\"\s*:\s*\{', block)))
print(f'Code has {len(ids)} workspaces: {ids}')
"
```

```bash
# Count from pipeline API
source .env
curl -s http://localhost:9099/v1/models \
  -H "Authorization: Bearer $PIPELINE_API_KEY" \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
ids=[m['id'] for m in d.get('data',[])]
ws=[i for i in ids if i.startswith('auto')]
print(f'Pipeline serves {len(ws)} workspaces: {sorted(ws)}')
print(f'Total models (workspaces+personas): {len(ids)}')
"
```
**Expected:** Same count. Currently should be **14** (includes `auto-compliance`).
**HOWTO currently says:** "Expected: 13 workspace IDs" — **FIX to 14**.
**HOWTO workspace table:** Missing `Portal Compliance Analyst` row — **ADD IT:**
```
| Portal Compliance Analyst | NERC CIP gap analysis | Qwen3.5-35B (MLX) |
```

**Test:** Verify workspace IDs match between router_pipe.py and backends.yaml.
```bash
python3 -c "
import re, yaml
src = open('portal_pipeline/router_pipe.py').read()
block = src[src.index('WORKSPACES:'):src.index('# ── Content-aware')]
pipe = sorted(set(re.findall(r'\"(auto[^\"]*)\"\s*:\s*\{', block)))
cfg = yaml.safe_load(open('config/backends.yaml'))
yml = sorted(cfg['workspace_routing'].keys())
print(f'router: {pipe}')
print(f'yaml:   {yml}')
assert pipe == yml, f'MISMATCH pipe_only={set(pipe)-set(yml)} yaml_only={set(yml)-set(pipe)}'
print('PASS: workspace IDs match')
"
```

**Test:** Verify `update_workspace_tools.py` covers all workspace IDs.
```bash
python3 -c "
import re
src = open('scripts/update_workspace_tools.py').read()
tools_ids = sorted(set(re.findall(r'\"(auto[^\"]*)\"\s*:', src)))
pipe = open('portal_pipeline/router_pipe.py').read()
block = pipe[pipe.index('WORKSPACES:'):pipe.index('# ── Content-aware')]
pipe_ids = sorted(set(re.findall(r'\"(auto[^\"]*)\"\s*:\s*\{', block)))
missing = set(pipe_ids) - set(tools_ids)
if missing:
    print(f'FAIL: update_workspace_tools.py missing: {missing}')
    print('FIX: Add these to WORKSPACE_TOOLS dict in scripts/update_workspace_tools.py')
else:
    print(f'PASS: all {len(tools_ids)} covered')
"
```
**Fix if fails:** Add `"auto-compliance": []` to `WORKSPACE_TOOLS` in `scripts/update_workspace_tools.py`.

---

## §3 continued — Chat through EVERY workspace

**Test:** Send a non-streaming chat through each workspace and verify response content.
```bash
source .env
python3 -c "
import httpx, json, re, sys

API_KEY = '$(grep PIPELINE_API_KEY .env | cut -d= -f2)'
src = open('portal_pipeline/router_pipe.py').read()
block = src[src.index('WORKSPACES:'):src.index('# ── Content-aware')]
ws_ids = sorted(set(re.findall(r'\"(auto[^\"]*)\"\s*:\{', block)))

h = {'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json'}
with httpx.Client(timeout=90) as c:
    for ws in ws_ids:
        try:
            r = c.post('http://localhost:9099/v1/chat/completions', headers=h,
                json={'model': ws, 'messages': [{'role':'user','content':f'Reply with one word. Workspace: {ws}'}],
                      'stream': False, 'max_tokens': 20})
            if r.status_code == 200:
                text = r.json().get('choices',[{}])[0].get('message',{}).get('content','')
                print(f'PASS {ws}: {text[:40]}')
            elif r.status_code == 503:
                print(f'WARN {ws}: 503 — model not pulled')
            else:
                print(f'FAIL {ws}: HTTP {r.status_code}')
        except Exception as e:
            print(f'FAIL {ws}: {e}')
"
```
**Expected:** PASS for every workspace. WARN is acceptable only if the specialized model isn't pulled yet — fix with `ollama pull <model>`.

---

## §4 Personas — All personas seeded and visible

**Test:** Count persona YAML files and verify they're in the pipeline model list.
```bash
source .env
python3 -c "
import yaml, json, httpx, os

# Read all personas from YAML
personas = []
for f in sorted(__import__('pathlib').Path('config/personas').glob('*.yaml')):
    personas.append(yaml.safe_load(f.read_text()))

print(f'Persona YAML files: {len(personas)}')

# Check which appear in pipeline
h = {'Authorization': f'Bearer {os.environ[\"PIPELINE_API_KEY\"]}'}
r = httpx.get('http://localhost:9099/v1/models', headers=h)
model_names = [m['name'].lower() for m in r.json().get('data', [])]
model_ids = [m['id'].lower() for m in r.json().get('data', [])]

found = []
missing = []
for p in personas:
    slug = p['slug'].lower()
    name = p['name'].lower()
    if slug in model_ids or name in model_names or any(slug in mid for mid in model_ids):
        found.append(p['name'])
    else:
        missing.append(f\"{p['name']} (slug={p['slug']})\")

print(f'Found in pipeline: {len(found)}/{len(personas)}')
if missing:
    print(f'MISSING: {missing}')
    print('FIX: Run ./launch.sh seed')
else:
    print('PASS: all personas present')
"
```
**HOWTO claims:** "35 total" — **FIX to actual count** (currently 37, includes new compliance personas).
**HOWTO persona table:** Missing compliance category — **ADD:**
```
| Compliance (2) | NERC CIP Compliance Analyst, CIP Policy Writer |
```

---

## §5 Code Execution — Sandbox actually runs code

**Test:** Call execute_python via real MCP SDK and verify output.
```bash
python3 -c "
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def test():
    async with streamablehttp_client('http://localhost:8914/mcp') as (r,w,_):
        async with ClientSession(r,w) as s:
            await s.initialize()
            result = await s.call_tool('execute_python', {'code': 'print(sum(range(1,101)))', 'timeout': 15})
            text = str(result.content[0].text) if result.content else str(result)
            if '5050' in text:
                print(f'PASS: sandbox returned 5050')
            else:
                print(f'RESULT: {text[:200]}')

asyncio.run(test())
"
```
**Expected:** Output contains `5050`.
**HOWTO §5 verify command:**
```bash
curl -s http://localhost:8914/health
# Should return: {"status": "ok"}
```
Run that too and confirm the response matches.

---

## §6 Security Routing — Auto-routing with security keywords

**Test:** Send security keywords through `auto` workspace, check pipeline routes to `auto-redteam`.
```bash
source .env
curl -s http://localhost:9099/v1/chat/completions \
  -H "Authorization: Bearer $PIPELINE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "auto", "messages": [{"role": "user", "content": "exploit vulnerability payload injection"}], "stream": false, "max_tokens": 5}' > /dev/null

docker compose -f deploy/portal-5/docker-compose.yml logs portal-pipeline --tail=5 | grep "Auto-routing"
```
**Expected:** Log line containing `detected workspace 'auto-redteam'`

---

## §7 Document Generation — Create actual .docx, .xlsx, .pptx files

**Test:** Call each document tool via MCP SDK, verify files created.
```bash
python3 -c "
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def test():
    async with streamablehttp_client('http://localhost:8913/mcp') as (r,w,_):
        async with ClientSession(r,w) as s:
            await s.initialize()

            # Word
            result = await s.call_tool('create_word_document', {'title':'Test Report','content':'# Summary\n\nValidation passed.\n\n## Details\n\n- All workspaces work\n- All tools operational'})
            print(f'Word: {result.content[0].text[:100]}')

            # PowerPoint
            result = await s.call_tool('create_powerpoint', {'title':'Test Deck','slides':[{'title':'Intro','content':'Portal 6.0'},{'title':'Done','content':'All tests passed'}]})
            print(f'PPTX: {result.content[0].text[:100]}')

            # Excel
            result = await s.call_tool('create_excel', {'title':'Budget','data':[['Item','Cost'],['HW',15000],['SW',8000]]})
            print(f'Excel: {result.content[0].text[:100]}')

            # List files
            result = await s.call_tool('list_generated_files', {})
            print(f'Files: {result.content[0].text[:200]}')

asyncio.run(test())
"
```
**Expected:** Each call returns `"success": true` with a filename.
**HOWTO §7 verify commands:**
```bash
curl -s http://localhost:8913/health
# Should return: {"status": "ok"}
curl -s http://localhost:8913/tools | python3 -m json.tool
# Should list: create_word_document, create_powerpoint, create_excel, convert_document, list_generated_files
```
Run both and verify output matches HOWTO claims.

---

## §8 Image Generation — ComfyUI health + MCP bridge + generate real image

**Test:**
```bash
curl -s http://localhost:8188/system_stats | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f'PASS: ComfyUI v{d[\"system\"][\"comfyui_version\"]}')
"

curl -s http://localhost:8910/health
# Should return: {"status": "ok", "service": "comfyui-mcp"}
```

**Test:** Generate a real image via MCP SDK (the Python script does this — verify output file path in response).

**Test:** Generate a real video via MCP SDK (HOWTO §9 — the Python script sends "ocean waves crashing on a rocky shoreline at golden hour").

**Nothing is optional on the production system.** ComfyUI, image generation, and video generation must all work.

---

## §10 Music Generation — MCP tool call

**Test:**
```bash
python3 -c "
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def test():
    async with streamablehttp_client('http://localhost:8912/mcp') as (r,w,_):
        async with ClientSession(r,w) as s:
            await s.initialize()
            result = await s.call_tool('list_music_models', {})
            print(f'Models: {result.content[0].text[:200]}')

asyncio.run(test())
"
```
**HOWTO §10 verify:** `curl -s http://localhost:8912/health` should return `{"status": "ok"}`
**HOWTO claims:** "Returns: {\"status\": \"ok\", \"backend\": \"audiocraft\"}" — verify this matches actual output and fix if different.

---

## §11 TTS — Direct API call matches HOWTO example

**Test:** Run the EXACT curl from HOWTO §11:
```bash
curl -X POST http://localhost:8916/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input": "Hello from Portal 5!", "voice": "af_heart"}' \
  --output /tmp/hello_test.wav

[ -s /tmp/hello_test.wav ] && echo "PASS: audio file created ($(wc -c < /tmp/hello_test.wav) bytes)" || echo "FAIL: no audio"
file /tmp/hello_test.wav 2>/dev/null || true
rm -f /tmp/hello_test.wav
```
**Expected:** WAV file > 0 bytes. NOTE: HOWTO says `--output hello.mp3` but the server returns WAV. **Fix HOWTO** to say `--output hello.wav` or note the actual format.

**Test:** Verify health matches HOWTO claim.
```bash
curl -s http://localhost:8916/health
# HOWTO claims: {"status": "ok", "backend": "kokoro"}
```
Verify actual output matches. Fix HOWTO if fields differ.

**Test:** Call speak via MCP SDK with each voice from HOWTO voice table:
```bash
python3 -c "
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

VOICES = ['af_heart','af_sky','af_bella','af_nicole','af_sarah','am_adam','am_michael','bf_emma','bf_isabella','bm_george','bm_lewis']

async def test():
    async with streamablehttp_client('http://localhost:8916/mcp') as (r,w,_):
        async with ClientSession(r,w) as s:
            await s.initialize()
            result = await s.call_tool('list_voices', {})
            available = result.content[0].text if result.content else ''
            print(f'Available voices: {available[:300]}')
            for v in VOICES:
                if v.lower() in available.lower():
                    print(f'  PASS: {v} available')
                else:
                    print(f'  WARN: {v} not in list (HOWTO claims it exists)')

asyncio.run(test())
"
```
**Expected:** All 11 voices from HOWTO §11 table are available. If any are missing, fix the HOWTO voice table.

---

## §12 Whisper — Health check per HOWTO

**Test:** Run the EXACT command from HOWTO:
```bash
docker exec portal5-mcp-whisper python3 -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8915/health').read().decode())"
```
**Expected:** `{"status": "ok", "service": "whisper-mcp"}`

---

## §13 Web Search — SearXNG healthy

**Test:**
```bash
docker compose -f deploy/portal-5/docker-compose.yml ps searxng
# Should show "healthy"
```

---

## §14 RAG — Embedding model pulled

**Test:**
```bash
# Try Docker Ollama first, then host Ollama
docker exec portal5-ollama ollama list 2>/dev/null | grep nomic-embed-text \
  || curl -s http://localhost:11434/api/tags | python3 -c "import sys,json; tags=[m['name'] for m in json.load(sys.stdin).get('models',[])]; print('PASS' if any('nomic' in t for t in tags) else 'FAIL: nomic-embed-text not found')"
```

---

## §15 User Management — CLI commands work

**Test:**
```bash
./launch.sh list-users
./launch.sh add-user acceptance-test@portal.local "Acceptance Tester" 2>&1 || true
```
**Expected:** list-users shows at least the admin account. add-user either creates or reports "already exists".

---

## §16-17 Telegram/Slack — Config presence only (requires external tokens)

**Test:** Verify the HOWTO-listed workspace IDs match code.
```bash
python3 -c "
import re
src = open('portal_pipeline/router_pipe.py').read()
block = src[src.index('WORKSPACES:'):src.index('# ── Content-aware')]
ids = sorted(set(re.findall(r'\"(auto[^\"]*)\"\s*:\s*\{', block)))
howto = open('docs/HOWTO.md').read()
# HOWTO §16 lists available workspaces for Telegram
howto_ws = re.findall(r'auto(?:-\w+)?', howto[howto.index('Available workspaces'):howto.index('Available workspaces')+500])
missing = set(ids) - set(howto_ws)
if missing:
    print(f'FAIL: HOWTO §16 missing workspace IDs: {missing}')
else:
    print(f'PASS: all {len(ids)} workspace IDs listed in §16')
"
```
**Fix if fails:** Add missing IDs (like `auto-compliance`) to the HOWTO §16 available workspaces list.

---

## §22 Metrics — All HOWTO verify commands

**Test:**
```bash
# Prometheus scraping (HOWTO §22 verify)
curl -s http://localhost:9090/api/v1/targets | python3 -c "import sys,json; t=json.load(sys.stdin)['data']['activeTargets']; p=[x for x in t if '9099' in str(x.get('scrapeUrl',''))]; print(f'PASS: {len(p)} pipeline target(s)' if p else 'FAIL: no pipeline target')"

# Pipeline /metrics (HOWTO §22 verify)
curl -s http://localhost:9099/metrics | head -20

# Metrics unauthenticated (recent fix)
curl -s -o /dev/null -w "%{http_code}" http://localhost:9099/metrics
# Expected: 200 without any auth header
```

**Test:** portal_workspaces_total matches code count.
```bash
curl -s http://localhost:9099/metrics | grep portal_workspaces_total
```
**Expected:** `portal_workspaces_total 14` (or whatever the current count is).

---

## GUI — Chromium: Login, every workspace, every persona, tool servers, admin

**Test:** Run the full Playwright browser suite.
```bash
python3 -c "
import asyncio, os, re, yaml, json

os.environ.setdefault('OPENWEBUI_ADMIN_EMAIL', 'admin@portal.local')
for line in open('.env').readlines():
    if '=' in line and not line.strip().startswith('#'):
        k,_,v = line.strip().partition('=')
        os.environ.setdefault(k,v)

EMAIL = os.environ['OPENWEBUI_ADMIN_EMAIL']
PASS = os.environ.get('OPENWEBUI_ADMIN_PASSWORD','')

# Load workspace names from code
src = open('portal_pipeline/router_pipe.py').read()
block = src[src.index('WORKSPACES:'):src.index('# ── Content-aware')]
ws_names = re.findall(r'\"name\":\s*\"([^\"]+)\"', block)

# Load persona names from YAML
personas = [yaml.safe_load(f.read_text())['name'] for f in sorted(__import__('pathlib').Path('config/personas').glob('*.yaml'))]

async def run():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await (await browser.new_context(viewport={'width':1440,'height':900})).new_page()

        # Login
        await page.goto('http://localhost:8080', wait_until='networkidle', timeout=20000)
        await page.fill('input[type=\"email\"], input[name=\"email\"]', EMAIL)
        await page.fill('input[type=\"password\"]', PASS)
        await page.locator('button[type=\"submit\"], button:has-text(\"Sign in\")').first.click()
        await page.wait_for_selector('textarea, [contenteditable]', timeout=15000)
        print('PASS: Login → chat loaded')
        await page.screenshot(path='/tmp/p5_gui_chat.png')

        # Open dropdown
        await page.wait_for_timeout(2000)
        for sel in ['button[aria-haspopup]','button:has-text(\"Portal\")','button:has-text(\"Auto\")']:
            loc = page.locator(sel)
            if await loc.count() > 0:
                await loc.first.click()
                await page.wait_for_timeout(2000)
                break

        body = await page.inner_text('body')
        body_l = body.lower()

        # Check every workspace
        ws_found = [n for n in ws_names if re.sub(r'^[^\w]+','',n).strip().lower() in body_l]
        ws_miss = [n for n in ws_names if re.sub(r'^[^\w]+','',n).strip().lower() not in body_l]
        print(f'Workspaces in GUI: {len(ws_found)}/{len(ws_names)}')
        if ws_miss: print(f'  MISSING: {ws_miss}')

        # Check every persona
        p_found = [n for n in personas if n.lower() in body_l]
        p_miss = [n for n in personas if n.lower() not in body_l]
        print(f'Personas in GUI: {len(p_found)}/{len(personas)}')
        if p_miss: print(f'  NOT VISIBLE (may need scroll): {p_miss[:10]}')

        await page.screenshot(path='/tmp/p5_gui_dropdown.png')
        await page.keyboard.press('Escape')

        # Chat textarea
        ta = page.locator('textarea, [contenteditable=\"true\"]')
        if await ta.count() > 0:
            await ta.first.fill('test'); await ta.first.fill('')
            print('PASS: Chat textarea works')

        # Admin panel
        await page.goto('http://localhost:8080/admin', wait_until='networkidle', timeout=10000)
        body = await page.inner_text('body')
        print(f\"PASS: Admin panel\" if any(w in body.lower() for w in ['admin','settings','users']) else 'WARN: Admin panel content unclear')
        await page.screenshot(path='/tmp/p5_gui_admin.png')

        await browser.close()

asyncio.run(run())
"
```
**Expected:** All workspaces found, majority of personas found (some may require scrolling), chat works, admin accessible.

---

## CLI Quick Reference — Every command from HOWTO tested

**Test:**
```bash
./launch.sh status && echo "PASS: status"
./launch.sh list-users && echo "PASS: list-users"
./launch.sh backup && echo "PASS: backup" && ls -la backups/ | tail -3
```

---

## HOWTO Document Corrections Checklist

After running all tests above, verify and fix:

- [ ] §3: Workspace count says "13" → change to actual count from code
- [ ] §3: Workspace table missing `Portal Compliance Analyst` → add row
- [ ] §4: Persona count says "35 total" → change to actual count from `config/personas/`
- [ ] §4: Persona table missing Compliance category → add `Compliance (2) | NERC CIP Compliance Analyst, CIP Policy Writer`
- [ ] §11: `--output hello.mp3` → verify actual format (WAV vs MP3) and fix
- [ ] §11: Health response claims `"backend": "audiocraft"` in §10 → verify actual JSON
- [ ] §16: Available workspaces list missing `auto-compliance` → add
- [ ] Footer: "Last updated: 2026-03-30 | Portal 5.2.0" → update date and version to 6.0

---

## Final Validation Loop

After all fixes:
```bash
# Re-run unit tests
pytest tests/ -v --tb=short

# Re-run workspace consistency
python3 -c "
import re, yaml
src = open('portal_pipeline/router_pipe.py').read()
block = src[src.index('WORKSPACES:'):src.index('# ── Content-aware')]
pipe = set(re.findall(r'\"(auto[^\"]*)\"\s*:\s*\{', block))
cfg = yaml.safe_load(open('config/backends.yaml'))
yml = set(cfg['workspace_routing'].keys())
tools = set(re.findall(r'\"(auto[^\"]*)\"\s*:', open('scripts/update_workspace_tools.py').read()))
assert pipe == yml == tools, f'MISMATCH pipe={pipe-yml} yaml={yml-pipe} tools={tools-pipe}'
print(f'PASS: {len(pipe)} workspace IDs consistent across router, backends.yaml, and update_workspace_tools.py')
"

# Re-run all service health
./launch.sh status

# Write results
echo "All tests passed" >> ACCEPTANCE_RESULTS.md
```

---

## Claude Code Instruction

> Execute every section of this document from top to bottom. Run each test command, compare to expected output, and fix any discrepancies. When fixing code: edit the file, re-run the test. When fixing docs: edit docs/HOWTO.md, note the change. After all sections complete, run the Final Validation Loop. Write all findings (PASS/FAIL/FIX) to ACCEPTANCE_RESULTS.md with timestamps. The goal: zero failures, docs match reality, ready for v6.0 tag.
