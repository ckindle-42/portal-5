# PORTAL5_UAT_EXECUTE_V2 — Claude Code Execution Prompt

Clone `https://github.com/ckindle-42/portal-5/`. The live system is already running.
`tests/portal5_uat_driver.py` is implemented and the driver's CLI is stable.

This is V2 of the execute prompt. The change from V1: **phased execution by tier, one section group at a time, with appended results and a resume tracker** — not one big `--all` invocation. Phased execution gives you a clean checkpoint between every memory-pressure transition, makes failures easy to bisect, and means an interrupted run can resume without re-running passing tests.

---

## Your Role

You are the **UAT execution agent**. You do not build or modify the driver. You run it phase by phase, monitor between phases, diagnose failures, and produce a clean run log.

**The model behavior is assumed correct.** If an assertion fails, your first assumption is that the keyword list is too strict or phrased differently than the model's output. Investigate before marking FAIL. Only mark FAIL after 3 prompt variants all produce genuinely wrong model behavior.

**Sequential only.** Single-user M4 Mac lab. Never send concurrent inference requests. The driver enforces this via cascade ordering — tests within any invocation run by tier (`mlx_large` → `mlx_small` → `ollama` → `any` → `media_heavy`) with full eviction at tier transitions. MLX and Ollama are never loaded simultaneously.

**Phased.** You do NOT run `--all` in one shot. You run section groups in tier-descending order, one invocation per group, with `--append`. Between phases you check memory and FAIL deltas before continuing. This is the most important V1→V2 change — read the Phase Plan below.

---

## What the UAT Driver Tests

102 tests that produce **real Open WebUI conversations visible in the browser** at `http://localhost:8080`. Each conversation is named, tagged, and reviewable. Artifacts (DOCX, XLSX, PPTX, WAV, MP4) appear as file attachments in the relevant chats.

The driver is NOT the acceptance suite. It validates user-observable behavioral contracts that keyword matching cannot catch: does the persona ask before diagnosing? Does the Excel Sheet compute values, not show formula text? Does the Code Review Assistant scope its review to the diff only?

---

## Phase 0 — Pre-flight (run once, ~3 min)

```bash
git clone https://github.com/ckindle-42/portal-5/ && cd portal-5

# Read the architectural reference. Do this BEFORE running anything.
cat CLAUDE.md
cat KNOWN_LIMITATIONS.md

# Driver present and parses
test -f tests/portal5_uat_driver.py && echo "Driver present" || echo "MISSING — abort"
python3 -m py_compile tests/portal5_uat_driver.py && echo "Syntax OK"
python3 tests/portal5_uat_driver.py --help

# Stack health
./launch.sh status
curl -sf http://localhost:8080/health && echo " OWUI OK"
curl -sf http://localhost:9099/health | python3 -m json.tool
curl -sf http://localhost:8081/health | python3 -m json.tool   # MLX proxy

# OWUI auth + chat API (the driver's critical path)
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
print('Auth + chat API OK')
"

# Playwright Chromium
python3 -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page()
    pg.goto('http://localhost:8080', timeout=10000)
    print('Playwright OK — title:', pg.title())
    b.close()
"

# MCP services (required for tool tests T-01..T-12)
for port in 8912 8913 8914 8916 8917 8918 8919; do
  curl -s --max-time 3 http://localhost:$port/health > /dev/null && echo " :$port OK" || echo " :$port DOWN"
done
```

**Hard stop:** if anything above fails, fix the environment first. Do not run tests against a degraded stack.

### Initialize the run tracker

The tracker is the agent's memory between phases. Without it, an interrupted run cannot resume.

```bash
RUN_TS=$(date -u +%Y%m%dT%H%MZ)
echo "$RUN_TS" > /tmp/uat_run_id

cat > tests/UAT_RUN_LOG.md <<EOF
# UAT Run Log — $RUN_TS

| Phase | Status | Started | Completed | Tests | P/W/F | Notes |
|---|---|---|---|---|---|---|
EOF
```

This file is the source of truth for "where am I in the run." Every phase appends one row when it completes (or marks itself BLOCKED so you can resume past it).

`tests/UAT_RESULTS.md` is the driver's output and accumulates across phases via `--append`. Do NOT delete it between phases; do NOT pass `--append` on the very first phase (smoke) so the file initializes cleanly.

---

## Phase Plan (this is the execution order)

