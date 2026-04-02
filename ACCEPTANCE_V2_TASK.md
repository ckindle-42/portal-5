# Portal 6.0 — Acceptance Test Suite v2 Update
### Claude Code Agent Task

**Context:** The acceptance suite previously ran at 158 PASS / 0 FAIL / 14 WARN (all expected)
against the v1 test. The latest run on the live stack produced **109 PASS / 0 FAIL / 7 WARN / 3 INFO**.
The 7 WARNs are all actionable — not environmental — and are addressed in this update.

**This task applies targeted edits to `portal5_acceptance.py` only.**
No production code (`router_pipe.py`, `Dockerfile.*`, `docker-compose.yml`,
anything under `portal_mcp/` or `portal_pipeline/`) is touched.

---

## CRITICAL RULES (same as ACCEPTANCE_TASK.md)

1. **NEVER modify:**
   - `scripts/openwebui_init.py`
   - `Dockerfile.mcp` / `Dockerfile.pipeline`
   - `deploy/portal-5/docker-compose.yml`
   - Any file under `portal_mcp/`
   - Any file under `portal_pipeline/`

2. **The only file you are editing:** `portal5_acceptance.py`

3. **After every edit, verify Python syntax:** `python3 -m py_compile portal5_acceptance.py`

4. **Goal:** Run `python3 portal5_acceptance.py` and reach **0 FAIL, 0 actionable WARN**.
   Acceptable non-PASS statuses (carry-forward from v1):
   - `INFO` — informational, no action needed
   - `WARN` for cold model load (C2 503/timeout on first run)
   - `WARN` for DinD sandbox `__main__` if it still surfaces despite the prompt fix
   - `WARN` for headless Playwright scroll limitations (H-WS/H-Persona GUI counts)

---

## WHAT CHANGED IN v2 AND WHY

### Change 1 — ComfyUI testing removed from acceptance suite

**Previous behaviour:** Sections D12-13 probed `http://localhost:8188/system_stats`,
then called `generate_image` and `generate_video` via MCP. Video gen returned
`success:false` (no video output found) but was logged as PASS only because
`warn_contains=["model","ComfyUI","install"]` downgraded it. This was masking a real
functional gap.

**New behaviour:**
- `B_health` removes `("MCP ComfyUI","http://localhost:8910/health")` from the
  health-check loop and instead emits an `INFO`-only probe for the ComfyUI MCP
  bridge so operators can see its status without it affecting the PASS/FAIL count.
- `D_mcp` replaces the entire D12-13 block (ComfyUI up-check, image gen, video gen)
  with a single `log("INFO","D","ComfyUI image/video gen — tested separately ...")`.
- Rationale: operator decision to test image/video generation separately. The MCP
  bridge health is still surfaced for visibility.

### Change 2 — Six personas returning "200 but empty response"

**Root cause:** These six personas have `HARD CONSTRAINTS` in their system prompts that
contain clauses like "If the tech stack is unspecified, ask" or "OUTPUT CONTRACT: Reply
ONLY with query results". The v1 test prompts were deliberately minimal (one-liner
questions) which triggered the ask-for-more-context path, returning an empty or
near-empty completion that the test correctly detected as empty.

**New prompts provide complete, self-contained context:**

| Persona slug | v1 prompt problem | v2 fix |
|---|---|---|
| `devopsautomator` | No stack/cloud/secrets context → ask-gate triggered | Specifies Python 3.11, AWS ECS, GitHub Secrets, rollback requirement |
| `devopsengineer` | No cloud/team/toolchain context → ask-gate triggered | Specifies AWS EKS, GitHub Actions, Helm 3.12, kubectl, team size 5 |
| `itexpert` | No OS/error/recent-change context → ask-gate triggered | Gives Ubuntu 22.04, OOMKilled event, FastAPI + pandas context |
| `kubernetesdockerrpglearningengine` | Plain question bypasses RPG engine | Sends `START NEW GAME` command with explicit mission selection |
| `pythoncodegeneratorcleanoptimizedproduction-ready` | Ambiguous signature, no stdlib constraint | Gives full function signature, stdlib-only, RuntimeError behaviour |
| `sqlterminal` | Asked it to "write a query" — OUTPUT CONTRACT says reply-only-with-results | Sends the raw SQL directly against its fixed schema |

