# TASK_REVIEW_FIXES_PHASE1_QUICK_WINS.md

**Source review:** `PORTAL5_REVIEW_V6.0.3.md` (independent review, 2026-04-25)
**Phase:** 1 of 3 — Confirmed defects + low-risk improvements
**Target version:** 6.0.4
**Estimated effort:** 4-6 hours total
**Risk:** Low — all fixes are surgical, programmatically verifiable, and reversible via `git checkout`

---

## Scope

This phase fixes 13 verified findings from the independent review. Every fix has:
- A specific source (file path + line number) verified by reading the code
- A programmatic test that proves it was wrong before and right after
- A rollback procedure (single `git checkout` of the touched files)

**Order matters.** Tasks are ordered so that earlier tasks unblock later verification (e.g., the hint validator in ME-01 cannot be added until QW-01/QW-02 land, since the validator would otherwise refuse to start the pipeline).

**Out of scope for Phase 1:** Architectural changes (move to Phase 3), test infrastructure changes beyond bug-fix scope (move to Phase 2).

---

## Pre-flight (run once before any task)

```bash
# Tag for rollback safety
git tag pre-phase1-fixes

# Sanity: tests pass on current HEAD
pytest tests/unit/ -q --tb=no
ruff check . 2>&1 | tail -5

# Capture current S70 acceptance state for after/before comparison
[ -f ACCEPTANCE_RESULTS.md ] && cp ACCEPTANCE_RESULTS.md ACCEPTANCE_RESULTS_BEFORE_PHASE1.md.tmp
```

---

## Task 1.1 — Fix `auto-research` mlx_model_hint typo (REL-02)

### Rationale
`router_pipe.py:652` references `Jiunsong/supergemma4-26b-uncensored-mlx-4bit-v2` which does not exist in `config/backends.yaml`. The actual model is `Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit`. The fallback `target_model = backend.models[0] if mlx_hint not in backend.models` then resolves to `mlx-community/Qwen3-Coder-Next-4bit` (the 80B BIG_MODEL coder, first in the MLX list). Result: every auto-research request triggers a 60s big-model load and is answered by a coding model. **Affects 8 personas** that route through `auto-research`. Root cause of 4 UAT FAILs that `tests/UAT_RESULTS.md` attributed to "zombie MLX state".

### Before
```python
# portal_pipeline/router_pipe.py:651-652
        "model_hint": "huihui_ai/tongyi-deepresearch-abliterated",
        "mlx_model_hint": "Jiunsong/supergemma4-26b-uncensored-mlx-4bit-v2",
```

### After
```python
# portal_pipeline/router_pipe.py:651-652
        "model_hint": "huihui_ai/tongyi-deepresearch-abliterated",
        "mlx_model_hint": "Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit",
```

### Edit
```bash
# Single-line replacement (exact strings)
python3 -c "
import re
p = 'portal_pipeline/router_pipe.py'
s = open(p).read()
old = '\"mlx_model_hint\": \"Jiunsong/supergemma4-26b-uncensored-mlx-4bit-v2\"'
new = '\"mlx_model_hint\": \"Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit\"'
assert s.count(old) == 1, f'expected 1 match, found {s.count(old)}'
open(p, 'w').write(s.replace(old, new))
print('OK: replaced 1 occurrence')
"
```

### Verify
```bash
# 1. The new hint exists in backends.yaml MLX models list
python3 -c "
import yaml
cfg = yaml.safe_load(open('config/backends.yaml'))
mlx = next(b['models'] for b in cfg['backends'] if b['type'] == 'mlx')
assert 'Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit' in mlx
print('OK: hint resolves')
"

# 2. The old broken hint is gone
! grep -q 'supergemma4-26b-uncensored-mlx-4bit-v2' portal_pipeline/router_pipe.py && echo OK

# 3. Pipeline imports cleanly
PIPELINE_API_KEY=test python3 -c "from portal_pipeline.router_pipe import WORKSPACES; assert WORKSPACES['auto-research']['mlx_model_hint'].endswith('multimodal-mlx-4bit'); print('OK')"
```

### Rollback
```bash
git checkout portal_pipeline/router_pipe.py
```

### Commit
```
fix(routing): correct auto-research MLX hint to existing model

The mlx_model_hint pointed to a model name that doesn't exist in
backends.yaml. The silent-fallback path in chat_completions resolved
target_model to the first model in the MLX list (Qwen3-Coder-Next 80B),
causing every auto-research request to load the 80GB coder and answer
research prompts with a coding model. Changes the hint to the model
that is actually in the catalog.

Resolves: REL-02 (root cause of 4 UAT FAILs in tests/UAT_RESULTS.md
2026-04-23 previously attributed to "zombie MLX state").
```

---

## Task 1.2 — Fix `auto-coding` / `auto-agentic` Ollama hint typo (REL-03)

### Rationale
`router_pipe.py:526` and `:545` reference `qwen3-coder-next:30b-q5` for the Ollama path, but no Ollama backend group lists this tag. When MLX is unavailable, both workspaces silently degrade to `qwen3.5:9b` (first in `ollama-coding` group). The closest existing tag is `qwen3-coder:30b` (62.8 TPS in latest bench).

### Before
```python
# portal_pipeline/router_pipe.py:526
        "model_hint": "qwen3-coder-next:30b-q5",
# (also at line 545 for auto-agentic)
```

### After
```python
# portal_pipeline/router_pipe.py:526 and :545
        "model_hint": "qwen3-coder:30b",
```

### Edit
```bash
python3 -c "
p = 'portal_pipeline/router_pipe.py'
s = open(p).read()
old = '\"model_hint\": \"qwen3-coder-next:30b-q5\"'
new = '\"model_hint\": \"qwen3-coder:30b\"'
n = s.count(old)
assert n == 2, f'expected 2 occurrences in auto-coding/auto-agentic, found {n}'
open(p, 'w').write(s.replace(old, new))
print(f'OK: replaced {n} occurrences')
"
```

### Verify
```bash
# 1. New hint exists in ollama-coding
python3 -c "
import yaml
cfg = yaml.safe_load(open('config/backends.yaml'))
coding = next(b['models'] for b in cfg['backends'] if b.get('group') == 'coding')
assert 'qwen3-coder:30b' in coding
print('OK')
"

# 2. Old broken hint removed
! grep -q 'qwen3-coder-next:30b-q5' portal_pipeline/router_pipe.py && echo OK

# 3. WORKSPACES still valid
PIPELINE_API_KEY=test python3 -c "
from portal_pipeline.router_pipe import WORKSPACES
assert WORKSPACES['auto-coding']['model_hint'] == 'qwen3-coder:30b'
assert WORKSPACES['auto-agentic']['model_hint'] == 'qwen3-coder:30b'
print('OK')
"
```

### Rollback
```bash
git checkout portal_pipeline/router_pipe.py
```

### Commit
```
fix(routing): correct auto-coding/auto-agentic Ollama hint

Both workspaces referenced qwen3-coder-next:30b-q5 which is not in any
Ollama backend group. The silent fallback path resolved to qwen3.5:9b
(first in ollama-coding), halving coding capability whenever MLX was
unavailable. Changes the hint to qwen3-coder:30b (existing tag,
62.8 TPS in latest bench_tps).

Resolves: REL-03
```

---

## Task 1.3 — Ensure `PROMETHEUS_MULTIPROC_DIR` exists (REL-01)

### Rationale
`router_pipe.py:2167-2174` reads `PROMETHEUS_MULTIPROC_DIR` and instantiates `MultiProcessCollector(dir)` but no code calls `os.makedirs(dir, exist_ok=True)`. The `prometheus_client` library writes per-pid files to that dir but does not create the parent. Latest `ACCEPTANCE_RESULTS.md` shows S70-07 failing with `[Errno 2] No such file or directory: '/dev/shm/portal_metrics/gauge_all_65656.db'`. Fix: ensure dir exists at startup AND lazily on first scrape.

