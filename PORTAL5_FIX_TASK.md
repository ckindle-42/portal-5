# Portal 5.2.1 — Acceptance Test Fix & Completion Task

**Repo:** https://github.com/ckindle-42/portal-5  
**Branch:** main (commit directly — see CLAUDE.md)  
**Reference docs:** `ACCEPTANCE_SUMMARY.md`, `ACCEPTANCE_RESULTS.md`, `CLAUDE.md`, `KNOWN_LIMITATIONS.md`  
**Test file:** `portal5_acceptance_v3.py`  
**Run instructions after fixes:** `PORTAL5_ACCEPTANCE_EXECUTE.md`

---

## Before You Start

Read these files in full before touching any code:

1. `CLAUDE.md` — architectural rules, protected files list, git workflow
2. `ACCEPTANCE_SUMMARY.md` — the three-run test history and blocked items with evidence
3. `portal5_acceptance_v3.py` — the full test suite (2922 lines)
4. `portal_pipeline/router_pipe.py` — the pipeline being tested
5. `docs/HOWTO.md` — operator documentation tested by S14

Run the workspace consistency check before and after any changes to `router_pipe.py`:

```bash
python3 -c "
import yaml, re
src = open('portal_pipeline/router_pipe.py').read()
s = src.index('WORKSPACES:')
e = src.index('# ── Content-aware', s)
pipe_ids = set(re.findall(r'\"(auto[^\"]*)\": *\{', src[s:e]))
cfg = yaml.safe_load(open('config/backends.yaml'))
yaml_ids = set(cfg['workspace_routing'].keys())
assert pipe_ids == yaml_ids, f'MISMATCH pipe={pipe_ids-yaml_ids} yaml={yaml_ids-pipe_ids}'
print(f'Workspace IDs consistent ({len(pipe_ids)} total)')
"
```

---

## Current State (Fresh Clone — 2026-04-03)

| Component | Current count | Expected |
|---|---|---|
| Workspaces in `router_pipe.py` | 16 | 16 ✓ |
| Workspaces in `backends.yaml` | 16 | 16 ✓ |
| Persona YAML files | 40 | 40 ✓ |
| HOWTO §3 workspace table rows | 15 | 16 ✗ |
| HOWTO §16 workspace list entries | 15 | 16 ✗ |
| Workspace JSONs in `imports/openwebui/workspaces/` | 15 | 16 ✗ |
| Entries in `workspaces_all.json` | 14 | 16 ✗ |
| `auto-spl` in `_WS_PROMPT` (test file) | absent | present ✗ |
| `auto-spl` in `_WS_MODEL_GROUPS` (test file) | absent | present ✗ |
| `splunksplgineer` in `_PERSONAS_BY_MODEL` (test file) | absent | present ✗ |
| `_chat()` reasoning field fallback | absent | present ✗ |
| Duplicate `S11-sum` emit | present | removed ✗ |

---

## PART A — Test File Fixes (`portal5_acceptance_v3.py`)

This file is explicitly listed as safe to edit in `PORTAL5_ACCEPTANCE_EXECUTE.md`.  
All changes below fix gaps in test coverage, not product code.

---

### A1. Add `auto-spl` to `_WS_PROMPT`

**Why:** `_WS_MODEL_GROUPS` iterates all 16 workspace IDs from `WS_IDS`. When a workspace
has no entry in `_WS_PROMPT`, the test falls back to a generic
`f"Describe your role as the {ws} workspace."` prompt that produces weak signal matching.
`auto-spl` is a real workspace routing to `DeepSeek-Coder-V2-Lite` for Splunk SPL queries.
It needs a domain-specific prompt that will trigger SPL-relevant output.

**Location:** `_WS_PROMPT` dict, approximately line 641. Add the following entry alongside
the other workspace entries. Alphabetical position is not required — add after `auto-security`
for logical grouping:

```python
"auto-spl": (
    "Write a Splunk SPL search that detects brute-force SSH login attempts: "
    "more than 10 failed logins from the same source IP within 5 minutes. "
    "Use tstats where possible. Explain each pipe in the pipeline."
),
```

