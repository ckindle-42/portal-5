# TASK_REVIEW_FIXES_PHASE2_HARDENING.md

**Source review:** `PORTAL5_REVIEW_V6.0.3.md` + Phase 1 prerequisites landed
**Phase:** 2 of 3 — Defense-in-depth hardening
**Target version:** 6.1.0
**Estimated effort:** 12-16 hours total (1-2 days)
**Prerequisite:** Phase 1 must be merged and verified live. The hint validator (Task 2.1) would otherwise refuse to start.
**Risk:** Medium — adds enforcement, extends test scaffolding, splits files. Each change is reversible via `git revert <commit>`.

---

## Scope

Phase 2 takes the surgical fixes from Phase 1 and turns them into systemic safeguards. Each task addresses a class of bugs rather than a single instance.

**Out of scope:** Architectural restructure (Phase 3). Phase 2 leaves `mlx-proxy.py`'s hardcoded `MODEL_MEMORY` in place — Phase 3 consolidates it into `backends.yaml`.

---

## Pre-flight

```bash
# Confirm Phase 1 landed
git log --oneline pre-phase1-fixes..HEAD | grep -c "^[a-f0-9]\+ " 
# Expected: 10+ commits including REL-02, REL-03, REL-08 fixes

# Tag for rollback
git tag pre-phase2-fixes

# Sanity
pytest tests/unit/ -q --tb=no
ruff check . 2>&1 | tail -5
```

---

## Task 2.1 — Startup hint validator (ME-01)

### Rationale
Phase 1 fixed two hint typos (REL-02, REL-03) and added a runtime warning (Task 1.12). This task adds **fail-fast enforcement at boot** so the next typo never reaches production. The validator iterates `WORKSPACES` and asserts every `model_hint` and `mlx_model_hint` exists in at least one `backend.models` entry whose group is in `workspace_routing[ws_id]`.

### Strategy
- Add `_validate_workspace_hints(registry)` function in `router_pipe.py` near the BackendRegistry import.
- Call it from `lifespan()` immediately after `BackendRegistry()` instantiation, before any startup warmup.
- Behaviour: log warning by default; fail-fast under `STRICT_HINT_VALIDATION=true`.

### Implementation

```python
# portal_pipeline/router_pipe.py — new function near line 200
def _validate_workspace_hints(registry: BackendRegistry) -> list[str]:
    """Verify every WORKSPACES hint resolves to an actual backend model.

    Returns a list of error strings. Empty list = all hints reachable.

    Hints check against the union of `backend.models` for all backends
    whose `group` appears in `workspace_routing[ws_id]`.
    """
    # Build group -> models map from registry
    group_models: dict[str, set[str]] = {}
    for be in registry.list_backends():
        group_models.setdefault(be.group, set()).update(be.models)

    errors: list[str] = []
    for ws_id, ws_cfg in WORKSPACES.items():
        groups = registry._workspace_routes.get(ws_id, [])  # ok to read internal
        available: set[str] = set()
        for g in groups:
            available |= group_models.get(g, set())

        for hint_key in ("model_hint", "mlx_model_hint"):
            hint = ws_cfg.get(hint_key)
            if hint and hint not in available:
                errors.append(
                    f"workspace={ws_id!r} {hint_key}={hint!r} "
                    f"not in any backend's models for groups={groups}. "
                    f"Add it to config/backends.yaml or correct the WORKSPACES hint."
                )
    return errors


# Inside lifespan(), after `registry = BackendRegistry()`:
    hint_errors = _validate_workspace_hints(registry)
    if hint_errors:
        for e in hint_errors:
            logger.error("HINT VALIDATION: %s", e)
        if os.environ.get("STRICT_HINT_VALIDATION", "false").lower() in ("true", "1", "yes"):
            raise RuntimeError(
                f"STRICT_HINT_VALIDATION=true and {len(hint_errors)} hint(s) failed validation. "
                "See logs above. Set STRICT_HINT_VALIDATION=false to start anyway."
            )
        else:
            logger.warning(
                "HINT VALIDATION: %d hint(s) failed but STRICT_HINT_VALIDATION=false — starting anyway. "
                "Hints will silently fall back at request time. Fix backends.yaml or WORKSPACES.",
                len(hint_errors),
            )
```

### Tests

Add `tests/unit/test_hint_validator.py`:

```python
"""Test the workspace hint validator."""

import pytest
from unittest.mock import MagicMock

from portal_pipeline.router_pipe import _validate_workspace_hints, WORKSPACES


def _mock_registry(backends: list[tuple[str, str, list[str]]], routes: dict[str, list[str]]):
    """Build a mock registry. backends = [(id, group, models), ...]."""
    reg = MagicMock()
    be_objs = []
    for bid, grp, models in backends:
        b = MagicMock()
        b.id = bid
        b.group = grp
        b.models = models
        be_objs.append(b)
    reg.list_backends.return_value = be_objs
    reg._workspace_routes = routes
    return reg


def test_validator_passes_when_hints_resolve():
    reg = _mock_registry(
        backends=[
            ("ollama-coding", "coding", ["qwen3-coder:30b"]),
            ("mlx-apple-silicon", "mlx", ["mlx-community/Qwen3-Coder-Next-4bit"]),
        ],
        routes={"auto-coding": ["mlx", "coding", "general"]},
    )
    # Patch WORKSPACES briefly
    saved = dict(WORKSPACES)
    WORKSPACES.clear()
    WORKSPACES["auto-coding"] = {
        "name": "test", "description": "test",
        "model_hint": "qwen3-coder:30b",
        "mlx_model_hint": "mlx-community/Qwen3-Coder-Next-4bit",
        "tools": [],
    }
    try:
        errors = _validate_workspace_hints(reg)
        assert errors == []
    finally:
        WORKSPACES.clear()
        WORKSPACES.update(saved)


def test_validator_catches_missing_hint():
    reg = _mock_registry(
        backends=[("ollama-coding", "coding", ["qwen3-coder:30b"])],
        routes={"auto-coding": ["coding"]},
    )
    saved = dict(WORKSPACES)
    WORKSPACES.clear()
    WORKSPACES["auto-coding"] = {
        "name": "test", "description": "test",
        "model_hint": "nonexistent:99b",
        "tools": [],
    }
    try:
        errors = _validate_workspace_hints(reg)
        assert len(errors) == 1
        assert "nonexistent:99b" in errors[0]
    finally:
        WORKSPACES.clear()
        WORKSPACES.update(saved)


def test_validator_catches_real_workspaces_dict():
    """Smoke test against the actual WORKSPACES dict and backends.yaml."""
    import yaml
    from portal_pipeline.cluster_backends import BackendRegistry
    reg = BackendRegistry()  # uses default config path
    errors = _validate_workspace_hints(reg)
    # Phase 1 should have eliminated all hint typos. If this fails, something regressed.
    assert errors == [], f"Hint validation regressions:\n  " + "\n  ".join(errors)
```

