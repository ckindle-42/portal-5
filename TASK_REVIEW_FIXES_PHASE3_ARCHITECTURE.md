# TASK_REVIEW_FIXES_PHASE3_ARCHITECTURE.md

**Source review:** `PORTAL5_REVIEW_V6.0.3.md`
**Phase:** 3 of 3 — Architectural improvements
**Target version:** 7.0.0 (breaking change for `mlx-proxy.py` config flow)
**Estimated effort:** 4-6 days total
**Prerequisite:** Phases 1 and 2 merged.
**Risk:** High — these are structural changes to inference, routing, and test infrastructure. Each task is independently revertible but should land sequentially with operator validation between them.

---

## Scope

Phase 3 addresses the structural causes of bugs that Phases 1 and 2 patched symptomatically:

- **REL-02, REL-03, REL-05** all stem from CLAUDE.md Rule 8 being violated: model registry hardcoded in Python instead of read from `backends.yaml`. Task 3.1 consolidates.
- **ARCH-02 (workspace ID duplication)** stems from `_VALID_WORKSPACE_IDS` and `_ROUTER_JSON_SCHEMA` enum being independent of `WORKSPACES`. Task 3.2 derives them.
- **ARCH-05 (two watchdogs)** stems from incremental layering. Task 3.3 consolidates.
- **Maintainability of router_pipe.py (3,338 lines)**. Task 3.4 splits it.
- **Tool-call cliff on MLX (Section 3.6 of review)**. Task 3.5 closes it.
- **UAT signal calibration** (memory note: "calibration must precede automation"). Task 3.7 builds the calibration mode.

**Branch strategy:** each task on its own feature branch, merged to main only after live operator validation. Phase 3 is the only phase that requires version bump to 7.0.0 because Task 3.1 changes `backends.yaml` schema (additive, but the migration is non-trivial).

---

## Pre-flight

```bash
git tag pre-phase3-architecture
pytest tests/unit/ -q
```

---

## Task 3.1 — Single-source MLX model registry (LA-01)

### Rationale
CLAUDE.md Rule 8: "Do NOT hardcode model names in Python — they come from `backends.yaml` or persona YAMLs." Currently `mlx-proxy.py` violates this with four hand-maintained Python collections:
- `MODEL_MEMORY` (dict, ~30 entries) — memory budget per model
- `BIG_MODEL_SET` (set, ~3 entries) — models requiring full-evict load
- `VLM_MODELS` (set, ~7 entries) — models requiring `mlx_vlm.server`
- `ALL_MODELS` (list, ~30 entries) — registered model catalog

Every model addition requires editing two files; every divergence is a latent bug (REL-05 was such a divergence).

### Strategy
Extend `backends.yaml` MLX model entries with structured metadata. Make `mlx-proxy.py` read it.

### Schema change

**Before** (`config/backends.yaml`):
```yaml
- id: mlx-apple-silicon
  type: mlx
  url: "${MLX_LM_URL:-http://host.docker.internal:8081}"
  group: mlx
  models:
    - mlx-community/Qwen3-Coder-Next-4bit
    - mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit
    # ... 24 more
```

**After:**
```yaml
- id: mlx-apple-silicon
  type: mlx
  url: "${MLX_LM_URL:-http://host.docker.internal:8081}"
  group: mlx
  # New canonical form. Old `models: [list of strings]` continues to work
  # but every entry should migrate to the dict form below.
  mlx_models:
    - id: mlx-community/Qwen3-Coder-Next-4bit
      memory_gb: 46
      big_model: true
      is_vlm: false
      notes: "80B MoE 4bit, ~46GB, BIG_MODEL — auto-agentic primary"
    - id: mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit
      memory_gb: 22
      big_model: false
      is_vlm: false
      notes: "30B MoE 3B-active, ~22GB"
    - id: mlx-community/Qwen3-VL-32B-Instruct-8bit
      memory_gb: 36
      big_model: true
      is_vlm: true
      notes: "Qwen3-VL 32B, ~36GB, VLM"
    # ... 24 more entries
  # Drop-in compatibility: `models` is auto-derived as [m['id'] for m in mlx_models]
  # so cluster_backends.py (which reads `models`) continues to work without change.
```

