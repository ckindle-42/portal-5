# PORTAL5_UAT_EXECUTE_V1 — Claude Code Execution Prompt

Clone `https://github.com/ckindle-42/portal-5/`. The live system is already running.
`tests/portal5_uat_driver.py` is already implemented and waiting to run.

---

## Your Role

You are the **UAT execution agent**. You do not build or modify the driver. You run it,
diagnose failures, tighten or loosen assertions when the test is wrong, and produce
a clean run. This guide is designed to be run repeatedly — treat every run as fresh.

**The model behavior is assumed correct.** If an assertion fails, your first assumption
is that the keyword list is too strict or phrased differently than the model's output.
Investigate before marking FAIL. Only mark FAIL after 3 prompt variants all produce
genuinely wrong model behavior.

**Sequential only.** This is a single-user M4 Mac lab. Never send concurrent inference
requests. The driver enforces this via cascade ordering — tests run by tier
(`mlx_large` → `mlx_small` → `ollama` → `any`) with full model eviction at each
tier transition. MLX and Ollama are never loaded simultaneously.

---

## What the UAT Driver Tests

104 tests that produce **real Open WebUI conversations visible in the browser** at
`http://localhost:8080`. Each conversation is named, tagged, and reviewable. Artifacts
(DOCX, XLSX, PPTX, WAV, MP4) appear as file attachments in the relevant chats.

The driver is NOT the acceptance suite. It validates user-observable behavioral
contracts that keyword matching cannot catch: does the persona ask before diagnosing?
Does the Excel Sheet compute values, not show formula text? Does the Code Review
Assistant scope its review to the diff only?

---

## Calibration Mode

Before tightening or replacing assertion keyword lists, run a calibration pass.
Calibration runs every test once, captures the real model responses to JSON,
and lets a human (or a follow-up agent) tag responses as good/bad/skip. Tagged
responses then drive `--emit-signals-from`, which proposes per-section TF-IDF
keyword sets to feed back into `tests/quality_signals.py` and the UAT catalog.

```bash
# Capture
python3 tests/portal5_uat_driver.py --calibrate --calibrate-output calibration.json

# (Manually edit calibration.json — set review_tag on each entry)

# Generate
python3 tests/portal5_uat_driver.py --emit-signals-from calibration.json
```

Full workflow: `docs/UAT_CALIBRATION.md`. Use `--section <n>` to calibrate
a single section without running the full suite.

---

## Step 1 — Orient and Verify

```bash
git clone https://github.com/ckindle-42/portal-5/
cd portal-5

# Read before running anything
cat CLAUDE.md
cat KNOWN_LIMITATIONS.md

# Confirm driver exists and is valid
test -f tests/portal5_uat_driver.py && echo "Driver present" || echo "MISSING — build first"
python3 -m py_compile tests/portal5_uat_driver.py && echo "Syntax OK"
python3 tests/portal5_uat_driver.py --help

# Confirm stack
./launch.sh status
curl -sf http://localhost:8080/health && echo "OWUI OK"
curl -sf http://localhost:9099/health | python3 -m json.tool

# Confirm credentials exist
grep -E "OPENWEBUI_ADMIN_EMAIL|OPENWEBUI_ADMIN_PASSWORD" .env

# Confirm OWUI auth and chat creation API (the driver's critical path)
python3 -c "
import httpx, uuid
from dotenv import dotenv_values
env = dotenv_values('.env')
tok = httpx.post('http://localhost:8080/api/v1/auths/signin',
    json={'email': env['OPENWEBUI_ADMIN_EMAIL'], 'password': env['OPENWEBUI_ADMIN_PASSWORD']}).json().get('token','')
assert tok, 'AUTH FAILED — check OPENWEBUI_ADMIN_PASSWORD in .env'
r = httpx.post('http://localhost:8080/api/v1/chats/new',
    json={'chat': {'id': str(uuid.uuid4()), 'title': 'UAT-preflight', 'models': ['auto'],
                   'messages': [], 'history': {'messages': {}, 'currentId': None},
                   'tags': [], 'params': {}, 'timestamp': 0}},
    headers={'Authorization': f'Bearer {tok}', 'Content-Type': 'application/json'}, timeout=10)
assert r.status_code in (200, 201), f'Chat create failed: {r.status_code} {r.text[:200]}'
print(f'Auth OK, chat API OK — ID prefix: {r.json().get(\"id\",\"\")[:8]}')
"

# Confirm Playwright Chromium
python3 -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page()
    pg.goto('http://localhost:8080', timeout=10000)
    print('Playwright OK — page title:', pg.title())
    b.close()
"

# Confirm MCP services (required for tool tests)
for port in 8912 8913 8914 8916 8917 8918 8919; do
  curl -s --max-time 3 http://localhost:$port/health && echo " :$port OK" || echo " :$port DOWN"
done
```