### Before
```python
# portal_pipeline/router_pipe.py — inside metrics() at line ~2167
    mp_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if mp_dir:
        if _mp_registry_cache is None or _mp_registry_dir_cache != mp_dir:
            from prometheus_client import multiprocess

            _mp_registry_cache = CollectorRegistry()
            multiprocess.MultiProcessCollector(_mp_registry_cache)
            _mp_registry_dir_cache = mp_dir
```

### After
```python
# portal_pipeline/router_pipe.py — inside metrics() at line ~2167
    mp_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if mp_dir:
        # P5-FIX: prometheus_client writes per-pid files but does not create the
        # parent dir. Without this, the first /metrics scrape after worker fork
        # fails with errno-2 (see ACCEPTANCE_RESULTS S70-07, 2026-04-25).
        os.makedirs(mp_dir, exist_ok=True)
        if _mp_registry_cache is None or _mp_registry_dir_cache != mp_dir:
            from prometheus_client import multiprocess

            _mp_registry_cache = CollectorRegistry()
            multiprocess.MultiProcessCollector(_mp_registry_cache)
            _mp_registry_dir_cache = mp_dir
```

### Also add to `lifespan()` startup
```python
# portal_pipeline/router_pipe.py — inside lifespan() near line 1919, after _request_semaphore creation
    # P5-FIX: pre-create Prometheus multiproc dir at startup so workers don't race.
    if (mp_dir := os.environ.get("PROMETHEUS_MULTIPROC_DIR")):
        os.makedirs(mp_dir, exist_ok=True)
```

### Edit
Manual `str_replace` at both sites — old strings are unique. Recommend doing both in one commit since they're conceptually paired.

### Verify
```bash
# Cleanroom test: no manual mkdir, dir does not exist
rm -rf /tmp/test_pmp_dir
PIPELINE_API_KEY=test PROMETHEUS_MULTIPROC_DIR=/tmp/test_pmp_dir python3 -c "
import os, asyncio
from portal_pipeline.router_pipe import metrics
# Simulate worker registering a metric — would normally happen on app startup
# Instead, just verify metrics() handler creates the dir on call
assert not os.path.exists('/tmp/test_pmp_dir'), 'precondition: dir absent'
asyncio.run(metrics())
assert os.path.exists('/tmp/test_pmp_dir'), 'metrics() should have created the dir'
print('OK: dir created on metrics() call')
"

# Then run the live S70-07 acceptance:
# python3 tests/portal5_acceptance_v6.py --section S70
# Expected: S70-07 PASS
```

### Rollback
```bash
git checkout portal_pipeline/router_pipe.py
```

### Commit
```
fix(metrics): create PROMETHEUS_MULTIPROC_DIR before use

prometheus_client writes per-pid files to PROMETHEUS_MULTIPROC_DIR but
does not auto-create the directory. Worker fork + first /metrics scrape
raised errno-2 on /dev/shm/portal_metrics/gauge_all_65656.db. Adds
os.makedirs(..., exist_ok=True) at lifespan startup AND inside metrics()
so single-worker runs that bypass lifespan still work.

Resolves: REL-01 (S70-07 FAIL in ACCEPTANCE_RESULTS.md 2026-04-25)
```

---

## Task 1.4 — Resolve port 8918 collision (REL-04)

### Rationale
Three places default to host port 8918:
1. `tool_registry.py:34` — `MCP_RESEARCH_URL` default
2. `deploy/portal-5/docker-compose.yml:655` — `RESEARCH_MCP_HOST_PORT` default
3. `portal_mcp/research/web_search_mcp.py:209` — internal `RESEARCH_MCP_PORT` default

The same compose file (lines 222, 227) binds `MLX_SPEECH_URL` to host:8918 — and `mlx-speech.py` also defaults to 8918. Whichever starts first wins. Move research MCP to **8922** (8919=security, 8920=memory, 8921=rag are already taken). Update CLAUDE.md and README port tables to reflect the full speech/memory/rag/research lineup.

### Files to change

**A. `portal_pipeline/tool_registry.py:34`**
```python
# Before
    "research": os.environ.get("MCP_RESEARCH_URL", "http://localhost:8918"),
# After
    "research": os.environ.get("MCP_RESEARCH_URL", "http://localhost:8922"),
```

**B. `portal_mcp/research/web_search_mcp.py:209`**
```python
# Before
    port = int(os.environ.get("RESEARCH_MCP_PORT", "8918"))
# After
    port = int(os.environ.get("RESEARCH_MCP_PORT", "8922"))
```

Also update line 8 docstring `Port: 8918 (RESEARCH_MCP_PORT env override).` → `Port: 8922 (RESEARCH_MCP_PORT env override).`

**C. `deploy/portal-5/docker-compose.yml:655-666`** — change `8918` → `8922` in the mcp-research service block (port mapping, RESEARCH_MCP_PORT, MCP_PORT, healthcheck URL)

**D. `.env.example`** — add documented default
```
RESEARCH_MCP_HOST_PORT=8922
```

**E. `CLAUDE.md`** Rule 7 ports table — update:
| 8918 | MLX speech (Kokoro + Qwen3-TTS/ASR) |
| 8919 | MCP Security |
| 8920 | MCP Memory |
| 8921 | MCP RAG |
| 8922 | MCP Research |

**F. `README.md`** "What Starts Automatically" service table:
- Update 8 MCP Servers line to enumerate all 11
- Or add a separate "Optional Services" row for research/memory/rag at 8922/8920/8921

### Verify
```bash
# 1. No remaining 8918 outside speech context
grep -rn "8918" --include="*.py" --include="*.yaml" --include="*.yml" --include="*.md" --include="*.example" \
    portal_pipeline/ portal_mcp/ deploy/ config/ docs/ scripts/mlx-speech.py *.md \
    | grep -v 'mlx-speech\|MLX_SPEECH\|kokoro\|tts\|Speech\|speech' \
    | grep -v '8918.\(MLX\|speech\|Speech\)'
# Expected: no matches

# 2. tool_registry uses 8922
PIPELINE_API_KEY=test python3 -c "
from portal_pipeline.tool_registry import MCP_SERVERS
assert MCP_SERVERS['research'].endswith(':8922'), f'got {MCP_SERVERS[\"research\"]}'
print('OK')
"

# 3. Compose file syntactically valid
docker compose -f deploy/portal-5/docker-compose.yml config --quiet && echo OK

# 4. Live test (after restart):
# ./launch.sh down && ./launch.sh up
# curl -s http://localhost:8918/v1/voices  # → MLX speech (Kokoro voices)
# curl -s http://localhost:8922/health     # → research MCP {"status":"ok"}
# python3 tests/portal5_acceptance_v6.py --section S70  # S70-02 should PASS
```

### Rollback
```bash
git checkout portal_pipeline/tool_registry.py portal_mcp/research/web_search_mcp.py \
              deploy/portal-5/docker-compose.yml .env.example CLAUDE.md README.md
```

### Commit
```
fix(ports): move Research MCP from 8918 to 8922 to free MLX speech

Research MCP, MLX speech (Kokoro + Qwen3-TTS/ASR) both defaulted to host
port 8918. The first to start won; the second silently failed. Latest
ACCEPTANCE_RESULTS S70-02 showed Research MCP unreachable as a result.
Moves Research to 8922 (next free after security=8919, memory=8920,
rag=8921) across all four sites: tool_registry default, compose service,
web_search_mcp default, env example. Updates CLAUDE.md Rule 7 port table
and README service list to enumerate the full speech/memory/rag/research
lineup that was previously absent from the docs.

Resolves: REL-04 (S70-02 WARN in ACCEPTANCE_RESULTS.md 2026-04-25)
```