### Verify
```bash
# 1. Unit tests pass
pytest tests/unit/test_hint_validator.py -v

# 2. Live: pipeline starts cleanly with valid hints
PIPELINE_API_KEY=test STRICT_HINT_VALIDATION=true python3 -m portal_pipeline &
sleep 5
curl -s -H "Authorization: Bearer test" http://localhost:9099/health | jq .
kill %1

# 3. Live: pipeline fails fast with bad hint
# (Temporarily edit a hint to be invalid; pipeline should exit 1)
```

### Commit
```
feat(routing): add startup hint validator

Validates every WORKSPACES model_hint and mlx_model_hint resolves to
an actual backend.models entry whose group is in the workspace's
routing list. Logs warnings by default; fails fast when
STRICT_HINT_VALIDATION=true.

Catches the class of bug that REL-02 (auto-research mlx_model_hint
typo) and REL-03 (auto-coding/agentic Ollama hint typo) belonged to.
The Phase 1 runtime warning (Task 1.12) only logs at first request;
this catches typos at boot.
```

---

## Task 2.2 — Acceptance S1 hint reachability subtest (ME-02)

### Rationale
Reuse the Phase 2.1 validator from the test side so misconfigurations are caught even if `STRICT_HINT_VALIDATION` is off in production.

### Action
In `tests/portal5_acceptance_v6.py`, locate the `S1()` async function (around line 1604). Add a new sub-check `S1-17: workspace hint reachability`:

```python
# Inside S1() near line 1700-1800
sec = "S1"
t0 = time.monotonic()
try:
    from portal_pipeline.router_pipe import _validate_workspace_hints
    from portal_pipeline.cluster_backends import BackendRegistry
    reg = BackendRegistry()
    errors = _validate_workspace_hints(reg)
    if not errors:
        record(sec, "S1-17", "workspace hint reachability", "PASS",
               f"all {len(WORKSPACES)} workspace hints resolve", t0=t0)
    else:
        record(sec, "S1-17", "workspace hint reachability", "FAIL",
               f"{len(errors)} hints unresolved: {errors[0][:120]}...", t0=t0)
except Exception as e:
    record(sec, "S1-17", "workspace hint reachability", "FAIL", str(e)[:200], t0=t0)
```

### Verify
```bash
python3 tests/portal5_acceptance_v6.py --section S1
# Expected: S1-17 PASS
```

### Commit
```
test(acceptance): add S1-17 workspace hint reachability check

Reuses the Phase 2.1 validator inside the acceptance suite so hint
typos are caught even in environments where STRICT_HINT_VALIDATION
is off in production.
```

---

## Task 2.3 — Sticky-tool-unhealthy backoff (ME-03)

### Rationale
`tool_registry.py:176` sets `tool.healthy = False` on any non-200 response. The flag stays false until next refresh (default `TOOL_REGISTRY_REFRESH_S=3600`). One transient MCP failure = 1 hour of disabled tool. Replace with exponential backoff.

### Implementation

```python
# portal_pipeline/tool_registry.py

@dataclass
class ToolDefinition:
    """A single tool, resolvable to an MCP server."""

    name: str
    description: str
    parameters: dict[str, Any]
    server_id: str
    server_url: str
    last_seen: float = 0.0
    healthy: bool = True
    custom_timeout_s: float | None = None
    # NEW: backoff state
    next_retry_at: float = 0.0       # when to allow retry (epoch seconds)
    consecutive_failures: int = 0     # for exponential backoff calc


def _backoff_seconds(failures: int) -> float:
    """Backoff schedule: 30s, 2m, 5m, 15m, 1h, capped."""
    schedule = [30, 120, 300, 900, 3600]
    return float(schedule[min(failures - 1, len(schedule) - 1)])


# In dispatch():
    async def dispatch(self, tool_name, arguments, request_id=""):
        tool = self.get(tool_name)
        if tool is None:
            return {"error": f"Tool '{tool_name}' not in registry"}

        # NEW: check backoff window
        now = time.time()
        if not tool.healthy and now < tool.next_retry_at:
            remaining = int(tool.next_retry_at - now)
            return {
                "error": f"Tool '{tool_name}' in backoff (retry in {remaining}s after "
                         f"{tool.consecutive_failures} consecutive failures)"
            }

        timeout_s = tool.custom_timeout_s or TOOL_DISPATCH_TIMEOUT_S
        url = f"{tool.server_url.rstrip('/')}/tools/{tool_name}"

        try:
            client = await self._client()
            r = await client.post(url, json={"arguments": arguments, "request_id": request_id}, timeout=timeout_s)
            if r.status_code == 200:
                # SUCCESS: reset backoff state
                tool.healthy = True
                tool.consecutive_failures = 0
                tool.next_retry_at = 0.0
                return r.json()
            else:
                # FAILURE: schedule retry per backoff
                tool.consecutive_failures += 1
                tool.healthy = False
                tool.next_retry_at = now + _backoff_seconds(tool.consecutive_failures)
                return {
                    "error": f"Tool '{tool_name}' returned HTTP {r.status_code}",
                    "detail": r.text[:200],
                }
        except asyncio.TimeoutError:
            tool.consecutive_failures += 1
            tool.healthy = False
            tool.next_retry_at = now + _backoff_seconds(tool.consecutive_failures)
            return {"error": f"Tool '{tool_name}' timed out after {timeout_s}s"}
        except Exception as e:
            tool.consecutive_failures += 1
            tool.healthy = False
            tool.next_retry_at = now + _backoff_seconds(tool.consecutive_failures)
            return {"error": f"Tool '{tool_name}' dispatch failed: {e}"}
```

