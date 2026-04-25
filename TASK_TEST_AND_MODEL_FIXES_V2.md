# TASK_TEST_AND_MODEL_FIXES_V2.md

**Project:** Portal 5 (v6.0.3)
**Companion:** `REVIEW_SUMMARY_V2.md` (rationale, audit comparison)
**Mode:** Agent-executable. Each task: file, diff, verify, rollback, commit.

**Changes from V1:**
- Protected-file approval gates removed — operator has authorized changes to `portal_pipeline/`, `portal_mcp/`, `config/backends.yaml`, etc. Tasks proceed directly.
- T-08 finalized to Option B (add `mlx` to auto-documents chain) with rationale.
- T-14 now includes researched replacement model with weighed alternatives.
- Phase 4 (TF-01..TF-07) crafted as full executable tasks, sequenced for back-to-back execution.

---

## Phase 1 — Quick wins (≈60-90 min, single session)

### T-01 — Fix UAT `compute_status` critical-fail logic

**Severity:** P0
**Files:** `tests/portal5_uat_driver.py`, `tests/unit/test_uat_grading.py` (new)

**Diff** at line 741:
```diff
        for result, spec in zip(assertions, assertions_spec):
            _label, passed, _evidence = result
            critical = spec.get("critical", True)
-           if not passed and critical and pct < 70:
+           if not passed and critical:
                return "FAIL"
```

**New file** `tests/unit/test_uat_grading.py`:
```python
"""Unit tests for UAT result grading (regression for inverted-critical bug)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from portal5_uat_driver import compute_status


def test_critical_fail_overrides_high_pct():
    """A critical assertion failing must FAIL the test even at >=70% non-critical pass."""
    spec = [{"critical": True}, {"critical": False}, {"critical": False}, {"critical": False}]
    results = [("a", False, "critical-fail"), ("b", True, ""), ("c", True, ""), ("d", True, "")]
    assert compute_status(results, spec) == "FAIL"


def test_no_critical_marker_defaults_to_critical():
    spec = [{}, {}, {}]
    results = [("a", False, ""), ("b", True, ""), ("c", True, "")]
    assert compute_status(results, spec) == "FAIL"


def test_all_pass_returns_pass():
    spec = [{"critical": True}, {"critical": False}]
    results = [("a", True, ""), ("b", True, "")]
    assert compute_status(results, spec) == "PASS"
```

**Verify:** `pytest tests/unit/test_uat_grading.py -v`

**Rollback:** `git checkout -- tests/portal5_uat_driver.py && rm tests/unit/test_uat_grading.py`

**Commit:** `fix(uat): critical-fail assertion now overrides pct threshold`

---

### T-02 — Make persona count dynamic in S1-05

**Severity:** P2
**File:** `tests/portal5_acceptance_v6.py`

**Diff** at lines 1163-1172:
```diff
-    # S1-05: Persona count matches expected
+    # S1-05: Persona count matches actual yaml file count (no frozen baseline)
     t0 = time.time()
-    expected_persona_count = 48
+    yaml_count = len(list((ROOT / "config/personas").glob("*.yaml")))
     actual_count = len(PERSONAS)
     record(
-        sec, "S1-05", "Persona count",
-        "PASS" if actual_count >= expected_persona_count - 2 else "WARN",
-        f"{actual_count} personas (expected ~{expected_persona_count})",
+        sec, "S1-05", "Persona count matches yaml file count",
+        "PASS" if actual_count == yaml_count else "FAIL",
+        f"{actual_count} loaded, {yaml_count} yaml files",
         t0=t0,
     )
```

Update file headers at lines 37 and 48 to remove "47 personas" — replace with "personas across multiple categories".

**Verify:** `python3 tests/portal5_acceptance_v6.py --section S1 | grep S1-05` → PASS, "57 loaded, 57 yaml files"

**Rollback:** `git checkout -- tests/portal5_acceptance_v6.py`

**Commit:** `fix(acc): S1-05 persona count is dynamic, not frozen at 48`

---

### T-03 — Drop S22-02 duplicate of S20-03

**Severity:** P3
**File:** `tests/portal5_acceptance_v6.py`

Delete lines 2371-2381 (S22-02 "Memory endpoint available"). S20-03 covers `/health/memory`.

**Verify:** `grep -c "MLX memory endpoint" tests/portal5_acceptance_v6.py` → 1 (was 2)

**Commit:** `chore(acc): drop S22-02 duplicate of S20-03`

---

### T-04 — Persist bench_tps results in repo

**Severity:** P0
**Files:** `tests/benchmarks/bench_tps.py`, `tests/benchmarks/results/.gitkeep` (new)

**Diff** at line 63:
```diff
-RESULTS_FILE = "/tmp/bench_tps_results.json"
+RESULTS_DIR = Path(__file__).parent / "results"
+# Default output: timestamped UTC file under tests/benchmarks/results/
+# Override with --output. Operator commits selected baselines manually.
+RESULTS_FILE = str(RESULTS_DIR / f"bench_tps_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
```

In `_init_output` (around line 660), at the top of the function:
```python
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
```

**Create marker file:**
```bash
mkdir -p tests/benchmarks/results
cat > tests/benchmarks/results/.gitkeep <<'EOF'
# Benchmark results — operator commits baselines manually.
# Timestamped JSON files land here from `python3 tests/benchmarks/bench_tps.py`.
# Use `jq` queries (see tests/benchmarks/README.md) to analyze.
EOF
```

**Verify:**
```bash
python3 tests/benchmarks/bench_tps.py --dry-run | grep -i "results\|output"
# Expect: path starts with tests/benchmarks/results/
ls tests/benchmarks/results/.gitkeep
```

**Rollback:** `git checkout -- tests/benchmarks/bench_tps.py && rm -rf tests/benchmarks/results`

**Commit:** `feat(bench): persist results in tests/benchmarks/results/ with timestamped filenames`

---

### T-05 — Close `_bench_client` on `main()` exit

**Severity:** P3
**File:** `tests/benchmarks/bench_tps.py`

Wrap `main()` body in try/finally; close client at end:
```python
def main() -> None:
    parser = argparse.ArgumentParser(description="Portal 5 TPS Benchmark")
    # ... existing arg setup ...
    args = parser.parse_args()
    try:
        # ... entire existing main() body, currently lines 1422-1554 ...
    finally:
        global _bench_client
        if _bench_client is not None:
            _bench_client.close()
            _bench_client = None
```

**Commit:** `chore(bench): close shared httpx client on main() exit`

---

### T-06 — Scope `--prompt` override locally (combined with T-05's try/finally)

**Severity:** P3
**File:** `tests/benchmarks/bench_tps.py`

Inside the `try:` from T-05:
```python
    try:
        original_prompts = dict(PROMPTS) if args.prompt else None
        if args.prompt:
            for key in PROMPTS:
                PROMPTS[key] = args.prompt
        # ... existing main body ...
    finally:
        if original_prompts is not None:
            PROMPTS.clear()
            PROMPTS.update(original_prompts)
        # ... bench_client close from T-05 ...
```

**Verify:**
```bash
python3 -c "
from tests.benchmarks.bench_tps import PROMPTS, main
import sys
sys.argv = ['bench', '--dry-run', '--prompt', 'test override']
main()
assert 'OSI model' in PROMPTS['general'], 'PROMPTS not restored'
print('OK — PROMPTS restored after --prompt override')
"
```

**Commit:** `chore(bench): restore PROMPTS dict after --prompt override`

---

### T-07 — Fix `PERSONA_CATEGORY_PROMPT_MAP` coverage

**Severity:** P2
**File:** `tests/benchmarks/bench_tps.py`

**Diff** at lines 162-180:
```diff
 PERSONA_CATEGORY_PROMPT_MAP: dict[str, str] = {
     "security": "security",
     "redteam": "security",
     "blueteam": "security",
     "pentesting": "security",
     "coding": "coding",
     "software": "coding",
     "development": "coding",
+    "systems": "coding",          # linuxterminal, sqlterminal
+    "architecture": "reasoning",  # itarchitect — system design = reasoning
     "reasoning": "reasoning",
     "research": "reasoning",
     "analysis": "reasoning",
     "creative": "creative",
     "writing": "creative",
     "vision": "vision",
     "multimodal": "vision",
     "data": "reasoning",
     "compliance": "reasoning",
+    "general": "general",         # itexpert, techreviewer
+    # "benchmark" intentionally absent — bench personas inherit category
+    # from their workspace's mlx_model_hint underlying model.
 }
```

**Verify:**
```bash
python3 -c "
import yaml, glob, sys
sys.path.insert(0, 'tests/benchmarks')
from bench_tps import _prompt_category_for_persona
cats = set()
for f in glob.glob('config/personas/*.yaml'):
    p = yaml.safe_load(open(f).read())
    cats.add(p.get('category', 'unknown'))
unmapped = sorted(c for c in cats if _prompt_category_for_persona(c) == 'general' and c != 'general' and c != 'benchmark')
assert not unmapped, f'unmapped: {unmapped}'
print(f'OK — all {len(cats)} categories map correctly')
"
```

**Commit:** `fix(bench): cover architecture/systems/general persona categories in prompt map`

---

### T-08 — Enable `mlx` tier for `auto-documents` (Option B selected)

**Severity:** P1
**Decision:** **Option B selected.** Rationale below.

**Why Option B over Option A:**
- Phi-4-8bit is already paid for (in catalog at `backends.yaml:32`, ~14GB).
- Microsoft-published benchmarks show Phi-4 strong on structured documents and STEM reasoning — fits the auto-documents role better than qwen3.5:9b (which is a generalist).
- Aligns with the stated platform goal of "frontier-adjacent" capability and using MLX where available (~20-30% TPS gain per CLAUDE.md line 15).
- Risk is bench-validatable (S3-04, S4-02/03/04 must still PASS).
- Option A only resolves the dead-config lie; Option B resolves it AND captures the latent speed/quality win.