---

### A2. Add `auto-spl` to `_WS_SIGNALS`

**Why:** Without signal words the test records WARN instead of PASS even when the workspace
returns a fully correct SPL response. These signal words are present in any valid SPL answer
to the A1 prompt.

**Location:** `_WS_SIGNALS` dict, approximately line 672. Add after `auto-security`:

```python
"auto-spl": ["tstats", "index=", "sourcetype", "stats", "count", "threshold", "spl"],
```

---

### A3. Add `auto-spl` to `_WS_MODEL_GROUPS`

**Why:** `auto-spl` routes to `mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit` (MLX)
or `deepseek-coder-v2:16b-lite-instruct-q4_K_M` (Ollama fallback). It is a separate MLX
model from `qwen3-coder-next` used by `auto-coding`, so it needs its own group. Placing it
after `mlx/coding` keeps the two MLX coding models adjacent, minimising proxy switching cost.

**Location:** `_WS_MODEL_GROUPS` list, approximately line 703. Insert the new group **after**
the existing `mlx/coding` group and **before** the `security` group:

```python
    # DeepSeek-Coder-V2-Lite (MLX) — SPL specialist
    (
        "mlx/spl",
        [
            "auto-spl",
        ],
    ),
```

After this insertion the full group order becomes:
`general` → `coding/qwen3.5` → `mlx/coding` → **`mlx/spl`** → `security` → `mlx/reasoning` → `mlx/vision`

---

### A4. Add SPL content-aware routing assertion to S3

**Why:** The router has a dedicated `_SPL_REGEX` and `auto-spl` routing path in
`_detect_workspace()`. S3-17 only validates that security keywords route to `auto-redteam`
via pipeline logs. There is no test that SPL keywords route to `auto-spl`. This is a gap
in coverage for a new routing path.

**Location:** In `async def S3()`, after the existing S3-17 block (approximately line 893)
and before the S3-18 streaming test. Add S3-17b:

```python
    # Content-aware routing: SPL keywords → auto-spl logged
    t0 = time.time()
    code, _ = await _chat(
        "auto",
        "write a splunk tstats search using index= and sourcetype= to count events",
        max_tokens=5,
        timeout=30,
    )
    spl_matches = _grep_logs(
        "portal5-pipeline", r"Auto-routing.*auto-spl|auto-spl.*detected"
    )
    record(
        sec,
        "S3-17b",
        "Content-aware routing: SPL keywords → auto-spl in pipeline logs",
        "PASS" if spl_matches else "WARN",
        "confirmed in logs"
        if spl_matches
        else f"HTTP {code} OK but auto-spl routing log not found — check pipeline logs",
        spl_matches[:2] if spl_matches else [],
        t0=t0,
    )
```

---

### A5. Fix `_chat()` to read `message.reasoning` when `message.content` is empty

**Why:** Reasoning models (DeepSeek-R1, Qwen3 in thinking mode, Magistral with `[THINK]`)
populate `message.reasoning` instead of `message.content` when `max_tokens` is fully
consumed by the thinking chain. The pipeline returns HTTP 200 with an empty `content` field.
`_chat()` currently returns an empty string in this case, causing every downstream test that
checks `text.strip()` to classify the response as empty/failed.

This is a test-side fix. The corresponding pipeline-side fix is in Part B (BLOCKED-1).
Both fixes are needed: the test must be robust to reasoning-model responses regardless of
whether the pipeline fix has been deployed yet, and will work correctly once the pipeline
promotes `reasoning` → `content` itself.

**Location:** `_chat()` function, line 288. The current non-streaming return is:

```python
            return 200, (r.json().get("choices", [{}])[0].get("message", {}).get("content", ""))
```

Replace with:

```python
            msg = r.json().get("choices", [{}])[0].get("message", {})
            return 200, (msg.get("content", "") or msg.get("reasoning", ""))
```

---

### A6. Fix `_persona_test_with_retry()` to read `message.reasoning` fallback