---

## Task 1.5 — Remove dead `MODEL_MEMORY` entry (REL-05)

### Rationale
`mlx-proxy.py:144` carries `mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit: 12.0`. KNOWN_LIMITATIONS P5-MLX-005 documents that this model was removed from `backends.yaml` on 2026-04-25 (gibberish output). The proxy was not updated.

### Before
```python
# scripts/mlx-proxy.py:144
    "mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit": 12.0,  # Lite 8bit (~12GB)
```

### After
Delete the entire line.

Also remove from `ALL_MODELS` list (line 70):
```python
# scripts/mlx-proxy.py:70 — delete this line
    "mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit",  # DS-Coder-V2 8bit (~12GB)
```

### Edit
```bash
python3 -c "
p = 'scripts/mlx-proxy.py'
s = open(p).read()
# remove from MODEL_MEMORY
old1 = '    \"mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit\": 12.0,  # Lite 8bit (~12GB)\n'
# remove from ALL_MODELS
old2 = '    \"mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit\",  # DS-Coder-V2 8bit (~12GB)\n'
assert s.count(old1) == 1
assert s.count(old2) == 1
s = s.replace(old1, '').replace(old2, '')
open(p, 'w').write(s)
print('OK: removed 2 lines')
"
```

### Verify
```bash
# Dead reference fully gone
! grep -q 'DeepSeek-Coder-V2-Lite-Instruct-8bit' scripts/mlx-proxy.py && echo OK

# MODEL_MEMORY count matches backends.yaml MLX list
python3 -c "
import re, yaml
cfg = yaml.safe_load(open('config/backends.yaml'))
yaml_mlx = set(b['models'] for b in cfg['backends'] if b['type']=='mlx').pop()
mp = open('scripts/mlx-proxy.py').read()
m = re.search(r'MODEL_MEMORY: dict\[str, float\] = \{(.*?)^\}', mp, re.DOTALL | re.MULTILINE)
mm = set(re.findall(r'\"([^\"]+)\":\s*[\d.]+', m.group(1)))
diff = mm - yaml_mlx
assert not diff, f'still in MODEL_MEMORY but not backends.yaml: {diff}'
print('OK: MODEL_MEMORY in sync with backends.yaml')
"
```

### Rollback
```bash
git checkout scripts/mlx-proxy.py
```

### Commit
```
chore(mlx-proxy): remove dead DeepSeek-Coder-V2-Lite entry

Model was removed from backends.yaml on 2026-04-25 (KNOWN_LIMITATIONS
P5-MLX-005, gibberish output) but remained in MODEL_MEMORY and
ALL_MODELS in mlx-proxy.py. Symptom of the broader Rule-8 violation
(model registry hardcoded in Python instead of read from yaml) — that
consolidation is in Phase 3. This task just clears the immediate stale
entry so MODEL_MEMORY matches backends.yaml.

Resolves: REL-05
```

---

## Task 1.6 — Fix semaphore leak in streaming path (REL-08, critical)

### Rationale
`_stream_with_tool_loop` (router_pipe.py:2786) accepts `sem` but **never releases it**. The function body has zero `sem.release()` calls. `_stream_with_preamble` (line 3105) does release correctly via `finally`. Worse, `chat_completions` only passes `_request_semaphore` to these stream functions; `_ws_sem` and `_api_sem` are never passed and only released in the non-streaming `finally` branch (line 2776, `if not _is_streaming`). Defaults: workspace concurrency = 5, API key concurrency = 10. Every streaming request leaks at minimum `_ws_sem` and `_api_sem`. Tool-using streaming additionally leaks `_request_semaphore`. After 5 streaming calls to one workspace, that workspace returns HTTP 429 "Workspace at concurrency limit" until pipeline restart.

### Strategy
Pass all three semaphores into both stream functions. Each must release exactly once via `finally`. Mirror the pattern `_stream_with_preamble` already uses for `sem`.

### Files

**A. `portal_pipeline/router_pipe.py:2786` — `_stream_with_tool_loop` signature**

```python
# Before
async def _stream_with_tool_loop(
    backend_url: str,
    body: dict,
    sem: asyncio.Semaphore,
    workspace_id: str,
    model: str,
    persona: str,
    effective_tools: set[str],
    start_time: float | None = None,
) -> AsyncIterator[bytes]:

# After
async def _stream_with_tool_loop(
    backend_url: str,
    body: dict,
    sem: asyncio.Semaphore,
    workspace_id: str,
    model: str,
    persona: str,
    effective_tools: set[str],
    start_time: float | None = None,
    ws_sem: asyncio.Semaphore | None = None,
    api_sem: asyncio.Semaphore | None = None,
) -> AsyncIterator[bytes]:
```

**B. Wrap entire body in try/finally** — at line 2802 (`request_id = ...`), open a try; at line 3102 (just before function returns), close with finally that releases all three sems.

```python
async def _stream_with_tool_loop(
    backend_url, body, sem, workspace_id, model, persona, effective_tools,
    start_time=None, ws_sem=None, api_sem=None,
) -> AsyncIterator[bytes]:
    """[existing docstring]"""
    try:
        request_id = f"chatcmpl-p5-{int(time.time())}"
        hop = 0
        current_body = dict(body)

        while hop < MAX_TOOL_HOPS:
            # ... entire existing body ...
            else:
                # Model finished without tool calls — done
                if start_time is not None:
                    _record_response_time(model, workspace_id, time.monotonic() - start_time)
                return
    finally:
        # Release all semaphores acquired by chat_completions on the streaming path.
        # Mirror _stream_with_preamble's pattern (single-sem release in its own finally).
        sem.release()
        if ws_sem is not None:
            ws_sem.release()
        if api_sem is not None:
            api_sem.release()
```

**C. `_stream_with_preamble` signature (line 3105) — same additions**

```python
async def _stream_with_preamble(
    url: str,
    body: dict,
    sem: asyncio.Semaphore,
    workspace_id: str = "unknown",
    model: str = "unknown",
    start_time: float | None = None,
    ws_sem: asyncio.Semaphore | None = None,
    api_sem: asyncio.Semaphore | None = None,
) -> AsyncIterator[bytes]:
```

**D. `_stream_with_preamble` finally block (line 3162-3163)**

```python
# Before
    finally:
        sem.release()

# After
    finally:
        sem.release()
        if ws_sem is not None:
            ws_sem.release()
        if api_sem is not None:
            api_sem.release()
```

**E. All four call sites in `chat_completions` — pass `_ws_sem` and `_api_sem`**

```python
# Both _stream_with_tool_loop calls (lines 2629 and 2666):
            _stream_with_tool_loop(
                backend.chat_url,
                backend_body,
                _request_semaphore,
                workspace_id,
                target_model,
                persona,
                set(effective_tools),
                start_time,
                ws_sem=_ws_sem,
                api_sem=_api_sem,
            )

# Both _stream_with_preamble calls (lines 2640 and 2677):
            _stream_with_preamble(
                backend.chat_url,
                backend_body,
                _request_semaphore,
                workspace_id=workspace_id,
                model=target_model,
                start_time=start_time,
                ws_sem=_ws_sem,
                api_sem=_api_sem,
            )
```