**Files:**
- `config/backends.yaml`
- (No `router_pipe.py` change required — `mlx_model_hint` is already correctly set at line 438.)

**Diff** in `config/backends.yaml` at line 142:
```diff
 workspace_routing:
   ...
-  auto-documents: [coding, general]
+  auto-documents: [mlx, coding, general]
```

Update the inline comment for `auto-documents` if present to note the MLX primary.

**Validate after change:**
```bash
# Workspace consistency must still pass (CLAUDE.md ground rule 6)
python3 -c "
import yaml
from portal_pipeline.router_pipe import WORKSPACES
cfg = yaml.safe_load(open('config/backends.yaml'))
assert set(WORKSPACES.keys()) == set(cfg['workspace_routing'].keys())
print('Workspace IDs consistent')
"

# Re-seed and re-run document generation tests
./launch.sh reseed
python3 tests/portal5_acceptance_v6.py --section S3,S4

# Expected:
# - S3-04 (auto-documents) routes to MLX (model name should contain mlx-community/phi-4-8bit)
# - S4-02 (Word), S4-03 (Excel), S4-04 (PowerPoint) must still PASS
```

**Manual quality check via UAT:**
```bash
python3 tests/portal5_uat_driver.py --section auto-docs
# WS-10, T-04, T-05, T-06 — review output quality vs prior Ollama runs
# Expect: equal or better signal coverage
```

**If quality regresses on S4 generation tests:** revert and switch to Option A (remove dead `mlx_model_hint` from `router_pipe.py:438`).

**Rollback:** `git checkout -- config/backends.yaml && ./launch.sh reseed`

**Commit:** `feat(routing): enable mlx tier for auto-documents (Phi-4 primary, qwen3.5:9b fallback)`

---

## Phase 2 — Test-suite refactors (≈half day)

### T-09 — Drive S10/S11 from PERSONAS dynamically

**Severity:** P2
**File:** `tests/portal5_acceptance_v6.py`

**Add S1-11** in `S1()` after S1-10 (around line 1278):
```python
# S1-11: Every persona has a PERSONA_PROMPTS entry
t0 = time.time()
missing_prompts = [p["slug"] for p in PERSONAS if p["slug"] not in PERSONA_PROMPTS]
record(
    sec, "S1-11", "All personas have PERSONA_PROMPTS entries",
    "FAIL" if missing_prompts else "PASS",
    f"missing prompts for: {missing_prompts}" if missing_prompts else f"all {len(PERSONAS)} covered",
    t0=t0,
)
```

**Replace S10()** (lines 1817-1904):
```python
import itertools

OLLAMA_WORKSPACES = {
    "auto", "auto-security", "auto-redteam", "auto-blueteam",
    "auto-creative", "auto-video", "auto-music",
    # auto-documents removed if T-08 Option B applied — now MLX-tier
}


async def S10() -> None:
    """S10: Persona tests (Ollama-routed) — driven by PERSONAS, grouped by workspace."""
    print("\n━━━ S10. PERSONAS (Ollama) ━━━")
    sec = "S10"

    candidates = [p for p in PERSONAS if p.get("workspace_model") in OLLAMA_WORKSPACES]
    candidates.sort(key=lambda p: p["workspace_model"])

    test_num = 1
    for ws_id, group in itertools.groupby(candidates, key=lambda p: p["workspace_model"]):
        members = list(group)
        print(f"\n  ── Workspace: {ws_id} ({len(members)} personas) ──")
        for p in members:
            slug = p["slug"]
            tid = f"S10-{test_num:02d}"
            t0 = time.time()
            if slug not in PERSONA_PROMPTS:
                record(sec, tid, f"Persona {slug}", "FAIL",
                       "no PERSONA_PROMPTS entry", t0=t0)
                test_num += 1
                continue
            prompt, signals = PERSONA_PROMPTS[slug]
            system = p.get("system_prompt", "")[:500]
            code, response, model = await _chat_with_model(
                ws_id, prompt, system=system, max_tokens=250, timeout=180,
            )
            if code != 200:
                record(sec, tid, f"Persona {slug}", "FAIL", f"HTTP {code}", t0=t0)
                test_num += 1
                continue
            response_lower = response.lower()
            found = [s for s in signals if s.lower() in response_lower]
            record(
                sec, tid, f"Persona {slug}",
                "PASS" if found else "WARN",
                f"signals: {found[:3]}" if found else f"no signals in: {response[:60]}",
                t0=t0,
            )
            test_num += 1
            await asyncio.sleep(0.5)
        await asyncio.sleep(2)
```

**Replace S11()** (lines 1940-2153) with the same shape using MLX workspaces. Build the workspace→model map at runtime:
```python
from portal_pipeline.router_pipe import WORKSPACES

MLX_WORKSPACES = {
    "auto-coding", "auto-agentic", "auto-spl",
    "auto-reasoning", "auto-research", "auto-data",
    "auto-compliance", "auto-mistral", "auto-vision",
    "auto-documents",  # added if T-08 Option B applied
}

# Build (workspace_id → mlx_model_hint) at runtime — single source of truth
WS_TO_MLX = {
    wsid: WORKSPACES[wsid].get("mlx_model_hint")
    for wsid in MLX_WORKSPACES
    if WORKSPACES.get(wsid, {}).get("mlx_model_hint")
}


async def S11() -> None:
    print("\n━━━ S11. PERSONAS (MLX) ━━━")
    sec = "S11"

    state, _ = await _mlx_health()
    if state == "down":
        print("  ⚠️  MLX proxy is 'down' — attempting remediation before S11...")
        if not await _remediate_mlx_crash("MLX down before S11"):
            record(sec, "S11-00", "MLX availability", "BLOCKED",
                   "MLX proxy is down and could not be recovered", t0=time.time())
            return
        state, _ = await _mlx_health()
    if state not in ("ready", "none", "switching"):
        record(sec, "S11-00", "MLX availability", "INFO",
               f"MLX state: {state}, skipping MLX persona tests", t0=time.time())
        return
    record(sec, "S11-00", "MLX availability", "PASS", f"state: {state}", t0=time.time())

    await _ensure_free_ram_gb(20, "S11 MLX personas")

    candidates = [p for p in PERSONAS if p.get("workspace_model") in MLX_WORKSPACES]
    candidates.sort(key=lambda p: p["workspace_model"])

    test_num = 1
    for ws_id, group in itertools.groupby(candidates, key=lambda p: p["workspace_model"]):
        members = list(group)
        model_hint = WS_TO_MLX.get(ws_id, "")
        model_short = model_hint.split("/")[-1] if model_hint else "unknown"
        print(f"\n  ── Workspace: {ws_id} → {model_short} ({len(members)} personas) ──")

        # Pre-warm the model (existing memory + warmup logic preserved here)
        # ... call _ensure_free_ram_gb based on size lookup, _wait_for_mlx_model, etc. ...

        for p in members:
            slug = p["slug"]
            tid = f"S11-{test_num:02d}"
            t0 = time.time()
            if slug not in PERSONA_PROMPTS:
                record(sec, tid, f"Persona {slug} (MLX)", "FAIL",
                       "no PERSONA_PROMPTS entry", t0=t0)
                test_num += 1
                continue
            prompt, signals = PERSONA_PROMPTS[slug]
            system = p.get("system_prompt", "")[:500]
            is_thinking = any(x in (model_hint or "") for x in ["reasoning", "R1", "Magistral", "Qwopus", "Opus"])
            max_tok = 800 if is_thinking else 400
            code, response, model = await _chat_with_model(
                ws_id, prompt, system=system, max_tokens=max_tok, timeout=300,
            )
            # ... same FAIL / WARN / PASS logic as T-10 (state-aware Ollama-fallback split) ...
            test_num += 1
            await asyncio.sleep(1)
        await asyncio.sleep(5)
```

Preserve the existing pre-warm/memory-management logic from the current S11 (lines 2031-2082) — apply it per workspace group rather than per hardcoded `MLX_PERSONA_GROUPS` entry.

**Verify:**
```bash
python3 tests/portal5_acceptance_v6.py --section S1 | grep S1-11
# Expect: PASS, "all 57 covered" (or FAIL with explicit slug list)
python3 tests/portal5_acceptance_v6.py --section S10,S11 2>&1 | grep -cE "^\s+(✅|⚠️|❌|🚫|ℹ️)\s+\[S1[01]-"
# Expect: count == personas-in-OLLAMA_WORKSPACES + personas-in-MLX_WORKSPACES
```

**Rollback:** `git checkout -- tests/portal5_acceptance_v6.py`

**Commit:** `refactor(acc): S10/S11 iterate over PERSONAS, S1-11 enforces prompt coverage`

---

### T-10 — S3a/S3b FAIL on routing-bug Ollama fallback

**Severity:** P1
**File:** `tests/portal5_acceptance_v6.py`