### Migration helper

```bash
# scripts/migrate_backends_yaml.py — one-shot script
"""Migrate MLX backend entries from `models: [str]` to `mlx_models: [dict]` form.

Reads MODEL_MEMORY, BIG_MODEL_SET, VLM_MODELS from mlx-proxy.py and emits
the structured form. Run once, review output, commit.
"""
import yaml, re, sys
from pathlib import Path

# Parse hardcoded constants from mlx-proxy.py
mp = Path("scripts/mlx-proxy.py").read_text()

mm_match = re.search(r'MODEL_MEMORY: dict\[str, float\] = \{(.*?)^\}', mp, re.DOTALL | re.MULTILINE)
model_memory = dict(re.findall(r'"([^"]+)":\s*([\d.]+)', mm_match.group(1)))
model_memory = {k: float(v) for k, v in model_memory.items()}

vlm_match = re.search(r'VLM_MODELS = \{(.*?)\}', mp, re.DOTALL)
vlm_models = set(re.findall(r'"([^"]+)"', vlm_match.group(1)))
# VLM_MODELS uses bare names; need to map to full HF paths via ALL_MODELS prefix matching

bm_match = re.search(r'BIG_MODEL_SET: set\[str\] = \{(.*?)\}', mp, re.DOTALL)
big_models = set(re.findall(r'"([^"]+)"', bm_match.group(1)))

cfg = yaml.safe_load(Path("config/backends.yaml").read_text())
mlx_be = next(b for b in cfg["backends"] if b["type"] == "mlx")
old_models = mlx_be["models"]

new_mlx_models = []
for m in old_models:
    suffix = m.rsplit("/", 1)[-1]
    new_mlx_models.append({
        "id": m,
        "memory_gb": model_memory.get(m, 20.0),
        "big_model": m in big_models,
        "is_vlm": suffix in vlm_models,
    })

mlx_be["mlx_models"] = new_mlx_models
del mlx_be["models"]  # canonical from now on

# Write back, preserving comments where possible
# (manual review still required — yaml.dump strips comments)
print(yaml.dump(cfg, sort_keys=False, default_flow_style=False))
```

### Code change in `cluster_backends.py`

```python
# In _load_config(), before the Backend object construction:
        for be in cfg.get("backends", []):
            # Backwards-compat: accept either `models: [str]` or `mlx_models: [dict]`
            if "mlx_models" in be:
                be["models"] = [m["id"] for m in be["mlx_models"]]
            backend = Backend(
                id=be["id"],
                type=be.get("type", "ollama"),
                url=be["url"],
                group=be.get("group", "general"),
                models=be.get("models", []),
            )
            # Optional: store the rich form for downstream use
            backend._raw_mlx_metadata = be.get("mlx_models", [])
```

### Code change in `mlx-proxy.py`

Replace the hardcoded constants with a loader called once at startup:

```python
def _load_mlx_metadata() -> tuple[dict[str, float], set[str], set[str], list[str]]:
    """Load MODEL_MEMORY, BIG_MODEL_SET, VLM_MODELS, ALL_MODELS from backends.yaml."""
    cfg = yaml.safe_load(open(_backends_yaml_path()).read())
    mlx_be = next((b for b in cfg["backends"] if b["type"] == "mlx"), None)
    if not mlx_be:
        return {}, set(), set(), []

    items = mlx_be.get("mlx_models", [])
    if not items:
        # Backwards-compat: degrade to id-only (no memory data)
        return {}, set(), set(), mlx_be.get("models", [])

    model_memory = {it["id"]: float(it.get("memory_gb", 20.0)) for it in items}
    big_models = {it["id"] for it in items if it.get("big_model")}
    vlm_models = {it["id"].rsplit("/", 1)[-1] for it in items if it.get("is_vlm")}
    all_models = [it["id"] for it in items]
    return model_memory, big_models, vlm_models, all_models


# Replace the hardcoded MODEL_MEMORY, BIG_MODEL_SET, VLM_MODELS, ALL_MODELS literals
# with the loader call:
MODEL_MEMORY, BIG_MODEL_SET, VLM_MODELS, ALL_MODELS = _load_mlx_metadata()

# Print summary at startup
print(f"[proxy] loaded {len(MODEL_MEMORY)} MLX models from backends.yaml "
      f"({len(BIG_MODEL_SET)} big, {len(VLM_MODELS)} VLM)", flush=True)
```

### Verify
```bash
# 1. Migration produces valid yaml
python3 scripts/migrate_backends_yaml.py > /tmp/new.yaml
python3 -c "import yaml; yaml.safe_load(open('/tmp/new.yaml'))"

# 2. Old code still loads (backwards compat)
git stash  # keep migration uncommitted
PIPELINE_API_KEY=test python3 -m portal_pipeline 2>&1 | head -5
git stash pop

# 3. After migration, MODEL_MEMORY in mlx-proxy.py is empty/auto-loaded
grep -A1 'MODEL_MEMORY: dict\[str, float\] = ' scripts/mlx-proxy.py | head -2
# Expected: assignment to function call result, not literal dict

# 4. Round-trip: load yaml, write yaml, load again — should be idempotent
```

### Commit (multi-step)
```
1. feat(config): add mlx_models structured form to backends.yaml schema
   (additive, accepts both forms; cluster_backends.py auto-flattens)

2. chore: migrate MLX entries to mlx_models structured form
   (one commit per `mlx-proxy.py` constant — MODEL_MEMORY, BIG_MODEL_SET,
   VLM_MODELS, ALL_MODELS — pulled from yaml; old literals deleted)

3. docs(claude): update Rule 8 — model registry now lives in backends.yaml only
```

---

## Task 3.2 — Workspace ID derivation (LA-02)

### Rationale
`router_pipe.py:1345-1399` declares `_VALID_WORKSPACE_IDS` (frozenset) and `_ROUTER_JSON_SCHEMA["properties"]["workspace"]["enum"]` (list) — two parallel hardcoded lists of 18 workspace IDs that must stay in sync.

### Action
Replace both with derivations from `WORKSPACES`:

```python
# portal_pipeline/router_pipe.py — replace frozenset declaration

# Valid workspace IDs the LLM router may return.
# Derived from WORKSPACES, excluding bench-* (those are user-selected only,
# never auto-routed to). Updates automatically when WORKSPACES changes.
_VALID_WORKSPACE_IDS: frozenset[str] = frozenset(
    k for k in WORKSPACES.keys() if not k.startswith("bench-")
)

# Same for the JSON schema — built lazily because WORKSPACES isn't fully
# populated at module load time on first import (workspace dict literal
# still being parsed). Use a function.
def _build_router_json_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "workspace": {
                "type": "string",
                "enum": sorted(_VALID_WORKSPACE_IDS),
            },
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        },
        "required": ["workspace", "confidence"],
    }

_ROUTER_JSON_SCHEMA: dict = _build_router_json_schema()
```

### Verify
```bash
PIPELINE_API_KEY=test python3 -c "
from portal_pipeline.router_pipe import (
    WORKSPACES, _VALID_WORKSPACE_IDS, _ROUTER_JSON_SCHEMA
)
expected = {k for k in WORKSPACES if not k.startswith('bench-')}
assert _VALID_WORKSPACE_IDS == expected
assert set(_ROUTER_JSON_SCHEMA['properties']['workspace']['enum']) == expected
print('OK: derived from WORKSPACES, count =', len(expected))
"
```