### Verify
```bash
# 1. Static check: every stream function call passes ws_sem and api_sem
python3 -c "
import re
s = open('portal_pipeline/router_pipe.py').read()
# Find all calls to _stream_with_tool_loop and _stream_with_preamble — should have ws_sem
calls_tl = re.findall(r'_stream_with_tool_loop\([^)]*?\)', s, re.DOTALL)
calls_pre = re.findall(r'_stream_with_preamble\([^)]*?\)', s, re.DOTALL)
# Filter out the def-site
calls_tl = [c for c in calls_tl if 'async def' not in c]
calls_pre = [c for c in calls_pre if 'async def' not in c]
for c in calls_tl + calls_pre:
    assert 'ws_sem=' in c and 'api_sem=' in c, f'missing sem args:\n{c[:120]}'
print(f'OK: {len(calls_tl)} tool_loop calls, {len(calls_pre)} preamble calls — all pass ws_sem and api_sem')
"

# 2. Static check: both stream functions have finally with three releases
python3 -c "
import re
s = open('portal_pipeline/router_pipe.py').read()
# Find each function and its finally block
for fn in ['_stream_with_tool_loop', '_stream_with_preamble']:
    # naive: find function header, then the next 'finally:' before the next 'async def'
    m = re.search(rf'async def {fn}\(.*?\n(?=async def|\Z)', s, re.DOTALL)
    assert m, f'function {fn} not found'
    body = m.group(0)
    finally_blocks = re.findall(r'finally:\s*\n(.*?)(?=\n\n|\nasync def|\nclass |\ndef )', body, re.DOTALL)
    assert any('sem.release' in fb and 'ws_sem' in fb and 'api_sem' in fb for fb in finally_blocks), \\
        f'{fn} finally block does not release all three semaphores'
    print(f'OK: {fn} has finally block releasing sem + ws_sem + api_sem')
"

# 3. Live load test (manual): hit one workspace 6 times in a row with stream=True.
# Without the fix, the 6th request returns HTTP 429.
# After the fix, all 6 succeed.
```

### Rollback
```bash
git checkout portal_pipeline/router_pipe.py
```

### Commit
```
fix(streaming): release per-workspace and per-API-key semaphores

_stream_with_tool_loop never released its semaphore; _stream_with_preamble
released only the global semaphore. The per-workspace and per-API-key
semaphores (defaults 5 and 10) were never passed to either stream
function and were released only on the non-streaming finally branch in
chat_completions. Every streaming request leaked _ws_sem and _api_sem;
every tool-using streaming request additionally leaked _request_semaphore.
After 5 streaming calls to a workspace it returned HTTP 429 until
pipeline restart. Adds ws_sem and api_sem parameters to both stream
functions and releases all three in finally blocks. Threads the values
through all four call sites in chat_completions.

Resolves: REL-08 (likely root cause of intermittent "Workspace at
concurrency limit" reports, not previously diagnosed)
```

---

## Task 1.7 — Add `mcp-servers.json` entries for research, memory, rag (REL-09)

### Rationale
`imports/openwebui/mcp-servers.json` lists 8 MCP servers but `tool_registry.py` knows about 11. Open WebUI's tool-server config is missing research, memory, and rag, so users can't call `web_search`/`web_fetch`/`news_search`/`remember`/`recall`/`kb_search` directly from a chat (workspace routing still works because the pipeline discovers them independently).

### Before
```json
{
    "version": "1.1",
    "description": "Portal 5.2.1 MCP Tool Server configurations",
    "tool_servers": [
        ... 8 entries ending with Portal Security Tools at :8919 ...
    ],
    "notes": { ... }
}
```

### After
```json
{
    "version": "1.2",
    "description": "Portal 6.0.4 MCP Tool Server configurations",
    "tool_servers": [
        ... existing 8 entries ...
        {
            "name": "Portal Memory",
            "id": "portal_memory",
            "url": "http://host.docker.internal:8920/mcp",
            "api_key": ""
        },
        {
            "name": "Portal RAG",
            "id": "portal_rag",
            "url": "http://host.docker.internal:8921/mcp",
            "api_key": ""
        },
        {
            "name": "Portal Research",
            "id": "portal_research",
            "url": "http://host.docker.internal:8922/mcp",
            "api_key": ""
        }
    ],
    "notes": { ... }
}
```

### Verify
```bash
# 1. JSON valid + 11 entries
python3 -c "
import json
d = json.load(open('imports/openwebui/mcp-servers.json'))
ids = [s['id'] for s in d['tool_servers']]
assert len(ids) == 11, f'expected 11 servers, got {len(ids)}'
assert 'portal_research' in ids
assert 'portal_memory' in ids
assert 'portal_rag' in ids
assert d['description'].startswith('Portal 6.0'), f'stale version: {d[\"description\"]}'
print('OK')
"

# 2. Ports match tool_registry defaults
python3 -c "
import json
d = json.load(open('imports/openwebui/mcp-servers.json'))
from portal_pipeline.tool_registry import MCP_SERVERS  # PIPELINE_API_KEY=test required
" 2>&1 | head -5
PIPELINE_API_KEY=test python3 -c "
import json
from portal_pipeline.tool_registry import MCP_SERVERS
d = {s['id'].replace('portal_', ''): s['url'] for s in json.load(open('imports/openwebui/mcp-servers.json'))['tool_servers']}
# 'comfyui' is the registry name for the MCP that registers as 'portal_comfyui' but is also called 'comfyui' internally
expected = {
    'comfyui': '8910', 'video': '8911', 'music': '8912', 'documents': '8913',
    'code': '8914', 'whisper': '8915', 'tts': '8916', 'security': '8919',
    'memory': '8920', 'rag': '8921', 'research': '8922',
}
for k, port in expected.items():
    assert k in d, f'missing {k}'
    assert port in d[k], f'{k}: expected port {port}, got {d[k]}'
print('OK')
"
```

### Rollback
```bash
git checkout imports/openwebui/mcp-servers.json
```

### Commit
```
feat(owui): register research, memory, rag MCPs in tool-servers config

Open WebUI's tool-servers config listed only 8 of the 11 MCP servers
that exist in the pipeline's tool_registry. Users couldn't call
web_search, web_fetch, news_search, remember, recall, or kb_search
directly from a chat. Adds the three missing entries on their actual
ports (memory=8920, rag=8921, research=8922 — see also: port-collision
fix for research moving from 8918). Updates description from "Portal
5.2.1" to "Portal 6.0.4".

Resolves: REL-09, REL-10
```

---

## Task 1.8 — Refresh stale version strings (REL-10 + cleanup)

### Rationale
Three docstrings still claim Portal 5.2.1; project is 6.0.3 (going to 6.0.4).

### Files

**A. `portal_pipeline/cluster_backends.py:1`**
```python
# Before
"""Portal 5.2.1 — Backend Registry with health checks and workspace routing.
# After
"""Portal 6.0.4 — Backend Registry with health checks and workspace routing.
```

**B. `tests/conftest.py:1-3`**
```python
# Before
"""
Pytest configuration for Portal 5.2.1.
# After
"""
Pytest configuration for Portal 6.0.4.
```

**C. `imports/openwebui/mcp-servers.json`** — already covered by Task 1.7

**D. `portal_pipeline/router_pipe.py:1`** — already says 6.0.3, bump to 6.0.4
```python
# Before
"""Portal 6.0.3 — Intelligent Router Pipeline.
# After
"""Portal 6.0.4 — Intelligent Router Pipeline.
```

**E. `CLAUDE.md` line 5**
```
**Version**: 6.0.3  →  **Version**: 6.0.4
```

**F. `config/backends.yaml` line 1**
```
# Portal 6.0.3 — Backend Registry  →  # Portal 6.0.4 — Backend Registry
```

**G. `pyproject.toml`** — bump `version = "6.0.3"` → `"6.0.4"`

### Verify
```bash
! grep -rn "5\\.2\\.1" portal_pipeline/ tests/conftest.py CLAUDE.md README.md && echo OK
grep -h '6.0.4' pyproject.toml CLAUDE.md config/backends.yaml | wc -l
```

### Commit
```
chore(version): bump to 6.0.4 and refresh stale 5.2.1 docstrings

Three files still declared "Portal 5.2.1" in their module docstrings.
Bump pyproject.toml + CLAUDE.md + backends.yaml + router_pipe.py
docstring + cluster_backends.py docstring + conftest.py docstring to
6.0.4 in lock-step with Phase 1 fixes.
```