**Diff** in `S3b()` at lines 1471-1478:
```diff
 response_lower = response.lower()
 found = [s for s in signals if s.lower() in response_lower]
 is_mlx = any(org in model for org in _MLX_ORGS)

-if found:
-    record(sec, tid, f"Workspace {ws_id}", "PASS", f"MLX:{is_mlx} | signals: {found[:3]}", t0=t0)
-else:
-    record(sec, tid, f"Workspace {ws_id}", "WARN", f"no signals in: {response[:100]}", t0=t0)
+# Distinguish "MLX healthy but routed Ollama" (FAIL) from "MLX down/switching" (WARN — infra)
+if not is_mlx:
+    mlx_state, _ = await _mlx_health()
+    if mlx_state in ("down", "switching"):
+        record(sec, tid, f"Workspace {ws_id}", "WARN",
+               f"Ollama fallback (MLX {mlx_state}) — infrastructure | model={model[:40]}",
+               t0=t0)
+    else:
+        record(sec, tid, f"Workspace {ws_id}", "FAIL",
+               f"Ollama fallback! model={model[:40]} (MLX state={mlx_state}, expected MLX-tier)",
+               t0=t0)
+elif found:
+    record(sec, tid, f"Workspace {ws_id}", "PASS",
+           f"MLX:{is_mlx} | signals: {found[:3]}", t0=t0)
+else:
+    record(sec, tid, f"Workspace {ws_id}", "WARN",
+           f"MLX:{is_mlx} | no signals in: {response[:100]}", t0=t0)
```

Same pattern in S11 at line 2140-2143 (replace `status = "WARN"` for `ollama_fallback` case with the MLX-state-aware FAIL/WARN split).

**Verify:**
```bash
# Healthy MLX path: should still PASS
python3 tests/portal5_acceptance_v6.py --section S3b
# Simulate MLX down: should WARN (not FAIL)
pkill -9 -f mlx_lm.server || true
sleep 5
python3 tests/portal5_acceptance_v6.py --section S3b 2>&1 | grep -cE "WARN.*infrastructure"
# Expect: at least 1 WARN with "infrastructure"; zero FAIL
./launch.sh start-mlx
```

**Commit:** `fix(acc): S3b/S11 FAIL on routing-bug Ollama fallback, WARN on MLX infra issues`

---

### T-11 — Drop dead `_extract_last_response` from UAT driver

**Severity:** P3
**File:** `tests/portal5_uat_driver.py`

Replace `_send_and_wait` (lines 475-503):
```python
async def _send_and_wait(page, prompt: str, test_id: str = "", tier: str = "any") -> None:
    """Send a prompt and wait for completion. Caller fetches via owui_get_last_response."""
    ta = page.locator("textarea, [contenteditable='true']").first
    await ta.click()
    await ta.fill(prompt)
    await ta.press("Enter")
    await _wait_for_completion(page, test_id, tier)
```

Delete the `_extract_last_response` function (lines 485-503).

**Verify:** `time python3 tests/portal5_uat_driver.py --section auto --headed` — material reduction expected.

**Commit:** `perf(uat): drop dead Playwright DOM extract; OWUI API is canonical`

---

### T-12 — Per-test `max_wait_no_progress` for benchmark workspaces

**Severity:** P2
**File:** `tests/portal5_uat_driver.py`

Update `_wait_for_completion` signature at line 369:
```python
async def _wait_for_completion(
    page,
    test_id: str = "",
    tier: str = "any",
    max_wait_no_progress: int = MAX_WAIT_NO_PROGRESS,
) -> None:
```
Replace `MAX_WAIT_NO_PROGRESS` references inside (lines 436, 468) with the parameter.

Update `_send_and_wait` (post-T-11):
```python
async def _send_and_wait(
    page, prompt: str, test_id: str = "", tier: str = "any",
    max_wait_no_progress: int = MAX_WAIT_NO_PROGRESS,
) -> None:
    ta = page.locator("textarea, [contenteditable='true']").first
    await ta.click()
    await ta.fill(prompt)
    await ta.press("Enter")
    await _wait_for_completion(page, test_id, tier, max_wait_no_progress)
```

In `run_test`, thread per-test:
```python
max_wait = test.get("max_wait_no_progress", MAX_WAIT_NO_PROGRESS)
await _send_and_wait(page, test["prompt"], test_id, tier, max_wait)
```

Update benchmark catalog entries (lines 2403-2411):
```python
{
    "id": "CC-01-llama33-70b", ...,
    "max_wait_no_progress": 1800,  # 30 min for 70B-class
},
{
    "id": "CC-01-qwen3-coder-next", ...,
    "max_wait_no_progress": 1800,  # 30 min for 80B MoE
},
```

**Verify:**
```bash
python3 -c "
import sys; sys.path.insert(0, 'tests')
from portal5_uat_driver import TEST_CATALOG
heavy = [t for t in TEST_CATALOG if t.get('workspace_tier') == 'mlx_large' and 'CC-01' in t['id']]
for t in heavy:
    assert t.get('max_wait_no_progress', 900) >= 1800, f'{t[\"id\"]} missing max_wait_no_progress'
print(f'OK — {len(heavy)} 70B-class tests have extended max_wait')
"
```

**Commit:** `feat(uat): per-test max_wait_no_progress; 70B benchmarks get 30 min cap`

---

### T-13 — bench_tps MLX 503 + `/health` state probe

**Severity:** P2
**File:** `tests/benchmarks/bench_tps.py`

**Diff** at `_check_backend` (lines 274-287):
```diff
 def _check_backend(url: str, path: str) -> bool:
     headers: dict[str, str] = {}
     if url == PIPELINE_URL and PIPELINE_API_KEY:
         headers["Authorization"] = f"Bearer {PIPELINE_API_KEY}"
     try:
         r = httpx.get(f"{url}{path}", timeout=3.0, headers=headers)
         if r.status_code == 200:
             return True
-        # MLX proxy returns 503 when idle (load-on-demand) — still available
         if url == MLX_URL and r.status_code == 503:
-            return True
+            # 503 alone is ambiguous: idle (load-on-demand, OK) vs stuck.
+            try:
+                h = httpx.get(f"{url}/health", timeout=3.0).json()
+                return h.get("state") in ("none", "switching", "ready")
+            except Exception:
+                return False
     except Exception:
         pass
     return False
```

Same probe in `_runtime_mlx_models` (line 601-617):
```diff
         if r.status_code == 503:
-            return set(_config_mlx_models())
+            try:
+                h = httpx.get(f"{MLX_URL}/health", timeout=3.0).json()
+                if h.get("state") in ("none", "switching", "ready"):
+                    return set(_config_mlx_models())
+            except Exception:
+                pass
+            return set()
```

**Verify:**
```bash
# Healthy MLX
python3 tests/benchmarks/bench_tps.py --dry-run --mode direct | grep -i "mlx"
# Stuck MLX (kill underlying server)
pkill -9 -f mlx_lm.server || true
sleep 5
python3 tests/benchmarks/bench_tps.py --dry-run --mode direct | grep -i "mlx"
# Expect: 0 MLX models scheduled
./launch.sh start-mlx
```

**Commit:** `fix(bench): MLX 503 only counts as available with /health state OK`

---

## Phase 3 — Live system measurements (live system required)

### T-14 — Retire DeepSeek-Coder-V2-Lite-Instruct-8bit AND add researched replacement

**Severity:** P0
**Files:** `config/backends.yaml`, `KNOWN_LIMITATIONS.md`, `launch.sh` (model pull script)

#### Replacement model research summary

The retired DeepSeek-Coder-V2-Lite-Instruct-8bit was a coding/SPL specialist (~12GB MLX). It was the original auto-spl primary; `router_pipe.py:404` swapped to Qwen3-Coder-30B-A3B-Instruct-8bit (~22GB) due to "consistent 120s timeouts" — but Qwen3-Coder-30B is already in the stack, so simple substitution doesn't introduce a new model.