**Why:** Same reasoning-model issue as A5. `_persona_test_with_retry` extracts content
on line 1951 using only `message.content`. Any persona whose `workspace_model` is a
reasoning model (e.g., `deepseek-r1:32b-q4_k_m`, `lmstudio-community/Magistral-Small-2509-MLX-8bit`)
will return empty text and be recorded as WARN.

**Location:** Line 1951. Current code:

```python
            text = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
```

Replace with:

```python
            msg = r.json().get("choices", [{}])[0].get("message", {})
            text = msg.get("content", "") or msg.get("reasoning", "")
```

---

### A7. Remove duplicate `S11-sum` record call

**Why:** `S11-sum` is emitted twice at lines 2091–2113. The result table in
`ACCEPTANCE_RESULTS.md` will contain two identical summary rows with different row numbers.
This does not cause a test failure but inflates the result count and is a copy-paste bug.

**Location:** Lines 2100–2113. Delete the second identical `record(...)` block entirely.
Keep only the first one (lines 2091–2099). The block to delete looks exactly like:

```python
    record(
        sec,
        "S11-sum",
        f"Persona suite summary ({len(PERSONAS)} total)",
        "PASS"
        if failed == 0 and warned < len(PERSONAS) // 4
        else (\"WARN\" if failed == 0 else \"FAIL\"),
        f\"{passed} PASS | {warned} WARN | {failed} FAIL\",
    )
```

---

### A8. Add `splunksplgineer` to `_PERSONA_PROMPT`

**Why:** `splunksplgineer` is the 40th persona YAML. It is not present in `_PERSONA_PROMPT`,
`_PERSONA_SIGNALS`, or `_PERSONAS_BY_MODEL`. As a result, S11 will test it with a generic
fallback prompt and WARN on every run rather than validating domain-specific output.

**Location:** `_PERSONA_PROMPT` dict, approximately line 1607. Add the entry in alphabetical
order (after `softwarequalityassurancetester`, before `sqlterminal`):

```python
    "splunksplgineer": (
        "Write a complete Splunk ES correlation search that detects lateral movement: "
        "a user authenticating to more than 5 distinct hosts within 10 minutes. "
        "Use tstats with the Authentication data model. Include: the full SPL, "
        "a pipe-by-pipe explanation, required data model accelerations, and a "
        "one-line performance verdict (FAST / ACCEPTABLE / SLOW)."
    ),
```

---

### A9. Add `splunksplgineer` to `_PERSONA_SIGNALS`

**Why:** Signal words validate that the persona response is domain-relevant. Without them
the test records WARN even on a correct response.

**Location:** `_PERSONA_SIGNALS` dict, approximately line 1872. Add in alphabetical order
(after `softwarequalityassurancetester`, before `sqlterminal`):

```python
    "splunksplgineer": ["tstats", "authentication", "datamodel", "stats", "distinct", "lateral"],
```

---

### A10. Add `splunksplgineer` to `_PERSONAS_BY_MODEL`

**Why:** `splunksplgineer` has `workspace_model: mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit`.
This model is the same backend as `auto-spl`. There is currently no group in `_PERSONAS_BY_MODEL`
for this model. A new group must be added.

**Location:** `_PERSONAS_BY_MODEL` list, approximately line 1789. The persona uses
`mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit` via `auto-spl`. Insert a new group
**after** the `qwen3-coder-next:30b-q5` group and **before** the `deepseek-r1:32b-q4_k_m`
group to keep MLX coding models together:

```python
    (
        "mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit",
        ["splunksplgineer"],
        "auto-spl",
    ),
```

After this insertion the full `_PERSONAS_BY_MODEL` group order becomes:
1. `qwen3-coder-next:30b-q5` (19 personas, `auto-coding`)
2. **`mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit` (1 persona, `auto-spl`)**
3. `deepseek-r1:32b-q4_k_m` (7 personas, `auto-reasoning`)
4. `dolphin-llama3:8b` (4 personas, `auto`)
5. `xploiter/the-xploiter` (2 personas, `auto-security`)
6. `baronllm:q6_k` (1 persona, `auto-redteam`)
7. `lily-cybersecurity:7b-q4_k_m` (1 persona, `auto-blueteam`)
8. `lazarevtill/Llama-3-WhiteRabbitNeo-8B-v2.0:q4_0` (1 persona, `auto-security`)
9. `Jackrong/MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit` (2 personas, `auto-compliance`)
10. `lmstudio-community/Magistral-Small-2509-MLX-8bit` (1 persona, `auto-mistral`)
11. `mlx-community/gemma-4-26b-a4b-4bit` (1 persona, `auto-vision`)