---

## Task 1.9 — README acceptance summary refresh (QW-06)

### Rationale
README "Acceptance Testing" block claims 154P/2I/0F/0W from Run 17 (2026-04-13). Latest `ACCEPTANCE_RESULTS.md` (2026-04-25) is partial — 3P/1F/3W from S70 only. Replace the hardcoded count with a link plus an auto-generated note.

### Before
```markdown
### Acceptance Testing

The full acceptance test suite runs 156 checks across all subsystems.
Latest run (2026-04-13, Run 17):

**154 PASS · 2 INFO · 0 FAIL · 0 WARN**

Clean run. See `ACCEPTANCE_RESULTS.md` for full results.
```

### After
```markdown
### Acceptance Testing

The full acceptance test suite (`tests/portal5_acceptance_v6.py`) runs
~250 checks across 30 sections. Run with:

```bash
python3 tests/portal5_acceptance_v6.py        # full suite
python3 tests/portal5_acceptance_v6.py --section S70  # one section
```

Latest run summary is in [ACCEPTANCE_RESULTS.md](ACCEPTANCE_RESULTS.md).
```

### Commit
```
docs(readme): replace stale acceptance summary with link

The hardcoded "154 PASS" claim from Run 17 (2026-04-13) was no longer
accurate after the partial 2026-04-25 run wrote new content to
ACCEPTANCE_RESULTS.md. Replaces the hardcoded count with a link plus
the run command. Also corrects "156 checks" → "~250" and "all
subsystems" → "30 sections" to match current scope.
```

---

## Task 1.10 — README workspace count refresh (QW-07)

### Rationale
README workspace dropdown table lists 17 entries; actual count is 18 functional + 9 bench = 27. The 17-entry table is missing `auto-math` and the bench-* set.

### Action
Update the workspace table in README.md "Workspaces" section:
1. Add `auto-math` row to the existing functional workspaces (Qwen2.5-Math primary)
2. Add a separate "Benchmark Workspaces (user-selected only)" subsection listing the 9 bench-* IDs with their pinned models
3. Change "17 workspaces" prose elsewhere to "18 functional workspaces (plus 9 benchmark workspaces for performance comparison)"

### Verify
```bash
# Functional workspaces in README match WORKSPACES dict (excluding bench-*)
PIPELINE_API_KEY=test python3 -c "
import re
from portal_pipeline.router_pipe import WORKSPACES
functional = [k for k in WORKSPACES if not k.startswith('bench-')]
readme = open('README.md').read()
for ws in functional:
    assert f'\`{ws}\`' in readme, f'{ws} missing from README workspace table'
print(f'OK: all {len(functional)} functional workspaces documented')
"
```

### Commit
```
docs(readme): add auto-math + benchmark workspaces to dropdown table

README listed 17 workspaces; actual count is 18 functional + 9 bench
(in WORKSPACES dict and backends.yaml workspace_routing). Adds the
missing auto-math row, adds a separate Benchmark Workspaces subsection
covering bench-devstral through bench-gptoss, and corrects "17" to
"18 functional + 9 benchmark" wording in surrounding prose.
```

---

## Task 1.11 — Add UAT routed-model capture (QW-09)

### Rationale
The UAT driver does not capture `x-portal-route` from the response header. Had it done so, REL-02 would have surfaced immediately as "expected supergemma4-26b, got Qwen3-Coder-Next-4bit". Cheap to add, high diagnostic value.

### Action

**A. In `tests/portal5_uat_driver.py`**, find the function that issues the chat HTTP request. Capture `response.headers.get('x-portal-route')` alongside the response body. Parse: `x-portal-route: <workspace>;<backend_id>;<model>`.

**B. Surface in result row.** Add `routed_model` field to the per-test result dict so it appears in `UAT_RESULTS.md` (markdown table) and (if exported) JSON.

**C. Display in detail column.** When a test fails, prepend `[routed: <model>]` to the detail string so the operator sees what was actually used.

### Verify
```bash
# 1. Static: routed_model is captured
grep -n "x-portal-route\|routed_model" tests/portal5_uat_driver.py | head -10

# 2. Live UAT row format includes [routed: ...] in detail when present
# Run one auto-research UAT test and confirm UAT_RESULTS.md row contains the routed model

# 3. Compare expected vs actual when WORKSPACES has a hint
PIPELINE_API_KEY=test python3 -c "
from portal_pipeline.router_pipe import WORKSPACES
# auto-research mlx_model_hint after Task 1.1 fix
expected = WORKSPACES['auto-research']['mlx_model_hint']
print(f'auto-research expected MLX model: {expected}')
"
```

### Commit
```
test(uat): capture x-portal-route in result rows

Adds routed_model field to UAT driver output by reading the
x-portal-route header that chat_completions already emits
(format: workspace;backend_id;model). Surfaces it in the per-test
detail column. Future hint typos like REL-02 (auto-research routing
to Qwen3-Coder-Next 80B instead of supergemma4) would have been
visible from the first UAT row instead of being misdiagnosed as
"zombie MLX state".
```

---

## Task 1.12 — Log warning on silent hint fallback (QW-10)

### Rationale
`router_pipe.py:2585` resolves `target_model = mlx_hint if mlx_hint in backend.models else backend.models[0]`. The fallback is silent. If a hint doesn't match (REL-02, REL-03), there is no log line to flag the typo. Adding one warning per fallback would have surfaced both bugs days ago.

### Before
```python
        # Pick the right hint for the backend type
        if backend.type == "mlx" and mlx_hint:
            target_model = mlx_hint if mlx_hint in backend.models else ""
            if not target_model:
                target_model = backend.models[0] if backend.models else "dolphin-llama3:8b"
        elif model_hint and model_hint in backend.models:
            target_model = model_hint
        else:
            target_model = backend.models[0] if backend.models else "dolphin-llama3:8b"
```

### After
```python
        # Pick the right hint for the backend type
        if backend.type == "mlx" and mlx_hint:
            if mlx_hint in backend.models:
                target_model = mlx_hint
            else:
                target_model = backend.models[0] if backend.models else "dolphin-llama3:8b"
                logger.warning(
                    "mlx_model_hint %r not in backend %s models — falling back to %r. "
                    "Add it to config/backends.yaml MLX list or correct the hint in WORKSPACES.",
                    mlx_hint, backend.id, target_model,
                )
        elif model_hint:
            if model_hint in backend.models:
                target_model = model_hint
            else:
                target_model = backend.models[0] if backend.models else "dolphin-llama3:8b"
                logger.warning(
                    "model_hint %r not in backend %s models — falling back to %r. "
                    "Add it to config/backends.yaml or correct the hint in WORKSPACES.",
                    model_hint, backend.id, target_model,
                )
        else:
            target_model = backend.models[0] if backend.models else "dolphin-llama3:8b"
```

### Verify
```bash
# Static: warnings present
grep -n "mlx_model_hint .* falling back\|model_hint .* falling back" portal_pipeline/router_pipe.py
# Expected: 2 lines

# Live: trigger fallback by setting a deliberately bad hint and checking pipeline log
# (Phase 2 ME-01 makes this strict; for now just the log)
```

### Commit
```
fix(routing): warn on silent model_hint fallback to backend.models[0]

Hint typos (REL-02 for auto-research, REL-03 for auto-coding/agentic)
went undiagnosed for weeks because the fallback path was silent. Adds a
single logger.warning() per fallback for both mlx_model_hint and
model_hint. Operators see "mlx_model_hint X not in backend Y — falling
back to Z" in pipeline logs the first time a typo is hit.
```

---

## Task 1.13 — `launch.sh install-mlx` env sourcing (REL-07 / ME-08 promoted)