Also relax `get_openai_tools` to allow tools whose backoff window has expired:

```python
    def get_openai_tools(self, names: list[str]) -> list[dict[str, Any]]:
        now = time.time()
        result = []
        for n in names:
            t = self._tools.get(n)
            if t is None:
                continue
            if t.healthy or now >= t.next_retry_at:
                result.append(t.to_openai_tool())
        return result
```

### Tests

Add `tests/unit/test_tool_backoff.py` covering: success resets state, single failure schedules 30s retry, three failures schedules 5m, retry-allowed after window passes, retry-blocked inside window.

### Commit
```
fix(tools): replace sticky unhealthy flag with exponential backoff

A single non-200 from any MCP server marked the tool unhealthy for
TOOL_REGISTRY_REFRESH_S (default 3600s = 1 hour). Transient failures
produced 1-hour outages. Replaces the boolean flag with a backoff
schedule (30s → 2m → 5m → 15m → 1h, capped) tracked per ToolDefinition.
Success resets the counter; failures advance it. get_openai_tools()
considers a tool dispatchable once its backoff window has elapsed.
```

---

## Task 2.4 — Persona seed validation (ME-04)

### Rationale
Phase 1 audit confirmed all 82 functional persona `workspace_model` values resolve correctly. Phase 2 enforces this at seed time so future YAML edits don't regress. `scripts/openwebui_init.py` reads each persona YAML and creates an Open WebUI preset; add a validation pass that aborts on invalid `workspace_model`.

### Action
In `scripts/openwebui_init.py`, before any preset creation, add `_validate_personas()`:

```python
def _validate_personas(personas_dir: Path, valid_workspace_ids: set[str]) -> list[str]:
    """Validate every persona YAML's workspace_model resolves.

    Returns a list of error strings. Empty list = all valid.
    """
    errors = []
    for f in sorted(personas_dir.glob("*.yaml")):
        if f.stem.startswith("bench_"):
            continue
        try:
            d = yaml.safe_load(f.read_text())
        except Exception as e:
            errors.append(f"{f.name}: YAML parse error: {e}")
            continue
        wm = d.get("workspace_model", "")
        if not wm:
            errors.append(f"{f.name}: missing workspace_model field")
            continue
        if wm not in valid_workspace_ids:
            errors.append(
                f"{f.name}: workspace_model={wm!r} not in WORKSPACES — "
                f"persona will fail to route. Use one of the auto-* IDs."
            )
    return errors


# Call from main seed flow:
def main():
    # ... existing setup ...
    from portal_pipeline.router_pipe import WORKSPACES
    valid = set(WORKSPACES.keys())
    errors = _validate_personas(Path("config/personas"), valid)
    if errors:
        for e in errors:
            print(f"[seed] PERSONA ERROR: {e}", file=sys.stderr)
        if os.environ.get("STRICT_PERSONA_VALIDATION", "true").lower() in ("true", "1", "yes"):
            sys.exit(1)
        print(f"[seed] {len(errors)} personas invalid — STRICT_PERSONA_VALIDATION=false, continuing", file=sys.stderr)
    # ... rest of seed flow ...
```

### Verify
```bash
# 1. Run seed against a deliberately-broken persona
cp config/personas/agentorchestrator.yaml /tmp/bad.yaml.bak
python3 -c "
import yaml
p = 'config/personas/agentorchestrator.yaml'
d = yaml.safe_load(open(p).read())
d['workspace_model'] = 'nonexistent-workspace'
open(p, 'w').write(yaml.dump(d))
"
STRICT_PERSONA_VALIDATION=true python3 scripts/openwebui_init.py
# Expected: exits 1 with "workspace_model='nonexistent-workspace' not in WORKSPACES"

# Restore
mv /tmp/bad.yaml.bak config/personas/agentorchestrator.yaml
```

### Commit
```
fix(seed): validate persona workspace_model before creating presets

openwebui_init.py created Open WebUI presets even when a persona's
workspace_model didn't exist in the WORKSPACES dict. The result was
silent: persona showed up in OWUI dropdown, but every chat using it
hit the fallback group. Adds a pre-flight validation pass and exits
non-zero unless STRICT_PERSONA_VALIDATION=false.

Phase 1 confirmed all 82 current personas pass; this prevents future
YAML edits from regressing.
```

---

## Task 2.5 — bench_tps quality hooks (ME-05)

### Rationale
`bench_tps` measures TPS but not time-to-first-token (TTFT, the metric users feel) and doesn't correlate with GPU memory state. Add both.

### Action

**A. TTFT capture.** Modify the inference function to record the timestamp of the first non-empty content chunk. Add `time_to_first_token_s` to the per-run dict.

**B. Memory snapshots.** Before and after each MLX run, hit `http://localhost:8081/health` and read `memory.free_gb` / `memory.used_gb`. Add `memory_before_gb` / `memory_after_gb` per result row.

### Implementation sketch