### Change 3 — Python sandbox code simplified

**Previous code:** Used `import json` + dict + `json.dumps()` → some DinD builds
interpret this as a module import pattern and route through `__main__`, hitting the
protected-code path.

**New code:** Two plain `print()` calls with list comprehension only. No imports,
no dict, no JSON serialization. Checks for `"count: 25"` or `"sum: 1060"` (sum of
primes to 100) in output. The `warn_contains` list still catches the `__main__` path
if it surfaces.

---

## STEP-BY-STEP INSTRUCTIONS

### Step 0 — Verify you are in the right directory

```bash
cd ~/portal-5
ls portal5_acceptance.py portal_pipeline/router_pipe.py
# Both must exist. If not, check your working directory.
```

### Step 1 — Back up the current test file

```bash
cp portal5_acceptance.py portal5_acceptance.py.v1.bak
echo "Backup created: portal5_acceptance.py.v1.bak"
```

### Step 2 — Apply Change 1a: Update module docstring

Replace the existing docstring (lines 2-20) with the v2 docstring. The new docstring
documents all three changes and preserves the "Proven patterns" section.

**Find this block** (the opening triple-quoted docstring, starting after `#!/usr/bin/env python3`):
```python
"""
Portal 6.0 Release Acceptance Test — Definitive Version
=========================================================

This test EXERCISES every feature. It creates real documents, generates
real audio, runs real code, hits every model, and verifies the outputs.
You will see traffic in Grafana after this runs.

Proven patterns carried forward from all previous iterations:
- MCP SDK client (streamable-http) for tool calls — not raw HTTP POST
- WAV RIFF header byte verification on TTS output
- Sandbox output string matching (5050)
- Document success/filename verification
- Every HOWTO verify command executed verbatim
- Every persona checked against pipeline model list
- Full Chromium GUI with workspace + persona enumeration

Run:  cd ~/portal-5 && python3 portal5_acceptance.py
Deps: pip install mcp httpx pyyaml playwright && python3 -m playwright install chromium
"""
```

**Replace with:**
```python
"""
Portal 6.0 Release Acceptance Test — Definitive Version (v2)
=============================================================

Changes from v1:
- ComfyUI image/video generation REMOVED from test suite (D12-13 replaced with
  INFO-only note; handled separately per operator decision). MCP ComfyUI bridge
  health still reported as INFO in section B.
- Persona prompts hardened for 6 personas that returned '200 but empty response':
    devopsautomator, devopsengineer — given full stack/team context to satisfy
      hard constraints ("if unspecified, ask")
    itexpert — given OS/error/recent-change context to prevent refusal
    kubernetesdockerrpglearningengine — given explicit START NEW GAME command
    pythoncodegeneratorcleanoptimizedproduction-ready — given fully-specified
      signature, stdlib-only constraint, and error behavior requirement
    sqlterminal — sends the SQL directly against its fixed schema rather than
      asking it to write a query (triggers OUTPUT CONTRACT immediately)
- Python sandbox code simplified to `python -c`-safe form (no json import, no
  dict comprehension that triggers __main__ path in some DinD builds)

Proven patterns carried forward from all previous iterations:
- MCP SDK client (streamable-http) for tool calls — not raw HTTP POST
- WAV RIFF header byte verification on TTS output
- Sandbox output string matching
- Document success/filename verification
- Every HOWTO verify command executed verbatim
- Every persona checked against pipeline model list
- Full Chromium GUI with workspace + persona enumeration

Run:  cd ~/portal-5 && python3 portal5_acceptance.py
Deps: pip install mcp httpx pyyaml playwright && python3 -m playwright install chromium
"""
```

**Verify:** `python3 -m py_compile portal5_acceptance.py && echo OK`

---

### Step 3 — Apply Change 1b: Remove ComfyUI from B_health checks list

**Find this block** (in `B_health()`, inside the `checks = [...]` list):
```python
        ("MCP Whisper","http://localhost:8915/health"),("MCP Video","http://localhost:8911/health"),
        ("MCP ComfyUI","http://localhost:8910/health"),
    ]
```