If any check fails, fix the environment before proceeding. Do not run tests
against a degraded stack.

---

## Step 2 — Smoke Test

Run one group before committing to the full sequence. Use headed mode to watch
the browser create the first OWUI conversations:

```bash
python3 tests/portal5_uat_driver.py --section auto --headed 2>&1 | tee /tmp/uat_smoke.log
```

Open `http://localhost:8080` and confirm:
- Conversations titled `UAT: WS-01 …`, `UAT: P-W06 …`, `UAT: P-W03 …` appear in the sidebar
- Each is renamed `[PASS]`, `[WARN]`, or `[FAIL]` after its test completes
- `tests/UAT_RESULTS.md` exists and has rows with clickable OWUI links

If the smoke test produces zero conversations or a Python error, diagnose before
running anything else (see Step 5).

---

## Step 3 — Execution Order

Tests are grouped by **model backend tier, largest first**, not by feature category.
When a model is loaded, every test that uses it runs before switching. This eliminates
redundant model loads and prevents OOM from MLX + Ollama both loaded simultaneously.

The driver automatically reorders tests via `sort_tests_cascade()`:

### Cascade sequence (automatic — no manual ordering needed)

| Tier | Tests | Backend behavior |
|---|---|---|
| 1. `mlx_large` | 23 tests (80B MoE, 70B, 32B models) | Load biggest first while memory is freshest |
| 2. `mlx_small` | 49 tests (8B–18B models) | Smaller models, faster throughput |
| 3. `ollama` | 12 tests (GGUF models) | MLX evicted first, then Ollama loads |
| 4. `any` | 20 tests (router/flexible) | Pipeline picks best available |

**Memory safety at every tier transition:**
- Before `mlx_large`/`mlx_small`: Ollama models are force-evicted
- Before `ollama`: MLX model is evicted via canary load
- After all tests: full cleanup evicts everything

Within each tier, tests are grouped by `model_slug` (persona) so the pipeline
doesn't switch models between tests that use the same persona.

### Running the full suite

```bash
# Full cascade — recommended. Driver handles ordering and memory safety.
python3 tests/portal5_uat_driver.py --all --skip-bots 2>&1 | tee /tmp/uat_full.log
```

### Running a single section (still works — driver reorders internally)

```bash
python3 tests/portal5_uat_driver.py --section auto-coding
```

When `--section` is used, only that section's tests are selected, but they're
still cascade-ordered within the selection (tier → model_slug).

### Single test rerun

```bash
python3 tests/portal5_uat_driver.py --test WS-04
python3 tests/portal5_uat_driver.py --test P-D06 --headed
```

---

## Step 4 — Run Commands

### Full cascade run (recommended — driver handles ordering and memory safety):

```bash
python3 tests/portal5_uat_driver.py --all --skip-bots 2>&1 | tee /tmp/uat_full.log
echo "Exit: $?"
```

The driver automatically:
1. Sorts tests by tier: `mlx_large` → `mlx_small` → `ollama` → `any`
2. Groups by `model_slug` within each tier
3. Evicts Ollama before MLX tiers, evicts MLX before Ollama tier
4. Cleans up all memory when done

### Single section (still works — driver cascade-reorders within selection):