### Commit
```
refactor(routing): derive _VALID_WORKSPACE_IDS from WORKSPACES dict

Two parallel hardcoded lists (_VALID_WORKSPACE_IDS frozenset and
_ROUTER_JSON_SCHEMA enum) had to be kept in sync with the WORKSPACES
dict — and with each other. Adding a workspace required edits in three
places. Now both derive from WORKSPACES (excluding bench-* which are
user-selected, never auto-routed). One source, no drift.

Resolves: ARCH-02
```

---

## Task 3.3 — Watchdog consolidation (LA-03)

### Rationale
Two watchdogs run side-by-side:
- In-process `_watchdog_loop` thread inside `mlx-proxy.py` (15s interval, zombie cleanup, state reset)
- External `mlx-watchdog.py` daemon under launchd (30s interval, process restart, notifications)

They overlap on zombie detection (both `pgrep` + `/health` probe, both `SIGTERM/SIGKILL`). The redundancy is benign (`ProcessLookupError` on second kill is silently caught) but creates two places to debug.

### Strategy: Keep external watchdog as canonical. Reduce in-process loop to memory sampling only.

### Action

**A.** In `mlx-proxy.py`, strip `_cleanup_zombie_servers` and the consecutive-failures recovery path from `_watchdog_loop`. Leave only:
- Periodic `_probe_server` to update `mlx_state` (for `/health` accuracy)
- Memory sampling (`memory_monitor.sample()` every 60s)

**B.** In `mlx-watchdog.py`, ensure it owns: zombie cleanup, process restart, notifications, recovery threshold counters.

**C.** Document the split in `docs/ADMIN_GUIDE.md`:
> The MLX subsystem has two health monitors:
> 1. **In-process probe** (mlx-proxy.py) — keeps the proxy's `/health` endpoint accurate; samples GPU memory.
> 2. **External daemon** (mlx-watchdog.py via launchd) — handles zombie cleanup, process restart, and notifications. This is the canonical recovery layer.

### Verify
```bash
# 1. mlx-proxy.py no longer kills processes
! grep -E 'pkill|SIGTERM|SIGKILL|_cleanup_zombie_servers' scripts/mlx-proxy.py | grep -v '^#' && echo OK

# 2. mlx-watchdog.py still has full recovery logic
grep -E 'SIGTERM|SIGKILL|recovery_attempts|consecutive_failures' scripts/mlx-watchdog.py | wc -l
# Expected: > 5 (recovery still owned here)

# 3. Live test (manual): kill mlx_lm.server forcibly
# Expect: mlx-watchdog.py picks it up within 30s, restarts proxy, notifies
```

### Commit
```
refactor(mlx): consolidate watchdog logic into external daemon

Two watchdogs ran side-by-side (in-process thread + launchd daemon)
with overlapping zombie cleanup. Reduces in-process _watchdog_loop to
memory sampling and probe-based state updates only. The external
mlx-watchdog.py owns zombie kill, process restart, and notifications.
Documents the split in ADMIN_GUIDE.md.

Resolves: ARCH-05
```

---

## Task 3.4 — `router_pipe.py` decomposition (LA-04)

### Rationale
3,338 lines in one file. Split into a small package preserving the public API (`from portal_pipeline.router_pipe import app, WORKSPACES`).

### Target layout

```
portal_pipeline/
├── __init__.py
├── __main__.py            # unchanged
├── cluster_backends.py    # unchanged
├── tool_registry.py       # unchanged
├── notifications/         # unchanged
└── router/
    ├── __init__.py        # re-exports app, WORKSPACES, lifespan, etc.
    ├── workspaces.py      # WORKSPACES dict + _resolve_persona_tools/_browser_policy
    ├── routing.py         # _route_with_llm, _detect_workspace, _build_router_prompt, _load_routing_config
    ├── streaming.py       # _stream_with_tool_loop, _stream_with_preamble, _stream_from_backend_guarded
    ├── tools.py           # _dispatch_tool_call (the chat-completions side; tool_registry.py stays separate)
    ├── auth.py            # _verify_key, _verify_admin_key, semaphore helpers
    ├── metrics.py         # Prometheus registry + counters + histograms + state save/load
    ├── lifespan.py        # lifespan async context manager + startup warmups
    └── app.py             # FastAPI app + endpoint handlers (chat_completions, list_models, /health, /metrics, admin_*)
```