Total: 40 personas across 11 model groups.

---

## PART B — Protected Product File Fixes

These are the BLOCKED items from `ACCEPTANCE_SUMMARY.md`. They require changes to protected
files. Apply them in order. Run lint after each file change:
`ruff check portal_pipeline/router_pipe.py --fix && ruff format portal_pipeline/router_pipe.py`

---

### B1. BLOCKED-1: Reasoning model `message.reasoning` → `message.content` promotion

**File:** `portal_pipeline/router_pipe.py`  
**Tests fixed:** S3-06 (auto-documents), S3-12 (auto-research), S4-05 (auto-documents round-trip)

**Root cause confirmed:** Direct curl to `POST /v1/chat/completions` with `model: auto-documents`
returns HTTP 200 with `choices[0].message.content = ""` and
`choices[0].message.reasoning = "Okay, the user just said Hello..."`. The thinking chain
consumes all `max_tokens`. Ollama direct confirms the model works correctly. The issue is
that the pipeline passes through the raw backend response unchanged, and callers read only
`message.content`.

**Change location 1 — `_try_non_streaming` function** (approximately line 1197, inside the
`try:` block, immediately after `data = resp.json()`):

Add a normalisation pass before `_record_usage(...)`:

```python
        data = resp.json()

        # Reasoning model normalisation: DeepSeek-R1, Qwen3 thinking mode, and Magistral
        # populate message.reasoning instead of message.content when the thinking chain
        # exhausts max_tokens. Promote reasoning→content so Open WebUI and all callers
        # always find the response in the standard OpenAI content field.
        try:
            for choice in data.get("choices") or []:
                msg = choice.get("message") or {}
                if not msg.get("content") and msg.get("reasoning"):
                    logger.debug(
                        "Backend %s: reasoning→content promotion for workspace=%s "
                        "(thinking chain consumed all tokens)",
                        backend.id,
                        workspace_id,
                    )
                    msg["content"] = msg["reasoning"]
        except Exception:
            pass  # Never let normalisation break a valid response

        _record_usage(
            ...existing args unchanged...
        )
```

**Change location 2 — streaming fallback SSE wrapper** inside `_stream_or_fallback()`
(approximately line 1431). The current content extraction reads:

```python
                            content = msg.get("content", "")
```

Replace with:

```python
                            # Reasoning model fallback: promote reasoning→content
                            content = msg.get("content", "") or msg.get("reasoning", "")
```

---

### B2. BLOCKED-2: `auto-vision` text-only fallback

**File:** `portal_pipeline/router_pipe.py`  
**Test fixed:** S3-16 (auto-vision workspace)

**Root cause confirmed:** `auto-vision` routes to `qwen3-vl:32b` (Ollama) or
`mlx-community/gemma-4-26b-a4b-4bit` (MLX). Both are vision-language models that return
empty `content` for text-only prompts containing no image data. There is no fallback.

**Change location:** In `async def chat_completions`, after the existing `auto` workspace
content-aware routing block (approximately line 1268) and before
`_request_count[workspace_id] = ...`. The existing auto routing block ends with:

```python
        if workspace_id == "auto":
            messages = body.get("messages", [])
            detected = _detect_workspace(messages)
            if detected:
                logger.info("Auto-routing: detected workspace '%s' from message content", detected)
                workspace_id = detected
```

Immediately after that block, add:

```python
        # auto-vision text-only fallback: vision-language models (qwen3-vl:32b, Gemma 4)
        # return empty content when no image is provided. Detect absence of image_url
        # content parts and reroute to auto-reasoning for text-only queries, so users
        # always receive a meaningful response from the auto-vision workspace.
        if workspace_id == "auto-vision":
            messages = body.get("messages", [])
            has_image = any(
                isinstance(part, dict) and part.get("type") == "image_url"
                for msg in messages
                for part in (
                    msg.get("content", [])
                    if isinstance(msg.get("content"), list)
                    else []
                )
            )
            if not has_image:
                logger.info(
                    "auto-vision: no image_url in request — rerouting to auto-reasoning "
                    "for text-only query"
                )
                workspace_id = "auto-reasoning"
```

---

### B3. BLOCKED-3: Streaming — Ollama NDJSON translation and timeout increase

**File:** `portal_pipeline/router_pipe.py`  
**Test fixed:** S3-18 (Streaming response delivers NDJSON chunks)

**Root cause confirmed:** Two separate issues:

**Issue 3a — httpx timeout:** `_http_client` is initialised with
`timeout=httpx.Timeout(120.0, connect=5.0)`. Cold-loading 32B reasoning models under
memory pressure takes 2–4 minutes. The 120s limit kills the connection before the first
token arrives.

**Change:** In `lifespan()`, replace:

```python
    _http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(120.0, connect=5.0),
        ...
    )
```

With:

```python
    # Timeout raised to 300s: cold-loading 32B models under memory pressure takes
    # 2-4 min before the first token. 120s was causing S3-18 streaming timeouts.
    # connect stays 5s — local backends should bind immediately.
    _http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(300.0, connect=5.0),
        ...
    )
```

**Issue 3b — Ollama native NDJSON passthrough:** Ollama's `/api/chat` endpoint returns
bare NDJSON (one JSON object per line, no `data:` prefix). The pipeline declares
`media_type="text/event-stream"` to clients but passes raw NDJSON bytes through unchanged.
Clients expecting SSE-framed `data: {...}\n\n` events receive unrecognised bytes and wait
until timeout.

**Change:** In `_stream_from_backend_guarded()`, replace the entire
`async for chunk in resp.aiter_bytes():` block with logic that:

1. Detects Ollama native format by checking
   `_is_ollama_native = "/api/chat" in url and "/v1/" not in url` (set once before the loop).
2. For Ollama native: decodes each chunk, splits on newlines, parses each line as JSON,
   and for each object:
   - Extracts `message.content` (or falls back to `message.reasoning` for thinking models)
     as `content_delta`.
   - If `content_delta` is non-empty, yields a properly SSE-framed OpenAI chunk:
     `data: {"id": rid, "object": "chat.completion.chunk", "created": ts, "model": workspace_id, "choices": [{"index": 0, "delta": {"content": content_delta}, "finish_reason": null}]}\n\n`
   - If `obj.get("done") == True`: calls `_record_usage(...)` with the final Ollama object
     (which contains `eval_count`, `eval_duration`, etc.), yields a `finish_reason: "stop"`
     chunk, then yields `data: [DONE]\n\n`.
3. For the non-native path (MLX, vLLM, `/v1/` Ollama compat): keep the existing `b'"done"'`
   scan and `b"data: [DONE]"` detection logic exactly as it is today — no changes to that path.

The `rid` and `ts` variables for SSE chunk IDs must be initialised **once before** the
`async for` loop, not inside it on each iteration.

The full `try/except/finally` block structure must be preserved — `_record_response_time`
and the optional `sem.release()` in `finally` must remain in place.

---

### B4. HOWTO §3 workspace table — add Portal SPL Engineer row

**File:** `docs/HOWTO.md`  
**Test fixed:** S14-02 (`§3 workspace table has 16 rows`)

**Root cause:** S14-02 counts lines starting with `| Portal` in HOWTO and compares to
`len(WS_IDS)`. The code has 16 workspace IDs; the §3 table has 15 rows. `auto-spl`
(`Portal SPL Engineer`) is absent.

**Change:** In `docs/HOWTO.md` §3, after the existing `| Portal Mistral Reasoner |` row
(line 80), add:

```
| Portal SPL Engineer | Writing or debugging Splunk SPL queries | DeepSeek-Coder-V2 (MLX) |
```

---