```python
# tests/benchmarks/bench_tps.py — modify _run_inference (or equivalent)

async def _run_pipeline_inference(model: str, prompt: str, ...) -> dict:
    payload = {"model": model, "messages": [...], "stream": True, ...}
    t_start = time.monotonic()
    t_first_token = None
    completion_tokens = 0
    full_text = ""

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        async with client.stream("POST", f"{PIPELINE_URL}/v1/chat/completions",
                                  json=payload, headers={"Authorization": f"Bearer {api_key}"}) as r:
            async for line in r.aiter_lines():
                if not line.startswith("data: "):
                    continue
                if line == "data: [DONE]":
                    break
                try:
                    obj = json.loads(line[6:])
                    delta = obj["choices"][0]["delta"]
                    chunk_text = delta.get("content") or ""
                    if chunk_text and t_first_token is None:
                        t_first_token = time.monotonic()
                    full_text += chunk_text
                    completion_tokens = obj.get("usage", {}).get("completion_tokens", completion_tokens)
                except Exception:
                    continue

    t_end = time.monotonic()
    elapsed = t_end - t_start
    ttft = (t_first_token - t_start) if t_first_token else None
    tps = completion_tokens / elapsed if elapsed > 0 else 0.0

    # Memory snapshot for MLX
    mem = {}
    try:
        h = httpx.get(f"{MLX_URL}/health", timeout=2.0).json()
        mem = h.get("memory", {})
    except Exception:
        pass

    return {
        "tps": tps,
        "completion_tokens": completion_tokens,
        "elapsed_s": elapsed,
        "time_to_first_token_s": ttft,
        "memory_free_gb": mem.get("free_gb"),
        "memory_used_gb": mem.get("used_gb"),
        "text": full_text[:500],
    }
```

### Verify
```bash
python3 tests/benchmarks/bench_tps.py --runs 1 --workspace auto-coding --output /tmp/test.json
python3 -c "
import json
d = json.load(open('/tmp/test.json'))
r = d['results'][0]['runs'][0]
assert 'time_to_first_token_s' in r
assert r['time_to_first_token_s'] is None or r['time_to_first_token_s'] > 0
print(f'OK: TTFT={r.get(\"time_to_first_token_s\")}s, TPS={r.get(\"tps\")}')
"
```

### Commit
```
feat(bench): add time-to-first-token and memory snapshots

bench_tps measured steady-state TPS but not TTFT, the metric users
actually feel during cold loads. Adds time_to_first_token_s to each
run record by capturing the timestamp of the first non-empty content
delta. Also captures memory_free_gb / memory_used_gb from the MLX
proxy /health endpoint before and after each run, exposing the
correlation between memory pressure and TPS regressions that was
otherwise invisible.
```

---

## Task 2.6 — Acceptance error classifier (ME-06)

### Rationale
`tests/ACCEPTANCE_EVIDENCE.md` says "All 7 FAILs are environmental" but two of them were code defects (S40-03 VLM log pattern, S40-05 model-quality issue subsequently surfaced as P5-MLX-005). The acceptance harness should auto-classify FAIL/WARN by error pattern.

### Action
In `tests/portal5_acceptance_v6.py`, add a small classification helper called by `record()`:

```python
_ERROR_PATTERNS_CODE_DEFECT = [
    r"No such file or directory.*portal_metrics",
    r"model_hint.*not in",
    r"workspace_model.*not in WORKSPACES",
    r"AttributeError|TypeError|NameError",
    r"port.*already in use|address already in use",
    r"semaphore.*concurrency limit",
]
_ERROR_PATTERNS_ENV_ISSUE = [
    r"All connection attempts failed",
    r"name resolution|getaddrinfo",
    r"docker.*registry|registry-1.docker.io",
    r"insufficient memory|out of memory",
    r"missing dependency|No module named",
    r"port.*not running|not running",
]


def _classify(detail: str) -> str:
    for pat in _ERROR_PATTERNS_CODE_DEFECT:
        if re.search(pat, detail, re.IGNORECASE):
            return "CODE-DEFECT"
    for pat in _ERROR_PATTERNS_ENV_ISSUE:
        if re.search(pat, detail, re.IGNORECASE):
            return "ENV-ISSUE"
    return "UNCLASSIFIED"


# In record(), when status in ("FAIL", "WARN"), append [class] to detail.
# In _emit() summary, count code defects vs env issues separately.
```

Update `ACCEPTANCE_RESULTS.md` template to include a header row:
```
**Code defects: 1 · Env issues: 3 · Unclassified: 0**
```

### Commit
```
test(acceptance): auto-classify FAIL/WARN as code defect vs env issue

The Run-13 narrative ("All 7 FAILs environmental") was misleading —
two were genuine code defects (VLM log pattern in test, gibberish-output
model in catalog). Adds a regex-based classifier inside record() so
the run summary shows code-defects vs env-issues separately. Operators
can prioritize: code defects need code fixes; env issues need ops fixes.
```

---

## Task 2.7 — Acceptance test split (ME-07)

### Rationale
`tests/portal5_acceptance_v6.py` is 4,230 lines and 30 section functions in one file. Splitting reduces merge conflicts and makes section-level work tractable.

### Action
Move each section body to a per-section module:

```
tests/acceptance/
├── _common.py          # already exists
├── s00_startup.py      # S0
├── s01_static_config.py # S1
├── s02_services.py     # S2
├── s03_routing.py      # S3, S3a, S3b
├── s04_documents.py    # S4
├── s05_health.py       # S5
├── s06_routing_more.py # S6
├── s07_music.py        # S7
├── s08_tts.py          # S8
├── s09_stt.py          # S9
├── s10_video.py        # S10
├── s11_personas.py     # S11
├── s12_metrics.py      # S12
├── s13_gui.py          # S13
├── s16_cli.py          # S16
├── s20_routing_eval.py # S20
├── s21_notifications.py # S21
├── s22_mlx_switching.py # S22
├── s23_fallback.py     # S23
├── s30_personas_mlx.py # S30, S31
├── s40_mlx_models.py   # S40, S41, S42
├── s50_negative.py     # already exists
├── s60_browser.py      # S60
├── s70_research_mcps.py # S70
└── __init__.py
```