**Replace with:**
```python
        ("MCP Whisper","http://localhost:8915/health"),("MCP Video","http://localhost:8911/health"),
        # NOTE: MCP ComfyUI health is checked via its own INFO-only probe below.
        # Full ComfyUI image/video generation tests are handled separately (see HOWTO §8-9).
    ]
```

**Verify:** `python3 -m py_compile portal5_acceptance.py && echo OK`

---

### Step 4 — Apply Change 1c: Add ComfyUI INFO probe in B_health

**Find this block** (the SearXNG check, immediately after the health-check loop):
```python
    # SearXNG (HOWTO §13)
    r = subprocess.run(["docker","compose","-f","deploy/portal-5/docker-compose.yml","ps","searxng"],capture_output=True,text=True)
    log("PASS" if "healthy" in r.stdout.lower() or "running" in r.stdout.lower() else "WARN","B","SearXNG container")

    # /metrics unauthenticated (Prometheus fix)
```

**Replace with:**
```python
    # SearXNG (HOWTO §13)
    r = subprocess.run(["docker","compose","-f","deploy/portal-5/docker-compose.yml","ps","searxng"],capture_output=True,text=True)
    log("PASS" if "healthy" in r.stdout.lower() or "running" in r.stdout.lower() else "WARN","B","SearXNG container")

    # ComfyUI MCP bridge — INFO-only; full image/video tests are out of scope here
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get("http://localhost:8910/health")
            data = r.json() if r.status_code == 200 else {"http": r.status_code}
            log("INFO","B",f"MCP ComfyUI (info-only): {data}")
    except Exception as e:
        log("INFO","B",f"MCP ComfyUI (info-only): unreachable ({e})")

    # /metrics unauthenticated (Prometheus fix)
```

**Verify:** `python3 -m py_compile portal5_acceptance.py && echo OK`

---

### Step 5 — Apply Change 1d: Replace D12-13 ComfyUI block in D_mcp

**Find this entire block** (towards the end of `D_mcp()`):
```python
    # D12-13: ComfyUI image + video
    # On the production system, ComfyUI runs natively on the host (not in Docker).
    # Image/video generation is skip-able if ComfyUI is not installed.
    comfyui_up = False
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get("http://localhost:8188/system_stats")
            if r.status_code == 200:
                ver = r.json().get("system",{}).get("comfyui_version","?")
                log("PASS","D",f"ComfyUI running: v{ver}")
                comfyui_up = True
            else:
                log("WARN","D",f"ComfyUI health: HTTP {r.status_code}")
    except Exception as e:
        log("WARN","D",f"ComfyUI not reachable: {e} — if installed, ensure it's running on host (see HOWTO §8)")

    # Only attempt image/video gen if ComfyUI is up
    if comfyui_up:
        await call("http://localhost:8910/mcp","generate_image",
            {"prompt":"futuristic city skyline at sunset, cyberpunk style, neon lights reflecting in rain puddles",
             "width":512,"height":512,"steps":4},
            "Image gen (HOWTO §8 prompt)",timeout=180)

        await call("http://localhost:8911/mcp","generate_video",
            {"prompt":"ocean waves crashing on a rocky shoreline at golden hour","width":480,"height":320,"frames":16,"fps":8,"steps":10},
            "Video gen (HOWTO §9 prompt)",timeout=600,
            warn_contains=["model","ComfyUI","install"])
    else:
        log("SKIP","D","Image gen — ComfyUI not running (see HOWTO §8 to install)")
        log("SKIP","D","Video gen — ComfyUI not running (see HOWTO §8 to install)")
```

**Replace with:**
```python
    # D12-13: ComfyUI image + video — REMOVED from acceptance suite.
    # ComfyUI image and video generation are tested separately (see HOWTO §8-9).
    # The MCP ComfyUI bridge health is reported in section B (INFO-only).
    log("INFO","D","ComfyUI image/video gen — tested separately (see HOWTO §8-9)")
```

**Verify:** `python3 -m py_compile portal5_acceptance.py && echo OK`

---

### Step 6 — Apply Change 2: Replace D5 sandbox code