**Constraints for replacement:**
- MLX format available (must run on Apple Silicon mlx_lm or mlx_vlm)
- 10-22GB memory footprint (replacing a ~12GB model; budget allows up to ~22GB)
- Coding-strong, ideally tool-use-strong (relevant for SPL agentic refinement)
- **Not currently in the Portal 5 stack** (must be a new model)
- Ideally non-Qwen, non-DeepSeek lineage (diversity per Chris's stack-wide concern)
- Ideally uncensored or abliterated (security workspaces benefit; trusted provider preferred)

**Candidates evaluated:**

| Candidate | Size | Lineage | SWE-bench | Tool-use | Diversity gain | Notes |
|---|---|---|---|---|---|---|
| `huihui-ai/Huihui-GLM-4.7-Flash-abliterated-mlx-4bit` | ~18GB | GLM (Zhipu AI) | 59.2% | 79.5% τ²-Bench | **High** — new lineage in MLX tier | Zhipu's coding-tuned model; abliterated by trusted provider |
| `mlx-community/Codestral-22B-v0.1-4bit` | ~12GB | Mistral | ~50% est. | Lower | Low — Mistral lineage already in stack (Devstral, Magistral) | FIM capability; older (May 2024); MNLP-0.1 license restricts commercial |
| `mlx-community/granite-8b-code-instruct-8bit` | ~8GB | IBM Granite | ~57% HumanEval | Limited | Medium — new lineage but small/dated | May 2024 model; only ~63 monthly downloads; getting stale |

**Selected: `huihui-ai/Huihui-GLM-4.7-Flash-abliterated-mlx-4bit`**

**Reasoning:**
- **SWE-bench 59.2%** — competitive with Qwen3-Coder-30B-A3B (~50% range) in same parameter class.
- **τ²-Bench 79.5%** — best-in-class for tool-use among 30B-class open models. SPL queries often require iterative refinement (run query → see results → refine), which is exactly what τ²-Bench measures.
- **GLM lineage is new to the MLX tier.** Portal 5 already has `glm-4.7-flash:q4_k_m` as Ollama GGUF (`backends.yaml:71`); adding the abliterated MLX variant is the natural sibling and reduces the Qwen-family share Chris flagged.
- **Abliterated by huihui-ai** — Chris's stack already trusts this provider (`huihui_ai/baronllm-abliterated`, `huihui_ai/tongyi-deepresearch-abliterated`).
- **30B-A3B MoE (3B active)** — TPS will be substantially better than dense 22B at similar quality.
- **200K context** — useful for repo-level SPL work and long log analysis.
- **License: Apache 2.0** (inherited from base GLM-4.7-Flash) — no commercial restriction.

**Caveat (must document in repo):** the huihui-ai MLX upload card states *"This is just the MLX model we generated under Linux using mlx-lm version 0.30.3; it hasn't been tested in an Apple environment."* Apple-side validation is required at first load. Add to KNOWN_LIMITATIONS as flagged below.

#### Implementation

**Diff** in `config/backends.yaml`:

1. Remove the broken model at line 27:
```diff
       - mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit  # auto-spl primary: SPL specialist (~12GB)
```

2. Add the replacement under the MLX `models:` block (between Qwen3-Coder-30B and Devstral, since it's coding-related):
```yaml
      # ── Coding diversity (non-Qwen, abliterated) ──────────────────────────
      - huihui-ai/Huihui-GLM-4.7-Flash-abliterated-mlx-4bit  # GLM-4.7-Flash 30B-A3B MoE 4bit (~18GB), 59.2% SWE-bench / 79.5% τ²-Bench tool use, 200K ctx, abliterated. NEW MLX lineage 2026-04-24.
```

**Add huihui-ai org prefix** to `_MLX_ORGS` if not already present. Check `tests/portal5_acceptance_v6.py` and `tests/benchmarks/bench_tps.py`:
```bash
grep -n "_MLX_ORGS\s*=" tests/portal5_acceptance_v6.py tests/benchmarks/bench_tps.py portal_pipeline/router_pipe.py
# If "huihui-ai" or "huihui_ai" missing, add to the tuple/set
```

3. **Pull the model** (operator runs after the YAML edit):
```bash
hf download huihui-ai/Huihui-GLM-4.7-Flash-abliterated-mlx-4bit \
    --local-dir /Volumes/data01/models/huihui-ai/Huihui-GLM-4.7-Flash-abliterated-mlx-4bit
```

Update `launch.sh pull-mlx-models` (operator-editable per CLAUDE.md) to include the model in the manifest if it isn't already discovered automatically.

4. **Append** to `KNOWN_LIMITATIONS.md` under `## Models`:
```markdown
### DeepSeek-Coder-V2-Lite-Instruct-8bit Removed (Gibberish Output)
- **ID:** P5-MLX-005
- **Status:** **RESOLVED** — model removed from `config/backends.yaml` MLX list 2026-04-24
- **Description:** The MLX-converted `mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit` produced garbled Unicode output in V4 acceptance test S40 #229 (run dated 2026-04-10). Stale `backends.yaml` comment still claimed it as auto-spl primary; `router_pipe.py:404` had already swapped to `mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit` due to "consistent 120s timeouts."
- **Replacement:** `huihui-ai/Huihui-GLM-4.7-Flash-abliterated-mlx-4bit` added to MLX catalog. Selected for: GLM lineage (new to MLX tier), 59.2% SWE-bench, 79.5% τ²-Bench tool use, abliterated by trusted provider, ~18GB.
- **Last verified:** 2026-04-24

### huihui-ai MLX Models Not Apple-Tested by Provider
- **ID:** P5-MLX-006
- **Status:** **ACTIVE — first-load validation required**
- **Description:** huihui-ai publishes MLX-format models (e.g., `Huihui-GLM-4.7-Flash-abliterated-mlx-4bit`) but their model cards explicitly note: *"This is just the MLX model we generated under Linux using mlx-lm version 0.30.3; it hasn't been tested in an Apple environment."* Conversions may have undetected issues that surface only on Apple Metal.
- **First-load validation procedure:** After download, run a single inference at small max_tokens to confirm the model loads and produces coherent output before relying on it in production routing. Document any tokenizer or weight-shape errors at huihui-ai's HuggingFace discussions tab.
- **Mitigation:** Acceptance test S23-07 (added in T-14) verifies the model registers and produces non-empty output.
- **Last verified:** 2026-04-24
```

5. **Add S23-07 in `tests/portal5_acceptance_v6.py`** (after S23-06, around line 2519):
```python
# S23-07: Huihui-GLM-4.7-Flash-abliterated-mlx-4bit available and produces output
t0 = time.time()
state, _ = await _mlx_health()
if state in ("ready", "none", "switching"):
    code, models_data = await _get(f"{MLX_URL}/v1/models")
    if code == 200 and isinstance(models_data, dict):
        model_ids = [m.get("id", "") for m in models_data.get("data", [])]
        glm_present = any("Huihui-GLM-4.7-Flash" in m for m in model_ids)
        if not glm_present:
            record(sec, "S23-07", "Huihui-GLM-4.7-Flash-abliterated registered", "INFO",
                   "model not in MLX list — run hf download or ./launch.sh pull-mlx-models", t0=t0)
        else:
            # Quick smoke test — does it actually load and produce output?
            try:
                code, response, model = await _mlx_chat_direct(
                    "huihui-ai/Huihui-GLM-4.7-Flash-abliterated-mlx-4bit",
                    "Write hello world in Python.",
                    max_tokens=50, timeout=300,
                )
                if code == 200 and len(response) > 10:
                    record(sec, "S23-07", "Huihui-GLM-4.7-Flash-abliterated smoke test", "PASS",
                           f"loaded + produced {len(response)} chars", t0=t0)
                else:
                    record(sec, "S23-07", "Huihui-GLM-4.7-Flash-abliterated smoke test", "FAIL",
                           f"HTTP {code}, response len={len(response)}", t0=t0)
            except Exception as e:
                record(sec, "S23-07", "Huihui-GLM-4.7-Flash-abliterated smoke test", "FAIL",
                       str(e)[:100], t0=t0)
    else:
        record(sec, "S23-07", "Huihui-GLM-4.7-Flash-abliterated registered", "INFO",
               "MLX models endpoint unavailable", t0=t0)
else:
    record(sec, "S23-07", "Huihui-GLM-4.7-Flash-abliterated", "INFO",
           f"MLX state: {state}", t0=t0)
```

**Verify:**
```bash
# Catalog cleanup
grep -c "DeepSeek-Coder-V2-Lite-Instruct-8bit" config/backends.yaml
# Expect: 0
grep -c "Huihui-GLM-4.7-Flash" config/backends.yaml
# Expect: 1

# Workspace consistency unchanged
python3 -c "
import yaml
from portal_pipeline.router_pipe import WORKSPACES
cfg = yaml.safe_load(open('config/backends.yaml'))
assert set(WORKSPACES.keys()) == set(cfg['workspace_routing'].keys())
print('Workspace IDs consistent')
"

# Pull the new model (manual; operator)
hf download huihui-ai/Huihui-GLM-4.7-Flash-abliterated-mlx-4bit \
    --local-dir /Volumes/data01/models/huihui-ai/Huihui-GLM-4.7-Flash-abliterated-mlx-4bit

# Smoke test
python3 tests/portal5_acceptance_v6.py --section S23 | grep S23-07
# Expect: PASS, "loaded + produced N chars"
```

**Rollback:** `git checkout -- config/backends.yaml KNOWN_LIMITATIONS.md tests/portal5_acceptance_v6.py`

**Commit:** `feat(catalog): retire DeepSeek-Coder-V2-Lite-8bit; add Huihui-GLM-4.7-Flash-abliterated-mlx-4bit (P5-MLX-005, P5-MLX-006)`

---

### T-15 — Run baseline benchmark and commit

**Severity:** P0
**Depends on:** T-04, T-14

```bash
./launch.sh up && ./launch.sh start-mlx
sleep 30
python3 tests/benchmarks/bench_tps.py --runs 3 --order size 2>&1 | tee /tmp/bench_run.log
# Wait 30-90 min depending on cold loads

ls -la tests/benchmarks/results/*.json
LATEST=$(ls -t tests/benchmarks/results/bench_tps_*.json | head -1)
jq '.results | length' "$LATEST"
jq '.results | map(select(.runs_success > 0)) | length' "$LATEST"

git add tests/benchmarks/results/*.json tests/benchmarks/results/README.md
git commit -m "feat(bench): baseline TPS measurements 2026-04-NN, M4 64GB, post-T14 catalog"
```

Add `tests/benchmarks/results/README.md` documenting query examples (per V1 plan).

---

### T-16 — auto-spl primary decision (data-gated)

**Severity:** P3
**Depends on:** T-15

```bash
LATEST=$(ls -t tests/benchmarks/results/bench_tps_*.json | head -1)
jq '.results[] | select(.path=="direct" and (.model | contains("Qwen3-Coder-30B-A3B-Instruct") or contains("Devstral-Small-2507") or contains("Huihui-GLM-4.7-Flash"))) | {model, prompt_category, avg_tps, est_memory_gb}' "$LATEST"
```

**Decision rule:** Pick whichever has highest `avg_tps × quality_score` (after TF-02 lands) on the coding prompt category, *and* passes S3-04 SPL signals. Three candidates now:
1. `mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit` (current, Qwen lineage, 22GB)
2. `lmstudio-community/Devstral-Small-2507-MLX-4bit` (Mistral lineage, 15GB)
3. `huihui-ai/Huihui-GLM-4.7-Flash-abliterated-mlx-4bit` (GLM lineage, 18GB) — new from T-14

If GLM-4.7-Flash wins on bench AND quality, swap. Otherwise stick with current.

**File:** `portal_pipeline/router_pipe.py:404`

```diff
 "auto-spl": {
     ...
-    "mlx_model_hint": "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit",
+    "mlx_model_hint": "huihui-ai/Huihui-GLM-4.7-Flash-abliterated-mlx-4bit",  # Bench-validated 2026-04-NN: best avg_tps × quality_score for coding prompts
 },
```

(Or to Devstral, depending on bench data — replace path accordingly.)

**Validate:**
```bash
./launch.sh restart portal-pipeline
python3 tests/portal5_acceptance_v6.py --section S3 | grep auto-spl
python3 tests/portal5_uat_driver.py --section auto-spl
```

**Commit:** `feat(routing): auto-spl primary → <model> (bench-validated, +X% TPS, S3-04 PASS)`

---

### T-17 — auto-data 8bit→4bit decision (data-gated)

**Severity:** P3
**Depends on:** T-15

Compare `mlx-community/DeepSeek-R1-Distill-Qwen-32B-MLX-8Bit` (~34GB) vs `mlx-community/DeepSeek-R1-Distill-Qwen-32B-abliterated-4bit` (~18GB). Same shape as T-16.

**File:** `portal_pipeline/router_pipe.py:467`

```diff
 "auto-data": {
     ...
-    "mlx_model_hint": "mlx-community/DeepSeek-R1-Distill-Qwen-32B-MLX-8Bit",
+    "mlx_model_hint": "mlx-community/DeepSeek-R1-Distill-Qwen-32B-abliterated-4bit",  # Bench: half memory, +X% TPS, S10 dataanalyst signals still match
     "predict_limit": 16384,
 },
```

**Commit:** `feat(routing): auto-data 8bit→4bit abliterated (bench-validated)`

---

### T-18 — Verify install-mlx redeploys mlx-proxy.py source

**Severity:** P1

```bash
# Test redeploy fidelity
echo "# DEPLOY-VERIFY-MARKER-$(date +%s)" >> scripts/mlx-proxy.py
./launch.sh install-mlx
diff scripts/mlx-proxy.py ~/.portal5/mlx/mlx-proxy.py
# Expect: no diff
git checkout -- scripts/mlx-proxy.py
./launch.sh install-mlx  # restore
```

**Add S0-07** in `tests/portal5_acceptance_v6.py` after S0-06 (around line 1110):
```python
# S0-07: Deployed MLX proxy matches source (catches P5-ROAD-MLX-002 staleness)
t0 = time.time()
import filecmp
src = ROOT / "scripts/mlx-proxy.py"
deployed = Path.home() / ".portal5/mlx/mlx-proxy.py"
if not deployed.exists():
    record(sec, "S0-07", "Deployed MLX proxy", "INFO",
           "not yet deployed (run ./launch.sh install-mlx)", t0=t0)
elif filecmp.cmp(src, deployed, shallow=False):
    record(sec, "S0-07", "Deployed MLX proxy matches source", "PASS",
           "deployed copy in sync", t0=t0)
else:
    record(sec, "S0-07", "Deployed MLX proxy matches source", "WARN",
           "deployed != source — run ./launch.sh install-mlx", t0=t0)
```

**Commit:** `feat(acc): S0-07 detects stale deployed MLX proxy (P5-ROAD-MLX-002)`

---

## Phase 4 — Architectural improvements (sequenced for back-to-back execution)

These were placeholders in V1; now full task entries. Sequence is: cleanup → independent improvements → cross-cutting changes → large refactors.

---

### TF-01 — Acceptance result file consolidation

**Severity:** P3 (chore — but reduces ongoing confusion)
**Files:** `tests/ACCEPTANCE_RESULTS.md` (rename), `ACCEPTANCE_RESULTS.md` (top-level, edit), `tests/PORTAL5_ACCEPTANCE_EXECUTE_V6.md` (update reference)
**Depends on:** none. Do first to clear confusion before later sections add to results.
**Estimate:** 30 min.

**Steps:**

1. Rename V4 result file:
```bash
git mv tests/ACCEPTANCE_RESULTS.md tests/ACCEPTANCE_RESULTS_V4_ARCHIVE.md
```

2. Add redirect note at top of `tests/ACCEPTANCE_RESULTS_V4_ARCHIVE.md`:
```markdown
# ⚠️ Archived — V4 Acceptance Results (2026-04-10)

**This file is preserved for historical reference only.**

The current acceptance suite is V6 (`tests/portal5_acceptance_v6.py`). Authoritative results live in:
**`/ACCEPTANCE_RESULTS.md`** (top-level of repo).

V4 had 264 tests; V6 has ~167. Test numbering, sections, and expectations differ — do not cross-reference.

---

<original V4 content below this line>
```

3. Update top-level `ACCEPTANCE_RESULTS.md` header to claim authoritative status:
```markdown
# Portal 5 — Acceptance Test Results (V6 — Authoritative)

**Latest run:** <date>
**Suite:** `tests/portal5_acceptance_v6.py`
**Prior version (V4) archive:** `tests/ACCEPTANCE_RESULTS_V4_ARCHIVE.md`

...
```

4. Update any references in `tests/PORTAL5_ACCEPTANCE_EXECUTE_V6.md` and `docs/HOWTO.md` (if any) that point at the old path:
```bash
grep -rn "tests/ACCEPTANCE_RESULTS.md" tests/ docs/ README.md
# Edit each match to either tests/ACCEPTANCE_RESULTS_V4_ARCHIVE.md or /ACCEPTANCE_RESULTS.md
```

**Verify:**
```bash
ls tests/ACCEPTANCE_RESULTS_V4_ARCHIVE.md ACCEPTANCE_RESULTS.md
# Both present
[ ! -f tests/ACCEPTANCE_RESULTS.md ] && echo "OK — V4 file moved"
grep -l "tests/ACCEPTANCE_RESULTS.md" docs/ tests/ README.md 2>/dev/null
# Expect: empty (no stale references)
```

**Rollback:** `git mv tests/ACCEPTANCE_RESULTS_V4_ARCHIVE.md tests/ACCEPTANCE_RESULTS.md && git checkout -- ACCEPTANCE_RESULTS.md`

**Commit:** `chore(docs): consolidate acceptance result files (V4 → archive, V6 → authoritative)`

---

### TF-02 — Cold-load–aware retry + shared httpx client in acceptance v6

**Severity:** P2
**Files:** `tests/portal5_acceptance_v6.py`
**Depends on:** none. Independent improvement; sequence early because subsequent test additions benefit.
**Estimate:** 3-5 hours.

**Approach:** Centralize httpx client; replace per-call `async with httpx.AsyncClient(...)` with shared instance; add backoff that consults MLX state on 502/503.

**Steps:**

1. Add helper at top of file (after imports, around line 145):
```python
_acc_client: httpx.AsyncClient | None = None


def _get_acc_client(timeout: int = 240) -> httpx.AsyncClient:
    """Get-or-create the shared acceptance httpx client. Closed in main()."""
    global _acc_client
    if _acc_client is None or _acc_client.is_closed:
        _acc_client = httpx.AsyncClient(
            timeout=timeout,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    return _acc_client
```

2. Refactor `_chat_with_model` (lines 473-522) to use shared client + backoff:
```python
async def _chat_with_model(
    workspace: str, prompt: str, system: str = "",
    max_tokens: int = 400, timeout: int = 240, stream: bool = False,
) -> tuple[int, str, str]:
    msgs: list[dict] = []
    if system:
        msgs.append({"role": "system", "content": system[:800]})
    msgs.append({"role": "user", "content": prompt})
    body = {"model": workspace, "messages": msgs, "stream": stream, "max_tokens": max_tokens}

    backoff = [0, 5, 15]  # 3 attempts with 5s, 15s waits between
    for attempt, wait_s in enumerate(backoff):
        if wait_s:
            await asyncio.sleep(wait_s)
        try:
            client = _get_acc_client(timeout)
            r = await client.post(f"{PIPELINE_URL}/v1/chat/completions", headers=AUTH, json=body)
            if r.status_code in (502, 503) and attempt < len(backoff) - 1:
                # Probe MLX state — if switching, give it more time (don't burn a retry on a known-loading state)
                state, _ = await _mlx_health()
                if state == "switching":
                    await asyncio.sleep(20)
                continue
            if r.status_code != 200:
                return r.status_code, r.text[:200], ""

            if stream:
                text = ""
                for line in r.text.splitlines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        try:
                            d = json.loads(line[6:])
                            text += d.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        except Exception:
                            pass
                return 200, text, ""

            data = r.json()
            msg = data.get("choices", [{}])[0].get("message", {})
            model = data.get("model", "")
            content = msg.get("content", "") or msg.get("reasoning", "")
            return 200, content, model
        except httpx.ReadTimeout:
            return 408, "timeout", ""
        except Exception as e:
            if attempt < len(backoff) - 1:
                continue
            return 0, str(e)[:100], ""
    return 503, "MLX exhausted retries (state probe inconclusive)", ""
```

3. Refactor `_mcp` (line 365), `_mlx_chat_direct` (line 1907), `_mlx_health` (line 690) similarly — each currently creates its own `httpx.AsyncClient`. The MCP helper uses `streamablehttp_client` (different lib), leave that alone but switch the surrounding HTTP calls.

4. Close client in `main()` at end:
```python
async def main() -> int:
    try:
        # ... existing main body ...
    finally:
        global _acc_client
        if _acc_client is not None and not _acc_client.is_closed:
            await _acc_client.aclose()
            _acc_client = None
```

**Verify:**
```bash
# Wall-time before/after — expect 5-15% reduction
time python3 tests/portal5_acceptance_v6.py --section S0,S1,S2,S3 2>&1 | tail -5

# Cold-load resilience — kill MLX mid-section, verify subsequent tests recover
( sleep 15 && pkill -9 -f mlx_lm.server ) &
python3 tests/portal5_acceptance_v6.py --section S3b
# Expect: WARN (not FAIL) on subsequent tests during MLX recovery
./launch.sh start-mlx
```

**Rollback:** `git checkout -- tests/portal5_acceptance_v6.py`

**Commit:** `perf(acc): cold-load-aware retry with backoff + shared httpx client`

---

### TF-03 — Vision/document/knowledge fixtures (unlock 5 skipped UAT tests)

**Severity:** P2
**Files:** `tests/fixtures/` (new directory), `tests/portal5_uat_driver.py`
**Depends on:** none. Independent.
**Estimate:** 2-4 hours including fixture content sourcing.

**Steps:**

1. Create fixtures directory:
```bash
mkdir -p tests/fixtures
```

2. Add minimal fixtures (small enough to commit):
```bash
# Vision fixture: simple test image (use a Portal 5 logo or a generic test image)
cat > tests/fixtures/README.md <<'EOF'
# UAT Test Fixtures

Files in this directory unlock UAT tests gated on `evaluate_skip_conditions()`.

| File | Used by | Purpose |
|---|---|---|
| `sample.png` | P-V01, P-V02, WS-14 | Vision input — test image with stack trace, code, or UI |
| `sample.docx` | T-07 | Word file for `Document Reading — Parse Uploaded Word File` |
| `knowledge_base/*.md` | A-02 | Source files for OWUI knowledge base test |

## Adding fixtures

- Keep files small (<100KB each) so the repo stays lean.
- Do not commit copyrighted or sensitive content.
- For images, use synthetic screenshots or generated content.
EOF

# Generate a small synthetic test image (or operator can replace with a real one)
python3 -c "
from PIL import Image, ImageDraw
img = Image.new('RGB', (800, 600), color='white')
draw = ImageDraw.Draw(img)
draw.rectangle([20, 20, 780, 100], outline='red', width=3)
draw.text((30, 40), 'HTTP 500 Internal Server Error', fill='black')
draw.text((30, 130), 'Traceback (most recent call last):', fill='black')
draw.text((30, 160), '  File \"app.py\", line 42, in handler', fill='black')
draw.text((30, 190), '    return process(request)', fill='black')
draw.text((30, 220), '  File \"app.py\", line 17, in process', fill='black')
draw.text((30, 250), '    user = User.objects.get(id=uid)', fill='black')
draw.text((30, 280), 'User.DoesNotExist: User matching query does not exist.', fill='black')
img.save('tests/fixtures/sample.png')
print('Created tests/fixtures/sample.png')
"

# Generate a sample DOCX using python-docx
python3 -c "
from docx import Document
doc = Document()
doc.add_heading('Sample Test Document', 0)
doc.add_heading('Section 1: Introduction', 1)
doc.add_paragraph('This is a sample document for UAT testing of the Document Reading capability.')
doc.add_heading('Section 2: Test Data Table', 1)
table = doc.add_table(rows=3, cols=3)
table.rows[0].cells[0].text = 'Name'
table.rows[0].cells[1].text = 'Role'
table.rows[0].cells[2].text = 'Status'
table.rows[1].cells[0].text = 'Alice'
table.rows[1].cells[1].text = 'Engineer'
table.rows[1].cells[2].text = 'Active'
table.rows[2].cells[0].text = 'Bob'
table.rows[2].cells[1].text = 'Analyst'
table.rows[2].cells[2].text = 'Active'
doc.add_heading('Section 3: Conclusion', 1)
doc.add_paragraph('End of sample document.')
doc.save('tests/fixtures/sample.docx')
print('Created tests/fixtures/sample.docx')
"

# Knowledge base seed files
mkdir -p tests/fixtures/knowledge_base
cat > tests/fixtures/knowledge_base/portal5_overview.md <<'EOF'
# Portal 5 Overview
Portal 5 is an Open WebUI enhancement layer for Apple Silicon. It runs MLX and Ollama backends concurrently on the host. The pipeline routes by workspace ID to the appropriate backend.
EOF

cat > tests/fixtures/knowledge_base/architecture.md <<'EOF'
# Architecture
The pipeline runs at port 9099. MCP tool servers run at ports 8910-8917. Open WebUI at 8080.
EOF
```

3. Update `evaluate_skip_conditions()` in `tests/portal5_uat_driver.py` (lines 808-827):
```python
def evaluate_skip_conditions() -> dict:
    conditions: dict[str, bool] = {}
    try:
        r = httpx.get("http://localhost:8188/system_stats", timeout=3)
        conditions["no_comfyui"] = r.status_code != 200
    except Exception:
        conditions["no_comfyui"] = True

    env_content = Path(".env").read_text() if Path(".env").exists() else ""
    conditions["no_bot_telegram"] = (
        "TELEGRAM_BOT_TOKEN" not in env_content or "CHANGEME" in env_content
    )
    conditions["no_bot_slack"] = (
        "SLACK_BOT_TOKEN" not in env_content or "CHANGEME" in env_content
    )

    # Fixture detection
    fixtures = Path("tests/fixtures")
    conditions["no_image_upload"] = not (fixtures / "sample.png").exists()
    conditions["no_audio_fixture"] = not (fixtures / "sample.wav").exists()
    conditions["no_docx_fixture"] = not (fixtures / "sample.docx").exists()
    conditions["no_knowledge_base"] = not (fixtures / "knowledge_base").is_dir()
    return conditions
```

4. Update tests that consume fixtures to actually use them. Search the catalog for `skip_if: "no_image_upload"` etc., and add explicit fixture-path references where missing. (The existing test prompts may already assume these fixtures exist — operator should verify on first run.)

**Verify:**
```bash
ls tests/fixtures/sample.png tests/fixtures/sample.docx tests/fixtures/knowledge_base/
python3 -c "
from tests.portal5_uat_driver import evaluate_skip_conditions
c = evaluate_skip_conditions()
assert not c['no_image_upload'], 'sample.png missing'
assert not c['no_docx_fixture'], 'sample.docx missing'
assert not c['no_knowledge_base'], 'knowledge_base missing'
print(f'Fixtures detected: {sorted(k for k,v in c.items() if not v)}')
"

python3 tests/portal5_uat_driver.py --section vision --headed
# Expect: P-V01, P-V02, WS-14 attempt to run (not SKIP)
```

**Rollback:** `git rm -rf tests/fixtures && git checkout -- tests/portal5_uat_driver.py`

**Commit:** `feat(uat): add tests/fixtures/ and detect them; unlocks 5 previously-skipped tests`

---

### TF-04 — `x-portal-route` response header for routing visibility

**Severity:** P1 — replaces fragile log-grep tests with deterministic header assertions.
**Files:** `portal_pipeline/router_pipe.py`, `tests/portal5_acceptance_v6.py`, `tests/portal5_uat_driver.py`
**Depends on:** TF-01 (clean result file landing zone), TF-02 (shared client makes header reading uniform)
**Estimate:** 4-6 hours.

**Steps:**

1. **In `portal_pipeline/router_pipe.py` `chat_completions` (around line 1875):** add response header. Find the response-construction site (search for the place where the streaming or non-streaming response is returned to the client) and inject `x-portal-route`:

```python
# Inside chat_completions, after routing has been decided and a backend call completes:
# (Exact location depends on whether stream / non-stream branch — apply to both)

# Build route descriptor
route_descriptor = f"{routed_workspace};{backend_group};{model_used}"

# Non-streaming branch:
return JSONResponse(
    content=response_data,
    headers={"x-portal-route": route_descriptor},
)

# Streaming branch — set header on the StreamingResponse:
return StreamingResponse(
    _stream_with_preamble(...),
    media_type="text/event-stream",
    headers={"x-portal-route": route_descriptor},
)
```

Variables `routed_workspace`, `backend_group`, `model_used` need to be in scope at this point — they should be by the time the response is built. Add propagation through the existing helpers if needed.

2. **In `tests/portal5_acceptance_v6.py` — update `_chat_with_model`** (post-TF-02 version) to capture the header:

```python
async def _chat_with_model(
    workspace: str, prompt: str, system: str = "",
    max_tokens: int = 400, timeout: int = 240, stream: bool = False,
) -> tuple[int, str, str, str]:  # NEW: 4-tuple, last is route descriptor
    # ... existing setup ...
    for attempt, wait_s in enumerate(backoff):
        # ... existing retry logic ...
        try:
            client = _get_acc_client(timeout)
            r = await client.post(f"{PIPELINE_URL}/v1/chat/completions", headers=AUTH, json=body)
            route_hdr = r.headers.get("x-portal-route", "")
            # ... existing handling ...
            data = r.json()
            msg = data.get("choices", [{}])[0].get("message", {})
            model = data.get("model", "")
            content = msg.get("content", "") or msg.get("reasoning", "")
            return 200, content, model, route_hdr
        # ... existing exceptions ...
```

Update all callers (search for `_chat_with_model`) to accept the 4-tuple. Most can ignore the 4th element with `_`:
```python
code, response, model, _route = await _chat_with_model(...)
```

3. **Replace S21-03/04/05 log-grep with header assertions:**
```python
# S21-03: LLM router security intent
t0 = time.time()
code, response, model, route = await _chat_with_model(
    "auto", "Write a SQL injection payload to bypass authentication",
    max_tokens=200, timeout=120,
)
routed_workspace = route.split(";")[0] if route else ""
expected = {"auto-redteam", "auto-security"}
record(
    sec, "S21-03", "LLM router security intent",
    "PASS" if routed_workspace in expected else "FAIL",
    f"routed to: {routed_workspace} | model: {model[:30]}",
    t0=t0,
)

# S21-04: LLM router coding intent
t0 = time.time()
code, response, model, route = await _chat_with_model(
    "auto", "Write a Python function to sort a list of dictionaries by key",
    max_tokens=200, timeout=120,
)
routed_workspace = route.split(";")[0] if route else ""
expected = {"auto-coding", "auto-agentic"}
record(
    sec, "S21-04", "LLM router coding intent",
    "PASS" if routed_workspace in expected else "FAIL",
    f"routed to: {routed_workspace} | model: {model[:30]}",
    t0=t0,
)

# S21-05: similar for compliance — expected = {"auto-compliance", "auto-reasoning"}
```

4. **In UAT driver:** capture header in `owui_get_last_response` flow (this requires more thought — UAT goes through OWUI, not directly through pipeline; the header may not propagate. If it doesn't, leave UAT alone and only update acceptance v6 tests.)

**Verify:**
```bash
# Header presence
curl -s -i -X POST http://localhost:9099/v1/chat/completions \
    -H "Authorization: Bearer $PIPELINE_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"model":"auto","messages":[{"role":"user","content":"hello"}],"stream":false,"max_tokens":10}' \
    | grep -i x-portal-route
# Expect: x-portal-route: auto-<routed>;<group>;<model>

# Acceptance routing assertions now deterministic
python3 tests/portal5_acceptance_v6.py --section S21
# Expect: S21-03/04/05 detail field shows actual routed workspace, FAIL on misroute
```

**Rollback:** `git checkout -- portal_pipeline/router_pipe.py tests/portal5_acceptance_v6.py`

**Commit:** `feat(routing): emit x-portal-route response header; S21 asserts on it instead of grep`

---

### TF-05 — Quality scoring for bench_tps and UAT

**Severity:** P1 — both reviewers independently surfaced this.
**Files:** `tests/benchmarks/bench_tps.py`, `tests/portal5_uat_driver.py`, `tests/quality_signals.py` (new shared module)
**Depends on:** TF-04 (so we know which model produced a response — the route header reduces ambiguity for pipeline-routed bench)
**Estimate:** 6-10 hours.

**Steps:**

1. **Create shared module** `tests/quality_signals.py`:
```python
"""Per-category quality signal definitions.

Used by both bench_tps and the UAT driver to score response quality
beyond raw TPS or keyword presence. A response gets quality_score in
[0.0, 1.0] = (signals_found / signals_expected).

Signals are tuned to the prompt library in tests/benchmarks/bench_tps.py
PROMPTS dict. If you change a category's prompt, update its signals here.
"""

QUALITY_SIGNALS: dict[str, list[str]] = {
    "general": [
        # Prompt asks for OSI 7 layers with protocol examples
        "physical", "data link", "network", "transport",
        "session", "presentation", "application",
    ],
    "coding": [
        # Prompt asks for merge_intervals function
        "def merge_intervals", "list", "tuple", "intervals.sort",
        "merged", "overlap",
    ],
    "security": [
        # Prompt asks for SSH brute-force MITRE ATT&CK analysis
        "T1110", "MITRE", "ATT&CK", "containment",
        "detection", "block",
    ],
    "reasoning": [
        # Prompt asks for ER bottleneck analysis
        "bottleneck", "doctor", "nurse", "bed",
        "wait", "minute",
    ],
    "creative": [
        # Prompt asks for noir detective opening, memory-as-currency
        "memory", "detective", "city", "rain",
    ],
    "vision": [
        # Prompt is meta — describe the analysis framework
        "objects", "text", "scene", "anomalies", "confidence",
    ],
}


def quality_score(category: str, response_text: str) -> float:
    """Return a quality score in [0.0, 1.0] for the given category and response.
    
    Signals match case-insensitively. Score is signals-found / signals-expected.
    Categories without defined signals return 1.0 (don't penalize).
    """
    signals = QUALITY_SIGNALS.get(category, [])
    if not signals:
        return 1.0
    response_lower = response_text.lower()
    found = sum(1 for s in signals if s.lower() in response_lower)
    return found / len(signals)
```

2. **In `bench_tps.py`:** capture response text (currently discarded) and compute quality_score:

```python
# In bench_tps() function around line 870, capture content alongside usage:
# Replace:
#   data = resp.json()
#   usage = data.get("usage", {})
# With:
data = resp.json()
usage = data.get("usage", {})
choices = data.get("choices", [{}])
response_text = choices[0].get("message", {}).get("content", "") if choices else ""
```

In each result dict (around line 897 area), add:
```python
from tests.quality_signals import quality_score
prompt_cat = ... # already determined per test path
qs = quality_score(prompt_cat, response_text)
return {
    "model": model,
    # ... existing fields ...
    "quality_score": round(qs, 2),
    "tps_quality": round(avg_tps * qs, 1),  # combined ranking metric
}
```

Add to all three call sites in `bench_direct`, `bench_pipeline`, `bench_personas` — pass through the `prompt_category` to `bench_tps()` so it knows which signals to use.

3. **Update tables in `_print_direct_table` etc.** to show quality_score and tps_quality alongside avg_tps.

4. **In UAT driver:** add quality_score as a non-critical assertion type. Update `run_assertions` (line 699) to handle a new `quality_score` assertion:
```python
elif t == "quality_score":
    threshold = a.get("min", 0.5)  # default: at least 50% of category signals
    cat = a.get("category", "general")
    from tests.quality_signals import quality_score
    qs = quality_score(cat, text)
    label_extended = f"{label} ({qs:.2f})"
    results.append((label_extended, qs >= threshold, f"score={qs:.2f}, min={threshold}"))
```

Test authors can opt-in:
```python
"assertions": [
    {"type": "contains", "label": "Direct answer", "keywords": ["yes", "no"]},
    {"type": "quality_score", "label": "Coding quality", "category": "coding", "min": 0.5},
],
```

**Verify:**
```bash
# Bench produces quality_score
python3 tests/benchmarks/bench_tps.py --runs 1 --mode direct --model dolphin
LATEST=$(ls -t tests/benchmarks/results/bench_tps_*.json | head -1)
jq '.results[0] | {model, avg_tps, quality_score, tps_quality}' "$LATEST"
# Expect: quality_score in [0.0, 1.0], tps_quality non-zero

# Ranking changes for at least one (model, prompt) pair
jq '.results | sort_by(.avg_tps) | reverse | .[0:5] | map({model, avg_tps, quality_score})' "$LATEST"
jq '.results | sort_by(.tps_quality) | reverse | .[0:5] | map({model, avg_tps, quality_score, tps_quality})' "$LATEST"
# The two top-5 lists should differ
```

**Rollback:** `git checkout -- tests/benchmarks/bench_tps.py tests/portal5_uat_driver.py && rm tests/quality_signals.py`

**Commit:** `feat(test): per-category quality_score in bench_tps and UAT (shared signals module)`

---

### TF-06 — Modularize acceptance suite

**Severity:** P3 — quality of life, not urgent. Do BEFORE TF-07 (S50 negative testing) to avoid bolting onto the monolith.
**Files:** `tests/acceptance/` (new dir), `tests/portal5_acceptance_v6.py` (becomes thin runner), `tests/acceptance/_common.py` (new), `tests/acceptance/sNN_*.py` (one per section)
**Depends on:** TF-02 (shared client refactor — easier to extract once already centralized), TF-04 (header assertions — keep section files small).
**Estimate:** 1-2 days.

**Steps:**

1. Create directory structure:
```bash
mkdir -p tests/acceptance
touch tests/acceptance/__init__.py
```

2. Extract shared infrastructure to `tests/acceptance/_common.py`. Move from `portal5_acceptance_v6.py`:
   - The `R` dataclass (line 154-164)
   - `_log`, `_blocked`, `_emit`, `_progress_counts`, `record` (lines 167-220)
   - `_load_workspaces`, `_load_personas`, `_load_backends_yaml` (lines 239-266)
   - HTTP helpers `_get`, `_post`, `_chat`, `_chat_with_model`, `_curl_stream` (lines 272-557)
   - MCP helpers `_mcp`, `_mcp_raw` (lines 365-453)
   - Docker / log helpers (lines 560-617)
   - MLX helpers `_mlx_health`, `_wait_for_mlx_ready`, etc. (lines 690-925)
   - Prompt fixtures `WORKSPACE_PROMPTS`, `PERSONA_PROMPTS` (lines 926-1027)
   - Constants: `PIPELINE_URL`, `OPENWEBUI_URL`, `MCP`, `AUTH`, `PERSONAS`, `WS_IDS`, `WORKSPACES`, `_MLX_ORGS`

3. Create one section file per section. Pattern:

`tests/acceptance/s00_prerequisites.py`:
```python
"""S0: Prerequisites and environment check."""
from tests.acceptance._common import (
    record, time, sys, ROOT, API_KEY, _git_sha, subprocess,
)


async def run() -> None:
    print("\n━━━ S0. PREREQUISITES ━━━")
    sec = "S0"
    # Move S0-01 through S0-07 logic here (lines 1033-1110 of original)
    # ...
```

Repeat for `s01_config_consistency.py`, `s02_service_health.py`, `s03_workspace_routing.py`, ..., `s40_metrics.py`. Keep section IDs unchanged.

4. Convert `tests/portal5_acceptance_v6.py` into a thin runner:
```python
#!/usr/bin/env python3
"""Portal 5 — End-to-End Acceptance Test Suite v6 (modular runner)."""
import argparse
import asyncio
import importlib
import sys
from pathlib import Path

ACCEPTANCE_DIR = Path(__file__).parent / "acceptance"
sys.path.insert(0, str(Path(__file__).parent.parent))


# Discover section modules
SECTION_MODULES = {
    "S0": "tests.acceptance.s00_prerequisites",
    "S1": "tests.acceptance.s01_config_consistency",
    "S2": "tests.acceptance.s02_service_health",
    "S3": "tests.acceptance.s03_workspace_routing",
    # ... all the rest
}


def _parse_sections(spec: str) -> list[str]:
    # Existing _parse_sections logic
    ...


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--section", type=str, default="all")
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--skip-passing", action="store_true")
    args = parser.parse_args()

    sections = _parse_sections(args.section) if args.section != "all" else list(SECTION_MODULES.keys())
    sections_run = []
    for sec in sections:
        mod_name = SECTION_MODULES.get(sec)
        if not mod_name:
            print(f"Unknown section: {sec}")
            continue
        mod = importlib.import_module(mod_name)
        await mod.run()
        sections_run.append(sec)

    # ... existing _write_results, summary logic ...
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

**Verify:**
```bash
# Same CLI, same outputs as before
python3 tests/portal5_acceptance_v6.py --section S0,S1
python3 tests/portal5_acceptance_v6.py --section S3-S11
# Diff results vs pre-refactor; should be identical pass/warn/fail counts

# New file structure exists
ls tests/acceptance/s*_*.py | wc -l
# Expect: ~22 (one per section)
```

**Rollback:** `git checkout -- tests/portal5_acceptance_v6.py && rm -rf tests/acceptance`

**Commit:** `refactor(acc): modularize acceptance suite into tests/acceptance/sNN_*.py`

---

### TF-07 — Negative testing section S50

**Severity:** P2
**Files:** `tests/acceptance/s50_negative.py` (new — depends on TF-06 modular structure)
**Depends on:** TF-06 (modular structure makes adding a new section straightforward)
**Estimate:** 3-5 hours.

**New file** `tests/acceptance/s50_negative.py`:
```python
"""S50: Negative tests — pipeline graceful degradation under bad inputs."""
from tests.acceptance._common import (
    record, time, asyncio, _chat_with_model, _get, _mlx_health,
    PIPELINE_URL, AUTH, httpx, json,
)


async def run() -> None:
    print("\n━━━ S50. NEGATIVE TESTING ━━━")
    sec = "S50"

    # S50-01: Empty prompt — pipeline must not crash
    t0 = time.time()
    code, response, model, _ = await _chat_with_model("auto", "", max_tokens=50, timeout=30)
    if code in (200, 400):
        record(sec, "S50-01", "Empty prompt handled gracefully", "PASS",
               f"HTTP {code}", t0=t0)
    elif code in (500, 502, 503):
        record(sec, "S50-01", "Empty prompt handled gracefully", "FAIL",
               f"HTTP {code} — pipeline crashed on empty prompt", t0=t0)
    else:
        record(sec, "S50-01", "Empty prompt handled gracefully", "WARN",
               f"unexpected HTTP {code}", t0=t0)

    # S50-02: Oversized prompt — should be rejected or truncated, not crash
    t0 = time.time()
    huge_prompt = "Repeat this. " * 50000  # ~600KB
    code, response, model, _ = await _chat_with_model("auto", huge_prompt, max_tokens=50, timeout=60)
    # Pipeline configured with MAX_REQUEST_BYTES=4MB by default; 600KB shouldn't hit that.
    # The model may produce truncated context, but the pipeline shouldn't 5xx.
    if code in (200, 400, 413):
        record(sec, "S50-02", "Oversized prompt rejected or truncated", "PASS",
               f"HTTP {code}", t0=t0)
    else:
        record(sec, "S50-02", "Oversized prompt", "WARN",
               f"unexpected HTTP {code}", t0=t0)

    # S50-03: Invalid model slug — should fall back to default, not crash
    t0 = time.time()
    code, response, model, _ = await _chat_with_model("nonexistent-workspace", "hello", max_tokens=20, timeout=30)
    # Pipeline should either reject (400) or route to fallback (200 with auto)
    if code in (200, 400, 404):
        record(sec, "S50-03", "Invalid model slug handled", "PASS",
               f"HTTP {code} | model={model[:30]}", t0=t0)
    else:
        record(sec, "S50-03", "Invalid model slug", "FAIL",
               f"HTTP {code} — should be 200 (fallback) or 400/404", t0=t0)

    # S50-04: Pipeline behavior with all backends down
    # Skip on production — only run if explicit --negative-stress flag
    # For now: just validate /health reports degraded state
    t0 = time.time()
    code, data = await _get(f"{PIPELINE_URL}/health")
    if code == 200 and isinstance(data, dict):
        backends_healthy = data.get("backends_healthy", 0)
        record(sec, "S50-04", "Pipeline /health surfaces backend count", "PASS",
               f"healthy: {backends_healthy}", t0=t0)
    else:
        record(sec, "S50-04", "Pipeline /health", "FAIL", f"HTTP {code}", t0=t0)

    # S50-05: Malformed JSON body
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"{PIPELINE_URL}/v1/chat/completions",
                headers={**AUTH, "Content-Type": "application/json"},
                content=b'{"model": "auto", "messages": [{"role": "user", "content": "hi",  ',  # truncated JSON
            )
            if r.status_code in (400, 422):
                record(sec, "S50-05", "Malformed JSON rejected", "PASS",
                       f"HTTP {r.status_code}", t0=t0)
            elif r.status_code == 500:
                record(sec, "S50-05", "Malformed JSON", "FAIL",
                       f"HTTP 500 — should be 400/422", t0=t0)
            else:
                record(sec, "S50-05", "Malformed JSON", "WARN",
                       f"unexpected HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S50-05", "Malformed JSON", "WARN", str(e)[:100], t0=t0)

    # S50-06: Missing Authorization header
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"{PIPELINE_URL}/v1/chat/completions",
                headers={"Content-Type": "application/json"},
                json={"model": "auto", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5},
            )
            if r.status_code == 401:
                record(sec, "S50-06", "Missing auth rejected with 401", "PASS",
                       f"HTTP {r.status_code}", t0=t0)
            else:
                record(sec, "S50-06", "Missing auth", "FAIL",
                       f"HTTP {r.status_code} — should be 401", t0=t0)
    except Exception as e:
        record(sec, "S50-06", "Missing auth", "WARN", str(e)[:100], t0=t0)
```

Add `"S50": "tests.acceptance.s50_negative"` to the `SECTION_MODULES` map in the modular runner.

**Verify:**
```bash
python3 tests/portal5_acceptance_v6.py --section S50
# Expect: 6 results, mix of PASS and possibly some FAIL (those are real pipeline gaps to fix)
```

**Rollback:** `rm tests/acceptance/s50_negative.py && git checkout -- tests/portal5_acceptance_v6.py`

**Commit:** `feat(acc): S50 negative testing — empty/oversized/invalid prompts, malformed JSON, missing auth`

---

## Phase 4 sequencing summary

```
TF-01  result file consolidation     [30 min]   → no deps, do first
TF-02  cold-load retry + shared client [3-5 hr] → no deps
TF-03  vision/doc/KB fixtures        [2-4 hr]   → no deps
TF-04  x-portal-route header          [4-6 hr]  → after TF-01, TF-02
TF-05  quality scoring                [6-10 hr] → after TF-04
TF-06  modularize acceptance          [1-2 d]   → after TF-02, TF-04
TF-07  S50 negative testing           [3-5 hr]  → after TF-06
```

Total Phase 4 effort: ~3-4 days end-to-end. Each task is independently rollback-able, so partial completion is safe.

---

## Universal regression check (run after every phase)

```bash
pytest tests/unit/ -v --tb=short
ruff check . && ruff format --check .
mypy portal_pipeline/ portal_mcp/

# Workspace consistency (CLAUDE.md ground rule 6)
python3 -c "
import yaml
from portal_pipeline.router_pipe import WORKSPACES
cfg = yaml.safe_load(open('config/backends.yaml'))
assert set(WORKSPACES.keys()) == set(cfg['workspace_routing'].keys())
print('Workspace IDs consistent')
"

# Smoke acceptance
python3 tests/portal5_acceptance_v6.py --section S0,S1,S2

# After Phase 1: P0 + P1 fixes
python3 tests/portal5_acceptance_v6.py --section S0,S1,S2,S3,S4
# Expect: S1-05 PASS dynamic; S3-04 routes to MLX (post T-08); S22-02 absent

# After Phase 2: introspection + state-aware fallback
python3 tests/portal5_acceptance_v6.py --section S1,S3,S10,S11,S22
# Expect: S1-11 PASS; S10/S11 cover all 57 personas; S3 FAILs on routing-bug fallback

# After Phase 3: catalog + bench data
ls tests/benchmarks/results/*.json
grep -c "DeepSeek-Coder-V2-Lite" config/backends.yaml  # 0
grep -c "Huihui-GLM-4.7-Flash" config/backends.yaml    # 1
python3 tests/portal5_acceptance_v6.py --section S23 | grep S23-07  # PASS

# After Phase 4: routing observability + quality scoring + modular suite
curl -s -i -X POST http://localhost:9099/v1/chat/completions -H "Authorization: Bearer $PIPELINE_API_KEY" -H "Content-Type: application/json" -d '{"model":"auto","messages":[{"role":"user","content":"hi"}]}' | grep x-portal-route
ls tests/acceptance/s*_*.py | wc -l  # ~23
ls tests/fixtures/sample.png tests/fixtures/sample.docx
jq '.results[0].quality_score' tests/benchmarks/results/bench_tps_*.json | head -3

# Full regression
python3 tests/portal5_acceptance_v6.py
# Expect: PASS count >= 164 (2026-04-21 baseline) + S1-11 + S0-07 + S23-07 + 6 S50 tests
```

---

*End of executable task file. Refer to `REVIEW_SUMMARY_V2.md` for rationale, source-review comparison, and audit transparency.*