| # | Phase | Why this phase exists | Approx time |
|---|---|---|---|
| 1 | Smoke (auto) | Confirm driver, OWUI, browser, results file all wire up. 4 tests, fast feedback before committing real time. | 5–10 min |
| 2 | mlx_large-heavy sections | Big models loaded while memory is freshest. Catches OOM early. | 60–90 min |
| 3 | mlx_small-heavy coding/reasoning | Bulk of the suite. Models in the 8–18 GB range. | 90–120 min |
| 4 | mlx_small-heavy data/research/creative | Same tier, separated to give a checkpoint mid-suite. | 30–45 min |
| 5 | ollama-only sections | MLX evicted before this phase starts. | 30–45 min |
| 6 | media_heavy (music/video) | Always last among inference. ComfyUI/Wan2.2 footprint. | 30–60 min |
| 7 | benchmark | Long, model-capability-only, can run independently. | 60–90 min |
| 8 | advanced + manual + verify | Manual reviews, OWUI conversation count, result tally. | 15–30 min |

**Pacing rule:** between phases, run the Inter-Phase Check (below) before launching the next. If the check fails — high wired memory, proxy down, FAIL spike — pause, recover, then continue. Do not chain phases blindly.

### How model loading works inside a phase (read this — it changes how you think about phases)

The driver's `sort_tests_cascade` (in `tests/portal5_uat_driver.py`) sorts every selected test by `(workspace_tier, model_slug, test_id)`. This means:

- **Within a single invocation, every test that uses the same persona runs back-to-back with the model loaded once.** No reload between consecutive tests on the same model_slug. Across personas within a tier, the driver still reloads once per model — that is unavoidable on a single-GPU box — but never more than once per model per phase.
- **When you pass multiple sections together (`--section A --section B --section C`), the cascade sort consolidates by model_slug ACROSS those sections.** If `auto-mistral` and `auto-spl` both have tests using mlx_small models, batching them in one invocation runs them grouped by their actual model, not interleaved with re-loads at the section boundary.
- **What this means for the agent:** the section-batching in each phase below is deliberate. Phase 4 batches six sections (auto-data, auto-reasoning, auto-creative, auto-mistral, auto-spl, auto-math, auto) into one invocation precisely because their mlx_small tests share model loads when consolidated. Splitting that into six separate invocations would cause six redundant model load cycles for the same tier — that's the failure mode this design avoids.

### What you must NOT do

- **Do NOT split a phase into per-section invocations** to "watch each section finish." The driver already tells you which test it's running and writes results live; you can `tail -f tests/UAT_RESULTS.md` to monitor. Splitting forces extra model loads.
- **Do NOT use `--test <id>` during a phased run** to "skip ahead" to a specific test. Single-test invocations force a fresh model load just for that test, then the next phase starts cold and reloads again. `--test` is for diagnosis AFTER all phases complete or DURING a paused phase, never as a substitute for `--section`.
- **Do NOT add `--timeout` overrides per-section if tests within the section need different timeouts.** Per-test `timeout` values in the catalog already handle that. Use `--timeout` only at phase level when an entire phase's models need extra time (e.g. agentic 80B MoE).

If you find yourself wanting to break a phase into smaller pieces, that's a sign you don't trust the driver's ordering. Read `sort_tests_cascade` in the driver to confirm what it's doing, then run the phase as designed.

---

## Phase 1 — Smoke

```bash
# First phase initializes UAT_RESULTS.md, so do NOT use --append here.
python3 tests/portal5_uat_driver.py --section auto --headed 2>&1 | tee /tmp/uat_phase1.log
PHASE1_EXIT=$?

# Open http://localhost:8080 in the headed browser and confirm:
#  - Conversations titled "UAT: WS-01 …", "UAT: P-W06 …", "UAT: P-W03 …" appear
#  - Each is renamed [PASS]/[WARN]/[FAIL] after its test completes
#  - tests/UAT_RESULTS.md exists with rows + clickable links
test -s tests/UAT_RESULTS.md && echo "Results file populated" || { echo "ABORT: results file empty"; exit 1; }

# Log the phase
{
  PASS=$(grep -c '| PASS |' tests/UAT_RESULTS.md)
  WARN=$(grep -c '| WARN |' tests/UAT_RESULTS.md)
  FAIL=$(grep -c '| FAIL |' tests/UAT_RESULTS.md)
  echo "| 1. smoke (auto) | DONE | $RUN_TS | $(date -u +%H:%MZ) | 4 | ${PASS}P/${WARN}W/${FAIL}F | exit=$PHASE1_EXIT |"
} >> tests/UAT_RUN_LOG.md
```