`portal_pipeline/router_pipe.py` becomes a compatibility shim:
```python
"""Compat shim for older imports. Prefer `from portal_pipeline.router import app`."""
from portal_pipeline.router.app import app
from portal_pipeline.router.workspaces import WORKSPACES
# ... re-export anything else still imported by external code
```

### Verify
- All existing imports keep working: `pytest tests/unit/ -q`
- `portal-pipeline` Docker image still starts: `./launch.sh rebuild && ./launch.sh up`
- `/v1/models`, `/v1/chat/completions`, `/health`, `/metrics` all respond as before

### Commits (one per module move, ~8 commits)
```
1. refactor(router): extract workspaces.py from router_pipe
2. refactor(router): extract routing.py (LLM router + keyword scorer)
3. refactor(router): extract streaming.py (3 streaming functions)
4. refactor(router): extract tools.py (_dispatch_tool_call)
5. refactor(router): extract auth.py (_verify_key + semaphores)
6. refactor(router): extract metrics.py (Prometheus + state save)
7. refactor(router): extract lifespan.py + app.py
8. refactor(router): collapse router_pipe.py to compat shim
```

---

## Task 3.5 — Tool calls on MLX (LA-05)

### Rationale
`router_pipe.py:2597`: `_has_tools = bool(effective_tools) and backend.type == "ollama"`. MLX backends never get tool calls in the streaming path. Most workspaces have MLX as primary route (`workspace_routing` lists `[mlx, ...]`), so the tool whitelist on `auto-coding`/`auto-agentic`/`auto-documents`/`auto-vision` is effectively dead code on the happy path.

### Constraint
mlx_lm 0.31+ supports OpenAI-compatible `tools` parameter. mlx_vlm support is uneven.

### Action

**A.** Identify which MLX models support tool calls (model card check or live probe).

**B.** Mark per-model in `backends.yaml`:
```yaml
- id: mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit
  memory_gb: 22
  big_model: false
  is_vlm: false
  supports_tools: true
- id: mlx-community/Llama-3.2-3B-Instruct-8bit
  memory_gb: 3
  supports_tools: true  # Llama-3 supports tool_use natively
- id: mlx-community/Qwen3-VL-32B-Instruct-8bit
  is_vlm: true
  supports_tools: false  # VLM tool support not stable in mlx_vlm
```

**C.** Read it in router:
```python
# router_pipe.py — chat_completions section
# was:  _has_tools = bool(effective_tools) and backend.type == "ollama"
# new:
backend_supports_tools = (
    backend.type == "ollama"
    or (backend.type == "mlx" and _model_supports_tools(target_model))
)
_has_tools = bool(effective_tools) and backend_supports_tools
```

where `_model_supports_tools(model_id)` reads the per-model `supports_tools` flag from the loaded MLX metadata (Task 3.1 makes this trivial).

**D.** Verify mlx_lm tool-call format compatibility. mlx_lm 0.31 `chat/completions` accepts `tools` in the request body and returns `tool_calls` in the response delta — same OpenAI shape Ollama uses. The existing `_stream_with_tool_loop` Ollama-native path should not be triggered for MLX (`/v1/` is in URL); the OpenAI SSE path applies.

### Verify
```bash
# Live test against MLX with tools
curl -sN -H "Authorization: Bearer $PIPELINE_API_KEY" -H "Content-Type: application/json" \
  -d '{
    "model": "auto-coding",
    "stream": true,
    "messages": [{"role": "user", "content": "Run print(2+2) in python"}]
  }' \
  http://localhost:9099/v1/chat/completions | head -50
# Expected: stream contains tool_calls with execute_python, then result, then completion
```