### Rationale
`launch.sh:2757` (`install-mlx)`) does NOT source `.env` before generating `com.portal5.mlx-proxy.plist`. Other launch.sh commands at lines 855, 877, 1009, 1155, 1168 do. If install-mlx runs without `.env` already in the calling shell, `HF_HUB_CACHE`/`HF_HOME`/`HF_TOKEN` are dropped from the plist's `EnvironmentVariables` block. The launchd-managed proxy then uses default `~/.cache/huggingface` and won't find models on the external drive.

### Before
```bash
  install-mlx)
    echo "=== Installing MLX dual-server (Apple Silicon native inference) ==="
    ARCH=$(uname -m)

    if [ "$ARCH" != "arm64" ]; then
        echo "  ℹ️  MLX is Apple Silicon only. On Linux, Ollama GGUF handles inference."
        exit 0
    fi
```

### After
```bash
  install-mlx)
    # Source .env so HF_HUB_CACHE/HF_HOME/HF_TOKEN propagate into the
    # generated com.portal5.mlx-proxy.plist EnvironmentVariables block.
    # Without this, a fresh shell running `./launch.sh install-mlx` produces
    # a plist that omits HF env vars, and the launchd-managed proxy looks
    # for models in ~/.cache/huggingface instead of the configured cache.
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a

    echo "=== Installing MLX dual-server (Apple Silicon native inference) ==="
    ARCH=$(uname -m)

    if [ "$ARCH" != "arm64" ]; then
        echo "  ℹ️  MLX is Apple Silicon only. On Linux, Ollama GGUF handles inference."
        exit 0
    fi
```

### Verify
```bash
# 1. Static: install-mlx now sources .env
grep -A2 'install-mlx)' launch.sh | head -5
# Expected: contains 'set -a; source "$ENV_FILE"'

# 2. Live (manual on Apple Silicon):
# Fresh shell, no env exports, then:
# ./launch.sh install-mlx
# cat ~/Library/LaunchAgents/com.portal5.mlx-proxy.plist | grep -A1 HF_HOME
# Expected: HF_HOME key present with value from .env
```

### Commit
```
fix(launch): source .env in install-mlx before generating plist

install-mlx generated com.portal5.mlx-proxy.plist by reading
HF_HUB_CACHE / HF_HOME / HF_TOKEN from the calling shell environment.
Other launch.sh commands sourced .env via `set -a; source $ENV_FILE`
but install-mlx did not. A fresh shell running install-mlx produced
a plist that omitted the HF env vars, leading the launchd-managed
proxy to look for models in ~/.cache/huggingface instead of the
configured external-drive cache. Adds the standard env-sourcing line
at the top of the install-mlx case.

Resolves: REL-07
```

---

## Task 1.14 — `launch.sh install-music` env sourcing (REL-15)

**Rationale.** `install-music` (line 2629) does not source `.env` before generating `com.portal5.music-mcp.plist` (line 2704-2740). The plist's `EnvironmentVariables` block hardcodes `HF_HOME`, `TRANSFORMERS_CACHE`, `OUTPUT_DIR`, `MUSIC_MCP_PORT` from the calling shell. A fresh shell running `./launch.sh install-music` produces a plist that defaults `HF_HOME` to `$HOME/.portal5/music/hf_cache` — separate from MLX's HF cache, fragmenting model storage. Same class of bug as REL-07.

**Before** (`launch.sh:2629-2630`):
```bash
  install-music)
    echo "=== Installing Music MCP natively (Apple Silicon / MPS) ==="
```

**After:**
```bash
  install-music)
    # Source .env so HF_HOME, AI_OUTPUT_DIR, and MUSIC_HOST_PORT propagate into
    # the generated com.portal5.music-mcp.plist EnvironmentVariables block.
    # Without this, a fresh shell running `./launch.sh install-music` defaults
    # HF_HOME to ~/.portal5/music/hf_cache — separate from MLX's HF cache,
    # fragmenting model storage.
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a

    echo "=== Installing Music MCP natively (Apple Silicon / MPS) ==="
```

**Verify.**
```bash
# Static
grep -A2 'install-music)' launch.sh | head -5
# Expected: contains 'set -a; source "$ENV_FILE"'

# Live (manual): fresh shell, no env exports, then:
# ./launch.sh install-music
# cat ~/Library/LaunchAgents/com.portal5.music-mcp.plist | grep -A1 HF_HOME
# Expected: HF_HOME from .env (e.g., /Volumes/data01/hf_cache), not the hf_cache fallback
```

**Rollback:** `git checkout launch.sh`

**Commit:**
```
fix(launch): source .env in install-music before generating plist

install-music generated com.portal5.music-mcp.plist by reading
HF_HOME / TRANSFORMERS_CACHE / AI_OUTPUT_DIR / MUSIC_HOST_PORT from
the calling shell environment. A fresh shell running install-music
produced a plist that defaulted HF_HOME to ~/.portal5/music/hf_cache,
separate from the MLX HF cache and fragmenting model storage. Adds
the standard env-sourcing line at the top of the install-music case.
Mirrors the install-mlx fix in REL-07 / Task 1.13.

Resolves: REL-15
```

---

## Task 1.15 — Async-ify `_fetch_mlx_context` (REL-13)

**Rationale.** `_fetch_mlx_context` is called from `check_thresholds_and_alert`, which is invoked as the `on_health_check` callback after each `BackendRegistry.health_check_all()` cycle. That cycle runs inside the asyncio event loop. The synchronous `httpx.get(..., timeout=5)` blocks the event loop for up to 5 seconds during a backend-down alert. Every other request queued on the loop (chat completions, tool dispatches, health checks) is paused.

**Before** (`portal_pipeline/notifications/dispatcher.py:151-172`):
```python
def _fetch_mlx_context(self) -> dict:
    """Fetch detailed MLX proxy state for alert enrichment.

    Makes a synchronous HTTP call to the MLX proxy /health endpoint.
    Returns context dict or empty dict on failure.
    """
    try:
        resp = httpx.get(_MLX_PROXY_HEALTH_URL, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "mlx_server": data.get("active_server", "unknown"),
                ...
            }
    except Exception as e:
        logger.debug("Failed to fetch MLX context for alert: %s", e)
    return {}
```

**After:**
```python
async def _fetch_mlx_context(self) -> dict:
    """Fetch detailed MLX proxy state for alert enrichment.

    Async — does not block the asyncio event loop. Caller must await.
    Returns context dict or empty dict on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(_MLX_PROXY_HEALTH_URL)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "mlx_server": data.get("active_server", "unknown"),
                    "mlx_model": data.get("loaded_model", "none"),
                    "mlx_state": data.get("state", "unknown"),
                    "mlx_error": data.get("last_error") or "none",
                    "mlx_consecutive_failures": data.get("consecutive_failures", 0),
                    "mlx_switch_count": data.get("switch_count", 0),
                    "mlx_state_duration": f"{data.get('state_duration_sec', 0)}s",
                }
    except Exception as e:
        logger.debug("Failed to fetch MLX context for alert: %s", e)
    return {}
```

**Caller change** — `check_thresholds_and_alert` is currently sync but is called from an async callback chain. Convert it to async:
```python
async def check_thresholds_and_alert(self, registry, down_threshold=None, alert_all_down=True):
    # ... existing logic ...
    if backend.type == "mlx":
        metadata = await self._fetch_mlx_context()
    # ... etc.
```

And the lifespan wiring at `router_pipe.py:1958-1963` — change the lambda to await the coroutine:
```python
# Before
on_health_check=(
    lambda r: (
        _notification_dispatcher.check_thresholds_and_alert(r)
        if _notification_dispatcher
        else None
    )
)
# After
async def _on_health(r):
    if _notification_dispatcher:
        await _notification_dispatcher.check_thresholds_and_alert(r)

on_health_check=_on_health
```