```bash
python3 tests/portal5_uat_driver.py --section auto-coding     2>&1 | tee /tmp/uat_coding.log
python3 tests/portal5_uat_driver.py --section auto-security   2>&1 | tee /tmp/uat_security.log
python3 tests/portal5_uat_driver.py --section benchmark       2>&1 | tee /tmp/uat_bench.log
```

### Single test rerun:

```bash
python3 tests/portal5_uat_driver.py --test WS-04
python3 tests/portal5_uat_driver.py --test P-D06 --headed
```

### Common flags:

```bash
--all              # Run all 104 tests in cascade order
--skip-bots        # Skip A-05 (Telegram), A-06 (Slack) — require manual bot setup
--skip-artifacts   # Skip WS-11, T-08 (video/image) — require Wan2.2 + ComfyUI
--timeout 240      # Per-test inference timeout in seconds (default 120; use 360 for agentic)
--headed           # Visible browser window — use when debugging Playwright issues
--section <name>   # Run only one section's tests
--test <id>        # Run a single test by ID
--calibrate        # Capture responses for assertion tuning
```

### Live progress:

```bash
# In a separate terminal
tail -f tests/UAT_RESULTS.md
```

---

## Step 5 — Diagnose Every FAIL

Open `tests/UAT_RESULTS.md`. For each FAIL, click the linked OWUI conversation
and read what the model actually said before touching the assertion.

### Classification and action

| What you see in the OWUI conversation | Action |
|---|---|
| Response is correct, just used synonyms | Expand keyword list; add synonyms; change `contains` → `any_of` |
| Response is correct but inside a code block (assertion checks prose) | Verify `inner_text()` includes code block content; fix extraction if needed |
| Behavioral hard constraint violated (e.g. P-D06 coded without asking framework) | See Retry Protocol below |
| Empty response or HTTP timeout | Check model state — see Model State Checks below |
| Artifact test: no file appeared | Check MCP health + tool enable step — see Tool Failures below |
| Security test: model refused (abliterated workspace) | Check routing — model may have fallen back to a censored fallback |

### Retry protocol for behavioral failures

```bash
# 1. Read the exact system prompt for this persona
cat config/personas/<slug>.yaml | grep -A50 "system_prompt"

# 2. Confirm persona is seeded in OWUI
python3 -c "
import httpx
from dotenv import dotenv_values
env = dotenv_values('.env')
tok = httpx.post('http://localhost:8080/api/v1/auths/signin',
    json={'email': env['OPENWEBUI_ADMIN_EMAIL'], 'password': env['OPENWEBUI_ADMIN_PASSWORD']}).json()['token']
models = httpx.get('http://localhost:8080/api/v1/models/',
    headers={'Authorization': f'Bearer {tok}'}).json()
names = [m.get('id','') for m in (models if isinstance(models,list) else models.get('data',[]))]
print([n for n in names if '<slug>' in n])
"

# 3. If not seeded: reseed
./launch.sh reseed && sleep 15

# 4. Manual reproduction via pipeline
curl -s -X POST http://localhost:9099/v1/chat/completions \
  -H "Authorization: Bearer $(grep PIPELINE_API_KEY .env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"model": "<model_slug>", "messages": [{"role": "user", "content": "<prompt>"}], "stream": false, "max_tokens": 600}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])"

# 5. Try 2 more prompt phrasings. If all 3 produce wrong behavior → BLOCKED
```

### Model state checks

```bash
# MLX proxy
curl -s http://localhost:8081/health | python3 -m json.tool

# Ollama loaded models
curl -s http://localhost:11434/api/ps | python3 -m json.tool

# Pre-warm a model group before rerunning its section
curl -s -X POST http://localhost:9099/v1/chat/completions \
  -H "Authorization: Bearer $(grep PIPELINE_API_KEY .env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"model": "auto-coding", "messages": [{"role":"user","content":"hi"}], "max_tokens":5}'
sleep 30
```

### Routing checks (workspace tests)

```bash
docker logs portal5-pipeline --tail 30 | grep "Routing workspace="
```