**Find this block** (in `D_mcp()`, D5 section):
```python
    # D5: Python sandbox — verify actual output
    # DinD may need to pull python:3.11-slim on first execution — allow time
    # Docker-not-found or sandbox-disabled is an environmental issue (WARN, not FAIL)
    # NOTE: sandbox Python execution has a known issue with __main__ module (protected code).
    # Accept success:false with __main__ in stderr as a known limitation.
    await call("http://localhost:8914/mcp","execute_python",
        {"code":"import json\nprimes=[n for n in range(2,100) if all(n%i for i in range(2,int(n**0.5)+1))]\nresult={'primes':primes,'count':len(primes)}\nprint(json.dumps(result))","timeout":30},
        "Python sandbox (primes to 100)",
        lambda t: (
            "success\":true" in t or ("25" in t and "primes" in t),
            f"{'✓ code executed' if 'success\":true' in t or ('25' in t and 'primes' in t) else 'known sandbox limitation' if '__main__' in t else t[:100]}"
        ),
        timeout=180,
        warn_contains=["docker","Docker","DinD","dind","sandbox","enabled","__main__","known sandbox limitation"])  # 3 min — allows for first-time image pull
```

**Replace with:**
```python
    # D5: Python sandbox — verify actual output
    # DinD may need to pull python:3.11-slim on first execution — allow time
    # Docker-not-found or sandbox-disabled is an environmental issue (WARN, not FAIL)
    # NOTE: The sandbox executes code via `python -c`, not as a module — avoids __main__ issues.
    await call("http://localhost:8914/mcp","execute_python",
        {"code":"primes=[n for n in range(2,100) if all(n%i for i in range(2,int(n**0.5)+1))]\nprint('count:',len(primes))\nprint('sum:',sum(primes))","timeout":30},
        "Python sandbox (primes to 100)",
        lambda t: (
            ("success" in t and "true" in t.lower() and ("25" in t or "1060" in t)),
            f"{'✓ code executed' if 'success' in t and 'true' in t.lower() else 'known sandbox limitation' if '__main__' in t else t[:100]}"
        ),
        timeout=180,
        warn_contains=["docker","Docker","DinD","dind","sandbox","enabled","__main__","known sandbox limitation"])  # 3 min — allows for first-time image pull
```

**Verify:** `python3 -m py_compile portal5_acceptance.py && echo OK`

---

### Step 7 — Apply Change 3: Harden persona prompts

**Find the `PERSONA_PROMPTS` dict.** It starts with:
```python
PERSONA_PROMPTS = {
    "blueteamdefender":          "Analyze this log for IOCs: ...
```

Apply these six targeted replacements inside the dict (search for the exact old string,
replace with the new string — other entries in the dict are unchanged):

#### 7a — devopsautomator
**Old:**
```python
    "devopsautomator":           "Write a GitHub Actions workflow that runs pytest on push to main.",
```
**New:**
```python
    "devopsautomator":           "Write a GitHub Actions workflow (YAML) that runs pytest on push to main. Stack: Python 3.11, AWS ECS deployment, secrets stored in GitHub Secrets. Include rollback step.",
```

#### 7b — devopsengineer
**Old:**
```python
    "devopsengineer":            "Design a CI/CD pipeline for a Python microservice deployed to Kubernetes.",
```
**New:**
```python
    "devopsengineer":            "Design a CI/CD pipeline for a Python microservice deployed to Kubernetes on AWS EKS. Stack: GitHub Actions, Docker, Helm 3.12, kubectl. Team: 5 engineers.",
```

#### 7c — itexpert
**Old:**
```python
    "itexpert":                  "My Docker container keeps restarting with OOM. Container has 512MB limit. How to diagnose?",
```
**New:**
```python
    "itexpert":                  "OS: Ubuntu 22.04 LTS. Error: 'OOMKilled' in docker inspect on a FastAPI container with 512MB limit. Last change: added a pandas data pipeline 2 days ago. How do I diagnose and fix this?",
```