### B5. HOWTO §16 workspace list — add `auto-mistral`

**File:** `docs/HOWTO.md`  
**Test fixed:** S14-05 (`§16 Telegram workspace list complete`)

**Root cause:** S14-05 scans the `Available workspaces:` line in §16 and compares the
set of `auto-*` IDs found against `WS_IDS`. `auto-mistral` is missing.

**Change:** In `docs/HOWTO.md` line 593, the current line is:

```
**Available workspaces:** `auto`, `auto-coding`, `auto-compliance`, `auto-security`, `auto-redteam`, `auto-blueteam`, `auto-creative`, `auto-reasoning`, `auto-documents`, `auto-video`, `auto-music`, `auto-research`, `auto-vision`, `auto-data`, `auto-spl`
```

Replace with (adding `auto-mistral` in alphabetical position between `auto-music` and
`auto-reasoning`):

```
**Available workspaces:** `auto`, `auto-coding`, `auto-compliance`, `auto-mistral`, `auto-security`, `auto-redteam`, `auto-blueteam`, `auto-creative`, `auto-reasoning`, `auto-documents`, `auto-video`, `auto-music`, `auto-research`, `auto-vision`, `auto-data`, `auto-spl`
```

---

### B6. Create missing `workspace_auto_mistral.json`

**File:** `imports/openwebui/workspaces/workspace_auto_mistral.json` (new file)  
**Why:** `scripts/openwebui_init.py` seeds Open WebUI by reading every
`workspace_*.json` file from `imports/openwebui/workspaces/`. `auto-mistral` has no JSON
file, so it is never seeded on `./launch.sh reseed` or fresh installs. `auto-spl` already
has `workspace_auto_spl.json` — `auto-mistral` needs the same.

**Create the file** with this exact content:

```json
{
  "id": "auto-mistral",
  "name": "🧪 Portal Mistral Reasoner",
  "meta": {
    "description": "Structured reasoning via Magistral-Small-2509 — Mistral training lineage, [THINK] mode, distinct failure profile from Qwen/DeepSeek",
    "profile_image_url": "",
    "toolIds": []
  },
  "params": {
    "system": "You are a rigorous structured reasoner using the Magistral reasoning model. Think through problems step by step using [THINK] mode. Make all assumptions explicit. Quantify uncertainty. State what additional information would change your recommendation.",
    "model": "auto-mistral"
  }
}
```

---

### B7. Update `workspaces_all.json` — add `auto-compliance` and `auto-mistral`

**File:** `imports/openwebui/workspaces/workspaces_all.json`  
**Why:** This file is used for bulk GUI import (Admin Panel → Import). It currently has 14
entries, missing `auto-compliance` and `auto-mistral`. While `openwebui_init.py` uses the
individual files (not `workspaces_all.json`), a user doing a manual bulk import would get
an incomplete set.

Read the existing entries in `workspaces_all.json`. Append two new objects to the JSON
array, matching the structure of existing entries. Use the content from
`workspace_auto_compliance.json` and the newly created `workspace_auto_mistral.json`
(B6 above) as the source for each object's fields.

The final array must have 16 entries.

---

## PART C — Update `PORTAL5_ACCEPTANCE_EXECUTE.md`

This file documents the testing methodology for future runs. It needs updating to reflect
the additions made in Parts A and B.

**Location of changes:**

**1. Persona group count in WORKSPACE TESTING section:**  
Current text says `10 unique models across 39 personas`. Update to:

```
11 unique models across 40 personas
```

**2. Persona group order in PERSONA TESTING section:**  
Current text describes 10 groups. Update to reflect the new DeepSeek-Coder-V2 group:

```
PERSONA TESTING (S11):
  - Personas grouped by workspace_model (11 unique models across 40 personas)
  - Order: largest group first (qwen3-coder-next: 19 personas) → DeepSeek-Coder-V2-Lite (1)
    → deepseek-r1 (7) → dolphin (4) → xploiter (2) → single-persona security models
    → MLX compliance (2) → Magistral (1) → Gemma 4 (1) — MLX models last
```