`tests/portal5_acceptance_v6.py` becomes a thin orchestrator:

```python
from tests.acceptance import s00_startup, s01_static_config, ...

SECTIONS = {
    "S0": s00_startup.run,
    "S1": s01_static_config.run,
    # ...
}

async def main():
    args = parse_args()
    for sid, fn in SECTIONS.items():
        if args.section and args.section != sid:
            continue
        await fn()
```

Each per-section module exports `async def run() -> None` and uses the shared `record()` from `tests/acceptance/_common.py`.

### Commit (one per ~5 sections, ~6 commits total)
```
test(acceptance): extract Sx_y to tests/acceptance/<section>.py

Splits portal5_acceptance_v6.py (4230 lines) into per-section modules.
This commit moves Sections S0–S5 into tests/acceptance/s00_startup.py
through s05_health.py. portal5_acceptance_v6.py imports and dispatches.
No behaviour change; pure refactor.
```

---

## Task 2.8 — VLM admission credit verification (ME-09)

### Rationale
`mlx-proxy.py:1132` reads `current_loaded = mlx_state.loaded_model` and credits `freed_by_stop_gb = MODEL_MEMORY.get(current_loaded, 0.0)`. When the active server is `vlm` and the new request is for `lm`, both servers do not run simultaneously — `stop_all()` will kill the VLM server, freeing its memory. But the credit lookup is correct only if `loaded_model` reflects the VLM model. Verify this invariant under all transitions.

### Action
Read `MLXState` in detail. Add an explicit `assert` (debug-only) that `mlx_state.loaded_model` and `mlx_state.active_server` always agree about which type of server holds memory.

Also add a unit test in `tests/unit/test_mlx_proxy.py`:

```python
def test_admission_credit_after_vlm_to_lm_switch():
    """Switching from a VLM model to a text model should credit VLM memory."""
    # Mock MLXState with VLM loaded
    state.set_ready("vlm", "mlx-community/Qwen3-VL-32B-Instruct-8bit")
    # Request a text model
    # Assert _check_memory_for_model receives the VLM model's memory as freed_by_stop_gb
    ...
```

### Commit
```
fix(mlx-proxy): verify admission credit on VLM↔LM transitions

When the active server is mlx_vlm and a request arrives for an
mlx_lm-only model, ensure_server stops the VLM server before loading
the LM model. The admission credit (freed_by_stop_gb) needs to reflect
the VLM model's memory so the check doesn't reject a valid switch.
Adds an assertion that mlx_state.loaded_model and active_server agree,
plus a unit test for the VLM-to-LM transition path.
```

---

## Task 2.9 — README ↔ acceptance sync target (ME-10)

### Rationale
README's "Acceptance Testing" block was 12 days stale. After Phase 1 Task 1.9 it links to the file rather than hardcoding. Phase 2 adds a maintenance helper.

### Action
Add `launch.sh sync-readme` command that pulls the latest acceptance summary into README:

```bash
# launch.sh
  sync-readme)
    if [ ! -f ACCEPTANCE_RESULTS.md ]; then
        echo "No ACCEPTANCE_RESULTS.md to sync from. Run acceptance tests first."
        exit 1
    fi
    SUMMARY=$(awk '/^## Summary/,/^## Results/' ACCEPTANCE_RESULTS.md)
    DATE=$(grep '^\\*\\*Date:' ACCEPTANCE_RESULTS.md | head -1 | sed 's/\\*\\*//g')
    # Replace the ### Acceptance Testing block in README.md
    python3 << PYEOF
import re
with open('README.md') as f:
    readme = f.read()
new_block = f"""### Acceptance Testing

The full acceptance test suite (\`tests/portal5_acceptance_v6.py\`) runs
~250 checks across 30 sections. Run with:

\`\`\`bash
python3 tests/portal5_acceptance_v6.py
python3 tests/portal5_acceptance_v6.py --section S70
\`\`\`

Latest run ({"$DATE"}):
{"$SUMMARY".strip()}

See [ACCEPTANCE_RESULTS.md](ACCEPTANCE_RESULTS.md) for full results.
"""
new = re.sub(
    r'### Acceptance Testing.*?(?=\n## |\n### |\Z)',
    new_block + '\n',
    readme,
    count=1,
    flags=re.DOTALL,
)
with open('README.md', 'w') as f:
    f.write(new)
PYEOF
    echo "README.md acceptance section refreshed."
    ;;
```

### Commit
```
chore(launch): add sync-readme command

After every full acceptance run, `./launch.sh sync-readme` regenerates
the README "Acceptance Testing" block from ACCEPTANCE_RESULTS.md so
the documented run never drifts from the actual run.
```

---

## Task 2.10 — Document MCP read-capability acceptance test (ME-extra)

### Rationale
`portal_mcp/documents/document_mcp.py` implements `read_word_document`/`read_excel`/`read_powerpoint`/`read_pdf` (verified in Phase A reading). No acceptance test exercises these. Add to S4.

### Action
Append four sub-tests to `S4()` in `tests/portal5_acceptance_v6.py`:

```python
# S4-05 .. S4-08
for tool, fixture in [
    ("read_word_document", "sample.docx"),
    ("read_excel", "sample.xlsx"),
    ("read_powerpoint", "sample.pptx"),
    ("read_pdf", "sample.pdf"),
]:
    t0 = time.monotonic()
    try:
        result = await _mcp("documents", tool, {"file_path": f"tests/fixtures/{fixture}"})
        if result and "content" in result:
            record("S4", f"S4-0{n}", f"MCP {tool}", "PASS",
                   f"got {len(result['content'])} chars from {fixture}", t0=t0)
        else:
            record("S4", f"S4-0{n}", f"MCP {tool}", "FAIL", "empty result", t0=t0)
    except FileNotFoundError:
        record("S4", f"S4-0{n}", f"MCP {tool}", "SKIP", f"fixture {fixture} missing", t0=t0)
    except Exception as e:
        record("S4", f"S4-0{n}", f"MCP {tool}", "FAIL", str(e)[:120], t0=t0)
```