If smoke produces zero conversations or a Python error, diagnose before any further phase (see Diagnosis section). Common cause: OWUI seeded models stale → `./launch.sh reseed && sleep 15`.

### → Inter-Phase Check (now and after every phase)

```bash
# Memory state
curl -s http://localhost:8081/health/wired 2>/dev/null | python3 -m json.tool || \
  curl -s http://localhost:8081/health | python3 -m json.tool

# Quick FAIL count
echo "Cumulative: $(grep -c '| PASS |' tests/UAT_RESULTS.md)P / $(grep -c '| WARN |' tests/UAT_RESULTS.md)W / $(grep -c '| FAIL |' tests/UAT_RESULTS.md)F"

# Pipeline alive
curl -sf http://localhost:9099/health > /dev/null && echo "pipeline OK" || echo "PIPELINE DOWN"
```

**Pause criteria** (do not proceed to next phase if any of these are true):
- `wired_gb > 30` — wait 60s, recheck; if still high, request `/unload`: `curl -X POST 'http://localhost:8081/unload?ollama=true'`
- Pipeline `/health` not responding
- Phase exit code non-zero AND no rows added to results file (driver crashed before any test ran)
- FAIL count jumped by more than 30% of the phase's tests (something systemic broke)

If you pause and recover, log it in `tests/UAT_RUN_LOG.md` as a row with Status=PAUSED before retrying the same phase.

---

## Phase 2 — mlx_large-heavy sections (compliance, agentic, vision, research, data, big coding)

These sections contain most of the `mlx_large` tier tests. Run them while memory is freshest.

```bash
python3 tests/portal5_uat_driver.py --append \
  --section auto-compliance \
  --section auto-agentic \
  --section auto-vision \
  --section auto-research \
  2>&1 | tee /tmp/uat_phase2.log
PHASE2_EXIT=$?

{
  TOTAL_NOW=$(grep -cE '\| (PASS|WARN|FAIL) \|' tests/UAT_RESULTS.md)
  PASS=$(grep -c '| PASS |' tests/UAT_RESULTS.md)
  WARN=$(grep -c '| WARN |' tests/UAT_RESULTS.md)
  FAIL=$(grep -c '| FAIL |' tests/UAT_RESULTS.md)
  echo "| 2. mlx_large heavy | DONE | $(date -u +%H:%MZ) | $(date -u +%H:%MZ) | $((TOTAL_NOW-4)) | ${PASS}P/${WARN}W/${FAIL}F (cum) | exit=$PHASE2_EXIT |"
} >> tests/UAT_RUN_LOG.md
```

Run the **Inter-Phase Check** before phase 3.

### Why these four sections and not auto-data?

`auto-data` mixes mlx_large and mlx_small with significant `any`-tier admin work (knowledge base list/create). It runs more reliably in phase 3 alongside the small-tier coding work, where memory is already settled.

### What about `auto-coding` heavy tests (CC-01)?

The `auto-coding` section has 26 tests spanning every tier. It's too large to interleave here. It gets its own phase.

---

## Phase 3 — Bulk coding (auto-coding alone)

26 tests spanning mlx_large, mlx_small, and any tiers. The cascade sort handles tier order internally; within each tier, tests group by model_slug so each coding persona's model loads exactly once. Running auto-coding alone (rather than batching it with phase 4 sections) gives a clean checkpoint between the heavy coding work and the lighter data/reasoning work. Don't sub-split it — that defeats the model-grouping benefit.

```bash
python3 tests/portal5_uat_driver.py --append \
  --section auto-coding \
  2>&1 | tee /tmp/uat_phase3.log
PHASE3_EXIT=$?

{
  PASS=$(grep -c '| PASS |' tests/UAT_RESULTS.md)
  WARN=$(grep -c '| WARN |' tests/UAT_RESULTS.md)
  FAIL=$(grep -c '| FAIL |' tests/UAT_RESULTS.md)
  echo "| 3. auto-coding | DONE | $(date -u +%H:%MZ) | $(date -u +%H:%MZ) | 26 | ${PASS}P/${WARN}W/${FAIL}F (cum) | exit=$PHASE3_EXIT |"
} >> tests/UAT_RUN_LOG.md
```

Run the **Inter-Phase Check** before phase 4.

---

## Phase 4 — Remaining mlx_small/any sections (data, reasoning, creative, mistral, spl, math)