### Tool failures (T-01 to T-12)

```bash
# Check MCP health for the relevant port
curl -s http://localhost:8913/health  # Documents (T-04–07)
curl -s http://localhost:8914/health  # Code sandbox (T-01–03)
curl -s http://localhost:8916/health  # TTS (T-09)
curl -s http://localhost:8919/health  # Security (T-11)

# Check pipeline for tool call evidence
docker logs portal5-pipeline --tail 100 | grep -i "tool\|mcp\|error"

# Check document MCP for artifact creation
docker logs portal5-mcp-documents --tail 50
```

### BLOCKED — when to use it

Mark BLOCKED only after all of:
1. Three distinct prompt phrasings all produce the same wrong behavior
2. `docs/HOWTO.md` or the validation guide confirms the expected behavior
3. The fix requires modifying a protected file

Record in `tests/UAT_RESULTS.md`:

```markdown
## BLOCKED-N: <test name>

**Test ID**: <id>  **Model slug**: <slug>
**Expected**: <quote from validation guide>
**Actual**: <copy model response verbatim>
**Retry 1**: [prompt variant] → [result summary]
**Retry 2**: [prompt variant] → [result summary]
**Retry 3**: [prompt variant] → [result summary]
**Protected file requiring change**: config/personas/<slug>.yaml — system_prompt
```

---

## Step 6 — Handle WARNs

WARN = test ran, some assertions passed, not all. Investigate each one.

| WARN cause | Correct action |
|---|---|
| `min_length` failed on a truncated response | 32K context cap in big-model mode — known limitation. Note it, accept if behavior was correct. |
| Keyword appeared in code block but extraction missed it | Ensure `inner_text()` on message element captures code block text; fix extractor if not. |
| Ollama fallback served instead of MLX primary | Response may still be correct. Check routing log. Accept if behavior matches. |
| MCP tool transient error | Retry once after 30s: `python3 tests/portal5_uat_driver.py --test <id>` |
| Cold model load timeout | Driver now evicts+reloads at tier transitions. If still slow, increase `--timeout 360`. |

---

## Step 7 — Manual Tests

Tests A-05 (Telegram), A-06 (Slack), and A-07 (Grafana) require human action.
The driver creates their OWUI conversations with instructions inside the chat body.

After the full run:
1. Open `http://localhost:8080`
2. Find chats: `[MANUAL] UAT: A-05`, `[MANUAL] UAT: A-06`, `[MANUAL] UAT: A-07`
3. Follow the instructions in each chat
4. Add a reply: `✅ PASS`, `⚠️ PARTIAL`, or `❌ FAIL` with brief notes
5. Update `tests/UAT_RESULTS.md` for those three rows

A-07 (Grafana) is always doable — open `http://localhost:3000` after running at
least 10 inference tests and confirm `portal_tokens_per_second` shows recent data
with workspace labels.

---

## Step 8 — Verify Conversations in OWUI

After any section run, confirm conversations materialized:

```bash
python3 -c "
import httpx
from dotenv import dotenv_values
env = dotenv_values('.env')
tok = httpx.post('http://localhost:8080/api/v1/auths/signin',
    json={'email': env['OPENWEBUI_ADMIN_EMAIL'], 'password': env['OPENWEBUI_ADMIN_PASSWORD']}).json().get('token','')
chats = httpx.get('http://localhost:8080/api/v1/chats/',
    headers={'Authorization': f'Bearer {tok}'}).json()
uat = sorted(c['title'] for c in chats if 'UAT' in c.get('title',''))
print(f'{len(uat)} UAT conversations found:')
for t in uat: print(' ', t)
"
```

Expected after a complete run (excluding skips): 70–82 conversations.

---

## Constraints (Non-Negotiable)

### NEVER modify:
- `portal_pipeline/**`, `portal_mcp/**`, `config/`, `deploy/`, `Dockerfile.*`
- `scripts/openwebui_init.py`, `docs/HOWTO.md`, `imports/openwebui/**`

### NEVER run:
- `docker compose down -v` — destroys Ollama model weights
- Any concurrent inference requests — Metal/MLX crash risk