**3. WORKSPACE TESTING section — add auto-spl group to group order description:**  
Current text:
```
Groups ordered: general (dolphin) → coding (qwen3.5) → mlx/coding → security → mlx/reasoning → mlx/vision
```

Update to:
```
Groups ordered: general (dolphin) → coding (qwen3.5) → mlx/coding → mlx/spl → security → mlx/reasoning → mlx/vision
```

**4. Add post-fix run instructions section** at the end of the file:

```
================================================================================
POST-FIX RUN INSTRUCTIONS (after PORTAL5_FIX_TASK.md changes are applied)
================================================================================

After all fixes are committed, rebuild the pipeline container to pick up router_pipe.py
changes, then run the full suite:

1. Rebuild pipeline:
   docker compose -f deploy/portal-5/docker-compose.yml up -d --build portal-pipeline

2. Confirm workspace count matches:
   curl -s http://localhost:9099/health | python3 -m json.tool
   # workspaces must show 16

3. Reseed Open WebUI (picks up new workspace_auto_mistral.json):
   ./launch.sh reseed

4. Run full suite:
   python3 portal5_acceptance_v3.py 2>&1 | tee /tmp/portal5_acceptance_run.log
   echo "Exit: $?"

5. Target result:
   - S3-06 (auto-documents): PASS  — reasoning field promotion fix
   - S3-12 (auto-research): PASS   — reasoning field promotion fix
   - S3-16 (auto-vision): PASS     — text-only fallback to auto-reasoning
   - S3-17b (auto-spl routing): PASS — new SPL content-aware test
   - S3-18 (streaming): PASS       — NDJSON→SSE translation + timeout increase
   - S4-05 (auto-documents round-trip): PASS
   - S11 persona suite: 40/40 tested, splunksplgineer included
   - S14-02 (§3 table rows): PASS  — 16 rows match 16 workspace IDs
   - S14-05 (§16 workspace list): PASS — auto-mistral present
   - Exit code: 0

6. Acceptable non-zero results that do NOT require further fixes:
   - WARN: cold model load (503), ComfyUI/MLX not running, DinD image pull in progress
   - INFO: git SHA, version strings, MLX proxy status
```

---

## Verification Checklist

Run these checks in order after completing all parts.

### 1. Workspace consistency (must print "consistent")
```bash
python3 -c "
import yaml, re
src = open('portal_pipeline/router_pipe.py').read()
s = src.index('WORKSPACES:')
e = src.index('# ── Content-aware', s)
pipe_ids = set(re.findall(r'\"(auto[^\"]*)\": *\{', src[s:e]))
cfg = yaml.safe_load(open('config/backends.yaml'))
yaml_ids = set(cfg['workspace_routing'].keys())
assert pipe_ids == yaml_ids, f'MISMATCH pipe={pipe_ids-yaml_ids} yaml={yaml_ids-pipe_ids}'
print(f'Workspace IDs consistent ({len(pipe_ids)} total)')
"
```

### 2. Persona count match (must print "40 personas, 11 model groups")
```bash
python3 -c "
import yaml
from pathlib import Path
ps = [yaml.safe_load(f.read_text()) for f in Path('config/personas').glob('*.yaml')]
print(f'{len(ps)} persona YAML files')
assert len(ps) == 40, f'Expected 40, got {len(ps)}'
"
```

### 3. Test file workspace/persona coverage (must show no missing)
```bash
python3 -c "
import re, yaml
from pathlib import Path

src = open('portal_pipeline/router_pipe.py').read()
s = src.index('WORKSPACES:')
e = src.index('# ── Content-aware', s)
ws_ids = set(re.findall(r'\"(auto[^\"]*)\": *\{', src[s:e]))

test_src = open('portal5_acceptance_v3.py').read()
ws_prompts = set(re.findall(r'\"(auto[^\"]*)\": ', test_src[:test_src.index('_WS_SIGNALS')]))
missing_prompts = ws_ids - ws_prompts
print(f'Workspaces missing from _WS_PROMPT: {sorted(missing_prompts)}')

personas = [yaml.safe_load(f.read_text()) for f in Path('config/personas').glob('*.yaml')]
slugs = {p['slug'] for p in personas}
prompt_start = test_src.index('_PERSONA_PROMPT')
prompt_end = test_src.index('_PERSONAS_BY_MODEL')
tested_slugs = set(re.findall(r'\"([a-z][^\"]+)\": ', test_src[prompt_start:prompt_end]))
missing_personas = slugs - tested_slugs
print(f'Personas missing from _PERSONA_PROMPT: {sorted(missing_personas)}')
"
```