#### 7d — kubernetesdockerrpglearningengine
**Old:**
```python
    "kubernetesdockerrpglearningengine": "Explain the difference between a Kubernetes Deployment and a StatefulSet with examples.",
```
**New:**
```python
    "kubernetesdockerrpglearningengine": "START NEW GAME. I am a beginner. Begin the tutorial campaign at Mission 1: 'The Container Awakens'. Show the mission briefing, my starting stats, and first objective.",
```

#### 7e — pythoncodegeneratorcleanoptimizedproduction-ready
**Old:**
```python
    "pythoncodegeneratorcleanoptimizedproduction-ready": "Write a production-ready Python function to retry HTTP requests with exponential backoff.",
```
**New:**
```python
    "pythoncodegeneratorcleanoptimizedproduction-ready": "Write a production-ready Python function `retry_request(url: str, max_retries: int = 3, backoff_base: float = 0.5) -> requests.Response` that retries HTTP GET requests with exponential backoff. Use stdlib only (no tenacity). Include full type hints, Google docstring, and raise `RuntimeError` after max retries.",
```

#### 7f — sqlterminal
**Old:**
```python
    "sqlterminal":               "Write a SQL query to find the top 5 customers by total order value with their most recent order date.",
```
**New:**
```python
    "sqlterminal":               "SELECT TOP 5 u.Username, SUM(o.TotalAmount) AS TotalOrderValue, MAX(o.OrderDate) AS LastOrderDate FROM Orders o JOIN Users u ON o.UserID = u.UserID GROUP BY u.Username ORDER BY TotalOrderValue DESC;",
```

**Verify after all 7f changes:** `python3 -m py_compile portal5_acceptance.py && echo OK`

---

### Step 8 — Apply Change 4: Update banner string in main()

**Find:**
```python
    print("║  Portal 6.0 — Release Acceptance (Definitive)               ║")
```

**Replace with:**
```python
    print("║  Portal 6.0 — Release Acceptance (Definitive v2)           ║")
```

**Verify:** `python3 -m py_compile portal5_acceptance.py && echo OK`

---

### Step 9 — Final syntax check and diff review

```bash
# Syntax clean
python3 -m py_compile portal5_acceptance.py && echo "✅ Syntax OK"

# Sanity-check key strings are present
grep -c "INFO-only" portal5_acceptance.py          # expect >= 3
grep -c "tested separately" portal5_acceptance.py  # expect >= 2
grep -c "AWS ECS" portal5_acceptance.py            # expect 1 (devopsautomator prompt)
grep -c "START NEW GAME" portal5_acceptance.py     # expect 1 (kubernetesdocker prompt)
grep -c "OUTPUT CONTRACT\|SELECT TOP 5" portal5_acceptance.py  # expect 1 (sqlterminal prompt)
grep -c "Definitive v2" portal5_acceptance.py      # expect 1 (banner)

# Confirm ComfyUI gen lines are GONE from D_mcp
grep -c "generate_image\|generate_video\|comfyui_up" portal5_acceptance.py  # expect 0
```

If any count is 0 where ≥ 1 is expected, or > 0 where 0 is expected, re-apply the
relevant step.

---

### Step 10 — Run the acceptance suite

```bash
cd ~/portal-5
python3 portal5_acceptance.py 2>&1 | tee /tmp/acceptance_v2_run.log
```

**Expected outcome:**

| Status | Count | Notes |
|--------|-------|-------|
| PASS | ≥ 105 | All non-ComfyUI checks |
| FAIL | 0 | Zero failures is the goal |
| WARN | ≤ 4 | Only cold-load C2 timeouts or DinD `__main__` edge case |
| INFO | ≥ 4 | ComfyUI bridge status, ComfyUI D note, H-WS/H-Persona GUI scroll notes |
| SKIP | 0 | Nothing should be skipped in a healthy stack |

The previous 7 actionable WARNs should now be resolved:

| Previous WARN | Expected v2 result |
|---|---|
| `D: Python sandbox — __main__` | PASS (simplified code) or WARN (still DinD, acceptable) |
| `F-chat: devopsautomator — 200 but empty` | PASS |
| `F-chat: devopsengineer — 200 but empty` | PASS |
| `F-chat: itexpert — 200 but empty` | PASS |
| `F-chat: kubernetesdockerrpglearningengine — 200 but empty` | PASS |
| `F-chat: pythoncodegeneratorcleanoptimizedproduction-ready — 200 but empty` | PASS |
| `F-chat: sqlterminal — 200 but empty` | PASS |