### Commit
```
feat(routing): enable tool calls on MLX backends

Tools were silently disabled whenever a workspace routed to MLX (most
workspaces, most of the time). Adds a per-model supports_tools flag to
backends.yaml and reads it in chat_completions when deciding whether
to advertise tools. mlx_lm 0.31+ accepts the OpenAI tools schema and
emits tool_calls in the same shape; mlx_vlm support is uneven so the
flag defaults to false there.

Closes: capability cliff documented in PORTAL5_REVIEW_V6.0.3.md §3.6
```

---

## Task 3.6 — Extended `/v1/models` for diagnostics (LA-06)

### Rationale
`/v1/models` returns only the 27 workspace IDs. Diagnostic tools (UAT driver, bench_tps) need to discover backend models too. They currently re-implement discovery by reading `backends.yaml` directly, duplicating the registry logic.

### Action
Add a sibling endpoint:

```python
@app.get("/v1/backends")
async def list_backends_endpoint(authorization: str | None = Header(None)) -> dict:
    """Returns the underlying backends and their models. Diagnostic-only."""
    _verify_key(authorization)
    if registry is None:
        raise HTTPException(status_code=503, detail="Backend registry not initialised")
    return {
        "object": "list",
        "data": [
            {
                "id": b.id,
                "type": b.type,
                "group": b.group,
                "url": b.url,
                "models": b.models,
                "healthy": b.healthy,
                "last_check": b.last_check,
            }
            for b in registry.list_backends()
        ],
    }
```

Update bench_tps and the UAT driver to use this endpoint instead of reading `backends.yaml` from disk.

### Commit
```
feat(api): add /v1/backends diagnostic endpoint

bench_tps and the UAT driver re-implemented backend discovery by
reading backends.yaml. Adds an authenticated /v1/backends endpoint
that returns the live BackendRegistry view (id, type, group, models,
healthy, last_check). Diagnostic tools now consume the registry
through the API like everything else.
```

---

## Task 3.7 — UAT calibration mode (LA-07)

### Rationale
Per memory: "calibration run against the live system must precede automation; building automation first just validates guesses." Current UAT tests have hand-written `assert_contains` lists that are guesses about what a good response should mention.

### Action
Add `--calibrate` mode to `portal5_uat_driver.py`:

```bash
# Run every test once, capture full responses + chat URLs
python3 tests/portal5_uat_driver.py --calibrate --output calibration.json

# Operator reviews calibration.json by hand (not all responses are good answers)
# Marks each as "good" / "bad" / "needs review" in the JSON

# Generate updated assert_* lists from the "good" responses
python3 tests/portal5_uat_driver.py --emit-signals-from calibration.json --output updated_signals.py
```

The flow:
1. Calibration run produces a structured JSON of every test → response.
2. Operator reviews and tags.
3. Signal generator extracts keywords from "good" responses (frequency analysis, weighted by inverse-document-frequency across the dataset).
4. Signal generator emits an updated `quality_signals.py` and proposed `assert_*` calls.
5. Operator commits the updated signals.

### Commits
```
1. feat(uat): add --calibrate mode for response capture
2. feat(uat): add --emit-signals-from for keyword extraction
3. docs(uat): add calibration workflow guide
```

---

## Phase 3 — Verification