Add `tests/fixtures/sample.xlsx`, `sample.pptx`, `sample.pdf` (small files, ~1KB each).

### Commit
```
test(acceptance): cover document MCP read tools (S4-05..S4-08)

portal_mcp/documents/document_mcp.py implements read_word_document,
read_excel, read_powerpoint, read_pdf but the acceptance harness
exercised only the create_* paths. Adds round-trip tests using
fixture files in tests/fixtures/.
```

---

## Task 2.11 — State file delta semantics + locking (REL-11 + REL-12)

**Rationale.** `_save_state` reads file → adds in-memory totals → writes back, but never resets in-memory after writing. Each save adds the cumulative-since-process-start totals on top of the file's existing values. Over T saves with N in-memory total, file shows ~N×T. With saves every 60s and 1 worker, daily summary deltas inflate by ~1440×.

Compounded by REL-12: read-merge-write isn't atomic across the read+write boundary. With multiple workers, last-write-wins loses deltas.

The notification scheduler (`notifications/scheduler.py:251 _send_daily_summary`) reads exactly this file as its source of truth. Daily summary numbers users see are consequently nondeterministic *and* inflated.

**Two parts to the fix:**

**(a) Delta semantics.** After each successful `_save_state`, reset in-memory accumulators to 0. The next save then adds only the new delta since the previous save.

**(b) File locking.** Wrap the read-merge-write block in `fcntl.flock(LOCK_EX)` so concurrent workers serialize. The combined operation becomes atomic.

**Before** (`portal_pipeline/router_pipe.py:117-171`):
```python
def _save_state() -> None:
    """Persist current metrics state to disk.

    With multiple workers, each process has its own in-memory counters.
    On save we read the existing file, merge our counters into it (sum for
    accumulators, max for peak), and write back atomically.
    """
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing: dict = {}
        if _STATE_FILE.exists():
            with suppress(json.JSONDecodeError, OSError):
                existing = json.loads(_STATE_FILE.read_text())

        merged = {
            "request_count": dict(existing.get("request_count", {})),
            "total_response_time_ms": float(existing.get("total_response_time_ms", 0.0)) + _total_response_time_ms,
            ...
        }
        for ws, count in _request_count.items():
            merged["request_count"][ws] = merged["request_count"].get(ws, 0) + count
        ...

        tmp = _STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(merged))
        tmp.rename(_STATE_FILE)
    except Exception as e:
        logger.debug("Failed to persist metrics state: %s", e)
```

**After:**
```python
import fcntl  # at top of module

def _save_state() -> None:
    """Persist current metrics state to disk with delta semantics.

    Cross-worker correctness:
      1. Acquire exclusive flock on a sidecar lockfile (serialises all workers).
      2. Read the file, add this worker's in-memory delta, write atomically.
      3. Reset in-memory accumulators to 0 — the delta has been persisted.
    The reset is critical: without it, every subsequent save re-adds the same
    cumulative totals on top of the file, inflating values by ~saves_per_day.
    Only `peak_concurrent` uses max() rather than addition — it survives the
    reset and accumulates correctly across saves.
    """
    global _total_response_time_ms, _total_tps, _request_tps_count
    global _total_input_tokens, _total_output_tokens
    global _request_count, _req_count_by_model, _req_count_by_error, _persona_usage_raw
    global _peak_concurrent

    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        lock_file = _STATE_FILE.with_suffix(".lock")
        with open(lock_file, "w") as lf:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            try:
                existing: dict = {}
                if _STATE_FILE.exists():
                    with suppress(json.JSONDecodeError, OSError):
                        existing = json.loads(_STATE_FILE.read_text())

                merged = {
                    "request_count": dict(existing.get("request_count", {})),
                    "total_response_time_ms": float(existing.get("total_response_time_ms", 0.0)) + _total_response_time_ms,
                    "total_tps": float(existing.get("total_tps", 0.0)) + _total_tps,
                    "request_tps_count": int(existing.get("request_tps_count", 0)) + _request_tps_count,
                    "total_input_tokens": int(existing.get("total_input_tokens", 0)) + _total_input_tokens,
                    "total_output_tokens": int(existing.get("total_output_tokens", 0)) + _total_output_tokens,
                    "req_count_by_model": dict(existing.get("req_count_by_model", {})),
                    "req_count_by_error": dict(existing.get("req_count_by_error", {})),
                    "peak_concurrent": max(int(existing.get("peak_concurrent", 0)), _peak_concurrent),
                    "persona_usage_raw": dict(existing.get("persona_usage_raw", {})),
                }
                for ws, count in _request_count.items():
                    merged["request_count"][ws] = merged["request_count"].get(ws, 0) + count
                for model, count in _req_count_by_model.items():
                    merged["req_count_by_model"][model] = merged["req_count_by_model"].get(model, 0) + count
                for err_type, count in _req_count_by_error.items():
                    merged["req_count_by_error"][err_type] = merged["req_count_by_error"].get(err_type, 0) + count
                for persona, models in _persona_usage_raw.items():
                    if persona not in merged["persona_usage_raw"]:
                        merged["persona_usage_raw"][persona] = {}
                    for model, count in models.items():
                        merged["persona_usage_raw"][persona][model] = (
                            merged["persona_usage_raw"][persona].get(model, 0) + count
                        )

                tmp = _STATE_FILE.with_suffix(".tmp")
                tmp.write_text(json.dumps(merged))
                tmp.rename(_STATE_FILE)

                # CRITICAL: reset in-memory accumulators after successful persist.
                # The delta is now in the file. Re-summing in-memory on the next
                # save would double-count.
                _total_response_time_ms = 0.0
                _total_tps = 0.0
                _request_tps_count = 0
                _total_input_tokens = 0
                _total_output_tokens = 0
                _request_count.clear()
                _req_count_by_model.clear()
                _req_count_by_error.clear()
                _persona_usage_raw.clear()
                # peak_concurrent is NOT reset — it uses max() and represents
                # an all-time peak that should survive across save cycles.
            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
    except Exception as e:
        logger.debug("Failed to persist metrics state: %s", e)
```