The `BackendRegistry.start_health_loop` callback type annotation will need updating from `Callable[[BackendRegistry], None]` to accept either sync or async; or just change to `Callable[[BackendRegistry], Awaitable[None] | None]` and `await` if the result is a coroutine.

**Verify.**
```bash
# Static: dispatcher uses AsyncClient
grep -A2 '_fetch_mlx_context' portal_pipeline/notifications/dispatcher.py | head -10
# Expected: 'async def' and 'AsyncClient'

# Unit test: existing test_notifications.py should still pass
pytest tests/unit/test_notifications.py -v
```

**Rollback:** `git checkout portal_pipeline/notifications/dispatcher.py portal_pipeline/router_pipe.py portal_pipeline/cluster_backends.py`

**Commit:**
```
fix(notifications): make _fetch_mlx_context async

_fetch_mlx_context used synchronous httpx.get(..., timeout=5) inside
an asyncio callback chain (check_thresholds_and_alert called from
the health-loop on_health_check). A backend-down alert blocked the
event loop for up to 5 seconds, pausing every other in-flight request.
Converts to httpx.AsyncClient and awaits, matching the rest of the
async pipeline. Updates the start_health_loop callback signature to
accept awaitables and the lifespan wrapper to use an async closure.

Resolves: REL-13
```

---

## Task 1.16 — `recover_proxy` uses `launchctl kickstart` (REL-16)

**Rationale.** `mlx-watchdog.py:404` restarts the proxy via `subprocess.Popen(["python3", "mlx-proxy.py"])`. This bypasses the `com.portal5.mlx-proxy.plist` entirely:

1. The recovered proxy loses the plist's `EnvironmentVariables` block (HF_HOME, HF_HUB_CACHE, HF_TOKEN). It inherits whatever the watchdog process has, which is whatever launchd gave the watchdog — typically nothing useful.
2. The new PID is not tracked by launchd. If it dies again, launchd's `KeepAlive` does nothing because launchd doesn't know about it.
3. The system can simultaneously have launchd-managed and watchdog-spawned proxy processes — confusing during incident response.

The fix uses `launchctl kickstart -k` to restart the existing launchd-managed service. `-k` kills first, then starts. The replacement process is launchd-tracked and inherits the plist's environment.

**Before** (`scripts/mlx-watchdog.py:357-426`):
```python
def recover_proxy() -> None:
    """Kill hung proxy and restart it.
    ...
    """
    # Kill all MLX processes — proxy and any servers it was managing
    for pattern in ["mlx-proxy.py", "mlx_lm.server", "mlx_vlm.server"]:
        result = subprocess.run(["pgrep", "-f", pattern], ...)
        for pid in result.stdout.strip().split("\n"):
            if pid:
                try:
                    os.kill(int(pid), signal.SIGTERM)
                ...

    # Also kill anything on the ports
    for port in [PROXY_PORT, LM_PORT, VLM_PORT]:
        result = subprocess.run(["lsof", "-ti", f":{port}"], ...)
        ...

    # Wait for GPU memory reclamation (critical on Apple Silicon)
    logger.info("Waiting 15s for GPU memory reclamation...")
    time.sleep(15)

    # Restart proxy — it will handle server lifecycle on demand
    script_dir = Path(__file__).parent
    proxy_script = script_dir / "mlx-proxy.py"
    if not proxy_script.exists():
        raise FileNotFoundError(f"mlx-proxy.py not found at {proxy_script}")

    subprocess.Popen(
        ["python3", str(proxy_script)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    logger.info("Restarted MLX proxy — it will load models on demand")
    ...
```

**After:**
```python
def recover_proxy() -> None:
    """Kill hung proxy and ask launchd to restart it.

    Uses `launchctl kickstart -k` so the recovered proxy inherits the
    com.portal5.mlx-proxy.plist EnvironmentVariables (HF_HOME,
    HF_HUB_CACHE, HF_TOKEN) and remains tracked by launchd's KeepAlive.
    Falls back to a direct subprocess.Popen only if launchctl is
    unavailable (Linux dev environments).
    """
    # Kill any MLX server processes the proxy was managing.
    # The proxy itself will be killed and respawned by launchctl below.
    for pattern in ["mlx_lm.server", "mlx_vlm.server"]:
        result = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
        for pid in result.stdout.strip().split("\n"):
            if pid:
                try:
                    os.kill(int(pid), signal.SIGTERM)
                    logger.info("Sent SIGTERM to %s (PID %s)", pattern, pid)
                except ProcessLookupError:
                    pass

    # Wait for GPU memory reclamation (critical on Apple Silicon)
    logger.info("Waiting 15s for GPU memory reclamation...")
    time.sleep(15)

    # Ask launchd to restart the proxy service. -k kills first, then starts.
    # The new process inherits the plist's EnvironmentVariables.
    launchd_label = "com.portal5.mlx-proxy"
    domain = f"gui/{os.getuid()}"
    try:
        result = subprocess.run(
            ["launchctl", "kickstart", "-k", f"{domain}/{launchd_label}"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            logger.info("Asked launchd to restart %s", launchd_label)
        else:
            logger.warning(
                "launchctl kickstart returned %d: %s — falling back to subprocess",
                result.returncode, result.stderr.strip(),
            )
            raise RuntimeError("launchctl kickstart failed")
    except (FileNotFoundError, subprocess.TimeoutExpired, RuntimeError):
        # Fallback: direct Popen (Linux or no launchd registration)
        logger.warning("Falling back to direct proxy spawn (no launchd)")
        for pattern in ["mlx-proxy.py"]:
            result = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
            for pid in result.stdout.strip().split("\n"):
                if pid:
                    try:
                        os.kill(int(pid), signal.SIGTERM)
                    except ProcessLookupError:
                        pass
        time.sleep(2)
        script_dir = Path(__file__).parent
        proxy_script = script_dir / "mlx-proxy.py"
        if proxy_script.exists():
            subprocess.Popen(
                ["python3", str(proxy_script)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )

    # Wait for proxy to respond (any response = alive)
    for attempt in range(30):
        time.sleep(2)
        try:
            r = httpx.get(f"http://127.0.0.1:{PROXY_PORT}/health", timeout=5)
            if r.status_code in (200, 503):
                COMPONENTS["proxy"].healthy = True
                COMPONENTS["proxy"].consecutive_failures = 0
                COMPONENTS["proxy"].recovery_attempts = 0
                send_notification("RECOVERED", f"MLX Proxy recovered on :{PROXY_PORT}")
                return
        except Exception:
            pass

    raise RuntimeError("MLX proxy did not come up after restart")
```

**Verify.**
```bash
# 1. Static: kickstart path present, launchd_label hardcoded
grep -A1 'launchctl.*kickstart' scripts/mlx-watchdog.py
# Expected: kickstart -k gui/<uid>/com.portal5.mlx-proxy

# 2. Live (Apple Silicon, requires manual SIGKILL of mlx-proxy):
# Send SIGKILL to mlx-proxy and watch the watchdog log:
# tail -f ~/.portal5/logs/mlx-watchdog.log
# Expect: "Asked launchd to restart com.portal5.mlx-proxy"
# Then: ps aux | grep mlx-proxy → process is launchd-tracked (parent PID = launchd)
# pstree -p (or equivalent) — new mlx-proxy parent is /sbin/launchd, not the watchdog

# 3. Confirm new proxy has HF_HOME from plist (not from watchdog):
# launchctl print gui/$(id -u)/com.portal5.mlx-proxy | grep HF_HOME
```

**Rollback:** `git checkout scripts/mlx-watchdog.py`