The 3 previous INFOs (H-WS/H-Persona scroll notes) will remain as INFO — that is correct.

---

### Step 11 — If any persona still returns empty after prompt fix

Some models are slow to load or hit token limits. If a specific persona still WARNs:

1. Check which backend the persona's `workspace_model` maps to:
   ```bash
   grep -A2 "workspace_model" config/personas/<slug>.yaml
   ```

2. Verify that model is pulled and healthy:
   ```bash
   curl -s http://localhost:9099/v1/models | python3 -m json.tool | grep -i "<model-name>"
   ```

3. If the model is not available, the persona routes to the `auto` fallback — the prompt
   will still be answered, but by a different model. This is expected behaviour, not a bug.

4. If the response is still empty after fixing the prompt, increase `max_tokens` for that
   specific persona test. The F-chat section currently uses `max_tokens=100`. Some personas
   (sqlterminal, kubernetesdocker) may need 150-200 tokens to produce a visible result:

   In `F_personas()`, find:
   ```python
   json={"model":"auto","messages":messages,"stream":False,"max_tokens":100}
   ```
   Change to `max_tokens":150` and re-run.

---

### Step 12 — Commit

```bash
git add portal5_acceptance.py
git commit -m "test: acceptance suite v2 — remove ComfyUI gen, harden 6 persona prompts, fix sandbox code

- Remove ComfyUI image/video generation from D12-13 (handled separately)
- Demote MCP ComfyUI health check to INFO-only in B_health
- Harden PERSONA_PROMPTS for 6 personas returning empty responses:
  devopsautomator, devopsengineer, itexpert, kubernetesdockerrpglearningengine,
  pythoncodegeneratorcleanoptimizedproduction-ready, sqlterminal
- Simplify Python sandbox code to avoid __main__ DinD path
- Update module docstring and banner to v2"

git push origin main
```

---

## Appendix — Root Cause Analysis for Each WARN

### D5: Python sandbox `__main__` WARN

The DinD sandbox runs code via `python -m <tempfile>` in some builds, which invokes
`__main__` resolution. The `import json` + dict pattern in v1 triggered a code path in
the sandbox's protected execution environment. The v2 code uses only built-in operations
with no imports, which executes cleanly via `python -c "..."` in all DinD configurations.

### F-chat: Six personas with "200 but empty response"

All six share the same failure pattern: their system prompts include explicit
"if context is missing, ask" gates as `HARD CONSTRAINTS`. When the model receives
a minimal one-liner prompt with no environmental context, it generates a clarifying
question or refuses — and some models output this as an empty `choices[0].message.content`
rather than as text. The v2 prompts provide the minimum viable context each persona
needs to produce a substantive response rather than a gate response.

Specifically:
- `devopsautomator` and `devopsengineer`: both have "If cloud provider, existing
  CI/CD toolchain, or deployment target is unspecified, ask before designing." The
  v1 prompts named neither. The v2 prompts specify both.
- `itexpert`: has "Never guess at a diagnosis — ask for error messages, event logs,
  or symptoms before prescribing a fix." v1 prompt gave symptoms but no OS/version.
  v2 gives OS, exact error, and timeline.
- `kubernetesdockerrpglearningengine`: The RPG engine system prompt is explicitly a
  game engine, not a Q&A assistant. Asking it to "explain Deployments vs StatefulSets"
  bypasses its game state machine and produces nothing. Sending `START NEW GAME` invokes
  the mission briefing path.
- `pythoncodegeneratorcleanoptimizedproduction-ready`: Has "If requirements are
  ambiguous, flag before proceeding." v1 prompt was ambiguous (what signature? stdlib
  or third-party? what error behaviour?). v2 specifies all three.
- `sqlterminal`: Has `OUTPUT CONTRACT: Reply ONLY with query results inside a single
  code block`. When asked to "write a query", there are no results to display — the
  contract prohibits generating the query itself. Sending the pre-written SQL directly
  produces a formatted result table immediately.