**Tests.** Add `tests/unit/test_state_persistence.py`:

```python
"""Verify _save_state delta semantics and concurrent-worker correctness."""

import json
import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_save_state_resets_in_memory_after_persist(tmp_path):
    """In-memory counters must be 0 after successful save."""
    state_file = tmp_path / "metrics_state.json"
    with patch.dict(os.environ, {"METRICS_STATE_FILE": str(state_file)}):
        # Force re-import so _STATE_FILE picks up env override
        import importlib
        import portal_pipeline.router_pipe as rp
        importlib.reload(rp)

        rp._total_tps = 100.0
        rp._request_tps_count = 5
        rp._save_state()

        # File now contains the totals
        data = json.loads(state_file.read_text())
        assert data["total_tps"] == 100.0
        assert data["request_tps_count"] == 5

        # In-memory must be reset
        assert rp._total_tps == 0.0
        assert rp._request_tps_count == 0


def test_save_state_no_double_counting(tmp_path):
    """Three save cycles with no new in-memory activity must not inflate the file."""
    state_file = tmp_path / "metrics_state.json"
    with patch.dict(os.environ, {"METRICS_STATE_FILE": str(state_file)}):
        import importlib
        import portal_pipeline.router_pipe as rp
        importlib.reload(rp)

        rp._total_tps = 100.0
        rp._request_tps_count = 5

        rp._save_state()  # writes 100, in-memory → 0
        rp._save_state()  # writes 100+0=100, in-memory still 0
        rp._save_state()  # writes 100+0=100

        data = json.loads(state_file.read_text())
        assert data["total_tps"] == 100.0  # NOT 300
        assert data["request_tps_count"] == 5


def test_save_state_concurrent_workers_serialize(tmp_path):
    """flock prevents lost-update race between concurrent saves."""
    # This requires a multiprocess test; for a unit test, just verify the
    # lockfile is created and flock is called.
    state_file = tmp_path / "metrics_state.json"
    with patch.dict(os.environ, {"METRICS_STATE_FILE": str(state_file)}):
        import importlib
        import portal_pipeline.router_pipe as rp
        importlib.reload(rp)

        rp._total_tps = 50.0
        rp._save_state()

        lock_file = state_file.with_suffix(".lock")
        assert lock_file.exists(), "lockfile must be created"
```

**Schema migration consideration.** Existing state files are inflated. After deploying this fix, the daily summary will compute deltas against the inflated baseline snapshot — first day post-fix may show wildly negative deltas (clamped to 0 by `_delta()`). Either:
- Delete the snapshot file once on deploy: `rm -f /app/data/daily_summary_snapshot.json` so the scheduler re-baselines on next startup.
- Document this in the commit message.

**Verify.**
```bash
pytest tests/unit/test_state_persistence.py -v

# Live: PIPELINE_WORKERS=4, generate 100 requests, wait 5 minutes (5 save cycles),
# inspect the state file. Counters should reflect 100 requests, not 500+.
cat /app/data/metrics_state.json | jq '.total_tps, .request_tps_count'
```

**Rollback:** `git checkout portal_pipeline/router_pipe.py`. Optionally delete `/app/data/daily_summary_snapshot.json` and `/app/data/metrics_state.json` to clear inflated history.

**Commit:**
```
fix(metrics): state file delta semantics and cross-worker locking

_save_state added in-memory accumulators to file totals every save
cycle but never reset the in-memory counters. Subsequent saves
re-added the same cumulative totals on top of the file, inflating
values linearly per save cycle (~1440× per worker per day at default
60s save interval).

The notification scheduler reads exactly this file as its source of
truth for daily summary deltas, so the inflation directly distorted
the numbers users saw. Prometheus multiprocess metrics were unaffected
(separate aggregation mechanism).

Compounded by a TOCTOU race: the read-merge-write block was not
atomic across the read+write boundary, so concurrent workers could
lose deltas to last-write-wins.

Fix:
  1. Wrap read-merge-write in fcntl.flock(LOCK_EX) on a sidecar
     lockfile, serialising all workers.
  2. Reset in-memory accumulators to 0 after each successful persist.
     peak_concurrent is excluded from the reset (uses max() and
     represents all-time peak).

Operators should `rm /app/data/daily_summary_snapshot.json` on deploy
to clear the inflated baseline; the next daily summary will re-baseline
from the corrected state file.

Resolves: REL-11, REL-12
```

---

## Task 2.12 — Fix `install-music` PORTAL_ROOT path resolution (REL-14)

**Rationale.** The music-mcp start.sh template at `launch.sh:2686` hardcodes:

```bash
PORTAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../projects/portal-5" 2>/dev/null && pwd)"
```

This assumes the repo lives at `$HOME/projects/portal-5`. The fallback at line 2689 runs `git rev-parse --show-toplevel` from `$HOME/.portal5/music/`, which isn't a git checkout — so it always fails.

**Better approach:** since `install-music` knows `$PORTAL_ROOT` at install time (line 3 of launch.sh sets it), bake the resolved path into the start.sh as a literal:

**Before** (`launch.sh:2683-2698`):
```bash
    cat > "$MUSIC_DIR/start.sh" << MUSIC_START
#!/bin/bash
# Start Music MCP natively for MPS acceleration on Apple Silicon
PORTAL_ROOT="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")/../../projects/portal-5" 2>/dev/null && pwd)"
# Fallback: walk up to find portal_mcp
if [ ! -d "\$PORTAL_ROOT/portal_mcp" ]; then
    PORTAL_ROOT="\$(python3 -c "import subprocess, os; r=subprocess.run(['git','-C',os.path.dirname(os.path.abspath('\$0')),  'rev-parse','--show-toplevel'],capture_output=True,text=True); print(r.stdout.strip())" 2>/dev/null)"
fi
export PYTHONPATH="\$PORTAL_ROOT"
export HF_HOME="${HF_CACHE}"
export TRANSFORMERS_CACHE="${HF_CACHE}"
export OUTPUT_DIR="\${AI_OUTPUT_DIR:-\$HOME/AI_Output}"
export MUSIC_MCP_PORT="${MUSIC_PORT}"
mkdir -p "\$OUTPUT_DIR"
exec "$MUSIC_VENV/bin/python" -m portal_mcp.generation.music_mcp
MUSIC_START
```

**After:**
```bash
    cat > "$MUSIC_DIR/start.sh" << MUSIC_START
#!/bin/bash
# Start Music MCP natively for MPS acceleration on Apple Silicon.
# PORTAL_ROOT is baked at install-music time — re-run install-music
# if the portal-5 repo moves.
PORTAL_ROOT="${PORTAL_ROOT}"
if [ ! -d "\$PORTAL_ROOT/portal_mcp" ]; then
    echo "ERROR: PORTAL_ROOT=\$PORTAL_ROOT no longer contains portal_mcp/" >&2
    echo "Re-run: ./launch.sh install-music" >&2
    exit 1
fi
export PYTHONPATH="\$PORTAL_ROOT"
export HF_HOME="${HF_CACHE}"
export TRANSFORMERS_CACHE="${HF_CACHE}"
export OUTPUT_DIR="\${AI_OUTPUT_DIR:-\$HOME/AI_Output}"
export MUSIC_MCP_PORT="${MUSIC_PORT}"
mkdir -p "\$OUTPUT_DIR"
exec "$MUSIC_VENV/bin/python" -m portal_mcp.generation.music_mcp
MUSIC_START
```

**Verify.**
```bash
# After install-music:
cat ~/.portal5/music/start.sh | grep PORTAL_ROOT=
# Expected: PORTAL_ROOT="<the actual install path>" (baked)

# Move repo, run start.sh manually:
# Expected: clear error message, exits 1
```

**Rollback:** `git checkout launch.sh`

**Commit:**
```
fix(launch): bake PORTAL_ROOT into install-music start.sh

The music-mcp start.sh used a brittle relative-path resolution that
hardcoded $HOME/projects/portal-5 as the expected install location.
The git-rev-parse fallback ran from ~/.portal5/music/ — which is not
a git checkout — so it always failed. Any user with the repo at a
different path saw an empty PORTAL_ROOT and a broken music MCP.

Bakes the resolved path at install-music time. On repo move the
operator gets a clear error pointing them at install-music to refresh.

Resolves: REL-14
```

---

## Phase 2 — Full verification

```bash
set -e

echo "── Phase 1 invariants still hold ──"
PIPELINE_API_KEY=test python3 -c "
import yaml
from portal_pipeline.router_pipe import WORKSPACES, _validate_workspace_hints
from portal_pipeline.cluster_backends import BackendRegistry
errors = _validate_workspace_hints(BackendRegistry())
assert not errors, errors
print('OK')
"

echo "── New unit tests pass ──"
pytest tests/unit/ -q --tb=short

echo "── Acceptance S1 includes hint check ──"
python3 tests/portal5_acceptance_v6.py --section S1 2>&1 | grep -q 'S1-17' && echo OK

echo "── Strict mode trips on bad hint ──"
python3 -c "
import os, subprocess
# Temporarily insert a bad hint
import portal_pipeline.router_pipe as r
saved = r.WORKSPACES['auto-coding'].copy()
r.WORKSPACES['auto-coding']['mlx_model_hint'] = 'bogus/model'
from portal_pipeline.cluster_backends import BackendRegistry
errors = r._validate_workspace_hints(BackendRegistry())
assert len(errors) >= 1
r.WORKSPACES['auto-coding'] = saved
print('OK: validator catches bad hint')
"

echo "── Phase 2 verification PASSED ──"
```

---

## Phase 2 — Rollback

```bash
git reset --hard pre-phase2-fixes
git tag -d pre-phase2-fixes
```

---

## Total scope

| Task | Files | Lines | Effort |
|---|---|---|---|
| 2.1 hint validator | router_pipe.py + new test | ~80 | 2h |
| 2.2 S1-17 acceptance | portal5_acceptance_v6.py | ~15 | 30m |
| 2.3 tool backoff | tool_registry.py + new test | ~80 | 2h |
| 2.4 persona seed validation | openwebui_init.py | ~40 | 1h |
| 2.5 bench TTFT + memory | bench_tps.py | ~50 | 1.5h |
| 2.6 error classifier | portal5_acceptance_v6.py | ~50 | 1h |
| 2.7 acceptance test split | many files | ~4000 (move) | 4h |
| 2.8 VLM admission verify | mlx-proxy.py + test | ~30 | 1h |
| 2.9 README sync target | launch.sh | ~30 | 30m |
| 2.10 doc MCP read tests | acceptance + fixtures | ~30 | 1h |
| 2.11 state file delta + locking | router_pipe.py + new test | ~60 | 2.5h |
| 2.12 install-music PORTAL_ROOT bake | launch.sh | ~10 | 30m |

**Total: ~17 hours of focused work, ~14 commits.**

— end of Phase 2 —