```bash
echo "── 3.1: MODEL_MEMORY etc derived from yaml ──"
PIPELINE_API_KEY=test python3 -c "
from scripts.mlx_proxy import MODEL_MEMORY, BIG_MODEL_SET, VLM_MODELS  # if importable
print(f'OK: {len(MODEL_MEMORY)} models, {len(BIG_MODEL_SET)} big, {len(VLM_MODELS)} VLM')
" 2>&1 | tail -1

echo "── 3.2: workspace IDs derived from WORKSPACES ──"
PIPELINE_API_KEY=test python3 -c "
from portal_pipeline.router_pipe import WORKSPACES, _VALID_WORKSPACE_IDS
expected = {k for k in WORKSPACES if not k.startswith('bench-')}
assert _VALID_WORKSPACE_IDS == expected
print('OK')
"

echo "── 3.3: in-proc watchdog reduced to probing ──"
! grep -E 'pgrep|SIGKILL' scripts/mlx-proxy.py | grep -v '^#' && echo OK

echo "── 3.4: router decomposed ──"
ls portal_pipeline/router/*.py | wc -l
# Expected: 8+

echo "── 3.5: tools work on MLX ──"
# (Live test only)

echo "── 3.6: /v1/backends responds ──"
# (Live test only)

echo "── 3.7: --calibrate mode exists ──"
python3 tests/portal5_uat_driver.py --help 2>&1 | grep -q 'calibrate' && echo OK
```

---

## Phase 3 — Rollback

Each task is on its own branch. Roll back any task individually:
```bash
git revert <commit-hash>
```

Full rollback:
```bash
git reset --hard pre-phase3-architecture
```

---

## Total scope

| Task | Files | Lines | Effort |
|---|---|---|---|
| 3.1 single-source MLX registry | backends.yaml, mlx-proxy.py, cluster_backends.py, migration script | ~300 | 1d |
| 3.2 workspace ID derivation | router_pipe.py | ~50 | 1h |
| 3.3 watchdog consolidation | mlx-proxy.py, mlx-watchdog.py, ADMIN_GUIDE.md | ~150 | 4h |
| 3.4 router decomposition | router_pipe.py → 8 files | 3,338 (move) | 1.5d |
| 3.5 tools on MLX | backends.yaml + router_pipe.py | ~100 | 1d |
| 3.6 /v1/backends endpoint | router_pipe.py + bench_tps.py + uat_driver.py | ~80 | 4h |
| 3.7 UAT calibration | portal5_uat_driver.py + new docs | ~200 | 1d |

**Total: ~5-6 days of focused work, ~25 commits across 7 feature branches.**

---

## Cross-phase impact summary

| Review finding | Phase | Task |
|---|---|---|
| REL-01 PROMETHEUS_MULTIPROC_DIR | 1 | 1.3 |
| REL-02 auto-research hint typo | 1 | 1.1 |
| REL-03 auto-coding hint typo | 1 | 1.2 |
| REL-04 port 8918 collision | 1 | 1.4 |
| REL-05 dead MODEL_MEMORY entry | 1 | 1.5 (and 3.1 eliminates the class) |
| REL-06 streaming early-disconnect window | 1 | 1.6 (covers REL-08; REL-06 is a subset) |
| REL-07 install-mlx env sourcing | 1 | 1.13 |
| REL-08 semaphore leak | 1 | 1.6 |
| REL-09 mcp-servers.json missing entries | 1 | 1.7 |
| REL-10 stale 5.2.1 strings | 1 | 1.8 |
| ARCH-01 hardcoded MLX registry | 3 | 3.1 |
| ARCH-02 duplicated workspace IDs | 3 | 3.2 |
| ARCH-03 stale 5.2.1 docstrings | 1 | 1.8 |
| ARCH-04 model-switch lock duration | (deferred; OMLX evaluation P5-OMLX-001 may resolve) | — |
| ARCH-05 two watchdogs | 3 | 3.3 |
| ARCH-06 mlx_state encapsulation break | (low priority cleanup, fold into 3.3) | 3.3 |
| ARCH-07 sticky tool-unhealthy flag | 2 | 2.3 |
| ARCH-08 pre-first-cycle health scan | (acceptable; first health cycle ≤15s) | — |
| QW-01..10, ME-01..10, LA-01..07 | 1, 2, 3 respectively | as labeled |

— end of Phase 3 / end of three-phase plan —