**Why all six in one invocation:** these sections share the mlx_small tier and several share model_slugs. Batching them lets the cascade ordering consolidate by model — every test for a given persona runs back-to-back, then the driver loads the next persona's model exactly once. Running them as six separate invocations would reload some models multiple times.

```bash
python3 tests/portal5_uat_driver.py --append \
  --section auto-data \
  --section auto-reasoning \
  --section auto-creative \
  --section auto-mistral \
  --section auto-spl \
  --section auto-math \
  --section auto \
  2>&1 | tee /tmp/uat_phase4.log
PHASE4_EXIT=$?
# Note: auto was already run in smoke; phase 4 reruns it but --append keeps both rows.
# That's fine — auto is small and acts as a regression spot-check after phases 2-3.

{
  PASS=$(grep -c '| PASS |' tests/UAT_RESULTS.md)
  WARN=$(grep -c '| WARN |' tests/UAT_RESULTS.md)
  FAIL=$(grep -c '| FAIL |' tests/UAT_RESULTS.md)
  echo "| 4. mlx_small bulk | DONE | $(date -u +%H:%MZ) | $(date -u +%H:%MZ) | ~22 | ${PASS}P/${WARN}W/${FAIL}F (cum) | exit=$PHASE4_EXIT |"
} >> tests/UAT_RUN_LOG.md
```

Inter-Phase Check.

---

## Phase 5 — Ollama-only (security, redteam, blueteam, docs)

Before this phase the driver will evict MLX. Wired memory should drop noticeably during the transition.

```bash
python3 tests/portal5_uat_driver.py --append \
  --section auto-security \
  --section auto-redteam \
  --section auto-blueteam \
  --section auto-docs \
  2>&1 | tee /tmp/uat_phase5.log
PHASE5_EXIT=$?

{
  PASS=$(grep -c '| PASS |' tests/UAT_RESULTS.md)
  WARN=$(grep -c '| WARN |' tests/UAT_RESULTS.md)
  FAIL=$(grep -c '| FAIL |' tests/UAT_RESULTS.md)
  echo "| 5. ollama tier | DONE | $(date -u +%H:%MZ) | $(date -u +%H:%MZ) | ~17 | ${PASS}P/${WARN}W/${FAIL}F (cum) | exit=$PHASE5_EXIT |"
} >> tests/UAT_RUN_LOG.md
```

Inter-Phase Check.

---

## Phase 6 — Media-heavy (music, video)

Skip with `--skip-artifacts` if ComfyUI/Wan2.2 aren't running locally.

```bash
python3 tests/portal5_uat_driver.py --append \
  --section auto-music \
  --section auto-video \
  2>&1 | tee /tmp/uat_phase6.log
PHASE6_EXIT=$?

{
  PASS=$(grep -c '| PASS |' tests/UAT_RESULTS.md)
  WARN=$(grep -c '| WARN |' tests/UAT_RESULTS.md)
  FAIL=$(grep -c '| FAIL |' tests/UAT_RESULTS.md)
  echo "| 6. media_heavy | DONE | $(date -u +%H:%MZ) | $(date -u +%H:%MZ) | 4 | ${PASS}P/${WARN}W/${FAIL}F (cum) | exit=$PHASE6_EXIT |"
} >> tests/UAT_RUN_LOG.md
```

Inter-Phase Check.

---

## Phase 7 — Benchmark (CC-01 across 9 models)

Long, model-by-model. The `bench-*` personas all share a system prompt by design — what's measured is raw model capability on a fixed task. Per-model fail rates are the bench's signal, not bugs.

```bash
python3 tests/portal5_uat_driver.py --append \
  --section benchmark \
  --timeout 360 \
  2>&1 | tee /tmp/uat_phase7.log
PHASE7_EXIT=$?

{
  PASS=$(grep -c '| PASS |' tests/UAT_RESULTS.md)
  WARN=$(grep -c '| WARN |' tests/UAT_RESULTS.md)
  FAIL=$(grep -c '| FAIL |' tests/UAT_RESULTS.md)
  echo "| 7. benchmark | DONE | $(date -u +%H:%MZ) | $(date -u +%H:%MZ) | 9 | ${PASS}P/${WARN}W/${FAIL}F (cum) | exit=$PHASE7_EXIT |"
} >> tests/UAT_RUN_LOG.md
```

Inter-Phase Check.

---

## Phase 8 — Advanced + manual + final verify