**Commit:**
```
fix(watchdog): restart MLX proxy via launchctl kickstart, not Popen

recover_proxy() called subprocess.Popen("python3 mlx-proxy.py"),
bypassing the com.portal5.mlx-proxy.plist EnvironmentVariables block.
The recovered proxy lost HF_HOME / HF_HUB_CACHE / HF_TOKEN, used the
default ~/.cache/huggingface for models, and was no longer tracked by
launchd's KeepAlive (so a second crash had no auto-recovery). Switches
to `launchctl kickstart -k gui/<uid>/com.portal5.mlx-proxy` so the
recovered process inherits the plist environment and remains
launchd-managed. Keeps the direct Popen as a fallback for Linux
development environments where the launchd plist isn't registered.

Resolves: REL-16
```

---

## Phase 1 — Full verification sequence

Run this end-to-end after all 16 tasks land. Stops on first failure.

```bash
set -e

echo "── Static checks ──"
ruff check portal_pipeline/ portal_mcp/ tests/ scripts/mlx-proxy.py
ruff format --check portal_pipeline/ portal_mcp/ tests/

echo "── Unit tests ──"
pytest tests/unit/ -q --tb=short

echo "── Workspace ID consistency ──"
PIPELINE_API_KEY=test python3 -c "
import yaml
from portal_pipeline.router_pipe import WORKSPACES
cfg = yaml.safe_load(open('config/backends.yaml'))
pipe_ids = set(WORKSPACES.keys())
yaml_ids = set(cfg['workspace_routing'].keys())
assert pipe_ids == yaml_ids, f'Mismatch: pipe={pipe_ids - yaml_ids} yaml={yaml_ids - pipe_ids}'
print('OK')
"

echo "── Hint reachability (every hint resolves) ──"
PIPELINE_API_KEY=test python3 -c "
import yaml
from portal_pipeline.router_pipe import WORKSPACES
cfg = yaml.safe_load(open('config/backends.yaml'))
groups = {}
for be in cfg['backends']:
    groups.setdefault(be['group'], set()).update(be['models'])
errors = []
for ws_id, ws in WORKSPACES.items():
    routes = cfg['workspace_routing'].get(ws_id, [])
    available = set().union(*[groups.get(g, set()) for g in routes])
    for hint_key in ('model_hint', 'mlx_model_hint'):
        if hint_key in ws and ws[hint_key]:
            if ws[hint_key] not in available:
                errors.append(f'{ws_id}.{hint_key}={ws[hint_key]!r} not in any of {routes}')
if errors:
    for e in errors: print(' -', e)
    raise SystemExit(1)
print('OK: all hints resolve')
"

echo "── MODEL_MEMORY in sync with backends.yaml ──"
python3 -c "
import re, yaml
cfg = yaml.safe_load(open('config/backends.yaml'))
mlx = next(b['models'] for b in cfg['backends'] if b['type']=='mlx')
mp = open('scripts/mlx-proxy.py').read()
m = re.search(r'MODEL_MEMORY: dict\[str, float\] = \{(.*?)^\}', mp, re.DOTALL | re.MULTILINE)
mm = set(re.findall(r'\"([^\"]+)\":\s*[\d.]+', m.group(1)))
in_mm_only = mm - set(mlx)
# Drafts are allowed in MODEL_MEMORY without being in primary list
drafts = {'mlx-community/Qwen2.5-0.5B-Instruct-4bit', 'mlx-community/Llama-3.2-1B-Instruct-4bit'}
in_mm_only -= drafts
assert not in_mm_only, f'MODEL_MEMORY has stale entries: {in_mm_only}'
print('OK: MODEL_MEMORY consistent with backends.yaml')
"

echo "── No port 8918 outside MLX speech ──"
GREP_RESULT=$(grep -rn "8918" --include="*.py" --include="*.yaml" --include="*.yml" --include="*.md" --include="*.example" \
    portal_pipeline/ portal_mcp/ deploy/ config/ docs/ scripts/mlx-speech.py *.md 2>/dev/null \
    | grep -v 'mlx-speech\|MLX_SPEECH\|kokoro\|tts\|Speech\|speech\|^scripts/mlx-speech' || true)
[ -z "$GREP_RESULT" ] && echo "OK" || (echo "FAIL: residual 8918 references:"; echo "$GREP_RESULT"; exit 1)

echo "── mcp-servers.json has 11 entries ──"
python3 -c "
import json
d = json.load(open('imports/openwebui/mcp-servers.json'))
assert len(d['tool_servers']) == 11
print('OK')
"

echo "── No Portal 5.2.1 strings remain ──"
! grep -rn "Portal 5\\.2\\.1" portal_pipeline/ tests/conftest.py CLAUDE.md README.md && echo "OK"

echo "── Phase 1 verification PASSED ──"
```

---

## Phase 1 — Rollback (if anything breaks)

```bash
git reset --hard pre-phase1-fixes
git tag -d pre-phase1-fixes
```

---

## Phase 1 — Live regression checklist (post-deploy)

After landing all 13 commits and rebuilding/restarting:

```bash
./launch.sh down
./launch.sh up
sleep 30  # wait for warm-up

# 1. S70 acceptance: previously had FAIL on S70-07 and WARN on S70-02
python3 tests/portal5_acceptance_v6.py --section S70
# Expected: 5/7 PASS minimum (S70-07 PASS now). S70-02 PASS if research MCP started.

# 2. UAT auto-research: previously had 4 FAILs
python3 tests/portal5_uat_driver.py --workspace auto-research
# Expected: at least 3/4 tests PASS (REL-02 fixed; some FAILs may persist if persona-level signals miss)
# routed_model column should now show Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit

# 3. Concurrency: hit auto-coding 8 times in a row with stream=true
for i in {1..8}; do
  curl -sN -H "Authorization: Bearer $PIPELINE_API_KEY" \
       -H "Content-Type: application/json" \
       -d '{"model":"auto-coding","stream":true,"messages":[{"role":"user","content":"hi"}]}' \
       http://localhost:9099/v1/chat/completions | head -c 100
  echo "  --- request $i done"
done
# Pre-fix: requests 6-8 returned HTTP 429 "Workspace at concurrency limit"
# Post-fix: all 8 succeed
```

---

## Total scope

| Task | Files touched | Lines changed | Effort |
|---|---|---|---|
| 1.1 auto-research hint | router_pipe.py | 1 | 5 min |
| 1.2 auto-coding hint | router_pipe.py | 2 | 5 min |
| 1.3 PROMETHEUS_MULTIPROC_DIR mkdir | router_pipe.py | ~6 | 10 min |
| 1.4 port 8918 collision | tool_registry.py, web_search_mcp.py, docker-compose.yml, .env.example, CLAUDE.md, README.md | ~20 | 30 min |
| 1.5 dead MODEL_MEMORY entry | mlx-proxy.py | 2 | 5 min |
| 1.6 semaphore leak | router_pipe.py | ~30 | 60 min (largest, careful) |
| 1.7 mcp-servers.json | mcp-servers.json | ~20 | 10 min |
| 1.8 version refresh | 7 files | ~10 | 10 min |
| 1.9 README acceptance summary | README.md | ~10 | 10 min |
| 1.10 README workspace table | README.md | ~30 | 20 min |
| 1.11 UAT routed-model capture | portal5_uat_driver.py | ~15 | 30 min |
| 1.12 hint-fallback warning | router_pipe.py | ~15 | 15 min |
| 1.13 install-mlx env sourcing | launch.sh | 2 | 5 min |
| 1.14 install-music env sourcing | launch.sh | 1 | 5 min |
| 1.15 async _fetch_mlx_context | dispatcher.py, router_pipe.py, cluster_backends.py | ~30 | 45 min |
| 1.16 watchdog launchctl kickstart | mlx-watchdog.py | ~50 | 30 min |

**Total: ~5 hours of focused work, 13 commits, 16 verifiable changes.**

— end of Phase 1 —