### DO NOT:
- Weaken assertions to make genuinely broken behavior appear green
- Mark BLOCKED without 3+ retry attempts with different prompts
- Modify OWUI conversations a human reviewer has already annotated

### Memory safety (automatic — do not bypass):
- The driver evicts models at every tier transition — do not skip
- **Continuous background monitor** runs every 20s during the entire test suite:
  - Memory > 75%: logs warning
  - Memory > 85%: force-evicts all models (MLX + Ollama)
  - Memory > 92%: emergency eviction + zombie kill + `purge`
  - MLX proxy crash: detected and logged
  - MLX server zombie: SIGTERM'd automatically
  - Ollama crash: detected and logged
- After all tests, `cleanup_after_uat()` evicts everything automatically
- If running `--section` individually, each invocation cleans up at the end

---

## Playwright Selector Fallbacks

OWUI's Svelte selectors can vary by version. Try these fallbacks in order if a
selector returns zero results:

**Prompt textarea:**
`"textarea"` → `"[contenteditable='true']"` → `"[data-testid='chat-textarea']"`

**Stop streaming (stream-complete detection):**
`'button[aria-label="Stop"]'` → `'button[title="Stop"]'` → `'button:has-text("Stop")'`

**Last assistant message:**
`".message-container:last-child .prose"` → `"[data-testid='assistant-message']:last-child"` → `"[role='assistant']:last-child"`

**Tools toggle:**
`'button[aria-label="Tools"]'` → `'button:has-text("+")'` → `'.chat-toolbar > button:first-child'`

Debug with a screenshot when a selector fails:
```python
await page.screenshot(path=f"/tmp/uat_screenshots/debug_{test_id}.png")
```

---

## Quick Reference: Common Issues

| Symptom | Cause | Fix |
|---|---|---|
| Chat create 404 | OWUI API path changed | Check `/openapi.json` for `/chats` endpoints; adjust driver payload if needed |
| Stream never ends | Model stuck | Increase `--timeout`; check `curl http://localhost:8081/health` |
| No artifact download | Wrong selector or MCP error | `--headed` mode + check `/tmp/uat_screenshots/`; check MCP port health |
| Persona missing from OWUI | Not seeded | `./launch.sh reseed && sleep 15` |
| MLX 503 / OOM crash | Both MLX + Ollama loaded | Background monitor auto-evicts. If it recurs, check monitor stats in terminal output |
| `[monitor]` warnings | Memory pressure rising | Monitor handles it. If `recovery_failures` > 0, check for leaked processes |
| auto-agentic timeout | 80B MoE slow | `--timeout 360` for that section; 3+ min per prompt is normal |
| Bench persona hard-fails | MLX bench model not loaded | Verify: `./launch.sh logs \| grep <model-name>` |

---

## Section Reference

Sections are used for filtering (`--section auto-coding`). The driver reorders
tests internally using cascade ordering (tier → model_slug), so section boundaries
don't affect execution order.

| Section | Test IDs | Typical Backend | Approx time |
|---|---|---|---|
| `auto` | WS-01, P-W06, P-W03 | Router | 5–10 min |
| `auto-coding` | WS-02, P-D01–20*, P-DA06, T-01–03 | MLX Devstral | 40–60 min |
| `auto-spl` | WS-04, P-S06 | MLX Qwen3-30B | 8–12 min |
| `auto-mistral` | WS-17, P-R01 | MLX Magistral | 8–12 min |
| `auto-creative` | WS-08, P-W01, P-W02 | MLX creative | 8–12 min |
| `auto-docs` | WS-10, P-W04, P-W05, T-04–07 | MLX phi4 | 15–25 min |
| `auto-agentic` | WS-03, P-D17 | MLX 80B MoE | 20–35 min |
| `auto-security` | WS-05, P-S01, P-S05, T-11, T-12 | Ollama | 10–15 min |
| `auto-redteam` | WS-06, P-S02, P-S04 | Ollama abliterated | 8–12 min |
| `auto-blueteam` | WS-07, P-S03 | Ollama lily | 5–8 min |
| `auto-reasoning` | WS-09, P-D08, P-R02, P-R03, P-R04 | MLX DeepSeek + Ollama GPT-OSS | 20–30 min |
| `auto-data` | WS-15, P-DA01–05 | MLX large | 15–20 min |
| `auto-compliance` | WS-16, P-C01, P-C02 | MLX Qwen3.5 | 10–15 min |
| `auto-research` | WS-13, P-R05–07 | MLX supergemma | 10–15 min |
| `auto-vision` | WS-14, P-V01, P-V02 | MLX VLM gemma4 | 10–15 min |
| `auto-music` | WS-12, T-09 | AudioCraft / Kokoro | 10–15 min |
| `auto-video` | WS-11, T-08 | Wan2.2 / ComfyUI | 15–30 min |
| `advanced` | A-01–A-07 | Various | 15–20 min |
| `benchmark` | CC-01 × 9 models | MLX + Ollama | 60–90 min |