### 4. Imports directory check (must show 16 workspace JSONs)
```bash
ls imports/openwebui/workspaces/workspace_auto*.json | wc -l
# Must print 16

python3 -c "
import json
d = json.loads(open('imports/openwebui/workspaces/workspaces_all.json').read())
print(f'workspaces_all.json: {len(d)} entries')
ids = sorted(x[\"id\"] for x in d)
print(ids)
assert len(d) == 16
"
```

### 5. Lint (must pass clean)
```bash
ruff check portal_pipeline/router_pipe.py --fix
ruff format portal_pipeline/router_pipe.py
ruff check portal5_acceptance_v3.py --fix
```

### 6. Unit tests (must pass)
```bash
pytest tests/ -v --tb=short
```

### 7. Commit
```bash
git add portal5_acceptance_v3.py \
        PORTAL5_ACCEPTANCE_EXECUTE.md \
        portal_pipeline/router_pipe.py \
        docs/HOWTO.md \
        imports/openwebui/workspaces/workspace_auto_mistral.json \
        imports/openwebui/workspaces/workspaces_all.json
git commit -m "fix(portal5): acceptance test fixes — 40 personas, 16 workspaces, blocked items

Test file (portal5_acceptance_v3.py):
- Add auto-spl to _WS_PROMPT, _WS_SIGNALS, _WS_MODEL_GROUPS (new mlx/spl group)
- Add S3-17b: SPL content-aware routing → auto-spl assertion
- Fix _chat(): read message.reasoning when content empty (reasoning model fallback)
- Fix _persona_test_with_retry(): same reasoning field fallback
- Remove duplicate S11-sum record() call
- Add splunksplgineer to _PERSONA_PROMPT, _PERSONA_SIGNALS, _PERSONAS_BY_MODEL
  (new DeepSeek-Coder-V2-Lite group, tested via auto-spl workspace)

Pipeline (router_pipe.py):
- BLOCKED-1: promote message.reasoning→content in _try_non_streaming and SSE wrapper
- BLOCKED-2: auto-vision text-only fallback to auto-reasoning when no image_url present
- BLOCKED-3: translate Ollama native NDJSON→SSE in _stream_from_backend_guarded
- BLOCKED-3: raise httpx read timeout 120s→300s for cold 32B model loads

Docs (HOWTO.md):
- §3 workspace table: add Portal SPL Engineer row (S14-02)
- §16 workspace list: add auto-mistral (S14-05)

Imports:
- Add imports/openwebui/workspaces/workspace_auto_mistral.json (new)
- Update workspaces_all.json: add auto-compliance and auto-mistral (14→16 entries)

PORTAL5_ACCEPTANCE_EXECUTE.md:
- Update persona counts 39→40, model groups 10→11
- Add auto-spl to workspace group order description
- Add post-fix run instructions section"
```

---

## What Not to Change

- Do **not** modify `config/backends.yaml` — workspace routing is already correct for all 16 workspaces.
- Do **not** modify any `portal_mcp/` files — MCP servers are not involved in these failures.
- Do **not** add new imports to `router_pipe.py` — `json`, `re`, `time`, `asyncio`, and `logger` are already imported.
- Do **not** change `_stream_with_preamble` — the preamble yield, semaphore ownership model, and routing annotation logic are all correct.
- Do **not** change `_detect_workspace` — SPL routing is already implemented and correct.
- Do **not** change the semaphore logic, `_record_usage`, metrics, or notification subsystem.
- Do **not** create a feature branch — commit directly to `main` per `CLAUDE.md`.
- Do **not** run `docker compose down -v` — this will destroy pulled Ollama models.