`advanced` covers the dispatcher paths (Telegram/Slack), cross-session memory, routing validation. `--skip-bots` if Telegram/Slack containers aren't configured.

```bash
python3 tests/portal5_uat_driver.py --append \
  --section advanced \
  --skip-bots \
  2>&1 | tee /tmp/uat_phase8.log
PHASE8_EXIT=$?

{
  PASS=$(grep -c '| PASS |' tests/UAT_RESULTS.md)
  WARN=$(grep -c '| WARN |' tests/UAT_RESULTS.md)
  FAIL=$(grep -c '| FAIL |' tests/UAT_RESULTS.md)
  TOTAL=$((PASS+WARN+FAIL))
  echo "| 8. advanced | DONE | $(date -u +%H:%MZ) | $(date -u +%H:%MZ) | ~7 | ${PASS}P/${WARN}W/${FAIL}F (cum) | exit=$PHASE8_EXIT |"
  echo ""
  echo "## Run summary — $RUN_TS"
  echo ""
  echo "- Total: $TOTAL  PASS: $PASS  WARN: $WARN  FAIL: $FAIL"
  echo "- Pass rate: $((PASS * 100 / TOTAL))%"
} >> tests/UAT_RUN_LOG.md
```

### Manual tests (A-05, A-06, A-07)

The driver creates `[MANUAL] UAT: …` chats with instructions in the chat body. Open OWUI:

1. Open `http://localhost:8080`
2. Find chats: `[MANUAL] UAT: A-05 (Telegram)`, `[MANUAL] UAT: A-06 (Slack)`, `[MANUAL] UAT: A-07 (Grafana)`
3. Follow the instructions in each
4. Append a reply: `✅ PASS`, `⚠️ PARTIAL`, or `❌ FAIL` with brief notes
5. Update `tests/UAT_RESULTS.md` for those three rows by hand (driver doesn't grade manual tests)

A-07 (Grafana) is always doable: open `http://localhost:3000` after running ≥10 inference tests and confirm `portal_tokens_per_second` shows recent data with workspace labels.

### Final verification — OWUI conversations exist

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
print(f'{len(uat)} UAT conversations found')
for t in uat: print(' ', t)
" | head -20
```

Expected after a complete run (excluding skips): 70–82 conversations. Fewer means at least one phase recorded results without OWUI chats — investigate `/tmp/uat_phase*.log` for the affected phase.

---

## Resume Protocol — when a phase is interrupted

The tracker file `tests/UAT_RUN_LOG.md` is the source of truth. It survives Ctrl+C, watchdog restarts, and even Mac reboots (it's committed to disk after each phase).

### To resume after an interruption:

```bash
# 1. Confirm what completed
cat tests/UAT_RUN_LOG.md

# 2. Find the last row marked DONE. The next phase to run is the one AFTER it.
#    Example: if the log shows phases 1-3 DONE and phase 4 has no row, resume at phase 4.

# 3. If a phase row exists with status PAUSED or no Completed timestamp, that phase
#    was interrupted mid-run. Decide:
#      a) Re-run the whole phase (safer, --append is idempotent in the sense that
#         duplicate rows are tolerated and a manual review can flag them)
#      b) Re-run only the failing tests by ID:
#         python3 tests/portal5_uat_driver.py --append --test <ID1> --test <ID2>

# 4. Confirm system state is clean before resuming:
#    - Check wired memory: should be < 12 GB if no model is loaded
curl -s http://localhost:8081/health/wired | python3 -m json.tool
#    - If wired_gb > 12 GB and state == "none", request unload
curl -X POST 'http://localhost:8081/unload?ollama=true' | python3 -m json.tool

# 5. Run the next phase command from the Phase Plan above (always with --append).
#    Append a new row to UAT_RUN_LOG.md when it completes.
```

### Resume after a full system reboot:

The same protocol applies. Stack health is the only extra step:

```bash
./launch.sh status
# If anything is down: ./launch.sh up && sleep 30
```

Then read `tests/UAT_RUN_LOG.md`, identify the last DONE row, and resume from the next phase.

### Re-running a single test (diagnosis only — do NOT use during phased run):

```bash
python3 tests/portal5_uat_driver.py --append --test WS-04
python3 tests/portal5_uat_driver.py --append --test P-D06 --headed
```

These append a single row to `UAT_RESULTS.md`. Use them ONLY for:
- Diagnosing a specific FAIL after all phases complete
- Re-running a small set of tests that need attention before declaring the run final
- Reproducing a behavioral failure with a different prompt during BLOCKED investigation

A single-test invocation forces the driver to load that test's model from cold, run one test, then stop. If you call `--test` mid-phase to "skip ahead," you waste a model load AND the next phase still starts cold. Always finish phases before you start cherry-picking tests.

---

## Calibration Mode (independent of phased run)

Used when assertion keyword lists need a refresh, NOT during a normal pass/fail run. Calibration captures full responses to JSON for human review, then `--emit-signals-from` proposes per-section TF-IDF keyword sets to feed into `tests/quality_signals.py` and the catalog.

```bash
python3 tests/portal5_uat_driver.py --calibrate --calibrate-output calibration.json
# (Edit calibration.json — set review_tag on each entry)
python3 tests/portal5_uat_driver.py --emit-signals-from calibration.json
```

Full workflow: `docs/UAT_CALIBRATION.md`. Use `--section <n>` to calibrate one section without running the full suite.

---

## Diagnosing FAILs

Open `tests/UAT_RESULTS.md`. For each FAIL, click the linked OWUI conversation and read what the model actually said BEFORE touching the assertion.

### Classification table

| What you see in the OWUI conversation | Action |
|---|---|
| Response is correct, just used synonyms | Expand keyword list; add synonyms; change `contains` → `any_of` |
| Response is correct but inside a code block (assertion checks prose) | Verify `inner_text()` includes code block content; fix extraction if needed |
| Behavioral hard constraint violated (e.g. P-D06 coded without asking framework) | See Retry Protocol below |
| Empty response | Check wired memory and proxy state — see Memory State Checks below |
| Artifact test: no file appeared | Check MCP health for the relevant port — see Tool Failures |
| Security test: model refused (abliterated workspace) | Check routing — model may have fallen back to a censored fallback |

### Retry protocol for behavioral failures

```bash
# 1. Read the persona system prompt
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

# 3. If not seeded:
./launch.sh reseed && sleep 15

# 4. Manual reproduction via the pipeline
curl -s -X POST http://localhost:9099/v1/chat/completions \
  -H "Authorization: Bearer $(grep PIPELINE_API_KEY .env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"model": "<model_slug>", "messages": [{"role": "user", "content": "<prompt>"}], "stream": false, "max_tokens": 600}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])"

# 5. Try 2 more prompt phrasings. If all 3 produce wrong behavior → BLOCKED.
```

### Memory state checks (use the proxy, not pkill)

The proxy now exposes graceful unload. Use it; do not `pkill -f mlx-proxy.py`.

```bash
# Wired-memory snapshot
curl -s http://localhost:8081/health/wired | python3 -m json.tool

# Full proxy health
curl -s http://localhost:8081/health | python3 -m json.tool

# Ollama loaded models
curl -s http://localhost:11434/api/ps | python3 -m json.tool

# Graceful unload (proxy handles SIGTERM grace, GPU buffer reclaim, optional Ollama eviction)
curl -X POST 'http://localhost:8081/unload?ollama=true' | python3 -m json.tool

# Pre-warm a model group before re-running its tests
curl -s -X POST http://localhost:9099/v1/chat/completions \
  -H "Authorization: Bearer $(grep PIPELINE_API_KEY .env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"model": "auto-coding", "messages": [{"role":"user","content":"hi"}], "max_tokens":5}'
sleep 30
```

If wired memory stays high (`wired_gb > threshold` per the watchdog config) for several minutes after `/unload`, the watchdog will detect a leak and restart the proxy via `launchctl kickstart -k`. You should not need to intervene; check `~/.portal5/logs/mlx-watchdog.log` if you suspect it didn't fire.

`sudo purge` is no longer part of any recovery path. If a guide tells you to run it, that guide is stale.

### Routing checks (for workspace tests)

```bash
docker logs portal5-pipeline --tail 30 | grep "Routing workspace="
```

### Tool failures (T-01 to T-12)

```bash
# MCP port health
curl -s http://localhost:8913/health  # Documents (T-04..T-07)
curl -s http://localhost:8914/health  # Code sandbox (T-01..T-03)
curl -s http://localhost:8916/health  # TTS (T-09)
curl -s http://localhost:8919/health  # Security (T-11)

# Pipeline tool-call evidence
docker logs portal5-pipeline --tail 100 | grep -i "tool\|mcp\|error"

# Document MCP artifact creation
docker logs portal5-mcp-documents --tail 50
```

### BLOCKED — when and how

Mark BLOCKED only after all of:
1. Three distinct prompt phrasings all produce the same wrong behavior
2. The persona's HARD CONSTRAINTS confirm the expected behavior
3. The fix requires modifying a protected file or a model upgrade

Append to `tests/UAT_RESULTS.md`:

```markdown
## BLOCKED-N: <test name>

**Test ID**: <id>  **Model slug**: <slug>
**Expected**: <quote from persona system_prompt>
**Actual**: <copy model response verbatim>
**Retry 1**: [prompt variant] → [result summary]
**Retry 2**: [prompt variant] → [result summary]
**Retry 3**: [prompt variant] → [result summary]
**Protected file requiring change**: config/personas/<slug>.yaml — system_prompt
```

---

## Handling WARNs

WARN = test ran, some assertions passed but not all (≥50% with no critical fail). Investigate; don't ignore.

| WARN cause | Correct action |
|---|---|
| `min_length` failed on a truncated response | 32K context cap in big-model mode — known limitation. Note it, accept if behavior was correct. |
| Keyword appeared in code block but extraction missed it | Ensure `inner_text()` on message element captures code block text; fix extractor if not. |
| Ollama fallback served instead of MLX primary | Response may still be correct. Check routing log. Accept if behavior matches. |
| MCP tool transient error | Retry once: `python3 tests/portal5_uat_driver.py --append --test <id>` |
| Cold model load timeout | Driver evicts and reloads at tier transitions. If still slow, increase `--timeout 360` for that section. |

---

## Constraints (Non-Negotiable)

### NEVER modify
- `portal_pipeline/**`, `portal_mcp/**`, `config/`, `deploy/`, `Dockerfile.*`
- `scripts/openwebui_init.py`, `docs/HOWTO.md`, `imports/openwebui/**`

### NEVER run
- `docker compose down -v` — destroys Ollama model weights
- Concurrent inference requests — Metal/MLX crash risk
- `pkill -f mlx-proxy.py` — use `POST /unload` and let the watchdog handle proxy lifecycle
- `sudo purge` — no longer part of any recovery path

### DO NOT
- Weaken assertions to make genuinely broken behavior appear green
- Mark BLOCKED without 3+ retry attempts with different prompts
- Modify OWUI conversations a human reviewer has already annotated
- Run `--all` in a single invocation — phased execution is the V2 contract

### Memory safety (handled by the system, not the agent)
The driver evicts at every tier transition. The proxy exposes `POST /unload[?ollama=true]` for explicit graceful eviction. The watchdog detects Metal GPU wired-buffer leaks (`state=none AND wired_gb > threshold` for N consecutive cycles) and recovers via `/unload` first, `launchctl kickstart -k` second. After all phases, `cleanup_after_uat()` runs automatically.

The agent's role is to observe, not to manage processes. Trust the system; if something is genuinely stuck, the watchdog will recover or notify.

### MLX on-demand loading rules
- **MLX loads models on request, not at startup.** A 503 from the proxy means it's idle and healthy — not crashed.
- **Model loading is slow.** A 32B model takes 30–90s; a 70–80B takes 1–3 minutes. Do NOT kill `mlx_lm.server` processes during loading.
- **Zombie = process stuck >5 min with /health dead.** Younger processes are still loading. The watchdog checks process age before killing.
- **Admission control is the authority on memory.** The proxy checks GPU memory before loading and rejects if insufficient. Do not preemptively evict below 90% memory — trust admission control.
- **First request to any MLX model is slow** (cold load). The driver retries on empty responses; second attempt usually succeeds.

---

## Playwright Selector Fallbacks

OWUI's Svelte selectors can vary by version. Try in order if a selector returns zero results:

**Prompt textarea:** `"textarea"` → `"[contenteditable='true']"` → `"[data-testid='chat-textarea']"`

**Stop streaming (stream-complete detection):** `'button[aria-label="Stop"]'` → `'button[title="Stop"]'` → `'button:has-text("Stop")'`

**Last assistant message:** `".message-container:last-child .prose"` → `"[data-testid='assistant-message']:last-child"` → `"[role='assistant']:last-child"`

**Tools toggle:** `'button[aria-label="Tools"]'` → `'button:has-text("+")'` → `'.chat-toolbar > button:first-child'`

Debug with a screenshot when a selector fails:
```python
await page.screenshot(path=f"/tmp/uat_screenshots/debug_{test_id}.png")
```

---

## Quick Reference: Common Issues

| Symptom | Cause | Fix |
|---|---|---|
| Chat create 404 | OWUI API path changed | Check `/openapi.json` for `/chats` endpoints; adjust driver payload |
| Stream never ends | Model stuck | Increase `--timeout`; `curl http://localhost:8081/health` |
| No artifact download | Wrong selector or MCP error | `--headed` + `/tmp/uat_screenshots/`; check MCP port health |
| Persona missing from OWUI | Not seeded | `./launch.sh reseed && sleep 15` |
| MLX 503 / OOM | Both MLX + Ollama loaded | Watchdog auto-evicts. If recurrent, check watchdog log. |
| `[monitor]` warnings | Memory pressure rising | Watchdog handles it. Check `wired_gb` via `/health/wired`. |
| auto-agentic timeout | 80B MoE slow | `--timeout 360`; 3+ min per prompt is normal |
| Bench persona hard-fails | MLX bench model not loaded | `./launch.sh logs \| grep <model-name>` |
| Wired memory stuck high after phase | Metal buffer leak | `curl -X POST 'http://localhost:8081/unload?ollama=true'` |

---

## Section Reference

Sections are filtering inputs (`--section auto-coding`). The driver reorders tests internally using cascade ordering (tier → model_slug), so section boundaries don't constrain execution order within a single invocation.

| Section | Test count | Predominant tier | Phase | Approx time alone |
|---|---|---|---|---|
| `auto` | 4 | mlx_small + any | 1 (smoke), 4 | 5–10 min |
| `auto-coding` | 26 | mlx_large + mlx_small | 3 | 40–60 min |
| `auto-spl` | 2 | mlx_small | 4 | 8–12 min |
| `auto-mistral` | 2 | mlx_small | 4 | 8–12 min |
| `auto-creative` | 3 | mlx_small | 4 | 8–12 min |
| `auto-docs` | 7 | mlx_small + ollama | 5 | 15–25 min |
| `auto-agentic` | 2 | mlx_large | 2 | 20–35 min |
| `auto-security` | 5 | ollama | 5 | 10–15 min |
| `auto-redteam` | 3 | ollama | 5 | 8–12 min |
| `auto-blueteam` | 2 | ollama | 5 | 5–8 min |
| `auto-reasoning` | 5 | mlx_large + mlx_small + ollama | 4 | 20–30 min |
| `auto-data` | 7 | mlx_large + mlx_small + any | 4 | 15–20 min |
| `auto-compliance` | 3 | mlx_large | 2 | 10–15 min |
| `auto-research` | 5 | mlx_large + any | 2 | 10–15 min |
| `auto-vision` | 6 | mlx_large + any | 2 | 10–15 min |
| `auto-music` | 2 | media_heavy | 6 | 10–15 min |
| `auto-video` | 2 | media_heavy | 6 | 15–30 min |
| `auto-math` | 2 | mlx_small | 4 | 5–10 min |
| `advanced` | 7 | ollama + any | 8 | 15–20 min |
| `benchmark` | 9 | mlx_large + mlx_small | 7 | 60–90 min |

**Total run (phases 1–8, `--skip-bots`):** approximately 280–420 minutes.

---

## Run Log Template

`tests/UAT_RUN_LOG.md` is what the agent writes. It accumulates across the run and is the resume reference. Format:

```markdown
# UAT Run Log — <YYYYMMDDTHHMMZ>

| Phase | Status | Started | Completed | Tests | P/W/F | Notes |
|---|---|---|---|---|---|---|
| 1. smoke (auto) | DONE | 14:02Z | 14:08Z | 4 | 4P/0W/0F | exit=0 |
| 2. mlx_large heavy | DONE | 14:09Z | 15:23Z | 16 | 14P/1W/1F (cum: 18P/1W/1F) | exit=0 |
| 3. auto-coding | PAUSED | 15:24Z | — | 12/26 | 9P/1W/2F (partial) | watchdog restart at 15:51Z |
| 3. auto-coding | DONE | 16:08Z | 17:01Z | 26 | resumed via --test for 14 remaining | 22P/2W/2F (cum) |
| ...
```

Status values: `DONE`, `PAUSED`, `BLOCKED`, `SKIPPED`. The agent is responsible for appending a row at the end of each phase or when it pauses.

---

*Last updated: 2026-04-28 (V2 — phased execution, resume tracker, model-grouping reinforcement; aligns with proxy `/unload` + `/health/wired` shipped in 6.0.5)*