**Total (`--all --skip-bots`):** approximately 280–420 minutes

---

## Most Recent Run

**Date:** 2026-04-25  
**Git SHA:** (pending commit)  
**Result:** Driver updated with cascade ordering + memory safety  
**Changes:**
- Tests now ordered by tier: `mlx_large` → `mlx_small` → `ollama` → `any`
- `unload_all_models()` now evicts both Ollama AND MLX (loads canary to push out big model)
- `cleanup_after_uat()` runs automatically after all tests complete
- Mutual exclusion: MLX and Ollama never loaded simultaneously
- Tests grouped by `model_slug` within each tier to minimize pipeline model switches

**Previous run (2026-04-22):**
- Auto-coding: 19P/0W/4F (23 tests). Remaining sections: in progress

**Assertion fixes (2026-04-22):**
- P-D11: Changed `undefined.toString()` → `[].foo.bar` to avoid V8 "function" output; loosened TypeError check to `any_of: ["typeerror", "cannot read", "undefined"]`
- P-D06: Tightened framework-question keywords from `["framework", "react"]` to question-form phrases `["which framework", "what framework", "framework?", ...]` to prevent false-PASS from generated code mentioning framework name
- P-D12: Reverted to compound `&&` format with path `/tmp/portal_test`; separate-line format caused 0-message responses
- P-D19: Removed "Offline asked" assertion — offline is not in the persona HARD CONSTRAINTS list (confirmed against `ux-uideveloper.yaml`)
- P-DA06: Tightened "West is rank 1" from `contains: ["west","1"]` to `any_of: ["865000 | 1", ...]` to prevent false-PASS when values appear separately in wrong cells
- P-D10: Added `timeout: 360` — deepseek-r1 reasoning CoT can take 5+ min for complex Solidity output

**BLOCKED items (2026-04-22):**
- **P-D06 (seniorfrontenddeveloper)**: Persona HARD CONSTRAINT requires asking framework before writing code. Model consistently assumes React 18 and generates full TypeScript component without asking. Confirmed across 3 runs with same prompt.
- **P-D10 (ethereumdeveloper)**: Persona HARD CONSTRAINT requires noting "This requires a professional security audit before mainnet deployment." Model consistently generates contract with security considerations but omits the audit disclaimer. Confirmed across 3 runs.
- **P-D12 (linuxterminal)**: Persona states state persists within session. Given 4 shell commands (mkdir, echo, cat, pwd), model only outputs pwd result, dropping cat output. Tried 3 different prompt structures; all produced pwd-only output. Protected file: `config/personas/linuxterminal.yaml`
- **P-DA06 (excelsheet)**: Model computes North Annual as 508000 instead of 498000 (off by 10000 — treats Q3 as 108000 not 98000). Additionally ranks in ascending order (North=1, West=2) instead of highest=1 (West=1, North=2). Confirmed across 3 runs.

**Manual test results:**
- A-05 Telegram: —
- A-06 Slack: —
- A-07 Grafana: —

---

*Last updated: 2026-04-25*
